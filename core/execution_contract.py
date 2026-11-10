"""Deterministic completion checks for tool side effects and verification receipts."""
import re

INPUT_ACTIONS={"click","double_click","drag","scroll","hotkey","type","fill","editor_select_tail","uia"}
VERIFY_ACTIONS={"observe","accessibility","uia_read"}
ACTION_WORDS=("打开","启动","关闭","读取","修改","写入","保存","运行","安装","下载",
              "删除","移动","复制","重命名","上传","提交","点击","输入","执行","修复",
              "测试","检查窗口","截屏","看屏幕","整理文件","创建文件","发送","发一段","发一句")
# Questions about how/why something works are not action requests even when they
# mention an action word ("下载速度慢是什么原因"). A real request keeps an
# explicit imperative marker, so "能不能帮我打开浏览器" still executes.
QUESTION_WORDS=("如何","怎么","为什么","解释一下","有什么区别","是什么","什么是","教我","步骤是",
                "什么","哪些","哪个","多少","多久","哪里","谁","何时","怎样","怎么样","是否",
                "是不是","有没有","吗","呢","？","?")
REQUEST_WORDS=("帮我","给我","替我","麻烦","请你","我要你","现在开始","执行一下","跑一下",
               "去把","去打开","去下载","去执行")
# Clauses that name a concrete side effect. Used only to tell a multi-step job
# from a one-shot action; the same words may also appear inside one clause.
COMPOSITE_ACTIONS=ACTION_WORDS+("发给","发到","发送到","发消息","发一段","发一句","上传到","导出","抽取",
                                "转写","渲染","投稿","下载到","解压","压缩","整理成","批量")
_SEQUENCE_SPLIT=re.compile(r'[，,。；;、]|然后|接着|之后|随后|最后|紧接着|并且|再(?![来说次])|并(?![且非])')


def execution_steps(prompt):
    """Count ordered action clauses; a short prompt can still be a real job."""
    text=str(prompt or '').strip()
    if not text:return 0
    count=0
    for clause in _SEQUENCE_SPLIT.split(text):
        clause=str(clause or '').strip()
        if clause and any(word in clause for word in COMPOSITE_ACTIONS):count+=1
    return count


def is_composite(prompt):
    """True when the request needs at least two dependent actions.

    The single-step fast path must not swallow these: they need planning,
    sequential execution and result-driven adjustment, not a 20-second budget.
    """
    return execution_steps(prompt)>=2


def _question_like(text):
    return any(word in text for word in QUESTION_WORDS)


def requires_execution(prompt):
    text=str(prompt or "").lower().strip()
    # 用户点名外部工具（“用豆包生成…”）就是执行请求：动作词表里没有“生成/写”，
    # 只看动作词会把这类指令误判成聊天，退化成咕嘎自己代写。
    try:
        from core import tool_mandate
        if tool_mandate.detect(prompt):return True
    except Exception:pass
    if not any(word in text for word in ACTION_WORDS):return False
    value=re.sub(r'^(?:小?咕嘎[，,\s]*)?(?:(?:请你?|麻烦你?|帮我|给我|替我|我要你|你能不能|你能|你可以|你可不可以|能不能|能否|可不可以|可以)[，,\s]*)*','',text)
    if re.match(r'^(?:解释|讲解|告诉我|教我).*(?:如何|怎么|为什么|是什么|什么意思)',value):return False
    imperative=re.match(r'^('+'|'.join(sorted(ACTION_WORDS,key=len,reverse=True))+r')[，,:：\s]*(.*)',value)
    if imperative:
        # A question inside a message/field is an action argument, not the
        # user's intent. Only inspect the leading instruction clause.
        clause=re.split(r'[，,。;；]|(?:发送|发给)',imperative.group(2),maxsplit=1)[0]
        knowledge=tuple(w for w in QUESTION_WORDS if w not in ('吗','呢','？','?'))
        if clause and not any(w in clause for w in knowledge):return True
    if _question_like(text) and not any(word in text for word in REQUEST_WORDS):return False
    return True


class ExecutionLedger:
    """Track only externally consequential work. Read-only failures stay recoverable."""
    def __init__(self,goal=''):
        self.expects_send=any(word in str(goal) for word in ('发送','发一段','发一句','发给','发条'))
        self.pending=[]
        self.failures={}
        self.completed=[]
        self.evidence_count=0
        self.input_sent=0        # 真正发出过键鼠输入动作的次数（不含只观察）

    @staticmethod
    def _ok(value):
        return bool(isinstance(value,dict) and value.get("ok") is True)

    def record(self,name,args,value):
        args=args if isinstance(args,dict) else {}
        value=value if isinstance(value,dict) else {}
        action=str(args.get("action",""))
        result=value.get("result") if isinstance(value.get("result"),dict) else {}
        ok=self._ok(value)
        if name not in ("task_plan","self_ask") and ok:
            self.evidence_count+=1
        if name=='applications' and action=='open':
            if ok and result.get('selection_required'):
                self.pending.append(dict(category='application_window',hwnd=None,
                    description='发现多个软件窗口，尚未选择并观察目标窗口'))
            return
        if name=='browser' and action not in ('open','close_tab'):
            page=value.get('page_id')
            if action in ('click','press','upload','scroll') and value.get('action_sent') is not False:
                self.pending.append(dict(category='browser_input',page_id=args.get('page_id'),
                    description='浏览器输入已尝试；需要重新snapshot读取页面并核对目标结果'))
            if action in ('snapshot','wait') and ok and value.get('snapshot_id'):
                self.pending=[p for p in self.pending if not (p.get('category')=='browser_input' and p.get('page_id')==page)]
                self.failures.pop('browser_session',None)
            elif not ok:self.failures['browser_session']='专用浏览器步骤未获得成功回执；先观察核对已有结果'
            elif action in ('fill_form','download') and value.get('verified'):
                self.completed.append(dict(category='browser_verified',action=action))
                self.failures.pop('browser_session',None)
            return
        if name in ("wechat_send_self","wechat","web_search","browser"):
            if name=='wechat' and action=='open' and self.expects_send and ok:
                self.pending=[p for p in self.pending if p.get('category')!='wechat_message']
                self.pending.append(dict(category='wechat_message',description='已定位微信会话，但尚未取得发送并回读消息的回执'))
            if name=='wechat' and action=='send' and ok and value.get('verified_message_visible'):
                self.pending=[p for p in self.pending if p.get('category')!='wechat_message']
            if ok:self.failures.pop(name,None)
            else:self.failures[name]=name+" 未获得成功验证回执，不能声称已完成"
            return
        if name=="computer":
            if action=='focus' and ok:
                for item in self.pending:
                    if item.get('category')=='application_window':item['hwnd']=args.get('hwnd')
            if action in INPUT_ACTIONS and ok:
                self.input_sent+=1
                verification=result.get('verification') or {}
                if (action=='uia' and result.get('verified') is True and verification.get('matched') is True
                        and verification.get('kind') in ('value_equals','keyboard_focus')):
                    self.completed.append(dict(category='computer_verified',action=action,hwnd=args.get('hwnd')))
                    self.failures.pop('computer',None)
                    return
                item=dict(category="computer_input",action=action,hwnd=args.get("hwnd"),
                          description=f"computer.{action} 已发送，尚未复查")
                self.pending.append(item)
                self.failures.pop("computer",None)
            elif action in VERIFY_ACTIONS and ok:
                observed=args.get('hwnd') or result.get('hwnd')
                self.pending=[x for x in self.pending if not (x.get('category')=='computer_input' and
                    (not x.get('hwnd') or (observed and x.get('hwnd')==observed)))]
                if observed:
                    self.pending=[x for x in self.pending if not (x.get('category')=='application_window' and x.get('hwnd')==observed)]
                self.failures.pop("computer",None)
                self.completed.append(dict(category="computer_verified",action=action))
            elif action in INPUT_ACTIONS and not ok:
                self.failures["computer"]=f"computer.{action} 未成功"
            return
        if name=="local_computer":
            if action in ("write","run"):
                category="local_write" if action=="write" else "local_run"
                if ok and (action=="write" and result.get("written") or
                           action=="run" and result.get("exit_code")==0 and not result.get("stopped")):
                    self.failures.pop(category,None)
                    self.completed.append(dict(category=category,action=action,path=args.get("path")))
                else:
                    self.failures[category]=f"local_computer.{action} 没有成功回执"
            return
        if name=="ecosystem":
            if action=="call":
                self.failures.pop("ecosystem",None) if ok else self.failures.update(ecosystem="外部软件工具调用失败")
            return
        if name=="battleground":
            if action=="netcut" and not ok:
                self.failures["battleground_netcut"]="拔线请求失败或未获确认"
            elif action=="netcut" and ok:
                self.failures.pop("battleground_netcut",None)
                self.completed.append(dict(category="battleground_netcut",action=action))

    def blockers(self):
        reasons=[item["description"] for item in self.pending]
        reasons.extend(self.failures.values())
        return reasons

    def summary(self):
        return dict(pending=list(self.pending),failures=dict(self.failures),evidence_count=self.evidence_count,
                    completed=list(self.completed[-30:]))
