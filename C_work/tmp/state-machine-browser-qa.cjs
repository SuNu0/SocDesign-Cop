const fs=require('node:fs'),path=require('node:path'),os=require('node:os');
const {spawn}=require('node:child_process'),{pathToFileURL}=require('node:url');
const root=path.resolve(__dirname,'../learning/ffn_state_machine');
const profile=fs.mkdtempSync(path.join(os.tmpdir(),'ffn-state-machine-'));
const browser=spawn('C:/Program Files (x86)/Microsoft/Edge/Application/msedge.exe',['--headless=new','--disable-gpu','--no-first-run','--no-default-browser-check','--disable-extensions','--remote-debugging-port=0','--user-data-dir='+profile,'about:blank'],{windowsHide:true,stdio:'ignore'});
const sleep=ms=>new Promise(r=>setTimeout(r,ms));
let socket,id=0;const pending=new Map(),errors=[];
function send(method,params={}){const call=++id;return new Promise((resolve,reject)=>{pending.set(call,{resolve,reject});socket.send(JSON.stringify({id:call,method,params}));setTimeout(()=>{if(pending.delete(call))reject(Error('Timeout '+method))},15000).unref()})}
async function evaluate(expression){const result=await send('Runtime.evaluate',{expression,returnByValue:true,awaitPromise:true});if(result.exceptionDetails)throw Error(JSON.stringify(result.exceptionDetails));return result.result.value}
function assert(condition,label){if(!condition)throw Error(label);console.log('PASS '+label)}
async function check(expression,label){assert(await evaluate(expression),label)}
async function click(selector){await evaluate(`document.querySelector(${JSON.stringify(selector)}).click()`)}
async function screenshot(name){await sleep(450);const result=await send('Page.captureScreenshot',{format:'png',captureBeyondViewport:false});fs.writeFileSync(path.join(root,name),Buffer.from(result.data,'base64'))}
async function select(selector,value){await evaluate(`document.querySelector(${JSON.stringify(selector)}).value=${JSON.stringify(value)};document.querySelector(${JSON.stringify(selector)}).dispatchEvent(new Event('change',{bubbles:true}))`)}
(async()=>{
 try{
  let port;for(let i=0;i<80;i++){try{port=Number(fs.readFileSync(path.join(profile,'DevToolsActivePort'),'utf8').split('\n')[0]);break}catch{}await sleep(100)}
  if(!port)throw Error('Browser not ready');
  const pages=await(await fetch('http://127.0.0.1:'+port+'/json/list')).json();
  socket=new WebSocket(pages.find(p=>p.type==='page').webSocketDebuggerUrl);
  await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true})});
  socket.addEventListener('message',event=>{const data=JSON.parse(event.data);if(data.id){const item=pending.get(data.id);if(item){pending.delete(data.id);data.error?item.reject(Error(JSON.stringify(data.error))):item.resolve(data.result)}}else if(data.method==='Runtime.exceptionThrown')errors.push(data.params.exceptionDetails)});
  await send('Runtime.enable');await send('Page.enable');
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1400,deviceScaleFactor:1,mobile:false});
  await send('Page.navigate',{url:pathToFileURL(path.join(root,'index.html')).href});
  for(let i=0;i<40;i++){if(await evaluate('document.readyState==="complete" && typeof machine!=="undefined"'))break;await sleep(100)}
  await check('machine.reg.state==="S_IDLE" && document.querySelectorAll(".state-node").length===5','initial five-state map loads');
  await check('document.documentElement.scrollWidth<=1440','desktop layout has no horizontal page overflow');
  await click('#start');await check('machine.reg.state==="S_BIAS" && machine.reg.cycle_count===0 && machine.edges===1','START uses one edge and does not count as busy');
  await check('document.querySelector("#code").textContent.includes("start_event") && document.querySelector("#metricState").textContent==="S_BIAS"','code shows old executed branch while status shows new state');
  await click('#step');await check('machine.reg.bias_issue===1 && machine.reg.bias_valid===1 && machine.reg.accumulator.every(n=>n===0)','first bias request does not immediately load accumulator');
  await click('#step');await check('machine.reg.accumulator[0]===65536 && machine.reg.bias_lane_d===1','next bias edge consumes old delayed lane and SRAM data');
  await click('#nextState');await check('machine.reg.state==="S_MAC" && machine.reg.cycle_count===5','next-state control includes final bias drain cycle');
  await click('#step');await click('#step');await click('#step');
  await check('machine.last.ops.find(o=>o.kind==="read").k===2 && machine.last.ops.find(o=>o.kind==="multiply").k===1 && machine.last.ops.find(o=>o.kind==="accumulate").k===0','pipeline displays different k values for simultaneous read/multiply/accumulate');
  await screenshot('preview.png');
  const before=await evaluate('machine.edges');await click('[data-state="S_WRITE"]');
  await check(`machine.reg.state==='S_MAC' && machine.edges===${before} && document.querySelector('#codeTitle').textContent.includes('S_WRITE')`,'clicking a state inspects explanation without changing simulation');
  await click('#follow');await click('#fullCode');await check('document.querySelector("#code").textContent.includes("negedge rst_n") && document.querySelector("#code").textContent.includes("default:")','complete source code can be expanded');await click('#fullCode');
  await select('#lane','2');await check('app.lane===2 && document.querySelector("#changes").textContent.includes("accumulator[2]")','lane selector updates register comparison');
  await evaluate('jumpTo("macTail")');
  await check('machine.reg.state==="S_MAC" && machine.reg.mac_issue===4 && machine.reg.product_last===0','MAC-tail target stops before pipeline drains');
  await click('#step');await check('machine.reg.state==="S_MAC" && machine.reg.product_last===1 && !machine.last.ops.some(o=>o.kind==="read")','first drain edge performs final multiplication with no new read');
  await click('#step');await check('machine.reg.state==="S_ROUND" && machine.reg.cycle_count===11','second drain edge adds final product then enters ROUND');
  await click('#step');await check('machine.reg.state==="S_WRITE" && JSON.stringify(machine.reg.output_buffer)==="[512,32767,-32768,-128]" && machine.reg.saturation_count===2','ROUND latches all four outputs and counts saturation once');
  await screenshot('preview-round.png');
  await evaluate('jumpTo("groupEnd")');await click('#step');
  await check('machine.reg.group_index===1 && machine.reg.row_index===0 && machine.reg.state==="S_BIAS" && machine.taskWrites===4','last write of group advances group only');
  await evaluate('jumpTo("rowEnd")');await click('#step');
  await check('machine.reg.row_index===1 && machine.reg.group_index===0 && machine.taskWrites===8','last group of row advances row and clears group');
  await evaluate('jumpTo("finish")');
  await check('machine.reg.done===0 && machine.taskWrites===15 && machine.reg.write_lane===3','completion target stops before final Y write');
  await click('#clear');await check('machine.reg.done===1 && machine.reg.state==="S_IDLE" && machine.reg.cycle_count===64 && machine.taskWrites===16','final done assignment wins over simultaneous clear_done');
  await click('#step');await check('machine.reg.done===1 && machine.reg.cycle_count===64','done holds and cycle counter stops in IDLE');
  await click('#clear');await check('machine.reg.done===0 && machine.outputs.size===16','clear_done preserves computed outputs');
  const resetEdge=await evaluate('machine.edges');await click('#reset');
  await check(`machine.edges===${resetEdge} && machine.rstLow && machine.reg.state==='S_IDLE' && machine.reg.cycle_count===0 && machine.outputs.size===16 && machine.taskWrites===0`,'asynchronous reset clears registers without clock and preserves SRAM');
  await click('#step');await check('machine.rstLow && machine.reg.cycle_count===0 && machine.reg.state==="S_IDLE"','clock while reset is held leaves registers reset');await click('#reset');
  await click('#play');await check('app.playing && machine.reg.state==="S_BIAS"','automatic playback starts the task');await click('#play');await check('!app.playing','automatic playback pauses');
  await select('#config','actual');await evaluate('jumpTo("finish")');
  await check('machine.reg.cycle_count===158399 && machine.reg.row_index===98 && machine.reg.group_index===15 && machine.reg.write_lane===15 && machine.taskWrites===25343','full-size jump reaches exact pre-completion boundary');
  await click('#step');await check('machine.reg.done===1 && machine.reg.cycle_count===158400 && machine.taskWrites===25344 && machine.reg.saturation_count===12672','full engineering model finishes with correct cycle, output and saturation counts');
  await screenshot('preview-complete.png');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await check('document.documentElement.scrollWidth<=390','mobile engineering view has no page overflow');
  await screenshot('preview-mobile.png');
  await select('#config','small');
  for(const target of ['biasTail','macTail','groupEnd','rowEnd','finish']){await evaluate(`jumpTo('${target}')`);await check('document.documentElement.scrollWidth<=390','mobile target '+target+' has no page overflow')}
  await send('Emulation.setDeviceMetricsOverride',{width:1440,height:1200,deviceScaleFactor:1,mobile:false});
  await click('#restart');
  await select('#waveLane','0');
  await check('!document.querySelector("#timingPanel").hidden && document.querySelector("#stateMap").hidden && document.querySelectorAll(".wave-label").length===13','timing diagram is the default presentation with thirteen pipeline tracks');
  await click('#waveDemo');for(let i=0;i<30;i++){if(await evaluate('!app.jumping && timing.selectedId!==null && machine.taskWrites===4'))break;await sleep(30)}
  await check('machine.edges===17 && machine.reg.group_index===1 && machine.waveTrace.length===18 && viewEvent().edge===9','one-group demo captures all clocks and selects the first accumulation');
  await check('[...document.querySelectorAll(".wave-dependency")].filter(el=>el.dataset.k==="0").length===2','same k is connected from read to multiply to accumulate');
  await check('document.querySelector("#waveInspector").textContent.includes("16,384") && document.querySelector("#waveInspector").textContent.includes("65,536") && document.querySelector("#codeTitle").textContent.includes("所选拍")','historical inspector and source distinguish old and new products');
  await check('machine.waveTrace.find(e=>e.ops.some(o=>o.kind==="read" && o.k===0)).edge===7 && machine.waveTrace.find(e=>e.ops.some(o=>o.kind==="multiply" && o.k===0)).edge===8 && machine.waveTrace.find(e=>e.ops.some(o=>o.kind==="accumulate" && o.k===0)).edge===9','recorded k=0 progresses through three distinct rising edges');
  await check('machine.waveTrace.find(e=>e.after.mac_read_last===1).edge===10 && machine.waveTrace.find(e=>e.after.product_last===1).edge===11','last marker is delayed by one registered stage');
  await evaluate('document.querySelector("#timingPanel").scrollIntoView({block:"start"})');
  await screenshot('preview-timing.png');
  await evaluate('[...document.querySelectorAll("[data-wave-id]")].find(el=>el.dataset.waveId==="7").dispatchEvent(new MouseEvent("click",{bubbles:true}))');
  await check('machine.edges===17 && viewEvent().edge===7 && document.querySelector("#edgeTitle").textContent.includes("回看 ↑7")','clicking waveform column reviews a historical edge without changing machine time');
  await click('#waveFollow');await check('timing.selectedId===null && viewEvent().edge===17 && timing.follow','follow latest exits historical review');
  await select('#waveGroup','overview');
  await check('document.querySelectorAll("[data-signal=start_event]").length===1 && timing.points("start_event","pulse",machine.waveTrace,18).some(p=>p.value===1 && p.time<1)','START pulse is drawn before its sampling edge');
  const asyncEdge=await evaluate('machine.edges');await click('#reset');
  await check(`machine.edges===${asyncEdge} && machine.last.kind==='reset' && machine.last.time>${asyncEdge} && machine.last.time<${asyncEdge+1} && machine.last.rstBefore===1 && machine.last.rstAfter===0`,'asynchronous reset has its own timestamp between rising edges');
  await check('timing.points("rst_n","bit",machine.waveTrace,machine.edges+1).some(p=>p.time===machine.last.time && p.value===0) && machine.reg.accumulator.every(x=>x===0)','reset waveform and register reset change at the asynchronous timestamp');
  await evaluate('timing.select(machine.last.waveId)');await check('!document.querySelector("#edgeTitle").textContent.includes("null") && document.querySelector("#waveInspector").textContent.includes("异步复位")','asynchronous event can be selected and explained');
  await screenshot('preview-timing-reset.png');
  await click('#reset');await click('#step');
  await click('#routeMode');await check('document.querySelector("#timingPanel").hidden && !document.querySelector("#stateMap").hidden','route presentation remains available');await click('#timingMode');
  await select('#waveLane','2');await check('app.lane===2 && document.querySelector("#changes").textContent.includes("accumulator[2]")','wave lane selector updates both waveform and register inspector');
  for(const group of ['overview','bias','mac','write','all']){await select('#waveGroup',group);await check('document.querySelectorAll(".wave-label").length>8 && document.querySelectorAll("#waveSvg path").length>0','waveform signal preset '+group+' renders')}
  await evaluate('document.querySelector("#waveScroll").scrollTop=150;document.querySelector("#waveScroll").dispatchEvent(new Event("scroll"))');
  await check('document.querySelector("#waveLabels").scrollTop===document.querySelector("#waveScroll").scrollTop','fixed signal labels follow vertical scrolling');
  await select('#waveGroup','mac');await select('#config','actual');await evaluate('jumpTo("finish")');
  await check('machine.waveTrace.length===512 && timing.minStart>0','long engineering run retains a bounded recent waveform history');
  const latestStart=await evaluate('timing.start');await click('#waveEarlier');await check(`!timing.follow && timing.start<${latestStart}`,'history controls pan to earlier clocks');
  await select('#waveSpan','48');await select('#waveZoom','56');await check('timing.span===48 && timing.zoom===56','timing window and horizontal zoom are adjustable');
  await send('Emulation.setDeviceMetricsOverride',{width:390,height:844,deviceScaleFactor:1,mobile:true});
  await check('document.documentElement.scrollWidth<=390 && document.querySelector("#waveScroll").scrollWidth>document.querySelector("#waveScroll").clientWidth','mobile waveform scrolls internally without page overflow');
  for(const group of ['overview','bias','mac','write','all']){await select('#waveGroup',group);await check('document.documentElement.scrollWidth<=390','mobile signal preset '+group+' stays within viewport')}
  await select('#config','small');await select('#waveGroup','mac');await click('#waveDemo');for(let i=0;i<30;i++){if(await evaluate('!app.jumping && timing.selectedId!==null && machine.taskWrites===4'))break;await sleep(30)}
  await evaluate('document.querySelector("#timingPanel").scrollIntoView({block:"start"})');await screenshot('preview-timing-mobile.png');
  assert(errors.length===0,'no browser runtime exceptions');
  console.log('Browser checks complete; previews saved to '+root);
 }finally{if(socket)socket.close();browser.kill()}
})().catch(error=>{console.error(error);process.exitCode=1});
