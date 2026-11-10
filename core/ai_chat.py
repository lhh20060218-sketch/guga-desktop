# -*- coding: utf-8 -*-
"""咕嘎企鹅 AI 大脑 — DeepSeek API 对话引擎（线程化，不阻塞 UI）

- 人设：娇憨调皮小企鹅"咕嘎"，称呼用户"饲养员/两脚兽"，爱调侃（善意搞笑）
- 领域：炉石传说酒馆战棋大师，配合多源 RAG 知识库（core.bg_knowledge）
- 回复格式：表情|动作|台词
  表情∈normal/happy/sleepy/surprised/sad/playful
  动作∈none/bounce/shake/point(指点江山)/peek(偷偷看我)/tsundere(傲娇摇头)
- 配置：ai_config.json（api_key/base_url/model/...）
- 失败兜底：emit failed，调用方回落到台词库
"""
import json
import os
import threading
import time
import uuid
from urllib.parse import urlsplit

import requests
from PyQt5.QtCore import QObject, pyqtSignal

from core.bg_knowledge import build_context
from core import guga_paths
from core.agent_task import ledger_note, ledger_snapshot
from core.reply_guard import ledger_disclosure, sanitize


EXPRESSIONS = ("normal", "happy", "sleepy", "surprised", "sad", "playful")
ACTIONS = ("none", "bounce", "shake", "point", "peek", "tsundere")

# 服务商识别只用于界面展示，绝不参与请求地址计算：没填 base_url 就不发请求。
_PROVIDER_HOSTS = {
    'api.deepseek.com': 'DeepSeek 官方',
    'open.bigmodel.cn': '智谱 GLM',
    'dashscope.aliyuncs.com': '通义千问',
    'maas.qianwenaiapi.com': '千问 MaaS 网关',
    'opencode.ai': 'OpenCode',
}


def provider_label(cfg=None) -> str:
    """当前服务商显示名；没配地址时明确写“未选择服务商”。"""
    cfg = cfg if isinstance(cfg, dict) else guga_paths.read_config()
    base = str(cfg.get('base_url') or '').strip()
    if not base:
        return '未选择服务商'
    host = urlsplit(base).hostname or ''
    custom = str(cfg.get('provider') or '').strip()
    return custom or _PROVIDER_HOSTS.get(host, host or base)


def endpoint_label(cfg=None) -> str:
    cfg = cfg if isinstance(cfg, dict) else guga_paths.read_config()
    return str(cfg.get('base_url') or '').strip() or '未填写接口地址'


def model_config_error(cfg=None) -> str:
    """返回可直接展示给用户的中文原因；空串表示三项都齐、可以发请求。"""
    cfg = cfg if isinstance(cfg, dict) else guga_paths.read_config()
    key = str(cfg.get('api_key') or '').strip()
    base = str(cfg.get('base_url') or '').strip()
    model = str(cfg.get('model') or '').strip()
    if not key:
        return ('未配置模型：没有 API Key。对话、完整对话、截图分析不可用；'
                '请点「模型设置」自己填写。接入 MCP 只负责发现软件路径，不等于模型可用。')
    if not base.startswith('http'):
        return ('未选择服务商：已填 API Key，但没有接口地址（base_url）。'
                '咕嘎不会把 Key 发到任何默认服务商，请到「模型设置」选择平台或填写地址。')
    if not model:
        return '未选择模型名：请到「模型设置」填写模型 id（例如 deepseek-chat）。'
    return ''


def require_model_config(cfg=None) -> dict:
    """模型请求前的统一校验；不通过时抛 ValueError，文案可直接显示。"""
    problem = model_config_error(cfg)
    if problem:
        raise ValueError(problem)
    return cfg if isinstance(cfg, dict) else guga_paths.read_config()

SYSTEM_PROMPT = """你是"咕嘎"——一只住在冰面上的娇憨调皮小企鹅桌宠。

【性格】
- 娇憨：圆滚滚、呆萌可爱，反应天真，偶尔犯迷糊说傻话。
- 调皮：爱捉弄饲养员，嘴贫爱调侃，但都是善意的搞笑。
- 傲娇：明明关心却嘴硬，比如"本鹅才不是担心你呢"。
- 称呼用户为"饲养员"或"两脚兽"，自称"本鹅"，经常调侃他：手残、运气差、又菜又爱玩、熬夜打游戏等，要可爱不要刻薄。
- 说话风格：短句，混入"咕嘎～""咕嘎嘎～""咕噜咕噜"等企鹅语，每句不超过60字，口语化，不用表情符号。

【领域】你是炉石传说酒馆战棋顶级军师，精通流派、英雄、饰品、站位与最新赛季机制（第14赛季黑暗之赐、发动等）。
当饲养员描述对局、发来棋盘截图分析或问战棋问题时，认真分析并给出实用建议：该买什么、刷不刷、升不升酒馆、转不转流派、怎么站位。
可以边调侃边给干货，例如先吐槽他一句再认真分析。
如果问题与酒馆战棋无关，就作为普通企鹅闲聊，但也可以把话题往酒馆战棋上拐。

【回复格式】严格以"表情|动作|台词"开头：
- 表情：normal/happy/sleepy/surprised/sad/playful 之一
- 动作：none/bounce/shake/point/peek/tsundere 之一
  point=指点江山（给战棋建议时用，配上指点手势）
  peek=偷偷看我（害羞/偷看时用）
  tsundere=傲娇摇头（嘴硬傲娇时用）
  bounce=开心蹦，shake=受惊抖
- 台词：你说的内容
例如：playful|point|咕嘎～听本鹅军师的，这波先别升酒馆！
例如：happy|bounce|咕嘎嘎～本鹅今天心情好，允许你摸一下！"""

# 对局分析专用提示词（覆盖默认人设的任务部分）
ANALYSIS_OVERRIDE = """你是"咕嘎"——一只住在冰面上的娇憨调皮小企鹅，同时是炉石传说酒馆战棋的顶级军师。

【性格】娇憨调皮傲娇，称呼用户为"饲养员/两脚兽"，自称"本鹅"，先调侃一句（嘲讽他手残/运气差/又菜又爱玩，但要可爱不刻薄），然后认真给干货。短句、混入"咕嘎～"等企鹅语，整段不超过120字，不用表情符号。

【任务】饲养员会发来棋盘截图分析或文字描述（英雄/回合/血量/铸币/酒馆等级/流派/场上随从/饰品/对手），你要：
1. 判断当前局面的核心矛盾（经济崩了？没核心？血线危险？流被卡？）
2. 给出当下最优先的1-3个动作：买什么、刷不刷、升不升酒馆、转不转流派、怎么站位
3. 提示下一步关键节奏（饰品回合、三连点、血线、决赛站位）
4. 结合最新赛季机制（第14赛季黑暗之赐、发动、上锁宝箱、鱼饵、烈毒改版；第13赛季饰品在第6/9回合4选1）
【铁律】严格依据棋盘扫描/描述里明确出现的信息分析；信息缺失时明确说出缺什么（如"看不到你的血量/铸币/酒馆等级"），绝不编造具体数值、随从或流派；若画面根本不是酒馆战棋对局，直接告诉饲养员"这不是战棋界面，本鹅看不了"。

【回复格式】严格以"表情|动作|台词"开头：表情∈normal/happy/sleepy/surprised/sad/playful，动作∈none/bounce/shake/point/peek/tsundere。
例如：playful|point|咕嘎～饲养员这局面还敢冲6级？本鹅军师的建议是……"""

# 实时战斗阶段胜率解读专用提示词（轨道③：解读"为什么是这个胜率"，不许只念数字）
WINRATE_OVERRIDE = """你是"咕嘎"——一只住在冰面上的娇憨调皮小企鹅，同时是炉石传说酒馆战棋的顶级军师。

【性格】娇憨调皮傲娇，称呼用户为"饲养员/两脚兽"，自称"本鹅"，先调侃一句（嘲讽他手残/运气差/又菜又爱玩，但要可爱不刻薄），然后认真给干货。短句、混入"咕嘎～"等企鹅语，整段不超过140字，不用表情符号。

【任务】饲养员正处于战斗阶段，要你解读实时胜率。你会收到：棋盘数据（己方/对手随从）、蒙特卡洛模拟的胜率/平局/败率、模拟解读数据（我方谁最先倒、对面最大威胁、我方输出担当、胜场胜负手）、对手阵容分析（流派/核心/威胁/弱点）。
你要：
1. 解读"为什么是这个胜率"：胜负手是什么（谁在决定这局输赢）、胜率背后的机制原因（比如对面烈毒克制你大身材、你亡语链被AOE克制）
2. 点出对面阵容最大威胁与弱点，给出针对性打法：站位怎么调（先杀谁、谁去挡毒、要不要分散防AOE）、这回合买什么/留什么能扭转战局
3. 结合最新赛季机制（第14赛季黑暗之赐、发动、烈毒改版）
【铁律】不要复述胜率数字本身（饲养员已经看到了），要讲数字背后的道理；只依据给你的数据，信息缺失时明确说出缺什么，绝不编造具体数值、随从或流派。

【回复格式】严格以"表情|动作|台词"开头：表情∈normal/happy/sleepy/surprised/sad/playful，动作∈none/bounce/shake/point/peek/tsundere。
例如：playful|point|咕嘎～对面这亡灵流靠瑞文翻盘，你56%胜率全押在集火他身上！站位把他的瑞文架到最前面打，再留个圣盾挡毒……"""

# 招募阶段阵容展望专用提示词（轨道⑤：点击讨论 → 未来阵容展望）
OUTLOOK_OVERRIDE = """你是"咕嘎"——一只住在冰面上的娇憨调皮小企鹅，同时是炉石传说酒馆战棋的顶级军师。

【性格】娇憨调皮傲娇，称呼用户为"饲养员/两脚兽"，自称"本鹅"，先调侃一句（嘲讽他手残/运气差/又菜又爱玩，但要可爱不刻薄），然后认真给干货。短句、混入"咕嘎～"等企鹅语，整段不超过140字，不用表情符号。

【任务】饲养员正在招募阶段，点了你，要听对未来阵容的展望。你会收到：当前局面（酒馆等级/铸币/血量/回合/己方随从，来自游戏日志的精确数据）和规则引擎的展望结果（当前阵容方向、置信度、依据、还缺的核心组件、成型阵容模板、下一步建议）。
你要：
1. 判断当前阵容方向对不对（确认方向，或指出该早点转型的信号）
2. 给出接下来的动作顺序与预算：优先买什么/刷什么、该不该升酒馆、铸币怎么花
3. 预估成型期与成型强度（参考规则引擎给的成型模板与成型期），何时考虑转型/保命
4. 结合最新赛季机制（第14赛季黑暗之赐、发动、饰品回合）
【铁律】只依据给你的数据与知识库信息，不编造具体随从或数值；信息缺失（如看不到血量）明确说出缺什么。

【回复格式】严格以"表情|动作|台词"开头：表情∈normal/happy/sleepy/surprised/sad/playful，动作∈none/bounce/shake/point/peek/tsundere。
例如：happy|point|咕嘎～你这野兽雏形对味了！还差瑞文和小黄，这回合铸币够就先刷鱼饵，再攒钱升4级，第8回合就能成型……"""


class AIChatWorker(threading.Thread):
    """单次 DS API 请求（后台线程）"""

    def __init__(self, cfg, system_prompt, history, user_msg, rag_context, result_cb,
                 session_id=None, rag_label="知识库参考"):
        super().__init__(daemon=True)
        self._cfg = cfg
        self._system_prompt = system_prompt
        self._history = history
        self._user_msg = user_msg
        self._rag_context = rag_context
        self._result_cb = result_cb
        self._session_id = session_id or str(uuid.uuid4())
        self._rag_label = rag_label

    def run(self):
        # 思考型模型可能把配额全花在 reasoning 上导致 content 为空 → 空回复自动重试
        for attempt in range(2):
            try:
                messages = [{"role": "system", "content": self._system_prompt}]
                if self._rag_context:
                    messages.append({
                        "role": "system",
                        "content": "【%s（来源于知识库，用于辅助回答，直接用它回答即可）】\n" % self._rag_label
                                   + self._rag_context,
                    })
                messages.extend(self._history)
                messages.append({"role": "user", "content": self._user_msg})

                problem = model_config_error(self._cfg)
                if problem:
                    # 没有服务商/模型就停在这里，绝不回退到任何内置端点。
                    self._result_cb(ok=False, error=problem)
                    return
                from core import model_endpoint
                base_url = model_endpoint.base_of(self._cfg.get('base_url')) or \
                    str(self._cfg.get('base_url')).strip().rstrip('/')
                headers = {
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {self._cfg.get('api_key', '')}",
                }
                endpoint = urlsplit(base_url)
                if endpoint.hostname == 'opencode.ai' and endpoint.path.startswith(
                        ('/inference/go/', '/zen/go/')):
                    # Go needs a client identity and a stable ID across conversation turns.
                    headers['User-Agent'] = 'GugaDesktopPet/1.0'
                    headers['x-opencode-session'] = self._session_id
                resp = model_endpoint.post(
                    base_url + "/chat/completions",
                    headers=headers,
                    json={
                        "model": self._cfg.get("model"),
                        "messages": messages,
                        "temperature": self._cfg.get("temperature", 0.85),
                        "max_tokens": self._cfg.get("max_tokens", 800),
                        "thinking": {"type": "disabled"},   # 关思考：桌宠回复要快
                        "stream": False,
                    },
                    timeout=self._cfg.get("request_timeout", 60),
                )
                try:
                    data = resp.json()
                except Exception:
                    data = {'_raw': (resp.text or '')[:200]}
                if resp.status_code != 200:
                    err = (data.get("error") or {}).get("message") if isinstance(data, dict) else ''
                    err = err or data.get('_raw') or str(resp.status_code)
                    info = model_endpoint.http_failure(resp.status_code, base_url,
                                                      model=self._cfg.get('model'), detail=err)
                    text = info.get('title') or ('API %s' % resp.status_code)
                    if info.get('next_step'):
                        text += '；' + info['next_step']
                    if info.get('examples'):
                        text += '。已验证可用：' + '；'.join(info['examples'])
                    self._result_cb(ok=False, error=text)
                    return
                text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
                if text:
                    self._result_cb(ok=True, text=text)
                    return
                if attempt == 0:
                    time.sleep(1.5)
                    continue
                self._result_cb(ok=False, error="API 返回空回复（可能思考过长）")
                return
            except requests.exceptions.Timeout:
                self._result_cb(ok=False, error="请求超时")
                return
            except requests.exceptions.ConnectionError:
                self._result_cb(ok=False, error="网络连接失败")
                return
            except Exception as e:
                self._result_cb(ok=False, error=str(e))
                return


class AIChatEngine(QObject):
    """AI 对话引擎门面（主线程使用，内部自动串行化请求）"""

    reply_ready = pyqtSignal(str, str, str)   # text, expression, action
    failed = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._cfg = self._load_config()
        self._history = []
        self._session_id = str(uuid.uuid4())
        self._worker = None
        self._pending_msg = None
        self._last_user_msg = ""
        self._rag_provider = None      # 可插拔检索器: fn(query) -> context str
        self._rag_label = "知识库参考"
        self._persona_fn = None        # 人设注入: fn() -> str(空串=不注入)
        self._ledger_snapshot = None   # 本轮回复前读到的任务台账快照

    @staticmethod
    def _load_config():
        return guga_paths.read_config()

    @property
    def enabled(self) -> bool:
        return bool(self._cfg.get('api_key'))

    def config_problem(self) -> str:
        """界面用：当前缺什么（空串=可用）。"""
        return model_config_error(self._cfg)

    def provider(self) -> str:
        return provider_label(self._cfg)

    def endpoint(self) -> str:
        return endpoint_label(self._cfg)

    def is_busy(self) -> bool:
        """是否正在请求中（自动观战用它避免打断正在进行的对话/分析）"""
        return bool(self._worker and self._worker.is_alive())

    def reset_history(self):
        self._history.clear()
        self._session_id = str(uuid.uuid4())

    def set_rag_provider(self, fn, label=None):
        """注册检索增强提供器: fn(query:str) -> context:str(空串=本次不注入).

        未注册时保持旧行为(走 core.bg_knowledge 战棋知识库).
        label: 注入 system 消息时的知识参考名称(如 "学者知识库").
        """
        self._rag_provider = fn
        if label:
            self._rag_label = str(label)

    def set_persona_provider(self, fn):
        """注册人设注入: fn() -> 前缀文本(空串=用默认人设).

        前缀会拼在默认 SYSTEM_PROMPT 之前, 回复格式(表情|动作|台词)不受影响.
        """
        self._persona_fn = fn

    def ask(self, user_msg: str, rag_query: str = None, system_override: str = None):
        problem = self.config_problem()
        if problem:
            self.failed.emit(problem)
            return
        rag_context = ""
        if rag_query or user_msg:
            q = rag_query or user_msg
            if self._rag_provider is not None:
                try:
                    rag_context = self._rag_provider(q) or ""
                except Exception:
                    rag_context = ""          # 检索失败不阻塞对话
            else:
                rag_context = build_context(q)
        if self._worker and self._worker.is_alive():
            self._pending_msg = (user_msg, rag_context, system_override)
            return
        self._start(user_msg, rag_context, system_override)

    def _start(self, user_msg, rag_context, system_override):
        if system_override is not None:
            prompt = system_override
        else:
            # 管家人设注入: persona_fn 返回空串则退回默认 SYSTEM_PROMPT
            prefix = ''
            if self._persona_fn is not None:
                try:
                    prefix = self._persona_fn() or ''
                except Exception:
                    prefix = ''
            prompt = (prefix + '\n' + SYSTEM_PROMPT) if prefix else SYSTEM_PROMPT
        # 语音/持续对话需要时间感知（远端语音稳定性线引入）
        from core.companion_dialogue import current_time_instructions
        prompt += current_time_instructions()
        # 第五项：每次回复前强制读当前任务台账并注入；读不到就写明读不到。
        try:
            snapshot = ledger_snapshot()
        except Exception as exc:
            snapshot = dict(ok=False, reason='%s: %s' % (type(exc).__name__, str(exc)[:120]))
        self._ledger_snapshot = snapshot
        prompt += '\n\n' + ledger_note(snapshot)
        history = self._history[-self._cfg.get('max_history', 8) * 2:]
        self._last_user_msg = user_msg
        self._worker = AIChatWorker(self._cfg, prompt, history, user_msg, rag_context,
                                   self._on_result, self._session_id,
                                   rag_label=self._rag_label)
        self._worker.start()

    def _on_result(self, ok: bool, text: str = "", error: str = ""):
        if self._pending_msg:
            user_msg, rag_context, system_override = self._pending_msg
            self._pending_msg = None
            self._start(user_msg, rag_context, system_override)
            return
        if ok:
            expr, action, content = parse_reply(text)
            snapshot = self._ledger_snapshot or {}
            has_evidence = bool(snapshot.get('ok') and (
                str(snapshot.get('status') or '') in ('completed', 'done', 'succeeded')
                or int(snapshot.get('evidence_count') or 0) > 0))
            # 第六项：没有执行回执时不许说“已转交/正在生成/请手动点”；本轮能执行时
            # 不许说“没有权限/纯问答模式”。
            content, _hits = sanitize(content, executable=True, has_evidence=has_evidence)
            # 第五项：台账读不到而用户在问进度 → 回复必须先如实说明读不到。
            disclosure = ledger_disclosure(snapshot, self._last_user_msg, executable=True)
            if disclosure:
                content = disclosure + '\n' + content
            self._history.append({"role": "user", "content": self._last_user_msg})
            self._history.append({"role": "assistant", "content": content})
            self.reply_ready.emit(content, expr, action)
        else:
            # 第六项：失败消息同样遵守诚实性规则，不许出现“已转交/正在生成/请手动点”。
            honest_error, _hits = sanitize(error or "未知错误", executable=True,
                                           has_evidence=False)
            self.failed.emit(honest_error)


def parse_reply(text: str):
    """解析 '表情|动作|台词' 或 '表情|台词' → (表情, 动作, 台词)"""
    from core.embodiment import spoken_reply
    clean_expr,clean_action,clean_text=spoken_reply(text)
    if clean_action!='none' or clean_text!=text.strip():
        return clean_expr,clean_action,clean_text or '咕嘎～'
    text = text.strip()
    parts = [p.strip() for p in text.split("|", 2)]
    expr, action, content = "normal", "none", text
    if len(parts) >= 2:
        if parts[0] in EXPRESSIONS:
            expr = parts[0]
            if len(parts) >= 3 and parts[1] in ACTIONS:
                action = parts[1]
                content = parts[2]
            else:
                content = parts[1]
        else:
            for e in EXPRESSIONS:
                if e in parts[0]:
                    expr = e
                    break
            content = text
    if not content.strip():
        content = "咕嘎～"
    return expr, action, content.strip()
