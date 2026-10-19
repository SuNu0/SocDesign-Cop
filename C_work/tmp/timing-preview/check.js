
(()=>{'use strict';
const TRACE=JSON.parse(document.getElementById('trace-data').textContent),$=id=>document.getElementById(id);
const HOST=['H_IDLE','H_READ','H_RESPONSE'],CORE=['S_IDLE','S_BIAS','S_MAC','S_ROUND','S_WRITE'];
const config=[
 {name:'写入一个数',short:'命令与写响应',title:'写 X[0,0]：握手成功的那个沿，SRAM 才写入',sub:'写地址 0x10000，低16位 0xFE00 表示 Q8.8 的 −2.0。命令被接受后产生写响应。',type:'bus',keys:['cmd_valid','cmd_ready','cmd_read','cmd_addr','cmd_wdata','rsp_valid','rsp_ready','rsp_err','host_state','x_en','x_we'],jumps:'bus'},
 {name:'读回一个数',short:'同步 SRAM 延迟',title:'读 X[0,0]：SRAM 读出后，再寄存到总线响应',sub:'这是同步 SRAM 读时序：命令沿之后得到读数据，下一沿进入响应寄存器，再下一沿才可完成响应握手。',type:'bus',keys:['cmd_valid','cmd_ready','cmd_read','cmd_addr','x_en','x_rdata','rsp_valid','rsp_ready','rsp_rdata','host_state'],jumps:'bus'},
 {name:'响应反压',short:'READY 拉低会怎样',title:'主机还没准备好：VALID、数据和错误位必须保持',sub:'本场景在读响应有效后继续等待3个完整周期。只有 rsp_valid 与 rsp_ready 同时为1的上升沿才结束响应。',type:'bus',keys:['cmd_valid','cmd_ready','rsp_valid','rsp_ready','rsp_rdata','rsp_err','host_state'],jumps:'bus'},
 {name:'一组100拍',short:'从 START 到16个结果',title:'START 之后：17 拍偏置、66 拍 MAC、1 拍舍入、16 拍写回',sub:'C0 是接受 START 的沿，不计入核心计数；C1…C100 是第0行、第0组，得到 Y[0,0…15]。',type:'core',keys:['cmd_valid','cmd_ready','state','busy','cycles','b_en','bias_valid','x_en','read_valid','product_valid','product_last','y_we','done'],jumps:'core'},
 {name:'完成与中断',short:'最后写回到 DONE',title:'最后一个数写入 SRAM 的同一个沿，DONE 与 IRQ 置位',sub:'直接展开最后一组（第98行、第15组），其前面的1,583组已执行但不逐拍铺开。完成后读回 Y[0,0]，再写 CONTROL=2 清中断。',type:'core',keys:['state','cycles','y_we','y_addr','write_lane','busy','done','irq','cmd_valid','cmd_ready','rsp_valid','rsp_ready'],jumps:'finish'},
 {name:'忙时访问',short:'报错与状态轮询',title:'BUSY 不是总线停摆：数据读报错，状态读仍成功',sub:'先读取运行中的 Y 数据窗口，得到 rsp_err=1；再读取 STATUS=1，表示 BUSY=1、DONE=0，且 rsp_err=0。',type:'bus',keys:['busy','cmd_valid','cmd_ready','cmd_addr','rsp_valid','rsp_ready','rsp_err','rsp_rdata','host_state','state'],jumps:'bus'},
 {name:'复位中止',short:'异步清状态',title:'rst_n 拉低：停止当前计算，清 BUSY、DONE 和接口状态',sub:'复位不清 SRAM。释放复位后 STATUS 返回0；旧输出不再代表一个已完成的新任务。平台应同步释放复位。',type:'core',keys:['rst_n','state','busy','cycles','read_valid','product_valid','done','irq','cmd_ready','rsp_valid'],jumps:'reset'}
];
const names={state:'core_state',cycles:'cycle_count',row:'row_index',group:'group_index',read_valid:'mac_read_valid',product_valid:'product_valid',product_last:'product_last',x_rdata:'X read data',w0_rdata:'W bank0 data',acc0:'accumulator[0]',product0:'product[0]',out0:'output_buffer[0]',y_wdata:'Y write data',done:'DONE',busy:'BUSY',irq:'IRQ',host_state:'host_state'};
const bits=new Set(['rst_n','cmd_valid','cmd_ready','cmd_read','rsp_valid','rsp_ready','rsp_err','busy','done','irq','x_en','x_we','b_en','bias_valid','read_valid','product_valid','product_last','y_en','y_we']);
const inputs=new Set(['rst_n','cmd_valid','cmd_read','cmd_addr','cmd_wdata','rsp_ready']);
const outputs=new Set(['cmd_ready','rsp_valid','rsp_rdata','rsp_err','busy','done','irq']);
const signedKeys=new Set(['acc0','product0','x_rdata','w0_rdata','b_rdata','y_wdata','out0']);
const state={scene:3,index:0,playing:false,speed:1,window:window.innerWidth<570?4:12};
let lastTick=0,drawLayout=null;
const clamp=(v,a,b)=>Math.max(a,Math.min(b,v));
const hex=(v,d=8)=>v===null?'X':'0x'+(v>>>0).toString(16).toUpperCase().padStart(d,'0');
const fmt=(key,v,brief=false)=>{if(v===null||v===undefined)return 'X';if(key==='state')return (CORE[v]||'?').replace(brief?'S_':'','');if(key==='host_state')return (HOST[v]||'?').replace(brief?'H_':'','');if(key==='cmd_addr')return hex(v,5);if(key==='cmd_wdata'||key==='rsp_rdata')return hex(v);return String(v);};
const frames=()=>TRACE.scenarios[state.scene],frame=()=>frames()[state.index],c=()=>config[state.scene];
const edgeLabel=f=>{if(state.scene===3)return 'C'+f.post.cycles;if(state.scene===4){const end=frames().find(e=>!e.pre.done&&e.post.done);return end&&f.edge>end.edge?'D+'+(f.edge-end.edge):'C'+f.post.cycles;}return 'E'+(f.edge-frames()[0].edge);};
const command=f=>f.pre.cmd_valid===1&&f.pre.cmd_ready===1;
const response=f=>f.pre.rsp_valid===1&&f.pre.rsp_ready===1;
const color=key=>inputs.has(key)?'#77c3b6':outputs.has(key)?'#efb388':'#b2a8dc';
function stageInfo(f){
 const p=f.pre,read=p.state===2&&p.mac_issue<64?p.mac_issue:null;
 const mul=p.state===2&&p.read_valid===1?(p.mac_issue<64?p.mac_issue-1:(p.product_valid&&p.product_last?null:63)):null;
 const acc=p.state===2&&p.product_valid===1?(p.product_last?63:clamp(p.mac_issue-2,0,62)):null;
 // During the two drain clocks mac_issue stays 64. First drain accumulates 62;
 // second drain accumulates 63, distinguished by the registered LAST bit.
 return {read,mul,acc};
}
function buildJumps(){
 const fs=frames(),cfg=c();let entries=[];
 if(cfg.jumps==='core')entries=[[0,'C0 · START'],[1,'C1 · 读偏置'],[17,'C17 · 偏置齐'],[18,'C18 · 读k0'],[19,'C19 · 乘k0'],[20,'C20 · 累k0'],[81,'C81 · 最后读取'],[83,'C83 · 流水清空'],[84,'C84 · 舍入'],[85,'C85 · 首次写回'],[100,'C100 · 换组']];
 else if(cfg.jumps==='finish'){
  const find=fn=>fs.findIndex(fn);entries=[[0,'最后一组'],[find(f=>f.pre.state===4),'首次写回'],[find(f=>f.pre.done===0&&f.post.done===1),'最后写入 / DONE'],[find(f=>command(f)&&f.pre.cmd_addr===0x40000),'CPU读结果'],[find(f=>command(f)&&f.pre.cmd_addr===0&&f.pre.cmd_wdata===2),'清DONE / IRQ']];
 }else if(cfg.jumps==='reset'){entries=[[0,'计算中'],[fs.findIndex(f=>f.pre.rst_n===0),'复位有效'],[fs.findIndex((f,i)=>i>0&&f.pre.rst_n===1&&fs[i-1].pre.rst_n===0),'释放复位'],[fs.findIndex(f=>command(f)&&f.pre.cmd_addr===4),'读STATUS']];}
 else{fs.forEach((f,i)=>{if(command(f))entries.push([i,f.pre.cmd_addr===4?'命令 · 读STATUS':'命令握手']);if(!f.pre.rsp_valid&&f.post.rsp_valid)entries.push([i,'响应VALID置位']);if(response(f))entries.push([i,'响应握手']);});}
 const seen=new Set();$('jumps').innerHTML='';for(const [i,label] of entries){if(i<0||seen.has(i+'-'+label))continue;seen.add(i+'-'+label);const b=document.createElement('button');b.className='jump';b.type='button';b.textContent=label;b.dataset.index=i;b.addEventListener('click',()=>seek(i));$('jumps').append(b);}
}
function describe(f){
 const p=f.pre,q=f.post;let title='',en='',words='';
 if(p.rst_n===0){title='异步复位有效';en='RESET ASSERTED';words='<code>rst_n=0</code> 已在两个采样沿之间拉低，异步复位立即把核心与总线状态清为空闲。此沿看到 <b>BUSY=0、DONE=0、rsp_valid=0、cmd_ready=0</b>。SRAM 内容保留，但任务已中止。';}
 else if(state.scene===6&&p.state===0){title='释放复位后空闲';en='RESET RELEASED';words='复位释放后接口可以重新接受命令，核心仍为 <code>S_IDLE</code>。读 STATUS 得到0；再次使用前应按软件约定装载完整输入与参数。';}
 if(command(f)){
  if(p.cmd_addr===0&&p.cmd_wdata===1&&q.rsp_err===0){title='接受 START';en='COMMAND ACCEPTED';words='上升沿前 <code>cmd_valid=1</code> 且 <code>cmd_ready=1</code>，CONTROL.bit0=1 被接受。沿后 <b>S_IDLE → S_BIAS，BUSY=1，CYCLES=0</b>，同时产生写响应。<b>写响应只确认启动命令被接受，不表示计算完成。</b>';}
  else if(p.cmd_addr===0&&p.cmd_wdata===2){title='软件清除完成标志';en='ACKNOWLEDGE DONE';words='E203 写 <code>CONTROL=2</code>，在本沿清除 <b>DONE 和 IRQ</b>。中断是电平信号，会持续为1直到软件清除，或下一次 START 被接受。';}
  else if(q.rsp_err===1){title='命令已接收，访问被拒绝';en='ACCEPTED / ERROR RESPONSE';words='BUSY=1 时读 Y 数据区，命令握手依然成立。译码器发现数据存储器被核心独占，沿后产生 <b>rsp_valid=1、rsp_err=1</b>，不读取 Y SRAM，也不中止计算。<b>命令握手不等于访问成功，主机还须检查响应错误位。</b>';}
  else if(p.cmd_read&&p.cmd_addr===4){title=p.busy?'BUSY 期间读取状态':'读取空闲状态';en='STATUS READ';words=`STATUS 是控制寄存器，不占用数据 SRAM。本沿接受读取，沿后响应 <code>STATUS=${q.rsp_rdata}</code>（bit0 BUSY=${q.rsp_rdata&1}，bit1 DONE=${(q.rsp_rdata>>1)&1}），<code>rsp_err=0</code>。${p.busy?'即使核心正在运行，也能正常轮询状态。':'此时核心空闲，复位已清除之前的运行与完成状态。'}`;}
  else if(p.cmd_read){title='发起同步 SRAM 读取';en='SYNCHRONOUS MEMORY READ';words=`本沿接受读地址 <code>${hex(p.cmd_addr,5)}</code>，SRAM 同步读取，读数据在沿后更新。总线状态变为 <code>H_READ</code>，<b>rsp_valid 仍为0</b>；下一沿才能把新数据寄存为响应。`;}
  else{title='命令握手并写 SRAM';en='MEMORY WRITE';words=`本沿同时满足 <code>cmd_valid && cmd_ready</code>，将写数据低16位 <code>0xFE00</code> 写入 X[0,0]，其有符号整数为 −512，Q8.8 实数为 <b>−2.0</b>。沿后返回写响应并进入 <code>H_RESPONSE</code>。`;}
 }else if(p.host_state===1){title='把 SRAM 数据寄存成响应';en='READ RESPONSE REGISTERED';words=`此沿从已更新的 SRAM 输出取值，符号扩展到32位，沿后 <code>rsp_valid=1</code>，<code>rsp_rdata=${hex(q.rsp_rdata)}</code>，进入 <code>H_RESPONSE</code>。<b>本沿前 VALID 还是0，因此本沿尚未响应握手。</b>`;}
 else if(response(f)){title='响应握手完成';en='RESPONSE ACCEPTED';words=`上升沿前 <code>rsp_valid=1</code> 且 <code>rsp_ready=1</code>，主机在本沿接收${p.rsp_err?'错误响应':'响应数据'}。沿后 <b>rsp_valid=0，H_RESPONSE → H_IDLE，cmd_ready=1</b>。本版最多一个未完成事务，本沿前READY仍为0，不能同沿再接新命令。`+(state.scene===3&&p.b_en?' <b>与此同时，核心独立读取 b[0]，开始本组第1个活动拍。</b>':'');}
 else if(p.rsp_valid&&!p.rsp_ready){title='反压：保持响应';en='HOLD UNTIL READY';words=`外设已有响应，但主机的 <code>rsp_ready=0</code>。此沿不消费响应，<b>rsp_valid、rsp_rdata、rsp_err保持</b>，<code>cmd_ready=0</code>。${p.busy?'核心计算状态机独立继续运行。':'本版接口会等这个响应被接受后，再接下一条命令。'}`;}
 else if(!words&&p.state===1){
  title=p.bias_issue<16?'读取偏置 / 预置累加器':'最后一个偏置收尾';en='BIAS / 17 CLOCKS';
  const reading=p.b_en?`本沿读 <b>b[${p.b_addr}]</b>，沿后更新 SRAM 输出。`:'';
  const filling=p.bias_valid?`同时将上一沿读出的偏置 <b>b[${p.group*16+p.bias_lane}]</b> 符号扩展、左移8位，写入对应40位累加器。`:'';
  words=reading+filling+(q.state===2?'最后一个偏置已进入第15路累加器，沿后切到 <code>S_MAC</code>。':'第1拍只发起读取，后16拍把读出的16个偏置依次预置，因此共17拍。');
 }else if(!words&&p.state===2){
  const stages=stageInfo(f);title=p.product_last&&p.product_valid?'最后一次累加 / 流水线清空':'读、乘、累加重叠执行';en='MAC / 64 + 2 CLOCKS';
  const parts=[];if(stages.read!==null)parts.push(`读第 <b>${stages.read}</b> 项输入与16路权重`);if(stages.mul!==null)parts.push(`用上一沿 SRAM 输出计算第 <b>${stages.mul}</b> 项乘积`);if(stages.acc!==null)parts.push(`将已寄存的第 <b>${stages.acc}</b> 项乘积加到16路累加器`);
  words='这一沿：'+parts.join('；')+'。'+(q.state===3?'第63项累计完成，沿后进入 <code>S_ROUND</code>。':stages.read===null?'64项已经全部发出读取，仍要等乘法与累加两级流完。':'<b>三个动作取的不是同一个 k</b>；非阻塞赋值让每一级使用沿前的旧寄存器值。');
 }else if(!words&&p.state===3){title='16路同时舍入和饱和';en='ROUND / 1 CLOCK';words='全部64项已经累加，偏置也已包含在累加器中。本沿按“最接近、半值远离零”将40位Q16小数累加值转回16位Q8.8，并饱和到合法范围，存入16个 <code>output_buffer</code> 寄存器。<b>这一拍还没写 Y SRAM。</b>';}
 else if(!words&&p.state===4){
  const end=q.done===1&&p.done===0;title=end?'最后一次写回 / 完成置位':'单端口 SRAM 顺序写回';en=end?'LAST WRITE / DONE':'WRITE BACK / 16 CLOCKS';
  words=`本沿写回第 <b>${p.write_lane}</b> 路：<code>Y[${p.row},${p.group*16+p.write_lane}]</code>，线性元素地址为 <b>${p.y_addr}</b>，数据编码为 <b>${p.y_wdata}</b>（实数 ${(p.y_wdata/256).toFixed(6)}）。`+(end?'这是第98行、第15组、第15路，也是整个矩阵最后一个结果。<b>写 SRAM 与 DONE=1、IRQ=1、BUSY=0 在同一沿完成。</b>':p.write_lane===15?'本组16个数已写完，沿后更新组号或行号，进入下一组的 <code>S_BIAS</code>。<b>整层尚未完成，DONE仍为0。</b>':'每拍只写一个数，所以16路结果需要16拍。');
 }else if(!words){title=p.done?'等待软件取结果':'等待下一条命令';en=p.done?'DONE IS STICKY':'IDLE';words=p.done?'核心已空闲，<b>DONE=1、IRQ=1</b> 持续保持。主机可以读取输出窗口，也可以写 CONTROL.bit1 清除完成标志。':'接口空闲时 <code>cmd_ready=1</code>。主机保持 VALID、地址和写数据，直到某个上升沿 VALID 与 READY 同时为1。';}
 return {title,en,words};
}
function inspector(f){
 const p=f.pre,q=f.post,iscore=c().type==='core',key=iscore?'state':'host_state';
 $('edgeNumber').textContent=edgeLabel(f);$('fsmLabel').textContent=iscore?'计算状态机 · 沿前 → 沿后':'总线状态机 · 沿前 → 沿后';$('beforeState').textContent=fmt(key,p[key]);$('afterState').textContent=fmt(key,q[key]);
 const chips=iscore?['busy','done','irq']:['cmd_ready','rsp_valid','rsp_err'];$('statusChips').innerHTML=chips.map(k=>`<span class="chip${q[k]?' on':''}${k==='rsp_err'&&q[k]?' hot':''}">${names[k]||k} ${q[k]??'X'}</span>`).join('');
 $('edgeNote').textContent=state.scene===3?`第${q.row}行 / 第${q.group}组；本沿后核心计数 ${q.cycles}。C0不计入活动拍。`:state.scene===4?`采样窗口从 C${frames()[0].post.cycles} 开始；省略此前组的重复执行。`:`仿真全局第 ${f.edge} 个上升沿；场景只截取相关的 ${frames().length} 个沿。`;
 $('formula').textContent=command(f)?'cmd_valid ∧ cmd_ready = 1':response(f)?'rsp_valid ∧ rsp_ready = 1':p.rsp_valid&&!p.rsp_ready?'VALID=1, READY=0 → HOLD':iscore?`cycles: ${p.cycles} → ${q.cycles}`:'握手只发生在上升沿';
 const keys=iscore?(p.state===4?['cycles','y_addr','write_lane','y_wdata','done']:p.state===1?['cycles','b_addr','bias_valid','bias_lane','acc0']:['cycles','mac_issue','read_valid','product0','acc0']):['cmd_ready','rsp_valid','rsp_err','rsp_rdata','x_rdata'];
 $('details').innerHTML=keys.map(k=>`<tr><td title="${names[k]||k}">${names[k]||k}</td><td title="${fmt(k,p[k])}">${fmt(k,p[k])}</td><td class="${p[k]!==q[k]?'changed':''}" title="${fmt(k,q[k])}">${fmt(k,q[k])}</td></tr>`).join('');
 const d=describe(f);$('phase').innerHTML=`${d.title}<small>${d.en}</small>`;$('narration').innerHTML=d.words;
}
function pipeline(f){
 const p=f.pre,q=f.post,visible=p.state===2||q.state===2||state.scene===3;
 $('datapath').hidden=!visible;if(!visible)return;
 const s=stageInfo(f),stages=[['readStage','01 / SRAM','同步读取',s.read,s.read!==null?`k = ${s.read}`:'—',s.read!==null?`沿后 X=${q.x_rdata}，W₀=${q.w0_rdata}`:'本沿不再发起数据读取'],['multiplyStage','02 / MULTIPLY','乘积寄存器',s.mul,s.mul!==null?String(q.product0):'—',s.mul!==null?`${p.x_rdata} × ${p.w0_rdata}，原始整数乘积`:'等待 SRAM 数据或已流完'],['accStage','03 / ACCUMULATE','40位累加器',s.acc,s.acc!==null?String(q.acc0):'—',s.acc!==null?`${p.acc0} + ${p.product0}`:'先预置偏置，再等待乘积']];
 for(const [id,n,title,k,value,note] of stages){const el=$(id);el.classList.toggle('active',k!==null);el.innerHTML=`<div class="stage-num">${n}</div><h3>${title}</h3><div class="stagevalue">${value}</div><p>${note}</p><span class="token">${k!==null?'k='+k:'空拍'}</span>${k!==null&&state.playing?'<i class="pulse"></i>':''}`;}
}
function waveform(){
 const canvas=$('waveCanvas'),viewport=canvas.parentElement,labelW=viewport.clientWidth<560?112:144,minW=labelW+12+state.window*36;
 canvas.style.minWidth=minW+'px';const rect=canvas.getBoundingClientRect();if(!rect.width)return;const fs=frames(),rows=['clk',...c().keys],cols=Math.min(state.window,fs.length),start=clamp(state.index-Math.floor(cols*.42),0,Math.max(0,fs.length-cols));
 const W=Math.max(minW,rect.width),headH=43,rowH=29,H=headH+rows.length*rowH+13,cellW=(W-labelW-12)/cols,dpr=Math.min(window.devicePixelRatio||1,2);
 canvas.style.height=H+'px';if(canvas.width!==Math.round(W*dpr)||canvas.height!==Math.round(H*dpr)){canvas.width=Math.round(W*dpr);canvas.height=Math.round(H*dpr);}const ctx=canvas.getContext('2d');ctx.setTransform(dpr,0,0,dpr,0,0);ctx.clearRect(0,0,W,H);drawLayout={W,H,labelW,headH,rowH,cellW,start,cols};
 ctx.font='10px Consolas, monospace';ctx.textBaseline='middle';
 // Each cell contains the PRE-edge sample. The highlighted line is the edge
 // whose POST-NBA changes are shown in the inspector, not an extra cycle.
 const selectedX=labelW+(state.index-start+.5)*cellW;
 ctx.fillStyle='#efb3880c';ctx.fillRect(selectedX-cellW/2,headH,cellW,H-headH);
 for(let col=0;col<cols;col++){const f=fs[start+col],x=labelW+(col+.5)*cellW;ctx.strokeStyle='#2d464e';ctx.lineWidth=1;ctx.setLineDash([2,4]);ctx.beginPath();ctx.moveTo(x,headH-5);ctx.lineTo(x,H-9);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=start+col===state.index?'#f1bb93':'#8ca9a2';ctx.font=`${start+col===state.index?'600 ':''}9px Consolas, monospace`;const label=edgeLabel(f);ctx.fillText(label,x-ctx.measureText(label).width/2,18);if(command(f)||response(f)){ctx.fillStyle=command(f)?'#77c3b6':'#efb388';ctx.beginPath();ctx.arc(x,33,2.5,0,Math.PI*2);ctx.fill();}}
 for(let r=0;r<rows.length;r++){
  const key=rows[r],cy=headH+r*rowH+rowH/2,high=cy-7,low=cy+7;ctx.strokeStyle='#24404a';ctx.lineWidth=.7;ctx.beginPath();ctx.moveTo(12,cy+rowH/2);ctx.lineTo(W-10,cy+rowH/2);ctx.stroke();ctx.fillStyle=key==='clk'?'#8fa69f':color(key);ctx.font='10px Consolas, monospace';ctx.fillText(key==='clk'?'clk ↑':names[key]||key,14,cy);
  if(key==='clk'){ctx.strokeStyle='#789a91';ctx.lineWidth=1;ctx.beginPath();for(let col=0;col<cols;col++){const x=labelW+col*cellW;ctx.moveTo(x,low);ctx.lineTo(x+cellW/2,low);ctx.lineTo(x+cellW/2,high);ctx.lineTo(x+cellW,high);ctx.lineTo(x+cellW,low);}ctx.stroke();continue;}
  if(bits.has(key)){
   ctx.strokeStyle=color(key);ctx.lineWidth=1.5;ctx.beginPath();for(let col=0;col<cols;col++){const f=fs[start+col],value=f.pre[key],x=labelW+col*cellW,y=value===1?high:value===0?low:cy;if(col===0)ctx.moveTo(x,y);else ctx.lineTo(x,y);ctx.lineTo(x+cellW,y);}ctx.stroke();
   for(let col=0;col<cols;col++){const value=fs[start+col].pre[key],x=labelW+(col+.5)*cellW;ctx.fillStyle=value===null?'#71877f':color(key);ctx.globalAlpha=value===1?1:.4;ctx.beginPath();ctx.arc(x,value===1?high:value===0?low:cy,1.8,0,Math.PI*2);ctx.fill();ctx.globalAlpha=1;}
  }else{
   for(let col=0;col<cols;col++){const x=labelW+col*cellW,v=fs[start+col].pre[key],txt=fmt(key,v,true);ctx.strokeStyle=color(key);ctx.globalAlpha=.5;ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x+2,cy);ctx.lineTo(x+6,cy-9);ctx.lineTo(x+cellW-4,cy-9);ctx.lineTo(x+cellW-1,cy);ctx.lineTo(x+cellW-4,cy+9);ctx.lineTo(x+6,cy+9);ctx.closePath();ctx.stroke();ctx.globalAlpha=1;ctx.fillStyle=v===null?'#6d8980':color(key);ctx.font='9px Consolas, monospace';ctx.save();ctx.beginPath();ctx.rect(x+5,cy-8,Math.max(0,cellW-10),16);ctx.clip();const textW=ctx.measureText(txt).width;if(textW>cellW-11&&cols>8){ctx.font='8px Consolas, monospace';}ctx.fillText(txt,x+cellW/2-ctx.measureText(txt).width/2,cy);ctx.restore();}
  }
 }
 ctx.strokeStyle='#f0b389';ctx.lineWidth=1.5;ctx.setLineDash([]);ctx.beginPath();ctx.moveTo(selectedX,headH-6);ctx.lineTo(selectedX,H-8);ctx.stroke();ctx.fillStyle='#f0b389';ctx.beginPath();ctx.moveTo(selectedX-4,headH-7);ctx.lineTo(selectedX+4,headH-7);ctx.lineTo(selectedX,headH-1);ctx.closePath();ctx.fill();
}
function render(){
 const f=frame();$('progress').max=frames().length-1;$('progress').value=state.index;$('progress').setAttribute('aria-valuetext',edgeLabel(f));$('progressValue').textContent=`${state.index+1} / ${frames().length}`;
 $('prev').disabled=state.index===0;$('next').disabled=state.index===frames().length-1;$('play').textContent=state.playing?'Ⅱ 暂停动画':state.index===frames().length-1?'↻ 重新播放':'▶ 播放时序';
 document.querySelectorAll('.jump').forEach(b=>b.classList.toggle('active',Number(b.dataset.index)===state.index));
 inspector(f);pipeline(f);waveform();
}
function pause(){state.playing=false;lastTick=0;}
function seek(i){pause();state.index=clamp(i,0,frames().length-1);render();}
function selectScene(s){pause();state.scene=s;state.index=0;document.querySelectorAll('.tab').forEach((b,i)=>{b.setAttribute('aria-selected',String(i===s));b.tabIndex=i===s?0:-1;});const tab=$('scene-'+s);$('tabs').scrollLeft=tab.offsetLeft-$('tabs').offsetLeft-($('tabs').clientWidth-tab.offsetWidth)/2;$('sceneTitle').textContent=c().title;$('sceneSubtitle').textContent=c().sub;$('windowTitle').textContent=c().type==='bus'?'ICB BUS':'CORE PIPELINE';$('captureBadge').textContent=`RTL TRACE / ${frames().length} EDGES`;$('datapath').hidden=c().type!=='core';buildJumps();render();}
function play(){if(state.index===frames().length-1)state.index=0;state.playing=!state.playing;lastTick=0;render();}
function loop(time){if(state.playing&&!document.hidden){if(!lastTick)lastTick=time;if(time-lastTick>=750/state.speed){lastTick=time;if(state.index<frames().length-1)state.index++;if(state.index===frames().length-1)pause();render();}}requestAnimationFrame(loop);}
for(let i=0;i<config.length;i++){const b=document.createElement('button');b.className='tab';b.type='button';b.role='tab';b.id='scene-'+i;b.setAttribute('aria-controls','timing-content');b.innerHTML=`<span class="num">${String(i+1).padStart(2,'0')}</span><span><b>${config[i].name}</b><small>${config[i].short}</small></span>`;b.addEventListener('click',()=>selectScene(i));b.addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();e.stopPropagation();const next=(state.scene+(e.key==='ArrowRight'?1:6))%7;selectScene(next);$('scene-'+next).focus();}});$('tabs').append(b);}
document.querySelector('.lab').id='timing-content';document.querySelector('.lab').setAttribute('role','tabpanel');
$('play').addEventListener('click',play);$('prev').addEventListener('click',()=>seek(state.index-1));$('next').addEventListener('click',()=>seek(state.index+1));$('progress').addEventListener('input',()=>seek(Number($('progress').value)));$('speed').addEventListener('change',()=>{state.speed=Number($('speed').value);lastTick=0;});$('windowSize').addEventListener('change',()=>{state.window=Number($('windowSize').value);waveform();});
$('waveCanvas').addEventListener('click',e=>{if(!drawLayout)return;const rect=e.currentTarget.getBoundingClientRect(),x=(e.clientX-rect.left)*drawLayout.W/rect.width;if(x<drawLayout.labelW)return;seek(drawLayout.start+Math.floor((x-drawLayout.labelW)/drawLayout.cellW));});
document.addEventListener('keydown',e=>{if(e.target.closest('input,select,button,a,summary'))return;if(e.code==='Space'){e.preventDefault();play();}else if(e.key==='ArrowRight'){e.preventDefault();seek(state.index+1);}else if(e.key==='ArrowLeft'){e.preventDefault();seek(state.index-1);}});
document.addEventListener('visibilitychange',()=>lastTick=0);window.addEventListener('resize',waveform);
$('sourceHash').textContent=TRACE.meta.rtl_sha256;$('frameCount').textContent=TRACE.scenarios.reduce((sum,s)=>sum+s.length,0);
window.timingLab=Object.freeze({snapshot:()=>({...state,label:edgeLabel(frame()),frame:frame(),stages:stageInfo(frame()),meta:TRACE.meta}),trace:()=>TRACE,select:selectScene,seek});
$('windowSize').value=state.window;selectScene(3);requestAnimationFrame(loop);
})();
