"""Record three local samples and bind the owner voice."""
import sys
import time
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
import numpy as np
import sounddevice as sd
from core.speaker_gate import SAMPLE_RATE,enroll

if __name__=='__main__':
    print('主人声纹录入：请在一个安静位置，连续说三句话，每句约 3 秒。')
    samples=[]
    for index in range(3):
        input(f'第 {index+1}/3 段，按 Enter 后开始，说完整一句话…')
        print('录音 3 秒…')
        audio=sd.rec(int(3*SAMPLE_RATE),samplerate=SAMPLE_RATE,channels=1,dtype='float32')
        sd.wait();audio=audio.reshape(-1)
        if float(np.sqrt(np.mean(audio*audio)))<.004:
            print('没有检测到有效声音，请重试。');sys.exit(2)
        samples.append(audio)
    try:
        result=enroll(samples)
        print(f"声纹已绑定：threshold={result['threshold']:.3f}")
        print('请重新启动咕嘎并开启长语音。')
    except Exception as exc:
        print('录入失败：'+str(exc));sys.exit(2)
