# MotionBricks 仓库导航

第一次运行动作生成，可以从[四个应用的入门教程](guided_tutorial.md)开始。接入自己的程序时看 [Python 运行时接口](runtime_api.md)和 [ONNX 输入输出](onnx_inference.md)。两套骨架的约定分别见 [SOMA](soma_model.md) 和 [Unitree G1](unitree_g1_model.md)。

## 在 CPU 上重跑早期代码

在仓库根目录使用 Python 3.12 或 3.13。模型契约测试需要 NumPy，其余六组只用 Python 标准库。下表链接到实现和对应的测试。

| 想核对什么 | 实现 | 测试 |
| --- | --- | --- |
| SOMA 与 G1 的张量形状、帧数范围和模型清单 | [模型契约](../motionbricks/model/contract.py) | [两套模型的契约测试](../tests/motionbricks/test_motion_bricks_contract.py) |
| 安装运行时之前，能否读取模型清单、校验输入姿态 | [环境与姿态预检](../tools/preflight.py) | [preflight](../tests/preflight) |
| 同一组整数换用二进制、平衡三进制和平衡七进制，点积是否一致 | [整数后端](../motionbricks/radix_portability.py) | [radix_portability](../tests/radix_portability) |
| 除法、对数和归一化遇到零时，调用方如何处理结果 | [零值处理](../motionbricks/zero_guard.py) | [zero_guard](../tests/zero_guard) |
| 倒数途中乘员要求暂停后，恢复和确认分别需要什么条件 | [乘员倒数](../motionbricks/crew_countdown.py) | [crew_countdown](../tests/crew_countdown) |
| 收到「训觉」请求后，暂停动作生成期间是否仍逐次调用平衡控制 | [休眠与唤醒](../motionbricks/sleep_mode.py) | [sleep_mode](../tests/sleep_mode) |
| 经典模拟器的双通道计数能否与采样请求、时钟记录对应 | [光钟与采样接口](../motionbricks/optical_quantum.py) | [optical_quantum](../tests/optical_quantum) |

```sh
(
  set -e
  python -m unittest discover -s tests/motionbricks -p test_motion_bricks_contract.py -v
  for suite in preflight radix_portability zero_guard crew_countdown sleep_mode optical_quantum
  do
    python -S -m unittest discover -s "tests/$suite" -v
  done
)
```

想先看一次计算，可以跑 `python -S -m motionbricks.radix_portability --backend all`。默认输入的三个 `value` 都应为 `-122`。[乘员倒数演示](../tools/crew_countdown/demo.py)可用 `python -S tools/crew_countdown/demo.py` 运行，逐步对照[十步模拟记录](crew_countdown_demo.json)，看倒数到零和乘员确认分别发生在哪一步。

完整 GPU 推理的安装与运行条件见[仓库安装说明](../README.md#setup)。离线预检输出中的 `offline_ok` 对应配置、清单及所提供的姿态，推理执行情况看 `inference` 字段。

## 按主题浏览

| 主题 | 入口 |
| --- | --- |
| 工程实验 | [CPU 推理参考](cpu_reference.md) · [跨进程整数后端](radix_ipc.md) · [PyIgnite](pyignite.md) |
| 研究与数据 | [研究专题](research/) · [VR 局部镇痛与患者自选医护形象](research/vr_localized_analgesia_zh.md) · [航天急救医学与工程博士项目倡议](research/space_emergency_medicine_phd_proposal_zh.md) · [行过油坊，条瘾会唔会静一阵？](research/peanut_oil_aroma_opioid_craving_zh.md) · [仓库数据集](../data/) |
| 建筑与设计 | [历史建筑档案](heritage/) · [概念设计](concepts/) · [往旅行者方向寄出的第二封信](concepts/voyager_second_letter/README.md) |
| 公共议题与文学 | [公共政策](policy/) · [换了货币，还是一家人](policy/eu_family_status_zh.md) · [广西候鸟诱捕调查与复查建议](policy/guangxi_migratory_birds_zh.md) · [小说与剧本](fiction/) · [粤语创作](creative/) · [深圳 APEC 夜景与美食新闻稿](creative/shenzhen_apec_2026/README.md) |
