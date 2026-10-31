#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 把 bench1_rerun_1031.json 变成报告里那几张表(md)。只读,不重算。

★★★ 2026-10-31 修了这张表的两个 bug(方法保真度排查 问一 / 问二 第 1、2 行):

  ① **「有值的被印成破折号」**。1029 那张汇总表把技-1 原著 System 2 的基准一
     印成了 `—`,而那个 **+0.070324 在 JSON 里一直都有**。下游于是把它读成
     「算不出」,把 System 2 的笔数(364)和 System 1 的差值(−0.323)
     拼成了一张表,还标成「System 1 的实测」。
     ★ 病根是「—」这一个符号被当成了三件事:「真的没有这个数」、
       「算出来了但不许当结论」、「前提破了」。
     ★ 修法:三种状态**分开印**,并加一道硬闸 —— 只要传进来的值不是 None
       却要印成「—」,**直接 raise**(见 `cell()` 与 `_selftest()`)。

  ② **被闸挡下的链悄悄消失**。技-1 原著 System 2 的集中度 0.5593 > 0.5,
     按既有口径这一版的收益数字本来就不可用 —— 它**不该给出一个数**,
     但也**不该从表里消失得无影无踪**(消失了,读表的人就只看到
     「System 1 输给随机」,看不到「System 2 这一版根本不出数」)。
     ★ 修法:新增「表五 · 被闸挡下、不出数的链」,逐条印出理由,
       集中度过半的显式印成「★数字不可用」。
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)

import gate_roster_1031 as GR  # noqa: E402

SRC = os.path.join(HERE, "bench1_rerun_1031.json")
HOLD = os.path.join(HERE, "holdout_1031.json")
DEGEN = os.path.join(HERE, "degenerate_r_1031.json")
PREV = os.path.join(os.path.dirname(os.path.dirname(HERE)),
                    "probe", "v2_rerun_1030", "rerun_results_1030.json")
OUT = os.path.join(HERE, "表-逐链-1031.md")

#: ★ 「真的没有这个数」—— 只有这一种情况才许印破折号
NO_VALUE = "—"


class DashBug(AssertionError):
    """★★★ 有值却要印成「—」—— 这正是 1029 那个 bug,不许再发生一次。"""


def cell(x, nd=4, *, 不出数=None):
    """★★★ 这张表里**唯一**的渲染口径。三种状态分开:

      · 不出数 给了原因  → 印「★不出数(原因)」★ 绝不印「—」
      · x is None        → 印「—」=「真的没有这个数」
      · 其余             → 印数字

    ★ 硬闸:`不出数` 没给、而 x **有值**,却渲染出「—」→ raise DashBug。
    """
    if 不出数:
        if str(不出数).strip() in ("", "-", NO_VALUE):
            raise DashBug("★ 「不出数」必须说出理由,不许只给一个破折号")
        return f"**★不出数({不出数})**"
    if x is None:
        return NO_VALUE
    if isinstance(x, bool):
        out = "是" if x else "否"
    else:
        try:
            out = f"{float(x):+.{nd}f}"
        except (TypeError, ValueError):
            out = str(x)
    if out.strip() == NO_VALUE:
        raise DashBug(f"★★★ 有值({x!r})却渲染成了破折号 —— 1029 那个 bug")
    return out


def pcell(x, nd=2, *, 不出数=None):
    """百分比版,口径与 `cell` 完全一致(同一样东西一个口径)。"""
    if 不出数 or x is None:
        return cell(None, 不出数=不出数)
    try:
        out = f"{float(x)*100:+.{nd}f}%"
    except (TypeError, ValueError):
        out = str(x)
    if out.strip() == NO_VALUE:
        raise DashBug(f"★★★ 有值({x!r})却渲染成了破折号")
    return out


def _selftest() -> None:
    """★ 反向自测:这几条一条都不许过不去 —— 过不去就说明闸是假的。"""
    # ① 有值必须印出来(1029 那个 +0.070324 就是在这里丢的)
    assert cell(0.070324) == "+0.0703", cell(0.070324)
    # ② 真的没有 → 破折号
    assert cell(None) == NO_VALUE
    # ③ 有值但不许当结论 → 印理由,不印破折号
    assert cell(0.070324, 不出数="集中度 0.5593 > 0.5").startswith("**★不出数(")
    assert NO_VALUE not in cell(0.070324, 不出数="集中度 0.5593 > 0.5")
    # ④ 「不出数」不许拿破折号当理由
    try:
        cell(1.0, 不出数="—")
    except DashBug:
        pass
    else:
        raise AssertionError("★ 闸没拦住「拿破折号当理由」")
    # ⑤ 百分比版同口径
    assert pcell(None) == NO_VALUE
    assert pcell(-0.1042) == "-10.42%"
    assert pcell(-0.1042, 不出数="前提破了").startswith("**★不出数(")


#: ★ 旧名字继续可用,但它们现在走的是同一道闸(不许再有第二个渲染口径)
f = cell
pc = pcell


def main() -> int:
    _selftest()
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
            L.append(f"| {i} | {r['链']} | {NO_VALUE} | {NO_VALUE} | **★跑不了** | "
                     + " | ".join([NO_VALUE] * 8) + " |")
            continue
        b1 = r.get("★新基准一值")
        broke = bool(r.get("★前提破了_禁止下游"))
        bl = r["链"] in blown
        dupmark = ("★副本" if r["链"] not in first_of else NO_VALUE)
        # ★★★ 「不出数」和「没有这个数」从这里开始分开:
        #   退化 R / 前提破裂 → 数**算出来了**,只是不许当结论 → 印理由
        #   ★ 以前这三列一律印「—」,于是「有值但不出」和「真的没有」
        #     在表面上一模一样 —— 那正是 1029 把 +0.070324 印成「—」的病根。
        why = None
        if bl:
            why = f"退化 R,数值已毁({blown[r['链']]:.3e})"
        elif broke:
            why = "对照组笔数没校准到容差内,基准一的前提破了"
        if why:
            b1cell = f"**★不出数({why})**"
        else:
            b1cell = f"**{cell(b1)}**"
        L.append("| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
            i, r["链"], r.get("笔数"), r.get("旧笔数(全大中池)") or NO_VALUE,
            b1cell,
            pcell(r.get("★对照笔数偏差"), 不出数=("前提破了" if broke else None)),
            pcell(r.get("旧对照笔数偏差")),
            cell(r.get("旧基准一(作废·仅用于看污染有多大)")),
            cell(r.get("★和旧值的差"), 不出数=why),
            cell(r.get("★符号是否翻转"), 不出数=why),
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

    # ── 表五 · ★★★ 被闸挡下、根本没进上面那张表的链(以前它们是悄悄消失的)
    prev = json.load(open(PREV, encoding="utf-8"))
    prows = [x for x in prev["逐链"] if "★跑不了" not in x]
    GR.selftest(prows)                     # ★ 拆理由不许改变判决,变了就 raise
    blocked = [(x["链"], GR.verdict(x)) for x in prows if not GR.gates_pass(x)]
    L.append("\n## 表五 · ★★★ 被闸挡下、**不出数**的链({} 条)\n".format(len(blocked)))
    L.append("> ★ 为什么要印出来:这些链**没有进表一**。以前它们是**悄悄消失**的 —— "
             "表里既没有它们、也没有一句「为什么不在」,")
    L.append("> 读表的人会以为「表里没有 = 没跑过」或者直接忽略掉。")
    L.append("> ★★ 技-1 原著 System 2 就是这么丢的:它的集中度 0.5593 > 0.5,"
             "按既有口径**这一版的收益数字本来就不可用**,")
    L.append("> 它既不该给出一个会被当成结论的数,也不该从表里消失。\n")
    L.append("| 链 | 笔数 | 集中度 | **数字能不能当结论** | 被挡下的理由 |")
    L.append("|---|--:|--:|:-:|---|")
    for n, v in blocked:
        L.append("| {} | {} | {} | **{}** | {} |".format(
            n, v["笔数"],
            cell(v["集中度"]),
            v["数字可用吗"],
            "<br>".join(v["挡下的理由"])))
    L.append("\n★ 读法:**「被闸挡下」不等于「这一派不成立」** —— "
             "样本不足、R 退化、集中度过半,说的都是"
             "「这一版的数字不能用来下结论」,不是「这个方法没用」。")

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
