"""Self-contained HTML replay of Python-generated roach-home observations."""
import json


def render_html(result: dict) -> str:
    # JSON lives in an inert script node; user-supplied room names cannot close it.
    payload = json.dumps(result, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    payload = payload.replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    return TEMPLATE.replace("__RUN_DATA__", payload)


TEMPLATE = r'''<!doctype html>
<html lang="zh-CN"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>虚拟民宅 · 蟑螂行为观察</title>
<style>
:root{color-scheme:dark;--bg:#101a1b;--panel:#172527;--line:#304345;--ink:#e5eee8;--muted:#9caaa4;--green:#b7d78d;--copper:#efad72}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 system-ui,sans-serif}
main{max-width:1240px;margin:auto;padding:32px}header{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:24px}
.eyebrow{font-size:11px;letter-spacing:.22em;color:var(--green)}h1{font-size:30px;font-weight:550;margin:5px 0}p{margin:5px 0;color:var(--muted)}
.badge{border:1px solid #647950;border-radius:30px;color:var(--green);font-size:12px;padding:7px 13px;white-space:nowrap}
.layout{display:grid;grid-template-columns:minmax(0,1fr) 265px;gap:20px}.panel{background:var(--panel);border:1px solid var(--line);border-radius:16px;overflow:hidden}
.bar{padding:16px 20px;display:flex;justify-content:space-between;align-items:center;gap:12px;border-bottom:1px solid var(--line)}
canvas{display:block;width:100%;height:auto}#stage{padding:8px;background:#142022}.controls{padding:18px 20px;border-top:1px solid var(--line)}
button,select{font:inherit;color:var(--ink);background:#243638;border:1px solid #49605b;border-radius:8px;padding:7px 12px;cursor:pointer}
button:focus-visible,select:focus-visible,input:focus-visible{outline:2px solid var(--green)}button.primary{color:#142022;background:var(--green);border-color:var(--green);min-width:80px}
.buttons{display:flex;gap:8px;align-items:center;flex-wrap:wrap}.slider{display:flex;gap:12px;align-items:center;margin-top:13px}input[type=range]{flex:1;min-width:0;accent-color:var(--green)}
.mono{font:13px ui-monospace,monospace}.small{font-size:12px;color:var(--muted)}.side{padding:20px}.side h2{font-size:14px;font-weight:500;color:var(--muted);margin:0 0 14px}
.number{font-size:40px;line-height:1.2;color:var(--green)}.metric{padding:15px 0;border-bottom:1px solid var(--line)}.metric b{float:right;font-weight:500}
.room{display:flex;justify-content:space-between;margin:9px 0}.legend{display:flex;flex-wrap:wrap;gap:15px;padding:0 20px 16px;font-size:12px;color:var(--muted)}
.dot{display:inline-block;width:8px;height:8px;border-radius:50%;margin-right:5px}footer{margin-top:20px;font-size:12px;color:var(--muted)}
details{margin-top:18px}summary{cursor:pointer}code{color:var(--green)}
@media(max-width:850px){main{padding:16px}.layout{grid-template-columns:1fr}.side{display:grid;grid-template-columns:1fr 1fr;gap:20px}header{align-items:flex-start}h1{font-size:24px}.badge{white-space:normal;max-width:120px}}
@media(prefers-reduced-motion:reduce){*{scroll-behavior:auto}}
</style>
<main><header><div><div class="eyebrow">MOTIONBRICKS / BEHAVIOR LAB 01</div><h1>一套民宅，一群蟑螂。</h1><p>观察局部规则如何形成整屋的活动分布。</p></div><div class="badge">规则模拟 · 非真实观察</div></header>
<div class="layout"><section class="panel"><div class="bar"><span id="home"></span><span class="mono" id="phase"></span></div>
<div id="stage"><canvas id="map" width="984" height="696" aria-label="民宅平面图与虚拟蟑螂位置"></canvas></div>
<div class="legend"><span><i class="dot" style="background:#efad72"></i>虚拟蟑螂</span><span><i class="dot" style="background:#667951"></i>藏身处</span><span><i class="dot" style="background:#f1ca71"></i>食物</span><span><i class="dot" style="background:#78bacf"></i>水源</span><span>深色块：墙体 / 家具</span></div>
<div class="controls"><div class="buttons"><button class="primary" id="play">播放</button><button id="restart">回到开始</button><button id="heat" aria-pressed="false">停留热图</button>
<label class="small">轨迹 <select id="track"><option value="-1">关闭</option></select></label><label class="small">速度 <select id="speed"><option value="180">1×</option><option value="60">3×</option><option value="20">9×</option></select></label></div>
<div class="slider"><input id="scrub" aria-label="回放时间" type="range" min="0" value="0"><span class="mono" id="clock"></span></div></div></section>
<aside class="panel side"><div><h2>当前观察</h2><div class="number" id="population"></div><div class="small">只虚拟个体 · 数量固定</div>
<div class="metric">藏身处占用 <b id="shelter"></b></div><div class="metric">贴壁个体 <b id="wall"></b></div><div class="metric">本步移动比例 <b id="moving"></b></div>
<h2 style="margin-top:25px">房间分布</h2><div id="rooms"></div></div><div><h2>本次实验</h2><p class="small" id="spec"></p><details><summary class="small">如何解读</summary><p class="small">热图覆盖整段运行，包括当前回放时刻之后的记录。抽样间隔大于 1 时，轨迹连线可能跨过障碍；核查路径需以 sample_every=1 重跑。步数没有换算为真实秒数。改变参数需用 Python 重新运行。</p><p class="small">本版不模拟繁殖、死亡、食尸、人类活动或感染传播。</p></details></div></aside></div>
<footer>Blattella germanica 文献启发的假设模型。参数未经民宅实测数据拟合；此处结果只说明模型行为。文件可离线打开，无网络请求。</footer></main>
<script id="run-data" type="application/json">__RUN_DATA__</script>
<script>
'use strict';
const data=JSON.parse(document.getElementById('run-data').textContent), $=id=>document.getElementById(id);
const grid=data.house.grid, W=grid[0].length,H=grid.length,canvas=$('map'),ctx=canvas.getContext('2d');
const cell=24;canvas.width=W*cell;canvas.height=H*cell;
let index=0,playing=false,showHeat=false,last=0;
$('home').textContent=data.house.name;$('population').textContent=data.config.agents;
$('spec').textContent=`情景 ${data.scenario} · 种子 ${data.config.seed} · ${data.config.steps} 步 · 每 ${data.config.sample_every} 步记录轨迹。`;
$('scrub').max=data.frames.length-1;
for(let i=0;i<data.config.agents;i++){const o=document.createElement('option');o.value=i;o.textContent=`#${i+1}`;$('track').appendChild(o)}
const roomNodes=data.house.rooms.map(r=>{const div=document.createElement('div');div.className='room';const label=document.createElement('span'),count=document.createElement('span');label.textContent=r.name;div.append(label,count);$('rooms').appendChild(div);return count});
const maxHeat=Math.max(1,...data.heat.flat());
function draw(){
 const frame=data.frames[index],tick=frame.tick;
 const on=data.scenario==='constant_light'||(Math.max(1,tick)-1)%data.config.cycle<data.config.light_ticks;
 ctx.fillStyle='#142022';ctx.fillRect(0,0,canvas.width,canvas.height);
 for(let y=0;y<H;y++)for(let x=0;x<W;x++){
  const c=grid[y][x];ctx.fillStyle=c==='#'?'#304244':c==='s'?'#42513d':on?'#243334':'#1b2a2c';ctx.fillRect(x*cell,y*cell,cell-1,cell-1);
  if(showHeat&&c!=='#'){ctx.fillStyle=`rgba(238,153,85,${.82*Math.log1p(data.heat[y][x])/Math.log1p(maxHeat)})`;ctx.fillRect(x*cell,y*cell,cell-1,cell-1)}
  if(c==='f'||c==='w'){ctx.fillStyle=c==='f'?'#f1ca71':'#78bacf';ctx.beginPath();ctx.arc((x+.5)*cell,(y+.5)*cell,5,0,Math.PI*2);ctx.fill()}
 }
 ctx.font='16px system-ui';ctx.fillStyle='#c0cbc17f';
 for(const r of data.house.rooms){const b=r.bounds;ctx.fillText(r.name,(b[0]+1.2)*cell,(b[1]+2.6)*cell)}
 const selected=Number($('track').value);
 if(selected>=0){ctx.strokeStyle='#b7d78d';ctx.lineWidth=2;ctx.beginPath();data.frames.slice(0,index+1).forEach((f,i)=>{const p=f.positions[selected];ctx[i?'lineTo':'moveTo']((p[0]+.5)*cell,(p[1]+.5)*cell)});ctx.stroke()}
 for(let i=0;i<frame.positions.length;i++){
  const p=frame.positions[i],prev=index?data.frames[index-1].positions[i]:p;
  ctx.save();ctx.translate((p[0]+.5)*cell,(p[1]+.5)*cell);ctx.rotate(Math.atan2(p[1]-prev[1],p[0]-prev[0]));
  ctx.strokeStyle=i===selected?'#d9f0ba':'#cf9b72';ctx.lineWidth=1;
  for(const dx of [-3,0,3]){ctx.beginPath();ctx.moveTo(dx,-3);ctx.lineTo(dx-2,-6);ctx.moveTo(dx,3);ctx.lineTo(dx-2,6);ctx.stroke()}
  ctx.fillStyle=i===selected?'#b7d78d':'#efad72';ctx.beginPath();ctx.ellipse(0,0,5,2.8,0,0,Math.PI*2);ctx.fill();ctx.restore();
 }
 const row=tick?data.metrics[tick-1]:null,n=data.config.agents;
 $('shelter').textContent=`${Math.round(frame.positions.filter(p=>grid[p[1]][p[0]]==='s').length/n*100)}%`;
 $('wall').textContent=`${Math.round(frame.positions.filter(([x,y])=>[[x+1,y],[x-1,y],[x,y+1],[x,y-1]].some(([a,b])=>grid[b]?.[a]==='#')).length/n*100)}%`;
 $('moving').textContent=row?`${Math.round(row.moving_fraction*100)}%`:'—';
 data.house.rooms.forEach((r,i)=>{const [x0,y0,x1,y1]=r.bounds;roomNodes[i].textContent=frame.positions.filter(([x,y])=>x>=x0&&x<=x1&&y>=y0&&y<=y1).length});
 $('phase').textContent=on?'● 开灯阶段':'○ 暗阶段';$('clock').textContent=`${tick} / ${data.config.steps}`;$('scrub').value=index;
}
function setPlaying(value){playing=value;$('play').textContent=playing?'暂停':'播放'}
$('play').onclick=()=>{if(index===data.frames.length-1)index=0;setPlaying(!playing);draw()};
$('restart').onclick=()=>{index=0;setPlaying(false);draw()};
$('scrub').oninput=()=>{index=Number($('scrub').value);setPlaying(false);draw()};
$('heat').onclick=()=>{showHeat=!showHeat;$('heat').setAttribute('aria-pressed',String(showHeat));draw()};
$('track').onchange=draw;
function animate(now){if(playing&&now-last>=Number($('speed').value)){last=now;if(index<data.frames.length-1){index++;draw()}else setPlaying(false)}requestAnimationFrame(animate)}
draw();requestAnimationFrame(animate);
</script></html>'''
