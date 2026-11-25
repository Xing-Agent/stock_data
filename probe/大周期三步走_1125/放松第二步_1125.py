# -*- coding: utf-8 -*-
"""第②步的两个数（实体 1.2 ATR、量 1.3 倍，Gemini 给的，原著没给）往松里挪，看真顶从哪一档开始回来、虚惊回来多少。只动第②步，第③步照拍板。"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("S", os.path.join(HERE, "三步走_1125.py")); S = importlib.util.module_from_spec(sp); sp.loader.exec_module(S)
out = {}
for nm in ("标普500指数", "道琼斯工业指数", "纳斯达克综合指数"):
    D = S.L.读(nm); 候, R = S.候选(D, "三层一版"); 候 = [x for x in 候 if str(x["日期"].date()) < S.封存]
    for tf, tfn in (("M", "月线"), ("W", "周线")):
        for 实体 in (0.0, 0.6, 0.9, 1.2):
            for 量 in (1.0, 1.3):
                for 窗 in (1, 3):
                    res = S.三步(D, tf, 候, N=2, 窗=窗, 实体=实体, 量=量); T, F = S.评指数(D, R, res, "确认日")
                    k = f"{nm}｜{tfn}｜实体{实体}｜量{量}｜破位窗{窗}"
                    out[k] = {s: S.概(T[(T["顶"] >= a) & (T["顶"] < b)] if len(T) else T, F[(F["日期"] >= a) & (F["日期"] < b)] if len(F) else F) for s, (a, b) in (("1928–1992", ("1900", "1993")), ("1993–2021", ("1993", S.封存)))}
                    if 实体 == 0.0 and 量 == 1.0 and 窗 == 3: T.to_csv(os.path.join(HERE, "out", f"{nm}_{tfn}_第二步全放开_每个大顶.csv"), index=False); F.to_csv(os.path.join(HERE, "out", f"{nm}_{tfn}_第二步全放开_别的转空.csv"), index=False)
                    a_, b_ = out[k]["1928–1992"], out[k]["1993–2021"]
                    print(k, "真顶认出", f'{a_["认出"]}/{a_["真大顶"]}', f'{b_["认出"]}/{b_["真大顶"]}', "虚惊", a_["其中虚惊(之后再跌不到10pct)"], b_["其中虚惊(之后再跌不到10pct)"], "离顶天中位", a_["认出离顶天中位"], b_["认出离顶天中位"], flush=True)
json.dump(out, open(os.path.join(HERE, "out", "放松第二步.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
