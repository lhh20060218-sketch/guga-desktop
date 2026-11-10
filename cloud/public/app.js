/* 咕嘎管家 Web 体验版 · 星海场景版前端逻辑 */
/* 安全规则：所有模型输出与用户输入均用 textContent 渲染，绝不 innerHTML 拼接 */
'use strict';

const $ = (id) => document.getElementById(id);
let token = sessionStorage.getItem('guga_token') || '';
let me = sessionStorage.getItem('guga_me') || '';
let pollTimer = null;
let seenLogCount = 0;
let chatBusy = false;
let sendMode = 'chat';          // 'chat' 对话 | 'task' 派单
let lastFinishedTs = 0;         // 庆祝动画判定
let sceneMode = 'full';         // 星海 | 纯净
let starField = null;
let petState = 'idle';
let spaces = ['默认空间'];
let curSpace = localStorage.getItem('guga_space') || '默认空间';

/* ---------- 工具 ---------- */
function show(el) { el.classList.remove('hidden'); }
function hide(el) { el.classList.add('hidden'); }
let toastTimer = null;
function toast(text, ms = 2600) {
  const t = $('toast');
  t.textContent = text; show(t);
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => hide(t), ms);
}
function fmtTime(ts) { return new Date(ts).toTimeString().slice(0, 8); }

/* ---------- 咕嘎语音（预生成音效包，事件触发） ---------- */
let voiceOn = sessionStorage.getItem('guga_voice') !== 'off';
let curVoice = null;       // 正在播的那一条（防叠音按"真的在播"判断，不靠猜时长）
let pendingVoice = null;   // 排队的一句：一句没播完就来新事件时排它，最多排一句
/* 音效包版本戳：静态 mp3 不带参数会被浏览器长期缓存，换包后用户听到的还是旧的。
   换音效包必须同步改这个戳（与 index.html 的 app.js?v 一起 bump）。 */
const VOICE_VER = '20261105e';
function playVoice(name) {
  if (!voiceOn || sleepOn) return;
  const next = () => {
    if (!pendingVoice) return;
    const p = pendingVoice;
    pendingVoice = null;
    start(p);
  };
  const start = (n) => {
    try {
      const audio = new Audio('voice/' + n + '.mp3?v=' + VOICE_VER);
      audio.volume = 0.9;
      curVoice = audio;
      audio.addEventListener('ended', () => { if (curVoice === audio) curVoice = null; next(); });
      audio.addEventListener('error', () => { if (curVoice === audio) curVoice = null; next(); });  // 缺文件也不卡队列
      audio.play().catch(() => {                      // 自动播放被拦截：清队，别积压成"迟到的播报"
        if (curVoice === audio) curVoice = null;
        pendingVoice = null;
      });
    } catch (e) { if (curVoice === audio) curVoice = null; }
  };
  if (curVoice && !curVoice.paused && !curVoice.ended) { pendingVoice = name; return; }
  start(name);
}
function updateVoiceBtn() {
  $('voiceToggle').textContent = voiceOn ? '🔊 语音' : '🔇 静音';
}
$('voiceToggle').addEventListener('click', () => {
  voiceOn = !voiceOn;
  sessionStorage.setItem('guga_voice', voiceOn ? 'on' : 'off');
  updateVoiceBtn();
  if (voiceOn) playVoice('idle');
});

/* ---------- 睡眠勿扰（借鉴 dsh-pet）：🌙 模式下停语音、停主动播报，台账静默记录 ---------- */
let sleepOn = sessionStorage.getItem('guga_sleep') === 'on';
function updateSleepBtn() {
  $('sleepToggle').textContent = sleepOn ? '😴 睡眠中' : '🐧 在岗';
}
$('sleepToggle').addEventListener('click', () => {
  sleepOn = !sleepOn;
  sessionStorage.setItem('guga_sleep', sleepOn ? 'on' : 'off');
  updateSleepBtn();
  if (sleepOn) { try { speechSynthesis.cancel(); } catch {} toast('😴 咕嘎进入睡眠勿扰：不吭声，台账照常静默记录'); }
  else { playVoice('idle'); say('少爷好，咕嘎睡饱了，继续盯活！'); }
});
updateSleepBtn();

/* ---------- 状态角标（六档工作状态的"一眼看懂"版） ---------- */
function setBadge(txt) {
  const b = $('petBadge');
  if (!txt) { b.classList.add('hidden'); return; }
  b.textContent = txt;
  b.classList.remove('hidden');
}

/* ---------- 咕嘎本尊 ---------- */
function setPet(state) {
  petState = state;
  const box = $('petBox');
  box.dataset.state = state;
  // 切状态时清掉 idle 小动作，避免动画打架
  box.classList.remove('mood-hop', 'mood-tilt', 'mood-peck', 'mood-waddle');
  // 位置保留：被少爷拖到哪就站哪（桌面宠物习惯），不再拽回原位
}
let lastSayTs = 0;             // 最近一次开口时间（主动播报与轮询文案的节流）

/* ---------- 开场显形 ----------
 * 形象统一为仓库本体内置的原创 Q 版企鹅（resources/expressions）。
 * 原 AI 生成的"光柱凝形"片是另一套形象，为避免同一作品出现两个角色，已停用，
 * 改为立绘淡入显形：0.7s 从透明到不透明，与星空场景同层，不与常驻立绘冲突。 */
const REVEAL_SRC = 'guga_front.png?v=qp1';
const REVEAL_MS = 700;         // 淡入时长
function playReveal() {
  const box = $('petBox'), rv = $('petReveal'), pic = $('petImg');
  if (!box || !rv || !pic) return;
  if (sessionStorage.getItem('guga_reveal_done')) return;      // 一个会话只放一次
  try {
    if (window.matchMedia('(prefers-reduced-motion: reduce)').matches) return;
  } catch { /* 老浏览器没有 matchMedia，照常播 */ }
  sessionStorage.setItem('guga_reveal_done', '1');

  const start = () => {
    box.classList.add('revealing');
    rv.src = REVEAL_SRC;
    rv.classList.add('on');
    pic.style.opacity = '0';
    setTimeout(() => {
      rv.classList.remove('on');        // 动画停在最后一帧，开始淡出
      pic.style.opacity = '';           // 立绘淡入
      setTimeout(() => {
        box.classList.remove('revealing');
        rv.removeAttribute('src');      // 释放动画占的内存
      }, 620);
    }, REVEAL_MS);
  };
  // 先预加载：图没到就让立绘直接站着，绝不把位置空在那儿
  const probe = new Image();
  probe.onload = start;
  probe.onerror = () => {};
  probe.src = REVEAL_SRC;
}

/* TTS 语音汇报：浏览器自带 speechSynthesis，零依赖离线可用。
 * 只读"正式汇报"（对少爷说的话），内心OS 不读（避免满屏碎碎念都出声）。 */
let ttsVoice = null;
(function pickTTSVoice() {
  try {
    const vs = speechSynthesis.getVoices();
    ttsVoice = vs.find(v => /zh[-_]CN/i.test(v.lang) && /female|女|晓|悦/i.test(v.name))
            || vs.find(v => /zh[-_]CN/i.test(v.lang)) || vs.find(v => /^zh/i.test(v.lang)) || null;
    speechSynthesis.onvoiceschanged = () => {
      const v2 = speechSynthesis.getVoices();
      ttsVoice = v2.find(v => /zh[-_]CN/i.test(v.lang)) || v2.find(v => /^zh/i.test(v.lang)) || ttsVoice;
    };
  } catch { /* 不支持则无声 */ }
})();
let lastTtsTs = 0;
function ttsSpeak(text) {
  if (sleepOn || !voiceOn || !('speechSynthesis' in window)) return;
  if (curVoice && !curVoice.paused && !curVoice.ended) return;   // 音效正在播：让位，避免两路声音打架
  const now = Date.now();
  if (now - lastTtsTs < 2500) return;    // 防叠音（与音效同一节流）
  lastTtsTs = now;
  try {
    speechSynthesis.cancel();
    const u = new SpeechSynthesisUtterance(String(text).slice(0, 120));
    if (ttsVoice) u.voice = ttsVoice;
    u.lang = 'zh-CN'; u.rate = 1.06; u.pitch = 1.18; u.volume = 0.95;
    speechSynthesis.speak(u);
  } catch { /* 忽略 */ }
}
function say(text, inner, silent) {
  const s = $('petSay');
  s.classList.toggle('inner', !!inner);
  s.innerHTML = '';
  const who = document.createElement('span');
  who.className = 'who'; who.textContent = inner ? '内心OS' : '咕嘎';
  s.appendChild(who);
  s.appendChild(document.createTextNode((inner ? '💭 ' : '') + text));
  lastSayTs = Date.now();
  if (!inner && !silent) ttsSpeak(text);   // 正式汇报同步读出来（流式聊天除外，读完整版）
}
function sayInner(text) { say(text, true); }
const PET_IDLE_LINES = [
  '少爷好，咕嘎随时听候差遣。',
  '戳我一下，我就精神一分。',
  '给我一个目标，还您一个结果。',
  '台账在右边，我的监工记录一清二楚。',
];
function petClick() {
  if (sleepOn) { toast('😴 咕嘎睡得正香（台账照常记录）'); return; }   // 睡眠勿扰：戳也不吭声
  const lines = petState === 'party'
    ? ['任务完结！咕嘎向少爷交差！', '嘎——这次的活干得漂亮！']
    : petState === 'urge'
      ? ['别催我，我在催他们！', '落后进度的那家伙已经被我记在板子上了。']
      : PET_IDLE_LINES;
  say(lines[Math.floor(Math.random() * lines.length)]);
}

/* ---------- 桌面宠物式 idle 小动作（借鉴 pet 插件：待机不呆站） ----------
 * 每 4~7 秒随机一次：小跳 / 歪头 / 啄食 / 摇摆踱步 / 掉头面向另一侧
 * 仅在 idle 态触发；进入监工/验收/催办等正式状态自动让位。 */
let petFacing = 1;
let petWalk = 0;          // 相对默认位的水平偏移（拖拽/踱步共享，px）
let waddleTimer = 0;
let petDragMoved = false; // 本次 press 是否发生了拖拽（区分点击与搬动）
const IDLE_MOODS = ['hop', 'tilt', 'peck', 'waddle', 'flip'];
setInterval(() => {
  if (petState !== 'idle' || chatBusy) return;
  const mv = $('mainView');
  if (!mv || mv.classList.contains('hidden')) return;
  if (Math.random() < 0.3) return;   // 偶尔歇一下，更有"活物感"
  const mood = IDLE_MOODS[Math.floor(Math.random() * IDLE_MOODS.length)];
  const box = $('petBox');
  if (mood === 'flip') {
    petFacing = -petFacing;
    box.style.setProperty('--f', String(petFacing));
    return;
  }
  if (mood === 'waddle') {
    const dist = petFacing * (14 + Math.random() * 22);
    const base = petWalk;
    petWalk = base + dist;
    box.style.setProperty('--walk', petWalk.toFixed(0) + 'px');
    box.classList.add('mood-waddle');
    waddleTimer = setTimeout(() => {
      box.classList.remove('mood-waddle');
      petWalk = base;
      box.style.setProperty('--walk', petWalk.toFixed(0) + 'px');
    }, 1800);
    return;
  }
  box.classList.add('mood-' + mood);
  setTimeout(() => box.classList.remove('mood-' + mood), 2000);
}, 4600);

/* ---------- 桌面宠物物理：抓起 / 拖拽 / 抛掷落地（对标 dsh-pet） ----------
 * 按住咕嘎可以直接抓起来满屏拖；松手后水平惯性滑行+摩擦衰减，
 * 垂直方向受重力落回地面，速度大还会弹一下；甩出方向决定它面朝哪边。 */
(function initPetDrag() {
  const box = $('petBox');
  let dragging = false, sx = 0, sy = 0, bw = 0, br = 0, rise = 0, vx = 0;
  let lastX = 0, lastT = 0, raf = 0;
  const clamp = (v, a, b) => Math.min(b, Math.max(a, v));
  function bounds() {
    const w = box.offsetWidth || 280;
    return {
      min: 10 - 224,
      max: window.innerWidth - w - 10 - 224,
      maxRise: Math.max(0, window.innerHeight - 150),
    };
  }
  function apply() {
    box.style.setProperty('--walk', petWalk.toFixed(0) + 'px');
    box.style.setProperty('--rise', rise.toFixed(0) + 'px');
  }
  box.addEventListener('pointerdown', (e) => {
    if (e.pointerType === 'mouse' && e.button !== 0) return;
    cancelAnimationFrame(raf);
    clearTimeout(waddleTimer);
    box.classList.remove('mood-waddle');
    dragging = true; petDragMoved = false;
    sx = e.clientX; sy = e.clientY;
    bw = petWalk; br = rise;
    vx = 0; lastX = e.clientX; lastT = performance.now();
    box.classList.add('dragging');
    try { box.setPointerCapture(e.pointerId); } catch { /* 忽略 */ }
  });
  box.addEventListener('pointermove', (e) => {
    if (!dragging) return;
    const dx = e.clientX - sx, dy = e.clientY - sy;
    if (!petDragMoved && Math.hypot(dx, dy) > 6) petDragMoved = true;
    const b = bounds();
    petWalk = clamp(bw + dx, b.min, b.max);
    rise = clamp(br - dy, 0, b.maxRise);
    const now = performance.now(), dt = Math.max(1, now - lastT);
    vx = 0.75 * vx + 0.25 * (e.clientX - lastX) / dt * 16;   // 平滑水平速度 px/帧
    lastX = e.clientX; lastT = now;
    apply();
  });
  function release() {
    if (!dragging) return;
    dragging = false;
    if (Math.abs(vx) > 2) {                    // 甩出的方向就是它面朝的方向
      petFacing = vx > 0 ? 1 : -1;
      box.style.setProperty('--f', String(petFacing));
    }
    if (Math.abs(vx) < 2 && rise < 2) {        // 轻放：直接结束
      box.classList.remove('dragging');
      return;
    }
    let vy = 0;                                // 抛掷物理：摩擦滑行 + 重力落地反弹
    const step = () => {
      const b = bounds();
      vx *= 0.95;
      petWalk = clamp(petWalk + vx, b.min, b.max);
      if (rise > 0 || vy < 0) {
        vy += 2.1; rise -= vy;
        if (rise <= 0) { rise = 0; vy = vy > 5 ? -vy * 0.38 : 0; }
      }
      apply();
      if (Math.abs(vx) > 0.15 || rise > 0 || vy !== 0) {
        raf = requestAnimationFrame(step);
      } else {
        box.classList.remove('dragging');      // 停稳后恢复 idle 呼吸动画
      }
    };
    raf = requestAnimationFrame(step);
  }
  box.addEventListener('pointerup', release);
  box.addEventListener('pointercancel', release);
})();

/* ---------- 远程指挥 · 设备选择器 ----------
 * 登录后拉取本账号在线的本体电脑 + 各自可指挥的 AI 软件（豆包/WorkBuddy…），
 * 派单时点名由哪台电脑真机执行；"WorkBuddy 出稿 → 豆包润色"这类跨软件跨设备接力就靠它。 */
let pickedDevice = localStorage.getItem('guga_device') || '';    // 稳定设备 id（旧值可能是设备名，服务端两者都认）
let pickedLabel = '';
let pickedName = localStorage.getItem('guga_device_name') || ''; // 设备显示名（掉线后列表里没有它，错误文案仍要能叫出名字）
let lastDevices = [];    // 最近一次 /api/agent/devices 快照：错误文案靠它把 id 还原成设备名
async function refreshDevices() {
  try {
    const r = await fetch('/api/agent/devices', { headers: authHeaders() });
    if (!r.ok) return;
    const d = await r.json();
    const sel = $('devicePick');
    const devs = d.devices || [];
    lastDevices = devs;
    const opts = ['<option value="">📡 自动 · 任一在线电脑</option>'].concat(devs.map(v => {
      const tools = (v.ai || []).join('、') || '未识别到 AI 软件';
      return `<option value="${v.id || v.device}">🖥 ${v.device}（${tools}）</option>`;
    }));
    /* 点名过的设备掉线后不悄悄改派：保留这一项并标注「已离线」，
       让服务端如实回 DEVICE_OFFLINE（用户才知道"这单没派出去、该换哪台"）。 */
    const gone = !!pickedDevice && !devs.some(v => (v.id || v.device) === pickedDevice);
    if (gone) opts.push(`<option value="${pickedDevice}">🖥 ${pickedName || pickedDevice}（已离线）</option>`);
    if (!devs.length && !gone) { sel.style.display = 'none'; sel.innerHTML = ''; return; }
    sel.style.display = '';
    sel.innerHTML = opts.join('');
    if (pickedDevice) {
      sel.value = pickedDevice;
      const cur = devs.find(v => (v.id || v.device) === pickedDevice);
      if (cur) { pickedName = cur.device; pickedLabel = (sel.selectedOptions[0] || {}).textContent || pickedDevice; }
      else pickedLabel = pickedName || pickedDevice;
      localStorage.setItem('guga_device_name', pickedName || '');
    } else { pickedLabel = ''; sel.value = ''; }
  } catch { /* 状态闪断不打扰少爷 */ }
}
/* ---------- 派单需要哪些工具（跨设备校验） ----------
 * 与桌面端 core/tool_router.required_tools 同口径：先认任务里点名的软件，
 * 没点名则按能力推载体（演示/文档偏 WPS、视频偏剪映、图片偏豆包），
 * 目标设备自己清单里有的载体优先，避免把"做PPT"误判成必须 WPS。
 * 只在点名了设备时随单上报；服务端仅在有 device + requiredTools 时校验清单。 */
const TOOL_NAME_HINTS = [
  [/workbuddy|work\s*buddy/i, 'WorkBuddy'],
  [/豆包|doubao/i, '豆包'],
  [/kimi/i, 'Kimi'],
  [/wps/i, 'WPS'],
  [/剪映|capcut/i, '剪映'],
  [/trae/i, 'Trae'],
  [/joycode/i, 'JoyCode'],
  [/即梦|jimeng/i, '即梦'],
];
const TOOL_CAP_HINTS = [
  [/视频|剪辑|字幕|短视频|成片|配音/, ['剪映']],
  [/ppt|演示文稿|幻灯片|汇报材料|路演/i, ['WPS', 'WorkBuddy']],
  [/文档|文案|报告|周报|总结|纪要|方案/, ['WPS', 'WorkBuddy']],
  [/图片|海报|插画|配图|封面/, ['豆包']],
];
function requiredToolsFor(goal, dev) {
  const out = [];
  const text = String(goal || '');
  for (const [re, name] of TOOL_NAME_HINTS) if (re.test(text) && !out.includes(name)) out.push(name);
  if (out.length) return out.slice(0, 2);
  const ai = ((dev && dev.ai) || []).map(x => String(x));
  for (const [re, carriers] of TOOL_CAP_HINTS) {
    if (!re.test(text)) continue;
    const own = carriers.find(n => ai.some(a => a.toLowerCase().includes(n.toLowerCase())));
    const pick = own || carriers[0];
    if (!out.includes(pick)) out.push(pick);
    break;
  }
  return out.slice(0, 2);
}
function deviceNameOf(id) {
  const d = lastDevices.find(v => v.id === id || v.device === id);
  return (d && d.device) || (id === pickedDevice && pickedName) || id || '所选设备';
}
async function inventorySnapshot() {
  try {
    const r = await fetch('/api/devices/inventory', { headers: authHeaders() });
    if (!r.ok) return [];
    return ((await r.json()).devices) || [];
  } catch { return []; }
}
function devicesWith(tools, inv) {
  const need = (tools || []).map(t => String(t).toLowerCase());
  return inv.filter(v => v.online && v.hasInventory && need.every(n =>
    (v.tools || []).some(it => {
      const name = String(it.name || '').toLowerCase();
      return name.includes(n) || n.includes(name);
    })));
}
function toolListText(invEntry) {
  return ((invEntry && invEntry.tools) || []).map(t => t.name).join('、') || '无';
}
/* 把服务端三条跨设备错误码翻译成"缺什么、哪台有、下一步怎么办" */
async function dispatchFailureText(data, needTools) {
  const code = data.code || '';
  const target = deviceNameOf(data.deviceId);
  const inv = await inventorySnapshot();
  const holders = devicesWith(needTools, inv);
  const holderText = holders.length
    ? holders.map(v => `${v.device}（${toolListText(v)}）`).join('、')
    : '暂无在线设备同时具备所需工具';
  const onlineText = inv.filter(v => v.online).map(v => v.device).join('、') || '暂无在线设备';
  if (code === 'DEVICE_OFFLINE') {
    return `⚠ ［DEVICE_OFFLINE］所选设备「${target}」的本体已离线，这单没有悄悄改派。\n当前在线：${onlineText}。`
      + (needTools.length ? `\n本单需要：${needTools.join('、')} → 可换到 ${holderText}，或去「${target}」重新启动咕嘎本体。`
        : `\n请换一台在线电脑，或去「${target}」重新启动咕嘎本体。`);
  }
  if (code === 'NO_INVENTORY') {
    return `⚠ ［NO_INVENTORY］所选设备「${target}」还没上报软件清单，无法确认它装了什么。`
      + (needTools.length ? `\n本单需要：${needTools.join('、')} → 已具备的在：${holderText}。` : '')
      + `\n让「${target}」的本体启动一次即可自动上报清单。`;
  }
  if (code === 'TOOL_MISSING') {
    const miss = data.missing || needTools;
    const avail = data.available || [];
    return `⚠ ［TOOL_MISSING］所选设备「${target}」上缺：${miss.join('、')}。`
      + (avail.length ? `\n它当前清单里只有：${avail.join('、')}。` : '')
      + `\n具备${miss.join('、')}的在：${holderText} → 换到那台派单，或先在「${target}」装好再派。`;
  }
  return '⚠ ' + (data.error || '派单失败');
}
$('devicePick').addEventListener('change', () => {
  pickedDevice = $('devicePick').value;
  pickedLabel = ($('devicePick').selectedOptions[0] || {}).textContent || pickedDevice;
  const cur = lastDevices.find(v => (v.id || v.device) === pickedDevice);
  if (pickedDevice) {
    pickedName = (cur && cur.device) || pickedName || pickedLabel;   // 选的是「已离线」占位项时沿用上次记住的设备名
    localStorage.setItem('guga_device', pickedDevice);
    localStorage.setItem('guga_device_name', pickedName || '');
  } else { localStorage.removeItem('guga_device'); localStorage.removeItem('guga_device_name'); }
  toast(pickedDevice ? `📡 已点名 ${pickedLabel} 承接真机任务` : '📡 已切回自动：任一在线电脑接单');
});

/* ---------- 登录 ---------- */
/* 远程指挥：给本会话起个设备名（localStorage 持久），派单时随登录上报——
 * 台账会显示"从哪台设备遥控、哪台电脑真机执行"。手机/平板/别的电脑登录同账号即可遥控本体电脑。 */
function deviceLabel() {
  let d = localStorage.getItem('guga_devid');
  if (d) return d;
  const mob = /Android|iPhone|iPad|Mobile/i.test(navigator.userAgent);
  const br = /Edg\//.test(navigator.userAgent) ? 'Edge'
    : /Chrome\//.test(navigator.userAgent) ? 'Chrome'
    : /Firefox\//.test(navigator.userAgent) ? 'Firefox' : '浏览器';
  d = (mob ? '📱 移动设备' : '🖥 电脑') + ' · ' + br;
  localStorage.setItem('guga_devid', d);
  return d;
}
async function login(user, pass) {
  const resp = await fetch('/api/login', {
    method: 'POST', headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username: user, password: pass, device: deviceLabel() }),
  });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || '登录失败');
  token = data.token; me = data.username;
  sessionStorage.setItem('guga_token', token);
  sessionStorage.setItem('guga_me', me);
}

$('loginForm').addEventListener('submit', async (e) => {
  e.preventDefault();
  const btn = $('loginBtn');
  btn.disabled = true;
  try {
    await login($('loginUser').value.trim(), $('loginPass').value);
    enterMain();
  } catch (err) {
    const errEl = $('loginErr');
    errEl.textContent = err.message; show(errEl);
  } finally { btn.disabled = false; }
});

$('logoutBtn').addEventListener('click', () => {
  sessionStorage.removeItem('guga_token');
  sessionStorage.removeItem('guga_me');
  location.reload();
});

function enterMain() {
  hide($('loginView')); show($('mainView'));
  $('whoami').textContent = '少爷：' + me;
  updateVoiceBtn();
  playVoice('hello');
  playReveal();                 // 开场显形：只在进主界面时放一次
  loadSpaces();
  startPolling();
  refreshDevices();
  setInterval(refreshDevices, 10000);   // 远程指挥设备列表 10 秒刷新（在线/离线/AI 软件清单）
  // 每个会话首次登录自动跑一次环境自检（评委一进来就看到体检报告）
  if (!sessionStorage.getItem('guga_sc_done')) {
    sessionStorage.setItem('guga_sc_done', '1');
    setTimeout(runSelfCheck, 700);
  }
}

/* ---------- 工作空间（仿 WorkBuddy：任务分区管理与切换） ---------- */
async function loadSpaces() {
  try {
    const resp = await fetch('/api/spaces', { headers: { Authorization: 'Bearer ' + token } });
    const d = await resp.json();
    spaces = d.spaces || ['默认空间'];
    if (!spaces.includes(curSpace)) curSpace = spaces[0];
    localStorage.setItem('guga_space', curSpace);
    renderSpaces();
  } catch { /* 保持默认 */ }
}
function renderSpaces() {
  const box = $('spaceList');
  box.textContent = '';
  for (const s of spaces) {
    const el = document.createElement('div');
    el.className = 'side-item' + (s === curSpace ? ' active' : '');
    el.textContent = (s === curSpace ? '▸ ' : ' folder ').replace(' folder ', '▫ ') + s;
    el.addEventListener('click', () => {
      curSpace = s;
      localStorage.setItem('guga_space', s);
      renderSpaces();
      pollState();
      closeSidebarMobile();
    });
    box.appendChild(el);
  }
}
function openSpaceAdd() {
  show($('spaceAddRow'));
  $('spaceName').value = '';
  $('spaceName').focus();
}
async function submitSpace() {
  const name = $('spaceName').value.trim();
  if (!name) return;
  try {
    const resp = await fetch('/api/spaces', { method: 'POST', headers: authHeaders(), body: JSON.stringify({ name }) });
    const d = await resp.json();
    if (!resp.ok) throw new Error(d.error || '创建失败');
    spaces = d.spaces;
    curSpace = name;
    localStorage.setItem('guga_space', curSpace);
    renderSpaces();
    hide($('spaceAddRow'));
    toast(`空间「${name}」已创建，之后派的单都归这里`);
  } catch (e) { toast(e.message); }
}
$('spaceAdd').addEventListener('click', openSpaceAdd);
$('spaceOk').addEventListener('click', submitSpace);
$('spaceName').addEventListener('keydown', (e) => { if (e.key === 'Enter') submitSpace(); });

/* ---------- 侧栏（移动端抽屉） ---------- */
$('sideToggle').addEventListener('click', () => $('sidebar').classList.toggle('open'));
function closeSidebarMobile() {
  if (window.innerWidth <= 700) $('sidebar').classList.remove('open');
}
function timeAgo(ts) {
  const m = Math.round((Date.now() - ts) / 60000);
  if (m < 1) return '刚刚';
  if (m < 60) return m + '分钟前';
  const h = Math.round(m / 60);
  if (h < 24) return h + '小时前';
  return Math.round(h / 24) + '天前';
}
function renderHistory(list) {
  const box = $('histList');
  box.textContent = '';
  if (!list.length) {
    const e = document.createElement('div');
    e.className = 'side-empty';
    e.textContent = '本空间暂无任务';
    box.appendChild(e);
    return;
  }
  for (const t of list) {
    const el = document.createElement('div');
    el.className = 'side-item task';
    const g = document.createElement('span'); g.className = 'g'; g.textContent = t.goal;
    const tm = document.createElement('span'); tm.className = 't'; tm.textContent = timeAgo(t.createdAt);
    el.appendChild(g); el.appendChild(tm);
    el.addEventListener('click', () => focusTask(t.id));
    box.appendChild(el);
  }
}
function focusTask(tid) {
  if ($('ledgerPanel').classList.contains('collapsed')) setLedger(false, true);
  const el = document.querySelector(`[data-taskid="${tid}"]`);
  if (el) {
    el.scrollIntoView({ behavior: 'smooth', block: 'start' });
    el.classList.add('flash');
    setTimeout(() => el.classList.remove('flash'), 2200);
  }
  closeSidebarMobile();
}

/* ---------- 场景（星海背景，底子：PyMaster StarField） ---------- */
function applyScene(mode) {
  sceneMode = mode;
  document.body.dataset.scene = mode;
  $('sceneToggle').textContent = mode === 'full' ? '✦ 星海' : '◌ 纯净';
  if (starField) starField.setMode(mode);
}
$('sceneToggle').addEventListener('click', () => {
  applyScene(sceneMode === 'full' ? 'off' : 'full');
});

/* ---------- 对话流（中间区：少爷 ⇄ 咕嘎 的聊天记录） ---------- */
function pushMsg(role, text) {
  const box = $('chatStream');
  const hint = box.querySelector('.chat-hint');
  if (hint) hint.remove();
  const m = document.createElement('div');
  m.className = 'msg ' + role;
  const b = document.createElement('div');
  b.className = 'bubble'; b.textContent = text;
  m.appendChild(b); box.appendChild(m);
  while (box.children.length > 60) box.firstElementChild.remove();
  box.scrollTop = box.scrollHeight;
  return b;
}

/* ---------- 对话（回复直接进咕嘎气泡）---------- */
async function sendChat(text, isGoal) {
  if (chatBusy) { toast('咕嘎正在忙，等它说完这句'); return; }
  chatBusy = true; $('sendBtn').disabled = true;
  pushMsg('me', text);
  let replyBubble = null;
  let bubbleText = '';
  const showBubble = (t, silent) => {
    bubbleText = t; say(t, false, silent);
    if (!replyBubble) replyBubble = pushMsg('cat', t);
    else { replyBubble.textContent = t; $('chatStream').scrollTop = $('chatStream').scrollHeight; }
  };
  showBubble(isGoal ? '少爷吩咐收到，正在拆解目标…' : '少爷，让我想想…');
  try {
    if (isGoal) {
      setPet('command');
      // 点名了设备时，按任务推导它必须具备的工具，服务端据此校验清单（NO_INVENTORY / TOOL_MISSING）
      const pickedDev = lastDevices.find(v => (v.id || v.device) === pickedDevice) || null;
      const needTools = pickedDevice ? requiredToolsFor(text, pickedDev) : [];
      const resp = await fetch('/api/tasks', {
        method: 'POST', headers: authHeaders(),
        body: JSON.stringify({ goal: text, space: curSpace, executor: localMode ? 'local' : 'cloud', device: pickedDevice, requiredTools: needTools }),
      });
      const data = await resp.json();
      if (!resp.ok) {
        const e = new Error(data.error || '派单失败');
        e.dispatch = data;          // 带上 code/missing/available/deviceId，错误文案要能说清"缺什么、哪台有"
        e.needTools = needTools;
        throw e;
      }
      setLedger(false, false);   // 派单成功自动展开台账，少爷能立刻看到监工现场
      const n = data.task.subtasks.length;
      let msg = data.mode === 'local'
        ? `少爷，本单已派给「${data.task.execDevice || '您配对的电脑'}」真机执行——它马上远程指挥本机 AI 软件真实干活${pickedDevice && pickedLabel && pickedLabel !== deviceLabel() ? '（远程指挥中，盯着那台电脑屏幕就能看到过程）' : '，盯着本机屏幕就能看到过程'}，产物回传后我照旧验收。`
        : `少爷，目标已拆解为 ${n} 个子任务——工人们已领单，现在开始真实执行，产物完成后可在台账里点开查看。我全程盯着，有超时或不合格当场处理。`;
      if (data.mode === 'demo') msg = `少爷，当前服务器未接入大模型，暂以内置剧本演示监工流程（无真实产物）。`;
      if (needTools.length) msg += `\n（已按任务需要校验工具：${needTools.join('、')}）`;
      showBubble(msg);
    } else {
      const resp = await fetch('/api/chat', {
        method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: text, space: curSpace, executor: localMode ? 'local' : 'cloud', device: pickedDevice }),
      });
      if (!resp.ok) {
        const data = await resp.json().catch(() => ({}));
        throw new Error(data.error || '服务暂时不可用');
      }
      const reader = resp.body.getReader();
      const decoder = new TextDecoder();
      let buf = '', full = '', dispatched = false;
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        buf += decoder.decode(value, { stream: true });
        const lines = buf.split('\n'); buf = lines.pop();
        for (const line of lines) {
          const s = line.trim();
          if (!s.startsWith('data:')) continue;
          const payload = s.slice(5).trim();
          if (payload === '[DONE]') continue;
          try {
            const d = JSON.parse(payload);
            if (d.dispatched) {
              dispatched = true;
              setPet('command');                       // 大脑转派双手，切指挥姿态
              setLedger(false, false);                 // 自动展开台账，少爷能立刻看到监工现场
            }
            if (d.delta) { full += d.delta; showBubble(full, true); }   // 流式过程静默，读完读全文
            if (d.error) throw new Error(d.error);
          } catch (e) { if (e.message && !/JSON/.test(e.message)) throw e; }
        }
      }
      if (dispatched && !full) showBubble('少爷，这活已派给执行方，进展请看台账');
      if (!full && !dispatched) showBubble('少爷，咕嘎走神了一下，再问一次好吗');
      if (full && !dispatched) ttsSpeak(full);   // 聊天回复读完整版（派单话术不读，避免与监工播报打架）
    }
  } catch (err) {
    showBubble(err.dispatch ? await dispatchFailureText(err.dispatch, err.needTools || []) : '⚠ ' + err.message);
  } finally {
    chatBusy = false; $('sendBtn').disabled = false;
  }
}
function authHeaders() { return { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' }; }

/* ---------- 发送模式切换 ---------- */
function setMode(mode) {
  sendMode = mode;
  $('modeChat').classList.toggle('on', mode === 'chat');
  $('modeTask').classList.toggle('on', mode === 'task');
  $('chatInput').placeholder = mode === 'task'
    ? '输入目标，咕嘎来拆解派单…（Enter 发送）'
    : '和咕嘎聊两句…（切到派单模式可下达目标）';
}
$('modeChat').addEventListener('click', () => setMode('chat'));
$('modeTask').addEventListener('click', () => setMode('task'));

$('sendBtn').addEventListener('click', () => {
  const v = $('chatInput').value.trim();
  if (!v) return;
  $('chatInput').value = '';
  sendChat(v, sendMode === 'task');
});
$('chatInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter') { e.preventDefault(); $('sendBtn').click(); }
});
document.querySelectorAll('.quick').forEach(btn => {
  btn.addEventListener('click', () => sendChat(btn.dataset.goal, true));
});
$('scBtn').addEventListener('click', runSelfCheck);
$('scClose').addEventListener('click', () => $('scModal').classList.add('hidden'));
$('petBox').addEventListener('click', () => {
  if (petDragMoved) { petDragMoved = false; return; }   // 拖拽/甩出不算"戳一戳"
  petClick();
});

/* ---------- 任务台账（轮询 + 状态机驱动咕嘎） ---------- */
const STATUS_LABEL = { pending: '待开工', running: '执行中', paused: '⏸ 已暂停', review: '验收中', done: '✅ 通过', returned: '❌ 已打回', error: '⚠ 异常' };

/* ---------- 台账收起/展开（手机端默认收起，记忆用户偏好） ---------- */
function setLedger(collapsed, persist) {
  $('ledgerPanel').classList.toggle('collapsed', collapsed);
  $('ledgerTab').classList.toggle('hidden', !collapsed);
  $('ledgerToggle').textContent = collapsed ? '▸ 收起' : '▸ 收起';
  if (persist) localStorage.setItem('guga_ledger_collapsed', collapsed ? '1' : '0');
}
$('ledgerToggle').addEventListener('click', () => setLedger(true, true));
$('ledgerTab').addEventListener('click', () => setLedger(false, true));

function updateLedgerTab(runCount) {
  const tab = $('ledgerTab');
  const n = runCount || 0;
  tab.innerHTML = '';
  tab.appendChild(document.createTextNode('📋 台账'));
  if (n > 0) {
    const b = document.createElement('span');
    b.className = 'n'; b.textContent = String(n);
    tab.appendChild(b);
  }
}

/* ---------- 咕嘎工作流水线可视化（六段：接单→拆解→派单→执行→验收→终检） ---------- */
const PIPE_STEPS = ['接单', '拆解', '派单', '执行', '验收', '终检'];
function pipelinePhase(task) {
  if (task.finishedAt) return { active: PIPE_STEPS.length - 1, finished: true };
  const sts = task.subtasks;
  if (sts.every(s => s.status === 'done' || s.status === 'error')) return { active: 5, finished: false };
  if (sts.some(s => s.status === 'running' || s.status === 'review' || s.status === 'paused')) return { active: 3, finished: false };
  if (sts.some(s => s.status === 'returned')) return { active: 3, finished: false };   // 打回重做也在执行段
  return { active: 1, finished: false };   // 全部待开工：拆解派单中
}
function renderPipeline(card, task) {
  const ph = pipelinePhase(task);
  const pipe = document.createElement('div');
  pipe.className = 'pipeline' + (ph.finished ? ' finished' : '');
  PIPE_STEPS.forEach((name, i) => {
    const step = document.createElement('div');
    step.className = 'pstep ' + (i < ph.active || ph.finished ? 'done' : i === ph.active ? 'active' : 'todo');
    const dot = document.createElement('i'); dot.className = 'dot';
    const lb = document.createElement('span'); lb.className = 'lb'; lb.textContent = name;
    step.appendChild(dot); step.appendChild(lb);
    pipe.appendChild(step);
  });
  // 打回返工徽标（监工在动手的证据）
  const reworks = task.subtasks.filter(s => s.attempts > 1).length;
  if (reworks > 0) {
    const tag = document.createElement('span');
    tag.className = 'rework-tag';
    tag.textContent = `🔁 返工 ${reworks}`;
    pipe.appendChild(tag);
  }
  return pipe;
}

/* ---------- 台账清空（两段式确认，防误触） ---------- */
let clearArmedUntil = 0;
$('ledgerClear').addEventListener('click', async () => {
  const btn = $('ledgerClear');
  if (Date.now() > clearArmedUntil) {
    clearArmedUntil = Date.now() + 3000;
    btn.textContent = '⚠ 确认?';
    setTimeout(() => { if (Date.now() > clearArmedUntil) btn.textContent = '🧹'; }, 3100);
    return;
  }
  clearArmedUntil = 0; btn.textContent = '🧹';
  try {
    const resp = await fetch('/api/clear', { method: 'POST', headers: authHeaders(), body: JSON.stringify({ space: curSpace }) });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || '清空失败');
    toast(`台账已清空（${data.removed} 单，产物一并删除）`);
    say('台账已清理干净，少爷。有新活随时吩咐。');
    pollState();
  } catch (e) { toast(e.message); }
});

function startPolling() {
  stopPolling();
  pollState();
  pollTimer = setInterval(pollState, 1500);
}
function stopPolling() { if (pollTimer) clearInterval(pollTimer); pollTimer = null; }

let lastAllTasks = [];        // 最近一次轮询的全量任务（对比弹窗等非台账模块共用）
async function pollState() {
  let data;
  try {
    const resp = await fetch('/api/state', { headers: { Authorization: 'Bearer ' + token } });
    if (resp.status === 401) { stopPolling(); toast('会话过期，请重新登录'); return; }
    data = await resp.json();
  } catch { return; }

  const box = $('ledgerBox');
  box.textContent = '';
  const allTasks = data.tasks || [];
  lastAllTasks = allTasks;
  const tasks = allTasks.filter(t => (t.space || '默认空间') === curSpace);
  let runCount = 0, doneCount = 0;

  if (!tasks.length) {
    const tip = document.createElement('div');
    tip.className = 'empty-tip';
    tip.textContent = '暂无任务。对咕嘎说一个目标（或点下方快捷目标），这里会出现监工台账。';
    box.appendChild(tip);
  }

  for (const task of tasks) {
    const card = document.createElement('div');
    card.className = 'task-card';
    card.dataset.taskid = task.id;

    const goal = document.createElement('div');
    goal.className = 'task-goal';
    goal.textContent = '🎯 ' + task.goal;
    card.appendChild(goal);

    const meta = document.createElement('div');
    meta.className = 'task-meta';
    const modeTag = task.demo ? ' · 演示模式（未接大模型）' : ' · 真实调度';
    const inFinal = !task.finishedAt && task.subtasks.every(s => s.status === 'done' || s.status === 'error');
    meta.textContent = task.finishedAt
      ? `已完结 · 耗时 ${Math.round((task.finishedAt - task.createdAt) / 1000)} 秒 · ${fmtTime(task.finishedAt)}${modeTag}`
      : inFinal
        ? `🔍 总目标终检中 · 开始于 ${fmtTime(task.createdAt)}${modeTag}`
        : `监工中 · 开始于 ${fmtTime(task.createdAt)}${modeTag}`;
    card.appendChild(meta);

    // 咕嘎工作流水线可视化（随真实任务状态实时点亮）
    card.appendChild(renderPipeline(card, task));

    for (const st of task.subtasks) {
      if (st.status === 'running') runCount++;
      if (st.status === 'done') doneCount++;
      const sub = document.createElement('div');
      sub.className = 'subtask ' + (st.status === 'done' ? 'done' : '');

      const head = document.createElement('div');
      head.className = 'sub-head';
      const name = document.createElement('span');
      const badge = document.createElement('span');
      badge.className = 'badge ' + (st.status === 'running' && st.overdue ? 'returned' : st.status);
      badge.textContent = st.status === 'running' && st.overdue ? '⏰ 超时·已催办' : STATUS_LABEL[st.status] || st.status;
      name.textContent = st.name + (st.attempts > 1 ? `（第 ${st.attempts} 次执行）` : '');
      const exec = document.createElement('span');
      exec.className = 'exec';
      exec.textContent = '执行方：' + st.executor;
      head.appendChild(name); head.appendChild(badge); head.appendChild(exec);
      sub.appendChild(head);

      const bar = document.createElement('div');
      bar.className = 'bar';
      const fill = document.createElement('i');
      fill.style.width = st.progress + '%';
      bar.appendChild(fill);
      sub.appendChild(bar);

      const acc = document.createElement('div');
      acc.className = 'acceptance';
      acc.textContent = '验收标准：' + st.acceptance;
      sub.appendChild(acc);

      // ⏸/▶ 暂停-继续（本机执行专用）：进度自动存档，15 分钟内无缝续跑，超时自动清理
      if (!task.finishedAt && !task.demo && st.executor === '本机执行'
          && (st.status === 'running' || st.status === 'paused')) {
        const prow = document.createElement('div');
        prow.className = 'pause-row';
        const pb = document.createElement('button');
        pb.className = 'view-artifact pause-btn';
        pb.dataset.tid = task.id;
        pb.dataset.sid = st.id;
        pb.addEventListener('click', () => pauseCtl(pb));
        if (st.status === 'running') {
          pb.textContent = '⏸ 暂停（进度自动存档）';
          pb.dataset.act = 'pause';
        } else {
          const leftMs = Math.max(0, (st.pausedAt || 0) + 15 * 60 * 1000 - Date.now());
          pb.textContent = '▶ 继续执行（无缝接续）';
          pb.dataset.act = 'resume';
          const left = document.createElement('span');
          left.className = 'pause-left' + (leftMs < 3 * 60 * 1000 ? ' urgent' : '');
          left.textContent = leftMs > 0
            ? `⏳ 存档保留剩 ${Math.ceil(leftMs / 60000)} 分钟，超时自动清理`
            : '⏳ 已超时，正在自动清理…';
          prow.appendChild(left);
        }
        prow.appendChild(pb);
        sub.appendChild(prow);
      }

      if (st.checkResult) {
        const ck = document.createElement('div');
        ck.className = 'check ' + (st.status === 'done' ? 'pass' : 'fail');
        ck.textContent = (st.status === 'done' ? '验收：' : '打回原因：') + st.checkResult;
        sub.appendChild(ck);
      }

      // 真实产物查看按钮
      if (st.artifact) {
        const btn = document.createElement('button');
        btn.className = 'view-artifact';
        btn.dataset.tid = task.id;
        btn.dataset.sid = st.id;
        btn.textContent = `📄 查看产物（${st.artifact.chars} 字 · 第 ${st.artifact.attempt} 次交付）`;
        sub.appendChild(btn);
      }
      // 三次未过验收 → 台账内嵌少爷裁决三键（human-in-the-loop）
      if (st.status === 'error' && !task.demo) {
        const vr = document.createElement('div');
        vr.className = 'verdict-inline-row';
        const label = document.createElement('span');
        label.className = 'v-label';
        label.textContent = '⚠ 三次未过验收，请少爷裁决：';
        vr.appendChild(label);
        for (const [action, txt] of [['approve', '✅ 通过'], ['rework', '🔁 再打回'], ['reassign', '👥 换将']]) {
          const vb = document.createElement('button');
          vb.className = 'verdict-inline ' + action;
          vb.dataset.action = action;
          vb.dataset.tid = task.id;
          vb.dataset.sid = st.id;
          vb.textContent = txt;
          vr.appendChild(vb);
        }
        sub.appendChild(vr);
      }
      card.appendChild(sub);
    }

    // 复盘卡片
    if (task.finishedAt) {
      const retry = task.subtasks.filter(s => s.attempts > 1).length;
      const review = document.createElement('div');
      review.className = 'retro';
      review.textContent = `📋 复盘：${task.subtasks.length} 个子任务全部通过验收，用时 ${Math.round((task.finishedAt - task.createdAt) / 1000)} 秒，期间催办/打回 ${retry} 次，监工经验已入库。`;
      card.appendChild(review);
      if (task.finishedAt > lastFinishedTs) lastFinishedTs = task.finishedAt;
    }

    // 监工日志（最近 6 条 · 活动流样式：时间与内容分层）
    const log = document.createElement('div');
    log.className = 'task-log';
    for (const ev of task.log.slice(-6)) {
      const line = document.createElement('div');
      line.className = ev.kind;
      const ts = document.createElement('span');
      ts.className = 'ts'; ts.textContent = fmtTime(ev.ts);
      line.appendChild(ts);
      line.appendChild(document.createTextNode(' ' + ev.text));
      log.appendChild(line);
    }
    card.appendChild(log);
    box.appendChild(card);
  }

  $('ledgerSpace').textContent = '# ' + curSpace;
  updateLedgerTab(runCount);
  renderHistory(tasks);

  /* 监工 KPI 条（今日 · 全空间）：派单 / 返工 / 催办 / 平均交付——监工的账，一眼看清 */
  {
    const t0 = new Date(); t0.setHours(0, 0, 0, 0);
    const todays = allTasks.filter(t => (t.createdAt || 0) >= t0.getTime());
    const tsubs = todays.flatMap(t => t.subtasks || []);
    const rework = tsubs.filter(s => (s.attempts || 1) > 1).length;
    const urgeN = todays.reduce((n, t) => n + (t.log || []).filter(l => l.kind === 'warn' && (l.text || '').includes('催办')).length, 0);
    const fins = todays.filter(t => t.finishedAt);
    const avgDur = fins.length ? Math.round(fins.reduce((n, t) => n + (t.finishedAt - t.createdAt), 0) / fins.length / 1000) : 0;
    $('ledgerSummary').textContent =
      (tasks.length ? `执行中 ${runCount} · 已通过 ${doneCount}　｜　` : '')
      + `今日派单 ${todays.length} · 返工 ${rework} · 催办 ${urgeN} · 平均交付 ${avgDur}s`;
  }

  /* 主动播报 + 内心 OS：新监工事件驱动咕嘎开口
   * 汇报（正式气泡）：整单完结；内心OS（虚线气泡）：派单/交付/催办/打回/单件通过 */
  const allSubs = tasks.flatMap(t => t.subtasks);
  const allLogs = tasks.flatMap(t => t.log);
  const latestEvent = allLogs.filter(l => l.kind === 'warn' || l.kind === 'good').slice(-1)[0];
  if (allLogs.length > seenLogCount && !sleepOn) {
    const freshAll = allLogs.slice(seenLogCount);
    const warns = freshAll.filter(l => l.kind === 'warn');
    const goods = freshAll.filter(l => l.kind === 'good');
    const infos = freshAll.filter(l => l.kind === 'info');
    const lastWarn = warns[warns.length - 1];
    const lastGood = goods[goods.length - 1];
    const lastInfo = infos[infos.length - 1];
    // 主动开口：完结汇报 > 催办/打回 > 单件通过 > 过程内心OS
    const finalEv = goods.find(l => l.text.includes('全部子任务') || l.text.includes('执行完毕'));
    if (finalEv) {
      lastFinishedTs = Date.now();
      setPet('party');
      say(finalEv.text.replace(/^📋\s*/, '').replace(/^🔍\s*/, ''));   // 正式汇报：say() 内走 TTS 语音，不叠 mp3 音效
    } else {
      // 事件音效（内心OS场景保留短音效，正式汇报走 TTS）
      if (lastWarn) playVoice(lastWarn.text.includes('打回') ? 'return' : 'urge');
      else if (lastGood) playVoice('pass');
      if (lastWarn) {
        setPet('urge');
        toast(lastWarn.text);
        sayInner(lastWarn.text.replace(/^[⏰❌🔍]\s*/, ''));
      } else if (lastGood) {
        sayInner(lastGood.text.replace(/^✅\s*/, ''));
      } else if (lastInfo) {
        sayInner(lastInfo.text.replace(/^📚\s*/, ''));
      }
    }
    seenLogCount = allLogs.length;
  }

  /* 咕嘎六状态状态机（轮询文案用内心OS，且 8 秒内不抢主动播报的话筒） */
  const canAuto = Date.now() - lastSayTs > 8000 && !sleepOn;
  if (Date.now() - lastFinishedTs < 6000) {
    setPet('party');
    setBadge('🎉 完结');
    if (canAuto) say(latestEvent ? latestEvent.text : '任务完结，向少爷交差！');
  } else if (allSubs.some(s => s.status === 'running' && s.overdue)) {
    setPet('urge');
    setBadge('⏰ 催办');
    if (canAuto) sayInner('有子任务落后于计划，盯紧点，先催一轮…');
  } else if (allSubs.some(s => s.status === 'review')) {
    setPet('review');
    setBadge('🔍 验收');
    if (canAuto) sayInner('正在按验收标准逐项核对，字数、格式、数据一个都不放过…');
  } else if (allSubs.some(s => s.status === 'running')) {
    setPet('watch');
    setBadge('🔨 监工');
    if (canAuto) sayInner('工人们正在干活，我盯着呢…');
  } else if (tasks.some(t => !t.finishedAt)) {
    setPet('command');
    setBadge('💬 待命');
    if (canAuto) sayInner('派单指挥中…');
  } else if (petState !== 'idle' && !chatBusy) {
    setPet('idle');
    setBadge('');
    if (!sleepOn) say(PET_IDLE_LINES[0]);
  }
}

/* ---------- 交付物预览（中区文档面板 · Markdown 渲染 · 少爷批示） ---------- */
// 迷你 Markdown 渲染：标题/粗体/行内代码/代码块/列表/引用/分隔线（先整体转义再渲染，防注入）
function renderMD(src) {
  const esc = (s) => s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  const inline = (s) => esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<i>$2</i>');
  const lines = String(src).split(/\r?\n/);
  let html = '', inCode = false, listType = null;
  const closeList = () => { if (listType) { html += '</' + listType + '>'; listType = null; } };
  for (const raw of lines) {
    if (/^```/.test(raw)) { closeList(); html += inCode ? '</code></pre>' : '<pre class="md-pre"><code>'; inCode = !inCode; continue; }
    if (inCode) { html += esc(raw) + '\n'; continue; }
    const line = raw.trimEnd();
    if (!line.trim()) { closeList(); continue; }
    let m;
    if ((m = line.match(/^(#{1,4})\s+(.*)/))) { closeList(); html += `<h${Math.min(m[1].length + 1, 5)}>${inline(m[2])}</h${Math.min(m[1].length + 1, 5)}>`; continue; }
    if (/^(-{3,}|\*{3,})$/.test(line.trim())) { closeList(); html += '<hr>'; continue; }
    if ((m = line.match(/^>\s?(.*)/))) { closeList(); html += '<blockquote>' + inline(m[1]) + '</blockquote>'; continue; }
    if ((m = line.match(/^\s*[-*·]\s+(.*)/))) { if (listType !== 'ul') { closeList(); html += '<ul>'; listType = 'ul'; } html += '<li>' + inline(m[1]) + '</li>'; continue; }
    if ((m = line.match(/^\s*\d+[.、)]\s+(.*)/))) { if (listType !== 'ol') { closeList(); html += '<ol>'; listType = 'ol'; } html += '<li>' + inline(m[1]) + '</li>'; continue; }
    closeList(); html += '<p>' + inline(line) + '</p>';
  }
  closeList();
  if (inCode) html += '</code></pre>';
  return html;
}

// 当前预览的子任务上下文（批示/裁决用）
let annoCtx = null;

async function openArtifact(tid, sid) {
  try {
    const resp = await fetch(`/api/artifact/${tid}/${sid}`, { headers: { Authorization: 'Bearer ' + token } });
    const data = await resp.json();
    if (!resp.ok) throw new Error(data.error || '加载失败');
    annoCtx = { tid, sid, status: data.status, demo: data.demo };
    $('artifactTitle').textContent = '📄 ' + data.name + ' · 交付物';
    $('artifactMeta').textContent = `执行方：${data.executor} ｜ 验收标准：${data.acceptance} ｜ 第 ${data.attempt} 次交付`
      + (data.feedback ? ` ｜ 上一轮意见：${data.feedback.slice(0, 50)}` : '');
    $('artifactBody').innerHTML = renderMD(data.body);
    $('artifactBody').scrollTop = 0;
    $('artifactDownload').href = `/api/artifact/${tid}/${sid}?download=1`;
    // 真机屏幕证据流：本机执行的单展示"豆包被真实操作"的实况截图墙
    // ⚠ <img>/<a> 直连不带 Authorization 头，必须拼 ?t=token 短通道（服务端单独校验+归属校验）
    const evdQ = '?t=' + encodeURIComponent(token);
    const evd = data.evidence || [];
    const wall = $('evdWall');
    if (evd.length) {
      wall.classList.remove('hidden');
      wall.innerHTML = '<div class="evd-title">🖥 真机执行证据（咕嘎本体实时回传的取证截图）</div>' +
        '<div class="evd-strip">' + evd.map(x =>
          `<a class="evd-thumb" href="/api/evidence/${encodeURIComponent(x.file)}${evdQ}" target="_blank" title="${x.tag}"><img loading="lazy" src="/api/evidence/${encodeURIComponent(x.file)}${evdQ}" alt="${x.tag}"><span>${x.tag}</span></a>`).join('') + '</div>';
    } else {
      wall.classList.add('hidden');
      wall.innerHTML = '';
    }
    // 批示栏：有产物且不在执行/验收中即可批示（演示剧本单不可批示）
    const busy = data.status === 'running' || data.status === 'review';
    $('annoBar').classList.toggle('hidden', !!(data.demo || busy));
    $('annoText').value = '';
    // 裁决栏：三次未过验收（error 态）请少爷裁决
    $('verdictBar').classList.toggle('hidden', data.status !== 'error');
    show($('artifactModal'));
  } catch (e) { toast(e.message); }
}

// 划词批注：在产物正文里选中文字 → 自动填进批示框
$('artifactBody').addEventListener('mouseup', () => {
  const sel = String(window.getSelection ? window.getSelection() : '').trim();
  if (sel && !$('annoBar').classList.contains('hidden')) {
    const t = $('annoText');
    t.value = ('「' + sel.slice(0, 80) + '」' + (t.value.replace(/「[^」]*」/g, '').trim() || '，这段需要改：')).replace('，，', '，');
    t.focus();
  }
});

// 暂停/继续本机子任务（进度自动存档，15 分钟内无缝续跑）
async function pauseCtl(btn) {
  btn.disabled = true;
  const act = btn.dataset.act;
  try {
    const resp = await fetch('/api/task-pause', {
      method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ taskId: btn.dataset.tid, stId: btn.dataset.sid, action: act }),
    });
    const d = await resp.json();
    if (!resp.ok) throw new Error(d.error || '操作失败');
    toast(act === 'pause' ? '⏸ 已请求暂停——执行方在当前步骤收尾后停手，进度自动存档' : '▶ 已继续——带着暂停前进度无缝接续');
    pollState();
  } catch (e) { toast(e.message); btn.disabled = false; }
}

// 提交批示（打回重做）
async function sendVerdict(action, comment) {
  if (!annoCtx) return;
  try {
    const resp = await fetch('/api/verdict', {
      method: 'POST', headers: { Authorization: 'Bearer ' + token, 'Content-Type': 'application/json' },
      body: JSON.stringify({ taskId: annoCtx.tid, stId: annoCtx.sid, action, comment: comment || '' }),
    });
    const d = await resp.json();
    if (!resp.ok) throw new Error(d.error || '操作失败');
    if (action === 'approve') { toast('👤 已记录：少爷验收通过'); hide($('artifactModal')); }
    else if (action === 'rework') { toast('👤 批示已回传，工人带意见重做中'); $('annoText').value = ''; }
    else { toast('👥 已换将重派，新工人领单中'); hide($('artifactModal')); }
    pollState();
  } catch (e) { toast(e.message); }
}
$('annoSend').addEventListener('click', () => {
  const c = $('annoText').value.trim();
  if (!c) { toast('先写一句批示（或直接点按钮，咕嘎会要求工人对照标准自查）'); return; }
  sendVerdict('rework', c);
});
$('annoText').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); $('annoSend').click(); }
});
document.querySelectorAll('#verdictBar .v-btn').forEach((b) => {
  b.addEventListener('click', () => {
    const action = b.dataset.action;
    if (action === 'rework') { $('verdictBar').classList.add('hidden'); $('annoBar').classList.remove('hidden'); $('annoText').focus(); return; }
    sendVerdict(action, $('annoText').value.trim());
  });
});
$('artifactClose').addEventListener('click', () => hide($('artifactModal')));
$('artifactModal').addEventListener('click', (e) => { if (e.target === $('artifactModal')) hide($('artifactModal')); });
$('ledgerBox').addEventListener('click', (e) => {
  const btn = e.target.closest('.view-artifact');
  if (btn) { openArtifact(btn.dataset.tid, btn.dataset.sid); return; }
  const vbtn = e.target.closest('.verdict-inline');
  if (vbtn) {
    const action = vbtn.dataset.action;
    if (action === 'approve') sendVerdict('approve', '');
    else if (action === 'reassign') sendVerdict('reassign', '');
    else openArtifact(vbtn.dataset.tid, vbtn.dataset.sid);   // 再打回 → 打开批示框写意见
  }
});

/* ---------- 工人小队画布（大脑 → 工人班组 → 监工验收员） ---------- */
async function openCrew() {
  show($('crewModal'));
  const grid = $('crewGrid');
  grid.innerHTML = '<div class="sc-loading">正在点名工人班组…</div>';
  try {
    const resp = await fetch('/api/crew', { headers: { Authorization: 'Bearer ' + token } });
    const d = await resp.json();
    if (!resp.ok) throw new Error(d.error || '加载失败');
    $('crewAgent').textContent = d.agent
      ? '🖥 本机执行方在线——本机单由您本机的咕嘎本体真实执行'
      : '';
    if (!d.crew.length) {
      grid.innerHTML = '<div class="sc-loading">班组刚成立还没接过单——派一单，工人们就上岗了</div>';
      return;
    }
    grid.innerHTML = '';
    for (const w of d.crew) {
      const card = document.createElement('div');
      card.className = 'crew-card' + (w.busy ? ' busy' : '');
      card.innerHTML = `
        <div class="cc-head"><span class="cc-dot${w.busy ? ' on' : ''}"></span><b>${w.name}</b><span class="cc-type">${w.executor}</span></div>
        <div class="cc-stats">
          <span>接单 ${w.jobs}</span><span>通过率 ${w.passRate}%</span><span class="${w.rework ? 'bad' : ''}">返工 ${w.rework}</span>
        </div>
        <div class="cc-state">${w.busy ? '🔨 在岗干活中' : '☕ 待命'}</div>`;
      grid.appendChild(card);
    }
    // 技能库 + 少爷记忆：咕嘎"越用越熟练、越用越懂你"的可视化
    const extra = $('crewExtra');
    const skills = d.skills || [];
    const mems = d.memories || [];
    extra.innerHTML =
      (skills.length ? `<div class="crew-extra-sec"><b>🧠 咕嘎的技能库（${skills.length} 招，同类目标自动走熟路）</b>` +
        skills.map(s => `<div class="crew-mem">「${s.goal}」<span class="uses">×${s.uses}</span><span class="steps">${s.steps.join(' → ')}</span></div>`).join('') + '</div>' : '') +
      (mems.length ? `<div class="crew-extra-sec"><b>📒 咕嘎记住的少爷偏好（办事时会想着这些）</b>` +
        mems.map(m => `<div class="crew-mem">${m.fact}</div>`).join('') + '</div>' : '');
  } catch (e) { grid.innerHTML = `<div class="sc-loading">${e.message}</div>`; }
}
$('crewBtn').addEventListener('click', openCrew);
$('crewClose').addEventListener('click', () => hide($('crewModal')));
$('crewModal').addEventListener('click', (e) => { if (e.target === $('crewModal')) hide($('crewModal')); });

/* ---------- 双模型同题对比（甲=默认模型，乙=您配置的模型） ---------- */
let cmpGroup = '';
let cmpTimer = 0;
const CMP_STATE_TXT = { pending: '待开工', running: '🔨 干活中', review: '🔍 验收中', done: '✅ 通过', returned: '❌ 打回重做', error: '⚠ 异常' };
function cmpRenderCol(el, task) {
  const subs = (task.subtasks || []).map(s =>
    `<div class="cmp-sub ${s.status}">${CMP_STATE_TXT[s.status] || s.status} · ${s.name}${s.worker ? `（${s.worker}）` : ''}</div>`).join('');
  const fin = task.finishedAt ? `<div class="cmp-fin">🏁 完结 · 用时 ${Math.max(1, Math.round((task.finishedAt - task.createdAt) / 1000))}s</div>` : '';
  const reworks = (task.subtasks || []).filter(s => (s.attempts || 1) > 1).length;
  el.innerHTML = `
    <div class="cmp-col-head">${task.compare.role}组 · ${task.compare.model}</div>
    <div class="cmp-goal">${task.goal}</div>
    ${subs}${fin}
    <div class="cmp-meta">返工 ${reworks} 次</div>`;
}
function cmpTick() {
  if (!cmpGroup || $('cmpModal').classList.contains('hidden')) { cmpTimer = 0; return; }
  const pair = lastAllTasks.filter(t => t.compare && t.compare.groupId === cmpGroup);
  if (pair.length === 2) {
    cmpRenderCol($('cmpColA'), pair.find(t => t.compare.role === '甲') || pair[0]);
    cmpRenderCol($('cmpColB'), pair.find(t => t.compare.role === '乙') || pair[1]);
    const allDone = pair.every(t => t.finishedAt);
    $('cmpJudge').classList.toggle('hidden', !allDone);
  }
  cmpTimer = setTimeout(cmpTick, 2000);
}
$('cmpBtn').addEventListener('click', () => show($('cmpModal')));
$('cmpClose').addEventListener('click', () => { hide($('cmpModal')); clearTimeout(cmpTimer); cmpTimer = 0; });
$('cmpModal').addEventListener('click', (e) => { if (e.target === $('cmpModal')) { hide($('cmpModal')); clearTimeout(cmpTimer); } });
$('cmpStart').addEventListener('click', async () => {
  const goal = $('cmpGoal').value.trim();
  if (!goal) { toast('先输入对比目标'); return; }
  $('cmpStart').disabled = true;
  try {
    const resp = await fetch('/api/compare', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ goal }) });
    const d = await resp.json();
    if (!resp.ok) throw new Error(d.error || '发起失败');
    cmpGroup = d.groupId;
    $('cmpGoal').value = '';
    $('cmpVerdict').classList.add('hidden');
    $('cmpColA').innerHTML = `<div class="cmp-col-head">甲组 · ${d.a.model}</div><div class="sc-loading">拆解中…</div>`;
    $('cmpColB').innerHTML = `<div class="cmp-col-head">乙组 · ${d.b.model}</div><div class="sc-loading">拆解中…</div>`;
    $('cmpArena').classList.remove('hidden');
    $('cmpJudge').classList.add('hidden');
    if (!cmpTimer) cmpTick();
    toast('对比开跑——两班组同题开工，进度实时刷新');
  } catch (e) { toast(e.message); }
  finally { $('cmpStart').disabled = false; }
});
$('cmpJudge').addEventListener('click', async () => {
  if (!cmpGroup) return;
  $('cmpJudge').disabled = true;
  $('cmpJudge').textContent = '🔍 咕嘎裁判评阅两份成果中…';
  try {
    const resp = await fetch('/api/compare/verdict', { method: 'POST', headers: { ...authHeaders(), 'Content-Type': 'application/json' }, body: JSON.stringify({ groupId: cmpGroup }) });
    const d = await resp.json();
    if (!resp.ok) throw new Error(d.error || '裁判失败');
    const v = $('cmpVerdict');
    v.textContent = '⚖ 裁判结论：' + d.verdict;
    v.classList.remove('hidden');
    say('少爷，对比结论出来了——' + d.verdict);   // 结论也语音播报
  } catch (e) { toast(e.message); }
  finally {
    $('cmpJudge').disabled = false;
    $('cmpJudge').textContent = '🏁 两单跑完，请咕嘎当裁判';
  }
});

/* ---------- 模型配置（咕嘎当壳，模型用户自带） ---------- */
async function openLLM() {
  try {
    const resp = await fetch('/api/llm', { headers: { Authorization: 'Bearer ' + token } });
    const d = await resp.json();
    $('llmUrl').value = d.baseUrl || '';
    $('llmKey').value = '';
    $('llmKey').placeholder = d.apiKeyMasked ? `已保存（${d.apiKeyMasked}），留空沿用` : 'sk-…';
    $('llmModel').value = d.model || '';
    $('llmStatus').textContent = d.configured
      ? `当前大脑：${d.model} · 已接入，指挥监工全链路可用`
      : '当前未配置模型，处于演示剧本模式（无真实产物）';
    $('llmStatus').className = 'llm-status ' + (d.configured ? 'ok' : 'off');
    show($('llmModal'));
  } catch (e) { toast(e.message); }
}
$('llmBtn').addEventListener('click', openLLM);
$('llmClose').addEventListener('click', () => hide($('llmModal')));
$('llmModal').addEventListener('click', (e) => { if (e.target === $('llmModal')) hide($('llmModal')); });
$('llmSave').addEventListener('click', async () => {
  const btn = $('llmSave');
  btn.disabled = true; btn.textContent = '测试中…（真实调用一次）';
  try {
    const resp = await fetch('/api/llm', {
      method: 'POST', headers: authHeaders(),
      body: JSON.stringify({ baseUrl: $('llmUrl').value.trim(), apiKey: $('llmKey').value.trim(), model: $('llmModel').value.trim() }),
    });
    const d = await resp.json();
    if (!resp.ok) throw new Error(d.error || '保存失败');
    $('llmStatus').textContent = `✅ 测试通过，已切换大脑：${d.model}。之后派单的拆解/执行/验收/终检都由它驱动`;
    $('llmStatus').className = 'llm-status ok';
    $('llmKey').value = '';
    $('llmKey').placeholder = `已保存（${d.apiKeyMasked}），留空沿用`;
    toast('模型配置已生效');
    say('少爷，新的大脑已接上，指挥监工照旧。');
  } catch (e) {
    $('llmStatus').textContent = '❌ ' + e.message;
    $('llmStatus').className = 'llm-status off';
  } finally { btn.disabled = false; btn.textContent = '保存并测试'; }
});

/* ---------- 本机执行方（配对闭环：网页发单 → 咕嘎本体真机执行） ---------- */
let localMode = false;
let agentOnline = false;

async function refreshAgentStatus() {
  try {
    const r = await fetch('/api/agent/status', { headers: authHeaders() });
    const d = await r.json();
    agentOnline = !!d.online;
  } catch { agentOnline = false; }
  const chip = $('modeLocal');
  chip.classList.toggle('live', agentOnline);
  chip.title = agentOnline
    ? '本机执行方在线——开启后派单由您本机的咕嘎本体真实拉起本机 AI 软件干活'
    : '本机执行方未连接——先在 🩺 自检 里下载咕嘎本体并用配对码绑定';
  const st = $('scExecState');
  if (st) {
    st.textContent = agentOnline ? '本机执行方：在线 ✓' : '本机执行方：未连接';
    st.classList.toggle('on', agentOnline);
  }
}

$('modeLocal').addEventListener('click', async () => {
  await refreshAgentStatus();
  if (!agentOnline) {
    toast('本机执行方未连接——先在 🩺 自检 里配对咕嘎本体');
    openModal('scModal'); runSelfCheck();
    return;
  }
  localMode = !localMode;
  $('modeLocal').classList.toggle('on', localMode);
  toast(localMode ? '🖥 本机执行已开启：接下来派的单由您本机的咕嘎本体真机执行' : '已切回云端执行');
  say(localMode
    ? '少爷，接下来派的单我会远程指挥您本机的 AI 软件真实干活，您在本机就能看到过程，产物照旧回台账验收。'
    : '好的少爷，已切回云端执行方。');
});

$('pairBtn').addEventListener('click', async () => {
  const btn = $('pairBtn');
  btn.disabled = true; btn.textContent = '生成中…';
  try {
    const r = await fetch('/api/pair/create', { method: 'POST', headers: authHeaders() });
    const d = await r.json();
    if (!r.ok) throw new Error(d.error || '生成失败');
    $('pairCode').textContent = d.code;
    $('pairCode').classList.remove('hidden');
    $('pairHint').innerHTML = `三步配对：① 下载上方本体压缩包（免安装，无需 Python）→ ② 在「下载」文件夹解压，进入 guga-desktop 文件夹，双击 <b>GUGA-Agent.exe</b>（⚠️ 别双击 .py 文件）→ ③ 黑窗口里输入配对码 <b>${d.code}</b>，显示"配对成功"即完成绑定`;
    say(`少爷，配对码 ${d.code} 已生成（点它可复制）。下载本体解压后，双击「GUGA-Agent.exe」把码输进去，我们就正式合体了。`);
  } catch (e) { toast(e.message); }
  btn.disabled = false; btn.textContent = '🔗 重新生成';
});

// 点配对码一键复制（免手抄 6 位数字）
$('pairCode').addEventListener('click', () => {
  const code = $('pairCode').textContent.trim();
  if (!code) return;
  (navigator.clipboard ? navigator.clipboard.writeText(code) : Promise.reject())
    .then(() => toast(`配对码 ${code} 已复制`))
    .catch(() => toast(`配对码：${code}`));
});

setInterval(refreshAgentStatus, 15000);
refreshAgentStatus();

/* ---------- 环境自检（云端真实探测 + 本体下载入口） ---------- */
function scRow(name, ok, detail, warn) {
  const mark = ok ? '✅' : (warn ? '🟡' : '❌');
  return `<div class="sc-row"><span class="sc-mark">${mark}</span><b>${name}</b><span class="sc-detail">${detail}</span></div>`;
}
async function runSelfCheck() {
  $('scModal').classList.remove('hidden');
  $('scBody').innerHTML = '<div class="sc-loading">咕嘎正在逐项体检（全部真实探测，约 1~3 秒）…</div>';
  try {
    const resp = await fetch('/api/selfcheck', { headers: authHeaders() });
    const d = await resp.json();
    if (!resp.ok) throw new Error(d.error || '自检失败');
    const rows = [];
    rows.push(scRow('大模型链路',
      d.llm.ok,
      d.llm.ready
        ? `${d.llm.model} · 实测连通 ${d.llm.ms}ms`
        : '未配置模型（⚙ 模型 可自带 Key，当前为演示剧本模式）',
      !d.llm.ready));
    rows.push(scRow('指挥知识库', d.kb.ok,
      `指挥规则 ${d.kb.routing} 条 · 拆解模板 ${d.kb.templates} 套 · 验收底线 ${d.kb.accept} 条`));
    rows.push(scRow('执行引擎', d.engineMode === 'real',
      d.engineMode === 'real'
        ? `真实调度 · 进行中 ${d.running} 单 · 全局限流 2 路并发`
        : '演示剧本模式（未接大模型）',
      d.engineMode !== 'real'));
    rows.push(scRow('产物存储', d.storeOk,
      d.storeOk ? '产物落盘可写 · 台账可下载查看' : '产物目录不可写（云端磁盘只读）'));
    rows.push(scRow('云端服务', true, `已连续运行 ${d.uptimeMin} 分钟 · 本次体检耗时 ${d.costMs || 0}ms`));
    const execOk = !!(d.executor && d.executor.online);
    // 多设备：账号下全部在线本体逐台列出（各是各的电脑、各有各的 AI 软件）
    const devs = (Array.isArray(d.devices) && d.devices.length) ? d.devices
      : (execOk ? [{ device: d.executor.device, path: d.executor.path, ai: d.executor.ai || [], aiFound: d.executor.aiFound, pyver: d.executor.pyver, agent: d.executor.agent, depsOk: d.executor.depsOk }] : []);
    const execPath = (d.executor && d.executor.path) || '';
    const pyver = devs.length === 1 ? (devs[0].pyver || '') : '';
    const depsOk = devs.every(v => v.depsOk !== false);
    const aiNames = devs.map(v => (v.ai || []).join('、')).filter(Boolean).join('；');
    const devList = devs.map(v => `「${v.device}」（${(v.ai || []).join('、') || '未识别到 AI 软件'}${v.path ? ` · 本体在 <b>${v.path}</b>` : ''}${v.agent ? ` · 本体 v${v.agent}` : ''}）`).join('；');
    rows.push(scRow('本机执行方', execOk,
      execOk
        ? `已连接 ${devs.length} 台 · ${devList}${devs.length === 1 && pyver ? ` · Python ${pyver}` : ''}`
        : '未连接（本台电脑）—— 若您之前配对过本体，看下面"找回已有本体"；没有才需要重新下载',
      true));
    if (execOk) {
      rows.push(scRow('设备归属', null,
        '浏览器在哪台电脑打开只是"遥控器"，本体归哪个账号管由配对码决定——想让这台电脑出现在上面列表里，去它上面双击咕嘎本体、输入本账号的配对码重新绑定即可', true));
    }
    // 版本判断（治本：跑旧包 / 换包没重开进程，都会静默跑旧逻辑，用户毫不知情）
    const latest = d.agentLatest || {};
    // 下载区版本号与自检结论同源（都读服务端 guga-version.txt）——
    // 之前这里是写死的 v0.6，跟上面的 v0.9 打架，等于让用户照着旧版本号判断要不要重下
    if (latest.version) {
      const vtxt = 'v' + latest.version;
      const h = $('scDlVer'); if (h) h.textContent = vtxt;
      const b = $('scDlBtn');
      if (b) {
        const stale0 = devs.some(v => (v.agent || '') !== latest.version);
        b.innerHTML = `⬇ 下载咕嘎本体（内测预览版 <b>${vtxt}</b> · 免安装 · 含值守程序与环境自检）`
          + (execOk && stale0 ? ' · <b>⚠ 本机不是这一版，建议重下</b>' : '');
      }
    }
    if (execOk && latest.version) {
      const bad = devs.filter(v => (v.agent || '') !== latest.version);
      if (bad.length) {
        const who = bad.map(v => `${v.device} 跑的是 ${v.agent ? 'v' + v.agent : '更早的包（不上报版本）'}`).join('；');
        rows.push(scRow('本体版本', false,
          `${who}，线上最新 <b>v${latest.version}</b>${latest.builtAt ? `（${latest.builtAt} 打包）` : ''} —— <b>换包三步</b>：① 关掉本体那个黑窗口（进程只认启动那一刻的代码，换包不重开＝还是旧逻辑）② 网页重新下载 guga-desktop.zip 并解压（别复用旧文件夹里的）③ 双击「2-启动咕嘎本体.bat」重开，再回来自检应显示 v${latest.version}`, false));
      } else {
        rows.push(scRow('本体版本', true,
          `v${latest.version}（${latest.builtAt} 打包）· 已是最新`));
      }
    } else if (!execOk && latest.version) {
      rows.push(scRow('本体版本', null,
        `线上最新 v${latest.version}${latest.builtAt ? `（${latest.builtAt} 打包）` : ''} · 本机未连接本体，连上后这里会比对是否最新`, true));
    }
    if (execOk && !depsOk) {
      rows.push(scRow('真机指挥依赖', null,
        '真机操控 AI 软件所需的自动化库还没装齐——配对和派单不受影响，但派"本机执行"单前请重开一次本体启动脚本（会自动走镜像补装），或改派云端单',
        true));
    }
    // 远程指挥：本体在线的电脑是"打工电脑"，同账号任何设备登录都能遥控它真机干活
    if (execOk) {
      rows.push(scRow('远程指挥', true,
        `已就绪 · ${devs.length} 台打工电脑待命（${devs.map(v => v.device).join('、')}）——手机、平板、任何一台电脑登录同账号派单，它们都会真实执行；多台时用派单框旁的设备选择器点名（用手机现在就可以试一单）`));
    }
    // 已有本体找回：网页直接报出当时配对的设备和文件夹，免得用户重复下载
    const offlineAgents = ((d.executor && d.executor.agents) || []).filter(x => !x.online);
    for (const h of offlineAgents) {
      const ago = h.lastSeen ? Math.max(1, Math.round((Date.now() - h.lastSeen) / 60000)) : 0;
      rows.push(scRow('找回已有本体', null,
        `${h.device} · ${ago > 0 ? ago + ' 分钟前活跃 · ' : ''}${h.path ? `本体还在 <b>${h.path}</b>` : '文件夹位置未上报（旧版本本体）'} —— 去该文件夹双击本体程序即可恢复值守，无需重新下载`,
        true));
    }
    $('scBody').innerHTML = rows.join('');
    const execEl = $('scExecState');
    execEl.textContent = execOk ? `本机执行方：在线 · ${devs.length} 台` : '本机执行方：未连接';
    execEl.classList.toggle('on', execOk);
    const greens = [d.llm.ok, d.kb.ok, d.engineMode === 'real', d.storeOk].filter(Boolean).length;
    if (d.llm.ok) say(execOk
      ? `少爷，自检完成：云端 ${greens} 项全绿，大模型链路 ${d.llm.ms}ms；本机执行方在线 ${devs.length} 台——${devs.map(v => `「${v.device}」识别 ${(v.ai || []).length} 个 AI 软件`).join('，')}，可以直接派「打开豆包干活」这类真机任务。`
      : `少爷，云端自检完成：${greens} 项全绿，大模型链路 ${d.llm.ms}ms。注意：这台电脑的本机执行方还没连接，派「打开豆包」这类真机任务前，请先下载下方咕嘎本体并配对。`);
    else say('少爷，云端自检完成。大模型还没接——点右上 ⚙ 模型 填一个 Key，我马上满血。');
  } catch (e) {
    $('scBody').innerHTML = scRow('自检失败', false, e.message);
  }
}

/* ---------- 启动 ---------- */
(function init() {
  // 台账初始状态：记住的偏好 > 手机端默认收起
  const storedLedger = localStorage.getItem('guga_ledger_collapsed');
  setLedger(storedLedger ? storedLedger === '1' : window.innerWidth < 700, false);

  // 星海背景
  try {
    if (window.StarField) {
      starField = window.StarField.create($('starCanvas'), {
        mode: 'full', primary: '#f5a623', deep: '#2a2013', accent: '#ffd98a',
      });
    }
  } catch (e) { starField = null; }

  if (token) {
    fetch('/api/state', { headers: { Authorization: 'Bearer ' + token } })
      .then(r => { if (r.ok) enterMain(); else { token = ''; show($('loginView')); } })
      .catch(() => show($('loginView')));
  } else {
    show($('loginView'));
  }
})();
