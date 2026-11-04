# 二进制／平衡三进制：表示与计算接口实验

本 fork 把《OpenAI 与 Linux 生态的治理及计算架构比较》中的接口建议转成一个可执行实验：
**同一个整数点积任务，显式选择表示方式与后端，检查协议与结果，并记录转换开销。**
它使用 Python 标准库，在现有二进制 CPU 上运行，不加载 MotionBricks 权重或 GPU 依赖。

> “Linux在开发二进制上很高效，但是这样对系统造成了易碎性，而且阻碍了其他进制和制式计算机的应用开发”
>
> ——孟城留

保留原批语，把其中的因果判断视为待检验主张。这个实验能检验表示转换、接口拒绝和计算正确性；
不能证明 Linux 的系统易碎性来自二进制，也不能代表原生三进制硬件的速度或能效。
本文和代码为用户 fork 的研究扩展，不代表上游维护者立场。

## 从资料到实现

| 资料中的启示 | 本次实现 | 仍需单独验证 |
| --- | --- | --- |
| 决策权与证据应分别审查 | 后端自行计算；调用方用独立整数 oracle 验证结果 | 这不是组织治理制度的自动化实现 |
| 显式声明既有架构假设 | 版本、数制、符号方式、数位顺序、宽度、容量均进入接口 | 原生 ABI、编译器、操作系统移植 |
| 维护可替换性与可接续性 | 两个后端实现同一个 `DotBackend` 协议 | 新硬件适配器及其维护成本 |
| 评价完整任务开销 | 分阶段计时，包含验证、编码、后端调用、解码及核验 | 设备传输、调度、能耗和真实任务性能 |
| 故障应有明确语义 | 错误输入、版本不符、陈旧返回、错误结果、异常分别测试 | 进程隔离、超时抢占及设备重连 |

组织比较提供设计启发，不是“非营利必然更可靠”的技术证明。相关背景见
[PR #27 的治理评论](openai_altman_governance_editorial_zh.md)。

## 运行

从源码仓库根目录运行，Python 3.12 或 3.13；不需要 `pip install .` 或 `uv sync`：

```sh
python -S -m motionbricks.radix_portability
python -S -m motionbricks.radix_portability --backend ternary
python -S -m unittest discover -s tests/radix_portability -v
```

默认任务为 `[13,-7,0,42] · [3,11,-9,-2]`。两个后端均应返回整数 `-122`，
共享 `workload_sha256`，而编码后的 `request_sha256` 不同。SHA-256 用于关联内容，
不认证适配器身份，也不提供防恶意代码能力。报告中的 `VERIFIED` 只表示该次整数结果通过核对。

自定义 `request.json`：

```json
{"schema_version":1,"lhs":[-8,3],"rhs":[9,-4]}
```

```sh
python -S -m motionbricks.radix_portability --input request.json --backend both
```

结果应为 `-84`。CLI 限制文件为 64 KiB，要求三个字段、整数列表和相等非零长度。
成功退出 0；输入、执行或结果错误输出 `FAILED` JSON 并退出 1；命令行语法错误退出 2。
`both` 任一后端失败则整次 CLI 失败，不发布部分成功报告或使用参考值替代失败结果。

Python 接口：

```python
from motionbricks.radix_portability import BalancedTernaryBackend, run_dot

report = run_dot([-8, 3], [9, -4], BalancedTernaryBackend(width=21))
assert report['value'] == -84
```

## 数值与接口约定

| 项目 | 二进制后端 | 平衡三进制后端 |
| --- | --- | --- |
| 标识 | `python-integer-v1` | `python-trit-convolution-v1` |
| 输入表示 | 固定宽度二进制补码，数字为 0、1 | 固定宽度平衡三进制，数字为 -1、0、1 |
| 默认宽度与范围 | 32 bit，[-2147483648,2147483647] | 21 trit，[-5230176601,5230176601] |
| 执行方式 | 解码后使用 Python 整数乘加 | 直接做 trit 卷积和带符号进位，不先解码操作数为整数 |
| 执行证据分类 | `HOST_INTEGER_REFERENCE` | `HOST_TRIT_SIMULATION` |

所有数位低位在前，数组为不可变 tuple；这是 Python 层的版本化数据契约，尚未定义跨进程线协议。
`Capabilities` 声明操作、表示、容量、执行类别和 schema 版本。每个请求最多 1024 对整数；
输入宽度可选 1–32 个数位。不同后端比较时应使用共同可表示的输入范围，不能将不同宽度简单等同。
布尔值、浮点数、空向量、长度不等、越界值及错误数位均被拒绝，不截断、不饱和、不隐式转型。

点积采用精确整数语义，不是浮点、定点量化或神经网络推理。结果宽度为
`2*w + ceil(log_radix(n))`，保留全部乘加结果；这不同于输入宽度下的模运算。
例如二进制最小负数的平方和、连续正负进位以及完全抵消均需保持精确。

后端必须拒绝不支持的输入版本／格式。返回结果携带请求摘要、版本、结果格式和数位。
调用方检查这些字段后解码，再与原始整数输入直接计算的 oracle 比较：

- `ContractError`：输入、能力声明、协议或输出格式不合法。
- `BackendFailure`：适配器抛出异常，保留异常原因，不自动重试或切换后端。
- `ResultMismatch`：格式合法但数值错误，属于 `BackendFailure`。

内置后端不缓存结果。测试用损坏数位、错误版本、错误请求摘要、伪造数值和异常验证拒绝路径，
并验证恢复正常适配器行为后的下一次请求。适配器是可信的进程内 Python 代码：
本模块不能终止卡死调用、隔离 native 崩溃或阻止恶意代码。不得据此宣称实现了设备故障隔离。

## 如何解读计时与测试

`timing_ns` 的 `total` 是五个阶段之和，从输入校验前到结果核验后；不含 CLI 文件读取、
后端构造、主机信息收集和最终 JSON 输出。`validation_reference` 包含独立 oracle 和工作负载摘要；
`encode` 包含请求校验与摘要；`backend_call` 包含适配器内部检查、运算、结果打包和摘要；
`decode` 包含返回契约校验；`verify` 是最终数值比较。不要把 `backend_call` 当成纯硬件算术时间。

这些是单次软件观察值，受 Python、操作系统和负载影响，不提供速度比或性能阈值。
`logical_input_digits` 统计逻辑数位，不代表内存字节数、线路数量或压缩率。
报告显式标注传输与能耗未测量、原生非二进制硬件未测试、运动推理未执行。

新增测试覆盖已知编码、完整小范围往返与乘法、60 组固定种子随机向量、1024 项极值累加、
负数进位、抵消、无整数解码的 trit 运算、输入与能力拒绝、返回损坏、异常后恢复以及 CLI。
使用 `python -S` 运行可验证不依赖 site-packages。新测试和示例已接入现有 CPU preflight
CI，沿用 Linux x86-64、Linux ARM64、macOS ARM64 与 Python 3.12／3.13 矩阵；
矩阵配置不等于各平台已经通过，实际结果以 PR 检查为准。

后续真实后端应独立实现并测试传输、超时、取消、内存生命周期及硬件结果校验，记录迁移工作量。
本实验为这些工作提供小型参考边界；不改变现有 TensorRT 引擎或 CPU ONNX 参考执行器。

## 技术背景资料

- [Linux 内核驱动接口](https://docs.kernel.org/process/stable-api-nonsense.html)：内部接口与用户接口的稳定性需分别讨论。
- [ELF 格式说明](https://gabi.xinuos.com/elf/01-intro.html)：程序格式与目标机器的数据假设。
- [现有 CPU 参考执行器](cpu_reference.md)：真实模型的执行和验证边界，与本整数实验不同。
