---
状态: 已归档
---

# 10-工具脚本 · 说明

这里是把原始数据变成第二大脑的全套脚本，**可以重新跑**。

## 目录

| 文件 | 作用 |
|---|---|
| `wechat_ingest.py` | 微信导出（JSON/CSV/TXT）→ 统一 JSONL + 原话池 + 语言指纹 |
| `wechat_stats.py` | 更严格的清洗：只留纯文本、解析联系人名、生成 `self-text.md` / `fingerprint.md` |
| `make_slices.py` | 把 26,988 条原话切成 12 个分析片 |
| `merge_findings.py` / `merge_render.py` | 合并 12 个分片的抽取结果，按主题落到笔记 |
| `sns_extract.py` / `sns_extract2.py` | 解密后的朋友圈库 → `moments.json` / `moments-self.md` |
| `style_stats.py` | 语言指纹精细统计（标点、emoji、句尾、高频词） |
| `sns_why.py` | 朋友圈缓存覆盖范围诊断 |
| `keeper/` | 微信解密工具链封装（chatlog-keeper，源码安装，本地运行） |

## 环境

- Python 3.12（脚本在 venv 里跑过；依赖：`pycryptodome`、`numpy`、`zstandard`）
- 微信解密用 `chatlog-keeper`，源码在 `08-语料` 之外单独保留于 `keeper/` 说明

## 注意

- 脚本里出现的 master key、路径、会话名都是**本机私有信息**，不要外传
- `keeper/wechat-export.ps1` 会重启微信以取 key，属中高风险操作，只在需要增量导出时用

## 重新导出的最小步骤

1. 手机微信「迁移聊天记录到电脑」（历史才会到 PC）
2. PC 微信登录目标号
3. 运行 `keeper/export-wechat.ps1 -Method targeted`（会拉起被调试的微信，扫码）
4. 解密成功后运行 `export_local.py` → `wechat_stats.py` → `make_slices.py`
5. 12 个分片交给 LLM 抽取，再用 `merge_render.py` 落库

上级：[[00-从这里开始]]
