# 四合院与八合院：直接看图的图册版

2026-11-10。用户选择“傻瓜版整理PR”后，本次将默认入口改为静态图册：看整体、选楼层图、下载模型。无需拖动三维视角或安装模型运行时。

## 打开入口

- [约1900年四合院说明与图片](beijing_siheyuan_1900/README.md)：20条构件、4条史料；历史类型复原。
- [八合院说明与图片](../../experiments/bahayuan/README.md)：8个院落、116条记录；二层及局部三层退台的当代概念。
- 下载相应目录后打开 `index.html`；静态构件目录在 `inventory.html`。
- 需要旋转时再打开 `interactive.html`。它保留原交互功能，仍属于待浏览器验收的可选实验入口。

默认页没有JavaScript、内嵌模型JSON、Canvas/WebGL或Service Worker；只引用一张总览SVG，其他图片以链接按需打开。两份HTML入口分别约2.9 KB / 3.0 KB，**图片字节另计，这不是浏览器内存或缓存占用测量**。

此前浏览器无法运行的实测原因是本地 `socket()` 权限和受控浏览器 `file://` 策略，不是已证实的缓存耗尽。本轮不绕过这些限制。

## 与原PR #42的关系

整合基准main为 `bc86b71864f76da521fe9ee1457d409c70862d4c`，原PR head为 `fb11f6b099d35cc16b22a81cfa03115558ea30d4`。发布前再次同步main至 `3577bda46d023df84c4518c75cb85ccf702b11b8`；两次实际冲突均仅根README。所有最新main已有项目入口完整保留，增加四合院和八合院入口。

原历史主JSON、catalog、两幅SVG、OBJ、场景数据保持不变。原交互首页移动为 `interactive.html`，新 `index.html` 为图册；新增 `inventory.html`，重新生成SHA-256清单。原档案现为9份生成文件，其中8份受清单校验。档案身份与几何数据版本仍为1.0.0，展示入口的变化由Git历史记录。

保留上一阶段的SVG构件名称转义修复。旧浏览器验收脚本改指向 `interactive.html`，不会把静态入口当成交互页测试。

八合院现为12份生成文件，清单校验其中11份。新增二层、三层、带屋顶与去屋顶固定图，静态目录列出116条记录。绿色区域标明为地面院落范围，不表示二三层悬空庭院。

## 本地验证

Python 3.12/3.13使用 `-S`，不加载site-packages。本次实际执行：每版档案11项、八合院8项、preflight 31项全部通过，两套生成器 `--check` 通过；两版导出的字节一致。执行记录在 [results/courtyard_simple](results/courtyard_simple/verification.json)。

```sh
python3.12 -S -m unittest discover -s tests/siheyuan -v
python3.12 -S -m unittest discover -s tests/bahayuan -v
python3.12 -S -m unittest discover -s tests/preflight -v
python3.12 -S tools/siheyuan/build.py --check
python3.12 -S experiments/bahayuan/build.py --check
```

再将上述 `python3.12` 换成 `python3.13`。生成器仍仅依赖标准库，静态SVG渲染检查工具不属于生成器或运行时依赖。

新增断言覆盖静态入口无脚本、目录20/116条记录、文件链接存在、首页不夹带模型JSON、三层图分别含80/24/4条实体记录，以及去屋顶视图恰好去除屋顶面。固定SVG通过XML解析，并使用本地librsvg/Cairo渲染为图像检查。交互版JS完成语法检查。

**未验证**：真实浏览器和手机的完整排版、下载操作及辅助技术；可选旋转页的实际交互；GPU场景加载、人物运动与碰撞。上述静态/CPU结果不能描述为浏览器PASS。新增GitHub CI定义及本地结果也不能冒充已经执行的远端CI。

## 合并范围

本PR整合原PR #42的档案、最小冲突解决、默认图册入口及八合院概念；原始历史档案和当代设计分别存放。PR #42保留，未自动关闭；本PR不自动合并。

审查重点：保留main入口；确认历史数据未变；两套CPU CI通过；默认图册的图片与文件链接完整。图册可独立作为静态交付审查，可选交互页仍明确标为未验收，不再让它成为查看模型的必经步骤。

八合院只是封闭体量原型：8个交通预留不是实际楼梯；结构、抗震、疏散、无障碍与跨模块通道仍待设计验证。
