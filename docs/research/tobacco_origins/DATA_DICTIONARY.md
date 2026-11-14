# 数据字典与复核

## 文件

| 文件 | 含义 |
|---|---|
| global_production_fao_owid.csv | 下载原件，1961–2024，数量单位吨；保留所有实体和汇总；不要把全表加总当世界总量 |
| global_production_fao_owid.metadata.json | 同次下载配套元数据，含更新时间、数据字段与原始来源 |
| countries.json | 全部三位代码国家／地区，加单列历史实体；最近观测、最近正值、2024正值分开 |
| excluded_aggregates.json | 不计作产地的世界、洲、经济组别等；原始CSV仍保留 |
| origins.json | 次国家、地名品牌、加工／收购、研究采样等角色记录；证据和状态逐条保留 |
| literature.json | 原始研究、材料／途径、产区、结果、限制、利益关系和访问深度 |
| traditional_texts.json | 本草书目线索；原版、页码未取得时为null |
| sources.json | 全局来源主键、URL、来源类别、访问深度、检索日期 |
| coverage.json | 机器生成计数；全覆盖状态明确为false |
| search_log.json | 代表性实际检索词、数据下载来源及失败记录 |
| batch_passport_template.json | 字段草案；没有填入虚构的真实产品或合规认证 |

## 字段语义

`source_ids`关联sources主键；`role`用于防止把制造城市／收购点当烟田；`documented`只表示来源明确列出，不代表已做独立认证。`leaf_origin_unverified`明确不具种植来源证据。

统计`country_or_area`沿用数据编码规则而非主权判定；`latest_positive_year`为空只说明下载序列内无正值。2024零值与无2024记录可通过原CSV区分；最新年份不足2024的记录不能视作2024生产为零。

## 下载与授权归属

FAO (2025), Production: Crops and livestock products，经Our World in Data加工：Tobacco production – UN FAO。[数据说明](https://ourworldindata.org/grapher/tobacco-production)。本次下载于2026-11-14；文件列元数据最后更新2026-02-25。FAO来源采用其统计数据使用条件，OWID加工采用其CC BY归属；不得删除原始机构署名。第三方来源许可与本仓代码许可分别适用。

实际下载URL：

- https://ourworldindata.org/grapher/tobacco-production.csv?useColumnShortNames=true
- https://ourworldindata.org/grapher/tobacco-production.metadata.json?useColumnShortNames=true

原始CSV未编辑，字节SHA-256记录于manifest。元数据中的`dateDownloaded`按供应端返回值保留。未保存FAO原始逐行估计标记，因此不应声称每个数字都是官方实测。

## 本地复核范围

使用Python标准库解析全部JSON／CSV、复算覆盖计数、核对来源外键、重复ID、论文标识、Markdown相对链接以及清单SHA-256。结果见validation.json。没有运行项目推理测试，没有声称CI通过，没有确认每个外链当前均可访问；部分出版站和官方下载端曾拒绝请求。
