#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 状-2「缺省值替我们表态看多」这个 bug 的修前 / 修后实测 —— 2026-10-30

三秒版:`_confirm_sequence` 里,**从来没确认过任何阶段**的走平格子,
        原来被缺省编成「阶段一 = 跌完了在筑底」,也就是**看多**。
        修成「transition = 说不清」之后,占比变了多少、哪几只票受影响。

★★ 为什么必须点名:★ 这个值已经通过 `engine/state2_topology_1029.py`
   给运营的逐日状态 CSV **出门了** —— 要重发,就得告诉他们哪几只的历史值作废。

★ 「天」一律是**交易日**。★ engine/ 的修正已落在 state_axis_tri_1029.py,
  本脚本只做测量,把坏版本在**本进程里**临时装回去做对照。
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import cache, pool_scope                      # noqa: E402
from engine import state_axis_tri_1029 as tri             # noqa: E402

OUT = os.path.join(HERE, "stage2_default_bull_1030.json")


def _confirm_BUGGY(raw, min_bars):
    """★★ 修好**之前**的 `_confirm_sequence`,原样留档做对照。

    ★ 病根就在最后那个 `else: stage = "1"` —— `last is None`
      (从来没确认过任何阶段)和 `last == "4"`(刚从第四阶段出来)共用它。
    ★★ 不要「顺手修好它」:它存在的理由就是让反向自测有东西可以 FAIL。
    """
    n = len(raw)
    daily = np.full(n, tri.WARMUP, dtype=object)
    events: list[dict] = []
    confirmed: list[str] = []
    cur_raw, run = None, 0
    cur_stage = tri.WARMUP
    for i in range(n):
        r = raw[i]
        if r == tri.WARMUP:
            daily[i] = tri.WARMUP
            cur_raw, run = None, 0
            continue
        if r == cur_raw:
            run += 1
        else:
            cur_raw, run = r, 1
        if run == min_bars and r in ("FLAT", "ADV", "DEC"):
            if r == "ADV":
                stage = "2"
            elif r == "DEC":
                stage = "4"
            else:
                last = confirmed[-1] if confirmed else None
                if last == "2":
                    stage = "3"
                elif last in ("1", "3"):
                    stage = last
                else:
                    stage = "1"
            if not confirmed or confirmed[-1] != stage:
                events.append({"i": i, "stage": stage,
                               "prev": confirmed[-1] if confirmed else None,
                               "prev2": confirmed[-2] if len(confirmed) >= 2 else None})
                confirmed.append(stage)
            cur_stage = stage
        daily[i] = cur_stage if cur_stage != tri.WARMUP else "transition"
        if cur_stage == tri.WARMUP:
            daily[i] = "transition"
    return daily, events


def panel_for(symbols, cl, ma, spec, fn) -> dict[str, np.ndarray]:
    out = {}
    for s in symbols:
        raw = tri._raw_stage(cl[s].to_numpy(), ma[s].to_numpy(), spec)
        daily, _ = fn(raw, spec.min_bars)
        out[s] = daily
    return out


def main() -> int:
    p = cache.load()
    cl = p["close"]
    ma = cl.rolling(150, min_periods=150).mean()
    idx = cl.index
    keep = np.asarray(idx >= pd.Timestamp(tri.START))
    syms = sorted(cl.columns)
    print(f"票 {len(syms)} · 计分窗口起点 {tri.START} · 窗口内交易日 {int(keep.sum())}")

    out = {"口径戳": pool_scope.stamp("large_mid", {
        "本页口径": "★ 和池子口径无关 —— 状-2 是状态判定,跑在全池 300 只上,"
                    "不涉及下单,所以不套 large_mid",
        "计分窗口": f"{tri.START} 起,窗口内 {int(keep.sum())} 个交易日",
        "修正落点": "engine/state_axis_tri_1029.py: _confirm_sequence()"
                    "(last is None 从 last=='4' 那条分支里拆出来)",
    }), "各版本": {}}

    for vname, spec in tri.STAGE_VERSIONS.items():
        pb = panel_for(syms, cl, ma, spec, _confirm_BUGGY)
        pa = panel_for(syms, cl, ma, spec, tri._confirm_sequence)
        db = tri.distribution({s: v[keep] for s, v in pb.items()}, tri.STAGE_STATES)
        da = tri.distribution({s: v[keep] for s, v in pa.items()}, tri.STAGE_STATES)
        # 逐票:窗口内有多少格从 "1" 变成 "transition"
        per_sym, n_cells = {}, 0
        mig: dict[str, int] = {}
        for s in syms:
            x, y = pb[s][keep], pa[s][keep]
            diff = int((x != y).sum())
            if diff:
                per_sym[s] = {
                    "变号格数(交易日)": diff,
                    "原来被编成阶段一的格数": int(((x == "1") & (y != "1")).sum()),
                    "窗口内总格数": int(keep.sum()),
                    "受影响比例": round(diff / int(keep.sum()), 4),
                }
                n_cells += diff
            for a_, b_ in zip(x, y):
                if a_ != b_:
                    k = f"{a_} → {b_}"
                    mig[k] = mig.get(k, 0) + 1
        out["各版本"][vname] = {
            "spec": {"flat_mode": spec.flat_mode, "flat_thr": spec.flat_thr,
                     "min_bars(交易日)": spec.min_bars, "note": spec.note},
            "修之前_分布": db, "修之后_分布": da,
            "★变号格数(票·交易日)": n_cells,
            "★受影响票数": len(per_sym),
            "迁移": dict(sorted(mig.items(), key=lambda kv: -kv[1])),
            "逐票": dict(sorted(per_sym.items(),
                                key=lambda kv: -kv[1]["变号格数(交易日)"])),
        }
        print(f"\n★★ {vname}  ({spec.note})")
        print(f"   变号 {n_cells:,} 格(票·交易日)· 受影响 {len(per_sym)} 只票")
        print(f"   迁移:{out['各版本'][vname]['迁移']}")
        for st in tri.STAGE_STATES:
            b = db.get(st) or db.get("占比", {}).get(st)
            a = da.get(st) or da.get("占比", {}).get(st)
            print(f"   阶段 {st:11s} 修前 {b} → 修后 {a}")

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n→ {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
