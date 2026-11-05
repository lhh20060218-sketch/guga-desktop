"""NDJSON speaker gate worker; keeps ONNX Runtime isolated from Qt/pythonnet."""
import base64
import json
import sys
import time
import numpy as np
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from core.speaker_gate import LocalSpeakerGate


def main():
    gate=None
    stats=dict(input_bytes=0,output_bytes=0,blocks=0,max_processing_ms=0.)
    for line in sys.stdin:
        try:request=json.loads(line)
        except ValueError:continue
        command=request.get('cmd')
        try:
            if command=='init':
                gate=LocalSpeakerGate(request['profile'],request['model'],request.get('threshold'))
                answer=dict(ok=True)
            elif command=='audio' and gate:
                raw=base64.b64decode(request.get('pcm',''));started=time.perf_counter()
                out=gate.process_pcm(raw,now=request.get('now'),blocked=request.get('blocked',False))
                stats['input_bytes']+=len(raw);stats['output_bytes']+=len(out);stats['blocks']+=1
                stats['max_processing_ms']=max(stats['max_processing_ms'],round((time.perf_counter()-started)*1000,2))
                pcm=np.frombuffer(raw,dtype=np.int16).astype(np.float32)/32768.
                stats['rms']=round(float(np.sqrt(np.mean(pcm*pcm))),5) if len(pcm) else 0.
                answer=dict(ok=True,out=base64.b64encode(out).decode('ascii'),state=gate.state,score=gate.last_score,
                    stats=dict(stats,threshold=gate.threshold,pending_ms=round(sum(map(len,gate.pending))/32),
                               voiced_ms=round(gate.voiced_samples/16)))
            elif command=='close':
                answer=dict(ok=True);print(json.dumps(answer),flush=True);return
            else:answer=dict(ok=False,error='声纹进程未初始化或命令无效')
        except Exception as exc:answer=dict(ok=False,error=str(exc))
        print(json.dumps(answer,ensure_ascii=False),flush=True)


if __name__=='__main__':main()
