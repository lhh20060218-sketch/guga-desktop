"""Compare pinned client-card metadata with the old laboratory pool."""
import argparse
import json
from pathlib import Path


def _load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--old-data',required=True)
    p.add_argument('--current',required=True)
    p.add_argument('--output',required=True)
    args=p.parse_args()
    old_minions={c['id']:c for c in _load(Path(args.old_data)/'bg_pool_minions.json')}
    old_spells={c['id']:c for c in _load(Path(args.old_data)/'bg_pool_spells.json')}
    payload=_load(args.current);current=payload['cards']
    new_minions={k:v for k,v in current.items() if v.get('type')=='minion' and v.get('pool')}
    new_spells={k:v for k,v in current.items() if v.get('type')=='spell' and v.get('pool')}
    def changes(old,new):
        result=[]
        for cid in sorted(set(old)&set(new)):
            a,b=old[cid],new[cid]
            diff={}
            for old_key,new_key in (('atk','attack'),('health','health'),('tech_level','tier')):
                if a.get(old_key)!=b.get(new_key):diff[new_key]=dict(old=a.get(old_key),new=b.get(new_key))
            old_name=a.get('name');new_name=b.get('name_en') or b.get('name')
            if old_name and new_name and old_name!=new_name:diff['name']=dict(old=old_name,new=new_name)
            old_text=(a.get('text') or '').strip();new_text=(b.get('text_en') or b.get('text') or '').strip()
            if old_text and new_text and old_text!=new_text:diff['text']=dict(old=old_text[:500],new=new_text[:500])
            if diff:result.append(dict(id=cid,**diff))
        return result
    report=dict(schema=1,current_patch=payload.get('patch'),source_revision=payload.get('source_revision'),
                old_counts=dict(minions=len(old_minions),spells=len(old_spells)),
                current_counts=dict(minions=len(new_minions),spells=len(new_spells)),
                minions=dict(added=sorted(set(new_minions)-set(old_minions)),
                             removed=sorted(set(old_minions)-set(new_minions)),
                             changed=changes(old_minions,new_minions)),
                spells=dict(added=sorted(set(new_spells)-set(old_spells)),
                            removed=sorted(set(old_spells)-set(new_spells)),
                            changed=changes(old_spells,new_spells)),
                limitation='Client definitions differ from the executable 36.2.2 laboratory; do not replace scripts by ID alone')
    target=Path(args.output);target.parent.mkdir(parents=True,exist_ok=True)
    target.write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(dict(old=report['old_counts'],current=report['current_counts'],
               minion_added=len(report['minions']['added']),minion_removed=len(report['minions']['removed']),
               minion_changed=len(report['minions']['changed']),spell_added=len(report['spells']['added']),
               spell_removed=len(report['spells']['removed']),spell_changed=len(report['spells']['changed'])))

if __name__=='__main__':main()
