"""Continuous local ASR turns, gated while the agent/TTS is busy. No audio uploads."""
import json
import queue
import threading
import time

from PyQt5.QtCore import QObject, pyqtSignal


class AgentVoice(QObject):
    utterance = pyqtSignal(str)
    status = pyqtSignal(str)
    failed = pyqtSignal(str)
    finished = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.stopped = threading.Event()
        self.listening = threading.Event()
        self.thread = None

    def start(self):
        if self.thread and self.thread.is_alive():
            return
        self.stopped.clear()
        self.listening.set()
        self.thread = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def pause(self, paused=True):
        if paused:
            self.listening.clear()
        else:
            self.listening.set()

    def stop(self):
        self.stopped.set()
        self.listening.set()

    def _run(self):
        try:
            from core.asr import MODEL_DIR, _pick_input_device
            import sounddevice as sd
            import vosk
            import numpy as np
            from pathlib import Path
            if not Path(MODEL_DIR).is_dir():
                raise RuntimeError('缺少本地中文语音模型，请先完成原语音模块配置')
            self.status.emit('正在加载本地语音识别…')
            model = vosk.Model(MODEL_DIR)
            device = _pick_input_device()
            while not self.stopped.is_set():
                if not self.listening.wait(.1):
                    continue
                if self.stopped.is_set():
                    break
                audio = queue.Queue(maxsize=24)
                recognizer = vosk.KaldiRecognizer(model, 16000)

                def receive(data, frames, timing, status):
                    try:
                        audio.put_nowait(bytes(data))
                    except queue.Full:
                        pass

                with sd.RawInputStream(samplerate=16000, blocksize=4000, dtype='int16',
                                       channels=1, device=device, callback=receive):
                    self.status.emit('正在听 · 说完停顿即可发送')
                    started = time.monotonic()
                    while self.listening.is_set() and not self.stopped.is_set():
                        try:
                            data = audio.get(timeout=.2)
                        except queue.Empty:
                            continue
                        samples = np.frombuffer(data, dtype=np.int16).astype(np.float32)
                        peak = float(np.abs(samples).max()) if samples.size else 0
                        if peak > 0:
                            samples *= min(6.0, 7000 / peak)
                            data = np.clip(samples, -32767, 32767).astype(np.int16).tobytes()
                        ready = recognizer.AcceptWaveform(data)
                        if ready or time.monotonic() - started > 20:
                            result = recognizer.Result() if ready else recognizer.FinalResult()
                            text = json.loads(result).get('text', '').strip()
                            started = time.monotonic()
                            if text:
                                self.listening.clear()
                                self.utterance.emit(text)
                                break
        except Exception as exc:
            self.failed.emit('语音未启动：' + str(exc))
        finally:
            self.finished.emit()
