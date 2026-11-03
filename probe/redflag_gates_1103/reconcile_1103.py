#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 对账脚本:三道基本面闸的逐闸数,和 probe/gate_decomp_1103 比。

跑法:python3 probe/redflag_gates_1103/reconcile_1103.py  [withR]
  不带参数 = 干净进程,只算三道基本面闸(NEED 只含 Q 的科目)
  带 withR = 先把四道排雷闸的面板算一遍,再算三道基本面闸
             → 用来验证「排雷闸的计算有没有污染基本面闸的状态」
"""
from __future__ import annotations
import os, sys, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE, os.path.join(ROOT, "probe", "masters_57_1030")):
    if p not in sys.path:
        sys.path.insert(0, p)

import run_redflag_gates_1103 as RUN
from engine import data, fundamentals as F
import ops_q57_1030 as Q

WITH_R = len(sys.argv) > 1 and sys.argv[1] == "withR"
if not WITH_R:
    # ★ 干净口径:loader 只留 Q 要的 13 个科目(= gate_decomp_1103 的 NEED)
    RUN.NEED = {m for m, _k in Q._COLS.values()}
    RUN.USE_RAWTAG_SGA = False

Q.install()
cal = data.trading_calendar()
perf = np.asarray((cal >= pd.Timestamp(data.PERF_START)) &
                  (cal <= pd.Timestamp(data.PERF_END)), dtype=bool)
n_days = int(perf.sum())
RUN.use_ext_library()
syms, smask, _ = RUN.ext_pool_mask(cal, perf)
print(f"实体 {len(syms)}  掩膜 {int(smask.sum()):,d}  交易日 {n_days}")

if WITH_R:
    import ops_redflag_1103 as R
    for n in ("int_cov", "sloan_accrual", "zmij_prob", "m_score"):
        df = R.get(n, syms)
        print(f"  (排雷) {n} 非空 {int(df.notna().sum().sum()):,d}")
        del df

fm = RUN.fundamental_masks(syms, smask, cal)
out = {}
for k, (ev, ps) in fm.items():
    out[k] = {"ev": int(ev.sum()), "ps": int(ps.sum())}
    print(f"{k}\n   ev {int(ev.sum()):,d}   ps {int(ps.sum()):,d}")
ks = list(fm)
ev3 = fm[ks[0]][0] & fm[ks[1]][0] & fm[ks[2]][0]
ps3 = fm[ks[0]][1] & fm[ks[1]][1] & fm[ks[2]][1]
out["三道全"] = {"ev3": int(ev3.sum()), "ps3": int(ps3.sum()),
                 "每天": round(int(ps3.sum()) / n_days, 4)}
print(f"三道全: ev3 {int(ev3.sum()):,d}  ps3 {int(ps3.sum()):,d}"
      f"  每天 {int(ps3.sum())/n_days:.4f}")
print("★ gate_decomp_1103 的目标值: ev 346914/725336/2197642, "
      "ps 92210/426035/442167, ev3 176346, ps3 13563 (6.7444/天)")
tag = "withR" if WITH_R else "clean"
json.dump(out, open(os.path.join(HERE, f"reconcile_{tag}.json"), "w"),
          ensure_ascii=False, indent=1)
