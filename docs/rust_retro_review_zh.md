# Rust 复古性考核：独立报告

日期：2026-11-10。这里将“复古性”操作性地定义为：**老硬件友好程度、低依赖、离线构建、可检查的资源占用及部署兼容性**。
它不是 Rust 语言年代评价，也不等同于一般回归测试。回归结果见[整合审查](rust_integration_review_zh.md)。

**结论：通过低依赖/离线/通用 CPU 构建考核；旧设备兼容性尚未通过实机验收。**
不使用缺乏权重依据的综合百分制，也不以“Rust”名称推导老电脑兼容。

## 实测门槛

| 考核项 | 结果 | 依据与边界 |
|---|---|---|
| 第三方 Rust 依赖 | 通过：0 个 crate | 新建空 CARGO_HOME，`cargo metadata --locked --offline` 仅有本地 package |
| 离线清洁构建 | 通过：约 0.944 秒 | 全新 target 与 Cargo home；`cargo build --release --locked --offline`；计时含 Cargo/编译，不含工具链下载 |
| 通用 CPU 配置 | 通过本机执行 | `RUSTFLAGS='-C target-cpu=x86-64'`，不启用 target-cpu=native；不是旧 CPU 仿真 |
| 原测试与新码本边界 | 9/9 通过 | 通用 CPU 配置下另行跑完整 Rust 测试 |
| 无 Python 的可执行文件 | 通过 | strip 后的 parity probe 独立执行 ReLU smoke；无 Torch/NumPy |
| 二进制尺寸 | 原 510,280 B；strip 后 428,512 B（约 418.5 KiB） | 测试 CLI 尺寸，不是纯 kernel 大小；不含动态系统库或编译工具链 |
| 操作系统依赖 | 有条件 | 实测 NEEDED：libgcc_s、libm、libc、ld-linux；不等于静态独立文件 |
| 旧 glibc | **未通过** | 本机生成的二进制最高引用 `GLIBC_2.34`；不能部署到只提供 glibc 2.17 的系统后声称已兼容 |
| 内存占用 | 有实测，有限结论 | 256 行 overall 码本基准独立进程 VmHWM 1,613,824 B；由 /proc/self/status 读取，含 runtime/夹具/输出 |
| 固定资源预算 | 尚未具备 | 每缓冲区上限 16,777,216 元素约 64 MiB；不是全进程上限；调用会分配输出 |
| 32 位、旧 Windows、嵌入式 | 未测试 | 本 crate 使用 std、Vec 和系统环境，不是 no_std 固件；未安装/执行对应目标 |
| 老芯片实机/功耗/硬实时 | 未测试 | 测量主机是 AMD EPYC 7763；没有 Pentium/老 Mac 实机、功率计或最坏执行时间证明 |

原始记录：[retro.json](results/rust_integration_20261110/retro.json)，包含完整 rustc 版本、编译/测试日志、
动态库与 glibc 符号列表。资源测量来自[benchmark.json](results/rust_integration_20261110/benchmark.json)。

Rust 官方[平台表](https://doc.rust-lang.org/rustc/platform-support.html)列出各 target 的不同支持层级，
并列出 x86_64-unknown-linux-gnu 的工具链平台要求。**官方 target 支持、代码能编译、
当前产物的链接要求、旧设备实际运行**是四项不同证据，不能互相替代。本次 `readelf` 是实际产物的证据。

## 复现

先按[主报告](rust_integration_review_zh.md#5-准确复现命令与验收)安装 Rust 1.85.0 并置为本次 shell 使用的工具链。
Linux x86_64 还需正常的 C 链接器及 binutils（`strip`、`readelf`）。

```sh
export RUSTUP_TOOLCHAIN=1.85.0
python tools/rust_review/retro_audit.py --output /tmp/mb-rust-retro.json
```

脚本在临时目录构建，使用独立 CARGO_HOME/CARGO_TARGET_DIR，结束后删除临时产物。
`--offline` 阻止 Cargo 下载依赖，但不代表初次安装编译器不需要联网，也不是对全系统网络流量的审计。
`rust-version=1.85` 已满足；没有试图降低 MSRV，也没有宣称更老编译器可用。

## 要成为真正“复古部署”模块，还需什么

1. 指定一台目标机器与 OS/glibc 版本，在对应旧 sysroot 或构建环境重新编译，再检查动态符号。
2. 在该实机重复码本正确性、拒绝输入、warm/cold 延迟与峰值 RSS；编译通用 ISA 不能替代实机测试。
3. 以预计 batch/frames 给出总内存预算；需要控制循环时，先设计预分配输出接口并独立核验其边界。
4. 保持生产核心小而可读：码本是保留对象；不借复古目标引入全套算子、依赖或第二个运行时。

码本解码的低依赖和小工作集值得保留，但“古老 CPU 已验证”“零操作系统依赖”“节能且更快”均不是本报告的结论。
