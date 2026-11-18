#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""《216》第一节的结构定义，写成能算的函数（2026-11-18 · 经验核对用）

大白话：把「摆动高低点、平台、实体跌破」这些词变成程序，后面每一条经验说法都用同一套定义去数。
所有判断只用当天及以前的数据（摆动点要等右边 2 根 K 线走完才算数）。
数字照《216》第一节的默认值：摆动点左右各 2 根；平台 = 最近 50 根内至少 2 个摆动点落在同一个 0.5×ATR 宽的价格带；
实体跌破 = 收盘在平台下沿之下至少 0.25×ATR；ATR = 14 根平均真实波幅。
"""
import numpy as np


def atr14(h, l, c, n=14):
    pc = np.roll(c, 1); pc[0] = np.nan
    tr = np.nanmax(np.vstack([h - l, np.abs(h - pc), np.abs(l - pc)]), axis=0)
    out = np.full(len(c), np.nan)
    ok = np.isfinite(tr)
    cs = np.cumsum(np.where(ok, tr, 0.0)); cn = np.cumsum(ok)
    out[n:] = (cs[n:] - cs[:-n]) / np.maximum(cn[n:] - cn[:-n], 1)
    out[(cn - np.concatenate([[0] * n, cn[:-n]])) < n] = np.nan
    return out


def 摆动点(x, 高=True, k=2):
    """返回下标数组：x[p] 严格高于（低于）左右各 k 根。p 这个点要到 p+k 那天才确认。"""
    T = len(x); out = []
    for p in range(k, T - k):
        v = x[p]
        if not np.isfinite(v):
            continue
        w = np.concatenate([x[p - k:p], x[p + 1:p + k + 1]])
        if not np.isfinite(w).all():
            continue
        if (高 and (v > w).all()) or ((not 高) and (v < w).all()):
            out.append(p)
    return np.array(out, dtype=int)


def 支撑平台(l, c, atr, 看回=50, 带宽=0.5, k=2):
    """每天给出「当时已经确认的、最靠近价格的支撑平台」的下沿和上沿（没有就是 nan）。
    平台 = 最近 `看回` 根内、已确认的摆动低点里，至少 2 个落在同一个 `带宽`×ATR 宽的价格带。
    多个平台时取下沿最高、且前一天收盘不低于下沿的那个（价格还站在它上面或里面）。"""
    T = len(c)
    lo = np.full(T, np.nan); hi = np.full(T, np.nan); cnt = np.zeros(T, dtype=int)
    sl = 摆动点(l, 高=False, k=k)
    j0 = 0; j1 = 0
    for t in range(1, T):
        a = atr[t - 1]
        if not np.isfinite(a) or a <= 0 or not np.isfinite(c[t - 1]):
            continue
        while j1 < len(sl) and sl[j1] + k <= t - 1:
            j1 += 1
        while j0 < j1 and sl[j0] < t - 看回:
            j0 += 1
        if j1 - j0 < 2:
            continue
        v = np.sort(l[sl[j0:j1]])
        best = None
        i = 0
        for e in range(len(v)):
            while v[e] - v[i] > 带宽 * a:
                i += 1
            if e - i + 1 >= 2 and v[i] <= c[t - 1]:
                if best is None or v[i] > best[0]:
                    best = (v[i], v[e], e - i + 1)
        if best:
            lo[t], hi[t], cnt[t] = best
    return lo, hi, cnt
