"""Only visually reviewed, content-bound action bundles enter the live pet."""
import hashlib
import json
import os
from pathlib import Path

from core import guga_paths


_CACHE_FILE = guga_paths.RUNTIME / 'avatar-approval-cache.json'
_MEM = {}
_ALPHA_MEM = {}


def _frame_files(folder):
    """一次 scandir 取代两次 glob（每段省一次目录遍历；16 段累计约几十 ms）."""
    folder = Path(folder)
    pngs, webps = [], []
    try:
        with os.scandir(folder) as entries:
            for entry in entries:
                name = entry.name.lower()
                if name.endswith('.png'):
                    pngs.append(entry.name)
                elif name.endswith('.webp'):
                    webps.append(entry.name)
    except OSError:
        return []
    pngs.sort()
    webps.sort()
    return [folder / name for name in pngs] + [folder / name for name in webps]


def _folder_signature(files):
    """廉价指纹: 文件名+大小+mtime_ns。内容一变签名就变, 无需重读 58MB 帧."""
    parts = []
    for path in files:
        st = path.stat()
        parts.append('%s:%d:%d' % (path.name, st.st_size, st.st_mtime_ns))
    return hashlib.sha256('|'.join(parts).encode('utf-8'))


def _load_cache():
    try:
        data = json.loads(_CACHE_FILE.read_text(encoding='utf-8'))
        if isinstance(data, dict):
            return data
    except (OSError, ValueError, TypeError):
        pass
    return {}


def _save_cache(data):
    try:
        _CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        tmp = _CACHE_FILE.with_name(_CACHE_FILE.name + '.tmp')
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        os.replace(tmp, _CACHE_FILE)
    except OSError:
        pass


def frames_digest(folder):
    digest = hashlib.sha256()
    files = _frame_files(folder)
    if not files:
        raise ValueError('动作没有 PNG/WebP 帧')
    for path in files:
        digest.update(path.name.encode('utf-8'))
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def _frames_digest_cached(folder):
    """2026-11-06: 首屏校验从 205ms 降到 ~5ms.

    旧实现每次启动对 2000+ 帧重做 SHA256(58.6MB); 现在先算 文件名/大小/mtime
    指纹, 命中则复用上次内容摘要. 帧内容/文件集一变指纹就失效, 会重新全量校验.
    """
    folder = Path(folder)
    files = _frame_files(folder)
    if not files:
        raise ValueError('动作没有 PNG/WebP 帧')
    key = str(folder.resolve())
    sig = _folder_signature(files).hexdigest()
    hit = _MEM.get(key)
    if hit and hit.get('sig') == sig:
        return hit['digest']
    cache = _load_cache()
    hit = cache.get(key)
    if isinstance(hit, dict) and hit.get('sig') == sig and hit.get('digest'):
        _MEM[key] = hit
        return hit['digest']
    digest = frames_digest(folder)
    entry = {'sig': sig, 'digest': digest}
    _MEM[key] = entry
    cache[key] = entry
    _save_cache(cache)
    return digest


def _alpha_sample_ok(folder):
    """抽样首/中/末帧: 有整块不透明/半透明底就拒绝.

    2026-11-07 事故: task-motion 六段旧素材 alpha 全 255（整幅实底），
    切到这些片段时角色外面套着一块不透明矩形。判据用“最外 2px 边框”:
    抠干净的素材边框基本全透明（实测各段 <1%），没抠底的边框整圈不透明
    （实测 100%）；半透明灰底也会让边框均值过阈值。只看三帧，按文件签名
    缓存，命中后启动零开销。
    """
    from PIL import Image, ImageStat

    files = _frame_files(folder)
    if not files:
        return False
    for path in (files[0], files[len(files) // 2], files[-1]):
        try:
            with Image.open(path) as image:
                alpha = image.convert('RGBA').getchannel('A')
        except (OSError, ValueError):
            return False
        width, height = alpha.size
        if max(alpha.getpixel((0, 0)), alpha.getpixel((width - 1, 0)),
               alpha.getpixel((0, height - 1)), alpha.getpixel((width - 1, height - 1))) >= 200:
            return False
        ring = max(ImageStat.Stat(band).mean[0] for band in (
            alpha.crop((0, 0, width, 2)), alpha.crop((0, height - 2, width, height)),
            alpha.crop((0, 0, 2, height)), alpha.crop((width - 2, 0, width, height))))
        if ring > 128:
            return False
    return True


def _alpha_approved(folder):
    folder = Path(folder)
    files = _frame_files(folder)
    if not files:
        return False
    key = str(folder.resolve())
    sig = _folder_signature(files).hexdigest()
    hit = _ALPHA_MEM.get(key)
    if hit and hit.get('sig') == sig:
        return hit['ok']
    cached = _load_cache().get(key + '#alpha2')
    if isinstance(cached, dict) and cached.get('sig') == sig:
        _ALPHA_MEM[key] = cached
        return cached['ok']
    ok = _alpha_sample_ok(folder)
    entry = {'sig': sig, 'ok': ok}
    _ALPHA_MEM[key] = entry
    cache = _load_cache()
    cache[key + '#alpha2'] = entry
    _save_cache(cache)
    return ok


def approved_action(folder):
    """A file-count test or an installed flag is never visual approval."""
    folder = Path(folder)
    try:
        review = json.loads((folder.parent/'visual-review.json').read_text(encoding='utf-8'))
        if review.get('status') != 'approved' or not str(review.get('reviewer', '')).strip():
            return False
        checks = review.get('checks', {})
        if not all(checks.get(key) is True for key in ('continuous_motion', 'no_ghosts', 'anatomy')):
            return False
        # The user may accept an explicitly shown appearance variation. Preserve
        # that decision without falsely labelling different proportions exact.
        accepted = review.get('user_approval', {})
        user_accepted = accepted.get('by') == 'user' and bool(str(accepted.get('quote', '')).strip())
        if checks.get('identity') is not True and not (user_accepted and checks.get('identity_variation_accepted') is True):
            return False
        if review.get('playback') == 'once':
            if checks.get('entry_exit_transition') is not True and not (user_accepted and checks.get('transition_variation_accepted') is True):
                return False
        elif checks.get('loop_seam') is not True:
            return False
        if not _alpha_approved(folder):
            return False
        return review.get('frames_sha256') == _frames_digest_cached(folder)
    except (OSError, ValueError, TypeError, AttributeError):
        return False
