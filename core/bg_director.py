"""Background game jobs, separate observation/action backends and factual reviews."""
from collections import deque
import threading
import time
import uuid

from PyQt5.QtCore import QObject, pyqtSignal


def review_text(records, *, combat_finished=False):
    verified = [r for r in records if r.get('verified')]
    prefix = '这一轮战斗结束了。' if combat_finished else '本次操作结束。'
    if not verified:
        return prefix + '没有获得已确认的操作回执，不能说已经完成买牌或出牌。'
    names = {'BUY':'买牌','PLAY':'出牌','SELL':'卖牌','UPGRADE':'升本','REFRESH':'刷新','FREEZE':'冻结切换'}
    details = '；'.join(names.get(r['action']['kind'],r['action']['kind'])+'：'+str(r.get('reason',''))[:100]
                       for r in verified[-3:])
    return prefix + f'日志确认了 {len(verified)} 步。' + details + '。这些是当时的决策理由，不能据此断言该操作导致了胜负。'


class BattlegroundDirector(QObject):
    event = pyqtSignal(object)

    def __init__(self, parent=None, session_factory=None):
        super().__init__(parent)
        self._factory = session_factory
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._worker = None
        self._session = None
        self._state = dict(running=False, mode=None, confirmed=0, phase='unknown')
        self._recent = deque(maxlen=12)
        self._event_seq = 0

    def status(self):
        from core.bg_lab_status import training_status
        from core.netcut_budget import DisconnectBudget
        from core.bg_current_knowledge import status as card_knowledge_status
        lab = training_status()
        try:
            from core.log_reader import read_current_board
            board = read_current_board() or {}
        except Exception:
            board = {}
        netcut = DisconnectBudget().status(board.get('game_key',''))
        with self._lock:
            from core.bg_pipeline import backend_capabilities
            return dict(self._state, recent=list(self._recent),
                        observation_backend='Power.log', action_backend='window_input',
                        screen_backend='existing_vision_model_game_client_only',
                        memory_execution_available=False, pipeline=backend_capabilities(),
                        local_training=lab, netcut=netcut,
                        card_knowledge=card_knowledge_status())

    def stop(self):
        self._stop.set()
        if self._session:
            self._session.stop.set()
        return dict(requested=True, message='已请求停止；正在返回的模型结果不会触发新输入')

    def start(self, mode='step', max_actions=12, seconds=240):
        if mode not in ('step','auto','observe','memory','look','netcut'):
            raise ValueError('未知战棋任务模式')
        if type(max_actions) is not int or not 1 <= max_actions <= 500:
            raise ValueError('本次最多允许 1—500 步')
        if type(seconds) is not int or not 10 <= seconds <= 1800:
            raise ValueError('本次时间预算需要 10—1800 秒')
        with self._lock:
            if self._worker and self._worker.is_alive():
                raise RuntimeError('战棋任务尚在运行；先查询状态或停止')
            self._stop = threading.Event()
            self._recent.clear()
            self._state = dict(running=True, mode=mode, confirmed=0, phase='unknown',
                               job_id=uuid.uuid4().hex, seconds=seconds,
                               conversation_id=getattr(self, 'conversation_id', None))
            self._worker = threading.Thread(target=self._run, args=(mode,1 if mode=='step' else max_actions,seconds),
                                            name='guga-bg-director',daemon=True)
            self._worker.start()
        return dict(accepted=True, job_id=self._state['job_id'], mode=mode, seconds=seconds,
                    message='任务已启动；后台运行不等于操作已成功。完成后会主动报告实际回执。')

    def _publish(self, event):
        with self._lock:
            self._event_seq += 1
            event = dict(event, event_id=self._state['job_id']+':'+str(self._event_seq),
                         job_id=self._state['job_id'], conversation_id=self._state.get('conversation_id'))
            self._recent.append(event)
        self.event.emit(event)

    def _record(self, event):
        if event['type'] == 'action_confirmed':
            with self._lock:
                self._state['confirmed'] += 1
        self._publish(event)

    def _run(self, mode, count, seconds):
        records, pending = [], []
        deadline = time.monotonic()+seconds
        try:
            if mode == 'netcut':
                from core.log_reader import read_current_board
                from core.netcut_budget import DisconnectBudget
                board = read_current_board()
                if not board or not board.get('active'):
                    raise RuntimeError('没有进行中的酒馆战棋对局，未拔线')
                if not board.get('theirs'):
                    raise RuntimeError('当前没有可见战斗，招募阶段拔线不会跳过战斗；未执行')
                combat_id = f"{board.get('turn','?')}:{len(board['theirs'])}"
                result = DisconnectBudget().cut(board.get('game_key',''), combat_id)
                with self._lock:
                    self._state['netcut'] = result
                self._publish(dict(type='netcut', ok=result['ok'],
                                   count=result['count'], remaining=result['remaining'],
                                   speech=f"已自动断开局连接，本局第 {result['count']} 次，最多 9 次；等待游戏重连。"))
                return
            if mode == 'look':
                from core.bg_live import inspect_screen
                from core.bg_live_windows import HearthstoneWindow
                from core.bg_agent import load_config
                image, _ = HearthstoneWindow().capture()
                result = inspect_screen(image,load_config())
                with self._lock:
                    self._state['screen_observation'] = result
                if not self._stop.is_set():
                    self._publish(dict(type='screen_observation',observation=result,
                        speech=('当前画面辨认不够清楚。' if result['confidence']<.9 else '我看到的当前画面是：')+result['summary']))
                return
            if mode == 'memory':
                from core.bg_memory import read_board
                snapshot = read_board()
                with self._lock:
                    self._state['memory_snapshot'] = snapshot
                if not self._stop.is_set():
                    self._publish(dict(type='memory_snapshot', snapshot=snapshot,
                                       speech='内存读取已返回棋盘快照；这不表示已经通过内存执行操作。'))
                return
            if self._factory:
                session = self._factory(self._record)
            elif mode == 'auto':
                from core.bg_auto import prepare_battleground
                from core.bg_live import LiveSession
                from core.bg_live_windows import HearthstoneWindow
                from core.bg_agent import load_config
                backend=HearthstoneWindow()
                ready=prepare_battleground(backend,load_config(),self._publish,
                                           self._stop,deadline)
                session=LiveSession(backend,ready['log_path'],on_event=self._record)
            else:
                from core.bg_live import LiveSession
                from core.bg_live_windows import HearthstoneWindow
                from core.log_reader import find_log_path
                path = find_log_path()
                if not path:
                    raise RuntimeError('未找到 Power.log；请先打开炉石并进入酒馆战棋')
                session = LiveSession(HearthstoneWindow(), path, on_event=self._record)
            self._session = session
            if self._stop.is_set():
                session.stop.set()
                return
            from core.bg_live import observed_phase
            previous_phase = 'unknown'
            initial_game = None
            attempts = 0
            auto_cut_speech = None
            while not self._stop.is_set() and time.monotonic() < deadline:
                session.reader.poll()
                game = getattr(session.reader.parser,'game_index',None)
                if initial_game is None:
                    initial_game = game
                elif game is not None and game != initial_game:
                    raise RuntimeError('日志已进入新对局，本次接管结束；请确认后重新启动')
                phase = observed_phase(session.reader.parser)
                with self._lock:
                    self._state['phase'] = phase
                if previous_phase == 'combat' and phase == 'recruit' and pending:
                    self._publish(dict(type='round_review', speech=review_text(pending,combat_finished=True)))
                    pending.clear()
                previous_phase = phase
                if mode == 'auto' and phase == 'combat':
                    # Automatic disconnects are scoped to an explicitly started
                    # full-auto session. Plugin/observe/step paths never enter.
                    try:
                        from core.log_reader import read_current_board
                        from core.netcut_budget import DisconnectBudget
                        from core.netcut_policy import auto_netcut_decision
                        board = read_current_board()
                        budget = DisconnectBudget()
                        budget_state = budget.status((board or {}).get('game_key',''))
                        combat_id = f"{game}:{board.get('turn','?')}:{len(board.get('theirs') or [])}"
                        should, reason = auto_netcut_decision(
                            board or {}, full_auto=True,
                            remaining=budget_state['remaining'],
                            cooldown_remaining=budget_state['cooldown_remaining'],
                            already_cut=combat_id in budget_state.get('combat_ids',[]))
                        if should:
                            cut = budget.cut((board or {}).get('game_key',''), combat_id)
                            if cut.get('ok'):
                                auto_cut_speech = f"全自动接管：{reason}；本局第 {cut['count']} 次，剩余 {cut['remaining']} 次。"
                                self._publish(dict(type='auto_netcut', reason=reason,
                                                   count=cut['count'], remaining=cut['remaining'],
                                                   speech=auto_cut_speech))
                    except Exception as exc:
                        self._publish(dict(type='auto_netcut_skipped',
                                           reason=str(exc)[:180],
                                           speech='全自动拔线判断未执行，继续按日志观察战斗。'))
                if mode == 'observe' or phase == 'combat' or attempts >= count:
                    if mode == 'step' and attempts >= count:
                        break
                    self._stop.wait(.5)
                    continue
                remaining = deadline-time.monotonic()
                if remaining < 1:
                    break
                # One execution at a time; phase and local cancellation checked between decisions.
                outcome = session.run(1, min(remaining,90))
                attempts += 1
                batch = outcome.get('records',[])
                records.extend(batch)
                pending.extend(batch)
                if not batch or any(not r.get('verified') for r in batch):
                    break  # Lobby clicks are unverified and never blindly repeated.
                if batch[-1]['action']['kind'] == 'FREEZE':
                    break
                self._stop.wait(.25)
            if pending or mode not in ('observe',):
                speech = review_text(pending or records)
                if auto_cut_speech:
                    speech = auto_cut_speech + ' ' + speech
                self._publish(dict(type='review', speech=speech, stopped=self._stop.is_set()))
        except Exception as exc:
            error = str(exc)[:240] if isinstance(exc,(RuntimeError,ValueError)) else '战棋后台读取或模型请求失败，已停止后续动作'
            self._publish(dict(type='paused', error=error, speech='战棋任务已暂停：'+error))
        finally:
            self._session = None
            with self._lock:
                self._state['running'] = False
            self._publish(dict(type='finished', stopped=self._stop.is_set()))
