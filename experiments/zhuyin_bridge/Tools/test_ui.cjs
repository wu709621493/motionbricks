// Optional UI verification: npm install --no-save playwright
// CHROMIUM_PATH=/path/to/chromium node Tools/test_ui.cjs
const {chromium}=require('playwright');
const assert=require('node:assert/strict'),path=require('node:path'),fs=require('node:fs');
const {pathToFileURL}=require('node:url');
(async()=>{
  const browser=await chromium.launch({headless:true,...(process.env.CHROMIUM_PATH?{executablePath:process.env.CHROMIUM_PATH}:{})});
  const page=await browser.newPage({viewport:{width:1280,height:1000}}), errors=[], requests=[];
  page.on('pageerror',e=>errors.push(e.message));
  page.on('request',r=>{if(/^https?:/.test(r.url()))requests.push(r.url());});
  await page.goto(pathToFileURL(path.resolve(__dirname,'../Web/index.html')).href);
  await page.locator('[data-symbol="ㄋ"]').click();await page.locator('[data-symbol="ㄧ"]').click();await page.locator('[data-tone="3"]').click();
  await page.locator('[data-symbol="ㄏ"]').click();await page.locator('[data-symbol="ㄠ"]').click();await page.locator('[data-tone="3"]').click();
  assert.equal(await page.locator('#pinyin').textContent(),'nǐ hǎo');
  await page.locator('#candidates button').filter({hasText:'你好'}).click();
  assert.equal(await page.locator('#output').inputValue(),'你好');
  for(const[word,read]of [['北京','bei3 jing1'],['華盛頓','hua2 sheng4 dun4'],['台北','tai2 bei3']]){
    await page.locator(`[data-example="${read}"]`).click();
    await page.locator('#candidates button').filter({hasText:word}).first().click();
  }
  assert.equal(await page.locator('#output').inputValue(),'你好北京華盛頓台北');
  await page.locator('[data-example="hua2 sheng4 dun4"]').click();await page.locator('#script').click();
  assert.equal(await page.locator('#candidates button').first().textContent(),'华盛顿');
  await page.locator('#candidates button').first().click();
  await page.locator('#hints').click();assert.equal(await page.locator('.hint').count(),0);await page.locator('#hints').click();
  await page.locator('#clear').click();await page.locator('[data-symbol="ㄅ"]').click();await page.locator('#space').click();
  assert.equal(await page.locator('#zhuyin').textContent(),'ㄅ');await page.locator('#raw').click();
  assert.ok((await page.locator('#output').inputValue()).endsWith('ㄅ'));
  await page.locator('#mode').click();await page.locator('.key').filter({hasText:/^a$/}).click();await page.locator('#shift').click();await page.locator('.key').filter({hasText:/^Z$/}).click();
  await page.locator('#numbers').click();await page.locator('.key').filter({hasText:/^7$/}).click();
  assert.ok((await page.locator('#output').inputValue()).endsWith('aZ7'));
  await page.locator('#delete').click();assert.ok((await page.locator('#output').inputValue()).endsWith('aZ'));
  // Text selection replacement and grapheme-aware deletion in the preview host.
  await page.locator('#output').fill('甲乙丙');await page.locator('#output').evaluate(el=>el.setSelectionRange(1,2));
  await page.locator('.key').filter({hasText:/^7$/}).click();assert.equal(await page.locator('#output').inputValue(),'甲7丙');
  await page.locator('#output').fill('👨‍👩‍👧‍👦');await page.locator('#delete').click();assert.equal(await page.locator('#output').inputValue(),'');
  await page.locator('#mode').click();await page.locator('[data-example="ni3 hao3"]').click();
  const screenshotDir=process.env.SCREENSHOT_DIR;
  for(const width of [1280,768,390,320]){
    await page.setViewportSize({width,height:width>880?1000:1600});
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth),`overflow at ${width}`);
    if(screenshotDir){fs.mkdirSync(screenshotDir,{recursive:true});await page.screenshot({path:path.join(screenshotDir,`preview-${width}.png`),fullPage:true});}
  }
  assert.deepEqual(errors,[]);assert.deepEqual(requests,[]);
  await browser.close();
  console.log('PASS: UI input, 3 cities, scripts, hints, unknown/raw, ABC/caps/numbers, deletion, selected text, emoji grapheme, 4 widths, no JS errors, no HTTP requests.');
})().catch(error=>{console.error(error);process.exit(1);});
