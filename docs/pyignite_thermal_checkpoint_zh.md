# 风冷场景的温度安全阀与最后数据保存

日期：2026-11-12（Asia/Shanghai）

吴孟城补充要求：CPU 温度稳定超过 100°C 时停止工作，尽量将最后数据先保存在 RAM，再存入硬盘。本实现将保护提前到 CPU 仍能正常运行期间：持续保存温度观测，以及每次完成的 FCBlock 结果；不等待 CPU 已经失效才尝试最后一次写盘。

## 实际行为

`TemperatureGuard` 是显式启用的保护上下文，配合 `FCBlock(..., temperature_guard=guard)` 使用：

- 后台默认每秒读取一次 CPU 温度。**同一传感器连续至少 10 秒、至少 3 个不同单调时刻的有效读数均严格高于 100°C**，锁定为 `THERMAL_TRIP`。等于 100°C 不触发此规则；降回阈值以内会重置该传感器的持续计时。
- 相邻采样间隔不得超过 2.5 秒。传感器缺失、非法读数、传感器集合变化或观测超时均停止受保护计算，不沿用最后温度伪装成当前温度。
- 硬件已有的 critical alarm 立即锁定，不等 10 秒。100°C 是用户指定的软件规则，不是所有处理器的安全温度；可配置更低阈值，不能提高到 100°C 以上。CPU 厂商／固件的保护优先。[1][2]
- RAM 中保留最近 16 个温度快照、最后一个完整 FCBlock 结果及其元数据。每次采样、每个完整结果和故障锁定时都写检查点。这里保存的是输出张量，不包含模型权重、输入或整个任务的状态，不能据此宣称完整任务可恢复。
- 每次调用前、分块前后、结果接受前检查安全阀。触发后不再开始新块、不返回部分输出，也不把温度记录冒充计算结果。已经运行的一个 C／NumPy 调用不能被本线程安全地强行中断；返回边界会拒绝它的结果。因此应选用测量后足够短的小分块。
- 降温不会自动解锁。现有检查点不会在下一次启动时被悄悄覆盖；应先恢复数据、检查散热和硬件，再显式使用 `resume_after_inspection=True`。恢复会保留旧结果和上一会话最后温度，但重新开始当前温度观测。

```python
import json
from pyignite import FCBlock, TemperatureGuard, ThermalSafetyError

# 默认只读 Linux 中已识别的 CPU 摄氏温度传感器。
# 路径必须在实际要持久保存数据的本地文件系统上。
try:
    with TemperatureGuard("checkpoints/last_complete.json") as guard:
        model = FCBlock(layers, backend="scalar", max_batch_rows=8,
                        temperature_guard=guard)
        result = model(x)  # 返回前，完整结果已完成配置中的写盘步骤
except ThermalSafetyError as exc:
    print(json.dumps(exc.report, ensure_ascii=False, indent=2))
    # 包括状态、最后温度/UTC/来源、检查点位置及写盘是否得到确认。
```

启用后每个完整结果都执行持久写入，会增加延迟和磁盘写入量，不是性能优化模式。默认结果上限为 1 MiB 原始字节，额外还有 base64/JSON 和内存复制开销；超限在运算前明确拒绝，可在评估资源后配置 `max_result_bytes`。不能把 1 MiB 误认为整个进程的内存上限。

## RAM → 硬盘的顺序

1. 完整输出先复制为进程拥有的字节，记录 shape、dtype、长度与 SHA-256；温度另带来源、UTC 和单调时刻。
2. 将这些完整对象序列化为带整体校验和的 JSON；不使用 pickle。
3. 同目录写临时文件，`flush` 后 `fsync` 文件。
4. 用 `os.replace` 原子替换最新检查点；POSIX 再对父目录执行 `fsync`。
5. 成功后内存报告才标记 `FILE_AND_DIRECTORY_FSYNC_COMPLETED`。若失败则锁定为 `CHECKPOINT_FAILED`，写盘状态 `NOT_CONFIRMED`，受保护调用不返回成功。

替换前失败时旧文件保留；替换后目录同步失败时不承诺旧／新版本哪一个已持久化。检查点文件记录事实和校验和，不在写盘完成前伪称“已耐断电”。读取校验和能发现许多文件损坏，但不能证明损坏 CPU 算出的内容正确，也不是防篡改签名。

恢复示例：

```python
import base64
import hashlib
import numpy as np
from pyignite.thermal import CheckpointStore

saved = CheckpointStore("checkpoints/last_complete.json").load()
record = saved["last_completed_result"]
if record is not None:
    raw = base64.b64decode(record["data"], validate=True)
    assert len(raw) == record["bytes"]
    assert hashlib.sha256(raw).hexdigest() == record["sha256"]
    last_result = np.frombuffer(raw, dtype=record["dtype"]).reshape(record["shape"]).copy()
# temperature_history 是历史记录，不作为当前传感器读数。
```

## 风冷与旧硬件边界

这里以风冷异常为使用场景，不会自动判断散热器类型，也没有控制风扇 PWM、电压或频率。风扇停转、积尘、接触不良等原因仍需人工／硬件诊断。

目前自动读取 Linux `coretemp` 的 Core／Package 摄氏温度，以及 `k10temp` 的 Tdie／Tccd；不拿 NVMe、GPU 或其他设备的温度代替 CPU。AMD Tctl 可能是控制值，不能一概解释为物理摄氏温度，所以不会用 Tctl-only 读数执行本规则。[2][3]

原始奔腾等旧设备通常不在这些传感器驱动覆盖范围内；没有可信读数就报告不可用。macOS、Windows、ARM 板载传感器或外部测温需要提供经验证的 `reader` 适配器；本 PR 没有宣称自动支持这些温度接口。既有普通推理仍可不用此可选保护。

**若 CPU 已经停机、系统已挂死或突然断电，同一台机器上的软件无法保证最后一次采样、RAM 正确性或写盘完成。** RAM 是易失的；硬盘／SSD 控制器也可能存在缓存和故障。这里能争取保留的是故障发生前最后一个成功写出的完整检查点。需要更强保证时，必须另用独立温控／硬件 watchdog、可靠供电和具有相应断电保护的存储；本代码未实现这些硬件能力。

采温线程也依赖 OS 调度和驱动正常响应，不能取代硬件关断。`fsync` 的完成是 OS 提供的写盘确认，不是对存储器、供电和未来故障的绝对保证。

## 验证

使用模拟传感器验证持续过热、恰好 100°C、短暂尖峰、传感器消失、采样断档、硬件告警、写盘失败、故障后锁定、RAM 所有权、文件校验、结果恢复、超限预拒绝及重启保护。三种 FC 后端均验证完整结果落盘；过热导致未完成调用不覆盖此前完整结果。

当前执行环境没有 `/sys/class/hwmon`，没有实施真实高温／风扇故障实验，也没有做 CPU 损坏或断电破坏性实验。模拟数据证明软件状态与文件操作流程，不证明真实风冷机器的硬件可靠性。

## 来源

1. Intel, [Information about Temperature for Intel Processors](https://www.intel.com/content/www/us/en/support/articles/000005597/processors.html)：温度限值因型号而异，内部节流／关断与软件监测的关系。
2. Linux, [coretemp](https://docs.kernel.org/hwmon/coretemp.html)：CPU 温度单位、传感器标签及 critical alarm。
3. Linux, [k10temp](https://docs.kernel.org/hwmon/k10temp.html)：Tctl 与 Tdie 区别及 CCD 温度来源。
