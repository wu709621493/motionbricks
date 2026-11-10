# PR #15 独立整合可行性审查

审查日期：2026-11-10。结论：**保留独立 Rust 码本实验；冻结重复的通用算子扩张。**
PR #66 的后续[合并就绪整理](rust_pr66_readiness_zh.md)已将 main 原有的 PE 偏差与本次整合分开：
固定 main 和当前分支分别构建、执行严格审计，以无新增回归作为合并门槛；不能称为全部数值 parity 通过。
本审查未修改、关闭或合并原 PR #15。

## 1. 固定输入与实际冲突

| 对象 | 本次核实值 |
|---|---|
| 用户给出的较早 main | `bc86b71864f76da521fe9ee1457d409c70862d4c` |
| 实际取得的最新 main | `3577bda46d023df84c4518c75cb85ccf702b11b8` |
| PR #15 head | `39b5553b64fc16c75a2eb58ec9e51e18f275857e` |
| merge base | `7d78474b0cd0fc9b2c7373df0620f65dcb831a82` |
| 本地三方合并实际冲突 | **仅 `README.md`，1 个连续冲突区** |
| PR 原始差异 | 12 文件，799 行新增，0 行删除 |

GitHub API 首次读取短暂返回 `mergeable=null/unknown`，后续返回 `false/dirty`。
PR API 的 `base.sha` 与 branches/main 返回值不同；本审查以实际 fetch 的 main SHA 为准，
不使用该缓存字段替代当前分支。证据见 [provenance.json](results/rust_integration_20261110/provenance.json)。

冲突发生在旧 README 的 sleep supervisor 段落之后（旧版约 302 行，新 main 约 313 行）。
main 在这里继续追加 oyasumi、其他研究与创作入口；PR #15 在同一文件末尾追加
`Experimental Rust inference core`。这是共同尾部的并发追加冲突，没有 Rust/C++ 源码冲突。
`git diff --name-only --diff-filter=U` 只返回 README；另外 11 个新增文件自动合并。

最小修复是**完整保留 main README，末尾追加 PR #15 原有 7 行**，不删去任何一方现有内容。
本 PR 另加 4 行审查/测评入口，因此最终 README 相对 main 共新增 11 行。
最小修复文件见 [readme-minimal.patch](results/rust_integration_20261110/readme-minimal.patch)。

可在单独的临时 worktree 重现冲突，避免触碰工作中的分支：

```sh
git fetch origin main pull/15/head:refs/remotes/origin/pr15
git worktree add --detach /tmp/mb-pr15-conflict 3577bda46d023df84c4518c75cb85ccf702b11b8
git -C /tmp/mb-pr15-conflict merge --no-commit --no-ff 39b5553b64fc16c75a2eb58ec9e51e18f275857e
# 上一命令预期返回 1：冲突已经复现。
git -C /tmp/mb-pr15-conflict diff --name-only --diff-filter=U
git -C /tmp/mb-pr15-conflict diff --cc README.md
git -C /tmp/mb-pr15-conflict merge --abort
```

## 2. Rust 与 PyIgnite 的实际边界

| 维度 | Rust PR #15 | 已合并的 PyIgnite | 整合判断 |
|---|---|---|---|
| 多头码本 | `decode_overall`、`decode_heads`；G1 8×10×32 布局 | 未实现 | 保留 Rust 独有价值，不在 C++ 再复制一份 |
| Linear | 独立 FP32 原语 | 私有 C ABI Linear，用于 FCBlock | 保留 Rust 为对照，后续组合层由 PyIgnite 负责 |
| 激活/归一化 | ReLU、逐行 Softmax | 隐藏层 LeakyReLU 0.01 | 语义不同，不能互相宣称完整覆盖 |
| 位置编码/组合层 | 无 PE、无 FCBlock | PE1d_sincos、eval FCBlock | 不为凑齐功能在 Rust 重做 |
| 精度 | FP32；码本/ReLU 精确值；Linear/Softmax `atol=2e-5, rtol=1e-5` | FP32；原门槛 `atol=rtol=2e-5` | 容差是有限样本门槛，不是普适误差上界 |
| 语言边界 | Rust owned Vec/Matrix；Result；生产库禁止 unsafe；无 Python/FFI 绑定 | Python/NumPy → ctypes → 私有 C ABI；指针合法性依赖边界契约 | 不将 Rust CLI 包装成逐帧生产接口 |
| 运行依赖 | 0 第三方 crate；仍使用 Rust std、系统 libc/libm 等 | Python、NumPy、C++17、系统动态库；无 LibTorch | 零 crate 不等于零系统依赖 |
| 平台证据 | 历史 Linux x86_64/ARM64、macOS ARM64 原生构建成功；原 Torch 对照只跑 x86_64 | 工作流覆盖相同三种平台 | 本地只复现 Linux x86_64；跨平台数值一致性仍不成立 |
| 维护成本 | 多一套 Rust 工具链与平台测试；约 185 行生产核心，额外测试/报告 | C ABI 所有权/尺寸验证；现有 Python 接入 | 为独有算子保留一套小实验；禁止无证据扩成双份框架 |

码本只是 2,560 个 FP32（10,240 字节），不是存储一亿个完整向量。
`10^8` 是组合编码空间。Rust 明确拒绝越界 overall 索引，上游 Python 会按位拆分并发生模回绕；
这是有意的更严格契约，错误输入不要求行为相同。

## 3. 本次测试复核

| 验证 | 本次结果 | 实际证据/限制 |
|---|---|---|
| 原 Rust 单元测试 | 6/6 通过 | 原核心源码不变 |
| 新码本测试 | 3/3 通过 | 枚举 225 种小码空间坐标，检查两种解码；输出上限、溢出/形状拒绝；signed zero/subnormal 位保留与批次顺序 |
| Rust → 当前 quantizer/PyTorch | 14/14 数值案例、6/6 异常请求通过 | 合成权重；Linear 最大误差 `2.0980835e-5`，Softmax `2.3841858e-7` |
| 9 组基准正确性 | 全通过 | dyadic 固定夹具，逐元素检查；码本另有直接索引 oracle |
| PyIgnite 契约测试 | 7/7 通过 | 不代表所有数值门槛通过 |
| PyIgnite 原 8 组数值案例 | **7 通过、1 失败** | `PE-4096-64`，3652/262144 元素超出原容差；4 组 FC 均通过 |
| CPU reference | 13 通过、1 跳过 | 假 session 合约测试；真实模型测试明确跳过 |
| Preflight / runtime refusal | 31/31、4/4 通过 | 仅相关本地套件，不宣称完整 CPU 工作流已在本机运行 |

新增测试不以“两个实现互相相等”作为唯一标准：小码空间用独立坐标枚举，基准用上游 oracle，
复制测试比较 FP32 位模式。原 `parity.py` 的码本覆盖只走 overall 模式；
新增测试补充 head 模式，但尚未穷举全部合法尺寸或构造所有分配失败。

历史 CI 的 Rust run `41429165014` 和 CPU preflight run `41429164880` 曾成功，
只证明历史 head 的相应执行。新的 CI 上传自己的结果，单独设置 PyIgnite 相对固定 main 的回归门槛。
严格审计仍对 PE 失败返回 1；回归脚本仅接受与现跑基线完全相同的那一个已知失败。
任何新增失败、改变的输出/参考值/超差掩码/统计量均返回非零，不使用 continue-on-error、不放宽容差。

## 4. 推荐整合方式与最小差异

保留 `native/motionbricks-core/`，不移动成新路径、不改包名、不引入运行时路由、FFI 或 crate 依赖。
Rust 的后续工作仅围绕码本契约、真实权重夹具、边界和成本测量。现有 Matrix 原语冻结为比较基线，
旧 README 的“逐步移植完整算子”路线标记为历史计划。PyIgnite 继续拥有 PE/FCBlock 的 Python 入口。
这比删除已经可复用的对照代码或马上建立跨语言共用框架所需改动更少。

| 文件/范围 | 修改 |
|---|---|
| 根 README | 保留双方并追加审查入口 |
| 原 PR 11 个新文件 | 原样引入，以下 README/workflow 例外；核心 `src/lib.rs`、原测试、NOTICE、历史结果不改 |
| `native/motionbricks-core/README.md`、`docs/pyignite.md` | 标明新整合边界与历史/当前证据 |
| `.github/workflows/rust-core.yml` | 路径筛选、离线 Cargo、固定 Rust 1.85.0；macOS 与仓库现有 CI 对齐到 macos-15；Linux 基准/复古审计；独立 PyIgnite 基线回归与严格失败报告上传 |
| `native/motionbricks-core/tests/codebook_review.rs` | 3 项有独立预期值的边界/码本测试 |
| `native/motionbricks-core/src/bin/benchmark_probe.rs` | 测试用原生计时，不进入运行时 |
| `tools/rust_review/{benchmark.py,pyignite_bench.cpp}` | 同夹具、分边界测评；复用未修改的 C++ kernel |
| `tools/rust_review/{audit_pyignite.py,retro_audit.py}` | 全案例保留失败、离线/通用 CPU/二进制审计 |
| 本报告、benchmark 报告、复古报告、results 目录 | 可核对结论、原始数据与复现命令 |

相对 PR #15 没有修改生产 Rust 算法；相对 main 没有修改 PyIgnite kernel、原导出器、模型加载或机器人运行路径。
本次实际整合保留 PR #15 的提交为 merge parent，方便追溯来源；新 PR 独立审查，旧 PR 的处置交由后续决定。

## 5. 准确复现命令与验收

从仓库根目录开始。使用独立 Python 3.12 环境，固定工具链；联网只用于一次性安装工具/依赖。

```sh
python3.12 -m venv .venv-rust-review
. .venv-rust-review/bin/activate
python -m pip install numpy==2.3.5 torch==2.15.0 --index-url https://download.pytorch.org/whl/cpu
rustup toolchain install 1.85.0 --profile minimal --component rustfmt
export RUSTUP_TOOLCHAIN=1.85.0
export OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1
mkdir -p /tmp/mb-rust-review
cargo fmt --check --manifest-path native/motionbricks-core/Cargo.toml
cargo test --locked --offline --manifest-path native/motionbricks-core/Cargo.toml
cargo build --release --locked --offline --manifest-path native/motionbricks-core/Cargo.toml
python native/motionbricks-core/tests/parity.py > /tmp/mb-rust-review/rust-parity.json
python tools/pyignite/build.py
python -m unittest discover -s tests/pyignite -v
python tools/rust_review/benchmark.py --output /tmp/mb-rust-review/benchmark.json
python tools/rust_review/retro_audit.py --output /tmp/mb-rust-review/retro.json
python -m unittest discover -s tests/cpu_reference -v
python -S -m unittest discover -s tests/preflight -v
python -S -m unittest discover -s tests/runtime_refusal -v
python -m unittest discover -s tests/rust_review -v
python tools/rust_review/baseline_regression.py --output-dir /tmp/mb-rust-review/regression
# 上一条是合并门槛；报告明确保留 strict_current_parity=FAIL。
python tools/rust_review/audit_pyignite.py --output /tmp/mb-rust-review/pyignite-audit.json
# 最后一条在本次主机返回 1，JSON 仍完整记录 8 组结果；必须人工读取失败原因。
# 原始入口同样可复现该失败：
python tools/pyignite/validate.py --output /tmp/mb-rust-review/pyignite-original.json
```

`retro_audit.py` 是 Linux x86_64 专项，其他平台主动拒绝，避免把跳过写成通过。
本次 Python 3.12.14 / NumPy 2.3.5 / Torch 2.15.0+cpu，不是导出器固定的 Torch 2.14.0 环境。

**转 Ready 的条件：** 精确新 head 的原生 CI 与基线回归门槛通过；按[就绪报告](rust_pr66_readiness_zh.md)
跟踪已存在的 PE 数值差异；README 内容与来源不丢失。性能数据不设置跨机器固定阈值。
**生产接入仍需：** 真实 G1 权重与中间输出、完整模型质量门槛、三平台数值对照、应用边界开销和资源预算。
当前没有真实 G1 推理、ONNX 导出器替代、瓦特/能效测量或硬实时证据。

相关入口：[PR #15](https://github.com/wu709621493/motionbricks/pull/15)、
[PR #17](https://github.com/wu709621493/motionbricks/pull/17)、
[Rust 历史 CI](https://github.com/wu709621493/motionbricks/actions/runs/41429165014)、
[benchmark](rust_benchmark_20261110_zh.md)、[单独的复古性报告](rust_retro_review_zh.md)。
