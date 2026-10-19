# Vivado实际综合结果与层级

2026-10-19，使用本机Vivado 2025.2完成综合，目标器件`xc7z020clg400-1`，顶层`ffn_accel`。
`flatten_hierarchy=none`，保留原有模块层级；没有修改RTL。

综合运行状态：`synth_design Complete!`。运行日志记录0 Errors、0 Critical Warnings；普通警告包括时钟周期取整到6.667 ns和顶层包含较多原语、不利于floorplanning。

## 打开综合层级

双击本目录的 `打开Vivado综合层级.cmd`。
它打开已完成的工程、加载`Open Synthesized Design`，显示顶层模块及X SRAM内部原理图。
启动成功后，Vivado窗口保持打开供你操作。

也可以直接打开工程：

```text
G:\0_TEMP\7_qiansai_chipdesign\sv_ffn_accel\build\vivado_hierarchy\project\ffn_accel_hierarchy.xpr
```

在Vivado中选择左侧`Synthesis → Open Synthesized Design`，然后在`Netlist`窗口展开`ffn_accel`。
右键模块选择`Schematic`，或选中模块后按F4，可查看相应连接。

当前有19个顶层子模块、30个保留的非原语实例，其中27个为逻辑SRAM实例。
控制、乘法、累加、舍入和结果暂存直接写在顶层，所以没有独立的`MAC`、`control`子模块名称。
`ffn_numeric_pkg`是包，不构成设计层级。其数值处理函数展开为顶层逻辑。

若要选中16个乘法DSP，在Vivado的Tcl Console执行：

```tcl
current_instance
select_objects [get_cells -hierarchical -filter {REF_NAME == DSP48E1}]
show_schematic -name "16 multiplier DSPs" [get_cells -hierarchical -filter {REF_NAME == DSP48E1}]
```

## 从综合设计导出的完整层级

下列内容来自Vivado的`get_cells -hierarchical`，不是根据源文件猜测：

```text
ffn_accel (top)
├─ gen_weight[0].u_mem : ffn_sram_1rw
├─ gen_weight[1].u_mem : ffn_sram_1rw
├─ gen_weight[2].u_mem : ffn_sram_1rw
├─ gen_weight[3].u_mem : ffn_sram_1rw
├─ gen_weight[4].u_mem : ffn_sram_1rw
├─ gen_weight[5].u_mem : ffn_sram_1rw
├─ gen_weight[6].u_mem : ffn_sram_1rw
├─ gen_weight[7].u_mem : ffn_sram_1rw
├─ gen_weight[8].u_mem : ffn_sram_1rw
├─ gen_weight[9].u_mem : ffn_sram_1rw
├─ gen_weight[10].u_mem : ffn_sram_1rw
├─ gen_weight[11].u_mem : ffn_sram_1rw
├─ gen_weight[12].u_mem : ffn_sram_1rw
├─ gen_weight[13].u_mem : ffn_sram_1rw
├─ gen_weight[14].u_mem : ffn_sram_1rw
├─ gen_weight[15].u_mem : ffn_sram_1rw
├─ u_bias : ffn_banked_sram
│  ├─ gen_bank[0].u_mem : ffn_sram_1rw
│  └─ gen_bank[1].u_mem : ffn_sram_1rw
├─ u_x : ffn_banked_sram
│  ├─ gen_bank[0].u_mem : ffn_sram_1rw
│  └─ gen_bank[1].u_mem : ffn_sram_1rw
└─ u_y : ffn_banked_sram
   ├─ gen_bank[0].u_mem : ffn_sram_1rw
   ├─ gen_bank[1].u_mem : ffn_sram_1rw
   ├─ gen_bank[2].u_mem : ffn_sram_1rw
   ├─ gen_bank[3].u_mem : ffn_sram_1rw
   ├─ gen_bank[4].u_mem : ffn_sram_1rw
   ├─ gen_bank[5].u_mem : ffn_sram_1rw
   └─ gen_bank[6].u_mem : ffn_sram_1rw
```

## FPGA资源与时序

| 项目 | 数量 |
|---|---:|
| Slice LUT | 3918 |
| 触发器 | 1065 |
| DSP48E1 | 16 |
| RAMB36E1 | 18 |
| RAMB18E1 | 18 |
| 等效36 Kb Block RAM Tile | 27 |

27个逻辑SRAM实例映射成18个RAMB36E1和18个RAMB18E1，合计27个36 Kb等效tile。
这与赛题ASIC SRAM宏的数量、面积和功耗不是同一种指标。

时钟目标150 MHz（Vivado取整后的周期6.667 ns）。综合后估算WNS=-7.182 ns，WHS=-0.661 ns，**当前没有满足该目标时序**。
最差setup路径从`accumulator_reg[3][0]`到`saturation_count_reg[31]`，经过舍入/饱和判断与饱和数量累加。
当前只完成综合，没有布局布线、引脚规划或生成bitstream；这些数字不能作为ASIC工艺验收结果。
原有接口延迟约束是模板，异步复位`rst_n`仍需平台复位方法学约束。

## 文件

| 文件 | 用途 |
|---|---|
| `hierarchy.txt` | 完整实例层级树 |
| `summary.json` | 机器可读结果、原语数量、时序与RTL哈希 |
| `../../sv_ffn_accel/build/vivado_hierarchy/ffn_accel_synth.dcp` | 实际综合检查点 |
| `../../sv_ffn_accel/build/vivado_hierarchy/ffn_accel_synth.v` | 综合后功能网表 |
| `../../sv_ffn_accel/build/vivado_hierarchy/reports/utilization_hierarchical.rpt` | 全部层级资源报告，关闭默认50原语过滤门槛 |
| `../../sv_ffn_accel/build/vivado_hierarchy/reports/timing_summary_post_synth.rpt` | 综合后时序报告 |
| `../../sv_ffn_accel/build/vivado_hierarchy/reports/vivado_top_modules.svg` | Vivado GUI导出的顶层模块原理图（GUI脚本执行成功后生成） |
| `../../sv_ffn_accel/build/vivado_hierarchy/reports/vivado_x_sram.svg` | Vivado GUI导出的X SRAM内部原理图（GUI脚本执行成功后生成） |

## 复现

```powershell
& 'E:/3_Engineering/vivado20252/2025.2/Vivado/bin/vivado.bat' -mode batch -source 'G:\0_TEMP\7_qiansai_chipdesign\sv_ffn_accel\scripts\vivado_hierarchy.tcl' -tclargs xc7z020clg400-1 G:/0_TEMP/7_qiansai_chipdesign/sv_ffn_accel/build/vivado_hierarchy_new
python 'G:\0_TEMP\7_qiansai_chipdesign\sv_ffn_accel\scripts\summarize_vivado_hierarchy.py'
```

综合脚本拒绝覆盖已有工程。第二个参数可指定新的输出目录。
汇总脚本默认读取本次`build/vivado_hierarchy`目录。
