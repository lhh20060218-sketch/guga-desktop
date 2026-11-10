"""Application-owned tool registry; the same handlers serve typed and spoken commands."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QApplication

from core import guga_paths


class AppRuntime:
    def __init__(self, pet, panel, store):
        self.pet, self.panel, self.store = pet, panel, store
        from core.authorized_apps import AuthorizedApps
        self.apps = AuthorizedApps()
        from core.bg_director import BattlegroundDirector
        from core.bg_shadow import ShadowManager
        self.shadow=ShadowManager()
        self.battleground = BattlegroundDirector(panel)
        self.battleground.event.connect(panel._battleground_event)
        from core.dsh_worker import DshManager
        self.dsh = DshManager(panel)
        self.dsh.tools_enabled=True
        self.dsh.archive.recover_once()
        self.dsh.event.connect(panel._dsh_event)
        from core.screen_share import ScreenShareController
        self.screen_share=ScreenShareController(panel)
        from core.music_performance import MusicPerformance
        self.music=MusicPerformance(panel)
        self.music.performance_event.connect(panel._music_event)
        from core.media_workflow import MediaWorkflow
        self.media=MediaWorkflow(self.store.path.parent/'video-workflows')
        from core.workflow_catalog import WorkflowCatalog
        self.workflows=WorkflowCatalog(self.store.path.parent/'workflows.sqlite3')
        self._restore_upgrade_playback()

    def _restore_upgrade_playback(self):
        """Consume one short-lived local restart receipt; never start a voice call."""
        import json,time
        from pathlib import Path
        path=guga_paths.RUNTIME/'personal-harness/restart.json'
        if not path.is_file():return
        try:
            state=json.loads(path.read_text(encoding='utf-8'))
            path.unlink()
            music=state.get('music',{})
            if not 0<=time.time()-float(state.get('created',0))<120:return
            if music.get('playing') and isinstance(music.get('title'),str) and len(music['title'])<=80:
                def restore():
                    self.music.sing(music['title'])
                    QTimer.singleShot(1200,lambda:self.music.player.setPosition(max(0,int(music.get('position_ms',0)))))
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(700,restore)
        except (OSError,ValueError,TypeError):pass

    # ---- JoyCode：无 API，派单+界面注入，全程以回执驱动 ----
    def _joycode_adapter(self, workspace=None):
        from core.adapters.joycode_adapter import JoyCodeAdapter
        current=getattr(self,'_joycode',None)
        wanted=str(workspace) if workspace else ''
        if current is None or (wanted and str(current.workspace)!=wanted):
            current=JoyCodeAdapter(workspace=workspace,journal=self.panel.agent.journal,poll_interval=.5,
                                   computer=self.panel.agent.computer)
            self._joycode=current
            self._joycode_results={}
        return current

    @staticmethod
    def _joycode_windows():
        from core.window_inventory import list_windows
        windows=[item for item in list_windows('joycode') if not item.get('minimized')]
        return windows or list_windows('joycode')

    def _ppt_execute(self,args):
        """PPT 只做排版：大纲由模型给，失败时回结构化原因让模型改大纲而不是硬失败。"""
        from core.ppt_builder import build, inspect, outline_of, PPTError
        action=args.get('action') or 'create'
        try:
            if action=='inspect':
                return dict(ok=True,**inspect(args.get('path') or args.get('output') or ''))
            if action!='create':raise PPTError('未知操作：%s；只支持 create/inspect'%action)
            return dict(ok=True,**build(outline_of(args.get('outline')),output=args.get('output'),
                                        accent=args.get('accent'),template=args.get('template')))
        except PPTError as exc:
            return dict(ok=False,error='outline_invalid',message=str(exc),
                        hint='按 message 修正 outline 后重试，不要原样重发')
        except Exception as exc:
            return dict(ok=False,error='ppt_failed',message=str(exc)[:300])

    def _video_execute(self,args):
        """零额度成片：外部成片可用就先本地后处理，不可用或失败自动回落本地合成。"""
        import time
        from core import video_studio
        action=str(args.get('action') or 'create').lower()
        try:
            if action=='inspect':
                return dict(ok=True,**video_studio.inspect(args.get('path') or args.get('output') or ''))
            if action!='create':raise video_studio.VideoError('未知操作：%s；只支持 create/inspect'%action)
            script=video_studio.script_of(args.get('script') or args.get('outline'))
            mode=str(args.get('mode') or 'auto').lower()
            source=str(args.get('source_path') or '').strip()
            started=time.perf_counter();fallback=None
            if mode!='local' and (source or mode=='external'):
                if source:
                    try:
                        result=self._video_external(script,source)
                        result.update(ok=True,route='external_postprocess',
                                      elapsed_ms=int((time.perf_counter()-started)*1000))
                        return result
                    except Exception as exc:
                        fallback=str(exc)[:300]
                else:
                    fallback='没有可用的外部成片 source_path（外部生成通常受额度限制）'
            result=video_studio.synthesize(script,voice=bool(args.get('voice',True)),
                                           output=args.get('output'),size=args.get('size') or '1280x720')
            result.update(ok=True,route='local_synthesis',requested_mode=mode,
                          elapsed_ms=int((time.perf_counter()-started)*1000))
            if fallback:
                result.update(fallback_from='external',fallback_reason=fallback)
            return result
        except video_studio.VideoError as exc:
            return dict(ok=False,error='script_invalid',message=str(exc),
                        hint='按 message 改 script（1—8镜，每镜一句 narration≤80字 + visual/headline），不要原样重发')
        except Exception as exc:
            return dict(ok=False,error='video_failed',message=str(exc)[:300])

    def _video_external(self,script,source):
        """外部/已有成片：核验原片 → 本地烧字幕 → 等待渲染，失败信息交给上层回落本地合成。"""
        import time
        from pathlib import Path
        from core import video_studio
        from core.media_workflow import inspect_video
        probe=inspect_video(str(Path(source).expanduser()))
        folder=video_studio.WORK_DIR/('external-'+time.strftime('%Y%m%d-%H%M%S'))
        srt=video_studio.write_subtitles(script,folder/'captions.srt',total=probe['seconds'])
        job=self.media.execute({'action':'render','path':probe['path'],'subtitles':str(srt)},
                               self.panel.agent.cancel_event)
        job_id=job['job_id'];deadline=time.monotonic()+60
        while time.monotonic()<deadline:
            state=self.media.status(job_id)
            if state.get('state') in ('ready','failed','cancelled','interrupted'):break
            if self.panel.agent.cancel_event.wait(.3):raise RuntimeError('外部后处理被取消')
        else:
            raise RuntimeError('外部后处理超过60秒未完成')
        if state.get('state')!='ready':
            raise RuntimeError('外部后处理失败：%s'%(state.get('error') or state.get('message') or state.get('state')))
        result=video_studio.inspect(state['output'])
        result.update(ok=True,subtitles=state.get('subtitles'),source_video=probe['path'],job_id=job_id)
        return result

    def _pipeline_execute(self,args):
        """跨工具链：WorkBuddy 提示词 → JoyCode 代码 → 本地核验；失败只报卡点，不自行生成。"""
        from core import cross_tool_pipeline
        requirement=str(args.get('requirement') or '').strip()
        if len(requirement)<8:
            return dict(ok=False,error='requirement_too_short',
                        message='requirement 太短，无法交给外部工具；请保留用户原始需求细节')
        try:
            return cross_tool_pipeline.run(
                requirement,acceptance=args.get('acceptance'),product=args.get('product') or 'website',
                timeout=max(120,min(int(args.get('timeout_seconds') or 900),1200)),
                cancel=self.panel.agent.cancel_event,why=str(args.get('why') or '').strip())
        except Exception as exc:
            return dict(ok=False,error='pipeline_failed',message=str(exc)[:300])

    def _local_tools_execute(self, args):
        """本机 AI 软件清单 + 本地优先路由 + 服务器上报。"""
        from core import local_tools
        from core import tool_router
        action = str(args.get('action') or 'list')
        try:
            if action == 'scan':
                data = local_tools.scan(launch_probe=bool(args.get('launch_probe')))
                verified = [t for t in data['tools'] if t.get('launch_ok')]
                return dict(ok=True, scanned=len(data['tools']), launchable=len(verified),
                            cached=str(local_tools.CACHE), tools=data['tools'])
            if action == 'list':
                entries = local_tools.inventory(args.get('query', ''), args.get('capability', ''))
                return dict(ok=True, total=len(entries), tools=entries,
                            note='commandable=有专用适配器可自动派单；launch_ok=真实启动核验结果')
            if action == 'probe':
                app_id = str(args.get('id') or '').strip()
                spec = next((s for s in local_tools.APPS if s['id'] == app_id), None)
                if not spec:
                    return dict(ok=False, error='unknown_tool',
                                message='未知软件 id；可选：' + '、'.join(s['id'] for s in local_tools.APPS))
                result = local_tools.probe(spec)
                return dict(ok=bool(result.get('launch_ok')), result=result,
                            error='' if result.get('launch_ok') else result.get('reason'))
            if action == 'route':
                requirement = str(args.get('requirement') or '').strip()
                if len(requirement) < 4:
                    return dict(ok=False, error='requirement_too_short',
                                message='route 需要用户需求原话')
                decision = tool_router.route(requirement)
                return dict(ok=True, decision=decision, explanation=tool_router.explain(decision))
            if action == 'report':
                return local_tools.report()
            raise ValueError('未知清单操作')
        except Exception as exc:
            return dict(ok=False, error='local_tools_failed', message=str(exc)[:300])

    def _joycode_execute(self,args):
        import json
        import threading
        from core.failure_report import failure_payload
        action=str(args.get('action') or 'status')
        adapter=self._joycode_adapter(args.get('workspace'))
        adapter.refresh_workspace()
        windows=self._joycode_windows()
        if action=='list':
            return dict(ide=windows,pending=adapter.pending_tasks(),inbox=str(adapter.inbox),
                        outbox=str(adapter.outbox),workspace=str(adapter.workspace))
        if action=='status':
            receipts=adapter.poll(mark_handled=False)
            background=getattr(self,'_joycode_results',{})
            return dict(ide=[dict(hwnd=item.get('hwnd'),title=item.get('title')) for item in windows],
                workspace=str(adapter.workspace),inbox=str(adapter.inbox),outbox=str(adapter.outbox),
                pending=adapter.pending_tasks(),
                receipts=[dict(task_id=r.get('task_id'),status=r.get('status'),
                               self_check=str(r.get('self_check') or '')[:300]) for r in receipts[-5:]],
                background=[dict(task_id=key,status=(value or {}).get('status'))
                            for key,value in list(background.items())[-5:]],
                hint='pending非空说明IDE还没取单；用prompt发送/guga-run，再用receipt查回执')
        if action=='dispatch':
            goal=str(args.get('goal') or '').strip();acceptance=str(args.get('acceptance') or '').strip()
            if not goal or not acceptance:raise ValueError('dispatch 需要 goal 和 acceptance')
            try:
                task=adapter.create_task(goal,acceptance,task_id=args.get('task_id'))
            except Exception as exc:
                if getattr(exc,'code','')=='workspace_not_found':
                    return failure_payload(
                        'workspace_not_found', '没找到 JoyCode 当前工程，请选择',
                        app='JoyCode', candidates=adapter.workspace_candidates,
                        workspace=dict(source=adapter.workspace_source,path=''))
                raise
            launched=None;error=None;trigger=None
            if args.get('launch',True):
                try:launched=adapter.open_ide()
                except Exception as exc:error=str(exc)[:200]
            auto=bool(args.get('auto',True))
            if auto and not error:
                try:trigger=adapter.trigger(task['task_id'])
                except Exception as exc:
                    trigger=dict(ok=False,error=getattr(exc,'code','trigger_failed'),
                                 message=str(exc)[:300],detail=getattr(exc,'detail',{}),
                                 manual=adapter._manual_for(getattr(exc,'code','trigger_failed'),task['task_id']))
            seconds=max(0,min(int(args.get('seconds') or 0),30))
            if seconds:
                def collect(task_id=task['task_id']):
                    receipt=adapter.wait_for_result(task_id,timeout=seconds,
                                                    cancel=self.panel.agent.cancel_event)
                    if receipt:self._joycode_results[task_id]=receipt
                threading.Thread(target=collect,daemon=True).start()
            submitted=bool((trigger or {}).get('submitted'))
            ok=not trigger or bool(trigger.get('ok',submitted))
            hint=(('已把 /guga-run %s 自动送进 JoyCode，用receipt查回执'%task['task_id']) if submitted
                  else '派单只是排队，不等于完成；可用 auto=true 自动触发，或人工敲 /guga-run 后再查receipt')
            result=dict(ok=ok,task_id=task['task_id'],
                inbox_file=str(adapter.inbox/(task['task_id']+'.json')),
                workspace=str(adapter.workspace),launched=launched,launch_error=error,trigger=trigger,
                ide=[dict(hwnd=item.get('hwnd'),title=item.get('title')) for item in windows],
                hint=hint)
            if not ok:
                raw_code=str((trigger or {}).get('error') or (trigger or {}).get('code') or 'not_submitted')
                raw=(str((trigger or {}).get('message') or '') or error or
                     str((trigger or {}).get('detail') or '') or
                     ('JoyCode 没有确认提交，回读/回车证据见 trigger.detail'))
                result.update(failure_payload(
                    raw_code, raw, str((trigger or {}).get('manual') or '') or hint,
                    app='JoyCode', hint=hint))
            return result
        if action=='receipt':
            task_id=str(args.get('task_id') or '').strip()
            if not task_id:raise ValueError('receipt 需要 task_id')
            receipt=getattr(self,'_joycode_results',{}).get(task_id)
            if not receipt:
                path=adapter.outbox/(task_id+'.json')
                if path.is_file():
                    try:receipt=json.loads(path.read_text(encoding='utf-8-sig'))
                    except (OSError,ValueError):receipt=None
            if not receipt:
                seconds=max(0,min(int(args.get('seconds') or 0),60))
                receipt=adapter.wait_for_result(task_id,timeout=seconds,
                                                cancel=self.panel.agent.cancel_event)
            return dict(task_id=task_id,found=bool(receipt),receipt=receipt,
                progress=adapter.progress(task_id),
                hint='没有回执时先确认JoyCode在运行、是否执行了/guga-run，以及inbox任务是否还在')
        if action=='prompt':
            text=str(args.get('text') or '').strip()
            if not text:raise ValueError('prompt 需要 text')
            import time
            started=time.perf_counter()
            submit=bool(args.get('submit',True))
            try:
                from core.adapters.joycode_ui import JoyCodeUIError
                result=adapter.trigger(text=text,submit=submit)
            except JoyCodeUIError as exc:
                return failure_payload(
                    exc.code, str(exc), app='JoyCode', filled=False, submitted=False,
                    detail=exc.detail,
                    hint=str(exc),manual=adapter._manual_for(exc.code,args.get('task_id') or '<task_id>'),
                    elapsed_ms=int((time.perf_counter()-started)*1000))
            except Exception as exc:
                return failure_payload(
                    'trigger_failed', '%s: %s' % (type(exc).__name__, str(exc)[:200]),
                    app='JoyCode', filled=False, submitted=False,
                    hint=str(exc)[:300],manual=adapter._ui_layer().manual_hint(args.get('task_id') or '<task_id>'),
                    elapsed_ms=int((time.perf_counter()-started)*1000))
            point=result.get('point') or {}
            history=[item for item in (result.get('history') or []) if isinstance(item,dict)]
            rounds=[item for item in history if item.get('stage')=='focus']
            submits_hist=[item for item in history if item.get('stage')=='submit']
            steps=[dict(step='window',hwnd=result.get('hwnd'),launched=result.get('launched'),
                        title=result.get('window_title')),
                   dict(step='panel',**(result.get('panel') or {})),
                   dict(step='locate',source=point.get('source'),x=point.get('x'),y=point.get('y')),
                   dict(step='fill',attempts=len(rounds),verified=bool(result.get('verified'))),
                   dict(step='submit',submits=submits_hist,submitted=result.get('submitted'))]
            return dict(ok=bool(result.get('submitted') or not submit),filled=bool(result.get('verified')),
                submitted=bool(result.get('submitted')),text_found=bool(result.get('verified')),
                point=point,steps=steps,status=result.get('status'),
                hint='已提交到JoyCode；等待IDE处理，用receipt查询回执，不要重复发送',
                elapsed_ms=int((time.perf_counter()-started)*1000))
        raise ValueError('未知 JoyCode 操作')

    def execute(self, name, args):
        if name=='screen_share':
            action=args.get('action')
            if action=='start':
                if not self.panel.voice_active:
                    raise RuntimeError('共享屏幕只在长语音对话中自动启用；当前没有长语音通话')
                self.panel._screen_share_manual_stop=False
                return self.screen_share.start(args.get('fps'),'call')
            if action=='stop':
                if self.panel.voice_active:self.panel._screen_share_manual_stop=True
                return self.screen_share.stop()
            if action=='status':return self.screen_share.status()
            if action=='context':return self.screen_share.context(max(1,min(60,int(args.get('max_age',12)))))
            if action=='assist':return self.screen_share.assist_context(max(1,min(60,int(args.get('max_age',12)))))
            if action=='observation':return self.screen_share.observation(max(1,min(60,int(args.get('max_age',12)))))
            if action=='snapshot':return self.screen_share.snapshot()
            raise ValueError('未知共享屏幕操作')
        if name=='voice_session':
            action=args.get('action')
            voice=self.panel.voice
            if action=='status':
                from core.realtime_voice import load_settings
                cfg=load_settings()
                return dict(active=bool(self.panel.voice_active and voice and voice.active),
                    connected=bool(voice and voice.connected),
                    reconnecting=bool(voice and voice.active and not voice.connected),
                    starting=bool(self.panel.voice_active and voice and not voice.active),
                    last_error=(voice.last_error if voice else ''),provider=cfg.get('provider'),
                    model=cfg.get('model'),free_only=bool(cfg.get('free_only',True)),
                    quota_confirmation_matches=(cfg.get('free_quota_confirmed_provider')==cfg.get('provider') and
                        cfg.get('free_quota_confirmed_model')==cfg.get('model')),
                    usage=dict(rounds=voice._usage_rounds,reported_total_tokens=voice._usage_total,
                        unreported_rounds=voice._usage_missing) if voice else None)
            if action=='start':
                if self.panel.voice_active or self.panel.busy or self.panel.short_voice.active:
                    raise RuntimeError('当前已有通话、任务或录音；未启动新语音会话')
                if self.pet._realtime_active() or getattr(self.pet,'_recording',False):
                    raise RuntimeError('另一种语音模式仍在使用麦克风；未启动新会话')
                from core.realtime_voice import load_settings,connection_url
                cfg=load_settings();connection_url(cfg)
                if cfg.get('free_only',True) and (cfg.get('free_quota_confirmed_provider')!=cfg.get('provider') or
                        cfg.get('free_quota_confirmed_model')!=cfg.get('model')):
                    raise RuntimeError('当前免费额度保护未匹配所选模型；已阻止语音联网')
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(0,lambda:self.pet._open_agent_voice())
                return dict(accepted=True,started=False,message='已请求咕嘎打开实时通话；请查询status确认麦克风与连接状态')
            if action=='stop':
                if not self.panel.voice_active:
                    return dict(stopped=False,active=False,message='当前没有活动的实时通话')
                from PyQt5.QtCore import QTimer
                QTimer.singleShot(0,lambda:self.pet._end_agent_voice())
                return dict(stopped=True,active=True,message='已请求结束实时通话；请查询status确认会话已断开')
            raise ValueError('未知实时语音操作')
        if name=='battleground' and args.get('action') in ('shadow','shadow_stop'):
            if args.get('action')=='shadow_stop':return self.shadow.stop()
            return self.shadow.start(args.get('seconds',900),bool(args.get('train',True)))
        if name=='music_performance':
            action=args.get('action')
            if action=='status':return self.music.status()
            if action=='stop':return self.music.stop()
            if action=='pause':return self.music.pause()
            if action=='resume':return self.music.resume()
            if action=='sing':return self.music.sing(str(args.get('title','')).strip())
            raise ValueError('未知音乐操作')
        if name=='media_workflow':
            return self.media.execute(dict(args),self.panel.agent.cancel_event)
        if name == 'dsh_task':
            action=args.get('action')
            if action=='status':return self.dsh.status()
            if action=='stop':return self.dsh.stop()
            if action=='start':
                accepted=self.dsh.start(args.get('task',''),self.panel.active_id,args.get('cwd'),
                    args.get('seconds',900),args.get('session_id'),profile=dict(self.panel.active_profile),
                    memory_context='\n'.join(x['content'] for x in self.panel.memory.recall(self.panel.active_agent_id,args.get('task',''),limit=6)),
                    workflow=self.workflows.match(args.get('task','')))
                self.pet._multi_agent.work_state(self.panel.active_agent_id,'thinking','dsh:'+accepted['job_id'])
                return accepted
            raise ValueError('未知 DSH 操作')
        if name == 'battleground':
            action = args.get('action')
            if action == 'status':
                return dict(self.battleground.status(),shadow=self.shadow.status())
            if action == 'stop':
                return self.battleground.stop()
            if action == 'open':
                from core.bg_live_windows import HearthstoneWindow
                return dict(message=HearthstoneWindow().open())
            self.battleground.conversation_id = self.panel.active_id
            return self.battleground.start(action,
                args.get('max_actions',120 if action=='auto' else 12),
                args.get('seconds',1200 if action=='auto' else 240))
        if name == 'applications':
            if args.get('action')=='command':
                from core.fast_commands import match
                text=str(args.get('name',''))
                if not match(text).get('matched'):raise ValueError('仅支持已识别的本地快速命令；本操作不会转交大模型')
                self.panel.send(text)
                return dict(self.panel._last_fast_result or {},route='local_fast_command')
            if args.get('action') == 'list':
                entries=self.apps.available(args.get('query',''))
                from core.window_inventory import list_windows
                running=list_windows(args.get('query','')) if self.apps.access.enabled else []
                return {'authorized_apps': list(entries)[:200], 'total':len(entries), 'running_windows':running,
                    'access':self.apps.access.status(),
                    'note':'running_windows是已打开软件，authorized_apps是可启动软件；先复用已打开窗口。'}
            if args.get('action') == 'open':
                try:
                    return self.apps.open(args['name'])
                except Exception as exc:
                    # 软件名查不到是可解释的失败，必须带 code/stage/next_action 四段，
                    # 不能以裸异常冒泡后显示成“未归类：未知异常类型”。
                    if getattr(exc, 'code', None) != 'app_not_found':
                        raise
                    from core.failure_report import failure_payload
                    return failure_payload('app_not_found',
                        '%s: %s' % (type(exc).__name__, str(exc)))
            raise ValueError('未知软件操作')
        if name == 'joycode':
            return self._joycode_execute(args)
        if name == 'ppt':
            return self._ppt_execute(args)
        if name == 'video':
            return self._video_execute(args)
        if name == 'pipeline':
            return self._pipeline_execute(args)
        if name == 'local_tools':
            return self._local_tools_execute(args)
        if name == 'confirm_external':
            if self.apps.access.enabled:
                return {'approved':True,'source':'user_enabled_full_access'}
            from PyQt5.QtWidgets import QMessageBox
            from PyQt5.QtCore import QTimer
            import json
            box = QMessageBox(self.panel)
            box.setWindowTitle('咕嘎 · 确认软件操作')
            box.setText('此工具尚未被标记为可直接执行的常规操作，是否允许本次调用？')
            box.setInformativeText(args['server'] + ' / ' + args['tool'] + '\n' + json.dumps(args.get('arguments', {}), ensure_ascii=False)[:1500])
            box.setStandardButtons(QMessageBox.Yes | QMessageBox.No)
            box.setDefaultButton(QMessageBox.No)
            QTimer.singleShot(30000, box.reject)
            cancel_timer = QTimer(box)
            cancel_timer.setInterval(100)
            cancel_timer.timeout.connect(lambda: box.reject() if self.panel.agent.cancel_event.is_set() else None)
            cancel_timer.start()
            approved = box.exec_() == QMessageBox.Yes
            cancel_timer.stop()
            return {'approved': approved}
        if name == 'app_state':
            import os
            from core.authorized_apps import ROOT
            from core.realtime_agent import ROUTER_VERSION
            from core.self_agent import HARNESS_VERSION
            return dict(runtime=dict(pid=os.getpid(),project_root=str(ROOT),voice_router_version=ROUTER_VERSION),
                        agent_harness_version=HARNESS_VERSION,
                        pet=dict(x=self.pet.x(), y=self.pet.y(), visible=self.pet.isVisible(),
                                opacity=self.pet.windowOpacity(), status=self.pet._status.snapshot(),
                                volume=self.pet._tts._player.volume()),
                        current_conversation_id=self.panel.active_id,
                        voice_active=self.panel.voice_active,
                        voice_path=dict(owner_only=bool(self.panel.voice._cfg.get('owner_only',False)) if self.panel.voice else False,
                            speaker_gate_active=bool(self.panel.voice and self.panel.voice._speaker_gate),
                            interaction=self.panel.voice.interaction_status() if self.panel.voice else None),
                        workspace=self.store.snapshot(),
                        authorized_apps=list(self.apps.entries()),
                        battleground=self.battleground.status(),
                        dsh=self.dsh.status(),
                        screen_share=dict(self.screen_share.status(),
                            call_expected=bool(self.panel.voice_active and not self.panel._screen_share_manual_stop),
                            watchdog_active=self.panel._screen_share_watchdog_timer.isActive(),
                            start_error=getattr(self.panel,'_screen_share_start_error',''),
                            voice_bridge=self.panel.voice.screen_bridge_status() if self.panel.voice else dict(attached=False),
                            recovery_failures=getattr(self.panel,'_screen_share_recovery_failures',0)),
                        performance=dict(avatar_idle_fps=round(1000/self.pet._anim2d._idle_interval_ms,1),
                            avatar_active_fps=round(1000/self.pet._anim2d._active_interval_ms,1),
                            avatar_interval_ms=self.pet._anim2d._timer.interval(),gaze_interval_ms=self.pet._gaze_timer.interval(),
                            background_interval_ms=self.pet._bg_timer.interval(),battleground_interval_ms=self.pet._watch_timer.interval(),
                            hidden_animation_paused=not self.pet.isVisible()),
                        media_workflow=self.media.status(),
                        personal_harness=dict(backend='auto:local-first',tickets=self.dsh.archive.recent(self.panel.active_agent_id,limit=5)),
                        assistant_contract=dict(version=HARNESS_VERSION,routing='local_first_dsh_for_complex_engineering',
                            browser_control=dict(mode='current_page_single_step',task_model=False,
                                success_feedback='immediate_bubble',manual_quiet_seconds=60),
                            conversation=dict(mode='awake' if self.panel.voice_active else 'companion',
                                companion_interval_seconds=self.panel.proactive.interval_seconds,
                                news_refresh_seconds=self.panel.proactive.news_refresh_seconds,
                                task_progress_seconds=30,foreground_qa_independent=True,
                                hold_to_talk_in_speech_bubble=True,speech_bubble_count=1,
                                qa_search='public_snippets_with_sources',profile_memory='explicit_user_facts'),
                            voice_control='local_mcp_start_status_stop_free_guard_v1',
                            fast_action_running=bool(getattr(self.panel,'_fast_inflight',False) or getattr(self.panel,'_fast_launch_count',0)),
                            failure_explanations='host_receipts_even_when_model_unavailable',
                            close_page='one_selected_tab_then_verify',
                            screen_share=dict(capture_fps=self.screen_share.fps,range=[2,5],max_visual_calls_per_minute=self.screen_share.max_calls_per_minute,
                                storage='memory_only',visible_preview=False,start_policy='long_voice_call',
                                visual_bridge='change_sampling_primary_chat_fallback',audio_model_direct_video=False),
                            isolation=dict(desktop='host',tab_worker='separate_process_7s',
                                           security_sandbox=False)),
                        music=self.music.status(),
                        stage=dict(sunglasses=self.pet._anim.sunglasses,dancing=self.pet._anim.dancing,
                                   pet_scale=getattr(self.pet,'_pet_scale',1.),
                                   floating_ui_version='2026-10-29.7',
                                   task_motion=self.pet._anim2d._task_motion.snapshot(),
                                   task_animation=self.pet._anim2d.task_animation_status(),
                                   gesture_version='2026-11-02.1',
                                   selection_trigger='uia_text_geometry_before_capture',
                                   selection_actions=['解释','截图分析'],
                                   menu_version='2026-11-02.3',
                                   selection_reading='cached_visual_region',
                                   selection_status=getattr(getattr(self.pet,'_screen_tools',None),'last_selection_status','unavailable'),
                                   chat_route=self.panel.route_combo.currentData(),
                                   answer_effort=self.panel.effort_combo.currentData(),
                                   short_voice_active=self.panel.short_voice.active,
                                   proactive=self.panel.proactive.status(),
                                   selection_toolbar_enabled=bool(getattr(getattr(self.pet,'_screen_tools',None),'selection_enabled',False)),
                                   selection_hook_active=bool(getattr(getattr(self.pet,'_screen_tools',None),'selection_hook_ok',False)),
                                   screen_hotkey_conflicts=list(getattr(getattr(self.pet,'_screen_tools',None),'hotkey_errors',[])),
                                   expression=self.pet._anim.expression,
                                   appearance='3d' if self.pet._anim is self.pet._anim3d else 'illustration',
                                   motion_version='2',demo_active=bool(getattr(self.pet,'_avatar_demo_running',False)),
                                   last_demo=getattr(self.pet,'_last_avatar_demo',None)),
                        multi_agent=getattr(getattr(self.pet,'_multi_agent',None),'status',lambda:{})(),
                        active_agent=dict(id=self.panel.active_agent_id,profile=self.panel.active_profile),
                        local_access=self.apps.access.status(),
                        task=self.panel.agent.task_status(),
                        capabilities=['pet_control', 'workspace', 'applications', 'self_ask', 'ecosystem','battleground','dsh_task','local_computer','computer','screen_share','task_plan','media_workflow','workflow_catalog','wechat_send_self','wechat','browser','web_search','music_performance'],
                        scope='本机能力由完整访问开关控制；继承咕嘎进程实际Windows权限')
        if name == 'pet_control':
            return self._pet(args)
        if name == 'workspace':
            return self._workspace(args)
        raise ValueError('该工具未注册')

    def _pet(self, args):
        pet = self.pet
        action = args.get('action')
        if action == 'move':
            x, y = int(args['x']), int(args['y'])
            screens = QApplication.screens()
            screen = next((s for s in screens if s.availableGeometry().contains(x, y)), QApplication.primaryScreen())
            g = screen.availableGeometry()
            x = max(g.left(), min(x, g.right() - pet.width() + 1))
            y = max(g.top(), min(y, g.bottom() - pet.height() + 1))
            pet.move(x, y)
            pet._save_state()
            return dict(x=pet.x(), y=pet.y())
        if action == 'show':
            pet.show()
            pet._force_top()
        elif action == 'hide':
            pet.hide()
        elif action == 'reset_position':
            pet._reset_pos()
        elif action == 'animate':
            name = args.get('name', 'bounce')
            if name not in ('look_up_step','idle_doze','idle_heart','bounce', 'shake', 'point', 'peek', 'tsundere','head_shake','nod','tilt','wave','sunglasses','remove_sunglasses','dance','stop_dance','sneak_peek'):
                raise ValueError('未知动画')
            if str(getattr(self.panel,'active_agent_id','001'))!='001' and hasattr(pet,'_multi_agent'):
                pet._multi_agent.gesture(self.panel.active_agent_id,name)
            else:pet._perform_gesture(name)
        elif action == 'set_expression':
            name = args.get('name')
            allowed=('normal','happy','sleepy','surprised','sad','playful')
            if str(getattr(self.panel,'active_agent_id','001'))!='001':allowed+=('angry','eating')
            if name not in allowed:raise ValueError('未知表情')
            if str(getattr(self.panel,'active_agent_id','001'))!='001' and hasattr(pet,'_multi_agent'):
                pet._multi_agent.set_expression(self.panel.active_agent_id,name)
                companion=pet._multi_agent.companions.get(self.panel.active_agent_id)
                expression=companion.anim.expression if companion else name
                return dict(action=action,expression=expression,held=expression!='normal',applied=expression==name)
            pet._anim.set_expression(name)
            return dict(action=action,expression=pet._anim.expression,
                        held=pet._anim.expression!='normal',
                        applied=pet._anim.expression==name)
        elif action == 'interact':
            name = args.get('name', '')
            if name not in ('feed', 'play', 'pet', 'sleep', 'dance'):
                raise ValueError('未知互动')
            pet._act(name)
        elif action == 'set_opacity':
            value = float(args['value'])
            if not .3 <= value <= 1:
                raise ValueError('透明度需要在 0.3—1 之间')
            pet.setWindowOpacity(value)
            pet._config.opacity = value
        elif action == 'set_volume':
            value = int(args['value'])
            if not 0 <= value <= 100:
                raise ValueError('音量需要在 0—100 之间')
            pet._tts._player.setVolume(value)
            pet._config._s.setValue('agent/volume', value)
        elif action == 'set_topmost':
            enabled = bool(args['value'])
            pet.setWindowFlag(Qt.WindowStaysOnTopHint, enabled)
            pet.show()
            pet._config._s.setValue('agent/topmost', enabled)
        elif action == 'set_bongo':
            if args['value']:
                pet._show_bongo()
            else:
                pet._bongo.hide()
                pet._bongo_on = False
                pet.setFixedSize(pet._iw, pet._ih)
        elif action == 'open_chat':
            self.panel.show()
            self.panel.raise_()
        elif action == 'open_voice_settings':
            # Deferred to avoid blocking the queued tool callback in a modal dialog.
            from PyQt5.QtCore import QTimer
            QTimer.singleShot(0, pet._configure_realtime_voice)
            return {'opened': '语音设置', 'state': '已请求打开，等待用户设置'}
        elif action == 'open_battleground_lab':
            pet._open_bg_agent()
        elif action == 'open_battleground_live':
            pet._open_bg_live()
        else:
            raise ValueError('未注册的自身操作')
        return dict(action=action, visible=pet.isVisible(), x=pet.x(), y=pet.y())

    def _workspace(self, args):
        action = args.get('action')
        ident = args.get('id') or self.panel.active_id
        result = {}
        if action == 'create_project':
            result['project_id'] = self.store.create_project(args['name'])
        elif action == 'rename_project':
            if not args.get('id'):
                raise ValueError('更名项目需要明确的项目 ID')
            self.store.rename('project', ident, args['name'])
        elif action == 'new_conversation':
            result['conversation_id'] = self.store.create_conversation(args.get('name', '新对话'), args.get('project_id') or None)
            # Keep this running turn bound to its original conversation.
        elif action == 'rename_conversation':
            self.store.rename('conversation', ident, args['name'])
        elif action == 'move_conversation':
            self.store.move(ident, args.get('project_id') or None)
        elif action == 'archive_conversation':
            self.store.archive(ident)
        elif action == 'restore_conversation':
            self.store.archive(ident, False)
        elif action == 'list_archived':
            return self.store.snapshot(archived=True)
        else:
            raise ValueError('未注册的会话操作')
        self.panel.refresh_tree()
        return dict(result, workspace=self.store.snapshot())
