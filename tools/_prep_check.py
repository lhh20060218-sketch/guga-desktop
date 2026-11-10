import json
d = json.load(open(r'D:\rengongzhineng\guga-competition\dist\e2e-20261110ac-r3\evidence\preflight.json', encoding='utf-8'))
for tag, entry in d.get('targets', {}).items():
    why = entry.get('why')
    print(f'{tag}: ok={entry.get("ok")} why={why}')
