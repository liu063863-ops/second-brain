# -*- coding: utf-8 -*-
"""看看朋友圈时间线的数据结构：我的帖子长什么样"""
import sqlite3
from datetime import datetime
from pathlib import Path

WS = Path(r"C:\Users\liujinhao\Documents\deepseek-harness\default-workspace")
DB = WS / "tools" / "tmp" / "decrypted" / "sns.db"
ME = "wxid_cufzf1yemb4e22_1e22"

conn = sqlite3.connect(str(DB))
print("=== 时间线 user_name 分布（前 10） ===")
for row in conn.execute("SELECT user_name, COUNT(*) c FROM SnsTimeLine GROUP BY user_name ORDER BY c DESC LIMIT 10"):
    print("  ", row)

print("\n=== 我的帖子数量 ===")
n = conn.execute("SELECT COUNT(*) FROM SnsTimeLine WHERE user_name LIKE ?", (ME[:10] + "%",)).fetchone()[0]
print("  ", n)

print("\n=== 前 3 条我的帖子（原始） ===")
for row in conn.execute("SELECT tid, content FROM SnsTimeLine WHERE user_name LIKE ? LIMIT 3", (ME[:10] + "%",)):
    print("TID:", row[0])
    print(str(row[1])[:1200])
    print("---")


def ts_from_tid(tid) -> str:
    try:
        v = int(tid)
        # 高 32 位是 unix 时间戳（秒）
        s = v >> 32
        if 1_400_000_000 < s < 2_000_000_000:
            return datetime.fromtimestamp(s).strftime("%Y-%m-%d %H:%M")
        s2 = v // 1_000_000_000
        if 1_400_000_000 < s2 < 2_000_000_000:
            return datetime.fromtimestamp(s2).strftime("%Y-%m-%d %H:%M")
    except Exception:  # noqa: BLE001
        pass
    return "?"


print("\n=== 我的帖子（时间 + 内容前 100） ===")
rows = conn.execute("SELECT tid, content FROM SnsTimeLine").fetchall()
mine = [(t, c) for (t, c) in rows if ME[:10] in str(c) or ME[:10] in str(t)]
print("匹配我的帖子:", len(mine))
for tid, content in mine[:12]:
    print(ts_from_tid(tid), "|", str(content)[:100].replace("\n", " "))
conn.close()
