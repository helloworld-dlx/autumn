const host = document.querySelector('#home-devices');

if (host) {
  const style = document.createElement('style');
  style.id = 'autumn-home-devices-style-v2';
  style.textContent = `
  .autumn-home-wrap{margin-top:12px}
  .autumn-home-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin:2px 0 12px}
  .autumn-home-head-copy{min-width:0}
  .autumn-home-head-copy p{margin:4px 0 0;color:var(--muted);font-size:10px;line-height:1.5}
  .autumn-home-discover{flex:0 0 auto;border:1px solid #de846a2b;background:linear-gradient(145deg,#f4bf8f2c,#de846a1f);color:#765049;border-radius:999px;padding:8px 11px;font-size:10px;font-weight:700}
  .autumn-home-discover:hover{background:linear-gradient(145deg,#f4bf8f42,#de846a2b)}
  .autumn-home-rooms{display:grid;gap:13px}
  .autumn-home-room{min-width:0}
  .autumn-home-room-head{display:flex;align-items:center;justify-content:space-between;padding:0 3px 7px;color:var(--muted);font-size:9px;letter-spacing:.06em}
  .autumn-home-room-head b{color:#6d5c65;font-size:10px;letter-spacing:.02em}
  .autumn-home-grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(148px,1fr));gap:9px}
  .autumn-home-card{position:relative;min-width:0;min-height:103px;border:1px solid #ffffffa0;background:linear-gradient(145deg,#fffaf6d9,#ffffffa6);box-shadow:0 8px 24px #402b3910;border-radius:17px;padding:11px;cursor:pointer;text-align:left;overflow:hidden;transition:transform .16s ease,box-shadow .16s ease,border-color .16s ease}
  .autumn-home-card:hover,.autumn-home-card:focus-visible{transform:translateY(-1px);border-color:#de846a3b;box-shadow:0 12px 28px #402b3917;outline:none}
  .autumn-home-card:after{content:"";position:absolute;width:72px;height:72px;right:-24px;bottom:-32px;border-radius:50%;background:radial-gradient(circle,#f2b48c23,transparent 68%);pointer-events:none}
  .autumn-home-card-top{display:flex;align-items:flex-start;justify-content:space-between;gap:8px}
  .autumn-home-icon{width:30px;height:30px;border-radius:11px;display:grid;place-items:center;background:#503e4a0b;font-size:15px}
  .autumn-home-badge{border:1px solid var(--line);background:#ffffff9c;color:var(--muted);padding:4px 6px;border-radius:999px;font-size:8px;white-space:nowrap}
  .autumn-home-badge.control{color:#955f4e;background:#de846a12;border-color:#de846a20}
  .autumn-home-name{margin-top:8px;font-size:11px;font-weight:720;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .autumn-home-state{margin-top:4px;font-size:13px;font-weight:680;letter-spacing:-.015em;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .autumn-home-sub{margin-top:5px;color:var(--muted);font-size:8.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .autumn-home-empty{padding:15px;border:1px dashed #6e59651f;border-radius:15px;color:var(--muted);font-size:10px;text-align:center}
  .autumn-home-discovery{display:none;margin:0 0 14px;padding:13px;border-radius:17px;background:#fff9f5a8;border:1px solid #ffffff9c;box-shadow:0 8px 24px #402b390b}
  .autumn-home-discovery.open{display:block}
  .autumn-home-discovery-head{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:9px}
  .autumn-home-discovery-head b{font-size:11px}.autumn-home-discovery-head span{font-size:9px;color:var(--muted)}
  .autumn-home-candidates{display:grid;grid-template-columns:repeat(auto-fill,minmax(210px,1fr));gap:8px}
  .autumn-home-candidate{display:grid;grid-template-columns:32px minmax(0,1fr) auto;gap:9px;align-items:center;padding:9px;border:1px solid var(--line);background:#ffffff99;border-radius:13px}
  .autumn-home-candidate .autumn-home-icon{width:30px;height:30px;border-radius:10px;font-size:15px}
  .autumn-home-candidate-name{font-size:10px;font-weight:700;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .autumn-home-candidate-meta{margin-top:2px;color:var(--muted);font-size:8px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .autumn-home-add{border:0;border-radius:999px;background:linear-gradient(145deg,var(--accent2),var(--accent));color:#57363b;padding:7px 9px;font-size:9px;font-weight:800}
  .autumn-home-add:disabled{opacity:.55}
  .autumn-home-overlay{position:fixed;inset:0;z-index:240;display:none;align-items:center;justify-content:center;padding:18px;background:#2f24302b;backdrop-filter:blur(5px);-webkit-backdrop-filter:blur(5px)}
  .autumn-home-overlay.open{display:flex}
  .autumn-home-sheet{width:min(390px,100%);border-radius:22px;background:#fffaf7f7;border:1px solid #ffffffcf;box-shadow:0 28px 78px #3a293741;padding:18px}
  .autumn-home-sheet-head{display:flex;align-items:flex-start;justify-content:space-between;gap:14px}
  .autumn-home-sheet-title{display:flex;align-items:center;gap:11px;min-width:0}
  .autumn-home-sheet-title .autumn-home-icon{width:40px;height:40px;font-size:20px}
  .autumn-home-sheet-title h3{margin:0;font-size:16px}.autumn-home-sheet-title p{margin:4px 0 0;color:var(--muted);font-size:9px}
  .autumn-home-close{border:0;width:30px;height:30px;border-radius:50%;background:#503e4a0b;color:var(--muted)}
  .autumn-home-capbox{margin-top:15px;padding:12px;border-radius:14px;background:#503e4a08;border:1px solid var(--line)}
  .autumn-home-capbox b{display:block;font-size:9px;margin-bottom:7px;color:#6f5a63}
  .autumn-home-chips{display:flex;flex-wrap:wrap;gap:5px}.autumn-home-chip{padding:5px 7px;border:1px solid var(--line);border-radius:999px;background:#fff;color:#6d5d65;font-size:8px}
  .autumn-home-say{margin-top:11px;padding:11px 12px;border-left:2px solid #de846a80;background:#fff6f1;border-radius:0 12px 12px 0;color:#735851;font-size:9px;line-height:1.6}
  @media(max-width:720px){
    .autumn-home-wrap{margin-top:10px}
    .autumn-home-head{margin-bottom:10px}
    .autumn-home-head-copy p{font-size:9px}
    .autumn-home-grid{grid-template-columns:repeat(2,minmax(0,1fr));gap:8px}
    .autumn-home-card{min-height:96px;padding:10px;border-radius:15px}
    .autumn-home-state{font-size:12px}
    .autumn-home-candidates{grid-template-columns:1fr}
    .autumn-home-overlay{align-items:flex-end;padding:8px}
    .autumn-home-sheet{border-radius:22px 22px 16px 16px;padding-bottom:max(18px,env(safe-area-inset-bottom))}
  }`;
  document.head.append(style);

  const wrap = document.createElement('div');
  wrap.className = 'autumn-home-wrap';
  host.parentNode.insertBefore(wrap, host);
  wrap.append(host);
  host.className = 'autumn-home-rooms';

  const head = document.createElement('div');
  head.className = 'autumn-home-head';
  head.innerHTML = `<div class="autumn-home-head-copy"><p>状态优先。日常控制继续交给 Chat / Talk。</p></div><button class="autumn-home-discover" type="button">＋ 发现新设备</button>`;
  wrap.insertBefore(head, host);

  const discovery = document.createElement('section');
  discovery.className = 'autumn-home-discovery';
  discovery.innerHTML = `<div class="autumn-home-discovery-head"><b>发现新设备</b><span>按物理设备去重 · 不会自动授权</span></div><div class="autumn-home-candidates"></div>`;
  wrap.insertBefore(discovery, host);

  const overlay = document.createElement('div');
  overlay.className = 'autumn-home-overlay';
  overlay.innerHTML = `<section class="autumn-home-sheet" role="dialog" aria-modal="true" aria-label="Home 设备详情"></section>`;
  document.body.append(overlay);

  const iconFor = kind => ({light:'💡',switch:'⏻',fan:'◌',speaker:'◖',climate_sensor:'⌁',temperature:'⌁',humidity:'◌'})[kind] || '◇';
  const kindName = kind => ({light:'灯光',switch:'开关',fan:'风扇',speaker:'音箱',climate_sensor:'温湿度计',temperature:'温度',humidity:'湿度'})[kind] || '设备';
  const commandName = command => ({on:'开',off:'关',set_speed:'风速',play:'播放',pause:'暂停',set_volume:'音量'})[command] || command;
  const stateName = state => ({on:'已开启',off:'已关闭',playing:'正在播放',paused:'已暂停',idle:'在线',buffering:'缓冲中',unavailable:'不可用',unknown:'未知'})[String(state||'').toLowerCase()] || String(state||'未知');
  const pct = value => typeof value === 'number' && Number.isFinite(value) ? Math.round(value) + '%' : '';
  const volumePct = value => typeof value === 'number' && Number.isFinite(value) ? Math.round(value * 100) + '%' : '';

  function viewState(device){
    const s=device?.state&&typeof device.state==='object'?device.state:{};
    if(device.kind==='climate_sensor'){
      const t=s.temperature!=null?String(s.temperature)+(s.temperature_unit||''):'';
      const h=s.humidity!=null?String(s.humidity)+(s.humidity_unit||''):'';
      return [t,h].filter(Boolean).join(' · ')||'暂无读数';
    }
    if(device.kind==='fan'){
      const base=stateName(s.state), speed=pct(s.percentage);
      return speed&&String(s.state).toLowerCase()!=='off'?base+' · '+speed:base;
    }
    if(device.kind==='speaker'){
      const base=stateName(s.state), volume=volumePct(s.volume_level);
      return volume?base+' · '+volume:base;
    }
    if(device.kind==='temperature'||device.kind==='humidity') return s.state!=null?String(s.state)+(s.unit_of_measurement||''):'暂无读数';
    return stateName(s.state);
  }

  function capabilityNames(device){
    if(device.kind==='climate_sensor') return ['温度','湿度'];
    const commands=Array.isArray(device.commands)?device.commands.map(commandName):[];
    if(device.kind==='light'&&device?.state?.brightness!=null) commands.push('读取亮度');
    return [...new Set(commands.length?commands:['读取状态'])];
  }

  function example(device){
    const label=device.label||'这个设备';
    if(device.kind==='fan') return `可以对 Autumn 说：“打开${label}” 或 “${label}风速调到 40%”。`;
    if(device.kind==='speaker') return `可以对 Autumn 说：“暂停${label}” 或 “${label}音量调到 30%”。`;
    if(device.kind==='light') return `可以对 Autumn 说：“打开${label}” 或 “关闭${label}”。`;
    if(device.kind==='climate_sensor') return `可以问 Autumn：“${label}现在温度和湿度多少？”`;
    if(device.kind==='temperature') return `可以问 Autumn：“${label}现在多少度？”`;
    if(device.kind==='humidity') return `可以问 Autumn：“${label}现在湿度多少？”`;
    return `可以直接在 Chat / Talk 里提到“${label}”。`;
  }

  function escapeHtml(value){
    return String(value??'').replace(/[&<>"']/g,ch=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[ch]));
  }

  function closeDevice(){ overlay.classList.remove('open'); }

  function openDevice(device){
    const sheet=overlay.querySelector('.autumn-home-sheet');
    const caps=capabilityNames(device);
    sheet.innerHTML=`<div class="autumn-home-sheet-head"><div class="autumn-home-sheet-title"><div class="autumn-home-icon">${iconFor(device.kind)}</div><div><h3>${escapeHtml(device.label||device.device||'Home Device')}</h3><p>${escapeHtml(device.room||'未分区')} · ${escapeHtml(viewState(device))}</p></div></div><button class="autumn-home-close" type="button" aria-label="关闭">×</button></div><div class="autumn-home-capbox"><b>${device.controllable?'Autumn 可以控制':'Autumn 可以读取'}</b><div class="autumn-home-chips">${caps.map(x=>`<span class="autumn-home-chip">${escapeHtml(x)}</span>`).join('')}</div></div><div class="autumn-home-say">${escapeHtml(example(device))}</div>`;
    overlay.classList.add('open');
    sheet.querySelector('.autumn-home-close')?.addEventListener('click', closeDevice, {once:true});
  }

  function render(home){
    host.replaceChildren();
    if(!home||home.configured!==true){
      host.innerHTML='<div class="autumn-home-empty">Home Assistant / Xiaomi Home 尚未配置。</div>';
      return;
    }
    const devices=Array.isArray(home.devices)?home.devices:[];
    if(!devices.length){host.innerHTML='<div class="autumn-home-empty">还没有设备加入 Autumn。</div>';return}
    const rooms=new Map();
    for(const device of devices){
      const room=String(device?.room||'未分区');
      if(!rooms.has(room))rooms.set(room,[]);
      rooms.get(room).push(device);
    }
    for(const [room,items] of rooms){
      const section=document.createElement('section');section.className='autumn-home-room';
      const roomHead=document.createElement('div');roomHead.className='autumn-home-room-head';
      roomHead.innerHTML=`<b>${escapeHtml(room)}</b><span>${items.length} 个设备</span>`;
      const grid=document.createElement('div');grid.className='autumn-home-grid';
      for(const device of items){
        const card=document.createElement('button');card.type='button';card.className='autumn-home-card';
        const controllable=device?.controllable===true;
        card.setAttribute('aria-label',`${device.label||'Home Device'}，${viewState(device)}，查看详情`);
        card.innerHTML=`<div class="autumn-home-card-top"><div class="autumn-home-icon">${iconFor(device.kind)}</div><span class="autumn-home-badge ${controllable?'control':''}">${controllable?'可控制':'只读'}</span></div><div class="autumn-home-name">${escapeHtml(device.label||device.device||'Home Device')}</div><div class="autumn-home-state">${escapeHtml(viewState(device))}</div><div class="autumn-home-sub">${escapeHtml(kindName(device.kind))}</div>`;
        card.addEventListener('click',()=>openDevice(device));
        grid.append(card);
      }
      section.append(roomHead,grid);host.append(section);
    }
  }

  async function discover(){
    const button=head.querySelector('.autumn-home-discover');
    button.disabled=true;button.textContent='正在发现…';discovery.classList.add('open');
    const list=discovery.querySelector('.autumn-home-candidates');
    list.innerHTML='<div class="autumn-home-empty">正在读取 Home Assistant…</div>';
    try{
      const response=await fetch('/api/home/discover',{method:'POST',headers:{'X-Autumn-Companion':'1'},cache:'no-store'});
      const payload=await response.json();
      if(!response.ok)throw new Error(payload?.message||'discover failed');
      const candidates=Array.isArray(payload.candidates)?payload.candidates:[];
      list.replaceChildren();
      if(!candidates.length) list.innerHTML='<div class="autumn-home-empty">没有新的可加入设备。</div>';
      for(const candidate of candidates){
        const item=document.createElement('article');item.className='autumn-home-candidate';
        item.innerHTML=`<div class="autumn-home-icon">${iconFor(candidate.kind)}</div><div><div class="autumn-home-candidate-name">${escapeHtml(candidate.label||'Home Device')}</div><div class="autumn-home-candidate-meta">${escapeHtml(candidate.room||'未分区')} · ${escapeHtml(kindName(candidate.kind))}</div></div><button class="autumn-home-add" type="button">加入 Autumn</button>`;
        const add=item.querySelector('.autumn-home-add');
        add.addEventListener('click',()=>authorize(candidate,add));
        list.append(item);
      }
      const unsupported=Number(payload.unsupported_count||0);
      discovery.querySelector('.autumn-home-discovery-head span').textContent=unsupported?`另有 ${unsupported} 个实体不在当前安全范围`:'按物理设备去重 · 不会自动授权';
    }catch{
      list.innerHTML='<div class="autumn-home-empty">暂时无法发现设备，请确认 Home Assistant 在线。</div>';
    }finally{
      button.disabled=false;button.textContent='＋ 发现新设备';
    }
  }

  async function authorize(candidate,button){
    button.disabled=true;button.textContent='加入中…';
    try{
      const response=await fetch('/api/home/authorize',{method:'POST',headers:{'Content-Type':'application/json','X-Autumn-Companion':'1'},body:JSON.stringify({candidateId:candidate.candidate_id})});
      const payload=await response.json();
      if(!response.ok)throw new Error(payload?.message||'authorize failed');
      button.textContent='已加入';
      await globalThis.autumnRefreshCompanionStatus?.();
      setTimeout(discover,250);
    }catch{
      button.disabled=false;button.textContent='重试';
    }
  }

  head.querySelector('.autumn-home-discover')?.addEventListener('click',()=>discovery.classList.contains('open')?discovery.classList.remove('open'):discover());
  overlay.addEventListener('click',event=>{if(event.target===overlay)closeDevice()});
  document.addEventListener('keydown',event=>{if(event.key==='Escape'&&overlay.classList.contains('open'))closeDevice()});
  globalThis.autumnRenderHomeDevices=render;
  globalThis.autumnRefreshCompanionStatus?.();
}
