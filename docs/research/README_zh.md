# 科研入口与复现边界

目录快照：2026-11-13，main `f43c457d27126fbb3d6f3d62e896ad3c0f1d7161`。这是精选入口，不是全部文件清单，也不是所有研究已经验收的声明。各文档中的历史数字应与其原始提交及环境一起阅读；本次整理没有逐项重跑。

实时 PR 状态与追加证据见[现有审查台](https://motionbricks-review-desk.consideratehumor1.chatgpt.site)。该站保留历史记录；GitHub 的开放、合并状态不等于科研结论已验证。

| 主题 | 正文与数据入口 | 仓内证据属于什么 | 下一步与不能声称的结论 |
| --- | --- | --- | --- |
| **优先 #99：维度与耦合场** | [v0.1 立论](../dimensional_transition_coupled_fields_zh.md) | 文献、候选作用量、符号推导 | 指定势能/耦合/初始数据后再求解；没有真实降维、虫洞生成或实验拟合结果 |
| **Rb-14 孤品芯片** | [概念](../rb14_unique_chip_concept_zh.md)、[物理预算](../rb14_phase1_physics_zh.md)、[配置](../../configs/rb14_phase1.json)、[历史报告](../results/rb14_phase1/report.json) | 假设参数下的质量、噪声、几何前向计算 | 器件制造、原子捕获、频率测量、熵与 PUF 安全均未验证；49配对量不等于49独立随机位 |
| **PyIgnite 数值与温控** | [接口](../../tools/pyignite/README.md)、[温控边界](../pyignite_thermal_checkpoint_zh.md)、[专用审查台](https://motionbricks-review-desk.consideratehumor1.chatgpt.site/pyignite)、[后续 #97](https://github.com/wu709621493/motionbricks/pull/97) | CPU实现、契约检查、严格数值对照与独立故障注入分别记账 | 严格 PE 偏差仍需解决；无新回归不等于严格通过，软件温控不能代替硬件保护 |
| 汉江药物与两栖研究 | [调查](../han_river_hormones_pde5_ecology_zh.md)、[两栖边界](../han_river_amphibians_xenopus_zh.md)、[CSV及口径](../data/han_river_pharmaceuticals/README.md)、[校验规则](../data/han_river_pharmaceuticals/VALIDATION.md) | 已发表资料整理；CSV区分实测汇总、未检出、模型和检索缺口 | ACCEPT仅为表格一致性，不能证明生态安全；本仓没有开展当地采样或动物实验 |
| BEC500 | [动力学](../bec500_dynamics.md)、[损失研究](../bec500_loss_study.md) | 有限双模模型数值计算及经典 Hopfield 对照 | 不是500可寻址量子比特；数值一致性不证明物理器件准确度 |
| Bell / CHSH | [协议与数值验证](../bell_chsh_validation.md) | 经典计算机上的概率采样与事件记账 | 理想 Bell 概率采样不是真实纠缠测量，不证明量子硬件或密码学随机性 |
| RS-72 动态阵风 | [原概念](../rs72_civil_weather_aircraft_zh.md)、[动态验证](../rs72_dynamic_gust_validation_zh.md) | 假设参数下的梁/单自由度响应与数值核验 | 参数校准、风洞、真机、适航均没有由这些计算得到验证 |
| 根系—土体—地震 | [模型与校准路线](../root_soil_seismic.md) | 人工参数的拟静力/刚性滑块计算 | 未校准树种、土槽、实测地震或现场；不是工程安全判定工具 |
| 虚拟民宅蟑螂行为 | [模型与限制](../roach_home/README_zh.md)、[实验配置与历史导出](../../experiments/roach_home/README.md) | 未校准的代理模拟与配对种子比较 | tick/cell无拟合物理尺度，不代表民宅真实行为，不涉及活体放养 |
| Putin Hypothesis 四作家 | [研究入口](putin_hypothesis/README_zh.md)、[方法](putin_hypothesis/METHODS_zh.md)、[来源](putin_hypothesis/SOURCES.md) | 档案资料与待执行预测任务 | 不研究普京私人关系；史料覆盖不能替代读者心理预测测试 |

## 从仓库根目录运行

以下是已有入口，使用 Python 3.12/3.13；是否通过取决于当前提交和环境。`-S` 表示不加载 site-packages，只用于标记为标准库的入口；它不是沙箱。涉及 NumPy/SciPy/Torch 的模块按各自文档装依赖。

| 目的 | 标准库命令 | 结果的含义 |
| --- | --- | --- |
| Rb-14 模型回归 | `python -S -m unittest discover -s tests/rb14 -v` | 软件符合既定计算模型，非硬件验证 |
| Rb-14 生成新报告 | `python -S -m motionbricks.rb14_feasibility --config configs/rb14_phase1.json --out-dir /tmp/rb14-new-review` | 合成前向预算；请选择新目录，不覆盖历史输出 |
| 汉江表格校验 | `python -S tools/validate_han_river_csv.py --json` | 字段/证据口径一致性；保留源文献冲突与未知量 |
| 汉江拒绝路径回归 | `python -S -m unittest discover -s tests/han_river -v` | 非法或混淆证据输入的拒绝行为 |
| 根土模型回归 | `python -S -m unittest discover -s tests/root_soil -v` | 合成模型的解析极限与边界 |
| 蟑螂模型回归 | `python -S -m unittest discover -s tests/roach_home -v` | 种子、网格、种群与导出契约，不验证生物学 |
| 四作家档案校验 | `python -S tools/research/validate_putin_hypothesis.py` | 引用和任务结构一致性，不计算心理预测准确率 |

## 新实验记录方式

1. 记录完整源码提交、实际系统/架构/Python、依赖与准确命令；PR正文和历史CI只能作为各自来源的证据。
2. 新输出写到新目录，记录实际字节数与 SHA-256；散列证明所取字节一致，不证明来源真实或科学结论成立。
3. 保留 FAIL、跳过、NOT_RUN、超时和清理失败；区分数值误差、模型误差、测量误差与未实施硬件任务。
4. 沿用各模块的验收规则。修改容差、参考答案或模型须另行明确说明，不能借目录整理改变结果含义。

本目录只增加入口和证据边界，不搬移原件、不覆盖结果、不修改运行时代码。
