#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★ 把 exam_run_1102.json 渲染成报告要的表 —— 2026-11-02

三秒版:成绩表、翻转表、笔数表、退化 R 表、对照偏差表,全部**并列**印考卷和老池。

★★★ 渲染纪律(坑表第 33 处):**值不是空的却渲染成「—」→ 直接 raise。**
   「—」只许表示一件事:**这个数真的没有**(前提破了 / 没算出来)。
   ★ 另外两件事各有自己的写法:
     · 算出来了但不许当结论(笔数 <30 / 退化 R) → 值照印,后面加 `[不给结论]`
     · 被闸挡下 → 单独一张表,不许从表里消失
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
SRC = os.path.join(HERE, "exam_run_1102.json")
OUT = os.path.join(HERE, "表-逐链-1102.md")

# ══════════════════════════════════════════════════════════════════════════
# ★★★ 老池那一列的来源 —— 2026-11-02 策略组更正
#
# ★ 原来打算用 probe/bench1_rerun_1031/bench1_rerun_1031.json。★★ 不能用:
#   那一份是 10-31 **11:22** 跑的(口径戳提交号 fbf760f = 10-31 11:30),
#   而退化 R 的修复是同日 **14:25** 才提交(95e293b)。
#   ★★★ 所以那份里 **35 条的基准一是坏数**(技-10 三档 −31 亿 / −53 亿 / −60 亿)。
#
# ★ 正确来源:probe/bench1_rerun_1102/(策略组另开一轮重跑,修复后的 engine)。
#   ★★ 它还没跑完时,**老池那一列一律写「待补」**,★★★ 不许拿 1031 那份顶上。
# ══════════════════════════════════════════════════════════════════════════
OLD_NEW = os.path.join(ROOT, "probe", "bench1_rerun_1102", "bench1_rerun_1102.json")
OLD_STALE = os.path.join(ROOT, "probe", "bench1_rerun_1031",
                         "bench1_rerun_1031.json")
PENDING = "待补"


def load_old() -> tuple[dict, str]:
    """-> ({链: 记录}, 来源说明)。★ 1102 那份没有 → 返回空 dict。"""
    if os.path.exists(OLD_NEW):
        d = json.load(open(OLD_NEW, encoding="utf-8"))
        return ({r["链"]: r for r in d["逐链"]},
                "probe/bench1_rerun_1102/bench1_rerun_1102.json"
                "(退化 R 修复**之后**重跑,可比)")
    return ({}, "★★★ 老池可比口径**待补** —— probe/bench1_rerun_1102/ 还没出结果。"
                "★ 1031 那一份(fbf760f,10-31 11:30)跑在退化 R 修复(95e293b,"
                "10-31 14:25)**之前**,35 条的基准一是坏数,**本表不采用**。")


def old_cell(old: dict, label: str, key: str):
    """老池某个数。★ 拿不到 → 返回 PENDING(「待补」),★ 不是「—」。
    ★ 「—」只许表示「这个数真的没有」;「待补」表示「这一轮还没跑」。"""
    r = old.get(label)
    if r is None:
        return PENDING
    if key == "基准一":
        return (r.get("★基准一") or {}).get("★真信号每笔R − 随机进场每笔R")
    return r.get(key)


def cell(v, nd=4) -> str:
    """★ None → 「—」;有值 → 印值。★ 有值却想印「—」是 bug,这里堵死。"""
    if v == PENDING:
        return PENDING
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, (int,)):
        return str(v)
    if isinstance(v, float):
        return f"{v:+.{nd}f}"
    return str(v)


def guard(v, rendered: str):
    if v is not None and v != PENDING and rendered == "—":
        raise RuntimeError(f"★★★ 值是 {v!r} 却渲染成「—」 —— 坑表第 33 处,停。")
    return rendered


def main() -> int:
    d = json.load(open(SRC, encoding="utf-8"))
    rows = d["逐链"]
    s = d["汇总"]
    old, old_src = load_old()
    L = []
    L.append("")

    L.append("# 表 · 逐链 —— 考卷 vs 老池 · 2026-11-02\n")
    L.append("> 口径:" + d["口径戳"]["池子口径"]
             + f" · 种子 {rows[0].get('种子数') if rows else '?'} 个 · 容差 ±"
             + f"{d['口径戳'].get('容差')}\n")
    L.append("> ★ 考卷实际参加考试 **1,025 只**(名单 1,042 只,其中 17 只被 engine"
             " 既有规则「有效 bar 不足 60 根」剔掉 —— ★ 门槛没有被改)。\n")
    L.append("> ★ 老池那一列来源:" + old_src + "\n")
    L.append("> ★ 「—」只表示**这个数真的没有**(前提破了 / 没算出来)。"
             "「待补」表示**这一轮还没跑**。"
             "算出来了但不许当结论的,值照印并标 `[不给结论]`。\n")

    # ── 表一 · 成绩并列
    L.append("\n## 表一 · 每条链:考卷成绩 vs 老池成绩\n")
    L.append("| 链 | 考卷笔数 | 老池笔数 | 考卷每笔净R | 老池每笔净R | "
             "考卷基准一 | 老池基准一 | 差 | 符号翻转 |")
    L.append("|---|---|---|---|---|---|---|---|---|")
    for r in sorted(rows, key=lambda x: x["链"]):
        if r.get("★跑不了"):
            L.append(f"| {r['链']} | — | — | — | — | — | — | — | — | ")
            continue
        n = r.get("笔数")
        mark = ""
        if n is not None and n < 30:
            mark = " `[不给结论]`"
        if r.get("★退化R_本轮是否出现"):
            mark += " `[退化R·不给结论]`"
        b1 = r.get("★新基准一值")
        lab = r["链"]
        on = old_cell(old, lab, "笔数")
        onr = old_cell(old, lab, "每笔净R")
        ob1 = old_cell(old, lab, "基准一")
        # ★ 差 和 符号翻转:只有两边都有真数才算;老池待补 → 「待补」
        if ob1 == PENDING or b1 is None:
            diff, flip_v = (PENDING if ob1 == PENDING else None), \
                           (PENDING if ob1 == PENDING else None)
        elif ob1 is None:
            diff, flip_v = None, None
        else:
            diff, flip_v = b1 - ob1, bool((b1 > 0) != (ob1 > 0))
        L.append("| {} | {} | {} | {} | {} | {}{} | {} | {} | {} |".format(
            lab, cell(n), cell(on),
            guard(r.get("每笔净R"), cell(r.get("每笔净R"))),
            guard(onr, cell(onr)),
            guard(b1, cell(b1)), mark,
            guard(ob1, cell(ob1)),
            guard(diff, cell(diff)),
            cell(flip_v)))

    # ── 表二 · 符号翻转
    L.append("\n## 表二 · 符号翻转(老池赢随机、考卷输随机,或反过来)\n")
    if not old:
        L.append("★★★ **算不了 —— 老池可比口径待补。**\n")
        L.append("> ★ 符号翻转要两边都有数才能判。老池那一边("
                 "`probe/bench1_rerun_1102/`)还没出结果,★★ 而 1031 那一份里"
                 "35 条的基准一是坏数,拿它判翻转会得出假的翻转数。"
                 "★★★ 所以这一格现在是「**说不清**」,不是「0 条」。\n")
        L.append("★ 考卷这一侧已经有的数:")
        pos = [r for r in rows if (r.get("★新基准一值") or 0) > 0]
        neg = [r for r in rows if r.get("★新基准一值") is not None
               and r["★新基准一值"] <= 0]
        L.append(f"- 考卷上**赢随机**(基准一 > 0)的 {len(pos)} 条")
        L.append(f"- 考卷上**输随机**(基准一 ≤ 0)的 {len(neg)} 条")
    else:
        flips = []
        for r in rows:
            b1 = r.get("★新基准一值")
            ob1 = old_cell(old, r["链"], "基准一")
            if b1 is None or ob1 in (None, PENDING):
                continue
            if (b1 > 0) != (ob1 > 0):
                flips.append((r["链"], ob1, b1))
        L.append(f"**{len(flips)} 条翻转。**\n")
        if flips:
            L.append("| 链 | 老池基准一 | 考卷基准一 | 方向 |")
            L.append("|---|---|---|---|")
            for lab, ob, nb in sorted(flips):
                direction = ("老池赢随机 → 考卷输随机" if ob > 0
                             else "老池输随机 → 考卷赢随机")
                L.append(f"| {lab} | {cell(ob)} | {cell(nb)} | {direction} |")
        else:
            L.append("(一条都没有)")

    # ── 表三 · 前提破裂 / 跑不了
    L.append("\n## 表三 · 前提破裂 / 跑不了(逐条说原因)\n")
    L.append(f"**前提破裂 {s['★前提破裂_算不出基准一的']} 条 · "
             f"跑不了 {s['跑不了的']} 条。**\n")
    if s["前提破裂名单"] or s["跑不了名单"]:
        L.append("| 链 | 哪一类 | 原因 |")
        L.append("|---|---|---|")
        for x in s["前提破裂名单"]:
            L.append(f"| {x['链']} | BenchmarkPremiseBroken | "
                     f"{str(x['说明']).replace(chr(10), ' ')} |")
        by = {r["链"]: r for r in rows}
        for lab in s["跑不了名单"]:
            tb = (by[lab].get("★跑不了") or "").strip().splitlines()
            L.append(f"| {lab} | 跑不了 | `{tb[-1] if tb else '?'}` |")
    else:
        L.append("(一条都没有)")

    # ── 表四 · 笔数门
    L.append("\n## 表四 · 门二 · 笔数 < 30 的链(不给统计结论)\n")
    L.append(f"**{s['★笔数小于30_不给统计结论的']} 条。**\n")
    if s["★笔数小于30名单"]:
        L.append("| 链 | 考卷笔数 | 老池笔数 |")
        L.append("|---|---|---|")
        for x in s["★笔数小于30名单"]:
            L.append(f"| {x['链']} | {x['笔数']} | "
                     f"{cell(old_cell(old, x['链'], '笔数'))} |")
    else:
        L.append("(一条都没有)")

    # ── 表五 · 退化 R
    L.append("\n## 表五 · 退化 R(止损价落在进场价上那一类)\n")
    L.append(f"**本轮再出现 {s['★退化R再出现的链数']} 条**"
             f"(判据:risk_per_share / entry_price < 1e-4,"
             f"和 `degenerate_r_1031.py` 同一条,没有改)。\n")
    if s["★退化R名单"]:
        L.append("| 链 | 真链退化笔数 / 总笔数 | 对照退化笔数 / 总笔数 | "
                 "最大\\|R\\| | 每笔R原样 | 每笔R剔掉退化笔 |")
        L.append("|---|---|---|---|---|---|")
        by = {r["链"]: r for r in rows}
        for x in s["★退化R名单"]:
            r = by[x["链"]]
            a = r.get("★退化R_真链流水") or {}
            b = r.get("★退化R_对照流水") or {}
            L.append("| {} | {} / {} | {} / {} | {} | {} | {} |".format(
                x["链"], a.get("退化笔数"), a.get("笔数"),
                b.get("退化笔数"), b.get("笔数"),
                cell(a.get("最大 |R|"), 1), cell(a.get("每笔R_原样")),
                cell(a.get("每笔R_剔掉退化笔"))))
    else:
        L.append("(一条都没有)")

    # ── 表六 · 对照组笔数偏差
    L.append("\n## 表六 · 对照组笔数偏差(容差 ±5% 硬断言)\n")
    L.append(f"**最大绝对偏差 {s['★对照笔数偏差_最大绝对值']} · "
             f"超 ±5% 的 {s['★对照笔数偏差超±5%的链数']} 条。**\n")
    if s["★对照笔数偏差超±5%名单"]:
        L.append("| 链 | 偏差 |")
        L.append("|---|---|")
        for x in s["★对照笔数偏差超±5%名单"]:
            L.append(f"| {x['链']} | {x['偏差']:+.4%} |")
    else:
        L.append("★ 一条都没有触发 —— 和新断言的预期一致。")

    # ── 表七 · 无止损
    L.append("\n## 表七 · 无止损的链(R 退化成收益率,不可和有止损同列排序)\n")
    L.append(f"**{s['★无止损(R退化成收益率)的链数']} 条。**\n")
    L.append("| 链 | 怎么判的 |")
    L.append("|---|---|")
    for x in s["★无止损名单(不可和有止损同列排序)"]:
        L.append(f"| {x['链']} | {x['怎么判的']} |")

    # ── 表八 · 被闸挡下
    L.append("\n## 表八 · 被闸挡下、没进逐链的链(不许悄悄消失)\n")
    bl = d.get("★被闸挡下_不出数的链") or []
    L.append(f"**{len(bl)} 条。**\n")
    if bl:
        L.append("| 链 | 理由 |")
        L.append("|---|---|")
        for x in bl:
            why = {k: v for k, v in x.items() if k != "链"}
            L.append(f"| {x['链']} | {json.dumps(why, ensure_ascii=False)} |")
    else:
        L.append("(一条都没有)")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")
    print("写到", OUT, "·", len(L), "行")
    return 0


if __name__ == "__main__":
    sys.exit(main())
