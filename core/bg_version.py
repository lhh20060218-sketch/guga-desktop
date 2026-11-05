"""Fail closed when an offline engine and the live client use different patches."""
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
CLIENT_CARDS=ROOT/'data/bg_agent/cards_37.json'


def client_patch():
    data=json.loads(CLIENT_CARDS.read_text(encoding='utf-8'))
    patch=str(data.get('patch','')).strip()
    if not patch:raise ValueError('客户端卡牌快照缺少 patch')
    return patch


def engine_patch(engine_root):
    path=Path(engine_root)/'data/bg_summary.json'
    data=json.loads(path.read_text(encoding='utf-8'))
    patch=str(data.get('patch','')).strip()
    if not patch:raise ValueError('离线引擎 bg_summary.json 缺少 patch')
    return patch


def verify_same_patch(engine_root):
    live=client_patch();offline=engine_patch(engine_root)
    if live!=offline:
        raise ValueError(f'离线引擎版本 {offline} 与当前客户端 {live} 不一致；拒绝训练旧版本')
    return dict(patch=live,engine=str(Path(engine_root).resolve()))
