#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查面板里「一天之内价格翻三倍以上 / 跌到三分之一以下」的地方（2026-11-18）

大白话：公司做「反向拆股」（比如 15 股并 1 股）时，股价一夜之间变成 15 倍，但你手里的股数也变成 1/15，钱没变。
       如果数据没把这件事折算进去，回测就会以为这只票一天涨了 15 倍 —— 假的暴利。
       这里把研发池 2015–2025 所有这种「一天跳三倍」的日子找出来，再看哪些策略的交易踩在上面。
只读面板和已有流水，不跑引擎。
"""
import glob, io, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
import numpy as np, pandas as pd
import 跑基本面_1106 as B
B.装层()
from engine import cache
hold = json.load(io.open(B.HOLD, encoding="utf-8"))
dev = [s for s in hold["研发池名单"] if s in cache._PANEL["close"].columns]
cl = cache._PANEL["close"][dev].astype(float).loc["2014-12-01":"2025-12-31"]
op = cache._PANEL["open"][dev].astype(float).loc["2014-12-01":"2025-12-31"]
ratio = cl / cl.shift(1)
gap = op / cl.shift(1)
跳 = (ratio > 3) | (ratio < 1 / 3)
ev = [(d, s, float(ratio.at[d, s]), float(gap.at[d, s])) for s in dev for d in ratio.index[跳[s].fillna(False).to_numpy()]]
E = pd.DataFrame(ev, columns=["日期", "代码", "收盘比前收", "开盘比前收"]).sort_values(["代码", "日期"])
E.to_csv(os.path.join(HERE, "一天跳三倍_清单_1118.csv"), index=False, encoding="utf-8-sig")
print("研发池只数", len(dev), "一天跳三倍以上的票日", len(E), "涉及票数", E["代码"].nunique(),
      "其中向上跳", int((E["收盘比前收"] > 3).sum()), "向下跳", int((E["收盘比前收"] < 1 / 3).sum()))
print(E.sort_values("收盘比前收", ascending=False).head(15).to_string())
# 哪些交易踩在上面：持仓期间（进场日之后到离场日）含有向上跳的日子
up = E[E["收盘比前收"] > 3]
jm = {}
for d, s in zip(up["日期"], up["代码"]):
    jm.setdefault(s, []).append(pd.Timestamp(d))
rows = []
for 目录, 标 in (("基本面融合_ledgers", ""), ("技术面中档_ledgers", "")):
    for p in sorted(glob.glob(os.path.join(HERE, 目录, "*.csv"))):
        x = pd.read_csv(p)
        if not len(x): continue
        ed, xd = pd.to_datetime(x.entry_date), pd.to_datetime(x.exit_date)
        hit = np.array([any(a < j <= b for j in jm.get(str(s), [])) for s, a, b in zip(x.symbol, ed, xd)])
        tot = float(x.net_pnl.sum())
        rows.append({"策略": os.path.basename(p)[:-4], "笔数": len(x), "踩到的笔数": int(hit.sum()),
                     "全部净利润": round(tot), "踩到那几笔的净利润": round(float(x.net_pnl[hit].sum())),
                     "占全部净利润pct": round(float(x.net_pnl[hit].sum()) / tot * 100, 1) if tot > 0 else None,
                     "踩到的票": ",".join(sorted(set(x.symbol[hit].astype(str))))[:80]})
R = pd.DataFrame(rows)
R.to_csv(os.path.join(HERE, "踩到跳三倍的交易_1118.csv"), index=False, encoding="utf-8-sig")
print(R[R["踩到的笔数"] > 0].to_string())
