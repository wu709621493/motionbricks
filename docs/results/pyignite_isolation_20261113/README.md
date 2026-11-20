# 本轮独立复核证据

基线 main：`6f7c2dc67c3d640ebbb32b9f97ef4dbb0fa4e0b0`。候选源码由 source-hashes.json 绑定；具体提交以收录本目录的 PR head 为准。

- contracts.txt：52项运行，51通过、1项因缺少safetensors跳过；不是52/52。
- isolation-review.json：隔离reader/fsync超时、进程清理、check/exit返回和完整结果恢复。临时文件残留与进程清理分开。
- numpy-supervision.json：真实NumPy/LAPACK SVD已进入，外层监督约1秒截止并清理。
- pe-diagnosis-not-run.json：缺Torch，严格对照NOT_RUN，命令退出2；保留原容差和oracle，未改动态PE kernel。
- baseline-fault-results.json：此前旧提交942cf0e2的失败证据，不是当前候选的执行。
- wheel-smoke.json / wheel-manifest.json：源码目录外安装的本地wheel与worker可用性、模拟hwmon、完整结果SHA-256。wheel未发布到PyPI，二进制未入仓。
- harness-wrong-working-directory.txt：一次在tools/pyignite目录执行discover的设置失败；不是产品回归。后来在仓根重跑，结果见contracts.txt。

准确命令、验收与风险见 ../../pyignite_isolated_guard_zh.md。所有本机结果均不等于当前跨平台CI、真实温度、断电、独立硬件watchdog或完整G1验证。报告中的进程号与计时是原始观测，不要求跨机器逐字一致。
