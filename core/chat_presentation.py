"""Presentation-only filtering; execution evidence stays in the local record."""
import re


def is_progress_ack(text):
    value=re.sub(r'[\s，。！～~、,.!]', '', str(text))
    return value in {'本鹅想一想','让本鹅想一想','这道问题倒是有点意思','嗯本鹅琢磨一下','交给本鹅','收到本鹅这就去办','好的我来处理',
                     '我来帮你处理','正在处理中','请稍等','稍等一下','我先看看',
                     '我正在处理','好的稍等','收到正在执行'}


def user_content(text, image_url=None):
    """Keep the image for this request only, outside persistent task metadata."""
    if not image_url:return text
    if not isinstance(image_url,str) or not image_url.startswith(('data:image/png;base64,','data:image/jpeg;base64,')):
        raise ValueError('截图附件格式不正确')
    if len(image_url)>12_000_000:raise ValueError('截图过大，请缩小框选范围')
    return [dict(type='text',text=text),dict(type='image_url',image_url=dict(url=image_url))]
