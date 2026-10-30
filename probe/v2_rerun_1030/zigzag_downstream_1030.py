#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★ zigzag 静默失败修好之后,状-1 / 状-4 / 状-6 的输出变了多少 —— 2026-10-30

三秒版:摆动点函数修好了,那三条压在它上面的判定跟着变了多少?这里把数并排摆出来。

★ 做法:在**本进程里**把 `engine.run_a0_states.zigzag_pivots` 临时换成
  修好之前那一版(`engine/checks/empty_result_guard._zigzag_BUGGY`,原样留档),
  跑一遍 状-4 / 状-6,再换回来跑一遍,两份并排。
  ★★ `engine/` 一个字符都没改;★ 也**不写** `engine/results_1029_A0状态两条.json`
     (那是别人的产出),结果只写进本目录。

★ 「天」一律是**交易日**。状-6 的评估日 = 绩效窗口内每个日历月的最后一个交易日。
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import cache, data, pool_scope, run_a0_states as A  # noqa: E402

OUT = os.path.join(HERE, "zigzag_downstream_1030.json")


def _buggy():
    p = os.path.join(ROOT, "engine", "checks", "empty_result_guard.py")
    spec = importlib.util.spec_from_file_location("erg", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m._zigzag_BUGGY


def pivot_stats(syms, use_wick=True):
    import numpy as np
    ns = []
    for s in syms:
        ns.append(len(A.piv_of(s, use_wick)))
    ns = np.array(ns, dtype=float)
    return {"票数": int(ns.size), "摆动点中位": float(np.median(ns)),
            "摆动点均值": round(float(ns.mean()), 2),
            "0个摆动点的票": int((ns == 0).sum()),
            "0个摆动点的票占比": round(float((ns == 0).mean()), 4)}


def run_side(syms, label):
    A._PIV.clear()
    t = time.time()
    out = {"口径": label,
           "状-1_摆动点_影线": pivot_stats(syms, True)}
    A._PIV.clear()
    out["状-1_摆动点_收盘"] = pivot_stats(syms, False)
    A._PIV.clear()
    out["状-4"] = A.run_wyckoff(syms)
    out["状-6"] = A.run_confluence(syms)
    out["耗时秒"] = round(time.time() - t, 1)
    return out


def main() -> int:
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    print(f"全池 {len(syms)} 只,绩效窗口 {data.PERF_START} .. {data.PERF_END}")

    fixed_fn = A.zigzag_pivots
    print("\n★ 一 · 修**之后**(engine 现状)")
    after = run_side(syms, "修之后(engine 现状)")

    print("\n★ 二 · 修**之前**(把函数临时换成留档的坏版本)")
    A.zigzag_pivots = _buggy()
    try:
        before = run_side(syms, "修之前(_zigzag_BUGGY 留档版)")
    finally:
        A.zigzag_pivots = fixed_fn
        A._PIV.clear()

    out = {
        "口径戳": pool_scope.stamp("large_mid", {
            "本页口径": "★ 这一页和池子口径无关 —— 状-4/状-6 是状态判定,"
                        "跑在全池 300 只上,不涉及下单,所以不套 large_mid",
            "摆动点阈值": "k = 3.0 × ATR(14)(状-4/状-6 的现行取值,"
                          "附录 D.8 原标「待校准」)",
            "没动的东西": "engine/ 一字未改;engine/results_1029_A0状态两条.json 没写",
        }),
        "修之后": after, "修之前": before,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n→ {os.path.relpath(OUT, ROOT)}")

    print("\n★★ 状-1 摆动点(k=3×ATR)")
    for src in ("状-1_摆动点_影线", "状-1_摆动点_收盘"):
        b, a = before[src], after[src]
        print(f"  {src}: 中位 {b['摆动点中位']:.0f} → {a['摆动点中位']:.0f} | "
              f"均值 {b['摆动点均值']} → {a['摆动点均值']} | "
              f"0 个的票 {b['0个摆动点的票']} → {a['0个摆动点的票']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
