# -*- coding: utf-8 -*-
"""Lin 11-21 的说法:要先有大型派发顶,才有日线级别的回调;这次走空很强。
把历史上的转跌分组看:前面有没有派发顶 / 破位那天强不强 → 之后 60 天有没有不一样。只读数据,不碰引擎。
派发顶(三档松紧并排,免得挑数):转跌前 N 天里出现过 252 日新高(说明是在高位),
  且这 N 天收盘价的高低差 ≤ K 倍日均波幅(横着走),且这 N 天下跌日的平均成交量 > 上涨日的(出货)。
"""
import os, io, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
P1 = os.path.join(HERE, "减仓五种并排_1121.py")
B = {"__file__": P1}; exec(compile(io.open(P1, encoding="utf-8").read().replace("\nmain()\n", "\n"), "b", "exec"), B)
load, ind, 事件, 组 = B["load"], B["ind"], B["事件"], B["组"]

def 特征(x, t):
    r = {}
    c, v = x.c, x.v
    for N, K in [(30, 6), (30, 8), (30, 10), (60, 10), (60, 14)]:
        w = slice(t - N, t)
        hi252 = (x.h.iloc[t - N:t] >= x.h.rolling(252).max().iloc[t - N:t] * 0.999).any()
        flat = (c.iloc[w].max() - c.iloc[w].min()) <= K * x.atr.iloc[t]
        ch = c.diff().iloc[w]; dn, up = v.iloc[w][ch < 0].mean(), v.iloc[w][ch > 0].mean()
        r[f"派发_{N}天_{K}倍"] = bool(hi252 and flat and dn > up)
    drop = (c.iloc[t - 1] - c.iloc[t]) / x.atr.iloc[t - 1]
    r["破位那天跌了几倍波幅"] = drop; r["破位那天量比"] = v.iloc[t] / x.vma20.iloc[t - 1]
    r["强破位"] = bool(drop >= 1.5 and r["破位那天量比"] >= 1.5)
    r["离一年高点pct"] = 100 * (c.iloc[t] / x.h.iloc[t - 252:t].max() - 1)
    r["f20"] = c.iloc[t + 20] / c.iloc[t] - 1; r["f60"] = c.iloc[t + 60] / c.iloc[t] - 1
    r["dd60"] = x.l.iloc[t + 1:t + 61].min() / c.iloc[t] - 1
    return r

def 扫(名, 取):
    rows = []
    for s in 名:
        x = 取(s)
        if x is None or len(x) < 600: continue
        x = ind(x)
        for t in 事件(x):
            if t < 260 or not ("2005-01-01" <= str(x.index[t])[:10] <= "2025-12-31"): continue
            r = 特征(x, t); r["票"] = s; r["日"] = x.index[t]; rows.append(r)
    return pd.DataFrame(rows)

def 报(df, 标):
    out = {}
    def one(m):
        if len(m) == 0: return {"次数": 0}
        return {"次数": int(len(m)), "60天后涨回来pct": round(100 * (m.f60 > 0).mean(), 1), "60天后平均pct": round(100 * m.f60.mean(), 2), "60天后中位pct": round(100 * m.f60.median(), 2),
                "60天后跌超10pct占比": round(100 * (m.f60 < -0.10).mean(), 1), "中途最深_中位pct": round(100 * m.dd60.median(), 2), "中途跌超15pct占比": round(100 * (m.dd60 < -0.15).mean(), 1)}
    out["全部"] = one(df)
    for k in [c for c in df.columns if c.startswith("派发_")]:
        out[k + "|有"] = one(df[df[k]]); out[k + "|没有"] = one(df[~df[k]])
    out["强破位|是"] = one(df[df["强破位"]]); out["强破位|否"] = one(df[~df["强破位"]])
    k = "派发_30天_8倍"; out["有派发且强破位"] = one(df[df[k] & df["强破位"]])
    for a, b, nm in [(-3, 0.1, "离一年高点不到3%"), (-10, -3, "3%到10%"), (-100, -10, "已经跌了10%以上")]:
        out["破位时" + nm] = one(df[(df["离一年高点pct"] > a) & (df["离一年高点pct"] <= b)])
    for pn, (a, b) in {"2005–2014": ("2005", "2015"), "2015–2025": ("2015", "2026")}.items():
        m = df[(df["日"] >= a) & (df["日"] < b)]
        out[f"{pn}|{k}|有"] = one(m[m[k]]); out[f"{pn}|{k}|没有"] = one(m[~m[k]])
        out[f"{pn}|强破位|是"] = one(m[m["强破位"]]); out[f"{pn}|强破位|否"] = one(m[~m["强破位"]])
    print("=====", 标)
    for kk, vv in out.items(): print(kk, vv)
    return out

res = {}
etf = 扫(组["指数"] + 组["行业"], load); etf.to_csv(os.path.join(HERE, "分组_ETF_逐事件.csv"), index=False); res["ETF"] = 报(etf, "ETF 17 只")
if os.environ.get("XING_STOCK") == "1":
    sp = importlib.util.spec_from_file_location("env", os.path.join(ROOT, "probe/两段时间_1120/环境2004_1120.py")); E = importlib.util.module_from_spec(sp); sp.loader.exec_module(E)
    E.install(只留测试期=False)
    from engine import cache
    P = cache._PANEL; syms = sorted(set(pd.read_csv(os.path.join(HERE, "个股转跌_逐事件.csv"))["票"]))
    def 取(s):
        x = pd.DataFrame({"o": P["open"][s], "h": P["high"][s], "l": P["low"][s], "c": P["close"][s], "v": P["volume"][s]}).dropna().astype(float)
        top, bot = x[["o", "c"]].max(axis=1), x[["o", "c"]].min(axis=1); bh, bl = x.h > top * 1.5, x.l < bot * 0.5
        x.loc[bh, "h"] = top[bh]; x.loc[bl, "l"] = bot[bl]; x["div"] = 0.0; return x
    st = 扫(syms, 取); st.to_csv(os.path.join(HERE, "分组_个股_逐事件.csv"), index=False); res["个股"] = 报(st, "个股 172 只")
json.dump(res, io.open(os.path.join(HERE, "分组_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
