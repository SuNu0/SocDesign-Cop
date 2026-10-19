"""Draw reviewable, code-native logical schematics of the current FFN RTL."""
from pathlib import Path
from html import escape
import hashlib
import json

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
RTL = PROJECT / "sv_ffn_accel/rtl"

COLORS = {"host": "#327d77", "mem": "#4678a3", "core": "#7766a0", "ctrl": "#ac6837", "plain": "#526a62"}
FILLS = {"host": "#edf7f2", "mem": "#eef5fb", "core": "#f3f0fa", "ctrl": "#fcf3e8", "plain": "#f6f8f3"}


class Drawing:
    def __init__(self, number, title, subtitle, width=1700, height=1120):
        self.width, self.height = width, height
        self.parts = [f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}" role="img" aria-label="{escape(title)}">',
                      '<defs>' + ''.join(f'<marker id="arrow-{k}" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto-start-reverse"><path d="M0 0 L10 5 L0 10 Z" fill="{v}"/></marker>' for k, v in COLORS.items()) + '</defs>',
                      '<style>text{font-family:"Microsoft YaHei","Segoe UI",sans-serif;fill:#243d37}.mono{font-family:Consolas,"Cascadia Code",monospace}.wire{fill:none;stroke-linejoin:round;stroke-linecap:round}.block{cursor:pointer}.block:hover .outline{stroke-width:2.5}.focus-dim{opacity:.12}.focus-on .outline{stroke-width:3}.focus-on.wire{stroke-width:3.8}</style>',
                      f'<rect width="{width}" height="{height}" fill="#fafbf8"/>']
        self.text(38, 35, f"FFN_ACCEL  /  RTL LOGICAL SCHEMATIC  /  SHEET {number:02d}", 12, "#6b8074", mono=True)
        self.text(38, 77, title, 29, weight=700)
        self.text(39, 104, subtitle, 13, "#6b8074")

    def text(self, x, y, text, size=13, color="#243d37", weight=400, mono=False, anchor="start"):
        self.parts.append(f'<text x="{x}" y="{y}" font-size="{size}" font-weight="{weight}" text-anchor="{anchor}" style="fill:{color}"{chr(32)+"class=\"mono\"" if mono else ""}>{escape(str(text))}</text>')

    def block(self, x, y, w, h, title, lines=(), kind="plain", key="", routes="", info=""):
        description=info or title + ("：" + "；".join(lines) if lines else "")
        self.parts.append(f'<g class="block" data-key="{key}" data-routes="{routes}" data-info="{escape(description, quote=True)}" tabindex="0" role="button" aria-label="{escape(title, quote=True)}"><title>{escape(description)}</title>')
        self.parts.append(f'<rect class="outline" x="{x}" y="{y}" width="{w}" height="{h}" rx="9" fill="{FILLS[kind]}" stroke="{COLORS[kind]}" stroke-width="1.4"/>')
        self.parts.append(f'<rect x="{x}" y="{y+13}" width="4" height="{h-26}" rx="2" fill="{COLORS[kind]}"/>')
        self.text(x+16, y+28, title, 16, COLORS[kind], 700)
        for i, line in enumerate(lines):
            self.text(x+16, y+52+i*20, line, 12, "#526a62", mono=all(ord(c)<128 for c in line))
        self.parts.append('</g>')

    def wire(self, points, label="", kind="plain", dashed=False, routes="", label_at=None, arrow=True):
        d = "M" + " L".join(f"{x},{y}" for x, y in points)
        self.parts.append(f'<path class="wire" data-routes="{routes}" d="{d}" stroke="{COLORS[kind]}" stroke-width="1.8"'+(' stroke-dasharray="6 5"' if dashed else '')+(f' marker-end="url(#arrow-{kind})"' if arrow else '')+'/>')
        if label:
            x, y = label_at or ((points[0][0]+points[-1][0])/2, (points[0][1]+points[-1][1])/2-8)
            self.parts.append(f'<g class="wirelabel" data-routes="{routes}">')
            self.text(x, y, label, 11, COLORS[kind], mono=all(ord(c)<128 for c in label), anchor="middle")
            self.parts.append('</g>')

    def frame(self, x, y, w, h, label, color="#bfcfc1"):
        self.parts.append(f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="12" fill="none" stroke="{color}" stroke-width="1.3" stroke-dasharray="8 5"/>')
        self.text(x+17, y+23, label, 12, "#708976", 600)

    def note(self, x, y, lines, color="#6b8074", size=12):
        for i, line in enumerate(lines):
            self.text(x, y+i*20, line, size, color)

    def finish(self, foot):
        self.parts.append(f'<line x1="38" x2="{self.width-38}" y1="{self.height-56}" y2="{self.height-56}" stroke="#dce5d8"/>')
        self.text(39, self.height-30, foot, 11, "#728675")
        self.text(self.width-40, self.height-30, "99 × 64 · 64 × 256 → 99 × 256", 11, "#728675", mono=True, anchor="end")
        self.parts.append('</svg>')
        return '\n'.join(self.parts)


def overview():
    d = Drawing(1, "整体连接：主机如何访问、硬件如何计算", "实线为数据/请求通路，虚线为调度与状态。框内功能直接对应当前ffn_accel.sv，详图见后续图纸。", 1800, 1180)
    d.frame(285, 132, 1470, 941, "ffn_accel 顶层边界 · 各功能框为逻辑划分")
    d.block(35, 200, 205, 192, "外部主机", ["当前：SystemVerilog测试平台", "后续：E203平台接入", "提供局部地址与写数据", "接收响应并检查rsp_err"], "host", "host", "xwrite read core", "主机发起总线读写；平台地址译码应先减去外设基地址，再把局部字节地址送到加速器。")
    d.block(335, 188, 295, 172, "命令接收 + 地址译码", ["cmd_addr[31:0] / wdata[31:0]", "cmd_read / wmask[3:0]", "accept = cmd_valid & cmd_ready", "生成dec_mem / dec_index / err"], "host", "decode", "xwrite read core", "cmd_ready=rst_n且host_state为H_IDLE。只有命令握手才触发访问；错误访问仍返回响应。")
    d.block(720, 188, 320, 172, "控制 / 状态 / 计数", ["CONTROL / STATUS / LAYER_TAG", "CYCLES / SATURATIONS", "M=99, K=64, N=256", "DONE保持，o_irq = DONE"], "ctrl", "regs", "core read", "寄存器不是数据SRAM。CONTROL写1启动、写2清DONE，读STATUS不会清IRQ。")
    d.block(1150, 188, 450, 172, "计算FSM + 地址发生器", ["S_IDLE → BIAS → MAC → ROUND → WRITE", "row_index[6:0] / group_index[3:0]", "mac_issue：0…63 / write_lane：0…15", "产生各SRAM的核心地址、en、we"], "ctrl", "ctrl", "core", "核心状态机与总线响应状态机独立运行。运行时核心独占数据存储端口。")
    d.wire([(240,250),(335,250)], "命令", "host", routes="xwrite read core", label_at=(287,239))
    d.wire([(335,307),(240,307)], "cmd_ready", "host", routes="xwrite read core", label_at=(287,295))
    d.wire([(630,240),(720,240)], "寄存器访问", "host", routes="read core", label_at=(674,229))
    d.wire([(1040,240),(1150,240)], "START / 清DONE", "ctrl", True, "core", label_at=(1094,228))
    d.wire([(1370,360),(1370,388),(670,388),(670,460),(630,460)], "核心地址与使能", "ctrl", True, "core", label_at=(970,380))
    d.wire([(1150,302),(1040,302)], "BUSY / DONE / 计数", "ctrl", True, "core read", label_at=(1095,327))
    d.block(335, 430, 295, 220, "存储访问选择", ["空闲：host_mem选择主机请求", "运行：计算FSM提供请求", "主机忙时访问数据 → 返回错误", "X / W / b：主机可读写", "Y：主机只读，核心可写"], "host", "access", "xwrite read core", "存储器均为单端口；本设计通过访问选择保证主机与核心不会争用同一个存储端口。")
    d.wire([(485,360),(485,430)], "dec_mem / dec_index", "host", routes="xwrite read", label_at=(562,406))
    mems = [(430,"X 输入SRAM",["6336 × 16 bit", "2 × 4096深度块"],"x"),
            (572,"W 权重SRAM",["16 bank × 1024 × 16 bit", "16个bank可同时读"],"w"),
            (714,"b 偏置SRAM",["256 × 16 bit", "2 × 128深度块"],"b"),
            (856,"Y 输出SRAM",["25344 × 16 bit", "7 × 4096深度块"],"y")]
    for n,(y,title,lines,key) in enumerate(mems):
        d.block(735,y,290,108,title,lines,"mem",key,"xwrite read core" if key=="x" else "read core", "同步单端口16位存储。容量来自ffn_banked_sram或权重的16个独立ffn_sram_1rw实例。")
        gy = 475+n*30
        d.wire([(630,gy),(660+n*13,gy),(660+n*13,y+38),(735,y+38)], "" if n else "地址 / en / we", "host", routes="xwrite read core" if key=="x" else "read core", label_at=(680,448))
    d.frame(1100, 412, 605, 586, "16路并行计算通路 · 详见图03", "#cfc3de")
    d.block(1210, 455, 365, 88, "16路乘法 + 乘积寄存器", ["signed16 × signed16 → signed32", "同一个X广播，16个W分别输入"], "core", "mul", "core", "所有16路同时计算同一输入行的16个输出列。乘积经过32位寄存器，不直接组合累加。")
    d.block(1210, 581, 365, 88, "16路40位累加器", ["先预置(b << 8)，再累加64项", "乘积先符号扩展到40位"], "core", "acc", "core")
    d.block(1210, 707, 365, 88, "16路舍入 + 饱和", ["16位小数 → 8位小数", "饱和标志汇总到SATURATIONS"], "core", "quant", "core")
    d.block(1210, 833, 365, 88, "结果暂存 + 16选1写回", ["output_buffer：16 × 16 bit", "write_lane每拍选择一个结果"], "core", "buffer", "core")
    d.wire([(1025,465),(1210,482)], "X：16 bit广播", "mem", routes="core", label_at=(1114,452))
    d.wire([(1025,610),(1070,610),(1070,519),(1210,519)], "W：16 × 16 bit", "mem", routes="core", label_at=(1135,509))
    d.wire([(1025,752),(1130,752),(1130,625),(1210,625)], "b：16 bit，依次预置", "mem", routes="core", label_at=(1121,683))
    d.wire([(1392,543),(1392,581)], "", "core", routes="core")
    d.wire([(1392,669),(1392,707)], "", "core", routes="core")
    d.wire([(1392,795),(1392,833)], "", "core", routes="core")
    d.wire([(1210,880),(1025,910)], "Y写数据：16 bit / 拍", "core", routes="core", label_at=(1112,924))
    d.block(335, 786, 295, 200, "读回选择 + 响应寄存器", ["选择X / W[bank] / b / Y读数", "16 → 32 bit符号扩展", "寄存器读：直接响应", "SRAM读：多经过H_READ一拍", "响应保持到rsp_valid & rsp_ready"], "host", "response", "read", "host_read_mem和host_read_bank在读命令接受时锁存，确保后续响应选择正确数据。错误响应返回err=1、rdata=0。")
    for n,(y,title,lines,key) in enumerate(mems):
        bend=707-n*13
        d.wire([(735,y+83),(bend,y+83),(bend,821+n*37),(630,821+n*37)], "", "mem", routes="read")
    d.wire([(335,867),(268,867),(268,430),(139,430),(139,392)], "rsp_valid / rdata[31:0] / err", "host", routes="read xwrite core", label_at=(170,680))
    d.wire([(200,392),(200,740),(318,740),(318,806),(335,806)], "rsp_ready", "host", routes="read xwrite core", label_at=(157,560))
    d.wire([(720,327),(649,327),(649,145),(141,145),(141,200)], "o_irq", "ctrl", True, "core", label_at=(430,139))
    d.note(1110,1020,["clk送各时序单元；rst_n复位控制与数据寄存器，SRAM数组保留。", "所有SRAM框是当前RTL抽象；正式宏替换与工艺实现仍待完成。"],size=11)
    return d.finish("跨线无圆点表示不连接；主机地址为局部字节地址；所有数据写入仅使用wdata[15:0]。")


def address():
    d = Drawing(2, "地址译码：写X[98,63]如何落到SRAM", "示例：i_icb_cmd_addr=0x162FC，i_icb_cmd_read=0，wmask=0xF，核心空闲。",1800,1240)
    d.block(40,159,315,175,"主机输入",["cmd_addr[31:0] = 0x000162FC", "cmd_wdata[31:0] = 0x00000180", "cmd_read = 0 / wmask = 0xF", "cmd_valid=1 & cmd_ready=1"],"host","addrin","xwrite", "地址由i_icb_cmd_addr输入；数据由i_icb_cmd_wdata输入，数据值本身不标记X/W/b/Y类别。")
    d.block(440,159,350,175,"地址范围比较 + 合法性检查",["0x10000 <= addr < 0x16300", "addr[1:0]=0，写掩码=0xF", "BUSY=0，dec_error=0", "dec_mem = MEM_X"],"host","decode","xwrite", "区间上界不包含在内。cmd_ready只说明命令可接受，访问成功还要检查响应rsp_err。")
    d.block(880,159,350,175,"计算逻辑元素编号",["dec_index = (addr-X_BASE) >> 2", "= (0x162FC-0x10000)/4", "= 6335 = 98*64+63", "x_addr[12:0] = 6335"],"host","index","xwrite", "总线每4字节映射一个16位元素；x_addr是元素编号，不是字节地址。")
    d.block(1320,159,420,175,"主机访问使能与写使能",["host_mem = accept && !dec_error", "           && dec_mem!=MEM_NONE", "MEM_X: x_en=1, x_we=!cmd_read", "SRAM wdata = cmd_wdata[15:0]"],"host","enable","xwrite")
    d.wire([(355,238),(440,238)],"32 bit","host",routes="xwrite",label_at=(397,225))
    d.wire([(790,238),(880,238)],"命中X窗口","host",routes="xwrite",label_at=(835,225))
    d.wire([(1230,238),(1320,238)],"合法写X","host",routes="xwrite",label_at=(1275,225))
    d.frame(430,400,1310,430,"u_x : ffn_banked_sram  /  DEPTH=6336  /  BANK_DEPTH=4096")
    d.block(465,454,360,150,"容量块选择 + 块内地址",["bank_select = x_addr >> 12 = 1", "bank_addr = x_addr[11:0]", "          = 2239 (0x8BF)", "6335 = 1*4096 + 2239"],"mem","bankselect","xwrite", "X的两个块用于增加深度，逻辑上仍只有一个端口；它们与权重的16路并行bank用途不同。")
    d.block(930,454,335,150,"X块0：4096 × 16 bit",["元素编号0…4095", "en = x_en && (bank_select==0)", "当前en=0，不发生写入", "未被选中的块保持内容"],"plain","xbank0","", "本次地址属于块1，所以块0的en=0。")
    d.block(1350,454,335,150,"X块1：4096 × 16 bit",["元素编号4096…6335有效", "en=1 / we=1 / addr=2239", "wdata=0x0180（Q8.8实数1.5）", "上升沿：mem[2239] <= 0x0180"],"mem","xbank1","xwrite")
    d.wire([(1055,334),(1055,376),(646,376),(646,454)],"x_addr[12:0]","host",routes="xwrite",label_at=(808,365))
    d.wire([(825,500),(930,500)],"en=0","plain",dashed=True,label_at=(877,486))
    d.wire([(825,567),(880,567),(880,657),(1518,657),(1518,604)],"bank=1 / addr[11:0]=2239","mem",routes="xwrite",label_at=(1163,647))
    d.wire([(1530,334),(1762,334),(1762,524),(1685,524)],"en / we / wdata[15:0]","host",routes="xwrite",label_at=(1640,371))
    d.block(80,450,280,154,"命令沿之后的响应",["o_icb_rsp_valid = 1", "o_icb_rsp_err = 0", "host_state = H_RESPONSE", "等待rsp_ready接收"],"host","response","xwrite", "合法写入发生在命令接受沿；响应反压不会使存储器重复写入。")
    d.note(470,715,["读操作：所选块在上升沿更新rdata，同时寄存read_select；输出MUX选择对应块的读数。", "写操作：本沿只修改选中块内容，rdata保持原值。复位不清mem数组。"],size=13)
    d.block(465,755,1220,51,"本次写入结果：X[98,63] → 逻辑元素6335 → 容量块1的2239号位置",[],"mem","result","xwrite")
    d.text(44,889,"其他区域使用同一套地址译码规则",20,weight=700)
    rows=[("X 输入","0x10000…0x162FC","(addr-0x10000)>>2","x_addr[12:0]","空闲可读写"),
          ("W 权重","0x20000…0x2FFFC","idx=(addr-0x20000)>>2","bank=idx[3:0], addr=idx[13:4]","空闲可读写"),
          ("b 偏置","0x30000…0x303FC","(addr-0x30000)>>2","b_addr[7:0]","空闲可读写"),
          ("Y 输出","0x40000…0x58BFC","(addr-0x40000)>>2","y_addr[14:0]","主机只读，核心写")]
    for i,row in enumerate(rows):
        y=925+i*48
        d.parts.append(f'<rect x="40" y="{y-22}" width="1700" height="43" rx="5" fill="{"#eff4eb" if i%2==0 else "#f7f9f4"}"/>')
        for x,v in zip([55,225,530,890,1490],row):d.text(x,y,v,13,mono=x in [225,530,890])
    d.note(45,1140,["W线性元素编号idx=k*256+j，因此bank=j%16，bank内地址=k*16+floor(j/16)。W上界0x30000恰是b首地址。"],size=12)
    return d.finish("图中块号从0开始。每元素虽为16位，总线地址槽仍为4字节；CPU绝对地址还需加平台分配的外设基地址。")


def datapath():
    d=Drawing(3,"计算通路：一条MAC通道如何复制成16路","同一行i、输出组g：16条通道并行计算j=16g…16g+15；k依次取0…63。",1800,1260)
    d.block(45,161,300,139,"X同步SRAM",["x_addr = {row_index, k[5:0]}","每次读出一个signed16的X[i,k]","x_rdata广播到全部16路"],"mem","x","core")
    d.block(435,161,410,139,"16个独立W bank",["bank=l，l=0…15", "w_addr[l] = {k[5:0],group_index}", "同时提供W[k,16g]…W[k,16g+15]"],"mem","w","core")
    d.block(935,161,380,139,"偏置同步SRAM",["b_addr={group_index,bias_issue[3:0]}","依次读16个偏置，延迟记录lane号","signed16扩到40位，再左移8位"],"mem","b","core")
    d.block(1405,161,345,139,"核心调度与有效位",["mac_read_valid：读数可用", "product_valid：乘积可累加", "bias_valid：偏置可预置"],"ctrl","ctrl","core")
    d.frame(45,357,1705,480,"通道l的逻辑展开（l=0…15）；相同结构共16份", "#ccbfdf")
    d.block(90,420,235,110,"有符号乘法器",["X signed16 × W signed16","32位完整乘积"],"core","multiply","core")
    d.block(395,420,230,110,"乘积寄存器",["product[l][31:0]","使能：mac_read_valid"],"core","product","core")
    d.block(695,420,215,110,"符号扩展",["32位 → 40位", "复制符号位到高8位"],"core","extend","core")
    d.block(985,420,215,110,"40位加法器",["ACC + product_ext","加法结果保持40位"],"core","adder","core")
    d.block(1275,420,210,110,"更新值选择",["BIAS：b << 8", "MAC：ACC + product"],"core","accmux","core")
    d.block(1540,420,170,110,"累加寄存器",["ACC[l][39:0]","不更新时保持"],"core","acc","core")
    d.wire([(195,300),(195,420)],"X：16 bit","mem",routes="core",label_at=(250,361))
    d.wire([(640,300),(640,382),(300,382),(300,420)],"W[l]：16 bit","mem",routes="core",label_at=(471,372))
    d.wire([(325,475),(395,475)],"32","core",routes="core",label_at=(360,463))
    d.wire([(625,475),(695,475)],"32","core",routes="core",label_at=(660,463))
    d.wire([(910,475),(985,475)],"40","core",routes="core",label_at=(946,463))
    d.wire([(1200,475),(1275,475)],"40","core",routes="core",label_at=(1238,463))
    d.wire([(1485,475),(1540,475)],"40","core",routes="core",label_at=(1512,463))
    d.wire([(1125,300),(1125,344),(1380,344),(1380,420)],"偏置预置：16位小数尺度","mem",routes="core",label_at=(1306,333))
    d.wire([(1580,300),(1580,324),(510,324),(510,420)],"mac_read_valid：乘积寄存器使能","ctrl",True,"core",label_at=(792,313))
    d.wire([(1650,300),(1650,367),(1625,367),(1625,420)],"bias_valid / product_valid","ctrl",True,"core",label_at=(1636,395))
    d.wire([(1625,530),(1625,586),(1090,586),(1090,530)],"反馈ACC的上一拍值","core",routes="core",label_at=(1370,576))
    d.note(92,581,["MAC流水线：同步读取 → 注册乘积 → 40位累加。", "前两拍填充流水线，最后两拍收尾；64项需要66个MAC状态拍。"],size=12)
    d.block(395,651,340,111,"requantize(ACC[l])",["最接近舍入，半值远离零", "舍入后限制到[-32768,32767]", "返回{sat_flag, result[15:0]}"],"core","quant","core")
    d.block(830,651,340,111,"结果寄存器",["output_buffer[l][15:0]", "S_ROUND时16路同时锁存", "共16 × 16 bit"],"core","output","core")
    d.wire([(1710,475),(1728,475),(1728,623),(565,623),(565,651)],"最终40位累加值","core",routes="core",label_at=(1240,614))
    d.wire([(735,707),(830,707)],"16 bit","core",routes="core",label_at=(782,695))
    d.block(1275,651,435,111,"饱和标记汇总",["16路sat_flag求和 → 5位增量", "S_ROUND更新32位saturation_count", "计数可从SATURATIONS寄存器读取"],"ctrl","sat","core read")
    d.wire([(735,747),(790,747),(790,790),(1230,790),(1230,707),(1275,707)],"sat_flag：每路1 bit，共16路","ctrl",routes="core",label_at=(1064,780))
    d.block(100,912,350,125,"output_buffer整体视图",["buffer[0] … buffer[15]", "与上方单路结果寄存器为同一组", "这里展开16路，不增加寄存器"],"core","buffers","core")
    d.block(605,912,350,125,"16选1输出MUX",["选择信号：write_lane[3:0]", "y_wdata=output_buffer[write_lane]", "每拍只选择一个16位结果"],"core","write_mux","core")
    d.block(1110,912,590,125,"Y单端口SRAM写回",["y_addr[14:0] = {row_index,group_index,write_lane}", "S_WRITE：y_en=1 / y_we=1", "write_lane=0…15，共16拍；完成后换组或置DONE"],"mem","y","core")
    d.wire([(1000,762),(1000,864),(275,864),(275,912)],"展开同一组16路结果寄存器","core",routes="core",label_at=(624,854))
    d.wire([(450,975),(605,975)],"16 × 16 bit","core",routes="core",label_at=(528,962))
    d.wire([(955,975),(1110,975)],"16 bit / 拍","core",routes="core",label_at=(1034,962))
    d.note(45,1090,["数值尺度：X、W、b、Y为8位小数。乘积有16位小数；偏置左移8位与其对齐；完整点积结束后只舍入一次。", "每组：17拍偏置 + 66拍MAC + 1拍舍入 + 16拍写回 = 100拍。16组/行 × 99行 = 158400拍。"],size=14)
    return d.finish("更新值选择是RTL行为的逻辑表示，实际门级结构由综合决定。上图用一条通道展开；硬件共16条。")


def control():
    d=Drawing(4,"控制连接：总线事务与计算任务分别推进","两个独立状态机：响应等待不会暂停计算；BUSY也不会禁止合法的状态寄存器读取。",1800,1190)
    d.frame(40,155,1700,360,"A · 总线事务状态机 host_state")
    d.block(100,230,340,145,"H_IDLE",["cmd_ready = rst_n", "等待accept=cmd_valid & cmd_ready", "命令接受时进行合法性检查"],"host","idle","read xwrite core")
    d.block(710,230,340,145,"H_READ",["只用于合法的数据SRAM读取", "同步读数据已在上一沿后更新", "本沿寄存符号扩展的读数"],"host","hread","read")
    d.block(1310,230,370,145,"H_RESPONSE",["rsp_valid=1，保持DATA与ERR", "等待rsp_ready接收响应", "响应握手后回到H_IDLE"],"host","response","read xwrite core")
    d.wire([(440,280),(710,280)],"合法SRAM读命令","host",routes="read",label_at=(575,266))
    d.wire([(1050,280),(1310,280)],"下一拍寄存读响应","host",routes="read",label_at=(1180,266))
    d.wire([(270,230),(270,198),(1495,198),(1495,230)],"寄存器读 / 所有写 / 错误访问：命令接受沿后直接产生响应","host",routes="xwrite read core",label_at=(904,190))
    d.wire([(1495,375),(1495,445),(270,445),(270,375)],"rsp_valid & rsp_ready：接收响应；下一沿才可接受新命令","host",routes="read xwrite core",label_at=(871,433))
    d.note(110,486,["反压：rsp_ready=0时保持H_RESPONSE；cmd_ready=0，最多允许一个未完成事务。"],size=13)
    d.frame(40,560,1700,414,"B · 计算状态机 state")
    blocks=[(90,"S_IDLE",["BUSY=0", "等待合法START"],"ctrl"),(425,"S_BIAS",["16个偏置同步读及收尾", "17拍"],"mem"),(760,"S_MAC",["64项流水乘累加及收尾", "66拍"],"core"),(1095,"S_ROUND",["16路同时舍入/饱和", "1拍"],"core"),(1430,"S_WRITE",["逐个写入16个结果", "16拍"],"mem")]
    for x,title,lines,kind in blocks:d.block(x,644,260,120,title,lines,kind,title,"core")
    for x1,x2,label in [(350,425,"START"),(685,760,"偏置齐"),(1020,1095,"末项累加"),(1355,1430,"结果暂存")]:d.wire([(x1,704),(x2,704)],label,"ctrl",True,"core",label_at=((x1+x2)/2,690))
    d.wire([(1560,764),(1560,831),(555,831),(555,764)],"还有下一组：group+1；一行16组完成后row+1","ctrl",True,"core",label_at=(1048,818))
    d.wire([(1560,764),(1560,909),(220,909),(220,764)],"最后一组最后写入：DONE=1 / IRQ=1 / BUSY=0；周期最终为158400","ctrl",True,"core",label_at=(893,896))
    d.wire([(220,375),(220,644)],"START事件来自合法CONTROL写入","ctrl",True,"core",label_at=(432,544))
    d.note(90,951,["S_IDLE读到旧DONE时可直接再START：自动清DONE/IRQ、周期和饱和计数；运行中重复START返回总线错误。"],size=12)
    d.block(40,1010,815,85,"共享条件：BUSY = (state != S_IDLE)",["运行时主机数据访问报错；寄存器仍可读，CONTROL可写0或2，LAYER_TAG禁止写。"],"ctrl","busy","core read")
    d.block(900,1010,840,85,"复位：rst_n异步低有效",["清两套状态机、DONE、计数与数据寄存器；不清SRAM数组；释放复位由平台同步。"],"ctrl","reset","core read xwrite")
    return d.finish("计算完成不是总线写响应：START响应只确认启动命令执行；任务完成由DONE或IRQ表示。")


def main():
    HERE.mkdir(exist_ok=True)
    sheets=[]
    for name,title,desc,draw in [
        ("01_overview","整体连接","从总线命令到存储器、计算和读回",overview),
        ("02_address_decode","地址译码与X写入","0x162FC如何选中X的具体存储位置",address),
        ("03_mac_datapath","16路计算通路","乘法、寄存、累加、舍入和逐个写回",datapath),
        ("04_control_fsm","控制与握手","两套状态机如何并行推进",control)]:
        svg=draw()
        (HERE/(name+".svg")).write_text(svg,encoding="utf-8")
        sheets.append(dict(id=name,title=title,description=desc,svg=svg))
    hashes={p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in RTL.glob("*.sv")}
    data=dict(sheets=sheets,rtl_hashes=hashes)
    (HERE/"schematic_data.json").write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    template=(HERE/"viewer.html").read_text(encoding="utf-8")
    encoded=json.dumps(data,ensure_ascii=False).replace("</","<\\/")
    (HERE/"index.html").write_text(template.replace("__SCHEMATIC_DATA__",encoded),encoding="utf-8")
    print(f"Generated {len(sheets)} SVG sheets and standalone index.html")


if __name__=="__main__":main()
