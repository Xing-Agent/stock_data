#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大盘闸 · 用「全部信号」量一遍（2026-11-18 · Lin 同意的三步里的第一步）

大白话：不限 10 只，把微仓全接版记下的每一个信号按「进场时大盘好不好」分成两堆，
       比两堆每笔平均赚多少。这样量的是闸本身，不受「碰巧挑中哪 10 只」影响。
闸 = 标普 500 收盘在 200 日线上方、且 200 日线比 20 天前高；用信号日（进场前一天）的状态。
数据：probe/含分红重出_1116/微仓_ledgers/微仓__*.csv（2015–2025，研发池，含分红，老池子范围）。
不跑引擎，只读已有流水。局限写在输出里。
"""
import glob, gzip, io, json, os
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
d = json.load(gzip.open(os.path.join(ROOT, "market_etf_1106/SPY/daily.json.gz")))["data"]
s = pd.Series({pd.Timestamp(r["date"]): r["close"] for r in d}).sort_index()
ma = s.rolling(200).mean()
g1 = ((s > ma) & (ma > ma.shift(20))).shift(1)
rows = []
for p in sorted(glob.glob(os.path.join(ROOT, "probe/含分红重出_1116/微仓_ledgers/微仓__*.csv"))):
    n = os.path.basename(p)[len("微仓__"):-4]
    x = pd.read_csv(p)
    if len(x) < 50:
        continue
    x["r"] = x.net_pnl / x.notional_in * 100
    st = g1.reindex(pd.to_datetime(x.entry_date), method="ffill").to_numpy()
    a, b = x.r[st == True], x.r[st == False]
    peak = int(pd.concat([pd.Series(1, index=pd.to_datetime(x.entry_date)),
                          pd.Series(-1, index=pd.to_datetime(x.exit_date))]).sort_index().cumsum().max())
    row = {"策略": n, "全部信号笔数": len(x), "同时持仓峰值": peak,
           "大盘好时_笔数": len(a), "大盘好时_每笔平均pct": round(a.mean(), 2) if len(a) else None,
           "大盘好时_每笔中位pct": round(a.median(), 2) if len(a) else None,
           "大盘好时_赚钱笔数占比pct": round((a > 0).mean() * 100, 1) if len(a) else None,
           "大盘差时_笔数": len(b), "大盘差时_每笔平均pct": round(b.mean(), 2) if len(b) else None,
           "大盘差时_每笔中位pct": round(b.median(), 2) if len(b) else None,
           "大盘差时_赚钱笔数占比pct": round((b > 0).mean() * 100, 1) if len(b) else None}
    row["备注"] = ("大盘差时不到 300 笔（配置自带大盘闸或信号太少），这一行两堆没法比" if len(b) < 300 else
                 ("同时持仓到过 900 个以上，没做到真的全接" if peak >= 900 else ""))
    rows.append(row)
out = pd.DataFrame(rows)
out.to_csv(os.path.join(os.path.dirname(os.path.abspath(__file__)), "量闸_全信号_1118.csv"), index=False, encoding="utf-8-sig")
能比 = out[out["大盘差时_笔数"] >= 300]
print(len(out), len(能比), "好时平均更高:", int((能比["大盘好时_每笔平均pct"] > 能比["大盘差时_每笔平均pct"]).sum()),
      "好时中位更高:", int((能比["大盘好时_每笔中位pct"] > 能比["大盘差时_每笔中位pct"]).sum()),
      "好时胜率更高:", int((能比["大盘好时_赚钱笔数占比pct"] > 能比["大盘差时_赚钱笔数占比pct"]).sum()))
print(能比[["策略","大盘好时_笔数","大盘好时_每笔平均pct","大盘差时_笔数","大盘差时_每笔平均pct","大盘好时_赚钱笔数占比pct","大盘差时_赚钱笔数占比pct"]].to_string())
