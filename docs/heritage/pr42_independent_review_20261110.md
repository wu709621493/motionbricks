# PR #42 独立复核与八合院扩展方案

> 本文是本对话上一阶段、尚未发布PR时的冻结复核记录。随后用户要求改为简单图册并整理PR；当前文件数量、验证结果与发布范围以 [图册版说明](courtyard_simple_20261110.md) 为准。下文“7个生成文件不变”“未提交”“分开PR”等描述仅对应当时快照，不适用于之后的图册入口调整。交互未验收仍是事实。

复核日期：2026-11-10（北京时间）。目标仓库：wu709621493/motionbricks。

**结论：实际合并冲突只有根 README，一处内容冲突，已在本地生成保留双方内容的候选。CPU回归及归档一致性通过；真实浏览器验收被环境阻断，不能宣布完整交互验收通过。建议补齐浏览器验收后再合并。八合院作为独立后续变更。**

本次只在隔离工作副本中复核、制作补丁和概念原型。没有创建提交、推送、发表评论、修改远端PR状态或合并GitHub内容。

## 1. 固定复核对象

| 对象 | 本次实际读取 |
|---|---|
| PR | [#42](https://github.com/wu709621493/motionbricks/pull/42)，open、draft=false、merged=false |
| PR head | `fb11f6b099d35cc16b22a81cfa03115558ea30d4` |
| 当前 main | `bc86b71864f76da521fe9ee1457d409c70862d4c`，已包含PR #63 |
| Git计算的共同祖先 | `a7d16bd144326c349e571bc327dafd3beaf70b48` |
| API合并状态 | `mergeable=false`、`mergeable_state=dirty`、`rebaseable=false` |
| README规模 | 共同祖先356行；当前main 489行；原PR head 364行 |

PR API中的base.sha仍显示旧基准，不能把它当作当前main。main由独立的branch API和本地Git对象交叉核对。用户提供的 `411836…` 已不是本轮最新main。结论仅覆盖上面两个固定SHA；后续任一端更新都需重新计算差异。

## 2. 真实冲突与最小解决方式

执行 `git merge-tree --write-tree <main> <head>` 及本地 `git merge --no-commit --no-ff <head>`，两者均仅报告 `README.md`。

共同祖先以“Integer representation portability lab”结束。双方都在文件末尾追加内容：

- main冲突侧位于其376—489行：从 Engineering humor 到最新多语言短剧，包含 Fan fiction、Zhuyin Bridge、CPU memory and rendering、Biophysics / RS-72及动态阵风、住宅服务器、Strategy and perception、Original fiction等入口。
- PR侧为head的358—364行：`### Beijing courtyard heritage archive (c. 1900)`及档案说明、重建命令。
- main在冲突段以外的其他新增内容也完整保留，包括前面的研究入口。没有采用“整份README选ours/theirs”的最终解决方式。

最小解法为：以**完整当前main README**为底，再追加原PR的四合院段落。相对main仅新增8行（含分隔空行），没有删除或改写main内容。PR其余13个文件原样带入，逐字节核对通过。原始冲突块见交付包 `evidence/README-conflict.diff`。

补丁 `01-readme-resolution.patch` 只展示根README的8行追加。`01-integrate-pr42.patch` 则包含PR原有14文件在固定main上的完整整合结果；其大量新增行来自原PR，不是本轮重新制作档案。

## 3. 复核中发现的生成器问题

| 问题 | 原行为及证据 | 修复与验证 |
|---|---|---|
| SVG文字未转义 | 将构件名设为含 `<`、`&` 的文本，`ElementTree`解析原生成图报错；标签也可被作为标记解释 | `plan_svg()`对文字节点加 `html.escape()`；新增回归覆盖 `<script>`、`&` 和引号，确认它们保留为文本 |

转义修复对现有中文构件名不改变输出。**原始主JSON与7个生成文件，包括原SHA-256清单，都保持逐字节相同。** 无需为了这项修复重建历史数据、改版本身份或篡改来源状态。原档案README的 `../../../data/...` 链接经路径解析确认正确，保持不变。

## 4. 浏览器验证：静态通过，实际交互未运行

本地已安装Playwright 1.62.1和Chromium，但启动过程在创建页面前报 `socket() failed: Operation not permitted (1)`。随后检查受控浏览器通道，`file://`被URL安全策略拒绝。未通过其他表面绕过限制。因此下表不得记为浏览器PASS，也没有实际浏览器截图或移动设备测试结果。

| 功能 | 本次静态检查 | 待执行的实际验收判据 |
|---|---|---|
| 构件选择 | 20项目录、change事件、详情及高亮更新逻辑存在 | 逐一选择20项，目录值、详情ID和高亮一致；三维指针点选可更新详情 |
| 三维旋转 | range的input事件重新投影顶点 | 鼠标/触摸拖动可旋转；方向键改变角度和投影；关键角度无异常裁切 |
| 屋顶隐藏 | 过滤 `kind==='roof'` 面 | 隐藏后只减少屋顶面，复选后恢复，主体仍可选择 |
| 平面点选 | 20个 `data-element` SVG构件绑定click | 点选建筑后详情与选中样式一致 |
| 键盘 | 平面构件tabindex=0，Enter/空格调用choose；下拉框可替代三维点选 | Tab可达20个平面构件，Enter/空格选择；旋转、复选框、视图、重置可全程键盘操作且焦点可见 |
| 导览线/重置 | 两视图同步及重置逻辑存在 | 导览线开关同步；重置回35°、屋顶/导览线开启、正房选中 |
| 不同宽度 | CSS有900/580 px断点、可伸缩网格和表格滚动容器 | 320/375/390/768/1024/1440 px逐页无全页横向溢出、文字遮挡或控件不可达；实机触摸另验 |
| 下载及离线 | 内嵌数据；无远端script/stylesheet/image依赖 | 断网打开file://后可操作，下载JSON与目录一致；外部来源链接不在离线验收范围 |

已完成的静态检查：两份档案SVG的XML解析、原档案和新概念的JS语法检查、生成HTML无外部脚本/样式/图像引用。它们不能证明布局、交互、下载、渲染顺序或屏幕阅读器表现。

新增 `tools/siheyuan/browser_review.cjs` 包含上述主要交互及六种宽度的自动化断言。**脚本只完成语法检查，尚未跑到任何浏览器断言。** 它针对原20构件档案；八合院需另加楼层切换和116记录场景。人工还需审查视觉遮挡、焦点样式、SVG可访问性树、屏幕阅读器、Safari/Firefox与真实手机触摸，自动化无全页溢出并不等于视觉验收通过。

## 5. Python、SHA-256和回归证据

本机是Linux x86_64，Python 3.12.14 / 3.13.5，Node 24.22.1。Python测试均带 `-S`，不加载site-packages。

| 对象/证据 | Python 3.12 | Python 3.13 | 解释 |
|---|---|---|---|
| 原PR head档案单测 | 9/9通过 | 9/9通过 | 本轮实际运行 |
| 原PR head preflight回归 | 31/31通过 | 31/31通过 | 本轮实际运行 |
| 仅README整合后的档案/preflight | 9/9 + 31/31通过 | 9/9 + 31/31通过 | 在当前main与PR整合树运行 |
| 最终小修后的档案单测 | 10/10通过 | 10/10通过 | 新增名称转义回归 |
| 八合院概念单测 | 7/7通过 | 7/7通过 | 几何与归档性质检查 |
| 原档案build --check | 通过 | 通过 | 20构件、4来源、7文件 |
| 八合院build --check | 通过 | 通过 | 8院落、116记录、6文件 |
| 双Python独立重建字节比较 | 原档案7文件相同 | 概念6文件相同 | 无跨版本导出漂移 |

标准库生成器只导入 `__future__`、argparse、hashlib、html、json、math、pathlib、re，不导入MotionBricks运行时、Warp或CUDA。新概念同样只用标准库并复用几何函数。

原清单独立重算的6个SHA-256均匹配。清单不包括自身、README、生成器源代码、远端史料或原照片，**校验和证明字节一致性，不证明史料真实或建筑可靠**。`--check`通过重建并逐字节比较7个预期文件，能发现生成物及清单被改动，但不会拒绝输出目录里所有额外文件。

历史CI：API返回28条check run（含重复运行），均success；包含档案3.12/3.13和跨平台CPU检查。本轮实际执行仅限上表Linux x86_64。历史macOS/ARM64通过不等于本轮在这些平台复现；本地补丁和八合院CI尚未提交，因而没有它们的远端CI结果。

Unitree G1 preflight另有实际诊断记录：离线检查可用，但运行时依赖和LFS权重未就绪。没有GPU推理、场景编辑器加载、机器人动态碰撞或人物动作结果。场景字段单测通过的是源码字段契约，导览线测试只是1.8 m高、半径0.35 m包络的0.05 m采样检查。

本轮没有重新查阅四条外部史料；保留原来源记录及其访问状态，不把既有来源文字升级为新的独立史学核验。

## 6. 可复现命令与判据

在仓库根目录、应用本轮小修后的整合候选上：

```sh
python3.12 -S tools/siheyuan/build.py --check
python3.12 -S -m unittest discover -s tests/siheyuan -v
python3.12 -S -m unittest discover -s tests/preflight -v
python3.13 -S tools/siheyuan/build.py --check
python3.13 -S -m unittest discover -s tests/siheyuan -v
python3.13 -S -m unittest discover -s tests/preflight -v
python3.12 -S experiments/bahayuan/build.py --check
python3.12 -S -m unittest discover -s tests/bahayuan -v
python3.13 -S experiments/bahayuan/build.py --check
python3.13 -S -m unittest discover -s tests/bahayuan -v
git diff --check
```

预期全部退出0；每版档案10项、preflight 31项、概念7项。历史档案的20构件、4史料、7生成物不得被概念覆盖。

在允许浏览器运行的独立环境中，准备Node及Playwright后：

```sh
npm install --no-save --package-lock=false playwright@1.62.1
npx playwright install chromium
node tools/siheyuan/browser_review.cjs "$PWD" /tmp/pr42-browser/report.json
```

可用 `CHROMIUM_PATH` 指定已有Chromium路径。此浏览器依赖仅用于验收，不是标准库生成器依赖，也未加入仓库主运行时。预期脚本所有断言PASS、无页面错误、无外部请求；再按上表补人工视觉与设备验收。不要把因浏览器未启动而没有测试结果解释为通过。

## 7. 八合院创新原型

方案详见 [概念说明](../../experiments/bahayuan/README.md)。四个两进模块，8个有明确矩形范围的露天院落；54 × 70 m假想场地；二层围合，正房局部三层四边退0.6 m，最高屋脊11.9 m。所有尺度均为设计假设。

| 新记录类别 | 数量 |
|---|---:|
| 一层：四份原20构件的当代衍生 | 80 |
| 二层：每模块6处楼房体量 | 24 |
| 三层：每模块1处退台正房体量 | 4 |
| 竖向交通预留：每模块2处 | 8 |
| 合计 | **116** |

116是构件/空间记录数，不是116种不同构造，也不是网格面数。8个交通预留无实际台阶、平台或门洞，未进入OBJ/场景实体。概念原型可以生成离线HTML、平面SVG、OBJ、场景包络JSON及校验清单；浏览器交互和运行时加载均未验收。

通过的几何测试只确认院落上空不被模型实体遮挡、上层投影在下层范围内、模块不重叠及标高衔接。不证明承重、抗震、无障碍或疏散。下一步应设计跨模块出入口、楼梯和内部通道，再细化柱梁楼板、基础、门窗、排水及机电；真实古建加层另需具体实测和专业论证。

## 8. 拟修改文件、最小差异与合并建议

| 变更组 | 文件 | 相对本轮起点的变化 |
|---|---|---|
| 必需冲突解决 | 根 `README.md` | 保留main全文，追加四合院原段落8行 |
| 小修 | `tools/siheyuan/build.py` | SVG名称转义一行修正 |
| 回归 | `tests/siheyuan/test_archive.py` | 新增XML名称转义测试，9→10项 |
| 验收材料 | `tools/siheyuan/browser_review.cjs`、本复核报告 | 可复现交互检查和已验证/未验证边界；未运行浏览器断言 |
| 独立概念扩展 | `experiments/bahayuan/{README.md,design.json,build.py,viewer.html,output/*}` | 8院落116记录；6个生成文件 |
| 扩展回归与CI定义 | `tests/bahayuan/test_concept.py`、`.github/workflows/bahayuan-concept.yml` | 7项CPU回归、3.12/3.13限定路径CI；远端CI未执行 |

建议先审查并应用PR #42的README冲突解决和小修；更新后的准确head需重新运行CI。完成桌面、窄屏及键盘浏览器验收后，才建议合并PR #42。它当前已经不是Draft，因此不需要也未执行“转为Ready”操作。

八合院单独建后续PR，标明“当代概念、界面待验收、结构未验证”，避免把原档案整合变成大范围建模改造。本次不会自动创建该PR。

剩余风险按优先级：浏览器交互/布局/辅助技术未验收；任一远端SHA变化会使冲突结论过期；新补丁未跑远端CI；场景GPU加载与实际通行未知；概念缺少工程与真实地址数据；原史料尚未新增独立复核。
