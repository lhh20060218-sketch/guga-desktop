"""Keep stage directions out of speech and map them to actual pet gestures."""
import re

ALIASES = {'摇头':'head_shake','摇摇头':'head_shake','点头':'nod','点点头':'nod',
           '歪头':'tilt','挥手':'wave','挥挥手':'wave','开心蹦':'bounce','蹦跳':'bounce',
           '抖动':'shake','指点':'point','偷看':'peek','傲娇摇头':'head_shake',
           'tsundere':'head_shake','戴墨镜':'sunglasses','摘墨镜':'remove_sunglasses',
           '跳舞':'dance','摇摆':'dance','晃动身体':'dance','停止跳舞':'stop_dance','暗中观察':'sneak_peek'}
ALIASES.update({'抬头回应':'look_up_step','打盹':'idle_doze','困倦打盹':'idle_doze','比心':'idle_heart','双手比心':'idle_heart'})
GESTURES = {'head_shake','nod','tilt','wave','bounce','shake','point','peek','none','sunglasses','remove_sunglasses','dance','stop_dance','sneak_peek','look_up_step','idle_doze','idle_heart'}
GESTURES.add('look_up_step')

def spoken_reply(text):
    text = str(text).strip()
    expression, action = 'normal', 'none'
    parts = [p.strip() for p in text.split('|',2)]
    if len(parts)==3 and (parts[1] in GESTURES or parts[1] in ALIASES):
        expression = parts[0] if parts[0] in {'normal','happy','sleepy','surprised','sad','playful'} else 'normal'
        action = ALIASES.get(parts[1],parts[1]); text = parts[2]
    # Only explicit stage directions; preserve normal statements such as “不要摇头”.
    pattern = r'(?:[（(【\[]\s*|\*\*?\s*)('+'|'.join(sorted(ALIASES,key=len,reverse=True))+r')(?:\s*[）)】\]]|\s*\*\*?)'
    def remove(match):
        nonlocal action
        if action=='none': action=ALIASES[match.group(1)]
        return ''
    text=re.sub(pattern,remove,text)
    return expression,action,text.strip()
