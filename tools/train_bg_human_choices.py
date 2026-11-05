"""Train a current-build human candidate ranker from allowlisted live cases."""
import argparse,json,math,time
from collections import Counter
from pathlib import Path
import numpy as np

KINDS=('END','BUY_MINION','BUY_SPELL','PLAY_MINION','PLAY_SPELL','HERO_POWER',
       'REFRESH','FREEZE','UPGRADE','SELL','DARK_GIFT','TRINKET','OTHER')


def kind_of(entity,chosen_target=None):
    card=str(entity.get('CARD_ID') or '');ctype=str(entity.get('CARDTYPE') or '');zone=str(entity.get('ZONE') or '')
    if card=='TB_BaconShop_DragBuy':return 'BUY_MINION'
    if card=='TB_BaconShop_DragBuy_Spell':return 'BUY_SPELL'
    if card=='TB_BaconShop_DragSell':return 'SELL'
    if card=='TB_BaconShop_8p_Reroll_Button':return 'REFRESH'
    if card=='TB_BaconShopLockAll_Button':return 'FREEZE'
    if card.startswith('TB_BaconShopTechUp'):return 'UPGRADE'
    if ctype=='HERO_POWER':return 'HERO_POWER'
    if card=='BG36_Button_DarkGift':return 'DARK_GIFT'
    if ctype=='BATTLEGROUND_TRINKET':return 'TRINKET'
    if zone=='HAND' and ctype=='MINION':return 'PLAY_MINION'
    if zone=='HAND' and ctype=='BATTLEGROUND_SPELL':return 'PLAY_SPELL'
    return 'OTHER'


def target_for(entity,entities,selected=False,target=None):
    if selected and target is not None:return entities.get(str(target),{})
    linked=entity.get('2442')
    if linked is not None:return entities.get(str(linked),{})
    return entity if entity.get('ZONE')=='HAND' else {}


def encode_group(sample):
    entities=sample['observed_entities'];controller=sample['local_controller']
    player=next((e for e in entities.values() if e.get('CARDTYPE')=='PLAYER' and e.get('CONTROLLER')==controller),{})
    game=next((e for e in entities.values() if e.get('CARDTYPE')=='GAME'),{})
    board=[e for e in entities.values() if e.get('CONTROLLER')==controller and e.get('ZONE')=='PLAY' and e.get('CARDTYPE')=='MINION']
    hand=[e for e in entities.values() if e.get('CONTROLLER')==controller and e.get('ZONE')=='HAND']
    res=float(player.get('RESOURCES') or 0);used=float(player.get('RESOURCES_USED') or 0);temp=float(player.get('TEMP_RESOURCES') or 0)
    hp=float((entities.get(str(player.get('HERO_ENTITY')),{}) or {}).get('HEALTH') or player.get('HEALTH') or 0)
    armor=float((entities.get(str(player.get('HERO_ENTITY')),{}) or {}).get('ARMOR') or 0)
    turn=float(game.get('TURN') or player.get('TURN') or 0);tier=float(player.get('PLAYER_TECH_LEVEL') or 0);gold=max(0,res-used+temp)
    state=[turn/20,gold/10,tier/6,len(board)/7,len(hand)/10,hp/50,armor/30,
           sum(float(e.get('ATK') or 0)+float(e.get('HEALTH') or 0) for e in board)/200,
           float(any(e.get('TAUNT')==1 for e in board)),float(len(hand)>=9)]
    selected=sample['selected'];chosen_target=selected.get('selectedTarget')
    rows=[];meta=[]
    for option in sample['options']:
        index=option['index'];entity=entities.get(str(option.get('entity_id')),{})
        if option.get('error_code')!='NONE' and index!=selected.get('selectedOption'):continue
        is_chosen=index==selected.get('selectedOption');target=target_for(entity,entities,is_chosen,chosen_target)
        kind=kind_of(entity,chosen_target);card_id=str(target.get('CARD_ID') or entity.get('CARD_ID') or '')
        if kind=='END':card_id=''
        card=target or entity;atk=float(card.get('ATK') or 0);health=float(card.get('HEALTH') or 0);cost=float(entity.get('COST') or card.get('COST') or 0);card_tier=float(card.get('TECH_LEVEL') or 0)
        copies=sum(1 for e in board+hand if e.get('CARD_ID')==card_id)/3 if card_id else 0
        vals=[cost/10,atk/30,health/30,card_tier/6,float(card.get('ZONE')=='HAND'),float(card.get('ZONE')=='PLAY'),
              float(card.get('TAUNT')==1),float(any(card.get(k)==1 for k in ('DIVINE_SHIELD','937'))),float(card.get('REBORN')==1),
              float(card.get('POISONOUS')==1),float(card.get('WINDFURY')==1),copies,
              (atk+health)/40,float(index)/25]
        rows.append([float(kind==k) for k in KINDS]+state+vals);meta.append(dict(index=index,kind=kind,card_id=card_id,target=str(chosen_target or '')))
    chosen_index=next((i for i,m in enumerate(meta) if m['index']==selected.get('selectedOption')),None)
    return rows,meta,chosen_index,dict(turn=turn,tier=tier,gold=gold,hp=hp,board=len(board),hand=len(hand))


def softmax(z):
    z=np.asarray(z,dtype=np.float64);z=z-z.max();e=np.exp(z);return e/e.sum()


def train(groups,epochs=300,lr=.05,l2=1e-3):
    dim=len(groups[0]['x'][0]);w=np.zeros(dim);m=np.zeros(dim);v=np.zeros(dim);beta1=.9;beta2=.999
    for step in range(1,epochs+1):
        grad=np.zeros(dim)
        for g in groups:
            x=np.asarray(g['x'],dtype=np.float64);p=softmax(x@w);p[g['y']]-=1.;grad+=x.T@p/len(groups)
        grad+=l2*w;m=beta1*m+(1-beta1)*grad;v=beta2*v+(1-beta2)*(grad*grad)
        mh=m/(1-beta1**step);vh=v/(1-beta2**step);w-=lr*mh/(np.sqrt(vh)+1e-8)
    return w


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--input',required=True);ap.add_argument('--client-build',required=True,type=int)
    ap.add_argument('--output',default='data/bg_agent/human_learning_254477.json');args=ap.parse_args()
    raw=[json.loads(line) for line in Path(args.input).open(encoding='utf-8') if line.strip()]
    seen=set();groups=[];cases=[];kind_counts=Counter()
    for sample in raw:
        if not sample.get('matched'):continue
        key=(sample.get('option_set_id'),json.dumps(sample.get('selected',{}),sort_keys=True))
        if key in seen:continue
        seen.add(key);rows,meta,chosen,state=encode_group(sample)
        if chosen is None or len(rows)<2:continue
        groups.append(dict(x=rows,y=chosen,option_set=sample.get('option_set_id'),time=sample.get('log_time'),state=state))
        kind=meta[chosen]['kind'];kind_counts[kind]+=1
        cases.append(dict(turn=int(state['turn']),tier=int(state['tier']),gold=state['gold'],board=state['board'],hand=state['hand'],selected_kind=kind,selected_card_id=meta[chosen]['card_id'],candidate_count=len(rows)))
    if len(groups)<8:raise RuntimeError('当前构建的高置信选择少于8组，拒绝训练')
    hold=max(3,len(groups)//5);train_groups=groups[:-hold];test_groups=groups[-hold:]
    w=train(train_groups)
    hits=0;ranks=[];chance=[]
    for g in test_groups:
        scores=np.asarray(g['x'])@w;order=np.argsort(-scores);rank=int(np.where(order==g['y'])[0][0])+1;ranks.append(rank);hits+=rank==1;chance.append(1/len(g['x']))
    top1=hits/len(test_groups);base=float(np.mean(chance));deployable=top1>=.5 and top1>=base+.15
    output=Path(args.output);output.parent.mkdir(parents=True,exist_ok=True)
    document=dict(schema=1,client_build=args.client_build,created_at=time.time(),source=str(Path(args.input)),
      feature_dim=len(w),kinds=list(KINDS),weights=w.astype(float).tolist(),groups=len(groups),
      selected_kind_counts=dict(kind_counts),metrics=dict(train_groups=len(train_groups),holdout_groups=len(test_groups),
      holdout_top1=round(top1,4),uniform_baseline=round(base,4),mean_rank=round(float(np.mean(ranks)),3),deployable=deployable,
      limitation='同版本真实人类选择；样本规模有限，用于行为先验，不是最优策略或胜率模型'),cases=cases)
    output.write_text(json.dumps(document,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:document[k] for k in ('client_build','groups','metrics')},ensure_ascii=False))

if __name__=='__main__':main()
