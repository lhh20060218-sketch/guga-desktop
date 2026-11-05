"""Finite real-device check: discard mic data, silent output, no network."""
import argparse
import json
from pathlib import Path
import queue
import sys
import time

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--seconds',type=int,default=90,choices=range(30,121))
    args=parser.parse_args()
    import sounddevice as sd
    from core.realtime_voice import RealtimeVoice,DEFAULTS
    voice=RealtimeVoice();voice._cfg=dict(DEFAULTS);voice._muted=True
    result=dict(seconds=args.seconds,input_callbacks=0,output_callbacks=0,input_status=0,output_status=0,
        max_input_gap_ms=0,nonzero_transmitted_samples=False,network=False,audio_saved=False)
    previous=None
    def capture(data,frames,timing,status):
        nonlocal previous
        now=time.monotonic()
        if previous is not None:result['max_input_gap_ms']=max(result['max_input_gap_ms'],round((now-previous)*1000,2))
        previous=now;result['input_callbacks']+=1;result['input_status']+=bool(status)
        # Production mute discards input before calculating levels/queuing PCM.
        voice._capture(data,frames,timing,status)
    def output(data,frames,timing,status):
        result['output_callbacks']+=1;result['output_status']+=bool(status)
        voice._playback(data,frames,timing,status)
    try:
        with sd.RawOutputStream(samplerate=24000,channels=1,dtype='int16',blocksize=960,callback=output):
            with sd.RawInputStream(samplerate=16000,channels=1,dtype='int16',blocksize=640,callback=capture):
                end=time.monotonic()+args.seconds
                while time.monotonic()<end:
                    try:
                        while True:
                            if any(voice._input.get_nowait()):result['nonzero_transmitted_samples']=True
                    except queue.Empty:pass
                    time.sleep(.01)
        result['devices_closed']=True
    except Exception as exc:
        result.update(error=type(exc).__name__,devices_closed=True)
    result['ok']=bool(not result.get('error') and result['input_callbacks']>=args.seconds*25*.9 and
        result['output_callbacks']>=args.seconds*25*.9 and result['max_input_gap_ms']<500 and
        not result['nonzero_transmitted_samples'])
    folder=ROOT/'runtime/voice-soak-qa';folder.mkdir(parents=True,exist_ok=True)
    (folder/'audio-device-health.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps(result));return 0 if result['ok'] else 1


if __name__=='__main__':raise SystemExit(main())
