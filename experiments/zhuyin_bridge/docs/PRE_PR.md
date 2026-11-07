# 注音桥原型审阅与入仓说明

2026-11-08 · 从 pre-PR 0.1 审阅包迁入 MotionBricks fork。

项目位于 `experiments/zhuyin_bridge/`，按独立输入法实验组织。提供 Xcode 工程、离线网页预览和协议草案。源码与网页不依赖 MotionBricks 的模型或运行环境。

## 审阅顺序

1. 打开 `Preview.html`，查看双标键帽、拼写变化和候选交互。
2. 检查 `Shared/BridgeEngine.swift` 与教学词库；数据来自显式有限表，不调用系统私有中文词库。
3. 查看 PR 上的 `Zhuyin Bridge` 工作流；单独核对资源、参考模型、Swift 测试、iOS 模拟器编译和浏览器测试的结果。
4. 检查 `USER_TERMS_DRAFT_ZH.md` 是否与实现一致，再读 `APPLE_POLICY_PROPOSAL_ZH.md`。
5. 按 `VALIDATION.md` 的设备验收步骤，在实际 iPhone/iPad 上补验布局、输入框切换与无障碍交互。

## 入仓完成的整理

- 根 README 增加入口，输入法代码集中在实验目录。
- 将 pre-PR 示例 CI 改为根目录独立工作流，资源再生成后必须没有差异。
- 自动同步 App 内协议与 Markdown 源文，保留开发者蜜语原句。
- 添加读取上下文、联网、持久化与完全访问相关的静态检查，以及 8 个 Swift XCTest 方法、11 项 Node 测试和浏览器交互脚本。
- 适用仓库既有源码/文档许可；产品用户协议草案不缩减开源许可授予的权利。

给 Android／华为的喊话保留在说明与提案中。未向企业或社交账号发送消息，没有改动 Apple 的实际条款。

## 原型范围

204 条教学词库不覆盖日用完整词汇；没有整句预测、用户学习词库、Android 或 HarmonyOS 实现。签名、真机输入生命周期、横屏/浮动键盘、VoiceOver 和用户上手效果需要另外验证。CI 的编译通过也不等于这些设备测试已经完成。

公开分发 App 前仍需填明发布主体和联系方式、准备图标与商店素材，并核对实际分发安排。本 PR 不执行 App Store 发布或仓库合并。
