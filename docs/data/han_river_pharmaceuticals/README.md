# 汉江药物与激素调查：证据和复核记录

核查日期：2026-11-11（Asia/Shanghai）。[中文正文](../../han_river_hormones_pde5_ecology_zh.md) · [浓度表](concentrations.csv)

## 范围与方法

本次为有针对性的公开资料检索与原始文献核查，不是穷尽数据库的系统综述，未做现场采样、实验或作者访谈。研究区域限定韩国汉江及相关首尔支流；排除中国 Hanjiang、武汉汉江、日本河流及无法定位的“韩国水体”浓度。检索覆盖英文和韩文关键词，使用两个搜索引擎交叉查找，并回到期刊、PubMed、作者机构或官方页面。

关键检索式（代表性记录，并非逐次搜索完整导出）：

| 目标 | 检索式 | 处理结果 |
| --- | --- | --- |
| 药物浓度 | `Han River sildenafil estrogen androgen contraceptive aquatic ecological risk Korea study` | 定位 S2–S4 |
| 类固醇 | `Han River steroid hormones testosterone ethinylestradiol levonorgestrel ecological risk South Korea` | 核实 S3 历史未检出结果；合成孕激素当地实测仍缺 |
| 韩文补查 | `한강 여성호르몬 남성호르몬 피임약 농도 생태 2024 2025 2026` | 未取得能更新本稿目标化合物浓度的可靠当前数据集 |
| 当地生物效应 | `"Han River" "vitellogenin"`、`"Han River" estrogen androgen fish vitellogenin intersex` | 未取得目标物与当地种群损害直接关联的可核实材料 |
| 新近资料 | `"Han River" "ethinylestradiol" 2022 2023 2024 2025` | 找到 S8；实验设定浓度不纳入现场表 |
| 孕激素危害 | `"Effects of synthetic gestagens on fish reproduction" "0.8"` | 核实 S6，进一步核查 S7；均属非汉江实验 |
| PDE-5 生物效应 | `"sildenafil" "fertilisation" "ng"` | 定位 S9，保留海洋物种和配子暴露边界 |
| 原论文纠错 | `"Contribution of sewage to occurrence of phosphodiesterase-5 inhibitors" correction corrigendum` | 本次未取得能解释表 1 与摘要差异的更正；不等于证明从未有过更正 |
| 韩国程序 | `site.ccourt.go.kr impeachment president National Assembly Constitution Article 65` | 用官方说明校准开场隐喻 |

检索日不能代替采样日。本次没有取得 2026 年全流域同批次目标物监测数据；也不能据此宣称韩国政府没有监测，或世界上不存在更新研究。

## 来源访问与取舍

S 编号及正式书目信息见正文参考资料。

| 来源 | 本次实际核查层级 | 主要限制 |
| --- | --- | --- |
| S1 | 韩国宪法法院官方程序页面 | 仅用于程序纠正，不评价具体总统案件 |
| S2 | 期刊／PMC 可读内容；INL 机构保存完整期刊 PDF；逐项目视核对 Table 1 | 网站访问间歇失败，使用机构副本复核；未取得原始逐样本数据及完整补充数据 |
| S3 | 原始论文摘要、期刊索引片段、作者机构书目互核 | 未完整取得正文表格；只用摘要报告的 `<1 ng/L`，不捏造逐物质精确检出限、采样日期或站点值 |
| S4 | 原始论文摘要与期刊可读摘要 | 人口／水体模型结果，未独立重跑，不是新实测 |
| S5 | 原始论文摘要与 PMC 索引可读内容 | 外国整湖实验；仅作危害证据 |
| S6 | 原始论文全文，包括分析方法与结果 | 最低报告暴露浓度与方法 LOQ 存在需解释的关系；保留小样本限制 |
| S7 | 原始研究摘要及期刊结果片段 | 2021 在线、2022 卷期；NOEC 按相关终点理解 |
| S8 | PMC 全文方法 | 河水是实验基质；不将加药实验浓度当作自然河水浓度 |
| S9 | 作者所在大学存储库的原始研究摘要 | 海洋配子实验，不能直接外推当地淡水生态 |
| S10 | 原始论文摘要 | 多地点、多工艺研究；未把汇总浓度拆成汉江特定点位 |

二手综述中出现的汉江睾酮具体数值，未能由本次取得的 S3 原始摘要支持，因此不纳入。S3 的 `<1` 与其他来源的更细阈值不擅自融合。搜索结果中来自别篇文章的引用、推荐文献摘要和正文内容严格分开。

## CSV 数据字典

本表是文献汇总证据表，不是原始样本数据，也不可把其中每行当作独立采样重复。

| 字段 | 含义 |
| --- | --- |
| `record_id` | 本稿唯一记录编号 |
| `source_id` | 正文参考资料编号；缺口行标记 `SEARCH_GAP` |
| `publication_year` | 发表年份，不是采样年份 |
| `sampling_period` / `sampling_year` | 原文核查到的期间；年份不明则空白 |
| `site` / `matrix` | 位置与介质，区分干流、支流、进水、出水 |
| `analyte` | 化合物名称；不把商品名当化学分类 |
| `evidence_type` | `measured_summary`、`reported_nondetect`、`modeled_range_of_means`、`not_retrieved` |
| `qualifier` | `mean`、`less_than`、`range_of_means`、`not_available` |
| `value_ng_L` | 原文报告的均值；不用于填写未检出或缺口 |
| `reported_plus_minus_ng_L` | S2 原表 ± 后数值；不自行指定为 SD 或 SE |
| `uncertainty_type` | `not_defined_in_table_caption` 或空白 |
| `lower_ng_L` / `upper_ng_L` | S4 四厂模型均值范围；不是样本最小／最大值 |
| `reporting_bound_ng_L` | S3 摘要未检出上界 1；不是实测值或逐物质确定的 LOQ |
| `source_url` / `locator` | 原始文献定位 |
| `notes` | 时效性、方法及解释限制 |

空白表示未报告或不适用，不能替换为零。全部浓度字段单位均为 ng/L；不包含药片剂量、组织浓度、国外实验暴露浓度或 S8 的人为加药值。

## 已复核的算术与未解决事项

1. S2 Table 1 五个干流点的三种药物均值相加，依次为 4、7、6、9、6 ng/L。这是本稿对已四舍五入表值的算术核对，不是重新分析原始样本。HR-4 的 9 与正文／摘要 `<7` 表述不一致。没有协方差和原始数据，不计算总和的 ± 值或显著性。
2. 表注未定义 Table 1 的 ± 类型。即使文章别处给图中误差条下了定义，也不自动推广到所有表格。
3. S2 采样方法中有 4 月 21–27 日及 6 月，所核查段落未注明年份；CSV 年份留空。研究在无雨条件下的观察也不能覆盖暴雨溢流情景。
4. S4 为模型估计；S3 为历史实测未检出。不同研究不能串成一条实测时间趋势。
5. S6 将 0.8 ng/L 用作实测暴露水平，同时列出 1.5 ng/L 的方法 LOQ；本稿标明待澄清，未擅自更改任一值。
6. 未取得左炔诺孕酮、屈螺酮的可核实汉江现场值。缺口行只帮助防止被误读为零，不声称这两项曾在某次采样中被分析。

## 本次交付验证

文档与数据使用一致的来源编号；CSV 保留未检出与模型标签；核对相对链接、记录唯一性、数值字段和 HR-4 算术。没有新增模型、现场实验或软件功能，不以软件 CI 代替生态证据。

正文中的监测点位扩展、时间频率、LC-MS/MS 与受体活性联测、治理比较及方法定量目标，均是本稿建议。尚未联系作者、政府、污水厂或实验室，也未代用户发送问询。
