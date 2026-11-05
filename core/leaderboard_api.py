# -*- coding: utf-8 -*-
"""咕嘎企鹅·国服炉石战旗排行榜查询模块

通过网易暴雪官网公开API拉取国服战旗排行榜:
- fetch_leaderboard(): 全量拉取当前赛季排行榜(约361人)
- lookup_score(battle_tag): 按战网昵称查分数
- get_cache(): 返回缓存的全量排行榜

API:
- 模式列表: https://webapi.blizzard.cn/hs-rank-api-server/api/v2/game/mode
- 排行榜:   https://webapi.blizzard.cn/hs-rank-api-server/api/game/ranks
  参数: page, page_size(<=25), mode_name=battlegrounds, season_id

设计: 后台线程拉取, 内存+JSON双缓存, 2小时过期
"""
import os
import json
import time
import threading
import logging
import urllib.request
import urllib.parse

_log = logging.getLogger(__name__)

_API_MODE = 'https://webapi.blizzard.cn/hs-rank-api-server/api/v2/game/mode'
_API_RANKS = 'https://webapi.blizzard.cn/hs-rank-api-server/api/game/ranks'
_HEADERS = {
    'User-Agent': 'Mozilla/5.0',
    'Referer': 'https://hs.blizzard.cn/community/leaderboards/index.html',
    'Accept': 'application/json, text/plain, */*',
}
_CACHE_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           'data', 'leaderboard_cache.json')
_CACHE_TTL = 7200  # 2小时过期(秒)

# 内存缓存
_cache_lock = threading.Lock()
_cache = None        # {'season': int, 'fetched_at': float, 'players': {name: score}, 'list': [...]}
_fetching = False    # 是否正在拉取


def _http_get(url, timeout=20):
    req = urllib.request.Request(url, headers=_HEADERS)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode('utf-8'))


def _get_season_id():
    """获取战旗最新赛季ID"""
    data = _http_get(_API_MODE)
    seasons = data.get('data', {}).get('season_map', {}).get('battlegrounds', [])
    if not seasons:
        return None
    return int(seasons[0]['season_id'])


def _fetch_all_pages(season_id):
    """分页拉取全部排行榜(每页25条), 返回 list[{position,battle_tag,score}]"""
    all_players = []
    page = 1
    while True:
        params = {'page': page, 'page_size': 25, 'mode_name': 'battlegrounds', 'season_id': season_id}
        url = _API_RANKS + '?' + urllib.parse.urlencode(params)
        data = _http_get(url)
        d = data.get('data', {})
        lst = d.get('list', [])
        if not lst:
            break
        all_players.extend(lst)
        total = int(d.get('total', 0))
        if page * 25 >= total:
            break
        page += 1
        if page > 30:  # 安全上限
            break
    return all_players


def fetch_leaderboard(force=False):
    """全量拉取排行榜, 更新内存+JSON缓存
    force=True 强制重新拉取
    返回: {'season': int, 'fetched_at': float, 'players': {name:score}, 'list': [...]} 或 None
    """
    global _cache, _fetching
    with _cache_lock:
        if _fetching:
            return _cache  # 已有线程在拉, 返回当前缓存
        _fetching = True
    try:
        # 检查缓存是否有效
        if not force and _cache and (time.time() - _cache.get('fetched_at', 0) < _CACHE_TTL):
            return _cache
        # 拉取
        season = _get_season_id()
        if season is None:
            _log.error("无法获取战旗赛季ID")
            return _cache
        players_list = _fetch_all_pages(season)
        players_map = {}
        for p in players_list:
            name = p.get('battle_tag', '').strip()
            score = int(p.get('score', 0))
            if name:
                players_map[name] = score
                # 也存去#后缀的版本(便于匹配)
                if '#' in name:
                    base = name.split('#')[0].strip()
                    players_map[base] = score
        new_cache = {
            'season': season,
            'fetched_at': time.time(),
            'players': players_map,
            'list': players_list,
            'total': len(players_list),
        }
        with _cache_lock:
            _cache = new_cache
        # 持久化
        try:
            os.makedirs(os.path.dirname(_CACHE_PATH), exist_ok=True)
            with open(_CACHE_PATH, 'w', encoding='utf-8') as f:
                json.dump(new_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            _log.error("保存排行榜缓存失败: %s", e)
        _log.info("排行榜拉取成功: 赛季=%s, %d人", season, len(players_list))
        return new_cache
    except Exception as e:
        _log.error("拉取排行榜失败: %s", e)
        return _cache
    finally:
        with _cache_lock:
            _fetching = False


def load_cache_from_disk():
    """从磁盘加载缓存(启动时调用)"""
    global _cache
    try:
        with open(_CACHE_PATH, 'r', encoding='utf-8') as f:
            _cache = json.load(f)
        _log.info("从磁盘加载排行榜缓存: %d人, 时间%s",
                  len(_cache.get('players', {})),
                  time.ctime(_cache.get('fetched_at', 0)))
        return _cache
    except Exception:
        return None


def get_cache():
    """返回当前缓存(可能为None)"""
    return _cache


def lookup_score(battle_tag):
    """按战网昵称查分数
    battle_tag: 玩家名(可能带#后缀, 如"彩虹丨涵雪#5746"或"彩虹丨涵雪")
    返回: int 分数 或 None(未上榜/缓存为空)
    """
    if not _cache:
        return None
    players = _cache.get('players', {})
    name = battle_tag.strip()
    # 1. 精确匹配
    if name in players:
        return players[name]
    # 2. 去#后缀匹配
    if '#' in name:
        base = name.split('#')[0].strip()
        if base in players:
            return players[base]
    # 3. 包含匹配(玩家名可能带公会前缀, 如"彩虹丨涵雪" vs "涵雪")
    for tag, score in players.items():
        if name and len(name) >= 3 and name in tag:
            return score
        if tag and len(tag) >= 3 and tag in name:
            return score
    return None


def fetch_in_background(callback=None):
    """后台线程拉取排行榜, 完成后调用 callback(cache) 或 callback(None)"""
    def _run():
        result = fetch_leaderboard()
        if callback:
            try:
                callback(result)
            except Exception:
                pass
    threading.Thread(target=_run, daemon=True).start()


if __name__ == '__main__':
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', line_buffering=True)
    print("=== 拉取国服战旗排行榜 ===")
    cache = fetch_leaderboard(force=True)
    if cache:
        print(f"赛季: {cache['season']}, 总人数: {cache['total']}")
        print("\nTop 10:")
        for p in cache['list'][:10]:
            print(f"  {p['position']}. {p['battle_tag']} - {p['score']}")
        print("\n=== 测试查分 ===")
        test_names = ['彩虹丨涵雪', '大嘟丨火车王', '不存在的玩家']
        for n in test_names:
            s = lookup_score(n)
            print(f"  {n}: {s}")
    else:
        print("拉取失败")
