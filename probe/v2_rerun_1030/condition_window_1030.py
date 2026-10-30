#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 说明书第②③栏的料:每条策略「它要的条件成立了多久」和「条件成立时的表现」
—— 2026-10-30,大+中池重跑口径。

三秒版:一条策略条件一年只成立两三次,和一条常年可用的,**是两种完全不同的商品**。
        所以必须先量「条件成立了多久」,再谈表现。

★★ 两个条件分开量(它们在引擎里是两道不同的闸,不许混成一个数):
  ① **市场环境条件**(`m.regime`,一维,每个交易日一个真假)
     = 配置里 ③ regime 那一块。★ 占比 = regime 为真的**交易日**数 / 窗口交易日数。
  ② **股票条件**(`m.universe`,二维 [交易日 × 票])
     = 配置里 ① universe 那一块,★★ 本轮已经与上了池子口径(大+中)。
     ★ 占比 = universe 为真的**票·交易日**数 / (窗口交易日 × 票数)。
  ③ 两个都成立 = ① AND ②,按票·交易日算。

★★★ 第③栏的诚实口径(★ 这一条必须写进说明书,不许含糊):
   引擎只在 `regime_next` 为真时产生候选(chain.py ⑤),所以**每一笔成交本来就
   全部发生在条件成立的区段里** —— ★ 也就是说逐笔统计(笔数/每笔R/胜率)
   **已经就是**「条件成立时的表现」,★★ 它不是全期平均。
   ★ 另外给一个净值口径的切分:净值在 regime 为真的交易日 vs 为假的交易日
     各累计了多少 —— ★★ 为假的那部分几乎全是空仓(所以≈0),
     这正好把「这条策略有多少时间在场外」这件事量出来。

★ 「天」一律是**交易日**。
"""
from __future__ import annotations

import copy
import json
import os
import sys
import time

import numpy as np
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import (cache, chain, data, matrices, ops_exits_1029,  # noqa: E402
                    pat6_ops, pool_scope)
import rerun_core_1030 as RC                                      # noqa: E402

CONFIG_DIR = os.path.join(ROOT, "engine", "configs")
IN_JSON = os.path.join(HERE, "rerun_results_1030.json")
OUT = os.path.join(HERE, "condition_window_1030.json")

VARIANT_MODULES = [
    ("A0十二条", "engine.run_a0_12"),
    ("技术派六条三版", "engine.pat6_run"),
    ("批五修正", "engine.run_p5_1029"),
    ("原著离场", "engine.run_orig_exits_1029"),
    ("剔污染", "engine.run_declean_1030"),
]


def main() -> int:
    prev = json.load(open(IN_JSON, encoding="utf-8"))
    labels = {r["链"] for r in prev["逐链"] if "★跑不了" not in r}
    pat6_ops.install()
    ops_exits_1029.install()
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]

    variants, seen = [], set()
    for batch, modname in VARIANT_MODULES:
        mod = __import__(modname, fromlist=["VARIANTS"])
        for v in getattr(mod, "VARIANTS"):
            label = f"{batch}/{v[0]}"
            if label not in labels or label in seen:
                continue
            seen.add(label)
            variants.append((label, v[1], v[2], v[4]))
    print(f"★ {len(variants)} 条,串行单进程\n")

    rows = []
    t0 = time.time()
    for i, (label, yml, ov, group) in enumerate(variants, 1):
        with open(os.path.join(CONFIG_DIR, yml), encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        if ov is not None:
            raw = ov(copy.deepcopy(raw))
        cfg = chain.ChainConfig.from_dict(raw)
        m = matrices.build(cfg.raw, syms)
        RC.apply_scope(m, "large_mid")
        perf = data.perf_window(m.index, data.PERF_START, data.PERF_END)
        i0 = int(m.index.get_loc(perf[0]))
        i1 = int(m.index.get_loc(perf[-1]))
        sl = slice(i0, i1 + 1)
        reg = np.asarray(m.regime[sl], dtype=bool)
        uni = np.asarray(m.universe[sl], dtype=bool)
        nd, ns_ = uni.shape
        both = uni & reg[:, None]

        res = chain.run_chain(cfg, syms, m=m)
        eq = res.equity
        dret = eq.pct_change().fillna(0.0).to_numpy()
        # 对齐:equity 的索引就是绩效窗口
        k = min(len(dret), len(reg))
        r_on = float(np.prod(1 + dret[:k][reg[:k]]) - 1.0) if reg[:k].any() else 0.0
        r_off = float(np.prod(1 + dret[:k][~reg[:k]]) - 1.0) if (~reg[:k]).any() else 0.0

        rec = {
            "链": label, "族": group, "配置": yml,
            "窗口交易日": int(nd), "票数": int(ns_),
            "②市场环境条件成立的交易日占比": round(float(reg.mean()), 4),
            "②市场环境条件成立的交易日数": int(reg.sum()),
            "②股票条件成立的票·交易日占比": round(float(uni.mean()), 4),
            "②两个条件都成立的票·交易日占比": round(float(both.mean()), 4),
            "②平均每个交易日有多少只票可买": round(float(both.sum() / max(1, nd)), 2),
            "③笔数": int(len(res.ledger)),
            "③合格进场信号(entry&universe)": int((m.entry & m.universe).sum()),
            "③净值在环境成立日的累计": round(r_on, 6),
            "③净值在环境不成立日的累计": round(r_off, 6),
            "③环境不成立日占比": round(float((~reg).mean()), 4),
        }
        rows.append(rec)
        print(f"[{i}/{len(variants)}] {label[:50]:50s} "
              f"环境成立 {rec['②市场环境条件成立的交易日占比']:6.1%} | "
              f"股票条件 {rec['②股票条件成立的票·交易日占比']:6.1%} | "
              f"两者都 {rec['②两个条件都成立的票·交易日占比']:6.1%} | "
              f"均每日可买 {rec['②平均每个交易日有多少只票可买']:6.1f} 只")

    out = {"口径戳": pool_scope.stamp("large_mid", {
        "本轮做法": "★ 大+中池真重跑口径下,逐链量「条件成立了多久」和「条件成立时的表现」",
        "②的两道闸": "① universe(股票条件,已与上池子口径)· ③ regime(市场环境条件)",
        "③的诚实口径": "★★ 引擎只在 regime 为真时产生候选,所以逐笔统计本来"
                        "就只统计了条件成立的区段 —— 它不是全期平均",
        "天": "全部是交易日",
    }), "逐链": rows}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n共 {round(time.time()-t0,1)}s → {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
