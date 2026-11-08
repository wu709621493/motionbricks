const test=require('node:test'),assert=require('node:assert/strict'),path=require('node:path');
const data=require('../Data/bridge.json');
const {BridgeEngine,markTone}=require('../Web/engine.js');
function spell(e,p,t){const s=data.syllables.find(s=>s.pinyin===p);assert.ok(s,p);for(const z of s.zhuyin)assert.ok(e.append(z),z);if(t)assert.ok(e.setTone(t));}
test('37 distinct keys and 409 bidirectional spellings',()=>{
  assert.equal(data.rows.flat().length,37);assert.equal(new Set(data.rows.flat().map(k=>k.symbol)).size,37);
  assert.equal(data.syllables.length,409);assert.equal(new Set(data.syllables.map(s=>s.zhuyin)).size,409);
  for(const s of data.syllables){const e=new BridgeEngine(data);for(const z of s.zhuyin)assert.ok(e.append(z));assert.equal(e.pinyin,s.pinyin);}
});
test('independent spelling fixtures including ü, apical vowels, contractions and zero initials',()=>{
  const fixtures={'ㄓ':'zhi','ㄔ':'chi','ㄕ':'shi','ㄖ':'ri','ㄗ':'zi','ㄘ':'ci','ㄙ':'si','ㄐㄩ':'ju','ㄑㄩㄝ':'que','ㄒㄩㄣ':'xun','ㄌㄩ':'lü','ㄋㄩ':'nü','ㄌㄩㄝ':'lüe','ㄋㄩㄝ':'nüe','ㄧㄡ':'you','ㄌㄧㄡ':'liu','ㄍㄨㄟ':'gui','ㄌㄨㄣ':'lun','ㄨㄟ':'wei','ㄨㄣ':'wen','ㄧㄣ':'yin','ㄧㄥ':'ying','ㄐㄩㄥ':'jiong','ㄩㄥ':'yong','ㄨㄥ':'weng','ㄉㄨㄥ':'dong','ㄧㄢ':'yan','ㄝ':'ê','ㄅㄛ':'bo'};
  for(const[z,p]of Object.entries(fixtures)){const e=new BridgeEngine(data);for(const c of z)e.append(c);assert.equal(e.pinyin,p);}
});
test('every teaching entry reaches candidates in both scripts',()=>{
  for(const entry of data.lexicon){const e=new BridgeEngine(data);for(const r of entry.readings)spell(e,r.slice(0,-1),+r.slice(-1));assert.ok(e.candidates.some(c=>c.text===entry.traditional),entry.traditional);e.simplified=true;assert.ok(e.candidates.some(c=>c.text===entry.simplified),entry.simplified);}
});
test('tones filter homophones; omitted tone differs from neutral',()=>{
  const e=new BridgeEngine(data);spell(e,'ma');assert.ok(e.candidates.length>=4);e.setTone(5);assert.deepEqual(e.candidates.map(c=>c.text),['嗎']);assert.equal(e.zhuyin,'˙ㄇㄚ');e.backspace();assert.ok(e.candidates.length>=4);e.setTone(3);assert.deepEqual(e.candidates.map(c=>c.text),['馬']);
});
test('phrase segmentation, explicit boundary deletion, commit reset',()=>{
  const e=new BridgeEngine(data);spell(e,'ni');e.separate();e.backspace();assert.equal(e.zhuyin,'ㄋㄧ');e.separate();spell(e,'hao');assert.equal(e.commit(0),'你好');assert.equal(e.pending,false);assert.equal(e.backspace(),false);
});
test('invalid input rejects atomically and never becomes guessed characters',()=>{
  const e=new BridgeEngine(data);assert.equal(e.append('x'),false);e.append('ㄅ');assert.equal(e.setTone(1),false);assert.equal(e.append('ㄓ'),false);assert.equal(e.zhuyin,'ㄅ');assert.equal(e.commit(0),null);assert.equal(e.pending,true);assert.equal(e.commitRaw(),'ㄅ');assert.equal(e.pending,false);
});
test('max length survives adversarial extra keys and separators',()=>{
  const e=new BridgeEngine(data);for(let i=0;i<8;i++)spell(e,'ma',1);const before=e.zhuyin;assert.equal(e.append('ㄇ'),false);assert.equal(e.separate(),false);assert.equal(e.zhuyin,before);assert.equal(e.segments.length,8);
});
test('tone accents and simplified duplicate removal',()=>{
  for(const[p,t,want]of [['liu',2,'liú'],['gui',4,'guì'],['lü',4,'lǜ'],['you',3,'yǒu'],['shui',3,'shuǐ'],['ma',5,'ma'],['xue',2,'xué']])assert.equal(markTone(p,t),want);
  const e=new BridgeEngine(data);spell(e,'ni',3);e.simplified=true;assert.equal(e.candidates.filter(c=>c.text==='你').length,1);
});
test('backspace removes tone, symbol, then restores previous segment',()=>{
  const e=new BridgeEngine(data);spell(e,'ni',3);spell(e,'hao',3);e.backspace();assert.equal(e.current.tone,0);e.backspace();assert.equal(e.current.symbols,'ㄏ');e.backspace();assert.equal(e.current.symbols,'');e.backspace();assert.deepEqual(e.current,{symbols:'ㄋㄧ',tone:3});
});
test('all tones and clear state on every finite syllable',()=>{
  for(const s of data.syllables)for(let t=1;t<=5;t++){const e=new BridgeEngine(data);spell(e,s.pinyin,t);assert.equal(e.current.tone,t);e.clear();assert.equal(e.pending,false);assert.equal(e.pinyin,'');assert.deepEqual(e.candidates,[]);}
});
test('malformed tone values do not alter current composition',()=>{
  const e=new BridgeEngine(data);spell(e,'ni',3);for(const t of [0,6,-1,2.5,NaN,'3'])assert.equal(e.setTone(t),false);assert.equal(e.pinyin,'nǐ');
});
