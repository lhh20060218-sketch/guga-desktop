# -*- coding: utf-8 -*-
"""咕嘎企鹅话术系统 — 企鹅语 + 人类语言混合，娇憨调皮风格

每条话术:
- text: 说的内容
- expression: 表情 (normal/happy/sleepy/surprised/sad/playful)
- action: 动作 (none/bounce/shake/point/peek/tsundere)
"""
import random


class SpeechLine:
    __slots__ = ('text', 'expression', 'action')

    def __init__(self, text: str, expression: str = "normal", action: str = "none"):
        self.text = text
        self.expression = expression
        self.action = action


# 咕嘎企鹅话术库 — 称呼"饲养员"或"两脚兽"，自称"本鹅"
SPEECHES = {
    "greeting": [
        SpeechLine("咕嘎…你来了啊，饲养员。", "normal", "none"),
        SpeechLine("咕嘎嘎～本鹅等你好久了，才不是特意等你的。", "happy", "bounce"),
        SpeechLine("哼，咕嘎～终于想起来看本鹅了？", "playful", "tsundere"),
        SpeechLine("咕嘎～看什么看，没见过这么帅的企鹅？", "playful", "bounce"),
        SpeechLine("咕…你又来打扰本鹅午睡了。", "sleepy", "none"),
    ],
    "click": [
        SpeechLine("咕嘎！别乱摸本鹅！", "surprised", "shake"),
        SpeechLine("咕嘎嘎～勉为其难让你摸一下。", "happy", "none"),
        SpeechLine("哼，咕～你手好凉。", "normal", "tsundere"),
        SpeechLine("咕嘎！本鹅警告你，别戳我肚子！", "surprised", "shake"),
        SpeechLine("咕嘎嘎～…再摸一会儿也可以。", "happy", "bounce"),
        SpeechLine("咕～你是真的很烦耶。", "playful", "peek"),
    ],
    "feed": [
        SpeechLine("咕嘎～磷虾！还行，算你识相。", "happy", "bounce"),
        SpeechLine("咕嘎嘎～本鹅勉为其难吃一点。", "happy", "none"),
        SpeechLine("咕？就这？本鹅要更好的。", "playful", "tsundere"),
        SpeechLine("咕嘎～下次要金枪鱼罐头，记住了。", "happy", "none"),
    ],
    "play": [
        SpeechLine("咕嘎！雪球？本鹅来了！", "surprised", "bounce"),
        SpeechLine("咕嘎嘎～别以为我胖就抓不到你。", "playful", "bounce"),
        SpeechLine("咕嘎～抓到了！看本鹅的滑步！", "happy", "bounce"),
        SpeechLine("咕嘎嘎～再玩一会儿，仅此一次。", "playful", "none"),
    ],
    "pet": [
        SpeechLine("咕噜咕噜…咕嘎～", "happy", "none"),
        SpeechLine("咕嘎嘎～…还行，不要停。", "happy", "none"),
        SpeechLine("咕噜咕噜…咕嘎～本鹅允许了。", "sleepy", "none"),
        SpeechLine("咕嘎～仅此一次，下不为例。", "normal", "tsundere"),
    ],
    "sleep": [
        SpeechLine("咕嘎～困了，别吵本鹅。", "sleepy", "none"),
        SpeechLine("呼噜呼噜…咕嘎～本鹅要睡了。", "sleepy", "none"),
        SpeechLine("咕嘎～帮我把灯关了。", "sleepy", "none"),
        SpeechLine("咕嘎嘎～谁也别想叫醒本鹅。", "sleepy", "none"),
    ],
    "hungry": [
        SpeechLine("咕…本鹅饿了，你看着办。", "sad", "none"),
        SpeechLine("咕嘎嘎～怎么还没开饭？", "sad", "none"),
        SpeechLine("咕嘎～本鹅命令你，立刻上菜。", "playful", "point"),
        SpeechLine("咕…再不喂本鹅，我就把你的鱼缸掀了。", "sad", "shake"),
    ],
    "sad": [
        SpeechLine("咕…你是不是有别的企鹅了？", "sad", "none"),
        SpeechLine("咕嘎嘎～你都多久没陪本鹅了。", "sad", "none"),
        SpeechLine("咕…本鹅很寂寞你懂吗？", "sad", "none"),
        SpeechLine("咕嘎～算了，反正你也不在意。", "sleepy", "none"),
    ],
    "surprised": [
        SpeechLine("咕嘎？！你吓到本鹅了！", "surprised", "shake"),
        SpeechLine("咕嘎嘎！怎么突然出现！", "surprised", "shake"),
        SpeechLine("咕嘎？！什么声音？！", "surprised", "shake"),
        SpeechLine("咕嘎嘎～你走路没声音的吗？", "surprised", "bounce"),
    ],
    "tease": [
        SpeechLine("咕嘎～你以为你能抓到本鹅？", "playful", "bounce"),
        SpeechLine("咕嘎嘎～本鹅才不告诉你我在想什么。", "playful", "peek"),
        SpeechLine("咕嘎～哼，你上当了。", "playful", "bounce"),
        SpeechLine("咕嘎嘎～本鹅的智商你无法理解。", "playful", "tsundere"),
    ],
    "bye": [
        SpeechLine("咕嘎～走了？记得早点回来喂本鹅。", "sleepy", "none"),
        SpeechLine("咕嘎嘎～别太久，本鹅会想…才怪。", "normal", "tsundere"),
        SpeechLine("咕嘎～路上小心，反正你也笨。", "playful", "none"),
        SpeechLine("咕嘎嘎～本鹅睡觉了，你随便。", "sleepy", "none"),
    ],
    "idle": [
        SpeechLine("咕嘎～你在忙什么呢，饲养员？", "normal", "none"),
        SpeechLine("咕嘎嘎～本鹅今天很无聊。", "playful", "none"),
        SpeechLine("咕嘎～这世界除了本鹅，还有谁可爱？", "playful", "none"),
        SpeechLine("咕嘎嘎～要不要本鹅允许你摸我？", "happy", "bounce"),
        SpeechLine("咕嘎～你看我干嘛？我都没看你。", "normal", "peek"),
        SpeechLine("咕嘎嘎～今天冰面不错，适合睡觉。", "sleepy", "none"),
        SpeechLine("咕嘎～本鹅命令你，别打游戏了，陪本鹅！", "playful", "point"),
        SpeechLine("咕嘎嘎～你存在的意义就是伺候本鹅。", "playful", "tsundere"),
        SpeechLine("咕嘎～听说你又去酒馆战棋连败了？", "playful", "peek"),
        SpeechLine("咕嘎嘎～本鹅可是战棋军师，要不要指点你一下？", "playful", "point"),
    ],
}


def get_speech(scene: str) -> SpeechLine:
    lines = SPEECHES.get(scene, SPEECHES["idle"])
    return random.choice(lines)


def get_random_speech() -> SpeechLine:
    all_lines = []
    for lines in SPEECHES.values():
        all_lines.extend(lines)
    return random.choice(all_lines)
