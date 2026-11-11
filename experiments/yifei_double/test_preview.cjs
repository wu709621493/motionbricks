// SPDX-License-Identifier: Apache-2.0
// Logic-only harness: this is not a browser or layout test.
const fs=require('node:fs');
const vm=require('node:vm');
const assert=require('node:assert/strict');
const html=fs.readFileSync(require('node:path').join(__dirname,'output','Yifei_Double_Audition.html'),'utf8');
const script=html.match(/<script>([\s\S]*?)<\/script>/)[1];
new vm.Script(script);
const elements={};
function element(selector){
  return elements[selector]??=( {value:'0',checked:false,textContent:'',listeners:{},addEventListener(name,fn){this.listeners[name]=fn;}} );
}
for(const key of ['play','mirror','delay','angle','time-slider','phase','time','rms','delay-label','angle-label'])element(`[data-${key}]`);
element('[data-delay]').value='.3';element('[data-angle]').value='15';
element('.cue');
let draws=0;
const context=new Proxy({}, {get:(t,k)=>t[k]??((...args)=>{assert(args.every(x=>typeof x!=='number'||Number.isFinite(x)));if(k==='stroke')draws++;}),set:(t,k,v)=>(t[k]=v,true)});
elements.canvas={clientWidth:327,clientHeight:290,width:0,height:0,getContext:()=>context};
const root={querySelector:element,dataset:{},isConnected:true};
let callbacks=new Map(),id=0;
const sandbox={document:{getElementById:()=>root,addEventListener(){}},window:{devicePixelRatio:1},getComputedStyle:()=>({getPropertyValue:()=> '#888888'}),ResizeObserver:class{constructor(f){this.f=f}observe(){this.f()}},requestAnimationFrame:f=>{callbacks.set(++id,f);return id},cancelAnimationFrame:i=>callbacks.delete(i)};
vm.runInNewContext(script,sandbox);
function input(key,value){const el=element(`[data-${key}]`);el.value=String(value);el.listeners.input({target:el});}
function click(){element('[data-play]').listeners.click();}
function tick(t){const pending=[...callbacks.values()];callbacks.clear();pending.forEach(f=>f(t));}
input('time-slider',2.2);input('delay',0);assert(+root.dataset.rms<1e-5);
input('delay',.3);assert(+root.dataset.rms>1);
input('time-slider',9.5);input('delay',0);assert(+root.dataset.rms<1e-5);
element('[data-mirror]').checked=true;element('[data-mirror]').listeners.input();assert(+root.dataset.rms>1);
click();tick(0);tick(100);assert(+root.dataset.time>9.5);click();assert.equal(callbacks.size,0);
input('time-slider',12);click();tick(200);tick(300);assert(+root.dataset.time<1);click();
assert(draws>0);
console.log(JSON.stringify({javascript_syntax:'PASS',mocked_dom_logic:'PASS',zero_delay:'PASS',delay_effect:'PASS',mirror:'PASS',play_pause_restart:'PASS',canvas_coordinates_finite:'PASS',browser_render:'NOT_RUN'}));
