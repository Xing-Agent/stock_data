#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""换挑法 · 用全部信号量（2026-11-18）

大白话：账户只有 10 个位子时，「碰巧挑中谁」的影响比挑法本身还大（随机抽 5 次能从 2% 差到 9%）。
       所以换个量法：不限位子，把每个信号都记下来（微仓全接版的流水），
       每天把当天的信号按「涨幅」从低到高排，分成五档，看哪一档的信号之后平均赚得多。
       如果涨得快的那一档确实更好，「先买涨得快的」才算有依据。
涨幅用信号当天（进场前一个交易日）收盘及以前的数据：当天、一周（5 天）、一个月（21 天）、三个月（63 天）。
同一天信号不足 5 个的日子不参与分档。
数据：probe/含分红重出_1116/微仓_ledgers（2015–2025，研发池，含分红，老池子范围）。只读，不跑引擎。
"""
import glob, io, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
import numpy as np, pandas as pd
import 跑基本面_1106 as B
B.装层()
from engine import cache
cl = cache._PANEL["close"].astype(float)
vol = cache._PANEL["volume"].astype(float)
idx = cl.index
pos = {d: i for i, d in enumerate(idx)}
G = {"当天": cl / cl.shift(1) - 1, "一周": cl / cl.shift(5) - 1, "一个月": cl / cl.shift(21) - 1, "三个月": cl / cl.shift(63) - 1,
     "成交额": (cl * vol).rolling(20, min_periods=20).mean()}
名单 = ["技-1", "trend_following", "trend_following-原著-唐奇安反向通道离场", "技-6-XING", "技-6-原著", "技-5-XING", "技-5-原著",
        "技-3-XING", "技-3-原著", "技-4-原著-中值", "技-4-原著", "融-2_突破"]
rows = []
for n in 名单:
    p = os.path.join(ROOT, "probe/含分红重出_1116/微仓_ledgers", f"微仓__{n}.csv")
    if not os.path.exists(p):
        continue
    x = pd.read_csv(p)
    if len(x) < 500:
        continue
    x["r"] = x.net_pnl / x.notional_in * 100
    ei = pd.to_datetime(x.entry_date).map(pos)
    x = x[ei.notna()].copy(); ei = ei[ei.notna()].astype(int) - 1
    x["sig"] = ei.values
    x = x[x.sig >= 0]
    cols = {s: j for j, s in enumerate(cl.columns)}
    cj = x.symbol.astype(str).map(cols)
    x = x[cj.notna()]; cj = cj[cj.notna()].astype(int)
    for 名, M in G.items():
        x[名] = M.to_numpy()[x.sig.to_numpy(), cj.to_numpy()]
    cnt = x.groupby("sig")["r"].transform("size")
    y = x[cnt >= 5].copy()
    for 名 in G:
        y[名] = pd.to_numeric(y[名], errors="coerce")
        y["档"] = np.floor((y.groupby("sig")[名].rank(pct=True) * 5).clip(upper=4.999))
        g = y.dropna(subset=["档"]).groupby("档")["r"]
        m_, md, wr, k = g.mean(), g.median(), g.apply(lambda s: (s > 0).mean() * 100), g.size()
        row = {"策略": n, "按什么排": 名, "参与的信号数": int(k.sum())}
        for q in range(5):
            lab = ["最低一档", "第二档", "中间档", "第四档", "最高一档"][q]
            row[lab + "_每笔平均pct"] = round(float(m_.get(q, np.nan)), 2)
            row[lab + "_赚钱笔数占比pct"] = round(float(wr.get(q, np.nan)), 1)
        row["最高档减最低档_每笔平均pct"] = round(row["最高一档_每笔平均pct"] - row["最低一档_每笔平均pct"], 2)
        # 赚超过一倍的大赢家落在哪一档
        big = y[y.r > 100]
        row["大赢家总数_每笔赚超一倍"] = int(len(big))
        row["大赢家在最高一档的占比pct"] = round(float((big["档"] == 4).mean() * 100), 1) if len(big) else None
        row["大赢家在最低一档的占比pct"] = round(float((big["档"] == 0).mean() * 100), 1) if len(big) else None
        rows.append(row)
R = pd.DataFrame(rows)
R.to_csv(os.path.join(HERE, "全信号按涨幅分档_1118.csv"), index=False, encoding="utf-8-sig")
pd.set_option("display.width", 250)
print(R[["策略", "按什么排", "参与的信号数", "最低一档_每笔平均pct", "中间档_每笔平均pct", "最高一档_每笔平均pct", "最高档减最低档_每笔平均pct",
         "最低一档_赚钱笔数占比pct", "最高一档_赚钱笔数占比pct", "大赢家总数_每笔赚超一倍", "大赢家在最高一档的占比pct", "大赢家在最低一档的占比pct"]].to_string())
for 名 in G:
    s = R[R["按什么排"] == 名]
    print(名, "最高档好过最低档的策略数:", int((s["最高档减最低档_每笔平均pct"] > 0).sum()), "/", len(s))
