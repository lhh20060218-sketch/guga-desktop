# -*- coding: utf-8 -*-
"""M1 知识库真题测试工具 (兼队友B验收工具)

用法:
  python scripts/quiz_knowledge.py scholar "我想学编程从哪开始"
  python scripts/quiz_knowledge.py tactician "三大报表怎么看" "市盈率是什么"
  python scripts/quiz_knowledge.py --all          # 跑内置验收题集

评分口径(队友B验收): 每甲 10 题, 检索 top1 命中相关文档且片段含
步骤/判断标准/例子之一 = 有用. 本工具给出 top 片段供人工判定.
"""
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO))

from core.knowledge_rag import KnowledgeRAG  # noqa: E402

# 内置验收题集(每甲首批; 交付后可扩充)
QUIZ = {
    'scholar': [
        '我想学编程从哪开始',
        'python 不是内部或外部命令怎么办',
        '第一个月应该学什么',
        '装完 python 打不开怎么办',
    ],
    'tactician': [
        '三大报表分别看什么',
        '为什么公司利润很高还会倒闭',
        '财报里哪个指标最该先看',
        '现金流为负说明什么',
    ],
}


def ask(armor_id, question, top_k=3):
    rag = KnowledgeRAG(armor_id)
    hits = rag.retrieve(question, top_k=top_k)
    print('\nQ(%s): %s' % (armor_id, question))
    if not hits:
        print('  ✗ 无检索结果')
        return False
    for i, h in enumerate(hits, 1):
        print('  %d. [%.1f分] %s  (来源: %s)' % (i, h['score'], h['title'], h['doc']))
    top = hits[0]
    snippet = top['text'][:200].replace('\n', ' ')
    print('  📄 %s' % (snippet + ('...' if len(top['text']) > 200 else '')))
    return True


def main():
    args = sys.argv[1:]
    if not args:
        sys.exit(__doc__)
    if args[0] == '--all':
        ok = total = 0
        for armor_id, questions in QUIZ.items():
            rag = KnowledgeRAG(armor_id)
            st = rag.status()
            print('\n=== %s: %d 篇文档, %d 个知识块 ===' % (armor_id, st['docs'], st['chunks']))
            if st['docs'] == 0:
                print('  (知识库为空, 跳过 — 等待队友B交付)')
                continue
            for q in questions:
                total += 1
                ok += 1 if ask(armor_id, q) else 0
        print('\n===== 验收结果: %d/%d 题有检索结果 =====' % (ok, total))
        return 0
    armor_id = args[0]
    questions = args[1:]
    for q in questions:
        ask(armor_id, q)
    return 0


if __name__ == '__main__':
    sys.exit(main())
