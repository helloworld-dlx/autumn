const MOBILE_QUERY = "(max-width: 900px)";

const ICONS = Object.freeze({
  mic: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="3" width="8" height="12" rx="4"/><path d="M5 11a7 7 0 0 0 14 0M12 18v3"/></svg>`,
  more: `<svg viewBox="0 0 24 24" aria-hidden="true"><circle cx="5" cy="12" r="1.4"/><circle cx="12" cy="12" r="1.4"/><circle cx="19" cy="12" r="1.4"/></svg>`,
  activity: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h4l2-5 4 10 2-5h4"/></svg>`,
  devices: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="4" y="4" width="16" height="10" rx="2"/><path d="M9 19h6M12 14v5"/></svg>`,
  eyes: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.5-6 9.5-6 9.5 6 9.5 6-3.5 6-9.5 6-9.5-6-9.5-6Z"/><circle cx="12" cy="12" r="2.5"/></svg>`,
  files: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5h6l2 2h8v12H4z"/></svg>`,
  conversation: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 5.5h16v11H10l-4.5 3v-3H4z"/></svg>`,
});

function isMobile() {
  return Boolean(globalThis.matchMedia?.(MOBILE_QUERY)?.matches);
}

function installStyles() {
  if (document.querySelector("#autumn-mobile-companion-style")) return;
  const style = document.createElement("style");
  style.id = "autumn-mobile-companion-style";
  style.textContent = `
  @media(max-width:900px){
    html.mobile-companion-ready,html.mobile-companion-ready body{height:100%;overflow:hidden}
    body.mobile-companion-open{margin:0;background:#6f466c;color:#fff8f3}
    body.mobile-companion-open .app{min-height:100%;height:100%;background:transparent}
    body.mobile-companion-open .app>.layout{display:none!important}
    body.mobile-companion-open>.autumn-mobile-nav-trigger,
    body.mobile-companion-open>.autumn-mobile-nav-backdrop{display:none!important}

    #autumn-mobile-root{
      --m-ink:#fff9f4;
      --m-muted:rgba(255,249,244,.62);
      --m-line:rgba(255,255,255,.16);
      --m-glass:rgba(255,255,255,.095);
      --m-glass-strong:rgba(255,255,255,.135);
      position:fixed;inset:0;z-index:110;display:flex;flex-direction:column;gap:9px;
      padding:max(11px,env(safe-area-inset-top)) 12px max(10px,env(safe-area-inset-bottom));
      overflow:hidden;color:var(--m-ink);
      background:
        radial-gradient(circle at 72% 72%,rgba(255,190,122,.48),transparent 25%),
        radial-gradient(circle at 13% 23%,rgba(164,98,151,.42),transparent 34%),
        linear-gradient(160deg,#6c456c 0%,#92536d 34%,#c9766e 66%,#efad75 100%);
    }
    #autumn-mobile-root:before{
      content:"";position:absolute;inset:0;z-index:-1;pointer-events:none;opacity:.62;
      background:
        linear-gradient(160deg,transparent 18%,rgba(255,255,255,.065) 18.3%,transparent 19% 63%,rgba(255,255,255,.075) 63.3%,transparent 64%),
        url('/assets/afterglow-home.webp') center/cover;
      mix-blend-mode:soft-light;
    }
    #autumn-mobile-root button{font:inherit}
    #autumn-mobile-root svg{width:19px;height:19px;display:block}
    #autumn-mobile-root svg path,#autumn-mobile-root svg rect,#autumn-mobile-root svg circle{
      stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round
    }
    .mobile-glass{
      background:var(--m-glass);border:1px solid var(--m-line);
      box-shadow:0 16px 46px rgba(52,29,48,.14);
      backdrop-filter:blur(20px) saturate(112%);-webkit-backdrop-filter:blur(20px) saturate(112%)
    }

    .mobile-topbar{flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;gap:10px;padding:3px 2px 1px}
    .mobile-brand{min-width:0}
    .mobile-brand b{display:block;font-family:Georgia,"Songti SC",serif;font-size:25px;font-weight:600;line-height:1}
    .mobile-brand span{display:block;margin-top:4px;color:var(--m-muted);font-size:9px;letter-spacing:.04em}
    .mobile-top-actions{display:flex;align-items:center;gap:7px}
    .mobile-circle{
      width:40px;height:40px;border-radius:14px;border:1px solid var(--m-line);
      background:rgba(255,255,255,.075);color:#fff;display:grid;place-items:center
    }
    #autumn-mobile-root #connectivity{
      position:static!important;min-width:40px;width:40px;height:40px;padding:0!important;border-radius:14px;
      display:grid;place-items:center;font-size:0!important;background:rgba(255,255,255,.075)!important;
      color:#fff!important;border:1px solid var(--m-line)!important;box-shadow:none!important
    }
    #autumn-mobile-root #connectivity:before{width:8px;height:8px;margin:0!important}

    .mobile-conversation-hero{
      flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;gap:12px;
      padding:13px 13px 13px 15px;border-radius:21px
    }
    .mobile-conversation-copy{min-width:0}
    .mobile-conversation-copy button{
      max-width:100%;padding:0;border:0;background:none;color:#fff;text-align:left
    }
    .mobile-conversation-copy b{
      display:block;max-width:100%;font-size:14px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis
    }
    .mobile-conversation-copy span{
      display:block;margin-top:4px;max-width:100%;font-size:9px;color:var(--m-muted);
      white-space:nowrap;overflow:hidden;text-overflow:ellipsis
    }
    .mobile-talk-primary{
      flex:0 0 auto;height:48px;padding:0 16px;border:0;border-radius:16px;
      display:flex;align-items:center;justify-content:center;gap:7px;
      color:#5f3946;font-size:11px;font-weight:800;
      background:linear-gradient(135deg,#ffd49f,#ef9872);box-shadow:0 10px 26px rgba(84,43,54,.16)
    }

    .mobile-quick-grid{flex:0 0 auto;display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:7px}
    .mobile-quick{
      min-width:0;height:66px;padding:9px 10px;border-radius:17px;border:1px solid var(--m-line);
      background:rgba(255,255,255,.07);color:#fff;text-align:left
    }
    .mobile-quick svg{width:17px!important;height:17px!important;margin-bottom:7px}
    .mobile-quick b{display:block;font-size:10px;white-space:nowrap}
    .mobile-quick span{display:block;margin-top:3px;color:var(--m-muted);font-size:7.5px;white-space:nowrap;overflow:hidden;text-overflow:ellipsis}

    .mobile-chat-host{flex:1 1 auto;min-height:0;display:flex}
    #autumn-mobile-root .chat-shell{
      flex:1 1 auto;min-height:0!important;height:100%!important;width:100%;
      display:block!important;overflow:hidden!important;border-radius:21px!important;
      background:rgba(255,255,255,.105)!important;border:1px solid var(--m-line)!important;
      box-shadow:0 16px 46px rgba(52,29,48,.14)!important;
      backdrop-filter:blur(20px)!important;-webkit-backdrop-filter:blur(20px)!important
    }
    #autumn-mobile-root .chat-pane{
      height:100%!important;min-height:0!important;color:#fff;display:flex;flex-direction:column
    }
    #autumn-mobile-root .chat-pane-head{display:none!important}
    #autumn-mobile-root .chat-messages{
      flex:1 1 auto;min-height:0;padding:13px 11px 8px!important;overflow-y:auto!important;overscroll-behavior:contain
    }
    #autumn-mobile-root .chat-empty{color:var(--m-muted)!important;padding:32px 16px!important}
    #autumn-mobile-root .chat-empty b{color:#fff!important}
    #autumn-mobile-root .chat-message{
      max-width:90%!important;font-size:12px!important;line-height:1.55!important;
      color:#49303d!important;background:rgba(255,250,247,.88)!important;
      border-color:rgba(255,255,255,.35)!important;box-shadow:0 7px 18px rgba(46,27,42,.08)!important
    }
    #autumn-mobile-root .chat-message.user{
      color:#653f4c!important;background:linear-gradient(145deg,rgba(255,220,183,.92),rgba(240,155,122,.88))!important
    }
    #autumn-mobile-root .chat-thinking{color:var(--m-muted)!important}
    #autumn-mobile-root .chat-bottom{
      flex:0 0 auto;padding:7px 8px 8px!important;border-top:1px solid rgba(255,255,255,.08);
      background:rgba(68,42,62,.10)
    }
    #autumn-mobile-root .chat-attachment-queue{margin:0 2px 6px}
    #autumn-mobile-root .attachment-chip{background:rgba(255,250,247,.88)!important;color:#543743!important}
    #autumn-mobile-root .chat-composer{
      border-color:rgba(255,255,255,.18)!important;background:rgba(255,250,247,.91)!important;
      box-shadow:0 9px 24px rgba(56,31,49,.12)!important
    }
    #autumn-mobile-root .chat-composer textarea{color:#3f3039!important;font-size:12px!important}
    #autumn-mobile-root .chat-attach{background:rgba(95,64,76,.08)!important;color:#684650!important}
    #autumn-mobile-root .chat-send{width:40px;height:40px}
    #autumn-mobile-root .chat-hint{display:none!important}

    #autumn-mobile-root .conversation-rail{
      display:none;position:fixed;z-index:132;left:12px;right:12px;
      top:max(72px,calc(env(safe-area-inset-top) + 62px));bottom:max(12px,env(safe-area-inset-bottom));
      padding:15px 12px;border-radius:22px;border:1px solid rgba(255,255,255,.58);
      background:rgba(255,248,243,.97);box-shadow:0 24px 70px rgba(39,24,38,.34);
      overflow:auto;color:#3f3038
    }
    #autumn-mobile-root .conversation-rail.open{display:block}
    #autumn-mobile-root .conversation-item{color:#776a71}
    #autumn-mobile-root .conversation-item.active{color:#3f3038}
    #autumn-mobile-root .mobile-rail-backdrop.open{
      display:block!important;position:fixed;inset:0;z-index:131;background:rgba(43,28,43,.30);backdrop-filter:blur(3px)
    }

    .mobile-panel{
      position:fixed;inset:0;z-index:135;display:none;flex-direction:column;
      padding:max(12px,env(safe-area-inset-top)) 12px max(12px,env(safe-area-inset-bottom));
      background:
        linear-gradient(180deg,rgba(81,48,76,.92),rgba(133,72,86,.92) 48%,rgba(212,127,103,.94)),
        url('/assets/afterglow-home.webp') center/cover
    }
    .mobile-panel.open{display:flex}
    .mobile-panel-head{flex:0 0 auto;display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:9px}
    .mobile-panel-title b{display:block;font-size:16px}.mobile-panel-title span{display:block;margin-top:3px;font-size:9px;color:var(--m-muted)}
    .mobile-panel-tools{display:flex;align-items:center;gap:7px}
    .mobile-panel-close,.mobile-panel-eyes{
      height:38px;border:1px solid var(--m-line);border-radius:13px;background:rgba(255,255,255,.075);color:#fff
    }
    .mobile-panel-close{width:38px;font-size:18px}.mobile-panel-eyes{padding:0 11px;font-size:9px}
    .mobile-panel-body{
      flex:1 1 auto;min-height:0;overflow:auto;border-radius:22px;padding:10px;
      background:rgba(255,255,255,.08);border:1px solid var(--m-line);
      backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)
    }
    #autumn-mobile-root .mobile-panel .section-page{padding:2px!important;max-width:none!important;margin:0!important;min-height:0!important;color:#fff}
    #autumn-mobile-root .mobile-panel .page-head{display:none!important}
    #autumn-mobile-root .mobile-panel .activity-grid,
    #autumn-mobile-root .mobile-panel .device-grid{grid-template-columns:1fr!important;gap:8px!important}
    #autumn-mobile-root .mobile-panel .activity-card,
    #autumn-mobile-root .mobile-panel .device,
    #autumn-mobile-root .mobile-panel .card{
      min-height:0!important;background:rgba(255,255,255,.09)!important;border-color:rgba(255,255,255,.12)!important;
      color:#fff!important;box-shadow:none!important
    }
    #autumn-mobile-root .mobile-panel .activity-meta,
    #autumn-mobile-root .mobile-panel .node-meta,
    #autumn-mobile-root .mobile-panel .status-note,
    #autumn-mobile-root .mobile-panel .kicker,
    #autumn-mobile-root .mobile-panel .autumn-home-sub{color:rgba(255,255,255,.58)!important}
    #autumn-mobile-root .mobile-panel .talk-wrap{max-width:none!important;margin:0!important}
    #autumn-mobile-root .mobile-panel .talk-card{
      min-height:100%;padding:18px 14px!important;background:transparent!important;border:0!important;box-shadow:none!important;color:#fff
    }
    #autumn-mobile-root .mobile-panel .talk-label,
    #autumn-mobile-root .mobile-panel .talk-state,
    #autumn-mobile-root .mobile-panel .talk-note{color:rgba(255,255,255,.64)!important}
    #autumn-mobile-root .mobile-panel .duskline{height:70px!important;margin:8px 0 10px!important}
    #autumn-mobile-root .mobile-panel .voice-button{width:86px!important;height:86px!important}
    #autumn-mobile-root .mobile-panel .recent{margin-top:15px!important}
    #autumn-mobile-root .mobile-panel .recent-card{background:rgba(255,255,255,.08)!important;border-color:rgba(255,255,255,.10)!important}
    #autumn-mobile-root .mobile-panel .recent-text{color:#fff!important}

    #autumn-mobile-root .mobile-panel .eyes-shell{
      max-width:none!important;margin:0!important;display:grid!important;grid-template-columns:1fr!important;gap:8px!important;color:#fff
    }
    #autumn-mobile-root .mobile-panel .eyes-stage,
    #autumn-mobile-root .mobile-panel .eyes-controls{
      background:rgba(255,255,255,.08)!important;border-color:rgba(255,255,255,.11)!important;color:#fff!important;box-shadow:none!important
    }

    .mobile-more-sheet{
      position:fixed;inset:0;z-index:140;display:none;align-items:flex-end;padding:10px;
      background:rgba(43,27,43,.28);backdrop-filter:blur(4px);-webkit-backdrop-filter:blur(4px)
    }
    .mobile-more-sheet.open{display:flex}
    .mobile-more-card{
      width:100%;padding:14px;border-radius:23px;background:rgba(72,45,68,.88);
      border:1px solid rgba(255,255,255,.18);backdrop-filter:blur(22px);-webkit-backdrop-filter:blur(22px);
      box-shadow:0 24px 70px rgba(39,24,38,.28)
    }
    .mobile-more-head{display:flex;align-items:center;justify-content:space-between;margin-bottom:10px}
    .mobile-more-head b{font-size:13px}
    .mobile-more-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:7px}
    .mobile-more-grid button{
      min-height:54px;border:1px solid var(--m-line);border-radius:15px;background:rgba(255,255,255,.075);
      color:#fff;display:flex;align-items:center;gap:9px;padding:10px;text-align:left;font-size:10px
    }
    .mobile-more-grid button svg{width:18px!important;height:18px!important}
    .mobile-more-close{width:32px;height:32px;border:0;border-radius:11px;background:rgba(255,255,255,.08);color:#fff}

    body.mobile-companion-open .files-modal{z-index:150}
    body.mobile-companion-open .files-dialog{max-height:84vh}
  }

  @media(max-width:390px){
    #autumn-mobile-root{padding-left:9px;padding-right:9px}
    .mobile-brand b{font-size:23px}
    .mobile-conversation-hero{padding-left:13px}
    .mobile-talk-primary{padding:0 13px}
    .mobile-quick{padding-left:8px;padding-right:8px}
  }
  `;
  document.head.append(style);
}

function makeButton(className, html, label) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = className;
  button.innerHTML = html;
  if (label) button.setAttribute("aria-label", label);
  return button;
}

function installMobileCompanion() {
  if (!isMobile()) return true;
  if (document.querySelector("#autumn-mobile-root")) return true;

  const app = document.querySelector(".app");
  const legacyLayout = document.querySelector(".app > .layout");
  const connectivity = document.querySelector("#connectivity");
  const chatShell = document.querySelector("#page-chat .chat-shell");
  const conversationRailBackdrop = document.querySelector("#mobile-rail-backdrop");
  const conversationToggle = document.querySelector("#conversation-toggle");
  const chatTitle = document.querySelector("#chat-conversation-title");
  const chatSubtitle = document.querySelector("#chat-conversation-subtitle");
  const talkWrap = document.querySelector("#page-talk .talk-wrap");
  const activityPage = document.querySelector("#page-activity .section-page");
  const devicesPage = document.querySelector("#page-devices .section-page");
  const eyesShell = document.querySelector("#page-eyes .eyes-shell");
  const filesOpenAll = document.querySelector("#files-open-all");

  if (!app || !legacyLayout || !connectivity || !chatShell || !talkWrap || !activityPage || !devicesPage || !eyesShell) return false;

  installStyles();

  const root = document.createElement("main");
  root.id = "autumn-mobile-root";
  root.setAttribute("aria-label", "Autumn Mobile Companion");
  root.innerHTML = `
    <header class="mobile-topbar">
      <div class="mobile-brand"><b>Autumn</b><span>Companion · Afterglow</span></div>
      <div class="mobile-top-actions">
        <button type="button" class="mobile-circle" id="mobile-more" aria-label="更多功能">${ICONS.more}</button>
        <div id="mobile-connectivity-slot"></div>
      </div>
    </header>

    <section class="mobile-conversation-hero mobile-glass">
      <div class="mobile-conversation-copy">
        <button type="button" id="mobile-conversation-open" aria-label="切换 Conversation">
          <b id="mobile-conversation-title">Main</b>
          <span id="mobile-conversation-subtitle">Chat + Talk · companion:main</span>
        </button>
      </div>
      <button type="button" class="mobile-talk-primary" id="mobile-talk-primary" data-page="talk" aria-label="打开 Talk">
        ${ICONS.mic}<span>Talk</span>
      </button>
    </section>

    <section class="mobile-quick-grid" aria-label="常用功能">
      <button type="button" class="mobile-quick" data-mobile-open="activity">${ICONS.activity}<b>Activity</b><span>最近活动</span></button>
      <button type="button" class="mobile-quick" data-mobile-open="devices">${ICONS.devices}<b>Devices</b><span>节点与 Home</span></button>
      <button type="button" class="mobile-quick" data-mobile-open="eyes">${ICONS.eyes}<b>Eyes</b><span>按需查看</span></button>
    </section>

    <section class="mobile-chat-host" id="mobile-chat-host"></section>

    <section class="mobile-panel" id="mobile-panel-talk" data-mobile-panel="talk" aria-hidden="true">
      <header class="mobile-panel-head">
        <div class="mobile-panel-title"><b>Talk</b><span id="mobile-talk-context">当前 Conversation</span></div>
        <div class="mobile-panel-tools">
          <button type="button" class="mobile-panel-eyes" id="mobile-talk-eyes">边聊边看</button>
          <button type="button" class="mobile-panel-close" data-mobile-close="talk" aria-label="关闭 Talk">×</button>
        </div>
      </header>
      <div class="mobile-panel-body" id="mobile-talk-body"></div>
    </section>

    <section class="mobile-panel" id="mobile-panel-activity" data-mobile-panel="activity" aria-hidden="true">
      <header class="mobile-panel-head"><div class="mobile-panel-title"><b>Activity</b><span>任务、文件与审批</span></div><button type="button" class="mobile-panel-close" data-mobile-close="activity">×</button></header>
      <div class="mobile-panel-body" id="mobile-activity-body"></div>
    </section>

    <section class="mobile-panel" id="mobile-panel-devices" data-mobile-panel="devices" aria-hidden="true">
      <header class="mobile-panel-head"><div class="mobile-panel-title"><b>Devices</b><span>Node Registry · Xiaomi Home</span></div><button type="button" class="mobile-panel-close" data-mobile-close="devices">×</button></header>
      <div class="mobile-panel-body" id="mobile-devices-body"></div>
    </section>

    <section class="mobile-panel" id="mobile-panel-eyes" data-mobile-panel="eyes" aria-hidden="true">
      <header class="mobile-panel-head"><div class="mobile-panel-title"><b>Eyes</b><span>按需视觉</span></div><button type="button" class="mobile-panel-close" data-mobile-close="eyes">×</button></header>
      <div class="mobile-panel-body" id="mobile-eyes-body"></div>
    </section>

    <div class="mobile-more-sheet" id="mobile-more-sheet" aria-hidden="true">
      <section class="mobile-more-card">
        <header class="mobile-more-head"><b>更多</b><button type="button" class="mobile-more-close" id="mobile-more-close" aria-label="关闭">×</button></header>
        <div class="mobile-more-grid">
          <button type="button" data-mobile-open="activity">${ICONS.activity}<span>Activity</span></button>
          <button type="button" data-mobile-open="devices">${ICONS.devices}<span>Devices</span></button>
          <button type="button" data-mobile-open="eyes">${ICONS.eyes}<span>Eyes</span></button>
          <button type="button" data-mobile-open="files">${ICONS.files}<span>Files</span></button>
        </div>
      </section>
    </div>
  `;

  app.append(root);
  document.body.classList.add("mobile-companion-open");
  document.documentElement.classList.add("mobile-companion-ready");
  document.documentElement.classList.remove("spatial-boot");
  legacyLayout.setAttribute("aria-hidden", "true");

  root.querySelector("#mobile-connectivity-slot")?.append(connectivity);
  if (conversationRailBackdrop) root.append(conversationRailBackdrop);
  root.querySelector("#mobile-chat-host")?.append(chatShell);
  root.querySelector("#mobile-talk-body")?.append(talkWrap);
  root.querySelector("#mobile-activity-body")?.append(activityPage);
  root.querySelector("#mobile-devices-body")?.append(devicesPage);
  root.querySelector("#mobile-eyes-body")?.append(eyesShell);

  const mobileTitle = root.querySelector("#mobile-conversation-title");
  const mobileSubtitle = root.querySelector("#mobile-conversation-subtitle");
  const mobileTalkContext = root.querySelector("#mobile-talk-context");
  const moreSheet = root.querySelector("#mobile-more-sheet");

  const syncConversation = () => {
    const title = chatTitle?.textContent?.trim() || "Main";
    const subtitle = chatSubtitle?.textContent?.trim() || "Chat + Talk · companion:main";
    if (mobileTitle) mobileTitle.textContent = title;
    if (mobileSubtitle) mobileSubtitle.textContent = subtitle;
    if (mobileTalkContext) mobileTalkContext.textContent = title + " · Voice";
  };
  syncConversation();
  if (chatTitle) new MutationObserver(syncConversation).observe(chatTitle, {subtree: true, characterData: true, childList: true});
  if (chatSubtitle) new MutationObserver(syncConversation).observe(chatSubtitle, {subtree: true, characterData: true, childList: true});

  function closeMore() {
    moreSheet?.classList.remove("open");
    moreSheet?.setAttribute("aria-hidden", "true");
  }

  function stopVoiceIfNeeded() {
    if (globalThis.autumnVoiceRunning?.()) document.querySelector("#stop")?.click();
  }

  function closePanels({keepVoice = false} = {}) {
    root.querySelectorAll(".mobile-panel.open").forEach((panel) => {
      if (panel.dataset.mobilePanel === "talk" && !keepVoice) stopVoiceIfNeeded();
      if (panel.dataset.mobilePanel === "eyes") globalThis.autumnEyesClose?.();
      panel.classList.remove("open");
      panel.setAttribute("aria-hidden", "true");
    });
  }

  function openPanel(name, {keepVoice = false} = {}) {
    closeMore();
    closePanels({keepVoice});
    const panel = root.querySelector(`[data-mobile-panel="${name}"]`);
    if (!panel) return;
    panel.classList.add("open");
    panel.setAttribute("aria-hidden", "false");
    if (name === "activity" || name === "devices") globalThis.autumnRefreshCompanionStatus?.();
    if (name === "eyes") globalThis.autumnEyesRefreshSources?.();
  }

  root.querySelector("#mobile-talk-primary")?.addEventListener("click", () => openPanel("talk"));
  root.querySelector("#mobile-conversation-open")?.addEventListener("click", () => conversationToggle?.click());

  root.querySelectorAll("[data-mobile-open]").forEach((button) => button.addEventListener("click", () => {
    const target = button.dataset.mobileOpen;
    if (target === "files") {
      closeMore();
      filesOpenAll?.click();
      return;
    }
    openPanel(target);
  }));

  root.querySelectorAll("[data-mobile-close]").forEach((button) => button.addEventListener("click", () => {
    const name = button.dataset.mobileClose;
    if (name === "talk") stopVoiceIfNeeded();
    if (name === "eyes") globalThis.autumnEyesClose?.();
    const panel = root.querySelector(`[data-mobile-panel="${name}"]`);
    panel?.classList.remove("open");
    panel?.setAttribute("aria-hidden", "true");
  }));

  root.querySelector("#mobile-talk-eyes")?.addEventListener("click", () => openPanel("eyes", {keepVoice: true}));

  root.querySelector("#mobile-more")?.addEventListener("click", () => {
    moreSheet?.classList.add("open");
    moreSheet?.setAttribute("aria-hidden", "false");
  });
  root.querySelector("#mobile-more-close")?.addEventListener("click", closeMore);
  moreSheet?.addEventListener("click", (event) => { if (event.target === moreSheet) closeMore(); });

  document.addEventListener("keydown", (event) => {
    if (event.key !== "Escape") return;
    if (moreSheet?.classList.contains("open")) closeMore();
    else closePanels();
  });

  globalThis.autumnSpatialOpenTalk = () => openPanel("talk");
  globalThis.autumnSpatialShowEyes = () => openPanel("eyes");
  globalThis.autumnSpatialShowStatus = () => openPanel("devices");
  globalThis.autumnMobileOpenActivity = () => openPanel("activity");

  globalThis.autumnRefreshCompanionStatus?.();

  const media = globalThis.matchMedia?.(MOBILE_QUERY);
  media?.addEventListener?.("change", () => globalThis.location?.reload());

  requestAnimationFrame(() => {
    document.documentElement.classList.remove("spatial-boot");
    document.documentElement.classList.add("mobile-companion-ready");
  });
  return true;
}

function bootMobileCompanion() {
  if (!isMobile()) return;

  let attempts = 0;

  const tryInstall = () => {
    if (installMobileCompanion()) return;

    attempts += 1;

    if (attempts < 60) {
      setTimeout(tryInstall, 50);
      return;
    }

    console.error("Autumn Mobile Companion dependencies did not become ready.");
  };

  tryInstall();
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", bootMobileCompanion, {once: true});
  else queueMicrotask(bootMobileCompanion);
}
