# -*- coding: utf-8 -*-
"""补一组（我加的）：吊灯的 ATR 放宽到大约「4 小时线上 2~3 倍」—— 1 小时 ATR 的 4 / 5 / 6 倍（4 小时 ATR 约是 1 小时的 2 倍，这是近似）。
只跑 BTC、ETH，2017–2021，带「收回突破位」，封存段不进统计。"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("J", os.path.join(HERE, "吊灯止损_1125.py")); J = importlib.util.module_from_spec(sp); sp.loader.exec_module(J)
out = {}; data = {s: J.b.load(s) for s in ("BTC", "ETH")}
for k in (4.0, 5.0, 6.0):
    for hold in (72, 240):
        L = []
        for s in ("BTC", "ETH"):
            t = J.跑(data[s], 出场="吊灯", k=k, hold=hold); t["票"] = s; L.append(t)
        T = pd.concat(L, ignore_index=True); T["t"] = pd.to_datetime(T["t"], utc=True).dt.tz_localize(None)
        T = T[(T["t"] >= "2017-01-01") & (T["t"] < "2022-01-01")]
        out[f"吊灯1小时ATR×{k}·最长{hold}根"] = {d_: J.S(x) for d_, x in T.groupby("dir")}
        print(k, hold, {d_: (v["笔数"], v["每笔净R"], v["胜率pct"], v["利润因子"], v["按笔累计最深回撤R"], v["平均拿几根"]) for d_, v in out[f"吊灯1小时ATR×{k}·最长{hold}根"].items()}, flush=True)
json.dump(out, open(os.path.join(HERE, "out", "吊灯_放宽_币.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
