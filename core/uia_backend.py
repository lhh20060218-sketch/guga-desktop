"""Persistent in-process Windows UI Automation adapter with stable snapshot references."""
import hashlib
from collections import deque
import threading
import time


class UIAUnavailable(RuntimeError):
    pass


class UIABackend:
    def __init__(self, ttl=30):
        self.ttl=ttl
        self.lock=threading.RLock()
        self.loaded=False
        self.elements={}
        self.revisions={}
        self._load()

    def _load(self):
        try:
            import clr
            from System import IntPtr
            bases=(r'C:/Windows/Microsoft.NET/Framework64/v4.0.30319/WPF',
                   r'C:/Windows/Microsoft.NET/Framework/v4.0.30319/WPF')
            import os
            for base in bases:
                if not os.path.isfile(base+'/UIAutomationClient.dll'):continue
                clr.AddReference(base+'/UIAutomationClient.dll')
                clr.AddReference(base+'/UIAutomationTypes.dll')
                break
            from System.Windows.Automation import (AutomationElement,TreeScope,Condition,TreeWalker,
                InvokePattern,SelectionItemPattern,ValuePattern,TogglePattern,ExpandCollapsePattern,ScrollPattern,
                CacheRequest,Automation,ControlType,PropertyCondition,AndCondition)
            self.IntPtr=IntPtr;self.AutomationElement=AutomationElement;self.TreeScope=TreeScope;self.Condition=Condition
            self.Patterns=dict(invoke=InvokePattern,select=SelectionItemPattern,set_value=ValuePattern,
                               toggle=TogglePattern,expand=ExpandCollapsePattern,collapse=ExpandCollapsePattern,
                               scroll=ScrollPattern)
            self.walker=TreeWalker.ControlViewWalker
            self.ControlType=ControlType;self.PropertyCondition=PropertyCondition;self.AndCondition=AndCondition
            self.cache=CacheRequest();self.cache.TreeScope=TreeScope.Element
            self.cache.TreeFilter=Automation.ControlViewCondition
            for prop in ('Name','AutomationId','ControlType','ClassName','IsEnabled','IsOffscreen',
                         'BoundingRectangle','IsPassword','RuntimeId','HasKeyboardFocus'):
                self.cache.Add(getattr(AutomationElement,prop+'Property'))
            self.availability={}
            pattern_names=dict(invoke='Invoke',select='SelectionItem',set_value='Value',toggle='Toggle',expand='ExpandCollapse',collapse='ExpandCollapse',scroll='Scroll')
            for name,kind in self.Patterns.items():
                prop=getattr(AutomationElement,'Is'+pattern_names[name]+'PatternAvailableProperty')
                self.cache.Add(prop);self.availability[name]=prop
            self.cache.Add(ValuePattern.Pattern);self.cache.Add(ValuePattern.ValueProperty)
            self.loaded=True
        except Exception as exc:
            raise UIAUnavailable('进程内 UIAutomation 不可用: '+type(exc).__name__) from None

    def _root(self,hwnd):
        return self.AutomationElement.FromHandle(self.IntPtr(int(hwnd)))

    @staticmethod
    def _rect(element,cached=False):
        try:r=(element.Cached if cached else element.Current).BoundingRectangle
        except Exception:return None
        return dict(left=float(r.Left),top=float(r.Top),right=float(r.Right),bottom=float(r.Bottom))

    def _entry(self,element,hwnd,index=0,cached=False):
        try:
            c=element.Cached if cached else element.Current
            runtime=list(element.GetCachedPropertyValue(self.AutomationElement.RuntimeIdProperty)) if cached else list(element.GetRuntimeId())
            identity='|'.join(str(x) for x in runtime)
            ref=hashlib.sha256((str(hwnd)+'|'+identity).encode()).hexdigest()[:20]
            item=dict(ref=ref,name=str(c.Name or '')[:200],id=str(c.AutomationId or '')[:200],
                      type=str(c.ControlType.ProgrammaticName or '').replace('ControlType.',''),
                      class_name=str(c.ClassName or '')[:100],enabled=bool(c.IsEnabled),
                      offscreen=bool(c.IsOffscreen),password=bool(c.IsPassword),focused=bool(c.HasKeyboardFocus),rect=self._rect(element,cached),
                      patterns=[str(kind.__name__) for name,kind in self.Patterns.items()
                        if bool(element.GetCachedPropertyValue(self.availability[name]) if cached else element.GetCurrentPropertyValue(self.availability[name]))])
            if not c.IsPassword:
                try:
                    pattern=element.GetCachedPattern(self.Patterns['set_value'].Pattern) if cached else element.GetCurrentPattern(self.Patterns['set_value'].Pattern)
                    item['value']=str((pattern.Cached if cached else pattern.Current).Value or '')[:1000]
                except Exception:pass
            return item,element
        except Exception:
            return None,None

    def snapshot(self,hwnd,limit=240,time_budget=2.5):
        hwnd=int(hwnd);limit=max(1,min(int(limit),500))
        with self.lock:
            root=self._root(hwnd).GetUpdatedCache(self.cache)
            now=time.monotonic();items=[]
            self.elements={k:v for k,v in self.elements.items() if now-v[1]<self.ttl}
            queue=deque([root]);visited=0
            while queue and len(items)<limit and time.monotonic()-now<time_budget:
                element=queue.popleft();visited+=1
                item,_=self._entry(element,hwnd,visited,cached=True)
                if item:
                    items.append(item);self.elements[item['ref']]=(element,now,hwnd)
                try:child=self.walker.GetFirstChild(element,self.cache)
                except Exception:child=None
                count=0
                while child is not None and count<500 and time.monotonic()-now<time_budget:
                    queue.append(child);count+=1
                    try:child=self.walker.GetNextSibling(child,self.cache)
                    except Exception:break
            revision=hashlib.sha256((str(hwnd)+str(now)+str(len(items))).encode()).hexdigest()[:16]
            self.revisions[hwnd]=revision
            return dict(hwnd=hwnd,revision=revision,elements=items,truncated=bool(queue),
                        elapsed_seconds=round(time.monotonic()-now,3),
                        hint='后续用 ref 调用 uia，避免重复遍历；状态变化后重新 snapshot')

    def _find(self,hwnd,name='',automation_id='',control_type='',root=None,include_offscreen=False):
        conditions=[]
        for prop,value in ((self.AutomationElement.NameProperty,name),(self.AutomationElement.AutomationIdProperty,automation_id)):
            if value:conditions.append(self.PropertyCondition(prop,str(value)))
        if control_type:
            kind=getattr(self.ControlType,str(control_type).replace('ControlType.',''),None)
            if kind is None:raise ValueError('未知UIA控件类型')
            conditions.append(self.PropertyCondition(self.AutomationElement.ControlTypeProperty,kind))
        if not conditions:raise ValueError('需要精确UIA目标，不能选择整棵树第一个控件')
        condition=conditions[0]
        for other in conditions[1:]:condition=self.AndCondition(condition,other)
        activation=self.cache.Activate()
        try:found=(root if root is not None else self._root(hwnd)).FindAll(self.TreeScope.Descendants,condition)
        finally:activation.Dispose()
        matches=[]
        for element in found:
            item,_=self._entry(element,hwnd,cached=True)
            if item:
                self.elements[item['ref']]=(element,time.monotonic(),hwnd)
                if include_offscreen or not item['offscreen']:matches.append((element,item))
        if not control_type:
            actionable=[x for x in matches if x[1]['type'] not in ('Text','Pane','Group','Document','Window')]
            if actionable:matches=actionable
        return matches

    def _resolve(self,hwnd,ref=None,name='',automation_id='',control_type='',include_offscreen=False):
        hwnd=int(hwnd)
        with self.lock:
            cached=self.elements.get(str(ref or ''))
            if cached and cached[2]==hwnd and time.monotonic()-cached[1]<self.ttl:
                element=cached[0].GetUpdatedCache(self.cache)
                item,_=self._entry(element,hwnd,cached=True)
                if item and item['ref']==ref and (include_offscreen or not item['offscreen']):
                    if name and item['name']!=name:raise RuntimeError('控件名称已变化，未发送操作')
                    if automation_id and item['id']!=automation_id:raise RuntimeError('控件ID已变化，未发送操作')
                    if control_type and item['type'].lower()!=control_type.lower():raise RuntimeError('控件类型已变化，未发送操作')
                    return element,item
            if ref:raise RuntimeError('UIA引用已过期或失效，请重新读取目标，未发送操作')
            matches=self._find(hwnd,name,automation_id,control_type,include_offscreen=include_offscreen)
            if len(matches)>1:raise RuntimeError('UIA目标不唯一，请指定更精确的控件，未发送操作')
            if matches:return matches[0]
            raise RuntimeError('UIA目标不存在或不可见，未发送操作')

    def page_input(self,hwnd,search=False):
        with self.lock:
            documents=self._find(int(hwnd),control_type='Document')
            if not documents:raise RuntimeError('网页未提供可访问的文档，未发送操作')
            def area(pair):
                r=pair[1].get('rect') or {}
                return max(0,r.get('right',0)-r.get('left',0))*max(0,r.get('bottom',0)-r.get('top',0))
            document=max(documents,key=area)[0]
            inputs=[pair for pair in self._find(int(hwnd),control_type='Edit',root=document)
                if pair[1].get('enabled') and not pair[1].get('password')]
            if search:
                named=[pair for pair in inputs if
                    any(word in pair[1].get('name','').casefold() for word in ('搜索','search'))]
                if named:inputs=named
            if len(inputs)!=1:raise RuntimeError('页面输入框不唯一或不存在，请说具体名称，未发送操作')
            return dict(hwnd=int(hwnd),element=inputs[0][1])

    def read(self,hwnd,**selector):
        with self.lock:
            _,item=self._resolve(hwnd,**selector)
            return dict(hwnd=int(hwnd),element=item,verified=True)

    def perceive(self,hwnd,limit=160):
        """Read visible controls in one native cache batch; never take an action."""
        hwnd=int(hwnd);limit=max(1,min(int(limit),240));started=time.monotonic()
        with self.lock:
            from System.Windows.Automation import CacheRequest
            cache=CacheRequest();cache.TreeScope=self.TreeScope.Element
            for prop in ('Name','ControlType','IsEnabled','IsOffscreen','IsPassword','BoundingRectangle'):
                cache.Add(getattr(self.AutomationElement,prop+'Property'))
            cache.Add(self.Patterns['set_value'].Pattern);cache.Add(self.Patterns['set_value'].ValueProperty)
            condition=self.AndCondition(self.PropertyCondition(self.AutomationElement.IsOffscreenProperty,False),
                self.PropertyCondition(self.AutomationElement.IsPasswordProperty,False))
            activation=cache.Activate()
            try:found=self._root(hwnd).FindAll(self.TreeScope.Descendants,condition)
            finally:activation.Dispose()
            items=[]
            for element in found:
                c=element.Cached;kind=str(c.ControlType.ProgrammaticName).replace('ControlType.','')
                if kind not in ('Text','Edit','ComboBox','Button','Hyperlink','MenuItem','TabItem','CheckBox','RadioButton','Document','ListItem'):continue
                item=dict(type=kind,name=str(c.Name or '')[:180],enabled=bool(c.IsEnabled),rect=self._rect(element,True))
                if kind in ('Edit','ComboBox'):
                    try:item['value']=str(element.GetCachedPattern(self.Patterns['set_value'].Pattern).Cached.Value or '')[:180]
                    except Exception:pass
                if item['name'] or kind in ('Edit','ComboBox'):items.append(item)
                if len(items)>=limit:break
            return dict(hwnd=hwnd,elements=items,truncated=len(items)>=limit,source='windows_uia',
                elapsed_ms=round((time.monotonic()-started)*1000,2),visual_content=False)

    def focused(self,hwnd):
        import win32gui
        with self.lock:
            if win32gui.GetForegroundWindow()!=int(hwnd):raise RuntimeError('前台窗口已变化，未发送操作')
            element=self.AutomationElement.FocusedElement.GetUpdatedCache(self.cache)
            item,_=self._entry(element,hwnd,cached=True)
            if not item or item['password'] or item['type'] not in ('Edit','ComboBox'):
                raise RuntimeError('当前焦点不是可填写的普通输入框，请先点击目标输入框')
            self.elements[item['ref']]=(element,time.monotonic(),int(hwnd))
            try:
                value=str(element.GetCurrentPattern(self.Patterns['set_value'].Pattern).Current.Value)
                item['value']=value[:4000];item['value_truncated']=len(value)>4000
            except Exception:raise RuntimeError('无法完整读取当前输入框，请先核对，未发送操作') from None
            return dict(hwnd=int(hwnd),element=item)

    def act(self,hwnd,operation,*,ref=None,name='',automation_id='',control_type='',value=''):
        with self.lock:
            element,item=self._resolve(hwnd,ref,name,automation_id,control_type)
            try:c=element.Current
            except Exception:raise RuntimeError('UIA元素已失效') from None
            if not c.IsEnabled:raise RuntimeError('UIA控件不可用')
            if c.IsPassword:raise RuntimeError('密码控件不进入通用语音输入路径')
            method=''
            try:
                if operation=='focus':method='SetFocus';element.SetFocus()
                elif operation=='invoke':
                    pattern=None
                    try:pattern=element.GetCurrentPattern(self.Patterns['invoke'].Pattern)
                    except Exception:pass
                    if pattern is not None:
                        method='InvokePattern';pattern.Invoke()
                    else:
                        try:pattern=element.GetCurrentPattern(self.Patterns['select'].Pattern)
                        except Exception:pass
                        if pattern is not None:method='SelectionItemPattern';pattern.Select()
                elif operation=='select':element.GetCurrentPattern(self.Patterns['select'].Pattern).Select();method='SelectionItemPattern'
                elif operation=='set_value':
                    pattern=element.GetCurrentPattern(self.Patterns['set_value'].Pattern)
                    if pattern.Current.IsReadOnly:raise RuntimeError('输入框只读，未发送操作')
                    method='ValuePattern';pattern.SetValue(str(value)[:4000])
                elif operation=='toggle':element.GetCurrentPattern(self.Patterns['toggle'].Pattern).Toggle();method='TogglePattern'
                elif operation in ('expand','collapse'):element.GetCurrentPattern(self.Patterns[operation].Pattern).Expand() if operation=='expand' else element.GetCurrentPattern(self.Patterns[operation].Pattern).Collapse();method=operation.title()+'Pattern'
                elif operation=='scroll':element.GetCurrentPattern(self.Patterns['scroll'].Pattern).Scroll(-1,-1);method='ScrollPattern'
                elif operation!='click':raise ValueError('未知UIA操作')
            except RuntimeError:raise
            except Exception:
                if method:raise RuntimeError('UIA操作已尝试，回执不确定；请先读取核对，未自动重试') from None
                if operation not in ('click','invoke'):raise RuntimeError('控件不支持该UIA操作') from None
            rect=self._rect(element)
            fallback=operation in ('click','invoke') and not method
            if fallback and (not rect or rect['right']<=rect['left'] or rect['bottom']<=rect['top']):
                raise RuntimeError('UIA控件没有可点击区域')
            verified=False;verification=None
            if operation=='set_value':
                deadline=time.monotonic()+.15
                while True:
                    actual=str(element.GetCurrentPattern(self.Patterns['set_value'].Pattern).Current.Value)
                    verified=actual==str(value)[:4000]
                    if verified or time.monotonic()>=deadline:break
                    time.sleep(.005)
                verification=dict(kind='value_equals',matched=verified)
            elif operation=='focus':
                verified=bool(element.Current.HasKeyboardFocus);verification=dict(kind='keyboard_focus',matched=verified)
            return dict(hwnd=int(hwnd),input_sent=not fallback,action='uia',needs_observe=not verified,
                        verified=verified,verification=verification,
                        method=method or 'MouseFallback',fallback=fallback,control=item,rect=rect,
                        revision=self.revisions.get(int(hwnd)),message='UIA动作已执行并回读确认' if verified else 'UIA动作已发送，需定向核对目标结果')

    def wait(self,hwnd,seconds=5,*,ref=None,name='',automation_id='',control_type='',state='exists',expected=None):
        hwnd=int(hwnd);deadline=time.monotonic()+max(.1,min(float(seconds),30))
        while time.monotonic()<=deadline:
            try:
                _,found=self._resolve(hwnd,ref,name,automation_id,control_type,include_offscreen=state=='offscreen')
                if state=='exists' and found:return dict(met=True,element=found)
                if found and state=='enabled' and bool(found['enabled'])==bool(expected):return dict(met=True,element=found)
                if found and state=='offscreen' and bool(found['offscreen'])==bool(expected):return dict(met=True,element=found)
            except Exception:
                pass
            time.sleep(min(.03,max(0,deadline-time.monotonic())))
        return dict(met=False,state=state,elapsed=round(time.monotonic()-(deadline-max(.1,min(float(seconds),30))),2))
