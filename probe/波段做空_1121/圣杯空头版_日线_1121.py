# -*- coding: utf-8 -*-
"""波段做空 · 做法①「圣杯空头版」(只用日线) · 引擎外脚本,不碰 engine/
规则照《341-Gemini原文回答-波段做空-1120.md》A 组策略一、C 组规则 9.1~9.4、规则 10 的次数限制。
不看未来:信号在 t 日收盘定,t+1 日触发才进;同一天又碰止损又碰目标 → 算先碰止损。
"""
import os, io, sys, json
import numpy as np, pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
D = os.path.join(ROOT, "market_ext_1105/ETF和币_1120/日线")
OUT = os.path.dirname(os.path.abspath(__file__))
组 = {"指数": ["SPY", "QQQ", "IWM", "DIA"],
      "行业": ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC", "SMH", "KRE"],
      "三倍杠杆": ["TQQQ", "SOXL"]}
SLIP = 0.0015; BORROW = 0.01
段 = {"2005–2014": ("2005-01-01", "2014-12-31"), "2015–2025": ("2015-01-01", "2025-12-31")}

def load(sym):
    d = pd.read_csv(os.path.join(D, sym + "_日线.csv"), parse_dates=["date"]).set_index("date").sort_index()
    x = pd.DataFrame({"o": d.open_adj, "h": d.high_adj, "l": d.low_adj, "c": d.close_adj, "v": d.volume_adj,
                      "div": d.dividend_amount / d.adj_factor})
    if sym == "XLF":   # 2016-09-19 分出 XLRE:数据里前后没接上(假跌 6.9%),这里按「那天平盘」接上,并把那笔分配当 0
        t = pd.Timestamp("2016-09-19"); i = x.index.get_loc(t)
        k = x.c.iloc[i] / x.c.iloc[i - 1]
        x.loc[x.index < t, ["o", "h", "l", "c"]] *= k; x.loc[x.index < t, "div"] *= k; x.loc[t, "div"] = 0.0
    return x

def ind(x):
    c, h, l = x.c, x.h, x.l
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    w = lambda s, n: s.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()   # Wilder
    x["atr"] = w(tr, 14)
    up, dn = h.diff(), -l.diff()
    pdm = pd.Series(np.where((up > dn) & (up > 0), up, 0.0), x.index); mdm = pd.Series(np.where((dn > up) & (dn > 0), dn, 0.0), x.index)
    pdi, mdi = 100 * w(pdm, 14) / x.atr, 100 * w(mdm, 14) / x.atr
    x["pdi"], x["mdi"] = pdi, mdi
    x["adx"] = w(100 * (pdi - mdi).abs() / (pdi + mdi).replace(0, np.nan), 14)
    x["ema20"] = c.ewm(span=20, adjust=False, min_periods=20).mean()
    x["sma50"], x["sma200"] = c.rolling(50).mean(), c.rolling(200).mean()
    x["vma20"] = x.v.rolling(20).mean()
    x["newlow20"] = l < l.shift(1).rolling(20).min()
    d = c.diff(); x["rsi"] = 100 - 100 / (1 + w(d.clip(lower=0), 14) / w((-d).clip(lower=0), 14))
    return x

def 开关表(spy):
    s = ind(spy.copy()); c = s.c
    c91 = (c < s.sma200) & (s.sma200 < s.sma200.shift(20))
    c92 = (s.ema20 < s.sma50) & (s.sma50 < s.sma200) & (s.sma50 < s.sma50.shift(10)) & ((c < s.sma200).rolling(15).sum() >= 10)
    c93 = (c >= s.ema20 - s.atr) & (s.rsi >= 35) & (s.rsi <= 62) & (s.adx >= 20) & (s.mdi > s.pdi)
    sq = (c / c.shift(1) - 1 >= 0.018) & (s.v > 1.2 * s.vma20) & ((c - s.l) / (s.h - s.l).clip(lower=1e-4) >= 0.75)
    c94 = sq.rolling(5).sum() == 0
    return pd.DataFrame({"不限": True, "熊市确认(C组四条)": c91 & c92 & c93 & c94,
                         "刚转弱(50日线下、200日线上)": (c < s.sma50) & (c > s.sma200),
                         "只看200日线下": c < s.sma200}).fillna(False)

def 出场(x, i, entry, stop, tp1, 用EMA=True):
    """i = 进场那天的位置。返回 (毛R, 天数, 出场位置, 怎么出的, 分红合计)。做空。"""
    R = stop - entry; tp2 = entry - 2.5 * R
    pos, real, be, hit1 = 1.0, 0.0, entry - 0.05 * x.atr.iloc[i - 1], False
    div = 0.0; maxfav = 0.0
    n = len(x); j = i; 待平 = None
    while j < n:
        o, h, l, c = x.o.iloc[j], x.h.iloc[j], x.l.iloc[j], x.c.iloc[j]
        if j > i:
            div += pos * x["div"].iloc[j]
            if 待平:                       # 昨天收盘决定今天开盘走
                return real + pos * (entry - o), j - i, j, 待平, div
            if o >= stop:                  # 跳空过止损,按开盘价
                return real + pos * (entry - o), j - i, j, "止损(跳空)" if not hit1 else "保本(跳空)", div
        if h >= stop:
            return real + pos * (entry - stop), j - i, j, "止损" if not hit1 else "保本", div
        if not hit1 and l <= tp1:
            px = min(o, tp1) if j > i else tp1
            real += 0.5 * (entry - px); pos = 0.5; hit1 = True; stop = be
        if hit1 and l <= tp2:
            px = min(o, tp2) if j > i else tp2
            return real + pos * (entry - px), j - i, j, "第二目标", div
        maxfav = max(maxfav, entry - l)
        k = j - i + 1
        if 用EMA and hit1 and c > x.ema20.iloc[j]: 待平 = "收盘站回20日线"   # 原文把它写在「第二目标」里,是给第一目标之后剩下那一半用的移动止盈
        elif k >= 8 and maxfav < R and not hit1: 待平 = "8天没到1R"
        elif k >= 20: 待平 = "满20天"
        j += 1
    return real + pos * (entry - x.c.iloc[-1]), n - 1 - i, n - 1, "数据到头", div

def 找信号(x, 要缩量=True):
    x = ind(x); n = len(x); out = []
    adx10 = x.adx.rolling(10).max() > 30
    low10 = x.newlow20.rolling(10).max() > 0
    zl, zh = x.ema20 - 0.3 * x.atr, x.ema20 + 0.5 * x.atr
    rng = (x.h - x.l).clip(lower=1e-9)
    base = (x.c < x.sma50) & (x.ema20 < x.sma50) & adx10 & low10 & (x.h >= zl) & (x.h <= zh + 10 * x.atr) \
        & ((x.c - x.l) / rng <= 0.40) & (x.c <= x.ema20 + 0.2 * x.atr)
    for t in np.where(base.values)[0]:
        if t + 1 >= n or t < 220: continue
        # 反弹期间 = 最近一次创 20 日新低之后到信号日;期间每天量都小于 20 日均量
        nl = np.where(x.newlow20.values[max(0, t - 10):t + 1])[0]
        if len(nl) == 0: continue
        s0 = max(0, t - 10) + nl[-1]
        if s0 >= t: continue                      # 创新低当天不算反弹
        if 要缩量 and not (x.v.values[s0 + 1:t + 1] < x.vma20.values[s0 + 1:t + 1]).all(): continue
        atr = x.atr.iloc[t]; sl, sh = x.l.iloc[t], x.h.iloc[t]
        trig = sl - 0.05 * atr
        o1, l1 = x.o.iloc[t + 1], x.l.iloc[t + 1]
        if o1 > sh or l1 > trig: continue         # 高开过信号 K 高点作废;没跌破不进
        entry = min(o1, trig)
        stop = max(sh, x.h.iloc[t - 4:t + 1].max()) + 0.35 * atr
        R = stop - entry
        if R <= 0: continue
        swing = x.l.iloc[s0]                       # 前一个波段低点 = 那次 20 日新低
        tp1 = max(swing, entry - 1.2 * R) if swing < entry else entry - 1.2 * R
        out.append((t, entry, stop, tp1))
    return x, out

def 一笔(x, t, entry, stop, tp1, sym):
    R = stop - entry
    g, days, j, how, div = 出场(x, t + 1, entry, stop, tp1)
    cal = (x.index[j] - x.index[t + 1]).days
    cost = 2 * SLIP * entry + BORROW * entry * cal / 365.0 + div
    return {"票": sym, "信号日": x.index[t], "进场日": x.index[t + 1], "出场日": x.index[j], "进场价": entry, "止损": stop,
            "毛R": g / R, "净R": (g - cost) / R, "天数": days, "怎么出的": how, "风险占价pct": 100 * R / entry}

def 随机对照(x, 真信号, sym, 次=100, seed=7):
    """同一只票、同一年里随机挑同样多的日子做空:t 日收盘定,t+1 开盘进,止损=max(当日高,5日高)+0.35ATR,出场规则一样。"""
    rng = np.random.default_rng(seed); n = len(x); res = []
    yrs = pd.Series([x.index[t + 1].year for t, *_ in 真信号]).value_counts()
    for y, k in yrs.items():
        cand = np.where((x.index.year == y))[0]; cand = cand[(cand > 220) & (cand < n - 2)]
        if len(cand) == 0: continue
        for t in rng.choice(cand, size=k * 次, replace=True):
            entry = x.o.iloc[t + 1]; atr = x.atr.iloc[t]
            stop = max(x.h.iloc[t], x.h.iloc[t - 4:t + 1].max()) + 0.35 * atr
            if stop <= entry or not np.isfinite(atr): continue
            R = stop - entry
            res.append(一笔(x, t, entry, stop, entry - 1.2 * R, sym))
    return pd.DataFrame(res)

def 次数限制(df):
    """C 组规则 10:每周最多 3 笔;连亏 2 笔停 5 个交易日;当月累计亏到 3R 当月停。按进场日先后过一遍。"""
    df = df.sort_values(["进场日", "票"]); keep = []; 连亏 = 0; 冷到 = pd.Timestamp("1900-01-01"); 周 = {}; 月 = {}
    for _, r in df.iterrows():
        d = r["进场日"]; wk = (d.isocalendar()[0], d.isocalendar()[1]); mo = (d.year, d.month)
        if d <= 冷到 or 周.get(wk, 0) >= 3 or 月.get(mo, 0.0) <= -3.0: continue
        keep.append(r); 周[wk] = 周.get(wk, 0) + 1; 月[mo] = 月.get(mo, 0.0) + r["净R"]
        连亏 = 连亏 + 1 if r["净R"] < 0 else 0
        if 连亏 >= 2: 冷到 = r["出场日"] + pd.tseries.offsets.BDay(5); 连亏 = 0
    return pd.DataFrame(keep)

def 汇总(df, col="净R"):
    if len(df) == 0: return {"笔数": 0}
    r = df[col]; w, l = r[r > 0], r[r <= 0]
    eq = r.cumsum(); dd = (eq - eq.cummax()).min()
    return {"笔数": int(len(r)), "每笔R": round(r.mean(), 3), "赚钱的笔pct": round(100 * (r > 0).mean(), 1),
            "利润因子": round(w.sum() / -l.sum(), 2) if l.sum() < 0 else None, "合计R": round(r.sum(), 1),
            "最深回撤R": round(dd, 1), "平均天数": round(df["天数"].mean(), 1)}

def main():
    要缩量 = os.environ.get("XING_NOVOL") != "1"
    spy = load("SPY"); sw = 开关表(spy)
    全, 随 = [], []
    for g, syms in 组.items():
        for s in syms:
            x, sig = 找信号(load(s), 要缩量)
            for t, e, st, tp in sig:
                r = 一笔(x, t, e, st, tp, s); r["组"] = g
                for k in sw.columns: r[k] = bool(sw[k].reindex([x.index[t]]).fillna(False).iloc[0])
                全.append(r)
            if sig:
                rd = 随机对照(x, sig, s); rd["组"] = g; 随.append(rd)
    df = pd.DataFrame(全); rd = pd.concat(随, ignore_index=True)
    tag = "" if 要缩量 else "_不要求缩量"
    df.to_csv(os.path.join(OUT, f"圣杯空头版_逐笔{tag}.csv"), index=False)
    res = {}
    for pn, (a, b) in 段.items():
        m = df[(df["进场日"] >= a) & (df["进场日"] <= b)]; mr = rd[(rd["进场日"] >= a) & (rd["进场日"] <= b)]
        for g in ["指数", "行业", "三倍杠杆", "指数+行业"]:
            mg = m[m["组"].isin(["指数", "行业"])] if g == "指数+行业" else m[m["组"] == g]
            rg = mr[mr["组"].isin(["指数", "行业"])] if g == "指数+行业" else mr[mr["组"] == g]
            for k in sw.columns:
                z = mg[mg[k]]
                res[f"{pn}|{g}|{k}"] = {"扣成本前": 汇总(z, "毛R"), "扣成本后": 汇总(z, "净R"),
                                         "加次数限制后": 汇总(次数限制(z)) if len(z) else {"笔数": 0}}
            res[f"{pn}|{g}|随机对照"] = {"扣成本前每笔R": round(rg["毛R"].mean(), 3) if len(rg) else None,
                                         "扣成本后每笔R": round(rg["净R"].mean(), 3) if len(rg) else None, "抽了多少笔": int(len(rg))}
        z = m[m["组"].isin(["指数", "行业"])]
        res[f"{pn}|指数+行业|分年(不限)"] = {int(y): {"笔": int(len(v)), "净R合计": round(v["净R"].sum(), 1)} for y, v in z.groupby(z["进场日"].dt.year)}
        res[f"{pn}|指数+行业|怎么出的(不限)"] = z["怎么出的"].value_counts().to_dict()
    json.dump(res, io.open(os.path.join(OUT, f"圣杯空头版_汇总{tag}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    for k, v in res.items():
        if "指数+行业" in k: print(k, json.dumps(v, ensure_ascii=False, default=str)[:330])

main()
