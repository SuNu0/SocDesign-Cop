# SocDesign-Cop

本科生组 KWT-1 前馈第一线性层加速器项目。

- [A 同学交付说明与复现命令](A_work/README.md)
- [已验证结果、剩余缺口和验证边界](A_work/reports/STATUS.md)
- [A/B/C 运算接口及数据格式](A_work/docs/INTERFACE.md)
- [冻结的 12 层真实测试数据](A_work/artifacts/real_12_layers/)

当前 A 运算核心与数值模型已完成本地验证：4445 条验证样本最差层 NRMSE 为
0.027578%；XSim 通过 9441 组点积及 2769 组数值转换用例。
E203 集成、指定 ASIC 工艺下的综合评估、独立交叉评审和官方统一评测仍待完成。

下载后可先检查交付文件是否完整，以下命令仅需 Python 标准库：

```powershell
python A_work/scripts/verify_delivery.py
```

完整运行环境和步骤见 A_work/README.md。大数据集、虚拟环境及仿真构建缓存不纳入 Git。
