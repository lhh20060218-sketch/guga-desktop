# -*- coding: utf-8 -*-
"""咕嘎企鹅·炉石战棋内存读取模块

通过 HearthMirror.dll 读取游戏进程内存, 获取战棋分数/玩家信息:
- get_my_rating():         自己的战棋分数(MMR), 即时可用
- get_lobby_info():         本局8人玩家列表(name/hero/account_id)
- get_hovered_entity_id(): 鼠标悬停的玩家实体ID(用于悬停查分)
- get_my_account_id():     自己的AccountId(用于在大厅中标记自己)

设计: 线程安全, DLL只加载一次, 所有方法可在后台线程调用不阻塞主线程
依赖: pythonnet(pip install pythonnet), lib/HearthMirror.dll 等
"""
import os
import threading
import logging
import json

_log = logging.getLogger(__name__)
_LIB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'lib')

_dll_lock = threading.Lock()
_dll_loaded = False
_refl_type = None
_refl = None
_load_error = None


def _ensure_loaded():
    global _dll_loaded, _refl_type, _refl, _load_error
    if _dll_loaded and _refl is not None:
        return True
    with _dll_lock:
        if _dll_loaded and _refl is not None:
            return True
        try:
            import pythonnet
            pythonnet.load("netfx")
        except Exception:
            pass
        try:
            import clr
            import System
            from System.Reflection import Assembly
            for d in ["Newtonsoft.Json.dll", "HearthDb.dll", "untapped-scry-dotnet.dll"]:
                clr.AddReference(os.path.join(_LIB_DIR, d))
            clr.AddReference(os.path.join(_LIB_DIR, "HearthMirror.dll"))
            asm = Assembly.LoadFrom(os.path.join(_LIB_DIR, "HearthMirror.dll"))
            all_types = []
            try:
                all_types = list(asm.GetTypes())
            except Exception as e:
                try:
                    for t in e.Types:
                        if t is not None:
                            all_types.append(t)
                except Exception:
                    pass
            for t in all_types:
                try:
                    if t.FullName == "HearthMirror.Reflection":
                        _refl_type = t
                        break
                except Exception:
                    continue
            if _refl_type is None:
                _load_error = "未找到 HearthMirror.Reflection 类型"
                return False
            _refl_type.GetMethod("StartIpcClient").Invoke(None, None)
            _refl = _refl_type.GetConstructor(System.Type.EmptyTypes).Invoke(None)
            _dll_loaded = True
            _load_error = None
            return True
        except Exception as e:
            _load_error = str(e)
            _log.error("加载 HearthMirror.dll 失败: %s", e)
            return False


def get_load_error():
    return _load_error


def get_my_rating():
    if not _ensure_loaded():
        return None
    try:
        ri = _refl_type.GetMethod("GetBattlegroundRatingInfo").Invoke(_refl, None)
        if ri is None:
            return None
        return int(ri.Rating)
    except Exception as e:
        _log.debug("get_my_rating 失败: %s", e)
        return None


def get_my_account_id():
    if not _ensure_loaded():
        return None
    try:
        aid = _refl_type.GetMethod("GetAccountId").Invoke(_refl, None)
        if aid is None:
            return None
        return (int(aid.Hi), int(aid.Lo))
    except Exception as e:
        _log.debug("get_my_account_id 失败: %s", e)
        return None


def get_lobby_info():
    if not _ensure_loaded():
        return None
    try:
        lobby = _refl_type.GetMethod("GetBattlegroundsLobbyInfo").Invoke(_refl, None)
        if lobby is None:
            return None
        players = lobby.Players
        my_aid = get_my_account_id()
        result = []
        for i in range(players.Count):
            p = players[i]
            name = str(p.Name) if p.Name else f"玩家{i+1}"
            hero = str(p.HeroCardId) if p.HeroCardId else "?"
            aid = None
            is_me = False
            try:
                a = p.AccountId
                aid = (int(a.Hi), int(a.Lo))
                if my_aid and aid[0] == my_aid[0] and aid[1] == my_aid[1]:
                    is_me = True
            except Exception:
                pass
            result.append({
                'name': name, 'hero': hero,
                'account_id': aid, 'is_me': is_me,
            })
        return result
    except Exception as e:
        _log.debug("get_lobby_info 失败: %s", e)
        return None


def get_hovered_entity_id():
    if not _ensure_loaded():
        return None
    try:
        result = _refl_type.GetMethod("GetBattlegroundsLeaderboardHoveredEntityId").Invoke(_refl, None)
        if result is None:
            return None
        try:
            val = int(result)
            return val if val > 0 else None
        except Exception:
            try:
                val = int(result.Value)
                return val if val > 0 else None
            except Exception:
                return None
    except Exception as e:
        _log.debug("get_hovered_entity_id 失败: %s", e)
        return None


_DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'rating_db.json')


def _load_db():
    try:
        with open(_DB_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {'games': [], 'players': {}}


def _save_db(db):
    try:
        os.makedirs(os.path.dirname(_DB_PATH), exist_ok=True)
        with open(_DB_PATH, 'w', encoding='utf-8') as f:
            json.dump(db, f, ensure_ascii=False, indent=2)
    except Exception as e:
        _log.error("保存分数数据库失败: %s", e)


def record_game(my_rating, players):
    db = _load_db()
    import time
    game = {
        'time': time.strftime('%Y-%m-%d %H:%M'),
        'my_rating': my_rating,
        'players': [{'name': p['name'], 'hero': p['hero'],
                      'aid': list(p['account_id']) if p['account_id'] else None}
                     for p in players],
    }
    db['games'].append(game)
    db['games'] = db['games'][-200:]
    for p in players:
        aid = p.get('account_id')
        if aid and not p['is_me']:
            key = f"{aid[0]}_{aid[1]}"
            db['players'][key] = {
                'name': p['name'],
                'last_met': game['time'],
                'my_rating_then': my_rating,
            }
    _save_db(db)


def lookup_player(account_id):
    if not account_id:
        return None
    db = _load_db()
    key = f"{account_id[0]}_{account_id[1]}"
    return db.get('players', {}).get(key)


if __name__ == '__main__':
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    print("=== 内存读取测试 ===")
    r = get_my_rating()
    print(f"我的战棋分数: {r}")
    print("\n=== 大厅信息 ===")
    lobby = get_lobby_info()
    if lobby:
        for i, p in enumerate(lobby):
            me = " (我)" if p['is_me'] else ""
            print(f"  {i+1}. {p['name']} | {p['hero']}{me}")
    else:
        print("  不在对局/无法读取")
    print("\n=== 悬停实体ID ===")
    hid = get_hovered_entity_id()
    print(f"  {hid}")
    print("\n=== 我的AccountId ===")
    aid = get_my_account_id()
    print(f"  {aid}")
