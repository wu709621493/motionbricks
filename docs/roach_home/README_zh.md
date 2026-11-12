# 虚拟民宅与蟑螂行为观察 v0.1

提出：吴孟城（Windy Wu）。实现与资料整理：Codex。日期：2026-11-13。

> 由于我认为直接租一个民宅研究蟑螂有点容易实验失控，但是我们又需要这个实际环境来研讨蟑螂行为学，所以我们只能用我们的代码仓写一个民宅，然后写一群蟑螂放到我们这个民宅里面观察了🤔

本模块已经实现一个可运行的二维民宅与多智能体假设模型。它用文献启发的规则生成模拟轨迹，用来提出问题、检查规则和比较情景。民宅是虚构户型；没有实测户型、现场蟑螂轨迹或参数拟合，因此还不是经过验证的真实民宅数字孪生。目标物种为德国小蠊（*Blattella germanica*）；没有使用人体或机器人 MotionBricks 权重推断昆虫行为。

## 直接运行

在仓库根目录使用 Python 3.12 或更高版本，无需安装第三方包或 GPU 依赖：

```sh
python -S -m motionbricks.roach_home --out-dir /tmp/roach-home-01
```

用浏览器打开输出目录中的 `observe.html`。可以播放、暂停、拖动时间、选择单只个体轨迹、调整回放速度，以及显示整段运行的停留热图。HTML 含有全部数据，可以离线使用；它回放 Python 的结果，不在浏览器里重算行为。

默认 40 只个体、720 个模型步、随机种子 1，每步保存轨迹；240 步为一个人为设定的明暗周期，其中前 120 步开灯。格子没有校准为厘米，模型步没有校准为秒。这里的 720 步不能解读成 12 分钟或数天。

```sh
python -S -m motionbricks.roach_home --agents 80 --steps 1200 --seed 7 \
  --house experiments/roach_home/apartment.json \
  --config experiments/roach_home/config.json --out-dir /tmp/roach-home-02
python -S -m motionbricks.roach_home --compare --seeds 1,2,3,4,5 \
  --out-dir /tmp/roach-home-comparison
python -S -m unittest discover -s tests/roach_home -v
```

输出目录必须尚不存在，以防覆盖旧实验。CLI 选项覆盖配置 JSON 中同名项；比较使用 `--seeds`，逐次替换配置中的 `seed`。若修改代码，应同时记录 Git 提交；配置 SHA-256 只标识模型版本字符串、情景、有效配置与有效户型，不是源代码散列。

## 已实现的民宅

41 × 29 格，四个房间：厨房、卫生间、客厅、卧室。外墙封闭，隔墙通过四组门洞连接；冰箱、餐桌、盥洗台、沙发与床用不可通行方块近似。家具下的三维缝隙没有建模。四组可进入的藏身格近似橱柜边缘、墙脚或床缘，不代表真实缝隙高度与角度。

编辑 [apartment.json](../../experiments/roach_home/apartment.json) 可修改户型与资源位置：

| 符号 | 含义 | 模型约束 |
| --- | --- | --- |
| `#` | 墙或实体家具 | 不能穿越；外围必须封闭 |
| `.` | 普通地面 | 每步只能停留或移动到上下左右一格 |
| `s` | 藏身格 | 具有遮光与停留加分，没有硬容量 |
| `f` | 普通食物点 | 无限补给的理想化资源，不消耗库存 |
| `w` | 水点 | 无限补给的理想化资源，不模拟湿度 |

所有可通行格须连通且恰好属于一个房间。单格允许多个个体重叠；拥挤只提供软惩罚，不模拟身体碰撞与真实密度上限。

## 规则及证据边界

| 机制 | 文献事实或来源范围 | v0.1 如何近似 | 不能声称 |
| --- | --- | --- | --- |
| 触觉与藏身几何 | 德国小蠊的选择实验显示对较小夹角藏身处的偏好 [S1] | 邻接墙体加分，藏身格加分 | 已复现触角力学、缝隙角度或真实速度 |
| 同伴与聚集 | 德国小蠊藏身处选择研究支持社会放大与资源限制的共同作用 [S2] | 同格及四邻格同伴数的 `log(1+n)` 加分，另有拥挤惩罚 | 复刻了论文方程、拟合值或最佳群体规模 |
| 食物附近的社会信息 | 德国小蠊 Y 型嗅觉仪实验显示摄食同伴的线索能影响短距离选择 [S3] | 食物场和通用同伴项各自加分 | 已识别或实现具体化学信号 |
| 聚集化学成分 | 德国小蠊初龄若虫实验未支持纯化表皮烃是主要聚集驱动 [S4] | 同伴项只称“社会作用代理” | 将所有聚集归因于一种确定信息素 |
| 光照与活动 | 本版采用假设性明暗调制；各数值均未拟合 | 开灯移动尝试率 0.30，暗时 0.75；藏身格有效光照乘 0.1 | 从人为设定的活动差异反证真实夜行性 |
| 饥饿、口渴与资源 | 行为需求的工程代理 | 饥饿每步加 0.008、口渴加 0.012，上限 1；接触对应资源后归零 | 真实代谢、脱水、存活时长或摄入热量 |

所有行为权重、活动率、需求增长率及感知距离都属于**待校准假设**。相关论文提供建模方向，没有提供本户型的数值参数。

一次更新使用更新前所有个体的占用快照，逐个抽取动作，最后同时更新位置。每个个体每步固定消耗两个伪随机数，使同种子情景具有相同初始位置、初始需求和对齐的随机数流。个体不知道整屋地图，也不比较所有目的地；资源场是按可通行路径距离构造、截断在 `sensor_range` 内的工程代理，**没有模拟气流、气味扩散或实际感受器**。同伴计数不透过墙体。

对“当前格 + 四邻可通行格”计算分数：贴壁项 − 有效光照项 + 藏身项 + 社会项 − 拥挤项 + 饥饿加权食物项 + 口渴加权水项 + 方向延续项 + 藏身原地停留项。再通过 softmax 采样；移动尝试未通过活动门控时留在原地。方向延续加分 0.6，藏身原地加分 0.8。资源场为 `exp(-图距离/4)`；拥挤项为 `crowd_weight × n²`。

## 对照与输出

| 情景 | 相对 baseline 的唯一设置变化 |
| --- | --- |
| `baseline` | 默认明暗、食物、水源、藏身格和社会权重 |
| `constant_light` | 全程按开灯阶段运行，包含活动门控的变化 |
| `no_food` | 所有 `f` 改为普通地面 |
| `no_water` | 所有 `w` 改为普通地面 |
| `no_shelters` | 所有 `s` 改为普通地面，同时移除遮光与藏身停留加分 |
| `no_social` | `social_weight=0`；拥挤惩罚仍然存在 |

`no_food` 不会产生饿死个体，`no_water` 不会产生脱水死亡；这两种对照只检查需求驱动移动规则。`no_shelters` 是移除抽象藏身属性，并没有封堵路径或移走家具。若要分离光照对活动门控与对位置偏好的影响，需要后续增加因子实验。

每次单次运行输出：

- `run.json`：有效户型、配置、运行平台、版本、配置散列、逐步指标、个体轨迹、停留计数和摘要。
- `metrics.csv`：每步移动比例、藏身比例、贴壁比例、各房间个体数，以及食物／水接触的个体步数。
- `observe.html`：离线观察回放。热图为整段运行累计值，不随回放游标截断；其单位是“个体 × 模型步”。
- `sha256.json`：同目录其他文件的 SHA-256；不包含自身。

需求归零只表示发生模型接触，不是实际摄食事件。`food_contact_agent_ticks` 和水源同类指标可重复累计同一个体的连续停留，不能称为访问次数或独立摄食次数。贴壁指四邻格存在墙／家具，不等同于实测触角接触。

比较模式输出每种子每情景的 `replicates.csv`、跨种子的 `comparison.csv`、完整比较配置和校验清单。比例摘要使用后半段模型步的算术平均；这只是预定分析窗口，不宣称系统已达平衡。`paired_delta_sd` 为不同种子的配对差值标准差，单种子时为空。随机种子不是生物学重复；结果不包含真实人群／蟑螂群体效应置信区间或显著性结论。

## 本次对话提出的下一层问题：同类遗体与间接暴露

吴孟城追问：“蟑螂会以其他蟑螂的遗体为食物吗”。答案为会，但不能把所有遗体当成稳定、等价的普通食物。

- 德国小蠊研究已实测同类遗体的摄食，而且不同实验室／野外来源品系之间存在差异 [S5]。该研究亦讨论了既有研究中食尸程度不一致的结果。
- 同时提供普通饲料与干燥遗体的实验中，蟑螂偏好普通饲料；仅以干燥遗体或粪便为食时寿命较短，研究未观察到繁殖 [S6]。不能由此泛化为“所有蟑螂只在极端饥饿时食尸”。
- 对德国小蠊的实验表明，食尸可以成为鼠伤寒沙门氏菌在同类间传播的途径；真实环境中的相对贡献仍不确定 [S7]。

因此未来的遗体实体至少要区分：可食质量、状态／放置时间、与普通食物的竞争、品系差异，以及独立的污染状态。营养回收不能创造能量，也不能直接推导“死一只能够养活多少只”。**v0.1 未实现死亡、遗体、食尸、病原体或毒饵。**当前 `f` 仅代表普通理想化食物，不能将它改名为遗体后宣称已研究食尸。

吴孟城进一步提出减少人与蟑螂的物理接触。公共卫生资料支持防止食物污染并减少蟑螂过敏原暴露 [S8–S9]；减少直接接触是其中一部分。排泄物、唾液与身体碎屑中的过敏原还可在环境中形成间接暴露。因此后续模型需分别记录直接触碰、表面污染、食物污染及尘埃暴露，不能把“人没有碰到蟑螂”当作零暴露。**这些人类活动与暴露机制尚未实现，当前没有感染风险估计。**

## 校准路线与当前限制

下一步应先选定物种、龄期、性别与来源，在可获取的公开原始视频／数据上分别校准行走、墙距、藏身停留和资源接触；保留独立数据用于验证，比较纯随机游走与逐项去除规则后的预测能力。还应扫描光照、贴壁、社会与拥挤权重，并改变户型和初始分布，检验结论是否只是参数选择的产物。任何真实动物观察须另有合适的封闭饲养、机构审查和环境控制安排；本代码没有实施真实动物实验。

本版没有温度、湿度、繁殖、死亡、龄期、性别、学习、长期记忆、真实触角、气味扩散、室外迁入、管道／墙缝三维网络、人体／食物污染或杀虫剂动力学。没有昆虫运动生成模型、真实 GPU 推理或人体研究。软件测试验证可复现性、墙体约束及输出完整性，不验证生物真实性。

## 原始研究与公共卫生来源

检索日期：2026-11-13。以下均为原始论文或政府公共卫生资料；无长篇复制。

| 编号 | 来源 | 使用范围 |
| --- | --- | --- |
| S1 | Chen et al. (2022), *The impact of thigmotaxis deprivation on the development of the German cockroach*. [全文](https://pmc.ncbi.nlm.nih.gov/articles/PMC9385682/), DOI: 10.1016/j.isci.2022.104802 | 触觉与藏身几何；不能推出本模型贴壁权重 |
| S2 | Amé et al. (2006), *Collegial decision making based on social amplification leads to optimal group formation*. [全文](https://pmc.ncbi.nlm.nih.gov/articles/PMC1458659/), DOI: 10.1073/pnas.0507877103 | 聚集与有限资源的建模方向；非论文方程复现 |
| S3 | Lihoreau & Rivault (2011), *Local Enhancement Promotes Cockroach Feeding Aggregations*. [全文](https://journals.plos.org/plosone/article?id=10.1371/journal.pone.0022048), DOI: 10.1371/journal.pone.0022048 | 短距离社会信息；不能推出真实民宅气味场 |
| S4 | Hamilton et al. (2019), *Role of Cuticular Hydrocarbons in German Cockroach Aggregation Behavior*. [摘要](https://pubmed.ncbi.nlm.nih.gov/31034573/), DOI: 10.1093/ee/nvz044 | 不把通用社会作用代理命名为已确定的表皮烃信息素 |
| S5 | *Differences in Salmonella Typhimurium infection and excretion among laboratory and field strains of the German cockroach suggest a genomic basis for vector competence* (2024). [全文](https://pmc.ncbi.nlm.nih.gov/articles/PMC11365788/), [PubMed](https://pubmed.ncbi.nlm.nih.gov/38901621/) | 遗体摄食实测、品系差异；不把表型差异直接认定为已确定的遗传因果 |
| S6 | Tabaru, Mochizuki & Watabe (2003), *Coprophagy and necrophagy of the German cockroach, Blattella germanica, in the laboratory condition*. [原文入口](https://www.jstage.jst.go.jp/article/mez/54/1/54_KJ00000825661/_article/-char/en), DOI: 10.7601/mez.54.13 | 干燥遗体与普通饲料的选择及长期营养限制；本文依据摘要，不推断鲜尸参数 |
| S7 | Mond & Pietri (2023), *Horizontal transmission of Salmonella Typhimurium among German cockroaches and its possible mechanisms*. [全文](https://pmc.ncbi.nlm.nih.gov/articles/PMC10166671/), DOI: 10.1002/ece3.10070 | 同类之间的食尸传播途径；不外推人的接触感染率 |
| S8 | US EPA, [Asthma Triggers: Gain Control](https://www.epa.gov/asthma/asthma-triggers-gain-control) | 蟑螂排泄物／唾液／身体碎屑中的过敏原 |
| S9 | NYC Health, [Cockroaches: Environment & Health Data Portal](https://a816-dohbesp.nyc.gov/IndicatorPublic/data-explorer/cockroaches/?id=2393) | 居家食物污染与过敏原暴露 |
