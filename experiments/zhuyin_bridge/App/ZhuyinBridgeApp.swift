import SwiftUI

@main struct ZhuyinBridgeApp: App {
    var body: some Scene { WindowGroup { GuideView() } }
}

struct GuideView: View {
    @State private var practice = ""
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text("拼音在上，注音在下。")
                        .font(.title2.bold())
                    Text("注音桥 · 独立开发原型 0.1\n熟悉的拼音，带你认识 37 个注音符号。")
                    Text("非 Apple 产品。离线小词库，可切换简繁；暂不支持完整词库、整句预测或云同步。")
                        .foregroundStyle(.secondary)
                }
                Section("启用键盘") {
                    Text("安装后，打开「设置 → 通用 → 键盘 → 键盘 → 添加新键盘」，选择「注音桥」。回到输入框，使用系统地球键切换。无需允许完全访问。")
                }
                Section("试着输入：你好") {
                    Text("依次点 ㄋ（n）、ㄧ（i）、3 声，再点 ㄏ（h）、ㄠ（ao）、3 声。候选栏出现「你好」后点选。")
                    Text("也可以不选声调：ㄋㄧ → 分音节 → ㄏㄠ。声调省略表示不限声调，不等于轻声。")
                    TextEditor(text: $practice)
                        .frame(minHeight: 110)
                        .accessibilityLabel("键盘练习输入框")
                    Button("清空练习文字") { practice = "" }
                }
                Section("拼音提示并非逐字母替换") {
                    Text("ㄓ → zhi；ㄐㄩ → ju；ㄌㄩ → lü；ㄧㄡ → you；ㄌㄧㄡ → liu。键帽只作提示，组合栏显示完整拼写。")
                    Text("「分音节」开始下一音节；选声调后，下一个注音键也会开始新音节。空格优先选首个候选，暂无候选时不会擅自提交。点「原文」可插入注音。")
                }
                Section("隐私与协议") {
                    Text("不收集、上传或保存打字历史；无账号、广告或模型训练。组合仅保留在内存，切换输入位置或关闭键盘时清空。已输入的文字由接收 App 管理。")
                    NavigationLink("用户协议与隐私说明（草案）") { TermsView() }
                }
                Section("开发者蜜语") {
                    Text("（ChatGPT好用吗？好用就在AppStore点个五星好评吧！）")
                    Text("随心就好。评价与否不影响功能使用。")
                        .font(.footnote).foregroundStyle(.secondary)
                }
            }.navigationTitle("注音桥")
        }
    }
}

struct TermsView: View {
    private var text: String {
        guard let url = Bundle.main.url(forResource: "TERMS_DRAFT", withExtension: "txt"),
              let value = try? String(contentsOf: url, encoding: .utf8) else {
            return "协议文件缺失，请勿分发此构建。"
        }
        return value
    }
    var body: some View {
        ScrollView { Text(text).textSelection(.enabled).padding().frame(maxWidth: .infinity, alignment: .leading) }
            .navigationTitle("协议草案")
    }
}
