import XCTest
@testable import ZhuyinBridgeCore

final class BridgeEngineTests: XCTestCase {
    func testSpellingExceptions() {
        for (z,p) in [("ㄓ","zhi"),("ㄐㄩ","ju"),("ㄩ","yu"),("ㄧㄡ","you"),("ㄌㄧㄡ","liu"),("ㄍㄨㄟ","gui"),("ㄌㄩ","lü"),("ㄌㄩㄝ","lüe"),("ㄐㄩㄥ","jiong"),("ㄩㄥ","yong"),("ㄨㄥ","weng")] {
            let engine=BridgeEngine()
            for s in z { XCTAssertTrue(engine.append(String(s))) }
            XCTAssertEqual(engine.pinyin,p)
        }
    }
    func testToneAndPhraseCommit() {
        let e=BridgeEngine()
        for z in "ㄋㄧ" { XCTAssertTrue(e.append(String(z))) }
        XCTAssertTrue(e.setTone(3))
        for z in "ㄏㄠ" { XCTAssertTrue(e.append(String(z))) }
        XCTAssertTrue(e.setTone(3))
        XCTAssertEqual(e.pinyin,"nǐ hǎo")
        XCTAssertEqual(e.commit(index:0),"你好")
        XCTAssertFalse(e.pending)
    }
    func testEveryDictionaryReading() {
        let data=BridgeData.value
        let mapping=Dictionary(uniqueKeysWithValues:data.syllables.map{($0.pinyin,$0.zhuyin)})
        for entry in data.lexicon {
            let e=BridgeEngine()
            for reading in entry.readings {
                for z in mapping[String(reading.dropLast())]! { XCTAssertTrue(e.append(String(z))) }
                XCTAssertTrue(e.setTone(Int(String(reading.suffix(1)))!))
            }
            XCTAssertTrue(e.candidates.contains{$0.text==entry.traditional},entry.traditional)
            e.simplified=true
            XCTAssertTrue(e.candidates.contains{$0.text==entry.simplified},entry.simplified)
        }
    }
    func testDeleteRejectAndRaw() {
        let e=BridgeEngine()
        XCTAssertFalse(e.backspace())
        XCTAssertTrue(e.append("ㄅ"))
        XCTAssertFalse(e.setTone(2))
        XCTAssertFalse(e.append("ㄓ"))
        XCTAssertEqual(e.zhuyin,"ㄅ")
        XCTAssertEqual(e.commitRaw(),"ㄅ")
        XCTAssertFalse(e.pending)
        XCTAssertNil(e.commit(index:0))
    }
    func testNeutralToneAndUnspecifiedDiffer() {
        let e=BridgeEngine();for s in "ㄇㄚ"{e.append(String(s))}
        XCTAssertGreaterThan(e.candidates.count,1)
        e.setTone(5)
        XCTAssertEqual(e.zhuyin,"˙ㄇㄚ")
        XCTAssertEqual(e.candidates.map(\.text),["嗎"])
        e.backspace();XCTAssertGreaterThan(e.candidates.count,1)
    }
    func testTonePlacement() {
        for (p,t,expected) in [("liu",2,"liú"),("gui",4,"guì"),("lü",4,"lǜ"),("you",3,"yǒu"),("ma",5,"ma")] {
            XCTAssertEqual(BridgeEngine.markTone(p,tone:t),expected)
        }
    }
    func testLengthBoundIsAtomic() {
        let e=BridgeEngine()
        for _ in 0..<8 { e.append("ㄇ");e.append("ㄚ");e.setTone(1) }
        let before=e.zhuyin
        XCTAssertFalse(e.append("ㄇ"));XCTAssertEqual(e.zhuyin,before)
        XCTAssertFalse(e.separate());XCTAssertEqual(e.zhuyin,before)
    }
    func testUnspecifiedPhraseAndBoundaryDeletion() {
        let e=BridgeEngine()
        for z in "ㄋㄧ"{e.append(String(z))};XCTAssertTrue(e.separate())
        XCTAssertTrue(e.backspace());XCTAssertEqual(e.zhuyin,"ㄋㄧ")
        e.separate();for z in "ㄏㄠ"{e.append(String(z))}
        XCTAssertEqual(e.commit(index:0),"你好")
    }
}
