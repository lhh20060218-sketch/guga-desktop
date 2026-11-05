# -*- coding: utf-8 -*-
"""咕嘎企鹅视觉模块 — GLM-4.6V-Flash 识别屏幕/图片（看棋盘）

- screenshot(): 截取主屏幕 → base64 → 调用智谱视觉 API
- analyze_board(): 带结构化提示词分析酒馆战棋棋盘
- analyze_image_path(): 分析指定图片文件
配置：ai_config.json 的 zhipu_api_key / vision_model（默认 glm-4.6v-flash 免费版）
"""
import base64
import io
import json
import os
import threading
import time

import requests

_CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'ai_config.json')

VISION_PROMPT = """你是酒馆战棋视觉分析器。仔细看这张游戏截图，逐项提取并结构化输出。铁律：只报告画面中明确可见的信息，看不清或不在画面里的写'?'，绝不编造。
1. 画面判断：这是不是炉石传说酒馆战棋对局画面？如果不是（如主菜单/其他游戏/普通桌面），直接说明画面内容，其余项全部写'?'。
2. 对局信息：回合数、酒馆等级（1-6）、铸币（金币）、血量（数字看不清写'?'）。
3. 场上随从：逐个列出（名称/种族/身材攻血/是否金色/星级），看不清的写'?'。
4. 备战席随从：同样列出。
5. 饰品：已装备的饰品名称（如果有，看不清写'?'）。
6. 特殊机制：黑暗之赐效果、发动图标等可见标记。
7. 对手信息：其他可见的对手血量/阵容线索。
8. 其他观察：画面中任何对决策有用的信息。
用中文编号列表输出。

最后（最重要）输出一个 JSON 代码块用于战斗模拟，格式：
```json
{"minions": [{"name":"随从名","atk":攻击,"hp":生命,"taunt":false,"divine_shield":false,"windfury":false,"poison":false,"reborn":false}],
 "opponents": [{"name":"对手随从名","atk":..,"hp":..,"taunt":..,"divine_shield":..,"windfury":..,"poison":..,"reborn":..}]}
```
规则：minions=己方场上随从，opponents=对手场上随从（战斗阶段才可见，不可见给空数组 []）；每项只填画面明确可见的信息，看不清的属性填 0/false；随从数量不超过画面实际数量。"""


def _load_cfg():
    try:
        with open(_CONFIG_PATH, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}


def _call_vision(image_b64: str, prompt: str) -> str:
    cfg = _load_cfg()
    api_key = cfg.get('zhipu_api_key', '')
    if not api_key:
        return '❌ 未配置 zhipu_api_key（ai_config.json）'
    model = cfg.get('vision_model', 'glm-4.6v-flash')
    # 429 限流退避重试（免费版并发限制）
    last_err = ''
    for attempt in range(4):
        try:
            resp = requests.post(
                'https://open.bigmodel.cn/api/paas/v4/chat/completions',
                headers={
                    'Content-Type': 'application/json',
                    'Authorization': f'Bearer {api_key}',
                },
                json={
                    'model': model,
                    'temperature': 0.3,
                    'thinking': {'type': 'disabled'},
                    'messages': [{
                        'role': 'user',
                        'content': [
                            {'type': 'image_url', 'image_url': {'url': image_b64}},
                            {'type': 'text', 'text': prompt},
                        ],
                    }],
                },
                timeout=60,
            )
            data = resp.json()
            if resp.status_code == 429:
                last_err = '429 限流'
                time.sleep(2 * (attempt + 1))
                continue
            if resp.status_code != 200:
                err = data.get('error', {}).get('message', str(resp.status_code))
                return f'❌ 视觉API {resp.status_code}: {err}'
            content = (data.get('choices') or [{}])[0].get('message', {}).get('content', '')
            return content or '❌ 视觉API返回空'
        except requests.exceptions.ConnectionError:
            last_err = '网络连接失败'
            time.sleep(2 * (attempt + 1))
        except Exception as e:
            last_err = str(e)
            break
    return f'❌ 视觉API多次失败（{last_err}），稍后重试'


def _find_game_window():
    """找炉石传说窗口（标题含 Hearthstone/炉石），返回 (left, top, right, bottom)，找不到返回 None"""
    try:
        import win32gui

        def cb(hwnd, results):
            if win32gui.IsWindowVisible(hwnd):
                try:
                    title = win32gui.GetWindowText(hwnd)
                    if 'hearthstone' in title.lower() or '炉石' in title:
                        rect = win32gui.GetWindowRect(hwnd)
                        if rect[2] - rect[0] > 200 and rect[3] - rect[1] > 200:
                            results.append(rect)
                except Exception:
                    pass
            return True

        results = []
        win32gui.EnumWindows(cb, results)
        return results[0] if results else None
    except Exception:
        return None


def screenshot_to_b64(max_side: int = 1024) -> str:
    """截取炉石窗口（找不到则全屏），缩放到 max_side，返回 data URI"""
    from PIL import ImageGrab
    rect = _find_game_window()
    img = ImageGrab.grab(bbox=rect) if rect else ImageGrab.grab()
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=72)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()


def image_path_to_b64(path: str, max_side: int = 1024) -> str:
    from PIL import Image
    img = Image.open(path).convert('RGB')
    w, h = img.size
    scale = min(1.0, max_side / max(w, h))
    if scale < 1.0:
        img = img.resize((int(w * scale), int(h * scale)))
    buf = io.BytesIO()
    img.save(buf, format='JPEG', quality=72)
    return 'data:image/jpeg;base64,' + base64.b64encode(buf.getvalue()).decode()


def analyze_board_screenshot(prompt: str = None) -> str:
    """截屏并分析棋盘（同步调用，放后台线程执行）"""
    try:
        b64 = screenshot_to_b64()
    except Exception as e:
        return f'❌ 截屏失败: {e}'
    return _call_vision(b64, prompt or VISION_PROMPT)


def analyze_board_image(path: str, prompt: str = None) -> str:
    """分析指定图片文件中的棋盘"""
    try:
        b64 = image_path_to_b64(path)
    except Exception as e:
        return f'❌ 图片读取失败: {e}'
    return _call_vision(b64, prompt or VISION_PROMPT)


def analyze_screen_tutor(prompt: str = None) -> str:
    # 助教模式: 截屏并分析屏幕上的 Python/大模型相关内容。
    # 复用 _call_vision + screenshot_to_b64, 不影响战棋 analyze_board_* 函数。
    from core.tutor import SCREEN_TUTOR_PROMPT
    try:
        b64 = screenshot_to_b64()
    except Exception as e:
        return f'屏幕看不清: {e}'
    return _call_vision(b64, prompt or SCREEN_TUTOR_PROMPT)



BG_RATING_PROMPT = """看这张炉石传说酒馆战棋的游戏截图，重点识别画面上的战棋分数(MMR/Rating)信息。

酒馆战棋对局中，画面通常会显示8个玩家的列表，每个玩家包含：
- 玩家昵称（可能含中文/英文/数字）
- 使用的英雄
- 当前战棋分数（MMR，通常是一个4位数，如 5230、8100）

请按以下格式提取，只报告画面明确可见的信息，看不清的写"?"：

【画面判断】这是不是酒馆战棋对局画面？如果不是，说明画面内容。
【8人分数】逐个列出可见的玩家及其分数，格式：
  1. 昵称 | 英雄 | 分数
  2. 昵称 | 英雄 | 分数
  ...（看不清的字段写"?"）
【分数排名】从高到低列出玩家昵称和分数。
【总结】用一句话概括本局对手强弱（如"本局平均分8000，高手局"或"本局分数参差"）。

注意：
- 分数通常显示在玩家头像旁边，可能是4位数（如5230）或带千分位（如5,230）
- 如果是招募阶段，8人列表通常在画面侧边；战斗阶段可能只看到对手
- 看不清的玩家也要列出，分数写"?"
- 不要编造不存在的分数，只报告画面明确可见的数字"""


def analyze_bg_ratings(prompt: str = None) -> str:
    """截屏识别酒馆战棋对局中8个玩家的战棋分数(MMR)。
    用 GLM-4.6V 视觉模型分析游戏 UI, 零封号风险(不读内存)。
    """
    try:
        b64 = screenshot_to_b64()
    except Exception as e:
        return f'屏幕看不清: {e}'
    return _call_vision(b64, prompt or BG_RATING_PROMPT)

def analyze_in_thread(path_or_none, result_cb, prompt: str = None):
    """后台线程执行视觉分析，result_cb(text) 回调"""
    def _run():
        try:
            text = analyze_board_image(path_or_none, prompt) if path_or_none else analyze_board_screenshot(prompt)
        except Exception as e:
            text = f'❌ 视觉分析异常: {e}'
        result_cb(text)
    threading.Thread(target=_run, daemon=True).start()
