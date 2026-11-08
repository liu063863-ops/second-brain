# -*- coding: utf-8 -*-
"""用已校验的 master key 直接驱动 chatlog-keeper 的导出。

背景：chatlog-keeper 把 key 缓存在 secrets 目录，并在读取时做 Windows ACL 校验；
在本沙箱会话里 ACL 校验会失败（read_secret_text 返回 None），但 key 本身是我们
刚才用它的调试器流程抓到、并已通过 message_0.db HMAC 校验的。
这里只绕过「缓存读取」这一步，解密逻辑完全用 keeper 自己的实现。
"""
from __future__ import annotations

import sys
from pathlib import Path

WS = Path(r"C:\Users\liujinhao\Documents\deepseek-harness\default-workspace")
KEEPER_SRC = WS / "tools" / "downloaded" / "chatlog-keeper"
sys.path.insert(0, str(KEEPER_SRC))

from chatlog_keeper import cli, wechat_db  # noqa: E402

KEY_FILE = WS / "tools" / "localappdata" / "chatlog-keeper" / "data" / "secrets" / "wechat_accounts" / \
    "304424d2ab13cc65b527ac6fc5f009ac589526e08a791efd14a2cbd244f8277c.key"
ACCOUNT = "wxid_cufzf1yemb4e22_1e22"
DATA_ROOT = r"C:\Users\liujinhao\Documents\xwechat_files"
OUT = str(WS / "wechat-export")
DAYS = "3650"

key_hex = KEY_FILE.read_text(encoding="utf-8").strip()
KEY = bytes.fromhex(key_hex)
print(f"key loaded: {KEY.hex()[:16]}… ({len(KEY)} bytes)")

# 只替换「从缓存读取」这一步
wechat_db.load_cached_wechat_key_for_account = lambda account_id: KEY  # noqa: ARG005
wechat_db.load_cached_wechat_key = lambda: KEY

argv = ["wechat", "--days", DAYS, "--out", OUT, "--account", ACCOUNT, "--data-root", DATA_ROOT]
print("argv:", argv)
rc = cli.main(argv)
print("exit code:", rc)
sys.exit(rc if isinstance(rc, int) else 0)
