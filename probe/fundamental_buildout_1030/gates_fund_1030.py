#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 基准二 + 四道门 —— 主格逐条摆数(2026-10-30)

三秒版:★★★ 本轮撞到一件**结构性**的事,它比任何一条链的成绩都重要:
        **基准一(同环境随机进场)对 `entry: always` 这类策略在构造上是退化的。**

══════════════════════════════════════════════════════════════════════════
★★★ 为什么退化 —— 这不是校准没收敛,是上限打满了
══════════════════════════════════════════════════════════════════════════
  ★ 基准一的设计意图:把第③步换成随机,★ 比的是「**挑进场时机**准不准」。
  ★★ 而这五条机械底仓链的第③步**就是 `always`** —— ★ 它们没有进场时机,
     只有一张筛选表。
  ★★★ 所以随机对照无论怎么调触发率都追不上真链的笔数:
     实测基-5(真链 425 笔)校准到 `rate = 1.0`(**已经是上限**,
     等于每天每只票都掷中)时对照均值仍只有 399 笔,偏差 −6.12% > 容差 ±5%
     → `BenchmarkPremiseBroken`。
  ★ 结论的写法:★★ 这**不是**「基准一说这条链不行」,也**不是** bug —— ★★★ 是
    **基准一问的那个问题,在这类策略上不存在**。★ 对这类链,
    能回答问题的是**基准二(同等仓位大盘)**和**筛选表自己的分位对照**。

★★ 处置(★ 不许绕过硬闸装作通过):
   ① 基准一:★ 如实记下 `BenchmarkPremiseBroken` 的原文和偏差数,★★ 不下结论。
   ② 基准二:★ 照跑(它不依赖基准一),★★ 这是这几条链的主基准。
   ③ 四道门:★ 对照组用 `strict=False` 拿到的那一版,★★★ **只摆数、不下结论** ——
      ★ 并且每一行都带上「对照笔数偏差」这个数,让读的人自己看它可不可信。
   ★★★ 一律不许写「不成立」:Z 不显著时写
      **「在现有样本容量下未显现统计显著性」**(Gemini 裁决,已采用)。

★ 先写结果再打印。★ 可续跑(每个主格一个 part 文件)。
跑法:python3 probe/fundamental_buildout_1030/gates_fund_1030.py
"""
from __future__ import annotations

import copy
import json
import os
import sys
import time
import traceback

import numpy as np
import pandas as pd
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE, os.path.join(ROOT, "probe", "v2_rerun_1030"),
          os.path.join(ROOT, "probe", "regime_install_1030")):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import analyze, cache, chain, data, matrices, stats_gate  # noqa: E402
import ops_fund_1030 as OF                                            # noqa: E402
import rerun_core_1030 as RC                                          # noqa: E402
import regime_vectors_1030 as RV                                      # noqa: E402
from run_fund_1030 import (CHAINS, CONFIG_DIR, DEV, MAIN_RANK,         # noqa: E402
                           MAIN_SLOTS, SCOPE, _load, _num, apply_grid)

PART_DIR = os.path.join(HERE, "parts_gate")
OUT_JSON = os.path.join(HERE, "gates_fund_1030.json")


def one(cid: str, arm: str) -> dict:
    t0 = time.time()
    raw = _load(CHAINS[cid])
    c = apply_grid(raw, cid, MAIN_SLOTS[cid], MAIN_RANK.get(cid))
    cfg = chain.ChainConfig.from_dict(copy.deepcopy(c))
    man = data.load_manifest()
    have = set(cache.symbols())
    syms = [s for s in sorted(man) if man[s].fundamentals_path and s in have]
    start, end = DEV

    uni = matrices.universe_mask(cfg.raw.get("universe") or {}, syms)
    OF.set_screen(cid, uni)
    m = matrices.build(cfg.raw, syms)
    RC.apply_scope(m, SCOPE)
    if arm == "乙_装非牛市":
        bull, _meta = RV.market_vectors(m.index)["乙·牛市"]
        m.regime = m.regime & (~bull.reindex(m.index).fillna(False).to_numpy())
    res = chain.run_chain(cfg, syms, start, end, 1_000_000.0, m=m)
    led = res.ledger
    n = len(led)

    rec = {"链": cid, "臂": arm, "笔数": n,
           "★样本量底线": ("够" if n >= stats_gate.SYSTEM_MIN_TRADES
                           else f"★★ 不够(n={n} < {stats_gate.SYSTEM_MIN_TRADES})"),
           "★样本不足警示": analyze.sample_size_banner(n)}

    bm = cfg.get("benchmark") or {}
    # ---- 基准二(★ 这几条链的主基准)
    try:
        rec["基准二_同等仓位大盘"] = _num(analyze.exposure_matched_benchmark(
            res, bm.get("component_match", "large"), bm.get("risk_free_annual")))
    except Exception as e:
        rec["基准二_跑挂了"] = f"{type(e).__name__}: {e}"

    # ---- 基准一(★ 如实记下硬闸的原文)
    try:
        rec["基准一_同环境随机进场"] = _num(analyze.random_entry_benchmark(
            cfg, res, syms, start, end))
        rec["基准一_结论"] = "★ 容差达标,这条链上基准一是可用的。"
    except Exception as e:
        rec["基准一_硬闸拦住了"] = f"{type(e).__name__}: {e}"
        rec["基准一_结论"] = (
            "★★★ 基准一在这条链上**构造性退化**,不是「这条链不行」—— "
            "③ 进场是 `always`,随机对照把触发率打到上限 1.0 仍追不上真链笔数。"
            "★ 这类策略没有「进场时机」可比,★★ 主基准看基准二。")

    # ---- 四道门(★★★ 只摆数,不下结论;对照组容差没达标也如实标)
    try:
        pre = analyze.calibrated_random_rate(cfg, syms, start, end, n,
                                             res.initial_equity, seed=20181001,
                                             max_iter=6, strict=False)
        ctrl = pre.get("ledger")
        v = analyze.bootstrap_on_ledger(res, ctrl)
        rec["四道门_原始数"] = _num(v)
        rec["四道门_对照组口径"] = {
            "对照笔数": int(pre.get("n_ctrl") or 0),
            "真链笔数": n,
            "★对照笔数偏差": float(pre.get("偏差", float("nan"))),
            "★容差": float(pre.get("tol", analyze.CONTROL_TOL)),
            "★容差达标": bool(pre.get("★容差达标")),
            "★读法": "★★★ 容差没达标时这一格的 Z **不可用于下结论** —— "
                      "μ_随机 被系统性拉偏。★ 这里把数留全是为了换门时不用重跑。",
        }
    except Exception as e:
        rec["四道门_跑挂了"] = f"{type(e).__name__}: {e}"
        rec["四道门_traceback"] = traceback.format_exc()[-1500:]

    # ---- 集中度(★ 第四道门)
    if n:
        bysym = led.groupby("symbol")["net_pnl"].sum().sort_values(ascending=False)
        tot = float(led["net_pnl"].sum())
        rec["集中度"] = {
            "成交票只数": int(led["symbol"].nunique()),
            "最赚那一只占净盈亏比例": (float(bysym.iloc[0] / tot)
                                      if tot != 0 else None),
            "前5只占净盈亏比例": (float(bysym.head(5).sum() / tot)
                                  if tot != 0 else None),
            "逐年笔数": {str(k): int(v) for k, v in
                         led.groupby(pd.to_datetime(led["exit_date"]).dt.year)
                         .size().items()},
        }
    rec["耗时秒"] = round(time.time() - t0, 1)
    return rec


def main() -> int:
    OF.install(with_operating_income=False)
    os.makedirs(PART_DIR, exist_ok=True)
    todo = [(cid, "甲_不装条件") for cid in CHAINS] + [("基-2", "乙_装非牛市")]
    out = {}
    for cid, arm in todo:
        part = os.path.join(PART_DIR, f"{cid}__{arm}.json")
        if os.path.exists(part):
            out[f"{cid}|{arm}"] = json.load(open(part, encoding="utf-8"))
            continue
        try:
            rec = one(cid, arm)
        except Exception as e:
            rec = {"链": cid, "臂": arm, "★跑挂了": f"{type(e).__name__}: {e}",
                   "traceback": traceback.format_exc()[-2000:]}
        with open(part, "w", encoding="utf-8") as fh:
            json.dump(_num(rec), fh, ensure_ascii=False, indent=2, default=str)
        out[f"{cid}|{arm}"] = rec
        try:
            print(f"{cid} {arm}: 笔数={rec.get('笔数')} "
                  f"基准一={'硬闸拦住' if '基准一_硬闸拦住了' in rec else '达标'} "
                  f"用时={rec.get('耗时秒')}s")
        except Exception as e:
            print(f"(打印出错:{type(e).__name__}: {e})")
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump({"窗口": f"{DEV[0]} .. {DEV[1]}(研发池)",
                   "★结论写法": "★★★ Z 不显著时一律写「在现有样本容量下"
                                 "未显现统计显著性」,★ 严禁写「不成立」。",
                   "主格": _num(out)}, fh, ensure_ascii=False, indent=2,
                  default=str)
    try:
        print(f"\n★ 写了:{OUT_JSON}")
    except Exception as e:
        print(f"(打印出错,结果已写出:{type(e).__name__}: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
