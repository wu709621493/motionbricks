# 早熟作物 × 根系、根际与共生固氮

> 归档版本：v0.1。归档日期：2026-11-15。
> 以下正文由已确认的 HTML 报告转换，保留原文结论、字段和来源。归档不代表已实施田间验证。

## 文件入口

| 文件 | 内容 |
| --- | --- |
| [原始资料包](Crop_Root_Rhizosphere_Review_v01.zip) | 原始压缩包完整字节，SHA-256 见清单 |
| [HTML 原报告](review_zh.html) | 下载后在浏览器离线阅读 |
| [字段字典](field_dictionary.json) | 117 个字段、单位、适用范围、来源和缺失规则 |
| [文献评议](literature_review.json) | 14 项研究/方法资料及其证据边界 |
| [观测空模板](observation_template.json) | 空 records，未生成实验观测 |
| [候选证据](candidate_evidence.json) | 四种作物的品种生育期资料比较 |
| [归档清单](manifest.json) | SHA-256、Git blob SHA、基准提交和本地核验范围 |

v0.1 · 2026-11-15 · 117 个字段 · 14 项文献/方法资料

研究目标：筛选暖区多季收获体系中、成熟期有约10–15天差距的材料，同时审视根系建立、根际菌群、共生固氮及最终产量品质能否协调。本报告将此前讨论转为可复用的数据字典和证据综述，没有新增田间测量。

**术语：**rhizome＝根茎；root system＝根系；rhizosphere＝根际；rhizobia＝根瘤菌。普通栽培水稻与玉米不具豆科式根瘤，根瘤字段记“不适用”；不排除非结瘤的关联或内生固氮，但须独立测量。

检索范围：根长测定、豆科信号与固氮方法、根构型功能、根际区室与时间序列；纳入经典原始研究、官方方法专著及少量明确标记的背景综合。属于有针对性的叙述性复核，不是穷尽检索或系统综述。对访问受限文献只采用可核对摘要支持的结论，不声称完成全文精读。

## 候选材料证据

| 作物 | 原资料比较 | 差值（天） | 证据边界 |
| --- | --- | --- | --- |
| 绿豆 | [IPM 02-3 65–70天 vs Virat约55天](https://www.icar-iipr.org.in/varieties/) | [10, 15] | 品种资料比较，非同地随机对照；尚无这对材料的地下性状配套数据 |
| 水稻 | [IR64 115–120天 vs IR50夏季105天](https://agritech.tnau.ac.in/agriculture/agri_cereals_rice4.html) | [10, 15] | IR50冬季可达130天；不可忽略季节或育秧起点 |
| 大豆 | [JS97-52约100天 vs JS20-34 86–88天](https://icar-nsri.res.in/aicrps_var.html) | [12, 14] | 相同区域品种资料，非本地同试验；光周期和菌株适配待测 |
| 籽粒玉米 | [CO1 105–110天 vs COH(M)4代表值94天](https://agritech.tnau.ac.in/agriculture/millets_maize_morphological_description.html) | [11, 16] | 接近目标的候补；不能用鲜食、青贮收获时间替代籽粒成熟 |

年收获两三季必须按同一地块的实际温光、育秧、换茬与收获终点验证。跨地南繁加代不等于同地年三熟；轮作三熟不等于同一作物连种三季。以上海外品种只提供早熟空间证据，未完成华南引种验证。

## 文献综合判断

1. 根长、根深、角度、根干重描述不同属性，不能由单一“根发达”概括。线交法和扫描法需说明洗根损失、取样土体与分辨率。[R01–R02]
2. RTCS与DRO1提供根发生和根角度的功能证据，没有证明成熟可提前10–15天。[R08–R09]
3. 共生建立存在宿主信号与菌株适配；nod基因诱导、结瘤、固氮速率、累计固定氮和增产是不同证据层。[R03–R04、R10]
4. 根际、根表、根内应分样；同日龄与同阶段分别比较。菌群差异可能伴随发育转换，不能直接断言其导致早熟。[R05–R07]
5. 大豆固氮时间轨迹不是统一日历；绿豆的14–25天起始范围是特定栽培资料，不能拿来填充各候选品种缺失值。[R13–R14]
6. 固氮有碳代价并受环境制约；更短生长季可能改变氮积累，但方向和幅度需要测量。豆科身份本身不能证明收后土壤净增氮。[R10–R11]

## 建议的验证设计（尚未执行）

以品种/早熟处理×土壤或水分条件为主要因素，使用独立田间小区和随机区组；豆科若比较接种效果，增设同背景接种与未接种对照。原有土壤根瘤菌仍可能使未接种组结瘤，故不能称其为“无菌”或“无固氮”。先做预试验确定方差，再按预设的产量、蛋白和种子质量容许差确定重复数。

采样同时设固定播种后日龄序列和匹配物候阶段序列；豆科至少覆盖结瘤建立、开花、结荚、鼓粒与成熟，其他作物按其物候对应。破坏性根样来自预留植株，不能把同小区植株当成独立田间重复。比较地下性状时纳入土层、日内时刻、土壤氮与水分；微生物提取/测序批次跨处理随机分配。

主要终点为播种至生理成熟天数、田块占用时间、校正含水率后的产量与品质；地下性状为机制终点。预先定义10–15天目标及产量品质不劣界值，报告效应量与区间。探索性多组学关联需控制多重检验；缺失数据和检出限单独标记。

## 数据记录规则

**scope：**四种作物的早熟候选与地下生物学补充；非系统综述，非本地品种推荐，未开展新试验。

**status_enum：**measured, literature_reported, derived, planned, not_measured, not_applicable, not_reported, below_detection

**missing_rule：**缺失值用null并附status；不得用0表示未测或不适用；检出限以下保留LOD。

**observation_unit：**一条观测对应一个样本、时间、区室/土层和field_id；技术重复嵌套于生物重复。

**comparison_rule：**同日龄与同发育阶段分别分析；环境×品种×季节的影响不能由品种标称成熟天数消除。

**inference_rule：**文献品种间差值不是同一品种加速干预的因果证据；根瘤数、nifH和菌群相关性均非固氮通量替代。

**noninferiority_rule：**成熟提前10–15天与产量/品质保持需分别检验；不劣界值、功效及独立小区数须在试验前确定。

15N自然丰度法常用形式：Ndfa=(δ15N参照−δ15N豆科)/(δ15N参照−B)。参照、B值和样品组织的适配必须说明，分母接近零时不应强行计算。累计固定氮估算只覆盖所测组织及对应时段，不能自动称为包括根际沉积与全部地下部的全系统固定氮。[R10]

## 完整字段字典

### 身份与试验设计

| 字段ID／名称 | 类型／单位 | 定义与记录口径 | 适用与依据 |
| --- | --- | --- | --- |
| study_id<br>研究编号 | string / — | 跨表连接键 | 全部<br> |
| site_id<br>地点编号 | string / — | 记录经纬度、海拔和场地类型的外部表键 | 全部<br> |
| latitude_deg<br>纬度 | number / degree | 北纬为正 | 全部<br> |
| longitude_deg<br>经度 | number / degree | 东经为正 | 全部<br> |
| season_year<br>年份 | integer / year | 试验年份 | 全部<br> |
| season_label<br>季别 | string / — | 春夏秋冬或当地农季 | 全部<br> |
| crop_species<br>作物学名 | string / — | 固定学名；不把不同用途材料混为同一终点 | 全部<br> |
| cultivar<br>品种 | string / — | 完整编号与种源 | 全部<br> |
| seed_lot<br>种子批次 | string / — | 种源和批次可追溯 | 全部<br> |
| genotype_markers<br>相关基因型 | object / — | 注明基因组版本、位点及分型证据；未知为null | 全部<br> |
| reference_assembly<br>参考基因组版本 | string / — | 组装编号/注释版本；不以物种名代替版本 | 全部<br> |
| treatment_id<br>处理编号 | string / — | 早熟材料或处理及对照定义 | 全部<br> |
| plot_id<br>小区编号 | string / — | 田间实验单位 | 全部<br> |
| block_id<br>区组编号 | string / — | 随机区组或其他设计 | 全部<br> |
| plant_id<br>植株编号 | string / — | 植株嵌套于小区；不作为独立田间重复 | 全部<br> |
| sample_id<br>样本编号 | string / — | 每次破坏性取样单独编号 | 全部<br> |
| previous_crop<br>前茬 | string / — | 作物及残体处置 | 全部<br> |
| cropping_history<br>种植历史 | string / — | 近年豆科、接种和病害记录 | 全部<br> |
| harvest_use<br>收获用途 | string / — | 干籽粒/鲜食/青贮分开 | 全部<br> |
| randomization<br>随机化方法 | string / — | 说明分配及空间阻断 | 全部<br> |
| biological_replicate_n<br>独立生物重复数 | integer / count | 单位必须是独立小区或独立盆 | 全部<br> |
| technical_replicate_n<br>技术重复数 | integer / count | 不能替代生物重复 | 全部<br> |
| destructive_sampling<br>破坏性取样 | boolean / — | 标记重复取样是否来自不同植株 | 全部<br> |
| protocol_version<br>方法版本 | string / — | 方法文件与版本可追溯 | 全部<br> |

### 物候与时间

| 字段ID／名称 | 类型／单位 | 定义与记录口径 | 适用与依据 |
| --- | --- | --- | --- |
| sowing_date<br>播种日 | string / ISO8601 date | 稻作包含育秧起点 | 全部<br>R07, R12 |
| emergence_date<br>出苗日 | string / ISO8601 date | 注明出苗比例阈值 | 全部<br>R07, R12 |
| transplant_date<br>移栽日 | string / ISO8601 date | 直播为not_applicable | 全部<br>R07, R12 |
| sample_datetime<br>采样时间 | string / ISO8601 datetime | 含时区及日内采样时间 | 全部<br>R07, R12 |
| days_after_sowing<br>播种后天数 | number / d | 采样日减播种日 | 全部<br>R07, R12 |
| days_after_transplant<br>移栽后天数 | number / d | 直播为not_applicable；不得替代全生育期 | 全部<br>R07, R12 |
| growth_stage<br>发育阶段 | string / — | 注明BBCH或作物专用阶段体系 | 全部<br>R07, R12 |
| stage_definition<br>阶段定义 | string / — | 大豆R1/R5/R7/R8等；稻抽穗比例阈值 | 全部<br>R07, R12 |
| first_flower_date<br>初花日 | string / ISO8601 date | 注明判定标准 | 全部<br>R07, R12 |
| heading_silking_date<br>抽穗或吐丝日 | string / ISO8601 date | 作物特定终点；附比例阈值 | 全部<br>R07, R12 |
| physiological_maturity_date<br>生理成熟日 | string / ISO8601 date | 与适宜收获日分开 | 全部<br>R07, R12 |
| final_harvest_date<br>末次收获日 | string / ISO8601 date | 绿豆多次收获需记录末次清田 | 全部<br>R07, R12 |
| field_occupancy_days<br>田块占用天数 | number / d | 大田播种/移栽至清田；说明育秧占地另计 | 全部<br>R07, R12 |
| turnaround_days<br>换茬间隔 | number / d | 前茬清田至后茬播种或移栽 | 全部<br>R07, R12 |
| growing_degree_days<br>有效积温 | number / degree_C_d | 必须连同基温、上限和计算法 | 全部<br>R07, R12 |
| gdd_model<br>积温算法 | object / — | 基温、上限、逐日或逐小时算法 | 全部<br>R07, R12 |
| photoperiod_h<br>光周期 | number / h_d-1 | 测得或由纬度日期计算，注明方法 | 全部<br>R07, R12 |

### 根系构型

| 字段ID／名称 | 类型／单位 | 定义与记录口径 | 适用与依据 |
| --- | --- | --- | --- |
| soil_depth_top_cm<br>土层上界 | number / cm | 地表为0 | 全部<br>R01, R02, R08, R09 |
| soil_depth_bottom_cm<br>土层下界 | number / cm | 须大于上界 | 全部<br>R01, R02, R08, R09 |
| soil_core_volume_cm3<br>取土体积 | number / cm3 | 用于根长密度的分母 | 全部<br>R01, R02, R08, R09 |
| root_type<br>根类型 | string / — | 主根/种子根/冠根/支撑根/侧根；按作物定义 | 全部<br>R01, R02, R08, R09 |
| total_root_length_cm<br>样本总根长 | number / cm | 注明洗根筛孔、扫描或线交法 | 全部<br>R01, R02, R08, R09 |
| root_length_density<br>根长密度 | number / cm_cm-3 | 根长除以对应原位土体积 | 全部<br>R01, R02, R08, R09 |
| root_dry_mass_g<br>根干重 | number / g | 记录取样范围、烘干温度及恒重标准 | 全部<br>R01, R02, R08, R09 |
| shoot_dry_mass_g<br>地上部干重 | number / g | 与根样同单位和同采样时间 | 全部<br>R01, R02, R08, R09 |
| root_shoot_ratio<br>根冠比 | number / g_g-1 | 根干重/地上部干重；不混用鲜重 | 全部<br>R01, R02, R08, R09 |
| root_angle_deg<br>根角度 | number / degree | 必须声明相对水平面还是垂直方向 | 全部<br>R01, R02, R08, R09 |
| root_diameter_mm<br>根直径 | number / mm | 按直径级统计；保留算法 | 全部<br>R01, R02, R08, R09 |
| specific_root_length<br>比根长 | number / m_g-1 | 根长/根干重；同一子样 | 全部<br>R01, R02, R08, R09 |
| rooting_depth_cm<br>观测根深 | number / cm | 观测最大深度受采样深度限制 | 全部<br>R01, R02, R08, R09 |
| root_measurement_method<br>根测量方法 | string / — | 设备、软件、分辨率、阈值、洗根流程 | 全部<br>R01, R02, R08, R09 |

### 豆科结瘤

| 字段ID／名称 | 类型／单位 | 定义与记录口径 | 适用与依据 |
| --- | --- | --- | --- |
| inoculation_status<br>接种状态 | string / — | 接种/未接种/本底菌存在/未知 | 绿豆、大豆；水稻和玉米普通栽培条件下设not_applicable，不填0<br>R04, R10, R13, R14 |
| rhizobial_strain_id<br>根瘤菌株 | string / — | 保藏编号与鉴定依据；不由宿主推断菌种 | 绿豆、大豆；水稻和玉米普通栽培条件下设not_applicable，不填0<br>R04, R10, R13, R14 |
| inoculation_method<br>接种方法 | string / — | 载体、时点、剂量和活菌计数依据 | 绿豆、大豆；水稻和玉米普通栽培条件下设not_applicable，不填0<br>R04, R10, R13, R14 |
| nodule_number_per_plant<br>每株根瘤数 | number / count_plant-1 | 记录是否完整挖根 | 绿豆、大豆；水稻和玉米普通栽培条件下设not_applicable，不填0<br>R04, R10, R13, R14 |
| nodule_dry_mass_g<br>每株根瘤干重 | number / g_plant-1 | 与根干重分开，注明是否包含根瘤 | 绿豆、大豆；水稻和玉米普通栽培条件下设not_applicable，不填0<br>R04, R10, R13, R14 |
| nodule_location<br>结瘤位置 | string / — | 主根/侧根/根颈附近及深度 | 绿豆、大豆；水稻和玉米普通栽培条件下设not_applicable，不填0<br>R04, R10, R13, R14 |
| nodule_internal_colour<br>根瘤内部颜色 | string / — | 粉红等仅作辅助表型，不代替固氮测量 | 绿豆、大豆；水稻和玉米普通栽培条件下设not_applicable，不填0<br>R04, R10, R13, R14 |
| first_nodulation_das<br>首次观察结瘤日龄 | number / d | 属于区间受限观测，注明巡查间隔 | 绿豆、大豆；水稻和玉米普通栽培条件下设not_applicable，不填0<br>R04, R10, R13, R14 |
| first_fixation_das<br>首次检出固氮日龄 | number / d | 必须有方法和检出限 | 绿豆、大豆；水稻和玉米普通栽培条件下设not_applicable，不填0<br>R04, R10, R13, R14 |
| nodule_occupancy<br>接种菌占瘤比例 | number / fraction | 菌株分型结果；不由接种与否推断 | 绿豆、大豆；水稻和玉米普通栽培条件下设not_applicable，不填0<br>R04, R10, R13, R14 |

### 固氮与植株氮

| 字段ID／名称 | 类型／单位 | 定义与记录口径 | 适用与依据 |
| --- | --- | --- | --- |
| fixation_method<br>固氮测定法 | string / — | ARA/15N自然丰度/同位素稀释/直接15N2/尿囊素等 | 全部<br>R03, R10, R14 |
| ara_rate<br>乙炔还原速率 | number / nmol_C2H4_plant-1_h-1 | 记录孵育时间、温度、气体比例与归一化分母 | 全部<br>R03, R10, R14 |
| ara_conditions<br>ARA条件 | object / — | 密闭系统、空白、漏气、仪器校准；不固定通用转化系数 | 全部<br>R03, R10, R14 |
| ndfa_fraction<br>氮来自空气比例 | number / fraction | 仅经相应方法估计；0到1 | 全部<br>R03, R10, R14 |
| reference_plant_id<br>参照植物编号 | string / — | 同位素方法非固氮参照及匹配依据 | 全部<br>R03, R10, R14 |
| delta15n_sample_permil<br>样品δ15N | number / permil | 注明标准 | 全部<br>R03, R10, R14 |
| delta15n_reference_permil<br>参照δ15N | number / permil | 同环境非固氮参照 | 全部<br>R03, R10, R14 |
| b_value_permil<br>B值 | number / permil | 对应宿主/菌株/组织及来源，不擅用通用常数 | 全部<br>R03, R10, R14 |
| plant_n_concentration<br>植株氮质量分数 | number / fraction | 干物质基础；注明组织 | 全部<br>R03, R10, R14 |
| plant_n_kg_ha<br>植株氮积累 | number / kg_N_ha-1 | 干物质量×氮质量分数；面积换算需依据 | 全部<br>R03, R10, R14 |
| fixed_n_kg_ha<br>累计固定氮 | number / kg_N_ha-1 | 适用时由Ndfa×对应氮积累估算；注明组织覆盖与采样时点 | 全部<br>R03, R10, R14 |
| ureide_fraction<br>尿囊素相关指标 | number / fraction | 限定经验证宿主与组织；记录公式与校准 | 全部<br>R03, R10, R14 |

### 土壤与根际环境

| 字段ID／名称 | 类型／单位 | 定义与记录口径 | 适用与依据 |
| --- | --- | --- | --- |
| soil_type<br>土壤类型 | string / — | 分类体系和质地 | 全部<br>R06, R10 |
| soil_temperature_c<br>土温 | number / degree_C | 记录深度与传感器 | 全部<br>R06, R10 |
| soil_water_content<br>土壤含水率 | number / fraction | 标明体积或质量基础 | 全部<br>R06, R10 |
| soil_moisture_basis<br>含水率基础 | string / — | volumetric或gravimetric | 全部<br>R06, R10 |
| soil_ph<br>土壤pH | number / — | 记录水或盐浸提及土液比 | 全部<br>R06, R10 |
| nitrate_n_mg_kg<br>硝态氮 | number / mg_N_kg-1_dry_soil | 以N计；记录浸提法 | 全部<br>R06, R10 |
| ammonium_n_mg_kg<br>铵态氮 | number / mg_N_kg-1_dry_soil | 以N计；记录浸提法 | 全部<br>R06, R10 |
| available_p_mg_kg<br>有效磷 | number / mg_P_kg-1_dry_soil | Olsen/Bray等方法不可直接混用 | 全部<br>R06, R10 |
| bulk_density_g_cm3<br>土壤容重 | number / g_cm-3 | 土层氮储量换算需要 | 全部<br>R06, R10 |
| fertilizer_n_kg_ha<br>施氮量 | number / kg_N_ha-1 | 分次施用时保留日期与形态 | 全部<br>R06, R10 |
| irrigation_log<br>灌溉记录 | array / — | 记录日期、水量及排水 | 全部<br>R06, R10 |
| water_regime<br>水分管理 | string / — | 淹水/间歇灌溉/旱作；水稻尤需记录 | 全部<br>R06, R10 |
| postharvest_soil_n<br>收后土壤氮 | number / mg_N_kg-1_dry_soil | 标明总氮或矿质氮、土层、方法，不混为单一指标 | 全部<br>R06, R10 |

### 根际微生物

| 字段ID／名称 | 类型／单位 | 定义与记录口径 | 适用与依据 |
| --- | --- | --- | --- |
| compartment<br>样本区室 | string / — | bulk_soil/rhizosphere/rhizoplane/endosphere；根瘤另列 | 全部<br>R05, R06, R07 |
| compartment_protocol<br>区室分离方法 | string / — | 抖土、洗涤、超声及表面处理均需记录 | 全部<br>R05, R06, R07 |
| storage_protocol<br>保存方法 | string / — | 采后延迟、温度、冻融次数 | 全部<br>R05, R06, R07 |
| extraction_batch<br>提取批次 | string / — | 与处理组随机化 | 全部<br>R05, R06, R07 |
| extraction_blank_id<br>提取空白 | string / — | 防止低生物量污染误判 | 全部<br>R05, R06, R07 |
| pcr_negative_id<br>PCR阴性对照 | string / — | 样本或批次连接键 | 全部<br>R05, R06, R07 |
| positive_control_id<br>阳性/模拟群落对照 | string / — | 采用时记录，不冒充必有 | 全部<br>R05, R06, R07 |
| sequencing_assay<br>测序类型 | string / — | 16S/ITS/shotgun等；16S不涵盖全部真菌 | 全部<br>R05, R06, R07 |
| primer_region<br>引物与区域 | string / — | 序列或明确文献链接 | 全部<br>R05, R06, R07 |
| raw_data_accession<br>原始数据编号 | string / — | SRA/ENA等；未知null | 全部<br>R05, R06, R07 |
| pipeline_version<br>分析流程版本 | string / — | 过滤、去污染、分类数据库及版本 | 全部<br>R05, R06, R07 |
| microbial_feature_table<br>菌群特征表路径 | string / — | ASV/OTU/基因；不得将相对丰度当绝对数量 | 全部<br>R05, R06, R07 |
| absolute_load_method<br>绝对负荷方法 | string / — | qPCR/spike-in等，仅在实际测定时填写 | 全部<br>R05, R06, R07 |
| functional_evidence<br>功能证据 | string / — | nifH存在/表达/酶活/直接同位素通量分级，不等价 | 全部<br>R05, R06, R07 |

### 收获与氮收支

| 字段ID／名称 | 类型／单位 | 定义与记录口径 | 适用与依据 |
| --- | --- | --- | --- |
| grain_yield_kg_ha<br>籽粒产量 | number / kg_ha-1 | 记录收获面积、损失及水分校正 | 全部<br>R10, R11 |
| grain_moisture_fraction<br>籽粒含水率 | number / fraction | 声明湿基 | 全部<br>R10, R11 |
| standard_moisture_fraction<br>标准含水率 | number / fraction | 不同作物标准另定，不跨口径比较 | 全部<br>R10, R11 |
| grain_protein_fraction<br>籽粒蛋白质量分数 | number / fraction | 注明干湿基、总氮换算系数或直接测法 | 全部<br>R10, R11 |
| thousand_seed_mass_g<br>千粒重 | number / g | 注明含水率 | 全部<br>R10, R11 |
| seed_germination_fraction<br>种子发芽率 | number / fraction | 若作为种用材料，按规定方法测定 | 全部<br>R10, R11 |
| residue_management<br>残体去向 | string / — | 还田/移除/饲用及数量 | 全部<br>R10, R11 |
| residue_n_kg_ha<br>残体氮 | number / kg_N_ha-1 | 是否包括地下残体须说明 | 全部<br>R10, R11 |
| grain_n_export_kg_ha<br>籽粒带走氮 | number / kg_N_ha-1 | 对应产量和氮浓度的质量基础一致 | 全部<br>R10, R11 |
| n_budget_boundary<br>氮收支边界 | string / — | 土层、组织、季节、气体和淋失是否覆盖 | 全部<br>R10, R11 |
| n_budget_kg_ha<br>氮收支 | number / kg_N_ha-1 | 注明输入输出公式；未测项不默认为零 | 全部<br>R10, R11 |
| annual_system_yield<br>全年体系产量 | number / kg_ha-1_year-1 | 跨作物相加仅限明示物质量；营养/经济产出另定义 | 全部<br>R10, R11 |
| annual_harvest_count<br>年内收获季数 | integer / count | 同地块、同一年；区分同种连作与轮作三熟 | 全部<br>R10, R11 |

## 逐篇文献评议

### R01 · Newman, 1966

[A method of estimating the total length of root in a sample](https://knowledgecenter.cimmyt.org/bib/19581)

方法原始论文｜多种根样

**支持：**根长测定的线交法基础，适合低设备成本的定量参照。

**边界：**洗根损失、根重叠及取向影响估计；不代表根深或吸收功能。

核验范围：书目及机构摘要核对

### R02 · Tennant, 1975

[A Test of a Modified Line Intersect Method of Estimating Root Length](https://www.jstor.org/stable/2258617)

方法原始论文｜小麦根样

**支持：**对改良线交法进行测试，为根长测定提供经典方法依据。

**边界：**不能将小麦方法的性能直接当作四种作物的本地验证。

核验范围：书目及摘要核对；全文访问受限

### R03 · Hardy et al., 1968

[The Acetylene-Ethylene Assay for N2 Fixation: Laboratory and Field Evaluation](https://doi.org/10.1104/pp.43.8.1185)

方法与实验｜固氮微生物、豆科等

**支持：**乙炔还原法用于检测固氮酶活性。

**边界：**短时活性不能未经校准直接换算整个生长季固定氮；记录条件和归一化分母。

核验范围：出版社/原论文索引摘要核对；全文访问受限

### R04 · Kosslak et al., 1987

[Induction of Bradyrhizobium japonicum common nod genes by isoflavones isolated from Glycine max](https://doi.org/10.1073/pnas.84.21.7428)

分子机制实验｜大豆与根瘤菌

**支持：**大豆异黄酮信号可诱导所研究菌株的nod基因表达。

**边界：**信号诱导不等于有效结瘤、净固氮或增产；不能直接外推绿豆。

核验范围：原论文索引摘要核对

### R05 · Lundberg et al., 2012

[Defining the core Arabidopsis thaliana root microbiome](https://doi.org/10.1038/nature11237)

微生物组原始研究｜拟南芥

**支持：**分开根际与根内区室，考察土壤和宿主因素。

**边界：**拟南芥是方法学参照，不能提供四种作物的通用菌群名单。

核验范围：原论文索引摘要核对；全文访问受限

### R06 · Edwards et al., 2015

[Structure, variation, and assembly of the root-associated microbiomes of rice](https://doi.org/10.1073/pnas.1414592112)

温室与多地点田间研究｜水稻

**支持：**区分根际、根表和根内；土壤、地点、宿主与栽培管理均影响菌群。

**边界：**共丰度网络和相对丰度不能单独证明互作因果或固氮通量。

核验范围：出版社全文已访问，核对区室方法及结果

### R07 · Edwards et al., 2018

[Compositional shifts in root-associated bacterial and archaeal microbiota track the plant life cycle in field-grown rice](https://doi.org/10.1371/journal.pbio.2003862)

跨季节/地点时间序列｜水稻

**支持：**菌群变化同时关联日龄与发育转换；支持同日龄和同阶段两种比较。

**边界：**不能由相关性推导菌群造成早熟；研究材料的时间点不构成普遍阈值。

核验范围：出版社全文已访问，核对摘要、方法与结果

### R08 · Taramino et al., 2007

[The maize (Zea mays L.) RTCS gene encodes a LOB domain protein that is a key regulator of embryonic seminal and post-embryonic shoot-borne root initiation](https://doi.org/10.1111/j.1365-313X.2007.03075.x)

突变体与基因克隆｜玉米

**支持：**RTCS参与种子根和茎生根发生；不同根类型需分别记录。

**边界：**证明根发生功能，不证明缩短生育期或在正常田间增产。

核验范围：出版社全文已访问，核对突变体、基因及根表型

### R09 · Uga et al., 2013

[Control of root system architecture by DEEPER ROOTING 1 increases rice yield under drought conditions](https://doi.org/10.1038/ng.2725)

遗传导入与干旱试验｜水稻

**支持：**DRO1调节根构型，深根有助于研究条件下的干旱避让与产量保持。

**边界：**深根收益依赖土壤与水分；不构成早熟10–15天的证据。

核验范围：出版社/原论文索引摘要核对；全文访问受限

### R10 · Unkovich et al., 2008, ACIAR MN136

[Measuring plant-associated nitrogen fixation in agricultural systems](https://www.aciar.gov.au/publication/books-and-manuals/measuring-plant-associated-nitrogen-fixation-agricultural-systems)

官方方法学专著｜农业固氮系统

**支持：**固氮方法选择、参照植物及同位素估计的经典手册。

**边界：**各方法假设不同，N差值、尿囊素、15N等估计不得混用；不能代替本地校准。

核验范围：官方书目及全文PDF已访问；本次为针对性方法复核

### R11 · Salvagiotti et al., 2008

[Nitrogen uptake, fixation and response to fertilizer N in soybeans: A review](https://doi.org/10.1016/j.fcr.2008.03.001)

文献综合（背景）｜大豆

**支持：**汇总氮吸收、固氮和施氮响应；说明氮来源与产量关系需综合评价。

**边界：**综合均值不能填入本项目品种实测值；不是新的田间对照。

核验范围：出版社摘要核对；作为背景综合，不充当原始试验

### R12 · Ha et al., 2021

[A near-complete genome sequence of mungbean (Vigna radiata L.) provides key insights into the modern breeding program](https://doi.org/10.1002/tpg2.20121)

基因组与QTL研究｜绿豆

**支持：**成熟同步性及相关候选基因，为地上物候与地下生理的联动分析提供背景。

**边界：**候选基因关联不等于根瘤因果，更没有证明本项目能减10–15天。

核验范围：全文已在本次对话前一轮访问

### R13 · GRDC GrowNotes, December 2014

[Mungbeans — Northern region](https://grdc.com.au/__data/assets/pdf_file/0034/238975/grdc-grownotes-mungbeans-northern.pdf.pdf)

官方栽培技术资料｜绿豆

**支持：**资料记载固氮可在播种后约14–25天开始；短季作物依赖及时结瘤。

**边界：**澳大利亚资料；不是Virat或中国地块的通用固氮起始日。

核验范围：官方PDF已访问；日期按文档封面而非搜索引擎抓取时间

### R14 · Temporal biological nitrogen fixation pattern in soybean inoculated with Bradyrhizobium, 2020

[Temporal biological nitrogen fixation pattern in soybean inoculated with Bradyrhizobium](https://doi.org/10.1002/agg2.20079)

时序固氮原始研究｜大豆

**支持：**所研究条件下R3和R5附近出现固氮速率峰值。

**边界：**峰值依材料和环境改变，不是大豆的固定日历；不外推绿豆。

核验范围：出版社摘要核对

## 公开数据入口

Edwards 2018：NCBI BioProject [PRJNA392701](https://www.ncbi.nlm.nih.gov/bioproject/PRJNA392701)；[Dryad](https://doi.org/10.5061/dryad.7q7k1)；[作者分析代码](https://github.com/bulksoil/LifeCycleManuscript)。入口由论文Data Availability核对；本次未下载或重新分析原始序列。

随附JSON包括字段字典、文献评议、候选证据及空观测模板。字段全部已定义；四种候选材料的地下生物学实测值尚未补齐。
