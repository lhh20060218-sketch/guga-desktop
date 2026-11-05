"""Bounded by the caller; isolate neural audio dependencies from Qt."""
import os,sys,json,hashlib,logging,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];MUSIC=ROOT/'runtime/music'
os.environ['PATH']=str(MUSIC/'bin')+os.pathsep+os.environ.get('PATH','')
os.environ.setdefault('OMP_NUM_THREADS','4')

def separate(source):
 from audio_separator.separator import Separator
 source=Path(source).resolve()
 if not source.is_file():raise ValueError('Missing source audio')
 ident=hashlib.sha256((str(source)+str(source.stat().st_size)).encode()).hexdigest()[:14]
 folder=MUSIC/'stems'/ident;folder.mkdir(parents=True,exist_ok=True)
 manifest=folder/'stems.json'
 if manifest.exists():
  d=json.loads(manifest.read_text(encoding='utf-8'))
  if all(Path(d[k]).is_file() for k in ('vocals','instrumental')):return d
 model='UVR_MDXNET_KARA_2.onnx'
 separator=Separator(output_dir=str(folder),output_format='WAV',model_file_dir=str(MUSIC/'models'),
  log_level=logging.WARNING,normalization_threshold=.95,mdx_params=dict(hop_length=1024,segment_size=256,overlap=.25,batch_size=1,enable_denoise=True))
 separator.load_model(model_filename=model)
 decoded=folder/'decoded.wav'
 if not decoded.exists():subprocess.run([str(MUSIC/'bin/ffmpeg.exe'),'-v','error','-y','-i',str(source),'-ar','44100','-ac','2',str(decoded)],check=True,timeout=40,creationflags=0x08000000)
 outputs=separator.separate(str(decoded))
 files=[Path(x) if Path(x).is_absolute() else folder/Path(x).name for x in outputs]
 vocal=next((x for x in files if 'vocal' in x.name.lower()),None)
 instrumental=next((x for x in files if 'instrumental' in x.name.lower()),None)
 if not vocal or not instrumental:raise RuntimeError('Separation did not produce both stems')
 d=dict(vocals=str(vocal),instrumental=str(instrumental),source=str(source),separator=model)
 manifest.write_text(json.dumps(d,ensure_ascii=True,indent=2),encoding='utf-8');return d
if __name__=='__main__':
 try:result=dict(ok=True,**separate(sys.argv[1]))
 except Exception as e:result=dict(ok=False,error=type(e).__name__,message=str(e)[:350])
 print(json.dumps(result,ensure_ascii=True),flush=True)
 sys.exit(0 if result['ok'] else 1)
