#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""查「同一个代码中间断了很久又接上」的票，以及踩在断档上的交易（2026-11-18）

大白话：有的公司退市了，几年后另一家公司（或它自己重新上市）又用了同一个代码。
       数据里这两段被接成了一只票。回测如果在断档前买入，就会「拿着」穿过好几年的空白，
       最后按新公司的价格卖出 —— 赚的钱是假的。例：TLN，2016 年买入，2024 年才「卖出」。
这里找出 2015–2025 研发池里中间断档 60 个交易日以上的票，再看哪些交易跨过了断档。
只读面板和已有流水。
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
idx = cl.index
gaps = []
for s in dev:
    v = cl[s].notna().to_numpy()
    if not v.any():
        continue
    pos = np.where(v)[0]
    d = np.diff(pos)
    for k in np.where(d > 60)[0]:
        gaps.append((s, idx[pos[k]], idx[pos[k + 1]], int(d[k]), float(cl[s].iloc[pos[k]]), float(cl[s].iloc[pos[k + 1]])))
G = pd.DataFrame(gaps, columns=["代码", "断档前最后一天", "接上的第一天", "断了多少个交易日", "断前收盘", "接上后收盘"])
G.to_csv(os.path.join(HERE, "代码中间断档_清单_1118.csv"), index=False, encoding="utf-8-sig")
print("研发池", len(dev), "只；中间断档超过 60 个交易日的：", len(G), "处，", G["代码"].nunique(), "只票")
print(G.sort_values("断了多少个交易日", ascending=False).head(12).to_string())
gm = {}
for s, a, b in zip(G["代码"], G["断档前最后一天"], G["接上的第一天"]):
    gm.setdefault(s, []).append((pd.Timestamp(a), pd.Timestamp(b)))
rows = []
for 目录 in ("技术面中档_ledgers", "基本面融合_ledgers", "基本面融合_ledgers_剔可疑票"):
    for p in sorted(glob.glob(os.path.join(HERE, 目录, "*.csv"))):
        x = pd.read_csv(p)
        if not len(x): continue
        ed, xd = pd.to_datetime(x.entry_date), pd.to_datetime(x.exit_date)
        hit = np.array([any(e <= a and b <= q for a, b in gm.get(str(s), [])) for s, e, q in zip(x.symbol, ed, xd)])
        if hit.any():
            tot = float(x.net_pnl.sum())
            rows.append({"哪一批": 目录, "策略": os.path.basename(p)[:-4], "笔数": len(x), "跨断档的笔数": int(hit.sum()),
                         "全部净利润": round(tot), "跨断档那几笔的净利润": round(float(x.net_pnl[hit].sum())),
                         "占全部净利润pct": round(float(x.net_pnl[hit].sum()) / tot * 100, 1) if tot > 0 else None,
                         "票": ",".join(sorted(set(x.symbol[hit].astype(str))))[:60]})
R = pd.DataFrame(rows)
R.to_csv(os.path.join(HERE, "跨断档的交易_1118.csv"), index=False, encoding="utf-8-sig")
print(R.to_string())
