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
DEGEN = os.path.join(HERE, "degenerate_r_1031.json")
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
    g = json.load(open(DEGEN, encoding="utf-8"))
    rows = d["逐链"]
    s = d["汇总"]

    # ★★★ 退化 R:爆掉的链,基准一一律**不出数**(不许把 −3.1e9 当成一个数渲染)
    blown = {x["链"]: x["值"]
             for x in g["★基准一数值已经爆掉(|值| > 10)的链"]}
    degen = {r["链"]: r for r in g["逐链"]}

    # ★ 去重:同笔数 + 同基准一值 = 同一份配置换了个批次标签
    fp = {}
    for r in rows:
        k = (r["笔数"], round(r["★新基准一值"], 12)
             if r.get("★新基准一值") is not None else None)
        fp.setdefault(k, []).append(r["链"])
    dup_groups = {k: v for k, v in fp.items() if len(v) > 1}
    first_of = {v[0] for v in fp.values()}

    L = []
    L.append("# 基准一重跑 · 逐链表 · 1031\n")
    L.append("> ★ 口径:研发池 {} 只 × 大+中(rank ≤ 2000)· 50 个写死种子 · "
             "对照组同池 · 容差 ±5% 硬断言\n".format(
                 d["口径戳"]["★研发池只数"]))
    L.append("> ★ 留出池 {} 只(SHA-256 `{}`)**本轮一笔都没跑**\n".format(
        d["口径戳"]["★留出池只数"], d["口径戳"]["★留出池SHA256"][:16] + "…"))

    # ── 表一 · 逐链
    L.append("\n## 表一 · 逐链(★ 对照组实际笔数偏差逐条报出 —— 这是本轮存在的理由)\n")
    L.append("| # | 链 | 笔数 | 旧笔数 | **新基准一** | **★对照笔数偏差** | "
             "旧对照偏差 | 旧基准一(作废) | 和旧值的差 | 符号翻转 | 无止损 | 重复 | 秒 |")
    L.append("|--:|---|--:|--:|--:|--:|--:|--:|--:|:-:|:-:|:-:|--:|")
    for i, r in enumerate(rows, 1):
        if r.get("★跑不了"):
            L.append(f"| {i} | {r['链']} | — | — | **★跑不了** | — | — | — | — | — | — | — | — |")
            continue
        b1 = r.get("★新基准一值")
        broke = bool(r.get("★前提破了_禁止下游"))
        bl = r["链"] in blown
        dupmark = ("★副本" if r["链"] not in first_of else "—")
        if bl:
            cell = "**★退化R·不出数**"
            diff = flip = "—"
        elif broke:
            cell = "**★前提破裂·不出数**"
            diff = flip = "—"
        else:
            cell = f"**{f(b1)}**"
            diff = f(r.get("★和旧值的差"))
            flip = f(r.get("★符号是否翻转"))
        L.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            i, r["链"], r.get("笔数"), r.get("旧笔数(全大中池)") or "—",
            cell,
            ("—" if broke else pc(r.get("★对照笔数偏差"))),
            pc(r.get("旧对照笔数偏差")),
            f(r.get("旧基准一(作废·仅用于看污染有多大)")),
            diff, flip,
            ("★是" if r.get("★无止损_R退化成收益率_不可和有止损同列排序") else "否"),
            dupmark,
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

    # ── 表三 · 退化 R
    L.append("\n## 表三 · ★★★ 新查出的第三处缺陷:退化 R\n")
    L.append(f"> 判据(★ XING 填的,不是原著):{g['判据(★ XING 填的,不是原著)']}\n")
    L.append(f"- 45 条里**至少有一笔退化 R** 的:**{g['★基准一不可用的链数']} 条**")
    L.append(f"- 其中**数值已经被毁掉**(|基准一| > 10)的:**{len(blown)} 条** ——"
             f" 全部是技-10 族")
    L.append("- ★ **真链流水一笔退化都没有**,45 条全是对照组那边出的")
    L.append("\n| 链 | 原样(垃圾) | 剔掉退化笔后(参考,非结论) | 对照退化笔 |")
    L.append("|---|--:|--:|--:|")
    for n in sorted(blown):
        r = degen[n]
        L.append("| {} | {:.4e} | {} | {} / {} |".format(
            n, r["基准一_原样"],
            f(r["★剔掉退化笔之后的基准一(参考,不是结论)"]),
            r["对照流水"]["退化笔数"], r["对照流水"]["笔数"]))

    # ── 表四 · 重复
    L.append("\n## 表四 · ★★ 45 条里只有 {} 份独立结果({} 条是同配置换标签)\n".format(
        len(fp), len(rows) - len(fp)))
    L.append("| 笔数 | 基准一 | 份数 | 链 |")
    L.append("|--:|--:|--:|---|")
    for k, v in sorted(dup_groups.items(), key=lambda x: -len(x[1])):
        L.append("| {} | {} | ×{} | {} |".format(
            k[0], (f"{k[1]:.4e}" if k[1] is not None and abs(k[1]) > 10
                   else f(k[1])), len(v), "<br>".join(v)))

    if s["符号翻转名单"]:
        real = [n for n in s["符号翻转名单"] if n not in blown]
        distinct, seen = [], set()
        for r in rows:
            if r["链"] in real:
                k = (r["笔数"], round(r["★新基准一值"], 12))
                if k not in seen:
                    seen.add(k)
                    distinct.append(r["链"])
        L.append("\n### 符号翻转:三个数要分开看\n")
        L.append(f"- 机械计数:**{len(s['符号翻转名单'])} 条**")
        L.append(f"- 减掉「数值已被退化 R 毁掉、翻转无意义」的 {len(blown)} 条 → "
                 f"**{len(real)} 条**")
        L.append(f"- 再去掉重复标签 → **★★★ {len(distinct)} 条**(这是该写进结论的数)\n")
        for n in distinct:
            r = next(x for x in rows if x["链"] == n)
            L.append(f"- {n} —— 旧 {f(r['旧基准一(作废·仅用于看污染有多大)'])} → "
                     f"新 {f(r['★新基准一值'])}(差 {f(r['★和旧值的差'])})")
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
