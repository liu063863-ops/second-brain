# -*- coding: utf-8 -*-
"""合并 12 个分片的抽取结果：聚类去重、按支持度排序，产出中间产物。"""
from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

WS = Path(r"C:\Users\liujinhao\Documents\deepseek-harness\default-workspace")
FIND = WS / "wechat-ingest" / "findings"
OUT = WS / "wechat-ingest"
DIMS = ["personality", "interaction", "procedure"]

CONF_RANK = {"high": 3, "medium": 2, "low": 1}


def norm(s: str) -> str:
    return re.sub(r"[\s，。！？、；：,.!?;:\"'“”‘’（）()\-—…]", "", (s or "")).lower()


def bigrams(s: str) -> set:
    s = norm(s)
    return {s[i:i + 2] for i in range(len(s) - 1)} or {s}


def similar(a: str, b: str) -> float:
    A, B = bigrams(a), bigrams(b)
    if not A or not B:
        return 0.0
    return len(A & B) / len(A | B)


def cluster(items: list, threshold: float = 0.45) -> list:
    clusters = []  # each: {claim, evidences:[{evidence,conversation,when,level,confidence}], support}
    for it in items:
        placed = False
        for c in clusters:
            if similar(it["claim"], c["claim"]) >= threshold:
                c["evidences"].append(it)
                c["support"] += 1
                if CONF_RANK.get(it["confidence"], 0) > CONF_RANK.get(c["confidence"], 0):
                    c["confidence"] = it["confidence"]
                if len(it["claim"]) > len(c["claim"]):
                    c["claim"] = it["claim"]
                placed = True
                break
        if not placed:
            clusters.append({
                "claim": it["claim"],
                "evidences": [it],
                "support": 1,
                "confidence": it["confidence"],
            })
    for c in clusters:
        seen, uniq = set(), []
        for e in c["evidences"]:
            key = norm(e["evidence"])
            if key in seen:
                continue
            seen.add(key)
            uniq.append(e)
        c["evidences"] = uniq[:4]
        c["conversations"] = sorted({e["conversation"] for e in c["evidences"]})
        c["when"] = sorted({e["when"][:10] for e in c["evidences"] if e.get("when")})[:3]
    clusters.sort(key=lambda c: (-c["support"], -CONF_RANK.get(c["confidence"], 0)))
    return clusters


files = sorted(FIND.glob("slice-*.json"))
print("findings 文件:", len(files))
data = []
for f in files:
    try:
        data.append(json.loads(f.read_text(encoding="utf-8")))
    except Exception as e:  # noqa: BLE001
        print(" 跳过坏文件", f.name, e)

merged = {"slices": len(data), "stats": {}, "dimensions": {}, "memory": [], "conflicts": []}
for dim in DIMS:
    items = [i for d in data for i in d.get(dim, [])]
    cl = cluster(items)
    merged["dimensions"][dim] = cl
    merged["stats"][dim] = {"raw": len(items), "clusters": len(cl)}

# memory 事件聚类
events = [m for d in data for m in d.get("memory", [])]
by_key = {}
for e in events:
    key = norm(e["event"])[:24] or norm(e["what"])[:24]
    if key in by_key:
        by_key[key]["support"] += 1
        if e.get("evidence") and e["evidence"] not in by_key[key]["evidence"]:
            by_key[key]["evidence"] += " / " + e["evidence"][:60]
    else:
        by_key[key] = {**e, "support": 1}
merged["memory"] = sorted(by_key.values(), key=lambda x: (-x["support"], x.get("when", "")))[:60]
merged["stats"]["memory"] = {"raw": len(events), "clusters": len(merged["memory"])}

# conflicts
seen = set()
for d in data:
    for c in d.get("conflicts", []):
        k = norm(c["a"])[:20] + "|" + norm(c["b"])[:20]
        if k in seen:
            continue
        seen.add(k)
        merged["conflicts"].append(c)
merged["stats"]["conflicts"] = {"count": len(merged["conflicts"])}

(OUT / "merged.json").write_text(json.dumps(merged, ensure_ascii=False, indent=1), encoding="utf-8")

# 人读版
lines = ["# 合并后的抽取结果", ""]
for dim, cn in (("personality", "性格与价值观"), ("interaction", "互动风格"), ("procedure", "做事方式")):
    st = merged["stats"][dim]
    lines += [f"# {cn}（原始 {st['raw']} 条 → 聚类 {st['clusters']} 条）", ""]
    for i, c in enumerate(merged["dimensions"][dim], 1):
        lines.append(f"## {i}. {c['claim']}  [支持×{c['support']} · {c['confidence']}]")
        for e in c["evidences"]:
            lines.append(f"- 「{e['evidence']}」 — {e['conversation']} · {e['when'][:10]} · {e['level']}")
        lines.append("")
lines += [f"# 重要事件（{len(merged['memory'])} 条）", ""]
for e in merged["memory"]:
    lines.append(f"- [{e.get('when','')[:10]}] {e['event']}｜{e.get('people','')}｜{e.get('what','')}｜支持×{e['support']}")
lines += ["", f"# 矛盾（{len(merged['conflicts'])} 条）", ""]
for c in merged["conflicts"]:
    lines.append(f"- A：{c['a']}（{c['evidence_a'][:40]}） vs B：{c['b']}（{c['evidence_b'][:40]}）")
(OUT / "merged.md").write_text("\n".join(lines), encoding="utf-8")

print(json.dumps(merged["stats"], ensure_ascii=False, indent=1))
print("merged.md:", round((OUT / "merged.md").stat().st_size / 1024, 1), "KB")
