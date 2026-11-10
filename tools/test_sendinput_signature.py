# -*- coding: utf-8 -*-
"""回归：启动自检的 SendInput 签名不得污染派单键盘输入。

同一进程内先跑 env_check._sendinput_check()，再调 computer_control._send_keys([65])；
修复前第二次调用会抛
  ArgumentError: argument 2: TypeError: expected LP_INPUT instance instead of pointer to _INPUT
（现场：20261110q，14:30:55，豆包适配器第 1/2 步）。

单独执行：python tools/test_sendinput_signature.py
"""
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from core import computer_control, env_check  # noqa: E402


def main():
    check = env_check._sendinput_check()
    print('selfcheck_state=%s level=%s value=%r'
          % (check.get('state'), check.get('level'), check.get('value')))
    assert check.get('state') == 'pass', '自检 sendinput 未通过：%r' % check
    # 真实发一次 A 键（down+up）。修复后不抛错；按键会落到当前前台窗口。
    computer_control._send_keys([65])
    print('send_keys_ok=true keys=[65]')
    print('RESULT PASS')
    return 0


if __name__ == '__main__':
    sys.exit(main())
