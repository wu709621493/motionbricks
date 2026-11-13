# #99 后续：退化情形的可运行自检

日期：2026-11-13。基线：`f43c457d27126fbb3d6f3d62e896ad3c0f1d7161`。

[v0.1 立论](dimensional_transition_coupled_fields_zh.md)及作者原话保持原样。本补充检查其中几个可独立计算的极限，不把这些极限拼接成新的物理机制。

| 检查 | 方法 | 不能由通过结果推出的结论 |
| --- | --- | --- |
| 均匀标量场 | 固定 Minkowski 背景、无物质源、无反馈，指定无量纲 U=χ²/2；RK4 积分 χ''+χ=0，与 cos(t) 及初始能量 1/2 比较 | 未求解 Einstein–物质–标量耦合系统；此势能未经高维约化或实验拟合 |
| 薄壁传播 | ρ=R/R₀、τ=ct/R₀，解析轨迹 ρ=√(1+τ²)；有限差分检验速度，检查归一化能量及 v<c | 不是二向箔、真实降维、带引力/阻力的成核模拟 |
| 两个半径 | 无量纲静态能量 ρ²−ρ³ 在 ρ=2/3 达势垒顶，零能成核半径为 ρ=1 | 未计算成核率或触发能 |
| 高斯力律 | 对 d=2/3/4 的纯幂律用对数斜率恢复 d_F | 不是实验测量，不能排除其他媒介或证明额外维度 |

薄壁式由 v0.1 第7节直接无量纲化，γ=ρ；能量检查只验证这些解析表达式的一致性，不能独立验证解析解。有限差分速度检查与标量场数值积分另外报告。所有浮点检验限于脚本明示的有限域。阈值是这些算例的软件验收精度，不是实验置信区间。

```bash
python -S -m unittest discover -s tests/dimensional_fields -v
python -S tools/research/check_dimensional_identities.py
# 故意用过粗步长：应输出 FAIL 并退出 1，不能吞掉失败。
python -S tools/research/check_dimensional_identities.py --steps 32
```

默认4000步，最多20000步，输出完整 JSON。退出0为算例通过、1为精度失败、2为参数拒绝。`full_coupled_field_solver`、`dimension_change`、`experimental_fit` 均保留 `NOT_RUN`。

文献沿用 v0.1 的 Coleman (1977)，[原始论文](https://doi.org/10.1103/PhysRevD.15.2929)。出版社同时列出[1977年勘误](https://doi.org/10.1103/PhysRevD.16.1248)；本轮读取了出版社摘要及勘误入口，未取得全文或重新核对原文推导。这里实现的是仓内已有公式的独立算例，不声称完成全文复现。
