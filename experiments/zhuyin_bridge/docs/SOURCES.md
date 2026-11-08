# 数据和来源

核对日期：2026-11-08。链接是工程与草案依据，不表示机构背书。

## 拼写

[教育部《漢語拼音與通用拼音對照表》](https://ws.moe.edu.tw/001/Upload/FileUpload/3692-16962/Documents/970918duizhao.pdf)提供注音与汉语拼音的声韵对应。项目采用汉语拼音提示，不是通用拼音。尤其区分 ㄓ 的 zh/zhi、ㄩ 的 ü/yu/u，以及无声母的 you/wei/wen 与有声母时的 iu/ui/un。

`Tools/build_data.py` 以人工编写的有限声韵组合白名单生成 409 种拼写。该数量是本项目覆盖数，不是“现代汉语只有 409 个音节”的语言学断言。少见音节、方言或音节化鼻音不在本版范围内。键帽中的 `i/u/ü` 是组合提示；完整音节会显示 `yi/wu/yu` 等拼法。

`Data/lexicon.tsv` 是为本次原型手工整理的 204 条教学词条，包含不同声调的单字与短词。未下载、复制或打包完整第三方词典；排序为文件固定顺序，不是词频模型。简繁字形在各条目中显式列出，不能代替通用简繁转换。例词采用词汇本调；多音字和各地读音差异没有穷尽。

## Apple 官方文档

| 来源 | 用途 |
|---|---|
| [Creating a custom keyboard](https://developer.apple.com/documentation/uikit/creating-a-custom-keyboard) | 扩展结构、公开入口和切换键盘交互 |
| [Configuring a custom keyboard interface](https://developer.apple.com/documentation/uikit/configuring-a-custom-keyboard-interface) | 系统输入框限制及布局适配要求 |
| [Configuring open access](https://developer.apple.com/documentation/uikit/configuring-open-access-for-a-custom-keyboard) | 不申请开放访问的设计 |
| [Enabling Developer Mode](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device) | 本地签名真机调试步骤 |
| [App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/) | 第 4.4、4.4.1 和 5.1 节，键盘功能及隐私文案检查 |
| [Developer Program License Agreement](https://developer.apple.com/support/terms/apple-developer-program-license-agreement/) | 区分本项目提案与正式开发分发条款 |
| [Standard EULA](https://www.apple.com/legal/internet-services/itunes/dev/stdeula/) | 正式分发时选择适当的许可安排 |

扩展里的代码没有评价或广告文案。用户要求的开发者蜜语位于配套 App 的帮助内容及网页介绍。它不会主动拉起其他 App。

## 尚未验证

pre-PR 阶段未执行 Apple 平台编译或 API 可用性实测。入仓后新增 macOS Swift 测试和 iOS 模拟器构建工作流，结果以当前 PR 对应提交的 CI 为准；真机 API 行为仍须实测。部署目标 iOS 16 是工程设置，不构成所有设备/OS 组合兼容性保证。Xcode 生成器的输出经过文件与 plist 静态检查；实际可编译性必须由 Xcode 运行确定。
