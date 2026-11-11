# 汉江证据 CSV：可复现校验与验收记录

日期：2026-11-11（Asia/Shanghai）。校验器仅使用 Python 标准库，离线、只读；不安装 MotionBricks、不加载 GPU、不调用网络。入口：[validate_han_river_csv.py](../../../tools/validate_han_river_csv.py)；[单元与 decline 测试](../../../tests/han_river/test_validator.py)。

## 读取基线与最小范围

读取 GitHub 最新 main 后固定到 `ee8bb24b274f5eaedb9ef422761da26e97bbd920`，取该提交的原 CSV、数据字典和调查正文。工作区为这些相关文件的局部快照，未将其冒充完整仓库回归；提交树在远端基线之上仅新增／修改本补丁列明的路径。

原 CSV Git blob：`e13c69f41df03fb1de9398868826a35afcc07b44`。原始字节 SHA-256：

```text
03ca7438dc5c119318821906411289ac888f53bda459b12dba5c5fdd19dc42ad
```

原 CSV 与原调查正文均不改动。数据字典 README 只增补导航；程序、测试、CI、校验说明、两栖动物推论和用户追加要求的对话摘要／仓库技能独立存放。

## 校验契约

| 检查 | 拒绝或保留规则 |
| --- | --- |
| 结构 | 固定 19 列及顺序；拒绝缺列、重复列、额外列、换单位表头、长短行、空表和 CSV 语法错误；支持 UTF-8 BOM 与 CRLF |
| 标识与去重 | `HAN-` 加至少三位数字；ID 唯一；另按 source_id、sampling_period、sampling_year、site、matrix、analyte 的六元组拒绝换 ID 的重复证据；不把 notes/locator 的变动当成新记录 |
| 来源 | 非缺口要求 HTTPS URL 和非空 locator；S2/S3/S4 的 DOI、发表年份和证据类型与已审阅契约一致。未知来源拒绝，须先更新契约 |
| 单位／基质 | 五个数值列固定 ng/L；拒绝数值中附单位、µg/L 表头及沉积物／组织基质；核对 S2 站点对应基质及 S3/S4 汇总范围 |
| 数值 | 只接受有限、非负十进制／科学计数；实测均值和已填未检出上界须大于零；± 可为零；模型下界不得大于上界；不设无依据的生态安全上限 |
| 年份 | 已填年份须为 1000–2999 的四位年份，采样不晚于发表；当前来源的采样年份未核实，必须空白；不按机器时钟或发表年份补值 |
| 不确定性 | 有实测 ± 时只能保留 `not_defined_in_table_caption`；无 ± 时留空；拒绝自称 SD/SE |
| 未知分析限值 | 未检出上界未知可以留空并警示；报告上界不变成 LOQ。本 schema 无逐物质 LOQ 列，不制造字段或数值 |
| 诊断 | 返回错误行号和稳定代码；已知问题作为警示保留。HR-4 算术若超出固定 Decimal 精度／指数容量，拒绝而不静默舍入 |

| evidence_type | qualifier | 可填数值 | 必须空白 |
| --- | --- | --- | --- |
| measured_summary | mean | value 必填；reported_plus_minus 可选 | lower、upper、reporting_bound |
| reported_nondetect | less_than | reporting_bound 可选，未知时警示 | value、reported_plus_minus、lower、upper、uncertainty_type |
| modeled_range_of_means | range_of_means | lower 与 upper 必填 | value、reported_plus_minus、reporting_bound、uncertainty_type |
| not_retrieved | not_available | 无 | 所有数值及 uncertainty_type；发表年、采样年、文献 URL 和 locator；来源固定 SEARCH_GAP |

模型／缺口仍须有非空 notes 和明确范围。上述“value”等简写均对应 CSV 的原始 `*_ng_L` 字段。

**能力边界：**软件不能发现所有“把 µg/L 数字原样放进 ng/L 列”的语义错误；合法数字及正确表头并不能证明原始单位。URL 检查是格式与已审阅 DOI 匹配，不证明链接存活或文献支持该数值。六元组只做精确去重，不解决不同拼写或不同来源重复引用同一数据。扩充文献必须同时审阅原始单位、来源映射与数据字典；现有快照计数测试需随经核实的扩充更新，不能通过删除测试掩盖变化。

## 准确运行命令与预期输出

从仓库根目录，以 Python 3.12+ 运行：

```bash
python -S tools/validate_han_river_csv.py
python -S tools/validate_han_river_csv.py --json
python -S -m unittest discover -s tests/han_river -v
```

不需要 pip 安装。默认 CSV 按脚本位置定位；也可传入候选文件：

```bash
python -S tools/validate_han_river_csv.py /absolute/path/to/candidate.csv --json
```

当前基线预期文本输出：

```text
ACCEPT: 49 records; 0 errors; 3 warnings
  measured_summary: 39
  modeled_range_of_means: 4
  not_retrieved: 2
  reported_nondetect: 4
HR-4 input sum (ng/L): 9
UNKNOWN_SAMPLING_YEAR: 43 observational summaries retain unknown sampling year.
LOQ_NOT_ENCODED: Schema has no analyte-specific LOQ field; reporting_bound_ng_L is not a LOQ.
HR4_SOURCE_CONFLICT: Unresolved historical S2 Table 1 HR-4: 5 + 2 + 2 = 9 ng/L versus prose <7 ng/L; do not repair source values.
```

退出码：0 = 无结构／契约错误，警示仍有效；1 = DECLINE（数据或读取失败）；2 = 命令行参数错误。JSON 给出 verdict、records、counts、hr4_sum_ng_L、errors、warnings。未知年份警示统计的是 43 条观测汇总，不把模型或检索缺口计为采样。

即使从候选 CSV 删除 HR-4 或把值改到低于 7，历史矛盾警示也不会消失；当前输入的求和另列。均值之和是对已发表四舍五入值的算术，不合成误差条、显著性或原始样本数据。该检查不锁定所有历史数值；原始字节是否变化需对比摘要／代码差异并进行文献复核。

## 本次实际执行与未完成事项

| 证据层级 | 本次状态 |
| --- | --- |
| 本地 CPU 软件实际执行 | Linux x86_64，Python 3.12.14；默认表检查返回 0，49 行／0 错误／3 警示；`python -S` 禁用 site 初始化也能运行 |
| 单元和异常输入实际执行 | `Ran 28 tests ... OK`；含多组参数化异常、CLI 退出码、缺文件、非法 UTF-8、BOM/CRLF、其他工作目录、输入字节不变与确定性输出 |
| 代表性 decline | 未检出填 0 或半上界、模型改装为实测、缺口改未检出、来源／定位缺失、跨类型数值污染、错误单位表头、负数／NaN／无穷、逆序范围、擅填年份、重复 ID／重复证据均被拒绝 |
| 仓库技能实际试跑 | 技能格式检查通过；独立只读试跑正确拒绝第 41 行 HAN-040 的未检出填 0，返回 1，报 FORBIDDEN_VALUE / ZERO_VALUE；基线通过，候选表与基线字节不变 |
| 历史人工检查 | 原 PR #72 的目视核对、一次性数据检查保留在原记录；不将其改标为本次独立全文复核 |
| 新增 CI 配置 | Ubuntu + Python 3.12/3.13，执行同两条标准库命令；配置存在不等于已执行，通过状态以 PR 对应提交的 Actions 回执为准 |
| 本次文献工作 | 定向检索并核对两栖动物原始文献／官方页面的可访问部分，逐项访问层级见补充文档；重新取得 S2 表格／正文索引片段，未重做全部论文全文审计 |
| 尚未完成 | S3 全文逐物质方法限值、S2 采样年份和表中 ± 定义、HR-4 作者解释、原始逐样本数据、当地两栖动物因果证据、任何现场或动物实验 |

本地测试使用独立临时异常副本，不改原表。软件 ACCEPT 不是环境安全证明，不提高任何文献的证据等级。

[本次讨论摘要](../../han_river_xenopus_session_summary_zh.md)记录了仓库技能 **lay eggs! Xenopus!** 的用途。该技能复用本校验器，不另复制一套判定逻辑。
