# -*- coding: utf-8 -*-
"""第二版合并：按「主题」归并 12 个分片的结论，渲染到 staging 树（再由 robocopy 落库）。

主题同时决定落到哪篇笔记，解决第一版聚类失效（措辞不同、Jaccard 太低）的问题。
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

WS = Path(r"C:\Users\liujinhao\Documents\deepseek-harness\default-workspace")
VAULT = Path(r"C:\Users\liujinhao\Documents\Obsidian Vault")
STAGE = WS / "staging4"
BACKUP = WS / "vault-notes-backup"
FIND = WS / "wechat-ingest" / "findings"
STAGE.mkdir(parents=True, exist_ok=True)
BACKUP.mkdir(parents=True, exist_ok=True)

CONF = {"high": 3, "medium": 2, "low": 1}

TOPICS = [
    ("personality", "价值观与判断标准", "性格-核心价值观",
     ["价值观", "原则", "底线", "不能接受", "值得", "吃亏", "靠谱", "判断", "重要", "应该"]),
    ("personality", "钱与消费", "性格-核心价值观",
     ["钱", "贵", "便宜", "花", "省", "生活费", "买", "账单", "付费"]),
    ("personality", "表达与用词习惯", "性格-口头禅与语言特征",
     ["口头禅", "句式", "标点", "emoji", "表情", "语气", "开场", "结尾", "称呼", "用词", "短句", "长句"]),
    ("personality", "情绪与触发点", "性格-情绪模式",
     ["情绪", "生气", "开心", "烦", "焦虑", "压力", "炸", "崩", "爽", "难受", "兴奋", "委屈"]),
    ("personality", "社交偏好", "性格-社交偏好",
     ["群", "朋友", "社交", "独处", "一起", "约", "聚会", "同学", "舍友"]),
    ("personality", "兴趣与审美", "性格-兴趣与审美",
     ["游戏", "音乐", "动漫", "电影", "吃", "球", "玩", "看", "喜欢", "爱"]),
    ("personality", "自我认知", "性格-自我认知与他者印象",
     ["自己", "觉得我", "能力", "自信", "废物", "牛逼", "菜", "强", "评价"]),
    ("interaction", "默认沟通方式", "互动-默认沟通方式",
     ["回复", "消息", "语音", "电话", "打字", "秒回", "寒暄", "在吗"]),
    ("interaction", "关心与安慰方式", "互动-默认沟通方式",
     ["安慰", "别难过", "没事", "加油", "心疼", "照顾", "陪"]),
    ("interaction", "提问与质疑", "互动-提问与质疑",
     ["问", "为什么", "质疑", "反问", "确认", "追问", "反驳", "推回"]),
    ("interaction", "冲突应对", "互动-冲突应对",
     ["吵", "冲突", "道歉", "骂", "不理", "冷战", "翻脸", "生气地"]),
    ("interaction", "排斥与不做", "互动-排斥场景",
     ["讨厌", "受不了", "烦", "别", "绝不", "拉黑", "不想理", "回避"]),
    ("procedure", "学习方法", "程序-任务推进习惯",
     ["学习", "复习", "考试", "课", "作业", "背", "刷题", "绩点"]),
    ("procedure", "工具与技术偏好", "程序-工具与环境",
     ["软件", "电脑", "手机", "工具", "app", "AI", "脚本", "系统", "配置"]),
    ("procedure", "计划与推进", "程序-任务推进习惯",
     ["计划", "安排", "推进", "效率", "拖", "任务", "进度", "准备"]),
    ("procedure", "质量标准", "程序-验收与交付标准",
     ["标准", "检查", "改", "细节", "错", "完善", "完成度", "质量"]),
    ("procedure", "决策依据", "程序-决策依据",
     ["选择", "决定", "考虑", "权衡", "比较", "性价比", "想清楚"]),
    ("procedure", "求助与边界", "程序-边界与求助",
     ["帮", "请教", "自己搞", "不会", "求助", "问一下"]),
    ("procedure", "反模式", "程序-反模式清单",
     ["反感", "无语", "垃圾", "别这样", "讨厌", "受不了", "烦人"]),
]
DEFAULT_NOTE = {"personality": "性格-核心价值观", "interaction": "互动-默认沟通方式",
                "procedure": "程序-任务推进习惯"}


def load_items():
    items = {"personality": [], "interaction": [], "procedure": [], "memory": [], "conflicts": []}
    for f in sorted(FIND.glob("slice-*.json")):
        d = json.loads(f.read_text(encoding="utf-8"))
        for dim in ("personality", "interaction", "procedure"):
            items[dim].extend(d.get(dim, []))
        items["memory"].extend(d.get("memory", []))
        items["conflicts"].extend(d.get("conflicts", []))
    return items


def assign_topic(item):
    text = item["claim"] + " " + item.get("evidence", "")
    best, score = None, 0
    for dim, topic, note, kws in TOPICS:
        s = sum(1 for k in kws if k in text)
        if s > score:
            best, score = (topic, note), s
    return best


def dedupe(items):
    seen, out = set(), []
    for it in items:
        k = re.sub(r"\s", "", it.get("evidence", ""))[:40]
        if k in seen:
            continue
        seen.add(k)
        out.append(it)
    return out


def write_stage(rel: str, text: str):
    p = STAGE / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(text, encoding="utf-8")


items = load_items()
groups = {}
for dim in ("personality", "interaction", "procedure"):
    for it in items[dim]:
        t = assign_topic(it)
        note, topic = (t[1], t[0]) if t else (DEFAULT_NOTE[dim], "其他观察")
        groups.setdefault(note, {}).setdefault(topic, []).append(it)

summary = {}
for note, topics in groups.items():
    for topic, its in topics.items():
        its = dedupe(its)
        its.sort(key=lambda x: (-CONF.get(x["confidence"], 0), x.get("when", "")))
        summary.setdefault(note, {})[topic] = its[:6]


def render_lines(its):
    out = []
    for it in its:
        out.append(f"- **{it['claim'].strip()}**")
        out.append(f"    - 「{it['evidence'].strip()[:80]}」— {it['conversation']} · "
                   f"{(it['when'] or '')[:10]}（`{it['level']}`） #证据/{it['level']}")
    return out


updated = 0
for note, topics in summary.items():
    p = next(VAULT.rglob(note + ".md"), None)
    if p is None:
        print("找不到笔记:", note)
        continue
    shutil.copyfile(p, BACKUP / p.name)
    txt = p.read_text(encoding="utf-8")
    total = sum(len(v) for v in topics.values())
    body = [f"## 已确认（微信语料 · {total} 条结论）", "",
            "> 来源：本机微信主号 144,332 条消息 → 我发送的 26,988 条纯文本（2025-06 ~ 2026-10）。",
            "> 每条都附原话；`verbatim` = 原话直接证明。", ""]
    for topic, its in sorted(topics.items(), key=lambda kv: -len(kv[1])):
        body.append(f"### {topic}")
        body.append("")
        body += render_lines(its)
        body.append("")
    m1 = txt.find("## 已确认")
    m2 = txt.find("\n---\n\n> 以下为主观印象区")
    if m1 == -1 or m2 == -1:
        print("结构不匹配，跳过:", note)
        continue
    new = txt[:m1] + "\n".join(body) + txt[m2:]
    new = (new.replace("状态: 待填", "状态: 部分确认")
              .replace("证据: 待定", "证据: verbatim")
              .replace("  - 状态/待填", "  - 状态/部分确认"))
    rel = str(p.relative_to(VAULT))
    write_stage(rel, new)
    updated += 1
    print(f"staged {rel}: {total} 条 / {len(topics)} 主题")

# 记忆事件
events = dedupe(items["memory"])
events.sort(key=lambda e: (e.get("when") or ""))
tl = VAULT / "00 索引" / "索引-记忆时间线.md"
if tl.exists():
    shutil.copyfile(tl, BACKUP / tl.name)
    t = tl.read_text(encoding="utf-8")
    rows = ["", "## 微信语料中的事件（自动抽取）", "",
            "| 时间 | 事件 | 相关的人 | 内容 |", "|---|---|---|---|"]
    for e in events[:60]:
        rows.append(f"| {(e.get('when') or '')[:10]} | {e['event'][:40]} | {(e.get('people') or '')[:20]} | "
                    f"{(e.get('what') or '')[:50]} |")
    write_stage(str(tl.relative_to(VAULT)), t.rstrip() + "\n" + "\n".join(rows) + "\n")
    print("staged 时间线事件:", min(60, len(events)))

# 矛盾
cf = VAULT / "06 蒸馏" / "矛盾-待裁定.md"
if cf.exists():
    shutil.copyfile(cf, BACKUP / cf.name)
    t = cf.read_text(encoding="utf-8")
    rows, seen = [], set()
    for c in items["conflicts"]:
        k = c["a"][:20] + c["b"][:20]
        if k in seen:
            continue
        seen.add(k)
        rows.append(f"| W{len(rows)+1} | — | {c['a'][:50]}（{c['evidence_a'][:25]}） | "
                    f"{c['b'][:50]}（{c['evidence_b'][:25]}） | — | 待判 |")
        if len(rows) >= 20:
            break
    if rows:
        t = t.replace("| 1 |  |  |  |  | 待判 |",
                      "| 1 |  |  |  |  | 待判 |\n" + "\n".join(rows), 1)
    write_stage(str(cf.relative_to(VAULT)), t)
    print("staged 矛盾:", len(rows))

# 统计页
page = ["---", "维度: 蒸馏", "状态: 已生成", "tags:", "  - 维度/蒸馏", "  - 状态/已生成", "---", "",
        "# 抽取-统计", "",
        "> 语料：26,988 条我发送的纯文本消息（245 会话，2025-06 ~ 2026-10），12 片并行抽取。", "",
        "## 各笔记结论数", ""]
for note, topics in sorted(summary.items(), key=lambda kv: -sum(len(v) for v in kv[1].values())):
    n = sum(len(v) for v in topics.values())
    page.append(f"- [[{note}]]: {n} 条（{len(topics)} 主题）")
page += ["", "## 原始数量", "",
         f"- 性格与价值观：{len(items['personality'])} 条",
         f"- 互动风格：{len(items['interaction'])} 条",
         f"- 做事方式：{len(items['procedure'])} 条",
         f"- 重要事件：{len(items['memory'])} 条",
         f"- 矛盾：{len(items['conflicts'])} 条", "",
         "## 关联", "", "[[素材-微信-总览]] · [[蒸馏-进度看板]] · [[索引-证据与状态]]", "",
         "上级：[[永生中枢]]"]
write_stage("06 蒸馏/抽取-统计.md", "\n".join(page))
print("staged 统计页；共", updated, "篇维度笔记")
