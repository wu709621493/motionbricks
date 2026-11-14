# #97 × #96：“联谊组合试错”与修复

日期：2026-11-14。用户原话：

> 代码仓97&96举行“联谊组合试错”，修一下bug

#96 已合并，#97 保持 Draft。本次将固定 main `d715dc1f08bd881796526beffad5a3931e26a0ed` 与 #97 原 head `4dd205ead357ebe687d95746a267cf003a93c21a` 合到同一工作树，集成基线提交为 `711f0e1`。使用 #97 的 `run_supervised` 监督 #96 的真实 CLI；模型子进程仍用 `python -S`，未增加模型依赖或改变行为参数。

## 复现与修复

| 问题 | 修复前证据 | 修复后行为 |
|---|---|---|
| 启动器退出 0，关闭管道的后代仍存活 | 后代在回执返回后生成一个真实蟑螂模拟输出目录 | 正常退出也检查自有 POSIX 进程组，TERM/KILL 清理；后代不能继续补写 |
| 有身份正确的回执，但清理状态为 fail | I/O transport 仍接受该回执 | 拒绝并锁定失败，不把进程退出 0 当成完整操作成功 |
| worker 返回 `[]`、`null`、数字或字符串 | 抛 AttributeError，transport 未锁定 | 要求对象和整数版本号；统一抛 IsolatedIOError，并禁止自动重试 |
| 大 stdin 阻塞后超时 | 父端 stdin 仍开放，原测试出现 ResourceWarning | 正常、超时和异常路径关闭全部父端管道 |
| 模型配置文件根节点不是对象 | `--config` 崩溃、退出 1、打印 traceback | 退出 2，返回结构化 `REFUSED`，不创建输出目录 |

清理等待是有限的。POSIX 进程组在宽限期结束后仍存在时返回 `cleanup=fail`；即使只剩尚未被 OS 回收的僵尸，也不推定已经完成清理。Windows 仍只覆盖直接子进程。主动脱离 session 的后代不属于进程组监督范围；未新增安全沙箱或硬件 watchdog 的声明。

## 本机验证

Linux x86-64 / CPython 3.12.14。保存的修复前失败日志与修复后日志见 [原始记录](results/roach_pyignite_integration_20261114/)。

- #96：14 项全部通过；`python -S` 模型契约仍独立执行。
- #97 与联合测试：59 项，58 通过、1 项缺少 safetensors 跳过。启用 `-W error::ResourceWarning`。另验证父进程异常时回收子进程并关闭管道。
- 六情景分别以固定种子 7、8 个体、20 步运行。被监督的 CLI 输出与同配置的直接模拟完整相等，检查 run.json、metrics.csv、observe.html 的 SHA-256。对每个目录再次运行均拒绝覆盖，且逐文件复核原哈希。
- 200 个体、7200 步的真实模拟已输出进入标记后，在 0.6 秒总期限中止，未发布 sha256.json 完整清单。
- 正常退出启动器遗留的后代被限制，等待后没有迟到模拟结果。清理状态未确认仍按失败处理，不将此情景登记为普通计算成功。
- 原 kernel、validate.py、Torch oracle 与位置编码实现保持不变。没有 Torch 的本机严格诊断仍为 NOT_RUN/退出 2；旧 CI 的 PE 严格失败记录保留，不能据软件契约通过声称数值偏差已修复。

```bash
python tools/pyignite/build.py
python -S -m unittest discover -s tests/roach_home -v
OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 python -W error::ResourceWarning -m unittest discover -s tests/pyignite -v
```

Virtual cockroach home workflow 增加 Windows/macOS/Linux、Python 3.12/3.13 的联合测试，并在 supervisor 改动时触发。跨平台结果需以提交后的实际 run 为准，不能把本机通过当成跨平台通过。

这些检查验证软件行为和合成数据的一致性；模型继续标为 SYNTHETIC_UNCALIBRATED / empirical_validation=NOT_RUN。本次未实现死亡、食尸、感染传播或模拟中的断点续算，也没有真实动物、真实过热、物理断电或浏览器交互验证。
