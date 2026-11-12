# PyIgnite：有期限的进程隔离 I/O 与严格 PE 诊断

2026-11-13；修复基线：`6f7c2dc67c3d640ebbb32b9f97ef4dbb0fa4e0b0`。

本轮得到明确批准后，新增可选的 `IsolatedTemperatureGuard` 与 `run_supervised`，不改默认推理、原始动态 PE kernel、Torch 参考答案或 `atol=rtol=2e-5`。原合作式 `TemperatureGuard` 保留；它仍不能独自处理卡住的 reader/fsync，不能把新入口的结果写成旧接口已获得进程隔离。

**软件温控不能强制中断已开始的原生调用，也不能替代 CPU 固件或独立硬件过热保护。** 外层进程监督可以终止计算进程；这不等于在同一进程内安全中断 C++/NumPy 调用，也不保证终止不可中断内核 I/O。

## 原问题与实际改动

此前独立故障注入发现：合作式 guard 在状态锁内调用 reader、写盘和 fsync。reader 或 fsync 卡住时，边界 `check()` 和退出流程会等待同一把锁。旧证据保留在 `docs/results/pyignite_isolation_20261113/baseline-fault-results.json`，对应旧执行提交 `942cf0e2691f9faa5678e0bccf8016dc4c63e5ab`。

新增入口将传感器调用、检查点 exists/load/commit 各自放入一次性的 Python 子进程。父进程经 stdin/stdout 传送版本化 JSON；`communicate(timeout=...)` 的期限包含发送输入、接收回执和等待退出，避免把大 stdin 写入本身遗漏在监督之外。nonce、请求内容 SHA-256、action、返回类型与持久化枚举都要匹配。超时、非零退出、身份不符、未知持久化状态或畸形回执均拒绝；超时后的“成功”也拒绝。失败 transport 锁定，不自动重试。

POSIX 子进程拥有独立 session，超时先 TERM，再 KILL 自己启动的进程组；二次等待也有期限。清理未完成记为 `fail`，不会无限等待或改写为通过。Windows 只有直接子进程语义，未实现 Job Object，不声称完整进程树清理。此入口调用可信、已安装的 provider，不是执行不可信代码的安全沙箱。

原 `CheckpointStore` 只增加可覆盖的 `exists()` 与构造 hook，序列化格式、完整 FCBlock 结果、校验和、临时文件→文件 fsync→原子替换→POSIX 目录 fsync 顺序保持不变。隔离入口的父进程不执行检查点目录创建/探测/读取/fsync。写盘 worker 超时后持久性为 `NOT_CONFIRMED`，不得接受部分结果或把未确认代次当成可恢复的新结果。

worker 被终止时可能来不及删除临时文件。**进程清理成功与临时文件清理成功分开记录。** 恢复先验证最后完整检查点；本补丁不会通配删除可能属于其他实例的临时文件。若错误/超时发生在原子替换之后，磁盘可能已有一个校验有效的新完整候选文件，但目录持久性和父进程是否收到确认仍未知；新增测试覆盖目录 fsync 在替换后报错。此时仍是 NOT_CONFIRMED，不返回成功结果。恢复必须显式检查、使用 resume_after_inspection=True，不能从文件存在或校验有效反推出故障前已确认持久化，更不能把旧数据当新测量。真实断电、存储控制器缓存、介质失效与恶意篡改防护均未验收；SHA-256 不证明故障 CPU 算对了。

## 使用

```python
from pyignite import FCBlock, IsolatedTemperatureGuard

# 显式启用；Linux 仍只接受已识别的 CPU 摄氏温度传感器。
with IsolatedTemperatureGuard('last-complete.json',
                              io_timeout_seconds=2.0,
                              cleanup_seconds=0.25) as guard:
    model = FCBlock(layers, backend='scalar', temperature_guard=guard)
    result = model(x)
```

自定义传感器使用 `reader_spec='installed_module:public_callable'` 和 JSON `reader_kwargs`。闭包、lambda、父进程里的可变状态、NumPy tensor 和原生指针不能跨越这个边界。每次调用都是新进程，不依赖 provider 的进程内累计状态。测试 provider 位于 `tests/pyignite/thermal_fault_fixtures.py`，不是实际温度测量。

```python
import sys
from pyignite import run_supervised

# 在外层进程施加总期限，可覆盖子进程持有 GIL 的原生计算。
receipt = run_supervised([sys.executable, 'inference_job.py'],
                         timeout_seconds=30.0,
                         cleanup_seconds=0.25)
if receipt['timed_out'] or receipt['exit_code'] != 0 or receipt['cleanup'] == 'fail':
    raise RuntimeError('计算未被确认完成；只能检查此前完整检查点')
```

该监督器是总运行时间监督，不冒充独立硬件温度 watchdog。新进程创建和检查点落盘增加延迟，实际采样间隔包含 I/O 时间；默认 max-gap 策略保持保守，开销过高可能使 guard 拒绝继续计算。没有实时 OS、吞吐、速度或功耗优势结论。

## 本次证据

| 类别 | 实际结果 | 边界 |
|---|---|---|
| 当前候选源码契约 | 运行52项，51通过、1跳过 | G1 adapter 缺少 safetensors；跳过不是通过 |
| reader 持续阻塞 | 隔离 worker 超时，清理完成，guard 锁定，后续 check/exit 可返回 | 模拟 provider；旧合作式入口仍受原边界限制 |
| fsync 持续阻塞 | 超时，`CHECKPOINT_FAILED / NOT_CONFIRMED`，旧完整文件保留 | worker 被杀后临时文件可残留，独立登记 |
| 其他拒绝/恢复 | fsync异常、替换前进程退出、观测过期、执行中触发、损坏恢复、错误/迟到回执拒绝 | 不是物理断电实验 |
| 持有 GIL 的原生子进程 | libc sleep 调用由外层期限监督结束并清理 | 终止进程，不是进程内中断调用 |
| 真实 NumPy/LAPACK SVD | 已输出进入标记，约1秒期限后终止并清理 | 2048×2048 FP64；单个本机实验，无真实过热 |
| wheel 安装 | 源码目录外的 venv 安装，私有worker已包含，模拟hwmon的完整FC输出校验通过 | venv沿用系统NumPy，不是全新无依赖系统 |
| 当前严格 Torch PE | `NOT_RUN`，诊断命令退出2 | 本机未安装Torch，不可升级为绿色 |

原始结果、环境、准确命令、源码与产物 SHA-256：[`results/pyignite_isolation_20261113/`](results/pyignite_isolation_20261113/)。这些是本机结果，不能当作本次 GitHub CI。跨平台新 CI 必须绑定本 PR 的实际 head/run/attempt；旧 CI 与新代码测试分开。

## 严格数值诊断

新增 `tools/pyignite/diagnose_pe.py`：先直接调用未改的 `tools/onnx/models/layers.py`，用原始 `np.testing.assert_allclose(..., atol=2e-5, rtol=2e-5)` 确定严格结果，并保存 native 输出、原 Torch 输出、超差掩码、Torch FP32 指数输入/频率/相位和文件哈希。之后才生成 NumPy exp、double exp 后舍入、double 运算顺序、可用的系统 libm expf 对照。受控频率替换一律标记 `LOCALIZATION_ONLY`，不能覆盖严格 PASS/FAIL。

缺少 Torch/原生库时记录 `NOT_RUN` 并退出2；严格失败退出1；严格通过才退出0。已有严格 validate 与固定基线 no-new-regression 工具均保留。CI 增加两套依赖环境的诊断与原始数组上传，严格失败不会被 `continue-on-error` 或放宽阈值掩盖。因此旧的已知严格 PE 失败仍可能使新 PR 的检查红色，不能据本补丁宣称动态 PE 已修复。

```bash
# 仓库根目录；解释器实际版本需另存。
python tools/pyignite/build.py
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -m unittest discover -s tests/pyignite -v
PYTHONPATH=tools/pyignite OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python tools/pyignite/review_isolation.py \
  --base-commit 6f7c2dc67c3d640ebbb32b9f97ef4dbb0fa4e0b0 --output /tmp/unique-isolation-result.json
PYTHONPATH=tools/pyignite python tools/pyignite/diagnose_pe.py \
  --base-commit 6f7c2dc67c3d640ebbb32b9f97ef4dbb0fa4e0b0 --output-dir /tmp/unique-pe-diagnosis
# 原始严格工具仍独立运行：
PYTHONPATH=tools/pyignite python tools/pyignite/validate.py --output /tmp/original-strict.json
```

诊断目录/独立结果文件必须未被使用，避免覆盖旧快照。当前候选不修改模型 PE buffer、频率算法、FP32 舍入、矩阵运算顺序或 fast-math 标志。真实模型输出、token决策、完整G1、GPU/机器人、macOS/ARM64当前独立复现、Windows、旧奔腾、真实风扇/CPU损坏、供电和独立硬件 watchdog 仍未完成。
