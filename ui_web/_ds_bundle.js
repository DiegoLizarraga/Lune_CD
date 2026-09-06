/* @ds-bundle: {"format":4,"namespace":"LuneCDShibuyaPunkDesignSystem_8598db","components":[{"name":"Avatar","sourcePath":"components/core/Avatar.jsx"},{"name":"Button","sourcePath":"components/core/Button.jsx"},{"name":"Card","sourcePath":"components/core/Card.jsx"},{"name":"ChatBubble","sourcePath":"components/core/ChatBubble.jsx"},{"name":"IconButton","sourcePath":"components/core/IconButton.jsx"},{"name":"Badge","sourcePath":"components/feedback/Badge.jsx"},{"name":"StatusPill","sourcePath":"components/feedback/StatusPill.jsx"},{"name":"Input","sourcePath":"components/forms/Input.jsx"},{"name":"Switch","sourcePath":"components/forms/Switch.jsx"},{"name":"ProviderTab","sourcePath":"components/navigation/ProviderTab.jsx"}],"sourceHashes":{"components/core/Avatar.jsx":"5fe0f865a14a","components/core/Button.jsx":"227f92f461e5","components/core/Card.jsx":"d199de59b3e2","components/core/ChatBubble.jsx":"da3315084906","components/core/IconButton.jsx":"2f66bcdec7ff","components/feedback/Badge.jsx":"eec33463d2b8","components/feedback/StatusPill.jsx":"4b41e6995a15","components/forms/Input.jsx":"1d6fdc76809f","components/forms/Switch.jsx":"bac2e8ceb057","components/navigation/ProviderTab.jsx":"91da56b3f1c0","ui_kits/lune-desktop/app.jsx":"ee5050db8ed8","ui_kits/lune-desktop/chat.jsx":"f01f8347ccc3","ui_kits/lune-desktop/icons.jsx":"44b3f73c69d5","ui_kits/lune-desktop/menu.jsx":"58a8286c222c","ui_kits/lune-desktop/settings.jsx":"5f6080b500b0","ui_kits/lune-desktop/sidebar.jsx":"55ca795f5d6f"},"inlinedExternals":[],"unexposedExports":[]} */

(() => {

const __ds_ns = (window.LuneCDShibuyaPunkDesignSystem_8598db = window.LuneCDShibuyaPunkDesignSystem_8598db || {});

const __ds_scope = {};

(__ds_ns.__errors = __ds_ns.__errors || []);

// components/core/Avatar.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const CSS = `
.lune-avatar{
  position:relative; display:inline-flex; align-items:center; justify-content:center;
  flex:none; overflow:hidden; background:var(--ink-700);
  border:var(--bw) solid var(--border-strong);
  font-family:var(--font-display); font-weight:700; color:var(--text);
  clip-path:var(--clip-tr);
}
.lune-avatar img{ width:100%; height:100%; object-fit:cover; object-position:top center; }
.lune-avatar.sz-sm{ width:30px; height:30px; font-size:12px; }
.lune-avatar.sz-md{ width:38px; height:38px; font-size:14px; }
.lune-avatar.sz-lg{ width:52px; height:52px; font-size:18px; }
.lune-avatar.sz-xl{ width:72px; height:72px; font-size:24px; }
.lune-avatar.ring-cyan{ border-color:var(--cyan-500); box-shadow:var(--glow-cyan-sm); }
.lune-avatar.ring-blue{ border-color:var(--blue-500); }
.lune-avatar.ring-yellow{ border-color:var(--yellow-500); }
.lune-avatar.is-bot{ background:linear-gradient(135deg,var(--blue-700),var(--cyan-700)); }
.lune-avatar-dot{
  position:absolute; right:-2px; bottom:-2px; width:11px; height:11px;
  border:2px solid var(--bg); background:var(--cyan-500);
}
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-avatar-css')) {
  const s = document.createElement('style');
  s.id = 'lune-avatar-css';
  s.textContent = CSS;
  document.head.appendChild(s);
}

/** Clipped avatar — mascot image, initials, or bot mark. */
function Avatar({
  src,
  alt = '',
  initials,
  bot = false,
  size = 'md',
  ring,
  online = false,
  className = '',
  ...rest
}) {
  const cls = ['lune-avatar', `sz-${size}`, ring && `ring-${ring}`, bot && 'is-bot', className].filter(Boolean).join(' ');
  return /*#__PURE__*/React.createElement("span", _extends({
    className: cls
  }, rest), src ? /*#__PURE__*/React.createElement("img", {
    src: src,
    alt: alt
  }) : initials || (bot ? '☾' : '?'), online && /*#__PURE__*/React.createElement("span", {
    className: "lune-avatar-dot"
  }));
}
Object.assign(__ds_scope, { Avatar });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Avatar.jsx", error: String((e && e.message) || e) }); }

// components/core/Button.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
/* Inject component styles once per document. */
const CSS = `
.lune-btn{
  --_fill: var(--cyan-500);
  --_ink: var(--ink-950);
  position:relative; display:inline-flex; align-items:center; justify-content:center;
  gap:8px; border:none; cursor:pointer; user-select:none; white-space:nowrap;
  font-family:var(--font-display); font-weight:700; text-transform:uppercase;
  letter-spacing:.08em; color:var(--_ink); background:var(--_fill);
  clip-path:polygon(0 0, calc(100% - 11px) 0, 100% 11px, 100% 100%, 0 100%);
  transition:transform var(--dur-fast) var(--ease-snap), filter var(--dur-fast), background var(--dur-fast);
}
.lune-btn::after{ /* hard offset shadow drawn as a sibling layer via box-shadow won't follow clip; use translate trick */ }
.lune-btn:hover{ filter:brightness(1.08) saturate(1.05); }
.lune-btn:active{ transform:translate(3px,3px); }
.lune-btn:focus-visible{ outline:2px solid var(--white); outline-offset:3px; }
.lune-btn:disabled{ cursor:not-allowed; opacity:.4; filter:grayscale(.4); transform:none; }

/* size */
.lune-btn.sz-sm{ height:34px; padding:0 14px; font-size:12px; }
.lune-btn.sz-md{ height:42px; padding:0 20px; font-size:13px; }
.lune-btn.sz-lg{ height:52px; padding:0 28px; font-size:15px; letter-spacing:.1em; }
.lune-btn.is-block{ width:100%; }

/* shadow wrapper keeps the hard print-shadow aligned to clip */
.lune-btn-wrap{ display:inline-flex; position:relative; }
.lune-btn-wrap.is-block{ display:flex; width:100%; }
.lune-btn-wrap::before{
  content:""; position:absolute; inset:0; transform:translate(4px,4px); z-index:0;
  background:var(--ink-950);
  clip-path:polygon(0 0, calc(100% - 11px) 0, 100% 11px, 100% 100%, 0 100%);
}
.lune-btn-wrap .lune-btn{ position:relative; z-index:1; }
.lune-btn-wrap.no-shadow::before{ display:none; }

/* variants */
.lune-btn.is-primary{ --_fill:var(--cyan-500); --_ink:var(--ink-950); }
.lune-btn.is-secondary{ --_fill:var(--blue-500); --_ink:var(--white); }
.lune-btn.is-pop{ --_fill:var(--yellow-500); --_ink:var(--ink-950); }
.lune-btn.is-danger{ --_fill:var(--red-500); --_ink:var(--white); }
.lune-btn.is-ghost{
  background:transparent; color:var(--cyan-500);
  box-shadow:inset 0 0 0 1.5px var(--cyan-500);
}
.lune-btn.is-ghost:hover{ background:rgba(0,229,255,.10); color:var(--cyan-300); }
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-button-css')) {
  const s = document.createElement('style');
  s.id = 'lune-button-css';
  s.textContent = CSS;
  document.head.appendChild(s);
}

/**
 * Lune CD primary action control. Angular, clipped corner, hard print-shadow.
 */
function Button({
  children,
  variant = 'primary',
  // primary | secondary | pop | ghost | danger
  size = 'md',
  // sm | md | lg
  block = false,
  shadow = true,
  leading = null,
  trailing = null,
  disabled = false,
  className = '',
  ...rest
}) {
  const noShadow = !shadow || variant === 'ghost';
  return /*#__PURE__*/React.createElement("span", {
    className: `lune-btn-wrap${block ? ' is-block' : ''}${noShadow ? ' no-shadow' : ''}`
  }, /*#__PURE__*/React.createElement("button", _extends({
    className: `lune-btn is-${variant} sz-${size}${block ? ' is-block' : ''} ${className}`,
    disabled: disabled
  }, rest), leading, children, trailing));
}
Object.assign(__ds_scope, { Button });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Button.jsx", error: String((e && e.message) || e) }); }

// components/core/Card.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const CSS = `
.lune-card{
  position:relative; background:var(--surface); color:var(--text);
  border:var(--bw) solid var(--border-strong);
  clip-path:var(--clip-notch);
  padding:var(--space-6);
}
.lune-card.is-flat{ clip-path:none; }
.lune-card.tone-raised{ background:var(--surface-2); }
.lune-card.tone-cyan{ border-color:var(--cyan-700); box-shadow:var(--glow-cyan-sm); }
.lune-card.tone-blue{ border-color:var(--blue-600); }
.lune-card.tone-yellow{ border-color:var(--yellow-600); }
.lune-card.is-grid{ background-image:var(--tex-grid); background-size:var(--tex-grid-size); }
.lune-card.is-scan::after{
  content:""; position:absolute; inset:0; background:var(--tex-scanline);
  pointer-events:none;
}
/* corner accent tick on the cut corner */
.lune-card.is-tick::before{
  content:""; position:absolute; top:0; right:0; width:14px; height:14px;
  background:var(--accent);
  clip-path:polygon(100% 0, 0 0, 100% 100%);
}
.lune-card-eyebrow{
  font:var(--text-overline); letter-spacing:var(--ls-mega);
  text-transform:uppercase; color:var(--accent); margin:0 0 var(--space-3);
  display:flex; align-items:center; gap:8px;
}
.lune-card-title{
  font-family:var(--font-display); font-weight:700; font-size:var(--fs-h3);
  text-transform:uppercase; letter-spacing:.03em; color:var(--text-strong);
  margin:0 0 var(--space-2);
}
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-card-css')) {
  const s = document.createElement('style');
  s.id = 'lune-card-css';
  s.textContent = CSS;
  document.head.appendChild(s);
}

/** Notched surface panel — the base container for Lune CD content. */
function Card({
  children,
  eyebrow,
  title,
  tone = 'default',
  notch = true,
  grid = false,
  scan = false,
  tick = false,
  className = '',
  style,
  ...rest
}) {
  const cls = ['lune-card', !notch && 'is-flat', tone !== 'default' && `tone-${tone}`, grid && 'is-grid', scan && 'is-scan', tick && 'is-tick', className].filter(Boolean).join(' ');
  return /*#__PURE__*/React.createElement("div", _extends({
    className: cls,
    style: style
  }, rest), eyebrow && /*#__PURE__*/React.createElement("p", {
    className: "lune-card-eyebrow"
  }, eyebrow), title && /*#__PURE__*/React.createElement("h3", {
    className: "lune-card-title"
  }, title), children);
}
Object.assign(__ds_scope, { Card });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/Card.jsx", error: String((e && e.message) || e) }); }

// components/core/ChatBubble.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const CSS = `
.lune-msg{ display:flex; gap:11px; padding:6px 4px; max-width:100%; }
.lune-msg.is-user{ flex-direction:row-reverse; }
.lune-msg-body{ max-width:560px; min-width:0; display:flex; flex-direction:column; gap:4px; }
.lune-msg.is-user .lune-msg-body{ align-items:flex-end; }

.lune-bubble{
  position:relative; padding:11px 15px; font-family:var(--font-sans);
  font-size:14px; line-height:1.55; color:var(--text);
  border:var(--bw) solid var(--border-strong); background:var(--ink-800);
  white-space:pre-wrap; word-break:break-word;
}
/* bot bubble: cut top-left, cyan edge */
.lune-msg.is-bot .lune-bubble{
  clip-path:polygon(0 0, 100% 0, 100% 100%, 11px 100%, 0 calc(100% - 11px));
  border-left:var(--bw-bold) solid var(--cyan-700);
  background:var(--ink-750, var(--ink-800));
}
/* user bubble: cut bottom-right, blue fill */
.lune-msg.is-user .lune-bubble{
  clip-path:polygon(0 0, 100% 0, 100% calc(100% - 11px), calc(100% - 11px) 100%, 0 100%);
  background:linear-gradient(135deg, var(--blue-700), var(--blue-600));
  border-color:var(--blue-500); color:var(--white);
}
.lune-msg.prov-local.is-bot .lune-bubble{ border-left-color:var(--cyan-500); }
.lune-msg.prov-cloud.is-bot .lune-bubble{ border-left-color:var(--blue-500); }

.lune-msg-sender{
  font-family:var(--font-mono); font-weight:700; font-size:10px;
  text-transform:uppercase; letter-spacing:.1em; color:var(--cyan-400);
  display:flex; align-items:center; gap:6px; margin-bottom:1px;
}
.lune-msg.prov-cloud .lune-msg-sender{ color:var(--blue-300); }
.lune-msg-time{ font-family:var(--font-mono); font-size:10px; color:var(--text-faint); padding:0 2px; }
.lune-bubble .caret{ color:var(--cyan-400); font-weight:700; }
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-chatbubble-css')) {
  const s = document.createElement('style');
  s.id = 'lune-chatbubble-css';
  s.textContent = CSS;
  document.head.appendChild(s);
}

/** A single chat row — mascot/user avatar + speech bubble. */
function ChatBubble({
  children,
  role = 'bot',
  provider = 'local',
  sender,
  avatar,
  time,
  streaming = false,
  className = '',
  ...rest
}) {
  const isUser = role === 'user';
  const senderLabel = sender ?? (provider === 'cloud' ? 'Lune · Nube' : 'Lune · Local');
  return /*#__PURE__*/React.createElement("div", _extends({
    className: `lune-msg is-${isUser ? 'user' : 'bot'} prov-${provider} ${className}`
  }, rest), avatar, /*#__PURE__*/React.createElement("div", {
    className: "lune-msg-body"
  }, !isUser && /*#__PURE__*/React.createElement("span", {
    className: "lune-msg-sender"
  }, senderLabel), /*#__PURE__*/React.createElement("div", {
    className: "lune-bubble"
  }, children, streaming && /*#__PURE__*/React.createElement("span", {
    className: "caret"
  }, "\u258B")), time && /*#__PURE__*/React.createElement("span", {
    className: "lune-msg-time"
  }, time)));
}
Object.assign(__ds_scope, { ChatBubble });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/ChatBubble.jsx", error: String((e && e.message) || e) }); }

// components/core/IconButton.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const CSS = `
.lune-iconbtn{
  display:inline-flex; align-items:center; justify-content:center;
  flex:none; cursor:pointer; color:var(--text-muted);
  background:transparent; border:var(--bw) solid transparent;
  transition:color var(--dur-fast), background var(--dur-fast), border-color var(--dur-fast), box-shadow var(--dur-fast);
}
.lune-iconbtn svg{ display:block; }
.lune-iconbtn.sz-sm{ width:32px; height:32px; }
.lune-iconbtn.sz-md{ width:40px; height:40px; }
.lune-iconbtn.sz-lg{ width:48px; height:48px; }
.lune-iconbtn.clip{ clip-path:var(--clip-tr); }
.lune-iconbtn:hover{ color:var(--cyan-400); background:var(--ink-700); }
.lune-iconbtn:active{ transform:translateY(1px); }
.lune-iconbtn:focus-visible{ outline:2px solid var(--cyan-500); outline-offset:1px; }
.lune-iconbtn.v-solid{ background:var(--ink-700); border-color:var(--border-strong); color:var(--text); }
.lune-iconbtn.v-solid:hover{ border-color:var(--cyan-700); color:var(--cyan-400); box-shadow:var(--glow-cyan-sm); }
.lune-iconbtn.v-cyan{ background:var(--cyan-500); color:var(--ink-950); }
.lune-iconbtn.v-cyan:hover{ filter:brightness(1.08); color:var(--ink-950); }
.lune-iconbtn.v-danger{ background:var(--red-500); color:var(--white); }
.lune-iconbtn.is-active{ color:var(--cyan-400); background:var(--ink-700); border-color:var(--cyan-700); }
.lune-iconbtn:disabled{ opacity:.4; cursor:not-allowed; }
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-iconbtn-css')) {
  const s = document.createElement('style');
  s.id = 'lune-iconbtn-css';
  s.textContent = CSS;
  document.head.appendChild(s);
}

/** Square icon-only button. Pass an inline SVG / icon node as children. */
function IconButton({
  children,
  label,
  variant = 'ghost',
  size = 'md',
  clip = false,
  active = false,
  className = '',
  ...rest
}) {
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    "aria-label": label,
    title: label,
    className: `lune-iconbtn v-${variant} sz-${size}${clip ? ' clip' : ''}${active ? ' is-active' : ''} ${className}`
  }, rest), children);
}
Object.assign(__ds_scope, { IconButton });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/core/IconButton.jsx", error: String((e && e.message) || e) }); }

// components/feedback/Badge.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const CSS = `
.lune-badge{
  display:inline-flex; align-items:center; gap:5px;
  font-family:var(--font-mono); font-weight:700; font-size:10px;
  text-transform:uppercase; letter-spacing:.1em; line-height:1;
  padding:4px 9px; white-space:nowrap;
  clip-path:var(--clip-tr);
  border:var(--bw) solid transparent;
}
.lune-badge.v-cyan{ background:var(--cyan-500); color:var(--ink-950); }
.lune-badge.v-blue{ background:var(--blue-500); color:var(--white); }
.lune-badge.v-yellow{ background:var(--yellow-500); color:var(--ink-950); }
.lune-badge.v-danger{ background:var(--red-500); color:var(--white); }
.lune-badge.v-ink{ background:var(--ink-700); color:var(--text-muted); border-color:var(--border-strong); }
/* outline variants */
.lune-badge.is-outline{ background:transparent; }
.lune-badge.is-outline.v-cyan{ color:var(--cyan-400); border-color:var(--cyan-700); }
.lune-badge.is-outline.v-blue{ color:var(--blue-300); border-color:var(--blue-600); }
.lune-badge.is-outline.v-yellow{ color:var(--yellow-500); border-color:var(--yellow-600); }
.lune-badge.is-outline.v-danger{ color:var(--red-500); border-color:var(--red-600); }
.lune-badge .jp{ font-family:var(--font-jp); font-weight:900; }
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-badge-css')) {
  const s = document.createElement('style');
  s.id = 'lune-badge-css';
  s.textContent = CSS;
  document.head.appendChild(s);
}

/** Compact tag/label chip. */
function Badge({
  children,
  variant = 'cyan',
  outline = false,
  className = '',
  ...rest
}) {
  return /*#__PURE__*/React.createElement("span", _extends({
    className: `lune-badge v-${variant}${outline ? ' is-outline' : ''} ${className}`
  }, rest), children);
}
Object.assign(__ds_scope, { Badge });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/Badge.jsx", error: String((e && e.message) || e) }); }

// components/feedback/StatusPill.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const CSS = `
.lune-status{
  display:inline-flex; align-items:center; gap:7px;
  font-family:var(--font-mono); font-weight:700; font-size:11px;
  text-transform:uppercase; letter-spacing:.08em; color:var(--text-muted);
  padding:5px 11px 5px 9px; background:var(--ink-800);
  border:var(--bw) solid var(--border-strong); border-radius:var(--radius-pill);
}
.lune-status .led{
  width:9px; height:9px; flex:none; border-radius:50%;
  background:var(--gray-400); position:relative;
}
.lune-status.s-live .led{ background:var(--cyan-500); box-shadow:0 0 0 0 rgba(0,229,255,.6); animation:lune-pulse 1.8s var(--ease-out) infinite; }
.lune-status.s-busy .led{ background:var(--yellow-500); }
.lune-status.s-error .led{ background:var(--red-500); }
.lune-status.s-off .led{ background:var(--gray-500); }
.lune-status.s-live{ color:var(--cyan-300); border-color:var(--cyan-700); }
.lune-status.s-busy{ color:var(--yellow-500); border-color:var(--yellow-600); }
.lune-status.s-error{ color:var(--red-500); border-color:var(--red-600); }
@keyframes lune-pulse{
  0%{ box-shadow:0 0 0 0 rgba(0,229,255,.55); }
  70%{ box-shadow:0 0 0 7px rgba(0,229,255,0); }
  100%{ box-shadow:0 0 0 0 rgba(0,229,255,0); }
}
@media (prefers-reduced-motion: reduce){ .lune-status .led{ animation:none !important; } }
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-status-css')) {
  const s = document.createElement('style');
  s.id = 'lune-status-css';
  s.textContent = CSS;
  document.head.appendChild(s);
}

/** Pill with pulsing LED indicating a live/busy/error/off state. */
function StatusPill({
  status = 'live',
  children,
  className = '',
  ...rest
}) {
  const label = children ?? {
    live: 'Listo',
    busy: 'Procesando',
    error: 'Error',
    off: 'Offline'
  }[status];
  return /*#__PURE__*/React.createElement("span", _extends({
    className: `lune-status s-${status} ${className}`
  }, rest), /*#__PURE__*/React.createElement("span", {
    className: "led"
  }), label);
}
Object.assign(__ds_scope, { StatusPill });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/feedback/StatusPill.jsx", error: String((e && e.message) || e) }); }

// components/forms/Input.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const CSS = `
.lune-field{ display:flex; flex-direction:column; gap:7px; width:100%; }
.lune-field-label{
  font:var(--text-overline); letter-spacing:var(--ls-mega);
  text-transform:uppercase; color:var(--text-dim);
  display:flex; align-items:center; gap:6px;
}
.lune-field-label .req{ color:var(--cyan-500); }
.lune-input-wrap{ position:relative; display:flex; align-items:center; }
.lune-input-wrap .lead{
  position:absolute; left:12px; display:flex; color:var(--text-dim);
  font-family:var(--font-mono); font-size:13px; pointer-events:none;
}
.lune-input, .lune-textarea{
  width:100%; font-family:var(--font-sans); font-size:14px; color:var(--text);
  background:var(--ink-900); border:var(--bw) solid var(--border);
  padding:11px 13px; outline:none;
  clip-path:var(--clip-tr);
  transition:border-color var(--dur-fast), box-shadow var(--dur-fast), background var(--dur-fast);
}
.lune-input{ height:44px; }
.lune-input.has-lead{ padding-left:34px; }
.lune-textarea{ resize:vertical; min-height:88px; line-height:1.5; }
.lune-input::placeholder, .lune-textarea::placeholder{ color:var(--text-faint); }
.lune-input:hover, .lune-textarea:hover{ border-color:var(--border-bright); }
.lune-input:focus, .lune-textarea:focus{
  border-color:var(--cyan-500); background:var(--ink-850);
  box-shadow:var(--glow-cyan-sm);
}
.lune-field.is-error .lune-input,
.lune-field.is-error .lune-textarea{ border-color:var(--red-500); }
.lune-input:disabled, .lune-textarea:disabled{ opacity:.45; cursor:not-allowed; }
.lune-field-hint{ font:var(--text-data); font-size:11px; color:var(--text-faint); }
.lune-field.is-error .lune-field-hint{ color:var(--red-500); }
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-input-css')) {
  const s = document.createElement('style');
  s.id = 'lune-input-css';
  s.textContent = CSS;
  document.head.appendChild(s);
}

/** Text input with optional label, leading glyph, hint and error state. */
function Input({
  label,
  required = false,
  leading = null,
  hint,
  error = false,
  textarea = false,
  className = '',
  id,
  ...rest
}) {
  const fid = id || (label ? `f-${String(label).replace(/\s+/g, '-').toLowerCase()}` : undefined);
  return /*#__PURE__*/React.createElement("div", {
    className: `lune-field${error ? ' is-error' : ''} ${className}`
  }, label && /*#__PURE__*/React.createElement("label", {
    className: "lune-field-label",
    htmlFor: fid
  }, label, required && /*#__PURE__*/React.createElement("span", {
    className: "req"
  }, "*")), textarea ? /*#__PURE__*/React.createElement("textarea", _extends({
    id: fid,
    className: "lune-textarea"
  }, rest)) : /*#__PURE__*/React.createElement("div", {
    className: "lune-input-wrap"
  }, leading && /*#__PURE__*/React.createElement("span", {
    className: "lead"
  }, leading), /*#__PURE__*/React.createElement("input", _extends({
    id: fid,
    className: `lune-input${leading ? ' has-lead' : ''}`
  }, rest))), hint && /*#__PURE__*/React.createElement("span", {
    className: "lune-field-hint"
  }, hint));
}
Object.assign(__ds_scope, { Input });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Input.jsx", error: String((e && e.message) || e) }); }

// components/forms/Switch.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const CSS = `
.lune-switch{ display:inline-flex; align-items:center; gap:11px; cursor:pointer; user-select:none; }
.lune-switch.is-disabled{ opacity:.45; cursor:not-allowed; }
.lune-switch-track{
  position:relative; width:46px; height:24px; flex:none;
  background:var(--ink-700); border:var(--bw) solid var(--border-strong);
  clip-path:polygon(5px 0,100% 0,100% 100%,0 100%,0 5px);
  transition:background var(--dur-fast), border-color var(--dur-fast), box-shadow var(--dur-fast);
}
.lune-switch-thumb{
  position:absolute; top:2px; left:2px; width:17px; height:17px;
  background:var(--gray-300);
  transition:transform var(--dur) var(--ease-snap), background var(--dur-fast);
}
.lune-switch input{ position:absolute; opacity:0; width:0; height:0; }
.lune-switch input:checked + .lune-switch-track{
  background:var(--cyan-700); border-color:var(--cyan-500); box-shadow:var(--glow-cyan-sm);
}
.lune-switch input:checked + .lune-switch-track .lune-switch-thumb{
  transform:translateX(22px); background:var(--cyan-400);
}
.lune-switch input:focus-visible + .lune-switch-track{ outline:2px solid var(--white); outline-offset:2px; }
.lune-switch-label{ font-family:var(--font-sans); font-size:14px; color:var(--text); }
.lune-switch.accent-blue input:checked + .lune-switch-track{ background:var(--blue-700); border-color:var(--blue-500); box-shadow:none; }
.lune-switch.accent-blue input:checked + .lune-switch-track .lune-switch-thumb{ background:var(--blue-400); }
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-switch-css')) {
  const s = document.createElement('style');
  s.id = 'lune-switch-css';
  s.textContent = CSS;
  document.head.appendChild(s);
}

/** Angular toggle switch. */
function Switch({
  checked,
  defaultChecked,
  onChange,
  label,
  disabled = false,
  accent = 'cyan',
  className = '',
  ...rest
}) {
  return /*#__PURE__*/React.createElement("label", {
    className: `lune-switch accent-${accent}${disabled ? ' is-disabled' : ''} ${className}`
  }, /*#__PURE__*/React.createElement("input", _extends({
    type: "checkbox",
    checked: checked,
    defaultChecked: defaultChecked,
    onChange: onChange,
    disabled: disabled
  }, rest)), /*#__PURE__*/React.createElement("span", {
    className: "lune-switch-track"
  }, /*#__PURE__*/React.createElement("span", {
    className: "lune-switch-thumb"
  })), label && /*#__PURE__*/React.createElement("span", {
    className: "lune-switch-label"
  }, label));
}
Object.assign(__ds_scope, { Switch });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/forms/Switch.jsx", error: String((e && e.message) || e) }); }

// components/navigation/ProviderTab.jsx
try { (() => {
function _extends() { return _extends = Object.assign ? Object.assign.bind() : function (n) { for (var e = 1; e < arguments.length; e++) { var t = arguments[e]; for (var r in t) ({}).hasOwnProperty.call(t, r) && (n[r] = t[r]); } return n; }, _extends.apply(null, arguments); }
const CSS = `
.lune-provtab{
  position:relative; display:flex; align-items:center; gap:11px; width:100%;
  padding:10px 12px; cursor:pointer; text-align:left;
  background:transparent; border:var(--bw) solid transparent;
  color:var(--text-muted);
  clip-path:var(--clip-tr);
  transition:background var(--dur-fast), border-color var(--dur-fast), color var(--dur-fast);
}
.lune-provtab:hover{ background:var(--ink-700); color:var(--text); }
.lune-provtab-ic{
  width:34px; height:34px; flex:none; display:flex; align-items:center; justify-content:center;
  background:var(--ink-700); border:var(--bw) solid var(--border-strong);
  clip-path:var(--clip-tr); color:var(--text-muted);
}
.lune-provtab-ic svg{ display:block; }
.lune-provtab-tx{ display:flex; flex-direction:column; gap:1px; min-width:0; }
.lune-provtab-name{ font-family:var(--font-display); font-weight:700; font-size:13px; text-transform:uppercase; letter-spacing:.03em; }
.lune-provtab-desc{ font-family:var(--font-mono); font-size:10px; color:var(--text-faint); text-transform:uppercase; letter-spacing:.05em; }
.lune-provtab-led{ margin-left:auto; width:8px; height:8px; flex:none; border-radius:50%; background:var(--gray-600); }

/* active — cyan (local) */
.lune-provtab.is-active.accent-cyan{ background:rgba(0,229,255,.10); border-color:var(--cyan-700); color:var(--cyan-300); }
.lune-provtab.is-active.accent-cyan .lune-provtab-ic{ background:var(--cyan-500); color:var(--ink-950); border-color:var(--cyan-400); }
.lune-provtab.is-active.accent-cyan .lune-provtab-name{ color:var(--cyan-300); }
.lune-provtab.is-active.accent-cyan .lune-provtab-led{ background:var(--cyan-500); box-shadow:var(--glow-cyan-sm); }
/* active — blue (cloud) */
.lune-provtab.is-active.accent-blue{ background:rgba(30,85,255,.12); border-color:var(--blue-600); color:var(--blue-300); }
.lune-provtab.is-active.accent-blue .lune-provtab-ic{ background:var(--blue-500); color:var(--white); border-color:var(--blue-400); }
.lune-provtab.is-active.accent-blue .lune-provtab-name{ color:var(--blue-300); }
.lune-provtab.is-active.accent-blue .lune-provtab-led{ background:var(--blue-400); }
`;
if (typeof document !== 'undefined' && !document.getElementById('lune-provtab-css')) {
  const s = document.createElement('style');
  s.id = 'lune-provtab-css';
  s.textContent = CSS;
  document.head.appendChild(s);
}

/** Sidebar provider selector row (Nube / Local). */
function ProviderTab({
  icon,
  name,
  desc,
  accent = 'cyan',
  active = false,
  onClick,
  className = '',
  ...rest
}) {
  return /*#__PURE__*/React.createElement("button", _extends({
    type: "button",
    className: `lune-provtab accent-${accent}${active ? ' is-active' : ''} ${className}`,
    onClick: onClick,
    "aria-pressed": active
  }, rest), /*#__PURE__*/React.createElement("span", {
    className: "lune-provtab-ic"
  }, icon), /*#__PURE__*/React.createElement("span", {
    className: "lune-provtab-tx"
  }, /*#__PURE__*/React.createElement("span", {
    className: "lune-provtab-name"
  }, name), /*#__PURE__*/React.createElement("span", {
    className: "lune-provtab-desc"
  }, desc)), /*#__PURE__*/React.createElement("span", {
    className: "lune-provtab-led"
  }));
}
Object.assign(__ds_scope, { ProviderTab });
})(); } catch (e) { __ds_ns.__errors.push({ path: "components/navigation/ProviderTab.jsx", error: String((e && e.message) || e) }); }

// ui_kits/lune-desktop/app.jsx
try { (() => {
/* Lune CD desktop — App shell + state */
const {
  useState,
  useRef,
  useCallback
} = React;
const PROVIDERS = {
  local: {
    name: 'Lune AI · Local',
    desc: 'Modelo offline · sin red',
    Icon: () => /*#__PURE__*/React.createElement(window.IconCpu, null),
    accent: 'cyan'
  },
  cloud: {
    name: 'Lune AI · Nube',
    desc: 'Enrutamiento inteligente',
    Icon: () => /*#__PURE__*/React.createElement(window.IconCloud, null),
    accent: 'blue'
  }
};
let _mid = 0;
const uid = () => `m${++_mid}`;
const NOW = () => new Date().toLocaleTimeString('es-MX', {
  hour: '2-digit',
  minute: '2-digit'
});
function Topbar({
  provider,
  status,
  view,
  onView,
  onMenu
}) {
  const {
    StatusPill,
    IconButton
  } = window.LUNE;
  const p = PROVIDERS[provider];
  return /*#__PURE__*/React.createElement("header", {
    className: "ln-topbar"
  }, /*#__PURE__*/React.createElement("span", {
    className: `ln-topbar-ic ${provider}`
  }, /*#__PURE__*/React.createElement(p.Icon, null)), /*#__PURE__*/React.createElement("div", {
    className: "ln-topbar-tx"
  }, /*#__PURE__*/React.createElement("span", {
    className: "ln-topbar-title"
  }, p.name), /*#__PURE__*/React.createElement("span", {
    className: "ln-topbar-desc"
  }, "\xB7 ", p.desc)), /*#__PURE__*/React.createElement("div", {
    className: "ln-topbar-right"
  }, /*#__PURE__*/React.createElement("button", {
    className: "p3-menubtn",
    onClick: onMenu
  }, /*#__PURE__*/React.createElement("span", null, "Men\xFA")), /*#__PURE__*/React.createElement(IconButton, {
    label: "Ajustes",
    variant: "ghost",
    active: view === 'settings',
    onClick: () => onView(view === 'settings' ? 'chat' : 'settings')
  }, /*#__PURE__*/React.createElement(window.IconGear, null)), /*#__PURE__*/React.createElement(StatusPill, {
    status: status
  })));
}
const SHARDS = [{
  l: '6%',
  s: 46,
  c: 'var(--cyan-500)',
  d: '26s',
  dl: '0s',
  o: .10
}, {
  l: '16%',
  s: 22,
  c: 'var(--blue-400)',
  d: '19s',
  dl: '-6s',
  o: .12
}, {
  l: '28%',
  s: 64,
  c: 'var(--blue-500)',
  d: '34s',
  dl: '-14s',
  o: .07
}, {
  l: '40%',
  s: 16,
  c: 'var(--yellow-500)',
  d: '22s',
  dl: '-3s',
  o: .14
}, {
  l: '52%',
  s: 38,
  c: 'var(--cyan-400)',
  d: '28s',
  dl: '-18s',
  o: .09
}, {
  l: '63%',
  s: 26,
  c: 'var(--blue-300)',
  d: '21s',
  dl: '-9s',
  o: .11
}, {
  l: '74%',
  s: 54,
  c: 'var(--cyan-500)',
  d: '36s',
  dl: '-24s',
  o: .06
}, {
  l: '84%',
  s: 18,
  c: 'var(--yellow-400)',
  d: '24s',
  dl: '-12s',
  o: .12
}, {
  l: '92%',
  s: 32,
  c: 'var(--blue-400)',
  d: '30s',
  dl: '-20s',
  o: .08
}];
function BgShards() {
  return /*#__PURE__*/React.createElement("div", {
    className: "p3-bg",
    "aria-hidden": "true"
  }, SHARDS.map((s, i) => /*#__PURE__*/React.createElement("span", {
    key: i,
    className: "p3-shard",
    style: {
      left: s.l,
      width: s.s,
      height: s.s * 1.4,
      background: s.c,
      '--o': s.o,
      animationDuration: s.d,
      animationDelay: s.dl
    }
  })));
}
function App() {
  const [provider, setProvider] = useState('local');
  const [view, setView] = useState('chat');
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [busy, setBusy] = useState(false);
  const [voiceOn, setVoiceOn] = useState(false);
  const [telegramOn, setTelegramOn] = useState(false);
  const [mascot, setMascot] = useState('normal');
  const [menuOpen, setMenuOpen] = useState(false);
  const [fx, setFx] = useState(() => {
    try {
      return JSON.parse(localStorage.getItem('lune-fx')) || {
        bg: true,
        sweep: true,
        micro: true
      };
    } catch (e) {
      return {
        bg: true,
        sweep: true,
        micro: true
      };
    }
  });
  React.useEffect(() => {
    localStorage.setItem('lune-fx', JSON.stringify(fx));
  }, [fx]);
  const setFxKey = k => e => setFx(f => ({
    ...f,
    [k]: e.target.checked
  }));
  const timers = useRef([]);
  const status = busy ? 'busy' : mascot === 'error' ? 'error' : 'live';
  const clearTimers = () => {
    timers.current.forEach(clearTimeout);
    timers.current = [];
  };
  const send = useCallback(() => {
    const text = input.trim();
    if (!text || busy) return;
    setView('chat');
    setInput('');
    const userMsg = {
      id: uid(),
      role: 'user',
      text,
      time: NOW()
    };
    setMessages(m => [...m, userMsg]);
    setBusy(true);
    setTyping(true);
    setMascot('thinking');
    const reply = window.buildReply(text, provider);
    const t1 = setTimeout(() => {
      setTyping(false);
      if (reply.kind === 'tool') {
        setMessages(m => [...m, {
          id: uid(),
          kind: 'tool',
          tool: reply.tool
        }]);
        setMascot(reply.mascot || 'happy');
        setBusy(false);
        return;
      }
      // typewriter stream
      const full = reply.text;
      const botId = uid();
      setMessages(m => [...m, {
        id: botId,
        role: 'bot',
        provider,
        text: '',
        time: NOW(),
        streaming: true
      }]);
      setMascot('typing');
      let i = 0;
      const step = () => {
        i += Math.max(2, Math.round(full.length / 22));
        const slice = full.slice(0, i);
        setMessages(m => m.map(x => x.id === botId ? {
          ...x,
          text: slice
        } : x));
        if (i < full.length) {
          const t = setTimeout(step, 32);
          timers.current.push(t);
        } else {
          setMessages(m => m.map(x => x.id === botId ? {
            ...x,
            streaming: false
          } : x));
          setMascot(reply.mascot || 'happy');
          setBusy(false);
          const tr = setTimeout(() => setMascot('normal'), 4000);
          timers.current.push(tr);
        }
      };
      step();
    }, 850);
    timers.current.push(t1);
  }, [input, busy, provider]);
  const stop = useCallback(() => {
    clearTimers();
    setTyping(false);
    setBusy(false);
    setMascot('normal');
    setMessages(m => m.map(x => x.streaming ? {
      ...x,
      streaming: false
    } : x));
  }, []);
  const clear = useCallback(() => {
    clearTimers();
    setMessages([]);
    setTyping(false);
    setBusy(false);
    setMascot('normal');
    setView('chat');
  }, []);
  return /*#__PURE__*/React.createElement("div", {
    className: `ln-app lune-backdrop${fx.bg ? '' : ' fx-no-bg'}${fx.sweep ? '' : ' fx-no-sweep'}${fx.micro ? '' : ' fx-no-micro'}`
  }, fx.bg && /*#__PURE__*/React.createElement(BgShards, null), /*#__PURE__*/React.createElement(window.Sidebar, {
    provider: provider,
    onProvider: setProvider,
    mascotState: mascot
  }), /*#__PURE__*/React.createElement("main", {
    className: "ln-main"
  }, /*#__PURE__*/React.createElement(Topbar, {
    provider: provider,
    status: status,
    view: view,
    onView: setView,
    onMenu: () => setMenuOpen(true)
  }), /*#__PURE__*/React.createElement("div", {
    className: "ln-view",
    key: view
  }, view === 'chat' ? /*#__PURE__*/React.createElement(window.ChatStream, {
    messages: messages,
    typing: typing,
    provider: provider
  }) : /*#__PURE__*/React.createElement(window.SettingsPanel, {
    voiceOn: voiceOn,
    onVoice: () => setVoiceOn(v => !v),
    fx: fx,
    setFxKey: setFxKey
  })), view === 'chat' && /*#__PURE__*/React.createElement(window.InputBar, {
    value: input,
    onChange: setInput,
    onSend: send,
    onStop: stop,
    busy: busy
  })), /*#__PURE__*/React.createElement(window.CommandMenu, {
    open: menuOpen,
    onClose: () => setMenuOpen(false),
    items: [{
      label: 'Chat',
      desc: 'Volver a la conversación',
      onClick: () => setView('chat')
    }, {
      label: 'Ajustes',
      desc: 'Configuración general',
      onClick: () => setView('settings')
    }, {
      label: 'Personajes',
      desc: 'Cambia el personaje activo',
      onClick: () => setView('chat')
    }, {
      label: 'Memoria',
      desc: 'Nodos de memoria persistente',
      onClick: () => setView('chat')
    }, {
      label: 'Tools',
      desc: 'Herramientas de escritorio',
      onClick: () => setView('chat')
    }, {
      label: 'Historial',
      desc: 'Conversaciones previas',
      onClick: () => setView('chat')
    }, {
      label: 'Optimizar',
      desc: 'Rendimiento del modelo',
      onClick: () => setView('chat')
    }, {
      label: 'Mascota',
      desc: 'Mascota flotante de escritorio',
      onClick: () => setView('chat')
    }, {
      label: `Voz ${voiceOn ? 'ON' : 'OFF'}`,
      desc: 'edge-tts · es-MX',
      on: voiceOn,
      onClick: () => setVoiceOn(v => !v)
    }, {
      label: 'Telegram',
      desc: 'Bot sincronizado',
      on: telegramOn,
      onClick: () => setTelegramOn(v => !v)
    }, {
      label: 'Limpiar chat',
      desc: 'Borra la conversación actual',
      danger: true,
      onClick: clear
    }]
  }));
}
window.LuneApp = App;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/lune-desktop/app.jsx", error: String((e && e.message) || e) }); }

// ui_kits/lune-desktop/chat.jsx
try { (() => {
/* Lune CD desktop — Chat surface + reply engine */

const NOW = () => new Date().toLocaleTimeString('es-MX', {
  hour: '2-digit',
  minute: '2-digit'
});

/* Fake intent engine — mirrors tools.py (web shortcuts, app launch, system info). */
function buildReply(text, provider) {
  const t = text.toLowerCase();
  const open = t.match(/\b(abre|ve a|abrir)\s+(youtube|netflix|wikipedia|spotify|github|gmail)/);
  if (open) {
    const site = open[2];
    return {
      kind: 'tool',
      tool: {
        ok: true,
        icon: 'ext',
        title: `Abriendo ${site}`,
        detail: `https://${site}.com — lanzado en tu navegador.`
      },
      mascot: 'happy'
    };
  }
  if (/\bbusca(r)?\b/.test(t)) {
    const q = text.replace(/.*busca(r)?\s*(en\s+\w+)?\s*/i, '').trim() || 'tu consulta';
    return {
      kind: 'tool',
      tool: {
        ok: true,
        icon: 'search',
        title: 'Búsqueda lanzada',
        detail: `Resultados para “${q}”.`
      },
      mascot: 'reading'
    };
  }
  if (/\b(lanza|abre el programa|abre la app)\b/.test(t)) {
    return {
      kind: 'tool',
      tool: {
        ok: true,
        icon: 'bolt',
        title: 'App lanzada',
        detail: 'Proceso iniciado localmente (0.1s, sin tokens).'
      },
      mascot: 'happy'
    };
  }
  if (/\b(estado del pc|info del sistema|sistema)\b/.test(t)) {
    return {
      kind: 'tool',
      tool: {
        ok: true,
        icon: 'cpu',
        title: 'Estado del sistema',
        detail: 'CPU 18% · RAM 42% · Disco 61% · Red OK'
      },
      mascot: 'reading'
    };
  }
  if (/\b(recuerda|anota)\b/.test(t)) {
    return {
      text: 'Anotado. Lo guardé en memoria — no se me olvida.',
      mascot: 'happy'
    };
  }
  const canned = ['Listo. Lo tengo. ¿Seguimos?', 'Hecho a mi manera — directa, sin relleno. Dime el siguiente paso.', provider === 'local' ? 'Corriendo en local, cero red, cero costo. Aquí mando yo.' : 'Tirando del modelo en la nube. Respuesta lista.', 'Te dejo lo esencial. Si quieres más profundidad, pídemelo.'];
  return {
    text: canned[Math.floor(Math.random() * canned.length)],
    mascot: 'happy'
  };
}
window.buildReply = buildReply;
function ToolCard({
  tool
}) {
  const {
    Card
  } = window.LUNE;
  const Ic = {
    ext: window.IconExternal,
    search: window.IconSearch,
    bolt: window.IconBolt,
    cpu: window.IconCpu
  }[tool.icon] || window.IconBolt;
  return /*#__PURE__*/React.createElement("div", {
    className: "ln-toolrow"
  }, /*#__PURE__*/React.createElement(Card, {
    tone: "cyan",
    tick: true,
    notch: true,
    className: "ln-toolcard"
  }, /*#__PURE__*/React.createElement("div", {
    className: "ln-tool-head"
  }, /*#__PURE__*/React.createElement("span", {
    className: "ln-tool-ic"
  }, /*#__PURE__*/React.createElement(Ic, {
    width: 18,
    height: 18
  })), /*#__PURE__*/React.createElement("span", {
    className: "ln-tool-title"
  }, tool.title), /*#__PURE__*/React.createElement("span", {
    className: "ln-tool-flag"
  }, "OK \xB7 0.1s")), /*#__PURE__*/React.createElement("p", {
    className: "ln-tool-detail"
  }, tool.detail)));
}
function TypingIndicator({
  provider
}) {
  const {
    Avatar
  } = window.LUNE;
  return /*#__PURE__*/React.createElement("div", {
    className: "ln-typing"
  }, /*#__PURE__*/React.createElement(Avatar, {
    src: "../../assets/mascot/anime/lune-thinking.png",
    size: "md",
    ring: provider === 'cloud' ? 'blue' : 'cyan'
  }), /*#__PURE__*/React.createElement("div", {
    className: "ln-typing-bubble"
  }, /*#__PURE__*/React.createElement("span", {
    className: "ln-dot"
  }), /*#__PURE__*/React.createElement("span", {
    className: "ln-dot"
  }), /*#__PURE__*/React.createElement("span", {
    className: "ln-dot"
  })));
}
function Welcome({
  provider
}) {
  return /*#__PURE__*/React.createElement("div", {
    className: "ln-welcome"
  }, /*#__PURE__*/React.createElement("div", {
    className: "ln-welcome-giant",
    "aria-hidden": "true"
  }, "LUNE"), /*#__PURE__*/React.createElement("div", {
    className: "ln-welcome-mark"
  }, /*#__PURE__*/React.createElement("img", {
    src: "../../assets/mascot/anime/lune-wave.png",
    alt: "Lune"
  })), /*#__PURE__*/React.createElement("div", {
    className: "ln-welcome-jp lune-jp"
  }, "\u30EB\u30CD\u8D77\u52D5"), /*#__PURE__*/React.createElement("h1", {
    className: "ln-welcome-title"
  }, "LUNE EN L\xCDNEA"), /*#__PURE__*/React.createElement("p", {
    className: "ln-welcome-sub"
  }, "Tu asistente de escritorio. Memoria persistente, herramientas al instante,", provider === 'cloud' ? ' modelos en la nube.' : ' 100% local y privada.'), /*#__PURE__*/React.createElement("div", {
    className: "ln-welcome-chips"
  }, /*#__PURE__*/React.createElement("span", {
    className: "ln-chip"
  }, "\"abre youtube\""), /*#__PURE__*/React.createElement("span", {
    className: "ln-chip"
  }, "\"busca lofi de shibuya\""), /*#__PURE__*/React.createElement("span", {
    className: "ln-chip"
  }, "\"estado del pc\""), /*#__PURE__*/React.createElement("span", {
    className: "ln-chip"
  }, "\"recuerda que...\"")));
}
function ChatStream({
  messages,
  typing,
  provider
}) {
  const {
    ChatBubble,
    Avatar
  } = window.LUNE;
  const endRef = React.useRef(null);
  React.useEffect(() => {
    if (endRef.current) endRef.current.scrollTop = endRef.current.scrollHeight;
  }, [messages, typing]);
  if (messages.length === 0) {
    return /*#__PURE__*/React.createElement("div", {
      className: "ln-stream",
      ref: endRef
    }, /*#__PURE__*/React.createElement(Welcome, {
      provider: provider
    }));
  }
  return /*#__PURE__*/React.createElement("div", {
    className: "ln-stream",
    ref: endRef
  }, /*#__PURE__*/React.createElement("div", {
    className: "ln-stream-inner"
  }, messages.map(m => {
    if (m.kind === 'tool') return /*#__PURE__*/React.createElement(ToolCard, {
      key: m.id,
      tool: m.tool
    });
    if (m.role === 'user') return /*#__PURE__*/React.createElement(ChatBubble, {
      key: m.id,
      role: "user",
      time: m.time
    }, m.text);
    return /*#__PURE__*/React.createElement(ChatBubble, {
      key: m.id,
      role: "bot",
      provider: m.provider,
      time: m.time,
      streaming: m.streaming,
      avatar: /*#__PURE__*/React.createElement(Avatar, {
        src: `../../assets/mascot/anime/lune-${m.provider === 'cloud' ? 'happy' : 'composed'}.png`,
        size: "md",
        ring: m.provider === 'cloud' ? 'blue' : 'cyan'
      })
    }, m.text);
  }), typing && /*#__PURE__*/React.createElement(TypingIndicator, {
    provider: provider
  })));
}
function InputBar({
  value,
  onChange,
  onSend,
  onStop,
  busy
}) {
  const {
    IconButton
  } = window.LUNE;
  return /*#__PURE__*/React.createElement("div", {
    className: "ln-inputbar"
  }, /*#__PURE__*/React.createElement(IconButton, {
    label: "Adjuntar",
    variant: "solid"
  }, /*#__PURE__*/React.createElement(window.IconClip, null)), /*#__PURE__*/React.createElement(IconButton, {
    label: "Dictar",
    variant: "solid"
  }, /*#__PURE__*/React.createElement(window.IconMic, null)), /*#__PURE__*/React.createElement("div", {
    className: "ln-input-wrap"
  }, /*#__PURE__*/React.createElement("span", {
    className: "ln-input-glyph"
  }, ">"), /*#__PURE__*/React.createElement("input", {
    className: "ln-input",
    value: value,
    placeholder: "Dime qu\xE9 necesitas\u2026 (Enter para enviar)",
    onChange: e => onChange(e.target.value),
    onKeyDown: e => {
      if (e.key === 'Enter' && !busy) onSend();
    },
    disabled: busy
  })), busy ? /*#__PURE__*/React.createElement(IconButton, {
    label: "Detener",
    variant: "danger",
    clip: true,
    onClick: onStop
  }, /*#__PURE__*/React.createElement(window.IconStop, null)) : /*#__PURE__*/React.createElement(IconButton, {
    label: "Enviar",
    variant: "cyan",
    clip: true,
    onClick: onSend
  }, /*#__PURE__*/React.createElement(window.IconSend, null)));
}
Object.assign(window, {
  ChatStream,
  InputBar
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/lune-desktop/chat.jsx", error: String((e && e.message) || e) }); }

// ui_kits/lune-desktop/icons.jsx
try { (() => {
/* Lune CD — inline SVG icon set (Lucide-style, 2px stroke).
   Exposed on window for the kit scripts. */
const I = (paths, props = {}) => p => React.createElement('svg', {
  width: 20,
  height: 20,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  ...props,
  ...p
}, paths.map((d, i) => React.createElement('path', {
  key: i,
  d
})));
const IconCloud = I(['M17.5 19a4.5 4.5 0 0 0 0-9h-1.26A8 8 0 1 0 4 15.25']);
const IconCpu = p => React.createElement('svg', {
  width: 20,
  height: 20,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  ...p
}, React.createElement('rect', {
  key: 0,
  x: 6,
  y: 6,
  width: 12,
  height: 12,
  rx: 1
}), React.createElement('path', {
  key: 1,
  d: 'M9 2v2M15 2v2M9 20v2M15 20v2M2 9h2M2 15h2M20 9h2M20 15h2'
}));
const IconGear = p => React.createElement('svg', {
  width: 20,
  height: 20,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  ...p
}, React.createElement('circle', {
  key: 0,
  cx: 12,
  cy: 12,
  r: 3
}), React.createElement('path', {
  key: 1,
  d: 'M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z'
}));
const IconTrash = I(['M3 6h18', 'M19 6l-1 14a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2L5 6', 'M8 6V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2', 'M10 11v6', 'M14 11v6']);
const IconBrain = I(['M12 5a3 3 0 1 0-5.99.14 4 4 0 0 0-1.5 7.06A3.5 3.5 0 0 0 8 18.5 3 3 0 0 0 12 19m0-14a3 3 0 1 1 5.99.14 4 4 0 0 1 1.5 7.06A3.5 3.5 0 0 1 16 18.5 3 3 0 0 1 12 19m0-14v14']);
const IconTool = I(['M14.7 6.3a4 4 0 0 1-5.4 5.4L4 17v3h3l5.3-5.3a4 4 0 0 0 5.4-5.4l-2.6 2.6-2-2 2.6-2.6z']);
const IconVolume = I(['M11 5 6 9H2v6h4l5 4z', 'M19 12a7 7 0 0 0-3-5.7', 'M15.5 8.5a3.5 3.5 0 0 1 0 5']);
const IconVolumeOff = I(['M11 5 6 9H2v6h4l5 4z', 'M22 9l-6 6', 'M16 9l6 6']);
const IconSend = p => React.createElement('svg', {
  width: 20,
  height: 20,
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2.4,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  ...p
}, React.createElement('path', {
  key: 0,
  d: 'M12 19V5'
}), React.createElement('path', {
  key: 1,
  d: 'M5 12l7-7 7 7'
}));
const IconStop = p => React.createElement('svg', {
  width: 18,
  height: 18,
  viewBox: '0 0 24 24',
  fill: 'currentColor',
  ...p
}, React.createElement('rect', {
  key: 0,
  x: 6,
  y: 6,
  width: 12,
  height: 12,
  rx: 1
}));
const IconTelegram = I(['m22 3-9.5 9.5', 'M22 3 15 21l-4-8-8-4 19-6z']);
const IconMoon = I(['M21 12.8A9 9 0 1 1 11.2 3 7 7 0 0 0 21 12.8z']);
const IconSearch = I(['M11 19a8 8 0 1 0 0-16 8 8 0 0 0 0 16z', 'm21 21-4.3-4.3']);
const IconBolt = p => React.createElement('svg', {
  width: 20,
  height: 20,
  viewBox: '0 0 24 24',
  fill: 'currentColor',
  ...p
}, React.createElement('path', {
  key: 0,
  d: 'M13 2 4.5 13.5H11l-1 8.5 8.5-11.5H12z'
}));
const IconExternal = I(['M15 3h6v6', 'M10 14 21 3', 'M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6']);
const IconClip = I(['m21.44 11.05-9.19 9.19a6 6 0 0 1-8.49-8.49l8.57-8.57A4 4 0 1 1 18 8.84l-8.59 8.57a2 2 0 0 1-2.83-2.83l8.49-8.48']);
const IconMic = I(['M12 2a3 3 0 0 0-3 3v7a3 3 0 0 0 6 0V5a3 3 0 0 0-3-3z', 'M19 10v2a7 7 0 0 1-14 0v-2', 'M12 19v3']);
const IconUsers = I(['M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2', 'M9 11a4 4 0 1 0 0-8 4 4 0 0 0 0 8z', 'M22 21v-2a4 4 0 0 0-3-3.87', 'M16 3.13a4 4 0 0 1 0 7.75']);
const IconHistory = I(['M3 12a9 9 0 1 0 3-6.7L3 8', 'M3 3v5h5', 'M12 7v5l4 2']);
Object.assign(window, {
  IconCloud,
  IconCpu,
  IconGear,
  IconTrash,
  IconBrain,
  IconTool,
  IconVolume,
  IconVolumeOff,
  IconSend,
  IconStop,
  IconTelegram,
  IconMoon,
  IconSearch,
  IconBolt,
  IconExternal,
  IconClip,
  IconMic,
  IconUsers,
  IconHistory
});
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/lune-desktop/icons.jsx", error: String((e && e.message) || e) }); }

// ui_kits/lune-desktop/menu.jsx
try { (() => {
/* Lune CD — Command Menu (Persona 3 Reload style) */
const CMD_COLORS = ['var(--cyan-300)', 'var(--cyan-400)', 'var(--cyan-500)', 'var(--blue-300)', 'var(--blue-400)', 'var(--paper)', 'var(--cyan-400)', 'var(--blue-300)', 'var(--cyan-500)', 'var(--blue-400)', 'var(--gray-300)'];
function CommandMenu({
  open,
  items,
  onClose
}) {
  const [idx, setIdx] = React.useState(0);
  React.useEffect(() => {
    if (open) setIdx(0);
  }, [open]);
  React.useEffect(() => {
    if (!open) return;
    const onKey = e => {
      if (e.key === 'Escape') onClose();else if (e.key === 'ArrowDown') setIdx(i => (i + 1) % items.length);else if (e.key === 'ArrowUp') setIdx(i => (i - 1 + items.length) % items.length);else if (e.key === 'Enter') {
        items[idx].onClick && items[idx].onClick();
        onClose();
      }
    };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [open, idx, items]);
  if (!open) return null;
  const active = items[idx];
  return /*#__PURE__*/React.createElement("div", {
    className: "p3-overlay",
    onClick: onClose
  }, /*#__PURE__*/React.createElement("div", {
    className: "p3-bigword",
    "aria-hidden": "true"
  }, "\u30B3\u30DE\u30F3\u30C9"), /*#__PURE__*/React.createElement("div", {
    className: "p3-slash-bg",
    "aria-hidden": "true"
  }), /*#__PURE__*/React.createElement("img", {
    className: "p3-mascot",
    src: "../../assets/mascot/anime/lune-base-cut.png",
    alt: ""
  }), /*#__PURE__*/React.createElement("div", {
    className: "p3-word-vert",
    "aria-hidden": "true"
  }, "LUNE"), /*#__PURE__*/React.createElement("nav", {
    className: "p3-list",
    onClick: e => e.stopPropagation()
  }, items.map((it, i) => /*#__PURE__*/React.createElement("button", {
    key: it.label,
    className: `p3-item${i === idx ? ' is-active' : ''}${it.danger ? ' is-danger' : ''}`,
    style: {
      '--i': i,
      '--c': CMD_COLORS[i % CMD_COLORS.length],
      marginLeft: `${i % 6 * 26}px`
    },
    onMouseEnter: () => setIdx(i),
    onClick: () => {
      it.onClick && it.onClick();
      onClose();
    }
  }, /*#__PURE__*/React.createElement("span", {
    className: "p3-item-tx"
  }, it.label), it.on != null && /*#__PURE__*/React.createElement("span", {
    className: `p3-item-led${it.on ? ' on' : ''}`
  })))), /*#__PURE__*/React.createElement("div", {
    className: "p3-cmdinfo",
    onClick: e => e.stopPropagation()
  }, /*#__PURE__*/React.createElement("div", {
    className: "p3-cmdinfo-name"
  }, active.label), /*#__PURE__*/React.createElement("div", {
    className: "p3-cmdinfo-line"
  }, "Command \u2500\u2500\u2500"), /*#__PURE__*/React.createElement("div", {
    className: "p3-cmdinfo-desc"
  }, active.desc), /*#__PURE__*/React.createElement("div", {
    className: "p3-cmdinfo-keys"
  }, /*#__PURE__*/React.createElement("b", null, "\u21B5"), " Confirmar\xA0\xA0", /*#__PURE__*/React.createElement("b", null, "Esc"), " Cerrar")));
}
window.CommandMenu = CommandMenu;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/lune-desktop/menu.jsx", error: String((e && e.message) || e) }); }

// ui_kits/lune-desktop/settings.jsx
try { (() => {
/* Lune CD desktop — Settings panel */
const MOONS = [{
  l: '3%',
  s: 34,
  m: 1,
  d: '11s',
  dl: '0s',
  o: .55
}, {
  l: '9%',
  s: 16,
  m: 0,
  d: '9s',
  dl: '-4s',
  o: .7
}, {
  l: '15%',
  s: 52,
  m: 1,
  d: '14s',
  dl: '-8s',
  o: .35
}, {
  l: '22%',
  s: 20,
  m: 0,
  d: '10s',
  dl: '-2s',
  o: .6
}, {
  l: '28%',
  s: 28,
  m: 1,
  d: '12s',
  dl: '-6s',
  o: .5
}, {
  l: '36%',
  s: 14,
  m: 0,
  d: '8s',
  dl: '-5s',
  o: .65
}, {
  l: '44%',
  s: 40,
  m: 1,
  d: '15s',
  dl: '-11s',
  o: .3
}, {
  l: '52%',
  s: 18,
  m: 0,
  d: '9.5s',
  dl: '-1s',
  o: .7
}, {
  l: '60%',
  s: 24,
  m: 1,
  d: '11s',
  dl: '-7s',
  o: .55
}, {
  l: '68%',
  s: 46,
  m: 0,
  d: '16s',
  dl: '-13s',
  o: .28
}, {
  l: '75%',
  s: 16,
  m: 1,
  d: '8.5s',
  dl: '-3s',
  o: .7
}, {
  l: '82%',
  s: 30,
  m: 0,
  d: '12s',
  dl: '-9s',
  o: .5
}, {
  l: '89%',
  s: 22,
  m: 1,
  d: '10s',
  dl: '-5.5s',
  o: .6
}, {
  l: '95%',
  s: 38,
  m: 0,
  d: '14s',
  dl: '-10s',
  o: .35
}];
const FIXED = [{
  t: '-3%',
  l: '-2%',
  s: 74,
  m: 1,
  r: -14
}, {
  t: '2%',
  l: '6%',
  s: 40,
  m: 0,
  r: 20
}, {
  t: '9%',
  l: '1%',
  s: 52,
  m: 0,
  r: -30
}, {
  t: '15%',
  l: '-3%',
  s: 88,
  m: 1,
  r: 38
}, {
  t: '23%',
  l: '4%',
  s: 30,
  m: 0,
  r: 10
}, {
  t: '-4%',
  l: '88%',
  s: 80,
  m: 1,
  r: 22
}, {
  t: '4%',
  l: '94%',
  s: 44,
  m: 0,
  r: -18
}, {
  t: '12%',
  l: '89%',
  s: 58,
  m: 1,
  r: -40
}, {
  t: '20%',
  l: '96%',
  s: 34,
  m: 0,
  r: 30
}, {
  t: '29%',
  l: '92%',
  s: 48,
  m: 1,
  r: 12
}];
function MoonField() {
  return /*#__PURE__*/React.createElement("div", {
    className: "p5-moonfield",
    "aria-hidden": "true"
  }, /*#__PURE__*/React.createElement("span", {
    className: "p5-streak",
    style: {
      top: '26%',
      left: '-10%',
      animationDelay: '0s'
    }
  }), /*#__PURE__*/React.createElement("span", {
    className: "p5-streak",
    style: {
      top: '58%',
      left: '-20%',
      animationDelay: '-5s'
    }
  }), FIXED.map((f, i) => /*#__PURE__*/React.createElement("span", {
    key: 'f' + i,
    className: (f.m ? 'p5-moon' : 'p5-star') + ' p5-fix',
    style: {
      top: f.t,
      left: f.l,
      width: f.s,
      height: f.s,
      '--r': `${f.r}deg`,
      animationDelay: `${-i * .7}s`
    }
  })), MOONS.map((m, i) => /*#__PURE__*/React.createElement("span", {
    key: i,
    className: m.m ? 'p5-moon' : 'p5-star',
    style: {
      left: m.l,
      width: m.s,
      height: m.s,
      '--o': m.o,
      animationDuration: m.d,
      animationDelay: m.dl
    }
  })), /*#__PURE__*/React.createElement("div", {
    className: "p5-horizon"
  }), /*#__PURE__*/React.createElement("div", {
    className: "p5-lune-sil"
  }, /*#__PURE__*/React.createElement("div", {
    className: "p5-bubble"
  }, "\xBFQu\xE9 ajustamos hoy?"), /*#__PURE__*/React.createElement("img", {
    src: "../../assets/mascot/anime/lune-base-cut.png",
    alt: ""
  })));
}
function SettingsPanel({
  voiceOn,
  onVoice,
  fx = {
    bg: true,
    sweep: true,
    micro: true
  },
  setFxKey = () => () => {}
}) {
  const {
    Card,
    Input,
    Switch,
    Button,
    Badge
  } = window.LUNE;
  return /*#__PURE__*/React.createElement("div", {
    className: "ln-settings"
  }, fx.bg && /*#__PURE__*/React.createElement(MoonField, null), /*#__PURE__*/React.createElement("div", {
    className: "ln-settings-inner"
  }, /*#__PURE__*/React.createElement("header", {
    className: "ln-settings-head"
  }, /*#__PURE__*/React.createElement("div", {
    className: "lune-overline"
  }, "// Panel de Control"), /*#__PURE__*/React.createElement("h2", {
    className: "ln-settings-title"
  }, /*#__PURE__*/React.createElement("span", null, "CONFIGURACI\xD3N GENERAL"))), /*#__PURE__*/React.createElement(Card, {
    eyebrow: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(window.IconCloud, {
      width: 13,
      height: 13
    }), " Red Neuronal"),
    title: "OpenRouter",
    tone: "cyan",
    tick: true
  }, /*#__PURE__*/React.createElement("div", {
    className: "ln-settings-grid"
  }, /*#__PURE__*/React.createElement(Input, {
    label: "API Key de OpenRouter",
    type: "password",
    defaultValue: "sk-or-v1-9f2a8c4e1b7d",
    hint: "Se guarda localmente en datos.json"
  }), /*#__PURE__*/React.createElement(Input, {
    label: "Modelo autom\xE1tico",
    defaultValue: "openrouter/auto"
  }))), /*#__PURE__*/React.createElement(Card, {
    eyebrow: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(window.IconTelegram, {
      width: 13,
      height: 13
    }), " Integraci\xF3n"),
    title: "Telegram",
    tone: "blue"
  }, /*#__PURE__*/React.createElement(Input, {
    label: "Token del Bot",
    type: "password",
    defaultValue: "7654321:AAH-bot-token",
    hint: "@BotFather \u2192 /newbot"
  })), /*#__PURE__*/React.createElement(Card, {
    eyebrow: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(window.IconBrain, {
      width: 13,
      height: 13
    }), " Comportamiento"),
    title: "Personalidad"
  }, /*#__PURE__*/React.createElement("div", {
    className: "ln-settings-grid"
  }, /*#__PURE__*/React.createElement(Input, {
    label: "Nombre del asistente",
    defaultValue: "Lune"
  }), /*#__PURE__*/React.createElement("div", null)), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 14
    }
  }), /*#__PURE__*/React.createElement(Input, {
    label: "System Prompt",
    textarea: true,
    rows: 3,
    defaultValue: "Eres Lune. Directa, con personalidad y filo. Experta en escribir, investigar y automatizar. Sin relleno, sin emoji. Responde claro y en español."
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 14
    }
  }), /*#__PURE__*/React.createElement(Input, {
    label: "Mensaje de bienvenida",
    defaultValue: "Lune en l\xEDnea. Dime qu\xE9 necesitas."
  }), /*#__PURE__*/React.createElement("div", {
    style: {
      height: 18
    }
  }), /*#__PURE__*/React.createElement("div", {
    className: "ln-toggle-row"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "Voz (edge-tts \xB7 es-MX)",
    checked: voiceOn,
    onChange: onVoice
  }), /*#__PURE__*/React.createElement(Switch, {
    label: "Memoria persistente",
    defaultChecked: true,
    accent: "blue"
  }), /*#__PURE__*/React.createElement(Switch, {
    label: "Herramientas de escritorio",
    defaultChecked: true
  }))), /*#__PURE__*/React.createElement(Card, {
    eyebrow: /*#__PURE__*/React.createElement(React.Fragment, null, /*#__PURE__*/React.createElement(window.IconBolt, {
      width: 13,
      height: 13
    }), " Rendimiento"),
    title: "Efectos visuales",
    tone: "yellow"
  }, /*#__PURE__*/React.createElement("p", {
    style: {
      margin: '0 0 14px',
      font: 'var(--text-data)',
      fontSize: 12,
      color: 'var(--text-dim)'
    }
  }, "Desactiva efectos para consumir menos recursos en equipos modestos."), /*#__PURE__*/React.createElement("div", {
    className: "ln-toggle-row"
  }, /*#__PURE__*/React.createElement(Switch, {
    label: "Fondo animado (fragmentos y grid)",
    checked: fx.bg,
    onChange: setFxKey('bg')
  }), /*#__PURE__*/React.createElement(Switch, {
    label: "Barrido al cambiar de vista",
    checked: fx.sweep,
    onChange: setFxKey('sweep'),
    accent: "blue"
  }), /*#__PURE__*/React.createElement(Switch, {
    label: "Micro-animaciones (burbujas, hover)",
    checked: fx.micro,
    onChange: setFxKey('micro')
  }))), /*#__PURE__*/React.createElement("div", {
    className: "ln-settings-foot"
  }, /*#__PURE__*/React.createElement(Badge, {
    variant: "ink",
    outline: true
  }, "datos.json"), /*#__PURE__*/React.createElement(Button, {
    variant: "primary",
    size: "lg"
  }, "Guardar configuraci\xF3n"))));
}
window.SettingsPanel = SettingsPanel;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/lune-desktop/settings.jsx", error: String((e && e.message) || e) }); }

// ui_kits/lune-desktop/sidebar.jsx
try { (() => {
/* Lune CD desktop — Sidebar (v9.0) */
const MASCOT = {
  normal: '../../assets/mascot/anime/lune-composed.png',
  happy: '../../assets/mascot/anime/lune-happy.png',
  reading: '../../assets/mascot/anime/lune-thinking.png',
  thinking: '../../assets/mascot/anime/lune-thinking.png',
  typing: '../../assets/mascot/anime/lune-composed.png',
  error: '../../assets/mascot/anime/lune-nervous.png'
};
function Sidebar({
  provider,
  onProvider,
  mascotState
}) {
  const {
    ProviderTab
  } = window.LUNE;
  return /*#__PURE__*/React.createElement("aside", {
    className: "ln-sidebar"
  }, /*#__PURE__*/React.createElement("div", {
    className: "ln-brand"
  }, /*#__PURE__*/React.createElement("div", {
    className: "ln-brand-mark lune-jp"
  }, "\u6708"), /*#__PURE__*/React.createElement("div", {
    className: "ln-brand-tx"
  }, /*#__PURE__*/React.createElement("div", {
    className: "ln-brand-name"
  }, "LUNE ", /*#__PURE__*/React.createElement("span", null, "CD")), /*#__PURE__*/React.createElement("div", {
    className: "ln-brand-sub"
  }, /*#__PURE__*/React.createElement("span", {
    className: "lune-jp"
  }, "\u30EB\u30CD"), " \xB7 H\xCDBRIDO v9.0"))), /*#__PURE__*/React.createElement("div", {
    className: "ln-sec-label"
  }, "// Red Neuronal"), /*#__PURE__*/React.createElement("div", {
    className: "ln-providers"
  }, /*#__PURE__*/React.createElement(ProviderTab, {
    icon: /*#__PURE__*/React.createElement(window.IconCloud, null),
    name: "Lune AI \xB7 Nube",
    desc: "Enrutamiento inteligente",
    accent: "blue",
    active: provider === 'cloud',
    onClick: () => onProvider('cloud')
  }), /*#__PURE__*/React.createElement(ProviderTab, {
    icon: /*#__PURE__*/React.createElement(window.IconCpu, null),
    name: "Lune AI \xB7 Local",
    desc: "Offline \xB7 sin red",
    accent: "cyan",
    active: provider === 'local',
    onClick: () => onProvider('local')
  })), /*#__PURE__*/React.createElement("div", {
    className: "ln-mascot"
  }, /*#__PURE__*/React.createElement("div", {
    className: "ln-mascot-stage"
  }, /*#__PURE__*/React.createElement("img", {
    src: MASCOT[mascotState] || MASCOT.normal,
    alt: "Lune"
  }))));
}
window.Sidebar = Sidebar;
})(); } catch (e) { __ds_ns.__errors.push({ path: "ui_kits/lune-desktop/sidebar.jsx", error: String((e && e.message) || e) }); }

__ds_ns.Avatar = __ds_scope.Avatar;

__ds_ns.Button = __ds_scope.Button;

__ds_ns.Card = __ds_scope.Card;

__ds_ns.ChatBubble = __ds_scope.ChatBubble;

__ds_ns.IconButton = __ds_scope.IconButton;

__ds_ns.Badge = __ds_scope.Badge;

__ds_ns.StatusPill = __ds_scope.StatusPill;

__ds_ns.Input = __ds_scope.Input;

__ds_ns.Switch = __ds_scope.Switch;

__ds_ns.ProviderTab = __ds_scope.ProviderTab;

})();
