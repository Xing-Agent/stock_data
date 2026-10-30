"""
★★★ 第一节的追加:历史短的时候,阶段号到底是**编反了**,还是**说不清**?

════════════════════════════════════════════════════════════════════════════
为什么必须加这一节
════════════════════════════════════════════════════════════════════════════
订正后的校准曲线出现两个看着矛盾的数:
    · 只看走平格子(截断后 label ∈ {1,3}):错号率 **0.0000**,每个桶都是 0
    · 看全部格子:                        错号率 75.4%(<250)/ 34.9%(250~400)
★★★ 这两个数不矛盾 —— 它们在说两件不同的事。本节把那 34.9% **逐对拆开**,
     证明它是「截断后还没确认、说不清」,不是「把顶编成了底」。

★★ 这件事为什么要紧:任务给的前提是「历史 <400 → 49.1% / 31.6% **编错号**」,
   而那个数是 **commit 8163aa7(修「缺省值替我们表态看多」)之前**的代码跑出来的。
   修完之后,「没有历史」不再被缺省成「阶段一 = 底部 = 该买」,而是落到 transition。
   → 所以「会编反」这个病的形态**已经变了**,本节给出变成了什么。

跑法:python3 probe/volume_direction_1030/decompose_shortfall.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
from collections import Counter

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _REPO)

from engine import cache                                          # noqa: E402
from engine import state_axis_tri_1029 as tri                     # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "_sp_1030", os.path.join(_REPO, "probe", "stage_path_1030", "run_probe.py"))
SP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SP)

OUT = os.path.join(_HERE, "results_1b分歧拆开.json")
BK = ((0, 250), (250, 400), (400, 550), (550, 700), (700, 1000), (1000, 10 ** 9))
OFFSETS = tuple(range(520, 2301, 120))

#: ★ 哪些标签算「说不清」(= 它根本没给方向),哪些算「给了方向」
UNSURE = ("transition", "WARMUP", "None")


def main() -> int:
    p = cache.load()
    cl = p["close"]
    syms = list(cl.columns)
    idx = cl.index
    keep = np.asarray(idx >= pd.Timestamp(tri.START))
    pos = np.arange(len(idx))
    fv = {}
    for s in syms:
        a = cl[s].notna().to_numpy()
        fv[s] = int(a.argmax()) if a.any() else len(a)

    base = {}
    for s in syms:
        base[s], _r, _e = SP.daily_labels(cl[s].to_numpy(), 0)

    pair = {b: Counter() for b in BK}
    kind = {b: Counter() for b in BK}
    for o in OFFSETS:
        for s in syms:
            f = fv[s]
            if o <= f:
                continue
            lab, _r, _e = SP.daily_labels(cl[s].to_numpy(), o)
            b = base[s]
            bs = np.asarray([str(x) for x in b])
            ts = np.asarray([str(x) for x in lab])
            ok = (keep & (bs != tri.WARMUP) & (bs != "None")
                  & (ts != tri.WARMUP) & (ts != "None"))
            hist = pos - o
            diff = ok & (bs != ts)
            for lo, hi in BK:
                m = diff & (hist >= lo) & (hist < hi)
                if not m.any():
                    continue
                for t in np.flatnonzero(m):
                    a_, b_ = bs[t], ts[t]
                    pair[(lo, hi)][f"全历史{a_} → 截断后{b_}"] += 1
                    if b_ in UNSURE:
                        kind[(lo, hi)]["★ 截断后说不清(transition)"] += 1
                    elif a_ in UNSURE:
                        kind[(lo, hi)]["★ 全历史说不清、截断后给了方向"] += 1
                    elif {a_, b_} == {"1", "3"}:
                        kind[(lo, hi)]["★★★ 顶↔底 编反(1↔3)"] += 1
                    elif {a_, b_} == {"2", "4"}:
                        kind[(lo, hi)]["★★ 涨↔跌 编反(2↔4)"] += 1
                    else:
                        kind[(lo, hi)][f"其他({a_}→{b_})"] += 1

    res = {
        "★ 这一节在回答什么": (
            "订正后的校准曲线里「全部格子」那一栏的错号率(<250 时 75.4%)"
            "**具体是哪一种错** —— 是把顶编成底(要害),还是截断后干脆没确认(说不清)。"),
        "★ 判据": {
            "顶↔底 编反": "全历史说 1、截断后说 3(或反过来)—— ★★★ 这才是会让人"
                         "在顶部买入 / 在底部卖出的那一种",
            "说不清": "截断后是 transition —— ★ 它没给方向,所以不会让人做反单",
        },
        "起点集合(只用真的切掉了有效 bar 的)": list(OFFSETS),
        "逐桶拆开": {},
    }
    for lo, hi in BK:
        tot = sum(kind[(lo, hi)].values())
        res["逐桶拆开"][f"手上历史 {lo}~{hi if hi < 10**9 else '∞'} 个有效交易日 bar"] = {
            "不一致的格子合计": tot,
            "按种类": dict(kind[(lo, hi)].most_common()),
            "★★★ 顶↔底编反占不一致的比例": (
                round(kind[(lo, hi)]["★★★ 顶↔底 编反(1↔3)"] / tot, 6) if tot else None),
            "最常见的 8 对": dict(pair[(lo, hi)].most_common(8)),
        }
    allk = Counter()
    for b in BK:
        allk.update(kind[b])
    res["★★★ 全部桶合计"] = {
        "不一致格子合计": sum(allk.values()),
        "按种类": dict(allk.most_common()),
        "★★★ 顶↔底编反的格子数": allk["★★★ 顶↔底 编反(1↔3)"],
        "★★★ 顶↔底编反占不一致的比例":
            round(allk["★★★ 顶↔底 编反(1↔3)"] / max(1, sum(allk.values())), 6),
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print(json.dumps(res["★★★ 全部桶合计"], ensure_ascii=False, indent=1))
    for k, v in res["逐桶拆开"].items():
        print(k, "→ 编反占比", v["★★★ 顶↔底编反占不一致的比例"],
              "| 合计", v["不一致的格子合计"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
