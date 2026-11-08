# -*- coding: utf-8 -*-
"""核查：朋友圈缓存时间范围、sns.db 文件时间、能否补全"""
import os
import re
import sqlite3
from collections import Counter
from datetime import datetime
from pathlib import Path

WS = Path(r"C:\Users\liujinhao\Documents\deepseek-harness\default-workspace")
DB = WS / "tools" / "tmp" / "decrypted" / "sns.db"
SRC = Path(r"C:\Users\liujinhao\Documents\xwechat_files\wxid_cufzf1yemb4e22_1e22\db_storage\sns\sns.db")
ME = "wxid_cufzf1yemb4e22"

conn = sqlite3.connect(str(DB))
rows = conn.execute("SELECT tid, user_name, content FROM SnsTimeLine").fetchall()
print("时间线条目:", len(rows))

recs = []
for tid, user, content in rows:
    m = re.search(r"<createTime>(\d+)</createTime>", content or "")
    if not m:
        continue
    dt = datetime.fromtimestamp(int(m.group(1)))
    recs.append((dt, user))
recs.sort()
print("整体时间范围:", recs[0][0].date(), "~", recs[-1][0].date())
mine = [d for d, u in recs if (u or "").startswith(ME[:10])]
print("我的帖子:", len(mine), "| 范围:", mine[0].date(), "~", mine[-1].date())

by_month_all = Counter(d.strftime("%Y-%m") for d, _ in recs)
by_month_mine = Counter(d.strftime("%Y-%m") for d in mine)
print("\n按月（全部缓存条目 / 其中我的）：")
for m in sorted(by_month_all):
    print(f"  {m}: {by_month_all[m]:3d} / {by_month_mine.get(m,0)}")

print("\n文件时间：")
for p in (SRC, DB, SRC.parent):
    st = p.stat()
    print(f"  {p.name}: mtime={datetime.fromtimestamp(st.st_mtime)}, ctime={datetime.fromtimestamp(st.st_ctime)}")

# 账号目录创建时间
acc = Path(r"C:\Users\liujinhao\Documents\xwechat_files\wxid_cufzf1yemb4e22_1e22")
print("\n账号目录:", datetime.fromtimestamp(acc.stat().st_ctime))
conn.close()
