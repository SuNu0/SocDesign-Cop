from pathlib import Path
import html
import json
import re

from reportlab.lib import colors
from reportlab.lib.enums import TA_LEFT, TA_CENTER
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak,
    KeepTogether,
)
import reportlab.lib.textsplit as textsplit
import reportlab.platypus.paragraph as paragraph_module

# Extend ReportLab's Japanese-centric line-break list for Chinese punctuation.
textsplit.ALL_CANNOT_START += '，；：？！）》”’'
paragraph_module.ALL_CANNOT_START = textsplit.ALL_CANNOT_START

ROOT = Path(r'G:\0_TEMP\7_qiansai_chipdesign')
OUT = ROOT / 'output'
OUT.mkdir(exist_ok=True)
PDF = OUT / '本科生组三周分工报告.pdf'
MD = OUT / '本科生组三周分工报告.md'

# One shared content source keeps the printable and editable versions aligned.
pages = []
def page(title, subtitle=None):
    p = {'title': title, 'subtitle': subtitle, 'blocks': []}
    pages.append(p)
    return p['blocks']
def para(b, text): b.append(('p', text))
def head(b, text): b.append(('h', text))
def bullets(b, items): b.append(('bullets', items))
def table(b, headers, rows, widths): b.append(('table', headers, rows, widths))

b = page('芯片设计赛道三人分工报告', '本科生组  三周执行计划')
para(b, '建议采用“A 负责模型与运算单元，B 负责矩阵调度与缓存，C 负责 SoC 接口与综合评估”的分工。三人各自主写一组可综合 RTL、完成本模块单元验证，再共同完成加速器和 E203 SoC 验证。A、B、C 可直接替换为实际姓名。')
head(b, '一 分工总览')
table(b, ['成员', '专项主责', '必须独立承担的 RTL', '最终验证主责'], [
    ['A 同学', '预训练模型部署与研究\n数值方案和参考模型', '长度 64 点积\n偏置与舍入饱和\n数值转换', '浮点精度评估\n逐位数值比对\n测试数据维护'],
    ['B 同学', '加速器架构与顶层集成\n矩阵计算和数据复用', '矩阵循环与计算调度\n内部 SRAM 缓冲\n结果组织和写回请求', '模块联调与矩阵验证\nSoC 回归组织\n问题闭环'],
    ['C 同学', '逻辑综合与报告评估\nSoC 接入和驱动', 'System Bus 接口适配\n配置与状态寄存器\n共享 SRAM 访问适配', '驱动和总线验证\n综合前后功能检查\n时序面积功耗评估'],
], [0.65, 1.55, 1.80, 1.70])
para(b, '专项主责表示该同学对成果和问题闭环负责，不表示其他成员不参与。不能只交模型脚本或综合报告：每人均须交付本人主写的 RTL、单元测试、交叉评审记录和最终验证结果。')
head(b, '二 三周内必须完成的范围')
bullets(b, [
    '完成赛题第 1 至 3 项：长度 64 点积及数值处理；99×64 输入与 64×256 权重相乘并加偏置；99×256 输出写回；E203 集成、驱动、仿真和逻辑综合。',
    '同一硬件依次装载 12 层各自的前馈第一线性层参数与对应输入。这里是 12 组线性层任务，不是把第一线性层输出直接串成十二层编码器。',
    '统一工作频率和综合目标为 150 MHz；新增加速器、接口逻辑和内部 SRAM 宏面积合计不超过 2.25 mm²；RTL 与提交的软件数值模型逐位一致。',
    '本科数值门槛为 12 层分别汇总样本后取最大 NRMSE，不超过 3%；性能测试中的每个任务还须单独满足 3% 门槛。',
])
para(b, '三周优先完成全部必做项。GELU、第二线性层、注意力及完整编码器均不进入本次承诺范围；基础版本稳定后，只选一项风险较小的复用或流水线优化。')

b = page('A 同学任务书', '预训练模型部署与研究  运算 RTL  数值验证')
head(b, '一 模型部署与研究')
bullets(b, [
    '在计算机端复现 ARM-software/keyword-transformer 提交 237e4097，使用 models_data_v2_12_labels/kwt1 及 best_weights，固定依赖、权重校验值和 labels.txt。运行推理模式，关闭随机增强和 Dropout；不重新训练、微调或蒸馏，不改变模型层数与维度。',
    '按指定代码处理 Speech Commands V2。训练划分只用于无梯度标定，验证划分用于调试与精度检查；测试划分不参与量化参数或数值配置调整。',
    '在每层注意力、残差和第一处 LayerNorm 之后，提取该层前馈第一线性层的 99×64 输入、64×256 权重及 256 项偏置。核对框架权重的转置方向，生成 99×256 浮点参考。',
    '研究数据范围、逐层动态范围、量化尺度及误差来源，形成数值格式说明。模型部署指电脑端推理、数据提取与参数转换，不要求在 E203 上部署完整 KWT-1。',
])
head(b, '二 必须完成的 RTL')
para(b, '主写 dot64_mac.sv、bias_requant.sv 及其单元测试，实际文件名可调整。实现长度 64 点积、清零与累加、偏置对齐、输出尺度转换、舍入和饱和；提供可供 B 复用的握手接口。模块必须参与最终线性加速器计算。')
para(b, '数值方案先以便于实现的整数定点为候选，例如 16 位输入和权重、40 位累加起步。长度 64 的有符号 16×16 位乘积累加至少按 38 位评估，偏置对齐后仍需重新核算范围。位宽和尺度必须通过真实权重与验证数据确定，不能假定该候选天然满足 3% 门槛。')
para(b, '软件模型逐步复现 RTL 的符号扩展、运算顺序、有限位宽截断、偏置、舍入、饱和和编解码，不能只用浮点矩阵乘法代替。第 3 天形成可测版本，第 4 天完成首次 12 层数值检查并冻结首版格式。')
head(b, '三 交付与验收')
table(b, ['交付物', '验收条件'], [
    ['模型与数据脚本', '从音频到各层线性输入、权重、偏置和参考输出可复现；记录模型版本、样本编号、数据划分和校验值。'],
    ['浮点及软件数值模型', '可对 12 层逐层计算 NRMSE，并生成与 RTL 一致的编码数据和期望输出；解码结果全部为有限值。'],
    ['运算 RTL 和单元验证', '正常值、正负极值、零、舍入临界点、饱和、复位、反压及连续任务通过；输出与软件模型逐位一致。'],
    ['数值格式与精度报告', '写明每类位宽、符号、尺度、字节序、偏置对齐和误差；报告每层误差与最差层，内部精度目标可争取低于 2%。'],
], [1.45, 4.25])
para(b, '验证分工：A 编写运算模块自测；B 交叉复核其 RTL 和期望结果生成方式；A 在最终联调中负责定位数值不一致，并交叉检查 C 的数据打包与寄存器读写。')

b = page('B 同学任务书', '矩阵调度与缓存 RTL  加速器顶层  联调组织')
head(b, '一 架构与 RTL')
bullets(b, [
    '主写 linear_ctrl.sv、tensor_buffer.sv、sram_wrapper.sv 和 linear_accel_top.sv。将 A 的点积模块组成完整线性层，管理 99 行、256 个输出通道和长度 64 的内积循环。',
    '负责内部 SRAM 组织、输入和权重复用、读写仲裁、地址与索引、偏置分发、结果排序及写回请求。C 负责将这些访存请求转换成平台总线事务。',
    '按平台指定的 16 bits×128、16 bits×1024、16 bits×4096 单端口或双端口宏实现内部存储，明确读延迟、端口冲突和读写同址行为。仿真存储模型与综合宏封装保持一致。',
    '先建立单路或低并行度可运行版本，再由综合结果决定是否扩展为 2 路或 4 路。并行扩展同时检查 SRAM 带宽和端口数量，不以增加乘法器数量代替带宽设计。',
])
head(b, '二 SoC 集成与验证组织')
para(b, 'B 负责顶层连线和集成清单，C 负责平台接口与驱动落地，A 提供可复现的输入、参数和参考输出。B 维护统一回归入口、失败用例列表和问题优先级，确保所有模块合入后可以一键复测。')
para(b, '完成输入装载、计算、输出写回的完整状态机。done 只在所有输出写回事务确认完成后产生；任务开始时清理上一任务的累加状态和有效标记，正确处理连续任务、复位及下游等待。')
head(b, '三 交付与验收')
table(b, ['交付物', '验收条件'], [
    ['架构与存储说明', '列明数据流、循环顺序、并行度、宏数量和容量、地址布局以及端口带宽；可对照 RTL。'],
    ['矩阵调度和缓冲 RTL', '完整输出 99×256 项；无漏算、重复、错位或越界；支持 12 层各自参数更换和连续任务。'],
    ['加速器顶层验证', '先小规模调试索引，再用固定赛题维度验证；注入 SRAM 延迟和接口反压；结果与 A 的软件数值模型逐位一致。'],
    ['SoC 回归与问题清单', '标准任务、12 层参数切换、复位、等待和连续任务均有日志；失败记录包含输入版本、提交号和复现命令。'],
], [1.45, 4.25])
head(b, '四 控制工作量')
para(b, '全矩阵包含 99×64×256＝1,622,016 次乘加。先验证结果顺序和端到端正确性，再做输入复用、权重复用或少量流水线优化。三周内不引入复杂指令集、通用 Transformer 调度器或多种并行架构。')
para(b, '验证分工：B 完成本模块单元验证和顶层联调；C 交叉检查 SRAM 时序、状态机与读写冲突；B 最终组织三人完成 SoC 回归并汇总通过记录。')

b = page('C 同学任务书', 'SoC 接口 RTL  逻辑综合  时序面积功耗评估')
head(b, '一 接口 RTL 与驱动')
para(b, '主写 soc_bus_adapter.sv、accel_csr.sv 和 shared_mem_adapter.sv。优先采用平台 System Bus 接入，复用现有总线协议和访问接口；若平台工程表明 NICE 接入明显更省时，由三人在第 2 天前确定并更新接口说明。只保留一种接入方式。')
bullets(b, [
    '实现配置、启动、busy、done、错误状态及结果完成管理；实现输入、权重、偏置和输出的地址配置。地址及寄存器位定义依据平台内存映射冻结，不自行假定总线协议。',
    '负责总线请求应答、等待和错误传播、共享 SRAM 访问与字节打包。复用平台已支持的数据搬运方式，不新增通用 DMA 或 DDR 控制器。',
    '编写 E203 驱动和最小运行示例，完成参数装载、命令下发、状态轮询及结果读取；与 B 协作接入平台参数装载仿真环境。',
])
head(b, '二 从第一周开始综合')
para(b, '第 1 至 2 天确认综合工具、指定标准单元库、SRAM 的仿真及综合模型、面积与功耗资料和使用权限。第 3 至 4 天跑通模块及框架综合，第 7 天完成首个整体基线。缺失宏模型或功耗资料时立即登记缺口并推动获取，不能将其按零面积或零功耗处理。')
para(b, '综合时钟设为 150 MHz，周期约 6.667 ns。沿用平台有效的 I/O、时钟和例外约束，报告约束完整性、关键路径、时序裕量、锁存器及未解析单元。加速器和 SoC 均纳入检查；用真实约束判断是否达标。')
head(b, '三 报告与功能核查')
table(b, ['评估内容', '必须提交的证据'], [
    ['综合与时序', '可复现脚本、SDC、库和工具版本、综合网表、时序报告及违例处理记录。'],
    ['面积', '新增加速器标准单元、接口逻辑和内部 SRAM 宏分项及合计；复用 E203、共享 SRAM 和固定平台面积单列。'],
    ['功耗与能耗', '同一任务窗口的 SAIF/VCD、活动映射与覆盖记录、SRAM 功耗建模、平均功耗和单任务能耗。'],
    ['综合前后功能检查', '使用相同向量核对 RTL 与综合网表输出；采用工具支持的门级仿真或等价检查，保留日志和差异闭环记录。'],
], [1.40, 4.30])
para(b, '验证分工：C 自测寄存器、总线等待、错误、字节序与驱动；A 交叉核对参数和输出打包；C 负责最终综合评估，A 复核数据与精度口径，B 复核计时边界及冻结配置。赛题不要求布局布线、物理验证或流片。')

b = page('接口边界与协作规则', '第 2 天完成首版  三人共同确认')
head(b, '一 明确模块之间的责任')
table(b, ['连接关系', '提供方负责', '接收方负责'], [
    ['A 运算模块与 B 调度', 'A 定义运算语义、有效输入接受条件、结果有效和数值转换；输出确定的计算结果。', 'B 按约定顺序提供 64 对操作数、偏置及任务边界，接收结果并组织矩阵位置。'],
    ['B 加速器与 C 接口', 'B 生成逻辑访存请求、张量索引和输出数据，标明所访问的张量与偏移。', 'C 按配置基地址转换为平台地址和总线事务，返回读数据、写确认与错误。'],
    ['C 寄存器与 B 顶层', 'C 保存配置，生成一次有效启动，提供状态读取；busy 时按约定处理重复启动。', 'B 接受启动后执行任务，反馈 busy、完成和错误；完成前确保输出写回已确认。'],
    ['A 数据文件与 B C 验证', 'A 生成编码数据、逐位期望值、浮点参考及清单，标明版本和样本来源。', 'B C 使用统一装载与编解码规则，不各自修改权重转置、尺度、地址顺序或字节序。'],
], [1.20, 2.25, 2.25])
head(b, '二 必须冻结的接口说明')
bullets(b, [
    '数值约定：输入、权重、偏置、累加及输出位宽，符号和尺度，累加及偏置顺序，舍入、饱和和打包规则。',
    '时序约定：时钟复位、valid/ready 或等效握手、反压时数据保持、点积首尾标记、可变延迟及 SRAM 读延迟。',
    '地址约定：矩阵布局、权重是否转置、步长、基地址、偏移单位、对齐和字节序；读写端口及合法范围。',
    '任务约定：启动接受、重复启动、busy/done/error、输出写回完成条件、复位中止和下次任务的状态清理。',
])
head(b, '三 合入与交叉验证')
para(b, '每个成员先自测，再按“A 检查 C、C 检查 B、B 检查 A”交叉评审。被评审者负责修复本模块问题。涉及位宽、延迟、地址布局和寄存器的改动，先更新接口说明，再由受影响成员更新脚本、驱动和测试。')
para(b, '每天用 15 分钟同步已完成项、阻塞与次日交付；每天保留一个可运行版本。第 7、14、18 天各建立里程碑版本。第 18 天冻结功能，第 19 天冻结最终网表及测试配置，最后两天只处理阻断问题、复现和材料整理。')
para(b, '建议按 rtl/compute、rtl/control、rtl/interface、sw、model、tb、scripts、reports 组织目录。变更记录保留成员、提交号和验证日志，便于答辩说明三人的实际 RTL 贡献。')

b = page('三人共同验证方案', '单元自测  交叉复核  加速器与 SoC 验收')
head(b, '一 验证责任和用例')
table(b, ['验证层次', '主责与协作', '用例及通过标准'], [
    ['运算模块', 'A 主责\nB 交叉检查', '零、正负数、极值、累加范围、偏置、舍入边界、饱和、复位和连续点积；与整数数值模型逐位一致。'],
    ['调度和缓存', 'B 主责\nC 交叉检查', '行列边界、首尾地址、端口冲突、读延迟、反压、输出顺序；无越界、遗漏和重复。'],
    ['接口和驱动', 'C 主责\nA 交叉检查', '寄存器读写、数据打包、启动和状态、总线等待、错误、写回确认及复位；与平台协议一致。'],
    ['完整线性层', 'B 组织\nA 提供数值检查\nC 注入接口等待', '99×64 乘 64×256 加偏置，输出全部 99×256 项；覆盖 12 层参数，每项输出逐位对照。'],
    ['E203 SoC', 'C 驱动运行\nB 负责集成回归\nA 复核输出', '通过平台装载数据，由 E203 启动并读取结果；覆盖连续任务、参数切换和复位；验证不是测试平台代算。'],
    ['综合后检查', 'C 主责\nA B 复核', '与 RTL 使用同一向量和配置；综合网表或等价检查结果一致；时序、面积及活动覆盖记录完整。'],
], [1.05, 1.45, 3.20])
head(b, '二 数值精度如何判断')
para(b, 'A 对每层汇总本地评估样本，计算“输出误差均方根 ÷ max(浮点参考均方根，10 的负 8 次方)”，再取 12 层中的最大值，与 3% 门槛比较。优先覆盖完整验证划分；若资源受限，报告实际样本数和范围，不以少量样本宣称已通过官方评测。')
para(b, 'RTL 调试先从每层至少一条真实验证样本建立 12 个任务，再加入独立边界向量。每次回归都比对软件数值模型的编码输出；不能把“接近浮点结果”当成逐位一致。官方 600 条评测样本由组委会选取，不能把它们作为调参数据。')
head(b, '三 性能评估必须使用统一窗口')
para(b, 'C 建立本地 12 任务性能流程，覆盖 12 层各自参数。每个任务开始前清空任务数据与参数缓存；从输入和参数开始装载计时，到所有结果写回确认后结束。参数装载、总线等待和 E203 调度均计入，任务间测试平台复位时间不计入。电脑端预处理和一次性格式转换不计入。')
para(b, '记录总周期 C_total，在 150 MHz 下总时间 T＝C_total÷150,000,000；吞吐量＝12÷T；单任务能耗＝平均功耗×T÷12。A 复核这 12 个任务各自误差不超过 3%，B 复核开始结束点，C 汇总同一冻结配置、网表和条件下的结果。')

b = page('三周进度与里程碑', 'D1 为实际启动日  以连续 21 天安排')
para(b, '前 7 天形成可运行基线，中间 7 天完成 SoC 闭环与指标检查，最后 7 天完成验证、有限优化和交付。所有同学从第一周开始写 RTL 和测试，综合与数值评估同步推进。')
table(b, ['时间', 'A 同学', 'B 同学', 'C 同学', '共同验收点'], [
    ['D1-D2', '模型环境与权重校验；提取真实线性输入；数值候选', '模块划分、数据流和 SRAM 方案；搭建顶层骨架', '确认平台、库和工具；接口与寄存器方案', '三人确认接口、数据布局和第一批交付清单'],
    ['D3-D4', '软件数值模型；MAC 与偏置 RTL；首次数值检查', '调度和缓冲 RTL；接入运算接口', '接口 RTL 与驱动骨架；跑通模块和框架综合', '冻结首版数值格式；真实数据能进入仿真'],
    ['D5-D7', '运算自测；12 层真实向量；精度报告首版', '完整维度计算和写回；单层加速器回归', '接口自测；整体基线综合；时序面积初估', 'M1 真实线性任务逐位通过；有首份综合报告'],
    ['D8-D10', '覆盖更多验证样本；定位数值差异', '参数切换、复位、等待和连续任务；顶层集成', '驱动和平台装载联调；收集第一版活动数据', '至少一个 E203 驱动的端到端任务通过'],
    ['D11-D14', '12 层精度复测；交叉检查数据打包', '12 层参数 SoC 回归；交叉检查运算模块', '修复时序面积问题；综合前后检查；功耗流程', 'M2 全部必做功能闭环；精度与综合指标复核'],
    ['D15-D17', '精度回归；记录优化前后误差', '只实施一项小规模优化；保留基线', '同条件综合与测量；输出优化对照表', '优化不破坏功能、精度、150 MHz 与面积预算'],
    ['D18-D19', '冻结模型脚本和数值配置；汇总数值证据', '冻结功能和 RTL；完整回归；整理集成说明', '冻结网表和约束；12 任务测量与报告定稿', 'M3 同一冻结版本形成全部验收证据'],
    ['D20-D21', '复核输入和数值脚本复现；答辩材料', '全新目录复现；工程打包；答辩演示', '复核综合和测量复现；报告与日志归档', '三人联合签收；D21 留作提交缓冲'],
], [0.85, 1.19, 1.19, 1.19, 1.38])
head(b, '里程碑未通过时的处理')
para(b, 'M1 未通过：三人集中修复数值、地址和接口，取消选做。M2 未通过：停止并行度扩展、双缓冲和新增流水线，只修必做功能、精度和综合问题。M3 未通过：不得混用早期配置的报告，回退到最近可复现的合格基线并重新测量。')
para(b, '每项问题只指定一个主责人，并写清复现步骤、影响范围、计划关闭日期和复测人。无法获得平台或库资料的阻塞在 D2 前暴露；D21 不安排新功能。')

b = page('交付验收与执行清单', '每人有 RTL  三人都验证  一份工程可复现')
head(b, '一 最终交付物和主责')
table(b, ['交付包', '主责', '必须包含'], [
    ['模型和数值包', 'A', '模型及数据版本、权重校验、提取和转换脚本、软件数值模型、格式说明、12 层精度表与测试向量。'],
    ['RTL 和仿真包', 'B 汇总\n三人各交本模块', '三组 RTL、宏封装、单元和顶层测试平台、SoC 仿真、回归脚本、通过日志及问题关闭记录。'],
    ['平台软件包', 'C\nB 集成', 'E203 驱动、装载与运行示例、内存和寄存器说明、完整运行命令。'],
    ['综合和评估包', 'C', 'SDC、脚本、综合网表、时序与面积、综合前后检查、SAIF/VCD 和功耗、周期吞吐及能耗记录。'],
    ['复现和答辩包', 'B 汇总\n三人复核', 'README、依赖和工具版本、文件校验、冻结提交号、设计引用、成员贡献、优化对照及答辩材料。'],
], [1.12, 1.05, 3.53])
head(b, '二 提交前共同确认')
bullets(b, [
    '每位成员都有可定位的本人 RTL、单元测试与交叉评审记录；三人均参加最终 SoC 回归和结果签收。',
    '12 层参数切换、固定矩阵形状、输出完整写回、复位及连续任务通过；RTL 与软件数值模型逐位一致；精度和性能任务误差满足赛题要求。',
    '150 MHz 时序达标，新增面积不超过 2.25 mm²。面积包含内部 SRAM 宏且不重计；复用平台面积单列。',
    '功耗统计覆盖 E203、加速器、互连和 SRAM 的动态与静态功耗；活动映射有覆盖检查。全部性能指标来自同一冻结配置和网表。',
    '在全新目录按 README 重跑仿真、数值检查和综合；日志、报告、配置和提交号相互对应。',
])
head(b, '三 主要风险和处理')
para(b, '精度不达标由 A 先检查权重方向、LayerNorm 后取数位置、尺度与舍入，再调整数值格式；B C 同步更新接口。时序或面积超限由 C 定位，B 优先降低并行度或优化存储，A 配合运算流水线或位宽调整。接口联调落后由 B C 使用真实小用例共同闭环，不再增加架构复杂度。')
para(b, '优化只保留一个变量，例如权重复用或简单流水线；精度、吞吐、能耗和面积均在相同条件下比较。新配置若未完成全部复测，就不替换已通过的基线。')
head(b, '四 第一日立即执行')
para(b, 'A 跑通指定权重推理并导出一个真实线性层样本；B 画出数据流并建立调度与缓冲 RTL 骨架；C 跑通平台示例和综合最小工程，列出缺失库与宏资料。当天汇总三个 RTL 模块列表和第二天的接口冻结事项。')
para(b, '依据为《嵌赛芯片设计赛道题目》正式赛题，重点参照印刷页码 3 至 8、10 至 13 页。赛题规则用于界定设计与验收范围；上述人员安排、模块文件名和 21 天节奏为团队执行建议。')

# Markdown is the editable counterpart; no visual-only text is omitted.
md = []
for i, p in enumerate(pages):
    md.append(('# ' if i == 0 else '## ') + p['title'])
    if p['subtitle']: md.extend(['', p['subtitle']])
    md.append('')
    for block in p['blocks']:
        if block[0] == 'p': md.extend([block[1], ''])
        elif block[0] == 'h': md.extend(['### ' + block[1], ''])
        elif block[0] == 'bullets':
            md.extend(['- ' + x for x in block[1]] + [''])
        elif block[0] == 'table':
            headers, rows = block[1], block[2]
            md.append('| ' + ' | '.join(headers) + ' |')
            md.append('| ' + ' | '.join(['---'] * len(headers)) + ' |')
            for row in rows: md.append('| ' + ' | '.join(x.replace('\n', '<br>') for x in row) + ' |')
            md.append('')
MD.write_text('\n'.join(md), encoding='utf-8')

pdfmetrics.registerFont(TTFont('MSYH', r'C:\Windows\Fonts\msyh.ttc', subfontIndex=0))
pdfmetrics.registerFont(TTFont('MSYH-Bold', r'C:\Windows\Fonts\msyhbd.ttc', subfontIndex=0))
INK = colors.HexColor('#142535')
BLUE = colors.HexColor('#224762')
MUTED = colors.HexColor('#536575')
styles = {
    'title': ParagraphStyle('title', fontName='MSYH-Bold', fontSize=23, leading=32, textColor=colors.black, spaceAfter=6),
    'section_title': ParagraphStyle('section_title', fontName='MSYH-Bold', fontSize=19, leading=27, textColor=colors.black, spaceAfter=5),
    'subtitle': ParagraphStyle('subtitle', fontName='MSYH', fontSize=10, leading=16, textColor=MUTED, spaceAfter=16),
    'h': ParagraphStyle('h', fontName='MSYH-Bold', fontSize=12, leading=19, textColor=INK, spaceBefore=9, spaceAfter=5, keepWithNext=True),
    'body': ParagraphStyle('body', fontName='MSYH', fontSize=10.1, leading=16.4, textColor=INK, spaceAfter=7, wordWrap='CJK'),
    'bullet': ParagraphStyle('bullet', fontName='MSYH', fontSize=10.1, leading=16.4, textColor=INK, spaceAfter=6, leftIndent=10, firstLineIndent=-10, wordWrap='CJK'),
    'cell': ParagraphStyle('cell', fontName='MSYH', fontSize=9.3, leading=14.5, textColor=INK, wordWrap='CJK'),
    'th': ParagraphStyle('th', fontName='MSYH-Bold', fontSize=9.5, leading=14.5, textColor=colors.white, wordWrap='CJK'),
}
def ptxt(text, style):
    return Paragraph(html.escape(text).replace('\n', '<br/>'), styles[style])

PAGE_W, PAGE_H = A4
MARGIN_X = 43
W = PAGE_W - MARGIN_X * 2
story = []
for i, p in enumerate(pages):
    if i: story.append(PageBreak())
    story.append(ptxt(p['title'], 'title' if i == 0 else 'section_title'))
    if p['subtitle']: story.append(ptxt(p['subtitle'], 'subtitle'))
    for block in p['blocks']:
        if block[0] == 'p': story.append(ptxt(block[1], 'body'))
        elif block[0] == 'h': story.append(ptxt(block[1], 'h'))
        elif block[0] == 'bullets':
            for text in block[1]: story.append(ptxt('• ' + text, 'bullet'))
        elif block[0] == 'table':
            headers, rows, widths = block[1], block[2], block[3]
            total = sum(widths)
            data = [[ptxt(x, 'th') for x in headers]] + [[ptxt(x, 'cell') for x in row] for row in rows]
            t = Table(data, colWidths=[W * v / total for v in widths], repeatRows=1, hAlign='LEFT')
            t.setStyle(TableStyle([
                ('BACKGROUND', (0,0), (-1,0), BLUE),
                ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.white, colors.HexColor('#F1F5F8')]),
                ('GRID', (0,0), (-1,-1), 0.45, colors.HexColor('#D9D9D9')),
                ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
                ('LEFTPADDING', (0,0), (-1,-1), 7),
                ('RIGHTPADDING', (0,0), (-1,-1), 11),
                ('TOPPADDING', (0,0), (-1,-1), 7),
                ('BOTTOMPADDING', (0,0), (-1,-1), 7),
            ]))
            story.extend([t, Spacer(1, 8)])

def footer(canvas, doc):
    canvas.saveState()
    canvas.setFont('MSYH', 8)
    canvas.setFillColor(MUTED)
    canvas.drawString(MARGIN_X, 24, '本科生组  三周分工与验收计划')
    canvas.drawRightString(PAGE_W - MARGIN_X, 24, str(doc.page))
    canvas.restoreState()

doc = SimpleDocTemplate(str(PDF), pagesize=A4, leftMargin=MARGIN_X, rightMargin=MARGIN_X,
    topMargin=37, bottomMargin=41, title='芯片设计赛道三人分工报告',
    author='参赛团队', subject='本科生组三周执行计划', pageCompression=1)
doc.build(story, onFirstPage=footer, onLaterPages=footer)
(ROOT / 'tmp' / 'pdfs' / 'report_content.json').write_text(json.dumps(pages, ensure_ascii=False, indent=2), encoding='utf-8')
print(PDF)
print(MD)
