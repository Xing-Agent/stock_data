#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 「哪些链进了基准一那张表、哪些没进、为什么没进」—— 唯一的一份口径。

三秒版:以前被闸挡下的链是**悄悄消失**的 —— 表里既没有它、也没有一句
        「它为什么不在」。本模块把「挡下」和「挡下的理由」变成一份
        **要印出来的名单**,所以没进表的链在表里也看得见。

★ 为什么要单独一个模块(不是抄两份):
  `run_bench1_1031.gates_pass` 和 `make_tables_1031` 都要这一套判据。
  抄两份就是排查报告 §五 那张「同一样东西两种写法」表上的第 12 行 ——
  ★ 所以这里只许有一份,两边都 import 这一份。

★ 这里**一个阈值都没有新增**:30 笔 / 三槽位 / 退化 / 集中度 0.50
  全部照抄 `probe/v2_rerun_1030/bench_two_1030.gates_pass`,
  一个数都没动。本模块只是把「过/不过」这一个布尔值,
  拆成「过/不过 + 为什么不过 + 这条链的数字还能不能当结论用」。
"""
from __future__ import annotations

#: ★ 集中度闸:前 10 笔占总盈利超过这个数,这一版的收益数字就不可用。
#  ★ 照抄 bench_two_1030.gates_pass 里的 `sh <= 0.50`,不是新定的数。
CONCENTRATION_MAX = 0.50

#: ★ 样本底线,同样照抄,不是新定的数。
MIN_TRADES = 30

#: ★★★ 三种「没有数」必须分开,不许都写成「—」:
#   数字不可用 = 算出来了,但按既有口径不许当结论(集中度过半 / R 退化)
#   前提破裂   = 这个数的前提不成立,算出来也没有意义
#   没有这个数 = 真的没有
数字不可用 = "★数字不可用"
前提破裂 = "★前提破裂"
没有这个数 = "★没有这个数"


def verdict(r: dict) -> dict:
    """一条 `rerun_results_1030.json/逐链` 的记录 → 这条链的闸门判决。

    返回:
      过闸      bool —— ★ 必须和 bench_two_1030.gates_pass 一模一样
      挡下的理由 list[str]
      数字可用吗 str  —— 「可用」/ 数字不可用
      集中度    float | None
    """
    a = r["大中_重跑"]
    c = a["集中度"]
    sh = c.get("集中度_前10笔占总盈利")

    reasons: list[str] = []
    unusable: list[str] = []

    if a["笔数"] < MIN_TRADES:
        reasons.append(f"笔数 {a['笔数']} < {MIN_TRADES}(样本不足,不是不成立)")
    if not r["四槽位"]["三槽位齐全_不含加仓"]:
        reasons.append("三槽位(进场/离场/止损)不齐全")
    if c.get("★退化"):
        reasons.append("R 退化")
        unusable.append("R 退化")
    if c.get("★半退化"):
        reasons.append("R 半退化")
        unusable.append("R 半退化")
    if sh is None:
        reasons.append("集中度算不出")
    elif sh > CONCENTRATION_MAX:
        why = (f"★ 集中度 {sh:.4f} > {CONCENTRATION_MAX} —— "
               f"曲线是前 10 笔扛起来的,按既有口径"
               f"**这一版的收益数字不可用**")
        reasons.append(why)
        unusable.append(why)

    return {
        "过闸": not reasons,
        "挡下的理由": reasons,
        "数字可用吗": (数字不可用 if unusable else "可用"),
        "为什么不可用": unusable,
        "集中度": sh,
        "笔数": a["笔数"],
        "读法": c.get("★读法"),
    }


def gates_pass(r: dict) -> bool:
    """★ 只有这一个布尔口径(`run_bench1_1031` 用它)。"""
    return verdict(r)["过闸"]


def _原口径(r: dict) -> bool:
    """★ 反向自测用:bench_two_1030.gates_pass 的原文,一个字不改。"""
    a = r["大中_重跑"]
    c = a["集中度"]
    sh = c.get("集中度_前10笔占总盈利")
    return (a["笔数"] >= 30
            and r["四槽位"]["三槽位齐全_不含加仓"]
            and not c.get("★退化") and not c.get("★半退化")
            and sh is not None and sh <= 0.50)


def selftest(rows: list[dict]) -> int:
    """★ 拆出理由之后判决**一条都不许变** —— 不一致就 raise。"""
    bad = [r["链"] for r in rows if gates_pass(r) != _原口径(r)]
    if bad:
        raise AssertionError(f"★★★ 拆理由改变了判决,{len(bad)} 条:{bad[:5]}")
    # ★ 反向自测:挡下的链必须说得出理由;过闸的链必须一条理由都没有
    for r in rows:
        v = verdict(r)
        if v["过闸"] and v["挡下的理由"]:
            raise AssertionError(f"★ {r['链']} 过闸却有理由")
        if not v["过闸"] and not v["挡下的理由"]:
            raise AssertionError(f"★ {r['链']} 被挡下却说不出理由")
    return len(rows)
