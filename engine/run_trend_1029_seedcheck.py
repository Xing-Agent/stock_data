"""
★ 随机对照的「种子噪声」有多大(2026-10-29)。

为什么要测:判据(stats_gate)那一套三个对照组,用的是**一个种子**跑出来的
随机对照流水;而基准一用的是**五个种子**取平均。本轮实测这两个数对不上
(slots=10:单种子对照每笔 R = +0.106,五种子平均 = −0.003),
★ 说明「随机对照」本身是个带噪声的量 —— 不量出来就不知道 Z 能信到第几位。

做法:用校准后的触发率,换 10 个种子各跑一遍同环境随机进场,
      看每笔 R 的分布;再把 10 个种子的流水并在一起当对照重算一次 Z。

跑法:python3 -m engine.run_trend_1029_seedcheck
"""

from __future__ import annotations

import gc
import json
import os

import numpy as np
import pandas as pd
import yaml

from . import analyze, cache, chain, data, matrices, stats_gate

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "results_1029_趋势跟随种子噪声.json")
N_SEEDS = 5        # ★ 10 个种子跑到一半把容器撑爆了(OOM),降到 5 个
SLOTS = (10,)      # ★ 只测配置主值那一档


def main() -> int:
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    out: dict = {"种子数": N_SEEDS, "链": {}}
    for slots in SLOTS:
        with open(os.path.join(HERE, "configs", "trend_following.yaml"),
                  encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        raw["slots"] = slots
        cfg = chain.ChainConfig.from_dict(raw)
        res = chain.run_chain(cfg, syms)
        n = len(res.ledger)
        sig = res.ledger["r_multiple"].dropna().to_numpy(float)

        cal = analyze.calibrated_random_rate(cfg, syms, data.PERF_START,
                                             data.PERF_END, n,
                                             res.initial_equity, seed=424242)
        rate = cal["rate"]

        per_seed, pooled = [], []
        for k in range(N_SEEDS):
            c2 = cfg.copy_with(entry={"type": "random",
                                      "params": {"rate": rate,
                                                 "seed": 424242 + 101 * k},
                                      "source": "随机对照:种子噪声实验"})
            led = chain.run_chain(c2, syms, data.PERF_START,
                                  data.PERF_END, res.initial_equity).ledger
            v = led["r_multiple"].dropna().to_numpy(float)
            per_seed.append({"种子": 424242 + 101 * k, "笔数": int(len(led)),
                             "每笔R": round(float(np.mean(v)), 4) if v.size else None})
            pooled.append(led[["r_multiple"]].copy())
            del led
            gc.collect()
        allled = pd.concat(pooled, ignore_index=True)
        v_all = allled["r_multiple"].dropna().to_numpy(float)

        ms = [p["每笔R"] for p in per_seed if p["每笔R"] is not None]
        verdict = analyze.bootstrap_on_ledger(res, allled)
        rec = {
            "真链笔数": n, "真链每笔R": round(float(np.mean(sig)), 4),
            "校准后触发率": rate,
            "每个种子": per_seed,
            "★单种子每笔R的范围": [min(ms), max(ms)],
            "★单种子每笔R的标准差": round(float(np.std(ms, ddof=1)), 4),
            "★10 个种子并池后的对照每笔R": round(float(np.mean(v_all)), 4),
            "★用并池对照重算的判据": {
                k: {"Z": round(float(r.z_effect), 2),
                    "p": round(float(r.p_empirical), 4),
                    "信号均值": round(float(r.signal_mean), 4),
                    "随机均值": round(float(r.random_mean), 4)}
                for k, r in verdict.results.items()},
            "判定": {"通过": bool(verdict.passed), "级别": verdict.level,
                     "理由": list(verdict.reasons)},
        }
        print("=" * 78)
        print(f"slots={slots}", json.dumps(rec, ensure_ascii=False, indent=2))
        out["链"][f"slots{slots}"] = rec

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\n写了:{OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
