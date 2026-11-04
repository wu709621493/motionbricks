<!-- SPDX-License-Identifier: CC-BY-4.0 -->
# Oyasumi 公益研究版：非营利定位与复现说明

提议：吴孟城（Windy Wu）；代码与文档整理：AI 辅助。
版本提案日期：2026-11-04。此说明随 [PR #26](https://github.com/wu709621493/motionbricks/pull/26)
接受审查，范围限定为 MotionBricks fork 中的 Oyasumi 睡眠补丁。

本版本以公开研究、教学和可复现的节能控制实验为目标，不以向出资者分配利润为目标。
“非营利”描述本版本拟采用的维护与发布方式；它不表示已经成立非营利法人、取得免税资格，
也不代表 NVIDIA、上游 MotionBricks 或其他贡献者作出了相同的组织承诺。

## 版本范围

公益研究版沿用同一套 Oyasumi 实现与回归测试，版本差异体现在本说明中的用途和维护政策。

| 内容 | 仓库入口 | 本版本安排 |
| --- | --- | --- |
| 睡眠监督与运行适配器 | [sleep_mode.py](../motionbricks/sleep_mode.py) | 一次晚安请求；持续执行平衡回调 |
| Oyasumi 回归测试 | [test_oyasumi.py](../tests/sleep_mode/test_oyasumi.py) | 公开命令取消、故障与恢复等测试 |
| 原有睡眠测试 | [test_sleep.py](../tests/sleep_mode/test_sleep.py) | 继续验证原接口与安全状态切换 |
| 技术接口及边界 | [sleep_mode.md](sleep_mode.md) | 公开阈值、假设和未验证的硬件指标 |

该监督模块及其睡眠测试只依赖 Python 标准库，可在本地 CPU 上复现。
这一范围不包括完整 MotionBricks 模型推理，也不免除整仓其他组件的依赖条件。

## 拟采用的维护与发布原则

1. **免费提供研究材料。** 本版本的源码、测试和说明公开提供；使用睡眠监督模块无需付费解锁、
   订阅、账户或许可证服务器。参与者自行承担其计算设备、用电和实验成本。
2. **完整提供控制功能。** 平衡回调、唤醒、故障锁定和恢复检查对所有使用者一致可用，
   不按付费或资助身份分级，不为商业展示关闭故障检查。
3. **按证据维护。** 修改通过 PR 记录行为、测试和局限；发现错误时公开修订。
   资助者身份不替代技术审查或实验结果，不据此提高已经验证的能力等级。
4. **资金用于研究目标。** 若未来接受资助或支持服务收入，拟记录来源、用途和相关利益关系，
   将资金用于测试、文档、计算资源与维护；合理劳务报酬和成本报销应列明。
   不按出资比例向出资者分配结余。本 PR 未建立募资渠道、收款安排或财务报告制度，
   也不承诺捐赠可抵税。

这些是本版本维护方的拟议项目政策，不向软件接收者添加新的许可义务。
第三方仍按各文件适用的许可证使用、修改和再分发。

## 许可证与署名

仓库 [LICENSE](../LICENSE) 开头将源码列为 Apache-2.0，将文档、skills 和资产列为
CC-BY-4.0。本补丁遵循这一安排，其他组件如有专门许可或第三方声明，应同时核对。

| 对象 | 适用安排 | 本说明的作用 |
| --- | --- | --- |
| Oyasumi Python 实现与测试 | 现有 Apache-2.0 | 保留许可证、修改说明及适用的原作者声明 |
| 本公益研究版说明与技术文档 | 现有 CC-BY-4.0 | 保留署名、许可链接及修改标记 |
| 上游模型、资产及其他第三方内容 | 对应文件与第三方许可声明 | 不扩大本补丁的授权范围 |

Apache-2.0 和 CC-BY-4.0 允许符合其条款的商业使用。
因此，本版本的非营利目标不构成“仅限非商业用途”条款，也不撤销接收者原已获得的权利。
本 PR 不替换根许可证，不把上游内容重新标为 CC-BY-NC，不声称独占上游成果。
“禁止商业使用”属于另一项许可决策，未在本版本实施。

核对依据（2026-11-04）：[Apache License 2.0](https://www.apache.org/licenses/LICENSE-2.0)，
特别是第 2—4、6、9 条；[CC BY 4.0 官方说明](https://creativecommons.org/licenses/by/4.0/)
及其[法律文本](https://creativecommons.org/licenses/by/4.0/legalcode.en)。
署名和原作者声明不表示原作者为本公益研究版背书。

## 晚安请求的技术约定

在正常控制周期传入一次 `oyasumi=True`，随后继续提供新鲜传感器数据。
系统先满足严格进入条件并持续稳定达到等待时间，再暂停可选动作生成。
每个周期仍须执行独立平衡回调；`oyasumi=False` 表示本周期没有新请求，不表示取消。

`wake=True` 清除待执行或已入睡的晚安请求。失稳进入 RECOVERY，数据异常、超时或回调失败
进入 FAULT，并清除请求；恢复或故障确认周期中的晚安请求会被丢弃。
恢复完成后，需在后续健康周期重新发送晚安请求。原有 `sleep_requested` 是调用方维护的
持续请求；若要保持清醒，调用方也应清除这一持续请求。

默认阈值是软件示例参数。该模块不计算平衡力矩，不直接驱动电机，也不提供硬件稳定性保证。
实际控制器、独立看门狗及过期规划结果处理仍须按 [技术文档](sleep_mode.md) 接入和验证。

## 本地复现与结果解释

从 PR 分支的仓库根目录使用 Python 3.12 或更高版本运行：

```bash
python3 -S -m unittest discover -s tests/sleep_mode -v
```

套件包含 22 项测试，其中 13 项覆盖 Oyasumi。
`test_one_shot_runtime_retains_balance_and_valid_zeros` 使用 0.1 秒稳定等待时间、
100 Hz 合成输入和一次晚安事件，在 100 个周期中执行 100 次平衡回调、10 次动作生成。
这里比较的是函数调用次数；不能据此声称耗电减少 90%。零倾角与零速度仍作为有效数据处理。

后续若开展硬件研究，应分别报告实际能耗、姿态偏差、支撑裕度、唤醒延迟和故障恢复结果，
并列出设备、负载、采样方式与对照条件。本版本没有提供这类硬件实测结果。

## English summary

Oyasumi Nonprofit Research Edition is a proposed public-benefit maintenance and
publication policy for the existing one-shot sleep patch. It provides the same
code and reproducible CPU tests freely, with no payment-dependent control path.
The existing Apache-2.0 source and CC-BY-4.0 documentation licenses continue to
apply, including their permissions for commercial use. This statement adds no
noncommercial restriction and does not establish a nonprofit legal entity,
tax-exempt status, donation eligibility, or endorsement by upstream contributors.
