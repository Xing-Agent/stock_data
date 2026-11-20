#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""在研发池上验「先看日线行情」那条过滤（2026-11-20 · 回《233》第三节）

大白话：考试那边在 5 只 ETF 上发现「日线上涨才做多」能把 2022 年从 −0.28R 拉到 −0.07R。这里把他们的程序
（probe/技术面大师考试_1119/trig4.py 的 run2，一个字不改）搬到研发池个股上，看这条过滤在个股上有没有用。
  · 数据：研发池小时线 2015–2025，折算价，**只用常规时段**（Lin 11-19 定：个股扳机只看常规时段）。
  · 日线行情：用这只票自己每天常规时段最后一根的收盘当日线收盘，照 lin.py 的 reg()：
      上涨 = 收盘 > 20 日指数均线 > 50 日指数均线，且 20 日均线比 3 天前高；下跌反过来；其余震荡。只用前一天的。
  · 并排四版（底子都是卡 v0.4：早鸟扳机 + 盈亏比双门槛 + 只做前两次 + 分票规则，不带箱体）：
      不加过滤 / 上涨才做多（做空不限，卡上现在这条）/ 上涨才做多且上涨里不做空 / 上涨才做多且下跌才做空
  · 每笔记下当时的日线行情，方便分行情看。成本另算一列：每边 5 个基点。
"""
import io, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
import numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
import pyarrow.dataset as ds
EX = os.path.join(ROOT, "probe/技术面大师考试_1119")
t1 = io.open(os.path.join(EX, "trig.py"), encoding="utf-8").read()
def atr(d, n=14):
    tr = pd.concat([d.high - d.low, (d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()], axis=1).max(axis=1); return tr.rolling(n).mean()
exec("def trend_series" + t1.split("def trend_series")[1].split("def run(")[0])
t4 = io.open(os.path.join(EX, "trig4.py"), encoding="utf-8").read()
exec("def h4info" + t4.split("def h4info")[1].split("\nif __name__")[0].split("\nS={k:v")[0].split("\nS = ")[0])   # run2 原样
def reg(dd):                                                                                    # 照抄 lin.py
    e20 = dd.ewm(span=20).mean(); e50 = dd.ewm(span=50).mean()
    up = (dd > e20) & (e20 > e50) & (e20 > e20.shift(3)); dn = (dd < e20) & (e20 < e50) & (e20 < e20.shift(3))
    r = pd.Series("震荡", index=dd.index); r[up] = "上涨"; r[dn] = "下跌"; return r.shift(1)
D = os.path.join(ROOT, "market_ext_1105/小时线_1119/全量_2015_2025")
N = int(os.environ.get("XING_N", "99999")); OUT = os.path.join(HERE, "out_日线过滤_" + os.environ.get("XING_TAG", "全量")); os.makedirs(OUT, exist_ok=True)
allsym = [l.strip() for l in io.open(os.path.join(ROOT, "probe/挂件_1119/小时线取数名单_研发池中档_1119.txt"), encoding="utf-8") if l.strip()][:N]
files = sorted(f for f in os.listdir(D) if f.endswith(".parquet"))
cols = ["symbol", "time_utc", "open_adj", "high_adj", "low_adj", "close_adj", "volume_adj"]
base = dict(trig="C", rrmode="gem", tk_rules=True, f_n=True)
B = 25
for b in range(0, len(allsym), B):
    fp = os.path.join(OUT, f"批{b // B:03d}.csv")
    if os.path.exists(fp): continue
    grp = allsym[b:b + B]; t0 = time.time()
    df = pd.concat([ds.dataset(os.path.join(D, f)).to_table(columns=cols, filter=ds.field("symbol").isin(grp) & (ds.field("session") == "regular")).to_pandas() for f in files])
    df.columns = ["symbol", "time", "open", "high", "low", "close", "volume"]
    rows = []
    for s, d in df.groupby("symbol"):
        d = d.set_index("time").sort_index(); d = d[~d.index.duplicated()].drop(columns="symbol").dropna(subset=["close"]); d = d[d.close > 0]
        if len(d) < 2000: continue
        day = d.close.groupby(d.index.normalize()).last(); r = reg(day).reindex(d.index.normalize(), method="ffill").values
        up = r == "上涨"; dn = r == "下跌"; one = np.ones(len(d), bool)
        for nm, la, sa in (("不加过滤", None, None), ("上涨才做多_空不限", up, one), ("上涨才做多_上涨里不空", up, ~up), ("上涨才做多_下跌才做空", up, dn)):
            try:
                x = run2(d, s, **base, la=la, sa=sa)
            except Exception as e:
                x = pd.DataFrame(); print("ERR", s, nm, repr(e)[:120], flush=True)
            if len(x):
                x["版"] = nm; x["日线行情"] = pd.Series(r, index=d.index).reindex(pd.to_datetime(x.t, utc=True)).values if d.index.tz is not None else pd.Series(r, index=d.index).reindex(pd.to_datetime(x.t)).values
                rows.append(x)
    (pd.concat(rows) if rows else pd.DataFrame(columns=["票"])).to_csv(fp, index=False)
    print(f"批 {b // B} 完成 {time.time() - t0:.0f}s", flush=True)
print("ALL_DONE", flush=True)
