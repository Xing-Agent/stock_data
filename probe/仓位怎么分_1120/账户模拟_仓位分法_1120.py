#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""仓位怎么分：同一批信号、同一种挑法，只换「每只给多少钱」（2026-11-20 · Lin：缺的最重要一环）

大白话：以前的回测每只票给的钱差不多。这里在引擎外面另写一个小账户，信号还是每条策略原来的全部信号，
挑哪只买还是「成交额大的先买」，只换每只票给多少钱，看账户每年赚多少、最惨跌多少。
所有分法只用买入前一天已经知道的东西，不看之后谁涨得多。

分法（「标准仓」= 账户的 10%，同时最多 10 只）：
  等权            每只 10%
  按成交额        当天在池子里成交额排名越靠前给越多
  按动量          过去 126 天涨幅在池子里排名越靠前给越多
  按波动反着给    过去 20 天波动越小给越多
  以上三种各有两档力度：温和（0.5~1.5 倍标准仓）、激进（排前五分之一的给 3 倍，其余给 0.5 倍）
  走出来再加      同时最多 20 只，每只先给 5%；之后每多涨 10% 就再加 5%（按当天收盘价加），加到单票上限为止
  等权 20 只      每只 5%（给「走出来再加」当对照）
单票上限三档：20% / 35% / 50%（买入和加仓时不许超过；涨上去超过的不强行卖）。不借钱：现金不够就少买或不买。
每次买卖扣 5 个基点。

⚠ 和引擎成绩不是一回事，不能直接比：这里不含分红；账户是我自己写的简化版；信号流来自「每个信号都接」的流水，
   其中 7 条策略当时同时持仓顶到上限、信号并不全（见《192》）。这里只用来比「分法之间谁好谁差」。
engine/ 没碰。
"""
import glob, io, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
import numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
import 跑基本面_1106 as B
B.装层()
from engine import cache
C = cache._PANEL["close"].astype(float); V = cache._PANEL["volume"].astype(float)
MK = pd.read_parquet(os.path.join(ROOT, "probe/流动性池_1114/流动性池掩膜_中.parquet"))
perf = MK.index; cols = [c for c in MK.columns if c in C.columns]
C = C[cols]; mk = MK[cols].reindex(C.index).fillna(False)
def pct(df): return df.where(mk).rank(axis=1, pct=True).shift(1)        # 只用前一天的排名
P = {"按成交额": pct((C * V[cols]).rolling(20, min_periods=20).mean()),
     "按动量": pct(C / C.shift(126) - 1),
     "按波动反着给": 1 - pct(C.pct_change().rolling(20, min_periods=20).std())}
Cf = C.ffill().reindex(perf); CA = Cf.to_numpy(); ci = {s: i for i, s in enumerate(cols)}; di = {d: i for i, d in enumerate(perf)}
PA = {k: v.reindex(perf).to_numpy() for k, v in P.items()}
FEE = 0.0005; yrs = (perf[-1] - perf[0]).days / 365.25

def 倍数(法, 力度, t, j):
    if 法 == "等权": return 1.0
    p = PA[法][t, j]
    if not np.isfinite(p): p = 0.5
    return (0.5 + p) if 力度 == "温和" else (3.0 if p >= 0.8 else 0.5)

def 模拟(L, 法, 力度, 上限, 槽=10, 标准=0.10, 加仓=False):
    by_in = {}; 
    for r in L.itertuples(index=False): by_in.setdefault(r.ti, []).append(r)
    cash = 1.0; pos = {}; eq = np.empty(len(perf)); 峰 = 0.0; 仓 = []
    pnl = []
    for t in range(len(perf)):
        for s in [s for s, p in pos.items() if p["to"] <= t]:
            p = pos.pop(s); cash += p["sh"] * p["xp"] * (1 - FEE); pnl.append(p["sh"] * p["xp"] * (1 - FEE) - p["cost"])
        E = cash + sum(p["sh"] * CA[t, p["j"]] for p in pos.values())
        if 加仓:
            for s, p in pos.items():
                px = CA[t, p["j"]]
                while px >= p["ep"] * (1 + 0.10 * (p["n"] + 1)) and p["sh"] * px / E + 0.05 <= 上限 + 1e-9 and cash >= 0.05 * E * (1 + FEE):
                    add = 0.05 * E; p["sh"] += add / px; p["cost"] += add * (1 + FEE); cash -= add * (1 + FEE); p["n"] += 1
        for r in sorted(by_in.get(t, []), key=lambda r: -r.adv):
            if len(pos) >= 槽 or r.symbol in pos or r.to <= t: continue
            j = ci[r.symbol]; w = min(标准 * 倍数(法, 力度, t, j), 上限); amt = min(w * E, cash / (1 + FEE))
            if amt < 0.01 * E: continue
            pos[r.symbol] = {"sh": amt / r.entry_price, "ep": r.entry_price, "xp": r.exit_price, "to": r.to, "j": j, "cost": amt * (1 + FEE), "n": 0}
            cash -= amt * (1 + FEE)
        vals = [p["sh"] * CA[t, p["j"]] for p in pos.values()]
        E = cash + sum(vals); eq[t] = E
        if vals: 峰 = max(峰, max(vals) / E)
        仓.append(sum(vals) / E)
    e = pd.Series(eq, index=perf); ann = e.iloc[-1] ** (1 / yrs) - 1; dd = (e / e.cummax() - 1).min()
    pnl = np.array(pnl); tot = pnl.sum()
    return {"每年赚pct": round(ann * 100, 2), "最惨跌pct": round(dd * 100, 2), "卡玛": round(ann / abs(dd), 3) if dd < 0 else None,
            "平均仓位pct": round(float(np.mean(仓)) * 100, 1), "单票占比最高到过pct": round(峰 * 100, 1), "成交笔数": int(len(pnl)),
            "最赚5笔占总利润pct": round(float(np.sort(pnl)[-5:].sum() / tot * 100), 1) if tot > 0 and len(pnl) > 5 else None}

方案 = [("等权", "等权", "—", 0.20, 10, 0.10, False)]
for 法 in ("按成交额", "按动量", "按波动反着给"):
    方案.append((f"{法}_温和", 法, "温和", 0.20, 10, 0.10, False))
    for cap in (0.35, 0.50): 方案.append((f"{法}_激进_上限{int(cap*100)}", 法, "激进", cap, 10, 0.10, False))
方案.append(("等权20只", "等权", "—", 0.20, 20, 0.05, False))
for cap in (0.20, 0.35, 0.50): 方案.append((f"走出来再加_上限{int(cap*100)}", "等权", "—", cap, 20, 0.05, True))

res = {}
for fp in sorted(glob.glob(os.path.join(ROOT, "probe/含分红重出_1116/微仓_ledgers/微仓__*.csv"))):
    n = os.path.basename(fp)[:-4].replace("微仓__", "")
    L = pd.read_csv(fp, usecols=["symbol", "entry_date", "exit_date", "entry_price", "exit_price", "adv20_at_entry"])
    L["ti"] = pd.to_datetime(L.entry_date).map(di); L["to"] = pd.to_datetime(L.exit_date).map(di)
    L = L[L.symbol.isin(ci)].dropna(subset=["ti", "to", "entry_price", "exit_price"]); L = L[(L.entry_price > 0) & (L.exit_price > 0)]
    if len(L) < 100: continue
    L["ti"] = L.ti.astype(int); L["to"] = L.to.astype(int); L["adv"] = L.adv20_at_entry.fillna(0)
    res[n] = {"信号笔数": int(len(L)), **{名: 模拟(L, 法, 力, cap, 槽, 标, 加) for 名, 法, 力, cap, 槽, 标, 加 in 方案}}
    print(n, len(L), res[n]["等权"]["每年赚pct"], res[n]["走出来再加_上限35"]["每年赚pct"], flush=True)
    io.open(os.path.join(HERE, "仓位分法_结果_1120.json"), "w", encoding="utf-8").write(json.dumps(res, ensure_ascii=False, indent=1))
rows = [{"策略": n, "信号笔数": r["信号笔数"], "分法": k, **v} for n, r in res.items() for k, v in r.items() if isinstance(v, dict)]
pd.DataFrame(rows).to_csv(os.path.join(HERE, "仓位分法_明细_1120.csv"), index=False)
print("ALL_DONE", flush=True)
