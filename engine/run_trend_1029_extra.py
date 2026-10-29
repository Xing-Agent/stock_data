"""
流派一 补两件(2026-10-29):

★ 一、分步归因按两个窗口分别算(2018-2021 / 2022-2025)——
     上一轮测出「挑票」这一步在 2018-2021 是负贡献,这次要回答「还是不是」。
     全周期那张表看不出窗口差异,所以必须分窗口再算一遍。

★ 二、四格硬关的明细(信号均值 / 随机均值 / σ)——
     slots=3 出现了「四格全正、全池判据却为负」,这两件事必须能对上账,
     所以把每格的随机对照均值单独打出来,不许只看 Z。

跑法:python3 -m engine.run_trend_1029_extra
"""

from __future__ import annotations

import json
import os

import numpy as np
import yaml

from . import analyze, cache, chain, data, matrices, stats_gate, window_pool
from .run_batch import window_pool_gate

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results_1029_趋势跟随补充.json")
WINDOWS = (("2018-2021", "2018-01-01", "2021-12-31"),
           ("2022-2025", "2022-01-01", "2025-12-31"),
           ("全周期 2018-2025", data.PERF_START, data.PERF_END))


def _cfg(slots: int) -> chain.ChainConfig:
    with open(os.path.join(HERE, "configs", "trend_following.yaml"),
              encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    raw["slots"] = slots
    return chain.ChainConfig.from_dict(raw)


def main() -> int:
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    out: dict = {"全池只数": len(syms), "分窗口归因": {}, "四格明细": {}}

    for slots in (3, 10):
        cfg = _cfg(slots)
        out["分窗口归因"][f"slots{slots}"] = {}
        for wname, s, e in WINDOWS:
            df = analyze.attribution(cfg, syms, s, e, 1_000_000.0)
            print("=" * 78)
            print(f"slots={slots}  窗口 {wname}")
            print(df.to_string())
            recs = json.loads(df.reset_index().to_json(orient="records",
                                                       force_ascii=False))
            out["分窗口归因"][f"slots{slots}"][wname] = recs

    for slots in (3, 10):
        cfg = _cfg(slots)
        v = window_pool_gate(cfg, syms)
        rows = []
        for c in v.cells:
            r = c.result
            rows.append({"格": c.key, "n": int(r.n_signal),
                         "信号均值": round(float(r.signal_mean), 4),
                         "随机均值": round(float(r.random_mean), 4),
                         "σ随机": round(float(r.random_std), 4),
                         "差值": round(float(r.diff), 4),
                         "Z": round(float(r.z_effect), 2),
                         "p": round(float(r.p_empirical), 4)})
        print("=" * 78)
        print(f"slots={slots} 四格明细")
        for r in rows:
            print("  ", r)
        out["四格明细"][f"slots{slots}"] = {"通过": bool(v.passed), "四格": rows}

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\n写了:{OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
