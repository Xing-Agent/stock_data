# -*- coding: utf-8 -*-
"""欧奈尔「派发日」计数 + 市场宽度:能不能把转跌分成「之后深跌」和「之后涨回来」。只读数据,不碰引擎。
派发日:指数当天收盘跌 ≥0.2% 且成交量大于前一天;数最近 25 个交易日里有几个(SPY、QQQ 各数,取多的那个)。
宽度(每天成交 1000 万美元以上、收盘 ≥5 美元的票):收盘在 50 日线上方的占比;创 52 周新高的票占比。
背离:SPY 最近 20 天创过一年新高,但那 20 天里「站上 50 日线占比」的最高值比再之前 60 天的最高值低 10 个点以上。
"""
import os, io, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
P1 = os.path.join(HERE, "减仓五种并排_1121.py")
B = {"__file__": P1}; exec(compile(io.open(P1, encoding="utf-8").read().replace("\nmain()\n", "\n"), "b", "exec"), B)
load = B["load"]

def 派发日数(sym):
    x = load(sym); d = (x.c / x.c.shift(1) - 1 <= -0.002) & (x.v > x.v.shift(1))
    return d.rolling(25).sum()

dd = pd.concat([派发日数("SPY"), 派发日数("QQQ")], axis=1).max(axis=1)

cache_f = os.path.join(HERE, "宽度_每日.csv")
if os.path.exists(cache_f):
    br = pd.read_csv(cache_f, parse_dates=["date"]).set_index("date")
else:
    sp = importlib.util.spec_from_file_location("env", os.path.join(ROOT, "probe/两段时间_1120/环境2004_1120.py")); E = importlib.util.module_from_spec(sp); sp.loader.exec_module(E)
    info = E.install(只留测试期=False)
    from engine import cache
    P = cache._PANEL; drop = set(info["拿掉"]); cols = [c for c in P["close"].columns if c not in drop]
    c = P["close"][cols].astype("float32"); v = P["volume"][cols].astype("float32")
    adv = (c * v).rolling(20, min_periods=20).mean(); ok = (adv >= 1e7) & (c >= 5)
    ma50 = c.rolling(50, min_periods=50).mean(); hi = P["high"][cols].astype("float32"); h252 = hi.rolling(252, min_periods=200).max()
    n = ok.sum(axis=1)
    br = pd.DataFrame({"池里几只": n, "站上50日线pct": 100 * ((c > ma50) & ok).sum(axis=1) / n, "创一年新高pct": 100 * ((hi >= h252) & ok).sum(axis=1) / n})
    br.index.name = "date"; br.to_csv(cache_f)
spy = load("SPY"); nh = spy.h >= spy.h.rolling(252).max() * 0.999
a50 = br["站上50日线pct"].reindex(spy.index)
背离 = (nh.rolling(20).max() > 0) & (a50.rolling(20).max() < a50.shift(20).rolling(60).max() - 10)

ev = pd.read_csv(os.path.join(HERE, "分组_ETF_逐事件.csv"), parse_dates=["日"])
ev["派发日数"] = dd.reindex(ev["日"]).values
ev["站上50日线pct"] = a50.reindex(ev["日"]).values
ev["创新高pct_20日均"] = br["创一年新高pct"].rolling(20).mean().reindex(ev["日"]).values
ev["背离"] = 背离.reindex(ev["日"]).fillna(False).values
ev = ev.dropna(subset=["派发日数", "站上50日线pct"])
ev.to_csv(os.path.join(HERE, "派发日和宽度_逐事件.csv"), index=False)

def one(m):
    if len(m) == 0: return {"次数": 0}
    return {"次数": int(len(m)), "不同的日子": int(m["日"].nunique()), "涨回来pct": round(100 * (m.f60 > 0).mean(), 1), "60天平均pct": round(100 * m.f60.mean(), 2),
            "60天后跌超10pct": round(100 * (m.f60 < -0.10).mean(), 1), "中途跌超15pct": round(100 * (m.dd60 < -0.15).mean(), 1)}
res = {}
for 标, m0 in [("四只指数", ev[ev["票"].isin(["SPY", "QQQ", "IWM", "DIA"])]), ("全部17只", ev)]:
    for pn, (a, b) in {"两段合起来": ("2005", "2026"), "2005–2014": ("2005", "2015"), "2015–2025": ("2015", "2026")}.items():
        m = m0[(m0["日"] >= a) & (m0["日"] < b)]; r = {"全部": one(m)}
        for k in (4, 5, 6):
            r[f"派发日≥{k}"] = one(m[m["派发日数"] >= k]); r[f"派发日<{k}"] = one(m[m["派发日数"] < k])
        for lo, hi, nm in [(0, 40, "站上50日线的票不到40%"), (40, 60, "40%到60%"), (60, 101, "60%以上")]:
            r["宽度:" + nm] = one(m[(m["站上50日线pct"] >= lo) & (m["站上50日线pct"] < hi)])
        r["有背离"] = one(m[m["背离"]]); r["没背离"] = one(m[~m["背离"]])
        r["派发日≥5 且 宽度<40%"] = one(m[(m["派发日数"] >= 5) & (m["站上50日线pct"] < 40)])
        res[f"{标}|{pn}"] = r
json.dump(res, io.open(os.path.join(HERE, "派发日和宽度_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for k, v in res.items():
    print("=====", k)
    for a, b in v.items(): print("  ", a, b)
print("宽度样本", br.loc["2005":"2025"].describe().round(1).T.to_string())
