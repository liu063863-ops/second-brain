# -*- coding: utf-8 -*-
"""语言风格统计：表情文字、结尾标点、句尾、笑声、长度分布"""
import json
import re
from collections import Counter

WS = r"C:\Users\liujinhao\Documents\deepseek-harness\default-workspace"
rows = [json.loads(l) for l in open(WS + r"\wechat-ingest\self-text.jsonl", encoding="utf-8")]
ts = [r["content"] for r in rows]
print("样本:", len(ts))

brackets = Counter(m for t in ts for m in re.findall(r"\[[^\[\]]{1,4}\]", t))
print("\n[表情文字] top15:", brackets.most_common(15))

END_PUNCT = set("，。！？…~、；：）)] }\"'" + "”’")
no_end = sum(1 for t in ts if t and t[-1] not in END_PUNCT)
print("\n结尾不带标点占比: %.0f%%" % (no_end / len(ts) * 100))

end2 = Counter(t[-2:] for t in ts if len(t) >= 2)
print("\n句尾两字 top15:", end2.most_common(15))

laugh = sum(1 for t in ts if re.search(r"哈{2,}|hhh|233", t))
print("\n带笑声的消息: %d 条 (%.1f%%)" % (laugh, laugh / len(ts) * 100))

qs = sum(1 for t in ts if t.rstrip().endswith("?"))
print("以问号结尾: %d 条 (%.1f%%)" % (qs, qs / len(ts) * 100))

lens = [len(t) for t in ts]
one = sum(1 for l in lens if l <= 3)
five = sum(1 for l in lens if 4 <= l <= 10)
print("≤3 字: %.0f%% | 4-10 字: %.0f%% | >30 字: %.1f%%"
      % (one / len(ts) * 100, five / len(ts) * 100, sum(1 for l in lens if l > 30) / len(ts) * 100))

calls = Counter()
for t in ts:
    for k in ("卧槽", "牛", "搞", "整", "弄", "行", "可以", "确实", "离谱", "逆天", "抽象", "绷", "寄"):
        if k in t:
            calls[k] += 1
print("\n高频词:", calls.most_common(14))
