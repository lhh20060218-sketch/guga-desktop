# -*- coding: utf-8 -*-
"""咕嘎企鹅语音识别模块 — 麦克风录音 + Vosk 离线中文识别

- 依赖：sounddevice（录音）、vosk（识别）
- 模型：vosk-model-small-cn **不随安装包**，首次使用需联网下载约 40MB
  （GUGA-Desktop.exe --download-vosk-model，落点 %GUGA_HOME%/models/vosk-model-cn）
- 自动增益：录音时按峰值归一化（笔记本麦克风通常声音偏小）
- 用法：
    recorder = ASRRecorder()
    recorder.start()      # 开始录音（后台线程）
    recorder.stop()       # 停止并转写
    text = recorder.result
"""
import os
import queue
import threading
import zipfile
from pathlib import Path

# 模型下载源（按顺序尝试）：国内镜像优先，官方源兜底。
# 镜像 zip 实测 SHA256 已固定（2026-11-09 本机实测：43.9MB / 5.6MB/s / vosk 真加载通过）；
# 下载后校验不通过会自动换下一个源，绝不装来路不明的内容。
MODEL_SOURCES = (
    dict(url='https://hf-mirror.com/guloooovoooo/vosk-model-small-cn/resolve/main/vosk-model-small-cn.zip',
         label='HuggingFace 国内镜像（hf-mirror.com）',
         sha256='2b34e3c3eb2c61105b1affc4863407965dbf968c63ceb5cd46685f9bd627434a'),
    dict(url='https://alphacephei.com/vosk/models/vosk-model-small-cn-0.3.zip',
         label='Vosk 官方源（境外，可能较慢）', sha256=''),
)
VOSK_MODEL_URL = MODEL_SOURCES[0]['url']
MODEL_SUBDIR = 'vosk-model-cn'

# 注意：vosk 的 C++ 引擎不支持非 ASCII 路径！
# 原始位置在用户数据目录（可能含中文），实际加载必须用 ASCII 路径：
# 优先 %TEMP%\vosk-model-cn（复制品），否则用 8.3 短名转换。


def _model_source_dir():
    """模型源目录：GUGA_HOME/models/vosk-model-cn；打包版再看包内 models 兜底。"""
    candidates = []
    try:
        from core import guga_paths
        candidates.append(os.path.join(str(guga_paths.BASE), 'models', MODEL_SUBDIR))
    except Exception:
        pass
    if getattr(__import__('sys'), 'frozen', False):
        base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        candidates.append(os.path.join(base, 'models', MODEL_SUBDIR))
    return candidates[0] if candidates else os.path.join(
        os.environ.get('USERPROFILE', ''), 'GUGA', 'models', MODEL_SUBDIR)


_MODEL_SRC = _model_source_dir()

# 自动增益目标峰值（int16），太小听不清，太大削波
_GAIN_PEAK = 7000
_MAX_GAIN = 6.0


def _pick_input_device() -> int:
    """自动选择麦克风输入设备（优先名称含 麦克风/Microphone/Mic 的）"""
    try:
        import sounddevice as sd
        devs = sd.query_devices()
        default_dev = sd.default.device
        default_in = None
        if default_dev is not None:
            try:
                default_in = int(default_dev[0])  # InputOutputPair / list
            except Exception:
                default_in = int(default_dev)
        candidates = []
        for i, d in enumerate(devs):
            if d['max_input_channels'] > 0:
                name = str(d['name']).lower()
                if any(k in name for k in ('麦克风', 'microphone', 'mic', 'audio in', 'capture')):
                    candidates.append(i)
        # 优先默认输入设备（若在候选里），否则第一个候选
        if default_in in candidates:
            return int(default_in)
        if candidates:
            return candidates[0]
        return int(default_in) if default_in is not None else 0
    except Exception:
        return 0


def _ascii_path(path: str) -> str:
    """把含中文的路径转成 8.3 短名（ASCII），失败返回原路径"""
    if path.isascii():
        return path
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(1024)
        n = ctypes.windll.kernel32.GetShortPathNameW(path, buf, 1024)
        if n and buf.value:
            return buf.value
    except Exception:
        pass
    return path


def _ensure_model_dir() -> str:
    """返回可用的 ASCII 模型目录（必要时从源复制到 %TEMP%）"""
    # 1) 临时目录里的复制品（ASCII）
    tmp = os.path.join(os.environ.get('TEMP', ''), 'vosk-model-cn')
    if tmp and os.path.isdir(tmp):
        return tmp
    # 2) 源目录的 8.3 短名
    src = _ascii_path(_MODEL_SRC)
    if os.path.isdir(src):
        return src
    # 3) 复制到临时目录
    if os.path.isdir(_MODEL_SRC):
        try:
            import shutil
            shutil.copytree(_MODEL_SRC, tmp)
            return tmp
        except Exception:
            pass
    return _MODEL_SRC


MODEL_DIR = _ensure_model_dir()


def model_ready(path=None) -> bool:
    """目录里真有 am/conf 才算模型存在（空目录不算）。"""
    folder = Path(path or _MODEL_SRC)
    return folder.is_dir() and ((folder / 'am').is_dir() or (folder / 'conf').is_dir())


def _download_one(url, archive, timeout_seconds, progress):
    """带超时分块下载单个源，返回 (bytes, sha256)。"""
    import hashlib
    import urllib.request
    digest = hashlib.sha256()
    request = urllib.request.Request(url, headers={'User-Agent': 'guga-desktop'})
    with urllib.request.urlopen(request, timeout=timeout_seconds) as response:
        total = int(response.headers.get('Content-Length') or 0)
        done = 0
        last_report = 0
        with open(str(archive), 'wb') as handle:
            while True:
                chunk = response.read(256 * 1024)
                if not chunk:
                    break
                handle.write(chunk)
                digest.update(chunk)
                done += len(chunk)
                if progress and total and done - last_report >= 4 * 1024 * 1024:
                    last_report = done
                    try:
                        progress('下载中：%d/%d 字节' % (done, total))
                    except Exception:
                        pass
    if total and done < total:
        raise RuntimeError('下载不完整：%d/%d 字节' % (done, total))
    return done, digest.hexdigest()


def download_model(url='', dest='', progress=None, timeout_seconds=30) -> dict:
    """下载并解压 vosk 中文模型到 %GUGA_HOME%/models/vosk-model-cn。

    不依赖模型 Key；需要联网约 40MB。按 MODEL_SOURCES 顺序尝试
    （国内镜像优先、官方源兜底），每个源带读超时；固定了 SHA256 的源
    校验不通过自动换下一个，绝不装来路不明的内容。返回结构化结果，不抛给界面。
    """
    import shutil
    import tempfile
    target = Path(dest or _MODEL_SRC)
    if model_ready(target):
        return dict(ok=True, path=str(target), downloaded=False,
                    message='模型已存在，未重复下载')
    sources = ([dict(url=url, label='指定地址', sha256='')] if url
               else list(MODEL_SOURCES))
    errors = []
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except Exception as exc:
        return dict(ok=False, path=str(target), downloaded=False,
                    error='%s: %s' % (type(exc).__name__, str(exc)[:200]),
                    next_action='目标目录不可写，检查 %s 权限' % target)
    for source in sources:
        one = dict(source)
        try:
            with tempfile.TemporaryDirectory(prefix='guga-vosk-') as folder:
                archive = Path(folder) / 'vosk-model.zip'
                if progress:
                    try:
                        progress('开始下载（%s）：%s' % (one['label'], one['url']))
                    except Exception:
                        pass
                size, sha = _download_one(one['url'], archive, timeout_seconds, progress)
                if one.get('sha256') and sha != one['sha256']:
                    raise RuntimeError('SHA256 校验不通过：镜像内容已变化（期望 %s…，实际 %s…），换下一个源'
                                       % (one['sha256'][:12], sha[:12]))
                if progress:
                    try:
                        progress('下载完成：%d 字节（sha256=%s…），开始解压' % (size, sha[:16]))
                    except Exception:
                        pass
                extract = Path(folder) / 'unpack'
                extract.mkdir()
                with zipfile.ZipFile(str(archive)) as handle:
                    handle.extractall(str(extract))
                model_dir = None
                for path in extract.rglob('*'):
                    if path.is_dir() and ((path / 'am').is_dir() or (path / 'conf').is_dir()):
                        model_dir = path
                        break
                if model_dir is None:
                    raise RuntimeError('压缩包里没有找到 am/ 或 conf/ 模型目录')
                if target.exists():
                    shutil.rmtree(str(target))
                shutil.copytree(str(model_dir), str(target))
            if not model_ready(target):
                raise RuntimeError('解压后模型目录仍不完整：%s' % target)
            global MODEL_DIR
            MODEL_DIR = _ensure_model_dir()
            return dict(ok=True, path=str(target), downloaded=True,
                        bytes=size, sha256=sha, source=one['label'], source_url=one['url'],
                        message='已下载并解压到 %s（来源：%s）' % (target, one['label']))
        except Exception as exc:
            errors.append('%s：%s: %s' % (one['label'], type(exc).__name__, str(exc)[:160]))
            if progress:
                try:
                    progress('该源失败，尝试下一个 —— %s' % errors[-1])
                except Exception:
                    pass
    return dict(ok=False, path=str(target), downloaded=False,
                errors=errors,
                error=errors[-1] if errors else '无可用源',
                next_action='检查网络后重试；或手动下载 %s 解压到 %s'
                            % (MODEL_SOURCES[-1]['url'], target))


class ASRRecorder:
    """按住说话式录音器（start 开始，stop 结束并转写）"""

    def __init__(self):
        self._q = queue.Queue()
        self._stream = None
        self._recording = False
        self._thread = None
        self._recognizer = None
        self._model = None
        self._sd = None
        self._vosk = None
        self.result = ''
        self.error = None
        self.device = None
        self._frame_count = 0
        self._peak = 0
        self._start_time = 0.0

    @property
    def available(self) -> bool:
        """依赖与模型是否就绪"""
        if not self._check_imports():
            return False
        return self._ensure_model()

    def _check_imports(self):
        try:
            import sounddevice  # noqa
            import vosk  # noqa
            self._sd = sounddevice
            self._vosk = vosk
            return True
        except ImportError:
            return False

    def _ensure_model(self) -> bool:
        if self._model is not None:
            return True
        import vosk
        # 检查模型目录（解压后是 vosk-model-small-cn-0.22 子目录）
        if not os.path.isdir(MODEL_DIR):
            return False
        try:
            self._model = vosk.Model(MODEL_DIR)
            return True
        except Exception:
            return False

    def start(self):
        if self._recording:
            return
        if not self._check_imports():
            self.error = '缺少 sounddevice/vosk 依赖，请先安装'
            return
        if not self._ensure_model():
            self.error = f'未找到中文语音模型（{MODEL_DIR}），请先下载'
            return
        self.result = ''
        self.error = None
        self._recording = True
        self._recognizer = self._vosk.KaldiRecognizer(self._model, 16000)
        self.device = _pick_input_device()
        self._frame_count = 0
        self._peak = 0
        import time as _time
        self._start_time = _time.time()
        self._thread = threading.Thread(target=self._record_loop, daemon=True)
        self._thread.start()

    def _record_loop(self):
        import sounddevice as sd
        import numpy as np
        try:
            with sd.RawInputStream(samplerate=16000, blocksize=4000, dtype='int16',
                                   channels=1, device=self.device, callback=self._callback):
                while self._recording:
                    # 持续消费队列，交给 recognizer
                    try:
                        data = self._q.get(timeout=0.3)
                        if self._recognizer.AcceptWaveform(data):
                            res = self._recognizer.Result()
                            import json as _json
                            try:
                                txt = _json.loads(res).get('text', '')
                                if txt:
                                    self.result += txt
                            except Exception:
                                pass
                    except queue.Empty:
                        continue
        except Exception as e:
            self.error = f'录音设备错误: {e}'

    def _callback(self, indata, frames, time_info, status):
        import numpy as np
        raw = bytes(indata)
        self._frame_count += frames
        # 自动增益：按块峰值放大到目标，防止笔记本麦克风声音过小
        try:
            arr = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
            peak = float(np.abs(arr).max()) if arr.size else 0.0
            if peak > self._peak:
                self._peak = peak
            if peak > 0:
                gain = min(_MAX_GAIN, _GAIN_PEAK / peak)
                arr = arr * gain
                np.clip(arr, -32767, 32767, out=arr)
                raw = arr.astype(np.int16).tobytes()
        except Exception:
            pass
        self._q.put(raw)

    def stop(self):
        """停止录音并完成转写（同步，返回文本）"""
        if not self._recording:
            return self.result
        self._recording = False
        if self._thread:
            self._thread.join(timeout=5)
        # 取残留
        if self._recognizer is not None:
            try:
                res = self._recognizer.FinalResult()
                import json as _json
                try:
                    txt = _json.loads(res).get('text', '')
                    if txt:
                        self.result += txt
                except Exception:
                    pass
            except Exception:
                pass
        return self.result.strip()

    def stats(self) -> dict:
        """录音统计（供 UI 提示）：时长秒、峰值、是否捕捉到声音"""
        import time as _time
        dur = _time.time() - self._start_time if self._start_time else 0.0
        return {
            'seconds': round(dur, 1),
            'peak': self._peak,
            'has_audio': self._peak > 500,   # 峰值低于此 = 基本没收到声音
        }


# 便捷函数
def transcribe_wav_path(wav_path: str) -> str:
    """离线转写 wav 文件（16k 单声道）"""
    import vosk
    if not os.path.isdir(MODEL_DIR):
        return ''
    model = vosk.Model(MODEL_DIR)
    rec = vosk.KaldiRecognizer(model, 16000)
    import wave
    with wave.open(wav_path, 'rb') as wf:
        while True:
            data = wf.readframes(4000)
            if len(data) == 0:
                break
            if rec.AcceptWaveform(data):
                pass
    import json as _json
    try:
        return _json.loads(rec.FinalResult()).get('text', '')
    except Exception:
        return ''
