// Browser integration checks for the self-contained file:// artifact.
const fs = require('fs');
const path = require('path');
const {pathToFileURL} = require('url');
const assert = require('assert/strict');
const {chromium} = require('C:/Users/LENOVO/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const root = __dirname;
const url = pathToFileURL(path.join(root,'index.html')).href;
const out = path.join(root,'preview');fs.mkdirSync(out,{recursive:true});

async function check(name,executablePath,full) {
  const browser=await chromium.launch({executablePath,headless:true});
  try {
    const page=await browser.newPage({viewport:{width:1540,height:1120},deviceScaleFactor:1});
    const errors=[];page.on('pageerror',e=>errors.push(e.message));
    await page.goto(url);
    await page.waitForFunction(()=>!!window.transactionLab);
    assert.equal(await page.locator('.case').count(),96);
    assert.equal(await page.locator('#errorBanner').isVisible(),false);
    await page.screenshot({path:path.join(out,name+'-desktop.png'),fullPage:true});
    const initial=await page.evaluate(()=>transactionLab.state.index);
    await page.click('#play');
    assert.ok(await page.evaluate(n=>transactionLab.state.index>n,initial));
    await page.click('#play');
    const paused=await page.evaluate(()=>transactionLab.state.index);
    await page.waitForTimeout(950);
    assert.equal(await page.evaluate(()=>transactionLab.state.index),paused);
    await page.click('#next');assert.equal(await page.evaluate(()=>transactionLab.state.index),paused+1);
    await page.click('#prev');assert.equal(await page.evaluate(()=>transactionLab.state.index),paused);
    await page.locator('#scrub').evaluate(el=>{el.value=el.max;el.dispatchEvent(new Event('input',{bubbles:true}));});
    assert.ok(await page.locator('#play').textContent().then(x=>x.includes('重播')));
    await page.selectOption('#speed','100');
    await page.click('#play');
    await page.waitForFunction(()=>transactionLab.state.index===transactionLab.scenes[transactionLab.state.scene].frames.length-1&&!transactionLab.state.playing);
    await page.fill('#search','越过末地址');assert.equal(await page.locator('.case').count(),3);
    await page.fill('#search','无此场景123');assert.equal(await page.locator('.case').count(),0);
    await page.fill('#search','');
    await page.selectOption('#groupFilter','忙时访问');assert.equal(await page.locator('.case').count(),24);
    await page.selectOption('#groupFilter','all');
    await page.click('#learningPath button:nth-of-type(4)');
    assert.equal(await page.locator('#sceneTitle').textContent(),'运行中读 STATUS');
    await page.locator('#jumps button').first().click();
    assert.equal(await page.locator('#cmdHandshake').getAttribute('class'),'handshake yes');
    await page.selectOption('#signalMode','all');
    assert.ok(await page.evaluate(()=>transactionLab.signals().length)>35);
    await page.selectOption('#signalMode','context');
    let checked=0;
    if(full) {
      checked=await page.evaluate(()=>{
        let count=0;
        for(const s of transactionLab.scenes){
          transactionLab.selectScene(s.id,false);
          for(let i=0;i<s.frames.length;i++){
            transactionLab.seek(i);
            if(document.getElementById('edgeLabel').textContent!=='E'+i)throw new Error('edge mismatch');
            if(!document.getElementById('eventText').textContent.trim())throw new Error('empty explanation');
            if(!document.getElementById('wave').querySelector('path'))throw new Error('empty waveform');
            if(document.getElementById('wave').innerHTML.includes('NaN'))throw new Error('invalid SVG coordinates');
            count++;
          }
        }
        return count;
      });
      assert.equal(checked,719);
    }
    await page.evaluate(()=>{transactionLab.selectScene(transactionLab.scenes.findIndex(s=>s.title==='SRAM读响应反压'));transactionLab.seek(5);});
    await page.screenshot({path:path.join(out,name+'-backpressure.png'),fullPage:true});
    for(const width of [390,768,1024,1540]) {
      await page.setViewportSize({width,height:960});
      const dimensions=await page.evaluate(()=>({view:innerWidth,scroll:document.documentElement.scrollWidth}));
      assert.ok(dimensions.scroll<=dimensions.view,JSON.stringify(dimensions));
    }
    await page.setViewportSize({width:390,height:900});
    await page.screenshot({path:path.join(out,name+'-mobile.png'),fullPage:true});
    await page.click('#next');
    assert.equal(await page.evaluate(()=>transactionLab.state.index),6);
    assert.deepEqual(errors,[]);
    return {browser:name,status:'PASS',scenes:96,framesRendered:checked,checks:'file open; play/pause/replay; speed; steps; scrub; search; filters; guide; edge jumps; all signals; responsive 390/768/1024/1540; no page errors'};
  } finally {await browser.close();}
}
(async()=>{
  const results=[];
  results.push(await check('Edge','C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',true));
  results.push(await check('Chrome','C:/Program Files/Google/Chrome/Application/chrome.exe',false));
  fs.writeFileSync(path.join(out,'browser_checks.json'),JSON.stringify(results,null,2));
  console.log(JSON.stringify(results,null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
