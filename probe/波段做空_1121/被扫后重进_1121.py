# -*- coding: utf-8 -*-
"""写规则 chat 的那题:「被止损扫出后,日线方向没变,小时线收线再破小区间,重进一次」是正是负。ETF 小时线,引擎外。
⚠ 原单是我自己搭的最简单可复现版本,不是卡的全套规则:
  方向 = 日线收盘和 20 日线都在 50 日线同侧,且 20 日线比 5 天前同向(用前一天的值)。
  原单 = 顺方向:1 小时线先回踩(反抽)碰到 1 小时 20 均线,之后第一根顺方向收线(多:阳线且收在均线上方并高过前一根高点)→ 下一根开盘进。
  止损 = 信号前 14 根小时线的最低(最高)外 0.5 倍日 ATR;1R 平一半并把止损推到成本,2.5R 全平,最长 10 天。
  重进 = 原单止损(没到过 1R)之后,等至少 4 根小时线形成小区间;日线方向没变;3 个交易日内小时线收线顺方向破出小区间 → 下一根开盘重进,
         止损 = 小区间另一侧外 0.3 倍日 ATR,出场同上。只重进一次。
  对照 = 不管有没有被扫,任何时候「日线方向成立 + 小时线收线顺方向破出最近 4 根的小区间」都进,同样的止损和出场(每只票同时只拿一笔)。
"""
import os, io, sys, json, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
P1 = os.path.join(HERE, "小时线三种_1121.py")
src = io.open(P1, encoding="utf-8").read().replace("\nmain()\n", "\n")
G = {"__file__": P1, "__name__": "h3"}; exec(compile(src, "h3", "exec"), G)
读小时, 备, 组, 段, SLIP, BORROW = G["读小时"], G["备"], G["组"], G["段"], G["SLIP"], G["BORROW"]

def 走(d, h, k, 向, stop, 最长=10):
    """k = 进场那根(按开盘价)。向 = +1 多 / -1 空。返回 dict 或 None。"""
    O, H, L, C, DI = h.o.values, h.h.values, h.l.values, h.c.values, h.di.values
    n = len(h)
    if k >= n: return None
    e = O[k]; R = (e - stop) * 向
    if R <= 0 or R / e > 0.15: return None
    t1, t2 = e + 向 * R, e + 向 * 2.5 * R
    pos, real, hit1 = 1.0, 0.0, False; j = k; how = None; px = None; di0 = DI[k]
    while j < n:
        o, hi, lo, c = O[j], H[j], L[j], C[j]
        adv, fav = (lo, hi) if 向 > 0 else (hi, lo)
        if j > k and (o - stop) * 向 <= 0: px, how = o, "止损(跳空)" if not hit1 else "保本(跳空)"; break
        if (adv - stop) * 向 <= 0: px, how = stop, "止损" if not hit1 else "保本"; break
        if not hit1 and (fav - t1) * 向 >= 0:
            p = t1 if (o - t1) * 向 < 0 or j == k else o
            real += 0.5 * (p - e) * 向; pos = 0.5; hit1 = True; stop = e
        if hit1 and (fav - t2) * 向 >= 0: px, how = (t2 if (o - t2) * 向 < 0 else o), "第二目标"; break
        if (j + 1 >= n or DI[j + 1] != DI[j]) and DI[j] - di0 + 1 >= 最长: px, how = c, "满10天"; break
        j += 1
    if px is None: j = n - 1; px, how = C[-1], "数据到头"
    g = real + pos * (px - e) * 向
    cal = (h.index[j] - h.index[k]).days
    cost = 2 * SLIP * e + (BORROW * e * cal / 365.0 if 向 < 0 else 0.0)
    return {"进场": h.index[k], "出场": h.index[j], "出场位置": j, "向": 向, "毛R": g / R, "净R": (g - cost) / R, "怎么出的": how, "到过1R": hit1, "风险占价pct": 100 * R / e}

def 一只(sym, H):
    d, h = 备(sym, H)
    c = d.c; up = (c > d.sma50) & (d.ema20 > d.sma50) & (d.ema20 > d.ema20.shift(5)); dn = (c < d.sma50) & (d.ema20 < d.sma50) & (d.ema20 < d.ema20.shift(5))
    dir_d = (up.astype(int) - dn.astype(int)).shift(1).fillna(0).values          # 用前一天收盘后的方向
    atr_d = d.atr.shift(1).values
    O, Hh, L, C, E, DI = h.o.values, h.h.values, h.l.values, h.c.values, h.ema20.values, h.di.values
    n = len(h); 原, 重, 照 = [], [], []
    # —— 原单 + 重进
    k = 30; touched = 0; free = 0
    while k < n - 2:
        di = DI[k]; 向 = int(dir_d[di]) if di < len(dir_d) else 0
        if 向 == 0 or not np.isfinite(atr_d[di]) or k < free: touched = 0; k += 1; continue
        if (向 > 0 and L[k] <= E[k]) or (向 < 0 and Hh[k] >= E[k]): touched = k
        sig = touched and k - touched <= 6 and k > touched and (
            (向 > 0 and C[k] > O[k] and C[k] > E[k] and C[k] > Hh[k - 1]) or (向 < 0 and C[k] < O[k] and C[k] < E[k] and C[k] < L[k - 1]))
        if not sig: k += 1; continue
        stop = (L[k - 13:k + 1].min() - 0.5 * atr_d[di]) if 向 > 0 else (Hh[k - 13:k + 1].max() + 0.5 * atr_d[di])
        r = 走(d, h, k + 1, 向, stop)
        touched = 0
        if r is None: k += 1; continue
        r["票"] = sym; 原.append(r); j = r["出场位置"]; free = j + 1
        if r["怎么出的"].startswith("止损"):
            # 重进:被扫后至少 4 根形成小区间,3 个交易日内顺方向收线破出
            a = j + 1; q = a + 4
            while q < n - 2 and DI[q] - DI[j] <= 3:
                dq = DI[q]
                if int(dir_d[dq]) != 向: break
                hi4, lo4 = Hh[a:q].max(), L[a:q].min()
                if (向 > 0 and C[q] > hi4) or (向 < 0 and C[q] < lo4):
                    st2 = (lo4 - 0.3 * atr_d[dq]) if 向 > 0 else (hi4 + 0.3 * atr_d[dq])
                    r2 = 走(d, h, q + 1, 向, st2)
                    if r2: r2["票"] = sym; r2["原单进场"] = r["进场"]; 重.append(r2); free = r2["出场位置"] + 1
                    break
                q += 1
        k = free
    # —— 对照:任何时候破最近 4 根小区间就进
    k = 30; free = 0
    while k < n - 2:
        di = DI[k]; 向 = int(dir_d[di]) if di < len(dir_d) else 0
        if 向 == 0 or not np.isfinite(atr_d[di]) or k < free: k += 1; continue
        hi4, lo4 = Hh[k - 4:k].max(), L[k - 4:k].min()
        if (向 > 0 and C[k] > hi4) or (向 < 0 and C[k] < lo4):
            st = (lo4 - 0.3 * atr_d[di]) if 向 > 0 else (hi4 + 0.3 * atr_d[di])
            r = 走(d, h, k + 1, 向, st)
            if r: r["票"] = sym; 照.append(r); free = r["出场位置"] + 1; k = free; continue
        k += 1
    return 原, 重, 照

def 汇(df):
    if len(df) == 0: return {"笔数": 0}
    r = df["净R"]; w, l = r[r > 0], r[r <= 0]
    return {"笔数": int(len(df)), "扣成本前每笔R": round(df["毛R"].mean(), 3), "扣成本后每笔R": round(r.mean(), 3), "赚钱的笔pct": round(100 * (r > 0).mean(), 1),
            "利润因子": round(w.sum() / -l.sum(), 2) if l.sum() < 0 else None}

def main():
    H = 读小时(); A = {"原单": [], "重进": [], "对照": []}
    for g, syms in 组.items():
        for s in syms:
            if s not in H: continue
            a, b, c = 一只(s, H)
            for nm, z in (("原单", a), ("重进", b), ("对照", c)):
                for r in z: r["组"] = g
                A[nm] += z
    res = {}
    for nm, z in A.items():
        df = pd.DataFrame(z); df.to_csv(os.path.join(HERE, f"被扫后重进_{nm}_逐笔.csv"), index=False)
        for pn, (a, b) in 段.items():
            m = df[(df["进场"] >= a) & (df["进场"] <= b + " 23:59")]
            for g in ["指数+行业", "三倍杠杆"]:
                mg = m[m["组"].isin(["指数", "行业"])] if g == "指数+行业" else m[m["组"] == g]
                res[f"{nm}|{pn}|{g}|多空合计"] = 汇(mg); res[f"{nm}|{pn}|{g}|多"] = 汇(mg[mg["向"] > 0]); res[f"{nm}|{pn}|{g}|空"] = 汇(mg[mg["向"] < 0])
    json.dump(res, io.open(os.path.join(HERE, "被扫后重进_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    for k, v in res.items(): print(k, v)
    o = pd.DataFrame(A["原单"]); o = o[o["组"].isin(["指数", "行业"])]
    print("原单里被止损的占比", round(100 * o["怎么出的"].str.startswith("止损").mean(), 1), "其中有重进的", len([1 for r in A["重进"] if r["组"] in ("指数", "行业")]))

main()
