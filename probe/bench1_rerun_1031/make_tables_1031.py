#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 把 bench1_rerun_1031.json 变成报告里那几张表(md)。只读,不重算。"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "bench1_rerun_1031.json")
HOLD = os.path.join(HERE, "holdout_1031.json")
OUT = os.path.join(HERE, "表-逐链-1031.md")


def f(x, nd=4):
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "是" if x else "否"
    try:
        return f"{float(x):+.{nd}f}"
    except (TypeError, ValueError):
        return str(x)


def pc(x, nd=2):
    if x is None:
        return "—"
    try:
        return f"{float(x)*100:+.{nd}f}%"
    except (TypeError, ValueError):
        return str(x)


def main() -> int:
    d = json.load(open(SRC, encoding="utf-8"))
    h = json.load(open(HOLD, encoding="utf-8"))
    rows = d["逐链"]
    s = d["汇总"]

    L = []
    L.append("# 基准一重跑 · 逐链表 · 1031\n")
    L.append("> ★ 口径:研发池 %d 只 × 大+中(rank ≤ 2000)· 50 个写死种子 · "
             "对照组同池 · 容差 ±5% 硬断言\n"
             % d["口径戳"]["★研发池只数"])
    L.append("> ★ 留出池 %d 只(SHA-256 `%s`)**本轮一笔都没跑**\n"
             % (d["口径戳"]["★留出池只数"], d["口径戳"]["★留出池SHA256"][:16] + "…"))

    # ── 表一 · 逐链
    L.append("\n## 表一 · 逐链(★ 对照组实际笔数偏差逐条报出 —— 这是本轮存在的理由)\n")
    L.append("| # | 链 | 笔数 | 旧笔数 | **新基准一** | **★对照笔数偏差** | "
             "旧对照偏差 | 旧基准一(作废) | 和旧值的差 | 符号翻转 | 无止损 | 秒 |")
    L.append("|--:|---|--:|--:|--:|--:|--:|--:|--:|:-:|:-:|--:|")
    for i, r in enumerate(rows, 1):
        if r.get("★跑不了"):
            L.append(f"| {i} | {r['链']} | — | — | **★跑不了** | — | — | — | — | — | — | — |")
            continue
        b1 = r.get("★新基准一值")
        broke = bool(r.get("★前提破了_禁止下游"))
        L.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            i, r["链"], r.get("笔数"), r.get("旧笔数(全大中池)") or "—",
            ("**★前提破裂·不出数**" if broke else f"**{f(b1)}**"),
            ("—" if broke else pc(r.get("★对照笔数偏差"))),
            pc(r.get("旧对照笔数偏差")),
            f(r.get("旧基准一(作废·仅用于看污染有多大)")),
            f(r.get("★和旧值的差")),
            f(r.get("★符号是否翻转")),
            ("★是" if r.get("★无止损_R退化成收益率_不可和有止损同列排序") else "否"),
            r.get("耗时秒")))

    # ── 表二 · 汇总
    L.append("\n## 表二 · 四个必报的数\n")
    L.append("| 问题 | 实测 |")
    L.append("|---|---|")
    L.append(f"| 留出池里其实我们已经跑过多少只 | **{h['★★★留出池里其实已经跑过的只数']} / "
             f"{h['★★★留出池只数']}({h['★★★留出池里其实已经跑过的比例']*100:.0f}%)** |")
    L.append(f"| 几条链符号翻转了 | **{s['★符号翻转的']} / {s['链数']}** |")
    L.append(f"| 几条链算不出基准一(前提破裂) | **{s['★前提破裂_算不出基准一的']} / {s['链数']}** |")
    L.append(f"| 几条链跑不了(异常) | {s['跑不了的']} / {s['链数']} |")
    L.append(f"| 对照笔数偏差 最大绝对值 | {abs(s['★对照笔数偏差_最大绝对值'])*100:.2f}%"
             f"(容差 ±5%) |")
    L.append(f"| 无止损(R 退化成收益率,不可和有止损同列排序) | "
             f"{s['★无止损(R退化成收益率)的链数']} 条 |")
    L.append(f"| 总耗时 | {d['总耗时秒']:.0f} 秒 |")

    if s["符号翻转名单"]:
        L.append("\n### 符号翻转的链\n")
        for n in s["符号翻转名单"]:
            r = next(x for x in rows if x["链"] == n)
            L.append(f"- {n} —— 旧 {f(r['旧基准一(作废·仅用于看污染有多大)'])} → "
                     f"新 {f(r['★新基准一值'])}")
    if s["前提破裂名单"]:
        L.append("\n### 算不出基准一的链(★ 新断言在正确工作)\n")
        for n in s["前提破裂名单"]:
            r = next(x for x in rows if x["链"] == n)
            L.append(f"- {n}(真链 {r['笔数']} 笔)")
    if s.get("★无止损名单(不可和有止损同列排序)"):
        L.append("\n### 无止损的链(1R = 进场价 → R 退化成收益率)\n")
        for x in s["★无止损名单(不可和有止损同列排序)"]:
            L.append(f"- {x['链']} —— {x['怎么判的']}")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    try:
        print(f"写出 {OUT}")
        print("\n".join(L[-40:]))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
