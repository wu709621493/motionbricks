import Foundation

struct BridgeKey: Codable { let symbol: String; let hint: String }
struct BridgeSpelling: Codable { let pinyin: String; let zhuyin: String }
struct BridgeEntry: Codable {
    let readings: [String]
    let traditional: String
    let simplified: String
}
struct BridgeDataset: Codable {
    let version: Int
    let syllables: [BridgeSpelling]
    let rows: [[BridgeKey]]
    let lexicon: [BridgeEntry]
}
struct BridgeSyllable: Equatable {
    var symbols: String
    var tone: Int = 0 // 0 = unspecified; 5 = neutral
    var display: String {
        if tone == 5 { return "˙" + symbols }
        return symbols + [0: "", 1: "", 2: "ˊ", 3: "ˇ", 4: "ˋ"][tone, default: ""]
    }
}
struct BridgeCandidate: Equatable {
    let text: String
    let reading: String
}

/// Finite, deterministic learning IME. Stores composition only in process memory.
final class BridgeEngine {
    static let maxSyllables = 8
    let data = BridgeData.value
    private(set) var completed: [BridgeSyllable] = []
    private(set) var current = BridgeSyllable(symbols: "")
    private(set) var message = "点击注音键，拼音会显示在这里"
    var simplified = false
    private let spelling: [String: String]
    private let prefixes: Set<String>

    init() {
        let pairs = BridgeData.value.syllables
        spelling = Dictionary(uniqueKeysWithValues: pairs.map { ($0.zhuyin, $0.pinyin) })
        prefixes = Set(pairs.flatMap { item in (1...item.zhuyin.count).map { String(item.zhuyin.prefix($0)) } })
    }
    var pending: Bool { !completed.isEmpty || !current.symbols.isEmpty }
    var segments: [BridgeSyllable] { completed + (current.symbols.isEmpty ? [] : [current]) }
    var zhuyin: String { segments.map(\.display).joined(separator: " ") }
    var pinyin: String {
        segments.map { segment in
            guard let p = spelling[segment.symbols] else { return "…" }
            return Self.markTone(p, tone: segment.tone)
        }.joined(separator: " ")
    }
    var candidates: [BridgeCandidate] {
        let input = segments
        guard !input.isEmpty, input.allSatisfy({ spelling[$0.symbols] != nil }) else { return [] }
        var seen = Set<String>()
        return data.lexicon.compactMap { entry in
            guard entry.readings.count == input.count else { return nil }
            for (i, value) in entry.readings.enumerated() {
                let base = String(value.dropLast())
                let tone = Int(String(value.suffix(1)))!
                guard spelling[input[i].symbols] == base, input[i].tone == 0 || input[i].tone == tone else { return nil }
            }
            let text = simplified ? entry.simplified : entry.traditional
            guard seen.insert(text).inserted else { return nil }
            let reading = entry.readings.map { Self.markTone(String($0.dropLast()), tone: Int(String($0.suffix(1)))!) }.joined(separator: " ")
            return BridgeCandidate(text: text, reading: reading)
        }
    }
    @discardableResult func append(_ symbol: String) -> Bool {
        guard data.rows.joined().contains(where: { $0.symbol == symbol }) else { return false }
        let boundary = current.tone != 0
        let next = (boundary ? "" : current.symbols) + symbol
        let count = completed.count + (boundary ? 1 : 0)
        guard count < Self.maxSyllables else { message = "每次最多 8 个音节，请先选字"; return false }
        guard prefixes.contains(next) else { message = "组合不在音节表中；请退格或点「分音节」"; return false }
        if boundary { completed.append(current) }
        current = BridgeSyllable(symbols: next)
        message = "可省略声调；词组请用「分音节」或先选声调"
        return true
    }
    @discardableResult func setTone(_ tone: Int) -> Bool {
        guard (1...5).contains(tone), spelling[current.symbols] != nil else {
            message = "请先输入完整音节，再选声调"; return false
        }
        current.tone = tone
        message = "已选声调；下一键开始新音节"
        return true
    }
    @discardableResult func separate() -> Bool {
        guard spelling[current.symbols] != nil else { message = "请先完成当前音节"; return false }
        guard completed.count + 1 < Self.maxSyllables else { message = "每次最多 8 个音节，请先选字"; return false }
        completed.append(current)
        current = BridgeSyllable(symbols: "")
        message = "继续下一个音节，或点击候选字"
        return true
    }
    /// False means there is no composition: caller may delete from the host.
    @discardableResult func backspace() -> Bool {
        if current.tone != 0 { current.tone = 0 }
        else if !current.symbols.isEmpty { current.symbols.removeLast() }
        else if let last = completed.popLast() { current = last }
        else { return false }
        message = "已退格"
        return true
    }
    func clear() {
        completed = []; current = BridgeSyllable(symbols: "")
        message = "点击注音键，拼音会显示在这里"
    }
    func commit(index: Int) -> String? {
        let values = candidates
        guard values.indices.contains(index) else { message = "小词库暂无候选；可点「注音原文」"; return nil }
        let text = values[index].text
        clear()
        return text
    }
    func commitRaw() -> String? {
        guard pending else { return nil }
        let text = zhuyin
        clear()
        return text
    }
    static func markTone(_ pinyin: String, tone: Int) -> String {
        guard (1...4).contains(tone) else { return pinyin }
        var chars = Array(pinyin)
        let index: Int?
        if let a = chars.firstIndex(of: "a") { index = a }
        else if let e = chars.firstIndex(of: "e") { index = e }
        else if pinyin.contains("ou") { index = chars.firstIndex(of: "o") }
        else { index = chars.lastIndex(where: { "iouüê".contains($0) }) }
        guard let i = index else { return pinyin }
        let vowels: [Character: [String]] = [
            "a": ["ā", "á", "ǎ", "à"], "e": ["ē", "é", "ě", "è"],
            "i": ["ī", "í", "ǐ", "ì"], "o": ["ō", "ó", "ǒ", "ò"],
            "u": ["ū", "ú", "ǔ", "ù"], "ü": ["ǖ", "ǘ", "ǚ", "ǜ"],
            "ê": ["ê̄", "ế", "ê̌", "ề"]
        ]
        guard let marked = vowels[chars[i]] else { return pinyin }
        chars[i] = Character(marked[tone - 1])
        return String(chars)
    }
}
