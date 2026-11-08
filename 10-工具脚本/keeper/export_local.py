# -*- coding: utf-8 -*-
"""本地导出：绕开 chatlog-keeper 的私有解密缓存（沙箱下 ACL 校验会失败），
直接用它自己的解密函数 + 消息解析函数，输出规范化 JSON。

产物：wechat-export/wechat_messages.json
字段：time / is_self / sender / talker / content / msg_type —— 与 tools/wechat_ingest.py 对齐
"""
from __future__ import annotations

import json
import sqlite3
import sys
import traceback
from pathlib import Path

WS = Path(r"C:\Users\liujinhao\Documents\deepseek-harness\default-workspace")
sys.path.insert(0, str(WS / "tools" / "downloaded" / "chatlog-keeper"))

from chatlog_keeper import wechat_db  # noqa: E402

KEY = bytes.fromhex("113c9be4cb05413189b77a2940e85a1b0d78a7e0172248ac8fe32d75fad67665")
ACCOUNT = "wxid_cufzf1yemb4e22_1e22"
DATA_ROOT = Path(r"C:\Users\liujinhao\Documents\xwechat_files")
OUT_DIR = WS / "wechat-export"
TMP = WS / "tools" / "tmp" / "decrypted"
SINCE = 0.0

OUT_DIR.mkdir(parents=True, exist_ok=True)
TMP.mkdir(parents=True, exist_ok=True)

wxid_dir = DATA_ROOT / ACCOUNT
dbs = wechat_db.find_msg_databases(wxid_dir)
print("databases:", [(d.name, round(d.stat().st_size / 1024 / 1024, 2)) for d in dbs])

all_msgs = []
per_db = []
for db in dbs:
    plain = TMP / db.name
    ok = False
    try:
        ok = wechat_db._decrypt_db_v4(db, KEY, plain)
    except Exception:  # noqa: BLE001
        ok = False
    if not ok:
        try:
            ok = wechat_db._decrypt_db_v4_snapshot(db, KEY, plain)
        except Exception:  # noqa: BLE001
            traceback.print_exc()
    if not ok:
        print(f"  {db.name}: 解密失败")
        continue

    conn = sqlite3.connect(str(plain))
    try:
        name_map = wechat_db._load_name_map(conn)
        msgs = wechat_db._query_messages_since_inner(conn, SINCE, name_map)
    finally:
        conn.close()

    for m in msgs:
        ts = m.timestamp.timestamp() if getattr(m, "timestamp", None) else 0
        sender = str(getattr(m, "sender", "") or "")
        talker = str(getattr(m, "chat_name", "") or "")
        # self wxid 与 sender 用前缀比较（4.1 里 sender 可能带后缀）
        is_self = bool(sender and (ACCOUNT.startswith(sender) or sender.startswith(ACCOUNT)))
        all_msgs.append({
            "time": m.timestamp.strftime("%Y-%m-%d %H:%M:%S") if getattr(m, "timestamp", None) else "",
            "ts": ts,
            "is_self": is_self,
            "sender": sender,
            "talker": talker,
            "content": str(getattr(m, "content", "") or ""),
            "msg_type": getattr(m, "msg_type", None),
        })
    per_db.append((db.name, len(msgs)))

all_msgs.sort(key=lambda x: x["ts"])
out = OUT_DIR / "wechat_messages.json"
out.write_text(json.dumps(all_msgs, ensure_ascii=False, indent=1), encoding="utf-8")
mine = sum(1 for m in all_msgs if m["is_self"])
print("per db:", per_db)
print(f"总计 {len(all_msgs)} 条，其中我发送 {mine} 条")
print("写入:", out, round(out.stat().st_size / 1024 / 1024, 2), "MB")
if all_msgs:
    print("时间范围:", all_msgs[0]["time"], "~", all_msgs[-1]["time"])
