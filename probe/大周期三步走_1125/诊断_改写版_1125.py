# -*- coding: utf-8 -*-
"""诊断：周线主版本每个真顶卡在哪一步（前提「两年内涨超 35%」/ 有没有破位 / 破位后有没有确认）。"""
import os, sys, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("G", os.path.join(HERE, "改写版_1125.py")); G = importlib.util.module_from_spec(sp); sp.loader.exec_module(G)
for nm in ("标普500指数", "道琼斯工业指数"):
    D = G.L.读(nm); W = G.周线(D); c = W.close
    lo2 = c.rolling(104, min_periods=52).min(); hi = c.rolling(52, min_periods=52).max().shift(1)
    ev = G.主版(W, 量起=pd.Timestamp("1950-01-01")); ev35 = G.主版(W, 涨=0.0, 量起=pd.Timestamp("1950-01-01"))
    print("==", nm)
    for a, b in G.L.真顶(D.close):
        ta = D.index[a]
        if ta >= G.封存: continue
        tb = G.熊底(D.close, a); w = c.loc[:ta + pd.Timedelta(days=6)]
        nh = w[(w > hi.loc[w.index])].index; last = nh[-1] if len(nh) else None
        rise = float(c.loc[last] / lo2.loc[last] - 1) if last is not None else np.nan
        hit = [e for e in ev if ta <= e["确认"] <= tb]; hit0 = [e for e in ev35 if ta <= e["确认"] <= tb]
        print(f'  顶 {ta.date()}  两年涨幅 {rise*100:5.1f}%  主版本 {"认出 " + str(hit[0]["确认"].date()) + hit[0]["路"] if hit else "没认出"}  ｜去掉35%前提 {"认出 " + str(hit0[0]["确认"].date()) if hit0 else "没认出"}')
    S, T, F = G.评(D, ev35); print("  去掉35%前提: 认出", S["认出"], "/", S["真大顶"], " 虚惊", S["其中虚惊"])
