#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""离场挂件第一轮：同一批买入，只换「拿的过程中怎么处理」（2026-11-19 · Lin：这周把这套手法当优化重点）

大白话：买入不变（还是每条策略原来买的那些票、那个价、那个初始止损），只换离场手法，看每一笔的结果怎么变。
「1R」= 买入价到初始止损的距离，也就是这一笔原计划最多亏的那一份。
五种手法：
  原样          策略原来的离场
  到目标减半    涨到 +kR 先卖一半，另一半照原样
  到目标推保本  涨到 +kR 后，止损推到买入价（不减仓）
  减半加保本    涨到 +kR 卖一半，另一半止损推到买入价
  减半加跟涨    涨到 +kR 卖一半，另一半止损跟着最高价往上推（最高价 − mR，且不低于买入价）
k、m 原著没有统一的数（Lin 的做法是到「最近的阻力」减仓，这里先用 R 的倍数代替），所以按红线②每个都跑相邻三点：k = 1.5 / 2 / 3；m = 1.5 / 2 / 3。
不偷看：到目标那天只做减仓，新止损从第二天才生效；同一天又到目标又破止损的，按先破止损算（对挂件不利的方向）。
跳空：开盘直接跳过目标，按开盘价卖；开盘直接跳破止损，按开盘价卖（比止损价更差）。每次卖出扣 5 个基点。
两种量法都出：账户里真买到的那些笔（技术面中档_ledgers），和每个信号都接的那些笔（微仓_ledgers）。
⚠ 这一轮没做的：卖出一半后腾出来的钱没有再拿去买别的票，所以这里只能比「每一笔」，不能直接推出账户每年赚多少。
engine/ 没碰：全部在引擎外面，用流水 + 日线面板重算。
"""
import glob, io, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
import numpy as np, pandas as pd
import 跑基本面_1106 as B
B.装层()
from engine import cache
P = {k: cache._PANEL[k] for k in ("open", "high", "low", "close")}
IDX = P["close"].index; POS = {d: i for i, d in enumerate(IDX)}
ARR = {}
def 票(s):
    if s not in ARR:
        ARR[s] = tuple(P[k][s].to_numpy(dtype=float) for k in ("open", "high", "low", "close")) if s in P["close"].columns else None
    return ARR[s]
FEE = 0.0005

def 一笔(o, h, l, c, i0, i1, ep, R, xp, 法, k, m):
    """返回这一笔的收益率（对买入价）。i0 买入日位置，i1 原离场日位置，xp 原离场价。"""
    if 法 == "原样" or not (R > 0) or i1 <= i0:
        return xp / ep - 1 - FEE
    tgt = ep + k * R; 到了 = False; 剩 = 1.0; 得 = 0.0; stop = None; 高 = ep
    for t in range(i0 + 1, i1 + 1):
        if not np.isfinite(c[t]): continue
        if 到了 and stop is not None:
            if o[t] <= stop or l[t] <= stop:
                px = min(o[t], stop)
                return 得 + 剩 * (px / ep - 1 - FEE)
        if not 到了 and h[t] >= tgt:
            到了 = True; px = max(o[t], tgt)
            if 法 in ("到目标减半", "减半加保本", "减半加跟涨"):
                得 += 0.5 * (px / ep - 1 - FEE); 剩 = 0.5
            if 法 in ("到目标推保本", "减半加保本"): stop = ep
        高 = max(高, h[t])
        if 到了 and 法 == "减半加跟涨": stop = max(ep, 高 - m * R)   # 用到今天为止的最高价，明天才生效
    return 得 + 剩 * (xp / ep - 1 - FEE)

变体 = [("原样", 2, 2)] + [(f, k, 2) for f in ("到目标减半", "到目标推保本", "减半加保本") for k in (1.5, 2, 3)] + \
       [("减半加跟涨", k, 2) for k in (1.5, 3)] + [("减半加跟涨", 2, m) for m in (1.5, 2, 3)]

def 算(fp):
    L = pd.read_csv(fp)
    if len(L) < 30: return None
    out = {}; rets = {v: [] for v in 变体}; w = []
    for r in L.itertuples(index=False):
        a = 票(str(r.symbol)); d0 = pd.Timestamp(r.entry_date); d1 = pd.Timestamp(r.exit_date)
        if a is None or d0 not in POS or d1 not in POS: continue
        ep = float(r.entry_price); R = ep - float(r.initial_stop) if pd.notna(r.initial_stop) else np.nan
        if not (ep > 0): continue
        w.append(float(r.notional_in))
        for v in 变体:
            rets[v].append(一笔(*a, POS[d0], POS[d1], ep, R, float(r.exit_price), *v))
    w = np.array(w)
    for v in 变体:
        x = np.array(rets[v]); win = x > 0
        pnl = x * w; top = np.argsort(rets[变体[0]])[-5:]
        out[f"{v[0]}_k{v[1]}" + (f"_m{v[2]}" if v[0] == "减半加跟涨" else "")] = {
            "笔数": int(len(x)), "赚钱的笔数占比pct": round(float(win.mean() * 100), 1),
            "平均每笔pct": round(float(x.mean() * 100), 2), "中位每笔pct": round(float(np.median(x) * 100), 2),
            "赚的平均赚pct": round(float(x[win].mean() * 100), 2) if win.any() else None,
            "亏的平均亏pct": round(float(x[~win].mean() * 100), 2) if (~win).any() else None,
            "盈亏比": round(float(x[win].mean() / abs(x[~win].mean())), 2) if win.any() and (~win).any() and x[~win].mean() != 0 else None,
            "亏超过5pct的笔数占比pct": round(float((x < -0.05).mean() * 100), 1),
            "按下单金额算的总盈亏": round(float(pnl.sum())),
            "原样里最赚的5笔_在这版里保住的比例pct": round(float(np.array(rets[v])[top].sum() / np.array(rets[变体[0]])[top].sum() * 100), 1)}
    return out

def main():
    res = {"账户里真买到的": {}, "每个信号都接": {}}
    for fp in sorted(glob.glob(os.path.join(ROOT, "probe/含分红重出_1116/技术面中档_ledgers/*.csv"))):
        r = 算(fp)
        if r: res["账户里真买到的"][os.path.basename(fp)[:-4]] = r
    for fp in sorted(glob.glob(os.path.join(ROOT, "probe/含分红重出_1116/微仓_ledgers/微仓__*.csv"))):
        n = os.path.basename(fp)[:-4].replace("微仓__", "")
        if n in res["账户里真买到的"]:
            r = 算(fp)
            if r: res["每个信号都接"][n] = r
    io.open(os.path.join(HERE, "离场挂件_结果_1119.json"), "w", encoding="utf-8").write(json.dumps(res, ensure_ascii=False, indent=1))
    rows = []
    for 量法, d in res.items():
        for n, r in d.items():
            for v, x in r.items(): rows.append({"量法": 量法, "策略": n, "手法": v, **x})
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "离场挂件_明细_1119.csv"), index=False)
    print("ok", {k: len(v) for k, v in res.items()})
main()
