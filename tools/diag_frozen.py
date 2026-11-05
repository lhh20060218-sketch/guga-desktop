# -*- coding: utf-8 -*-
"""frozen 环境诊断（console onefile, 只打印不启动 GUI）"""
import os
import sys

print('python:', sys.version.split()[0])
print('frozen:', getattr(sys, 'frozen', False))
print('MEIPASS:', getattr(sys, '_MEIPASS', '(none)'))

try:
    import core.butler_cloud as bc
    print('[1] butler_cloud import OK')
    print('    __file__:', bc.__file__)
    cfg = bc.load_cloud_cfg()
    print('[2] load_cloud_cfg:', 'OK keys=' + str(sorted(cfg)) if cfg else 'None')
except Exception as e:
    print('[1/2] FAIL:', e)

try:
    import guga_agent as ga
    print('[3] guga_agent import OK  BASE=%s  HERE=%s' % (ga.BASE, ga.HERE))
    print('    api=None?', hasattr(ga, 'api'), ' pair?', hasattr(ga, 'pair'),
          ' run_job?', hasattr(ga, 'run_job'))
except Exception as e:
    print('[3] guga_agent FAIL:', type(e).__name__, str(e)[:150])

try:
    import guga_executor as dex
    print('[4] guga_executor import OK  EXEC_VERSION=%s' % dex.EXEC_VERSION)
except Exception as e:
    print('[4] guga_executor FAIL:', type(e).__name__, str(e)[:150])

try:
    import guga_selfcheck as sc
    chk = sc.run_check()
    print('[5] selfcheck OK, AI软件:', chk.get('ai'))
except Exception as e:
    print('[5] selfcheck FAIL:', type(e).__name__, str(e)[:150])

try:
    from ui.comp_window import CompWindow
    print('[6] comp_window import OK')
except Exception as e:
    print('[6] comp_window FAIL:', type(e).__name__, str(e)[:150])

print('=== 诊断结束 ===')
os.system('pause') if os.name == 'nt' else None
