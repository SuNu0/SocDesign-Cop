const {chromium}=require('C:/Users/LENOVO/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright');
const fs=require('fs'),path=require('path'),{pathToFileURL}=require('url'),assert=require('assert/strict');
(async()=>{
 const browser=await chromium.launch({executablePath:'C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1900,height:1400},deviceScaleFactor:1});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  const data=JSON.parse(fs.readFileSync(path.join(__dirname,'schematic_data.json'),'utf8'));
  const overflows=[];
  for(const sheet of data.sheets){
   await page.goto(pathToFileURL(path.join(__dirname,sheet.id+'.svg')).href);
   await page.locator('svg').screenshot({path:path.join(__dirname,sheet.id+'.png')});
   const bounds=await page.evaluate(()=>{
    const failures=[];
    for(const g of document.querySelectorAll('g.block')){
     const r=g.querySelector('rect').getBBox();
     for(const t of g.querySelectorAll('text')){
      const b=t.getBBox();if(b.x+b.width>r.x+r.width-5||b.y+b.height>r.y+r.height-3)failures.push({block:g.dataset.key,text:t.textContent,overflow:Math.ceil(b.x+b.width-r.x-r.width)});
     }
    }
    return failures;
   });
   if(bounds.length)overflows.push({sheet:sheet.id,bounds});
  }
  console.log(JSON.stringify({textBounds:overflows},null,2));
  await page.setViewportSize({width:1500,height:1080});
  await page.goto(pathToFileURL(path.join(__dirname,'index.html')).href);
  await page.waitForFunction(()=>!!window.schematicViewer);
  assert.equal(await page.locator('#view svg').count(),1);
  for(let i=0;i<4;i++){
   await page.locator('.tab').nth(i).click();assert.equal(await page.evaluate(()=>schematicViewer.sheet),i);
   await page.locator(await page.locator('[data-route="core"]').isEnabled()?'[data-route="core"]':'[data-route="xwrite"]').click();assert.ok(await page.locator('.focus-on').count()>0);
   await page.locator('[data-route="all"]').click();assert.equal(await page.locator('.focus-dim').count(),0);
   await page.locator('g.block').first().click();assert.ok((await page.locator('#detailText').textContent()).length>10);
   await page.locator('#actual').click();assert.equal(await page.evaluate(()=>schematicViewer.scale),1);
   await page.locator('#plus').click();assert.ok(await page.evaluate(()=>schematicViewer.scale)>1);
   await page.locator('#minus').click();await page.locator('#fit').click();
  }
  const download=page.waitForEvent('download');await page.locator('#save').click();const saved=await download;assert.equal(saved.suggestedFilename(),'04_control_fsm.svg');
  await page.locator('.tab').first().click();
  await page.screenshot({path:path.join(__dirname,'viewer_desktop.png'),fullPage:true});
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
  await page.locator('.tab').nth(1).click();await page.locator('[data-route="xwrite"]').click();
  assert.ok(await page.locator('.focus-on').count()>0);
  await page.screenshot({path:path.join(__dirname,'viewer_mobile.png'),fullPage:true});
  assert.deepEqual(errors,[]);
  fs.writeFileSync(path.join(__dirname,'verification.json'),JSON.stringify({viewer:'PASS',sheets:4,svgExports:4,checks:'tabs, highlighting, module descriptions, zoom, fit, SVG download, offline file open, mobile width',overflows},null,2));
  console.log(JSON.stringify({viewer:'PASS',overflows},null,2));
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
