
(() => {
  'use strict';
  const N=99,K=64,M=256,LANES=16;
  const $=id=>document.getElementById(id);
  const fmt=(v,d=6)=>Math.abs(v)<0.5*Math.pow(10,-d)?(0).toFixed(d):v.toFixed(d);
  const clamp=(v,min,max)=>Math.max(min,Math.min(max,v));
  const sub=n=>String(n).replace(/\d/g,d=>'₀₁₂₃₄₅₆₇₈₉'[Number(d)]);
  const cache=new Map(),completed=new Set();
  const state={tab:0,row:0,col:0,layer:0,step:0,playing:false,speed:1};
  const titles=['先看全貌：一行输入，生成 256 个输出','只算一个数：64 次相乘、累加，再加偏置','相同的输入广播，16 个输出同时累加','12 套输入与参数，复用同一块计算硬件'];
  const subtitles=['每个热图小格对应一个真实元素；高亮显示当前读取和写回的位置。','完整数据维度不变。这里只展开所选输出对应的 64 项，避免铺满整个数据集。','一种可实现的并行方案：16 个乘法器 + 16 个累加寄存器，沿输出特征方向并行。','每层都计算 99×64 乘 64×256 加偏置；数据逐层更换，不需要复制 12 套硬件。'];
  let dataset,heatmaps,lastTick=0,canvasLayout=null;
  function seeded(seed){let a=seed>>>0;return ()=>{a=(Math.imul(1664525,a)+1013904223)>>>0;return a/4294967296;};}
  function makeData(layer){
    if(cache.has(layer))return cache.get(layer);
    const rand=seeded(20261017+layer*7919),X=new Float64Array(N*K),W=new Float64Array(K*M),b=new Float64Array(M),Y=new Float64Array(N*M);
    for(let i=0;i<X.length;i++)X[i]=(rand()+rand()+rand()+rand()+rand()+rand()-3)*1.4;
    for(let i=0;i<W.length;i++)W[i]=(rand()-.5)*.26;
    for(let j=0;j<M;j++)b[j]=(rand()-.5)*.08;
    // 每个输出都完整累加64项，再加一次偏置；没有缩小矩阵。
    for(let i=0;i<N;i++)for(let j=0;j<M;j++){let acc=0;for(let k=0;k<K;k++)acc+=X[i*K+k]*W[k*M+j];Y[i*M+j]=acc+b[j];}
    const result={X,W,b,Y};cache.set(layer,result);return result;
  }
  function heat(data,rows,cols){
    const c=document.createElement('canvas');c.width=cols;c.height=rows;const ctx=c.getContext('2d'),im=ctx.createImageData(cols,rows);
    let max=0;for(const v of data)max=Math.max(max,Math.abs(v));
    for(let n=0;n<data.length;n++){const t=Math.pow(Math.min(1,Math.abs(data[n])/max),.7),end=data[n]<0?[49,131,145]:[215,117,74];for(let z=0;z<3;z++)im.data[n*4+z]=Math.round([242,246,239][z]*(1-t)+end[z]*t);im.data[n*4+3]=255;}
    ctx.putImageData(im,0,0);return c;
  }
  function selectData(){dataset=makeData(state.layer);heatmaps={X:heat(dataset.X,N,K),W:heat(dataset.W,K,M),Y:heat(dataset.Y,N,M)};}
  function partial(j,n){let a=0;for(let k=0;k<n;k++)a+=dataset.X[state.row*K+k]*dataset.W[k*M+j];return a;}
  function phase(){return state.step===0?'准备读取':state.step<=64?'乘累加':state.step===65?'加偏置':'写回结果';}
  function updateSettings(){$('rowInput').value=state.row;$('colInput').value=state.col;$('layerInput').value=state.layer;}
  function describe(){
    const {row:i,col:j,step:s,layer:l}=state,k=Math.max(0,s-1),n=Math.min(s,64);
    let tag=phase(),text='';
    if(state.tab===3){
      tag=s===0?'准备装载':s<=8?'装载数据':s<=64?'硬件计算':s===65?'加偏置':'写回结果';
      text=s===0?`准备第 <b>${l}</b> 层的输入 X${sub(l)}、权重 W${sub(l)} 和偏置 b${sub(l)}。它们与其他层各自独立。`:s<=8?`E203 将第 <b>${l}</b> 层数据送入缓冲区：输入 <b>6,336</b> 个数、权重 <b>16,384</b> 个数、偏置 <b>256</b> 个数。`:s<=64?`复用相同的乘累加阵列，完成第 <b>${l}</b> 层的 <b>1,622,016 次乘累加</b>；这段是整层流程示意，不是单个输出的逐拍计时。`:s===65?`把对应的 <b>256 个偏置</b> 加到每一行的相应列上。各输出偏置只加一次。`:`第 <b>${l}</b> 层得到 <b>99×256</b> 输出并写回。下一层会重新装载它自己对应的 99×64 输入，不直接接用此矩阵。`;
    }else if(state.tab===2){
      const start=Math.floor(j/LANES)*LANES;
      text=s===0?`准备同时计算 <b>Y[${i},${start}…${start+15}]</b>。16 路共用同一行输入，每一路读取权重的不同列。`:s<=64?`第 <b>${s}/64</b> 个乘累加拍：把 <b>X[${i},${k}] = ${fmt(dataset.X[i*K+k])}</b> 同时送给 16 个乘法器；分别乘以该行的 16 个权重，并更新 16 个累加值。`:s===65?`64 项已经全部累加。现在分别加上 <b>b[${start}…${start+15}]</b>，得到 16 个输出。偏置处理的实际周期由硬件结构决定。`:`写回 <b>Y[${i},${start}…${start+15}]</b> 共 16 个数。每行需要 <b>16 组</b>，全部 99 行需要 <b>1,584 组</b>。`;
    }else{
      text=s===0?`选定输入第 <b>${i}</b> 行和权重第 <b>${j}</b> 列：各取 64 个数，目标是 <b>Y[${i},${j}]</b>。点击播放或单步开始。`:s<=64?`第 <b>${s}/64</b> 项：<b>X[${i},${k}] × W[${k},${j}]</b>，乘积 ${fmt(dataset.X[i*K+k]*dataset.W[k*M+j])}；加入累加寄存器后，当前点积部分和为 <b>${fmt(partial(j,n))}</b>。`:s===65?`64 项点积已经得到 <b>${fmt(partial(j,64))}</b>，再加一次偏置 <b>b[${j}] = ${fmt(dataset.b[j])}</b>，得到 <b>${fmt(dataset.Y[i*M+j])}</b>。`:`把 <b>${fmt(dataset.Y[i*M+j])}</b> 写入 <b>Y[${i},${j}]</b>。固定这一行，遍历权重 256 列；再对全部 99 行重复。`;
    }
    $('phasePill').textContent=tag;$('narration').innerHTML=text;
  }
  function renderDot(){
    const {row:i,col:j,step:s}=state,n=Math.min(s,64),active=clamp(s-1,0,63),start=Math.floor(active/8)*8;
    $('xHeading').textContent=`X[${i},k]`;$('wHeading').textContent=`W[k,${j}]`;$('termWindow').textContent=`k = ${start} … ${start+7} / 63`;
    let rows='';for(let k=start;k<start+8;k++){const x=dataset.X[i*K+k],w=dataset.W[k*M+j],cls=s>0&&k===active&&s<=64?'current':k<n?'done':'pending';rows+=`<tr class="${cls}"><td>${String(k).padStart(2,'0')}</td><td>${fmt(x)}</td><td>${fmt(w)}</td><td>${fmt(x*w)}</td></tr>`;}$('termBody').innerHTML=rows;
    $('dotFormula').textContent=`Y[${i},${j}] = Σ X[${i},k]·W[k,${j}] + b[${j}]`;
    $('accValue').textContent=fmt(partial(j,n)+(s>=65?dataset.b[j]:0));
    $('accSub').textContent=s===0?'尚未读取第 0 项':s<=64?`已累加 ${s} / 64 项，偏置尚未加入`:s===65?'已加偏置，等待写回':'结果已写回输出矩阵';
    $('dotTotal').textContent=s>=64?fmt(partial(j,64)):`${n} / 64 项`;
    $('biasLabel').textContent=`偏置 b[${j}]`;$('biasValue').textContent=fmt(dataset.b[j])+(s>=65?' ✓':'');
    $('resultLabel').textContent=`最终 Y[${i},${j}]`;$('finalValue').textContent=s>=65?fmt(dataset.Y[i*M+j]):'等待计算';
    for(let k=0;k<64;k++)$('dots64').children[k].className='dotcell'+(k<n?' done':'')+(s>0&&s<=64&&k===active?' current':'');
  }
  function renderParallel(){
    const {row:i,col:j,step:s}=state,start=Math.floor(j/16)*16,n=Math.min(s,64),k=clamp(s-1,0,63);
    $('broadcastValue').textContent=`X[${i},${k}] = ${fmt(dataset.X[i*K+k],4)}`;
    $('parallelStep').textContent=s===0?'准备开始':s<=64?`第 ${s} / 64 拍`:s===65?'分别加偏置':'16 个结果写回';
    let html='';for(let lane=0;lane<16;lane++){const c=start+lane,acc=partial(c,n)+(s>=65?dataset.b[c]:0);html+=`<div class="lane${s>=65?' active':''}${c===j?' selected':''}"><div class="lanetitle"><span>MAC ${String(lane).padStart(2,'0')}</span><b>j=${c}</b></div><div class="weight">${s>=65?'b = '+fmt(dataset.b[c],4):'w = '+fmt(dataset.W[k*M+c],4)}</div><div class="laneacc">${fmt(acc,4)}</div></div>`;}$('lanes').innerHTML=html;
    $('groupStatus').textContent=`当前第 ${Math.floor(j/16)+1} / 16 组，处理第 ${i} 行的第 ${start}～${start+15} 列。每拍完成 16 次乘累加。`;
  }
  function renderLayers(){
    const {layer:l,step:s}=state,t=sub(l);
    for(const btn of $('layerButtons').children){const index=Number(btn.dataset.layer);btn.setAttribute('aria-pressed',String(index===l));btn.classList.toggle('completed',completed.has(index));}
    $('loadTitle').textContent=`装载第 ${l} 层数据`;$('loadShapes').innerHTML=`X${t} : 99 × 64<br>W${t} : 64 × 256<br>b${t} : 256`;
    $('layerEquation').textContent=`Y${t} = X${t} × W${t} + b${t}`;$('writeTitle').textContent=`写回第 ${l} 层结果`;$('writeShape').textContent=`Y${t} : 99 × 256`;
    $('loadCard').classList.toggle('active',s<=8);$('engineCard').classList.toggle('active',s>8&&s<=65);$('writeCard').classList.toggle('active',s===66);
    $('engineBar').style.width=`${clamp((s-8)/56,0,1)*100}%`;
  }
  function paintMatrices(){
    if(state.tab!==0)return;
    const canvas=$('matrixCanvas'),rect=canvas.getBoundingClientRect();if(!rect.width)return;
    const mobile=rect.width<560,L=mobile?{width:540,height:740,X:{x:35,y:128,w:128,h:198},W:{x:245,y:128,w:256,h:128},Y:{x:190,y:432,w:256,h:198}}:{width:1040,height:440,X:{x:40,y:145,w:128,h:198},W:{x:270,y:145,w:384,h:128},Y:{x:738,y:145,w:256,h:198}};
    canvasLayout=L;canvas.style.aspectRatio=`${L.width}/${L.height}`;
    const dpr=Math.min(window.devicePixelRatio||1,2),pixelW=Math.round(rect.width*dpr),pixelH=Math.round(rect.width*L.height/L.width*dpr);
    if(canvas.width!==pixelW||canvas.height!==pixelH){canvas.width=pixelW;canvas.height=pixelH;}
    const ctx=canvas.getContext('2d');ctx.setTransform(canvas.width/L.width,0,0,canvas.height/L.height,0,0);ctx.clearRect(0,0,L.width,L.height);ctx.imageSmoothingEnabled=false;
    const text=(txt,x,y,size=13,color='#687e76',weight=400)=>{ctx.font=`${weight} ${size}px "Segoe UI","Microsoft YaHei",sans-serif`;ctx.fillStyle=color;ctx.fillText(txt,x,y);};
    text('完整尺寸，没有缩成小矩阵。',mobile?35:40,45,mobile?20:22,'#19343b',650);
    text(`当前目标  Y[${state.row}, ${state.col}]  ·  第 ${state.layer} 层`,mobile?35:40,74,mobile?14:15,'#7b8d83');
    const mat=(name,rows,cols,color)=>{const r=L[name];ctx.drawImage(heatmaps[name],r.x,r.y,r.w,r.h);ctx.strokeStyle='#c5d2c8';ctx.lineWidth=1;ctx.strokeRect(r.x-.5,r.y-.5,r.w+1,r.h+1);text(name,r.x,r.y-34,23,color,700);text(`${rows} × ${cols}`,r.x+35,r.y-35,16,'#63796f',600);};
    mat('X',N,K,'#287e8a');mat('W',K,M,'#7866a2');mat('Y',N,M,'#d76840');
    const a=L.X,w=L.W,y=L.Y,i=state.row,j=state.col,k=clamp(state.step-1,0,63);
    ctx.fillStyle='#df8c4860';ctx.fillRect(a.x,a.y+i*a.h/N,a.w,Math.max(2,a.h/N));ctx.strokeStyle='#bd643d';ctx.lineWidth=1.5;ctx.strokeRect(a.x-3,a.y+i*a.h/N-1,a.w+6,Math.max(3,a.h/N)+2);
    ctx.fillStyle='#b05f584d';ctx.fillRect(w.x+j*w.w/M,w.y,Math.max(2,w.w/M),w.h);ctx.strokeRect(w.x+j*w.w/M-1,w.y-3,Math.max(3,w.w/M)+2,w.h+6);
    if(state.step>0){ctx.fillStyle='#19343b';ctx.fillRect(a.x+k*a.w/K,a.y+i*a.h/N,Math.max(2,a.w/K),Math.max(2,a.h/N));ctx.fillRect(w.x+j*w.w/M,w.y+k*w.h/K,Math.max(2,w.w/M),Math.max(2,w.h/K));}
    const cellx=y.x+(j+.5)*y.w/M,celly=y.y+(i+.5)*y.h/N;ctx.strokeStyle='#d76840';ctx.lineWidth=1;ctx.setLineDash([3,4]);ctx.beginPath();ctx.moveTo(y.x,celly);ctx.lineTo(y.x+y.w,celly);ctx.moveTo(cellx,y.y);ctx.lineTo(cellx,y.y+y.h);ctx.stroke();ctx.setLineDash([]);
    ctx.fillStyle=state.step>=66?'#d76840':'#fff';ctx.fillRect(cellx-3,celly-3,6,6);ctx.strokeStyle='#b95734';ctx.lineWidth=2;ctx.strokeRect(cellx-4,celly-4,8,8);
    if(mobile){text('×',194,209,30,'#b5c2b7');text('64 项点积，再加对应偏置',107,370,18,'#19343b',600);text('↓',293,403,24,'#9bad9e');text(`输入第 ${i} 行 · 64 个数`,35,352,13);text(`权重第 ${j} 列 · 64 个数`,245,289,13);text(`输出第 ${i} 行、第 ${j} 列`,190,661,14);text(state.step>=65?`Y = ${fmt(dataset.Y[i*M+j])}`:`b[${j}] = ${fmt(dataset.b[j])}`,190,690,16,'#d76840',600);}
    else{text('×',205,238,35,'#b5c2b7');text('→',687,238,31,'#b5c2b7');text(`输入第 ${i} 行`,40,376,14);text('64 个特征',40,399,12);text(`权重第 ${j} 列 · 64 个数`,270,308,14);text('每一列生成一个输出特征',270,331,12);text(`输出 Y[${i},${j}]`,738,376,14);text(state.step>=65?`= ${fmt(dataset.Y[i*M+j])}`:`+ b[${j}] = ${fmt(dataset.b[j])}`,738,402,15,'#d76840',600);}
  }
  function render(){
    $('progress').value=state.step;$('progressText').textContent=state.tab===3?`${String(state.step).padStart(2,'0')} / 66`:state.step<=64?`${String(state.step).padStart(2,'0')} / 64`:state.step===65?'加偏置':'已写回';
    $('progress').setAttribute('aria-valuetext',state.tab===3?`第${state.layer}层，流程帧${state.step}`:`${phase()}，已完成${Math.min(state.step,64)}项点积`);
    $('playBtn').textContent=state.playing?'Ⅱ 暂停动画':'▶ 播放演示';$('playBtn').setAttribute('aria-label',state.playing?'暂停动画':'播放动画');
    if(state.tab===0)paintMatrices();else if(state.tab===1)renderDot();else if(state.tab===2)renderParallel();else renderLayers();describe();
  }
  function pause(){state.playing=false;lastTick=0;}
  function reset(){pause();state.step=0;render();}
  function selectLayer(l){state.layer=clamp(l,0,11);state.step=0;selectData();updateSettings();}
  function switchTab(t){pause();state.tab=t;state.step=0;document.querySelectorAll('.chapter').forEach((el,index)=>{el.setAttribute('aria-selected',String(index===t));el.tabIndex=index===t?0:-1;});for(let i=0;i<4;i++)$('panel-'+i).hidden=i!==t;$('chapterTitle').textContent=titles[t];$('chapterSubtitle').textContent=subtitles[t];$('progress').setAttribute('aria-label',t===3?'十二层流程动画进度，0至66帧':'点积动画进度，0至64为乘累加，65加偏置，66写回');render();}
  function advance(){
    if(state.step<66){state.step++;if(state.tab===3&&state.step===66)completed.add(state.layer);}
    else if(state.tab===3){if(state.layer===11){pause();render();return;}selectLayer(state.layer+1);}
    else{const increment=state.tab===2?16:1;state.col=state.tab===2?(Math.floor(state.col/16)+1)*16:state.col+increment;if(state.col>=M){state.col=0;state.row=(state.row+1)%N;}state.step=0;updateSettings();}
    render();
  }
  function loop(now){
    if(state.playing&&!document.hidden){if(!lastTick)lastTick=now;const interval=(state.step===66?1050:125)/state.speed;if(now-lastTick>=interval){lastTick=now;advance();}}
    requestAnimationFrame(loop);
  }
  for(let l=0;l<12;l++){const option=document.createElement('option');option.value=l;option.textContent=`第 ${l} 层`;$('layerInput').append(option);const btn=document.createElement('button');btn.type='button';btn.className='layerbtn';btn.dataset.layer=l;btn.setAttribute('aria-pressed',String(l===0));btn.setAttribute('aria-label',`选择第${l}层`);btn.innerHTML=`<small>LAYER</small>${String(l).padStart(2,'0')}`;btn.addEventListener('click',()=>{pause();selectLayer(l);render();});$('layerButtons').append(btn);}
  for(let k=0;k<64;k++){const el=document.createElement('span');el.className='dotcell';el.title=`第 ${k} 项`;$('dots64').append(el);}
  document.querySelectorAll('.chapter').forEach(el=>{el.addEventListener('click',()=>switchTab(Number(el.dataset.tab)));el.addEventListener('keydown',e=>{if(e.key==='ArrowRight'||e.key==='ArrowLeft'){e.preventDefault();e.stopPropagation();const next=(state.tab+(e.key==='ArrowRight'?1:3))%4;switchTab(next);$('tab-'+next).focus();}});});
  $('rowInput').addEventListener('change',()=>{pause();state.row=clamp(Math.round(Number($('rowInput').value)||0),0,98);state.step=0;updateSettings();render();});
  $('colInput').addEventListener('change',()=>{pause();state.col=clamp(Math.round(Number($('colInput').value)||0),0,255);state.step=0;updateSettings();render();});
  $('layerInput').addEventListener('change',()=>{pause();selectLayer(Number($('layerInput').value));render();});
  $('playBtn').addEventListener('click',()=>{state.playing=!state.playing;lastTick=0;render();});
  $('stepBtn').addEventListener('click',()=>{pause();advance();});$('resetBtn').addEventListener('click',reset);
  $('progress').addEventListener('input',()=>{pause();state.step=Number($('progress').value);if(state.tab===3&&state.step===66)completed.add(state.layer);render();});
  $('speed').addEventListener('change',()=>{state.speed=Number($('speed').value);lastTick=0;});
  $('matrixCanvas').addEventListener('click',e=>{if(!canvasLayout)return;const rect=e.currentTarget.getBoundingClientRect(),x=(e.clientX-rect.left)*canvasLayout.width/rect.width,y=(e.clientY-rect.top)*canvasLayout.height/rect.height,r=canvasLayout.Y;if(x>=r.x&&x<=r.x+r.w&&y>=r.y&&y<=r.y+r.h){pause();state.row=clamp(Math.floor((y-r.y)/r.h*N),0,98);state.col=clamp(Math.floor((x-r.x)/r.w*M),0,255);state.step=0;updateSettings();render();}});
  document.addEventListener('keydown',e=>{if(e.target.closest('input,select,button,a,summary'))return;if(e.code==='Space'){e.preventDefault();$('playBtn').click();}else if(e.key==='ArrowRight'){e.preventDefault();$('stepBtn').click();}});
  document.addEventListener('visibilitychange',()=>{lastTick=0;});window.addEventListener('resize',paintMatrices);
  // 只读快照，用于核对完整尺寸及动画中的数值。
  window.linearLab=Object.freeze({snapshot:()=>({...state,shapeX:[N,K],shapeW:[K,M],shapeY:[N,M],bias:dataset.b[state.col],dot:partial(state.col,64),output:dataset.Y[state.row*M+state.col],partial:partial(state.col,Math.min(state.step,64)),elements:{X:dataset.X.length,W:dataset.W.length,b:dataset.b.length,Y:dataset.Y.length}}),value:(name,index)=>dataset[name]?.[index],canvasLayout:()=>canvasLayout});
  selectData();render();requestAnimationFrame(loop);
  if(!window.matchMedia('(prefers-reduced-motion: reduce)').matches){state.playing=true;render();}
})();
