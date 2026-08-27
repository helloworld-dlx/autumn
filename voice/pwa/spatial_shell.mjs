const MAX_DESKTOP_OBJECTS = 3;
const MAX_MOBILE_OBJECTS = 2;

export function nextObjectLayout(activeNames, incoming, { mobile = false } = {}) {
  const current = activeNames.filter((name) => name !== incoming);
  const budget = mobile ? MAX_MOBILE_OBJECTS : MAX_DESKTOP_OBJECTS;
  const visible = [incoming, ...current].slice(0, budget);
  const stacked = current.slice(Math.max(0, budget - 1));
  return {
    hero: visible[0] || null,
    secondary: visible.slice(1),
    stacked,
  };
}

export function shouldShowIdle(activeNames = []) {
  return activeNames.length === 0;
}

export function transientLifecycle(name) {
  return Object.freeze({ name, enter: "visible", retire: "stack", final: "hidden" });
}


export function smartObjectRects(activeNames, { mobile = false } = {}) {
  const names = [...activeNames];
  if (!names.length) return {};
  if (mobile) {
    if (names.length === 1) return { [names[0]]: { left: 2, top: 3, width: 96, height: 76 } };
    return {
      [names[0]]: { left: 2, top: 2, width: 96, height: 57 },
      [names[1]]: { left: 2, top: 62, width: 96, height: 32 },
    };
  }
  if (names.length === 1) return { [names[0]]: { left: 3, top: 3, width: 94, height: 88 } };
  if (names.length === 2) {
    return {
      [names[0]]: { left: 2, top: 3, width: 63, height: 86 },
      [names[1]]: { left: 67, top: 3, width: 31, height: 86 },
    };
  }
  return {
    [names[0]]: { left: 2, top: 3, width: 62, height: 86 },
    [names[1]]: { left: 66, top: 3, width: 32, height: 41 },
    [names[2]]: { left: 66, top: 48, width: 32, height: 41 },
  };
}

export function rectsOverlap(a, b, gap = 8) {
  if (!a || !b) return false;
  return !(
    a.right + gap <= b.left ||
    b.right + gap <= a.left ||
    a.bottom + gap <= b.top ||
    b.bottom + gap <= a.top
  );
}

function installStyles() {
  if (document.querySelector("#autumn-spatial-style")) return;
  const style = document.createElement("style");
  style.id = "autumn-spatial-style";
  style.textContent = `
  html,body{height:100%;overflow:hidden}
  body.spatial-open{background:#8a6277;color:#fff}
  body.spatial-open>.app{height:100vh;height:100dvh;min-height:0;overflow:hidden;background:#9f7080}
  body.spatial-open>.app>.layout{display:none!important}
  body.spatial-open>.app>.mobile-dock{display:none!important}
  body.spatial-open .theme-panel{z-index:160}
  body.spatial-open .files-modal{z-index:170}

  #autumn-spatial-root{
    position:fixed;inset:0;z-index:100;display:grid;grid-template-columns:64px minmax(0,1fr) 344px;
    color:#fffaf6;overflow:hidden;
    background:
      linear-gradient(180deg,rgba(67,36,61,.03),rgba(80,39,62,.10)),
      url('/assets/afterglow-home.webp') center/cover no-repeat;
    --sg:rgba(255,255,255,.095);
    --sg2:rgba(255,255,255,.145);
    --sl:rgba(255,255,255,.18);
    --sl2:rgba(255,255,255,.10);
    --warm:#f3b982;
    --coral:#df8b73;
    --muted-sp:rgba(255,250,246,.66);
    --shadow-sp:0 20px 68px rgba(55,31,50,.18);
  }
  #autumn-spatial-root:before{
    content:"";position:absolute;inset:0;pointer-events:none;
    background:
      linear-gradient(rgba(255,255,255,.034) 1px,transparent 1px),
      linear-gradient(90deg,rgba(255,255,255,.028) 1px,transparent 1px),
      radial-gradient(circle at 70% 8%,rgba(255,241,214,.12),transparent 24%);
    background-size:46px 46px,46px 46px,auto;
    mask-image:linear-gradient(to bottom,rgba(0,0,0,.58),rgba(0,0,0,.10) 82%,transparent);
    opacity:.52;
  }
  .spatial-ambient-plane{
    position:absolute;pointer-events:none;z-index:0;border:1px solid rgba(255,255,255,.10);
    background:linear-gradient(130deg,rgba(255,255,255,.07),rgba(255,255,255,.015) 56%,rgba(246,181,124,.045));
    backdrop-filter:blur(12px) saturate(112%);-webkit-backdrop-filter:blur(12px) saturate(112%);
    box-shadow:inset 0 0 0 1px rgba(255,255,255,.02);opacity:.42
  }
  .spatial-ambient-plane.a{width:29vw;height:12vh;left:-2vw;top:13vh;transform:rotate(-2deg);clip-path:polygon(0 0,100% 5%,97% 100%,2% 94%)}
  .spatial-ambient-plane.b{width:25vw;height:14vh;right:-2vw;top:31vh;transform:rotate(2deg);clip-path:polygon(3% 0,100% 0,97% 95%,0 100%)}

  .spatial-rail{
    position:relative;z-index:4;padding:14px 9px;display:flex;flex-direction:column;align-items:center;gap:5px;
    background:rgba(48,29,48,.17);border-right:1px solid rgba(255,255,255,.08);
    backdrop-filter:blur(18px);-webkit-backdrop-filter:blur(18px)
  }
  .spatial-mark{
    width:38px;height:38px;border-radius:13px;margin:2px 0 21px;position:relative;
    background:linear-gradient(145deg,rgba(81,66,96,.70),rgba(228,144,113,.78));
    border:1px solid rgba(255,255,255,.18);box-shadow:0 9px 25px rgba(52,27,51,.14)
  }
  .spatial-mark:after{content:"";position:absolute;left:8px;right:8px;bottom:9px;height:2px;border-radius:9px;background:linear-gradient(90deg,transparent,#ffe1b5,transparent);box-shadow:0 0 12px rgba(255,222,180,.5)}
  .spatial-action{
    width:46px;height:48px;border:0;border-radius:13px;background:transparent;color:#fff;opacity:.68;font-size:15px;
    display:flex;flex-direction:column;align-items:center;justify-content:center;gap:3px
  }
  .spatial-action .spatial-action-icon{width:17px;height:17px;display:grid;place-items:center}
  .spatial-action .spatial-action-icon svg{width:17px;height:17px;display:block;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
  .spatial-action .spatial-action-label{font-size:6.5px;line-height:1;letter-spacing:.02em;opacity:.78}
  .spatial-action:hover,.spatial-action.active{opacity:1;background:rgba(255,255,255,.09)}
  .spatial-rail-note{margin-top:auto;font-size:7px;line-height:1.5;letter-spacing:.13em;opacity:.44;text-align:center}

  .spatial-main{position:relative;z-index:2;min-width:0;padding:14px 16px;display:flex;flex-direction:column;gap:10px;overflow:hidden}
  .spatial-topbar{display:flex;align-items:center;justify-content:space-between;gap:12px;min-height:40px}
  .spatial-brand{min-width:0}
  .spatial-brand b{font-family:Georgia,"Songti SC",serif;font-size:20px;font-weight:600}
  .spatial-brand small{display:block;margin-top:2px;font-size:9px;letter-spacing:.06em;color:var(--muted-sp)}
  .spatial-top-actions{display:flex;gap:7px;align-items:center;justify-content:flex-end;min-width:0;flex:0 0 auto}
  .spatial-mobile-actions{display:none}
  .spatial-mobile-action{border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.08);color:#fffaf6;border-radius:12px;width:38px;height:38px;display:grid;place-items:center;backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);box-shadow:0 8px 22px rgba(50,28,47,.12);touch-action:manipulation}
  .spatial-mobile-action svg{width:17px;height:17px;display:block;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round}
  .spatial-mobile-talk{width:auto;min-width:60px;padding:0 10px;display:flex;align-items:center;justify-content:center;gap:6px}
  .spatial-mobile-talk span{font-size:9px;letter-spacing:.02em;font-weight:650}
  .spatial-mobile-more{font-size:15px;letter-spacing:2px;padding:0 0 5px}
  .spatial-mobile-menu{position:absolute;right:0;top:46px;z-index:95;display:none;grid-template-columns:repeat(2,minmax(90px,1fr));gap:6px;min-width:196px;max-width:calc(100vw - 24px);padding:8px;border-radius:16px;background:rgba(56,34,55,.78);border:1px solid rgba(255,255,255,.16);backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);box-shadow:var(--shadow-sp)}
  .spatial-mobile-menu.open{display:grid}
  .spatial-mobile-menu button{min-height:38px;border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.08);color:#fffaf6;border-radius:10px;padding:9px 10px;text-align:left;font-size:9px;touch-action:manipulation}
  .spatial-mobile-menu button:hover,.spatial-mobile-menu button:focus-visible{background:rgba(255,255,255,.16);outline:none}
  #autumn-spatial-root .conn,#autumn-spatial-root .icon-btn{
    border:1px solid rgba(255,255,255,.18);background:rgba(255,255,255,.08);color:#fffaf6;
    backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);box-shadow:0 8px 22px rgba(50,28,47,.12)
  }

  .spatial-field{
    flex:1;min-height:0;position:relative;overflow:hidden;border-radius:28px;border:1px solid rgba(255,255,255,.15);
    background:linear-gradient(180deg,rgba(255,255,255,.035),rgba(255,255,255,.014));box-shadow:var(--shadow-sp)
  }
  .spatial-field-head{
    position:absolute;left:16px;right:16px;top:14px;z-index:14;display:flex;align-items:center;justify-content:space-between;gap:10px
  }
  .spatial-context-open{border:0;background:none;color:#fff;text-align:left;padding:0}
  .spatial-context-open b{font-size:11px}.spatial-context-open small{display:block;font-size:8px;color:var(--muted-sp);margin-top:2px}
  .spatial-context-pop{
    position:absolute;left:0;top:44px;width:min(680px,calc(100vw - 120px));z-index:40;display:none;padding:10px;border-radius:20px;
    background:rgba(61,38,61,.44);border:1px solid rgba(255,255,255,.16);
    backdrop-filter:blur(20px);-webkit-backdrop-filter:blur(20px);box-shadow:var(--shadow-sp)
  }
  .spatial-context-pop.open{display:block}
  .spatial-context-pop .conversation-rail{
    display:block!important;position:static!important;inset:auto!important;width:auto!important;max-height:min(68vh,680px)!important;
    background:transparent!important;border:0!important;box-shadow:none!important;border-radius:0!important;color:#fff!important;overflow:auto!important
  }
  .spatial-context-pop .conversation-head{color:#fff}.spatial-context-pop .conversation-item{color:#fff;border-color:rgba(255,255,255,.08)!important}
  .spatial-context-pop .conversation-item:hover,.spatial-context-pop .conversation-item.active{background:rgba(255,255,255,.09)!important}
  .spatial-context-pop .conversation-preview,.spatial-context-pop .rail-note{color:rgba(255,255,255,.56)!important}
  .spatial-context-pop .conversation-new{color:#fff!important;background:rgba(255,255,255,.08)!important}

  .spatial-field-actions{display:flex;gap:6px}
  .spatial-chip-btn{
    border:1px solid rgba(255,255,255,.14);background:rgba(255,255,255,.065);color:#fff;border-radius:999px;
    padding:6px 9px;font-size:8px;backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)
  }
  .spatial-chip-btn:hover{background:rgba(255,255,255,.11)}

  .spatial-canvas{position:absolute;inset:60px 14px 54px;overflow:hidden}
  #spatial-object-layer{position:absolute;inset:0}
  .spatial-idle{position:absolute;inset:0;display:grid;place-items:center;text-align:center;transition:opacity .24s ease}
  .spatial-idle.hidden{opacity:0;pointer-events:none}
  .spatial-idle-glass{width:min(54vw,520px);height:min(27vh,220px);position:relative}
  .spatial-idle-glass:before,.spatial-idle-glass:after{
    content:"";position:absolute;inset:0;border:1px solid rgba(255,255,255,.11);
    background:linear-gradient(135deg,rgba(255,255,255,.07),rgba(255,255,255,.012) 62%,rgba(246,181,124,.035));
    backdrop-filter:blur(16px);-webkit-backdrop-filter:blur(16px)
  }
  .spatial-idle-glass:before{transform:translate(-10px,-5px) rotate(-1deg);clip-path:polygon(0 0,100% 4%,98% 100%,2% 96%)}
  .spatial-idle-glass:after{transform:translate(10px,6px) rotate(1deg);clip-path:polygon(2% 0,98% 0,100% 96%,0 100%)}
  .spatial-idle-copy{position:absolute;inset:0;z-index:2;display:grid;place-items:center;padding:20px}
  .spatial-idle-copy b{font-size:12px;letter-spacing:.08em}.spatial-idle-copy span{display:block;margin-top:7px;font-size:9px;line-height:1.65;color:var(--muted-sp)}

  .spatial-object{
    position:absolute;opacity:1;transition:all .46s cubic-bezier(.2,.8,.2,1),opacity .34s ease;
    background:linear-gradient(145deg,rgba(255,255,255,.105),rgba(255,255,255,.032) 48%,rgba(246,181,124,.04));
    border:1px solid rgba(255,255,255,.18);border-radius:21px;overflow:hidden;
    backdrop-filter:blur(18px) saturate(114%);-webkit-backdrop-filter:blur(18px) saturate(114%);
    box-shadow:inset 0 1px 0 rgba(255,255,255,.14),inset -1px 0 0 rgba(244,179,132,.05),0 18px 58px rgba(50,29,48,.16);color:#fff
  }
  .spatial-object.hidden{opacity:0;transform:translateY(12px) scale(.985);pointer-events:none}
  .spatial-object.hero{left:4%;top:5%;width:66%;height:76%}
  .spatial-object.secondary.one{right:3%;top:8%;width:25%;height:35%}
  .spatial-object.secondary.two{right:7%;bottom:8%;width:29%;height:31%}
  .spatial-object.transient{right:3%;top:4%;width:242px;min-height:132px}
  .spatial-object-head{height:38px;display:flex;align-items:center;justify-content:space-between;gap:8px;padding:0 12px;border-bottom:1px solid rgba(255,255,255,.065);cursor:grab;touch-action:none;user-select:none}
  .spatial-object.dragging{transition:none!important;z-index:45!important;box-shadow:0 26px 72px rgba(50,29,48,.24)}
  .spatial-object.dragging .spatial-object-head{cursor:grabbing}
  .spatial-object-head b{font-size:9px;letter-spacing:.06em}.spatial-object-head span{font-size:7px;color:var(--muted-sp)}
  .spatial-object-actions{display:flex;gap:5px}
  .spatial-object-actions button{border:0;background:rgba(255,255,255,.07);color:#fff;border-radius:8px;width:26px;height:26px}
  .spatial-object-body{height:calc(100% - 38px);min-height:0;overflow:auto;padding:10px}
  @media(min-width:901px){.spatial-object.resizable{resize:both;min-width:260px;min-height:190px;max-width:96%;max-height:92%}}
  #autumn-spatial-root.object-focus-mode .spatial-object.focus-target{left:2.5%!important;right:auto!important;top:2%!important;bottom:auto!important;width:95%!important;height:92%!important;z-index:32;opacity:1!important;transform:none!important}
  #autumn-spatial-root.object-focus-mode .spatial-object.focus-muted{opacity:0!important;transform:scale(.94)!important;pointer-events:none!important}
  .spatial-object-actions button[data-focus].active{background:rgba(255,220,186,.18);color:#ffe0bd}

  .spatial-vision-object .spatial-object-body{padding:9px}
  .spatial-vision-object .eyes-shell{max-width:none;margin:0;display:grid;grid-template-columns:minmax(0,1.2fr) minmax(230px,.8fr);gap:10px;height:100%}
  .spatial-vision-object .eyes-stage,.spatial-vision-object .eyes-controls{
    min-height:0!important;height:100%;padding:12px!important;border-radius:16px!important;
    background:rgba(255,255,255,.07)!important;border:1px solid rgba(255,255,255,.11)!important;
    box-shadow:none!important;color:#fff!important;backdrop-filter:none!important
  }
  .spatial-vision-object .eyes-preview{min-height:220px!important;background:rgba(45,32,46,.30)!important;border:1px solid rgba(255,255,255,.08)}
  .spatial-vision-object .eyes-source-grid button,.spatial-vision-object .eyes-actions button{
    background:rgba(255,255,255,.08)!important;color:#fff!important;border-color:rgba(255,255,255,.12)!important
  }
  .spatial-vision-object .eyes-source-grid button.primary{background:linear-gradient(145deg,rgba(245,201,159,.88),rgba(233,144,115,.90))!important;color:#51363d!important}
  .spatial-vision-object .eyes-question{background:rgba(255,255,255,.08)!important;color:#fff!important;border-color:rgba(255,255,255,.12)!important}
  .spatial-vision-object .eyes-question::placeholder{color:rgba(255,255,255,.46)}
  .spatial-vision-object .eyes-note,.spatial-vision-object .kicker{color:rgba(255,255,255,.57)!important}
  .spatial-vision-object .eyes-result{background:rgba(255,255,255,.075)!important;border-color:rgba(255,255,255,.10)!important;color:#fff!important;white-space:normal!important}
  .spatial-vision-object .eyes-result .markdown,.spatial-vision-object .eyes-result .markdown *{color:inherit}
  .spatial-vision-object #eyes-chat{display:none!important}

  .spatial-files-list .activity-item,.spatial-status-body .node-item{border-color:rgba(255,255,255,.08)!important;color:#fff!important}
  .spatial-files-list .activity-meta,.spatial-status-body .node-meta,.spatial-status-body .status-note{color:rgba(255,255,255,.58)!important}
  .spatial-files-list .file-download,.spatial-files-list .file-hide{color:#fff!important;border-color:rgba(255,255,255,.11)!important;background:rgba(255,255,255,.07)!important}
  .spatial-files-more{display:flex;gap:7px;margin-top:8px}
  .spatial-files-more button{border:1px solid rgba(255,255,255,.12);background:rgba(255,255,255,.07);color:#fff;border-radius:999px;padding:6px 9px;font-size:8px}

  .spatial-edge-stack{position:absolute;left:14px;right:14px;bottom:12px;z-index:15;display:flex;gap:7px;overflow:auto}
  .spatial-stack-pill{
    flex:0 0 auto;display:flex;align-items:center;gap:7px;padding:6px 9px;border-radius:999px;font-size:8px;
    background:rgba(255,255,255,.075);border:1px solid rgba(255,255,255,.13);backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px)
  }
  .spatial-stack-pill button{border:0;background:rgba(255,255,255,.10);color:#fff;border-radius:999px;padding:3px 7px;font-size:7px}

  .spatial-chat-host{position:relative;z-index:5;padding:14px 14px 14px 0;min-width:0;overflow:hidden}
  .spatial-chat-host .chat-shell{display:block!important;height:100%;min-height:0!important;background:transparent!important;border:0!important;box-shadow:none!important;backdrop-filter:none!important;overflow:visible!important}
  .spatial-chat-host .conversation-rail{display:none!important}
  .spatial-chat-host .chat-pane{
    height:100%;min-height:0!important;border-radius:25px!important;overflow:hidden;
    background:linear-gradient(180deg,rgba(255,255,255,.105),rgba(255,255,255,.055))!important;
    border:1px solid rgba(255,255,255,.17)!important;color:#fff!important;
    backdrop-filter:blur(19px) saturate(112%)!important;-webkit-backdrop-filter:blur(19px) saturate(112%)!important;
    box-shadow:0 18px 58px rgba(51,29,49,.15)!important
  }
  .spatial-chat-host .chat-pane-head{background:transparent!important;border-color:rgba(255,255,255,.07)!important;color:#fff!important}
  .spatial-chat-host .chat-pane-title small,.spatial-chat-host .chat-hint,.spatial-chat-host .chat-thinking{color:rgba(255,255,255,.57)!important}
  .spatial-chat-host .chat-context{display:none!important}
  .spatial-chat-host .conversation-toggle{display:none!important}
  .spatial-chat-host .chat-pane-head{position:relative}
  .spatial-chat-host .chat-messages{color:#fff!important}
  .spatial-chat-host .chat-message{background:rgba(255,255,255,.075)!important;border-color:rgba(255,255,255,.11)!important;color:#fff!important;box-shadow:none!important}
  .spatial-chat-host .chat-message.user{background:rgba(224,143,115,.16)!important;border-color:rgba(255,205,174,.12)!important}
  .spatial-chat-host .chat-message .markdown,.spatial-chat-host .chat-message .markdown *{color:inherit}
  .spatial-chat-host .chat-message .markdown a{color:#ffd4b1!important}
  .spatial-chat-host .chat-message .markdown pre,.spatial-chat-host .chat-message .markdown code{background:rgba(40,28,42,.20)!important}
  .spatial-chat-host .chat-bottom{background:transparent!important}
  .spatial-chat-host .chat-composer{background:rgba(255,255,255,.07)!important;border-color:rgba(255,255,255,.11)!important;box-shadow:none!important}
  .spatial-chat-host .chat-composer textarea{color:#fff!important}
  .spatial-chat-host .chat-composer textarea::placeholder{color:rgba(255,255,255,.43)}
  .spatial-chat-host .chat-attach{background:rgba(255,255,255,.08)!important;color:#fff!important}
  .spatial-chat-host .attachment-chip,.spatial-chat-host .message-attachment{background:rgba(255,255,255,.07)!important;border-color:rgba(255,255,255,.10)!important;color:#fff!important}
  .spatial-chat-collapse{
    width:30px;height:30px;border:0;border-radius:9px;background:rgba(255,255,255,.07);color:#fff;margin-left:5px
  }
  #autumn-spatial-root.chat-collapsed{grid-template-columns:64px minmax(0,1fr) 54px}
  #autumn-spatial-root.chat-collapsed .spatial-chat-host{padding-right:8px}
  #autumn-spatial-root.chat-collapsed .spatial-chat-host .chat-pane-head{height:100%;padding:8px!important;display:flex;flex-direction:column;align-items:center!important;justify-content:flex-start!important}
  #autumn-spatial-root.chat-collapsed .spatial-chat-host .chat-head-actions,
  #autumn-spatial-root.chat-collapsed .spatial-chat-host .chat-context,
  #autumn-spatial-root.chat-collapsed .spatial-chat-host .chat-messages,
  #autumn-spatial-root.chat-collapsed .spatial-chat-host .chat-bottom{display:none!important}
  #autumn-spatial-root.chat-collapsed .spatial-chat-collapse{width:38px;height:64px;display:flex!important;flex-direction:column;align-items:center;justify-content:center;gap:5px;transform:none}
  #autumn-spatial-root.chat-collapsed .spatial-chat-collapse .expanded-glyph{display:none}
  #autumn-spatial-root.chat-collapsed .spatial-chat-collapse .collapsed-glyph,
  #autumn-spatial-root.chat-collapsed .spatial-chat-collapse .collapsed-label{display:block}
  .spatial-chat-collapse .collapsed-glyph,.spatial-chat-collapse .collapsed-label{display:none}
  .spatial-chat-collapse .collapsed-label{font-size:7px;letter-spacing:.08em}

  .spatial-talk-overlay{
    position:absolute;left:50%;bottom:18px;z-index:70;display:none;width:min(700px,calc(100% - 36px));
    transform:translateX(-50%);background:transparent;backdrop-filter:none;-webkit-backdrop-filter:none;pointer-events:none
  }
  .spatial-talk-overlay.open{display:block}
  .spatial-talk-card{
    position:relative;width:100%;padding:9px 44px 9px 12px;border-radius:20px;overflow:hidden;pointer-events:auto;
    background:rgba(255,255,255,.12);border:1px solid rgba(255,255,255,.20);
    backdrop-filter:blur(18px) saturate(112%);-webkit-backdrop-filter:blur(18px) saturate(112%);
    box-shadow:0 22px 62px rgba(50,29,48,.18)
  }
  .spatial-talk-close,.spatial-talk-eyes{position:absolute;top:9px;z-index:4;border:0;width:30px;height:30px;border-radius:9px;background:rgba(255,255,255,.08);color:#fff}
  .spatial-talk-close{right:9px}.spatial-talk-eyes{right:43px}
  .spatial-talk-card .talk-wrap{max-width:none;margin:0!important;color:#fff}
  .spatial-talk-card .talk-card{padding:7px 8px!important;background:transparent!important;border:0!important;box-shadow:none!important;color:#fff!important;display:grid!important;grid-template-columns:minmax(105px,1fr) auto minmax(170px,1fr);grid-template-rows:auto auto 24px;column-gap:12px;align-items:center}
  .spatial-talk-card .talk-label{grid-column:1;grid-row:1;color:rgba(255,255,255,.62)!important;text-align:left!important}
  .spatial-talk-card .talk-state{grid-column:1;grid-row:2;color:rgba(255,255,255,.82)!important;margin:3px 0 0!important;text-align:left!important;font-size:12px!important}
  .spatial-talk-card .voice-button{grid-column:2;grid-row:1 / span 2;width:62px!important;height:48px!important;margin:0!important;border-radius:16px!important;font-size:18px!important;box-shadow:0 10px 26px rgba(80,38,55,.20)!important}
  .spatial-talk-card .mode-switch{grid-column:3;grid-row:1 / span 2;margin:0!important;background:rgba(255,255,255,.06)!important;min-width:170px}
  .spatial-talk-card .mode-switch button{padding:8px!important;color:rgba(255,255,255,.62)!important}
  .spatial-talk-card .mode-switch button.selected{color:#51343b!important}
  .spatial-talk-card .duskline{grid-column:1 / -1;grid-row:3;height:22px!important;margin:1px 0 0!important}
  .spatial-talk-card .talk-note,.spatial-talk-card .recent,.spatial-talk-card .debug{display:none!important}
  .spatial-utility-drawer{
    position:absolute;z-index:75;right:16px;top:58px;bottom:16px;width:min(700px,calc(100% - 96px));
    transform:translateX(calc(100% + 24px));opacity:0;pointer-events:none;transition:.28s ease;
    padding:15px;border-radius:23px;background:rgba(255,255,255,.125);border:1px solid rgba(255,255,255,.19);
    backdrop-filter:blur(22px) saturate(112%);-webkit-backdrop-filter:blur(22px) saturate(112%);box-shadow:var(--shadow-sp);overflow:auto;color:#fff
  }
  .spatial-utility-drawer.open{transform:none;opacity:1;pointer-events:auto}
  .spatial-drawer-head{display:flex;align-items:center;justify-content:space-between;gap:10px;margin-bottom:10px}
  .spatial-drawer-head b{font-size:12px}.spatial-drawer-head button{border:0;width:30px;height:30px;border-radius:9px;background:rgba(255,255,255,.08);color:#fff}
  .spatial-utility-drawer .section-page{padding:0!important;max-width:none!important;margin:0!important;color:#fff}
  .spatial-utility-drawer .page-head h1,.spatial-utility-drawer .activity-card h2,.spatial-utility-drawer .device h3,.spatial-utility-drawer .sense b,.spatial-utility-drawer .activity-title,.spatial-utility-drawer .node-title{color:#fff!important}
  .spatial-utility-drawer .page-head p,.spatial-utility-drawer .kicker,.spatial-utility-drawer .activity-meta,.spatial-utility-drawer .device-capabilities,.spatial-utility-drawer .sense span,.spatial-utility-drawer .status-note{color:rgba(255,255,255,.58)!important}
  .spatial-utility-drawer .surface,.spatial-utility-drawer .card,.spatial-utility-drawer .activity-card,.spatial-utility-drawer .device,.spatial-utility-drawer .sense{
    background:rgba(255,255,255,.07)!important;border-color:rgba(255,255,255,.10)!important;box-shadow:none!important;color:#fff!important
  }
  .spatial-utility-drawer .activity-item,.spatial-utility-drawer .node-item{border-color:rgba(255,255,255,.08)!important}
  .spatial-utility-drawer .status-badge,.spatial-utility-drawer .device-state{filter:saturate(.85)}
  .spatial-utility-page{display:none}.spatial-utility-page.active{display:block}

  .spatial-toast{
    position:absolute;z-index:90;left:50%;top:18px;transform:translate(-50%,-14px);opacity:0;pointer-events:none;transition:.22s;
    padding:7px 11px;border-radius:999px;background:rgba(56,34,54,.38);border:1px solid rgba(255,255,255,.13);
    backdrop-filter:blur(14px);-webkit-backdrop-filter:blur(14px);font-size:8px
  }
  .spatial-toast.show{opacity:1;transform:translate(-50%,0)}

  @media(max-width:900px){
    .spatial-context-pop{left:8px;right:8px;top:50px;width:auto!important;max-height:72vh;overflow:auto}
    #autumn-spatial-root,#autumn-spatial-root.chat-collapsed{display:block}
    .spatial-rail{display:none}
    .spatial-mobile-actions{display:flex;position:relative;z-index:95;gap:6px;align-items:center}
    .spatial-main{height:100vh;height:100dvh;padding:max(10px,env(safe-area-inset-top)) 10px max(70px,calc(env(safe-area-inset-bottom) + 60px))}
    .spatial-topbar{padding:0 2px;gap:8px;min-width:0}
    .spatial-brand{min-width:0;flex:1 1 auto}
    .spatial-brand small{display:none}
    .spatial-top-actions{flex:0 0 auto;gap:5px}
    #autumn-spatial-root .conn{width:34px;height:34px;padding:0;font-size:0;display:grid;place-items:center;overflow:hidden}
    #autumn-spatial-root .conn:before{margin-right:0}
    .spatial-field{border-radius:24px}
    .spatial-field-actions{display:none!important}
    .spatial-edge-stack{display:none!important}
    .spatial-canvas{inset:58px 8px 8px}
    .spatial-idle-glass{width:84vw;height:200px}
    .spatial-object.hero,.spatial-object.secondary.one,.spatial-object.secondary.two{
      left:0!important;right:auto!important;top:0!important;bottom:auto!important;
      width:100%!important;height:100%!important
    }
    .spatial-object.transient{display:none!important}
    .spatial-vision-object .eyes-shell{grid-template-columns:1fr!important;height:auto!important}
    .spatial-vision-object .eyes-stage{min-height:245px!important}
    .spatial-vision-object .eyes-controls{height:auto!important}
    .spatial-chat-host{
      position:fixed;left:10px;right:10px;bottom:max(10px,env(safe-area-inset-bottom));z-index:60;height:min(48vh,470px);padding:0;transition:height .28s ease
    }
    #autumn-spatial-root.mobile-chat-collapsed .spatial-chat-host{height:56px}
    #autumn-spatial-root.mobile-chat-collapsed .spatial-chat-host .chat-messages,
    #autumn-spatial-root.mobile-chat-collapsed .spatial-chat-host .chat-bottom{display:none!important}
    #autumn-spatial-root.mobile-chat-collapsed .spatial-chat-host .chat-pane-head{height:56px}
    #autumn-spatial-root.mobile-chat-collapsed .spatial-chat-host .chat-pane{border-radius:18px!important}
    .spatial-chat-host .chat-pane{border-radius:20px!important}
    .spatial-chat-host .chat-shell{height:100%!important}
    .spatial-chat-host .chat-pane{height:100%!important}
    .spatial-chat-host .chat-messages{padding:13px!important}
    .spatial-chat-host .chat-bottom{padding:0 10px 10px!important}
    .spatial-context-pop{position:fixed;left:12px;right:12px;top:max(64px,calc(env(safe-area-inset-top) + 54px));width:auto;max-height:56vh}
    .spatial-talk-overlay{
      position:fixed;left:10px;right:10px;
      top:max(112px,calc(env(safe-area-inset-top) + 102px));bottom:auto;
      width:auto;transform:none
    }
    .spatial-talk-card .talk-card{grid-template-columns:1fr auto!important;grid-template-rows:auto auto 22px!important}
    .spatial-talk-card .mode-switch{grid-column:1 / -1!important;grid-row:3!important;min-width:0!important}
    .spatial-talk-card .duskline{display:none!important}
    .spatial-talk-card .voice-button{grid-column:2!important;grid-row:1 / span 2!important}
    .spatial-talk-card .talk-label,.spatial-talk-card .talk-state{grid-column:1!important}
    .spatial-utility-drawer{
      position:fixed;left:10px;right:10px;
      top:max(104px,calc(env(safe-area-inset-top) + 94px));
      bottom:max(76px,calc(env(safe-area-inset-bottom) + 66px));
      width:auto;transform:translateY(calc(100% + 24px))
    }
    .spatial-utility-drawer.open{transform:none}
  }
  @media(max-width:430px){
    .spatial-brand small{display:none}
    .spatial-brand b{font-size:18px}
    .spatial-mobile-talk{min-width:56px;padding:0 9px}
  }
  `;
  document.head.append(style);
}

function makeButton(label, title, onClick, extra = {}) {
  const button = document.createElement("button");
  button.type = "button";
  button.className = extra.className || "spatial-action";
  button.textContent = label;
  if (title) button.title = title;
  if (extra.page) button.dataset.page = extra.page;
  button.addEventListener("click", onClick);
  return button;
}

const RAIL_ICONS = Object.freeze({
  space: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 12h16M12 4v16"/><path d="M7 7l10 10M17 7L7 17" opacity=".45"/></svg>`,
  talk: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="9" y="3" width="6" height="12" rx="3"/><path d="M6.5 11.5a5.5 5.5 0 0 0 11 0M12 17v4M9 21h6"/></svg>`,
  eyes: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M2.5 12s3.4-5 9.5-5 9.5 5 9.5 5-3.4 5-9.5 5-9.5-5-9.5-5Z"/><circle cx="12" cy="12" r="2.5"/></svg>`,
  files: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3.5 6.5h6l2 2H20.5v9.5a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2Z"/></svg>`,
  devices: `<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="3" y="4" width="18" height="12" rx="2"/><path d="M8 20h8M12 16v4"/></svg>`,
  activity: `<svg viewBox="0 0 24 24" aria-hidden="true"><path d="M3 12h4l2-5 4 10 2-5h6"/></svg>`,
});
function makeRailButton(icon, label, title, onClick, extra = {}) {
  const button = makeButton("", title, onClick, { ...extra, className: extra.className || "spatial-action" });
  const glyph = document.createElement("span");
  glyph.className = "spatial-action-icon";
  glyph.innerHTML = RAIL_ICONS[icon] || "";
  const text = document.createElement("span");
  text.className = "spatial-action-label";
  text.textContent = label;
  button.replaceChildren(glyph, text);
  button.setAttribute("aria-label", title || label);
  return button;
}

function copyNodeContent(source, target) {
  if (!source || !target) return;
  target.replaceChildren(...[...source.childNodes].map((node) => node.cloneNode(true)));
}

function installSpatialShell() {
  // Desktop keeps the full multi-object Spatial experience. Phones use the
  // dedicated Chat-first Mobile Companion instead of a compressed Spatial UI.
  if (globalThis.matchMedia?.("(max-width: 900px)")?.matches) return;
  if (document.querySelector("#autumn-spatial-root")) return;
  const legacyLayout = document.querySelector(".app > .layout");
  const chatShell = document.querySelector("#page-chat .chat-shell");
  const talkWrap = document.querySelector("#page-talk .talk-wrap");
  const eyesShell = document.querySelector("#page-eyes .eyes-shell");
  const conversationRail = document.querySelector("#conversation-rail");
  const railBackdrop = document.querySelector("#mobile-rail-backdrop");
  const connectivity = document.querySelector("#connectivity");
  const themeToggle = document.querySelector("#themeToggle");
  const themePanel = document.querySelector("#themePanel");
  const activityPage = document.querySelector("#page-activity .section-page");
  const devicesPage = document.querySelector("#page-devices .section-page");
  const homeNodes = document.querySelector("#home-nodes");
  const activityFiles = document.querySelector("#activity-files");
  const filesOpenAll = document.querySelector("#files-open-all");

  if (!legacyLayout || !chatShell || !talkWrap || !eyesShell) return;

  installStyles();

  const root = document.createElement("div");
  root.id = "autumn-spatial-root";
  root.innerHTML = `
    <div class="spatial-ambient-plane a"></div><div class="spatial-ambient-plane b"></div>
    <aside class="spatial-rail"><div class="spatial-mark"></div><div id="spatial-rail-actions"></div><div class="spatial-rail-note">ONE<br>AUTUMN</div></aside>
    <main class="spatial-main">
      <header class="spatial-topbar"><div class="spatial-brand"><b>Autumn</b><small>Afterglow Spatial Interface · One Space</small></div><div class="spatial-top-actions" id="spatial-top-actions"><div class="spatial-mobile-actions" id="spatial-mobile-actions"><button type="button" class="spatial-mobile-action spatial-mobile-talk" id="spatial-mobile-talk" aria-label="打开 Talk" title="打开 Talk"></button><button type="button" class="spatial-mobile-action spatial-mobile-more" id="spatial-mobile-more" aria-label="更多功能" aria-controls="spatial-mobile-menu" aria-expanded="false" title="更多功能">•••</button><div class="spatial-mobile-menu" id="spatial-mobile-menu" role="menu"><button type="button" data-mobile-utility="activity" role="menuitem">Activity</button><button type="button" data-mobile-utility="devices" role="menuitem">Devices</button><button type="button" data-mobile-utility="eyes" role="menuitem">Eyes</button><button type="button" data-mobile-utility="files" role="menuitem">Files</button></div></div></div></header>
      <section class="spatial-field">
        <div class="spatial-toast" id="spatial-toast"></div>
        <header class="spatial-field-head">
          <button type="button" class="spatial-context-open" id="spatial-context-open"><b>Context Field</b><small>点击切换 / 管理 Conversation</small></button>
          <div class="spatial-field-actions" id="spatial-field-actions"></div>
        </header>
        <div class="spatial-context-pop" id="spatial-context-pop"></div>
        <div class="spatial-canvas">
          <div class="spatial-idle" id="spatial-idle"><div class="spatial-idle-glass"><div class="spatial-idle-copy"><div><b>AUTUMN · IDLE</b><span>空间默认保持安静。<br>Eyes、Files、设备状态只在需要时出现。</span></div></div></div></div>
          <div id="spatial-object-layer"></div>
        </div>
        <div class="spatial-edge-stack" id="spatial-edge-stack"></div>
      </section>
    </main>
    <aside class="spatial-chat-host" id="spatial-chat-host"></aside>
    <div class="spatial-talk-overlay" id="spatial-talk-overlay"><section class="spatial-talk-card"><button type="button" class="spatial-talk-eyes" id="spatial-talk-eyes" title="边聊边看">◎</button><button type="button" class="spatial-talk-close" id="spatial-talk-close">×</button><div id="spatial-talk-body"></div></section></div>
    <aside class="spatial-utility-drawer" id="spatial-utility-drawer"><div class="spatial-drawer-head"><b id="spatial-drawer-title">Utility</b><button type="button" id="spatial-drawer-close">×</button></div><div id="spatial-utility-activity" class="spatial-utility-page"></div><div id="spatial-utility-devices" class="spatial-utility-page"></div></aside>
  `;

  document.querySelector(".app")?.append(root);
  document.body.classList.add("spatial-open");

  const railActions = root.querySelector("#spatial-rail-actions");
  const topActions = root.querySelector("#spatial-top-actions");
  const fieldActions = root.querySelector("#spatial-field-actions");
  const objectLayer = root.querySelector("#spatial-object-layer");
  const edgeStack = root.querySelector("#spatial-edge-stack");
  const idle = root.querySelector("#spatial-idle");
  const contextPop = root.querySelector("#spatial-context-pop");
  const toast = root.querySelector("#spatial-toast");
  const talkOverlay = root.querySelector("#spatial-talk-overlay");
  const talkBody = root.querySelector("#spatial-talk-body");
  const utilityDrawer = root.querySelector("#spatial-utility-drawer");
  const utilityActivity = root.querySelector("#spatial-utility-activity");
  const utilityDevices = root.querySelector("#spatial-utility-devices");
  const drawerTitle = root.querySelector("#spatial-drawer-title");
  const chatHost = root.querySelector("#spatial-chat-host");

  if (connectivity) topActions.append(connectivity);
  if (themeToggle) topActions.append(themeToggle);
  if (railBackdrop) root.append(railBackdrop);
  chatHost.append(chatShell);
  talkBody.append(talkWrap);
  if (conversationRail) contextPop?.append(conversationRail);
  if (activityPage) utilityActivity.append(activityPage);
  if (devicesPage) utilityDevices.append(devicesPage);

  const chatHead = chatShell.querySelector(".chat-pane-head");
  const chatCollapse = document.createElement("button");
  chatCollapse.type = "button";
  chatCollapse.className = "spatial-chat-collapse";
  chatCollapse.innerHTML = `<span class="expanded-glyph">›</span><span class="collapsed-glyph" aria-hidden="true"><svg viewBox="0 0 24 24" width="18" height="18"><path d="M5 6.5h14a2 2 0 0 1 2 2v7a2 2 0 0 1-2 2h-7l-4.5 3v-3H5a2 2 0 0 1-2-2v-7a2 2 0 0 1 2-2Z" fill="none" stroke="currentColor" stroke-width="1.7" stroke-linejoin="round"/></svg></span><span class="collapsed-label">CHAT</span>`;
  chatCollapse.title = "折叠 Conversation";
  chatHead?.append(chatCollapse);

  const visionObject = document.createElement("section");
  visionObject.className = "spatial-object spatial-vision-object resizable hidden";
  visionObject.dataset.object = "vision";
  visionObject.innerHTML = `<header class="spatial-object-head"><div><b>EYES</b> <span>ON-DEMAND · current Conversation</span></div><div class="spatial-object-actions"><button type="button" data-focus="vision" title="专注放大">⛶</button><button type="button" data-stack="vision" title="收起到 Shelf">−</button><button type="button" data-close="vision" title="关闭并移除">×</button></div></header><div class="spatial-object-body" id="spatial-vision-body"></div>`;
  visionObject.querySelector("#spatial-vision-body").append(eyesShell);
  objectLayer.append(visionObject);

  const filesObject = document.createElement("section");
  filesObject.className = "spatial-object resizable hidden";
  filesObject.dataset.object = "files";
  filesObject.innerHTML = `<header class="spatial-object-head"><div><b>FILES</b> <span>recent returned files</span></div><div class="spatial-object-actions"><button type="button" data-focus="files" title="专注放大">⛶</button><button type="button" data-stack="files" title="收起到 Shelf">−</button><button type="button" data-close="files" title="关闭并移除">×</button></div></header><div class="spatial-object-body"><div class="spatial-files-list" id="spatial-files-list"></div><div class="spatial-files-more"><button type="button" id="spatial-files-refresh">刷新</button><button type="button" id="spatial-files-all">查看全部</button></div></div>`;
  objectLayer.append(filesObject);

  const statusObject = document.createElement("section");
  statusObject.className = "spatial-object transient hidden";
  statusObject.dataset.object = "status";
  statusObject.innerHTML = `<header class="spatial-object-head"><div><b>DEVICES</b> <span>ambient status</span></div><div class="spatial-object-actions"><button type="button" id="spatial-status-details" title="详情">…</button></div></header><div class="spatial-object-body spatial-status-body" id="spatial-status-body"></div>`;
  objectLayer.append(statusObject);

  const objects = {
    vision: { node: visionObject, label: "Eyes" },
    files: { node: filesObject, label: "Files" },
  };
  let active = [];
  let stacked = [];
  let statusTimer = null;
  let statusShelfTimer = null;
  let toastTimer = null;
  let focusedName = null;
  let layoutMode = "auto";

  const isMobile = () => globalThis.matchMedia?.("(max-width: 900px)")?.matches;
  const updateIdle = () => idle.classList.toggle("hidden", active.length > 0 || !statusObject.classList.contains("hidden"));

  function showToast(text) {
    toast.textContent = text;
    toast.classList.add("show");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(() => toast.classList.remove("show"), 1800);
  }

  function renderStack() {
    edgeStack.replaceChildren();
    edgeStack.classList.toggle("has-items", stacked.length > 0);
    for (const name of stacked) {
      const item = objects[name];
      if (!item) continue;
      const pill = document.createElement("div");
      pill.className = "spatial-stack-pill";
      const label = document.createElement("span");
      label.textContent = item.label;
      const bring = document.createElement("button");
      bring.type = "button";
      bring.textContent = "展开";
      bring.title = "带回 Context Field";
      bring.addEventListener("click", () => presentObject(name));
      const close = document.createElement("button");
      close.type = "button";
      close.className = "shelf-close";
      close.textContent = "×";
      close.title = "从 Shelf 移除";
      close.addEventListener("click", () => { stacked = stacked.filter((entry) => entry !== name); renderStack(); });
      pill.append(label, bring, close);
      edgeStack.append(pill);
    }
  }

  function setRect(node, rect) {
    node.style.left = `${rect.left}%`;
    node.style.top = `${rect.top}%`;
    node.style.width = `${rect.width}%`;
    node.style.height = `${rect.height}%`;
    node.style.right = "auto";
    node.style.bottom = "auto";
  }

  function clearManualRect(node) {
    for (const key of ["left", "top", "right", "bottom", "width", "height"]) node.style[key] = "";
  }

  function normalizedActive() {
    const unique = active.filter((name, index) => objects[name] && active.indexOf(name) === index);
    const budget = isMobile() ? MAX_MOBILE_OBJECTS : MAX_DESKTOP_OBJECTS;
    if (unique.length <= budget) return unique;
    const keep = unique.slice(0, budget);
    for (const overflow of unique.slice(budget)) {
      if (!stacked.includes(overflow)) stacked.push(overflow);
    }
    return keep;
  }

  function applyAutoLayout() {
    active = normalizedActive();
    layoutMode = "auto";
    const rects = smartObjectRects(active, { mobile: isMobile() });
    for (const [name, item] of Object.entries(objects)) {
      item.node.classList.remove("hero", "secondary", "one", "two", "manual");
      if (!active.includes(name)) {
        item.node.classList.add("hidden");
        clearManualRect(item.node);
        continue;
      }
      item.node.classList.remove("hidden");
      const index = active.indexOf(name);
      item.node.classList.add(index === 0 ? "hero" : "secondary");
      if (index > 0) item.node.classList.add(index === 1 ? "one" : "two");
      setRect(item.node, rects[name]);
    }
    applyFocusState();
    renderStack();
    updateIdle();
  }

  function applyFocusState() {
    for (const [name, item] of Object.entries(objects)) {
      item.node.classList.toggle("focus-target", focusedName === name);
      item.node.classList.toggle("focus-muted", Boolean(focusedName) && focusedName !== name && active.includes(name));
      item.node.querySelector("[data-focus]")?.classList.toggle("active", focusedName === name);
    }
    root.classList.toggle("object-focus-mode", Boolean(focusedName));
  }

  function applyObjectLayout() {
    if (layoutMode === "auto") {
      applyAutoLayout();
      return;
    }
    for (const [name, item] of Object.entries(objects)) {
      item.node.classList.toggle("hidden", !active.includes(name));
      item.node.classList.toggle("manual", active.includes(name));
    }
    applyFocusState();
    updateIdle();
  }

  function reflowObjects({ announce = true } = {}) {
    focusedName = null;
    applyAutoLayout();
    if (announce) showToast("已按当前窗口重新排布");
  }

  function presentObject(name) {
    if (!objects[name]) return;
    if (isMobile()) {
      for (const current of active) {
        if (current !== name && current === "vision") globalThis.autumnEyesClose?.();
      }
      active = active.filter((current) => current === name);
      stacked = [];
      focusedName = null;
    }
    if (focusedName && focusedName !== name) focusedName = null;
    stacked = stacked.filter((item) => item !== name);
    if (!active.includes(name)) active.push(name);
    const budget = isMobile() ? MAX_MOBILE_OBJECTS : MAX_DESKTOP_OBJECTS;
    while (active.length > budget) {
      const overflow = active.pop();
      if (overflow && !stacked.includes(overflow)) stacked.push(overflow);
    }
    // New objects always trigger a collision-free smart arrangement.
    applyAutoLayout();
    if (isMobile()) root.classList.add("mobile-chat-collapsed");
  }

  function objectRect(node) {
    const canvasRect = objectLayer.getBoundingClientRect();
    const rect = node.getBoundingClientRect();
    return {
      left: rect.left - canvasRect.left,
      top: rect.top - canvasRect.top,
      right: rect.right - canvasRect.left,
      bottom: rect.bottom - canvasRect.top,
      width: rect.width,
      height: rect.height,
    };
  }

  function anyOverlap(name) {
    const current = objects[name]?.node;
    if (!current) return false;
    const a = objectRect(current);
    return active.some((otherName) => {
      if (otherName === name) return false;
      const other = objects[otherName]?.node;
      return other && rectsOverlap(a, objectRect(other), 10);
    });
  }

  function enableDragging(name, node) {
    const handle = node.querySelector(".spatial-object-head");
    if (!handle) return;
    let drag = null;

    handle.addEventListener("pointerdown", (event) => {
      if (isMobile() || focusedName || event.button !== 0 || event.target.closest("button,input,textarea,a,video")) return;
      const canvasRect = objectLayer.getBoundingClientRect();
      const rect = node.getBoundingClientRect();
      drag = {
        pointerId: event.pointerId,
        startX: event.clientX,
        startY: event.clientY,
        left: rect.left - canvasRect.left,
        top: rect.top - canvasRect.top,
        canvasRect,
      };
      layoutMode = "manual";
      node.classList.add("dragging", "manual");
      handle.setPointerCapture?.(event.pointerId);
      event.preventDefault();
    });

    handle.addEventListener("pointermove", (event) => {
      if (!drag || drag.pointerId !== event.pointerId) return;
      const maxLeft = Math.max(0, drag.canvasRect.width - node.offsetWidth);
      const maxTop = Math.max(0, drag.canvasRect.height - node.offsetHeight);
      const left = Math.min(maxLeft, Math.max(0, drag.left + event.clientX - drag.startX));
      const top = Math.min(maxTop, Math.max(0, drag.top + event.clientY - drag.startY));
      node.style.left = `${left}px`;
      node.style.top = `${top}px`;
      node.style.right = "auto";
      node.style.bottom = "auto";
    });

    const finish = (event) => {
      if (!drag || drag.pointerId !== event.pointerId) return;
      handle.releasePointerCapture?.(event.pointerId);
      node.classList.remove("dragging");
      drag = null;
      if (anyOverlap(name)) {
        showToast("检测到窗口重叠，已自动重排");
        reflowObjects({ announce: false });
      }
    };
    handle.addEventListener("pointerup", finish);
    handle.addEventListener("pointercancel", finish);
  }

  function closeObject(name, { stack = false } = {}) {
    if (focusedName === name) focusedName = null;
    active = active.filter((item) => item !== name);
    if (stack && !stacked.includes(name)) stacked.push(name);
    else stacked = stacked.filter((item) => item !== name);
    if (name === "vision") globalThis.autumnEyesClose?.();
    applyAutoLayout();
  }

  function toggleFocus(name) {
    if (!objects[name] || !active.includes(name)) return;
    focusedName = focusedName === name ? null : name;
    applyObjectLayout();
    showToast(focusedName ? `${objects[name].label} 已进入专注视图` : "已恢复桌面布局");
  }

  function refreshFilesSnapshot() {
    globalThis.autumnRefreshCompanionStatus?.();
    setTimeout(() => {
      const target = root.querySelector("#spatial-files-list");
      copyNodeContent(activityFiles, target);
      target?.querySelectorAll(".file-hide,.file-restore").forEach((button) => button.remove());
    }, 120);
  }

  function clearMobileObjects({ keepVision = false } = {}) {
    if (!isMobile()) return;
    if (!keepVision && active.includes("vision")) globalThis.autumnEyesClose?.();
    active = [];
    stacked = [];
    focusedName = null;
    statusObject.classList.add("hidden");
    clearTimeout(statusTimer);
    clearTimeout(statusShelfTimer);
    edgeStack.replaceChildren();
    applyAutoLayout();
  }

  function hideTalkVisual({ stop = true } = {}) {
    if (stop && globalThis.autumnVoiceRunning?.()) document.querySelector("#stop")?.click();
    talkOverlay.classList.remove("open");
  }

  function showFiles() {
    if (isMobile()) {
      hideTalkVisual();
      closeUtility();
      clearMobileObjects();
      root.classList.add("mobile-chat-collapsed");
    }
    refreshFilesSnapshot();
    presentObject("files");
  }

  function showEyes({ keepVoice = false } = {}) {
    if (isMobile()) {
      hideTalkVisual({ stop: !keepVoice });
      closeUtility();
      clearMobileObjects({ keepVision: true });
      root.classList.add("mobile-chat-collapsed");
    }
    globalThis.autumnEyesRefreshSources?.();
    presentObject("vision");
  }

  function showStatus() {
    if (isMobile()) {
      openUtility("devices");
      return;
    }
    globalThis.autumnRefreshCompanionStatus?.();
    clearTimeout(statusTimer);
    clearTimeout(statusShelfTimer);
    edgeStack.querySelector('[data-transient="status"]')?.remove();
    setTimeout(() => copyNodeContent(homeNodes, root.querySelector("#spatial-status-body")), 120);
    statusObject.classList.remove("hidden");
    updateIdle();
    statusTimer = setTimeout(() => {
      statusObject.classList.add("hidden");
      updateIdle();
      const pill = document.createElement("div");
      pill.className = "spatial-stack-pill";
      pill.dataset.transient = "status";
      pill.innerHTML = `<span>Devices · status</span><button type="button">展开</button><button type="button" class="shelf-close">×</button>`;
      const [bring, close] = pill.querySelectorAll("button");
      bring.addEventListener("click", () => { pill.remove(); showStatus(); });
      close.addEventListener("click", () => pill.remove());
      edgeStack.classList.add("has-items");
      edgeStack.prepend(pill);
      statusShelfTimer = setTimeout(() => { pill.classList.add("fading"); setTimeout(() => { pill.remove(); if (!edgeStack.children.length) edgeStack.classList.remove("has-items"); }, 500); }, 18000);
    }, 7000);
  }

  function openTalk({ autostart = false } = {}) {
    closeUtility();
    if (isMobile()) {
      clearMobileObjects();
      root.classList.add("mobile-chat-collapsed");
    }
    talkOverlay.classList.add("open");
    if (autostart && !globalThis.autumnVoiceRunning?.()) document.querySelector("#start")?.click();
  }

  function closeTalk() {
    hideTalkVisual({ stop: true });
  }

  function openUtility(which) {
    if (isMobile()) {
      hideTalkVisual();
      clearMobileObjects();
      root.classList.add("mobile-chat-collapsed");
    }
    utilityActivity.classList.toggle("active", which === "activity");
    utilityDevices.classList.toggle("active", which === "devices");
    drawerTitle.textContent = which === "activity" ? "Activity" : "Devices";
    if (which === "activity" || which === "devices") globalThis.autumnRefreshCompanionStatus?.();
    utilityDrawer.classList.add("open");
  }

  const mobileTalk = root.querySelector("#spatial-mobile-talk");
  const mobileMore = root.querySelector("#spatial-mobile-more");
  const mobileMenu = root.querySelector("#spatial-mobile-menu");
  if (mobileTalk && mobileMore && mobileMenu) {
    mobileTalk.innerHTML = `${RAIL_ICONS.talk}<span>Talk</span>`;
    const closeMobileMenu = () => {
      mobileMenu.classList.remove("open");
      mobileMore.setAttribute("aria-expanded", "false");
    };
    mobileTalk.addEventListener("click", () => { closeMobileMenu(); openTalk(); });
    mobileMore.addEventListener("click", (event) => {
      event.stopPropagation();
      const open = !mobileMenu.classList.contains("open");
      mobileMenu.classList.toggle("open", open);
      mobileMore.setAttribute("aria-expanded", String(open));
    });
    mobileMenu.querySelectorAll("[data-mobile-utility]").forEach((button) => button.addEventListener("click", () => {
      const action = button.dataset.mobileUtility;
      closeMobileMenu();
      if (action === "activity" || action === "devices") openUtility(action);
      else if (action === "eyes") showEyes();
      else if (action === "files") showFiles();
    }));
    document.addEventListener("click", (event) => {
      if (mobileMenu.classList.contains("open") && !mobileMenu.contains(event.target) && event.target !== mobileMore) closeMobileMenu();
    });
    document.addEventListener("keydown", (event) => { if (event.key === "Escape") closeMobileMenu(); });
    globalThis.addEventListener?.("resize", closeMobileMenu, { passive: true });
  }

  function closeUtility() {
    utilityDrawer.classList.remove("open");
  }

  function toggleContextPop(force = null) {
    if (!contextPop) return;
    const open = force === null ? !contextPop.classList.contains("open") : Boolean(force);
    contextPop.classList.toggle("open", open);
  }

  chatCollapse.addEventListener("click", () => {
    toggleContextPop(false);
    if (isMobile()) root.classList.toggle("mobile-chat-collapsed");
    else root.classList.toggle("chat-collapsed");
  });
  document.querySelector("#chat-input")?.addEventListener("focus", () => {
    if (isMobile()) {
      hideTalkVisual();
      closeUtility();
      clearMobileObjects();
      root.classList.remove("mobile-chat-collapsed");
    }
  });

  contextPop?.addEventListener("click", (event) => {
    if (event.target.closest?.(".conversation-item")) toggleContextPop(false);
  });
  root.querySelector("#spatial-context-open")?.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleContextPop();
  });
  document.addEventListener("click", (event) => {
    if (contextPop?.classList.contains("open") && !contextPop.contains(event.target) && !event.target.closest?.("#spatial-context-open")) toggleContextPop(false);
  });

  root.querySelector("#spatial-talk-close").addEventListener("click", closeTalk);
  root.querySelector("#spatial-talk-eyes").addEventListener("click", () => showEyes({ keepVoice: true }));
  root.querySelector("#spatial-drawer-close").addEventListener("click", closeUtility);
  root.querySelector("#spatial-status-details").addEventListener("click", () => openUtility("devices"));
  root.querySelector("#spatial-files-refresh").addEventListener("click", refreshFilesSnapshot);
  root.querySelector("#spatial-files-all").addEventListener("click", () => filesOpenAll?.click());

  root.querySelectorAll("[data-close]").forEach((button) => button.addEventListener("click", () => closeObject(button.dataset.close)));
  root.querySelectorAll("[data-stack]").forEach((button) => button.addEventListener("click", () => closeObject(button.dataset.stack, { stack: true })));
  root.querySelectorAll("[data-focus]").forEach((button) => button.addEventListener("click", () => toggleFocus(button.dataset.focus)));
  Object.entries(objects).forEach(([name, item]) => item.node.addEventListener("dblclick", (event) => { if (!event.target.closest("button,textarea,input,a,video")) toggleFocus(name); }));

  const actions = [
    makeRailButton("space", "空间", "Autumn 空间", () => { closeUtility(); }, { className: "spatial-action active" }),
    makeRailButton("talk", "对话", "Talk / 语音", () => openTalk(), { page: "talk" }),
    makeRailButton("eyes", "视觉", "Eyes / 视觉", showEyes),
    makeRailButton("files", "文件", "Files / 文件", showFiles),
    makeRailButton("devices", "设备", "Devices / 设备", showStatus),
    makeRailButton("activity", "动态", "Activity / 动态", () => openUtility("activity")),
  ];
  actions.forEach((button) => railActions.append(button));

  fieldActions.append(
    makeButton("Eyes", "", showEyes, { className: "spatial-chip-btn" }),
    makeButton("Files", "", showFiles, { className: "spatial-chip-btn" }),
    makeButton("设备状态", "", showStatus, { className: "spatial-chip-btn" }),
    makeButton("重排", "", () => reflowObjects(), { className: "spatial-chip-btn" }),
  );

  for (const [name, item] of Object.entries(objects)) enableDragging(name, item.node);
  globalThis.addEventListener?.("resize", () => {
    if (layoutMode === "auto" && active.length) applyAutoLayout();
  });
  globalThis.addEventListener?.("autumn:spatial-present", (event) => {
    const name = event?.detail?.object;
    if (name === "vision") showEyes();
    else if (name === "files") showFiles();
    else if (name === "status") showStatus();
  });

  if (isMobile()) root.classList.add("mobile-chat-collapsed");

  globalThis.autumnSpatialShowEyes = showEyes;
  globalThis.autumnSpatialShowFiles = showFiles;
  globalThis.autumnSpatialShowStatus = showStatus;
  globalThis.autumnSpatialOpenTalk = openTalk;
  globalThis.autumnSpatialPresentObject = presentObject;
  globalThis.autumnSpatialReflow = reflowObjects;

  if (globalThis.autumnVoiceRunning?.()) openTalk();

  if (themePanel) themePanel.addEventListener("click", () => {});
  if (legacyLayout) legacyLayout.setAttribute("aria-hidden", "true");
  refreshFilesSnapshot();
  updateIdle();
  requestAnimationFrame(() => requestAnimationFrame(() => {
    document.documentElement.classList.remove("spatial-boot");
    document.documentElement.classList.add("spatial-ready");
  }));
}

if (typeof document !== "undefined") {
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", installSpatialShell, { once: true });
  else queueMicrotask(installSpatialShell);
}
