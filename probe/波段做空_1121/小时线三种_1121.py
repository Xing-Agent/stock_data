# -*- coding: utf-8 -*-
"""波段做空 · 做法②③④(要 1 小时 / 4 小时线) · 引擎外脚本,不碰 engine/
规则照《341-Gemini原文回答-波段做空-1120.md》A 组策略二、三、四。只用常规时段的小时线。
不看未来:小时线收线定,下一根开盘进;同一根又碰止损又碰目标 → 算先碰止损;跳空过止损按开盘价。
"""
import os, io, sys, json, glob, importlib.util
import numpy as np, pandas as pd, pyarrow.parquet as pq, pyarrow.compute as pc
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
_s = importlib.util.spec_from_file_location("b1", os.path.join(HERE, "圣杯空头版_日线_1121.py"))
src = io.open(os.path.join(HERE, "圣杯空头版_日线_1121.py"), encoding="utf-8").read().replace("\nmain()\n", "\n")
B = {"__file__": os.path.join(HERE, "圣杯空头版_日线_1121.py")}; exec(compile(src, "b1", "exec"), B)
load, ind, 开关表, 次数限制, 汇总, 组, 段, SLIP, BORROW = (B[k] for k in ["load", "ind", "开关表", "次数限制", "汇总", "组", "段", "SLIP", "BORROW"])
HD = [os.path.join(ROOT, "market_ext_1105/ETF和币_1120/小时线_2004_2014"), os.path.join(ROOT, "market_ext_1105/ETF和币_1120/小时线_2015起")]
SYMS = [s for g in 组.values() for s in g]
坏点数 = {}

def 读小时():
    parts = []
    for d in HD:
        for f in sorted(glob.glob(d + "/*.parquet")):
            t = pq.read_table(f, columns=["symbol", "time_utc", "session", "open_adj", "high_adj", "low_adj", "close_adj", "volume_adj"],
                              filters=[("session", "=", "regular"), ("symbol", "in", SYMS)])
            parts.append(t.to_pandas())
    h = pd.concat(parts, ignore_index=True)
    h["t"] = h.time_utc.dt.tz_convert("America/New_York").dt.tz_localize(None)
    h = h.rename(columns={"open_adj": "o", "high_adj": "h", "low_adj": "l", "close_adj": "c", "volume_adj": "v"})
    return {s: g.sort_values("t").drop_duplicates("t").set_index("t")[["o", "h", "l", "c", "v"]] for s, g in h.groupby("symbol")}

def 备(sym, H):
    d = ind(load(sym))
    c = d.c
    d["ema10"] = c.ewm(span=10, adjust=False, min_periods=10).mean(); d["sma20"] = c.rolling(20).mean()
    w = lambda s, n: s.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    df = c.diff()
    for n in (2, 4): d[f"rsi{n}"] = 100 - 100 / (1 + w(df.clip(lower=0), n) / w((-df).clip(lower=0), n).replace(0, 1e-12))
    d["bbl"] = d.sma20 - 2 * c.rolling(20).std(ddof=0)
    h = H[sym].copy()
    if sym == "XLF":
        t = pd.Timestamp("2016-09-19"); raw = pd.read_csv(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/日线/XLF_日线.csv"), parse_dates=["date"]).set_index("date")
        i = raw.index.get_loc(t); k = raw.close_adj.iloc[i] / raw.close_adj.iloc[i - 1]
        h.loc[h.index < t, ["o", "h", "l", "c"]] *= k
    lim = 0.25 if sym in ("TQQQ", "SQQQ", "SOXL", "SOXS") else 0.08       # 小时线同样清坏点:一根小时线里高(低)出开收盘 8% 以上(三倍杠杆 25%)
    top, bot = h[["o", "c"]].max(axis=1), h[["o", "c"]].min(axis=1)
    bh, bl = h.h > top * (1 + lim), h.l < bot * (1 - lim)
    h.loc[bh, "h"] = top[bh]; h.loc[bl, "l"] = bot[bl]
    坏点数[sym] = int(bh.sum() + bl.sum())
    h["day"] = h.index.normalize()
    h = h[h.day.isin(d.index)]
    dh = h.c.diff(); h["rsi"] = 100 - 100 / (1 + w(dh.clip(lower=0), 14) / w((-dh).clip(lower=0), 14).replace(0, 1e-12))
    h["ema20"] = h.c.ewm(span=20, adjust=False, min_periods=20).mean()
    h["di"] = d.index.get_indexer(h.day)           # 这根小时线属于日线第几行
    return d, h

def 模拟(d, h, k, stop, tp1, tp2, 最长天, 收盘查=None, 到期=("收盘", None)):
    """k = 进场那根小时线的位置,按它的开盘价做空。返回 dict。"""
    n = len(h); entry = h.o.iloc[k]
    R = stop - entry
    if R <= 0 or k >= n: return None
    if tp1 >= entry: tp1 = entry - 1.0 * R
    if tp2 is None or tp2 >= tp1: tp2 = entry - 2.5 * R
    pos, real, hit1 = 1.0, 0.0, False; be = entry
    di0 = h.di.iloc[k]; j = k; how = None; px = None; 触底 = False
    O, Hh, L, C, DI = h.o.values, h.h.values, h.l.values, h.c.values, h.di.values
    while j < n:
        o, hi, lo, c = O[j], Hh[j], L[j], C[j]
        if j > k and o >= stop: px, how = o, ("保本(跳空)" if hit1 else "止损(跳空)"); break
        if hi >= stop: px, how = stop, ("保本" if hit1 else "止损"); break
        if not hit1 and lo <= tp1:
            p = min(o, tp1); real += 0.5 * (entry - p); pos = 0.5; hit1 = True; stop = be
        if hit1 and lo <= tp2: px, how = min(o, tp2), "第二目标"; break
        last_of_day = (j + 1 >= n) or (DI[j + 1] != DI[j])
        if last_of_day:
            day = DI[j]; kday = day - di0 + 1
            if 收盘查 is not None:
                r = 收盘查(day, c, kday, hit1)
                if r: px, how = c, r; break
            if kday >= 最长天:
                if 到期[1] is None or not (c < 到期[1]): px, how = c, f"满{最长天}天"; break
                if kday >= 最长天 + 10: px, how = c, "到头"; break
        j += 1
    if px is None: j = n - 1; px, how = C[-1], "数据到头"
    g = real + pos * (entry - px)
    t0, t1 = h.index[k], h.index[min(j, n - 1)]
    div = d["div"].loc[(d.index > t0.normalize()) & (d.index <= t1.normalize())].sum() * 0.75   # 持仓大约介于全仓和半仓之间,取 0.75
    cost = 2 * SLIP * entry + BORROW * entry * (t1 - t0).days / 365.0 + div
    return {"进场日": t0, "出场日": t1, "进场价": entry, "止损": entry + R, "毛R": g / R, "净R": (g - cost) / R,
            "天数": int(DI[min(j, n - 1)] - di0), "怎么出的": how, "风险占价pct": 100 * R / entry}

def 做法二(d, h):
    out = []; c = d.c
    up = (c > c.shift(1)).astype(int); streak = up.groupby((up == 0).cumsum()).cumsum()
    setup = (c < d.sma200) & (d.sma50 < d.sma200) & (d.sma20 < d.sma20.shift(5)) & (streak >= 2) & (streak <= 4) \
        & ((d.rsi2 >= 90) | (d.rsi4 >= 80)) & (c - d.ema10 > 1.0 * d.atr)
    H, Lo, Cc, Oo, RS, DI = h.h.values, h.l.values, h.c.values, h.o.values, h.rsi.values, h.di.values
    first = {}; 
    for idx, di in enumerate(DI): first.setdefault(di, idx)
    busy = -1
    for t in np.where(setup.values)[0]:
        s0 = t - int(streak.iloc[t]) + 1
        a, b = first.get(s0), first.get(t + 4)           # 触发只在之后 3 个交易日内找
        k0 = first.get(t + 1)
        if a is None or k0 is None: continue
        if b is None: b = len(h)
        armed = False; above = False
        for k in range(a, b - 1):
            if RS[k] > 70: above = True
            if above and RS[k] < 65: armed, above = True, False
            if k < k0 or not armed or k <= busy: continue
            if Cc[k] < Oo[k] and Cc[k - 1] > Oo[k - 1] and Cc[k] < Lo[k - 1]:
                bounce = H[a:k + 1].max(); atr = d.atr.iloc[t]
                stop = bounce + 0.5 * atr; entry = Oo[k + 1]
                R = stop - entry
                if R <= 0: break
                def chk(day, cl, kday, hit1, d=d):
                    return "日线RSI2到15以下" if d.rsi2.iloc[day] <= 15 else None
                e10 = d.ema10.iloc[DI[k + 1] - 1]; bbl = d.bbl.iloc[DI[k + 1] - 1]
                r = 模拟(d, h, k + 1, stop, max(e10, entry - R) if e10 < entry else entry - R, bbl if bbl < entry else None, 5, chk)
                if r: r["信号日"] = d.index[t]; out.append(r); busy = h.index.get_indexer([r["出场日"]])[0]
                break
    return out

def 枢轴低(L, k, w=2):
    """k 之前最近一个已确认的小时线摆动低点(左右各 w 根都更高)。"""
    for i in range(k - w, max(w, k - 60), -1):
        if L[i] <= L[i - w:i].min() and L[i] < L[i + 1:i + w + 1].min(): return L[i]
    return None

def 做法三(d, h):
    out = []; busy = -1
    H, Lo, Cc, Oo, E, DI = h.h.values, h.l.values, h.c.values, h.o.values, h.ema20.values, h.di.values
    first = {}; 
    for idx, di in enumerate(DI): first.setdefault(di, idx)
    body = d.o - d.c
    imp = (d.c < d.o) & (body > 1.2 * d.atr.shift(1)) & (d.v > 1.3 * d.vma20.shift(1))
    for p in np.where(imp.values)[0]:
        if p < 220 or p + 2 >= len(d): continue
        atr = d.atr.iloc[p]
        ih = d.h.iloc[max(0, p - 5):p + 1].max()
        for q in range(p, min(p + 3, len(d) - 2)):            # q = 这波下跌的最低那天
            il = d.l.iloc[p:q + 1].min()
            if d.l.iloc[q] > il or ih - il <= 2.5 * atr: continue
            done = False
            for t in range(q + 2, min(q + 6, len(d))):        # 反弹第 2~5 天
                if not (3 <= t - p <= 7): continue
                if d.l.iloc[q + 1:t + 1].min() < il: break     # 又创新低,不是反弹
                if not (d.v.iloc[q + 1:t + 1] < 0.7 * d.v.iloc[p]).all(): break
                a, b = first.get(t), first.get(t + 1)
                kq = first.get(q + 1)
                if a is None or kq is None: continue
                if b is None: b = len(h)
                for k in range(a, b - 1):
                    if k <= busy: continue
                    rh = H[kq:k + 1].max(); ret = (rh - il) / (ih - il)
                    if not (0.382 <= ret <= 0.618): continue
                    sw = 枢轴低(Lo, k)
                    if sw is None: continue
                    if Cc[k] < Oo[k] and Cc[k] < E[k] and Cc[k] < sw:
                        stop = rh + 0.30 * atr; entry = Oo[k + 1]; R = stop - entry
                        if R <= 0 or il >= entry: continue
                        tp2 = max(rh - (ih - il), entry - 2.5 * R)
                        r = 模拟(d, h, k + 1, stop, il, tp2, 10, None, ("次日", il))
                        if r: r["信号日"] = d.index[t]; out.append(r); busy = h.index.get_indexer([r["出场日"]])[0]
                        done = True; break
                if done: break
            if done: break
    return out

def 拼4h(h):
    g = h.copy(); g["n"] = g.groupby("di").cumcount(); g["blk"] = (g.n >= 4).astype(int)
    a = g.groupby(["di", "blk"]).agg(o=("o", "first"), h=("h", "max"), l=("l", "min"), c=("c", "last"), v=("v", "sum"))
    a["last_k"] = g.reset_index().groupby(["di", "blk"]).apply(lambda z: z.index[-1]).values     # 这根 4 小时线最后一根小时线的位置
    a = a.reset_index()
    e12, e26 = a.c.ewm(span=12, adjust=False).mean(), a.c.ewm(span=26, adjust=False).mean()
    a["macd"] = e12 - e26; a["hst"] = a.macd - a.macd.ewm(span=9, adjust=False).mean()
    return a

def 做法四(d, h):
    out = []; busy = -1; a = 拼4h(h)
    AH, AL, AC, AV, AD, AK, MA, HI = a.h.values, a.l.values, a.c.values, a.v.values, a.di.values, a.last_k.values, a.macd.values, a.hst.values
    Oo, Lo = h.o.values, h.l.values
    for m in range(30, len(a) - 1):
        di = AD[m]
        if di < 220: continue
        y = di - 1
        e10, e20, s50, atr = d.ema10.iloc[y], d.ema20.iloc[y], d.sma50.iloc[y], d.atr.iloc[y]
        if not (e10 < e20 < s50): continue
        if not (AH[m] >= e20 and AH[m] <= s50 + 0.5 * atr): continue
        # 本轮反弹起点:过去 6 个交易日内的最低点(4 小时线)
        lo_m = max(0, m - 12); st = lo_m + int(np.argmin(AL[lo_m:m]))
        days = di - AD[st]
        if not (3 <= days <= 6) or m - st < 4: continue
        # 第一波高点:起点之后、今天之前的最高那根,且之后有回调
        seg = AH[st + 1:m]
        if len(seg) < 3: continue
        p1 = st + 1 + int(np.argmax(seg))
        if p1 >= m - 1: continue
        pull = AL[p1 + 1:m].min()
        if not (AH[m] > AH[p1] and AH[m] - AH[p1] <= 0.5 * atr and AC[m] < AH[p1]): continue
        if not ((MA[m] < MA[p1] or HI[m] < HI[p1]) and AV[m] < AV[p1]): continue
        # 跌破信号 K 最低点进场:之后两根 4 小时线内
        k0 = AK[m] + 1; k1 = AK[min(m + 2, len(a) - 1)]
        if k0 <= busy: continue
        for k in range(k0, k1 + 1):
            if Lo[k] < AL[m]:
                # 用「下一根小时线开盘」进,保守、不偷看
                if k + 1 >= len(h): break
                stop = AH[m] + 0.35 * atr; entry = Oo[k + 1]; R = stop - entry
                if R <= 0: break
                dsl = d.l.iloc[max(0, AD[st] - 20):AD[st] + 1].min()
                cnt = {"n": 0}
                def chk(day, cl, kday, hit1, d=d, cnt=cnt):
                    cnt["n"] = cnt["n"] + 1 if cl > d.sma50.iloc[day] else 0     # 原文是连续两根 4 小时线,这里按连续两天收盘,略宽
                    return "站回50日线" if cnt["n"] >= 2 else None
                r = 模拟(d, h, k + 1, stop, pull if pull < entry else entry - R, dsl if dsl < entry else None, 12, chk)
                if r: r["信号日"] = d.index[di]; out.append(r); busy = h.index.get_indexer([r["出场日"]])[0]
                break
    return out

def 随机(d, h, 真, 次=50, seed=11):
    rng = np.random.default_rng(seed); res = []
    yrs = pd.Series([r["进场日"].year for r in 真]).value_counts()
    Hh = h.h.values; DI = h.di.values; n = len(h)
    for y, k in yrs.items():
        cand = np.where(h.index.year == y)[0]; cand = cand[(cand > 300) & (cand < n - 20)]
        if len(cand) == 0: continue
        for i in rng.choice(cand, size=k * 次, replace=True):
            atr = d.atr.iloc[DI[i] - 1]
            if not np.isfinite(atr): continue
            stop = Hh[i - 14:i].max() + 0.5 * atr
            r = 模拟(d, h, i, stop, -1e9 if False else h.o.iloc[i] - (stop - h.o.iloc[i]), None, 10)
            if r: res.append(r)
    return res

def main():
    H = 读小时(); sw = 开关表(load("SPY")); 全 = []; 随 = []
    名 = {"②短期超买转弱": 做法二, "③长阴后反弹一半": 做法三, "④4小时二次冲高": 做法四}
    for g, syms in 组.items():
        for s in syms:
            if s not in H: continue
            d, h = 备(s, H)
            for nm, fn in 名.items():
                tr = fn(d, h)
                for r in tr:
                    r.update({"票": s, "组": g, "做法": nm})
                    day = r["信号日"]
                    for k in sw.columns: r[k] = bool(sw[k].reindex([day]).fillna(False).iloc[0])
                全 += tr
                if tr:
                    for r in 随机(d, h, tr): r.update({"票": s, "组": g, "做法": nm}); 随.append(r)
    df = pd.DataFrame(全); rd = pd.DataFrame(随); print("小时线坏点", 坏点数)
    df.to_csv(os.path.join(HERE, "小时线三种_逐笔.csv"), index=False)
    res = {}
    for nm in 名:
        for pn, (a, b) in 段.items():
            m = df[(df["做法"] == nm) & (df["进场日"] >= a) & (df["进场日"] <= b + " 23:59")]
            mr = rd[(rd["做法"] == nm) & (rd["进场日"] >= a) & (rd["进场日"] <= b + " 23:59")]
            for g in ["指数", "行业", "三倍杠杆", "指数+行业"]:
                sel = (lambda z: z[z["组"].isin(["指数", "行业"])]) if g == "指数+行业" else (lambda z, g=g: z[z["组"] == g])
                mg, rg = sel(m), sel(mr)
                for k in sw.columns:
                    z = mg[mg[k]] if len(mg) else mg
                    res[f"{nm}|{pn}|{g}|{k}"] = {"扣成本前": 汇总(z, "毛R"), "扣成本后": 汇总(z, "净R"), "加次数限制后": 汇总(次数限制(z)) if len(z) else {"笔数": 0}}
                res[f"{nm}|{pn}|{g}|随机对照"] = {"扣成本前每笔R": round(rg["毛R"].mean(), 3) if len(rg) else None, "扣成本后每笔R": round(rg["净R"].mean(), 3) if len(rg) else None, "抽了多少笔": int(len(rg))}
            z = m[m["组"].isin(["指数", "行业"])]
            if len(z):
                res[f"{nm}|{pn}|指数+行业|分年"] = {int(y): {"笔": int(len(v)), "净R合计": round(v["净R"].sum(), 1)} for y, v in z.groupby(z["进场日"].dt.year)}
                res[f"{nm}|{pn}|指数+行业|怎么出的"] = z["怎么出的"].value_counts().to_dict()
    json.dump(res, io.open(os.path.join(HERE, "小时线三种_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    for k, v in res.items():
        if "指数+行业" not in k: continue
        if "扣成本前" in v and isinstance(v["扣成本前"], dict):
            a, b, c = v["扣成本前"], v["扣成本后"], v["加次数限制后"]
            print(k, "| 笔", a.get("笔数"), "毛R", a.get("每笔R"), "净R", b.get("每笔R"), "胜", b.get("赚钱的笔pct"), "PF", b.get("利润因子"), "| 限后", c.get("笔数"), c.get("每笔R"))
        else: print(k, json.dumps(v, ensure_ascii=False, default=str)[:260])

main()
