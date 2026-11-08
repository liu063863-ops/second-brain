# -*- coding: utf-8 -*-
"""重新解密 sns.db（用户已在 PC 端翻到第一条朋友圈）并全量抽取我的帖子"""
import json
import re
import sqlite3
import sys
import traceback
from collections import Counter
from datetime import datetime
from pathlib import Path

WS = Path(r"C:\Users\liujinhao\Documents\deepseek-harness\default-workspace")
sys.path.insert(0, str(WS / "tools" / "downloaded" / "chatlog-keeper"))
from chatlog_keeper import wechat_db  # noqa: E402

KEY = bytes.fromhex("113c9be4cb05413189b77a2940e85a1b0d78a7e0172248ac8fe32d75fad67665")
ACC = Path(r"C:\Users\liujinhao\Documents\xwechat_files\wxid_cufzf1yemb4e22_1e22")
SRC = ACC / "db_storage" / "sns" / "sns.db"
TMP = WS / "tools" / "tmp" / "decrypted"
OUT = WS / "wechat-ingest"
TMP.mkdir(parents=True, exist_ok=True)
OUT.mkdir(exist_ok=True)
ME = "wxid_cufzf1yemb4e22"

print("源 sns.db:", round(SRC.stat().st_size / 1024 / 1024, 2), "MB",
      "| mtime", datetime.fromtimestamp(SRC.stat().st_mtime))

dst = TMP / "sns2.db"
ok = False
try:
    ok = wechat_db._decrypt_db_v4(SRC, KEY, dst)
except Exception:  # noqa: BLE001
    traceback.print_exc()
if not ok:
    ok = wechat_db._decrypt_db_v4_snapshot(SRC, KEY, dst)
print("解密:", ok)
if not ok:
    sys.exit(1)

conn = sqlite3.connect(str(dst))
rows = conn.execute("SELECT tid, user_name, content FROM SnsTimeLine").fetchall()
print("时间线条目:", len(rows))

recs = []
for tid, user, content in rows:
    if not content:
        continue
    m = re.search(r"<createTime>(\d+)</createTime>", content)
    if not m:
        continue
    try:
        dt = datetime.fromtimestamp(int(m.group(1)))
    except Exception:  # noqa: BLE001
        continue
    recs.append((dt, user or "", content))
recs.sort()

mine = [(dt, c) for dt, u, c in recs if u.startswith(ME[:10])]
print("我的帖子:", len(mine), "| 范围:", mine[0][0].date() if mine else "-", "~",
      mine[-1][0].date() if mine else "-")


def tag(xml, name, default=""):
    m = re.search(rf"<{name}[^>]*>(.*?)</{name}>", xml, re.S)
    return m.group(1).strip() if m else default


posts = []
for dt, content in mine:
    text = tag(content, "contentDesc")
    n_media = content.count("<media>")
    lat = re.search(r'latitude="([\d.\-]+)"', content)
    loc = bool(lat and lat.group(1) not in ("0", "0.0"))
    ctype = tag(content, "type")
    posts.append({"time": dt.strftime("%Y-%m-%d %H:%M"), "date": dt.strftime("%Y-%m-%d"),
                  "text": text, "media": n_media, "has_location": loc, "content_type": ctype})

(OUT / "moments.json").write_text(json.dumps(posts, ensure_ascii=False, indent=1), encoding="utf-8")

by_year = Counter(p["time"][:4] for p in posts)
texts = [p["text"] for p in posts if p["text"]]
print("\n按年:", dict(sorted(by_year.items())))
print("有文字:", len(texts), "| 纯图:", len(posts) - len(texts))

# 全部条目（含好友）范围
print("全部缓存范围:", recs[0][0].date(), "~", recs[-1][0].date())
conn.close()

lines = ["# 我的朋友圈（全量）", "",
         f"> 共 {len(posts)} 条，{posts[0]['date']} ~ {posts[-1]['date']}", ""]
for p in posts:
    flags = []
    if p["media"]:
        flags.append(f"图×{p['media']}")
    if p["has_location"]:
        flags.append("定位")
    t = p["text"].replace("\n", " ")
    lines.append(f"- **{p['date']}** {t}" + (f"（{'·'.join(flags)}）" if flags else ""))
(OUT / "moments-self.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
print("\n写完 moments.json / moments-self.md")
