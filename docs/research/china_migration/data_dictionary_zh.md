# 数据字典与规范对应 v0.1

所有引用编号对应[data/sources.json](data/sources.json)。文件采用UTF-8；JSONL每行一个对象。表格统计值保留源表精度，不补造置信区间。行政区划代码仅作为2020年省级查询键，不构成全历史政区数据库。

| 观测字段 | 定义 |
|---|---|
| record_id / series_id | 唯一记录键 / 同统计定义的系列键；不同系列不自动拼接 |
| year / year_basis | 统计年 / calendar、US_fiscal或survey_end_year；美国FY从上一年10月1日起 |
| count / unit | 公开表格数值 / persons、visas、respondents；样本数与总体数不同 |
| measure_type | stock、visa_issuance、sample_composition；不存在以签证替代LPR的隐式换算 |
| origin / destination | 来源或目的标签；须结合geography_basis读取 |
| geography_basis | 户籍对现住地、出生地、国籍、签证归属地、签发机构或抽样社区 |
| male / female | 七普省级边际表性别分项；总数须等于两项之和；不是遗传性别推断 |
| visa_class | 源表类别；F/H/J等为大类，未细分F-1、H-1B或主申请人/家属 |
| source_id / source_locator | 来源外键及精确行列或章节定位 |
| evidence_status / data_origin | extracted / public_aggregate；禁止悄悄混入参与者数据 |
| missing_reason | 本版已提取观测为null；尚缺统计单列检索缺口，不用0占位 |

历史事件使用历史地名、路线中间节点（文献确有记载者）、机制和宽时间包络。`reported_quantity_numeric`只为原文数量级或下界编码，不是现代确数；`modern_exact_count`固定null。历史“户”“家”“口”不互相换算。纪年采用负数表示公元前，不使用0年。`documented`意为来源支持事件存在，绝不表示其人口数、族属和后代谱系均已验证。`secondary_lead`和`contested_origin_claim`须单独筛选。

## 与 All of Us 的对应关系

| 官方原则或能力 | 本版落实 | 尚未做到 |
|---|---|---|
| 祖源结果依赖参考样本和分析版本 [AOU25] | 保存研究/面板名称、样本范围和分类来源 | 未下载受限参考基因组；未做参与者投影 |
| 祖源与种族、族群认同有区别 [AOU_FAQ] | 地理、语言/民系、遗传研究记录分层 | 尚无经同意采集的家族资料 |
| 受控个体数据在安全环境内分析 [AOU_POLICY] | 仓库限定public_aggregate，校验器拒绝其他来源标识 | 本仓不是获准Researcher Workbench |
| 1—20计数及可推导小单元保护 [AOU_POLICY] | 提供直接阈值拒绝；即使通过仍提示需要交叉发布审查 | 不宣称自动解决互补抑制、差分攻击或取得发布许可 |
| 标准化、可审计研究 | 本项目版本、来源键、定义、SHA-256与实际测试回执 | 没有All of Us官方“历史迁徙表”规范可照搬；本schema非官方OMOP扩展 |

## 后续受控研究建议字段（未收集）

`birth_place`、`parents_birth_places[]`、`grandparents_birth_places[]`、`residence_episodes[]`、`home_languages[]`、`self_identified_minxi[]`、`first_us_arrival_year`、`most_recent_us_arrival_year`、`data_collection_consent_version`、`genetic_reference_panel_version`、`genetic_coordinates`。

每个家族地理字段同时保存行政区划版本、原始回答、精度和缺失原因。祖籍、出生地、户籍、出发地、求学地与招募地分别记录；族谱文件及亲属身份不进入公开示例。允许不知道、拒答、多来源和迁徙后改认同；不会用现代省界替参与者填写民系或遗传比例。
