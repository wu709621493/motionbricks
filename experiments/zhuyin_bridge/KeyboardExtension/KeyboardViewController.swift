import UIKit

final class KeyboardViewController: UIInputViewController {
    private let engine = BridgeEngine()
    private let stack = UIStackView()
    private let composition = UILabel()
    private let candidates = UIStackView()
    private let keyRows = UIStackView()
    private var globe: UIButton!
    private var scriptButton: UIButton!
    private var hintsButton: UIButton!
    private var alphabetButton: UIButton!
    private var shiftButton: UIButton!
    private var toneRow: UIStackView!
    private var mode = "zhuyin"
    private var showHints = true
    private var uppercase = false

    override func viewDidLoad() {
        super.viewDidLoad()
        view.backgroundColor = .systemGroupedBackground
        stack.axis = .vertical
        stack.spacing = 5
        stack.translatesAutoresizingMaskIntoConstraints = false
        view.addSubview(stack)
        NSLayoutConstraint.activate([
            stack.leadingAnchor.constraint(equalTo: view.leadingAnchor, constant: 5),
            stack.trailingAnchor.constraint(equalTo: view.trailingAnchor, constant: -5),
            stack.topAnchor.constraint(equalTo: view.topAnchor, constant: 5),
            stack.bottomAnchor.constraint(equalTo: view.bottomAnchor, constant: -5)
        ])
        let height = view.heightAnchor.constraint(equalToConstant: 438)
        height.priority = .defaultHigh
        height.isActive = true

        scriptButton = button("繁體") { [weak self] in
            guard let self else { return }
            self.engine.simplified.toggle(); self.refresh()
        }
        hintsButton = button("拼音 开") { [weak self] in
            guard let self else { return }
            self.showHints.toggle(); self.renderKeys(); self.refresh()
        }
        alphabetButton = button("ABC") { [weak self] in
            guard let self else { return }
            self.changeMode(self.mode == "zhuyin" ? "abc" : "zhuyin")
        }
        let numberButton = button("123") { [weak self] in self?.changeMode("numbers") }
        let clear = button("清空") { [weak self] in self?.engine.clear(); self?.refresh() }
        let toolbar = row([scriptButton, hintsButton, alphabetButton, numberButton, clear])
        toolbar.heightAnchor.constraint(equalToConstant: 32).isActive = true
        stack.addArrangedSubview(toolbar)

        composition.numberOfLines = 2
        composition.font = .systemFont(ofSize: 14)
        composition.textColor = .label
        composition.adjustsFontSizeToFitWidth = true
        composition.minimumScaleFactor = 0.7
        composition.heightAnchor.constraint(equalToConstant: 42).isActive = true
        stack.addArrangedSubview(composition)

        let scroller = UIScrollView()
        scroller.showsHorizontalScrollIndicator = false
        scroller.heightAnchor.constraint(equalToConstant: 42).isActive = true
        candidates.axis = .horizontal; candidates.spacing = 6
        candidates.translatesAutoresizingMaskIntoConstraints = false
        scroller.addSubview(candidates)
        NSLayoutConstraint.activate([
            candidates.leadingAnchor.constraint(equalTo: scroller.contentLayoutGuide.leadingAnchor),
            candidates.trailingAnchor.constraint(equalTo: scroller.contentLayoutGuide.trailingAnchor),
            candidates.topAnchor.constraint(equalTo: scroller.contentLayoutGuide.topAnchor),
            candidates.bottomAnchor.constraint(equalTo: scroller.contentLayoutGuide.bottomAnchor),
            candidates.heightAnchor.constraint(equalTo: scroller.frameLayoutGuide.heightAnchor)
        ])
        stack.addArrangedSubview(scroller)

        let toneLabels = ["1 ˉ", "2 ˊ", "3 ˇ", "4 ˋ", "5 ˙"]
        var toneButtons = toneLabels.enumerated().map { i, label in
            button(label, accessibility: "第 \(i + 1) 声，5 为轻声") { [weak self] in
                self?.engine.setTone(i + 1); self?.refresh()
            }
        }
        toneButtons.append(button("分音节") { [weak self] in self?.engine.separate(); self?.refresh() })
        toneButtons.append(button("原文", accessibility: "插入注音原文") { [weak self] in
            guard let self, let text = self.engine.commitRaw() else { return }
            self.textDocumentProxy.insertText(text); self.refresh()
        })
        toneRow = row(toneButtons)
        toneRow.heightAnchor.constraint(equalToConstant: 34).isActive = true
        stack.addArrangedSubview(toneRow)

        keyRows.axis = .vertical; keyRows.distribution = .fillEqually; keyRows.spacing = 5
        stack.addArrangedSubview(keyRows)
        renderKeys()

        globe = UIButton(type: .system)
        style(globe); globe.setTitle("🌐", for: .normal)
        globe.accessibilityLabel = "切换到其他键盘，长按显示列表"
        globe.addTarget(self, action: #selector(handleInputModeList(from:with:)), for: .allTouchEvents)
        shiftButton = button("⇧", accessibility: "切换英文字母大小写") { [weak self] in
            guard let self else { return }
            self.uppercase.toggle(); self.renderKeys(); self.refresh()
        }
        let delete = button("⌫", accessibility: "退格") { [weak self] in
            guard let self else { return }
            if !self.engine.backspace() { self.textDocumentProxy.deleteBackward() }
            self.refresh()
        }
        let space = button("空格 / 选字") { [weak self] in self?.finishOrInsert(" ") }
        let enter = button("换行") { [weak self] in self?.finishOrInsert("\n") }
        let hide = button("收起") { [weak self] in
            self?.engine.clear(); self?.dismissKeyboard()
        }
        let bottom = row([globe, shiftButton, delete, space, enter, hide])
        bottom.heightAnchor.constraint(equalToConstant: 42).isActive = true
        stack.addArrangedSubview(bottom)
        refresh()
    }

    override func viewWillLayoutSubviews() {
        super.viewWillLayoutSubviews()
        globe?.isHidden = !needsInputModeSwitchKey
    }
    override func viewWillAppear(_ animated: Bool) {
        super.viewWillAppear(animated)
        engine.clear()
        if isViewLoaded { refresh() }
    }
    override func viewWillDisappear(_ animated: Bool) {
        engine.clear()
        if isViewLoaded { refresh() }
        super.viewWillDisappear(animated)
    }
    override func textWillChange(_ textInput: UITextInput?) {
        // An external selection/field change must not carry pending text into another field.
        engine.clear()
        if isViewLoaded { refresh() }
    }
    private func changeMode(_ value: String) {
        guard !engine.pending else { composition.text = "请先选字、插入注音原文，或清空组合"; return }
        mode = value; renderKeys(); refresh()
    }
    private func finishOrInsert(_ value: String) {
        if engine.pending {
            if let text = engine.commit(index: 0) { textDocumentProxy.insertText(text) }
        } else { textDocumentProxy.insertText(value) }
        refresh()
    }
    private func renderKeys() {
        keyRows.arrangedSubviews.forEach { $0.removeFromSuperview() }
        if mode == "zhuyin" {
            for keys in engine.data.rows {
                let buttons = keys.map { key -> UIButton in
                    let b = button("", accessibility: "\(key.symbol)，拼音提示 \(key.hint)") { [weak self] in
                        self?.engine.append(key.symbol); self?.refresh()
                    }
                    let text = NSMutableAttributedString(string: "")
                    if showHints {
                        text.append(NSAttributedString(string: key.hint + "\n", attributes: [.font: UIFont.systemFont(ofSize: 11, weight: .medium), .foregroundColor: UIColor.systemBlue]))
                    }
                    text.append(NSAttributedString(string: key.symbol, attributes: [.font: UIFont.systemFont(ofSize: 22), .foregroundColor: UIColor.label]))
                    b.setAttributedTitle(text, for: .normal)
                    return b
                }
                keyRows.addArrangedSubview(row(buttons))
            }
        } else {
            let strings = mode == "numbers"
                ? ["1234567890", "-/:;()$&@\"", ".,?!'[]{}#%", "_\\|~<>^*+=`"]
                : ["qwertyuiop", "asdfghjkl", "zxcvbnm", ".,@?!'-_/"]
            for keys in strings {
                keyRows.addArrangedSubview(row(keys.map { character in
                    let value = mode == "abc" && uppercase ? String(character).uppercased() : String(character)
                    return button(value) { [weak self] in self?.textDocumentProxy.insertText(value) }
                }))
            }
        }
    }
    private func refresh() {
        composition.text = engine.pending ? engine.zhuyin + "   ·   " + engine.pinyin + "\n" + engine.message : engine.message
        scriptButton?.setTitle(engine.simplified ? "简体" : "繁體", for: .normal)
        hintsButton?.setTitle(showHints ? "拼音 开" : "拼音 关", for: .normal)
        alphabetButton?.setTitle(mode == "zhuyin" ? "ABC" : "注音", for: .normal)
        shiftButton?.isHidden = mode != "abc"
        shiftButton?.setTitle(uppercase ? "⇪" : "⇧", for: .normal)
        toneRow?.isHidden = mode != "zhuyin"
        candidates.arrangedSubviews.forEach { $0.removeFromSuperview() }
        let values = engine.candidates
        for (index, candidate) in values.enumerated() {
            let b = button(candidate.text, accessibility: "\(candidate.text)，\(candidate.reading)") { [weak self] in
                guard let self, let text = self.engine.commit(index: index) else { return }
                self.textDocumentProxy.insertText(text); self.refresh()
            }
            b.widthAnchor.constraint(greaterThanOrEqualToConstant: max(52, CGFloat(candidate.text.count) * 25)).isActive = true
            candidates.addArrangedSubview(b)
        }
        if values.isEmpty {
            let note = UILabel()
            note.font = .systemFont(ofSize: 13); note.textColor = .secondaryLabel
            note.text = engine.pending ? "演示词库暂无候选；「原文」可插入注音" : "离线学习版 · 简繁可切换"
            candidates.addArrangedSubview(note)
        }
    }
    private func row(_ buttons: [UIButton]) -> UIStackView {
        let s = UIStackView(arrangedSubviews: buttons)
        s.axis = .horizontal; s.spacing = 4; s.distribution = .fillEqually
        return s
    }
    private func style(_ b: UIButton) {
        b.backgroundColor = .secondarySystemGroupedBackground
        b.setTitleColor(.label, for: .normal)
        b.layer.cornerRadius = 6
        b.titleLabel?.font = .systemFont(ofSize: 13)
        b.titleLabel?.numberOfLines = 2
        b.titleLabel?.textAlignment = .center
        b.titleLabel?.adjustsFontSizeToFitWidth = true
        b.titleLabel?.minimumScaleFactor = 0.65
    }
    private func button(_ title: String, accessibility: String? = nil, action: @escaping () -> Void) -> UIButton {
        let b = UIButton(type: .system)
        style(b); b.setTitle(title, for: .normal)
        b.accessibilityLabel = accessibility ?? title
        b.addAction(UIAction { _ in action() }, for: .touchUpInside)
        return b
    }
}
