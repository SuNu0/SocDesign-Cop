# FFN加速器设计原理图

打开 `index.html` 可在四张模块级原理图之间切换、缩放、按路径高亮、点击模块查看说明和保存当前SVG。
HTML已内嵌全部图纸，可离线使用，也可单独复制到其他电脑打开。

| 图纸 | 内容 | 图片 / 矢量文件 |
|---|---|---|
| 01 整体连接 | 主机握手、译码、控制与状态、存储访问选择、X/W/b/Y、16路计算、读回与响应 | `01_overview.png` / `01_overview.svg` |
| 02 地址译码与X写入 | 从0x162FC到第6335号元素，再到X容量块1的2239号地址；给出各区域映射与权重bank规则 | `02_address_decode.png` / `02_address_decode.svg` |
| 03 16路计算通路 | 展开一条乘法、乘积寄存器、40位加法反馈、偏置预置、舍入饱和、16路暂存与16选1写回 | `03_mac_datapath.png` / `03_mac_datapath.svg` |
| 04 控制状态机 | 独立的总线FSM与计算FSM、同步读等待、响应反压、组与行推进、DONE/IRQ和复位 | `04_control_fsm.png` / `04_control_fsm.svg` |

图纸来源是当前 `sv_ffn_accel/rtl/ffn_accel.sv`、`ffn_sram_1rw.sv`、`ffn_numeric_pkg.sv`。
功能框是对RTL的逻辑划分，不表示已经拆成同名的独立SV模块；门级拓扑由综合决定。
SRAM仍是RTL存储抽象，尚未完成指定工艺宏的替换与物理实现。

## 阅读约定

- 实线表示数据或请求，虚线表示调度或状态；跨线没有圆点时不连接。
- 图中地址均为外设局部字节地址。CPU访问时由平台分配外设基地址，并在转发命令前减去基地址。
- X/W/b/Y存储元素为16位，每个元素对应一个4字节总线地址槽。
- X/b/Y的多个容量块用于拼接存储深度；W的16个bank用于同时读取16个权重。
- DATA与READY握手方向分别画出；只有上升沿前VALID和READY同时为1时完成传输。
- 图03的结果寄存器展开为单通道视图，底部“16路输出暂存值”是同一组寄存器的整体视图，不是第二套额外寄存器。
- 正式集成E203与工艺实现仍待完成。图中的CPU为外部主机角色，当前验证使用测试平台。

## 生成与检查

```powershell
python build_schematic.py
node check_and_export.cjs
```

Python脚本生成SVG、内嵌数据及最终HTML，不修改加速器RTL。
浏览器脚本使用本机已有的Playwright和Edge，导出四张PNG并检查切换、缩放、路径高亮、模块说明、SVG下载和移动宽度；同时检查模块文字是否越框。
本机依赖的绝对路径记录在脚本中，其他电脑可以直接使用生成的SVG/PNG/HTML，无需安装这些工具。

`schematic_data.json`记录绘图时RTL的SHA-256；`verification.json`保存图纸检查结果。
本次只添加说明图纸，没有修改RTL或重新运行计算功能回归。
