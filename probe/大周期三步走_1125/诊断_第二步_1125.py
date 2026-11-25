# -*- coding: utf-8 -*-
"""诊断：第②步「放量大阴线破位」到底卡在哪一条。对每次原报警，看它那根（月线 / 周线 / 日线）实体是几倍 ATR、量是几倍均量、收盘在不在箱底下。"""
import os, sys, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
sp = importlib.util.spec_from_file_location("S", os.path.join(HERE, "三步走_1125.py")); S = importlib.util.module_from_spec(sp); sp.loader.exec_module(S)
rows = []
for nm in ("标普500指数", "道琼斯工业指数", "纳斯达克综合指数"):
    D = S.L.读(nm); 候, R = S.候选(D, "三层一版"); 候 = [x for x in 候 if str(x["日期"].date()) < S.封存]
    T, F = S.评指数(D, R, 候, "日期"); 真 = set(T[T["认出"] != "没认出"]["认出"])
    for tf in ("M", "W", "D"):
        B = S.K线(D, tf); o, h, l, c, v = (B[x].to_numpy(float) for x in ("open", "high", "low", "close", "volume")); idx = B.index
        pc = np.r_[c[0], c[:-1]]; atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14, min_periods=5).mean().to_numpy()
        v20 = pd.Series(v).rolling(20, min_periods=5).mean().shift(1).to_numpy()
        for e in 候:
            j = int(np.searchsorted(idx.values, np.datetime64(e["日期"])))
            if j >= len(c): continue
            rows.append({"指数": nm, "周期": tf, "报警": str(e["日期"].date()), "是真顶那次": str(e["日期"].date()) in 真, "收阴": c[j] < o[j], "实体除ATR": round((o[j] - c[j]) / atr[j], 2),
                         "量比": round(v[j] / v20[j], 2) if v[j] > 0 and v20[j] > 0 else None, "收在箱底下": c[j] < e["箱底"]})
X = pd.DataFrame(rows); X.to_csv(os.path.join(HERE, "out", "诊断_第二步.csv"), index=False)
for (tf, z), g in X.groupby(["周期", "是真顶那次"]):
    print(tf, "真顶那次" if z else "别的", len(g), "收阴", round(g["收阴"].mean(), 2), "实体>1.2ATR", round((g["实体除ATR"] > 1.2).mean(), 2), "实体中位", g["实体除ATR"].median(),
          "量>1.3", round((g["量比"].dropna() > 1.3).mean(), 2), "有量", g["量比"].notna().sum(), "收在箱底下", round(g["收在箱底下"].mean(), 2))
