"""Two bounded provider checks using synthetic questions/images, never desktop data."""
import base64,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import requests
from core.ai_chat import AIChatEngine
from core.chat_answer import request_payload
from core.chat_presentation import user_content


def run():
    root=Path(__file__).resolve().parents[1];cfg=AIChatEngine._load_config();base=cfg['base_url'].rstrip('/')
    fixture=root/'runtime/floating-ui-20261029/ocr-fixture.png'
    image='data:image/png;base64,'+base64.b64encode(fixture.read_bytes()).decode()
    cases=[('quick','图里已完成几项、共几项？只回答数字。',image),('low','9.8 和 9.11 哪个数大？只回答较大的数。',None)]
    records=[]
    for effort,text,picture in cases:
        payload=request_payload(cfg,[dict(role='user',content=user_content(text,picture))],effort)
        started=time.monotonic();answer='';first=None;usage=None;reasoning_seen=False
        with requests.post(base+'/chat/completions',headers={'Authorization':'Bearer '+cfg['api_key'],'Content-Type':'application/json','User-Agent':'GugaDesktopPet/1.0','x-opencode-session':'guga-answer-fixture-20261029'},json=payload,stream=True,timeout=(6,40)) as response:
            if response.status_code!=200:
                records.append(dict(effort=effort,ok=False,http=response.status_code));break
            for line in response.iter_lines(chunk_size=128):
                if time.monotonic()-started>60:raise RuntimeError('Fixture exceeded its 60 second budget')
                if not line or not line.startswith(b'data:'):continue
                item=line[5:].strip()
                if item==b'[DONE]':break
                data=json.loads(item);usage=data.get('usage') or usage;choices=data.get('choices') or []
                delta=choices[0].get('delta',{}) if choices else {}
                reasoning_seen=reasoning_seen or bool(delta.get('reasoning_content'))
                if isinstance(delta.get('content'),str):
                    answer+=delta['content']
                    if first is None:first=round(time.monotonic()-started,2)
        record=dict(effort=effort,ok=bool(answer),answer=answer[:140],first_answer_seconds=first,total_seconds=round(time.monotonic()-started,2),reasoning_seen=reasoning_seen,usage=usage)
        records.append(record);print(json.dumps(record,ensure_ascii=False),flush=True)
    target=root/'runtime/floating-ui-20261029/answer-service-check.json';target.write_text(json.dumps(records,ensure_ascii=False,indent=2),encoding='utf-8')
    return 0 if len(records)==2 and all(r.get('ok') for r in records) and not records[0].get('reasoning_seen') else 1


if __name__=='__main__':sys.exit(run())
