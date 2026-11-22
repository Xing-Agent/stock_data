# -*- coding: utf-8 -*-
"""大周期状态机 · 第二版（按 Lin 11-22 21:53 看图后的话改）· BTC / ETH 日线 · 引擎外
Lin 指出第一版的错：
  ① 涨势里的「上涨中继平台」（2024-01 那次回调、2024-03 到 10 月那个大区间）被标成了跌势 —— 不对；
  ② 这一轮 2026-10 反弹到 8.6 万、高过了前一个反弹高点 8.2 万多 → 顶在抬高、框架已经转换、至少这一波跌结束了；
     但筑底还没完全结束，是「筑了一个大底、准备去走一浪」的阶段，可以深度回调。
第二版的五种状态：涨势 / 涨势·中继 / 见顶 / 跌势 / 转涨期
我的写法（★ 都是我为了把 Lin 的话写成能算的而提的，没有出处，要 Lin 和 Gemini 看）：
  - 「地板」= 上一个被**有效突破**（之后的最高价高过它 15% 以上；10%、12%、20% 也试了：10% 会在 2025-08 提前转空，20% 要到 2026-02 才转空，12% 和 15% 都在 2025-10-16 / 17 转空）的周线摆动高点（左右各 4 周）。
    多头框架里（涨势 / 中继 / 见顶），回调只要收盘没有跌回地板之下 2%，就还是多头框架：满足涨势条件标涨势，满足见顶条件标见顶，其余标「涨势·中继」。
    收盘跌回地板之下 2% → 框架转空，标跌势。
  - 跌势里：盯着「最近一个已确认的大反弹高点」（周线摆动高点，左右各 4 周，而且是在这轮跌势里出现的）。收盘高过它、并且在 200 日线之上 → 框架转换，标「转涨期」。
    （先试过左右各 2 周、不看 200 日线：2026 年 1 月、4 月的小反弹都会被当成转涨，和 Lin 的判断不符）
  - 转涨期：满足涨势全部条件（顶底抬高、收盘 > 50 日线 > 200 日线、离半年高点 < 15%）**并且收复了这轮跌幅的一半** → 涨势；
    （不加「收复一半」的话，2026-10 反弹到 8.6 万会直接标成涨势；Lin 说那时筑底还没完全结束）
    跌破关键位（最近 60 天最低的已确认摆动低点）且 5 天内反弹不到 0.382 → 切回跌势；收盘跌破这轮跌势的最低点 → 跌势。
  - 涨势、见顶的原始条件同第一版（Gemini 的写法）。
"""
import os, sys, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("v1", os.path.join(HERE, "四档状态机_1122.py")); v1 = importlib.util.module_from_spec(sp); sp.loader.exec_module(v1)

def 周线摆动高点(D, k):
    W = D.resample("W").agg({"high": "max"}).dropna(); x = W.high.values; out = []
    for i in range(k, len(W) - k):
        if x[i] == x[i - k:i + k + 1].max(): out.append((W.index[i + k], W.index[i], float(x[i])))     # (确认日, 发生那周, 价格)
    return out

def 跑(D, k=3, 突破幅度=0.15, 地板容差=0.02, 收复比例=0.5):
    o, h, l, c = D.open.values, D.high.values, D.low.values, D.close.values; n = len(D); idx = D.index
    e50 = D.close.ewm(span=50, adjust=False).mean().values; e200 = D.close.ewm(span=200, adjust=False).mean().values
    h180 = D.high.rolling(180, min_periods=60).max().values; h365 = D.high.rolling(365, min_periods=120).max().values
    W4 = 周线摆动高点(D, 4); W2 = 周线摆动高点(D, 2)
    SH, SL = [], []; st = ["历史不够"] * n; why = [""] * n; cur = None; floor = np.nan; pend = None
    框架起点 = idx[0]; 跌势起点 = None; 跌势最低 = np.nan; fl = [np.nan] * n; 前高 = np.nan; 参考高 = np.nan; 转涨最高 = np.nan
    for i in range(n):
        j = i - k
        if j >= k:
            w = slice(j - k, j + k + 1)
            if h[j] == h[w].max(): SH.append((i, h[j]))
            if l[j] == l[w].min(): SL.append((i, l[j]))
        if i < 220 or len(SH) < 2 or len(SL) < 2: continue
        t = idx[i]; hh = SH[-1][1] > SH[-2][1]; hl = SL[-1][1] > SL[-2][1]
        up = hh and hl and c[i] > e50[i] > e200[i] and c[i] > 0.85 * h180[i]
        top = c[i] > 0.80 * h365[i] and SH[-1][1] <= SH[-2][1] * 1.015 and c[i] < e50[i] and c[i] > e200[i]
        new = cur; r = ""
        if cur is None:
            new = "涨势" if c[i] > e200[i] else "跌势"; r = "起始：看在 200 日线上还是下"
            if new == "跌势": 跌势起点 = t; 跌势最低 = l[i]
        elif cur in ("涨势", "涨势·中继", "见顶"):
            前高 = h[i] if np.isnan(前高) else max(前高, h[i])
            # 地板：框架起点之后发生、已确认、且之后被有效突破的周线高点里最近的一个
            cand = [(wk, p) for (cf, wk, p) in W4 if cf <= t and wk >= 框架起点 and D.high.loc[wk:t].max() >= p * (1 + 突破幅度)]
            if cand: floor = cand[-1][1]
            if not np.isnan(floor) and c[i] < floor * (1 - 地板容差):
                new = "跌势"; r = f"收盘跌回上一个被有效突破的前高（{floor:,.0f}）之下，框架转空"; 跌势起点 = t; 跌势最低 = l[i]
            elif up: new = "涨势"
            elif top: new = "见顶"
            else: new = "涨势·中继"
            if new != cur and r == "": r = {"涨势": "顶底抬高、站上 50 和 200 日线", "见顶": "离一年高点两成以内、新高点没超过前高、跌破 50 日线", "涨势·中继": "回调，但没跌回上一个被有效突破的前高"}[new]
        elif cur == "跌势":
            跌势最低 = min(跌势最低, l[i])
            reb = [(wk, p) for (cf, wk, p) in W4 if cf <= t and wk > 跌势起点]
            ref = reb[-1][1] if reb else np.nan
            if not np.isnan(参考高): ref = 参考高 if np.isnan(ref) else min(ref, 参考高)      # 上一次转涨失败时到过的最高点，也算一个要越过的反弹高点
            if not np.isnan(ref) and c[i] > ref and c[i] > e200[i]:
                new = "转涨期"; r = f"收盘高过这轮跌势里最近一个反弹高点（{ref:,.0f}），顶在抬高，框架转换"; pend = None; 转涨最高 = h[i]; 参考高 = np.nan
        elif cur == "转涨期":
            转涨最高 = h[i] if np.isnan(转涨最高) else max(转涨最高, h[i])
            if up and (np.isnan(前高) or c[i] >= 跌势最低 + 收复比例 * (前高 - 跌势最低)):
                new = "涨势"; r = "顶底抬高、站上 50 和 200 日线，并收复了这轮跌幅的一半"; 前高 = h[i]; 框架起点 = 跌势起点 if 跌势起点 is not None else 框架起点; floor = 跌势最低
            elif c[i] < 跌势最低:
                new = "跌势"; r = "跌破这轮跌势的最低点"; 跌势起点 = t; 跌势最低 = l[i]; 参考高 = 转涨最高
            else:
                rec = [p for (ci, p) in SL if ci >= i - 60]
                if pend is None and rec and c[i] < min(rec) and c[i] < o[i]: pend = {"i": i, "lvl": min(rec), "top": SH[-1][1], "low": l[i]}
                if pend is not None:
                    pend["low"] = min(pend["low"], l[i])
                    if i - pend["i"] >= 5:
                        rb = (h[pend["i"] + 1:i + 1].max() - pend["low"]) / max(pend["top"] - pend["low"], 1e-9)
                        if rb < 0.382 and c[i] < pend["lvl"]:
                            new = "跌势"; r = f"跌破关键位（{pend['lvl']:,.0f}）后 5 天反弹不到 0.382，切回跌势"; 跌势起点 = t; 跌势最低 = min(跌势最低, l[i]); 参考高 = 转涨最高
                        pend = None
        if new != cur: why[i] = r
        cur = new; st[i] = cur; fl[i] = floor
    return pd.DataFrame({"close": c, "档": st, "切换原因": why, "地板": fl}, index=idx)

if __name__ == "__main__":
    for sym in ("BTC", "ETH"):
        D = v1.日线(sym); R = 跑(D); R.to_csv(os.path.join(HERE, "out", f"{sym}_二版_每天的档.csv"))
        sw = R[R["切换原因"] != ""]; sw.to_csv(os.path.join(HERE, "out", f"{sym}_二版_切换清单.csv"))
        print(sym, R["档"].value_counts().to_dict())
        x = sw[(sw["档"].isin(["跌势", "转涨期"])) | (sw["档"].shift().isin(["跌势", "转涨期"]))]
        print(x[["close", "档", "切换原因"]].to_string()[:5000])
