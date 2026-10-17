# A 同学交付包：模型、数值模型与运算 RTL

本目录对应《本科生组三周分工报告》第 2 页的 A 同学任务。最终实测结果与未完成项见
`reports/STATUS.md`，接口见 `docs/INTERFACE.md`。原始赛题与分工 PDF 保持不变。

## 计算范围

`Y[99,256] = X[99,64] @ W[64,256] + b[256]`。
软件端提取指定 KWT-1 的 12 个前馈第一线性层任务；每层的输入均来自原始浮点模型中
注意力、残差与第一处 LayerNorm 之后。12 组数据分别计算，不将第一线性层输出直接串成 12 层。

RTL 提供 signed16 点积、signed40 累加、signed40 偏置对齐、signed41 偏置相加、
最近舍入（半值远离零）及 signed16 饱和。`compute_lane` 是供 B 复用的单路运算单元。
完整矩阵调度、SRAM 和 E203 总线不在此模块内。

## 文件依赖

```text
外部 keyword-transformer 固定提交 + best_weights + Speech Commands V2
  → model/extract_evaluate.py
  → formats.json / samples.json / precision_report.json / layer_00..11
  → model/make_vectors.py → 输入、原始点积、转换后输出期望值
  → tb/tb_a_compute.sv → dot64_mac / compute_lane / bias_requant
  → scripts/run_xsim.ps1 → 真实 XSim 日志与终端 PASS 标记

model/pack_vectors.py → little-endian 二进制数据及 SHA-256 → B/C 联调
```

`model/numeric.py` 是有限位宽整数参考，不以浮点矩阵乘法替代 RTL 数值语义。
`dot64_scalar()` 明确逐项乘加和 40 位截断；矩阵版本利用 signed16×64 不会超出
signed38 的范围事实做等价向量化。`test_numeric.py` 检查两种实现的一致性及边界。

## 当前本机路径

工作根：`C:\Users\Sunuo\Desktop\xinpian`。
仓库：`SocDesign-Cop`。环境：工作根的 `.venv-a`。
官方模型：工作根的 `keyword-transformer`，提交必须为
`237e4097afd4f6851e0b82f0a8d65c2dfe8eae30`。
数据：`A_work/data/speech_commands_v0.02`。

## 复现命令（PowerShell，在 A_work 中执行）

首先运行 `scripts/bootstrap.ps1`，或手动使用 uv 安装 Python 3.8 并按 `requirements-lock.txt`
创建环境。所有新增输出都使用新目录，避免混合不同版本的数值配置。

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File scripts\bootstrap.ps1
$python = '..\..\.venv-a\Scripts\python.exe'
& $python model\test_numeric.py

# 第一次需下载约 2.43 GB 压缩包，并解压约十万份音频文件。
& $python scripts\fetch_dataset.py --out data

# 训练划分每类16条标定；完整验证划分评估；不读取测试划分进行调参。
& $python model\extract_evaluate.py --upstream ..\..\keyword-transformer --dataset data\speech_commands_v0.02 --out build\real_reproduce --calibration-per-class 16 --validation-per-class 0 --batch-size 16
& $python model\pack_vectors.py --real build\real_reproduce
& $python model\make_vectors.py --real build\real_reproduce --out build\vectors_reproduce

powershell -NoProfile -ExecutionPolicy Bypass -File scripts\run_xsim.ps1 -Vivado 'D:\Xilinx\2025.2\Vivado\bin\vivado.bat' -Vectors build\vectors_reproduce
```

小样本调试可把 `--validation-per-class 0` 改成 `2`，但小样本结果不能当成完整验证结果。
真实向量覆盖每层首个验证样本的第 0、49、98 行和全部 256 个输出通道，
共 9216 个点积，加 225 个独立合成用例。它验证 A 运算核心，不能代替 B 的完整矩阵调度验证。

对一个新的浮点任务应用已经冻结的配置，禁止重新拟合尺度：

```powershell
& $python model\run_numeric_task.py --input artifacts\real_12_layers\layer_00\float_sample.npz --formats artifacts\real_12_layers\formats.json --layer 0 --out build\new_task_result.npz
```

## 工具与版本边界

原仓库要求 TensorFlow 2.4.0rc1；当前 PyPI 精确版本入口返回 404，因此本环境使用
TensorFlow 2.4.0 正式版、TensorFlow Addons 0.12.1、NumPy 1.19.5 与 Python 3.8.20。
依赖完整冻结在 `requirements-lock.txt`。保留这个差异，不声称已与不可取得的 rc1 做逐位对照。
代码对全部模型权重执行独立检查点逐元素核对，并比较提取用数据流与原模型的分类输出，
避免把加载警告、权重漏载或取数位置错误隐藏在精度报告里。

使用了 AMD ROSS `vivado-simulate-rtl` Skill。已尝试 Vivado MCP 的
`vivado_start`，但代理启动失败；本次有效仿真通过本机 Vivado 2025.2/XSim 批处理完成。
不能将本次报告写成“Vivado MCP 会话执行成功”。

`synth_fpga_smoke.tcl` 仅检查 RTL 可综合性，目标为 xc7z020clg400-1。
其 LUT、DSP、综合后时序和 DRC 均不能替代 E203 平台指定工艺、标准单元库、
SRAM 宏和真实 I/O 约束下的 ASIC 评估；未进行 FPGA 布局布线或板级测试。

## 交接和防错

- 先看 `reports/STATUS.md`，再看 `docs/INTERFACE.md`，不要根据模块名猜延迟或打包方式。
- 每 64 次 `valid && ready` 才形成一个点积，停顿不推进计数；元数据只在首对接受时采样。
- 保留 W 的 [64,256] 方向，偏置先对齐到乘积尺度，再舍入饱和。
- 逐位一致与浮点 NRMSE 是两个独立验收项，两者都需要通过。
- 归档的真实模型向量及配置需共同使用；修改位宽、尺度或舍入必须全量重生成并复测。
- testbench 有 watchdog 和显式终端 PASS。Vivado Tcl 返回成功不足以证明功能通过。
- `build/` 和 `data/` 为本地生成目录，不提交大数据或工具缓存。稳定证据复制到
  `reports/`，冻结的 12 层交接数据保存在 `artifacts/real_12_layers/`。
- 本代码由 AI 协助生成并运行检查。A 本人仍需理解和复核；独立交叉评审与成员贡献确认尚须团队完成。

## 来源

- [ARM 官方模型与预训练权重](https://github.com/ARM-software/keyword-transformer/tree/237e4097afd4f6851e0b82f0a8d65c2dfe8eae30)，Apache-2.0，原始源码未改动。
- [Speech Commands V2 数据集](https://storage.googleapis.com/download.tensorflow.org/data/speech_commands_v0.02.tar.gz)，数据许可见压缩包内原始 LICENSE/README。
- [AMD UG900 仿真选项](https://docs.amd.com/r/2024.1-English/ug900-vivado-logic-simulation/Vivado-Simulator-Simulation-Options)。
- 本仓库赛题 PDF 与工作根的三周分工报告决定交付范围。
