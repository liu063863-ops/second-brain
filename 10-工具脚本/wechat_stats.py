# -*- coding: utf-8 -*-
"""微信导出 → 蒸馏素材（v2：只取我发的纯文本 + 联系人名字映射 + 指纹）

输入：wechat-export/wechat_messages.json（由 tools/keeper/export_local.py 生成）
输出：wechat-ingest/
  self-text.md / self-text.jsonl   我发的纯文本消息（verbatim 池，按真实名字分组）
  fingerprint.md                   语言指纹
  conversations.csv                会话统计（真实名字）
  report.txt                       总览
"""
from __future__ import annotations

import csv
import json
import re
import sqlite3
import sys
from collections import Counter, defaultdict
from pathlib import Path

WS = Path(r"C:\Users\liujinhao\Documents\deepseek-harness\default-workspace")
sys.path.insert(0, str(WS / "tools" / "downloaded" / "chatlog-keeper"))
from chatlog_keeper import wechat_db  # noqa: E402

KEY = bytes.fromhex("113c9be4cb05413189b77a2940e85a1b0d78a7e0172248ac8fe32d75fad67665")
ACC = Path(r"C:\Users\liujinhao\Documents\xwechat_files\wxid_cufzf1yemb4e22_1e22")
TMP = WS / "tools" / "tmp" / "decrypted"
SRC = WS / "wechat-export" / "wechat_messages.json"
OUT = WS / "wechat-ingest"
OUT.mkdir(parents=True, exist_ok=True)

PLACEHOLDER = re.compile(
    r"^(\[[^\]]{0,12}\]|语音|图片|表情|视频|文件|引用|链接|动画表情|位置|转账|红包|"
    r"小程序|聊天记录|名片|拍一拍|系统消息|接龙|视频号|音乐|卡券|订单|群公告)\s*\d*\"?$"
)
PREFIX = re.compile(r"^[A-Za-z0-9_\-]{4,64}:\n")
EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
PUNCT = re.compile(r"[，。！？…~、；：\-—【】（）()\"'“”‘’]+")
CJK_SEG = re.compile(r"[^\u4e00-\u9fff]+")


def load_names() -> dict:
    """username -> 显示名（备注 > 昵称 > username）"""
    names = {}
    src = ACC / "db_storage" / "contact" / "contact.db"
    dst = TMP / "contact.db"
    ok = wechat_db._decrypt_db_v4_snapshot(src, KEY, dst)
    if not ok:
        print("警告：contact.db 解密失败，名字将用 wxid")
        return names
    conn = sqlite3.connect(str(dst))
    try:
        for username, remark, nick in conn.execute(
                "SELECT username, remark, nick_name FROM contact"):
            username = (username or "").strip()
            display = (remark or "").strip() or (nick or "").strip() or username
            if username:
                names[username] = display
    finally:
        conn.close()
    return names


names = load_names()
print("联系人名映射:", len(names))

rows = json.loads(SRC.read_text(encoding="utf-8"))
print("原始消息:", len(rows))

conv = defaultdict(lambda: {"all": 0, "mine": 0, "first": None, "last": None})
self_text = []
kept_types = Counter()

for r in rows:
    talker = (r.get("talker") or "").strip() or "未知会话"
    mine = bool(r.get("is_self"))
    ts = r.get("time") or ""
    c = conv[talker]
    c["all"] += 1
    if ts:
        c["first"] = ts if c["first"] is None or ts < c["first"] else c["first"]
        c["last"] = ts if c["last"] is None or ts > c["last"] else c["last"]
    if not mine:
        continue
    c["mine"] += 1

    content = (r.get("content") or "").strip()
    if r.get("msg_type") not in (None, 1):
        kept_types[r.get("msg_type")] += 1
        continue
    content = PREFIX.sub("", content).strip()
    if not content or PLACEHOLDER.match(content) or len(content) < 2:
        continue
    if "撤回了一条消息" in content or "加入了群聊" in content:
        continue
    self_text.append({
        "time": ts,
        "talker": talker,
        "name": names.get(talker, talker),
        "content": content,
    })

print("我说的话（纯文本）:", len(self_text))

by_talker = defaultdict(list)
for m in self_text:
    by_talker[m["name"]].append(m)
ordered = sorted(by_talker.items(), key=lambda kv: -len(kv[1]))

lines = ["# 我说过的话（微信纯文本 · verbatim 池）", "",
         f"> 来源：本机微信库导出；样本 {len(self_text)} 条我发送的纯文本消息，"
         f"覆盖 {len(by_talker)} 个会话。",
         "> 已剔除：图片/语音/表情/引用等非文本消息、占位符、群聊 `wxid:` 前缀。", ""]
for name, items in ordered:
    lines.append(f"## {name}（{len(items)} 条 · {items[0]['time'][:10]} ~ {items[-1]['time'][:10]}）")
    lines.append("")
    for m in items[-300:]:
        lines.append(f"- `{m['time'][:16]}` {m['content']}")
    lines.append("")
(OUT / "self-text.md").write_text("\n".join(lines), encoding="utf-8")

with (OUT / "self-text.jsonl").open("w", encoding="utf-8") as f:
    for m in self_text:
        f.write(json.dumps(m, ensure_ascii=False) + "\n")

# ---- 指纹 ----
texts = [m["content"] for m in self_text]
lens = sorted(len(t) for t in texts)
emo = Counter(ch for t in texts for ch in EMOJI.findall(t))
pun = Counter(ch for t in texts for ch in PUNCT.findall(t))
grams = Counter()
for t in texts:
    for seg in CJK_SEG.split(t):
        for n in (2, 3):
            for i in range(len(seg) - n + 1):
                grams[seg[i:i + n]] += 1
opens = Counter(t[:3] for t in texts if len(t) >= 3)
tails = Counter(t[-2:] for t in texts if len(t) >= 2)
emo_lines = [f"- {k} × {v}" for k, v in emo.most_common(15)] or ["- （几乎不用 emoji）"]

fp = ["# 语言指纹（纯文本口径）", "",
      f"- 样本：{len(texts)} 条",
      f"- 平均句长 {sum(lens)/len(lens):.1f} 字；中位 {lens[len(lens)//2]} 字；"
      f"P90 {lens[int(len(lens)*0.9)]} 字",
      f"- ≤5 字占比 {sum(1 for l in lens if l <= 5)/len(lens):.0%}；"
      f"≥50 字占比 {sum(1 for l in lens if l >= 50)/len(lens):.1%}",
      "", "## 标点", "", *[f"- `{k}` × {v}" for k, v in pun.most_common(12)],
      "", "## emoji", "", *emo_lines,
      "", "## 高频二/三字串（口头禅候选，需人工筛）", "",
      *[f"- {k} × {v}" for k, v in grams.most_common(40)],
      "", "## 高频开头三字", "", *[f"- 「{k}…」 × {v}" for k, v in opens.most_common(15)],
      "", "## 高频结尾两字", "", *[f"- 「…{k}」 × {v}" for k, v in tails.most_common(15)]]
(OUT / "fingerprint.md").write_text("\n".join(fp) + "\n", encoding="utf-8")

with (OUT / "conversations.csv").open("w", encoding="utf-8-sig", newline="") as f:
    w = csv.writer(f)
    w.writerow(["会话", "会话ID", "总条数", "我发送", "首条", "末条"])
    for talker, c in sorted(conv.items(), key=lambda kv: -kv[1]["all"]):
        w.writerow([names.get(talker, talker), talker, c["all"], c["mine"],
                    c["first"] or "", c["last"] or ""])

mine_total = sum(1 for r in rows if r.get("is_self"))
report = ["微信导出 → 蒸馏素材", "",
          f"总消息 {len(rows)} 条；我发送 {mine_total} 条",
          f"纯文本「我说的话」{len(self_text)} 条，覆盖 {len(by_talker)} 个会话",
          f"时间范围 {(min((r['time'] for r in rows if r.get('time')), default='') or '')[:10]} ~ "
          f"{(max((r['time'] for r in rows if r.get('time')), default='') or '')[:10]}",
          "", "Top 15 会话（按总条数）："]
for talker, c in sorted(conv.items(), key=lambda kv: -kv[1]["all"])[:15]:
    report.append(f"  {names.get(talker, talker)}: {c['all']} 条（我 {c['mine']}）")
report += ["", "Top 15 会话（按我发的条数）："]
for talker, c in sorted(conv.items(), key=lambda kv: -kv[1]["mine"])[:15]:
    report.append(f"  {names.get(talker, talker)}: 我 {c['mine']} 条（共 {c['all']}）")
(OUT / "report.txt").write_text("\n".join(report), encoding="utf-8")
print("\n".join(report))
