# B：矩阵调度、缓存与 A 运算接口适配 v1

维护归属：**B 同学（矩阵部分）**；提交账号 [ckycao69-prog](https://github.com/ckycao69-prog)。

阶段标记：**B-matrix-v1**。十二层完整矩阵的 304,128 项输出已逐位通过 A/B 联合仿真；C/SoC 接入和官方宏、综合验收待完成。

本科组前馈第一线性层：`X[99×64] · W[64×256] + b[256] → Y[99×256]`。

B 负责矩阵调度、内部 SRAM 组织、结果写回请求和加速器顶层。联合顶层已连接 A 的 `compute_lane` 正式 RTL，读取外部交接数据；C 的实际 SoC 接口/驱动/综合环境仍待对接。

## A/B 联合测试

需要 Python 3 和支持 SystemVerilog 2012 的 Icarus Verilog（iverilog、vvp）。Python 脚本只使用标准库。已验证 Python 3.13.15、Icarus 14.0 devel。

测试同时需要共享仓库中的 `A_work`，其中应包含 A 的三份运算 RTL，以及 `artifacts/real_12_layers` 数据包。B 交付包保留引用，不重复复制 A 的代码和数据。例如共同仓库可组织为：

```text
SocDesign-Cop/
  A_work/
  B_work/       # 本目录的文件
```

在 B 工作目录的 PowerShell 中运行：

```powershell
# 抽取十二层的3行、5列，验证任务切换、反压、错误与复位恢复
.\Run-AB-Tests.ps1 -AWork '..\A_work' -AllLayers -Quick

# 第0层完整99×64×256任务
.\Run-AB-Tests.ps1 -AWork '..\A_work' -Layer 0

# 十二层完整任务，分3组并行，每组连续执行4层
.\Run-AB-Tests.ps1 -AWork '..\A_work' -AllLayers
```

`-AWork` 可以是 A_work 的任何实际路径。更换同格式数据包时增加 `-Data PATH`；`-Layer` 和 `-AllLayers` 互斥。`-Workers 1` 可改为顺序运行。Python 入口为：

```text
python scripts/run_ab_regression.py --a-work ../A_work --layer 0
python scripts/run_ab_regression.py --a-work ../A_work --all-layers
```

工具未加入 PATH 时，PowerShell 可指定 `-Python PATH -Iverilog PATH -Vvp PATH`；Python 可指定 `--iverilog PATH --vvp PATH`。脚本保留开发机常用安装目录的后备查找，不要求队友使用相同目录。

成功标记为 `AB_ALL_TESTS_PASS`。每次运行保存在独立目录 `reports/ab_regression/runs/<运行编号>/`，终端会打印路径；该目录的 `summary.json` 与日志一起保留。上级目录的 `summary_quick.json`、`summary_single_layer.json`、`summary_all_layers.json` 分别指向各模式最近一次运行，具体目录见摘要中的 `run_directory`。

运行目录内的每个矩阵用例包含输入快照、编译/仿真日志、全部实际输出 `observed.txt`，以及便于阅读的十进制抽样对照表 `sample_results.csv`；出现数值差异时保存 `first_mismatch.json`。摘要记录所用 A/B 源码、测试脚本、外部数据及生成产物的 SHA-256，后续测试不会覆盖前一次的日志。

## 外部数据约定

`-Data` 指向包含 `formats.json` 和 `layer_00` 等子目录的数据根。格式表需完整描述 0—11 层；只运行某一层时，仅需该层的数据目录。每层需有 `memory_manifest.json`、`x/w/b/y.hex` 和 manifest 声明的四份 `.bin`。

入口先检查数值格式、形状、编码、文件数量、二进制长度、SHA-256、小端二进制回读，并独立核对软件整数期望；再运行 A 正式 RTL 与 B 调度的联合仿真，逐项核对实际写回。二进制文件在读取前核对长度，读取也受预期长度限制。外部输入目录保持只读，归一后的仿真输入写入 reports。格式或数值不一致会报出文件，或层号/行列与预期/实际值。

采用 A 的 signed16 输入/权重、signed40 偏置/点积、signed41 偏置加法、最近舍入（半值远离零）和 signed16 饱和输出。`shift` 来自各层配置并在任务接受时锁存；当前冻结数据的层编号2为17，其余为16，代码没有硬编码这张表。

## 原 B 合成回归

```powershell
.\Run-B-Tests.ps1 -Quick
.\Run-B-Tests.ps1
```

保留原 B 独立测试：运算端使用 TEST ONLY 模型，默认40位模加结果，成功标记 `B_ALL_TESTS_PASS`。标准回归增加两个完整尺寸合成任务，`-FullLayers` 为十二个完整尺寸合成任务。该入口与 A/B 联合入口采用不同的运算契约；实际运行范围以各自摘要为准。

## 交付内容

| 路径 | 用途 |
| --- | --- |
| `rtl/control/linear_ctrl.sv` | 参数装载、矩阵循环、MAC 握手、写回等待、状态和错误处理 |
| `rtl/memory/tensor_buffer.sv` | 多 bank、16 位通道缓冲组织 |
| `rtl/memory/sram_wrapper.sv` | 行为 SRAM/官方宏适配边界 |
| `rtl/linear_accel_top.sv` | B 顶层，外接 A 运算与 C 访存端 |
| `rtl/integration/a_compute_adapter.sv` | A运算适配，点积边界、元数据、清空和错误处理 |
| `rtl/linear_accel_a_top.sv` | 真实 A/B 联合顶层，接 C 逻辑访存端 |
| `tb/` | 自检查平台，以及标注为 TEST ONLY 的 A/C 仿真模型 |
| `scripts/run_b_regression.py` | 合成数据、独立整数期望、编译及逐位比对 |
| `Run-B-Tests.ps1` | Windows 运行入口 |
| `scripts/a_vectors.py` | 只读外部数据加载、格式和独立数值校验 |
| `scripts/run_ab_regression.py`、`Run-AB-Tests.ps1` | A/B 联合回归及 Windows 入口 |
| [接口草案](docs/B接口草案_v0.md) | A/B/C 需要确认的端口、格式、布局和完成条件 |

## 已验证与待对接

联合测试覆盖真实层数据、层编号和shift锁存、逐项写回、反压、读写错误、末次写确认、忙时更改配置和读/部分点积/写阶段复位恢复。适配器单测另检查0/16/17/63移位、正负半值、饱和、41位偏置和、错误点积边界、待取结果清空。数据加载单测检查损坏数据及非法布局等拒绝路径。原 B 回归保留存储边界和参数检查。

实际运行模式、成功任务数和逐位核对数量以本次 `summary*.json` 为准，交付时的冻结记录见 `VERIFICATION.json`。完整十二层联合测试按三组运行，组内连续任务之间不复位；控制与异常恢复在抽样矩阵上覆盖。

联合入口使用 A 的正式运算 RTL 和交接数据，C 访存仍是仿真模型，SRAM 仍为行为后端。每层导出的一个输入矩阵通过不能代替全部验证语音、官方600条精度评测或 SoC 验收。官方宏、C正式接口/E203、综合前后检查、150 MHz 时序、面积及功耗仍待验证。64位逻辑载荷不代表实际平台总线。

`task_cycles` 为 B 内部调试计数，不能直接用作官方端到端性能数据。定义 `B_USE_OFFICIAL_SRAM` 后必须提供实际宏适配器，缺少适配器将编译失败。

阶段交付目录附带 `VERIFICATION.json` 与 `MANIFEST.sha256`，用于回查验证范围及文件一致性。原始赛题、个人学习记录、本机环境盘点和生成的仿真产物不属于团队代码交付内容。
