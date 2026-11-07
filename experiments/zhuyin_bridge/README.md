# 注音桥 · Zhuyin Bridge

**拼音在上，注音在下。** 为熟悉汉语拼音的用户提供注音键帽提示、整音节拼音和离线选字。

状态：**PR 原型 0.1，2026-11-08**。独立原型；不是 Apple 产品。已提供 Xcode 工程和测试源文件；本地环境没有 Swift / Xcode；已接入仓库的 macOS Swift 测试、iOS 模拟器构建及 Chromium 交互 CI。CI 结果以当前 PR 对应提交为准；签名和真机测试仍待完成，详见 [验证记录](docs/VALIDATION.md)。

创意与需求：吴孟城（Windy Wu）；AI 辅助实现与文案：ChatGPT。

## 先体验

直接打开根目录的 `Preview.html`，或 `Web/index.html`。预览完全本地运行，只向本页文本框输入，不会安装系统键盘。源码、CSS 和词库均在包内，没有 CDN、字体下载或网络依赖。

1. 点击键帽 `n / ㄋ`、`i / ㄧ`、`3 ˇ`，接着点 `h / ㄏ`、`ao / ㄠ`、`3 ˇ`。
2. 组合栏显示 `ㄋㄧˇ ㄏㄠˇ` 和 `nǐ hǎo`；点「你好」提交。
3. 声调可省略，使用「分音节」分开两个音节。省略表示不限声调；轻声用 `5 ˙`。
4. 「繁體／简体」切换词库中的字形；「拼音 开／关」控制键帽提示。
5. 「原文」直接插入注音。空格或换行键在有组合时先选第一个候选，没有候选则保留组合；无组合时才输入空格或换行。
6. 「ABC」「123」提供英文大小写、数字、常用符号；有未提交组合时先选字、插入原文或清空组合。

「清空组合」只清除未提交内容。「清空正文」只出现在网页预览；iOS 键盘不会提供一键清空其他 App 正文的功能。

## 已实现的范围

| 项目 | 当前实现 |
|---|---|
| 键帽 | 37 个注音符号，拼音在上；教学顺序布局，非标准注音硬件键位 |
| 音节 | 409 种有限白名单拼写；整音节转换，不把注音机械替换为英文字母 |
| 候选 | 204 条人工整理的教学词条，精确音节匹配，可按声调过滤 |
| 词组 | 最多 8 个音节；明确分界；包括北京、華盛頓、台北 |
| 简繁 | 从词条选择对应输出，不作整段文章简繁转换 |
| 隐私 | 无网络实现、账号、广告 SDK、输入历史存储或模型训练；不请求完全访问 |
| iOS | SwiftUI 配套 App + UIKit Custom Keyboard Extension；最低部署目标 iOS/iPadOS 16 |
| 可访问性 | 设置按钮文字标签与注音/拼音读屏标签；真机 VoiceOver、动态字号与触控测试待做 |

这是小词库学习原型。暂无通用整句转换、完整人名地名词库、预测、模糊音、自动纠错、用户词频学习、粤语/闽南语、儿化连写或地区读音自动切换。第一声在注音中不显示调号；组合栏的拼音仍显示音调。读音按词汇本调，未实现「一／不」或三声连读的变调显示。

## 在 Mac 上开发和安装

1. 使用支持 iOS 16 或更高 SDK 的 Xcode，打开 `ZhuyinBridge.xcodeproj`。工程没有第三方编译依赖。
2. 对 **ZhuyinBridge** 与 **ZhuyinBridgeKeyboard** 两个 target 选择自己的签名 Team；把示例 Bundle ID 改成自己的唯一值。扩展 ID 保持以 App ID 为前缀，例如 `your.identifier.bridge.Keyboard`。
3. 先选择 iOS 模拟器运行 App，检查引导页、练习框和协议。
4. 真机调试：连接 iPhone/iPad 与 Mac 并配对，按设备提示在「设置 → 隐私与安全性 → 开发者模式」启用、重启并确认，然后由 Xcode 运行。[Apple 开发者模式说明](https://developer.apple.com/documentation/xcode/enabling-developer-mode-on-a-device)
5. 在「设置 → 通用 → 键盘 → 键盘 → 添加新键盘」中启用「注音桥」。回到练习框，用地球键切换。无需允许完全访问。

开发者模式用于运行本地开发签名的软件；它不等于编辑系统自带键盘，也不等于取得 Apple 协议的修改权限。App Store / TestFlight 安装不要求用户开启开发者模式。

```bash
# 从工程根目录运行；Python 3.10+、Node 20+。
python3 Tools/build_data.py
python3 Tools/make_project.py
python3 Tools/build_preview.py
python3 Tools/check_package.py
node --test Tools/test_engine.cjs

# 以下两项需要 Swift / Xcode；尚未在交付环境执行。
swift test
xcodebuild -project ZhuyinBridge.xcodeproj -scheme ZhuyinBridge \
  -sdk iphonesimulator -destination 'generic/platform=iOS Simulator' \
  CODE_SIGNING_ALLOWED=NO build

# 可选浏览器测试，需要本机 Playwright 与 Chromium。
npm install --no-save --ignore-scripts --package-lock=false playwright@1.62.1
npx playwright install chromium
node Tools/test_ui.cjs
```

Apple 会在密码等安全输入框中切回系统键盘；部分应用也会禁止第三方键盘。这不是本项目可以绕开的行为。[Apple 键盘界面说明](https://developer.apple.com/documentation/uikit/configuring-a-custom-keyboard-interface)

## 文件导航

- `Shared/`：iOS 组字状态机与生成的数据；`CoreTests/`：Swift XCTest。
- `App/`：启用说明、练习框、用户协议、开发者蜜语。
- `KeyboardExtension/`：双标键帽、候选栏和系统文本插入。
- `Data/lexicon.tsv`：可编辑教学词库；`Tools/build_data.py`：有限音节表及数据生成器。
- `Web/`：交互预览与独立 JavaScript 参考模型。模型测试不证明 Swift 已通过。
- [用户协议草案](docs/USER_TERMS_DRAFT_ZH.md)、[苹果负责人视角的条款提案](docs/APPLE_POLICY_PROPOSAL_ZH.md)。
- [原型入仓说明](docs/PRE_PR.md)、[可粘贴 PR 草稿](docs/PR_DRAFT.md)、[验证记录](docs/VALIDATION.md)、[数据与来源](docs/SOURCES.md)。

## 开发者蜜语

（ChatGPT好用吗？好用就在AppStore点个五星好评吧！）

按用户原话保留在配套 App 和演示说明页。评价与否不影响任何功能，不自动跳转、索取评价或提交评分。

## 给隔壁的友好喊话

> Android 阵营、华为的朋友：这些年价格战打得爽了吗？下一轮，来比谁能让不同输入习惯的人更容易打字。

这是提案文案，不是已发出的社交媒体 @ 提醒。未实现 Android 或 HarmonyOS 输入法；数据格式可供后续适配参考。

## 仓库集成与许可

本项目位于 `experiments/zhuyin_bridge/`，可独立构建；不导入 MotionBricks 或加载模型。专用工作流为 [Zhuyin Bridge](../../.github/workflows/zhuyin-bridge.yml)，包含资源生成一致性、Node 模型、Swift 核心、iOS 模拟器编译和浏览器预览验证。设备签名与真机验收不由这些检查替代。

本目录新增源码遵循仓库的 Apache-2.0，文档与教学数据遵循 CC-BY-4.0；参见根目录 [LICENSE](../../LICENSE)。用户协议草案是产品使用及隐私文案，不对仓库的开源授权追加限制。第三方标识、Apple SDK 与后续引入的词库仍遵循各自权利和条款。
