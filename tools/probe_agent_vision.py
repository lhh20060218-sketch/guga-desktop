"""One configured model request using a synthetic image, never desktop pixels."""
import base64
import io
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from PIL import Image,ImageDraw,ImageFont
from core.self_agent import SelfAgent
image=Image.new('RGB',(600,180),'white');draw=ImageDraw.Draw(image)
draw.text((35,50),'GUGA 7316',font=ImageFont.truetype('C:/Windows/Fonts/arial.ttf',58),fill='black')
buffer=io.BytesIO();image.save(buffer,format='PNG')
agent=SelfAgent(None)
response=agent._request([dict(role='system',content='只返回图片中的字母和数字。'),dict(role='user',content=[dict(type='text',text='读出图片文字。'),dict(type='image_url',image_url=dict(url='data:image/png;base64,'+base64.b64encode(buffer.getvalue()).decode()))])],'guga-vision-capability-test',tools=False)
answer=response.get('content','')
print(dict(model=agent.config.get('model'),synthetic_image_only=True,vision_passed='7316' in answer,reply=answer[:100]))
if '7316' not in answer:raise SystemExit(1)
