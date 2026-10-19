(() => {
  'use strict';
  const DATA = JSON.parse(document.getElementById('trace-data').textContent);
  const scenes = DATA.scenes, $ = id => document.getElementById(id);
  const GROUPS = [...new Set(scenes.map(s => s.group))];
  const ORDER = [...scenes].sort((a,b) => GROUPS.indexOf(a.group)-GROUPS.indexOf(b.group) || a.id-b.id);
  const RANK = new Map(ORDER.map((s,i) => [s.id,i]));
  const HOST = ['H_IDLE', 'H_READ', 'H_RESPONSE'];
  const CORE = ['S_IDLE', 'S_BIAS', 'S_MAC', 'S_ROUND', 'S_WRITE'];
  const BITS = new Set(['rst_n', 'cmd_valid', 'cmd_ready', 'cmd_read', 'rsp_valid', 'rsp_ready', 'rsp_err', 'busy', 'done', 'irq', 'dec_error', 'start_event', 'clear_done', 'x_en', 'x_we', 'b_en', 'b_we', 'y_en', 'y_we']);
  const INPUTS = new Set(['clk', 'rst_n', 'cmd_valid', 'cmd_read', 'cmd_addr', 'cmd_wdata', 'cmd_wmask', 'rsp_ready']);
  const OUTPUTS = new Set(['cmd_ready', 'rsp_valid', 'rsp_err', 'rsp_rdata', 'irq']);
  const HEX = new Set(['cmd_addr', 'cmd_wdata', 'cmd_wmask', 'rsp_rdata', 'x_rdata', 'w_en', 'w_we', 'w_rdata0', 'w_rdata15', 'b_rdata', 'y_rdata', 'y_wdata']);
  const BASE = ['cmd_valid', 'cmd_ready', 'cmd_read', 'cmd_addr', 'cmd_wdata', 'cmd_wmask', 'rsp_valid', 'rsp_ready', 'rsp_err', 'rsp_rdata', 'host_state'];
  const LABEL = {state: 'core_state', cycles: 'cycle_count', irq: 'o_irq', busy: 'BUSY', done: 'DONE', layer_tag: 'LAYER_TAG', saturations: 'SATURATIONS', w_addr0: 'w_addr[0]', w_addr15: 'w_addr[15]', w_rdata0: 'w_rdata[0]', w_rdata15: 'w_rdata[15]'};
  const HELP = {clk: '时钟，上升沿采样命令与响应', rst_n: '异步低有效复位', cmd_valid: '主机：命令有效', cmd_ready: '外设：当前可接受一条命令', cmd_read: '1为读，0为写；只在命令握手时有意义', cmd_addr: '局部字节地址，必须4字节对齐', cmd_wdata: '32位写数据，SRAM只保存低16位', cmd_wmask: '写事务必须为0xF，读事务忽略', rsp_valid: '外设：响应有效', rsp_ready: '主机：可以接收响应', rsp_err: '只在响应有效时表示成功0或失败1', rsp_rdata: '32位响应数据；SRAM读做符号扩展', host_state: '独立的总线响应状态机', state: '计算状态机，与总线状态机并行工作', busy: '计算核心是否处于活动状态', done: '任务完成保持标志', irq: '电平中断，始终等于DONE', cycles: '不包含START接受拍的核心活动周期数', dec_error: '组合译码结果；只有命令握手时才形成响应', start_event: '本拍接受到合法START命令', clear_done: '本拍接受到合法清DONE命令'};
  const palette = key => INPUTS.has(key) ? '#7ecab6' : OUTPUTS.has(key) ? '#e8b17c' : '#b8a7e3';
  const hex = (v, width = 8) => v == null ? 'X' : '0x' + (v >>> 0).toString(16).toUpperCase().padStart(width, '0');
  const esc = v => String(v).replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  const fmt = (key, v) => {
    if (v == null) return 'X';
    if (key === 'host_state') return HOST[v] || '?';
    if (key === 'state') return CORE[v] || '?';
    if (HEX.has(key)) return hex(v, key === 'cmd_wmask' ? 1 : key === 'cmd_addr' ? 5 : key === 'cmd_wdata' || key === 'rsp_rdata' ? 8 : 4);
    return String(v);
  };
  const signed32 = v => v >> 0;
  const state = {scene: 0, index: 0, playing: false, mode: 'context', speed: 800, query: '', group: 'all'};
  let timer = null, waveLayout = null;
  const current = () => scenes[state.scene];
  const frame = () => current().frames[state.index];
  const command = f => f.pre.rst_n === 1 && f.pre.cmd_valid === 1 && f.pre.cmd_ready === 1;
  const response = f => f.pre.rst_n === 1 && f.pre.rsp_valid === 1 && f.pre.rsp_ready === 1;
  function signals() {
    if (state.mode === 'all') return ['clk', ...Object.keys(frame().pre)];
    if (state.mode === 'bus') return ['clk', ...BASE];
    let keys = ['clk', ...BASE, ...current().focus];
    if (current().kind === 'reset') keys.unshift('rst_n');
    return [...new Set(keys)];
  }
  function visibleScenes() {
    const q = state.query.toLowerCase().replace(/\s/g, '');
    return ORDER.filter(s => (state.group === 'all' || s.group === state.group) && (!q ||
      (s.title + s.description + s.group + (s.address == null ? '' : hex(s.address, 5))).toLowerCase().replace(/\s/g, '').includes(q)));
  }
  function buildCatalog() {
    const list = visibleScenes();
    let last = '', markup = '';
    for (const s of list) {
      if (s.group !== last) {
        last = s.group;
        markup += `<div class="catgroup"><span>${esc(last)}</span><span>${list.filter(x => x.group === last).length}</span></div>`;
      }
      const addr = s.address == null ? (s.kind === 'reset' ? 'RESET / ASYNC' : 'OBSERVE / SEQUENCE') : hex(s.address, 5);
      markup += `<button type="button" class="case ${s.id === state.scene ? 'active' : ''} ${s.error ? 'errorcase' : ''}" data-scene="${s.id}" aria-current="${s.id === state.scene ? 'true' : 'false'}"><span class="num">${String(RANK.get(s.id)+1).padStart(2, '0')}</span><span>${esc(s.title)}<small>${addr}${s.error ? ' · ERR' : ''}</small></span></button>`;
    }
    $('catalogList').innerHTML = markup || '<p class="empty">没有匹配场景。试试“STATUS”“反压”或“复位”。</p>';
    $('visibleCount').textContent = `${list.length} / ${scenes.length} 个场景`;
  }
  function describe(f) {
    const p = f.pre, q = f.post, s = current();
    if (!p.rst_n) return ['异步复位已经生效', 'RESET ASSERTED', '主机在前一个下降沿拉低 <code>rst_n</code>。异步复位在本上升沿之前已清状态，因此沿前就能看到 <b>BUSY=0、DONE=0、rsp_valid=0、cmd_ready=0</b>。SRAM内容保留，未完成的响应被取消。'];
    if (!p.done && q.done) return ['最后写回与完成同时发生', 'TASK COMPLETED', `本沿把最后一个输出写入 <code>Y[98,255]</code>，内部地址为 <code>${p.y_addr}</code>。沿后 <b>CYCLES=${q.cycles}、BUSY=0、DONE=1、IRQ=1</b>。这是任务完成事件，不是一笔CPU总线事务。`];
    if (command(f)) {
      if (q.rsp_err) return ['接收命令，返回错误', 'COMMAND → ERROR', `沿前 <code>cmd_valid=1 && cmd_ready=1</code>，命令被接受；译码检查失败，沿后给出 <b>rsp_valid=1、rsp_err=1、rdata=0</b>。${esc(s.description)} ${p.busy ? '核心继续运行，错误事务不会重启或取消计算。' : '本次非法访问不会执行写入或启动动作。'}`];
      if (p.start_event) return ['接受START，核心立即启动', 'START ACCEPTED', '命令握手沿接受CONTROL的启动位。沿后 <b>S_IDLE → S_BIAS，BUSY=1、CYCLES=0、DONE=0、IRQ=0</b>，同时产生写响应。写响应确认这条启动命令已执行；整个矩阵运算尚未完成。'];
      if (p.clear_done) return ['接受清除DONE命令', 'CLEAR DONE / IRQ', `在本沿执行 <code>CONTROL.bit1=1</code>，清除DONE及IRQ，沿后产生成功响应。SRAM与周期计数不因清除动作而清空。${p.busy ? '本次处于计算中，清除动作不会停止计算。' : '完成中断是保持电平，软件应答使它撤销。'}`];
      if (p.cmd_read && p.cmd_addr >= 0x10000) return ['接受同步SRAM读命令', 'COMMAND → H_READ', `读地址 <code>${hex(p.cmd_addr, 5)}</code> 被接受，SRAM在本沿进行同步读取。沿后总线状态进入 <b>H_READ</b>，<code>rsp_valid</code>仍为0；下一沿才把读出的16位数符号扩展并寄存为响应。`];
      if (p.cmd_read) {
        let extra = p.cmd_addr === 4 ? ` 本次STATUS=${q.rsp_rdata}，BUSY=${q.rsp_rdata & 1}、DONE=${(q.rsp_rdata >>> 1) & 1}；读取不会清中断。` : '';
        return ['接受寄存器读命令', 'COMMAND → RESPONSE', `本沿读取地址 <code>${hex(p.cmd_addr, 5)}</code>，直接寄存沿前的寄存器值。沿后 <b>rsp_valid=1、rsp_rdata=${hex(q.rsp_rdata)}、rsp_err=0</b>。由于沿前VALID为0，响应还要等后续握手。${extra}`];
      }
      if (p.cmd_addr >= 0x10000) {
        const val = p.cmd_wdata & 0xffff, signed = val > 32767 ? val - 65536 : val;
        return ['命令握手，SRAM写入', 'COMMAND → WRITE', `本沿将 <code>wdata[15:0]=${hex(val, 4)}</code> 写入地址 <code>${hex(p.cmd_addr, 5)}</code>。整数编码为${signed}，Q8.8实数为<b>${signed/256}</b>。沿后产生成功写响应；即使主机延迟接收响应，也不会重复写入。`];
      }
      if (p.cmd_addr === 0x20) return ['写入层号标签', 'LAYER TAG UPDATED', `本沿把 <code>LAYER_TAG</code> 从${p.layer_tag}改为${q.layer_tag}，沿后产生成功响应。该标签供软件标记任务，硬件不会据此切换参数或自动启动。`];
      return ['接受无操作控制写入', 'CONTROL = 0', 'CONTROL写0合法，返回成功响应。没有START和清DONE动作，计算状态与存储内容保持各自原有行为。'];
    }
    if (p.host_state === 1) return ['SRAM数据进入响应寄存器', 'H_READ → H_RESPONSE', `同步读数据已经在上一沿后更新。本沿将其符号扩展并寄存，沿后 <b>rsp_valid=1、rsp_rdata=${hex(q.rsp_rdata)}</b>。沿前rsp_valid仍为0，所以这一沿不消费响应。`];
    if (response(f)) return ['主机接收响应，事务结束', 'RESPONSE ACCEPTED', `沿前 <code>rsp_valid=1 && rsp_ready=1</code>，主机接收${p.rsp_err ? '<b>错误响应</b>' : '成功响应'}${p.cmd_read ? `，数据为<code>${hex(p.rsp_rdata)}</code>` : ''}。沿后回到 <b>H_IDLE</b>，rsp_valid清零、cmd_ready置1。此沿前cmd_ready仍为0，下一条命令最快在下一上升沿被接受。`];
    if (p.rsp_valid && !p.rsp_ready) return ['主机未就绪，保持响应', 'RESPONSE BACKPRESSURE', `<code>rsp_valid=1</code>而<code>rsp_ready=0</code>，本沿不消费响应。<b>VALID、DATA和ERR都保持，cmd_ready=0</b>。${p.cmd_valid ? '下一条命令虽然已拉高VALID，仍须保持地址和数据，等待READY。' : ''}${p.busy ? '核心状态机独立继续运行，CYCLES持续增加。' : ''}`];
    if (p.cmd_valid && !p.cmd_ready) return ['命令等待接收', 'COMMAND WAIT', '主机已经提出命令，但外设cmd_ready=0。此沿没有命令握手，主机应继续保持VALID、地址、读写方向和写数据，直到被接受。'];
    if (p.y_we && p.state === 4) return ['计算核心写回输出', 'CORE SRAM WRITE', `核心把一个16位结果写入内部Y地址 <code>${p.y_addr}</code>，CPU总线没有发起事务。<b>CYCLES：${p.cycles} → ${q.cycles}</b>；最后一个元素写入后才置DONE。`];
    if (p.busy) return ['核心计算继续', 'CORE RUNNING', `总线当前没有新的命令或响应握手，计算状态机继续工作：<code>${CORE[p.state]} → ${CORE[q.state]}</code>，<b>CYCLES：${p.cycles} → ${q.cycles}</b>。BUSY不等于总线READY为0；运行中仍可发起寄存器读事务。`];
    if (state.index && current().frames[state.index-1].pre.rst_n === 0 && p.rst_n) return ['复位释放，等待新命令', 'RESET RELEASED', 'rst_n恢复为1，接口回到H_IDLE，cmd_ready=1，可以接受新事务。之前被复位取消的响应不会重新出现。'];
    return ['等待下一次握手', 'IDLE / NO TRANSFER', `本沿没有命令或响应传输。${p.done ? '<b>DONE与IRQ仍为1</b>，完成标志保持直到写CONTROL=2或接受下一次START。' : '即使地址和数据有电平，只要cmd_valid为0，就不会执行访问。'} 信号显示的是实际寄存器或线网值；rsp_err与rsp_rdata只有在rsp_valid有效时才构成响应。`];
  }
  function events() {
    const result = [];
    current().frames.forEach((f, i) => {
      const p = f.pre, q = f.post;
      if (command(f)) result.push({i, label: q.rsp_err ? '接受命令 / 报错' : p.start_event ? '接受START' : p.clear_done ? '清DONE / IRQ' : '命令握手'});
      if (!p.rsp_valid && q.rsp_valid) result.push({i, label: '响应产生'});
      if (response(f)) result.push({i, label: '响应握手'});
      if (!p.done && q.done) result.push({i, label: '最后写入 / DONE'});
      if (!p.rst_n && (i === 0 || current().frames[i-1].pre.rst_n)) result.push({i, label: '复位已生效'});
      if (i > 0 && p.rst_n && !current().frames[i-1].pre.rst_n) result.push({i, label: '复位释放'});
      if (p.rsp_valid && !p.rsp_ready && (i === 0 || !current().frames[i-1].pre.rsp_valid)) result.push({i, label: '响应等待'});
    });
    return result;
  }
  function drawWave() {
    const keys = signals(), fs = current().frames;
    const left = 148, cell = 88, half = cell/2, top = 58, row = 29;
    const width = left + cell * fs.length + 15, height = top + row * keys.length + 13;
    waveLayout = {left, cell, width, height};
    const selectedX = left + state.index * cell;
    let svg = `<rect width="${width}" height="${height}" fill="#142e31"/><rect x="${selectedX}" y="0" width="${cell}" height="${height}" fill="#b47d3c" opacity=".13"/>`;
    let labels = `<rect x="0" y="0" width="${left-5}" height="${height}" fill="#193437"/><text x="13" y="22" fill="#aac3b6" font-size="10">SIGNAL / DIRECTION</text><text x="13" y="41" fill="#6c9587" font-size="9">左半：沿前 · 右半：沿后</text>`;
    fs.forEach((f, i) => {
      const x = left + i*cell, edgeX = x+half;
      svg += `<line x1="${x}" x2="${x}" y1="44" y2="${height}" stroke="#294549" stroke-width=".7"/>`;
      svg += `<line x1="${edgeX}" x2="${edgeX}" y1="42" y2="${height}" stroke="${i===state.index ? '#e7b17e' : '#456253'}" stroke-dasharray="${i===state.index ? '0' : '2 4'}" opacity="${i===state.index ? '.9' : '.55'}"/>`;
      svg += `<text x="${edgeX}" y="21" text-anchor="middle" fill="${i===state.index ? '#ffd5aa' : '#9cb7aa'}" font-size="11">E${i}</text>`;
      const badges = [command(f) ? 'C' : '', response(f) ? 'R' : '', !f.pre.done && f.post.done ? 'D' : ''].filter(Boolean).join('·');
      if (badges) svg += `<text x="${edgeX}" y="37" text-anchor="middle" fill="#e4c098" font-size="9">${badges}</text>`;
    });
    keys.forEach((key, ri) => {
      const mid = top + ri*row + 13, high = mid-7, low = mid+7, color = palette(key);
      const direction = INPUTS.has(key) ? '→' : OUTPUTS.has(key) ? '←' : '·';
      svg += `<line x1="5" x2="${width}" y1="${mid+14}" y2="${mid+14}" stroke="#294448" stroke-width=".5"/>`;
      labels += `<text x="12" y="${mid+4}" fill="${color}" font-size="10"><title>${esc(HELP[key] || key)}</title>${esc(LABEL[key] || key)}</text><text x="132" y="${mid+4}" fill="#6d9485" font-size="11">${direction}</text>`;
      const values = fs.flatMap(f => key === 'clk' ? [0, 1] : [f.pre[key], f.post[key]]);
      if (key === 'clk' || BITS.has(key)) {
        let d = '';
        values.forEach((v, j) => {
          const x = left+j*half, y = v === 1 ? high : v === 0 ? low : mid;
          d += j === 0 ? `M${x},${y}` : `L${x},${y}`;
          d += `L${x+half},${y}`;
          if (v == null) svg += `<text x="${x+half/2}" y="${mid-3}" fill="${color}" font-size="9" text-anchor="middle">X</text>`;
        });
        svg += `<path d="${d}" fill="none" stroke="${color}" stroke-width="${key==='clk' ? 1.25 : 1.6}"/>`;
      } else {
        for (let j=0; j<values.length;) {
          let end=j+1;while(end<values.length && values[end]===values[j])end++;
          const x=left+j*half, w=(end-j)*half, value=fmt(key,values[j]);
          svg += `<path d="M${x},${mid} L${x+4},${high} H${x+w-4} L${x+w},${mid} L${x+w-4},${low} H${x+4} Z" fill="${color}" fill-opacity=".045" stroke="${color}" stroke-width="1.1"><title>${esc((LABEL[key]||key)+': '+value)}</title></path>`;
          const maxChars = Math.floor((w-13)/5.7);
          let shown = value.length <= maxChars ? value : maxChars > 3 ? value.slice(0,maxChars-1)+'…' : '…';
          svg += `<text x="${x+w/2}" y="${mid+3.5}" fill="${color}" text-anchor="middle" font-size="10"><title>${esc(value)}</title>${esc(shown)}</text>`;
          j=end;
        }
      }
    });
    $('wave').setAttribute('width', width);
    $('wave').setAttribute('height', height);
    $('wave').setAttribute('viewBox', `0 0 ${width} ${height}`);
    $('wave').style.fontFamily = 'Consolas, monospace';
    $('wave').innerHTML = svg + `<g id="waveLabels" transform="translate(${$('waveScroll').scrollLeft},0)">${labels}</g>`;
  }
  function updateInspector() {
    const f=frame(), p=f.pre, q=f.post;
    $('edgeLabel').textContent='E'+state.index;
    for (const [id,a,b] of [['cmdHandshake','cmd_valid','cmd_ready'],['rspHandshake','rsp_valid','rsp_ready']]) {
      const yes = p.rst_n && p[a]===1 && p[b]===1;
      $(id).classList.toggle('yes',!!yes);
      $(id).querySelector('b').textContent = `${p[a]} & ${p[b]} = ${yes ? 1 : 0}`;
    }
    $('statePre').textContent=HOST[p.host_state] || 'X';
    $('statePost').textContent=HOST[q.host_state] || 'X';
    $('statusChips').innerHTML=['busy','done','irq'].map(k=>`<span class="${q[k] ? 'on':''}">${k.toUpperCase()} ${q[k]}</span>`).join('')+(q.rsp_valid&&q.rsp_err ? '<span class="error">ERR 1</span>':'');
    $('edgeTime').innerHTML=`真实仿真沿 #${f.edge}<br>时间 ${(f.time_ps/1000).toLocaleString('en-US')} ns · 本段E0起计<br>${q.rsp_valid && f.pre.cmd_read && current().address >= 0x10000 && !q.rsp_err ? `读数：${signed32(q.rsp_rdata)} / 256 = <b>${signed32(q.rsp_rdata)/256}</b>` : '握手按沿前值判断，状态显示沿后值。'}`;
    let keys=['cmd_valid','cmd_ready','rsp_valid','rsp_ready','rsp_err','rsp_rdata',...current().focus];
    if(current().kind==='reset')keys.unshift('rst_n');
    if(current().kind==='write')keys.splice(2,0,'cmd_wdata','cmd_wmask');
    keys=[...new Set(keys)];
    $('values').innerHTML=keys.map(k=>`<tr><td title="${esc(HELP[k] || k)}">${esc(LABEL[k]||k)}</td><td title="${esc(fmt(k,p[k]))}">${esc(fmt(k,p[k]))}</td><td class="${p[k]!==q[k]?'changed':''}" title="${esc(fmt(k,q[k]))}">${esc(fmt(k,q[k]))}</td></tr>`).join('');
    const [title,tag,text]=describe(f);
    $('eventTitle').textContent=title;$('eventTag').textContent=tag;$('eventText').innerHTML=text;
    $('frameLabel').textContent=`${state.index+1} / ${current().frames.length}`;
    $('scrub').value=state.index;
    $('prev').disabled=state.index===0;
    $('next').disabled=state.index===current().frames.length-1;
    $('play').textContent=state.playing?'❚❚ 暂停':state.index===current().frames.length-1?'↻ 重播':'▶ 播放';
    document.querySelectorAll('#jumps button').forEach(b=>b.classList.toggle('current',+b.dataset.edge===state.index));
  }
  function keepCursorVisible() {
    const el=$('waveScroll'), x=waveLayout.left+state.index*waveLayout.cell+waveLayout.cell/2;
    if(x>el.scrollLeft+el.clientWidth-55)el.scrollLeft=x-el.clientWidth+90;
    else if(x<el.scrollLeft+waveLayout.left+25)el.scrollLeft=Math.max(0,x-waveLayout.left-45);
    const labels=$('waveLabels');if(labels)labels.setAttribute('transform',`translate(${el.scrollLeft},0)`);
  }
  function render(scroll=false) {drawWave();updateInspector();if(scroll)keepCursorVisible();}
  function stop() {clearTimeout(timer);timer=null;state.playing=false;}
  function seek(index) {stop();state.index=Math.max(0,Math.min(current().frames.length-1,index));render(true);}
  function tick() {
    if(!state.playing)return;
    if(state.index<current().frames.length-1)state.index++;
    if(state.index===current().frames.length-1)stop();
    render(true);
    if(state.playing)timer=setTimeout(tick,state.speed);
  }
  function playPause() {
    if(state.playing){stop();updateInspector();return;}
    if(state.index===current().frames.length-1)state.index=0;
    state.playing=true;tick();
  }
  function selectScene(id, changeHash=true) {
    if(!scenes[id])return;
    stop();state.scene=id;state.index=0;
    const s=current();
    $('sceneCategory').textContent=`${s.group} / ${String(RANK.get(id)+1).padStart(2,'0')} OF ${scenes.length}`;
    $('sceneTitle').textContent=s.title;$('sceneDescription').textContent=s.description;
    const type={read:'READ',write:'WRITE',sequence:'TWO COMMANDS',observe:'OBSERVE',reset:'ASYNC RESET'}[s.kind];
    $('commandLine').innerHTML=`<span class="pill ${s.error?'warn':''}">${type}${s.error?' · ERROR':''}</span>`+
      (s.address==null?'':`<span class="pill">ADDR ${hex(s.address,5)}</span>`)+
      (s.value==null?'':`<span class="pill">WDATA ${hex(s.value)}</span>`)+
      (s.expected==null?'':`<span class="pill">RDATA ${hex(s.expected)}</span>`)+
      `<span class="pill">${s.frames.length} 个采样沿</span>`;
    $('scrub').max=s.frames.length-1;
    const ev=events();
    $('jumps').innerHTML=(ev.length ? ev : [{i:0,label:'首个采样沿'}]).map(e=>`<button type="button" data-edge="${e.i}">E${e.i} · ${esc(e.label)}</button>`).join('');
    $('eventList').innerHTML=ev.length ? ev.map(e=>`<button type="button" data-edge="${e.i}"><strong>E${e.i}</strong>${esc(e.label)}</button>`).join('') : '<span class="tiny">本场景没有总线握手，用于观察无VALID时的行为。</span>';
    $('sceneNote').textContent=s.note || s.description;
    $('waveScroll').scrollLeft=0;
    $('prevScene').disabled=RANK.get(id)===0;$('nextScene').disabled=RANK.get(id)===scenes.length-1;
    buildCatalog();render();
    const active=$('catalogList').querySelector('.active');
    if(active){const a=active.getBoundingClientRect(),n=$('catalogList').getBoundingClientRect();if(a.top<n.top||a.bottom>n.bottom)$('catalogList').scrollTop+=a.top-n.top-25;}
    if(changeHash)history.replaceState(null,'','#scene-'+id);
  }
  $('catalogList').addEventListener('click',e=>{const b=e.target.closest('[data-scene]');if(b)selectScene(+b.dataset.scene);});
  $('search').addEventListener('input',e=>{state.query=e.target.value;buildCatalog();});
  $('groupFilter').addEventListener('change',e=>{state.group=e.target.value;buildCatalog();});
  $('play').addEventListener('click',playPause);
  $('prev').addEventListener('click',()=>seek(state.index-1));
  $('next').addEventListener('click',()=>seek(state.index+1));
  $('scrub').addEventListener('input',e=>seek(+e.target.value));
  $('speed').addEventListener('change',e=>{state.speed=+e.target.value;if(state.playing){clearTimeout(timer);timer=setTimeout(tick,state.speed);}});
  $('signalMode').addEventListener('change',e=>{state.mode=e.target.value;render();});
  for(const id of ['jumps','eventList'])$(id).addEventListener('click',e=>{const b=e.target.closest('[data-edge]');if(b)seek(+b.dataset.edge);});
  $('prevScene').addEventListener('click',()=>selectScene(ORDER[RANK.get(state.scene)-1]?.id));
  $('nextScene').addEventListener('click',()=>selectScene(ORDER[RANK.get(state.scene)+1]?.id));
  $('wave').addEventListener('click',e=>{
    if(e.clientX<$('waveScroll').getBoundingClientRect().left+waveLayout.left)return;
    const rect=$('wave').getBoundingClientRect(),x=(e.clientX-rect.left)*waveLayout.width/rect.width;
    if(x>=waveLayout.left)seek(Math.floor((x-waveLayout.left)/waveLayout.cell));
  });
  $('waveScroll').addEventListener('scroll',()=>{const g=$('waveLabels');if(g)g.setAttribute('transform',`translate(${$('waveScroll').scrollLeft},0)`);},{passive:true});
  window.addEventListener('resize',()=>requestAnimationFrame(keepCursorVisible));
  document.addEventListener('keydown',e=>{
    if(/^(INPUT|SELECT|TEXTAREA|BUTTON)$/.test(e.target.tagName)||e.ctrlKey||e.metaKey||e.altKey)return;
    if(e.code==='Space'){e.preventDefault();playPause();}
    if(e.key==='ArrowLeft'){e.preventDefault();seek(state.index-1);}
    if(e.key==='ArrowRight'){e.preventDefault();seek(state.index+1);}
    if(e.key==='Home'){e.preventDefault();seek(0);}
    if(e.key==='End'){e.preventDefault();seek(current().frames.length-1);}
  });
  window.addEventListener('hashchange',()=>{const m=location.hash.match(/^#scene-(\d+)$/);if(m)selectScene(+m[1],false);});
  const groups=GROUPS;
  $('groupFilter').innerHTML='<option value="all">全部类别</option>'+groups.map(g=>`<option>${esc(g)}</option>`).join('');
  const path=[['写X','写 X[0,0]'],['读X','读 X[0,0]'],['启动','START：写 CONTROL = 1'],['查状态','运行中读 STATUS'],['完成','最后一次写回 → DONE / IRQ'],['读Y','完成后读 Y[0,0]'],['应答','完成后清除 DONE / IRQ']];
  path.forEach(([label,title],i)=>{if(i){const arrow=document.createElement('span');arrow.textContent='→';$('learningPath').append(arrow);}const b=document.createElement('button');b.type='button';b.textContent=label;b.addEventListener('click',()=>selectScene(scenes.findIndex(s=>s.title===title)));$('learningPath').append(b);});
  $('caseCount').textContent=scenes.length;$('groupCount').textContent=groups.length;$('frameCount').textContent=DATA.meta.frames;
  $('sourceMeta').innerHTML=`采集器：${esc(DATA.meta.source)}。共${DATA.meta.checks}项时序断言通过。<br>`+Object.entries(DATA.meta.hashes).map(([k,v])=>`${esc(k)} SHA-256：<code>${v}</code>`).join('<br>');
  const initial=location.hash.match(/^#scene-(\d+)$/);
  selectScene(initial&&scenes[+initial[1]] ? +initial[1] : 0,false);
  $('startup').textContent=`运行就绪 · ${scenes.length}个场景已载入 · 播放会立即前进一拍`;
  window.transactionLab={state,scenes,selectScene,seek,playPause,stop,events,signals,meta:DATA.meta};
})();
