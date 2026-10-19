"""Generate a complete transaction catalogue and capture the unchanged FFN RTL."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1] / "sv_ffn_accel"
BUILD = HERE / "capture"
SCENES: list[dict] = []
STEPS: list[str] = []


def bus(rd, addr, value=0, mask=15, stall=0, error=0, expected=None):
    result = f"bus({rd},32'h{addr:08x},32'h{value & 0xffffffff:08x},4'h{mask:x},{stall},{error});"
    if expected is not None:
        result += f" check_data(32'h{expected & 0xffffffff:08x});"
    return result


def scene(group, title, description, code, *, kind="read", address=None, value=None,
          error=False, focus=None, note="", expected=None):
    idx = len(SCENES)
    SCENES.append(dict(id=idx, group=group, title=title, description=description,
                       kind=kind, address=address, value=value, error=error,
                       focus=focus or [], note=note, expected=expected))
    STEPS.append(f"begin_case({idx});\n{code}\nend_case();")


REGS = [
    (0x00, "CONTROL", 0, "读取恒为0；START与清除位是写命令，不保存为可读位。"),
    (0x04, "STATUS", 0, "bit0为BUSY，bit1为DONE；读取不会清除完成标志。"),
    (0x08, "CYCLES", 0, "显示当前或最近一次任务的核心活动拍数。"),
    (0x0c, "MAC_COUNT", 1622016, "固定任务包含99×64×256次乘累加，不是实时进度计数。"),
    (0x10, "M", 99, "固定输入行数99，不能通过写寄存器调整。"),
    (0x14, "K", 64, "固定点积长度64，不能通过写寄存器调整。"),
    (0x18, "N", 256, "固定输出列数256，不能通过写寄存器调整。"),
    (0x1c, "FORMAT", 0x810, "0x0810：高8位表示8位小数，低8位表示16位数据。"),
    (0x20, "LAYER_TAG", 0, "层号只是一项软件标签；不会自动切换权重。"),
    (0x24, "SATURATIONS", 0, "输出超出有符号16位范围时计数；每次START清零。"),
    (0x28, "VERSION", 0x10000, "当前版本号0x00010000。"),
]
MEM = [
    ("X[0,0]", 0x10000, 0x180, ["x_en", "x_we", "x_addr", "x_rdata"]),
    ("X[98,63]", 0x162fc, 0xff00, ["x_en", "x_we", "x_addr", "x_rdata"]),
    ("W[0,0]", 0x20000, 0xa5a5ff00, ["w_en", "w_we", "w_addr0", "w_rdata0"]),
    ("W[63,255]", 0x2fffc, 0x80, ["w_en", "w_we", "w_addr15", "w_rdata15"]),
    ("b[0]", 0x30000, 0x80, ["b_en", "b_we", "b_addr", "b_rdata"]),
    ("b[255]", 0x303fc, 0x100, ["b_en", "b_we", "b_addr", "b_rdata"]),
]


def catalogue():
    for name, addr, val, focus in MEM:
        s16 = (val & 0xffff) - (65536 if val & 0x8000 else 0)
        scene("数据写入", f"写 {name}",
              f"局部地址0x{addr:05X}；写数据低16位编码{s16}，实数{s16/256:g}。命令接受沿直接写SRAM，沿后给出写响应。",
              bus(0, addr, val), kind="write", address=addr, value=val, focus=focus,
              note="所有写事务都要求wmask=0xF。W[0,0]示例故意把高16位设为0xA5A5，存储器只保存低16位。")
    for name, addr, val, focus in MEM:
        expected = (val & 0xffff) - (65536 if val & 0x8000 else 0)
        scene("数据读回", f"读 {name}", "同步SRAM读取：接受命令后进入H_READ，下一上升沿寄存响应；负数符号扩展到32位。",
              bus(1, addr, expected=expected), address=addr, focus=focus, expected=expected & 0xffffffff)
    for addr, name, val, note in REGS:
        scene("寄存器读取", f"空闲时读 {name}", note,
              bus(1, addr, expected=val), address=addr, expected=val,
              focus=["host_state", "busy", "done", "cycles", "layer_tag", "saturations"])
    for val in [0, 11]:
        scene("控制与层号", f"写 LAYER_TAG = {val}", "空闲时可以写0…11，命令握手沿更新标签；不会装载参数或自动启动。",
              bus(0, 0x20, val) + f"\nif(dut.layer_tag!==4'd{val})$fatal(1,\"TAG did not update\");",
              kind="write", address=0x20, value=val, focus=["layer_tag", "busy"])
    for val in [0, 2]:
        scene("控制与层号", f"空闲时写 CONTROL = {val}", "写0不触发动作。写2清DONE/IRQ，不清SRAM，也不清周期计数。此时DONE原本为0。",
              bus(0, 0, val), kind="write", address=0, value=val, focus=["state", "busy", "done", "irq"])
    scene("握手与等待", "寄存器读响应反压", "主机在响应有效后继续拉低rsp_ready 3拍；模块保持VALID、DATA、ERR，拒绝新命令。",
          bus(1, 0x10, stall=3, expected=99), address=0x10)
    scene("握手与等待", "SRAM读响应反压", "同步读多一拍；响应一旦产生，即使主机暂不接收，读数据仍保持。",
          bus(1, 0x10000, stall=3, expected=384), address=0x10000, focus=["x_en", "x_rdata"])
    scene("握手与等待", "写响应反压", "SRAM在命令握手沿已经写入。延迟接收写响应不会重复写入。",
          bus(0, 0x10000, 384, stall=3), kind="write", address=0x10000, value=384, focus=["x_en", "x_we"])
    scene("握手与等待", "下一命令提前到达，等待READY", "先读M，在旧响应等待期间提出读K并保持命令。旧响应消费沿前cmd_ready仍为0，下一沿才能接受新命令。",
          "queued_commands();", kind="sequence", focus=["host_state"])
    scene("握手与等待", "VALID为0，地址变化不触发访问", "主机可以在cmd_valid=0时改变地址与数据；没有命令握手，也没有响应或写入。",
          "@(negedge clk);cmd_addr=32'h10000;cmd_wdata=32'hdeadbeef;cmd_read=0;repeat(3)@(negedge clk);",
          kind="observe", focus=["x_en", "x_we"])
    for addr, name, _, _ in REGS:
        if addr in (0, 0x20):
            continue
        scene("错误与保护", f"错误：写只读寄存器 {name}", "地址有效，但这个寄存器只允许读；返回rsp_err=1和rdata=0，不改变寄存器。",
              bus(0, addr, 123, error=1, expected=0), kind="write", address=addr, value=123, error=True)
    invalid = [
        ("写只读Y窗口", 0, 0x40000, 1, 15, "Y只能由计算核心写入，主机只能读取。"),
        ("读未映射地址", 1, 0x60000, 0, 15, "0x60000不在任何数据窗口或寄存器地址中。"),
        ("写未映射地址", 0, 0x60000, 1, 15, "无地址目标，返回错误且无写入。"),
        ("读未对齐地址", 1, 0x10001, 0, 15, "所有访问必须4字节对齐，地址低2位必须为0。"),
        ("写未对齐地址", 0, 0x10002, 1, 15, "数据虽只有16位，也不能发出半字地址访问。"),
        ("写掩码0x3", 0, 0x10000, 1, 3, "本实现拒绝部分字节写入，即使只需写16位也要求wmask=0xF。"),
        ("写掩码0x0", 0, 0x10000, 1, 0, "零掩码写入也报错，并非无操作事务。"),
        ("层号超出范围", 0, 0x20, 12, 15, "LAYER_TAG整字写值只能为0…11。"),
        ("CONTROL保留位为1", 0, 0, 4, 15, "CONTROL只允许bit0与bit1，写bit2触发错误。"),
        ("X窗口越过末地址", 1, 0x16300, 0, 15, "X的最后有效元素地址是0x162FC，0x16300已越界。"),
        ("b窗口越过末地址", 1, 0x30400, 0, 15, "b的最后有效元素地址是0x303FC。"),
        ("Y窗口越过末地址", 1, 0x58c00, 0, 15, "Y的最后有效元素地址是0x58BFC。"),
    ]
    for name, rd, addr, val, mask, note in invalid:
        scene("错误与保护", "错误：" + name, note, bus(rd, addr, val, mask, error=1, expected=0),
              kind="read" if rd else "write", address=addr, value=val if not rd else None, error=True)
    scene("握手与等待", "错误响应也支持反压", "非法访问同样产生一个必须被接收的响应；ERR与DATA在等待中保持。",
          bus(1, 0x60000, stall=3, error=1, expected=0), address=0x60000, error=True)
    scene("握手与等待", "读事务忽略写掩码", "wmask只约束写事务。本次读M把wmask置0，仍然正常返回99。",
          bus(1, 0x10, mask=0, expected=99), address=0x10)
    scene("控制与层号", "START：写 CONTROL = 1", "X/W/b已经通过总线完整装载。命令接受沿启动计算，沿后BUSY=1、CYCLES=0；写响应不代表运算完成。",
          bus(0, 0, 1), kind="write", address=0, value=1, focus=["state", "busy", "cycles", "done", "irq"])
    for addr, name, val, note in REGS:
        expected = 1 if addr == 4 else 11 if addr == 0x20 else None if addr in (8, 0x24) else val
        scene("忙时访问", f"运行中读 {name}", "核心继续计算，总线仍可读取寄存器。" + note,
              bus(1, addr, expected=expected), address=addr,
              focus=["state", "busy", "cycles", "done", "layer_tag", "saturations"], expected=expected)
    for name, addr in [("X", 0x10000), ("W", 0x20000), ("b", 0x30000), ("Y", 0x40000)]:
        for rd in [1, 0]:
            scene("忙时访问", f"错误：运行中{'读' if rd else '写'} {name}",
                  "核心独占数据存储器，主机访问直接报错，不会等到空闲。原计算继续；Y写入同时违反只读规则。" if name == "Y" else "核心独占数据存储器，主机访问直接报错，不会等到空闲；原计算继续。",
                  bus(rd, addr, error=1, expected=0), kind="read" if rd else "write", address=addr,
                  error=True, focus=["busy", "cycles", "state"])
    for val in [1, 3]:
        scene("忙时访问", f"错误：运行中写 CONTROL = {val}", "bit0要求启动新任务，但BUSY=1。整条命令被拒绝，不重启，也不执行其中的清除动作。",
              bus(0, 0, val, error=1, expected=0), kind="write", address=0, value=val, error=True,
              focus=["busy", "cycles", "done", "state"])
    scene("忙时访问", "错误：运行中修改 LAYER_TAG", "运行中禁止写层号，保持原先标签11。",
          bus(0, 0x20, 0, error=1, expected=0), kind="write", address=0x20, value=0, error=True, focus=["layer_tag", "busy"])
    for val in [0, 2]:
        scene("忙时访问", f"运行中写 CONTROL = {val}", "写0是无操作；写2是清DONE/IRQ。两者都不取消计算，CYCLES继续增加。",
              bus(0, 0, val), kind="write", address=0, value=val, focus=["state", "busy", "cycles", "done", "irq"])
    STEPS.append("while(dut.cycle_count<158394)@(negedge clk);")
    scene("完成与复位", "最后一次写回 → DONE / IRQ", "这里只展开整层计算的末尾。前面的计算已在RTL中实际执行；最后一个Y元素写入的同一沿置DONE/IRQ。",
          "while(!irq)@(negedge clk);repeat(2)@(negedge clk);if(dut.cycle_count!==158400)$fatal(1,\"cycle count\");",
          kind="observe", focus=["state", "cycles", "y_en", "y_we", "y_addr", "y_wdata", "busy", "done", "irq"])
    for addr, name, val in [(4, "STATUS", 2), (8, "CYCLES", 158400), (0x24, "SATURATIONS", 0)]:
        scene("完成与复位", f"完成后读 {name}", "任务完成后BUSY=0，DONE与IRQ保持为1；读取寄存器不会应答中断。",
              bus(1, addr, expected=val), address=addr, expected=val, focus=["busy", "done", "irq", "cycles"])
    for name, addr, val in [("Y[0,0]", 0x40000, -256), ("Y[98,255]", 0x58bfc, 128)]:
        scene("数据读回", f"完成后读 {name}", f"结果的Q8.8整数编码为{val}，实数为{val/256:g}。Y按同步SRAM方式读取，负数符号扩展。",
              bus(1, addr, expected=val), address=addr, expected=val & 0xffffffff, focus=["y_en", "y_we", "y_addr", "y_rdata", "done"])
    scene("控制与层号", "完成后清除 DONE / IRQ", "写CONTROL=2，在命令接受沿清除DONE与IRQ，结果SRAM及CYCLES保持。",
          bus(0, 0, 2), kind="write", address=0, value=2, focus=["done", "irq", "cycles", "busy"])
    scene("完成与复位", "清除后读 STATUS", "读回0：BUSY=0且DONE=0。清完成标志没有擦除结果。",
          bus(1, 4, expected=0), address=4, expected=0, focus=["done", "irq", "busy"])
    scene("控制与层号", "CONTROL = 3：清除并启动", "空闲时写3合法，清除完成标志并启动新任务；周期计数从158400清零。",
          bus(0, 0, 3), kind="write", address=0, value=3, focus=["state", "busy", "cycles", "done", "irq"])
    scene("完成与复位", "运行中异步复位", "rst_n在下降沿拉低，异步复位在下一上升沿之前已清状态。SRAM内容保留，当前任务被中止。复位释放应由实际平台同步。",
          "reset_dut();", kind="reset", focus=["rst_n", "state", "busy", "cycles", "done", "irq"])
    scene("握手与等待", "START响应等待时，计算继续", "写START后延迟5拍接收响应。总线等待rsp_ready，但核心已独立工作，CYCLES持续增加。",
          bus(0, 0, 1, stall=5), kind="write", address=0, value=1, focus=["state", "busy", "cycles", "b_en"])
    STEPS.append("while(!irq)@(negedge clk);")
    scene("控制与层号", "DONE未清时再次 START", "前一任务已实际运行至完成。无需先写2，空闲时新的START本身就会清旧DONE/IRQ并把计数清零。",
          bus(0, 0, 1), kind="write", address=0, value=1, focus=["done", "irq", "busy", "cycles", "state"])
    STEPS.append("reset_dut();")
    scene("完成与复位", "同步SRAM读等待中复位", "读命令已接受，状态进入H_READ；在响应产生前拉低rst_n，取消未完成事务，不留下旧响应。",
          "begin_read_then_reset(0);", kind="reset", focus=["rst_n", "host_state", "x_en", "x_rdata"])
    scene("完成与复位", "响应被反压时复位", "寄存器响应已经有效，但主机未接收。复位清除rsp_valid；释放后可重新提交命令。",
          "begin_read_then_reset(1);", kind="reset", focus=["rst_n", "host_state", "rsp_valid"])
    scene("完成与复位", "复位后读 STATUS", "复位后BUSY、DONE和周期计数均清零，SRAM没有复位。",
          bus(1, 4, expected=0), address=4, expected=0, focus=["rst_n", "busy", "done", "cycles"])
    scene("完成与复位", "复位后数据仍保留", "读取X[0,0]仍得到384（实数1.5）。复位中止状态机而不清存储；旧Y不能当作被中止任务的完整结果。",
          bus(1, 0x10000, expected=384), address=0x10000, expected=384, focus=["x_en", "x_rdata", "busy", "done"])


SIGNALS = {
    "rst_n": "rst_n", "cmd_valid": "cmd_valid", "cmd_ready": "cmd_ready", "cmd_read": "cmd_read",
    "cmd_addr": "cmd_addr", "cmd_wdata": "cmd_wdata", "cmd_wmask": "cmd_wmask",
    "rsp_valid": "rsp_valid", "rsp_ready": "rsp_ready", "rsp_err": "rsp_err", "rsp_rdata": "rsp_rdata",
    "host_state": "dut.host_state", "state": "dut.state", "busy": "dut.busy", "done": "dut.done", "irq": "irq",
    "cycles": "dut.cycle_count", "layer_tag": "dut.layer_tag", "saturations": "dut.saturation_count",
    "dec_error": "dut.dec_error", "start_event": "dut.start_event", "clear_done": "dut.clear_done",
    "x_en": "dut.x_en", "x_we": "dut.x_we", "x_addr": "dut.x_addr", "x_rdata": "dut.x_rdata",
    "w_en": "dut.w_en", "w_we": "dut.w_we", "w_addr0": "dut.w_addr[0]", "w_addr15": "dut.w_addr[15]",
    "w_rdata0": "dut.w_rdata[0]", "w_rdata15": "dut.w_rdata[15]",
    "b_en": "dut.b_en", "b_we": "dut.b_we", "b_addr": "dut.b_addr", "b_rdata": "dut.b_rdata",
    "y_en": "dut.y_en", "y_we": "dut.y_we", "y_addr": "dut.y_addr", "y_wdata": "dut.y_wdata", "y_rdata": "dut.y_rdata",
}

TB = r'''`timescale 1ns/1ps
module tb_transactions;
reg clk=0; always #5 clk=~clk; // 10 ns teaching clock; cycle relationships are unchanged.
reg rst_n=0,cmd_valid=0,cmd_read=0,rsp_ready=0;
reg [31:0] cmd_addr=0,cmd_wdata=0;
reg [3:0] cmd_wmask=15;
wire cmd_ready,rsp_valid,rsp_err,irq;
wire [31:0] rsp_rdata;
ffn_accel dut(.clk(clk),.rst_n(rst_n),.i_icb_cmd_valid(cmd_valid),.o_icb_cmd_ready(cmd_ready),
 .i_icb_cmd_read(cmd_read),.i_icb_cmd_addr(cmd_addr),.i_icb_cmd_wdata(cmd_wdata),.i_icb_cmd_wmask(cmd_wmask),
 .o_icb_rsp_valid(rsp_valid),.i_icb_rsp_ready(rsp_ready),.o_icb_rsp_rdata(rsp_rdata),.o_icb_rsp_err(rsp_err),.o_irq(irq));
integer fd,scenario=-1,edge_no=0;
reg [31:0] readback;
task snapshot;
begin
__SNAPSHOT__
end
endtask
always @(posedge clk)begin
 edge_no=edge_no+1;
 if(scenario>=0)begin
  $fwrite(fd,"{\"scene\":%0d,\"edge\":%0d,\"time_ps\":%0t,\"pre\":",scenario,edge_no,$realtime);
  snapshot(); #0.001; $fwrite(fd,",\"post\":"); snapshot(); $fwrite(fd,"}\n");
 end
end
task automatic begin_case(input integer number);
begin scenario=number;repeat(2)@(negedge clk);end endtask
task automatic end_case;
begin repeat(2)@(negedge clk);scenario=-1;end endtask
task automatic check_data(input reg[31:0] want);
begin if(readback!==want)$fatal(1,"scene=%0d got=%h expected=%h",scenario,readback,want);end endtask
task automatic bus(input bit rd,input reg[31:0] addr,input reg[31:0] data,
 input reg[3:0] mask,input integer stall,input bit want_error);
begin
 @(negedge clk);cmd_valid=1;cmd_read=rd;cmd_addr=addr;cmd_wdata=data;cmd_wmask=mask;rsp_ready=0;
 while(!cmd_ready)@(negedge clk);
 @(posedge clk);@(negedge clk);cmd_valid=0;
 while(!rsp_valid)@(negedge clk);
 repeat(stall)@(negedge clk);
 if(rsp_err!==want_error)$fatal(1,"scene=%0d addr=%h error mismatch",scenario,addr);
 readback=rsp_rdata;rsp_ready=1;
 @(posedge clk);@(negedge clk);rsp_ready=0;
end endtask
task automatic reset_dut;
begin
 @(negedge clk);rst_n=0;cmd_valid=0;rsp_ready=0;
 repeat(3)@(negedge clk);rst_n=1;repeat(2)@(negedge clk);
end endtask
task automatic queued_commands;
begin
 @(negedge clk);cmd_valid=1;cmd_read=1;cmd_addr=32'h10;cmd_wmask=15;rsp_ready=0;
 @(posedge clk);@(negedge clk);cmd_addr=32'h14;
 repeat(3)@(negedge clk);
 if(cmd_ready!==0 || rsp_rdata!==99)$fatal(1,"queue response");
 rsp_ready=1;
 @(posedge clk);@(negedge clk);rsp_ready=0;
 @(posedge clk);@(negedge clk);cmd_valid=0;
 if(rsp_valid!==1 || rsp_rdata!==64)$fatal(1,"queued K response");
 rsp_ready=1;@(posedge clk);@(negedge clk);rsp_ready=0;
end endtask
task automatic begin_read_then_reset(input bit response_phase);
begin
 @(negedge clk);cmd_valid=1;cmd_read=1;cmd_addr=response_phase?32'h10:32'h10000;cmd_wmask=15;rsp_ready=0;
 @(posedge clk);@(negedge clk);cmd_valid=0;
 // Reset now, between command and the next sampling edge. For SRAM H_READ is active.
 rst_n=0;repeat(3)@(negedge clk);rst_n=1;repeat(2)@(negedge clk);
 if(rsp_valid!==0)$fatal(1,"stale response after reset");
end endtask
initial begin
 fd=$fopen("trace.jsonl","w");if(!fd)$fatal(1,"trace open");
 repeat(4)@(negedge clk);rst_n=1;repeat(2)@(negedge clk);
 // Full-size memory initialization is exclusively through the public bus.
 for(integer i=0;i<6336;i=i+1)bus(0,32'h10000+4*i,0,15,0,0);
 for(integer i=0;i<16384;i=i+1)bus(0,32'h20000+4*i,0,15,0,0);
 for(integer i=0;i<256;i=i+1)bus(0,32'h30000+4*i,0,15,0,0);
__STEPS__
 $fclose(fd);$display("TRANSACTION TRACE PASS");$finish;
end
initial begin #10000000;$fatal(1,"watchdog");end
endmodule
'''


def generate_tb():
    snapshot = ['$fwrite(fd,"{");']
    for i, (key, expression) in enumerate(SIGNALS.items()):
        suffix = "," if i < len(SIGNALS) - 1 else "}"
        snapshot.append(f'$fwrite(fd,"\\\"{key}\\\":\\\"%0d\\\"{suffix}",{expression});')
    return TB.replace("__SNAPSHOT__", "\n".join(snapshot)).replace("__STEPS__", "\n".join(STEPS))


def verify(groups):
    checks = 0
    for s, frames in zip(SCENES, groups):
        assert frames, s["title"]
        assert all(b["time_ps"]-a["time_ps"] == 10000 for a, b in zip(frames, frames[1:])), s["title"]
        commands = 0
        for idx, f in enumerate(frames):
            p, q = f["pre"], f["post"]
            if not p["rst_n"]:
                assert q["busy"] == q["done"] == q["rsp_valid"] == q["cmd_ready"] == 0
                checks += 1
                continue
            assert q["irq"] == q["done"]
            if p["rsp_valid"] and not p["rsp_ready"]:
                assert all(p[k] == q[k] for k in ("rsp_valid", "rsp_rdata", "rsp_err"))
                assert q["cmd_ready"] == 0
                checks += 1
            if p["cmd_valid"] and p["cmd_ready"]:
                commands += 1
                assert q["rsp_err"] == int(s["error"]), s["title"]
                memread = p["cmd_read"] and p["cmd_addr"] >= 0x10000 and not s["error"]
                assert q["host_state"] == (1 if memread else 2), s["title"]
                assert q["rsp_valid"] == (0 if memread else 1)
                if s["error"]:
                    assert q["rsp_rdata"] == 0 and not p["start_event"]
                    assert not p["clear_done"]
                if s["expected"] is not None:
                    r = frames[idx+1]["post"] if memread else q
                    assert r["rsp_rdata"] == s["expected"] & 0xffffffff, s["title"]
                if p["start_event"]:
                    assert q["busy"] == 1 and q["done"] == 0 and q["cycles"] == 0
                checks += 1
            if p["rsp_valid"] and p["rsp_ready"]:
                assert not p["cmd_ready"] and not q["rsp_valid"] and q["cmd_ready"]
                checks += 1
        if s["kind"] in ("read", "write"):
            assert commands == 1, (s["title"], commands)
    finish = next(g for s, g in zip(SCENES, groups) if s["title"].startswith("最后一次"))
    done = next(f for f in finish if not f["pre"]["done"] and f["post"]["done"])
    assert done["post"]["cycles"] == 158400 and done["pre"]["y_we"] == 1
    assert done["pre"]["y_addr"] == 25343
    return checks


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--pack-only", action="store_true")
    parser.add_argument("--capture-only", action="store_true")
    args = parser.parse_args()
    BUILD.mkdir(exist_ok=True)
    catalogue()
    sources = [ROOT / "rtl/ffn_numeric_pkg.sv", ROOT / "rtl/ffn_sram_1rw.sv", ROOT / "rtl/ffn_accel.sv"]
    tb = BUILD / "tb_transactions.sv"
    if not args.pack_only:
        tb.write_text(generate_tb(), encoding="utf-8")
        compiler = shutil.which("iverilog") or "iverilog"
        simulator = shutil.which("vvp") or "vvp"
        commands = [[compiler, "-g2012", "-s", "tb_transactions", "-o", str(BUILD / "sim.vvp"), *map(str, sources), str(tb)],
                    [simulator, str(BUILD / "sim.vvp")]]
        for cmd in commands:
            run = subprocess.run(cmd, cwd=BUILD, capture_output=True, text=True)
            if run.returncode:
                raise RuntimeError(run.stdout + run.stderr)
            if run.stdout:
                print(run.stdout, flush=True)
        groups = [[] for _ in SCENES]
        for line in (BUILD / "trace.jsonl").read_text(encoding="utf-8").splitlines():
            f = json.loads(line)
            for phase in ["pre", "post"]:
                f[phase] = {k: int(v) if v.lstrip("-").isdigit() else None for k, v in f[phase].items()}
            groups[f["scene"]].append(f)
        checks = verify(groups)
        for s, frames in zip(SCENES, groups):
            s["frames"] = frames
        hashes = {str(p.relative_to(ROOT)): hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
        data = dict(meta=dict(clock_period_ps=10000, post_delay_ps=1, source="Icarus Verilog / unchanged RTL",
                             checks=checks, cases=len(SCENES), frames=sum(map(len, groups)), hashes=hashes,
                             tb_sha256=hashlib.sha256(tb.read_bytes()).hexdigest(), synthetic=True), scenes=SCENES)
        (BUILD / "data.json").write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    else:
        data = json.loads((BUILD / "data.json").read_text(encoding="utf-8"))
        for name, digest in data["meta"]["hashes"].items():
            assert hashlib.sha256((ROOT / name).read_bytes()).hexdigest() == digest, name
        assert hashlib.sha256(tb.read_bytes()).hexdigest() == data["meta"]["tb_sha256"]
    if args.capture_only:
        print(f"Captured and checked {data['meta']['cases']} scenes / {data['meta']['frames']} edges", flush=True)
        return
    template = (HERE / "template.html").read_text(encoding="utf-8")
    js = (HERE / "app.js").read_text(encoding="utf-8")
    html = template.replace("__TRACE_DATA__", json.dumps(data, ensure_ascii=False, separators=(",", ":"))).replace("__APP_JS__", js)
    (HERE / "index.html").write_text(html, encoding="utf-8")
    summary = dict(data["meta"], status="PASS", categories={g: sum(s["group"]==g for s in data["scenes"]) for g in dict.fromkeys(s["group"] for s in data["scenes"])})
    (BUILD / "verification.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2), flush=True)
    print("HTML:", HERE / "index.html", flush=True)


if __name__ == "__main__":
    main()
