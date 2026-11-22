# -*- coding: utf-8 -*-
"""「破位那根收盘直接追」补相邻参数和更多品种（写规则 chat《247》第二节点名）· 1 小时线 · 引擎外
基准 = 《382》的 C 组：4 小时箱体（过去 20 根、箱高 2~6 倍 ATR、上下各碰 2 次）被放量实体 K 线收盘突破 0.25×ATR → 那根收盘进；
止损 = 分界线往里 0.5×ATR；第一目标 = 线外 1 倍箱高（平一半、推成本），第二目标 = 1.618 倍；最长 72 根；成本单边 0.05%。
这一轮：箱体长度 15 / 20 / 30；突破幅度 0.15 / 0.25 / 0.35；止损 0.25 / 0.5 / 0.75；量比 1.2 / 1.5 / 2.0。每次只动一个。
品种：22 只 ETF（含反向和杠杆）+ BTC、ETH。两个十年分开，多空分开。另加随机对照：同一只票同一个月随便一根收盘、同方向、同样的止损距离和目标倍数。
"""
import os, sys, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("b", os.path.join(HERE, "贴线整理_1122.py")); b = importlib.util.module_from_spec(sp); sp.loader.exec_module(b)
FEE = 0.0005

def 走(O, H, L, C, ei, Lg, e, stp, tp1, tp2, hold=72):
    risk = (e - stp) if Lg else (stp - e); n = len(C)
    rr1 = ((tp1 - e) if Lg else (e - tp1)) / risk; rr2 = ((tp2 - e) if Lg else (e - tp2)) / risk
    half = False; res = None; Rm = 0; s = stp; jj = ei
    for j in range(ei + 1, min(ei + 1 + hold, n)):
        jj = j
        if not half:
            if (L[j] <= s) if Lg else (H[j] >= s): res = -1; break
            if (H[j] >= tp1) if Lg else (L[j] <= tp1): half = True; Rm = 0.5 * rr1; s = e
        else:
            if (L[j] <= s) if Lg else (H[j] >= s): res = Rm; break
            if (H[j] >= tp2) if Lg else (L[j] <= tp2): res = Rm + 0.5 * rr2; break
    if res is None:
        last = C[jj]; res = (Rm if half else 0) + (0.5 if half else 1) * (((last - e) if Lg else (e - last)) / risk)
    return res, half, jj

def 跑(d, N=20, brk=0.25, stk=0.5, volx=1.5, seed=0):
    B = b.boxes(d, N=N); A = b.atr(d).values
    O, H, L, C, V = [d[c].values for c in ["open", "high", "low", "close", "volume"]]
    top, bot, ok = B.top.values, B.bot.values, B.ok.fillna(False).values.astype(bool)
    vma = pd.Series(V).rolling(20).mean().shift(1).values; n = len(d); T = []; i = 150
    ym = (d.index.year * 100 + d.index.month).values; rng = np.random.default_rng(seed)
    while i < n - 8:
        if not ok[i] or np.isnan(A[i]) or np.isnan(vma[i]): i += 1; continue
        body = abs(C[i] - O[i]); rg = H[i] - L[i] + 1e-12
        up = C[i] > top[i] + brk * A[i] and C[i - 1] <= top[i]; dn = C[i] < bot[i] - brk * A[i] and C[i - 1] >= bot[i]
        if not (up or dn) or V[i] < volx * vma[i] or body < 0.5 * rg: i += 1; continue
        Lg = up; line = top[i] if Lg else bot[i]; bh = top[i] - bot[i]
        e = C[i]; stp = line - stk * A[i] if Lg else line + stk * A[i]; risk = (e - stp) if Lg else (stp - e)
        tp1 = line + bh if Lg else line - bh; tp2 = line + 1.618 * bh if Lg else line - 1.618 * bh
        if risk <= 0 or ((tp1 - e) if Lg else (e - tp1)) <= 0: i += 1; continue
        res, half, jj = 走(O, H, L, C, i, Lg, e, stp, tp1, tp2)
        # 随机对照：同月随便一根，同方向，同样的止损距离比例和目标倍数
        cand = np.where(ym == ym[i])[0]; cand = cand[(cand > 150) & (cand < n - 8)]; rr = []
        for k in rng.choice(cand, size=min(5, len(cand)), replace=False):
            e2 = C[k]; rk = risk / e * e2; m1 = abs(tp1 - e) / risk; m2 = abs(tp2 - e) / risk
            s2 = e2 - rk if Lg else e2 + rk; t1 = e2 + m1 * rk if Lg else e2 - m1 * rk; t2 = e2 + m2 * rk if Lg else e2 - m2 * rk
            rr.append(走(O, H, L, C, k, Lg, e2, s2, t1, t2)[0] - 2 * FEE / (rk / e2))
        T.append({"t": d.index[i], "年": d.index[i].year, "dir": "多" if Lg else "空", "R": res, "净R": res - 2 * FEE / (risk / e), "tp1": half, "riskp": risk / e, "随机净R": float(np.mean(rr)) if rr else np.nan})
        i = jj + 1
    return pd.DataFrame(T)

def S(t):
    if len(t) == 0: return {"笔数": 0}
    r = t["净R"]; w = r[r > 0].sum(); l = -r[r < 0].sum()
    return {"笔数": int(len(t)), "每笔毛R": round(float(t.R.mean()), 3), "每笔净R": round(float(r.mean()), 3), "胜率pct": round(float((r > 0).mean() * 100), 1), "利润因子": round(float(w / l), 2) if l > 0 else None,
            "到第一目标pct": round(float(t.tp1.mean() * 100), 1), "止损宽中位pct": round(float(t.riskp.median() * 100), 2), "随机对照净R": round(float(t["随机净R"].mean()), 3)}

if __name__ == "__main__":
    syms = ["SPY", "QQQ", "DIA", "IWM", "SMH", "KRE", "XLB", "XLE", "XLF", "XLI", "XLK", "XLP", "XLRE", "XLU", "XLV", "XLY", "TQQQ", "SOXL", "SQQQ", "SOXS", "PSQ", "SH", "BTC", "ETH"]
    组 = {"基准": {}, "箱体15根": dict(N=15), "箱体30根": dict(N=30), "突破0.15": dict(brk=0.15), "突破0.35": dict(brk=0.35), "止损0.25": dict(stk=0.25), "止损0.75": dict(stk=0.75), "量比1.2": dict(volx=1.2), "量比2.0": dict(volx=2.0)}
    类 = lambda s: "币" if s in ("BTC", "ETH") else ("杠杆和反向ETF" if s in ("TQQQ", "SOXL", "SQQQ", "SOXS", "PSQ", "SH") else ("大指数ETF" if s in ("SPY", "QQQ", "DIA", "IWM") else "行业ETF"))
    data = {s: b.load(s) for s in syms}; allT = {}
    for g, kw in 组.items():
        L = []
        for s in syms:
            t = 跑(data[s], **kw)
            if len(t): t["票"] = s; t["类"] = 类(s); L.append(t)
        allT[g] = pd.concat(L); print(g, S(allT[g]), flush=True)
    allT["基准"].to_csv(os.path.join(HERE, "out", "直接追_基准_逐笔.csv"), index=False)
    out = {}
    for g, t in allT.items():
        t = t[(t["年"] >= 2005) & (t["年"] <= 2025)]; t["段"] = np.where(t["年"] <= 2014, "2005–2014", "2015–2025")
        out[g] = {"全部": S(t), "分段分多空": {f"{a}｜{d_}": S(x) for (a, d_), x in t.groupby(["段", "dir"])}, "分类分段分多空": {f"{c}｜{a}｜{d_}": S(x) for (c, a, d_), x in t.groupby(["类", "段", "dir"])}}
        if g == "基准": out[g]["分票"] = {f"{s}｜{a}": S(x) for (s, a), x in t.groupby(["票", "段"])}; out[g]["分年"] = {int(y): S(x) for y, x in t.groupby("年")}
    json.dump(out, open(os.path.join(HERE, "out", "直接追_扫参数_结果.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("DONE")
