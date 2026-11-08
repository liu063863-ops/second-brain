# -*- coding: utf-8 -*-
"""解密 sns.db（朋友圈）并看看里面有什么"""
import sqlite3
import sys
import traceback
from pathlib import Path

WS = Path(r"C:\Users\liujinhao\Documents\deepseek-harness\default-workspace")
sys.path.insert(0, str(WS / "tools" / "downloaded" / "chatlog-keeper"))
from chatlog_keeper import wechat_db  # noqa: E402

KEY = bytes.fromhex("113c9be4cb05413189b77a2940e85a1b0d78a7e0172248ac8fe32d75fad67665")
ACC = Path(r"C:\Users\liujinhao\Documents\xwechat_files\wxid_cufzf1yemb4e22_1e22")
TMP = WS / "tools" / "tmp" / "decrypted"
TMP.mkdir(parents=True, exist_ok=True)

src = ACC / "db_storage" / "sns" / "sns.db"
print("源文件:", src, src.stat().st_size / 1024 / 1024, "MB")
dst = TMP / "sns.db"
ok = False
try:
    ok = wechat_db._decrypt_db_v4(src, KEY, dst)
except Exception:  # noqa: BLE001
    traceback.print_exc()
if not ok:
    ok = wechat_db._decrypt_db_v4_snapshot(src, KEY, dst)
print("解密:", ok)
if not ok:
    sys.exit(1)

conn = sqlite3.connect(str(dst))
tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")]
print("\n表:", tables)
for t in tables:
    try:
        n = conn.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
        cols = [r[1] for r in conn.execute(f'PRAGMA table_info("{t}")')]
        print(f"  {t}: {n} 行 | {cols[:12]}")
    except sqlite3.Error as e:
        print("  ", t, "ERR", e)
conn.close()
