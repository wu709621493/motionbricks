# Rust / PyIgnite benchmark 测评

日期：2026-11-10。**码本值得保留为独立实验；大 Linear 没有扩张重复实现的性能依据。**
所有数字来自本次主机执行；不能从这些 API 边界不同的数字推出“Rust 语言比 C++/PyTorch 快”。

## 环境与方法

- AMD EPYC 7763，Linux x86_64，glibc 2.41；Python 3.12.14、NumPy 2.3.5、Torch 2.15.0+cpu。
- Rust 1.85.0，Cargo release 默认 opt-level=3；C++ 使用 `-std=c++17 -O2 -ffp-contract=off`，无 fast-math、无 target-cpu=native。
- PyTorch 单线程；OMP/OPENBLAS 线程环境设为 1。共享主机，未锁频，未控制温度/电源策略，固定测量顺序；没有跨机器统计推断。
- 每例 5 次预热，30 个样本，每样本 20 次调用。表为批均值的中位数，原 JSON 留存全部样本/min/p95。p95 是**批均值**分位数，不是单请求尾延迟。
- 码本：8 heads × 10 entries × 32 width；1/32/256 行；overall 与 head 两种模式。
- Linear：`[rows,in] @ W[out,in].T + b[out]`，三种形状；复用原 PyIgnite `ignite_linear(..., activate=0)`，没有新增 C++ 码本或冒称测了完整 FCBlock。
- dyadic 合成 FP32 夹具使这 9 组输出能逐元素精确比较；同时保留原 seeded 随机 parity suite，避免把简单可精确表达的夹具当成全部数值证据。

## 调用边界

| 列 | 计入什么 | 不计入什么 |
|---|---|---|
| Rust native | 原生函数、输出分配/初始化/释放、输出 finite 扫描 | 预先构造并验证的输入、进程启动、序列化 |
| PyIgnite C++ | 未修改的 C ABI kernel，输入/权重 finite 扫描；harness 每次分配/初始化/释放输出 | Python/ctypes、进程启动 |
| PyIgnite ctypes | Python NumPy 输出分配、ctypes 验证/调用、同一 C ABI kernel | FCBlock 多层封装、权重构造 |
| Torch Python | Python 调度、Torch 运算和输出分配 | NumPy→Tensor 转换、权重构造 |

Rust 将输入验证放在构造期，C++ kernel 每次扫描输入/权重；优化级别、验证工作与分配策略也不同。
因此这是**当前实现与边界的成本比较**，不是纯语言或等工作量的编译器竞赛。

## 本次测量（µs/调用）

| 案例 | Rust native | PyIgnite C++ | PyIgnite ctypes | Torch Python |
|---|---:|---:|---:|---:|
| codebook_overall_1 | 0.235 | — | — | 54.528 |
| codebook_heads_1 | 0.423 | — | — | 12.801 |
| codebook_overall_32 | 6.909 | — | — | 107.469 |
| codebook_heads_32 | 7.508 | — | — | 54.827 |
| codebook_overall_256 | 61.305 | — | — | 379.539 |
| codebook_heads_256 | 62.165 | — | — | 291.438 |
| linear_1_32_32 | 1.293 | 1.173 | 17.493 | 2.516 |
| linear_32_128_64 | 271.357 | 230.301 | 273.037 | 9.558 |
| linear_32_256_256 | 2496.317 | 2085.595 | 2507.446 | 67.889 |

9 组正确性门槛全部通过，最大绝对差为 0；码本还用直接索引构造独立预期。
大 Linear `[32,256]→[32,256]` 的 Rust 中位数 2496.3 µs，
Torch 67.9 µs；这一差距支持保留优化库作为通用矩阵路径。
Rust 码本省去了当前 Python 调度和张量操作链，但没有 Python 生产绑定；未来接入必须重新计入边界成本。

另测 30 次 `parity_probe` 的单元素 ReLU 子进程往返：中位数 **1921.3 µs**。
此项含 Python subprocess、启动、解析、计算和文本输出；不能拿它当 Rust kernel 时间，也不能将 CLI 逐帧方案当成低延迟接入。

二进制（未 strip）：Rust benchmark 506,568 B，
Rust parity probe 510,280 B，C++ benchmark 18,392 B。
尺寸比较不包含动态库、编译器或 Python 依赖；strip 后的 Rust 与系统兼容边界见[复古性报告](rust_retro_review_zh.md)。

## 原有 PyIgnite 数值门槛：本次发现失败

完整保留原 8 组夹具与 `atol=2e-5, rtol=2e-5`，重新检查全部案例：7 通过，1 失败。
`PE-4096-64` 的 **3652/262144** 元素不满足门槛，最大绝对误差 **0.0001220703125**。
4 组 FC 均通过；其最大误差为 **2.6226043701171875e-6**。10 次重复输出一致并不意味着相对 oracle 正确。

首次用 NumPy 2.5.4 发现该问题；换回 PyIgnite 固定的 2.3.5 后相同失败仍在，
因此不能将失败归因于 NumPy 升级。后续[就绪诊断](rust_pr66_readiness_zh.md)将本机偏差隔离至
Torch 与 libm 的一个 exp 频率相差 1 ULP，被较长序列放大。本 PR 不修改 C++ kernel，不放宽容差。
原 `validate.py` 会在失败处退出；严格审计逐项记录后同样返回 1。
CI 的合并门槛改为与固定 main 实际构建结果比较、禁止新增回归；其通过不代表严格 parity 全通过。

## 证据与复现

- [benchmark.json](results/rust_integration_20261110/benchmark.json)：样本、编译器、CPU/affinity、版本、源文件 SHA256、整进程 VmHWM、输出哈希。
- [Rust 当前 parity](results/rust_integration_20261110/rust-parity.json)：原 14 数值/6 异常通过；随机 Linear 最大误差约 2.10e-5。
- [PyIgnite 固定版本完整审计](results/rust_integration_20261110/pyignite-audit.json)与[首次 NumPy 2.5.4 审计](results/rust_integration_20261110/pyignite-audit-numpy254.json)。
- [复现命令及验收标准](rust_integration_review_zh.md#5-准确复现命令与验收)。

测量时本地源码提交为 `f8d522fcf46b13336e21a074fc18c29f6a8fdff2`；结果文件等未提交导致 `git_dirty=true`，
本地 commit 不保证可在 GitHub 查询；JSON 中源码哈希给出准确测量输入。历史 `native/motionbricks-core/tests/parity-results.json`
和 `docs/results/pyignite_v1.json` 均保留，禁止将历史数据改名充当当前测量。

本地结果不是三平台复现。原生 ARM64/macOS 构建测试与 x86_64 Torch 对照的范围不同。
没有执行真实 G1 checkpoint、完整 ONNX 导出或机器人控制，没有测瓦特或能效。
