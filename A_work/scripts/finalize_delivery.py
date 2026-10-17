"""Freeze only completed, actually passing local evidence into the handoff pack."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil

def digest(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(4*1024*1024),b''):h.update(b)
    return h.hexdigest()

def main():
    p=argparse.ArgumentParser()
    p.add_argument('--real',type=Path,required=True)
    p.add_argument('--sim',type=Path,required=True)
    p.add_argument('--vectors',type=Path,required=True)
    p.add_argument('--synth',type=Path,required=True)
    a=p.parse_args()
    root=Path(__file__).resolve().parents[1]
    report=json.loads((a.real/'precision_report.json').read_text())
    audit=json.loads((a.real/'checkpoint_audit.json').read_text())
    vectors=json.loads((a.vectors/'manifest.json').read_text())
    log=a.sim/'a_compute.sim'/'sim_1'/'behav'/'xsim'/'simulate.log'
    text=log.read_text()
    expected='ALL_A_COMPUTE_TESTS_PASSED dots=%d requant=%d'%(vectors['dot_cases'],vectors['requant_cases'])
    if expected not in text or re.search(r'Fatal:|Error:|WATCHDOG phase=',text):
        raise RuntimeError('Simulation PASS gate failed')
    if not report['complete_validation'] or not report['local_precision_pass']:
        raise RuntimeError('Complete local precision gate failed')
    if not all(x['exact_equal'] for x in audit):raise RuntimeError('Checkpoint audit failed')
    target=root/'artifacts'/'real_12_layers'
    if target.exists():raise FileExistsError('Frozen artifacts already exist')
    shutil.copytree(a.real,target)
    reports=root/'reports';reports.mkdir(exist_ok=True)
    for name in ['precision_report.json','formats.json','provenance.json','checkpoint_audit.json']:
        shutil.copy2(a.real/name,reports/name)
    simdir=log.parent
    for name in ['simulate.log','xvlog.log','elaborate.log']:
        path=simdir/name
        if path.exists():shutil.copy2(path,reports/('xsim_'+name))
    shutil.copy2(a.sim/'vivado.log',reports/'vivado_real_regression.log')
    shutil.copy2(a.real.parent/(a.real.name+'_console.log'),reports/'model_evaluation.log')
    shutil.copy2(a.vectors/'manifest.json',reports/'rtl_vector_manifest.json')
    shutil.copy2(root/'data'/'dataset_manifest.json',reports/'dataset_manifest.json')
    for path in a.synth.glob('*.rpt'):shutil.copy2(path,reports/path.name)
    formats=json.loads((a.real/'formats.json').read_text())['layers']
    rows=[]
    for x,cfg in zip(report['layers'],formats):
        rows.append('| %d | %d/%d/%d | %d | %.6f%% | %.6f%% | %d/%d |'%(
            x['layer'],cfg['fx'],cfg['fw'],cfg['fy'],cfg['shift'],x['nrmse']*100,
            x['worst_task_nrmse']*100,x['input_clipped_values'],x['output_saturated_values']))
    status='''# A 同学交付状态（2026-10-17）

## 已完成并实际验证

- 指定 ARM 模型提交 `237e4097afd4f6851e0b82f0a8d65c2dfe8eae30` 与 best_weights，%d 个模型权重张量全部逐元素等于检查点。
- 原代码完成音频解码、MFCC、模型推理与 12 层第一线性层取数。提取链与原模型分类输出最大绝对差为 %.9g。
- 训练划分 %d 条样本无梯度标定；完整本地验证划分 %d 条样本评估。未使用测试划分调整数值配置。
- 最大逐层 NRMSE 为 **%.6f%%**，低于 3%%；全部验证任务中最大单任务 NRMSE 为 %.6f%%。
- 软件有限位宽数值模型；5 项独立数值单测通过。
- dot64_mac、bias_requant、compute_lane 及自检 TB；XSim 2025.2 实际通过 %d 组点积和 %d 组数值转换测试。
- 点积真实向量覆盖 12 层 × 3 行 × 256 输出通道，共 %d 组，另有 %d 组合成点积；MAC 原始累加和最终 lane 输出都逐位检查。
- 输入停顿、输出反压时保持、元数据首拍采样、部分任务复位中止、待取结果复位中止和连续任务均通过。
- 12 层完整 99×256 软件期望输出、编码 HEX、little-endian 二进制数据、样本及权重哈希、复现脚本、候选接口说明已交付。

这里的“完整本地验证划分”指指定代码在本机建立的 12 类验证索引，未知词选择与样本清单保存在 samples.json。
这是本地精度验证，不是官方 600 条统一评测通过证明。RTL 回归验证 A 运算核心；没有验证 B 的全矩阵调度和 C 的 SoC。

## 逐层精度和冻结数值格式

f 表示真实值 = 编码 × 2^(-f)，层编号从 0 开始。

| 层 | fx/fw/fy | 右移量 | 汇总 NRMSE | 最大单任务 NRMSE | 输入截幅/输出饱和数 |
|---|---|---|---|---|---|
%s

## 仍缺少什么

| 缺口 | 需要的资料或动作 | 谁负责推进 |
|---|---|---|
| 正式 E203 平台工程 | System Bus/NICE 协议、共享内存映射、参数装载仿真环境 | 团队向组委会取得，C 落地 |
| B 的矩阵调度与缓存 RTL | 99×64×256 循环、SRAM 读延迟、索引与写回；实例化 A 运算模块 | B，A 配合数值定位 |
| C 的接口与数据打包实现 | 寄存器、总线适配和驱动；按真实平台做参数及输出回读 | C，A 交叉检查 |
| ASIC 工具、工艺库和 SRAM 宏资料 | 合法可用的标准单元库、宏模型/面积/功耗、综合工具、SDC | 团队取得，C 运行评估 |
| 团队接口签收及独立交叉评审 | B 检查 A 的 RTL/期望值生成；A 检查 C 的打包与寄存器 | A/B/C 实际完成并记录 |
| 最终集成后的数值复核 | 对接 B/C 后逐位复测连续任务、复位、等待和 12 层参数切换 | B/C 集成，A 负责数值问题 |
| 官方统一评测 | 冻结后由组委会提供/选取的 600 条样本及 12 个性能任务 | 组委会与团队 |

前两项集成资料当前仓库没有，不能通过猜测地址或自行选一个 E203 工程来声称完成指定 SoC 验证。
当前 A 自包含运算与数值交付已完成；A 在最终联调、交叉评审和冻结版复核中的责任仍待团队集成后履行。

## AI 能做和不能替代的部分

AI 已实际完成脚本、数值实现、RTL、测试、运行日志和本地精度分析，也可以在资料齐全后继续协助集成和修复。
AI 无法凭空获得未公开的工艺库、宏模型、账号许可或尚未公布的官方评测数据；需由有权限的人提供或开通。
AI 不能把自身复查写成 B/C 本人已经独立评审，不能代替 A 本人理解设计、确认贡献和进行答辩。
对于没有运行环境或资料的 ASIC/SoC 项，不能生成真实通过证据，也不能承诺未知样本上的结果。
赛题当前范围不要求布局布线、流片或实体板卡；本次没有把这些额外事项列为必做缺口。

## 工具与验证边界

TensorFlow 2.4.0rc1 当前 PyPI 版本入口返回 404，本次使用 2.4.0 final；该差异与依赖锁定文件均保留。
检查点加载有旧版 GELU trackable 引用警告，但全部 %d 个模型权重已逐项独立比对，不依靠警告消失判断正确性。

本次使用 AMD ROSS `vivado-simulate-rtl` Skill。MCP `vivado_start` 报代理启动失败；
实际成功的检查通过原生 Vivado/XSim 2025.2 批处理执行。有效功能证据为 `xsim_simulate.log` 的终端 PASS 与对应编译/展开日志。
波形显示警告涉及大测试向量数组超出 GUI 显示位数，不涉及 DUT 结果；日志原样保留。未声称形式验证或代码覆盖率闭合。

RTL 可综合性另用 FPGA OOC 试跑。多拍数值转换版本为 277 LUT、290 寄存器、1 DSP，内部寄存器路径 WNS 为 +1.563 ns（6.667 ns 时钟约束）。
无锁存器或黑盒；这不是 ASIC 面积或时序结果，也没有真实顶层 I/O 约束、物理时钟延迟和布局布线证据。
因此不能据此声称已满足赛题 150 MHz、2.25 mm² 或功耗门槛。

## 使用入口

旧 `C:\\Users\\Sunuo\\Desktop\\FPGA_Project\\104_kwt_ffn_v0_1` 保持原样。
该草案采用 int32 偏置/输出与 8 路权重布局，本包采用 signed40 偏置、signed16 输出和单路运算接口。
B/C 需要按 `docs/INTERFACE.md` 明确签收，不能混用两版的配置和打包数据。

先阅读 `../README.md` 和 `../docs/INTERFACE.md`。
冻结 12 层数据位于 `../artifacts/real_12_layers/`。软件精度详见 `precision_report.json`，
RTL 真实回归详见 `xsim_simulate.log`，精确依赖见 `../requirements-lock.txt`。
本报告描述冻结交付内容；提交和推送状态以 Git 历史及远程分支记录为准。
'''%(len(audit),report['instrumentation_logits_max_abs_diff'],report['calibration_samples'],
        report['validation_samples'],100*report['max_layer_nrmse'],
        100*max(x['worst_task_nrmse'] for x in report['layers']),vectors['dot_cases'],
        vectors['requant_cases'],vectors['real_dot_cases'],vectors['synthetic_dot_cases'],'\n'.join(rows),len(audit))
    (reports/'STATUS.md').write_text(status,encoding='utf-8')
    files={}
    for folder in ['rtl','tb','model','scripts','docs','reports','artifacts']:
        for path in (root/folder).rglob('*'):
            if path.is_file() and '__pycache__' not in path.parts and path.name!='delivery_manifest.json':
                files[path.relative_to(root).as_posix()]=digest(path)
    for name in ['README.md','requirements.txt','requirements-lock.txt']:
        files[name]=digest(root/name)
    manifest={'status':'LOCAL_A_CORE_AND_NUMERICS_VERIFIED_SOC_PENDING',
        'files_sha256':files,'official_evaluation_pass':False,'asic_signoff_pass':False}
    (reports/'delivery_manifest.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
    print('A_DELIVERY_FROZEN files=%d max_nrmse_percent=%.6f'%(len(files),100*report['max_layer_nrmse']))

if __name__=='__main__':main()
