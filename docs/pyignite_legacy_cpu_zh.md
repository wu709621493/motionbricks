# PyIgnite：奔腾时代 CPU 兼容与硬件异常处理

日期：2026-11-12（Asia/Shanghai）

提案：吴孟城（Windy Wu）；实现基线：PR #82 合并提交 `b6d27559016e41f2facceedd1a55c02a9939f2f7`。

目标是让正常工作的旧硬件有明确的执行入口，让不满足指令集、软件环境或正确性条件的设备明确退出。本文给出**已实现的实验能力、候选 CPU 范围和仍待验收的条件**，不宣称 PyIgnite 已支持所有奔腾机器。现代 x86-64／ARM64 路径继续保留。

## 1. 先校准“CPU 脱磁”和“cache 老化”

常规 CPU 逻辑和这些处理器的 SRAM 缓存不靠磁畴保存状态，因此“脱磁”不适合作为故障类别，也没有软件“重新充磁”修复。需要区分晶体管／互连老化、瞬态位翻转、供电或散热异常、内存／存储损坏、指令集不支持和软件错误。

SRAM 老化研究讨论 BTI、热载流子效应、介质击穿、电迁移等机制及其对裕量和可靠性的影响；它并不提供根据机器年限或一次跑分计算缓存剩余寿命的方法。[1] 位翻转也不自动意味着永久损坏。缓存 miss、变慢或一次数值偏差，都不能单独确诊缓存老化。

Linux 的 MCE／EDAC 信息依赖具体 CPU、芯片组、固件、内核和权限；某些平台能报告缓存错误，某些只能看到部分内存错误。[2][3] **无事件记录或无传感器，状态应是未知。** 不把现代 Xeon 的纠错能力外推到老奔腾。

软件能做的是控制工作量、验证已知答案、保留证据和停止不可信执行；不能修复物理损坏。缩小批次不保证避开坏缓存单元，缓存 flush 不会修复晶体管；本实现不修改 BIOS、微码、电压、频率、缓存开关或纠错配置。

## 2. CPU 候选矩阵

以实际能力和 ABI 为准，不按“Pentium”“Celeron”“Athlon”品牌自动放行。GCC 文档说明各目标允许生成的指令；这些说明不是我们的真机测试结果。[4]

| 候选机型 | 保守执行档 | 关键边界 | 本次支持等级 |
|---|---|---|---|
| Intel Pentium P5、Pentium MMX | `p5-x87` | 32 位，x87；不要求 MMX／SSE／CMOV | 原生核心候选；真机未验收 |
| Pentium Pro／II／III，以及相应时期 Celeron | `p5-x87` | Pentium III 有 SSE，不能据此假定 SSE2；统一先用较低基线 | 同上 |
| Pentium 4／Pentium M，满足条件的后续 Pentium | `ia32-sse2` | 必须有 SSE2；某些 Pentium 4 仍是 32 位，不能凭名称认定 x86-64 | 同上 |
| AMD K5／K6／K6-2／K6-III | `p5-x87` | 不依赖 3DNow!；需逐型号／步进验证 | 同上 |
| AMD Athlon／Duron／Athlon XP | `p5-x87` | 不能把后期 AMD 的 SSE2 能力套用到整个系列 | 同上 |
| Cyrix 6x86／MII、VIA C3 | `p5-x87` | 功能随型号变化，不假定通用 i686／CMOV／SSE2 基线 | 同上 |
| AMD Athlon 64 等早期 x86-64 | 显式低基线 64 位构建，或匹配的 32 位档 | 需单独检查依赖是否提高到 x86-64-v2 或更高 | 当前无专门认证 |
| 同期 PowerPC／MIPS／SPARC 等非 x86 平台 | 后续移植候选 | ISA、ABI、字节序、工具链分别验收 | 本 PR 未实现 |
| 现有 Linux x86-64／ARM64、macOS ARM64 | `host` | 继续现有原生构建与 CI | 本次本机仅 Linux x86-64 实测；其余看本提交 CI |

“候选”是工程目标，不是保证每个型号都能启动。最老一代 CPU 可能运行不了当前操作系统、Python 解释器或编译工具。允许在现代构建机上编译，再将独立二进制送往匹配的老系统；目标机不需要安装编译器。

## 3. 已实现：显式构建与独立自检

`tools/pyignite/build.py` 增加：

- `host`：原有默认平台构建；不自动增加 AVX 或使用 `-march=native`。
- `p5-x87`：Linux ELF32，`-march=pentium`，禁用 MMX／SSE／SSE2 与自动向量化，使用 x87 和 `-fexcess-precision=standard`。建议现代 GCC 13+ 的 32 位工具链；不支持该选项的编译器必须报错，不能悄悄去掉约束。
- `ia32-sse2`：Linux ELF32，Pentium 4 指令目标、SSE 浮点、关闭自动向量化。
- `--kind smoke`：与核心同编译的独立可执行文件。`--kind library` 保留 ctypes 库；旧档必须显式另选输出位置，防止覆盖默认宿主库。
- 每个产物旁生成 `.build.json`，记录命令、编译器版本、核心／头文件／构建脚本哈希和产物哈希。`BUILD_ONLY` 不等于验收通过。

所有配置关闭 fast-math 和浮点收缩。**x87 仍可能有中间精度和 libm 差异**；`-fexcess-precision=standard` 控制语义类型的舍入，不是与所有 SSE 实现逐位一致的证明。[5] 本次没有改写已有动态位置编码、oracle 或容差。

```sh
# 仓库根目录；当前正常主机
python tools/pyignite/build.py
python tools/pyignite/build.py --kind smoke
python -S tools/pyignite/doctor.py \
  --binary tools/pyignite/build/host/pyignite-smoke \
  --timeout 10 --output smoke-host.json

# 已准备好 Linux 32 位 C++ 开发库／目标 sysroot 的构建机
python tools/pyignite/build.py --profile p5-x87 --kind smoke
python tools/pyignite/build.py --profile ia32-sse2 --kind smoke
python tools/pyignite/build.py --profile p5-x87 \
  --output tools/pyignite/build/p5-x87/libpyignite.so
```

目标老机器可以直接执行 `pyignite-smoke`，不需要 Python／NumPy。仍需匹配的 OS、加载器、libc／libm 等动态依赖。`file`、`readelf -h`、`readelf -d`、反汇编与目标运行应结合使用，不能只检查我们编译的一个源文件。

自检覆盖 7 组小检查：固定答案 Linear、固定答案融合 FC、负半轴激活、NaN 拒绝、溢出拒绝、位置编码原点，以及经典除法残差。固定答案循环 32 次，工作量固定。除法选用 `4195835 / 3145727`；它来源于历史 Pentium FDIV 问题的公开分析。[6] 只有 x87 构建才覆盖相应指令路径；这是已知案例检查，不是所有 FPU 缺陷扫描。历史 FDIV 是设计缺陷，不能归为老化。

`doctor.py` 是**可选预检工具**：无需导入 PyIgnite／NumPy，启动独立子进程并设置超时；POSIX 超时后终止整个子进程组。它验证 JSON 回执、返回码、有限输出长度和执行前后产物哈希。崩溃、SIGILL、超时、非零返回或无效报告都返回非零退出码，不自动重试。

同进程的普通 `FCBlock` 调用**尚未**接入这个进程监督器。预检成功不能保证之后的运行不会失败；需要可靠执行的服务应另外隔离完整推理任务。该监督器也不能接管内核 panic、硬件断电或全机挂死。

## 4. 已实现：小工作集与保守故障策略

```python
from pyignite import FCBlock
model = FCBlock(layers, backend="scalar", max_batch_rows=8)
y = model(x)
```

`max_batch_rows` 为可选正整数，将输入前导维度展平为行，分块计算，再还原输出形状。scalar、fused、numpy 三个后端均可使用；默认不分块。融合后端隐藏 scratch 从 `2 × 总行数 × 最大隐藏宽度 × 4` 字节降到至多 `2 × 分块行数 × 最大隐藏宽度 × 4` 字节。

这不包含权重、完整输出、输入连续化副本、每块输出和 NumPy／BLAS 内部内存；不是总内存上限，也不保证更快或更凉。NumPy 分块可能因 BLAS 路径而改变舍入；测试用既有 FP32 容差核对。晚期分块失败会抛异常，不向调用者返回半成品。

| 观察到的情况 | 行为 | 是否自动恢复 |
|---|---|---|
| 只有旧型号、小缓存或低可用内存，未观察到错误 | 手动选择已验证基线、较小批次；限制上层任务并发 | 可调工作量，但不是老化诊断 |
| SIGILL／加载失败／ABI 不匹配 | `STOP`；核对目标和完整依赖链 | 不盲目切换后端；明确 ISA 问题后才重编译并重测 |
| 数值自检失败、崩溃、超时、无效回执 | `STOP`；保留产物哈希与失败信息 | 不靠重复直到一次成功来验收 |
| 调用者报告 `corrected-error` | `REVIEW_REQUIRED`，不再执行 smoke | 这是本项目保守策略；不表示所有 CE 都预示失效 |
| 调用者报告 `thermal-alarm` | `STOP_AND_COOL`，不再执行 smoke | 检查散热／供电并解决事件后重新验收 |
| 调用者报告 `uncorrected-error` 或 `data-mismatch` | `QUARANTINE`，不再执行 smoke | 不返回可信结果；由 OS／运维隔离检查 |
| smoke 通过但没有硬件观测 | `SMOKE_PASS_HEALTH_UNKNOWN`，退出码 0 | 只表示这些小测试通过 |

`--event` 是调用者提供的观测标签，**没有自动读取温度、MCE、EDAC 或 Windows WHEA**。动作名称表示本工具拒绝继续测试，不代表已经隔离 CPU、修改 OS 或停止其他进程。没有传感器不能填写“健康”。本 PR 的故障策略是工程选择；具体硬件事件含义应按厂商／内核文档解释。[2][3]

```sh
python -S tools/pyignite/doctor.py \
  --binary tools/pyignite/build/host/pyignite-smoke \
  --event uncorrected-error --output fault-observation.json
# 退出码 2，QUARANTINE，probe=NOT_RUN；不修改硬件。
```

正确性进一步验收应把相同输入与可信、独立机器上的结果比较，并验证权重文件哈希。单机重复、同 CPU 的两个后端、同机计算的哈希都有共同故障盲区；不构成可靠纠错。NaN 检查也发现不了全部有限值错误。

## 5. 全框架兼容的边界

当前 Python 分发仍要求 Python >=3.12、NumPy >=1.26.4。只降低 `kernels.cpp` 的 ISA 基线，不能降低解释器、动态加载器、glibc、NumPy、BLAS 或 wheel 的要求。NumPy 区分构建时 baseline 和运行时 dispatch；禁用某条 dispatch 路径不能消除已编入二进制的最低要求。[7] 不把 `backend='scalar'` 等同于“无需 NumPy”。

本次不新增 Windows、DOS、Windows 95/98 支持，不发布声称适用于老 CPU 的 wheel，不降级现有 Python 版本门槛。老系统依赖验证必须在固定 sysroot 和真实目标环境中单独做。x87 数值、完整 G1 推理、模型运行时大小和实际延迟均未获得老机证据。已知动态 PE-4096-64 跨环境差异继续保留；固定 PE buffer 路径也不能替代整机验收。

## 6. 验证与验收门槛

本次本机证据放在 [`results/pyignite_legacy_20261112/`](results/pyignite_legacy_20261112/)：包括原生构建清单、smoke、Python 回归、打包结果和 32 位构建尝试。当前主机缺少 32 位开发库，不能将本机编译失败写成代码已在奔腾运行。

新增 CI 对两个旧档安装 multilib、构建 ELF32 库与独立程序，并在**现代 x86-64 runner 的 32 位 ABI** 下运行 smoke；三个现有平台继续跑原有测试并新增独立 smoke。CI 不使用真实奔腾，也没有覆盖古老 glibc。

| 证据层级 | 能证明什么 | 不能证明什么 |
|---|---|---|
| 源码和编译命令审查 | 有明确基线和失败条件 | 编译器输出和依赖实际都合格 |
| 现代 runner 的 ELF32 smoke | 32 位 ABI、少量算子／异常路径能运行 | 老 CPU ISA 或物理健康 |
| 限制 CPU 模型的 QEMU 测试 | 在该模拟配置和 sysroot 下可执行 | 真实电气／热学／缓存老化、真实性能 |
| 指定型号／步进的真机测试 | 该设备／系统组合的实际结果 | 整个品牌或未来运行都可靠 |

未来使用 QEMU 时可调用 `doctor.py --binary ... --qemu-cpu pentium --qemu-root /path/to/verified/sysroot`，输出标记为 `EMULATED`。这只是调用入口，**本次没有执行 QEMU 验收**。现代 i386 glibc 可能已要求 i686 等能力，因加载器 SIGILL 而失败应原样记录，不能替换成模拟成功。

提升某一档为“已支持”前必须记录：具体 CPU 型号／步进、OS 与 ABI、工具链与完整动态依赖、产物／模型哈希、原始数值 oracle 和容差、长序列／非有限值／溢出／尺寸上限、内存峰值与延迟、传感器可用性、当前提交，以及模拟或真机的来源。保留原有严格 oracle；没有证据的项目写 `NOT_RUN`。

## 参考来源

以下资料用于机制和边界说明；我们的候选矩阵及故障策略是据此作出的工程设计。

1. Liu et al., *Comprehensive reliability and aging analysis on SRAMs within microprocessor systems*, Microelectronics Reliability 55 (2015), 1290–1296. DOI: [10.1016/j.microrel.2015.06.078](https://doi.org/10.1016/j.microrel.2015.06.078)。只依据可访问摘要／介绍，不声称获取全文实验。
2. Linux kernel, [Reliability, Availability and Serviceability](https://www.kernel.org/doc/html/latest/admin-guide/RAS/main.html)，EDAC、可纠正／不可纠正错误与硬件覆盖边界。
3. Linux kernel, [x86-64 machine check](https://docs.kernel.org/arch/x86/x86_64/machinecheck.html)；另见 [Intel 架构手册入口](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-sdm.html)。老型号还需查对应历史规格与勘误。
4. GCC, [x86 Options](https://gcc.gnu.org/onlinedocs/gcc/x86-Options.html)，处理器目标及指令约束。
5. GCC 14.1, [Optimize Options](https://gcc.gnu.org/onlinedocs/gcc-14.1.0/gcc/Optimize-Options.html)，浮点收缩、fast-math、excess precision。
6. Cleve Moler / MathWorks, [Pentium Division Bug Revisited](https://blogs.mathworks.com/cleve/2013/04/29/pentium-division-bug/)，2013-04-29，重刊其 1995 年分析。
7. NumPy, [CPU Build Options](https://numpy.org/doc/stable/reference/simd/build-options.html)，构建基线与分派。链接随稳定版变化；部署必须固定实际版本。

## 补充：风冷温度安全阀

按用户后续要求增加 [温度保护与最后数据检查点](pyignite_thermal_checkpoint_zh.md)。
显式启用 `TemperatureGuard` 后，默认连续 10 秒、至少 3 次读数严格高于 100°C 即锁定；运行期间持续将温度及最后完整 FC 结果由 RAM 写入校验过的原子检查点。传感器失联与写盘失败均阻止受保护计算成功。自动采温目前限部分 Linux CPU 驱动；旧奔腾无传感器时不虚构温度。该机制不承诺 CPU 已失效后还能补写磁盘。
