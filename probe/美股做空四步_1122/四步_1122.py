# -*- coding: utf-8 -*-
"""《396》第一件 · 美股做空四步（Lin《394》第二节）扫两个十年 · 引擎外，engine/ 一个字节没动。
大白话：① 顶部派发已形成 → ② 收盘跌破派发区间低点、走出第一段（A）→ ③ 反弹（B）碰到「核心位置」没站上去、然后转弱 → 空，
       ④ 赌下一段（C）：止损在反弹最高点上方，第一目标 C = A，第二目标 C = 1.618A；反弹收盘站上核心位置 = 假设作废、当天走。
       状态机（《394》第 7 条）：C 段走到第一目标（「三浪走出来了」）之后，再看四浪反弹过不过它自己的核心位置，没过 → 空五浪。

══ 拍板没写死、我补的定义（报告里逐条列；带数字的都跑了相邻两点，见 PARAMS 和 邻点）══
 D1 ①认法 a「派发确认」照 probe/派发顶_1121/两段认法_1121.py 的 确认段()：收盘比过去 252 天最高收盘低 8% → 从低点弹 4% 以上、
    没收回前高 → 收盘再跌破前低（这一下同时就是 ② 的跌破，颈线 = 前低）。8% / 4% 是那份认法原有的数，这里没动。
    ★ 我加：一次形态用完以后，要等收盘回到「离一年高点 8% 以内」才重新开始认下一个顶（不然大跌途中会反复认出「顶」）。
 D2 ①认法 b「假突破」：收盘创 252 天新高 → F 天内（基准 5，邻点 3 / 8）收盘回到前高之下 = 假突破；
    派发区间低点 = 新高那天往前 60 天的最低价；之后 BW 天内（基准 60，邻点 40 / 90）收盘跌破它 = ② 跌破；中途收盘再创新高 = 真突破，作废。
 D3 第一段 A = 顶部最高价 H0（认法 a：跌破那天往前 252 天的最高价；认法 b：新高那天到跌破那天的最高价）到跌破后的最低价。
    「够大才算一段」：A ≥ k × ATR14（基准 k=5，邻点 3 / 7）。之后又创新低就把 A 的低点往下挪、反弹重新算。
 D4 核心位置 = A 低点 + r × A（r 基准 0.618，邻点 0.5 / 0.786）上下 w × ATR14（w 基准 0.5，邻点 0.25 / 0.75；《394》表里原写 ±0.5 ATR）。
    「碰到」= 当天最高价 ≥ 区间下沿；「站上」= 收盘 > 区间上沿；「转弱」= 碰到以后某天收盘跌破前一天最低价、且收盘仍在区间上沿之下 → 当天收盘空。
    A 低点之后 W 天（基准 60，邻点 40 / 80）还没进场就放弃。
 D5 叠加的三样，碰到那天判，落在核心位置区间里才算一样：
    · 前一个跌破位 / 颈线 = 派发区间低点（认法 a 的前低、认法 b 的 60 天低点；四浪那层用 A 段低点）；
    · 成交密集区 = 跌破前 120 天、按收盘价分 40 格累计成交量，量最大那一格的中点；
    · 向下的 50 日线 = 50 日均线比 5 天前低，且落在区间里。
 D6 止损 = 反弹最高价 + sb × ATR（sb 基准 0.25，同《389》；邻点 0.1 / 0.5）；止损距离 > 20% 的不做（同《389》）。
 D7 出场（逐笔 R 用）：一半在第一目标走、剩下一半止损挪到进场价、在第二目标走；反弹收盘站上核心位置区间上沿 = 全走；最多拿 120 天。
    跳空越过止损 / 目标按开盘价；同一天既碰止损又碰目标，按先碰止损算（保守）。
 D8 「下一段走没走出来」= 在碰到原止损、或收盘站上核心位置之前，120 天内最低价碰到目标（1 倍 / 1.618 倍）。
 D9 四浪那层：三浪的低点 = 进场到碰第一目标之间的最低价（之后再创新低就往下挪）；三浪长度 = 二浪最高点 − 三浪低点；
    核心位置、碰到、转弱、止损同上；五浪目标 = 四浪最高点 − 1 倍 / 1.618 倍 A 段长度（艾略特「五浪≈一浪」）。
 D10 成本：单边 0.15%（按价格）+ 借券年化 1%（个股另报 5%）；不算分红（做空要倒贴分红，偏乐观）。
 D11 随机对照：同一只票、同一个月、随便一天收盘空，止损距离和两个目标按同样的 R 倍数、同样的一半一半出场、120 天，不看核心位置；每笔抽 10 次取平均。
"""
import os, io, sys, json, time
import numpy as np, pandas as pd
from numba import njit
HERE = os.path.dirname(os.path.abspath(__file__)); CACHE = os.path.join(HERE, "cache"); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
D0 = np.datetime64("1970-01-01")
DLO = int((np.datetime64("2005-01-03") - D0).astype(int)); DHI = int((np.datetime64("2025-12-31") - D0).astype(int))
BASE = dict(r=0.618, k=5.0, w=0.5, F=5, W=60, sb=0.25, BW=60)
邻点 = {"r": (0.5, 0.786), "k": (3.0, 7.0), "w": (0.25, 0.75), "F": (3, 8), "W": (40, 80), "sb": (0.1, 0.5), "BW": (40, 90)}
MAXHOLD = 120; STOPCAP = 0.20
EV_COLS = ["层", "进场i", "E", "止损", "R", "T1", "T2", "叠几样", "叠颈线", "叠密集区", "叠50线", "到1倍", "到1618", "毛R", "费F", "借F",
           "出场i", "怎么出", "头5天最多赚R", "头5天最多亏R", "头5天被止损", "第5天收盘R", "A段pct", "跌破i", "碰到i", "拿几天", "H0", "A低", "B高", "区上沿", "反弹深度"]
PS_COLS = ["层", "i", "f20", "f60", "120天内收回顶部", "叠几样_碰到时", "碰到过", "在池"]


@njit(cache=True)
def _sim(o, h, l, c, e, E, stop, T1, T2, zhi, n):
    R = stop - E; end = min(e + 120, n - 1)
    r1 = 0; r2 = 0; t1i = -1
    for j in range(e + 1, end + 1):
        if h[j] >= stop: break
        if l[j] <= T1 and r1 == 0: r1 = 1; t1i = j
        if l[j] <= T2: r2 = 1; break
        if c[j] > zhi: break
    gross = 0.0; feeF = 0.0; borF = 0.0; w = 1.0; s = stop; half = False; reason = 0; xi = end; held = 0
    for j in range(e + 1, end + 1):
        px = -1.0
        if not half:
            if o[j] >= s: px = o[j]; reason = 1
            elif h[j] >= s: px = s; reason = 1
            elif l[j] <= T1:
                p1 = o[j] if o[j] < T1 else T1
                gross += 0.5 * (E - p1) / R; feeF += 0.5 * (E + p1) / R; borF += 0.5 * (j - e) * E / R / 252.0
                w = 0.5; half = True; s = E
                if l[j] <= T2: px = o[j] if o[j] < T2 else T2; reason = 3
                elif c[j] > zhi: px = c[j]; reason = 2
            elif c[j] > zhi: px = c[j]; reason = 2
        else:
            if o[j] >= s: px = o[j]; reason = 4
            elif h[j] >= s: px = s; reason = 4
            elif l[j] <= T2: px = o[j] if o[j] < T2 else T2; reason = 3
            elif c[j] > zhi: px = c[j]; reason = 2
        if px > 0:
            gross += w * (E - px) / R; feeF += w * (E + px) / R; borF += w * (j - e) * E / R / 252.0; xi = j; held = j - e; w = 0.0; break
    if w > 0:
        px = c[end]; reason = 6 if (end == n - 1 and e + 120 > n - 1) else 5
        gross += w * (E - px) / R; feeF += w * (E + px) / R; borF += w * (end - e) * E / R / 252.0; xi = end; held = end - e
    e5 = min(e + 5, n - 1); mfe = 0.0; mae = 0.0; st5 = 0
    for j in range(e + 1, e5 + 1):
        mfe = max(mfe, (E - l[j]) / R); mae = max(mae, (h[j] - E) / R)
        if h[j] >= stop: st5 = 1
    c5 = (E - c[e5]) / R
    return gross, feeF, borF, xi, reason, r1, r2, t1i, mfe, mae, st5, c5, held


@njit(cache=True)
def _poc(h, l, c, v, a, b):
    lo = 1e18; hi = -1e18
    for j in range(a, b + 1):
        lo = min(lo, l[j]); hi = max(hi, h[j])
    if hi <= lo: return c[b]
    bins = np.zeros(40)
    for j in range(a, b + 1):
        k = int((c[j] - lo) / (hi - lo) * 40)
        if k >= 40: k = 39
        if k < 0: k = 0
        bins[k] += v[j]
    k = np.argmax(bins)
    return lo + (k + 0.5) * (hi - lo) / 40


@njit(cache=True)
def _wait(o, h, l, c, v, ok, d, atr, sma50, start, top, low0, lowi0, neck, r, k, w, W, dlo, dhi, n, poc):
    """等反弹：返回 (状态, 进场 i, 反弹最高, 段长, 区上沿, 叠颈线, 叠密集区, 叠50线, 碰到 i, 段低, 结束 i, 碰到过)
       状态 1=进场 2=站上核心位置 3=超时/段太小 4=进场那天不在池里或不在时段里"""
    A = low0; li = lowi0; Bh = h[lowi0]; touched = False; zlo_f = 0.0; zhi_f = 0.0; cn = 0; cp = 0; cm = 0; ti = -1
    t = start
    while t < n - 1:
        if t - li > W: return 3, -1, Bh, top - A, zhi_f, cn, cp, cm, ti, A, t, touched
        if l[t] < A:
            A = l[t]; li = t; Bh = h[t]; touched = False; t += 1; continue
        if h[t] > Bh: Bh = h[t]
        leg = top - A; fib = A + r * leg
        if touched: zlo = zlo_f; zhi = zhi_f
        else: zlo = fib - w * atr[t]; zhi = fib + w * atr[t]
        if c[t] > zhi:
            if leg >= k * atr[t] or touched: return 2, -1, Bh, leg, zhi, cn, cp, cm, ti, A, t, touched
            return 3, -1, Bh, leg, zhi, cn, cp, cm, ti, A, t, touched
        if (not touched) and h[t] >= zlo and leg >= k * atr[t]:
            touched = True; zlo_f = zlo; zhi_f = zhi; ti = t
            cn = 1 if (neck >= zlo and neck <= zhi) else 0
            cp = 1 if (poc >= zlo and poc <= zhi) else 0
            cm = 1 if (t >= 5 and sma50[t] < sma50[t - 5] and sma50[t] >= zlo and sma50[t] <= zhi) else 0
        if touched and c[t] < l[t - 1] and c[t] <= zhi_f:
            if ok[t] and d[t] >= dlo and d[t] <= dhi: return 1, t, Bh, leg, zhi_f, cn, cp, cm, ti, A, t, touched
            return 4, -1, Bh, leg, zhi_f, cn, cp, cm, ti, A, t, touched
        t += 1
    return 3, -1, Bh, top - A, zhi_f, cn, cp, cm, ti, A, t, touched


@njit(cache=True)
def _put(ev, ne, a0, a1, a2, a3, a4, a5, a6, a7, a8, a9, a10, a11, a12, a13, a14, a15, a16, a17, a18, a19, a20, a21, a22, a23, a24, a25, a26, a27, a28, a29, a30):
    ev[ne, 0] = a0
    ev[ne, 1] = a1
    ev[ne, 2] = a2
    ev[ne, 3] = a3
    ev[ne, 4] = a4
    ev[ne, 5] = a5
    ev[ne, 6] = a6
    ev[ne, 7] = a7
    ev[ne, 8] = a8
    ev[ne, 9] = a9
    ev[ne, 10] = a10
    ev[ne, 11] = a11
    ev[ne, 12] = a12
    ev[ne, 13] = a13
    ev[ne, 14] = a14
    ev[ne, 15] = a15
    ev[ne, 16] = a16
    ev[ne, 17] = a17
    ev[ne, 18] = a18
    ev[ne, 19] = a19
    ev[ne, 20] = a20
    ev[ne, 21] = a21
    ev[ne, 22] = a22
    ev[ne, 23] = a23
    ev[ne, 24] = a24
    ev[ne, 25] = a25
    ev[ne, 26] = a26
    ev[ne, 27] = a27
    ev[ne, 28] = a28
    ev[ne, 29] = a29
    ev[ne, 30] = a30


@njit(cache=True)
def scan(d, o, h, l, c, v, ok, variant, r, k, w, F, W, sb, BW, dlo, dhi, ev, ps):
    n = len(c)
    atr = np.full(n, np.nan); sma50 = np.full(n, np.nan); pk = np.full(n, np.nan); hh = np.full(n, np.nan); ll60 = np.full(n, np.nan)
    s = 0.0
    for i in range(1, n):
        tr = max(h[i] - l[i], max(abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
        if i < 14: s += tr
        elif i == 14: s += tr; atr[i] = s / 14.0
        else: atr[i] = atr[i - 1] + (tr - atr[i - 1]) / 14.0
    acc = 0.0
    for i in range(n):
        acc += c[i]
        if i >= 50: acc -= c[i - 50]
        if i >= 49: sma50[i] = acc / 50.0
    for i in range(252, n):
        m = -1e18; mh = -1e18
        for j in range(i - 252, i): m = max(m, c[j])
        for j in range(i - 251, i + 1): mh = max(mh, h[j])
        pk[i] = m; hh[i] = mh
    for i in range(60, n):
        m = 1e18
        for j in range(i - 60, i + 1): m = min(m, l[j])
        ll60[i] = m
    ne = 0; np_ = 0; i = 260; armed = True
    while i < n - 2 and ne < ev.shape[0] - 2 and np_ < ps.shape[0] - 2:
        b = -1; H0 = 0.0; neck = 0.0
        if variant == 0:
            state = 0; peak = 0.0; L1 = 0.0; bounced = False
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
                        if l[i] < L1: L1 = l[i]
                        if c[i] >= L1 * 1.04: bounced = True
                    elif c[i] < L1:
                        b = i; H0 = hh[i]; neck = L1; break
                i += 1
        else:
            while i < n - 2 and b < 0:
                if not (c[i] > pk[i]): i += 1; continue
                j = i; lvl = pk[i]; f = -1
                for t in range(j + 1, min(j + F, n - 3) + 1):
                    if c[t] < lvl: f = t; break
                if f < 0: i += 1; continue
                rl = ll60[j]; topH = -1e18
                for t in range(j, f + 1): topH = max(topH, h[t])
                endt = f
                for t in range(f + 1, min(f + BW, n - 3) + 1):
                    endt = t
                    if c[t] > topH: break
                    if h[t] > topH: topH = h[t]
                    if c[t] < rl: b = t; H0 = topH; neck = rl; break
                if b < 0: i = endt + 1
        if b < 0: break
        armed = False
        poc = _poc(h, l, c, v, max(0, b - 120), b)
        st, e, Bh, leg, zhi, cn, cp, cm, ti, A, tend, touched = _wait(o, h, l, c, v, ok, d, atr, sma50, b + 1, H0, l[b], b, neck, r, k, w, W, dlo, dhi, n, poc)
        if st == 2:
            ps[np_, 0] = 1; ps[np_, 1] = tend
            ps[np_, 2] = c[tend + 20] / c[tend] - 1 if tend + 20 < n else np.nan
            ps[np_, 3] = c[tend + 60] / c[tend] - 1 if tend + 60 < n else np.nan
            back = 0
            for j in range(tend + 1, min(tend + 120, n - 1) + 1):
                if c[j] > H0: back = 1; break
            ps[np_, 4] = back; ps[np_, 5] = cn + cp + cm; ps[np_, 6] = 1 if touched else 0; ps[np_, 7] = 1 if ok[tend] else 0; np_ += 1
        if st != 1:
            i = tend + 1; continue
        E = c[e]; stop = Bh + sb * atr[e]; R = stop - E
        if R <= 0 or R / E > 0.20:
            i = e + 1; continue
        T1 = Bh - leg; T2 = Bh - 1.618 * leg
        g, fF, bF, xi, why, r1, r2, t1i, mfe, mae, st5, c5, held = _sim(o, h, l, c, e, E, stop, T1, T2, zhi, n)
        _put(ev, ne, 1.0, e, E, stop, R, T1, T2, cn + cp + cm, cn, cp, cm, r1, r2, g, fF, bF, xi, why, mfe, mae, st5, c5, leg / H0, b, ti, held, H0, A, Bh, zhi, (Bh - A) / leg)
        ne += 1; last = xi
        if r1 == 1:
            lowi = e; C = l[e]
            for j in range(e, t1i + 1):
                if l[j] < C: C = l[j]; lowi = j
            poc2 = _poc(h, l, c, v, max(0, lowi - 120), lowi)
            st2, e2, Bh2, leg3, zhi2, cn2, cp2, cm2, ti2, C2, tend2, touched2 = _wait(o, h, l, c, v, ok, d, atr, sma50, t1i + 1, Bh, C, lowi, A, r, k, w, W, dlo, dhi, n, poc2)
            if st2 == 2:
                ps[np_, 0] = 2; ps[np_, 1] = tend2
                ps[np_, 2] = c[tend2 + 20] / c[tend2] - 1 if tend2 + 20 < n else np.nan
                ps[np_, 3] = c[tend2 + 60] / c[tend2] - 1 if tend2 + 60 < n else np.nan
                back = 0
                for j in range(tend2 + 1, min(tend2 + 120, n - 1) + 1):
                    if c[j] > Bh: back = 1; break
                ps[np_, 4] = back; ps[np_, 5] = cn2 + cp2 + cm2; ps[np_, 6] = 1 if touched2 else 0; ps[np_, 7] = 1 if ok[tend2] else 0; np_ += 1
            last = max(last, tend2)
            if st2 == 1:
                E2 = c[e2]; stop2 = Bh2 + sb * atr[e2]; R2 = stop2 - E2
                if R2 > 0 and R2 / E2 <= 0.20:
                    U1 = Bh2 - leg; U2 = Bh2 - 1.618 * leg
                    g, fF, bF, xi2, why, q1, q2, _t, mfe, mae, st5, c5, held = _sim(o, h, l, c, e2, E2, stop2, U1, U2, zhi2, n)
                    _put(ev, ne, 2.0, e2, E2, stop2, R2, U1, U2, cn2 + cp2 + cm2, cn2, cp2, cm2, q1, q2, g, fF, bF, xi2, why, mfe, mae, st5, c5, leg3 / Bh, lowi, ti2, held, Bh, C2, Bh2, zhi2, (Bh2 - C2) / leg3)
                    ne += 1; last = max(last, xi2)
        i = last + 1
    return ne, np_


@njit(cache=True)
def 随机(o, h, l, c, cands, Rp, m1, m2, n, seed):
    np.random.seed(seed); gs = 0.0; fs = 0.0; bs = 0.0; r1s = 0.0; m = 0
    for _ in range(10):
        e = cands[np.random.randint(0, len(cands))]
        E = c[e]; stop = E * (1 + Rp); R = stop - E
        g, fF, bF, xi, why, r1, r2, t1i, mfe, mae, st5, c5, held = _sim(o, h, l, c, e, E, stop, E - m1 * R, E - m2 * R, 1e18, n)
        gs += g; fs += fF; bs += bF; r1s += r1; m += 1
    return gs / m, fs / m, bs / m, r1s / m


def 读(name):
    z = np.load(os.path.join(CACHE, name + ".npz"))
    return {k: z[k] for k in z.files}


def 跑一类(Z, variant, p, 随机对照=True):
    off = Z["off"]; EV = []; PS = []
    ev = np.zeros((600, 31)); ps = np.zeros((600, 8))
    for si, s in enumerate(Z["syms"]):
        a, b = off[si], off[si + 1]
        d, o, h, l, c, v, ok = (Z[k][a:b] for k in ("d", "o", "h", "l", "c", "v", "ok"))
        if b - a < 300: continue
        ne, nps = scan(d, o, h, l, c, v, ok, variant, p["r"], p["k"], p["w"], int(p["F"]), int(p["W"]), p["sb"], int(p["BW"]), DLO, DHI, ev, ps)
        if ne:
            t = pd.DataFrame(ev[:ne].copy(), columns=EV_COLS); t["票"] = s; t["退市股"] = bool(Z["delisted"][si])
            t["日"] = (d[t["进场i"].astype(int).values].astype("timedelta64[D]") + D0)
            t["出场日"] = (d[t["出场i"].astype(int).values].astype("timedelta64[D]") + D0)
            if 随机对照:
                ym = (d.astype("timedelta64[D]") + D0).astype("datetime64[M]")
                rr = []
                for q in range(ne):
                    e = int(t["进场i"].iat[q]); cand = np.where((ym == ym[e]) & ok & (np.arange(len(c)) < len(c) - 2))[0]
                    if len(cand) == 0: cand = np.array([e])
                    E = t["E"].iat[q]; R = t["R"].iat[q]
                    rr.append(随机(o, h, l, c, cand.astype(np.int64), R / E, (E - t["T1"].iat[q]) / R, (E - t["T2"].iat[q]) / R, len(c), si * 1000 + q))
                rr = np.array(rr); t["随机毛R"], t["随机费F"], t["随机借F"], t["随机到1倍"] = rr.T
            EV.append(t)
        if nps:
            u = pd.DataFrame(ps[:nps].copy(), columns=PS_COLS); u["票"] = s
            u["日"] = (d[u["i"].astype(int).values].astype("timedelta64[D]") + D0); PS.append(u)
    EVd = pd.concat(EV, ignore_index=True) if EV else pd.DataFrame(columns=EV_COLS + ["票", "日"])
    PSd = pd.concat(PS, ignore_index=True) if PS else pd.DataFrame(columns=PS_COLS + ["票", "日"])
    PSd = PSd[(PSd["日"] >= "2005-01-03") & (PSd["日"] <= "2025-12-31")] if len(PSd) else PSd
    return EVd, PSd


def 配置():
    yield "基准", dict(BASE)
    for kk, vs in 邻点.items():
        for vv in vs:
            p = dict(BASE); p[kk] = vv; yield f"{kk}={vv}", p


if __name__ == "__main__":
    类 = sys.argv[1:] or ["指数", "行业", "个股_研究库", "个股_退市股"]
    for name in 类:
        Z = 读(name)
        for variant, vn in ((0, "认法a派发确认"), (1, "认法b假突破")):
            for cn, p in 配置():
                if variant == 0 and cn.startswith(("F=", "BW=")): continue
                fn = os.path.join(OUT, f"{name}__{vn}__{cn}.pkl")
                if os.path.exists(fn): continue                     # 断点续跑：做完的不重做
                t0 = time.time(); EVd, PSd = 跑一类(Z, variant, p, 随机对照=(cn == "基准"))
                pd.to_pickle({"ev": EVd, "ps": PSd, "p": p}, fn + ".tmp"); os.replace(fn + ".tmp", fn)
                print(name, vn, cn, "笔", len(EVd), "过核心", len(PSd), f"{time.time() - t0:.0f}s", flush=True)
    print("DONE", flush=True)
