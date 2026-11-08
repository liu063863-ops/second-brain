# -*- coding: utf-8 -*-
"""微信导出文件 → 蒸馏素材（verbatim 池）

用法：
    python wechat_ingest.py <导出文件或目录> [-o 输出目录]

支持自动识别：
  1. chatlog 的 JSON（/api/v1/chatlog?format=json）
  2. chatlog 的 CSV（format=csv）
  3. MemoTrace / 留痕 的 CSV（发送者,内容,时间）
  4. chatlog / 通用 TXT（"YYYY-MM-DD HH:MM:SS 发送者" 换行 内容）

输出（默认 ./wechat-ingest/）：
  messages.jsonl   全量规范化消息（含对方，用于研究互动）
  self-said.md     只含「我」发的消息，按会话分组 —— 直接喂给蒸馏
  fingerprint.md   语言指纹初稿：句长、标点、emoji、高频二/三字词、高频开场
  report.txt       识别到的格式与统计
"""
from __future__ import annotations

import argparse
import csv
import io
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path

# ---------------- 字段识别 ----------------

TIME_KEYS = ["time", "createTime", "create_time", "timestamp", "ts", "时间", "日期"]
SELF_KEYS = ["isSelf", "is_self", "isSender", "is_sender", "self", "是否自己发送", "发送方向"]
TEXT_KEYS = ["content", "text", "msg", "strContent", "消息", "内容"]
SENDER_KEYS = ["senderName", "sender", "talkerName", "nickname", "发送者", "昵称", "备注"]
TALKER_KEYS = ["talker", "channel", "session", "strTalker", "会话", "聊天对象"]

NOISE = re.compile(
    r"^\[(图片|表情|语音|视频|文件|链接|动画表情|位置|转账|红包|小程序|视频号|接龙|聊天记录|"
    r"音乐|名片|引用|收藏|拍一拍|礼物|直播|卡券|订单|群公告)\]?$"
)
SYSTEM_HINT = ("撤回了一条消息", "加入了群聊", "邀请", "修改群名为", "拍了拍", "已成为新成员")


def pick(d: dict, keys) -> object:
    for k in keys:
        if k in d and d[k] not in (None, ""):
            return d[k]
    lower = {str(k).lower(): v for k, v in d.items()}
    for k in keys:
        if k.lower() in lower and lower[k.lower()] not in (None, ""):
            return lower[k.lower()]
    return None


def norm_time(v) -> str:
    if v is None:
        return ""
    if isinstance(v, (int, float)) or (isinstance(v, str) and v.isdigit()):
        n = int(v)
        if n > 10_000_000_000:  # 毫秒
            n //= 1000
        try:
            return datetime.fromtimestamp(n).strftime("%Y-%m-%d %H:%M:%S")
        except (OSError, ValueError):
            return str(v)
    s = str(v).strip().replace("T", " ").replace("Z", "")
    return s[:19]


class Msg(dict):
    @property
    def is_self(self) -> bool:
        return bool(self.get("is_self"))


def make_msg(time, sender, text, is_self, talker, source) -> Msg | None:
    text = (text or "").strip()
    if not text or NOISE.match(text):
        return None
    if any(h in text for h in SYSTEM_HINT) and not is_self:
        return None
    return Msg(time=norm_time(time), sender=str(sender or ""), text=text,
               is_self=bool(is_self), talker=str(talker or ""), source=source)


# ---------------- 各格式解析 ----------------

def parse_json(raw: str, source: str) -> list[Msg]:
    data = json.loads(raw)
    if isinstance(data, dict):
        for k in ("messages", "data", "list", "items", "rows"):
            if isinstance(data.get(k), list):
                data = data[k]
                break
        else:
            data = [data]
    out = []
    for item in data:
        if not isinstance(item, dict):
            continue
        text = pick(item, TEXT_KEYS)
        sender = pick(item, SENDER_KEYS)
        talker = pick(item, TALKER_KEYS) or sender
        is_self = pick(item, SELF_KEYS)
        if is_self is None:
            is_self = str(sender or "") in ("我", "self", "me")
        out.append(make_msg(pick(item, TIME_KEYS), sender, text, bool(is_self), talker, source))
    return [m for m in out if m]


def parse_csv(raw: str, source: str) -> list[Msg]:
    reader = csv.DictReader(io.StringIO(raw))
    fields = reader.fieldnames or []
    if not fields:
        return []
    out = []
    for row in reader:
        text = pick(row, TEXT_KEYS)
        sender = pick(row, SENDER_KEYS)
        talker = pick(row, TALKER_KEYS) or sender
        is_self = pick(row, SELF_KEYS)
        if is_self is None:
            is_self = str(sender or "").strip() in ("我", "self", "me", "1", "True")
        out.append(make_msg(pick(row, TIME_KEYS), sender, text, bool(is_self), talker, source))
    if not any(m for m in out):
        raise ValueError(f"CSV 表头无法识别：{fields}")
    return [m for m in out if m]


TXT_HEAD = re.compile(r"^(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}(?::\d{2})?)\s+(.+?)\s*$")


def parse_txt(raw: str, source: str) -> list[Msg]:
    out, cur_t, cur_s, buf = [], "", "", []

    def flush():
        if buf and cur_s:
            out.append(make_msg(cur_t, cur_s, "\n".join(buf), cur_s in ("我", "self"), cur_s, source))

    for line in raw.splitlines():
        m = TXT_HEAD.match(line)
        if m:
            flush()
            cur_t, cur_s, buf = m.group(1), m.group(2).strip(), []
        elif line.strip():
            buf.append(line.strip())
    flush()
    return [m for m in out if m]


# ---------------- 指纹统计 ----------------

EMOJI = re.compile("[\U0001F300-\U0001FAFF\u2600-\u27BF]")
PUNCT = re.compile(r"[，。！？…~、；：\-—【】（）()\"'“”‘’]+")


def fingerprint(msgs: list[Msg]) -> str:
    mine = [m for m in msgs if m.is_self]
    if not mine:
        return "# 语言指纹\n\n（没有识别到「我」发送的消息，请检查 self 判定）\n"
    texts = [m["text"] for m in mine]
    lens = [len(t) for t in texts]
    emo = Counter(ch for t in texts for ch in EMOJI.findall(t))
    pun = Counter(ch for t in texts for ch in PUNCT.findall(t))
    # 中文二/三字串频次（无分词依赖的粗略口头禅候选）
    grams = Counter()
    for t in texts:
        t2 = re.sub(r"[^\u4e00-\u9fff]", " ", t)
        for seg in t2.split():
            for n in (2, 3):
                for i in range(len(seg) - n + 1):
                    grams[seg[i:i + n]] += 1
    opens = Counter(t[:4] for t in texts if len(t) >= 4)
    emo_lines = [f"- {k} × {v}" for k, v in emo.most_common(10)] or ["- （几乎不用 emoji）"]
    lines = [
        "# 语言指纹初稿（自动统计）", "",
        f"- 「我」的消息：{len(mine)} 条 / 全部 {len(msgs)} 条",
        f"- 平均句长：{sum(lens)/len(lens):.1f} 字（最长 {max(lens)}，最短 {min(lens)}）",
        f"- 单条 5 字以内占比：{sum(1 for l in lens if l <= 5)/len(lens):.0%}",
        "", "## 标点习惯", "",
        *[f"- `{k}` × {v}" for k, v in pun.most_common(10)],
        "", "## emoji 使用", "",
        *emo_lines,
        "", "## 高频二/三字串（口头禅候选，需人工筛）", "",
        *[f"- {k} × {v}" for k, v in grams.most_common(30)],
        "", "## 高频开场", "",
        *[f"- 「{k}…」 × {v}" for k, v in opens.most_common(10)],
    ]
    return "\n".join(lines) + "\n"


def self_said(msgs: list[Msg], limit_per_talker: int = 400) -> str:
    by: dict[str, list[Msg]] = {}
    for m in msgs:
        if m.is_self:
            by.setdefault(m["talker"] or "未知会话", []).append(m)
    out = ["# 我说过的话（自动抽取 · verbatim 池）", "",
           "> 只含「我」发送的消息，按会话分组。可直接拆进 [[性格-口头禅与语言特征]] / [[互动-默认沟通方式]]。", ""]
    for talker, items in sorted(by.items(), key=lambda x: -len(x[1])):
        items = items[-limit_per_talker:]
        out += [f"## {talker}（{len(items)} 条）", ""]
        out += [f"- `{m['time'][:16]}` {m['text']}" for m in items]
        out.append("")
    return "\n".join(out)


# ---------------- 主流程 ----------------

def load(path: Path) -> list[Msg]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    suffix = path.suffix.lower()
    if suffix == ".json":
        return parse_json(raw, path.name)
    if suffix == ".csv":
        return parse_csv(raw, path.name)
    if suffix in (".txt", ".md", ".log"):
        return parse_txt(raw, path.name)
    raise ValueError(f"不支持的扩展名：{suffix}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("-o", "--out", default="wechat-ingest")
    args = ap.parse_args()

    src = Path(args.input)
    files = [src] if src.is_file() else sorted(
        [p for p in src.rglob("*") if p.suffix.lower() in (".json", ".csv", ".txt", ".md", ".log")])
    if not files:
        print("没有找到可解析文件", file=sys.stderr)
        return 1

    all_msgs: list[Msg] = []
    report = []
    for f in files:
        try:
            got = load(f)
            all_msgs += got
            report.append(f"  {f.name}: {len(got)} 条")
        except Exception as e:  # noqa: BLE001
            report.append(f"  {f.name}: 解析失败 - {e}")

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "messages.jsonl").open("w", encoding="utf-8") as fh:
        for m in all_msgs:
            fh.write(json.dumps(m, ensure_ascii=False) + "\n")
    (out_dir / "self-said.md").write_text(self_said(all_msgs), encoding="utf-8")
    (out_dir / "fingerprint.md").write_text(fingerprint(all_msgs), encoding="utf-8")
    mine = sum(1 for m in all_msgs if m.is_self)
    (out_dir / "report.txt").write_text(
        "\n".join(["解析结果：", *report, "",
                   f"总计 {len(all_msgs)} 条，其中我发送 {mine} 条",
                   f"时间范围：{min((m['time'] for m in all_msgs), default='')} ~ "
                   f"{max((m['time'] for m in all_msgs), default='')}"]),
        encoding="utf-8")
    print("\n".join(["解析结果：", *report, "",
                     f"总计 {len(all_msgs)} 条，我发送 {mine} 条",
                     f"输出目录：{out_dir.resolve()}"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
