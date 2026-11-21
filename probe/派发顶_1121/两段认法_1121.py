# -*- coding: utf-8 -*-
"""《拍板·361 派发顶》第 1~4 项:预警段逐项、确认段、SPY 回调清单、快顶提示。引擎外,只读。
指标定义照《361-Gemini原文回答-派发顶-1121.md》;原文没写死的地方在各处注明我的读法。
"""
import os, io, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
P1 = os.path.join(ROOT, "probe/减仓_1121/减仓五种并排_1121.py")
B = {"__file__": P1}; exec(compile(io.open(P1, encoding="utf-8").read().replace("\nmain()\n", "\n"), "b", "exec"), B)
load, ind, 事件, 组 = B["load"], B["ind"], B["事件"], B["组"]
ETF = 组["指数"] + 组["行业"]

# ---------- 面板:个股 + 宽度三项 ----------
sp = importlib.util.spec_from_file_location("env", os.path.join(ROOT, "probe/两段时间_1120/环境2004_1120.py")); E = importlib.util.module_from_spec(sp); sp.loader.exec_module(E)
info = E.install(只留测试期=False)
from engine import cache
P = cache._PANEL; drop = set(info["拿掉"]); cols = [c for c in P["close"].columns if c not in drop]
c = P["close"][cols].astype("float32"); v = P["volume"][cols].astype("float32"); hi = P["high"][cols].astype("float32"); lo = P["low"][cols].astype("float32")
ok = ((c * v).rolling(20, min_periods=20).mean() >= 1e7) & (c >= 5); n = ok.sum(axis=1)
ma50 = c.rolling(50, min_periods=50).mean()
br = pd.DataFrame({"b50": 100 * ((c > ma50) & ok).sum(axis=1) / n,
                   "新高pct": 100 * ((hi >= hi.rolling(252, min_periods=200).max()) & ok).sum(axis=1) / n,
                   "新低pct": 100 * ((lo <= lo.rolling(252, min_periods=200).min()) & ok).sum(axis=1) / n})
ret = c.pct_change(); ret = ret.where(ok.shift(1).fillna(False) & (ret.abs() < 0.6))
br["等权净值"] = (1 + ret.mean(axis=1).fillna(0)).cumprod()
spy = ind(load("SPY")); qqq = ind(load("QQQ"))
br = br.reindex(spy.index).ffill()
ratio = br["等权净值"] / spy.c; br["等权比标普在50日线下"] = ratio < ratio.rolling(50).mean()
br["新低多于新高连5天"] = (br["新低pct"] > br["新高pct"]).rolling(5).sum() == 5
spy_near = spy.c >= spy.c.rolling(252).max() * 0.97
was75 = br["b50"].rolling(60).max() > 75
br["宽度从75跌破50"] = was75 & (br["b50"] < 50)
br["宽度从75跌破50且指数离高点3%内"] = (was75 & (br["b50"] < 50) & spy_near).rolling(20).max() > 0     # 最近 20 天里出现过
def 派发日(x):
    r = x.c / x.c.shift(1) - 1
    dd = (r <= -0.002) & (x.v > x.v.shift(1))
    stall = (r >= 0) & (r <= 0.002) & (x.v > x.v.shift(1)) & ((x.c - x.l) / (x.h - x.l).clip(lower=1e-6) < 0.5)      # 放量滞涨日也算一个
    f = (dd | stall).values; cl = x.c.values; out = np.zeros(len(x))
    for i in range(len(x)):
        k = 0
        for j in range(max(0, i - 24), i + 1):
            if f[j] and cl[j + 1:i + 1].max(initial=0) < cl[j] * 1.05: k += 1       # 之后涨过 5% 的作废
        out[i] = k
    return pd.Series(out, x.index)
br["派发日数"] = pd.concat([派发日(spy), 派发日(qqq)], axis=1).max(axis=1)
br.to_csv(os.path.join(HERE, "宽度和派发日_每日.csv"))

# ---------- 每只票的预警指标 ----------
def 备(x):
    x = ind(x); rng = (x.h - x.l).clip(lower=1e-6)
    x["clv01"] = (x.c - x.l) / rng; x["clv"] = (2 * x.c - x.h - x.l) / rng
    x["v50"] = x.v.rolling(50).mean(); r = x.c / x.c.shift(1) - 1
    churn = (x.v > 1.3 * x.v50.shift(1)) & ((r.abs() < 0.004) | (x.clv01 < 0.35))
    x["滞涨日20"] = churn.rolling(20).sum()
    x["低收放量日20"] = ((x.clv01 < 0.30) & (x.v > 1.2 * x.v50.shift(1))).rolling(20).sum()
    x["clv20"] = x.clv.rolling(20).mean()
    x["cmf20"] = (x.clv * x.v).rolling(20).sum() / x.v.rolling(20).sum()
    tr = pd.concat([x.h - x.l, (x.h - x.c.shift(1)).abs(), (x.l - x.c.shift(1)).abs()], axis=1).max(axis=1) / x.c
    x["波动扩张"] = tr.rolling(20).mean() / tr.rolling(20).mean().shift(60)
    x["一年涨幅"] = x.c / x.c.shift(250) - 1
    x["离一年高点"] = x.c / x.h.rolling(252).max() - 1
    return x

def 小时指标(sym):
    """ETF:最近 20 天里「最后一小时下跌且量占全天 25% 以上」的天数;最后两小时累计涨跌减去头两小时的(20 天合计)。"""
    import pyarrow.parquet as pq, glob
    parts = []
    for d in ("小时线_2004_2014", "小时线_2015起"):
        for f in sorted(glob.glob(os.path.join(ROOT, "market_ext_1105/ETF和币_1120", d, "*.parquet"))):
            parts.append(pq.read_table(f, columns=["symbol", "time_utc", "open_adj", "close_adj", "volume_adj"], filters=[("session", "=", "regular"), ("symbol", "=", sym)]).to_pandas())
    h = pd.concat(parts); h["t"] = h.time_utc.dt.tz_convert("America/New_York").dt.tz_localize(None); h = h.sort_values("t"); h["day"] = h.t.dt.normalize()
    h["r"] = h.close_adj / h.open_adj - 1; g = h.groupby("day")
    h["k"] = g.cumcount(); h["kn"] = g["k"].transform("max")
    last = h[h.k == h.kn].set_index("day"); tot = g.volume_adj.sum()
    tail_bad = (last.r < 0) & (last.volume_adj / tot > 0.25)
    last2 = h[h.k >= h.kn - 1].groupby("day").r.sum(); first2 = h[h.k <= 1].groupby("day").r.sum()
    return pd.DataFrame({"尾盘放量跌20": tail_bad.rolling(20).sum(), "尾盘减早盘20": (last2 - first2).rolling(20).sum()})

def 特征(x, t, extra=None):
    r = {k: float(x[k].iloc[t]) for k in ["滞涨日20", "低收放量日20", "clv20", "cmf20", "波动扩张", "一年涨幅", "离一年高点"]}
    d = x.index[t]
    for k in ["派发日数", "b50"]: r[k] = float(br[k].get(d, np.nan))
    for k in ["等权比标普在50日线下", "新低多于新高连5天", "宽度从75跌破50", "宽度从75跌破50且指数离高点3%内"]: r[k] = bool(br[k].get(d, False))
    if extra is not None and d in extra.index: r.update({k: float(extra[k].loc[d]) for k in extra.columns})
    cc = x.c
    r["f20"] = cc.iloc[t + 20] / cc.iloc[t] - 1; r["f60"] = cc.iloc[t + 60] / cc.iloc[t] - 1; r["dd60"] = x.l.iloc[t + 1:t + 61].min() / cc.iloc[t] - 1
    return r

def 确认段(x):
    """先跌 8% 以上 → 反弹(从低点弹 4% 以上)过不了前高 → 收盘再跌破前低。前高 = 过去 252 天最高收盘。不偷看。"""
    cl, hi_, lo_ = x.c.values, x.h.values, x.l.values; out = []; state = 0; peak = L1 = 0.0; i = 260; pk = cl[8:260].max() if len(cl) > 260 else 0
    roll = pd.Series(cl).rolling(252).max().values
    while i < len(cl) - 61:
        if state == 0:
            peak = roll[i - 1]
            if cl[i] <= peak * 0.92: state, L1, bounced = 1, lo_[i], False
        else:
            if cl[i] > peak: state = 0
            elif not bounced:
                L1 = min(L1, lo_[i])
                if cl[i] >= L1 * 1.04: bounced = True
            else:
                if cl[i] < L1: out.append((i, cl[i] / peak - 1)); state = 0; i += 20
        i += 1
    return out

def 快顶(x):
    """高位(前一天离一年高点 5% 以内)单日放量长阴:跌幅超过 2 倍 ATR、量 > 1.5 倍 50 日均量、收盘跌破 20 日线(另记是否也破 50 日线)。"""
    r = x.c.shift(1) - x.c
    m = (x["离一年高点"].shift(1) > -0.05) & (r > 2 * x.atr.shift(1)) & (x.v > 1.5 * x.v50.shift(1)) & (x.c < x.ema20)
    return [t for t in np.where(m.values)[0] if 260 < t < len(x) - 61]

rows, conf, fast = [], [], []
def 跑(sym, x, 类, extra=None):
    x = 备(x)
    for t in 事件(x):
        if t < 320 or not ("2005-01-01" <= str(x.index[t])[:10] <= "2025-12-31"): continue
        r = 特征(x, t, extra); r.update({"票": sym, "日": x.index[t], "类": 类}); rows.append(r)
    for t, dpk in 确认段(x):
        if "2005-01-01" <= str(x.index[t])[:10] <= "2025-12-31":
            conf.append({"票": sym, "日": x.index[t], "类": 类, "离前高": dpk, "f20": x.c.iloc[t + 20] / x.c.iloc[t] - 1, "f60": x.c.iloc[t + 60] / x.c.iloc[t] - 1, "dd60": x.l.iloc[t + 1:t + 61].min() / x.c.iloc[t] - 1})
    for t in 快顶(x):
        if "2005-01-01" <= str(x.index[t])[:10] <= "2025-12-31":
            fast.append({"票": sym, "日": x.index[t], "类": 类, "也破50日线": bool(x.c.iloc[t] < x.sma50.iloc[t]), "f20": x.c.iloc[t + 20] / x.c.iloc[t] - 1, "f60": x.c.iloc[t + 60] / x.c.iloc[t] - 1, "dd60": x.l.iloc[t + 1:t + 61].min() / x.c.iloc[t] - 1})
for s in ETF: 跑(s, load(s), "ETF", 小时指标(s))
syms = sorted(set(pd.read_csv(os.path.join(ROOT, "probe/减仓_1121/个股转跌_逐事件.csv"))["票"]))
for s in syms:
    x = pd.DataFrame({"o": P["open"][s], "h": P["high"][s], "l": P["low"][s], "c": P["close"][s], "v": P["volume"][s]}).dropna().astype(float)
    top, bot = x[["o", "c"]].max(axis=1), x[["o", "c"]].min(axis=1); bh, bl = x.h > top * 1.5, x.l < bot * 0.5
    x.loc[bh, "h"] = top[bh]; x.loc[bl, "l"] = bot[bl]; x["div"] = 0.0
    跑(s, x, "个股")
ev = pd.DataFrame(rows); cf = pd.DataFrame(conf); fa = pd.DataFrame(fast)
ev.to_csv(os.path.join(HERE, "预警_逐事件.csv"), index=False); cf.to_csv(os.path.join(HERE, "确认段_逐事件.csv"), index=False); fa.to_csv(os.path.join(HERE, "快顶_逐事件.csv"), index=False)
print(len(ev), len(cf), len(fa)); print(ev.groupby("类")[["滞涨日20", "低收放量日20", "clv20", "cmf20", "波动扩张", "派发日数", "b50"]].median().round(2).to_string())
