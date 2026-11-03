# 数据字典与采集前检查

配套 [完整流程](workflow.md)。以下 CSV 均为仅含表头的模板，没有真实或模拟受试者结果。字段为建议的数据合同，尚无自动校验程序。

## 文件与连接关系

| 模板 | 一行代表 | 主键与关联 |
| --- | --- | --- |
| [sites.csv](sites.csv) | 一次访视的一个牙面 ROI | visit_id + site_id；participant_id 只用匿名编号 |
| [ph_timeseries.csv](ph_timeseries.csv) | 一个时间点的探头读数 | visit_id + site_id + sensor_id + time_s；关联 calibration_id |
| [samples.csv](samples.csv) | 一份回收样本的一个分析小份 | aliquot_id 唯一，关联 sample_id、visit_id、site_id |
| [calibrations.csv](calibrations.csv) | 一次校准中的一个缓冲液读数 | calibration_id + phase + point_index |

`schema_version` 固定为 `0.1`。所有时间戳用含时区的 ISO 8601；`time_s` 相对该访视标准化挑战开始时间，负数表示基线。缺失值用空单元格，同时在 `missing_reason` 或 `qc_reason` 说明；零值只代表实测零。禁止 NaN/Infinity 字符串和为避免除零而偷偷加 epsilon。

## sites.csv

- `participant_id`, `visit_id`, `site_id`：字符串；同一人的访视保持 participant_id 一致。
- `tooth_system`, `tooth_id`, `surface`, `roi_id`：牙位体系、牙号、表面、图像 ROI 标识，不仅记录“左边”。
- `group_code`：盲态编码；真实组别对应表独立保存。四组定义见流程。
- `pre_image_ref`, `post_image_ref`, `mask_ref`：受控存储引用；不要上传身份信息或真实口内图像到公开仓库。
- `area_basis`：`projected_mm2`、`surface_mm2` 或 `pixels`。不同定义不能直接合并。
- `evaluable_area_pre`, `plaque_area_pre`, `evaluable_area_post`, `plaque_area_post`：与 area_basis 对应；非负，菌斑面积不超过有效牙面面积。前后有效 ROI 不同则先做配准与共同区域分析。
- `coverage_pre_pct`, `coverage_post_pct`：0–100；与对应面积比一致。
- `saliva_flow_ml_min`, `buffer_method`, `buffer_result`：流量和独立缓冲测定；结果的单位/方法写入 buffer_method，不混合不同方法结果。
- `disclosing_agent`, `last_hygiene_at`, `last_food_at`, `protocol_version`：干扰项与方法追溯。
- `qc_status`：`pass`、`flag`、`fail`、`not_assessed`；`qc_reason` 解释。

## ph_timeseries.csv

- `sensor_id`, `calibration_id`：设备及该次测前/测后校准记录的关联。
- `measurement_target`：`natural_plaque`、`saliva`、`sensor_biofilm`，禁止混写。
- `time_s`, `recorded_at`, `ph`, `temperature_c`：保留原始时间和温度；pH 必须落在已验证设备范围，否则标记失败，不裁剪到边界。
- `event`：`baseline`、`challenge_start`、`intervention`、`observation`、`sampling_start`、`stop` 等；事件时间由操作者确认。
- `qc_status`, `qc_reason`：探头位移、缺口、校准漂移、接触污染等。各传感器时间须严格递增；重复时间戳需调查，不静默平均。

## samples.csv

- `sample_id`, `aliquot_id`：原始回收样本和分样编号；不同小份不是独立生物学重复。
- `collection_method`：`floss`、`curette`、`prototype_brush`；`operator_id` 为机构内编码。
- `collected_at`, `received_at`, `assayed_at`, `transport_temperature_c`, `transport_medium`, `medium_lot`：运输条件；时间顺序必须合理。
- `recovered_volume_ml`, `aliquot_volume_ml`, `dilution_factor`：均为正；稀释因子定义为测定液浓度换算回原小份的倍数，至少为 1；与分样体积放大不要重复计算。
- `acid_assay_method`, `assay_protocol_ref`, `raw_assay_ref`：方法、完整参数/设定点/底物/空白引用及原始文件引用。缺少这些引用则无法审计净产酸。
- `net_acid_rate_umol_min`：标记为当前分析小份尺度，已扣匹配空白，未自动外推到整份回收液；负值允许且需检查。
- `recovery_fraction`, `recovery_validation_ref`：仅填经验证且适用的回收估计。有效比例应在 (0,1]；表观大于 1 保留在原始文件并标记失败，不强制裁剪。未测留空。
- `biomass_value`, `biomass_unit`, `biomass_method`：可选生物量标准化；方法与单位必须成对填写。
- `qc_status`, `qc_reason`, `missing_reason`：污染、低于定量限、运输偏离、缺失原因。

## calibrations.csv

- `phase`：`pre` 或 `post`；`point_index`：缓冲液读数序号；同一 calibration_id 关联一个测量时段。
- `sensor_id`, `recorded_at`, `buffer_lot`, `temperature_c`：设备、时间、批次、温度。
- `reference_ph`, `measured_ph`, `residual_ph`：温度适配的参考值、读数、读数减参考值；保留符号。
- `acceptance_protocol_ref`：冻结的验收条件文件；`qc_status`, `qc_reason`：结果和理由。

## 采集前必须冻结的参数（未填写不得进入正式采集）

| 参数 | 必须记录的内容 |
| --- | --- |
| pH 验收 | 有效范围、校准残差/漂移容差、响应时间、参考仪及独立检查方法 |
| 时序 | 采样间隔、允许缺口、同步误差、基线稳定性、观察窗 |
| 挑战/干预 | 底物、剂量、暴露时间、实际配方、释放验证、口内方案审批引用 |
| 取样 | ROI、器具、清洁时长/动作/压力控制、洗脱体积、回收与活性接受范围 |
| 成像 | 光学条件、面积定义、分割验证、定量限、显色剂干扰结果 |
| 转运 | 介质、时间/温度范围、分样顺序、活性验证 |
| 产酸 | 检测体积/设定点、空白、时间窗、气体与温度、定量限、重复性 |
| 分析 | 主要终点、pH 参考线、恢复容差/持续时长、统计模型、排除和缺失规则 |

## 数据验收清单

- 主键唯一，所有外键可解析，匿名标识一致；不将 sample_id 当 participant_id。
- 图像区域与采样区域匹配；无法匹配时明确降级为组间/独立区域比较。
- 每个 pH 时段具备测前与测后校准；失败读数不进入主要终点。
- 时间、单位、面积范围、分样比例及空白校正一致；原始数据不可覆盖。
- 缺失、未恢复和低于定量限各自有原因；不以零代替。
- 分析报告注明本次数据是真实、合成还是空模板；本目录只提供空模板。
