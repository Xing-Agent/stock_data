#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""顶部形态做空，按「这只票当时本身强不强」分开看（2026-11-20 · Lin：很多个股、尤其是弱的小票是可以空的）

大白话：《331》把所有票混在一起算，结论是做空不赚。Lin 指出弱票、小票应该不一样。这里用同一批交易，
按进场前一天就能知道的三样东西分组：这只票在不在自己的 200 日线下面、过去半年涨幅在池子里排第几、成交额大小。
只读已有的逐笔结果和收盘价，不跑新回测。
"""
import io, json, os
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
import numpy as np, pandas as pd, pyarrow.parquet as pq
X = pd.read_parquet(os.path.join(HERE, "顶部形态_逐笔_1120.parquet")); X["d"] = pd.to_datetime(X["日"])
MK = {k: pd.read_parquet(os.path.join(ROOT, f"probe/流动性池_1114/流动性池掩膜_{k}.parquet")) for k in "低中高"}
pool = [s for s in MK["中"].columns if MK["中"][s].any()]
fp = os.path.join(ROOT, "probe/newpool_1106/ohlcv_panel_newpool.parquet"); names = pq.ParquetFile(fp).schema_arrow.names
want = {f"('close', '{s}')" for s in pool}
t = pq.read_table(fp, columns=[n for n in names if n in want] + ["date"]).to_pandas(); t.columns = [c[1] if isinstance(c, tuple) else c for c in t.columns]
C = t[[s for s in pool if s in t.columns]].astype(float)
ma200 = C.rolling(200, min_periods=200).mean(); 在200下 = (C < ma200).shift(1); 线向下 = (ma200 < ma200.shift(20)).shift(1)
mom = (C / C.shift(126) - 1).where(MK["中"].reindex(C.index).fillna(False)[C.columns]); rs = mom.rank(axis=1, pct=True).shift(1)
距高 = (C / C.rolling(252, min_periods=120).max() - 1).shift(1)
def 取(df, r): 
    try: return df.at[r.d, r.票]
    except Exception: return np.nan
X["在200日线下"] = [取(在200下, r) for r in X.itertuples()]; X["200日线向下"] = [取(线向下, r) for r in X.itertuples()]
X["半年强弱排名"] = [取(rs, r) for r in X.itertuples()]; X["离一年高点"] = [取(距高, r) for r in X.itertuples()]
X["高成交"] = [bool(MK["高"].at[r.d, r.票]) if (r.票 in MK["高"].columns and r.d in MK["高"].index) else False for r in X.itertuples()]
def st(g):
    r = g.R; w = r[r > 0].sum(); l = -r[r < 0].sum()
    return {"笔": int(len(g)), "每笔R": round(float(r.mean()), 3), "利润因子": round(float(w / l), 2) if l > 0 else None, "赚钱pct": round(float((r > 0).mean() * 100), 1)}
out = {}
for 进, g in X.groupby("进法"):
    o = {}
    a = g.dropna(subset=["在200日线下"])
    o["按自己的200日线"] = {"在200日线上方": st(a[a["在200日线下"] == False]), "在200日线下方": st(a[a["在200日线下"] == True]),
                        "在200日线下方_且线在往下走": st(a[(a["在200日线下"] == True) & (a["200日线向下"] == True)])}
    b = g.dropna(subset=["半年强弱排名"]); b = b.assign(档=pd.cut(b["半年强弱排名"], [0, .2, .4, .6, .8, 1.0], labels=["最弱的五分之一", "偏弱", "中", "偏强", "最强的五分之一"]))
    o["按过去半年涨幅在池子里的排名"] = {str(k): st(v) for k, v in b.groupby("档", observed=True)}
    c = g.dropna(subset=["离一年高点"]); c = c.assign(档=pd.cut(c["离一年高点"], [-1, -0.5, -0.3, -0.15, -0.05, 0.01], labels=["离高点跌了50%以上", "跌30%~50%", "跌15%~30%", "跌5%~15%", "离高点不到5%"]))
    o["按离一年高点多远"] = {str(k): st(v) for k, v in c.groupby("档", observed=True)}
    o["按成交额"] = {"每天2000万美元以上": st(g[g["高成交"]]), "1000万~2000万": st(g[~g["高成交"]])}
    d = a[(a["在200日线下"] == True) & (a["200日线向下"] == True)]
    o["弱票_分形态"] = {str(k): st(v) for k, v in d.groupby("形态")}
    o["弱票_分年"] = {int(k): st(v) for k, v in d.groupby("年")}
    o["弱票里再挑最弱五分之一"] = st(d[d["半年强弱排名"] <= 0.2])
    out[进] = o
io.open(os.path.join(HERE, "做空按票的强弱分_结果_1120.json"), "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
for 进, o in out.items():
    print("=====", 进)
    for k, v in o.items(): print(k); [print("   ", a, b) for a, b in (v.items() if isinstance(list(v.values())[0], dict) else [("", v)])]
