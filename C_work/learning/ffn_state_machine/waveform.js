'use strict';
const waveEscape=value=>String(value).replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const waveNumber=value=>typeof value==='number'?value.toLocaleString('en-US'):String(value);
const WAVE_PRESETS={
  overview:['clk','rst_n','start_event','clear_done','state','busy','done','cycle_count','row_index','group_index','write_lane'],
  bias:['clk','rst_n','state','bias_issue','bias_valid','bias_lane_d','b_rdata','bias_event','load_event','accumulator'],
  mac:['clk','rst_n','state','mac_issue','mac_read_valid','mac_read_last','product_valid','product_last','read_event','multiply_event','accumulate_event','product','accumulator'],
  write:['clk','rst_n','state','accumulator','quantized','output_buffer','saturation_increment','saturation_count','write_lane','y_en','write_event','done']
};
const WAVE_SIGNALS={
  clk:['clk','1 bit','clock'],rst_n:['rst_n','低有效复位','bit'],state:['state','3 bit · 沿后状态','bus'],
  start_event:['start_event','时钟沿前的启动输入','pulse'],clear_done:['clear_done','时钟沿前的清除输入','pulse'],
  busy:['busy','state ≠ S_IDLE','bit'],done:['done','保持型完成标志','bit'],cycle_count:['cycle_count','32 bit','bus'],
  row_index:['row_index','7 bit','bus'],group_index:['group_index','4 bit','bus'],write_lane:['write_lane','4 bit','bus'],
  bias_issue:['bias_issue','5 bit · 下一次读取进度','bus'],bias_valid:['bias_valid','1 bit · 偏置数据有效','bit'],bias_lane_d:['bias_lane_d','4 bit · 延迟通道编号','bus'],
  b_rdata:['b_rdata','16 bit · 偏置返回数据','bus'],mac_issue:['mac_issue','7 bit · 下一次读取进度','bus'],
  mac_read_valid:['mac_read_valid','1 bit · 乘法输入有效','bit'],mac_read_last:['mac_read_last','1 bit · 最后一次读取','bit'],
  product_valid:['product_valid','1 bit · 旧乘积可累加','bit'],product_last:['product_last','1 bit · 最后一个乘积','bit'],
  x_rdata:['x_rdata','16 bit · 输入返回数据','bus'],w_rdata:['w_rdata[lane]','16 bit · 权重返回数据','bus'],
  product:['product[lane]','32 bit · signed','bus'],accumulator:['accumulator[lane]','40 bit · signed','bus'],
  quantized:['quantized[lane][15:0]','组合量化结果 · signed 解读','bus'],output_buffer:['output_buffer[lane]','16 bit · signed 解读','bus'],
  saturation_increment:['saturation_increment','5 bit · 当前组饱和数','bus'],saturation_count:['saturation_count','32 bit · 全任务饱和总计','bus'],
  y_en:['y_en / y_we','1 bit · S_WRITE 时写使能','bit'],
  bias_event:['本拍读偏置 · 事件','B lane 编号，不是寄存器','event'],load_event:['本拍装偏置 · 事件','实际更新的 lane','event'],
  read_event:['本拍读取 · 事件','k：读取 X 与所有 W','event'],multiply_event:['本拍乘法 · 事件','k：保存哪些输入的乘积','event'],
  accumulate_event:['本拍累加 · 事件','k：加入哪个旧乘积','event'],write_event:['本拍写 Y · 事件','lane：写回哪个缓冲结果','event']
};
const WAVE_STATE_COLORS={S_IDLE:'#edf0e9',S_BIAS:'#f4eedb',S_MAC:'#e2eee5',S_ROUND:'#e5edf5',S_WRITE:'#f7eade'};
class TimingDiagram {
  constructor(callbacks){
    this.callbacks=callbacks;this.owner=null;this.selectedId=null;this.group='mac';this.span=24;this.zoom=88;this.start=0;this.follow=true;this.drawArrows=true;this.latestDrawn=null;
    this.$=id=>document.getElementById(id);
    this.$('waveGroup').addEventListener('change',e=>{this.group=e.target.value;this.renderCurrent()});
    this.$('waveSpan').addEventListener('change',e=>{this.span=Number(e.target.value);this.renderCurrent()});
    this.$('waveZoom').addEventListener('change',e=>{this.zoom=Number(e.target.value);this.latestDrawn=null;this.renderCurrent()});
    this.$('waveArrows').addEventListener('change',e=>{this.drawArrows=e.target.checked;this.renderCurrent()});
    this.$('waveLane').addEventListener('change',e=>callbacks.onLane(Number(e.target.value)));
    this.$('waveHistory').addEventListener('input',e=>{this.follow=false;this.start=Number(e.target.value);this.$('waveScroll').scrollLeft=0;this.renderCurrent()});
    this.$('waveEarlier').addEventListener('click',()=>this.move(-Math.max(1,Math.floor(this.span/2))));
    this.$('waveLater').addEventListener('click',()=>this.move(Math.max(1,Math.floor(this.span/2))));
    this.$('waveFollow').addEventListener('click',()=>{this.toLatest();callbacks.onSelect()});
    this.$('waveDemo').addEventListener('click',()=>callbacks.onDemo());
    this.$('waveSvg').addEventListener('click',e=>{const hit=e.target.closest('[data-wave-id]');if(hit)this.select(Number(hit.dataset.waveId))});
    this.$('waveSvg').addEventListener('keydown',e=>{const hit=e.target.closest('[data-wave-id]');if(hit&&(e.key==='Enter'||e.key===' ')){e.preventDefault();e.stopPropagation();this.select(Number(hit.dataset.waveId))}});
    this.$('waveScroll').addEventListener('scroll',()=>{this.$('waveLabels').scrollTop=this.$('waveScroll').scrollTop});
  }
  selection(machine){return this.owner===machine&&this.selectedId!==null?machine.waveTrace.find(e=>e.waveId===this.selectedId)||null:null}
  toLatest(){this.selectedId=null;this.follow=true;this.latestDrawn=null}
  select(id){this.selectedId=id;this.follow=false;this.callbacks.onSelect()}
  move(amount){this.follow=false;this.start=Math.max(this.minStart,Math.min(this.maxStart,this.start+amount));this.$('waveScroll').scrollLeft=0;this.renderCurrent()}
  renderCurrent(){if(this.owner)this.render(this.owner,this.lane)}
  signalValue(key,event,side){
    const r=event[side],sram=event[side==='before'?'sramBefore':'sramAfter'],lane=this.lane;
    if(key==='rst_n')return event[side==='before'?'rstBefore':'rstAfter'];
    if(key==='busy')return Number(r.state!=='S_IDLE');
    if(key==='y_en')return Number(r.state==='S_WRITE');
    if(key==='b_rdata')return sram.b?sram.b.value:'—';
    if(key==='x_rdata')return sram.read?sram.read.x:'—';
    if(key==='w_rdata')return sram.read?sram.read.weights[lane]:'—';
    if(['product','accumulator','output_buffer'].includes(key))return r[key][lane];
    if(key==='quantized')return quantize(r.accumulator[lane]).data;
    if(key==='saturation_increment')return r.accumulator.reduce((v,acc)=>v+quantize(acc).flag,0);
    return r[key];
  }
  points(key,type,events,end){
    let all=[];
    if(type==='clock'){
      events.filter(e=>e.kind==='clock').forEach(e=>{all.push({time:e.time,value:1},{time:e.time+0.5,value:0})});
    }else if(type==='pulse'){
      const input=key==='start_event'?'start':'clear';
      events.filter(e=>e.kind==='clock'&&e.inputs[input]).forEach(e=>all.push({time:e.time-0.28,value:1},{time:e.time+0.08,value:0}));
    }else{
      all=[{time:events[0].time-1,value:this.signalValue(key,events[0],'before')},...events.map(e=>({time:e.time,value:this.signalValue(key,e,'after')}))];
    }
    all.sort((a,b)=>a.time-b.time);
    let value=type==='clock'||type==='pulse'?0:all[0].value;
    for(const point of all){if(point.time<=this.start)value=point.value;else break}
    const result=[{time:this.start,value}];
    for(const point of all){if(point.time>this.start&&point.time<=end&&point.value!==result[result.length-1].value)result.push(point)}
    return result;
  }
  eventAction(key,event){
    const kinds={read_event:'read',multiply_event:'multiply',accumulate_event:'accumulate',bias_event:'biasRead',load_event:'biasLoad',write_event:'write'};
    const op=event.ops.find(op=>op.kind===kinds[key]);
    if(!op)return null;
    return {label:op.k!==undefined?'k='+op.k:'L'+op.lane,title:op.kind==='write'?'Y['+op.row+']['+op.col+'] ← '+op.data:op.k!==undefined?op.kind+' 第 '+op.k+' 项':'lane '+op.lane};
  }
  render(machine,lane){
    const ownerChanged=this.owner!==machine;
    if(ownerChanged){this.owner=machine;this.toLatest();this.start=0}
    this.lane=lane;
    if(this.$('timingPanel').hidden)return;
    const events=machine.waveTrace,last=events[events.length-1];
    this.minStart=Math.max(0,Math.floor(events[0].time-0.65));
    this.maxStart=Math.max(this.minStart,Math.ceil(last.time+1)-this.span);
    this.start=this.follow?this.maxStart:Math.max(this.minStart,Math.min(this.maxStart,this.start));
    const selected=this.selection(machine),focus=selected||machine.last;
    const rows=this.group==='all'?Object.keys(WAVE_SIGNALS):WAVE_PRESETS[this.group];
    const rowH=34,top=54,width=this.span*this.zoom+24,height=top+rows.length*rowH+15;
    const limit=Math.min(this.start+this.span,last.time+0.7),x=t=>12+(t-this.start)*this.zoom;
    const y=i=>top+i*rowH;
    this.$('waveLane').innerHTML=Array.from({length:machine.config.lanes},(_,i)=>'<option value="'+i+'" '+(i===lane?'selected':'')+'>lane '+i+'</option>').join('');
    this.$('waveLabels').innerHTML='<div class="wave-label-axis">信号 / 从左向右读 →</div>'+rows.map(key=>{const d=WAVE_SIGNALS[key];return '<div class="wave-label '+(d[2]==='event'?'is-event':'')+'" title="'+waveEscape(d[0]+' · '+d[1])+'"><b>'+waveEscape(d[0].replace('[lane]','['+lane+']'))+'</b><small>'+waveEscape(d[1])+'</small></div>'}).join('');
    let svg='<defs><marker id="waveArrowHead" markerWidth="6" markerHeight="6" refX="5" refY="3" orient="auto"><path d="M0,0 L6,3 L0,6" fill="#bf6b38"/></marker></defs><rect width="'+width+'" height="'+height+'" fill="#fffefa"/>';
    for(let i=0;i<rows.length;i++){
      svg+='<rect x="0" y="'+y(i)+'" width="'+width+'" height="'+rowH+'" fill="'+(WAVE_SIGNALS[rows[i]][2]==='event'?'#fbf2e7':i%2?'#f7f8f2':'#fffefa')+'"/><line x1="0" y1="'+(y(i)+rowH)+'" x2="'+width+'" y2="'+(y(i)+rowH)+'" stroke="#e9ecdf"/>';
    }
    for(let t=Math.ceil(this.start);t<=this.start+this.span;t++){
      svg+='<line x1="'+x(t)+'" y1="25" x2="'+x(t)+'" y2="'+(height-8)+'" stroke="#d5dfcd" stroke-dasharray="3 5"/><text x="'+(x(t)+5)+'" y="21" class="wave-tick">'+(t===0?'初始':'↑'+t.toLocaleString('en-US'))+'</text>';
    }
    svg+='<text x="14" y="42" class="wave-axis-note">上升沿左侧：旧值　│　右侧：更新后</text>';
    rows.forEach((key,index)=>{
      const type=WAVE_SIGNALS[key][2],base=y(index),color=['product_valid','product_last','product'].includes(key)?'#467b97':['accumulator','accumulate_event'].includes(key)?'#b76c36':'#2a7358';
      if(type==='event'){
        for(const event of events){if(event.time<this.start||event.time>limit)continue;const action=this.eventAction(key,event);if(!action)continue;
          const cx=x(event.time),w=Math.min(this.zoom*0.8,100);
          svg+='<g class="wave-event" data-event-type="'+key+'" data-edge="'+event.edge+'"><title>'+waveEscape(action.title)+'</title><rect x="'+(cx-w/2)+'" y="'+(base+6)+'" width="'+w+'" height="22" rx="5" fill="#fff8ed" stroke="#d9ad7e"/><text x="'+cx+'" y="'+(base+21)+'" text-anchor="middle" class="wave-value event-value">'+waveEscape(action.label)+'</text></g>';
        }
        return;
      }
      const points=this.points(key,type,events,limit);
      if(type==='bit'||type==='clock'||type==='pulse'){
        const level=value=>base+(value?8:26);
        let path='M'+x(this.start)+' '+level(points[0].value);
        for(let i=1;i<points.length;i++)path+=' H'+x(points[i].time)+' V'+level(points[i].value);
        path+=' H'+x(limit);
        svg+='<path class="wave-digital" data-signal="'+key+'" d="'+path+'" fill="none" stroke="'+color+'" stroke-width="'+(key==='clk'?2:1.8)+'"/>';
      }else{
        for(let i=0;i<points.length;i++){
          const a=x(points[i].time),b=x(i+1<points.length?points[i+1].time:limit),value=points[i].value;
          if(b-a<1)continue;
          const slope=Math.min(4,(b-a)/3),fill=key==='state'?(WAVE_STATE_COLORS[value]||'#edf1e8'):'#edf4e8';
          const full=key==='state'?String(value).replace('S_',''):waveNumber(value);
          const text=full.length*6<(b-a-8)?full:(b-a>28?full.slice(0,Math.max(1,Math.floor((b-a-15)/6)))+'…':'');
          svg+='<g class="wave-bus" data-signal="'+key+'" data-value="'+waveEscape(value)+'"><title>'+waveEscape(WAVE_SIGNALS[key][0]+': '+waveNumber(value))+'</title><path d="M'+a+' '+(base+17)+' L'+(a+slope)+' '+(base+6)+' H'+(b-slope)+' L'+b+' '+(base+17)+' L'+(b-slope)+' '+(base+28)+' H'+(a+slope)+' Z" fill="'+fill+'" stroke="'+color+'" stroke-opacity=".7"/><text x="'+((a+b)/2)+'" y="'+(base+21)+'" text-anchor="middle" class="wave-value">'+waveEscape(text)+'</text></g>';
        }
      }
    });
    if(this.drawArrows&&rows.includes('read_event')&&rows.includes('multiply_event')&&rows.includes('accumulate_event'))svg+=this.dependencyArrows(events,focus,rows,x,y,limit);
    if(limit<this.start+this.span){svg+='<rect x="'+x(limit)+'" y="28" width="'+(width-x(limit))+'" height="'+(height-28)+'" fill="#edf0e9" opacity=".8"/><text x="'+(x(limit)+15)+'" y="'+(top+24)+'" class="wave-future">尚未推进 →</text>'}
    const active=focus.kind!=='initial'&&focus.time>=this.start&&focus.time<=limit;
    if(active)svg+='<line class="wave-cursor" x1="'+x(focus.time)+'" y1="27" x2="'+x(focus.time)+'" y2="'+(height-8)+'" stroke="#b97839" stroke-width="2" stroke-dasharray="5 3"/><circle cx="'+x(focus.time)+'" cy="31" r="4" fill="#b97839"/>';
    const visible=events.filter(e=>e.kind!=='initial'&&e.time>=this.start&&e.time<=limit);
    visible.forEach((event,index)=>{
      const previous=index?visible[index-1].time:event.time-0.5,next=index+1<visible.length?visible[index+1].time:event.time+0.5;
      const left=Math.max(this.start,(previous+event.time)/2),right=Math.min(limit,(next+event.time)/2);
      svg+='<rect class="wave-hit" x="'+x(left)+'" y="27" width="'+Math.max(1,(right-left)*this.zoom)+'" height="'+(height-28)+'" fill="transparent" tabindex="0" role="button" data-wave-id="'+event.waveId+'" aria-label="'+waveEscape(event.kind==='clock'?'查看第 '+event.edge+' 拍':'查看'+(event.kind==='reset'?'异步复位':'复位释放')+'事件')+'"><title>'+waveEscape(event.reason)+'</title></rect>';
    });
    const element=this.$('waveSvg');element.setAttribute('width',width);element.setAttribute('height',height);element.setAttribute('viewBox','0 0 '+width+' '+height);element.innerHTML=svg;
    this.$('waveHistory').min=this.minStart;this.$('waveHistory').max=this.maxStart;this.$('waveHistory').value=this.start;
    this.$('waveEarlier').disabled=this.start<=this.minStart;this.$('waveLater').disabled=this.start>=this.maxStart;
    this.$('waveFollow').classList.toggle('active',this.follow&&this.selectedId===null);
    this.$('waveRange').textContent='窗口 '+this.start+'～'+(this.start+this.span)+' · 记录到 ↑'+machine.edges+(this.minStart>0?' · 较早记录已滚动移除':'');
    this.renderInspector(focus,selected,machine);
    const scroll=this.$('waveScroll');
    if((this.follow&&this.latestDrawn!==last.waveId)||ownerChanged)scroll.scrollLeft=Math.max(0,x(last.time)-scroll.clientWidth+100);
    this.latestDrawn=last.waveId;this.$('waveLabels').scrollTop=scroll.scrollTop;
  }
  dependencyArrows(events,focus,rows,x,y,limit){
    const actions=focus.ops,preferred=actions.find(o=>o.kind==='accumulate')||actions.find(o=>o.kind==='multiply')||actions.find(o=>o.kind==='read');
    const k=preferred?preferred.k:0,r=focus.before;
    const find=kind=>events.find(e=>e.before.row_index===r.row_index&&e.before.group_index===r.group_index&&e.ops.some(o=>o.kind===kind&&o.k===k));
    const stages=[['read','read_event'],['multiply','multiply_event'],['accumulate','accumulate_event']].map(([kind,key])=>({event:find(kind),row:rows.indexOf(key)}));
    let markup='';
    for(let i=0;i<2;i++){
      const a=stages[i],b=stages[i+1];if(!a.event||!b.event||a.event.time<this.start||b.event.time>limit)continue;
      const xa=x(a.event.time)+6,xb=x(b.event.time)-6,ya=y(a.row)+27,yb=y(b.row)+6;
      markup+='<path class="wave-dependency" data-k="'+k+'" d="M'+xa+' '+ya+' C'+xa+' '+(ya+16)+','+xb+' '+(yb-16)+','+xb+' '+yb+'" fill="none" stroke="#bf6b38" stroke-width="2.3" marker-end="url(#waveArrowHead)"/>';
    }
    return markup;
  }
  renderInspector(event,selected,machine){
    const title=event.kind==='initial'?'还没有时钟记录':event.kind==='clock'?(selected?'回看 ↑':'最新 ↑')+event.edge+'：'+event.before.state+' → '+event.after.state:event.kind==='reset'?'两次上升沿之间：异步复位立即生效':'两次上升沿之间：释放复位';
    const acc=event.ops.find(o=>o.kind==='accumulate'),lane=this.lane;
    this.$('waveInspector').innerHTML='<div class="wave-inspector-title"><b>'+waveEscape(title)+'</b><span>模型当前在 ↑'+machine.edges+'；点击图中时钟列可回看，不会倒转模型。</span></div><p>'+waveEscape(event.reason)+'</p>'+(acc?'<div class="wave-proof"><span>沿前 product['+lane+']：<b>'+waveNumber(event.before.product[lane])+'</b></span><span>沿后 product['+lane+']：<b>'+waveNumber(event.after.product[lane])+'</b></span><span>本拍累加使用：<b>'+waveNumber(acc.products[lane])+'（旧值）</b></span></div>':'')+'<a href="#edgeTitle">对照这一拍的寄存器与源码 ↓</a>';
  }
}
