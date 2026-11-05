"""Small evidence-producing web search, run only in the agent worker."""
import requests,re,html
from html.parser import HTMLParser
class Results(HTMLParser):
    def __init__(self):super().__init__();self.results=[];self.item=None;self.depth=0;self.anchor=False
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag=='li' and 'b_algo' in a.get('class','').split():self.item=dict(title='',url='',snippet='');self.depth=1
        elif self.item is not None:
            if tag=='li':self.depth+=1
            if tag=='a' and not self.item['url'] and a.get('href','').startswith('http'):self.item['url']=a['href'];self.anchor=True
    def handle_endtag(self,tag):
        if self.item is None:return
        if tag=='a':self.anchor=False
        if tag=='li':
            self.depth-=1
            if not self.depth:
                if self.item['title'] and self.item['url']:self.results.append(self.item)
                self.item=None
    def handle_data(self,data):
        if self.item is not None:
            key='title' if self.anchor else 'snippet'
            self.item[key]+=data+' '
def search(query):
    query=str(query).strip()[:300]
    if not query:raise ValueError('搜索关键词不能为空')
    response=requests.get('https://www.bing.com/search',params={'q':query,'setlang':'zh-hans'},headers={'User-Agent':'Mozilla/5.0'},timeout=(5,8))
    try:
        response.raise_for_status()
        parser=Results();parser.feed(response.text[:2_000_000])
    finally:response.close()
    results=[dict(title=r['title'].strip()[:160],url=r['url'],snippet=re.sub(r'\s+',' ',r['snippet']).strip()[:550]) for r in parser.results[:5]]
    return dict(ok=bool(results),results=results,message='公开搜索摘要，引用来源后汇报；摘要不等于已核实全文' if results else '搜索页没有可读取摘要，可能为验证页；不能编造搜索结果')
