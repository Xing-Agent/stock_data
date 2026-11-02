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
SRC = os.path.join(HERE, "exam_run_1102.json")
OUT = os.path.join(HERE, "表-逐链-1102.md")


def cell(v, nd=4) -> str:
    """★ None → 「—」;有值 → 印值。★ 有值却想印「—」是 bug,这里堵死。"""
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
    if v is not None and rendered == "—":
        raise RuntimeError(f"★★★ 值是 {v!r} 却渲染成「—」 —— 坑表第 33 处,停。")
    return rendered


def main() -> int:
    d = json.load(open(SRC, encoding="utf-8"))
    rows = d["逐链"]
    s = d["汇总"]
    L = []

    L.append("# 表 · 逐链 —— 考卷 vs 老池 · 2026-11-02\n")
    L.append("> 口径:" + d["口径戳"]["池子口径"]
             + f" · 种子 {rows[0].get('种子数') if rows else '?'} 个 · 容差 ±"
             + f"{d['口径戳'].get('容差')}\n")
    L.append("> ★ 老池那一列 = `probe/bench1_rerun_1031/bench1_rerun_1031.json`"
             "(研发池 198 只,同一套口径)。\n")
    L.append("> ★ 「—」只表示**这个数真的没有**。算出来了但不许当结论的,"
             "值照印并标 `[不给结论]`。\n")

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
        ob1 = r.get("老池_基准一")
        L.append("| {} | {} | {} | {} | {} | {}{} | {}{} | {} | {} |".format(
            r["链"], cell(n), cell(r.get("老池_笔数")),
            guard(r.get("每笔净R"), cell(r.get("每笔净R"))),
            guard(r.get("老池_每笔净R"), cell(r.get("老池_每笔净R"))),
            guard(b1, cell(b1)), mark,
            guard(ob1, cell(ob1)),
            " `[老池这条已被退化R判为不可用]`"
            if r.get("★老池这条链的基准一本来就被退化R判为不可用") else "",
            guard(r.get("★和老池的差"), cell(r.get("★和老池的差"))),
            cell(r.get("★符号是否翻转"))))

    # ── 表二 · 符号翻转
    L.append("\n## 表二 · 符号翻转(老池赢随机、考卷输随机,或反过来)\n")
    L.append(f"**{s['★符号翻转的']} 条翻转。**\n")
    if s["符号翻转名单"]:
        L.append("| 链 | 老池基准一 | 考卷基准一 | 方向 |")
        L.append("|---|---|---|---|")
        by = {r["链"]: r for r in rows}
        for lab in s["符号翻转名单"]:
            r = by[lab]
            ob, nb = r.get("老池_基准一"), r.get("★新基准一值")
            direction = ("老池赢随机 → 考卷输随机" if (ob or 0) > 0
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
        by = {r["链"]: r for r in rows}
        for x in s["★笔数小于30名单"]:
            L.append(f"| {x['链']} | {x['笔数']} | "
                     f"{cell(by[x['链']].get('老池_笔数'))} |")
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
