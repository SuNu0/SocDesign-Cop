'use strict';
const $=id=>document.getElementById(id);
const escapeHtml=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const number=value=>Number(value).toLocaleString('en-US');
const app={config:'small',lane:0,presentation:'timing',playing:false,timer:null,jumping:false,jumpToken:0,inspect:null,fullCode:false,traceOpen:true};
let machine=new FfnMachine(CONFIGS.small);
const timing=new TimingDiagram({
  onSelect(){pause();app.inspect=null;render()},
  onLane(lane){app.lane=lane;render()},
  async onDemo(){
    await jumpTo('oneGroup');timing.group='mac';$('waveGroup').value='mac';
    timing.span=app.config==='actual'?120:24;$('waveSpan').value=String(timing.span);
    const firstAdd=machine.waveTrace.find(e=>e.ops.some(o=>o.kind==='accumulate'));
    timing.follow=false;timing.start=0;timing.selectedId=firstAdd?firstAdd.waveId:null;render();
    const scroll=$('waveScroll');if(firstAdd)scroll.scrollLeft=Math.max(0,(firstAdd.time-timing.start)*timing.zoom-scroll.clientWidth/2);
  }
});
const SOURCE_LINES=["  always_ff @(posedge clk or negedge rst_n) begin", "    if (!rst_n) begin", "      state<=S_IDLE; done<=0; cycle_count<=0; saturation_count<=0;", "      row_index<=0; group_index<=0; write_lane<=0;", "      bias_issue<=0; bias_valid<=0; bias_lane_d<=0;", "      mac_issue<=0; mac_read_valid<=0; mac_read_last<=0;", "      product_valid<=0; product_last<=0;", "      for (lane=0;lane<LANES;lane=lane+1) begin", "        accumulator[lane]<=0; product[lane]<=0; output_buffer[lane]<=0;", "      end", "    end else begin", "      if (clear_done) done<=0;", "      if (busy) cycle_count<=cycle_count+1;", "      case (state)", "        S_IDLE: if (start_event) begin", "          done<=0; cycle_count<=0; saturation_count<=0;", "          row_index<=0; group_index<=0; write_lane<=0;", "          bias_issue<=0; bias_valid<=0; mac_issue<=0;", "          mac_read_valid<=0; product_valid<=0;", "          state<=S_BIAS;", "        end", "        S_BIAS: begin", "          // 16 synchronous bias reads + one drain cycle. Bias is aligned to Q16.", "          bias_valid<=(bias_issue<16);", "          if (bias_issue<16) begin", "            bias_lane_d<=bias_issue[3:0]; bias_issue<=bias_issue+1;", "          end", "          if (bias_valid) begin", "            accumulator[bias_lane_d]<=", "              $signed({{24{b_rdata[15]}},b_rdata}) <<< 8;", "            if (bias_lane_d==15) begin", "              mac_issue<=0; mac_read_valid<=0; mac_read_last<=0;", "              product_valid<=0; product_last<=0; state<=S_MAC;", "            end", "          end", "        end", "        S_MAC: begin", "          // SRAM read -> registered 16x16 products -> 40-bit accumulation.", "          mac_read_valid<=(mac_issue<64);", "          mac_read_last<=(mac_issue==63);", "          if (mac_issue<64) mac_issue<=mac_issue+1;", "          product_valid<=mac_read_valid; product_last<=mac_read_last;", "          if (mac_read_valid)", "            for (lane=0;lane<LANES;lane=lane+1)", "              product[lane]<=$signed(x_rdata)*$signed(w_rdata[lane]);", "          if (product_valid)", "            for (lane=0;lane<LANES;lane=lane+1)", "              accumulator[lane]<=accumulator[lane]+", "                $signed({{8{product[lane][31]}},product[lane]});", "          if (product_valid && product_last) state<=S_ROUND;", "        end", "        S_ROUND: begin", "          for (lane=0;lane<LANES;lane=lane+1)", "            output_buffer[lane]<=quantized[lane][15:0];", "          saturation_count<=saturation_count+{27'd0,saturation_increment};", "          write_lane<=0; state<=S_WRITE;", "        end", "        S_WRITE: begin", "          if (write_lane==15) begin", "            if (group_index==15 && row_index==98) begin", "              done<=1; state<=S_IDLE;", "            end else begin", "              if (group_index==15) begin group_index<=0; row_index<=row_index+1; end", "              else group_index<=group_index+1;", "              bias_issue<=0; bias_valid<=0; state<=S_BIAS;", "            end", "          end else write_lane<=write_lane+1;", "        end", "        default: state<=S_IDLE;", "      endcase", "    end", "  end"];
const states=[
  ['S_IDLE','等待启动'],['S_BIAS','装入偏置'],['S_MAC','乘法与累加'],['S_ROUND','保存量化结果'],['S_WRITE','逐个写回']
];
const codeRanges={S_IDLE:[228,234],S_BIAS:[235,249],S_MAC:[250,264],S_ROUND:[265,270],S_WRITE:[271,281]};
function viewEvent(){return timing.selection(machine)||machine.last}
function currentExplanation(){return app.inspect||viewEvent().before.state}
function render(){
  const r=machine.reg,c=machine.config,last=viewEvent(),reviewing=Boolean(timing.selection(machine));
  const inTiming=app.presentation==='timing';
  document.body.classList.toggle('timing-view',inTiming);$('stateMap').hidden=inTiming;$('timingPanel').hidden=!inTiming;
  $('timingMode').classList.toggle('active',inTiming);$('timingMode').setAttribute('aria-pressed',String(inTiming));
  $('routeMode').classList.toggle('active',!inTiming);$('routeMode').setAttribute('aria-pressed',String(!inTiming));
  $('configNote').textContent=app.config==='small'?'先用较小数量看懂循环。动画中的阈值改为 4 / 4 / 1；右侧代码保留工程原文。':'严格使用工程的 16 通道、64 项乘加、99 行、16 组阈值。';
  $('budget').textContent='每组 '+machine.groupCycles+' 拍 · 全任务 '+number(machine.totalCycles)+' 个 busy 时钟';
  $('stateNodes').innerHTML=states.map(([state,label],i)=>'<button class="state-node '+(r.state===state?'current ':'')+(app.inspect===state?'inspect':'')+'" data-state="'+state+'" '+(r.state===state?'aria-current="step"':'')+'><span class="state-number">0'+(i+1)+'</span><code>'+state+'</code><span>'+label+'</span></button>').join('');
  $('metricState').textContent=r.state;
  $('metricFlags').innerHTML='<span class="'+(machine.busy?'good':'off')+'" style="display:inline;font:inherit">'+machine.busy+'</span> / <span class="'+(r.done?'good':'off')+'" style="display:inline;font:inherit">'+r.done+'</span>';
  $('metricCycles').textContent=number(r.cycle_count);
  $('metricPosition').textContent=r.row_index+' / '+r.group_index;
  $('metricWritten').textContent=number(machine.taskWrites)+' / '+number(machine.totalOutputs);
  $('metricSaturation').textContent=number(r.saturation_count);
  const changed=last.before.state!==last.after.state;
  $('edgeTitle').textContent=(reviewing?(last.edge!==null?'回看 ↑'+last.edge+'：':'回看异步事件：'):'')+(last.kind==='clock'?(changed?last.before.state+' → '+last.after.state:'执行 '+last.before.state):last.kind==='reset'?'异步复位，立即生效':last.kind==='release'?'释放复位，等待时钟':'从 S_IDLE 出发');
  $('clockBadge').textContent=(reviewing?'选中 ↑'+(last.edge??'异步')+' / 当前 ↑'+number(machine.edges):'↑ '+number(machine.edges))+' · rst_n='+last.rstAfter;
  $('edgeReason').textContent=last.reason;
  $('lane').innerHTML=Array.from({length:c.lanes},(_,i)=>'<option value="'+i+'" '+(app.lane===i?'selected':'')+'>lane '+i+'</option>').join('');
  renderOperations();renderChanges();renderTrace();renderOutputs();renderCode();renderLesson();renderControls();timing.render(machine,app.lane);
}
function renderControls(){
  const r=machine.reg,locked=machine.rstLow||app.jumping;
  $('start').disabled=locked||machine.busy===1;
  $('start').textContent=r.done?'启动下一次任务':'发出启动';
  $('step').disabled=app.jumping;
  $('nextState').disabled=locked;
  $('play').disabled=machine.rstLow;
  $('play').textContent=app.jumping?'■ 停止定位':app.playing?'Ⅱ 暂停':r.done?'↻ 重新播放':'▶ 自动播放';
  $('clear').disabled=app.jumping||machine.rstLow;
  $('reset').textContent=machine.rstLow?'释放复位':'拉低复位';
  $('jump').disabled=app.jumping;
  $('waveDemo').disabled=app.jumping;
  $('controlNote').textContent=app.jumping?'正在从头重放到目标边界… 已执行 '+number(machine.edges)+' 个时钟沿。可以点击“停止定位”。':machine.rstLow?'rst_n 保持为低：单步时钟可以继续产生沿，但寄存器保持复位值。点击“释放复位”后才能正常启动。':'“发出启动”会产生一次带 start_event 的时钟沿；“单步时钟”每次只推进一个真实模型时钟。定位会从头重放到所选边界。';
}
function renderOperations(){
  const event=viewEvent(),ops=event.ops,lane=app.lane;
  const find=kind=>ops.find(op=>op.kind===kind);
  const read=find('read'),biasRead=find('biasRead'),mul=find('multiply'),acc=find('accumulate'),load=find('biasLoad'),round=find('round'),write=find('write');
  let cards=[
    {title:'SRAM 本拍采样',tag:'READ',math:'没有新的读取',note:'关闭读取不表示存储器清零。'},
    {title:'乘积本拍保存',tag:'MULTIPLY',math:'没有有效乘法输入',note:'mac_read_valid=1 才保存新的 product。'},
    {title:'累加器本拍更新',tag:'ACCUMULATE',math:'累加器保持原值',note:'product_valid=1 才加入一个旧 product。'}
  ];
  if(read)cards[0]={title:'SRAM 读取 · k='+read.k,tag:'READ',math:'X = '+number(read.x)+'<br>W['+lane+'] = '+number(read.weights[lane]),note:'本拍读回的新数据，下一拍才能用于乘法。',active:true};
  if(biasRead)cards[0]={title:'读取偏置 · lane '+biasRead.lane,tag:'BIAS READ',math:'B = '+number(biasRead.value),note:'本拍发出的读取，偏置在沿后返回。',active:true};
  if(mul)cards[1]={title:'保存乘积 · k='+mul.k,tag:'PRODUCT',math:number(mul.x)+' × '+number(mul.weights[lane])+'<br>= '+number(mul.products[lane]),note:'乘的是上拍 SRAM 数据；本拍新 product 不会立刻参与累加。',active:true,color:'blue'};
  if(load)cards[2]={title:'装入偏置 · lane '+load.lane,tag:'BIAS LOAD',math:number(load.bias)+' × 256<br>= '+number(load.result),note:'上拍返回的偏置扩展为 40 位，再左移 8 位，与乘积尺度对齐。',active:true};
  if(acc)cards[2]={title:'加入旧乘积 · k='+acc.k,tag:'ACCUMULATE',math:number(acc.before[lane])+' + '+number(acc.products[lane])+'<br>= '+number(acc.after[lane]),note:'这个乘积属于更早的读取。观察三个卡片的 k 编号。',active:true,color:'orange'};
  if(round){
    const q=round.quantized[lane];
    cards=[{title:'读取最终累加值',tag:'40 BIT',math:number(event.before.accumulator[lane]),note:'最后一个乘积在上一拍已经加入。',active:true},
      {title:'本拍保存量化结果',tag:'16 BIT',math:'lane '+lane+' → '+number(q.data)+'<br>饱和标志 = '+q.flag,note:'全部 '+machine.config.lanes+' 条通道同拍保存到 output_buffer。',active:true,color:'blue'},
      {title:'更新饱和总计',tag:'COUNT',math:number(event.before.saturation_count)+' + '+round.increment+'<br>= '+number(event.after.saturation_count),note:'每组只在 S_ROUND 累计一次，不是在每次乘法时累计。',active:true,color:'orange'}];
  }
  if(write)cards=[{title:'选中输出缓冲',tag:'LANE '+write.lane,math:'output_buffer['+write.lane+']<br>= '+number(write.data),note:'使用时钟沿前的 write_lane 选通道。',active:true},
    {title:'本拍写入 SRAM',tag:'Y WRITE',math:'Y['+write.row+']['+write.col+']<br>← '+number(write.data),note:'内部存储地址 = '+write.address+'；每拍写一个 16 位结果。',active:true,color:'blue'},
    {title:'更新写回进度',tag:'NEXT',math:'write_lane: '+event.before.write_lane+' → '+event.after.write_lane,note:event.after.state!=='S_WRITE'?'这组写完，状态切换。write_lane 要到下一次 S_ROUND 才清零。':'下一拍继续写下一个通道。',active:true,color:'orange'}];
  $('operations').innerHTML=cards.map(card=>'<article class="op-card '+(card.active?'active ':'')+(card.color||'')+'"><div class="op-title"><span>'+card.title+'</span><span class="op-tag">'+card.tag+'</span></div><div class="op-math">'+card.math+'</div><p>'+card.note+'</p></article>').join('');
}
function renderChanges(){
  const event=viewEvent(),b=event.before,a=event.after,lane=app.lane;
  const names=['state','done','cycle_count','saturation_count','row_index','group_index','write_lane','bias_issue','bias_valid','bias_lane_d','mac_issue','mac_read_valid','mac_read_last','product_valid','product_last'];
  const rows=names.map(name=>[name,b[name],a[name]]);
  ['product','accumulator','output_buffer'].forEach(name=>rows.push([name+'['+lane+']',b[name][lane],a[name][lane]]));
  $('changes').innerHTML=rows.map(([name,before,after])=>'<tr class="'+(before!==after?'changed':'')+'"><td>'+name+'</td><td>'+escapeHtml(typeof before==='number'?number(before):before)+'</td><td>'+escapeHtml(typeof after==='number'?number(after):after)+'</td></tr>').join('');
}
function renderTrace(){
  $('traceWrap').hidden=!app.traceOpen;$('traceToggle').textContent=app.traceOpen?'收起':'展开';$('traceToggle').setAttribute('aria-expanded',String(app.traceOpen));
  $('trace').innerHTML=machine.trace.length?machine.trace.map(event=>{
    const find=k=>event.ops.find(op=>op.kind===k),read=find('read'),bias=find('biasRead'),mul=find('multiply'),acc=find('accumulate'),load=find('biasLoad'),write=find('write'),round=find('round');
    return '<tr><td>'+event.edge+'</td><td>'+event.before.state+(event.before.state!==event.after.state?' → '+event.after.state:'')+'</td><td>'+(read?'k='+read.k:bias?'B lane '+bias.lane:'—')+'</td><td>'+(mul?'k='+mul.k:'—')+'</td><td>'+(acc?'加 k='+acc.k:load?'装 B lane '+load.lane:write?'写 lane '+write.lane:round?'存全部结果':'—')+'</td></tr>';
  }).join(''):'<tr><td colspan="5" class="trace-empty">还没有时钟记录。点击“发出启动”，再按“单步时钟”。</td></tr>';
}
function renderOutputs(){
  const r=machine.reg,c=machine.config;
  $('outputPosition').textContent='row '+r.row_index+' / group '+r.group_index;
  $('outputGrid').className='output-grid'+(c.lanes===16?' dense-output':'');
  $('outputGrid').innerHTML=Array.from({length:c.lanes},(_,lane)=>{
    const address=machine.address(r.row_index,r.group_index,lane),exists=machine.outputs.has(address),written=exists&&machine.outputEpoch.get(address)===machine.epoch,value=machine.outputs.get(address);
    return '<div class="output-cell '+(written?'written ':'')+(lane===app.lane?'focus':'')+'"><small>lane '+lane+'</small><b>'+number(r.output_buffer[lane])+'</b><div class="y-value">'+(written?'Y: ':exists?'Y旧值: ':'Y: ')+(exists?number(value):'尚未写入')+'</div></div>';
  }).join('');
}
function renderCode(){
  const event=viewEvent(),view=currentExplanation(),reset=!app.inspect&&['reset','initial'].includes(event.kind);
  const range=reset?[214,224]:codeRanges[view]||[228,234];
  const visible=SOURCE_LINES.map((text,i)=>({text,line:214+i})).filter(item=>app.fullCode||(item.line>=range[0]&&item.line<=range[1])||[214,224,225,226,227,284,285].includes(item.line));
  let previous=null;
  $('code').innerHTML=visible.map(item=>{const gap=previous!==null&&item.line>previous+1;previous=item.line;return (gap?'<span class="code-line ellipsis"><span class="line-no">…</span>其他状态分支</span>':'')+'<span class="code-line '+(!app.inspect&&event.lines.includes(item.line)?'hot':'')+'"><span class="line-no">'+item.line+'</span>'+escapeHtml(item.text)+'</span>'}).join('');
  $('codeTitle').textContent=app.inspect?'查看分支：'+view:timing.selection(machine)?'所选拍执行的代码':'本拍执行的代码';
  $('fullCode').textContent=app.fullCode?'只看当前分支':'展开完整代码';$('fullCode').setAttribute('aria-pressed',String(app.fullCode));
  $('sourceMode').textContent=app.config==='small'?'入门动画：通道 16→4，乘加项 64→4，组数 16→2，行数 99→2。下方保留工程原始代码。':'工程模式：使用原始代码的全部阈值。';
  $('codeFoot').textContent=app.inspect?'点击状态节点只查看说明，不会改变正在运行的状态。':'高亮为所选事件实际执行的语句。case 选择沿前 state；沿后 state 可能已切换。行号对应 ffn_accel.sv。';
}
function renderLesson(){
  const c=machine.config,view=currentExplanation();
  const descriptions={
    S_IDLE:['等待命令，准备一轮新任务','start_event 有效的时钟沿清零本轮统计和索引，再把 state 改为 S_BIAS。该时钟沿沿前 busy=0，因此不计入忙碌周期。done 会保持到清除、重启或复位。', [['busy','0'],['启动后的状态','S_BIAS'],['接收启动这一拍','cycle_count=0']]],
    S_BIAS:['先给每条通道装入偏置','偏置 SRAM 是同步读取。先发地址，下一拍才使用返回值；bias_lane_d 让通道编号延迟一拍，与偏置对齐。左移 8 位让偏置和乘积具有相同尺度。最后一项返回后再进入乘加。',[['读取次数',String(c.lanes)],['含最后等待拍',String(c.lanes+1)+' 拍'],['装入累加器','符号扩展(B) × 256']]],
    S_MAC:['三段流水线，同时向前走','本拍 SRAM 读第 k 项、乘法保存上拍的输入、累加器加入更早保存的乘积。valid 标记有效性，last 随同数据延迟。读取发完以后，要再等两拍，直到最后乘积真正累加。',[['每通道乘积数',String(c.inner)],['填充与排空合计',String(c.inner+2)+' 拍'],['结束条件','product_valid && product_last']]],
    S_ROUND:['把最终结果一起保存','requantize 是组合逻辑，在上一拍最终累加值更新后就会响应。这个状态用一个时钟沿把所有通道的低 16 位存入 output_buffer，并把本组饱和数量加入总计。',[['停留时间','1 拍'],['并行保存',String(c.lanes)+' 个结果'],['接下来','write_lane=0，S_WRITE']]],
    S_WRITE:['算好的结果，逐个送回存储器','Y 只有一个写端口，所以每拍写一个通道。当前组最后一个结果写完后，先判断任务是否结束，再决定换组或换行。最后一个结果写完的同一拍才把 done 置 1。',[['当前组写回次数',String(c.lanes)+' 拍'],['组的范围','0～'+(c.groups-1)],['行的范围','0～'+(c.rows-1)]]]
  };
  const info=descriptions[view]||descriptions.S_IDLE;
  $('lessonTitle').textContent=info[0];$('lessonBody').textContent=info[1];
  $('stateFacts').innerHTML=info[2].map(([label,value])=>'<div class="fact"><span>'+label+'</span><b>'+value+'</b></div>').join('');
  $('follow').hidden=!app.inspect;
}
function pause(){app.playing=false;clearTimeout(app.timer);app.timer=null;if(app.jumping){app.jumpToken++;app.jumping=false}}
function clock(options={}){app.inspect=null;timing.toLatest();machine.clock(options);if(machine.reg.done&&machine.reg.state==='S_IDLE'){app.playing=false;clearTimeout(app.timer)}render();const el=$('operations');el.classList.remove('flash');void el.offsetWidth;el.classList.add('flash')}
function restart(){pause();machine=new FfnMachine(CONFIGS[app.config]);app.lane=Math.min(app.lane,machine.config.lanes-1);app.inspect=null;render()}
function schedule(){clearTimeout(app.timer);if(app.playing)app.timer=setTimeout(()=>{clock();if(app.playing)schedule()},Number($('speed').value))}
function togglePlay(){
  if(app.playing||app.jumping){pause();render();return}
  if(machine.rstLow)return;
  if(machine.reg.done)restart();
  app.playing=true;
  if(machine.reg.state==='S_IDLE')clock({start:true});
  renderControls();schedule();
}
function nextState(){
  pause();if(machine.rstLow)return;app.inspect=null;timing.toLatest();
  if(machine.reg.state==='S_IDLE')machine.clock({start:true});
  else {const state=machine.reg.state;for(let i=0;i<200&&machine.reg.state===state;i++)machine.clock()}
  render();
}
async function jumpTo(target){
  pause();const token=++app.jumpToken;app.jumping=true;app.inspect=null;
  machine=new FfnMachine(CONFIGS[app.config]);machine.clock({start:true});
  const reached=()=>{const r=machine.reg,c=machine.config;return target==='biasTail'?r.state==='S_BIAS'&&r.bias_issue===c.lanes:target==='macTail'?r.state==='S_MAC'&&r.mac_issue===c.inner:target==='groupEnd'||target==='oneGroup'?r.state==='S_WRITE'&&r.write_lane===c.lanes-1&&r.group_index===0&&r.row_index===0:target==='rowEnd'?r.state==='S_WRITE'&&r.write_lane===c.lanes-1&&r.group_index===c.groups-1&&r.row_index===0:r.state==='S_WRITE'&&r.write_lane===c.lanes-1&&r.group_index===c.groups-1&&r.row_index===c.rows-1};
  while(!reached()&&machine.edges<=machine.totalCycles+1){
    for(let i=0;i<3000&&!reached();i++)machine.clock();
    render();await new Promise(requestAnimationFrame);if(token!==app.jumpToken)return;
  }
  if(target==='oneGroup')machine.clock();
  app.jumping=false;render();
}
$('start').addEventListener('click',()=>{pause();clock({start:true})});
$('step').addEventListener('click',()=>{pause();clock()});
$('play').addEventListener('click',togglePlay);
$('nextState').addEventListener('click',nextState);
$('speed').addEventListener('change',schedule);
$('lane').addEventListener('change',e=>{app.lane=Number(e.target.value);render()});
$('config').addEventListener('change',e=>{app.config=e.target.value;restart()});
$('jump').addEventListener('click',()=>jumpTo($('jumpTarget').value));
$('clear').addEventListener('click',()=>{pause();clock({clear:true})});
$('reset').addEventListener('click',()=>{pause();app.inspect=null;timing.toLatest();machine.setReset(!machine.rstLow);render()});
$('restart').addEventListener('click',restart);
$('stateNodes').addEventListener('click',e=>{const button=e.target.closest('[data-state]');if(button){pause();timing.toLatest();app.inspect=button.dataset.state;render()}});
$('follow').addEventListener('click',()=>{app.inspect=null;render()});
$('fullCode').addEventListener('click',()=>{app.fullCode=!app.fullCode;renderCode()});
$('traceToggle').addEventListener('click',()=>{app.traceOpen=!app.traceOpen;renderTrace()});
$('timingMode').addEventListener('click',()=>{app.presentation='timing';render()});
$('routeMode').addEventListener('click',()=>{timing.toLatest();app.presentation='route';render()});
document.addEventListener('keydown',e=>{if(e.target.closest('button,select,input,textarea,a,summary'))return;if(e.code==='Space'){e.preventDefault();togglePlay()}else if(e.key==='ArrowRight'&&!app.jumping){e.preventDefault();pause();clock()}});
document.addEventListener('visibilitychange',()=>{if(document.hidden&&app.playing){pause();renderControls()}});
render();
