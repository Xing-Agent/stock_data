# -*- coding: utf-8 -*-
"""《396》第一件 · 第二轮：日线四步不变，进场改成「1 小时线在核心位置出派发」，只做有小时线的 ETF（4 只大指数 + 13 只行业 + SOXX）。
大白话：第一轮是日线收盘跌破前一天低点就空。Lin 的做法是到了核心位置以后看小周期 —— 小周期顶部也出了派发才空，止损可以放得更窄。
这一轮把这一层加上，看能不能把第一轮的负数翻过来。个股没有小时线，不做。

══ 我补的定义（第一轮的 D1~D11 照旧，下面是新加的）══
 H1 日线部分照第一轮：①②认法 a（派发确认，ETF 上认法 b 次数太少，这轮不做）、A ≥ 5 ATR、等反弹 60 天、作废 = 日线收盘站上核心区上沿。
 H2 核心位置四种：0.5 / 0.618 / 0.786 各上下 0.5 ATR；外加「0.618~0.786 整片」（下沿 = 0.618 − 0.5 ATR，上沿 = 0.786 + 0.5 ATR）—— Lin 这次半导体那一下就在这片里。
 H3 小周期派发（只看正常交易时段的 1 小时线）：日线最高价碰进核心区以后，1 小时线收盘跌破「碰进核心区以来、最近 7 根 1 小时线（约一个交易日）的最低价」
    = 小周期破位 → 这根收盘空。邻点：最近 4 根 / 14 根。
 H4 止损两种：宽 = 日线反弹最高价 + 0.25 日线 ATR（同第一轮）；窄（Lin 说的「放针尖」）= 碰进核心区以来 1 小时线最高价 + 0.2 × 1 小时 ATR14。
 H5 目标、出场同第一轮（一半在 1 倍、剩下推保本在 1.618 倍、日线收盘站上核心区上沿全走、最多 120 个交易日），但逐根 1 小时线判，跳空按开盘价，同一根碰止损又碰目标按先止损。
 H5b 被止损后再试（Lin「左小右重」的「左小」那一半）：同一次反弹、日线还没站上核心区上沿、也没跌回 A 低点之前，止损出来以后再等下一次 1 小时破位，最多试 3 次（邻点 1 / 2）。
    每次都是一整份风险，没做「右重」（第几次加大仓位）。
 H6 成本：单边 0.15% + 借券年化 1%（ETF 一般借得到）；不算分红。
 H7 《428》的核心压力位打分器没用：主 chat 自己在《428》里查出它分不出好坏（85% 的日子都有核心带、分越高越差），套上去只会加噪音。叠加照第一轮的三样数。
"""
import os, io, sys, json, glob
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out")
指数 = ["SPY", "QQQ", "DIA", "IWM"]; 行业 = ["XLK", "XLF", "XLE", "XLV", "XLI", "XLY", "XLP", "XLU", "XLB", "XLRE", "XLC", "SMH", "KRE", "SOXX"]
FEE, BOR = 0.0015, 0.01


def 日线(sym):
    if sym == "SOXX":
        f = glob.glob(os.path.join(ROOT, "market_ext_1105/SOXX_1123/日线/*"))[0]
        d = pd.read_parquet(f) if f.endswith("parquet") else pd.read_csv(f)
    else:
        d = pd.read_csv(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/日线", sym + "_日线.csv"))
    d["date"] = pd.to_datetime(d["date"]); d = d.set_index("date").sort_index()
    x = pd.DataFrame({"o": d.open_adj, "h": d.high_adj, "l": d.low_adj, "c": d.close_adj, "v": d.volume_adj}).dropna()
    top, bot = x[["o", "c"]].max(axis=1), x[["o", "c"]].min(axis=1)
    x.loc[x.h > top * 1.2, "h"] = top; x.loc[x.l < bot * 0.8, "l"] = bot
    if sym == "XLF":
        t = pd.Timestamp("2016-09-19"); i = x.index.get_loc(t); k = x.c.iloc[i] / x.c.iloc[i - 1]
        x.loc[x.index < t, ["o", "h", "l", "c"]] *= k
    return x


_H = {}
def 小时线(sym):
    if sym in _H: return _H[sym]
    if sym == "SOXX":
        fs = sorted(glob.glob(os.path.join(ROOT, "market_ext_1105/SOXX_1123/小时线/*.parquet")))
        h = pd.concat([pd.read_parquet(f) for f in fs])
    else:
        fs = sorted(glob.glob(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/小时线_2004_2014/*.parquet")) + glob.glob(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/小时线_2015起/*.parquet")))
        h = pd.concat([pd.read_parquet(f, filters=[("symbol", "==", sym)]) for f in fs])
    h = h[h["session"] == "regular"].copy()
    t = pd.to_datetime(h["time_utc"], utc=True).dt.tz_convert("America/New_York")
    h = pd.DataFrame({"t": t.values, "d": t.dt.tz_localize(None).dt.normalize().values, "o": h.open_adj.values, "h": h.high_adj.values, "l": h.low_adj.values, "c": h.close_adj.values}).dropna().sort_values("t").reset_index(drop=True)
    # 同一天的小时线和日线对齐（两边折算口径一样都是只折拆股；偶有差异按当天日线收盘比例对齐）
    _H[sym] = h; return h


def atr(h, l, c, n=14):
    pc = np.r_[c[0], c[:-1]]; tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    return pd.Series(tr).ewm(alpha=1 / n, adjust=False, min_periods=n).mean().to_numpy()


def 日线setups(x, zone, k=5.0, W=60):
    """照第一轮认法 a 找 ① 顶 → ② 跌破 → 反弹碰进核心区（日线）。返回每次「碰进」的信息，进场交给小时线判。"""
    o, h, l, c = (x[a].to_numpy() for a in "ohlc"); n = len(c); A_ = atr(h, l, c)
    pk = pd.Series(c).shift(1).rolling(252).max().to_numpy(); hh = pd.Series(h).rolling(252).max().to_numpy()
    out = []; i = 260; armed = True
    while i < n - 2:
        # ①② 派发确认
        state = 0; b = -1
        while i < n - 2:
            if not armed:
                if c[i] > pk[i] * 0.92: armed = True
                i += 1; continue
            if state == 0:
                peak = pk[i]
                if c[i] <= peak * 0.92: state = 1; L1 = l[i]; bounced = False
            else:
                if c[i] > peak: state = 0
                elif not bounced:
                    L1 = min(L1, l[i])
                    if c[i] >= L1 * 1.04: bounced = True
                elif c[i] < L1: b = i; H0 = hh[i]; neck = L1; break
            i += 1
        if b < 0: break
        armed = False
        A = l[b]; li = b; Bh = h[b]; t = b + 1; got = None
        while t < n - 1 and t - li <= W:
            if l[t] < A: A = l[t]; li = t; Bh = h[t]; t += 1; continue
            Bh = max(Bh, h[t]); leg = H0 - A
            zlo, zhi = zone(A, leg, A_[t])
            if c[t] > zhi: break
            if h[t] >= zlo and leg >= k * A_[t]:
                got = dict(碰到i=t, A低=A, A低i=li, H0=H0, 段=leg, 区下=zlo, 区上=zhi, 日ATR=A_[t], 颈线=neck, 跌破i=b); break
            t += 1
        if got: out.append(got)
        i = (got["碰到i"] + 1) if got else t + 1
    return out


def 模拟(hb, e, E, stop, T1, T2, zhi_daily_close, d_end):
    """逐根 1 小时线：hb 是该票小时线；e = 进场那根的下标；日线收盘站上区上沿 = 该交易日最后一根收盘 > 区上沿。"""
    R = stop - E; g = fF = bF = 0.0; w = 1.0; s = stop; half = False; r1 = r2 = 0; st_orig = False
    o, h, l, c, d = hb["o"].to_numpy(), hb["h"].to_numpy(), hb["l"].to_numpy(), hb["c"].to_numpy(), hb["d"].to_numpy()
    last_of_day = np.r_[d[1:] != d[:-1], True]
    d0 = d[e]; nd = 0; xi = e; why = "到期"
    for j in range(e + 1, len(c)):
        if d[j] != d[j - 1]: nd += 1
        if nd > 120 or d[j] > d_end: break
        dd = (d[j] - d0) / np.timedelta64(1, "D") / 365.25 * 252
        # 「走没走出来」：碰原止损或日线站上区上沿之前碰到目标
        if not st_orig:
            if h[j] >= stop: st_orig = True
            else:
                if l[j] <= T1: r1 = 1
                if l[j] <= T2: r2 = 1
                if last_of_day[j] and c[j] > zhi_daily_close: st_orig = True
        px = None
        if o[j] >= s: px = o[j]; why = "止损" if not half else "保本"
        elif h[j] >= s: px = s; why = "止损" if not half else "保本"
        elif not half and l[j] <= T1:
            p1 = min(o[j], T1); g += 0.5 * (E - p1) / R; fF += 0.5 * (E + p1) / R; bF += 0.5 * dd * E / R / 252; w = 0.5; half = True; s = E
            if l[j] <= T2: px = min(o[j], T2); why = "1.618倍"
        elif half and l[j] <= T2: px = min(o[j], T2); why = "1.618倍"
        if px is None and last_of_day[j] and c[j] > zhi_daily_close: px = c[j]; why = "站上核心区作废"
        if px is not None:
            g += w * (E - px) / R; fF += w * (E + px) / R; bF += w * dd * E / R / 252; w = 0; xi = j; break
        xi = j
    if w > 0:
        dd = (d[xi] - d0) / np.timedelta64(1, "D") / 365.25 * 252
        g += w * (E - c[xi]) / R; fF += w * (E + c[xi]) / R; bF += w * dd * E / R / 252
    return dict(毛R=g, 净R=g - FEE * fF - BOR * bF, 到1倍=r1, 到1618=r2, 怎么出=why, 出场=str(pd.Timestamp(d[xi]).date()))


def 跑(sym, zone, zname, K=7, d_end="2025-12-31", 试几次=3):
    x = 日线(sym); hb = 小时线(sym); 日 = x.index
    hA = atr(hb.h.to_numpy(), hb.l.to_numpy(), hb.c.to_numpy())
    c日 = x.c; 收200 = c日.rolling(50).mean()
    rows = []
    for s in 日线setups(x, zone):
        dt = 日[s["碰到i"]]
        if dt < pd.Timestamp("2005-01-03") or dt > pd.Timestamp(d_end): continue
        # 小时线与日线对齐：按碰到那天两边收盘的比例
        hd = hb[hb.d == dt]
        if len(hd) == 0: continue
        k_ = float(c日.loc[dt] / hd.c.iloc[-1])
        if abs(k_ - 1) > 0.02: continue          # 两边口径差太多的跳过（记数）
        j0 = hd.index[0]
        W_end = 日[min(len(日) - 1, s["A低i"] + 60)]
        hbk = hb.assign(o=hb.o * k_, h=hb.h * k_, l=hb.l * k_, c=hb.c * k_)
        for sn in ("宽", "窄"):
            j = j0; hi = -1e18; 第几次 = 0; start = j0
            while j < len(hb) and 第几次 < 试几次:
                if hb.d.iat[j] > W_end: break
                hi = max(hi, hb.h.iat[j])
                if (j + 1 == len(hb) or hb.d.iat[j + 1] != hb.d.iat[j]) and hb.c.iat[j] * k_ > s["区上"]: break   # 日线收盘站上区上沿：作废
                if hb.l.iat[j] * k_ < s["A低"]: break                                                            # 跌回 A 低点以下：这次反弹结束
                lo = hb.l.iloc[max(start, j - K):j].min() if j > start else np.inf
                if j - start >= 2 and hb.c.iat[j] < lo and hb.c.iat[j] * k_ <= s["区上"]:
                    E = hb.c.iat[j] * k_; Bh = max(x.h.iloc[s["A低i"]:日.get_loc(hb.d.iat[j]) + 1].max(), hi * k_)
                    T1 = Bh - s["段"]; T2 = Bh - 1.618 * s["段"]
                    stop = Bh + 0.25 * s["日ATR"] if sn == "宽" else hi * k_ + 0.2 * hA[j] * k_
                    if stop <= E or (stop - E) / E > 0.2: j += 1; continue
                    第几次 += 1
                    r = 模拟(hbk, j, E, stop, T1, T2, s["区上"], pd.Timestamp(d_end) + pd.Timedelta(days=200))
                    rows.append(dict(票=sym, 核心=zname, K=K, 试几次=试几次, 第几次=第几次, 止损=sn, 进场时刻=str(hb.t.iat[j]), 日=str(hb.d.iat[j])[:10],
                                     E=round(E, 2), 止损价=round(stop, 2), 止损距pct=round((stop - E) / E * 100, 2), T1=round(T1, 2), 碰到日=str(dt.date()), **r))
                    if r["怎么出"] != "止损": break           # 只有被止损才再试
                    # 从止损那根之后接着找；高点从头算
                    jx = hb.index[(hb.t > hb.t.iat[j]) & (hb.d <= pd.Timestamp(r["出场"]))]
                    j = (int(jx[-1]) + 1) if len(jx) else j + 1; start = j; hi = -1e18
                    while j < len(hb) and hb.d.iat[j] <= pd.Timestamp(r["出场"]): hi = max(hi, hb.h.iat[j]); j += 1
                    start = j
                    continue
                j += 1
    return rows


ZONES = {
    "0.5": lambda A, L, a: (A + 0.5 * L - 0.5 * a, A + 0.5 * L + 0.5 * a),
    "0.618": lambda A, L, a: (A + 0.618 * L - 0.5 * a, A + 0.618 * L + 0.5 * a),
    "0.786": lambda A, L, a: (A + 0.786 * L - 0.5 * a, A + 0.786 * L + 0.5 * a),
    "0.618~0.786整片": lambda A, L, a: (A + 0.618 * L - 0.5 * a, A + 0.786 * L + 0.5 * a),
}

if __name__ == "__main__":
    allr = []
    for sym in 指数 + 行业:
        for zn, z in ZONES.items():
            for K in ((4, 7, 14) if zn in ("0.618", "0.618~0.786整片") else (7,)):
                allr += 跑(sym, z, zn, K)
            for 试 in (1, 2): allr += 跑(sym, z, zn, 7, 试几次=试)
        print(sym, len(allr), flush=True)
    T = pd.DataFrame(allr); T.to_csv(os.path.join(OUT, "第二轮_小周期_逐笔.csv"), index=False)
    # 核对：2026 年 SOXX / QQQ / SMH 认没认出 Lin 这次
    chk = []
    for sym in ("SOXX", "SMH", "QQQ"):
        for zn in ("0.618", "0.786", "0.618~0.786整片"):
            chk += [r for r in 跑(sym, ZONES[zn], zn, 7, d_end="2026-11-20") if r["日"] >= "2026-01-01"]
    pd.DataFrame(chk).to_csv(os.path.join(OUT, "第二轮_2026核对.csv"), index=False)
    print("DONE", len(T))
