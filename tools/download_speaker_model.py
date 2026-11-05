import sys
import hashlib
from pathlib import Path
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
TARGET=ROOT/'resources/models/speaker/3dspeaker_eres2net_base_16k.onnx'
URL='https://github.com/k2-fsa/sherpa-onnx/releases/download/speaker-recongition-models/3dspeaker_speech_eres2net_base_sv_zh-cn_3dspeaker_16k.onnx'
SHA256='1a331345f04805badbb495c775a6ddffcdd1a732567d5ec8b3d5749e3c7a5e4b'

if __name__=='__main__':
    TARGET.parent.mkdir(parents=True,exist_ok=True)
    if not TARGET.is_file():
        print('Downloading local speaker model...')
        urllib.request.urlretrieve(URL,TARGET)
    digest=hashlib.sha256(TARGET.read_bytes()).hexdigest()
    if digest!=SHA256:
        TARGET.unlink(missing_ok=True)
        raise SystemExit('Speaker model SHA-256 mismatch; deleted the download')
    print(f'Ready: {TARGET} ({TARGET.stat().st_size} bytes)')
    sys.exit(0)
