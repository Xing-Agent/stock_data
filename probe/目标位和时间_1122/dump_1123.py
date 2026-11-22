# -*- coding: utf-8 -*-
"""把成交最活跃的 172 只研发池个股的日线取出来（每个十年各取一次，按那个十年的成交额中位数排）。引擎只读不改。"""
import os, sys, io, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
seg = sys.argv[1]
if seg == "a":
    sys.path.insert(0, os.path.join(ROOT, "probe/两段时间_1120")); sys.path.insert(0, ROOT)
    import 环境2004_1120 as ENV
    env = ENV.install(只留测试期=False); dev = list(env["dev"]); hs = set(env["留出池"]); s0, s1 = "2004-01-01", "2014-12-31"
    mk = pd.read_parquet(os.path.join(ROOT, "probe/两段时间_1120/流动性池掩膜2004_中.parquet"))
else:
    sys.path.insert(0, os.path.join(ROOT, "probe/联合_1122")); sys.path.insert(0, ROOT)
    import 联合回测_1122 as U
    B, FIX = U.装(); hold = json.load(io.open(B.HOLD, encoding="utf-8")); dev = hold["研发池名单"]; hs = set(hold["留出池名单"]); s0, s1 = "2014-01-01", "2025-12-31"
    mk = pd.read_parquet(os.path.join(ROOT, "probe/流动性池_1114/流动性池掩膜_中.parquet"))
from engine import cache
P = cache._PANEL; print(list(P.keys()))
cols = [s for s in dev if s in P["close"].columns and s not in hs]
c = P["close"][cols].astype(float).loc[s0:s1]; v = P["volume"][cols].astype(float).loc[s0:s1]
dv = (c * v).median().where(c.notna().sum() > 1500).dropna().sort_values(ascending=False)
top = list(dv.index[:172]); print(seg, len(top), top[:10])
L = []
for s in top:
    d = pd.DataFrame({k: P[k][s].astype(float).loc[s0:s1] for k in ("open", "high", "low", "close", "volume")}).dropna(); d["symbol"] = s; L.append(d.reset_index().rename(columns={d.index.name or "index": "date"}))
pd.concat(L).to_parquet(os.path.join(HERE, "out", f"个股日线_{seg}.parquet"))
