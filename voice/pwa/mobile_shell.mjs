const sidebar=document.querySelector('.sidebar');

if(sidebar){
  const style=document.createElement('style');
  style.id='autumn-mobile-shell-style-v1';
  style.textContent=`
  .autumn-mobile-nav-trigger,.autumn-mobile-nav-backdrop{display:none}
  @media(max-width:720px){
    .mobile-dock{display:none!important}
    .layout{display:block!important;min-height:100dvh}
    .main{width:100%;min-height:100dvh}
    .sidebar{
      display:flex!important;position:fixed!important;inset:0 auto 0 0!important;width:min(78vw,280px)!important;height:100dvh!important;
      z-index:230!important;transform:translateX(-105%);transition:transform .22s cubic-bezier(.2,.8,.2,1);
      box-shadow:18px 0 52px #281d282e
    }
    body.autumn-mobile-nav-open .sidebar{transform:translateX(0)}
    .autumn-mobile-nav-trigger{
      display:inline-flex;position:fixed;left:11px;top:max(11px,env(safe-area-inset-top));z-index:225;align-items:center;gap:7px;
      border:1px solid #ffffff4d;background:#30243245;color:#fff9f3;backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px);
      border-radius:999px;padding:7px 10px;box-shadow:0 8px 22px #2d1c2b1f;font-size:9px
    }
    .autumn-mobile-nav-mark{width:7px;height:7px;border-radius:50%;background:#f0a27c;box-shadow:0 0 9px #f0a27c99}
    .autumn-mobile-nav-backdrop{position:fixed;inset:0;z-index:220;background:#2c21302b;backdrop-filter:blur(3px);-webkit-backdrop-filter:blur(3px)}
    body.autumn-mobile-nav-open .autumn-mobile-nav-backdrop{display:block}
    body.spatial-open .autumn-mobile-nav-trigger,body.spatial-open .autumn-mobile-nav-backdrop{display:none!important}
    .section-page{padding-top:max(68px,calc(env(safe-area-inset-top) + 58px))!important;padding-bottom:max(26px,env(safe-area-inset-bottom))!important}
    #page-home .hero-copy{top:max(72px,calc(env(safe-area-inset-top) + 62px))}
    .top-actions{top:max(11px,env(safe-area-inset-top));right:11px}
    #page-chat .section-page{padding-bottom:0!important}
    #page-chat .chat-bottom{padding-bottom:max(8px,env(safe-area-inset-bottom))}
  }`;
  document.head.append(style);

  const trigger=document.createElement('button');
  trigger.type='button';trigger.className='autumn-mobile-nav-trigger';
  trigger.setAttribute('aria-label','打开 Autumn 导航');
  trigger.innerHTML='<span class="autumn-mobile-nav-mark"></span><span class="autumn-mobile-nav-label">Autumn</span>';
  document.body.append(trigger);

  const backdrop=document.createElement('div');
  backdrop.className='autumn-mobile-nav-backdrop';
  document.body.append(backdrop);

  const label=trigger.querySelector('.autumn-mobile-nav-label');
  const names={home:'主页',chat:'对话',talk:'Talk',activity:'活动',devices:'设备'};
  function close(){document.body.classList.remove('autumn-mobile-nav-open');trigger.setAttribute('aria-expanded','false')}
  function open(){document.body.classList.add('autumn-mobile-nav-open');trigger.setAttribute('aria-expanded','true')}
  function sync(){
    const active=document.querySelector('.page.active');
    const key=active?.id?.replace(/^page-/,'');
    label.textContent=names[key]||'Autumn';
  }
  trigger.addEventListener('click',()=>document.body.classList.contains('autumn-mobile-nav-open')?close():open());
  backdrop.addEventListener('click',close);
  sidebar.querySelectorAll('.nav-btn').forEach(btn=>btn.addEventListener('click',()=>{close();queueMicrotask(sync)}));
  document.addEventListener('keydown',event=>{if(event.key==='Escape')close()});
  new MutationObserver(sync).observe(document.querySelector('.main')||document.body,{subtree:true,attributes:true,attributeFilter:['class']});
  sync();
}
