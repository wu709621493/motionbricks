'use strict';
const engine=new BridgeEngine(BRIDGE_DATA);
const $=id=>document.getElementById(id);
let hints=true, mode='zhuyin', uppercase=false;
function insert(text){if(text==null)return;const el=$('output'),start=el.selectionStart,end=el.selectionEnd;el.setRangeText(text,start,end,'end');}
function render(){
  $('pinyin').textContent=engine.pinyin||'跟着拼音，认识注音';
  $('zhuyin').textContent=engine.zhuyin||'ㄅ ㄆ ㄇ ㄈ';
  $('status').textContent=engine.message;
  $('script').textContent=engine.simplified?'简体':'繁體';
  $('hints').textContent=hints?'拼音 开':'拼音 关';$('hints').classList.toggle('active',hints);
  $('mode').textContent=mode==='zhuyin'?'ABC':'注音';
  $('tones').classList.toggle('hidden',mode!=='zhuyin');
  $('shift').classList.toggle('hidden',mode!=='abc');$('shift').textContent=uppercase?'⇪':'⇧';
  const box=$('candidates');box.replaceChildren();
  const values=engine.candidates;
  values.forEach((c,i)=>{const b=document.createElement('button');b.textContent=c.text;b.title=c.reading;b.setAttribute('aria-label',c.text+' '+c.reading);b.onclick=()=>{insert(engine.commit(i));render();};box.append(b);});
  if(!values.length){const t=document.createElement('span');t.className='empty';t.textContent=engine.pending?'小词库暂无候选；可用「原文」插入注音':'离线学习版 · 简繁可切换';box.append(t);}
}
function renderKeys(){
  $('keys').replaceChildren();
  const rows=mode==='zhuyin'?BRIDGE_DATA.rows:(mode==='abc'?['qwertyuiop','asdfghjkl','zxcvbnm','.,@?!\'-_/']:['1234567890','-/:;()$&@"','.,?!\'[]{}#%','_\\|~<>^*+=`']).map(s=>[...s]);
  rows.forEach(keys=>{const row=document.createElement('div');row.className='keyrow';keys.forEach(k=>{
    const b=document.createElement('button');b.className='key';
    if(mode==='zhuyin'){
      if(hints){const h=document.createElement('span');h.className='hint';h.textContent=k.hint;b.append(h);}
      const z=document.createElement('span');z.className='symbol';z.textContent=k.symbol;b.append(z);b.setAttribute('aria-label',k.symbol+'，拼音提示 '+k.hint);b.dataset.symbol=k.symbol;
      b.onclick=()=>{engine.append(k.symbol);render();};
    }else{const value=mode==='abc'&&uppercase?k.toUpperCase():k;b.textContent=value;b.classList.add('ascii');b.onclick=()=>insert(value);}
    row.append(b);
  });$('keys').append(row);});
}
function changeMode(next){if(engine.pending){engine.message='请先选字、插入注音原文，或清空组合';render();return;}mode=next;renderKeys();render();}
function finish(value){if(engine.pending)insert(engine.commit(0));else insert(value);render();}
$('script').onclick=()=>{engine.simplified=!engine.simplified;render();};
$('hints').onclick=()=>{hints=!hints;renderKeys();render();};
$('mode').onclick=()=>changeMode(mode==='zhuyin'?'abc':'zhuyin');
$('numbers').onclick=()=>changeMode('numbers');
$('shift').onclick=()=>{uppercase=!uppercase;renderKeys();render();};
$('clear').onclick=()=>{engine.clear();render();};
$('erase').onclick=()=>{$('output').value='';engine.clear();render();};
$('raw').onclick=()=>{insert(engine.commitRaw());render();};
$('separate').onclick=()=>{engine.separate();render();};
$('delete').onclick=()=>{
  if(!engine.backspace()){
    const el=$('output');const start=el.selectionStart,end=el.selectionEnd;
    if(start!==end)el.setRangeText('',start,end,'end');
    else if(start>0){
      const segments=[...new Intl.Segmenter(undefined,{granularity:'grapheme'}).segment(el.value.slice(0,start))];
      el.setRangeText('',segments.at(-1).index,start,'end');
    }
  }render();
};
$('space').onclick=()=>finish(' ');$('enter').onclick=()=>finish('\n');
document.querySelectorAll('[data-tone]').forEach(b=>b.onclick=()=>{engine.setTone(+b.dataset.tone);render();});
document.querySelectorAll('[data-example]').forEach(b=>b.onclick=()=>{
  engine.clear();mode='zhuyin';renderKeys();
  for(const r of b.dataset.example.split(' ')){
    const item=BRIDGE_DATA.syllables.find(s=>s.pinyin===r.slice(0,-1));
    for(const symbol of item.zhuyin)engine.append(symbol);engine.setTone(+r.slice(-1));
  }render();$('toast').textContent='例子已放入组合栏；点候选字即可提交。';
});
$('output').addEventListener('pointerdown',()=>{engine.clear();render();});
$('output').addEventListener('input',()=>{engine.clear();render();});
document.addEventListener('visibilitychange',()=>{if(document.hidden){engine.clear();render();}});
renderKeys();render();
