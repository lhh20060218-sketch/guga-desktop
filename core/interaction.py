# -*- coding: utf-8 -*-
"""咕嘎企鹅互动动作定义 — 含战棋军师专属动作"""
from dataclasses import dataclass, field
from typing import List


@dataclass
class Action:
    name: str
    label: str
    icon: str
    hunger_delta: float = 0
    happy_delta: float = 0
    energy_delta: float = 0
    mood_result: str = '😊'
    messages: List[str] = field(default_factory=list)
    animation: str = 'happy'          # 表情
    gesture: str = 'none'             # 动作: none/bounce/shake/point/peek/tsundere


ACTIONS = {
    'feed': Action(
        name='feed', label='喂食', icon='🐟',
        hunger_delta=12, happy_delta=4, energy_delta=-2,
        mood_result='😊',
        messages=['咕嘎…还行吧。', '哼，勉强能吃。', '下次要磷虾！'],
        animation='happy', gesture='bounce',
    ),
    'play': Action(
        name='play', label='逗企鹅', icon='🪶',
        hunger_delta=-5, happy_delta=14, energy_delta=-8,
        mood_result='😄',
        messages=['咕嘎！本鹅要抓到你！', '别以为我胖就追不上你。', '哼，本鹅允许你陪我玩。'],
        animation='happy', gesture='bounce',
    ),
    'pet': Action(
        name='pet', label='摸摸', icon='✋',
        hunger_delta=0, happy_delta=8, energy_delta=-1,
        mood_result='🥰',
        messages=['咕噜咕噜…', '仅此一次。', '…不要停。'],
        animation='happy', gesture='none',
    ),
    'sleep': Action(
        name='sleep', label='打盹', icon='🌙',
        hunger_delta=-3, happy_delta=2, energy_delta=20,
        mood_result='😴',
        messages=['咕…困了。', '别吵我。', '呼噜呼噜…'],
        animation='sleepy', gesture='none',
    ),
    'dance': Action(
        name='dance', label='摇摆', icon='🐧',
        hunger_delta=-4, happy_delta=10, energy_delta=-6,
        mood_result='😄',
        messages=['咕嘎～摇起来。', '看本鹅的舞步。', '哼，优雅。'],
        animation='happy', gesture='bounce',
    ),
    # ---- 战棋军师专属动作 ----
    'advise': Action(
        name='advise', label='指点江山', icon='🗺️',
        hunger_delta=-2, happy_delta=6, energy_delta=-4,
        mood_result='😄',
        messages=['咕嘎！听本鹅军师的！', '这波听我的，稳赢。', '升！买！本鹅说了算！'],
        animation='playful', gesture='point',
    ),
    'peek': Action(
        name='peek', label='偷偷看我', icon='👀',
        hunger_delta=0, happy_delta=5, energy_delta=-1,
        mood_result='😊',
        messages=['咕…本鹅在偷看你。', '以为我没发现？', '哼，我才没有一直看你。'],
        animation='normal', gesture='peek',
    ),
    'tsundere': Action(
        name='tsundere', label='傲娇摇头', icon='😤',
        hunger_delta=0, happy_delta=5, energy_delta=0,
        mood_result='😕',
        messages=['哼，才不是担心你呢。', '本鹅才不需要你摸。', '哼！你爱玩不玩！'],
        animation='playful', gesture='tsundere',
    ),
    'see_board': Action(
        name='see_board', label='看我的棋盘', icon='🖥️',
        hunger_delta=0, happy_delta=8, energy_delta=-3,
        mood_result='😄',
        messages=['咕嘎～让本鹅看看你的烂摊子。', '截屏了，本鹅来当军师！'],
        animation='surprised', gesture='point',
    ),
    # ---- Python/大模型助教动作 ----
    'ask_tutor': Action(
        name='ask_tutor', label='请教助教', icon='📚',
        hunger_delta=0, happy_delta=5, energy_delta=-2,
        mood_result='😊',
        messages=['咕嘎～想问什么？本鹅耐心讲解～', '饲养员尽管问，本鹅在呢～'],
        animation='happy', gesture='point',
    ),
    'quiz_user': Action(
        name='quiz_user', label='助教出题', icon='❓',
        hunger_delta=0, happy_delta=6, energy_delta=-2,
        mood_result='😄',
        messages=['咕嘎～本鹅出题考考你！', '来来来，思考题时间～'],
        animation='playful', gesture='point',
    ),
}


def get_action(name: str) -> Action:
    return ACTIONS.get(name, ACTIONS['play'])
