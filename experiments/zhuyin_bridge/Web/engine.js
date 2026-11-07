/* Reference model for the preview. Shared data, independent Swift implementation.
   Node tests validate this JS model, NOT the uncompiled iOS executable. */
(function (root) {
  'use strict';
  const marks = {a:['ā','á','ǎ','à'],e:['ē','é','ě','è'],i:['ī','í','ǐ','ì'],o:['ō','ó','ǒ','ò'],u:['ū','ú','ǔ','ù'],ü:['ǖ','ǘ','ǚ','ǜ'],ê:['ê̄','ế','ê̌','ề']};
  function markTone(pinyin,tone) {
    if(tone<1 || tone>4) return pinyin;
    let i=pinyin.indexOf('a');
    if(i<0) i=pinyin.indexOf('e');
    if(i<0 && pinyin.includes('ou')) i=pinyin.indexOf('o');
    if(i<0) for(let k=pinyin.length-1;k>=0;k--) if('iouüê'.includes(pinyin[k])) { i=k; break; }
    return i<0 ? pinyin : pinyin.slice(0,i)+marks[pinyin[i]][tone-1]+pinyin.slice(i+1);
  }
  function display(s) { return s.tone===5 ? '˙'+s.symbols : s.symbols+({2:'ˊ',3:'ˇ',4:'ˋ'}[s.tone]||''); }
  class BridgeEngine {
    constructor(data) {
      this.data=data; this.simplified=false;
      this.spelling=new Map(data.syllables.map(s=>[s.zhuyin,s.pinyin]));
      this.prefixes=new Set(data.syllables.flatMap(s=>[...s.zhuyin].map((_,i)=>s.zhuyin.slice(0,i+1))));
      this.clear();
    }
    clear(){this.completed=[];this.current={symbols:'',tone:0};this.message='点击注音键，拼音会显示在这里';}
    get pending(){return this.completed.length>0 || this.current.symbols!=='';}
    get segments(){return this.completed.concat(this.current.symbols?[this.current]:[]);}
    get zhuyin(){return this.segments.map(display).join(' ');}
    get pinyin(){return this.segments.map(s=>this.spelling.has(s.symbols)?markTone(this.spelling.get(s.symbols),s.tone):'…').join(' ');}
    get candidates(){
      const parts=this.segments, seen=new Set();
      if(!parts.length || parts.some(s=>!this.spelling.has(s.symbols)))return [];
      return this.data.lexicon.filter(e=>e.readings.length===parts.length && e.readings.every((r,i)=>r.slice(0,-1)===this.spelling.get(parts[i].symbols) && (!parts[i].tone || parts[i].tone===+r.slice(-1))))
        .map(e=>({text:this.simplified?e.simplified:e.traditional,reading:e.readings.map(r=>markTone(r.slice(0,-1),+r.slice(-1))).join(' ')}))
        .filter(e=>{if(seen.has(e.text))return false;seen.add(e.text);return true;});
    }
    append(symbol){
      if(!this.data.rows.flat().some(k=>k.symbol===symbol))return false;
      const boundary=this.current.tone!==0, next=(boundary?'':this.current.symbols)+symbol;
      if(this.completed.length+(boundary?1:0)>=8){this.message='每次最多 8 个音节，请先选字';return false;}
      if(!this.prefixes.has(next)){this.message='组合不在音节表中；请退格或点「分音节」';return false;}
      if(boundary)this.completed.push({...this.current});
      this.current={symbols:next,tone:0};this.message='可省略声调；词组请用「分音节」或先选声调';return true;
    }
    setTone(tone){
      if(!Number.isInteger(tone)||tone<1||tone>5||!this.spelling.has(this.current.symbols)){this.message='请先输入完整音节，再选声调';return false;}
      this.current.tone=tone;this.message='已选声调；下一键开始新音节';return true;
    }
    separate(){
      if(!this.spelling.has(this.current.symbols)){this.message='请先完成当前音节';return false;}
      if(this.completed.length+1>=8){this.message='每次最多 8 个音节，请先选字';return false;}
      this.completed.push({...this.current});this.current={symbols:'',tone:0};this.message='继续下一个音节，或点击候选字';return true;
    }
    backspace(){
      if(this.current.tone)this.current.tone=0;
      else if(this.current.symbols)this.current.symbols=this.current.symbols.slice(0,-1);
      else if(this.completed.length)this.current=this.completed.pop();
      else return false;
      this.message='已退格';return true;
    }
    commit(index){
      const candidate=this.candidates[index];
      if(!candidate){this.message='小词库暂无候选；可点「注音原文」';return null;}
      this.clear();return candidate.text;
    }
    commitRaw(){if(!this.pending)return null;const text=this.zhuyin;this.clear();return text;}
  }
  root.BridgeEngine=BridgeEngine;root.bridgeMarkTone=markTone;
  if(typeof module!=='undefined')module.exports={BridgeEngine,markTone};
})(globalThis);
