# PR #66 合并就绪整理

日期：2026-11-10。范围：将 Rust 码本实验整理为可审查、可合并的独立整合。
**采用“固定 main 上无新增回归”的合并标准；保留已有的 PyIgnite PE 严格 parity 失败。**
没有将该失败修复成通过，也没有取消严格审计、放宽容差或修改生产算子。

## 阻塞项与处置

1. 初版 PR 的 Rust Linux x86_64 / ARM64 CI 已通过；失败项是 PyIgnite `PE-4096-64`。
2. 从固定 main `3577bda46d023df84c4518c75cb85ccf702b11b8` 提取源文件，单独构建共享库，
   用相同 Python/NumPy/Torch 环境运行全部 8 组原夹具，再独立构建并测试当前分支。
   两边均为 7/8 严格通过；PE 失败的逐元素输出、参考值、超差掩码及全部统计量完全相同。
3. Rust 工作流中的 macos-14 初版任务未分配 runner 即被取消。改用仓库 CPU preflight
   已使用的 macos-15，继续执行相同 Rust 测试，并输出实际 rustc host；不把取消当通过。

## 回归门槛为何允许合并

PyIgnite kernel、Python 绑定、原校验夹具、上游 layers.py 的 SHA256 均与固定 main 一致。
本次 Rust 实验不接入 PyIgnite、主导出器或机器人运行路径。为修一个已经存在的 PE 差异而
改变位置编码语义，需要单独的算子和真实模型影响审查，不应混入这次隔离实验的整合。

`baseline_regression.py` 每次重新构建基线，不使用历史绿色记录替代执行。
只容许一个明确命名的既有失败 `PE-4096-64`，且要求基线本次也失败、两边失败案例的完整记录逐项相同。
缺失/重复案例、变更容差、环境不一致、新失败、已知失败变化、构建或审计异常都拒绝。
若后续正确修好 PE，当前全部通过可以接受；其他任意基线失败不能自动成为白名单。
5 项单元测试验证这些放行与拒绝条件。

严格审计原始状态依旧为 `FAIL`，独立脚本依旧退出 1。
新的合并检查命名为 **PyIgnite no-new-regression (known PE parity gap)**，输出
`PASS_NO_NEW_REGRESSION` 与 `strict_current_parity=FAIL`，上传两份完整严格审计报告，
避免把“无新增回归”误读为“已修复所有数值误差”。

## 本机偏差诊断

在 4096×64 夹具中，偶数通道 6 的 exp 参数为约 `-0.8634694219`。
Torch AVX2 路径与系统 libm expf 的频率结果相差 1 ULP：
约 `0.4216965139` 与 `0.4216964841`。乘以较大的位置索引后，phase 舍入差异被放大。
只把 Torch oracle 的 exp 频率换为 libm expf、保留 Torch FP32 phase 与 sin/cos，
即可消除原容差下的超差；记录见 [pe-diagnosis.json](results/rust_integration_20261110/readiness/pe-diagnosis.json)。
这是一项定位实验，不是修改生产 oracle，也不宣称所有 CPU/数学库都以同样方式舍入。

## 复现与证据

先按[整合审查](rust_integration_review_zh.md#5-准确复现命令与验收)准备固定环境。
基线 commit 必须存在于本地 git 对象库；CI checkout 使用 fetch-depth 0。

```sh
python -m unittest discover -s tests/rust_review -v
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python tools/rust_review/baseline_regression.py --output-dir /tmp/pr66-regression
python tools/rust_review/audit_pyignite.py --output /tmp/pr66-strict.json
# 前者：本机 PASS_NO_NEW_REGRESSION；后者：保留的严格 FAIL，退出 1。
```

本次[回归结论](results/rust_integration_20261110/readiness/regression.json)、
[现跑 main 严格结果](results/rust_integration_20261110/readiness/baseline-strict-parity.json)、
[当前分支严格结果](results/rust_integration_20261110/readiness/current-strict-parity.json)
可直接核对。此前 benchmark、复古审计与严格失败数据保留原样。

最终 Ready 状态以新 head 的 Rust 三平台检查、CPU preflight 与本基线回归检查为准。
真实 G1 模型推理、导出器替换、跨平台数值一致性及旧硬件实机验收仍在本 PR 范围之外。
