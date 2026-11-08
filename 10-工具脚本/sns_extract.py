# -*- coding: utf-8 -*-
"""从解密后的 sns.db 提取：我发的朋友圈 + 我在朋友圈的评论"""
import json
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

WS = Path(r"C:\Users\liujinhao\Documents\deepseek-harness\default-workspace")
DB = WS / "tools" / "tmp" / "decrypted" / "sns.db"
OUT = WS / "wechat-ingest"
OUT.mkdir(exist_ok=True)
ME = "wxid_cufzf1yemb4e22"


def tag(xml: str, name: str, default: str = "") -> str:
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", xml, re.S)
    return m.group(1).strip() if m else default


conn = sqlite3.connect(str(DB))

posts = []
for tid, user, content in conn.execute("SELECT tid, user_name, content FROM SnsTimeLine"):
    if not user or not user.startswith(ME[:10]):
        continue
    if not content or "<TimelineObject>" not in content:
        continue
    ct = tag(content, "createTime")
    try:
        dt = datetime.fromtimestamp(int(ct))
    except Exception:  # noqa: BLE001
        continue
    text = tag(content, "contentDesc")
    ctype = tag(content, "type")  # ContentObject type
    n_media = content.count("<media>")
    lat = re.search(r'latitude="([\d.\-]+)"', content)
    has_loc = bool(lat and lat.group(1) not in ("0", "0.0"))
    posts.append({
        "time": dt.strftime("%Y-%m-%d %H:%M"),
        "date": dt.strftime("%Y-%m-%d"),
        "text": text,
        "content_type": ctype,
        "media": n_media,
        "has_location": has_loc,
    })

posts.sort(key=lambda p: p["time"])
print("我的朋友圈:", len(posts))
(OUT / "moments.json").write_text(json.dumps(posts, ensure_ascii=False, indent=1), encoding="utf-8")

# 评论 / 点赞
comments = []
for row in conn.execute(
        "SELECT create_time, type, feed_id, from_username, from_nickname, "
        "to_username, to_nickname, content FROM SnsMessage_tmp3"):
    ct, typ, feed, fu, fn, tu, tn, body = row
    try:
        dt = datetime.fromtimestamp(int(ct)).strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        dt = "?"
    comments.append({"time": dt, "type": typ, "feed": str(feed), "from": fu,
                     "from_name": fn, "to": tu, "content": (body or "")[:200]})
conn.close()

mine = [c for c in comments if (c["from"] or "").startswith(ME[:10])]
print("我在朋友圈的评论/点赞:", len(mine), "| 全部互动:", len(comments))

# 我发的帖子下面收到的评论
my_feed_ids = set()
for tid, content in []:
    pass

lines = ["# 我的朋友圈（自动抽取）", "",
         f"> 来自本机 sns.db，共 {len(posts)} 条，{posts[0]['date'] if posts else ''} ~ "
         f"{posts[-1]['date'] if posts else ''}", ""]
for p in posts:
    flags = []
    if p["media"]:
        flags.append(f"图×{p['media']}")
    if p["has_location"]:
        flags.append("带定位")
    print("- %s %s%s" % (p["time"][:10], p["text"], ("｜" + "·".join(flags)) if flags else ""))
    lines.append(f"- **{p['time'][:10]}** {p['text']}" + (f"（{'·'.join(flags)}）" if flags else ""))
(OUT / "moments-self.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

# 统计
by_month = Counter(p["time"][:7] for p in posts)
by_year = Counter(p["time"][:4] for p in posts)
lens = [len(p["text"]) for p in posts if p["text"]]
texts = [p["text"] for p in posts if p["text"]]
poetic = sum(1 for t in texts if re.search(r"[，。！？].{2,}[，。！？]|兮|之|一阕|诗|词", t))
stats = ["# 朋友圈统计", "",
         f"- 总条数：{len(posts)}（有文字 {len(texts)} 条，纯图/视频 {len(posts)-len(texts)} 条）",
         f"- 配图帖子：{sum(1 for p in posts if p['media'])} 条",
         f"- 带定位：{sum(1 for p in posts if p['has_location'])} 条",
         f"- 平均文字长度：{sum(lens)/len(lens):.0f} 字" if lens else "",
         f"- 疑似诗词/文言/文学习作：{poetic} 条", "",
         "## 按年", ""] + [f"- {y}: {c}" for y, c in sorted(by_year.items())]
stats += ["", "## 按月", ""] + [f"- {m}: {c}" for m, c in sorted(by_month.items())]
(OUT / "moments-stats.md").write_text("\n".join(stats), encoding="utf-8")
print("\n".join(stats))
