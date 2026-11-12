# PyIgnite v0.2：固定位置编码、FCBlock 优化与真实 G1 子图

日期：2026-11-12。基于 main `38f6b26038e8a45a06f7b810dfc58b4ef43858d6`。

本次把三个阶段的最小实现串起来：保存模型位置编码、优化 FCBlock 调用、
验证真实 G1 权重子图，并构建可安装的实验 wheel。所有后端选择仍为显式；
原 scalar 默认、原导出器、ONNX Runtime CPU reference 和机器人路径保持原行为。

## 1. PE 的实际结论

历史 PR #66 在其主机记录过 PE-4096-64 的严格失败：最大误差约 1.22e-4，
3652 个元素超差。当前主机的原代码在 Torch 2.14.0+cpu / NumPy 1.26.4 和
Torch 2.15.0+cpu / NumPy 2.3.5 下均为 8/8；固定历史基线重新构建后也均为 8/8。
另在当前主机以 `ATEN_CPU_CAPABILITY=avx2` 跑旧代码仍通过。
因此不能把环境变化造成的通过写成修复，也不能从本次结果撤销历史问题。

**动态 PE 生成器未修改，原 oracle 和 atol=rtol=2e-5 未修改，历史问题仍开放。**
原工作流的严格 parity 检查保留；新工作流还运行既有固定基线比较，保留原始
PASS/FAIL 与 no-new-regression 两种结论。后者允许的既有失败规则没有扩大。

新增 `PositionEmbedding` 直接接受模型内的 FP32 `[sequence,1,dimension]` buffer，
对 `[batch,time,dimension]` 输入执行 eval 模式加法。保存为 NPY 时要求显式 SHA-256；
加载时解析的就是刚刚核验的同一份字节，不使用 pickle，不重新计算 sin/cos/exp。
输入必须有限、非空、维度匹配且 time 不超过已保存长度；溢出拒绝。
缓冲区以不可写 bytes 持有，外部数组修改或重新启用 ndarray 写入不能改变它。

这条路径解决固定模型部署时的位置编码重算差异；它不等价于修复通用动态 PE。
两个合成 buffer 和实际 G1 保存的 buffer，经文件往返后，位置加法均与原模块逐位一致。

## 2. FCBlock 三个显式后端

| 后端 | 实现 | 使用边界 |
|---|---|---|
| `scalar`，默认 | 原逐层 ctypes 调用与 `ignite_linear` | 独立参考路径，保留逐次权重扫描 |
| `fused` | 整块一次 ctypes 调用；隐藏层复用两个 scratch buffer | 权重构造时校验并存为不可写 bytes；每次调用独立 scratch，可并发 |
| `numpy` | NumPy matmul、原位 bias 和 LeakyReLU | 使用 NumPy 自带矩阵后端，不额外强绑某一个 BLAS |

隐藏层 LeakyReLU slope 仍为 0.01，末层仍无激活；FP32 输入、任意正前导维度、
非连续输入拷贝等契约保留。每条计算路径仍拒绝非有限结果。未引入 fast-math。
融合路径的权重重复扫描被安全移到构造期；这属于 API 工作量改进，不能称为语言速度比较。

两块 workspace 大小为 `2 * rows * max_hidden_width * 4` 字节，另有最终输出。
每次调用分配一次 workspace 并在隐藏层间复用；**没有声称跨调用零分配**。
NumPy 路径仍逐层分配输出。未来应根据真实 profile 再评估长期工作区和更专门的矩阵库。

## 3. 真实 G1 子图

离线 adapter 固定读取仓库 `tools/onnx/checksums.py` 中已发布的 G1 root checkpoint：

- 大小：136,510,540 字节。
- SHA-256：`da6ff2c05e45dfe4ac5e8e8362a6404f5c927fcddb18410e6804b61e55d4f2dc`。
- FCBlock：`backbone_net._proj_start_input`。
- 三层权重形状：`[512,384]`、`[512,512]`、`[512,512]`。
- 位置编码：`backbone_net._position_emb.embed`，形状 `[16,1,512]`。

文件大小和 SHA-256 核对后才解析同一份 SafeTensors 字节，并检查选定子图的完整键集、
形状、dtype 和有限性。权重未提交到仓库，未隐式联网下载。

**实际执行范围：真实发布权重 + seed 20261112 的合成输入。**
FC 输入 `[1,384]`、`[2,4,384]`；位置输入 `[2,16,512]`。
三个 PyIgnite 后端对照未经修改的上游 FCBlock；另构造标准 ONNX MatMul/Add/LeakyRelu
子图，在 ORT CPU 对照，并检查其每层输出与 Torch 中间值。
该 ONNX 子图是显式构建的验证模型，未冒充从完整 G1 图抽取的实际执行轨迹。

没有执行完整 G1、采样器、token 决策、动作输出或机器人控制。下一步需要捕获真实
模型运行的激活，再扩大子图范围；这一关仍未完成。

## 4. 本次主机测量

两套环境均为 Python 3.12.14、Linux x86-64；Torch 单线程，OMP/OPENBLAS 线程数为 1。
5 次预热，每个后端 50 次单请求测量，每轮随机打乱后端顺序。记录全部样本、中位数、
单请求 P95、首次调用及构造时间；首次调用不是解释器/进程冷启动。
共享主机未锁频，结果只代表本次实现、环境和调用边界。

固定导出器版本环境（Torch 2.14.0+cpu / NumPy 1.26.4）中位数，µs：

| 案例 | 原 scalar | fused | NumPy | Torch | ORT |
|---|---:|---:|---:|---:|---:|
| 小 FC，输入 `[3]` | 26.80 | 13.76 | 25.78 | 23.14 | 14.39 |
| 合成 FC，输入 `[32,128]` | 2454.81 | 2347.77 | 559.08 | 192.87 | 120.49 |
| G1 真实权重，输入 `[1,384]` | 870.92 | 442.06 | 261.85 | 164.16 | 143.01 |
| G1 真实权重，输入 `[2,4,384]` | 3945.53 | 3470.98 | 1252.74 | 270.26 | 205.39 |

这表明融合调用对小块有收益，NumPy 对较大块优于原标量实现；也表明本次较大子图
仍慢于 Torch/ORT。没有承诺 PyIgnite 全面更快，未自动切换生产路径。
另一套 Torch 2.15 / NumPy 2.3.5 原始结果独立保存，不合并成一个跨环境速度结论。

## 5. 验收与安装包

- 本机 14 项契约测试：包括非均匀层宽、rank 1/2/3、输入/输出别名、不可变权重、
  并发调用、非有限值、溢出、错误 checkpoint 大小/哈希及 NPY pickle 拒绝。
- 两套环境各执行 5 组 FC 案例和 3 组保存位置编码案例，均通过原有数值门槛。
- 两套环境重新构建旧基线与当前版本：原始严格测试均 8/8；回归比较通过。
- 单独构建 sdist 与本平台 wheel，从 sdist 编译成功；干净 venv 安装 wheel 后，
  在源码目录之外执行三个 FC 后端和位置编码，验证未导入 Torch。
- CI 配置覆盖 Ubuntu x86-64、Ubuntu ARM64、macOS ARM64 和两套 Torch/NumPy 版本；
  每个任务上传报告和原生 wheel。**配置不是已执行证据，实际通过状态以对应提交 Actions 为准。**
- CI 中真实 G1 权重测试限定 Ubuntu x86-64 / Torch 2.14；其余平台执行合成子图，
  不能把它们写成真实 G1 跨平台验证。

Linux wheel 是原生平台标签，不是 manylinux 认证；老 glibc/老硬件、Windows、GPU、
Python 3.13+、完整模型的峰值内存、进程冷启动与功耗尚未验收。
`wheel_smoke.py` 只记录隔离进程导入时间和小夹具峰值 RSS，不能代表完整 G1 部署成本。
分发名 `motionbricks-pyignite`；Python 导入名仍为 `pyignite`。没有发布到 PyPI。

## 6. 复现

在独立 Python 3.12 环境，从仓库根目录运行：

```sh
python -m pip install numpy==1.26.4 -r tools/pyignite/requirements-review.txt
python -m pip install torch==2.14.0+cpu --index-url https://download.pytorch.org/whl/cpu
python tools/pyignite/build.py
python -m unittest discover -s tests/pyignite -v
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python tools/pyignite/review.py \
  --g1-root /path/to/model-step=2000000.safetensors --output /tmp/g1-subset.json
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python tools/rust_review/baseline_regression.py \
  --output-dir /tmp/pyignite-regression
python -m pip install build
python -m build tools/pyignite --outdir wheelhouse
```

不传 `--g1-root` 时仍可跑合成案例，但报告明确标记 checkpoint `NOT_RUN`。
真实文件下载位置见原[导出器文档](../tools/onnx/README.md)，受 NVIDIA 模型许可约束。

原始证据：[固定导出器环境](results/pyignite_20261112/review-exporter.json)、
[Torch 2.15 环境](results/pyignite_20261112/review-torch215.json)、
[原始严格测试与基线比较](results/pyignite_20261112/legacy-exporter/regression.json)、
[契约测试](results/pyignite_20261112/contracts.txt)。报告保留运行时版本、源文件哈希、
输入/权重哈希、逐请求样本和未验证边界；测量时 git HEAD 为起始 main，待提交改动以源码哈希定位。

后续顺序：捕获真实激活与完整模型中间输出 → 按 profile 扩算子 → 检查离散决策与采样 →
按实际硬件验收完整模型延迟/内存/冷启动 → 再考虑生产后端切换。
