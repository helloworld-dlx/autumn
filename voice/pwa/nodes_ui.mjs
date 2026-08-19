const grid = document.querySelector('#devices-grid');

if (grid) {
  const style = document.createElement('style');
  style.id = 'autumn-node-devices-style-v1';
  style.textContent = `
  #devices-grid.autumn-node-grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:12px}
  .autumn-node-card{min-width:0;min-height:112px;border-radius:19px;padding:15px 16px;background:var(--paper);border:1px solid #ffffff94;box-shadow:0 14px 40px #37233214}
  .autumn-node-head{display:flex;align-items:center;justify-content:space-between;gap:10px}
  .autumn-node-title{font-size:13px;font-weight:720;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .autumn-node-secondary{margin-top:22px;color:var(--muted);font-size:9.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}
  .autumn-node-state{flex:0 0 auto;display:inline-flex;align-items:center;gap:5px;border:1px solid var(--line);background:#302a310d;color:var(--muted);padding:5px 8px;border-radius:999px;font-size:8.5px}
  .autumn-node-state:before{content:"";width:6px;height:6px;border-radius:50%;background:#9a8d95}
  .autumn-node-state.online{color:#3d7b5a;background:#5caa7c15}.autumn-node-state.online:before{background:#63a77c}
  .autumn-node-state.recent{color:#9a6746;background:#d99a681a}.autumn-node-state.recent:before{background:#d59664}
  .autumn-node-state.offline{color:#a65b62;background:#c76c7515}.autumn-node-state.offline:before{background:#bd6f76}
  @media(max-width:720px){
    #devices-grid.autumn-node-grid{grid-template-columns:1fr;gap:7px}
    .autumn-node-card{min-height:0;padding:11px 12px;border-radius:15px;display:grid;grid-template-columns:minmax(0,1fr) auto;grid-template-rows:auto auto;column-gap:10px;row-gap:3px;align-items:center}
    .autumn-node-head{display:contents}
    .autumn-node-title{grid-column:1;grid-row:1;font-size:11.5px}
    .autumn-node-state{grid-column:2;grid-row:1/3;align-self:center;font-size:8px}
    .autumn-node-secondary{grid-column:1;grid-row:2;margin:0;font-size:8.5px}
  }`;
  document.head.append(style);

  const profiles = {
    'pi5-core': {title:'Pi 5 · Core', role:'Autumn 中枢'},
    'windows-main': {title:'Windows · Runner', role:'执行节点'},
    'xiaomi15': {title:'Xiaomi 15 · Phone', role:'Companion'},
  };

  function safeState(value){
    const s=String(value||'UNKNOWN').toUpperCase();
    return ['ONLINE','RECENT','OFFLINE','UNKNOWN'].includes(s)?s:'UNKNOWN';
  }

  function humanLastSeen(value){
    if(typeof value!=='string'||!value.trim()) return '尚无最近活动';
    const t=Date.parse(value);
    if(!Number.isFinite(t)) return '尚无最近活动';
    const seconds=Math.max(0,Math.round((Date.now()-t)/1000));
    if(seconds<45) return '刚刚';
    if(seconds<3600) return `${Math.max(1,Math.round(seconds/60))} 分钟前`;
    if(seconds<86400) return `${Math.max(1,Math.round(seconds/3600))} 小时前`;
    return '较早';
  }

  function fallbackTitle(node){
    const id=String(node?.node_id||'Device').replace(/[-_]+/g,' ').trim();
    return id ? id.replace(/\b\w/g,m=>m.toUpperCase()) : 'Device';
  }

  function render(nodes){
    const list=Array.isArray(nodes)?nodes:[];
    grid.className='device-grid autumn-node-grid';
    grid.replaceChildren();
    if(!list.length){
      const card=document.createElement('section');
      card.className='autumn-node-card';
      card.innerHTML='<div class="status-note">Node Registry 暂不可用。</div>';
      grid.append(card);
      return;
    }
    for(const node of list){
      const profile=profiles[node?.node_id]||{title:fallbackTitle(node),role:'Autumn Node'};
      const state=safeState(node?.online);
      const card=document.createElement('section');
      card.className='autumn-node-card';
      const head=document.createElement('div');head.className='autumn-node-head';
      const title=document.createElement('div');title.className='autumn-node-title';title.textContent=profile.title;
      const pill=document.createElement('span');pill.className='autumn-node-state '+state.toLowerCase();pill.textContent=state;
      const secondary=document.createElement('div');secondary.className='autumn-node-secondary';
      secondary.textContent=`${profile.role} · ${humanLastSeen(node?.last_seen)}`;
      head.append(title,pill);card.append(head,secondary);grid.append(card);
    }
  }

  globalThis.autumnRenderNodes=render;
}
