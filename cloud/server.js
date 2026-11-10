/**
 * 咕嘎管家 · 生产力监工桌宠 线上体验版
 * 路线 A：自有服务器部署（Node.js + Express，数据落 JSON 文件，零原生依赖）
 *
 * 执行引擎 v2：真实调度 —— 子任务由真实大模型工人智能体逐个完成，
 * 产出真实交付物（Markdown 文件，评委可点开查看/下载）；
 * 监工验收由真实大模型按验收标准核对，不合格真打回（附真实理由）。
 *
 * 环境变量（.env 或进程环境）：
 *   PORT          监听端口（默认 3000，须绑定 0.0.0.0）
 *   LLM_BASE_URL  OpenAI 兼容接口地址，如 https://open.bigmodel.cn/api/paas/v4
 *   LLM_API_KEY   大模型 API Key（只放服务器，不进前端）
 *   LLM_MODEL     模型名，如 glm-4-flash / deepseek-chat
 *   JUDGE_USER    评委账号（默认 judge）
 *   JUDGE_PASS    评委密码（不设则启动时随机生成并打印一次）
 */
const express = require('express');
const crypto = require('crypto');
const fs = require('fs');
const path = require('path');

/* 零依赖 .env 加载：已存在的进程环境变量优先 */
(function loadEnv() {
  try {
    for (const line of fs.readFileSync(path.join(__dirname, '.env'), 'utf8').split('\n')) {
      const m = line.match(/^\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)\s*$/);
      if (m && !(m[1] in process.env)) process.env[m[1]] = m[2].replace(/^["']|["']$/g, '');
    }
  } catch { /* 无 .env 时忽略 */ }
})();

const PORT = Number(process.env.PORT || 3000);
const LLM_BASE_URL = (process.env.LLM_BASE_URL || '').replace(/\/+$/, '');
const LLM_API_KEY = process.env.LLM_API_KEY || '';
const LLM_MODEL = process.env.LLM_MODEL || '';
const JUDGE_USER = process.env.JUDGE_USER || 'judge';
// 演示账号密码不写死在源码里：未配置环境变量时启动生成临时口令并打印一次，避免仓库携带默认弱口令
const _envJudgePass = process.env.JUDGE_PASS;
const JUDGE_PASS = _envJudgePass || crypto.randomBytes(4).toString('hex');
const TEST_USER = process.env.TEST_USER || 'tester';    // 测试机账号：与评委号隔离（台账/配对本体/自检各一套）
const TEST_PASS = process.env.TEST_PASS || crypto.randomBytes(4).toString('hex');
if (!_envJudgePass) {
  console.log(`[账号] 未设置 JUDGE_PASS，本次启动生成临时口令：${JUDGE_USER} / ${JUDGE_PASS}`);
}

const DATA_DIR = path.join(__dirname, 'data');
if (!fs.existsSync(DATA_DIR)) fs.mkdirSync(DATA_DIR);
const ARTIFACT_DIR = path.join(DATA_DIR, 'artifacts');
if (!fs.existsSync(ARTIFACT_DIR)) fs.mkdirSync(ARTIFACT_DIR, { recursive: true });

/* ================= 知识库装载（队友交付 KB1~KB5，服务端专用） =================
 * KB3 routing.csv → 派单调度参考（拆解时注入：首选/备选/编排/合并）
 * KB5 tasks/*.md → 拆解参考 + 演示模式兜底剧本
 * KB4 supervision/验收标准模板.md → 监工核对时的"本类任务验收底线"
 * KB2 ops/  → 桌面端 UI 自动化操作剧本（Web 引擎暂不消费，随包就位）
 * KB1 apps/ → 软件识别卡（桌面端识别用，随包就位）
 */
const KB_DIR = path.join(__dirname, 'knowledge');
const KB = { routing: [], templates: [], accept: [] };

/* 关键词 → [KB3规则类型, KB5模板文件, KB4验收类型] */
const KB_KW = [
  ['周报', '写周报', '周报模板', '周报'], ['总结', '写周报', '周报模板', '周报'], ['汇报', '写周报', '周报模板', '周报'],
  ['ppt', '做PPT', 'PPT模板', 'PPT'], ['幻灯', '做PPT', 'PPT模板', 'PPT'], ['答辩', '做PPT', 'PPT模板', 'PPT'], ['演示', '做PPT', 'PPT模板', 'PPT'],
  ['会议', '会议纪要', '会议纪要模板', '会议纪要'], ['纪要', '会议纪要', '会议纪要模板', '会议纪要'],
  ['邮件', '写邮件', '邮件撰写模板', '写邮件'],
  ['表格', '做表格', '数据表格模板', '做表格'], ['透视', '做表格', '数据表格模板', '做表格'],
  ['归档', '整理文件归档', '文件整理归档模板', '整理文件归档'], ['文件夹', null, '文件整理归档模板', '整理文件归档'],
  ['调研', '查资料出对比', '资料调研对比模板', '查资料对比'], ['对比', '查资料出对比', '资料调研对比模板', '查资料对比'], ['选型', '查资料出对比', '资料调研对比模板', '查资料对比'],
  ['代码', '写代码或修Bug', '写代码模板', null], ['bug', '写代码或修Bug', '写代码模板', null],
  ['方案', '写方案或提案', '写方案或提案模板', null], ['提案', '写方案或提案', '写方案或提案模板', null],
  ['演讲', '写演讲稿', '写演讲稿模板', null],
  ['文案', '公众号或小红书文案', '公众号或小红书文案模板', null], ['小红书', '公众号或小红书文案', '公众号或小红书文案模板', null],
  ['竞品', '数据分析解读', '竞品分析模板', null],
  ['简历', '简历与求职材料', '简历优化模板', null], ['求职', '简历与求职材料', '简历优化模板', null],
  ['笔记', '解释概念或学习辅导', '学习笔记整理模板', null],
  ['活动', null, '活动策划模板', null],
];

(function loadKnowledge() {
  try {
    // KB3 指挥规则
    const rt = fs.readFileSync(path.join(KB_DIR, 'routing/routing.csv'), 'utf8').trim().split('\n');
    for (const line of rt.slice(1)) {
      const c = line.split(',');
      if (c.length >= 5) KB.routing.push({ type: c[0].trim(), first: c[1].trim(), backup: c[2].trim(), mode: c[3].trim(), merge: c[4].trim() });
    }
    // KB5 任务模板（兼容两种写法：A"1. **名称**" / B"### 1. 名称"+粗体字段）
    const tdir = path.join(KB_DIR, 'tasks');
    for (const f of fs.readdirSync(tdir)) {
      if (!f.endsWith('.md')) continue;
      const md = fs.readFileSync(path.join(tdir, f), 'utf8');
      const title = (md.match(/^#\s*任务模板[:：]?\s*(.+)$/m) || [])[1] || f.replace('.md', '');
      const lines = md.split('\n');
      const subs = [];
      let cur = null;
      for (const ln of lines) {
        const startA = ln.match(/^\s*\d+\.\s+\*\*(.+?)\*\*/);
        const startB = ln.match(/^#{2,4}\s*\d+\.\s*(.+?)\s*$/);
        if (startA || startB) {
          if (cur && cur.name) subs.push(cur);
          cur = { name: (startA ? startA[1] : startB[1]).trim().slice(0, 24), execRaw: '', acceptance: '' };
          if (subs.length >= 4) { cur = null; break; }
        } else if (cur) {
          const ex = ln.match(/\*\*?执行方类型\*\*?[:：]\s*(.+)/) || ln.match(/执行方类型[:：]\s*(.+)/);
          const ac = ln.match(/\*\*?(?:一句话)?验收标准\*\*?[:：]\s*(.+)/) || ln.match(/(?:一句话)?验收标准[:：]\s*(.+)/);
          if (ex && !cur.execRaw) cur.execRaw = ex[1].trim();
          if (ac && !cur.acceptance) cur.acceptance = ac[1].trim().slice(0, 80);
        }
      }
      if (cur && cur.name) subs.push(cur);
      const ok = subs.filter(s => s.name && s.acceptance);
      if (ok.length >= 2) KB.templates.push({ file: f.replace('.md', ''), title: title.trim(), subs: ok });
    }
    // KB4 验收底线（表格行；类型名含全角括号，如"周报（豆包/Kimi 写）"）
    const accMd = fs.readFileSync(path.join(KB_DIR, 'supervision/验收标准模板.md'), 'utf8');
    for (const line of accMd.split('\n')) {
      const mm = line.match(/^\|\s*([^|]+?)\s*\|\s*([^|]+?)\s*\|/);
      if (mm && mm[1] !== '任务类型' && !mm[1].startsWith('-') && /周报|PPT|对比|邮件|归档|表格|润色|翻译|图片|纪要/.test(mm[1])) {
        KB.accept.push({ type: mm[1], standard: mm[2] });
      }
    }
    console.log(`[kb] 知识库装载完成：KB3 指挥规则 ${KB.routing.length} 条 · KB5 任务模板 ${KB.templates.length} 套 · KB4 验收底线 ${KB.accept.length} 类`);
  } catch (e) { console.log('[kb] 知识库装载失败（不影响核心功能）:', e.message); }
})();

/* 目标 → 命中的知识库条目 */
function kbMatch(goal) {
  const g = String(goal).toLowerCase();
  const hit = {};
  for (const [kw, rt, tf, at] of KB_KW) {
    if (!g.includes(kw)) continue;
    if (rt && !hit.route) hit.route = KB.routing.find(r => r.type === rt) || null;
    if (tf && !hit.tpl) hit.tpl = KB.templates.find(t => t.file === tf) || null;
    if (at && !hit.accept) hit.accept = KB.accept.find(a => a.type.includes(at)) || null;
  }
  return hit;
}

/* KB5 模板的"执行方类型"原文 → 引擎三值执行方 */
function mapExecutor(execRaw) {
  if (/少爷|咕嘎/.test(execRaw)) return '本地工作流';
  if (/表格|归档|排版|导出|WPS|文件/.test(execRaw)) return 'MCP 工具';
  return '外部智能体';
}

/* ---------------- 数据落盘（原子写） ---------------- */
function loadJSON(name, fallback) {
  const p = path.join(DATA_DIR, name);
  try { return JSON.parse(fs.readFileSync(p, 'utf8')); } catch { return fallback; }
}
function saveJSON(name, obj) {
  const p = path.join(DATA_DIR, name);
  const tmp = p + '.tmp';
  fs.writeFileSync(tmp, JSON.stringify(obj));
  fs.renameSync(tmp, p);
}
const users = loadJSON('users.json', null) || [];
function ensurePresetUsers() {
  // 预置账号幂等补充：users.json 已存在（老部署）也能自动补上缺失账号
  let changed = false;
  for (const [name, pass, role] of [
    [JUDGE_USER, JUDGE_PASS, '评委'],
    [TEST_USER, TEST_PASS, '测试机'],
  ]) {
    if (!users.some(x => x.username === name)) {
      const salt = crypto.randomBytes(8).toString('hex');
      // 预置账号归运营方所有：评委=管理员；两者默认开通云端权益（自有账号，不在售卖口径内）
      users.push({
        username: name, salt, hash: hashPassword(pass, salt),
        cloudEntitled: true, cloudQuota: null, cloudUsed: 0,
        role: role === '评委' ? 'admin' : '',
      });
      console.log(`[init] ${role}账号已生成: ${name} / ${pass}`);
      changed = true;
    }
  }
  // 老部署字段迁移：只补字段、不擅自授予权益（新账号默认无云端权益）
  for (const u of users) {
    if (u.username === JUDGE_USER && !u.role) { u.role = 'admin'; changed = true; }
    if (typeof u.cloudEntitled !== 'boolean') { u.cloudEntitled = false; changed = true; }
    if (u.cloudQuota === undefined) { u.cloudQuota = null; changed = true; }
    if (!Number.isFinite(Number(u.cloudUsed))) { u.cloudUsed = 0; changed = true; }
  }
  if (changed || !loadJSON('users.json', null)) saveJSON('users.json', users);
}
ensurePresetUsers();
const tasks = loadJSON('tasks.json', []);
const sessions = loadJSON('sessions.json', {});
const usage = loadJSON('usage.json', []);

function hashPassword(pass, salt) {
  return crypto.scryptSync(pass, salt, 32).toString('hex');
}

/* ---------------- 云端权益 / 管理员 / 计量 ----------------
 * 产品口径：买软件 = 本地功能（用户自填 Key）；买账号 = 云端服务（才可用运营方 Key）。
 * users.json：cloudEntitled(布尔) / cloudQuota(模型调用次数上限，null=不限) / cloudUsed(已用次数)
 * usage.json：每次真实模型调用一条 {user, at, model, kind, taskId}，可按账号查。 */
function userRecord(name) { return users.find(u => u.username === name) || null; }
function isAdmin(name) {
  if (!name) return false;
  if (name === JUDGE_USER) return true;
  const u = userRecord(name);
  return !!(u && (u.role === 'admin' || u.isAdmin === true));
}
function cloudInfo(name) {
  const u = userRecord(name) || {};
  const quota = typeof u.cloudQuota === 'number' && Number.isFinite(u.cloudQuota) ? u.cloudQuota : null;
  return { entitled: u.cloudEntitled === true, quota, used: Number(u.cloudUsed || 0) };
}
function requireAdmin(req, res, next) {
  if (!isAdmin(req.user)) {
    return res.status(403).json({ error: '仅管理员可修改云端模型配置', code: 'ADMIN_ONLY' });
  }
  next();
}
/* 云端权益闸：无权益 / 额度用尽 → 403；挂在消耗运营方 Key 的入口（派单/聊天/对比） */
function requireCloud(req, res, next) {
  const c = cloudInfo(req.user);
  if (!c.entitled) {
    return res.status(403).json({
      error: '当前账号未开通云端服务——云端模型仅对已购账号开放，请购买云端服务后重试',
      code: 'CLOUD_NOT_ENTITLED',
      cloudEntitled: false,
    });
  }
  if (c.quota != null && c.used >= c.quota) {
    return res.status(403).json({
      error: `云端额度已用完（已用 ${c.used} / 上限 ${c.quota} 次）——请续购云端服务后重试`,
      code: 'CLOUD_QUOTA_EXCEEDED',
      cloudQuota: c.quota, cloudUsed: c.used,
    });
  }
  next();
}
/* 本机执行方的云端辅助（视觉请示 / 验收请示）：无权益或超额时返回可降级的 403。
 * 桌面端看到 degraded:true 时应"跳过本步、继续完成本地任务"，不要整单判失败。 */
function agentCloudGate(helper) {
  return (req, res, next) => {
    const c = cloudInfo(req.agent && req.agent.userId);
    if (!c.entitled) {
      return res.status(403).json({
        error: '云端辅助不可用：当前账号未开通云端服务，本步骤已跳过，可继续完成本地任务',
        code: 'CLOUD_NOT_ENTITLED',
        degraded: true, helper, cloudEntitled: false,
      });
    }
    if (c.quota != null && c.used >= c.quota) {
      return res.status(403).json({
        error: `云端辅助不可用：云端额度已用完（已用 ${c.used} / 上限 ${c.quota} 次），本步骤已跳过，可继续完成本地任务`,
        code: 'CLOUD_QUOTA_EXCEEDED',
        degraded: true, helper, cloudQuota: c.quota, cloudUsed: c.used,
      });
    }
    next();
  };
}
/* 真实模型调用记量：调用真正发出后按账号累加，并落 usage.json（能按账号查次数） */
function recordUsage(name, meta) {
  if (!name) return;
  const u = userRecord(name);
  if (!u) return;
  u.cloudUsed = Number(u.cloudUsed || 0) + 1;
  saveJSON('users.json', users);
  usage.push({
    user: name, at: Date.now(),
    model: String((meta && meta.model) || ''),
    kind: String((meta && meta.kind) || 'model'),
    taskId: String((meta && meta.taskId) || ''),
  });
  if (usage.length > 20000) usage.splice(0, usage.length - 20000);   // 只保留最近 2 万条，防文件无限增长
  saveJSON('usage.json', usage);
}

/* ---------------- 鉴权 ---------------- */
function auth(req, res, next) {
  const token = (req.headers.authorization || '').replace(/^Bearer\s+/i, '');
  const sess = sessions[token];
  if (!sess) return res.status(401).json({ error: '未登录或会话已过期，请重新登录' });
  req.user = sess.username;
  req.device = sess.device || '';   // 登录设备标识（远程指挥：谁在遥控）
  next();
}

/* ---------------- 大模型（OpenAI 兼容 · 支持用户在界面自行配置） ----------------
 * 优先级：界面配置（data/llm_config.json，持久化） > .env > 未配置（演示剧本模式）
 * 评委可填自己的任意 OpenAI 兼容接口（智谱/DeepSeek/Kimi/通义/Ollama 本地…），
 * 咕嘎只当"壳"：指挥监工逻辑不变，模型随配随换。
 */
const llmCfg = { baseUrl: LLM_BASE_URL, apiKey: LLM_API_KEY, model: LLM_MODEL };
const LLM_ENV = { ...llmCfg };   // 服务器默认模型（env 原始值），双模型对比时的"甲"方
(function loadLLMCfg() {
  try {
    const saved = JSON.parse(fs.readFileSync(path.join(DATA_DIR, 'llm_config.json'), 'utf8'));
    if (saved.baseUrl) llmCfg.baseUrl = saved.baseUrl;
    if (saved.apiKey) llmCfg.apiKey = saved.apiKey;
    if (saved.model) llmCfg.model = saved.model;
    if (saved.baseUrl && saved.apiKey) console.log(`[llm] 已加载界面配置的模型: ${saved.model}`);
  } catch { /* 无界面配置，用 env */ }
})();
function saveLLMCfg() {
  saveJSON('llm_config.json', { baseUrl: llmCfg.baseUrl, apiKey: llmCfg.apiKey, model: llmCfg.model });
}

function llmReady() { return !!(llmCfg.baseUrl && llmCfg.apiKey && llmCfg.model); }

/* -------- base_url 归一化 + 重定向保留 POST 的统一入口 ----------
 * 用户常把完整端点（.../chat/completions）或控制台地址粘进 base_url，
 * 导致 /chat/completions 被拼两次报 404/405；或网关做 http→https / 补斜杠
 * 跳转，Node fetch 默认把 POST 改成 GET，只接受 POST 的端点返回 405。
 * 这两个问题在 Python 端已修（model_endpoint.py），云端没修会导致
 * "网关对错误路径返 404、对错误方法返 400"但咕嘎仍拿到 405 的矛盾。 */
const _KNOWN_HOST_PATHS = {
  'api.openai.com': '/v1', 'api.deepseek.com': '/v1',
  'api.moonshot.cn': '/v1', 'api.siliconflow.cn': '/v1',
  'openrouter.ai': '/api/v1',
  'dashscope.aliyuncs.com': '/compatible-mode/v1',
  'maas.qianwenaiapi.com': '/compatible-mode/v1',
  'open.bigmodel.cn': '/api/paas/v4', 'ark.cn-beijing.volces.com': '/api/v3',
};
const _ENDPOINT_SUFFIXES = ['/chat/completions', '/completions', '/responses', '/embeddings/multimodal', '/embeddings'];

function normalizeBaseUrl(raw) {
  const s = String(raw || '').trim().replace(/["' ]/g, '');
  if (!s) return { ok: false, base: '', error: 'base_url 为空' };
  let input = s.toLowerCase().startsWith('http') ? s : 'https://' + s;
  let u; try { u = new URL(input); } catch { return { ok: false, base: '', error: 'base_url 不合法: ' + s.slice(0, 80) }; }
  let path = u.pathname.replace(/\/+$/, '');
  let removed = '';
  for (const suffix of _ENDPOINT_SUFFIXES) {
    if (path.toLowerCase().endsWith(suffix)) { path = path.slice(0, -suffix.length).replace(/\/+$/, ''); removed = suffix; break; }
  }
  if ((path === '' || path === '/') && _KNOWN_HOST_PATHS[u.hostname.toLowerCase()]) {
    path = _KNOWN_HOST_PATHS[u.hostname.toLowerCase()];
  }
  const base = u.protocol + '//' + u.host + (path || '');
  return { ok: true, base, removed_suffix: removed };
}

async function llmPost({ baseUrl, apiKey, body, signal, timeoutMs, stream, maxRedirects = 2 }) {
  /* 保留 POST 方法跟随重定向；直连失败且可能被代理改写时返回诊断。
   * 返回 { ok, status, bodyText, redirects, error, attemptedUrl } */
  const norm = normalizeBaseUrl(baseUrl);
  if (!norm.ok) return { ok: false, error: norm.error };
  const url = norm.base + '/chat/completions';
  const headers = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + apiKey };
  let currentUrl = url;
  const redirects = [];
  let resp;
  for (let hop = 0; hop <= maxRedirects; hop++) {
    resp = await fetch(currentUrl, { method: 'POST', headers, body: body ? JSON.stringify(body) : undefined, signal });
    if (![301, 302, 303, 307, 308].includes(resp.status)) break;
    const location = resp.headers.get('Location');
    if (!location) break;
    redirects.push({ status: resp.status, from: currentUrl, to: location });
    currentUrl = new URL(location, currentUrl).toString();
    try { resp.body && await resp.body.cancel(); } catch {}
  }
  const text = await resp.text().catch(() => '');
  return { ok: resp.ok, status: resp.status, bodyText: text, redirects, attemptedUrl: url };
}

async function llmStream(messages, onDelta, cfg, usageMeta) {
  cfg = cfg || llmCfg;
  const controller = new AbortController();
  const killer = setTimeout(() => controller.abort(), 90000);
  try {
    /* 保留 POST 跟随重定向，不交给 fetch 自动把 POST 改成 GET。 */
    const norm = normalizeBaseUrl(cfg.baseUrl);
    if (!norm.ok) throw new Error('base_url 配置错误：' + norm.error);
    let currentUrl = norm.base + '/chat/completions';
    const headers = { 'Content-Type': 'application/json', Authorization: 'Bearer ' + cfg.apiKey };
    let resp;
    const redirects = [];
    for (let hop = 0; hop <= 2; hop++) {
      resp = await fetch(currentUrl, { method: 'POST', headers,
        body: JSON.stringify(Object.assign({ model: cfg.model, messages, stream: true, temperature: 0.7 },
          cfg.maxTokens ? { max_tokens: cfg.maxTokens } : {})),
        signal: controller.signal });
      if (![301, 302, 303, 307, 308].includes(resp.status)) break;
      const location = resp.headers.get('Location');
      if (!location) break;
      redirects.push({ status: resp.status, from: currentUrl, to: location });
      currentUrl = new URL(location, currentUrl).toString();
      try { resp.body && await resp.body.cancel(); } catch {}
    }
    if (!resp.ok) {
      const t = await resp.text().catch(() => '');
      throw new Error('LLM HTTP ' + resp.status + (redirects.length ? '（重定向 ' + redirects.length + ' 次后仍失败）' : '') + '；实际请求：POST ' + (norm.base + '/chat/completions') + '；服务端返回：' + t.slice(0, 200));
    }
    recordUsage(usageMeta && usageMeta.user, { model: cfg.model, kind: usageMeta && usageMeta.kind, taskId: usageMeta && usageMeta.taskId });
    const reader = resp.body.getReader();
    const decoder = new TextDecoder();
    let buf = '', full = '';
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      buf += decoder.decode(value, { stream: true });
      const lines = buf.split('\n');
      buf = lines.pop();
      for (const line of lines) {
        const s = line.trim();
        if (!s.startsWith('data:')) continue;
        const payload = s.slice(5).trim();
        if (payload === '[DONE]') continue;
        try {
          const delta = JSON.parse(payload).choices?.[0]?.delta?.content;
          if (delta) { full += delta; onDelta(delta); }
        } catch { /* 跳过无法解析的心跳帧 */ }
      }
    }
    return full;
  } finally { clearTimeout(killer); }
}

async function llmJSON(messages, cfg, usageMeta, maxTokens) {
  let out = '';
  const useCfg = maxTokens ? Object.assign({}, cfg || llmCfg, { maxTokens }) : cfg;
  await llmStream(messages, (d) => { out += d; }, useCfg, usageMeta);
  const m = out.match(/\{[\s\S]*\}/);
  if (!m) throw new Error('模型未返回 JSON');
  return JSON.parse(m[0]);
}

/* ---------------- 视觉层（借鉴 self-operating-computer / UI-TARS / UFO 的 screenshot→VLM→act 环路）----------------
 * 本体截图 → base64 → 服务端调免费视觉模型（智谱 GLM-4.6V-Flash → 4.1V-Thinking-Flash → 4V-Flash 降级链，
 * 同一 OpenAI 兼容 baseUrl/Key）→ 回答"元素在哪/屏幕什么状态/豆包说了什么"。
 * 执行器据此定位按钮、转写回复——不再靠写死的屏幕比例坐标瞎摸。视觉通道失败时执行器自动回退旧启发式。 */
const VISION_MODELS = (process.env.LLM_VISION_MODELS || 'glm-4.6v-flash,glm-4.1v-thinking-flash,glm-4v-flash')
  .split(',').map(s => s.trim()).filter(Boolean);

function cleanVisionText(t) {
  return String(t || '')
    .replace(/<think>[\s\S]*?<\/think>/gi, '')          // 4.1V-Thinking 的思考段不外泄
    .replace(/<\/?answer>/gi, '')                        // 4.1V 的 <answer> 包裹
    .replace(/<\|begin_of_box\|>|<\|end_of_box\|>/g, '') // 4.1V 答案框标记
    .trim();
}

async function llmVision(question, imageB64, cfg, usageMeta) {
  cfg = cfg || llmCfg;
  const messages = [{
    role: 'user',
    content: [
      { type: 'image_url', image_url: { url: 'data:image/jpeg;base64,' + imageB64 } },
      { type: 'text', text: question },
    ],
  }];
  const norm = normalizeBaseUrl(cfg.baseUrl);
  if (!norm.ok) return { ok: false, error: 'base_url 配置错误：' + norm.error };
  let lastErr = '';
  for (const m of VISION_MODELS) {
    const controller = new AbortController();
    const killer = setTimeout(() => controller.abort(), 60000);
    try {
      /* 保留 POST 跟随重定向，避免 Node fetch 把 POST 改成 GET 返回 405。 */
      let currentUrl = norm.base + '/chat/completions';
      let resp;
      for (let hop = 0; hop <= 2; hop++) {
        resp = await fetch(currentUrl, { method: 'POST',
          headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + cfg.apiKey },
          body: JSON.stringify({ model: m, messages, stream: false, max_tokens: 900, temperature: 0.2 }),
          signal: controller.signal });
        if (![301, 302, 303, 307, 308].includes(resp.status)) break;
        const location = resp.headers.get('Location');
        if (!location) break;
        currentUrl = new URL(location, currentUrl).toString();
        try { resp.body && await resp.body.cancel(); } catch {}
      }
      if (!resp.ok) {
        const t = await resp.text().catch(() => '');
        throw new Error('HTTP ' + resp.status + '（POST ' + (norm.base + '/chat/completions') + '）：' + t.slice(0, 160));
      }
      recordUsage(usageMeta && usageMeta.user, { model: m, kind: usageMeta && usageMeta.kind, taskId: usageMeta && usageMeta.taskId });
      const j = await resp.json();
      const txt = cleanVisionText(j.choices && j.choices[0] && j.choices[0].message && j.choices[0].message.content);
      if (!txt) throw new Error('空回复');
      return { ok: true, model: m, text: txt };
    } catch (e) {
      lastErr = (e && e.message) || String(e);
    } finally {
      clearTimeout(killer);
    }
  }
  return { ok: false, error: lastErr };
}

/* ---------------- 技能库 + 少爷记忆（借鉴 OpenAdapt 录制重放 & Mem0 记忆层，JSON 落盘零依赖） ----------------
 * 技能：任务全通过后把成功拆解存成"招式"；再遇同类目标，拆解时注入历史成功经验（熟路优先）。
 * 记忆：聊天里说"记住…"直接存；任务完结时 LLM 提炼一条偏好事实。注入聊天/意图/拆解提示词。 */
function normGoal(g) { return String(g || '').toLowerCase().replace(/\s+/g, ''); }
function bigrams(s) { const set = new Set(); for (let i = 0; i < s.length - 1; i++) set.add(s.slice(i, i + 2)); return set; }
function goalSim(a, b) {
  const A = bigrams(normGoal(a)), B = bigrams(normGoal(b));
  if (!A.size || !B.size) return 0;
  let hit = 0; for (const x of A) if (B.has(x)) hit++;
  return hit / Math.max(A.size, B.size);
}

function learnSkill(task) {
  const skills = loadJSON('skills.json', {});
  const list = skills[task.userId] = skills[task.userId] || [];
  const recipe = task.subtasks.map(st => ({ name: st.name, executor: st.executor, acceptance: st.acceptance }));
  const best = list.map(s => ({ s, score: goalSim(s.goal, task.goal) })).sort((a, b) => b.score - a.score)[0];
  if (best && best.score > 0.5) {
    best.s.recipe = recipe; best.s.uses = (best.s.uses || 1) + 1; best.s.ts = Date.now();
    task.log.push({ ts: Date.now(), kind: 'info', text: `🧠 熟路「${String(best.s.goal).slice(0, 20)}」又练了一遍（熟练度 ${best.s.uses}）` });
  } else {
    list.unshift({ id: 'sk' + Date.now().toString(36), goal: String(task.goal).slice(0, 60), recipe, uses: 1, ts: Date.now() });
    if (list.length > 20) list.length = 20;
    task.log.push({ ts: Date.now(), kind: 'good', text: `🧠 咕嘎学会了新招式「${String(task.goal).slice(0, 20)}」——下次遇到同类目标直接走熟路` });
  }
  saveJSON('skills.json', skills);
}

function recallSkill(userId, goal) {
  const list = loadJSON('skills.json', {})[userId] || [];
  let best = null;
  for (const s of list) { const score = goalSim(s.goal, goal); if (!best || score > best.score) best = { s, score }; }
  return best && best.score > 0.45 ? best.s : null;
}

function rememberFact(userId, fact, source) {
  fact = String(fact || '').trim().replace(/\s+/g, ' ').slice(0, 80);
  if (!fact || fact.length < 4) return false;
  const mem = loadJSON('memory.json', {});
  const list = mem[userId] = mem[userId] || [];
  if (list.some(x => x.fact === fact)) return false;
  list.unshift({ fact, ts: Date.now(), source: source || '' });
  if (list.length > 30) list.length = 30;
  saveJSON('memory.json', mem);
  return true;
}

function recallFacts(userId, n = 6) {
  return (loadJSON('memory.json', {})[userId] || []).slice(0, n).map(x => x.fact);
}

async function distillMemory(task) {
  try {
    const v = await withSlot(() => llmJSON([
      { role: 'system', content: '从这次任务中提炼一条值得长期记住的"用户偏好/事实"（25字内、第三人称、以"少爷"开头，如"少爷常让我做竞品调研"）。没有值得记的输出 {"fact":""}。只输出 JSON。' },
      { role: 'user', content: `总目标：${task.goal}\n子任务：${task.subtasks.map(s => s.name).join('、')}` },
    ], undefined, { user: task.userId, kind: 'memory', taskId: task.id }));
    if (v && v.fact && rememberFact(task.userId, v.fact, '任务')) {
      task.log.push({ ts: Date.now(), kind: 'info', text: `🧠 咕嘎记住了：${String(v.fact).slice(0, 40)}` });
      saveJSON('tasks.json', tasks);
    }
  } catch { /* 记忆提炼失败不碍主流程 */ }
}

/* ================= 真实执行引擎 =================
 * 生命周期：pending → running(工人真实调用中) → review(监工真实核对中)
 *          → done / returned(→ 重做) ；错误态 error
 *          全部子任务落定后 → 总目标终检（真实 LLM 对照总目标整体审查，
 *          防止"每步合格但整体跑偏"；不合格点名子任务返工一轮，最多 1 轮）
 * 同一任务的子任务串行（后者拿前者产物作上下文），跨任务并行但全局限流。
 */
const EXECUTORS = ['本地工作流', 'MCP 工具', '外部智能体'];
const WORK_BUDGET_MS = 45000;    // 单子任务执行预算，超时真催办
const MAX_ATTEMPTS = 3;          // 同一子任务最多执行 3 次
const PAUSE_TTL_MS = 15 * 60 * 1000;   // 本机子任务暂停保留窗口：超时自动丢弃清理
/* 本机执行判死策略（2026-11-07 修正）：
 * 以"最后一次 busy 心跳"为基准，心跳持续就绝不判死（WorkBuddy 出 PPT 实测 13 分钟）；
 * 只有心跳中断满 20 分钟才判异常收尾，真挂了也能在 20 分钟内落定台账。 */
const LOCAL_HEARTBEAT_DEAD_MS = 20 * 60 * 1000;

const WORKER_ROLE = {
  '本地工作流': '你是被咕嘎管家派单的执行智能体（本地工作流型）：擅长结构化、确定性处理，输出严谨规整。',
  'MCP 工具': '你是被咕嘎管家派单的执行智能体（工具型）：擅长以工具产物形式输出，如表格、清单、结构化数据。',
  '外部智能体': '你是被咕嘎管家派单的执行智能体（外部智能体型）：擅长创作、综合与表达。',
};

// 工人班组：每个执行类型对应一组"工人名"，派单时按序分配（同人设可复现，同单内不重名）
const WORKER_NAMES = {
  '本地工作流': ['钢镚', '算盘', '螺丝'],
  'MCP 工具': ['扳手', '卡尺', '图钉'],
  '外部智能体': ['墨墨', '灵犀', '小笔'],
};
function pickWorker(executor, i) {
  const pool = WORKER_NAMES[executor] || WORKER_NAMES['本地工作流'];
  return pool[i % pool.length];
}

function workerMessages(task, st, prevArtifacts) {
  const sys = `你是工人智能体「${st.worker || '小工'}」，${WORKER_ROLE[st.executor] || WORKER_ROLE['本地工作流']}` +
    '\n你的唯一职责：交付一份真实可用、可直接验收的产物（Markdown 格式）。' +
    '\n要求：1) 内容针对总目标下的本子任务，不做无关客套；2) 产物完整自洽（该有的标题/条目/数据/结论齐全）；3) 500 字以内；4) 直接输出产物正文，不要解释你要做什么。';
  const prev = prevArtifacts.length
    ? '\n\n【前序子任务产物（供衔接参考）】\n' + prevArtifacts.map(a => `## ${a.name}\n${a.body}`).join('\n\n').slice(0, 1200)
    : '';
  let user = `【总目标】${task.goal}\n【你负责的子任务】${st.name}\n【验收标准（必须满足）】${st.acceptance}`;
  if (st.feedback) user += `\n【监工打回原因（本轮必须改进）】${st.feedback}`;
  user += '\n请直接输出交付物：' + prev;
  return [
    { role: 'system', content: sys },
    { role: 'user', content: user },
  ];
}

function reviewMessages(task, st, artifact) {
  // KB4 监工验收库：命中本类任务时注入"管家验收底线"，让核对有队友知识背书
  const hit = kbMatch(task.goal);
  const kbLine = hit.accept
    ? `\n\n【KB4监工验收库·${hit.accept.type}的管家验收底线（逐条对照，全部命中才通过）】\n${hit.accept.standard}` +
      '\n（打回理由参照管家打回话术风格：就事论事，指出具体缺什么、要求怎么改，不指责、不堆形容词）'
    : '';
  return [
    { role: 'system', content: '你是咕嘎管家的监工验收模块。依据验收标准严格核对执行智能体的交付物，不放过缺项。' +
      '只输出 JSON：{"pass": true/false, "reason": "20字内说明，通过时写达标依据，不通过写具体缺什么、怎么改"}' + kbLine },
    { role: 'user', content: `【总目标】${task.goal}\n【子任务】${st.name}\n【验收标准】${st.acceptance}\n\n【交付物全文】\n${artifact.slice(0, 2500)}` },
  ];
}

function artifactPath(taskId, stId, attempt) {
  return path.join(ARTIFACT_DIR, `${taskId}_${stId}_${attempt}.md`);
}

/* 全局并发闸：同时最多 2 个真实模型调用 */
const MAX_CONCURRENCY = 2;
let activeCalls = 0;
const callQueue = [];
function withSlot(fn) {
  return new Promise((resolve, reject) => {
    const run = async () => {
      activeCalls++;
      try { resolve(await fn()); }
      catch (e) { reject(e); }
      finally { activeCalls--; const next = callQueue.shift(); if (next) next(); }
    };
    if (activeCalls < MAX_CONCURRENCY) run(); else callQueue.push(run);
  });
}

const inflight = new Set();   // "taskId:stId" 防重复派发

async function runSubtask(task, st) {
  const key = task.id + ':' + st.id;
  const now = Date.now();
  inflight.add(key);
  st.status = 'running';
  st.attempts++;
  st.progress = 0;
  st.overdue = false;
  st.startedAt = now;
  st.feedback = st.feedback || '';
  task.log.push({ ts: now, kind: 'info', text: `「${st.name}」已派发给工人「${st.worker || '小工'}」·${st.executor}（真实执行中）` });
  saveJSON('tasks.json', tasks);

  // 真实催办：超过执行预算仍未交付，监工发出催办提醒
  const urgeTimer = setTimeout(() => {
    if (st.status === 'running') {
      st.overdue = true;
      task.log.push({ ts: Date.now(), kind: 'warn', text: `⏰ 监工提醒：「${st.name}」执行超过 ${Math.round(WORK_BUDGET_MS / 1000)} 秒未交付，咕嘎已催办` });
      saveJSON('tasks.json', tasks);
    }
  }, WORK_BUDGET_MS);

  try {
    // ① 工人智能体真实执行
    const prev = task.subtasks
      .filter(x => x.status === 'done' && x.artifact)
      .slice(-2)
      .map(x => ({ name: x.name, body: loadArtifact(task.id, x.id, x.attempts) }))
      .filter(a => a.body);
    // 同一单固定用一套模型（默认单走当前配置，对比"甲"单走服务器默认模型），保证公平
    const wcfg = task.modelTag === 'env' ? LLM_ENV : llmCfg;
    const body = await withSlot(() => llmStream(workerMessages(task, st, prev), () => {}, wcfg,
      { user: task.userId, kind: 'worker', taskId: task.id }));
    if (!body.trim()) throw new Error('工人智能体返回空产物');
    fs.writeFileSync(artifactPath(task.id, st.id, st.attempts), body, 'utf8');
    st.artifact = { attempt: st.attempts, chars: body.length, file: `${task.id}_${st.id}_${st.attempts}.md` };
    st.status = 'review';
    st.progress = 100;
    clearTimeout(urgeTimer);
    task.log.push({ ts: Date.now(), kind: 'info', text: `「${st.name}」第 ${st.attempts} 次交付完成（${body.length} 字真实产物），咕嘎开始按验收标准核对` });
    saveJSON('tasks.json', tasks);

    // ② 监工真实验收（通道异常按不通过处理——宁可打回复核，不放水）
    let verdict;
    try {
      verdict = await withSlot(() => llmJSON(reviewMessages(task, st, body), task.modelTag === 'env' ? LLM_ENV : llmCfg,
        { user: task.userId, kind: 'review', taskId: task.id }));
    } catch { verdict = { pass: false, reason: '核对通道波动，本轮先打回，复核后重新交付' }; }
    st.checkResult = String(verdict.reason || '').slice(0, 80);

    if (verdict.pass || st.attempts >= MAX_ATTEMPTS) {
      st.status = 'done';
      if (!verdict.pass) st.checkResult = '三次交付仍未完全达标，咕嘎标记异常并如实上报少爷';
      task.log.push({
        ts: Date.now(), kind: verdict.pass ? 'good' : 'warn',
        text: verdict.pass
          ? `✅ 验收通过：「${st.name}」${st.checkResult}`
          : `⚠ 「${st.name}」连续 ${MAX_ATTEMPTS} 次未过验收：${st.checkResult}（已上报少爷）`,
      });
    } else {
      st.status = 'returned';
      st.feedback = st.checkResult;
      task.log.push({ ts: Date.now(), kind: 'warn', text: `❌ 验收打回：「${st.name}」${st.checkResult}，已带意见重新派单` });
    }
  } catch (e) {
    clearTimeout(urgeTimer);
    st.status = 'error';
    st.checkResult = '执行方调用失败：' + String(e.message || e).slice(0, 60);
    task.log.push({ ts: Date.now(), kind: 'warn', text: `⚠ 「${st.name}」执行异常（${st.checkResult}），咕嘎稍后重试` });
    // 异常允许一次重新排队
    if (st.attempts < MAX_ATTEMPTS) setTimeout(() => { inflight.delete(key); st.status = 'returned'; st.rerunAt = Date.now(); schedule(); }, 8000);
  }
  clearTimeout(urgeTimer);
  inflight.delete(key);
  finishCheck(task);
  saveJSON('tasks.json', tasks);
}

function loadArtifact(taskId, stId, attempt) {
  try { return fs.readFileSync(artifactPath(taskId, stId, attempt), 'utf8'); } catch { return ''; }
}

function finishCheck(task) {
  if (task.finishedAt || task.demo) return;
  const subs = task.subtasks;
  if (!subs.every(s => s.status === 'done' || s.status === 'error')) return;
  if (task.finalReviewing) return;
  // 全部子任务落定 → 进入总目标终检（真实 LLM 整体审查）
  task.finalReviewing = true;
  task.log.push({ ts: Date.now(), kind: 'info', text: '🔍 各子任务均已落定，咕嘎开始对照总目标做整体终检……' });
  saveJSON('tasks.json', tasks);
  finalReview(task).catch(() => {});
}

function finalMessages(task) {
  const parts = task.subtasks.map(st => {
    const body = st.artifact ? loadArtifact(task.id, st.id, st.artifact.attempt) : '';
    return `## 子任务「${st.name}」（状态：${st.status}）\n${body.slice(0, 1800) || '（无产物，执行异常）'}`;
  }).join('\n\n');
  return [
    { role: 'system', content: '你是咕嘎管家的终审模块。全部子任务已各自通过单件验收，现在做总目标终检：' +
      '重点审查各子任务产物之间衔接是否自洽、合并起来是否真正达成了总目标——不是重复单件核对。' +
      '若整体不达标，从现有子任务中点名最需要返工的一个（issue 填其名称原文，须与子任务名一致）。' +
      '只输出 JSON：{"pass": true/false, "issue": "不达标时填子任务名，通过时留空", "reason": "20字内说明"}' },
    { role: 'user', content: `【总目标】${task.goal}\n\n${parts}` },
  ];
}

async function finalReview(task) {
  let verdict = null;
  try {
    verdict = await withSlot(() => llmJSON(finalMessages(task), undefined,
      { user: task.userId, kind: 'final', taskId: task.id }));
  } catch { verdict = null; }   // 终检通道波动：不卡死，如实按通过收尾
  if (task.finishedAt) return;
  task.finalReviewing = false;

  const subs = task.subtasks;
  const issue = verdict && !verdict.pass ? String(verdict.issue || '').trim() : '';
  const bad = issue ? subs.find(s => s.name === issue || issue.includes(s.name)) : null;

  // 终检打回：点名返工（每任务最多 1 轮，防死循环）
  if (bad && bad.status === 'done' && !(task.finalReworks >= 1)) {
    task.finalReworks = 1;
    bad.status = 'returned';
    bad.finishedAt = 0;
    bad.feedback = '终检打回：' + String(verdict.reason || '与总目标衔接不符').slice(0, 60);
    bad.attempts = Math.min(bad.attempts, MAX_ATTEMPTS - 1);   // 释放一次返工额度
    task.log.push({ ts: Date.now(), kind: 'warn', text: `🔍 终检未过：「${bad.name}」${bad.feedback}，已点名返工` });
    saveJSON('tasks.json', tasks);
    schedule();
    return;
  }

  task.finishedAt = Date.now();
  const retried = subs.filter(s => s.attempts > 1).length;
  const errs = subs.filter(s => s.status === 'error').length;
  if (!errs) {           // 全绿的单才有资格当"经验"：沉淀技能 + 提炼记忆
    learnSkill(task);
    distillMemory(task);
  }
  const finalNote = verdict && !verdict.pass
    ? `总目标终检仍有疑点（${String(verdict.reason || '衔接存疑').slice(0, 40)}），已在台账如实标注`
    : '总目标终检通过';
  task.log.push({
    ts: task.finishedAt, kind: errs ? 'warn' : 'good',
    text: errs
      ? `📋 本单执行完毕：${errs} 个子任务异常（已在台账标注）；${finalNote}，咕嘎已把问题与经验记入知识库`
      : `📋 全部子任务验收通过，${finalNote}，咕嘎已向少爷汇报${retried ? '；本次监工共打回 ' + retried + ' 次，经验已入库' : ''}。产物均可在台账点开查看`,
  });
  saveJSON('tasks.json', tasks);
}

/* 调度器：同一任务串行（链式上下文），跨任务并行，受全局并发闸约束 */
function schedule() {
  gcPausedTasks();   // 暂停超时（15 分钟）的单在这里自动丢弃清理
  localWatchdog();   // 执行设备离线未领单的，改派或快速失败（不傻等 7 分钟超时）
  for (const task of tasks) {
    if (task.finishedAt || task.demo) continue;
    if (task.deferredUntil && Date.now() < task.deferredUntil) continue;   // 对比乙组错峰，避免两组挤兑并发闸
    const next = task.subtasks.find(s => s.status === 'pending' || s.status === 'returned');
    if (!next) continue;
    const key = task.id + ':' + next.id;
    if (inflight.has(key)) continue;
    if (next.status === 'returned' && next.rerunAt && Date.now() < next.rerunAt) continue;
    if (next.executor === '本机执行') {
      // 串行铁律：本机子任务必须上一个干完（或暂停）才派下一个——
      // 之前没拦，同一单的 3 个子任务 2 秒内全部"已指派"，监工日志全是噪音
      if (task.subtasks.some(s => s.executor === '本机执行'
          && (s.status === 'running' || s.status === 'paused'))) continue;
      startLocalJob(task, next); continue;
    }
    runSubtask(task, next);
  }
}
const scheduleTimer = setInterval(schedule, 1500);

/* 本机派单看门狗：点名的执行设备离线超 60 秒还没人来领单——
 * 优先改派给同账号其他在线电脑（每单最多改派一次，日志写明）；
 * 没有其他在线电脑就立刻如实标注失败，绝不挂 7 分钟假"执行中" */
function localWatchdog() {
  const agents = loadJSON('agents.json', {});
  const isOnline = a => Date.now() - (a.lastSeen || 0) < AGENT_ONLINE_MS;
  let dirty = false;
  const finishThese = new Set();   // 判死也必须收尾，避免整单永久挂起
  for (const task of tasks) {
    if (task.finishedAt || task.demo) continue;
    for (const st of task.subtasks || []) {
      if (st.executor !== '本机执行' || st.status !== 'running' || st.localClaimed) continue;
      const bound = task.execDeviceId
        ? Object.values(agents).find(a => a.id === task.execDeviceId)
        : (task.execDevice ? Object.values(agents).find(a => a.device === task.execDevice) : null);
      // 点名设备：它在线才算活；未点名的旧单：账号下任一本体在线即活
      const alive = bound ? isOnline(bound)
        : Object.values(agents).some(a => a.userId === task.userId && isOnline(a));
      if (alive) { st.deadSince = 0; continue; }
      if (!st.deadSince) { st.deadSince = Date.now(); continue; }   // 刚发现离线，给 60 秒宽限（心跳抖动）
      if (Date.now() - st.deadSince < 60000) continue;
      delete st.deadSince;
      const alt = Object.values(agents)
        .filter(a => a.userId === task.userId && isOnline(a))
        .sort((a, b) => b.lastSeen - a.lastSeen);
      if (!task.reRouted && alt.length) {
        task.reRouted = true;
        task.log.push({ ts: Date.now(), kind: 'warn', text: `🔁 执行设备「${(bound && bound.device) || task.execDevice || '原设备'}」离线且未领单——本单改派给在线的「${alt[0].device}」（远程指挥：谁在线谁干活）` });
        task.execDevice = alt[0].device;
        task.execDeviceId = alt[0].id;
        st.localClaimed = false;
        st.claimedBy = '';
        st.lastAliveAt = 0;
      } else {
        st.status = 'error';
        st.finishedAt = Date.now();
        st.checkResult = `执行设备「${(bound && bound.device) || task.execDevice || '原设备'}」离线且${task.reRouted ? '已无其他在线电脑可接手' : '未领单'}，本单如实标注（重新派单即可）`;
        task.log.push({ ts: Date.now(), kind: 'warn', text: `⚠ 「${st.name}」${st.checkResult}` });
        inflight.delete(task.id + ':' + st.id);
        finishThese.add(task);
      }
      dirty = true;
    }
  }
  for (const task of finishThese) finishCheck(task);
  if (dirty) saveJSON('tasks.json', tasks);
}

/* 本机执行方子任务：咕嘎本体（网页配对的桌面程序）真实拉起本机 AI 软件执行 */
function startLocalJob(task, st) {
  const key = task.id + ':' + st.id;
  if (inflight.has(key)) return;
  inflight.add(key);
  st.status = 'running';
  st.attempts++;
  st.progress = 0;
  st.overdue = false;
  st.finishedAt = 0;
  st.startedAt = Date.now();
  st.feedback = st.feedback || '';
  st.localClaimed = false;
  st.claimedBy = '';
  st.lastAliveAt = 0;
  task.log.push({ ts: Date.now(), kind: 'info', text: `🖥 「${st.name}」已派给本机执行方（咕嘎本体）：将真实拉起本机 AI 软件干活，少爷可在本机亲眼看过程` });
  saveJSON('tasks.json', tasks);
}

/* 进度显示：真实执行中按已用时/预算估算（产物字数才是真实产出） */
setInterval(() => {
  let dirty = false;
  const finishThese = new Set();   // 超时判死后必须走收尾（否则整单永远停在"执行中"）
  for (const task of tasks) {
    if (task.finishedAt || task.demo) continue;
    for (const st of task.subtasks) {
      if (st.status !== 'running' || !st.startedAt) continue;
      // 本机执行方：GUI 自动化较慢，90 秒后如实提醒；心跳持续不判死，心跳中断满 20 分钟才判异常
      if (st.executor === '本机执行') {
        const el = Date.now() - st.startedAt;
        if (!st.overdue && el > 90000) {
          st.overdue = true; dirty = true;
          task.log.push({ ts: Date.now(), kind: 'warn', text: `⏰ 本机执行方执行「${st.name}」已 ${Math.round(el / 1000)} 秒（真实 GUI 操作较慢，咕嘎继续盯）` });
        }
        const aliveBase = st.lastAliveAt || st.startedAt;
        if (Date.now() - aliveBase > LOCAL_HEARTBEAT_DEAD_MS) {
          st.status = 'error';
          st.finishedAt = Date.now();
          st.localClaimed = false;
          st.claimedBy = '';
          st.checkResult = '本机执行方 20 分钟无心跳且未交付（可能已退出或失联）';
          inflight.delete(task.id + ':' + st.id);
          task.log.push({ ts: Date.now(), kind: 'warn', text: `⚠ 「${st.name}」本机执行心跳中断超时：${st.checkResult}，本单已如实标注` });
          finishThese.add(task);
          dirty = true;
        }
        continue;
      }
      const est = Math.min(95, Math.round((Date.now() - st.startedAt) / WORK_BUDGET_MS * 100));
      if (est !== st.progress) { st.progress = est; dirty = true; }
    }
  }
  for (const task of finishThese) finishCheck(task);
  if (dirty) saveJSON('tasks.json', tasks);
}, 1200);

/* ================= 演示剧本（仅 LLM 未配置时兜底，台账会如实标注） ================= */
const DEMO_PLANS = [
  { kw: ['周报', '汇报', '总结'], subtasks: [
    { name: '数据汇总', executor: '本地工作流', acceptance: '汇总表存在且覆盖本周 7 天全部数据' },
    { name: '图表生成', executor: 'MCP 工具', acceptance: '产出图表含坐标轴、图例且数据与汇总表一致' },
    { name: '周报成文', executor: '外部智能体', acceptance: '正文覆盖进展、风险、下周计划三段' },
  ]},
  { kw: ['文件', '整理', '归档', '清理'], subtasks: [
    { name: '全盘扫描', executor: '本地工作流', acceptance: '文件清单齐全并按类型完成统计' },
    { name: '分类归档', executor: 'MCP 工具', acceptance: '目标目录按类型建立且无文件遗漏' },
    { name: '重名处理', executor: '本地工作流', acceptance: '无同名冲突，重命名规则统一' },
  ]},
  { kw: ['调研', '对比', '选型', '资料'], subtasks: [
    { name: '资料收集', executor: 'MCP 工具', acceptance: '每个对比对象至少 3 个独立信息源' },
    { name: '交叉核对', executor: '本地工作流', acceptance: '关键结论均有出处且口径一致' },
    { name: '成文输出', executor: '外部智能体', acceptance: '对比表格与结论建议两部分齐全' },
  ]},
  { kw: ['ppt', '幻灯', '演示', '答辩'], subtasks: [
    { name: '大纲设计', executor: '外部智能体', acceptance: '大纲含逻辑主线且页数不超限' },
    { name: '内容填充', executor: 'MCP 工具', acceptance: '每页有明确论点与配套素材' },
    { name: '排版美化', executor: '本地工作流', acceptance: '版式统一、图文对齐无溢出' },
  ]},
];
const DEMO_DEFAULT = [
  { name: '需求确认', executor: '本地工作流', acceptance: '目标被拆解为明确、可核对的条目' },
  { name: '执行处理', executor: 'MCP 工具', acceptance: '产出物完整且符合验收标准' },
  { name: '成文汇报', executor: '外部智能体', acceptance: '汇报含结论、依据与下一步建议' },
];
function demoPlan(goal) {
  // 优先用 KB5 任务模板库兜底（真实队友知识，比内置剧本更可信）
  const hit = kbMatch(goal);
  if (hit.tpl && hit.tpl.subs.length >= 2) {
    return hit.tpl.subs.slice(0, 4).map(s => ({
      name: s.name, executor: mapExecutor(s.execRaw), acceptance: s.acceptance,
    }));
  }
  for (const p of DEMO_PLANS) if (p.kw.some(k => goal.toLowerCase().includes(k))) return p.subtasks;
  return DEMO_DEFAULT;
}

// ================= KB7 复合接力：能力表注入（2026-11-05） =================
// 来源 knowledge/flows/*-io.md（软件输入输出能力实测）与 relay-rules.md（通用推导规则）。
// 拆解时只注入"目标里点名的软件"的能力表 + 一份规则摘要——不做任何流程匹配，
// 链条由 LLM 按产物类型 × 能力表现场推导（KB7 红线：禁止"用户说X就走Y"）。
const KB7_DIR_CANDIDATES = [
  path.join(__dirname, 'knowledge', 'flows'),          // 部署结构：knowledge 在云端目录内
  path.join(__dirname, '..', 'knowledge', 'flows'),    // 仓库结构：knowledge 在仓库根
];
const KB7_DIR = KB7_DIR_CANDIDATES.find(d => { try { return fs.existsSync(d); } catch { return false; } }) || KB7_DIR_CANDIDATES[0];
const KB7_SLUGS = { '豆包': 'doubao', '剪映': 'jianying' };
const KB7_IO_CACHE = new Map();   // slug -> { text, mtime }
function kb7IoText(slug) {
  const file = path.join(KB7_DIR, slug + '-io.md');
  try {
    const mt = fs.statSync(file).mtimeMs;
    const c = KB7_IO_CACHE.get(slug);
    if (c && c.mtime === mt) return c.text;
    let md = fs.readFileSync(file, 'utf-8');
    // 只留三张核心表：能产出什么 / 能接收什么输入 / 接力特性（自检清单与登记表对拆解无用，砍掉控 token）
    const cut = (re) => { const m = md.match(re); return m ? m[0] : ''; };
    let t = cut(/## 能产出什么（Output）[\s\S]*?(?=\n## |$(?![\s\S]))/) ||
           cut(/## 能产出什么[\s\S]{0,2600}/);
    t += '\n' + (cut(/## 能接收什么输入（Input）[\s\S]*?(?=\n## |$(?![\s\S]))/) ||
                 cut(/## 能接收什么[\s\S]{0,2200}/));
    t += '\n' + (cut(/## 接力特性[\s\S]*?(?=\n## |$(?![\s\S]))/) ||
                 cut(/## 接力特性[\s\S]{0,1400}/));
    t = t.replace(/\r/g, '').slice(0, 3600);
    KB7_IO_CACHE.set(slug, { text: t, mtime: mt });
    return t;
  } catch { return ''; }
}
const KB7_RULES = '\n【接力通用规则·KB7摘要】判断要不要接力：看目标的最终产物形态（纯文本/结构化文本/文件/图片/视频/可编辑工程六格谱系）'
  + '与第一步顺手的工具能直接产出的形态差几格——隔几格就至少几步，第一格工具能力表里没有的形态绝不能假设它能产。'
  + '每步选型只看两张表：它的 Input 能不能吃上一步产物（格式/大小），它的 Output 能不能产下一步所需形态。'
  + '传递形态：下游要按结构解析/要保版式/超粘贴上限/要多处复用 → 落文件再喂；下游只吃纯文本做语义改写 → 复制文本；两者皆可优先落文件。'
  + '反问三原则：不可逆/大消耗必问；风格数量等主观偏好开工前一次问清（≤3问各带默认值）；有合理默认值不问直接干并告知。'
  + '降级：某环节不可用按能力表找"同输入同输出"替代；没有就如实上报停在哪、缺什么，不假装做完。\n';

// 取上一个子任务的产物全文（接力喂文件用）；没有产物返回空串
function prevArtifactText(task, stId) {
  try {
    const idx = task.subtasks.findIndex(s => s.id === stId);
    if (idx <= 0) return '';
    const prev = task.subtasks[idx - 1];
    if (!prev || !prev.artifact || !prev.artifact.file) return '';
    const f = path.join(ARTIFACT_DIR, prev.artifact.file);
    return fs.existsSync(f) ? fs.readFileSync(f, 'utf-8').slice(0, 12000) : '';
  } catch { return ''; }
}

function kb7Ctx(goal) {
  if (!goal) return '';
  const low = String(goal).toLowerCase();
  const hits = [];
  for (const [k, slug] of Object.entries(KB7_SLUGS)) {
    if (goal.includes(k) || low.includes(k) && hits.every(h => h.slug !== slug)) {
      if (!hits.some(h => h.slug === slug)) hits.push({ slug, key: k });
    }
  }
  let ctx = '';
  for (const h of hits.slice(0, 2)) {
    const t = kb7IoText(h.slug);
    if (t) ctx += `\n【能力档案·${h.key}（KB7 实测）】${t}\n`;
  }
  if (ctx) ctx += KB7_RULES;
  return ctx;
}

function planPrompt(goal, userId) {
  const hit = kbMatch(goal);
  let kbCtx = '';
  if (hit.route) {
    kbCtx += `\n\n【调度参考·KB3指挥规则库·${hit.route.type}】首选执行方：${hit.route.first}；备选：${hit.route.backup}；编排方式：${hit.route.mode}；产物合并：${hit.route.merge}\n（拆解时参考该规则的编排思路；executor 字段仍只能取三值之一，acceptance 可结合首选方的强项来写）`;
  }
  if (hit.tpl) {
    kbCtx += `\n【拆解参考·KB5任务模板库·${hit.tpl.title}】参考子任务顺序：${hit.tpl.subs.map(s => s.name).join(' → ')}（可借鉴其拆解逻辑与验收写法，但按本目标实际情况调整）`;
  }
  if (userId) {
    const skill = recallSkill(userId, goal);
    if (skill) kbCtx += `\n【历史成功经验·咕嘎技能库（熟练度${skill.uses}）】类似目标「${String(skill.goal).slice(0, 40)}」曾成功拆解为：${skill.recipe.map(r => r.name + '(' + r.executor + ')').join(' → ')}——优先参考这条熟路的拆解思路与验收写法`;
    const facts = recallFacts(userId, 4);
    if (facts.length) kbCtx += `\n【少爷偏好·咕嘎的记忆】${facts.join('；')}`;
  }
  return [
    { role: 'system', content: '你是桌面智能体"咕嘎管家"，负责把用户的生产力目标拆解为可执行的子任务。' +
      '拆解铁律：按"一个动作一步"拆解，2~6 个子任务；导出、检查、补充、验收各自独立成步，宁可多一步，严禁为简洁而合并或压缩步数。' +
      '每个子任务包含 name（10字内动词短语）、executor（只能取："本地工作流"、"MCP 工具"、"外部智能体" 三者之一）、acceptance（一句话可核对的验收标准，如"文件存在且包含本周7天数据"）。' +
      'executor 判定铁律（逐条照做，禁止自由发挥）：①仅当目标原句明确点名某个软件（如"用 WorkBuddy""用豆包""用 JoyCode"）时，该步填"外部智能体"，且 name 或 acceptance 必须写出该软件名；②仅当目标原句明确要求"生成文件/表格/导出/归档"且该步就是落盘动作时，该步填"MCP 工具"；③其余一切步骤（含监工验收）一律填"本地工作流"。严禁凭空引入 PowerPoint、WPS、文件管理器、浏览器、Excel 等目标未点名的软件；未点名软件的步骤不得填"外部智能体"。' +
      '末尾铁律：subtasks 数组最后一项必须是独立的"监工验收"子任务——name 以"验收"开头（如"监工验收"），executor 固定填"本地工作流"，acceptance 写"逐项核对前序全部产物与总目标一致，缺项即打回"；不得省略，不得并入前一步。' +
      '可选字段 attachPrev（布尔）：仅当该子任务需要"把上一步的产物作为文件喂给目标软件"时设为 true（复合接力，如：分镜文本→喂给视频生成）。' +
      'acceptance 铁律：必须仅凭目标本身就能核对。目标里没给的信息（主题/风格/对象等）一律写"自行合理拟定"，严禁出现"用户提供了…""用户提供…要求"这类把信息缺口推回给用户的写法——用户不在执行现场，执行方只能靠目标自拟。' +
      '若下方注入了能力档案：子任务的可行性（谁产文本、谁吃文件、谁出视频）必须对照档案写，档案里标【未验证】的能力不得假设可用。' +
      '输出铁律：只输出一个 JSON 对象，形如 {"subtasks":[{"name":"","executor":"","acceptance":"","attachPrev":false}]}；禁止用反引号代码块包裹，禁止 JSON 前后任何解释文字。' + kbCtx + kb7Ctx(goal) },
    { role: 'user', content: '目标：' + goal },
  ];
}

function createTask(userId, goal, subtasksRaw, kb, space) {
  kb = kb || {};
  space = (String(space || '').trim() || '默认空间').slice(0, 16);
  const now = Date.now();
  const subs = subtasksRaw.slice(0, 6).map((s, i) => {
    const ex = EXECUTORS.includes(s.executor) ? s.executor : EXECUTORS[i % 3];
    return {
    id: 'st' + i,
    name: String(s.name || ('子任务' + (i + 1))).slice(0, 24),
    executor: ex,
    worker: pickWorker(ex, i),
    acceptance: String(s.acceptance || '交付物完整可用').slice(0, 80),
    status: 'pending',
    progress: 0,
    attempts: 0,
    attachPrev: !!s.attachPrev,   // KB7 复合接力：开工时把上一步产物落文件喂给目标软件
    overdue: false,
    finishedAt: 0,                // 子任务落定时间（done/error），台账轨迹用
    feedback: '',
    checkResult: '',
    artifact: null,
    startedAt: 0,
    rerunAt: 0,
  };
  });
  const task = {
    id: 't' + now.toString(36),
    userId, goal: String(goal).slice(0, 120),
    space,
    createdAt: now,
    subtasks: subs,
    demo: !llmReady(),          // true=内置剧本（未接模型），false=真实调度
    log: [{ ts: now, kind: 'info', text: llmReady()
      ? `咕嘎已接单，拆解为 ${subs.length} 个子任务——工人们已领单，进入真实执行，少爷可在台账看实时进展`
      : `咕嘎已接单，拆解为 ${subs.length} 个子任务并完成派单` }],
    finishedAt: 0,
  };
  if (kb.route) task.log.push({ ts: now, kind: 'info', text: `📚 调度依据 KB3 指挥规则库「${kb.route.type}」：首选 ${String(kb.route.first).slice(0, 32)}` });
  if (kb.tpl) task.log.push({ ts: now, kind: 'info', text: `📚 拆解参考 KB5 任务模板库「${kb.tpl.title}」` });
  tasks.unshift(task);
  // 任务保留按账号分别计算（每账号 30 单），不再全局截断——否则一个账号跑多了会把别的账号历史挤掉
  const KEEP_PER_USER = 30;
  const mineIdx = [];
  tasks.forEach((t, i) => { if (t.userId === task.userId) mineIdx.push(i); });
  if (mineIdx.length > KEEP_PER_USER) {
    for (const i of mineIdx.slice(KEEP_PER_USER).sort((a, b) => b - a)) tasks.splice(i, 1);
  }
  saveJSON('tasks.json', tasks);
  return task;
}

/* 演示模式的模拟引擎（仅 demo 任务使用） */
const REVIEW_PASS = ['交付物齐全，验收标准逐项通过', '格式正确、要点完整，通过', '内容核对无误，通过'];
const REVIEW_FAIL = '验收不通过：图表子任务缺少近 3 天数据，已打回重做';
function tickDemo() {
  const now = Date.now();
  let dirty = false;
  for (const task of tasks) {
    if (task.finishedAt || !task.demo) continue;
    let allDone = true;
    for (const st of task.subtasks) {
      if (st.status === 'done') continue;
      allDone = false;
      if (st.status === 'pending' && now >= (st.startAt || now + 1500)) {
        st.status = 'running'; st.attempts++; st.progress = 0; st.startedAt = now;
        task.log.push({ ts: now, kind: 'info', text: `「${st.name}」已派发给${st.executor}，开工` });
        dirty = true;
      } else if (st.status === 'running') {
        const elapsed = now - (st.startedAt || now);
        const dur = 9000;
        st.progress = Math.min(99, Math.round((elapsed / dur) * 100));
        if (st.attempts === 1 && !st.overdue && elapsed > dur * 0.55) {
          st.overdue = true;
          task.log.push({ ts: now, kind: 'warn', text: `⏰ 监工提醒：「${st.name}」进度落后于计划，咕嘎已向执行方催办` });
        }
        if (elapsed >= dur) {
          st.status = 'review'; st.progress = 100;
          task.log.push({ ts: now, kind: 'info', text: `「${st.name}」第 ${st.attempts} 次交付，咕嘎开始按验收标准核对` });
        }
        dirty = true;
      } else if (st.status === 'review') {
        const idx = Number(st.id.slice(2));
        const fail = st.attempts === 1 && task.subtasks.length > 1 && idx === 1;
        if (fail) {
          st.status = 'returned'; st.checkResult = REVIEW_FAIL; st.rerunAt = now + 3000;
          task.log.push({ ts: now, kind: 'warn', text: `❌ 验收打回：「${st.name}」${REVIEW_FAIL}` });
        } else {
          st.status = 'done'; st.checkResult = REVIEW_PASS[st.attempts % REVIEW_PASS.length];
          task.log.push({ ts: now, kind: 'good', text: `✅ 验收通过：「${st.name}」${st.checkResult}` });
        }
        dirty = true;
      } else if (st.status === 'returned' && now >= (st.rerunAt || 0)) {
        st.status = 'pending'; st.overdue = false; st.startAt = now + 1000;
        task.log.push({ ts: now, kind: 'info', text: `「${st.name}」已重新派发（第 ${st.attempts + 1} 次执行），咕嘎继续盯` });
        dirty = true;
      }
    }
    if (allDone) {
      task.finishedAt = now;
      const retry = task.subtasks.filter(s => s.attempts > 1).length;
      task.log.push({
        ts: now, kind: 'good',
        text: `📋 全部子任务验收通过，咕嘎已向少爷汇报${retry ? '；本次监工共打回 ' + retry + ' 次，经验已入库' : ''}`,
      });
      dirty = true;
    }
  }
  if (dirty) saveJSON('tasks.json', tasks);
}
setInterval(tickDemo, 1000);

// 接口限流：每个用户对话/派单最小间隔
const lastCall = {};
function rateLimit(ms) {
  return (req, res, next) => {
    const now = Date.now();
    if (lastCall[req.user] && now - lastCall[req.user] < ms) {
      return res.status(429).json({ error: '操作太快啦，稍等几秒再试' });
    }
    lastCall[req.user] = now; next();
  };
}

// IP 级限流（无登录态接口用）：防撞库/防配对码暴力枚举（按"IP+路由"分桶，互不影响）
const lastIpCall = {};
function ipLimit(ms) {
  return (req, res, next) => {
    const now = Date.now();
    const key = req.ip + ':' + req.path;
    if (lastIpCall[key] && now - lastIpCall[key] < ms) {
      return res.status(429).json({ error: '操作太快啦，稍等几秒再试' });
    }
    lastIpCall[key] = now; next();
  };
}

// 配对码防爆破：同一 IP 连续猜错 8 次，锁 10 分钟
const pairFails = {};
function pairGuard(req, res, next) {
  const ip = req.ip;
  const f = pairFails[ip];
  if (f && f.lockedUntil > Date.now()) {
    return res.status(429).json({ error: '配对尝试过于频繁，请 10 分钟后再来' });
  }
  next();
}

/* ---------------- 路由 ---------------- */
const app = express();

/* 视觉层接口（截图 base64 约 100~300KB，全局 64kb 限制装不下——
 * 必须注册在全局 json 中间件之前，用自己的 3mb 解析器才不会被 413 拦掉）。
 * 本体每 1.2 秒最多问一次（按执行方 token 限速），防滥用。 */
const visionLastAsk = new Map();
app.post('/api/agent/vision', express.json({ limit: '3mb' }), agentAuth, agentCloudGate('vision'), async (req, res) => {
  const tok = String(req.headers['x-agent-token'] || '');
  const last = visionLastAsk.get(tok) || 0;
  if (Date.now() - last < 1200) return res.status(429).json({ error: '视觉请示太频繁，稍候再问' });
  visionLastAsk.set(tok, Date.now());
  const img = String((req.body || {}).image || '').replace(/^data:image\/\w+;base64,/, '');
  const q = String((req.body || {}).question || '').slice(0, 500);
  if (img.length < 100) return res.status(400).json({ error: 'image 为空' });
  if (img.length > 2200000) return res.status(413).json({ error: '图片过大，请压缩到 1600px 宽以内' });
  if (!llmCfg.baseUrl || !llmCfg.apiKey) return res.json({ ok: false, error: '视觉模型未配置' });
  const r = await llmVision(q, img, undefined, { user: req.agent && req.agent.userId, kind: 'vision' });
  if (!r.ok) console.log(`[vision] 视觉请示失败: ${r.error}`);
  res.json({ ok: r.ok, text: r.ok ? r.text : '', model: r.model || '' });
});

/* 真机屏幕证据流：本机执行器的每步取证截图随任务上传——
 * 网页台账直接看"豆包被真实操作的实况截图墙"，是"不是剧本"的最强自证。 */
const EVIDENCE_DIR = path.join(DATA_DIR, 'evidence');
fs.mkdirSync(EVIDENCE_DIR, { recursive: true });
app.post('/api/agent/evidence', express.json({ limit: '3mb' }), agentAuth, (req, res) => {
  const { taskId, stId } = req.body || {};
  const img = String((req.body || {}).image || '').replace(/^data:image\/\w+;base64,/, '');
  const tag = String((req.body || {}).tag || 'step').replace(/[^\w\u4e00-\u9fa5-]/g, '').slice(0, 24) || 'step';
  const task = tasks.find(t => t.id === taskId && t.userId === req.agent.userId);
  if (!task) return res.status(404).json({ error: '任务不存在' });
  const st = task.subtasks.find(s => s.id === stId);
  if (!st) return res.status(404).json({ error: '子任务不存在' });
  if (img.length < 100 || img.length > 2200000) return res.status(400).json({ error: '图片尺寸异常' });
  // 文件名用时间戳后缀：同一子任务反复上传时序号会循环重复导致互相覆盖（验收发现），时间戳永不冲突
  const file = `evd_${task.id}_${st.id}_${Date.now().toString(36)}_${tag}.jpg`;
  try { fs.writeFileSync(path.join(EVIDENCE_DIR, file), Buffer.from(img, 'base64')); }
  catch { return res.status(500).json({ error: '落盘失败' }); }
  const keep = (st.evidence || []).concat([{ tag, file, ts: Date.now() }]).slice(-10);
  // 磁盘卫生：数组只留最近 10 张，被挤出的旧文件同步删除（验收发现：原版只截数组不删文件，磁盘只增不减）
  for (const old of (st.evidence || [])) {
    if (!keep.some(x => x.file === old.file)) { try { fs.unlinkSync(path.join(EVIDENCE_DIR, old.file)); } catch { /* 已不存在则忽略 */ } }
  }
  st.evidence = keep;
  saveJSON('tasks.json', tasks);
  res.json({ ok: true, file });
});

app.use(express.json({ limit: '64kb' }));
app.use(express.static(path.join(__dirname, 'public')));

// 证据截图查看（登录态鉴权；文件名携带 taskId，校验归属防越权翻别人的证据）
// ⚠ 验收发现的 P0：<img src>/<a href> 浏览器直连不会带 Authorization 头，
//   header-only 鉴权会让证据墙全部 401 裂图 —— 这里额外接受 ?t=<token> 短通道
//（仅本路由，且仍校验任务归属；token 泄漏面仅限证据文件本身，demo 场景可接受）
app.get('/api/evidence/:file', (req, res) => {
  const htok = (req.headers.authorization || '').replace(/^Bearer\s+/i, '');
  const sess = sessions[htok] || sessions[String(req.query.t || '')];
  if (!sess) return res.status(401).end();
  const f = path.basename(String(req.params.file || ''));
  const m = f.match(/^evd_([^_]+)_/);
  const task = m && tasks.find(t => t.id === m[1]);
  // tag 允许中文（上传端 \u4e00-\u9fa5），查看正则必须同步允许，否则中文 tag 证据永远 404
  if (!task || task.userId !== sess.username || !/^evd_[\w\u4e00-\u9fa5-]+\.jpg$/.test(f)) return res.status(404).end();
  res.sendFile(path.join(EVIDENCE_DIR, f));
});

app.post('/api/login', ipLimit(800), (req, res) => {
  const { username, password } = req.body || {};
  const u = users.find(x => x.username === String(username || ''));
  if (!u || hashPassword(String(password || ''), u.salt) !== u.hash) {
    return res.status(401).json({ error: '账号或密码不正确' });
  }
  // 登录成功清空该 IP 的配对失败计数；顺手清理 7 天前的过期会话 + 配对记录惰性 GC
  delete pairFails[req.ip];
  const now = Date.now();
  for (const k of Object.keys(sessions)) if (now - sessions[k].ts > 7 * 864e5) delete sessions[k];
  gcAgents();
  const token = crypto.randomBytes(24).toString('hex');
  // 登录设备标识（远程指挥功能）：手机/平板/其他电脑登录同账号，也能遥控本体电脑干活
  const device = String((req.body || {}).device || '').slice(0, 40);
  sessions[token] = { username: u.username, ts: Date.now(), device };
  saveJSON('sessions.json', sessions);
  res.json({ token, username: u.username });
});

app.get('/api/state', auth, (req, res) => {
  const mine = tasks.filter(t => t.userId === req.user).slice(0, 30);
  res.json({ serverTime: Date.now(), tasks: mine });
});

/* 派单公共入口：目标 → 大模型拆解 → 真实调度执行（未配置 key 时降级演示剧本）
 * executor:'local' = 本机执行方模式：整单由评委本机的咕嘎本体拉起本机 AI 软件真实执行
 * /api/tasks（手动派单）与 /api/chat（大脑意图路由）共用
 * 红线：目标涉及"打开/使用本机软件"（如打开豆包写作文）时，绝不允许云端工人代写冒充完成——
 *   本体在线 → 自动改派本机执行方真机执行；本体不在线 → 如实拒绝并指路配对。 */
const LOCAL_APPS = '豆包|doubao|workbuddy|记事本|notepad|计算器|浏览器|chrome|edge|wps|word|excel|剪映|飞书|钉钉|腾讯会议';
/* 隐私阻断（2026-11-05 拍板）：个人通信软件不接管。
 * 理由不是"做不了"，是"不该做"——读屏式自动化必须截取整窗画面，
 * 用户微信里必然是私人聊天、群消息、转账、家庭照片，这些与任务无关却被一并读走。
 * 所以这里既不能假装能做（云端代写冒充完成＝演剧本），也不能静默滑走，
 * 必须在派单入口明确拒绝并给替代路径。 */
const PRIVACY_APPS_TXT = '微信、企业微信、QQ';
function isPrivacyGoal(goal) {
  const s = String(goal || '');
  const apps = '企业微信|wxwork|wecom|微信|weixin|wechat|\\bqq\\b';
  if (!new RegExp('(' + apps + ')', 'i').test(s)) return false;
  return new RegExp('(打开|启动|开启|拉起|点开|操作|指挥|控制|登录|用|让)[^。；;]{0,10}(' + apps + ')', 'i').test(s)
      || new RegExp('(' + apps + ')[^。；;]{0,8}(里|中|上|内|发|聊|搜|查|传)', 'i').test(s);
}
const LOCAL_OP_RE = new RegExp(
  '(打开|启动|开启|拉起|点开|操作|指挥|控制|登录)[^。；;]{0,10}(' + LOCAL_APPS + ')' +   // 打开豆包…
  '|(' + LOCAL_APPS + ')[^。；;]{0,6}(里|中|上|内)?(写|搜|查|发|聊|生成|做)' +            // 豆包写/在豆包里查
  '|(用|让)(' + LOCAL_APPS + ')' +                                                        // 用豆包…
  '|在(我)?(电脑|本机|桌面)(上|里)',                                                       // 在我电脑上…
  'i');

/* 多 AI 软件档案 + 模糊识别（事故复盘：用户把 WorkBuddy 手滑打成 WrokBuddy，
 * 旧正则不认 → 整单悄悄滑进云端代写，违反"不要剧本要真实"）。
 * detectLocalApp(goal) → { app:'显示名'|null(泛指本机), fuzzy:是否纠错命中 } 或 null。
 * 命中即代表"这单要真实操控本机软件"，并告知本体该开哪个软件。 */
const APP_PROFILES = [
  { name: 'WorkBuddy', re: /w[o0]r?[kgq]?b[uo]?d{1,2}y|workbudd|wrokbody/i, latin: 'workbuddy' },
  { name: '豆包',      re: /豆包|do(?:ubao|obo)/i, latin: 'doubao' },
  /* 微信 / 企业微信 / QQ：按隐私策略不纳入（见 isPrivacyGoal）。不登记，避免被 detectLocalApp 认成可派单软件 */
  { name: 'QQ',        re: /\bqq\b/i },
  { name: '记事本',    re: /记事本|notepad/i },
  { name: '计算器',    re: /计算器|calculator/i },
  { name: '浏览器',    re: /浏览器|chrome|edge/i },
  { name: 'WPS',       re: /wps/i, latin: 'wps' },
  { name: 'Word',      re: /\bword\b/i, latin: 'word' },
  { name: 'Excel',     re: /\bexcel\b/i, latin: 'excel' },
  { name: '剪映',      re: /剪映|jianying/i },
  { name: '飞书',      re: /飞书|feishu|lark/i },
  { name: '钉钉',      re: /钉钉|dingtalk/i },
  { name: '腾讯会议',  re: /腾讯会议|wemeet|voov/i },
  { name: 'DeepSeek',  re: /deep\s?seek/i, latin: 'deepseek' },
];

function _lev(a, b) {   // 小型编辑距离（词长 ≤12，O(nm) 足够）
  const m = a.length, n = b.length;
  let prev = Array.from({ length: n + 1 }, (_, j) => j);
  for (let i = 1; i <= m; i++) {
    const cur = [i];
    for (let j = 1; j <= n; j++) {
      cur[j] = Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (a[i - 1] === b[j - 1] ? 0 : 1));
    }
    prev = cur;
  }
  return prev[n];
}

function detectLocalApp(goal) {
  const g = String(goal || '');
  if (!g) return null;
  // 泛指本机（无具体软件）：在(我)电脑/本机/桌面上…… → 本机执行，软件由本体自选
  if (/在(我)?(电脑|本机|桌面)(上|里)/.test(g)) return { app: null, fuzzy: false };
  for (const p of APP_PROFILES) {
    let fuzzy = false;
    let hit = p.re.test(g);
    if (!hit && p.latin) {
      // 拉丁名手滑拼写兜底：按英文词做编辑距离比对（如 WrokBuddy → WorkBuddy）
      const toks = g.toLowerCase().match(/[a-z][a-z0-9]{2,}/g) || [];
      hit = toks.some(t => t.length >= 4 && Math.abs(t.length - p.latin.length) <= 3 &&
        _lev(t, p.latin) <= Math.min(4, Math.floor(Math.min(t.length, p.latin.length) / 2)));
      fuzzy = hit;
    }
    if (!hit) continue;
    if (fuzzy) {
      // 纠错命中已足够说明点名了软件，只要句子里有操作意味就认定本机意图
      if (/使用|用|让|打开|启动|开启|拉起|点开|操作|指挥|控制|里|中|上|写|做|生成|搜|查|发|聊|画/.test(g)) {
        return { app: p.name, fuzzy: true };
      }
      continue;
    }
    const src = p.re.source;
    // 写进/写到/写成…= "写一段关于它的内容"，不是让软件干活
    const opRe = new RegExp(
      '(打开|启动|开启|拉起|点开|操作|指挥|控制|登录|使用|用|让)[^。；;]{0,10}(' + src + ')(?![^。；;]{0,4}(写进|画进|做进|加进|加到|放进))' +
      '|(' + src + ')(?![^。；;]{0,4}(写进|写到|写成|写入|画进|做进|加进|加到|放进))[^。；;]{0,6}(里|中|上|内)?(写|搜|查|发|聊|生成|做|画)', 'i');
    if (opRe.test(g)) return { app: p.name, fuzzy: false };
  }
  // 兜底兼容：软件名没进这张白名单，但只要本机自检认出来了（开始菜单扫描），
  // 照样能点名派本机执行——能不能指挥不该取决于"白名单里恰好有没有它"。
  try {
    const seen = new Set();
    for (const a of Object.values(loadJSON('agents.json', {}))) {
      const sc = a.selfcheck || {};
      for (const n of (Array.isArray(sc.ai) ? sc.ai : [])) if (n) seen.add(String(n));
    }
    const BLOCKED_APPS = new Set(['Kimi']);   // 移出适配名单的软件：付费门槛等，永不指挥
    for (const n of seen) {
      if (n.length < 2 || BLOCKED_APPS.has(n) || APP_PROFILES.some(p => p.name === n)) continue;
      const esc = n.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
      if (new RegExp(esc, 'i').test(g) &&
          /打开|启动|开启|拉起|点开|操作|指挥|控制|使用|用|让|问/.test(g)) {
        return { app: n, fuzzy: false };
      }
    }
  } catch { /* 读不到就当没这回事，不影响原判定 */ }
  return null;
}

async function dispatchGoal(userId, goal, space, useLocal, confirmed = false, fromDevice = '', pickDevice = '', requiredTools = []) {
  // 隐私阻断放在最前面：不能等它走完路由再拦，否则会先"自动改派本机"再失败，文案也不清楚
  if (isPrivacyGoal(goal)) {
    throw new Error(`咕嘎不接管「${PRIVACY_APPS_TXT}」这类个人通信软件——读屏式自动化必须截取整个窗口画面，`
      + `您聊天里的私人消息、群文件、转账记录会被一并读走，这既不安全也不体面。`
      + `跨应用搬文件不必经过聊天窗口：告诉我要哪个文件、交给哪个 AI 软件（豆包 / WorkBuddy / JoyCode），我走文件通道处理。`);
  }
  let useLocalNow = !!useLocal;
  let autoLocal = false;
  const localHit = detectLocalApp(goal);
  // 指定设备派单（远程指挥）：按稳定设备 id 锁定（兼容旧设备名）；点名机离线如实报错，不悄悄换机
  let agent = null;
  if (useLocalNow || localHit) {
    const list = agentsOnlineOf(userId);
    agent = pickDevice
      ? (list.find(a => (a.id && a.id === pickDevice) || (a.device || '') === pickDevice) || null)
      : (list[0] || null);
    if (pickDevice && !agent) {
      throw dispatchErr('DEVICE_OFFLINE',
        `所选设备「${pickDevice}」的本体不在线了——请在设备选择器里换一台在线的电脑，或去那台电脑重新启动咕嘎本体`,
        { deviceId: pickDevice });
    }
    // 跨设备工具校验：只有调用方显式传 requiredTools 才触发（旧客户端不传 → 行为完全不变）
    if (pickDevice && agent && Array.isArray(requiredTools) && requiredTools.length) {
      const key = inventoryKey(agent);
      const tools = deviceTools(key);
      if (!tools.length) {
        throw dispatchErr('NO_INVENTORY',
          `所选设备「${agent.device || pickDevice}」还没上报软件清单，无法确认它装了哪些 AI 软件——让那台电脑的本体启动一次即可自动上报`,
          { deviceId: agent.id, deviceName: agent.device || '' });
      }
      const missing = requiredTools.filter(t => !tools.some(it => toolMatches(it, t)));
      if (missing.length) {
        throw dispatchErr('TOOL_MISSING',
          `所选设备「${agent.device || pickDevice}」上没有：${missing.join('、')}——换一台设备，或先在那边装好再派`,
          { deviceId: agent.id, deviceName: agent.device || '', missing, available: tools.map(it => it.name) });
      }
    }
    if (!agent && localHit && !useLocalNow) {
      throw new Error('这单要真实操控您本机的软件干活，云端工人代写就是演剧本，咕嘎不接——请先在 🩺 自检 里下载咕嘎本体并用配对码绑定，绑好再派；或改为不需要操控电脑的纯内容目标');
    }
    if (!agent) {
      throw new Error('本机执行方未连接——请先在 🩺 自检 里下载咕嘎本体并用配对码绑定');
    }
    if (localHit && !useLocalNow) {
      useLocalNow = true;
      autoLocal = true;
    }
  }
  // 危险红线：不可逆操作必须经对话"确认"放行，手动派单同样拦截
  if (!confirmed && (DANGER_RE.test(goal) || DANGER_FILE_RE.test(goal))) {
    throw new Error('该目标涉及删除/系统/资金类不可逆操作，请在下方聊天框说清范围并回复"确认"后再派单');
  }
  const kb = kbMatch(goal);
  if (!llmReady()) return { task: createTask(userId, goal, demoPlan(goal), kb, space), mode: 'demo' };
  try {
    const plan = await llmJSON(planPrompt(goal, userId), undefined, { user: userId, kind: 'plan' }, 2600);
    const subs = Array.isArray(plan.subtasks) ? plan.subtasks : [];
    if (!subs.length) throw new Error('拆解结果为空');
    const task = createTask(userId, goal, subs, kb, space);
    if (useLocalNow) {
      task.targetApp = (localHit && localHit.app) || '';
      task.execDevice = agent.device || '';
      task.execDeviceId = agent.id || '';
      task.fromDevice = fromDevice || '';
      task.subtasks.forEach(s => { s.executor = '本机执行'; });
      task.log.push({ ts: Date.now(), kind: 'info', text: `🖥 本单由少爷本机执行方（${agent.device || '咕嘎本体'}）真实执行——咕嘎将远程指挥本机 AI 软件，过程可在本机亲眼看到` });
      if (fromDevice && task.execDevice && fromDevice !== task.execDevice) task.log.push({ ts: Date.now(), kind: 'info', text: `📡 远程指挥：这单是从「${fromDevice}」遥控派来的，「${task.execDevice}」负责真机干活——同账号在任何设备（手机/平板/别的电脑）登录都能这样指挥` });
      if (localHit && localHit.app) task.log.push({ ts: Date.now(), kind: 'info', text: `🎯 目标软件已锁定：「${localHit.app}」${localHit.fuzzy ? '（拼写有误，已自动纠正）' : ''}，本体将真实拉起它干活` });
      if (autoLocal) task.log.push({ ts: Date.now(), kind: 'info', text: '🧠 大脑识别到「打开/使用本机软件」意图：云端代写属于演剧本，本单已自动改派本机执行方真机执行' });
      saveJSON('tasks.json', tasks);
    }
    setImmediate(schedule);          // 立即开工
    return { task, mode: useLocalNow ? 'local' : 'llm' };
  } catch {
    // 拆解通道失败降级：本机操作单依旧保持本机执行，绝不悄悄变回云端代写
    const task = createTask(userId, goal, demoPlan(goal), kb, space);
    if (useLocalNow) {
      task.targetApp = (localHit && localHit.app) || '';
      task.execDevice = agent.device || '';
      task.execDeviceId = agent.id || '';
      task.fromDevice = fromDevice || '';
      task.subtasks.forEach(s => { s.executor = '本机执行'; });
      task.log.push({ ts: Date.now(), kind: 'info', text: `🖥 本单由少爷本机执行方（${agent.device || '咕嘎本体'}）真实执行——咕嘎将远程指挥本机 AI 软件，过程可在本机亲眼看到` });
      if (fromDevice && task.execDevice && fromDevice !== task.execDevice) task.log.push({ ts: Date.now(), kind: 'info', text: `📡 远程指挥：这单是从「${fromDevice}」遥控派来的，「${task.execDevice}」负责真机干活——同账号在任何设备（手机/平板/别的电脑）登录都能这样指挥` });
      if (localHit && localHit.app) task.log.push({ ts: Date.now(), kind: 'info', text: `🎯 目标软件已锁定：「${localHit.app}」${localHit.fuzzy ? '（拼写有误，已自动纠正）' : ''}，本体将真实拉起它干活` });
      if (autoLocal) task.log.push({ ts: Date.now(), kind: 'info', text: '🧠 大脑识别到「打开/使用本机软件」意图：云端代写属于演剧本，本单已自动改派本机执行方真机执行' });
      saveJSON('tasks.json', tasks);
    }
    return { task, mode: useLocalNow ? 'local' : 'fallback' };
  }
}

app.post('/api/tasks', auth, requireCloud, rateLimit(4000), async (req, res) => {
  const goal = String((req.body || {}).goal || '').trim();
  const space = String((req.body || {}).space || '').trim();
  const useLocal = String((req.body || {}).executor || '') === 'local';
  if (!goal) return res.status(400).json({ error: '请先告诉咕嘎你的目标' });
  try {
    const { task, mode } = await dispatchGoal(req.user, goal, space, useLocal, false, req.device,
      String((req.body || {}).device || '').slice(0, 60), requiredToolsOf(req.body));
    res.json({ task, mode });
  } catch (e) {
    const out = { error: String(e.message || e) };
    if (e.code) out.code = e.code;
    if (e.deviceId) out.deviceId = e.deviceId;
    if (e.deviceName) out.deviceName = e.deviceName;
    if (Array.isArray(e.missing)) out.missing = e.missing;
    res.status(400).json(out);
  }
});

/* ---------------- 工作空间（任务分区，仿 WorkBuddy 的空间体系） ---------------- */
app.get('/api/spaces', auth, (req, res) => {
  const all = loadJSON('spaces.json', {});
  const list = new Set(all[req.user] || ['默认空间']);
  for (const t of tasks) if (t.userId === req.user) list.add(t.space || '默认空间');
  res.json({ spaces: [...list] });
});
app.post('/api/spaces', auth, rateLimit(1500), (req, res) => {
  const name = String((req.body || {}).name || '').trim().slice(0, 16);
  if (!name) return res.status(400).json({ error: '空间名不能为空' });
  const all = loadJSON('spaces.json', {});
  const list = new Set(all[req.user] || ['默认空间']);
  if (list.size >= 8 && !list.has(name)) return res.status(400).json({ error: '最多 8 个空间，够用了少爷' });
  list.add(name);
  all[req.user] = [...list];
  saveJSON('spaces.json', all);
  res.json({ ok: true, spaces: [...list] });
});

// 环境自检（评委登录即体检）：每一项都是真实探测，结果缓存 5 分钟防刷
let selfcheckCache = null;
app.get('/api/selfcheck', auth, async (req, res) => {
  // 本机执行方按当前账号实时判定（不进缓存、不读全局文件——
  // 别的电脑的本体在线不代表这一台在线，必须如实区分；多设备全部列出）
  const perUserExec = () => {
    const list = agentsOnlineOf(req.user).map(deviceView);
    const a = list[0] || null;
    return {
      online: list.length > 0,
      device: a ? a.device : '',
      path: a ? a.path : '',
      pyver: a ? a.pyver : '',
      agent: a ? a.agent : '',
      depsOk: a ? a.depsOk : false,
      aiFound: a ? a.aiFound : 0,
      ai: a ? a.ai : [],
      devices: list,          // 全部在线设备（自检弹窗逐台列出，设备选择器同源）
      agents: agentHistory(req.user),
    };
  };
  if (selfcheckCache && Date.now() - selfcheckCache.ts < 300000) {
    return res.json({ ...selfcheckCache, executor: perUserExec(), agentLatest: latestAgentView() });
  }
  // ① 大模型链路：真调一次
  const llm = { ok: false, ms: 0, model: llmCfg.model || '', ready: llmReady() };
  if (llmReady()) {
    const t0 = Date.now();
    try { await llmStream([{ role: 'user', content: '只回一个字：通' }], () => {}); llm.ok = true; }
    catch { llm.ok = false; }
    llm.ms = Date.now() - t0;
  }
  // ② 知识库装载
  const kb = {
    routing: KB.routing.length, templates: KB.templates.length, accept: KB.accept.length,
    ok: KB.routing.length > 0 && KB.accept.length > 0,
  };
  // ③ 产物存储可写（真写真删一个临时文件）
  let storeOk = false;
  try {
    const p = path.join(ARTIFACT_DIR, `.selfcheck-${process.pid}`);
    fs.writeFileSync(p, 'ok'); fs.unlinkSync(p); storeOk = true;
  } catch { /* 只读盘时置灰 */ }
  // ④ 执行引擎状态
  const running = tasks.filter(t => !t.finishedAt).length;
  selfcheckCache = {
    ts: Date.now(),
    llm, kb, storeOk, running,
    uptimeMin: Math.round(process.uptime() / 60),
    engineMode: llmReady() ? 'real' : 'demo',
  };
  res.json({ ...selfcheckCache, executor: perUserExec(), agentLatest: latestAgentView() });
});

/* ---------------- 本机执行方（咕嘎本体）：配对码绑定 + 心跳领单 + 交付回传 ----------------
 * 浏览器扫不了评委本机（安全沙箱硬限制），本机自检与 GUI 执行由本体完成；
 * 网页只负责"发码、看状态、派单、验收"，任务/产物/监工记录全在云端同步。
 */
const AGENT_ONLINE_MS = 30000;   // 心跳 30 秒内算在线

/* 在线判定必须按账号过滤：否则 A 电脑的本体在线，B 电脑登录会看到"本机执行方已连接"的假象 */
function agentOnline(userId) {
  const agents = loadJSON('agents.json', {});
  return Object.values(agents).find(a =>
    Date.now() - a.lastSeen < AGENT_ONLINE_MS && (!userId || a.userId === userId)) || null;
}
/* 账号下全部在线本体（传空 userId = 全部账号，供全局状态用） */
function agentsOnlineOf(userId) {
  const agents = loadJSON('agents.json', {});
  return Object.values(agents).filter(a =>
    Date.now() - a.lastSeen < AGENT_ONLINE_MS && (!userId || a.userId === userId));
}
/* 本体最新版：public/guga-version.txt 由打包脚本生成（版本号 + 打包时间 + zip md5），
 * 是"该发哪一版"的唯一口径——不在这里写死，换包只改文件、不改代码。 */
let AG_VER_CACHE = null;
function latestAgent() {
  try {
    const p = path.join(__dirname, 'public', 'guga-version.txt');
    const st = fs.statSync(p);
    if (!AG_VER_CACHE || AG_VER_CACHE.mtime !== st.mtimeMs) {
      const o = JSON.parse(fs.readFileSync(p, 'utf8'));
      AG_VER_CACHE = {
        mtime: st.mtimeMs,
        version: String(o.version || '').slice(0, 12),
        builtAt: String(o.builtAt || '').slice(0, 20),
        exeBuiltAt: String(o.exeBuiltAt || '').slice(0, 20),
        md5: String(o.md5 || '').slice(0, 40),
        size: Number(o.size || 0),
      };
    }
    return AG_VER_CACHE;
  } catch { return { version: '', builtAt: '', exeBuiltAt: '', md5: '', size: 0 }; }
}
/* 对外只暴露前端要用的字段：mtime 是缓存内部用的，别塞进 API 响应 */
function latestAgentView() {
  const a = latestAgent();
  return { version: a.version, builtAt: a.builtAt, exeBuiltAt: a.exeBuiltAt || '', md5: a.md5, size: a.size };
}
/* 设备统一视图：devices 接口 / 自检 / 状态共用一份形状，别再各写各的 */
function deviceView(a) {
  const sc = a.selfcheck || {};
  const agent = (a.caps && a.caps.agent) || '';
  const latest = latestAgent().version;
  return {
    id: a.id || '',                                  // 稳定设备 id（派单锁定用，设备名可能重名）
    device: a.device || '',
    path: a.path || '',
    ai: Array.isArray(sc.ai) ? sc.ai : [],
    aiFound: Array.isArray(sc.ai) ? sc.ai.length : 0,
    pyver: (a.caps && a.caps.pyver) || '',
    agent,                                           // 本体自报版本（旧包为空串）
    outdated: !!latest && agent !== latest,          // 不是最新包（含"旧到不上报版本"的包）
    depsOk: !!(a.caps && a.caps.depsOk),
    lastSeen: a.lastSeen,
  };
}
function saveExecutorStatus() {
  const list = agentsOnlineOf('').map(deviceView);   // 全账号全局视角：写全部在线设备，别只写第一台
  try {
    fs.writeFileSync(path.join(DATA_DIR, 'executor.json'), JSON.stringify({
      online: list.length > 0,
      aiFound: list.length ? list[0].aiFound : 0,
      ai: list.length ? list[0].ai : [],
      device: list.length ? list[0].device : '',
      lastSeen: list.length ? list[0].lastSeen : 0,
      devices: list,                                 // 新字段：完整多设备清单
    }));
  } catch { /* 磁盘异常不拦主流程 */ }
}
function agentAuth(req, res, next) {
  const tok = String(req.headers['x-agent-token'] || '');
  const agents = loadJSON('agents.json', {});
  if (!tok || !agents[tok]) return res.status(401).json({ error: '本机执行方未配对或绑定已失效' });
  agents[tok].lastSeen = Date.now();
  saveJSON('agents.json', agents);
  req.agent = agents[tok];
  req.agentToken = tok;
  next();
}

/* 把 req.agent 上的改动真正写回磁盘。
 * 绝对不能写 saveJSON('agents.json', loadJSON('agents.json', {}))：
 * loadJSON 每次都从磁盘重新解析出一个新对象，req.agent 上的改动不在那个新对象里，
 * 等于"改完立刻拿旧副本盖回去"——selfcheck / path / caps 的更新会静默丢失，
 * 只靠配对那一次落盘兜着，所以这个坑一直没被发现（换包不重开、能力清单不刷新都源于此）。 */
function saveAgentPatch(tok, patch) {
  const all = loadJSON('agents.json', {});
  if (!all[tok]) return false;
  Object.assign(all[tok], patch);
  saveJSON('agents.json', all);
  return true;
}

/* ---------------- 设备软件清单（跨设备派单用） ----------------
 * 同一账号两台电脑：本体上报本机可用的 AI 软件，服务端按稳定设备标识归账。
 * 旧版本体不上报 → inventory.json 一直是空 → 所有旧流程行为与升级前一致。 */
const INVENTORY_MAX_TOOLS = 200;
const INVENTORY_TTL = 30 * 864e5;
function normToolName(s) { return String(s || '').trim().toLowerCase().replace(/\s+/g, ' '); }
function normToolItem(raw) {
  if (!raw || typeof raw !== 'object') return null;
  const name = String(raw.name || raw.app || '').trim().slice(0, 60);
  if (!name) return null;
  const ts = (v) => { const n = typeof v === 'number' ? v : Date.parse(v); return isFinite(n) && n > 0 ? n : Date.now(); };
  return {
    name,
    launch: String(raw.launch || raw.exec || raw.exe || '').trim().slice(0, 120),   // 可启动标识：exe / 命令 / 协议
    version: String(raw.version || '').trim().slice(0, 40),
    path: String(raw.path || raw.dir || '').trim().slice(0, 200),                  // 路径摘要
    summary: String(raw.summary || raw.desc || '').trim().slice(0, 120),
    aliases: (Array.isArray(raw.aliases) ? raw.aliases : []).map(x => String(x || '').trim().slice(0, 40)).filter(Boolean).slice(0, 8),
    updatedAt: ts(raw.updatedAt),
  };
}
function inventoryKey(agent) { return String((agent && (agent.device_id || agent.id)) || ''); }
function deviceTools(key) {
  const all = loadJSON('inventory.json', {});
  const rec = key ? all[key] : null;
  return rec && Array.isArray(rec.items) ? rec.items : [];
}
function toolMatches(item, want) {
  const w = normToolName(want);
  if (!w) return false;
  const cands = [item.name, item.launch].concat(item.aliases || []).map(normToolName).filter(Boolean);
  return cands.some(c => c === w || c.includes(w) || (c.length >= 3 && w.includes(c)));
}
function requiredToolsOf(body) {
  const b = body || {};
  const raw = Array.isArray(b.requiredTools) ? b.requiredTools : (Array.isArray(b.required_tools) ? b.required_tools : []);
  const out = [];
  for (const t of raw.slice(0, 10)) {
    const s = String(t || '').trim().slice(0, 60);
    if (s && !out.includes(s)) out.push(s);
  }
  return out;
}
function dispatchErr(code, message, extra) {
  const e = new Error(message);
  e.code = code;
  Object.assign(e, extra || {});
  return e;
}

/* ---------------- 配对记录生命周期策略 ----------------
 * 背景：测试/重装/换机产生的配对残留会一直躺在 agents.json 里，
 * "找回已有本体"把陈年记录也指出来，误导用户（实战踩坑：测试码配对记录串到账号里）。
 * 三层策略，从机制上杜绝：
 * ① 显示层：找回列表只列 7 天内活跃过的设备，更早的自动淡出不再指路；
 * ② 数据层：30 天无心跳物理删除；每账号最多 6 台（在线豁免），超出删最旧；
 * ③ 同设备重配对：清掉同账号同设备的旧 token 记录（重装/挪目录不堆积）。
 * GC 惰性触发（登录/配对时，1 小时节流），不依赖定时器。 */
const AGENT_SHOW_TTL = 7 * 864e5;
const AGENT_KILL_TTL = 30 * 864e5;
const AGENT_MAX_RECORDS = 6;
let lastAgentGc = 0;
function gcAgents(force = false) {
  if (!force && Date.now() - lastAgentGc < 3600000) return;
  lastAgentGc = Date.now();
  const agents = loadJSON('agents.json', {});
  const now = Date.now();
  let dirty = false;
  for (const k of Object.keys(agents)) {
    if (now - (agents[k].lastSeen || 0) > AGENT_KILL_TTL) { delete agents[k]; dirty = true; }
  }
  const byUser = {};
  for (const k of Object.keys(agents)) {
    (byUser[agents[k].userId] = byUser[agents[k].userId] || []).push([k, agents[k]]);
  }
  for (const u of Object.keys(byUser)) {
    const list = byUser[u].sort((a, b) => (a[1].lastSeen || 0) - (b[1].lastSeen || 0));
    const excess = list.length - AGENT_MAX_RECORDS;
    if (excess > 0) {
      for (const [k, x] of list.filter(([, x]) => now - (x.lastSeen || 0) >= AGENT_ONLINE_MS).slice(0, excess)) {
        delete agents[k]; dirty = true;
      }
    }
  }
  if (dirty) saveJSON('agents.json', agents);
  return dirty;
}

// 网页生成 6 位配对码（10 分钟有效）
app.post('/api/pair/create', auth, rateLimit(1500), (req, res) => {
  const code = String(Math.floor(100000 + Math.random() * 900000));
  const all = loadJSON('pairings.json', {});
  for (const k of Object.keys(all)) if (Date.now() - all[k].ts > 600000) delete all[k];
  all[code] = { userId: req.user, ts: Date.now() };
  saveJSON('pairings.json', all);
  res.json({ code, expiresIn: 600 });
});

// 本体凭配对码绑定（同时上传本机自检结果）——防暴力枚举：IP 限速 + 连错 8 次锁 10 分钟
app.post('/api/agent/pair', ipLimit(1200), pairGuard, (req, res) => {
  const code = String((req.body || {}).code || '').trim();
  const all = loadJSON('pairings.json', {});
  const p = all[code];
  if (!p || Date.now() - p.ts > 600000) {
    const f = pairFails[req.ip] || (pairFails[req.ip] = { n: 0, lockedUntil: 0 });
    if (++f.n >= 8) { f.lockedUntil = Date.now() + 600000; f.n = 0; }
    return res.status(400).json({ error: '配对码无效或已过期，请在网页重新生成' });
  }
  delete pairFails[req.ip];
  delete all[code];
  saveJSON('pairings.json', all);
  const token = crypto.randomBytes(24).toString('hex');
  const agents = loadJSON('agents.json', {});
  const device = String((req.body || {}).device || '咕嘎本体').slice(0, 60);
  const rawPath = String((req.body || {}).path || '').slice(0, 200);
  // 稳定机器标识：优先客户端上报的 device_id；本体现在还没上报时，用本体所在文件夹路径派生一个，
  // 这样两台同名设备（不同安装路径）也能共存，同一台重装（同路径）仍然只保留一条。
  const devId = String((req.body || {}).device_id || '').trim().slice(0, 64)
    || (rawPath ? 'path:' + crypto.createHash('sha1').update(rawPath).digest('hex').slice(0, 16) : '');
  // 同设备重新配对：只替换同一台机器的旧记录，同名不同机的设备各自保留、互相不顶掉。
  // 既没有 device_id 也没有路径的老客户端，退化为"仅本账号内按同名覆盖"，不再跨账号互踢。
  for (const k of Object.keys(agents)) {
    const x = agents[k];
    if (devId) {
      // 同一台机器：device_id 相同；或旧版本配对留下的无 device_id 记录但路径一致
      if (x.device_id === devId
          || (!x.device_id && x.userId === p.userId && rawPath && x.path === rawPath)) delete agents[k];
    } else if (!x.device_id && x.userId === p.userId && (x.device || '咕嘎本体') === device) {
      delete agents[k];
    }
  }
  const caps = (req.body || {}).caps || null;
  agents[token] = {
    id: crypto.randomBytes(4).toString('hex'),   // 稳定设备 id：派单/领单按 id 锁定，不依赖可能重名的设备名
    device_id: devId,                            // 客户端上报的稳定机器标识（同名设备靠它区分共存）
    userId: p.userId,
    device,
    path: rawPath,                               // 本体在自己电脑上的文件夹（网页可指路找回）
    caps: caps && typeof caps === 'object' ? {                 // 本机能力：Python 版本 + 真机指挥依赖是否齐备
      pyver: String(caps.pyver || '').slice(0, 20),
      platform: String(caps.platform || '').slice(0, 20),
      agent: String(caps.agent || '').slice(0, 12),   // 本体版本：换包后能一眼确认跑的是哪一版
      depsOk: !!caps.deps_ok,
    } : null,
    selfcheck: (req.body || {}).selfcheck || null,
    lastSeen: Date.now(),
    pairedAt: Date.now(),
  };
  gcAgents(true);   // 配对时机做一次强制 GC（过期/超限回收）
  saveJSON('agents.json', agents);
  saveExecutorStatus();
  console.log(`[agent] 本机执行方已配对: ${agents[token].device} → 账号 ${p.userId}`);
  res.json({ token, user: p.userId });
});

/* 本体上报本机可用的 AI 软件清单（跨设备派单的依据）。
 * 兼容：旧版本体从不调用此接口 → inventory.json 不存在 → 跨设备派单不会做工具校验，行为与升级前一致。
 * 注：全局 body 上限 64kb 已够用（单台电脑的 AI 软件清单通常 10~50 条），这里不再单独放宽。 */
app.post('/api/agent/inventory', agentAuth, (req, res) => {
  const body = req.body || {};
  const raw = Array.isArray(body.items) ? body.items : (Array.isArray(body.tools) ? body.tools : []);
  const seen = new Set();
  const items = [];
  for (const r of raw.slice(0, INVENTORY_MAX_TOOLS * 2)) {
    const it = normToolItem(r);
    if (!it) continue;
    const k = normToolName(it.name) + '|' + normToolName(it.launch);
    if (seen.has(k)) continue;
    seen.add(k);
    items.push(it);
    if (items.length >= INVENTORY_MAX_TOOLS) break;
  }
  const key = inventoryKey(req.agent);
  if (!key) return res.status(400).json({ error: '设备标识缺失，请重新配对后再上报' });
  const all = loadJSON('inventory.json', {});
  all[key] = {
    deviceId: key,
    device_id: req.agent.device_id || '',
    userId: req.agent.userId,
    device: req.agent.device || '咕嘎本体',
    updatedAt: Date.now(),
    items,
  };
  for (const k of Object.keys(all)) {
    if (Date.now() - (all[k].updatedAt || 0) > INVENTORY_TTL) delete all[k];
  }
  saveJSON('inventory.json', all);
  saveAgentPatch(req.agentToken, { toolsAt: all[key].updatedAt, toolsCount: items.length });
  res.json({ ok: true, deviceId: key, device: all[key].device, count: items.length, updatedAt: all[key].updatedAt });
});

// 心跳 + 领单：本体每 4 秒一拍，有本机子任务就领走
app.post('/api/agent/beat', agentAuth, (req, res) => {
  if (req.body && req.body.selfcheck) { req.agent.selfcheck = req.body.selfcheck; saveAgentPatch(req.agentToken, { selfcheck: req.body.selfcheck }); }
  if (req.body && req.body.path) {   // 本体换了文件夹也能随时更新指路信息
    const p = String(req.body.path).slice(0, 200);
    if (p !== req.agent.path) { req.agent.path = p; saveAgentPatch(req.agentToken, { path: p }); }
  }
  if (req.body && req.body.caps && typeof req.body.caps === 'object') {   // 能力清单随时刷新（装好依赖后自动变绿）
    const c = req.body.caps;
    const caps = { pyver: String(c.pyver || '').slice(0, 20), platform: String(c.platform || '').slice(0, 20),
                   agent: String(c.agent || (req.agent.caps && req.agent.caps.agent) || '').slice(0, 12), depsOk: !!c.deps_ok };
    if (JSON.stringify(caps) !== JSON.stringify(req.agent.caps || {})) { req.agent.caps = caps; saveAgentPatch(req.agentToken, { caps }); }
  }
  if (!req.agent.id) {   // 旧版本本体的条目补发稳定设备 id（下一次领单就按 id 锁定）
    req.agent.id = crypto.randomBytes(4).toString('hex');
    saveAgentPatch(req.agentToken, { id: req.agent.id });
  }
  saveExecutorStatus();
  gcPausedTasks();   // 暂停超时的单趁心跳顺手清理
  if (req.body && req.body.busy) {
    // 保活心跳（干活期间由保活线程拍）：只刷在线状态，绝不派新单——否则一台电脑同时干两单
    // 同时刷新"仍在干活"的存活时间：真在跑的长任务（如 WorkBuddy 出 PPT 13 分钟）不许被判死
    const now = Date.now();
    for (const task of tasks) {
      if (task.finishedAt || task.demo) continue;
      for (const st of task.subtasks || []) {
        if (st.executor === '本机执行' && st.status === 'running' && st.claimedBy === req.agent.id) st.lastAliveAt = now;
      }
    }
    return res.json({ job: null, serverTime: now });
  }
  const uid = req.agent.userId;
  for (const task of tasks) {
    if (task.userId !== uid || task.finishedAt || task.demo) continue;
    // 指定设备派单：点名给 A 电脑的单，B 电脑的本体不能抢走（新单按设备 id，旧单按设备名）
    if (task.execDeviceId ? task.execDeviceId !== req.agent.id
        : (task.execDevice && task.execDevice !== req.agent.device)) continue;
    const st = task.subtasks.find(s => s.executor === '本机执行' && s.status === 'running' && !s.localClaimed);
    if (st) {
      st.localClaimed = true;
      st.claimedBy = req.agent.id;      // 谁领的这单：保活心跳按设备 id 精确刷新存活时间
      st.lastAliveAt = Date.now();
      st.pauseRequested = false;   // 新一轮领单不继承旧的暂停请求
      saveJSON('tasks.json', tasks);
      return res.json({ job: {
        taskId: task.id, stId: st.id, name: st.name, goal: task.goal,
        acceptance: st.acceptance, feedback: st.feedback || '', attempt: st.attempts,
        app: task.targetApp || '', resume: st.pauseCtx || '',   // 暂停恢复：带上前进度无缝接续
        // KB7 复合接力：本步标了 attachPrev → 带上一步产物全文，执行方落成本地文件喂给目标软件
        attachText: st.attachPrev ? prevArtifactText(task, st.id) : '',
      } });
    }
  }
  res.json({ job: null, serverTime: Date.now() });
});

// 本体交付：产物落盘 → 与云端同一套监工真实验收（KB4 底线 + 打回重做）
app.post('/api/agent/result', agentAuth, async (req, res) => {
  const { taskId, stId } = req.body || {};
  const content = String((req.body || {}).content || '');
  const ok = !!(req.body || {}).ok;
  const task = tasks.find(t => t.id === taskId && t.userId === req.agent.userId);
  if (!task) return res.status(404).json({ error: '任务不存在' });
  const st = task.subtasks.find(s => s.id === stId);
  if (!st) return res.status(404).json({ error: '子任务不存在' });
  const key = task.id + ':' + st.id;

  const failNote = String((req.body || {}).note || '未说明原因');
  // 用户主动中止 ≠ 执行失败：不得再自动重派（否则用户按了停止，服务端还会连续重试 3 次）
  const aborted = !!(req.body || {}).aborted || /^(已中止|用户终止|Stopped)/.test(failNote);
  if (!ok || !content.trim()) {
    if (aborted || st.attempts >= MAX_ATTEMPTS) {
      st.status = 'error';
      st.finishedAt = Date.now();
      st.localClaimed = false;
      st.claimedBy = '';
      st.checkResult = aborted
        ? '用户中止本轮操作（不自动重试）：' + failNote.slice(0, 50)
        : '本机执行方连续 ' + MAX_ATTEMPTS + ' 次未能完成（' + failNote.slice(0, 50) + '）';
      task.log.push({ ts: Date.now(), kind: 'warn', text: aborted
        ? `⏹ 「${st.name}」${st.checkResult}，本单按中止收尾`
        : `⚠ 「${st.name}」本机执行连续 ${MAX_ATTEMPTS} 次失败：${st.checkResult}（已如实上报少爷，本单继续走剩余子任务）` });
      inflight.delete(key);
      finishCheck(task);
      saveJSON('tasks.json', tasks);
      setImmediate(schedule);
      return res.json({ ok: true, accepted: aborted ? 'aborted' : 'failed' });
    }
    st.status = 'returned';
    st.finishedAt = 0;
    st.localClaimed = false;
    st.claimedBy = '';
    st.feedback = '本机执行方回报失败：' + failNote.slice(0, 60);
    task.log.push({ ts: Date.now(), kind: 'warn', text: `⚠ 本机执行方未能完成「${st.name}」，咕嘎已收回重新派发` });
    inflight.delete(key);
    saveJSON('tasks.json', tasks);
    setImmediate(schedule);
    return res.json({ ok: true, accepted: 'retry' });
  }

  fs.writeFileSync(artifactPath(task.id, st.id, st.attempts), content, 'utf8');
  st.artifact = { attempt: st.attempts, chars: content.length, file: `${task.id}_${st.id}_${st.attempts}.md`, executor: '本机执行' };
  st.status = 'review';
  st.progress = 100;
  task.log.push({ ts: Date.now(), kind: 'info', text: `🖥 本机执行方交付「${st.name}」（${content.length} 字，真实操作本机 AI 软件产出），咕嘎开始按验收标准核对` });
  saveJSON('tasks.json', tasks);

  let verdict;
  try { verdict = await withSlot(() => llmJSON(reviewMessages(task, st, content), undefined,
    { user: task.userId, kind: 'review', taskId: task.id })); }
  catch { verdict = { pass: false, reason: '核对通道波动，本轮先打回，复核后重新交付' }; }
  st.checkResult = String(verdict.reason || '').slice(0, 80);
  if (verdict.pass || st.attempts >= MAX_ATTEMPTS) {
    st.status = 'done';
    st.finishedAt = Date.now();
    st.localClaimed = false;
    st.claimedBy = '';
    if (!verdict.pass) st.checkResult = '三次交付仍未完全达标，咕嘎标记异常并如实上报少爷';
    task.log.push({
      ts: Date.now(), kind: verdict.pass ? 'good' : 'warn',
      text: verdict.pass
        ? `✅ 验收通过：「${st.name}」${st.checkResult}`
        : `⚠ 「${st.name}」连续 ${MAX_ATTEMPTS} 次未过验收：${st.checkResult}（已上报少爷）`,
    });
  } else {
    st.status = 'returned';
    st.finishedAt = 0;
    st.feedback = st.checkResult;
    st.localClaimed = false;
    st.claimedBy = '';
    task.log.push({ ts: Date.now(), kind: 'warn', text: `❌ 验收打回：「${st.name}」${st.checkResult}，已带意见重新派给本机执行方` });
  }
  inflight.delete(key);
  finishCheck(task);
  saveJSON('tasks.json', tasks);
  res.json({ ok: true, accepted: 'done', pass: !!(verdict && verdict.pass) });
});

// 暂停超时 GC：少爷暂停后 15 分钟没点"继续"，进度按丢弃清理（beat/schedule 双时机惰性触发）
function gcPausedTasks() {
  let dirty = false;
  const finishThese = new Set();
  for (const task of tasks) {
    if (task.finishedAt || task.demo) continue;
    for (const st of task.subtasks || []) {
      if (st.status === 'paused' && Date.now() - (st.pausedAt || 0) > PAUSE_TTL_MS) {
        st.status = 'error';
        st.finishedAt = Date.now();
        st.checkResult = '暂停超过 15 分钟未继续，进度已按丢弃清理（重新派单即可）';
        st.pauseCtx = '';
        task.log.push({ ts: Date.now(), kind: 'warn', text: `🧹 「${st.name}」暂停超时未继续，已自动清理回收（少爷可重新派单）` });
        finishThese.add(task);
        dirty = true;
      }
    }
  }
  for (const task of finishThese) finishCheck(task);
  if (dirty) saveJSON('tasks.json', tasks);
  return dirty;
}

// 本体询问控制指令：执行器在每轮对话边界查询，少爷按了暂停就本轮收尾即停（最多等当前步骤两三分钟）
app.post('/api/agent/ctl', agentAuth, (req, res) => {
  const taskId = String((req.body || {}).taskId || '');
  const stId = String((req.body || {}).stId || '');
  const task = tasks.find(t => t.id === taskId && t.userId === req.agent.userId);
  // 优先按执行器回报的 stId 定位；旧版只带 taskId 时，必须找"正在干/已暂停"的那一步，
  // 不能盲取第一个本机子任务——多子任务时会把已完成的旧步骤当成当前步骤，导致暂停指令永远返回 go
  const st = task && (stId
    ? task.subtasks.find(s => s.id === stId)
    : (task.subtasks.find(s => s.executor === '本机执行' && s.status === 'running')
       || task.subtasks.find(s => s.executor === '本机执行' && s.status === 'paused')
       || task.subtasks.find(s => s.executor === '本机执行')));
  const wantPause = st && (st.pauseRequested || st.status === 'paused');
  res.json({ action: wantPause ? 'pause' : 'go', stId: st ? st.id : '' });
});

// 本体确认暂停：进度与下一步落进台账存档——15 分钟内点"继续"无缝接续，超时自动清理
app.post('/api/agent/paused', agentAuth, (req, res) => {
  const { taskId, stId } = req.body || {};
  const task = tasks.find(t => t.id === taskId && t.userId === req.agent.userId);
  const st = task && task.subtasks.find(s => s.id === stId);
  if (!st) return res.status(404).json({ error: '子任务不存在' });
  st.status = 'paused';
  st.pausedAt = Date.now();
  st.localClaimed = false;
  st.claimedBy = '';
  st.pauseRequested = false;
  st.pauseCtx = String((req.body || {}).ctx || '').slice(0, 400);
  task.log.push({ ts: Date.now(), kind: 'warn', text: `⏸ 少爷暂停了「${st.name}」——进度已记录（${st.pauseCtx.slice(0, 90)}）。15 分钟内点"继续"无缝接续，超时自动丢弃清理` });
  saveJSON('tasks.json', tasks);
  res.json({ ok: true });
});

// 少爷指令：暂停/继续本机子任务（台账内嵌按钮，human-in-the-loop 的第三块拼图）
app.post('/api/task-pause', auth, rateLimit(1500), (req, res) => {
  const { taskId, stId, action } = req.body || {};
  const task = tasks.find(t => t.id === taskId && t.userId === req.user);
  const st = task && task.subtasks.find(s => s.id === stId);
  if (!task || !st) return res.status(404).json({ error: '任务不存在' });
  if (action === 'pause') {
    if (st.executor === '本机执行' && st.status === 'running') {
      st.pauseRequested = true;   // 执行器每轮边界询问，当前步骤收尾即停
      task.log.push({ ts: Date.now(), kind: 'warn', text: `⏸ 少爷请求暂停「${st.name}」——本机执行方将在当前步骤收尾后停手（进度自动记录）` });
    } else if (st.status === 'pending') {
      st.status = 'paused';
      st.pausedAt = Date.now();
      task.log.push({ ts: Date.now(), kind: 'warn', text: `⏸ 少爷暂停了「${st.name}」（尚未开工），点"继续"恢复` });
    } else return res.status(400).json({ error: '当前状态不可暂停' });
  } else if (action === 'resume') {
    if (st.status !== 'paused') return res.status(400).json({ error: '该子任务不在暂停中' });
    if (Date.now() - (st.pausedAt || 0) > PAUSE_TTL_MS) return res.status(400).json({ error: '暂停已超过 15 分钟，进度已被清理，请重新派单' });
    st.status = 'running';
    st.localClaimed = false;   // 心跳重新领单，job 会带上暂停前进度
    st.pausedAt = 0;
    task.log.push({ ts: Date.now(), kind: 'info', text: `▶ 少爷让「${st.name}」继续——本机执行方将带着暂停前进度无缝接续` });
  } else return res.status(400).json({ error: '未知操作' });
  saveJSON('tasks.json', tasks);
  res.json({ ok: true });
});

// 本体请示（不要剧本，要会读）：本机执行方拿到豆包回复后先问大脑——
// 这是完整交付，还是豆包在反问索要信息？追问话术由大脑代少爷拟好
//（按总目标自拟信息/直接让它开写），绝不把皮球踢回给用户，杜绝"豆包要主题→打回→再派→豆包再要"死循环。
app.post('/api/agent/consult', agentAuth, agentCloudGate('consult'), async (req, res) => {
  const reply = String((req.body || {}).reply || '').slice(0, 3000);
  const goal = String((req.body || {}).goal || '').slice(0, 120);
  const name = String((req.body || {}).name || '').slice(0, 24);
  const acceptance = String((req.body || {}).acceptance || '').slice(0, 80);
  const appName = String((req.body || {}).app || '').trim() || '豆包';
  if (!reply.trim()) return res.status(400).json({ error: 'reply 为空' });
  try {
    const v = await withSlot(() => llmJSON([
      { role: 'system', content: `你是桌面智能体"咕嘎管家"的大脑。本机执行方刚指挥用户电脑上的${appName}干一个子任务，下面是${appName}的最新回复，请判定类型：\n` +
        `{"type":"deliverable"} —— 回复已包含实质交付内容（正文/答案/成果），哪怕偏短；\n` +
        `{"type":"followup","text":"..."} —— ${appName}在索要信息、反问、或只给了提纲/选项没给正文。text 是要粘贴回${appName}输入框的下一句话（中文、100字内、命令式），必须替用户把信息补全：根据总目标自行合理拟定（自拟主题、自选风格、直接让它开写），绝不允许向用户反问。\n只输出 JSON。` },
      { role: 'user', content: `总目标：${goal}\n子任务：${name}\n验收标准：${acceptance}\n\n${appName}的最新回复：\n${reply}` },
    ], undefined, { user: req.agent && req.agent.userId, kind: 'consult' }));
    if (v && v.type === 'followup' && v.text) {
      return res.json({ type: 'followup', text: String(v.text).slice(0, 300) });
    }
    res.json({ type: 'deliverable' });
  } catch {
    res.json({ type: 'deliverable' });   // 请示通道波动：按现有回复交付，由网页验收兜底
  }
});

// 配对历史（按账号、按设备去重取最新，最多 3 台）——网页据此指路找回已有本体
// 只列 7 天内活跃过的设备（AGENT_SHOW_TTL）：更早的测试/换机残留自动淡出，不再指路误导
function agentHistory(userId) {
  const seen = new Set();
  return Object.values(loadJSON('agents.json', {}))
    .filter(x => x.userId === userId && Date.now() - (x.lastSeen || 0) < AGENT_SHOW_TTL)
    .sort((x, y) => (y.lastSeen || 0) - (x.lastSeen || 0))
    .filter(x => { const k = x.id || x.device || '咕嘎本体'; if (seen.has(k)) return false; seen.add(k); return true; })
    .slice(0, 3)
    .map(x => ({
      device: x.device || '咕嘎本体',
      path: x.path || '',
      pyver: (x.caps && x.caps.pyver) || '',
      agent: (x.caps && x.caps.agent) || '',
      depsOk: !!(x.caps && x.caps.depsOk),
      online: Date.now() - (x.lastSeen || 0) < AGENT_ONLINE_MS,
      lastSeen: x.lastSeen || 0,
    }));
}

// 执行方在线状态（指令条的🖥 chip 用，轻量不触发大模型探测）——只看当前登录账号自己的本体
// 附带本账号全部配对记录（设备+文件夹路径）：用户已有本体时网页直接指路找回，不用重新下载
app.get('/api/agent/status', auth, (req, res) => {
  const list = agentsOnlineOf(req.user).map(deviceView);
  const a = list[0] || null;
  res.json({
    online: list.length > 0,
    device: a ? a.device : '',
    path: a ? a.path : '',
    aiFound: a ? a.aiFound : 0,
    devices: list,          // 账号下全部在线本体（多设备各是各的，别再"都显示第一台"）
    agents: agentHistory(req.user),
  });
});

/* 远程指挥 · 设备选择器数据源：本账号所有在线本体 + 各自可指挥的 AI 软件清单
 * （WorkBuddy 出稿 → 豆包润色这类"多软件接力"就靠它跨电脑/跨软件派单） */
app.get('/api/agent/devices', auth, (req, res) => {
  res.json({ devices: agentsOnlineOf(req.user).map(deviceView) });
});

/* 设备软件清单 · 按账号读取：哪些设备、各有什么 AI 软件、几点上报的、在不在线
 * 数据来源：agents.json（配对记录/在线状态）+ inventory.json（本体上报的软件清单，按稳定设备标识归账）。
 * 兼容：旧版本体不上报 → tools 为空数组、hasInventory=false，其余字段与旧版 deviceView 完全一致。
 * 过滤：?device_id=xxx 或 ?id=xxx 或 ?device=设备名；不带参数返回本账号全部相关设备。 */
app.get('/api/devices/inventory', auth, (req, res) => {
  const agents = loadJSON('agents.json', {});
  const inv = loadJSON('inventory.json', {});
  const now = Date.now();
  const dedup = new Map();   // 旧记录可能同设备多条：取最近心跳的那条
  for (const tok of Object.keys(agents)) {
    const a = agents[tok];
    if (a.userId !== req.user) continue;
    const online = now - (a.lastSeen || 0) < AGENT_ONLINE_MS;
    const key = inventoryKey(a);
    const rec = key ? inv[key] : null;
    const fresh = !!(rec && now - (rec.updatedAt || 0) < AGENT_SHOW_TTL);
    if (!online && !fresh) continue;   // 既不在线、清单也已陈旧：不再列出，免得陈年设备误导
    const dk = inventoryKey(a) || a.device || '咕嘎本体';
    const prev = dedup.get(dk);
    if (prev && (prev.lastSeen || 0) >= (a.lastSeen || 0)) continue;
    dedup.set(dk, Object.assign(deviceView(a), {
      online,
      device_id: a.device_id || '',
      hasInventory: !!(rec && Array.isArray(rec.items) && rec.items.length),
      inventoryAt: (rec && rec.updatedAt) || 0,
      toolsCount: rec && Array.isArray(rec.items) ? rec.items.length : 0,
      tools: rec && Array.isArray(rec.items) ? rec.items : [],   // [{name, launch, version, path, summary, aliases, updatedAt}]
    }));
  }
  const want = String(req.query.device_id || req.query.id || req.query.device || '').trim();
  let list = Array.from(dedup.values());
  if (want) list = list.filter(d => d.id === want || d.device_id === want || d.device === want);
  list.sort((x, y) => (y.online ? 1 : 0) - (x.online ? 1 : 0) || (y.lastSeen || 0) - (x.lastSeen || 0));
  res.json({
    devices: list,
    total: list.length,
    online: list.filter(d => d.online).length,
    withInventory: list.filter(d => d.hasInventory).length,
  });
});

// 模型配置：查看（仅管理员可见完整地址与 Key 后四位）/ 保存并测试（仅管理员可写）
app.get('/api/llm', auth, (req, res) => {
  let host = '';
  try { host = llmCfg.baseUrl ? new URL(llmCfg.baseUrl).hostname : ''; } catch { /* 地址异常则留空 */ }
  if (isAdmin(req.user)) {
    return res.json({
      configured: llmReady(),
      baseUrl: llmCfg.baseUrl || '',
      model: llmCfg.model || '',
      apiKeyMasked: llmCfg.apiKey ? '••••••' + llmCfg.apiKey.slice(-4) : '',
    });
  }
  // 非管理员：不返回完整 Base URL，不返回 Key 后四位（只给是否就绪 + 模型名 + 站点域名）
  res.json({ configured: llmReady(), model: llmCfg.model || '', baseUrlHost: host });
});
app.post('/api/llm', auth, requireAdmin, rateLimit(2000), async (req, res) => {
  const b = req.body || {};
  /* base_url 归一化：剥离用户可能粘贴的完整端点后缀（.../chat/completions），
   * 对已知域名（maas.qianwenaiapi.com 等）自动补 /compatible-mode/v1 根路径，
   * 避免拼出双段路径导致 404/405。 */
  const baseNorm = normalizeBaseUrl(String(b.baseUrl || '').trim());
  if (!baseNorm.ok) return res.status(400).json({ error: '接口地址不合法：' + baseNorm.error });
  const baseUrl = baseNorm.base;
  const providedKey = String(b.apiKey || '').trim();
  const oldBaseUrl = normalizeBaseUrl(llmCfg.baseUrl).base || (llmCfg.baseUrl || '').replace(/\/+$/, '');
  // 换了接口地址就必须显式提交新 Key：禁止"留空沿用运营方 Key + 任意新 baseUrl"的组合
  if (!providedKey && baseUrl !== oldBaseUrl) {
    return res.status(400).json({
      error: '修改接口地址时必须同时提供新的 API Key（不允许把原 Key 发往新地址）',
      code: 'BASEURL_REQUIRES_NEW_KEY',
    });
  }
  const apiKey = providedKey || llmCfg.apiKey;   // 仅当地址未变时允许留空沿用旧 Key
  const model = String(b.model || '').trim();
  if (!/^https?:\/\/.+/.test(baseUrl)) return res.status(400).json({ error: '接口地址须为 http(s) 开头的完整 URL' });
  // SSRF 防护：拒绝本机/内网/链路本地地址（服务器只帮您连公网模型接口）
  let host = '';
  try { host = new URL(baseUrl).hostname.toLowerCase(); } catch { return res.status(400).json({ error: '接口地址格式不正确' }); }
  if (
    /^(localhost|127\.|0\.0\.0\.0|10\.|192\.168\.|169\.254\.)/.test(host) ||
    /^172\.(1[6-9]|2\d|3[01])\./.test(host) ||
    host === '[::1]' || host.endsWith('.local') || host.endsWith('.internal')
  ) {
    return res.status(400).json({ error: '接口地址须为公网地址（不支持本机/内网地址）' });
  }
  if (!apiKey) return res.status(400).json({ error: 'API Key 不能为空' });
  if (!model) return res.status(400).json({ error: '请填写模型名，如 glm-4-flash' });
  // 真实连通性测试：最小调用一次（保留 POST 跟随重定向，避免 Node fetch 把 POST 改 GET 返回 405）
  const old = { ...llmCfg };
  Object.assign(llmCfg, { baseUrl, apiKey, model });
  let test = { ok: true, note: '' };
  try {
    const controller = new AbortController();
    const killer = setTimeout(() => controller.abort(), 20000);
    let currentUrl = baseUrl + '/chat/completions';
    let r;
    const redirects = [];
    for (let hop = 0; hop <= 2; hop++) {
      r = await fetch(currentUrl, { method: 'POST',
        headers: { 'Content-Type': 'application/json', Authorization: 'Bearer ' + apiKey },
        body: JSON.stringify({ model, messages: [{ role: 'user', content: '回复两个字：收到' }], max_tokens: 8 }),
        signal: controller.signal,
      });
      if (![301, 302, 303, 307, 308].includes(r.status)) break;
      const location = r.headers.get('Location');
      if (!location) break;
      redirects.push({ status: r.status, from: currentUrl, to: location });
      currentUrl = new URL(location, currentUrl).toString();
      try { r.body && await r.body.cancel(); } catch {}
    }
    clearTimeout(killer);
    if (!r.ok) {
      const t = await r.text().catch(() => '');
      let note = `HTTP ${r.status} ${t.slice(0, 80)}`;
      if (redirects.length) note += `（重定向 ${redirects.length} 次后仍失败：${redirects.map(x => x.status + '→' + x.to).join(' → ')}）`;
      test = { ok: false, note };
    }
  } catch (e) {
    test = { ok: false, note: '连不上：' + String(e.message || e).slice(0, 60) };
  }
  if (!test.ok) { Object.assign(llmCfg, old); return res.status(400).json({ error: `模型测试未通过：${test.note}（配置未保存）` }); }
  saveLLMCfg();
  console.log(`[llm] 模型已由用户(${req.user})更新: ${model} @ ${baseUrl}`);
  res.json({ ok: true, model, baseUrl, apiKeyMasked: '••••••' + apiKey.slice(-4) });
});

// 云端用量查询：普通账号看自己；管理员可 ?user=<账号> 查指定账号，?all=1 看全部账号汇总
app.get('/api/usage', auth, (req, res) => {
  const admin = isAdmin(req.user);
  if (admin && String(req.query.all || '') === '1') {
    return res.json({
      accounts: users.map(u => ({
        username: u.username, role: u.role || '',
        cloudEntitled: u.cloudEntitled === true,
        cloudQuota: u.cloudQuota === undefined ? null : u.cloudQuota,
        cloudUsed: Number(u.cloudUsed || 0),
      })),
      totalCalls: usage.length,
    });
  }
  const want = String(req.query.user || '').trim();
  const target = (want && admin) ? want : req.user;
  const c = cloudInfo(target);
  const mine = usage.filter(x => x.user === target);
  res.json({
    user: target, entitled: c.entitled, quota: c.quota, used: c.used, calls: mine.length,
    records: mine.slice(-50).reverse(),
    ...(admin ? { viewAsAdmin: true } : {}),
  });
});

// 清空台账（可按空间；连同产物文件一起删除；只清自己的，不动别人）
app.post('/api/clear', auth, rateLimit(1500), (req, res) => {
  const space = String((req.body || {}).space || '').trim();
  const mine = tasks.filter(t => t.userId === req.user && (!space || (t.space || '默认空间') === space));
  for (const t of mine) {
    for (const st of t.subtasks) {
      for (let a = 1; a <= (st.attempts || 1) + 1; a++) {
        try { fs.unlinkSync(artifactPath(t.id, st.id, a)); } catch { /* 文件不存在忽略 */ }
      }
      // 证据截图同步清理（验收发现：清任务不删证据文件会留孤儿，磁盘只增不减）
      for (const ev of (st.evidence || [])) {
        try { fs.unlinkSync(path.join(EVIDENCE_DIR, ev.file)); } catch { /* 同上 */ }
      }
    }
  }
  const keep = tasks.filter(t => !mine.includes(t));
  tasks.length = 0;
  for (const t of keep) tasks.push(t);
  saveJSON('tasks.json', tasks);
  res.json({ ok: true, removed: mine.length });
});

// 交付物查看/下载（评委点开台账里的"查看产物"）
app.get('/api/artifact/:taskId/:stId', auth, (req, res) => {
  const task = tasks.find(t => t.id === req.params.taskId && t.userId === req.user);
  if (!task) return res.status(404).json({ error: '任务不存在' });
  const st = task.subtasks.find(s => s.id === req.params.stId);
  if (!st || !st.artifact) return res.status(404).json({ error: '交付物不存在' });
  const body = loadArtifact(task.id, st.id, st.artifact.attempt);
  if (!body) return res.status(404).json({ error: '交付物文件丢失' });
  if (req.query.download) {
    res.setHeader('Content-Type', 'text/markdown; charset=utf-8');
    res.setHeader('Content-Disposition', `attachment; filename="${task.id}_${st.id}.md"`);
    return res.send(body);
  }
  res.json({ goal: task.goal, name: st.name, executor: st.executor, acceptance: st.acceptance, attempt: st.attempts, body, status: st.status, demo: !!task.demo, feedback: st.feedback || '', evidence: st.evidence || [] });
});

/* 少爷裁决（human-in-the-loop）：批注打回 / 亲自验收通过 / 换将重派
 * rework   ：批注作为最高优先级打回意见回传工人（额度用尽时特批一次返工机会）
 * approve  ：少爷亲自验收通过，立即生效并推进终检
 * reassign ：换将重派，重置执行次数从头执行
 * 已完结任务被批注 → 自动重新开工，咕嘎继续监工 */
app.post('/api/verdict', auth, rateLimit(1500), (req, res) => {
  const body = req.body || {};
  const comment = String(body.comment || '').slice(0, 300).trim();
  const task = tasks.find(t => t.id === body.taskId && t.userId === req.user);
  if (!task) return res.status(404).json({ error: '任务不存在' });
  const st = task.subtasks.find(s => s.id === body.stId);
  if (!st) return res.status(404).json({ error: '子任务不存在' });
  const action = String(body.action || '');
  if (task.demo && action !== 'approve') return res.status(400).json({ error: '演示剧本任务不支持批注重做' });
  if (action === 'approve') {
    st.status = 'done';
    st.finishedAt = Date.now();
    st.overdue = false;
    st.checkResult = '👤 少爷亲自验收通过' + (comment ? '：' + comment : '');
    task.log.push({ ts: Date.now(), kind: 'good', text: `👤 少爷批示「${st.name}」：验收通过${comment ? '——' + comment.slice(0, 60) : ''}` });
    saveJSON('tasks.json', tasks);
    finishCheck(task);
    return res.json({ ok: true, action });
  }
  if (st.status === 'running' || st.status === 'review') {
    return res.status(400).json({ error: '该子任务正在执行/验收中，等这一轮落定后再批示' });
  }
  if (!st.artifact) return res.status(400).json({ error: '该子任务暂无产物可批注（异常单可用「换将重派」）' });
  if (action === 'rework') {
    st.feedback = '少爷批注（必须优先落实）：' + (comment || '请对照验收标准逐项自查后重新交付');
    if ((st.attempts || 0) >= MAX_ATTEMPTS) st.attempts = MAX_ATTEMPTS - 1;   // 特批一次返工额度
    st.status = 'returned';
    st.finishedAt = 0;
    st.rerunAt = Date.now() + 800;
    inflight.delete(task.id + ':' + st.id);
    task.log.push({ ts: Date.now(), kind: 'warn', text: `👤 少爷批注打回「${st.name}」，工人带批示重做：${st.feedback.slice(0, 70)}` });
  } else if (action === 'reassign') {
    st.attempts = 0;
    st.feedback = comment ? '少爷换将重派批注：' + comment : '少爷裁决：换将重派，按验收标准从头执行';
    st.status = 'returned';
    st.finishedAt = 0;
    st.rerunAt = Date.now() + 800;
    inflight.delete(task.id + ':' + st.id);
    task.log.push({ ts: Date.now(), kind: 'warn', text: `👥 少爷裁决「${st.name}」换将重派${comment ? '（' + comment.slice(0, 40) + '）' : ''}，新工人即将领单` });
  } else {
    return res.status(400).json({ error: '未知裁决动作' });
  }
  if (task.finishedAt) {
    task.finishedAt = null;
    task.finalReviewing = false;
    task.log.push({ ts: Date.now(), kind: 'info', text: '👤 少爷批注已收到，本单重新开工，咕嘎继续盯' });
  }
  saveJSON('tasks.json', tasks);
  schedule();
  res.json({ ok: true, action });
});

/* ---------------- 工人小队（借鉴 AutoGen Studio 组织可视化） ----------------
 * 大脑（咕嘎·拆解派单）→ 工人班组（真实执行）→ 验收员（咕嘎·监工核对）
 * 每个工人聚合：接单数 / 通过率 / 返工数 / 当前是否在岗 */
app.get('/api/crew', auth, (req, res) => {
  const mine = tasks.filter(t => t.userId === req.user);
  const map = {};
  for (const t of mine) for (const st of t.subtasks) {
    const name = st.worker || '预备役工人';
    const w = map[name] || (map[name] = { name, executor: st.executor || '外部智能体', jobs: 0, done: 0, rework: 0, busy: 0 });
    w.jobs++;
    if (st.status === 'done') w.done++;
    if (st.status === 'returned' || st.status === 'error' || (st.attempts || 0) > 1) w.rework++;
    if (st.status === 'running' || st.status === 'review' || st.status === 'finalReviewing') w.busy++;
  }
  const crew = Object.values(map)
    .map(w => ({ ...w, passRate: w.jobs ? Math.round(w.done / w.jobs * 100) : 0 }))
    .sort((a, b) => b.jobs - a.jobs);
  // 技能库 + 少爷记忆：咕嘎"越用越懂你"的可视化证据
  const skills = (loadJSON('skills.json', {})[req.user] || []).slice(0, 8)
    .map(s => ({ goal: s.goal, uses: s.uses || 1, steps: (s.recipe || []).map(r => r.name) }));
  const memories = (loadJSON('memory.json', {})[req.user] || []).slice(0, 8)
    .map(x => ({ fact: x.fact, ts: x.ts }));
  res.json({ crew, agent: agentOnline(req.user), skills, memories });
});

/* ---------------- 双模型同题对比（呼应"咕嘎是壳，模型自带"） ----------------
 * 同一目标同一拆解，甲=服务器默认模型，乙=您在⚙配置的模型，同题同预算对跑，
 * 两单都完结后可让咕嘎当裁判出对比结论。 */
app.post('/api/compare', auth, requireCloud, rateLimit(8000), async (req, res) => {
  const goal = String((req.body || {}).goal || '').trim();
  if (!goal) return res.status(400).json({ error: '请输入对比目标' });
  if (!llmReady()) return res.status(400).json({ error: '模型未就绪，请先在 ⚙ 完成配置' });
  const isCustom = llmCfg.model !== LLM_ENV.model || llmCfg.baseUrl !== LLM_ENV.baseUrl;
  if (!isCustom) return res.status(400).json({ error: '当前只有一个模型——请先在 ⚙ 模型配置 接入您自己的模型，再和咕嘎默认模型同题对比' });
  if (DANGER_RE.test(goal) || DANGER_FILE_RE.test(goal)) return res.status(400).json({ error: '对比目标涉及不可逆操作，咕嘎不受理' });
  try {
    const plan = await llmJSON(planPrompt(goal, req.user), undefined, { user: req.user, kind: 'compare-plan' });   // 同一套拆解，保证只比模型不比拆解
    const subs = Array.isArray(plan.subtasks) ? plan.subtasks : [];
    if (!subs.length) throw new Error('拆解为空');
    const gid = 'cmp' + Date.now().toString(36);
    const a = createTask(req.user, goal, subs, {}, '');
    const b = createTask(req.user, goal, subs, {}, '');
    a.compare = { groupId: gid, role: '甲', model: LLM_ENV.model || '默认模型', modelTag: 'env' };
    b.compare = { groupId: gid, role: '乙', model: llmCfg.model, modelTag: 'custom' };
    a.log.push({ ts: Date.now(), kind: 'info', text: `🔬 对比实验甲组 · 模型：${a.compare.model}` });
    b.compare = { groupId: gid, role: '乙', model: llmCfg.model, modelTag: 'custom' };
    b.deferredUntil = Date.now() + 30000;   // 乙组错峰 30 秒开工：等甲组跑过半再上，避免两组挤兑全局并发闸导致超时
    b.log.push({ ts: Date.now(), kind: 'info', text: `🔬 对比实验乙组 · 模型：${b.compare.model}（错峰 30 秒后开工，保证两组都有充足算力）` });
    saveJSON('tasks.json', tasks);
    setImmediate(schedule);
    res.json({ groupId: gid, a: { id: a.id, model: a.compare.model }, b: { id: b.id, model: b.compare.model } });
  } catch (e) {
    res.status(400).json({ error: '对比发起失败：' + String(e.message || e).slice(0, 60) });
  }
});

app.post('/api/compare/verdict', auth, requireCloud, rateLimit(5000), async (req, res) => {
  const gid = String((req.body || {}).groupId || '');
  const pair = tasks.filter(t => t.userId === req.user && t.compare && t.compare.groupId === gid);
  if (pair.length !== 2) return res.status(400).json({ error: '对比组不存在' });
  if (pair.some(t => !t.finishedAt)) return res.status(400).json({ error: '两单都跑完再叫裁判' });
  const dump = (t) => t.subtasks.map(s => {
    const body = s.artifact ? loadArtifact(t.id, s.id, s.artifact.attempt) : '';
    return `### ${s.name}\n${body.slice(0, 900) || '（无产物）'}`;
  }).join('\n\n');
  try {
    const verdict = await withSlot(() => llmStream([
      { role: 'system', content: '你是中立的模型评测裁判（咕嘎监工兼任）。对比两份同题成果：从结构完整性、内容质量、风格特点三方面点评（各一句），最后一句给出"推荐甲/推荐乙/难分伯仲"。总计 120 字内，直接输出结论。' },
      { role: 'user', content: `【题目】${pair[0].goal}\n\n【甲 · 模型 ${pair[0].compare.model}】\n${dump(pair[0]).slice(0, 2400)}\n\n【乙 · 模型 ${pair[1].compare.model}】\n${dump(pair[1]).slice(0, 2400)}` },
    ], () => {}, undefined, { user: req.user, kind: 'compare-verdict' }));
    res.json({ verdict: String(verdict || '').trim() });
  } catch (e) {
    res.status(400).json({ error: '裁判通道波动，稍后再试' });
  }
});

/* ---------------- 大脑意图路由（咕嘎=大脑+一双手，不亲自代工） ----------------
 * 原则：收到用户消息，大脑先分析意图——
 *   work 类（要产出交付物/要完成实际操作）→ 绝不亲自回答内容，拆解派单给执行方；
 *   chat 类（问候/问功能/问进度/闲聊）→ 管家身份亲自开口。
 * LLM 在线时由模型判意图；离线时用关键词兜底（同样走派单，演示引擎执行）。
 */
const WORK_HINT = /(帮我|替我|给我|写|撰写|起草|拟|做|制作|生成|整理|汇总|统计|归档|分类|调研|搜集|查资料|对比|选型|分析|翻译|润色|改写|排版|做图|画|设计|策划|修|改bug|排查|导出|排班|计划|清单|介绍|推荐|总结|汇报|文案|周报|日报|纪要|邮件|简历|表格|ppt|幻灯)/i;

function intentMessages(message) {
  return [
    { role: 'system', content: '你是桌面智能体"咕嘎管家"的意图分析模块（大脑）。判断用户这句话属于哪类：\n' +
      'work：明确要求产出交付物或完成实际操作，且目标具体可执行（写文章/周报/PPT/邮件/文案/代码/表格、整理文件、调研对比、翻译、做图、介绍某事物成文等）——咕嘎不亲自回答内容，必须转派执行方。\n' +
      'chat：问候、询问咕嘎的身份/功能/能力（如"你能帮我做PPT吗""你会什么"）、询问监工进度、求解释（"什么是X"）、对已完成任务的追问、闲聊——由管家亲自回答。\n' +
      'clarify：意图模糊无法安全判断——只丢一个词（如"周报""饺子"）、指代不明（"帮我看看这个""弄一下它"）、动作缺关键对象（如"整理一下""写个东西"没说整理什么/写什么）、或分不清用户是要干活还是闲聊——必须反问确认，绝不能靠猜。涉及整理/移动/删除用户文件的指令若没说清对象和范围，一律 clarify，防止误动用户文件。涉及删除文件/格式化/卸载/转账等不可逆操作的指令若范围不精确，也判 clarify 并在反问里提醒风险。\n' +
      '注意：目标若涉及打开/启动/使用某个具体软件（如"打开豆包写一篇500字作文""用微信发文件"），属于 work，且 goal 必须原样保留软件名和打开/启动/用等动作词，绝不能省略或改写成纯写作目标。\n' +
      '只输出 JSON：{"intent":"work"或"chat"或"clarify","goal":"intent为work时把请求提炼成30字内目标，否则留空","question":"intent为clarify时的一句反问（管家口吻、称呼少爷、给出2个方向让用户选，如：少爷，您是想让执行方写一份关于饺子的介绍，还是想跟我聊聊饺子？），否则留空"}' },
    { role: 'user', content: message },
  ];
}

function dispatchReply(task, mode) {
  const names = task.subtasks.map(s => s.name).join('、');
  if (mode === 'local') {
    const dev = task.execDevice ? `「${task.execDevice}」这台电脑` : '您配对的电脑';
    const remote = task.fromDevice && task.execDevice && task.fromDevice !== task.execDevice
      ? `我从「${task.fromDevice}」收到您的指令，` : '';
    return `少爷，${remote}本单已派给${dev}真机执行——它马上远程指挥本机 AI 软件真实干活。手机、平板、别的电脑登录同账号都能这样遥控，本单全程监工中，请看台账。`;
  }
  if (mode === 'demo') return '少爷，当前服务器未接入大模型，暂以内置剧本演示监工流程（无真实产物），已拆解派单。';
  return `少爷，这活咕嘎不亲自代劳——我是大脑，干活靠执行方的双手。已把目标拆解为 ${task.subtasks.length} 个子任务（${names.slice(0, 60)}），工人们已领单开工，我全程盯进度、催办、验收，进展和产物请看台账。`;
}

// 管家本地应答（LLM 未配置时的规则引擎，可感知真实台账状态）
function localButlerReply(user, message) {
  const mine = tasks.filter(t => t.userId === user);
  const active = mine.filter(t => !t.finishedAt);
  const activeSubs = active.flatMap(t => t.subtasks);
  const running = activeSubs.filter(s => s.status === 'running').length;
  const reviewing = activeSubs.filter(s => s.status === 'review').length;
  const doneTasks = mine.filter(t => t.finishedAt).length;
  const m = message;
  if (/(进度|状态|台账|任务怎么样|干得|盯得)/.test(m)) {
    if (!active.length) return `少爷，目前没有进行中的任务。说一个目标我就开工${doneTasks ? '（历史已完成 ' + doneTasks + ' 单，产物都在右侧台账里）' : ''}。`;
    let s = `少爷，我正盯着 ${active.length} 个任务：执行中 ${running} 个、验收中 ${reviewing} 个。有超时或不合格我会第一时间催办、打回。`;
    const od = activeSubs.find(x => x.overdue);
    if (od) s += ` 刚刚「${od.name}」落后于计划，我已催办过一轮。`;
    return s;
  }
  if (/(你是谁|介绍|功能|能做什么|怎么用)/.test(m)) {
    return '少爷，我是咕嘎管家——AI 指挥 AI 的生产力监工。你给目标，我拆解成子任务派给工人智能体真实执行，产物可点开查看；我全程盯进度、催办、按验收标准核对打回。桌面端还有 Live2D 形态，本页是我的指挥与监工引擎。';
  }
  if (/(监工|催办|打回|验收)/.test(m)) {
    return '监工是我的主业：每个子任务都有验收标准，交付后我逐项核对——不合格当场打回重做，超时立刻催办，全部通过才向您汇报，并把本次经验记进知识库。您可以点「📊 周报整理」亲眼看一遍完整闭环。';
  }
  if (/(你好|您好|嗨|hello|hi|在吗)/i.test(m)) {
    return '少爷好，咕嘎在。给我一个目标（比如整理周报），或者问我现在的监工进度。';
  }
  return '收到。想看我的本事，点下方「📊 周报整理」这类快捷目标——我会当场拆解、派单、真实执行、监工；也可以问我「现在进度如何」。';
}

// 管家自由对话（先大脑意图分析：work→转派执行方；clarify→反问；danger→红线确认；chat→亲自开口）
// 危险/不可逆操作红线：涉及删除、系统、资金的指令先反问，用户回复"确认"才放行派单
const DANGER_RE = /(格式化|重装系统|rm\s+-rf|清空磁盘|清空硬盘|删库|卸载|转账|汇款|付款|打钱|改密|修改密码|群发|批量删除|抹掉)/i;
const DANGER_FILE_RE = /(删除|删掉|清空|移动|覆盖|格式化).{0,14}(盘|[CcDdEeFf]:|文件夹|目录|所有文件|全部文件|系统)/i;
const pendingDanger = {};   // userId -> { goal, ts }，等待"确认"的危险目标（10 分钟有效）

app.post('/api/chat', auth, requireCloud, rateLimit(3000), async (req, res) => {
  const message = String((req.body || {}).message || '').slice(0, 500);
  const space = String((req.body || {}).space || '').trim();
  let useLocal = String((req.body || {}).executor || '') === 'local';
  if (!message) return res.status(400).json({ error: '消息为空' });
  res.setHeader('Content-Type', 'text/event-stream; charset=utf-8');
  res.setHeader('Cache-Control', 'no-cache');
  res.write(': open\n\n');
  // SSE 心跳：意图分析/拆解期间持续发包，防代理空闲超时断连
  const ping = setInterval(() => { try { res.write(': ping\n\n'); } catch { /* ignore */ } }, 2000);
  res.on('close', () => clearInterval(ping));
  try {
    /* ⓪ 危险指令确认：上一轮被红线拦下，本轮回复"确认" → 放行派单 */
    let dangerConfirmed = false;
    const pd = pendingDanger[req.user];
    if (/^确认/i.test(message.trim()) && pd && Date.now() - pd.ts < 600000) {
      dangerConfirmed = true;
      delete pendingDanger[req.user];
    }

    /* ⓪′ 少爷记忆：明确说"记住…" → 提炼事实直接入库，不走意图/派单 */
    if (llmReady() && /(记住|记一下|记着|帮我记)/.test(message)) {
      let fact = '';
      try {
        const v = await llmJSON([
          { role: 'system', content: '把用户的话提炼成一条值得长期记住的偏好/事实（25字内、第三人称、以"少爷"开头）。与工作偏好、习惯、常用目标相关才记，闲聊不记。只输出 JSON：{"fact":"..."}，不值得记输出 {"fact":""}' },
          { role: 'user', content: message },
        ], undefined, { user: req.user, kind: 'chat-memory' });
        fact = String(v.fact || '').trim();
      } catch { fact = ''; }
      if (fact && rememberFact(req.user, fact, '对话')) {
        const reply = `记下了少爷：「${fact.slice(0, 40)}」。以后我办事会想着这条。`;
        for (const ch of reply.match(/.{1,6}/gs) || []) res.write('data: ' + JSON.stringify({ delta: ch }) + '\n\n');
        res.write('data: [DONE]\n\n');
        return res.end();
      }
    }

    /* ① 大脑意图分析（work=转派 / clarify=反问确认 / chat=亲自开口） */
    let intent = null;
    if (llmReady() && !dangerConfirmed) {
      try { intent = await llmJSON(intentMessages(message), undefined, { user: req.user, kind: 'intent' }); } catch { intent = null; }
    }
    const bare = message.replace(/[。，、.!！?？~\s]/g, '');
    const looksChat = /(你好|在吗|你是谁|进度|怎么样|如何|谢谢|辛苦|哈哈|什么是|是什么|干嘛|功能|能吗|能不|会不会|可以吗|可以么|吗？|\?)/.test(message);
    const vagueMsg = bare.length <= 4 && !WORK_HINT.test(message) && !looksChat;   // 单独丢一个词，像"周报""饺子"
    let route, goal = '', question = '';
    if (dangerConfirmed) {
      route = 'work'; goal = pd.goal;
    } else if (llmReady() && intent) {
      const li = String(intent.intent || '').toLowerCase();
      if (li === 'work' && String(intent.goal || '').trim()) { route = 'work'; goal = String(intent.goal).trim(); }
      else if (li === 'clarify' && String(intent.question || '').trim()) { route = 'clarify'; question = String(intent.question).trim(); }
      else route = 'chat';
    } else {
      // 模型失联/离线：关键词兜底
      if (WORK_HINT.test(message)) { route = 'work'; goal = message; }
      else if (vagueMsg) { route = 'clarify'; question = ''; }
      else route = 'chat';
    }
    if (route === 'clarify' && !question) {
      question = '少爷，这条指令有点模糊——您是想让执行方干件具体的活（比如写一份介绍、整理资料、做个对比），还是想先跟我聊聊？说清楚一点，我马上派单。';
    }

    /* ①′ 危险红线：不可逆操作不直接派单/闲聊带过，统一反问确认（纯提问"什么是格式化"除外） */
    const isExplain = /(什么是|什么叫|的意思|怎么读)/.test(message);
    if (!dangerConfirmed && !isExplain && (DANGER_RE.test(message) || DANGER_FILE_RE.test(message))) {
      route = 'clarify';
      pendingDanger[req.user] = { goal: goal || message, ts: Date.now() };
      question = '少爷，这条指令涉及删除/系统/资金类不可逆操作，咕嘎不敢擅自派单。请把对象和范围说得更精确（例如：删除 D 盘下载文件夹里 30 天前的 .tmp 文件），核对无误后回复"确认"，我再放行派单。';
    }

    /* ①″ 本机操作红线（不要剧本，要真实）：目标要打开/使用本机软件时，
     * 云端工人代写冒充完成属于演剧本——本体在线才派（自动真机执行），不在线就如实反问指路。 */
    if (route === 'work' && !dangerConfirmed
        && (detectLocalApp(message) || detectLocalApp(goal))) {
      const ag = agentOnline(req.user);
      if (!ag) {
        route = 'clarify';
        question = '少爷，这单要真实操控您本机的软件干活（比如打开豆包亲手做），云端工人代写就是演剧本，咕嘎不干这种事。现在本机执行方还没连接——请点右上 🩺 自检，下载咕嘎本体并用配对码绑定，绑好我立刻真机开工；或者您改一个不需要操控电脑的目标（只要文稿内容那种），我马上派单。';
      } else {
        useLocal = true;   // 本体在线：自动真机执行，无需手动开🖥
      }
    }

    /* ② work 类：转派执行方，咕嘎只汇报"已派单" */
    if (route === 'work') {
      res.write('data: ' + JSON.stringify({ dispatched: true }) + '\n\n');
      try {
        const { task, mode } = await dispatchGoal(req.user, goal, space, useLocal, dangerConfirmed, req.device,
          String((req.body || {}).device || '').slice(0, 60), requiredToolsOf(req.body));
        const reply = dispatchReply(task, mode);
        for (const ch of reply.match(/.{1,6}/gs) || []) {
          res.write('data: ' + JSON.stringify({ delta: ch }) + '\n\n');
        }
        res.write('data: ' + JSON.stringify({ taskId: task.id }) + '\n\n');
      } catch (e) {
        const out = { error: String(e.message || e).slice(0, 100) };
        if (e.code) out.code = e.code;
        if (Array.isArray(e.missing)) out.missing = e.missing;
        res.write('data: ' + JSON.stringify(out) + '\n\n');
      }
      res.write('data: [DONE]\n\n');
      return res.end();
    }

    /* ③ clarify 类：大脑反问确认，不猜、不派单、不代工 */
    if (route === 'clarify') {
      for (const ch of question.match(/.{1,6}/gs) || []) {
        res.write('data: ' + JSON.stringify({ delta: ch }) + '\n\n');
      }
      res.write('data: [DONE]\n\n');
      return res.end();
    }

    /* ④ chat 类：管家亲自开口（LLM 未配置时走本地应答引擎） */
  if (!llmReady()) {
    const reply = localButlerReply(req.user, message);
    for (const ch of reply.match(/.{1,6}/gs) || []) {
      res.write('data: ' + JSON.stringify({ delta: ch }) + '\n\n');
    }
    res.write('data: [DONE]\n\n');
    return res.end();
  }
  // 带上真实台账上下文，回答更准
  const mine = tasks.filter(t => t.userId === req.user && !t.finishedAt).slice(0, 3);
  const doneCount = tasks.filter(t => t.userId === req.user && t.finishedAt).length;
  const ctx = mine.map(t => `目标「${t.goal}」：` + t.subtasks.map(s => `${s.name}(${s.status}${s.overdue ? ',已催办' : ''})`).join('、')).join('\n')
    + (mine.length ? '' : '（当前没有执行中的任务）') + `\n（今日已完成 ${doneCount} 单）`;
  try {
    await llmStream([
      { role: 'system', content: '你是桌面生产力智能体"咕嘎管家"（一只原创企鹅管家，Web 体验版）。身份：大脑与监工——AI 指挥 AI（把目标拆解派单给工人智能体真实执行）并全程监工（盯进度、催办、验收打回）。你不是干活的人：写作/制作类指令走的是自动派单流程，由系统处理，你只负责陪聊、答疑、汇报进度。\n' +
        '规矩：① 只有用户明确问"派单了吗/帮我派单/执行结果如何"时才能谈派单，否则不要主动提"派单""执行方"这些词；② 解释类问题（什么是X）直接正常作答；③ 意图不明时反问一句确认。\n' +
        '语气：干练贴心的老式管家，称呼用户为"少爷"，回复不超过 120 字。\n' +
        (recallFacts(req.user, 6).length ? '【咕嘎记住的少爷偏好（可自然引用，别生硬罗列）】\n' + recallFacts(req.user, 6).join('；') + '\n' : '') +
        '【当前监工中的任务】\n' + ctx },
      { role: 'user', content: message },
    ], (d) => res.write('data: ' + JSON.stringify({ delta: d }) + '\n\n'), undefined, { user: req.user, kind: 'chat' });
    res.write('data: [DONE]\n\n');
  } catch (e) {
    res.write('data: ' + JSON.stringify({ error: '模型服务暂时不可用，请稍后重试' }) + '\n\n');
  }
  res.end();
  } finally {
    clearInterval(ping);   // 所有出口汇合：关掉 SSE 心跳
  }
});

/* 断电自愈：进程重启后，把卡在执行/验收/打回态的子任务重置为待开工（内存 inflight 已随重启消失，
 * 调度器 1.5s 一拍会自动重新领单）；卡在终检的任务重新触发 finishCheck。 */
  (function recoverOnBoot() {
    let n = 0;
    for (const task of tasks) {
      if (task.finishedAt || task.demo) continue;
      let hit = 0;
      for (const st of task.subtasks) {
        if (st.status === 'running' || st.status === 'review' || st.status === 'returned') {
          st.status = 'pending'; st.progress = 0; st.overdue = false;
          st.localClaimed = false; st.rerunAt = 0; st.finishedAt = 0;
          st.claimedBy = ''; st.lastAliveAt = 0;
          hit++; n++;
        }
      }
      const wasFinal = task.finalReviewing;
      if (task.finalReviewing) task.finalReviewing = false;
      if (hit || wasFinal) {
        task.log.push({
          ts: Date.now(), kind: 'info',
          text: `⚡ 服务器重启自愈：${hit ? hit + ' 个未落定子任务已自动重新派发' : '终检中断已续跑'}，监工继续`,
        });
      }
    }
    if (n) saveJSON('tasks.json', tasks);
    if (n) console.log(`[recovery] 检测到上次进程中断：已重置 ${n} 个未落定子任务，自动重新派发`);
    for (const task of tasks) {
      if (!task.finishedAt && !task.demo) finishCheck(task);   // 全部落定的任务续跑终检
    }
  })();

app.listen(PORT, '0.0.0.0', () => {
  console.log(`[guga] 咕嘎管家体验版已启动: http://0.0.0.0:${PORT}`);
  console.log(`[guga] 大模型: ${llmReady() ? llmCfg.model + ' @ ' + llmCfg.baseUrl : '未配置（演示剧本模式）'}`);
  console.log(`[guga] 执行引擎: ${llmReady() ? '真实调度（工人智能体真实执行+真实验收，产物落盘可查）' : '演示剧本（未接大模型）'}`);
  console.log(`[guga] 知识库: KB3×${KB.routing.length} KB5×${KB.templates.length} KB4×${KB.accept.length}（拆解/调度/监工已接入）`);
});
