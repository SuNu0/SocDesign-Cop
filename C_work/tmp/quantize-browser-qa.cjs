const fs=require('node:fs');
const path=require('node:path');
const os=require('node:os');
const {spawn}=require('node:child_process');
const {pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'../learning/parallel_quantize');
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'quantize-browser-'));
const child=spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',[
 '--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-extensions',
 '--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'
],{windowsHide:true,stdio:'ignore'});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let ws,id=0;
const pending=new Map(),errors=[];
async function send(method,params={}){const n=++id;return new Promise((resolve,reject)=>{pending.set(n,{resolve,reject});ws.send(JSON.stringify({id:n,method,params}));setTimeout(()=>{if(pending.delete(n))reject(Error('CDP timeout: '+method))},12000).unref()})}
async function evaluate(expression){const r=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(r.exceptionDetails)throw Error(r.exceptionDetails.text+JSON.stringify(r.exceptionDetails.exception));return r.result.value}
function assert(value,message){if(!value)throw Error(message);console.log('PASS '+message)}
async function check(expression,label){assert(await evaluate(expression),label)}
async function click(selector){return evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`)}
async function screenshot(name){await sleep(420);const shot=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(root,name),Buffer.from(shot.data,'base64'))}
(async()=>{
 try{
  let port;for(let n=0;n<80;n++){try{port=Number(fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0]);break}catch{}await sleep(100)}
  if(!port)throw Error('Browser did not start');
  const tabs=await (await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  ws=new WebSocket(tabs.find(t=>t.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{ws.addEventListener('open',resolve,{once:true});ws.addEventListener('error',reject,{once:true})});
  ws.addEventListener('message',ev=>{const d=JSON.parse(ev.data);if(d.id){const p=pending.get(d.id);if(p){pending.delete(d.id);d.error?p.reject(Error(JSON.stringify(d.error))):p.resolve(d.result)}}else if(d.method==='Runtime.exceptionThrown')errors.push(d.params.exceptionDetails.text)});
  await send('Runtime.enable');await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1100,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:pathToFileURL(path.join(root,'index.html')).href});
  for(let n=0;n<40;n++){if(await evaluate('document.readyState==="complete" && typeof state!=="undefined"'))break;await sleep(100)}
  await check('state.row===37 && document.querySelectorAll("[data-bit]").length===7','initial lesson loads with seven binary switches');
  await click('[data-bit="0"]');await check('state.row===36','binary switch changes numeric value');
  await evaluate('state.row=127;render()');await click('#addRow');await check('state.row===0 && document.querySelector(".formula").textContent==="0 = 0"','seven-bit overflow and zero equation');
  await click('#reset');
  await screenshot('preview.png');
  await click('[data-step="1"]');await click('[data-lane="2"]');
  await check('state.selected===2 && document.querySelectorAll(".array-cell.sel").length===4','array selection highlights all four elements in lane');
  await click('[data-step="2"]');
  await check('document.querySelectorAll(".quantizer").length===4','generate shows four separate quantizers');
  await click('[data-scenario="saturated"]');await check('results().every(x=>x.sat)','all saturated scenario');
  await click('[data-scenario="normal"]');await check('results().every(x=>!x.sat)','all normal scenario');
  await click('[data-scenario="mixed"]');
  await click('[data-step="3"]');await click('[data-lane="0"]');
  const cases=[[0,0,0],[127,0,0],[-127,0,0],[128,1,0],[-128,-1,0],[-3200,-13,0],[8388352,32767,0],[8388480,32767,1],[-8388608,-32768,0],[-8388736,-32768,1],[549755813887,32767,1],[-549755813888,-32768,1]];
  for(const [acc,data,flag] of cases){await evaluate(`document.querySelector('#accValue').value='${acc}';document.querySelector('#accForm').requestSubmit()`);await check(`state.values[0]===${acc} && requantize(state.values[0]).data===${data} && requantize(state.values[0]).flag===${flag} && document.querySelector('.tiny-bit.flag').textContent==='${flag}'`,'quantization boundary '+acc+' → '+data+', flag '+flag)}
  await click('[data-acc="-3200"]');await check('document.querySelectorAll(".tiny-bit").length===17 && document.querySelector(".tiny-bit.sign").textContent==="1" && document.querySelector(".tiny-bit.flag").textContent==="0"','negative signed data has sign bit 1 and saturation flag 0');
  await evaluate('applyAcc(549755813888)');await check('document.querySelector("#validation").textContent.includes("请输入")','out-of-range accumulator is rejected');
  await click('[data-step="4"]');await click('[data-scenario="mixed"]');
  await check('document.querySelector(".count-result strong").textContent==="2"','mixed four-lane saturation count equals two');
  await evaluate('document.querySelector("#laneCount").value="16";document.querySelector("#laneCount").dispatchEvent(new Event("change",{bubbles:true}))');
  await click('[data-scenario="saturated"]');await check('document.querySelectorAll(".flag-card").length===16 && document.querySelector(".count-result strong").textContent==="16" && document.querySelector(".count-result small").textContent.includes("10000")','16 saturated lanes produce five-bit count 10000');
  await click('#play');await evaluate('clearTimeout(state.timer);tick();clearTimeout(state.timer)');await click('#play');
  await check('!state.playing && document.querySelector(".count-result strong").textContent==="16"','pausing sum animation restores complete combinational sum');
  await click('[data-step="5"]');await click('[data-control="issue"]');await check('document.querySelector(".control-data").textContent.includes("0～64")','issue counters explain terminal values');
  await click('[data-control="valid"]');await check('document.querySelector(".control-data").textContent.includes("product_last")','valid and last controls are available');
  await click('#reset');await click('#play');await check('state.playing','play button starts timeline');
  await evaluate('clearTimeout(state.timer);for(let n=0;n<70 && state.playing;n++){tick();clearTimeout(state.timer)}');
  await check('state.finished && !state.playing && state.step===5','entire six-lesson timeline finishes and pauses');
  await click('#reset');await click('[data-step="2"]');await screenshot('preview-parallel.png');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await check('document.documentElement.scrollWidth<=390','mobile parallel lesson has no page overflow');
  await screenshot('preview-mobile.png');
  for(let step=0;step<6;step++){
   await evaluate(`gotoStep(${step})`);
   await check('document.documentElement.scrollWidth<=390','mobile lesson '+(step+1)+' has no page overflow');
  }
  await evaluate('document.querySelector("#laneCount").value="16";document.querySelector("#laneCount").dispatchEvent(new Event("change"))');
  for(const step of [1,2,3,4]){await evaluate(`gotoStep(${step})`);await check('document.documentElement.scrollWidth<=390','mobile 16-lane lesson '+(step+1)+' has no page overflow')}
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1200,deviceScaleFactor:1,mobile:false});
  await click('#reset');await click('#play');await click('#manualMode');
  await check('state.mode==="manual" && !state.playing && document.querySelector("#animationToolbar").hidden','manual mode pauses animation and replaces playback controls');
  await check('document.querySelector("#manualAnswer").value==="" && document.querySelector("#manualSolution").hidden && manualProgress()===0','manual answers start empty and reference solutions are hidden');
  await click('[data-manual-preset="simple"]');
  await check('state.values[0]===640 && state.values[3]===-3200','beginner exercise uses positive and negative half values');
  const answer=async value=>{await evaluate(`document.querySelector('#manualAnswer').value=${JSON.stringify(String(value))};document.querySelector('#manualAnswer').dispatchEvent(new Event('input',{bubbles:true}));document.querySelector('#manualAnswerForm').requestSubmit()`)};
  await answer('');await check('document.querySelector("#manualFeedback").textContent.includes("先填写") && manualProgress()===0','blank answer is rejected');
  await answer(2);await check('document.querySelector("#manualFeedback").classList.contains("bad") && document.querySelector("#manualSolution").hidden && manualProgress()===0','wrong division is flagged without revealing the answer');
  await click('[data-manual-action="hint"]');await check('!document.querySelector("#manualHint").hidden && document.querySelector("#manualAnswer").value==="2"','hint preserves the learner answer');
  await click('[data-manual-action="reveal"]');
  await check('!document.querySelector("#manualSolution").hidden && document.querySelector("#manualSolution").textContent.includes("2.5") && document.querySelector("#manualAnswer").value==="2" && manualProgress()===0','worked solution shows exact calculation without auto-filling or counting as complete');
  await answer('2.5');await check('manualProgress()===1 && document.querySelector("#manualFeedback").textContent.includes("参考")','correct referenced answer is acknowledged');
  await evaluate('document.querySelector("#manualAnswer").value="9";document.querySelector("#manualAnswer").dispatchEvent(new Event("input",{bubbles:true}))');
  await check('manualProgress()===0 && document.querySelector(".manual-meta .chip").textContent.includes("0 / 21") && !document.querySelectorAll("[data-manual-phase]")[0].classList.contains("done")','editing an answer immediately invalidates progress and status');
  await answer('2.5');await click('[data-manual-action="next"]');await answer(3);
  await check('manual.phase===1 && manualProgress()===2','positive half rounds away from zero');
  await click('#animationMode');await click('#manualMode');
  await check('manual.phase===1 && document.querySelector("#manualAnswer").value==="3" && manualProgress()===2','switching modes retains worksheet drafts');
  await screenshot('preview-manual.png');
  await click('[data-manual-action="resetAll"]');
  const solutions=[['2.5','3','3','0','0 | 0000000000000011'],['40000','40000','32767','1','1 | 0111111111111111'],['-40000','-40000','-32768','1','1 | 1000000000000000'],['-12.5','-13','-13','0','0 | 1111111111110011']];
  for(let lane=0;lane<4;lane++){
   await click(`[data-manual-lane="${lane}"]`);
   for(let phase=0;phase<5;phase++){
    await click(`[data-manual-phase="${phase}"]`);await answer(solutions[lane][phase]);
    await check('document.querySelector("#manualFeedback").classList.contains("good")','manual lane '+lane+', phase '+phase+' accepts correct arithmetic and bit pattern');
   }
  }
  await check('manualProgress()===20 && document.querySelectorAll(".manual-lanes button.done").length===4','four completed lanes show 20 verified items');
  await click('[data-manual-action="next"]');await check('manual.phase===5','last lane advances to group sum');
  await answer(1);await check('manualProgress()===20 && document.querySelector("#manualFeedback").classList.contains("bad")','incorrect group sum is rejected');
  await answer(2);await check('manualProgress()===21 && !!document.querySelector(".manual-complete")','whole four-lane worksheet completes with sum two');
  await click('[data-manual-action="reveal"]');await check('document.querySelector("#manualSolution").textContent.includes("00010")','sum explanation includes five-bit encoding');
  await screenshot('preview-manual-sum.png');
  await click('[data-manual-lane="0"]');
  await evaluate('document.querySelector("#manualAcc").value="549755813888";document.querySelector("#manualAccForm").requestSubmit()');
  await check('state.values[0]===640 && manualProgress()===21 && document.querySelector("#manualNotice").textContent.includes("请输入")','custom input rejects values outside signed 40-bit range without losing drafts');
  await evaluate('document.querySelector("#manualAcc").value="640";document.querySelector("#manualAccForm").requestSubmit()');
  await check('manualProgress()===21','reapplying unchanged problem preserves answers');
  await evaluate('document.querySelector("#manualAcc").value="128";document.querySelector("#manualAccForm").requestSubmit()');
  await check('manualProgress()===15 && manual.sheets[1][0].value==="40000" && manual.total.value===""','changing one lane clears only its five answers and group total');
  await evaluate('document.querySelector("#laneCount").value="16";document.querySelector("#laneCount").dispatchEvent(new Event("change"))');
  await check('manualProgress()===15 && document.querySelectorAll(".manual-lanes button").length===16','16-lane mode retains existing per-lane drafts');
  await click('[data-manual-preset="boundary"]');await click('[data-manual-lane="3"]');await click('[data-manual-phase="1"]');await answer(-32769);
  await check('document.querySelector("#manualFeedback").classList.contains("good")','negative boundary half rounds to -32769 before saturation');
  await click('[data-manual-phase="2"]');await answer(-32768);await click('[data-manual-phase="3"]');await answer(1);await click('[data-manual-phase="4"]');
  await answer('1|1000_0000_0000_0000');await check('document.querySelector("#manualFeedback").classList.contains("good")','binary answer accepts pipe, underscore, and exact 17-bit result');
  await answer('1000000000000000');await check('document.querySelector("#manualFeedback").textContent.includes("17 位")','sixteen-bit answer is rejected when 17 bits are required');
  await click('[data-manual-action="reveal"]');await check('document.querySelector("#manualSolution").textContent.includes("逐位取反")','negative result solution explains two-complement construction');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  for(let phase=0;phase<6;phase++){
   await click(`[data-manual-phase="${phase}"]`);await click('[data-manual-action="reveal"]');
   await check('document.documentElement.scrollWidth<=390','mobile manual phase '+phase+' has no page overflow with 16 lanes and solution');
  }
  await screenshot('preview-manual-mobile.png');
  await click('#animationMode');await evaluate('setScenario("saturated")');await click('#manualMode');await click('[data-manual-phase="5"]');await answer(16);
  await check('document.querySelector("#manualFeedback").classList.contains("good")','manual group sum accepts all 16 saturated lanes');
  await click('[data-manual-action="reveal"]');await check('document.querySelector("#manualSolution").textContent.includes("10000")','sixteen-lane manual sum explains five-bit count 10000');
  assert(errors.length===0,'no browser runtime exceptions');
  console.log('Screenshots saved to '+root);
 }finally{if(ws)ws.close();child.kill()}
})().catch(err=>{console.error(err);process.exitCode=1});
