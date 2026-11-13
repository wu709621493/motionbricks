# Rb-14 共模协方差的数值抵消修复

基线：`f43c457d27126fbb3d6f3d62e896ad3c0f1d7161`。日期：2026-11-13。

原实现使用 Sherman–Morrison 的相减形式。当独立噪声方差 v 远小于共模向量 u 的平方时，两个几乎相等的浮点数相减会丢失有效位。

单通道例：f=10⁸ Hz，white=0.01 Hz√s，floor=0，共模分数σ=0.01，τ=1 s，a=b=1。解析逆方差为约 `5e-13`，基线返回约 `5.551115123125783e-13`，相对误差约11%。进一步减小独立噪声可使原式返回零。这是极端输入的回归夹具，不是已测器件噪声。

对 C=vI+uuᵀ，令 s=|u|、q=u/s。使用恒等式：

$$
a^TC^{-1}b=\frac{a\cdot b}{v+s^2}
+\frac{s^2}{v(v+s^2)}\sum_{i<j}(a_iq_j-a_jq_i)(b_iq_j-b_jq_i).
$$

该式来自 Lagrange 恒等式，与原协方差模型一致；s=0 单独处理。对 a=b，各项非负，避免原式中两个大数相减。代价为 O(n²)，当前仅1/3通道。交叉内积仍可能因真实结果接近零而丢失相对精度，不能称为任意条件数下的高精度求逆器。

新增回归覆盖：单通道解析逆方差、共模/差模本征方向、80位 Decimal 的独立2×2矩阵求逆，以及非有限向量/方差下溢拒绝。未改变噪声参数、物理模型、容差或熵声明；已有 `docs/results/rb14_phase1/` 保留为历史结果，不覆盖。重新计算须写入新目录：

```bash
python -S -m unittest discover -s tests/rb14 -v
python -S -m motionbricks.rb14_feasibility --config configs/rb14_phase1.json --out-dir /tmp/rb14-stability
```

此修复不增加任何硬件制造、捕获、频率测量、量子随机性或 PUF 安全证据。
