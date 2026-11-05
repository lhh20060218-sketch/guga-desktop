"""Only visually reviewed, content-bound action bundles enter the live pet."""
import hashlib
import json
from pathlib import Path


def frames_digest(folder):
    digest = hashlib.sha256()
    files = sorted(list(Path(folder).glob('*.png')) + list(Path(folder).glob('*.webp')))
    if not files:
        raise ValueError('动作没有 PNG/WebP 帧')
    for path in files:
        digest.update(path.name.encode('utf-8'))
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


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
        return review.get('frames_sha256') == frames_digest(folder)
    except (OSError, ValueError, TypeError, AttributeError):
        return False
