# -*- coding: utf-8 -*-
"""把 self-text.jsonl 切成若干「分析片」，供并行抽取用。

每片是一份 markdown：按会话分组，保留原话与时间，单条超长截断。
输出：wechat-ingest/slices/slice-01.md ... 以及 index.json（每片统计）
"""
from __future__ import annotations

import json
from collections import defaultdict
from pathlib import Path

WS = Path(r"C:\Users\liujinhao\Documents\deepseek-harness\default-workspace")
SRC = WS / "wechat-ingest" / "self-text.jsonl"
OUT = WS / "wechat-ingest" / "slices"
OUT.mkdir(parents=True, exist_ok=True)

rows = [json.loads(l) for l in SRC.read_text(encoding="utf-8").splitlines() if l.strip()]
by_conv = defaultdict(list)
for r in rows:
    by_conv[(r["talker"], r["name"])].append(r)

# 按会话体量排序，贪心分配到 N 片，保持体量均衡
N = 12
convs = sorted(by_conv.items(), key=lambda kv: -len(kv[1]))
buckets = [[] for _ in range(N)]
loads = [0] * N
for (talker, name), items in convs:
    i = loads.index(min(loads))
    buckets[i].append(((talker, name), items))
    loads[i] += len(items)

index = []
for i, bucket in enumerate(buckets, 1):
    lines = [f"# 微信语料分析片 {i}/{N}", "",
             f"> 只含「我」（刘锦昊）发送的消息，共 {loads[i-1]} 条，"
             f"覆盖 {len(bucket)} 个会话。", ""]
    for (talker, name), items in sorted(bucket, key=lambda x: -len(x[1])):
        lines.append(f"## 会话：{name}（{len(items)} 条）")
        lines.append("")
        for m in items:
            c = m["content"].replace("\n", " ⏎ ")
            if len(c) > 300:
                c = c[:300] + "…"
            lines.append(f"- [{m['time'][:16]}] {c}")
        lines.append("")
    p = OUT / f"slice-{i:02d}.md"
    p.write_text("\n".join(lines), encoding="utf-8")
    index.append({"slice": f"slice-{i:02d}.md", "messages": loads[i - 1],
                  "conversations": [n for (_, n), _ in bucket],
                  "kb": round(p.stat().st_size / 1024, 1)})

(OUT / "index.json").write_text(json.dumps(index, ensure_ascii=False, indent=1), encoding="utf-8")
for it in index:
    print(f'{it["slice"]}: {it["messages"]} 条, {len(it["conversations"])} 会话, {it["kb"]} KB')
print("总消息:", sum(it["messages"] for it in index))
