"""Fetch a pinned HearthSim extraction, retain raw XML and export BG definitions.

This is client card data, not Blizzard's server-side pool or executable rules.
"""
import argparse
import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
import xml.etree.ElementTree as ET
import requests


def extract(path):
    cards=[]
    wanted={'ATK':'atk','HEALTH':'health','COST':'cost','TECH_LEVEL':'tech_level',
            'CARDTYPE':'card_type','CARDRACE':'race','IS_BACON_POOL_MINION':'pool_minion',
            'IS_BACON_POOL_SPELL':'pool_spell','BACON_DUOS_EXCLUSIVE':'duos',
            'TAG_SCRIPT_DATA_NUM_1':'num1','TAG_SCRIPT_DATA_NUM_2':'num2',
            'BACON_TRIPLE_UPGRADE_MINION_ID':'golden_dbf',
            'BACON_TRIPLED_BASE_MINION_ID':'base_dbf'}
    for _,entity in ET.iterparse(path,events=('end',)):
        if entity.tag!='Entity':continue
        tags={t.get('name'):t for t in entity.findall('Tag')}
        def value(name,default=0):
            t=tags.get(name)
            return int(t.get('value',default)) if t is not None else default
        if value('CARD_SET')==1453:
            card=dict(id=entity.get('CardID'),dbf_id=int(entity.get('ID')),keywords=[])
            for name,key in wanted.items():
                if name in tags:card[key]=value(name)
            for name,key in [('CARDNAME','name'),('CARDTEXT','text')]:
                t=tags.get(name)
                for language in ('enUS','zhCN'):
                    card[key+'_'+language]=t.findtext(language,'') if t is not None else ''
            for name in ('TAUNT','DIVINE_SHIELD','DEATHRATTLE','BATTLECRY','REBORN',
                         'VENOMOUS','POISONOUS','WINDFURY','MAGNETIC'):
                if value(name):card['keywords'].append(name.lower())
            cards.append(card)
        entity.clear()
    if not cards:
        raise ValueError('Missing Battlegrounds definitions')
    # CardDefs.Bacon can carry duplicate entities for alternate definitions.
    # Keep the last complete entity (the database merge semantics) and reject
    # two conflicting definitions that would require guessing.
    unique = {}
    for card in cards:
        prior = unique.get(card['id'])
        if prior is not None and prior != card:
            # Some duplicate rows differ only in localized display metadata;
            # preserve the richer definition rather than silently inventing.
            if (prior.get('text_enUS', '') and not card.get('text_enUS')) or \
                    (prior.get('atk') is not None and card.get('atk') is None):
                continue
        unique[card['id']] = card
    return list(unique.values())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--revision',required=True);p.add_argument('--output',required=True)
    p.add_argument('--input',help='Existing pinned CardDefs.Bacon.xml; skips download')
    p.add_argument('--patch',required=True);args=p.parse_args()
    if not re.fullmatch('[a-f0-9]{40}',args.revision):p.error('Pin a full Git commit')
    output=Path(args.output);output.mkdir(parents=True,exist_ok=False)
    raw=output/'raw';processed=output/'processed';raw.mkdir();processed.mkdir()
    remote='CardDefs.Bacon.xml'
    url=f'https://raw.githubusercontent.com/HearthSim/hsdata/{args.revision}/{remote}'
    started=time.monotonic();size=0
    if args.input:
        content=Path(args.input).read_bytes()
        if not content.lstrip().startswith(b'<?xml'):raise ValueError('Input is not CardDefs XML')
        (raw/remote).write_bytes(content);size=len(content)
    else:
        with requests.get(url,stream=True,timeout=(5,30)) as response:
            response.raise_for_status()
            with (raw/remote).open('wb') as target:
                for chunk in response.iter_content(1024*1024):
                    size+=len(chunk)
                    if size>300_000_000 or time.monotonic()-started>240:raise TimeoutError('Card data download budget')
                    target.write(chunk)
    cards=extract(raw/remote)
    (processed/'bg_cards.json').write_text(json.dumps(cards,ensure_ascii=False,indent=2),encoding='utf-8')
    fields=['id','dbf_id','name_enUS','name_zhCN','atk','health','tech_level','pool_minion','pool_spell']
    with (processed/'bg_cards.csv').open('w',encoding='utf-8-sig',newline='') as target:
        writer=csv.DictWriter(target,fieldnames=fields,extrasaction='ignore');writer.writeheader();writer.writerows(cards)
    metadata=dict(source='HearthSim client data extraction; not an official server rules API',
                  url=url,revision=args.revision,patch=args.patch,access_method='HTTPS pinned bulk XML',
                  accessed_at=datetime.now(timezone.utc).isoformat(),bytes=size,cards=len(cards),
                  sha256=hashlib.sha256((raw/remote).read_bytes()).hexdigest(),
                  license='Game content belongs to Blizzard; no redistribution license inferred',
                  limitations=['pool flags alone do not prove current server rotation',
                               'card text is not executable effect logic','patch label supplied explicitly'])
    (output/'sources.json').write_text(json.dumps(metadata,indent=2),encoding='utf-8')
    (output/'data-dictionary.md').write_text('# BG card extraction\n\nIdentifiers are exact client IDs. Stats/cost/tier are integer client values; missing fields remain absent. Names and text use enUS/zhCN locales. Pool flags are client metadata, not live lobby membership. keywords are explicit XML tags. Data is a pinned snapshot, not live stats.\n',encoding='utf-8')
    print(json.dumps(metadata))

if __name__=='__main__':main()
