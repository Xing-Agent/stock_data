# -*- coding: utf-8 -*-
"""每条策略 vs 它自己的「同样仓位的标普」（《390》Lin 拍的相对及格线），新旧口径各算一次"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
from 新口径拿得住_1122 import 指数净值, 等仓位标普, 生存, 名, 池, 序, OUT

print("| 策略 · 池 | 平均仓位 | 旧:策略 / 同仓标普 / 过没过 | 新:策略 / 同仓标普 / 过没过 |")
print("|---|---|---|---|")
res=[]
for k in 序:
    for p, pz in 池.items():
        f = os.path.join(OUT, f"日线_{k}_{p}.parquet")
        if not os.path.exists(f): continue
        d = pd.read_parquet(f); eq = d["eq"].dropna(); eq = eq/eq.iloc[0]
        spy = 指数净值("SPY", eq.index)
        bm = 等仓位标普(eq.index, d["expo"]); bm = bm/bm.iloc[0]
        o_s,_,_ = 生存(eq, spy, 新口径=False); o_b,_,_ = 生存(bm, spy, 新口径=False)
        n_s,_,_ = 生存(eq, spy, 新口径=True);  n_b,_,_ = 生存(bm, spy, 新口径=True)
        ex = round(float(d["expo"].mean())*100,1)
        f1 = "✅过" if o_s>=o_b else "❌不过"; f2 = "✅过" if n_s>=n_b else "❌不过"
        print(f"| {名[k]} · {pz} | {ex}% | {o_s}% / {o_b}% / {f1} | {n_s}% / {n_b}% / {f2} |")
        res.append((f"{名[k]}·{pz}", o_s>=o_b, n_s>=n_b, round(n_s-n_b,1)))
print()
print("旧口径过的条数:", sum(1 for r in res if r[1]), "/", len(res))
print("新口径过的条数:", sum(1 for r in res if r[2]), "/", len(res))
print("换口径后状态变了的:", [ (r[0], ("过→不过" if r[1] and not r[2] else "不过→过")) for r in res if r[1]!=r[2] ])
