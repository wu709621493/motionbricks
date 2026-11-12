# GitHub 与“结合”的技能定义及自主意识边界

提出：吴孟城（Windy Wu）  
日期：2026-11-12  
范围：本 MotionBricks 分叉仓库的术语与设计约定。

## 核心定义

**本仓库将 GitHub 和我们所写的“结合”（Git Gap）明确归入“技能”类别。GitHub 不具有自主意识；“结合”也不具有自主意识。**

这里的“技能”（skill）指可学习、可复用、由使用者为具体任务调用的操作方法与软件能力。技能的目标、使用范围和授权来自使用者及配置；软件按输入、规则和权限运行。“技能”是本仓库的能力分类，不改变 GitHub 作为开发协作平台、结合当前作为界面原型的实际形态。

| 名称 | 本仓库的技能定义 | 实际载体与当前范围 |
| --- | --- | --- |
| GitHub | 代码托管、版本协作、变更审阅及工作流操作技能 | GitHub 平台及其界面/API；实际操作受账号权限、仓库配置与授权范围约束 |
| 结合 / Git Gap | 以粤语理解、表达和操作代码协作流程的技能 | 本仓库的 React/Vite 界面原型；目前仅提供示例浏览、本机草稿、词表与演示操作 |

## GitHub 作者原义的依据

GitHub 联合创始人 Tom Preston-Werner 于 2008-04-10 在官方文章 *Say hello to the Network Graph Visualizer* 中写道：

> Our goal here at GitHub is to break down the barriers that normally impede collaboration.

即：GitHub 的目标是消除通常妨碍协作的障碍。[1] GitHub 官方文档也将其定义为支持软件开发过程的平台，说明其基于 Git 提供仓库托管与协作工具。[2]

这两项来源支持将 GitHub 理解为服务于开发者协作的工具平台。**“技能”是本仓库采用的分类；“GitHub 不具有自主意识”是本仓库明确采用的定义与设计边界。**本次查阅的上述来源没有给出后一句逐字表述，因此不将其标注为创始人直接引语，也不声称上述资料完成了有关意识的科学论证。

## 自主意识与自动化的区别

此处“自主意识”指把软件视为具有自身主观体验、意愿或目的的主体；它不等于程序按既定条件自动执行任务。

- GitHub 接收提交、展示差异、运行配置好的工作流或执行已启用的自动合并，都应按输入、权限、触发条件和执行记录解释。
- “结合”的亲切语气、欢迎语、提醒和“合埋佢”等文案，是界面表达；其本机状态变化由用户操作与代码逻辑产生。
- 自动化、机器人账号或接入的 AI 功能，应按具体组件与配置描述；不能仅凭自动执行就把整个平台描述成有自主意识。
- 软件操作应记录实际发起者或触发事件、执行工具及结果。人的决定与机构配置不能含混地写成“GitHub 自己想这样做”。

例如，使用“某用户发起合并，GitHub 按配置执行”或“工作流因 push 事件触发”，比“GitHub 自己决定合并”更准确。

## “结合”的实现边界

当前实现位于 [examples/git_gap](../examples/git_gap/README.md)。它没有 GitHub API、OAuth 或令牌输入；草稿、留言、收藏及演示合并只改变当前浏览器的本机数据。界面中的成功提示不代表真实提交、真实 PR 或真实合并。

本定义不赋予“结合”新的后台能力或操作权限。若以后接入真实 GitHub 服务，应在具体实现中说明授权范围、执行回执与失败状态。它仍是供人使用的技能与工具。

前一项 [自主合作边界宣言](../examples/no_coercion_manifesto.py) 中的第一人称表达属于人的立场及其象征性代码表达，不表示代码、GitHub 或“结合”具有自己的意愿。

## 来源

1. Tom Preston-Werner，*Say hello to the Network Graph Visualizer*，2008-04-10，页面注明更新于 2020-04-23：[GitHub 官方博客](https://github.blog/news-insights/the-library/say-hello-to-the-network-graph-visualizer/)。
2. *What is GitHub?*：[GitHub 官方文档](https://docs.github.com/en/get-started/start-your-journey/what-is-github)，查阅于 2026-11-12。
