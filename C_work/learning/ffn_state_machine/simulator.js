'use strict';

// A clock-edge teaching model of ffn_accel.sv. Every RHS reads the OLD snapshot.
const CONFIGS = {
  small: {name:'入门模型',rows:2,groups:2,lanes:4,inner:4},
  actual: {name:'工程参数',rows:99,groups:16,lanes:16,inner:64}
};
function signedWrap(value,width){const size=2**width;let bits=((value%size)+size)%size;return bits>=size/2?bits-size:bits}
function quantize(acc){
  const magnitude=Math.floor((Math.abs(acc)+128)/256);
  const rounded=acc<0&&magnitude!==0?-magnitude:magnitude;
  const saturated=rounded>32767||rounded< -32768;
  const data=Math.max(-32768,Math.min(32767,rounded));
  return {rounded,data,flag:Number(saturated),bits:data&65535};
}
function inputValue(row,k){return [256,512,-256,128][k%4]*(1+row%3)}
function biasValue(group,lane){return [256+(group%4)*32,0,0,-128][lane%4]}
function weightValue(group,k,lane){
  if(lane%4===1)return 32767;
  if(lane%4===2)return -32768;
  if(lane%4===3)return [-64,128,64,-256][k%4];
  return [64,128,192,256][k%4]+group%4;
}
function emptyRegisters(n){return {
  state:'S_IDLE',done:0,cycle_count:0,saturation_count:0,
  row_index:0,group_index:0,write_lane:0,
  bias_issue:0,bias_valid:0,bias_lane_d:0,
  mac_issue:0,mac_read_valid:0,mac_read_last:0,product_valid:0,product_last:0,
  accumulator:Array(n).fill(0),product:Array(n).fill(0),output_buffer:Array(n).fill(0),productTag:null
}}
class FfnMachine {
  constructor(config){
    this.config={...config};this.reg=emptyRegisters(config.lanes);
    this.sramB=null;this.sramRead=null;this.outputs=new Map();this.outputEpoch=new Map();this.epoch=0;this.taskWrites=0;this.edges=0;this.rstLow=false;
    this.trace=[];this.last={kind:'initial',before:this.reg,after:this.reg,ops:[],reason:'寄存器初值为 0，状态为 S_IDLE。点击“发出启动”开始。',lines:[214,215,216,217,218,219,220,221,222,223]};
    this.waveTrace=[];this.waveSerial=0;this.asyncFraction=0;
    this.recordWave(this.last);
  }
  get busy(){return Number(this.reg.state!=='S_IDLE')}
  get groupCycles(){return (this.config.lanes+1)+(this.config.inner+2)+1+this.config.lanes}
  get totalCycles(){return this.groupCycles*this.config.rows*this.config.groups}
  get totalOutputs(){return this.config.rows*this.config.groups*this.config.lanes}
  address(row,group,lane){return (row*this.config.groups+group)*this.config.lanes+lane}
  setReset(low){
    const before=this.reg,rstBefore=Number(!this.rstLow);this.rstLow=low;
    if(low){this.reg=emptyRegisters(this.config.lanes);this.taskWrites=0;this.epoch++}
    this.last={kind:low?'reset':'release',before,after:this.reg,ops:[],lines:low?[214,215,216,217,218,219,220,221,222,223]:[214,224],
      reason:low?'rst_n 从 1 变为 0：异步复位立即清零寄存器，不需要等待时钟。Y 存储器内容保留。':'rst_n 恢复为 1：这里只释放复位，寄存器等待下一个时钟上升沿才正常更新。'};
    this.recordWave(this.last,{rstBefore,rstAfter:Number(!low)});
  }
  clock({start=false,clear=false}={}){
    const o=this.reg,c=this.config;
    this.edges++;
    this.wavePending={inputs:{start:Number(start),clear:Number(clear)},sramBefore:{b:this.sramB,read:this.sramRead}};
    const ops=[],lines=[214],previousB=this.sramB,previousRead=this.sramRead;
    // Synchronous SRAM samples the pre-edge request, independently of core reset.
    if(o.state==='S_BIAS'&&o.bias_issue<c.lanes){
      this.sramB={lane:o.bias_issue,value:biasValue(o.group_index,o.bias_issue)};
      ops.push({kind:'biasRead',lane:o.bias_issue,value:this.sramB.value});
    }
    if(o.state==='S_MAC'&&o.mac_issue<c.inner){
      const k=o.mac_issue;
      this.sramRead={k,x:inputValue(o.row_index,k),weights:Array.from({length:c.lanes},(_,lane)=>weightValue(o.group_index,k,lane))};
      ops.push({kind:'read',...this.sramRead});
    }
    if(o.state==='S_WRITE'){
      const address=this.address(o.row_index,o.group_index,o.write_lane),data=o.output_buffer[o.write_lane];
      this.outputs.set(address,data);
      this.outputEpoch.set(address,this.epoch);this.taskWrites++;
      ops.push({kind:'write',lane:o.write_lane,address,data,row:o.row_index,col:o.group_index*c.lanes+o.write_lane});
    }
    if(this.rstLow){
      this.reg=emptyRegisters(c.lanes);
      return this.record(o,this.reg,ops,'复位保持为低，寄存器继续保持复位值。', [214,215,216,222]);
    }
    const n={...o,product:[...o.product],accumulator:[...o.accumulator],output_buffer:[...o.output_buffer]};
    if(clear){n.done=0;lines.push(225);ops.push({kind:'clear'})}
    if(o.state!=='S_IDLE'){n.cycle_count=o.cycle_count+1;lines.push(226)}
    let reason='S_IDLE 等待启动。未被赋值的寄存器保持原值。';
    switch(o.state){
      case 'S_IDLE':
        lines.push(228);
        if(start){
          this.taskWrites=0;this.epoch++;
          Object.assign(n,{done:0,cycle_count:0,saturation_count:0,row_index:0,group_index:0,write_lane:0,bias_issue:0,bias_valid:0,mac_issue:0,mac_read_valid:0,product_valid:0,state:'S_BIAS'});
          lines.push(229,230,231,232,233);ops.push({kind:'start'});
          reason='本拍在 S_IDLE 接收 start_event：清零本轮统计与索引，state 更新为 S_BIAS。下一拍才执行 S_BIAS 分支。';
        }else if(clear)reason='S_IDLE 中清除 done，计算结果和其他统计保持不变。';
        break;
      case 'S_BIAS':
        lines.push(235,237);n.bias_valid=Number(o.bias_issue<c.lanes);
        if(o.bias_issue<c.lanes){n.bias_lane_d=o.bias_issue;n.bias_issue=o.bias_issue+1;lines.push(238,239)}
        if(o.bias_valid){
          if(!previousB)throw Error('Missing synchronous bias data');
          n.accumulator[o.bias_lane_d]=signedWrap(previousB.value*256,40);
          ops.push({kind:'biasLoad',lane:o.bias_lane_d,bias:previousB.value,result:n.accumulator[o.bias_lane_d]});lines.push(241,242,243);
          if(o.bias_lane_d===c.lanes-1){
            Object.assign(n,{mac_issue:0,mac_read_valid:0,mac_read_last:0,product_valid:0,product_last:0,state:'S_MAC'});
            lines.push(244,245,246);
          }
        }
        reason=n.state==='S_MAC'?'最后一个偏置已装入累加器，转入 S_MAC。即使本拍没有新的偏置读取，仍要接收前一拍返回的数据。':o.bias_valid?'本拍发起下一次偏置读取，同时用旧 bias_valid、旧 bias_lane_d 和上拍读回的偏置，更新对应累加器。':'第一次偏置读取只发请求，旧 bias_valid=0，所以这一拍还不装载累加器。';
        break;
      case 'S_MAC':
        lines.push(250,252,253,255);
        n.mac_read_valid=Number(o.mac_issue<c.inner);n.mac_read_last=Number(o.mac_issue===c.inner-1);
        if(o.mac_issue<c.inner){n.mac_issue=o.mac_issue+1;lines.push(254)}
        n.product_valid=o.mac_read_valid;n.product_last=o.mac_read_last;
        if(o.mac_read_valid){
          if(!previousRead)throw Error('Missing synchronous multiply inputs');
          n.product=previousRead.weights.map(w=>signedWrap(previousRead.x*w,32));n.productTag=previousRead.k;
          ops.push({kind:'multiply',k:previousRead.k,x:previousRead.x,weights:previousRead.weights,products:[...n.product]});lines.push(256,257,258);
        }
        if(o.product_valid){
          n.accumulator=o.accumulator.map((acc,lane)=>signedWrap(acc+o.product[lane],40));
          ops.push({kind:'accumulate',k:o.productTag,products:[...o.product],before:[...o.accumulator],after:[...n.accumulator]});lines.push(259,260,261,262);
        }
        if(o.product_valid&&o.product_last){n.state='S_ROUND';lines.push(263)}
        reason=n.state==='S_ROUND'?'最后一项乘积本拍真正加入累加器，product_valid 和 product_last 同时为 1，转入 S_ROUND。':o.mac_issue>=c.inner?'所有读取请求已经发完，仍留在 S_MAC 等待流水线剩余数据完成乘法和累加。':'读 SRAM、保存乘积、更新累加器可在同一拍进行，但处理的是不同的 k。所有右侧表达式都使用时钟沿前的旧值。';
        break;
      case 'S_ROUND':{
        const quantized=o.accumulator.map(quantize),increment=quantized.reduce((v,q)=>v+q.flag,0);
        n.output_buffer=quantized.map(q=>q.data);n.saturation_count=o.saturation_count+increment;n.write_lane=0;n.state='S_WRITE';
        ops.push({kind:'round',quantized,increment});lines.push(265,266,267,268,269);
        reason='所有通道的量化结果在本拍同时保存到 output_buffer；本组饱和数只在这里加入总计，然后转入 S_WRITE。';break;
      }
      case 'S_WRITE':
        lines.push(271,272);
        if(o.write_lane===c.lanes-1){
          if(o.group_index===c.groups-1&&o.row_index===c.rows-1){n.done=1;n.state='S_IDLE';lines.push(273,274);reason='最后一行、最后一组、最后一个通道已经写入 Y。本拍 done 置 1，状态回到 S_IDLE，busy 随即变为 0。'}
          else{
            if(o.group_index===c.groups-1){n.group_index=0;n.row_index=o.row_index+1;lines.push(276);reason='当前行的最后一组写完：group_index 清零，row_index 加 1，下一行从偏置读取重新开始。'}
            else{n.group_index=o.group_index+1;lines.push(277);reason='当前组写完：group_index 加 1，row_index 不变，重新进入 S_BIAS 处理下一组。'}
            n.bias_issue=0;n.bias_valid=0;n.state='S_BIAS';lines.push(278);
          }
        }else{n.write_lane=o.write_lane+1;lines.push(280);reason='本拍把旧 write_lane 对应的缓冲结果写入 Y，然后 write_lane 加 1，下一拍再写下一条通道。'}
        break;
      default:n.state='S_IDLE';lines.push(282);reason='遇到未知状态，default 分支使状态回到 S_IDLE。';
    }
    this.reg=n;
    return this.record(o,n,ops,reason,lines);
  }
  record(before,after,ops,reason,lines){
    const event={kind:'clock',edge:this.edges,before,after,ops,reason,lines};this.last=event;
    this.recordWave(event,this.wavePending);
    this.trace.push(event);if(this.trace.length>12)this.trace.shift();return event;
  }
  recordWave(event,meta={}){
    const clock=event.kind==='clock';
    if(clock)this.asyncFraction=0;
    else if(event.kind!=='initial')this.asyncFraction=this.asyncFraction===0?0.65:1-(1-this.asyncFraction)/2;
    Object.assign(event,{waveId:this.waveSerial++,time:clock?this.edges:this.edges+this.asyncFraction,
      edge:clock?this.edges:null,inputs:meta.inputs||{start:0,clear:0},
      rstBefore:meta.rstBefore??Number(!this.rstLow),rstAfter:meta.rstAfter??Number(!this.rstLow),
      sramBefore:meta.sramBefore||{b:this.sramB,read:this.sramRead},sramAfter:{b:this.sramB,read:this.sramRead}});
    this.waveTrace.push(event);if(this.waveTrace.length>512)this.waveTrace.shift();
  }
}
if(typeof module!=='undefined')module.exports={FfnMachine,CONFIGS,quantize,inputValue,biasValue,weightValue,signedWrap};
