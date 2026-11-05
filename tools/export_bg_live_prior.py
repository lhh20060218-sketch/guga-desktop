import hashlib,json
from pathlib import Path
import torch
root=Path(__file__).resolve().parents[1]
checkpoint=root/'runtime/bg-lab/champion-20261020/champion.pt'
raw=torch.load(checkpoint,map_location='cpu',weights_only=True)
expected={'schema':1,'profile':'hsrl2-rich-spell-position-v2','feature_dim':48}
if any(raw.get(k)!=v for k,v in expected.items()):raise ValueError('Unexpected checkpoint schema')
weights={k:v.detach().cpu().numpy().astype('float32').tolist() for k,v in raw['state_dict'].items() if k.startswith('actor')}
renamed={'w1':weights['actor.0.weight'],'b1':weights['actor.0.bias'],'w2':weights['actor.2.weight'],
         'b2':weights['actor.2.bias'],'w3':weights['actor.4.weight'],'b3':weights['actor.4.bias']}
engine=Path.home()/'Desktop/Vibe oding/output/guga-selfplay-lab-20261016/HSBRSIM'
engine_patch=json.loads((engine/'data/bg_summary.json').read_text(encoding='utf-8'))['patch']
document=dict(schema=1,source_checkpoint=str(checkpoint.relative_to(root)),checkpoint_sha256=hashlib.sha256(checkpoint.read_bytes()).hexdigest(),
 profile=raw['profile'],engine_revision=raw['engine_revision'],feature_dim=48,weights=renamed,
 training_patch=engine_patch,
 limitation='旧规则子集实验室冠军，仅作为实时候选排序先验；不是当前酒馆规则或天梯胜率')
target=root/'data/bg_agent/live_prior_20261020.json';target.write_text(json.dumps(document,separators=(',',':')),encoding='utf-8')
print(json.dumps(dict(path=str(target),bytes=target.stat().st_size,checkpoint_sha256=document['checkpoint_sha256'])))
