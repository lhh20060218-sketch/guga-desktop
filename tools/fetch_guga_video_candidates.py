"""Bounded public video acquisition, no cookies/login or access-control bypass."""
import concurrent.futures,json,time
from pathlib import Path
import yt_dlp

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'runtime/references/guga-source-videos-20261102'
SOURCES=[('bili-dance','https://www.bilibili.com/video/BV1MGR3BjE7B/'),
         ('bili-dance-pure','https://www.bilibili.com/video/BV1pFwdzmEna/')]

class QuietLog:
    def debug(self,*args):pass
    def warning(self,*args):pass
    def error(self,*args):pass

def fetch(source):
    name,url=source;start=time.monotonic();target=OUT/name;target.mkdir(parents=True,exist_ok=True)
    opts=dict(quiet=True,no_warnings=True,logger=QuietLog(),noplaylist=True,
              socket_timeout=12,retries=0,extractor_retries=0,fragment_retries=0,
              format='bestvideo[height<=720]/bestvideo/best',max_filesize=50*1024*1024,
              outtmpl=str(target/'source.%(ext)s'),restrictfilenames=True)
    row=dict(id=name,source=url,review='not_reviewed',redistribution='not_verified')
    try:
        with yt_dlp.YoutubeDL(opts) as downloader:
            info=downloader.extract_info(url,download=False)
            if info.get('duration',0)>90:raise ValueError('Long source outside this sampling stage')
            row.update(title=info.get('title'),duration=info.get('duration'),
                       width=info.get('width'),height=info.get('height'),fps=info.get('fps'))
            downloader.process_info(info)
            files=[p for p in target.glob('source.*') if p.suffix.lower() in ('.mp4','.webm','.flv','.mkv','.mov','.m4v')]
            row.update(files=[dict(name=p.name,bytes=p.stat().st_size) for p in files],downloaded=bool(files))
    except Exception as exc:
        # Error messages may contain ephemeral signed transport URLs. Keep a
        # short error category and public source, never login/cookie material.
        message=str(exc)
        row.update(downloaded=False,error=type(exc).__name__,detail=(
            'HTTP 412' if '412' in message else 'HTTP 403' if '403' in message else
            'requires cookies' if 'cookie' in message.lower() else
            'HTTP 429' if '429' in message else message.splitlines()[0][:220]))
    row['elapsed_seconds']=round(time.monotonic()-start,2)
    (target/'source.json').write_text(json.dumps(row,ensure_ascii=False,indent=2),encoding='utf-8')
    return row

def main():
    OUT.mkdir(parents=True,exist_ok=True)
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
        results=list(pool.map(fetch,SOURCES))
    (OUT/'acquisition.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(results,ensure_ascii=True))

if __name__=='__main__':main()
