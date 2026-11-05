# -*- coding: utf-8 -*-
"""咕嘎企鹅 RAG 检索 — 多源知识库（knowledge/battlegrounds/*.json）

轻量实现（关键词 + 字符 n-gram 打分），无需向量库/外部依赖：
对用户消息与知识块做子串/双字组重叠打分，返回最相关的 Top-K
知识块拼成上下文，注入大模型提示词。
"""
import json
import os
import re

_KB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'knowledge', 'battlegrounds')
_KB = None


def _load_kb():
    global _KB
    if _KB is None:
        chunks = []
        if os.path.isdir(_KB_DIR):
            for name in sorted(os.listdir(_KB_DIR)):
                if not name.endswith('.json'):
                    continue
                try:
                    with open(os.path.join(_KB_DIR, name), 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    if isinstance(data, dict) and 'chunks' in data:
                        chunks.extend(data['chunks'])
                    elif isinstance(data, list):
                        chunks.extend(data)
                except Exception:
                    continue
        _KB = chunks
    return _KB


def _bigrams(text: str) -> set:
    clean = re.sub(r'[\s，。！？、；：“”‘’（）【】《》\.,!?;:()\[\]"\'\-]', '', text)
    return {clean[i:i + 2] for i in range(len(clean) - 1) if clean[i:i + 2].strip()}


def _score_chunk(chunk: dict, user_text: str, user_bigrams: set) -> float:
    score = 0.0
    for tag in chunk.get('tags', []):
        if tag and tag in user_text:
            score += 3.0
    content = chunk['content']
    overlap = len(user_bigrams & _bigrams(content))
    score += overlap * 1.0
    return score


def retrieve(query: str, top_k: int = 4, min_score: float = 3.0):
    if not query or not query.strip():
        return []
    user_bigrams = _bigrams(query)
    scored = []
    for chunk in _load_kb():
        s = _score_chunk(chunk, query, user_bigrams)
        if s >= min_score:
            scored.append((chunk, s))
    scored.sort(key=lambda x: -x[1])
    return scored[:top_k]


def build_context(query: str, top_k: int = 4, min_score: float = 3.0) -> str:
    hits = retrieve(query, top_k=top_k, min_score=min_score)
    if not hits:
        return ""
    lines = []
    for i, (chunk, _s) in enumerate(hits, 1):
        cat = chunk.get('category', '')
        lines.append(f"[知识{i}·{cat}] {chunk['content']}")
    return "\n".join(lines)


def kb_stats() -> dict:
    """知识库统计（用于检测报告）"""
    chunks = _load_kb()
    cats = {}
    for c in chunks:
        cat = c.get('category', '未知')
        cats[cat] = cats.get(cat, 0) + 1
    return {'total': len(chunks), 'categories': cats}


if __name__ == '__main__':
    import sys
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    print('知识库统计:', kb_stats())
    for q in sys.argv[1:] or ['黑暗之赐怎么用？我玩机械流要不要升5级？', '郭分荷是谁？他的野兽阵容怎么玩？']:
        print(f"--- 查询: {q} ---")
        ctx = build_context(q)
        print(ctx if ctx else "(无命中)")
        print()
