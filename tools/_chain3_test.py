# -*- coding: utf-8 -*-
"""3-step chain test: 豆包→WorkBuddy→JoyCode"""
import os, sys, json, time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
os.environ['GUGA_HOME'] = r'd:\rengongzhineng\guga-competition\dist\e2e-20261110ac-r21\home'
os.environ['GUGA_WORKSPACE'] = r'd:\rengongzhineng'

from core.adapter_chain import detect, run

PROMPT = '用豆包写一句"测试通过"，然后让WorkBuddy把这句话做成单页PPT，再让JoyCode写一个Python脚本打印这句话'

print('=== PARSE ===')
chain = detect(PROMPT)
for i, step in enumerate(chain['steps']):
    p = step['instruction']
    print('Step %d: app=%s(%s) inst=%d chars: %s...' % (i+1, step['name'], step['app_id'], len(p), p[:60]))
print('Total steps:', len(chain['steps']))
print()

print('=== RUN ===')
result = run(chain, timeout_seconds=900)
print()
print('=== RESULT ===')
print('ok:', result.get('ok'))
if result.get('ok'):
    print('text[:500]:', (result.get('text') or '')[:500])
else:
    print('code:', result.get('code'))
    print('detail[:300]:', (result.get('detail') or '')[:300])

# write evidence
home = os.environ['GUGA_HOME']
os.makedirs(os.path.join(home, 'evidence'), exist_ok=True)
with open(os.path.join(home, 'evidence', 'chain3_result.json'), 'w', encoding='utf-8') as f:
    json.dump(result, f, ensure_ascii=False, indent=2)
print()
print('evidence saved')
