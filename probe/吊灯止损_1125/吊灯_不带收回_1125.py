# -*- coding: utf-8 -*-
"""补一组（我加的，任务单没要）：吊灯但不带「收回突破位就撤」，看这一条把吊灯拖累了多少。只跑 BTC、ETH，2017–2021，封存段照样不进统计。"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("J", os.path.join(HERE, "吊灯止损_1125.py")); J = importlib.util.module_from_spec(sp); sp.loader.exec_module(J)
src = open(os.path.join(HERE, "吊灯止损_1125.py"), encoding="utf-8").read()
# 只去掉「收回突破位」那一行，其余一字不改
exec(src.split("def 走(")[0][:0] + "def 走2(" + src.split("def 走(")[1].split("\ndef 跑(")[0].replace('if (C[j] < line) if Lg else (C[j] > line): return pnl(C[j]), "收回突破位", j, j - ei', 'pass'), J.__dict__)
J.走 = J.__dict__["走2"]
out = {}
for k in (2.0, 2.5, 3.0):
    for hold in (72, 240):
        L = []
        for s in ("BTC", "ETH"):
            t = J.跑(J.b.load(s), 出场="吊灯", k=k, hold=hold); t["票"] = s; L.append(t)
        T = pd.concat(L, ignore_index=True); T["t"] = pd.to_datetime(T["t"], utc=True).dt.tz_localize(None)
        T = T[(T["t"] >= "2017-01-01") & (T["t"] < "2022-01-01")]
        out[f"吊灯k={k}·最长{hold}根·不带收回"] = {d_: J.S(x) for d_, x in T.groupby("dir")}
        print(k, hold, {d_: (v["笔数"], v["每笔净R"], v["利润因子"], v["平均拿几根"]) for d_, v in out[f"吊灯k={k}·最长{hold}根·不带收回"].items()}, flush=True)
json.dump(out, open(os.path.join(HERE, "out", "吊灯_不带收回_币.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
