const { chromium } = require('playwright');
const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const root = path.resolve(process.argv[2] || path.join(__dirname, '../..'));
const output = path.resolve(process.argv[3] || 'browser-review.json');
fs.mkdirSync(path.dirname(output),{recursive:true});
(async()=>{
 const browser=await chromium.launch({...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{}),headless:true,args:['--no-sandbox']});
 const context=await browser.newContext({viewport:{width:1440,height:1000},offline:true,acceptDownloads:true});
 const page=await context.newPage(), errors=[], requests=[], checks=[];
 page.on('pageerror',e=>errors.push(String(e)));
 page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url());});
 const check=async(name,fn)=>{try{const detail=await fn();checks.push({name,status:'PASS',detail});}catch(e){checks.push({name,status:'FAIL',error:String(e)});}};
 await page.goto('file://'+path.join(root,'docs/heritage/beijing_siheyuan_1900/interactive.html'));
 await check('offline initial render',async()=>{assert.equal(await page.locator('#element option').count(),20);assert.equal(await page.locator('#source-cards .card').count(),4);assert.equal(await page.locator('#detail-id').textContent(),'main_hall');});
 await check('select all 20 components',async()=>{const ids=await page.locator('#element option').evaluateAll(ns=>ns.map(n=>n.value));for(const id of ids){await page.selectOption('#element',id);assert.equal(await page.locator('#detail-id').textContent(),id);}return ids;});
 await check('3D pointer selection',async()=>{
  const point=await page.locator('#iso').evaluate(el=>{const r=el.getBoundingClientRect();for(let y=r.top+30;y<r.bottom-30;y+=9)for(let x=r.left+20;x<r.right-20;x+=9){const n=document.elementFromPoint(x,y);if(n?.matches('#iso polygon[data-element]')&&n.dataset.element==='main_hall')return {x,y,id:n.dataset.element};}});
  assert.ok(point,'visible main hall point');await page.mouse.click(point.x,point.y);assert.equal(await page.locator('#detail-id').textContent(),point.id);return point;
 });
 await check('keyboard rotation changes geometry',async()=>{await page.locator('#rotation').focus();const before=await page.locator('#iso polygon').first().getAttribute('points');await page.keyboard.press('ArrowRight');assert.equal(await page.locator('#rotation').inputValue(),'36');assert.notEqual(await page.locator('#iso polygon').first().getAttribute('points'),before);});
 await check('roof hiding removes exact roof faces',async()=>{const count=await page.locator('#iso polygon').count();const faces=await page.locator('#archive-data').evaluate(n=>JSON.parse(n.textContent).parts.filter(p=>p.kind==='roof').reduce((s,p)=>s+p.faces.length,0));await page.locator('#roofs').uncheck();assert.equal(await page.locator('#iso polygon').count(),count-faces);await page.locator('#roofs').check();assert.equal(await page.locator('#iso polygon').count(),count);return {count,roof_faces:faces};});
 await check('plan pointer and keyboard Enter/Space',async()=>{await page.locator('#show-plan').click();assert.ok(await page.locator('#plan').isVisible());await page.locator('#plan [data-element="main_hall"]').click();assert.equal(await page.locator('#detail-id').textContent(),'main_hall');const ids=await page.locator('#plan [data-element]').evaluateAll(ns=>ns.map(n=>n.dataset.element));for(let i=0;i<ids.length;i++){const n=page.locator(`#plan [data-element="${ids[i]}"]`);await n.focus();await page.keyboard.press(i%2?'Space':'Enter');assert.equal(await page.locator('#detail-id').textContent(),ids[i]);}return ids.length;});
 await check('plan shapes in real Tab sequence',async()=>{await page.locator('#plan [data-element]').first().focus();const ids=[];for(let i=0;i<20;i++){ids.push(await page.evaluate(()=>document.activeElement.dataset.element));await page.keyboard.press('Tab');}assert.equal(new Set(ids).size,20);assert.ok(ids.every(Boolean));return ids;});
 await check('route control both views and keyboard reset',async()=>{await page.locator('#route').uncheck();assert.equal(await page.locator('#plan [data-route]').evaluate(n=>getComputedStyle(n).display),'none');await page.locator('#show-iso').click();assert.equal(await page.locator('#iso polyline').count(),0);await page.locator('#reset').focus();await page.keyboard.press('Enter');assert.equal(await page.locator('#rotation').inputValue(),'35');assert.ok(await page.locator('#roofs').isChecked());assert.ok(await page.locator('#route').isChecked());assert.equal(await page.locator('#detail-id').textContent(),'main_hall');});
 await check('tabs keyboard and JSON download',async()=>{await page.locator('[data-page="sources"]').focus();await page.keyboard.press('Enter');assert.ok(await page.locator('#page-sources').isVisible());await page.locator('[data-page="record"]').focus();await page.keyboard.press('Space');assert.ok(await page.locator('#page-record').isVisible());const promise=page.waitForEvent('download');await page.locator('#download-json').click();const d=await promise;const p=await d.path();const data=JSON.parse(fs.readFileSync(p));assert.equal(data.elements.length,20);return {filename:d.suggestedFilename()};});
 for(const width of [320,375,390,768,1024,1440])await check(`responsive ${width}px`,async()=>{
  await page.setViewportSize({width,height:900});const detail=[];
  for(const tab of ['model','sources','record']){await page.locator(`[data-page="${tab}"]`).click();const size=await page.evaluate(()=>({client:document.documentElement.clientWidth,scroll:document.documentElement.scrollWidth}));assert.ok(size.scroll<=size.client+1,`${tab} overflow ${JSON.stringify(size)}`);detail.push({tab,...size});}
  return detail;
 });
 await page.setViewportSize({width:1440,height:1000});await page.locator('[data-page="model"]').click();await page.locator('#reset').click();await page.screenshot({path:output.replace('.json','-desktop.png'),fullPage:true});
 await page.setViewportSize({width:390,height:844});await page.screenshot({path:output.replace('.json','-mobile.png'),fullPage:true});
 await check('no page errors or external requests',async()=>{assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);});
 const result={browser:await browser.version(),platform:process.platform,url:page.url(),mode:'headless Chromium file://, network offline; simulated viewports, no physical mobile device',checks,errors,requests};
 fs.writeFileSync(output,JSON.stringify(result,null,2));console.log(JSON.stringify({browser:result.browser,checks},null,2));await browser.close();if(checks.some(c=>c.status==='FAIL'))process.exitCode=1;
})().catch(e=>{console.error(e);process.exit(1)});
