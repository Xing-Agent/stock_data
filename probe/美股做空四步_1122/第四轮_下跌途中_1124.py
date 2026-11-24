# -*- coding: utf-8 -*-
"""《396》第一件 · 第四轮：下跌途中每一次大反弹都看（Lin 11-24 晚：「从顶部下来也是一浪、二浪、三浪、四浪慢慢下的，中间有很多很多大的反弹」）。
大白话：前三轮认出一次顶、用完一次以后，要等价格回到离高点 8% 以内才重新认 —— 2008 年这种一路往下的熊市，后面一浪接一浪的反弹全没看。
这一轮改成：认出顶（同第一轮认法 a）以后进入「下跌期」，直到收盘创一年新高才结束；下跌期里每一段下跌都是一个新的第一段，
反弹到这一段的核心位置不过、转弱 → 空，目标 = 下一段和这一段一样长（1 倍 / 1.618 倍）。

══ 我补的定义（新加的；核心位置、碰到、转弱、止损、出场、成本照第一轮 D4~D10）══
 E1 下跌期：从认法 a 的跌破那天开始，到收盘高过「过去 252 天最高收盘」那天结束。结束后照第一轮重新认下一个顶。
 E2 一段下跌的起点（段顶）：下跌期第一段 = 顶部最高价 H0；之后每当一次反弹碰到过核心位置、随后又跌破这一段的低点，
    下一段的段顶 = 那次反弹的最高价（就是艾略特的二浪顶、四浪顶）。反弹没碰到核心位置、但反弹幅度 ≥ 这一段的 0.382（邻点 0.236 / 0.5）又创新低的，
    也算一浪，下一段同样从这次反弹最高价算起；更小的反弹不算，段顶不变（算同一段还在往下走）。
    （第一版只认「碰过核心位置的反弹」，结果 SPY 2008 年一笔没空：那年的反弹回撤大多 0.4~0.6，够不着从顶部量的整段 0.618。）
    反弹收盘站上核心区上沿（「过了」）= 这一段结束；之后的高点一路往上挪，直到又开始往下，从那个高点算新的一段。
 E3 一段要 ≥ 5 ATR 才算（同第一轮，邻点 3 / 7）。同一只票同一时间只拿一笔；拿着的时候结构照样往下数，但不开新仓。
 E4 第几段：下跌期里第 1 次空 = 「空三浪」（二浪反弹不过），第 2 次 = 「空五浪」……按次数分开报。
"""
import os, sys, time
import numpy as np, pandas as pd
from numba import njit
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import importlib
M = importlib.import_module("四步_1122")
OUT = M.OUT


@njit(cache=True)
def scan_bear(d, o, h, l, c, v, ok, r, k, w, sb, q, dlo, dhi, ev):
    n = len(c)
    atr = np.full(n, np.nan); sma50 = np.full(n, np.nan); pk = np.full(n, np.nan); hh = np.full(n, np.nan)
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
    ne = 0; i = 260; armed = True; nbear = 0
    while i < n - 2 and ne < ev.shape[0] - 2:
        # ①② 认法 a 找顶
        state = 0; peak = 0.0; L1 = 0.0; bounced = False; b = -1; H0 = 0.0; neck = 0.0
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
        if b < 0: break
        armed = False; nbear += 1
        # 下跌期
        SH = H0; L = l[b]; Li = b; Bh = h[b]; mode = 0      # mode 0 = 这一段在往下 / 等反弹；1 = 反弹过了核心位置，高点往上挪
        touched = False; zlo_f = 0.0; zhi_f = 0.0; cn = 0; cp = 0; cm = 0; ti = -1; nk = neck; used = False
        intrade_until = -1; legno = 0
        t = b + 1
        while t < n - 1:
            if c[t] > pk[t]: break                           # 收盘创一年新高：下跌期结束
            if mode == 1:
                if h[t] > SH: SH = h[t]
                if c[t] < l[t - 1] and h[t] < SH:             # 开始往下：新一段，段顶 = 这一波最高价
                    mode = 0; L = l[t]; Li = t; Bh = h[t]; touched = False; used = False
                t += 1; continue
            if h[t] > SH and not touched:                     # 还没碰核心位置就创了段顶之上的新高：段顶上挪
                SH = h[t]; L = l[t]; Li = t; Bh = h[t]; t += 1; continue
            if l[t] < L:
                if touched or (Bh - L) >= q * (SH - L): SH = Bh; nk = L   # 够大的反弹（碰过核心位置，或回撤 ≥ q）失败 → 下一段的段顶 = 这次反弹最高
                L = l[t]; Li = t; Bh = h[t]; touched = False; used = False; t += 1; continue
            if h[t] > Bh: Bh = h[t]
            leg = SH - L; fib = L + r * leg
            if touched: zlo = zlo_f; zhi = zhi_f
            else: zlo = fib - w * atr[t]; zhi = fib + w * atr[t]
            if c[t] > zhi and (touched or leg >= k * atr[t]):
                mode = 1; SH = Bh; t += 1; continue          # 反弹过了核心位置：这一段结束
            if (not touched) and h[t] >= zlo and leg >= k * atr[t]:
                touched = True; zlo_f = zlo; zhi_f = zhi; ti = t
                poc = M._poc(h, l, c, v, max(0, Li - 120), Li)
                cn = 1 if (nk >= zlo and nk <= zhi) else 0
                cp = 1 if (poc >= zlo and poc <= zhi) else 0
                cm = 1 if (t >= 5 and sma50[t] < sma50[t - 5] and sma50[t] >= zlo and sma50[t] <= zhi) else 0
            if touched and (not used) and t > intrade_until and c[t] < l[t - 1] and c[t] <= zhi_f:
                used = True
                if ok[t] and d[t] >= dlo and d[t] <= dhi:
                    E = c[t]; stop = Bh + sb * atr[t]; R = stop - E
                    if R > 0 and R / E <= 0.20:
                        T1 = Bh - leg; T2 = Bh - 1.618 * leg
                        g, fF, bF, xi, why, r1, r2, t1i, mfe, mae, st5, c5, held = M._sim(o, h, l, c, t, E, stop, T1, T2, zhi_f, n)
                        legno += 1
                        M._put(ev, ne, float(legno), t, E, stop, R, T1, T2, cn + cp + cm, cn, cp, cm, r1, r2, g, fF, bF, xi, why, mfe, mae, st5, c5, leg / SH, b, ti, held, SH, L, Bh, zhi_f, float(nbear))
                        ne += 1; intrade_until = xi
            t += 1
        i = t + 1
    return ne


def 跑一类(Z, p, 随机对照=True):
    off = Z["off"]; EV = []; ev = np.zeros((2000, 31))
    for si, s in enumerate(Z["syms"]):
        a, b = off[si], off[si + 1]
        if b - a < 300: continue
        d, o, h, l, c, v, ok = (Z[k][a:b] for k in ("d", "o", "h", "l", "c", "v", "ok"))
        ne = scan_bear(d, o, h, l, c, v, ok, p["r"], p["k"], p["w"], p["sb"], p.get("q", 0.382), M.DLO, M.DHI, ev)
        if ne:
            t = pd.DataFrame(ev[:ne].copy(), columns=M.EV_COLS).rename(columns={"层": "第几次", "反弹深度": "第几轮下跌"}); t["票"] = s; t["退市股"] = bool(Z["delisted"][si])
            t["日"] = (d[t["进场i"].astype(int).values].astype("timedelta64[D]") + M.D0)
            if not 随机对照: EV.append(t); continue
            # 随机对照：同票同月随便一天
            ym = (d.astype("timedelta64[D]") + M.D0).astype("datetime64[M]"); rr = []
            for q in range(ne):
                e = int(t["进场i"].iat[q]); cand = np.where((ym == ym[e]) & ok & (np.arange(len(c)) < len(c) - 2))[0]
                if len(cand) == 0: cand = np.array([e])
                E = t["E"].iat[q]; R = t["R"].iat[q]
                rr.append(M.随机(o, h, l, c, cand.astype(np.int64), R / E, (E - t["T1"].iat[q]) / R, (E - t["T2"].iat[q]) / R, len(c), si * 1000 + q))
            rr = np.array(rr); t["随机毛R"], t["随机费F"], t["随机借F"], t["随机到1倍"] = rr.T
            EV.append(t)
    return pd.concat(EV, ignore_index=True) if EV else pd.DataFrame()


if __name__ == "__main__":
    for name in ("指数", "行业", "个股_研究库", "个股_退市股"):
        Z = M.读(name)
        for cn, p in [("基准", dict(M.BASE))] + [(f"{kk}={vv}", {**M.BASE, kk: vv}) for kk in ("r", "k", "w", "sb", "q") for vv in {**M.邻点, "q": (0.236, 0.5)}[kk]]:
            fn = os.path.join(OUT, f"第四轮__{name}__{cn}.pkl")
            if os.path.exists(fn): continue
            t0 = time.time(); ev = 跑一类(Z, p, 随机对照=(cn == "基准")); pd.to_pickle(ev, fn)
            print(name, cn, len(ev), f"{time.time() - t0:.0f}s", flush=True)
    print("DONE")
