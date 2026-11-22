#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Lin 11-21 夜说的那种做法的最简版:挑中的票拿着不动 + 大盘关了就全卖、开了再买回。engine/ 不动(闸在内存里换 m.regime,清仓开关在配置副本里开)。
范围:D = 动量前 20% + 增长前 30%(另跑 30/40 档);对照 A = 整个流动性池。大盘开关三种:行业版(SPY 在 200 日线上且 200 日线比 20 天前高)、
Faber 月线(SPY 月末在 10 个月均线上)、温斯坦周线(SPY 周收盘在 30 周均线上且均线向上)。都只用前一天及更早的收盘。"""
import copy, io, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import importlib.util
sp = importlib.util.spec_from_file_location("J", os.path.join(HERE, "联合回测_1122.py")); J = importlib.util.module_from_spec(sp); sp.loader.exec_module(J)
import yaml, numpy as np, pandas as pd
B, FIX = J.装()
from engine import matrices, data
from engine_v2 import chain
hold = json.load(io.open(B.HOLD, encoding="utf-8")); dev, hs = hold["研发池名单"], set(hold["留出池名单"])
raw0 = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs/buy_and_hold.yaml"), encoding="utf-8"))
m = matrices.build(chain.ChainConfig.from_dict(copy.deepcopy(raw0)).raw, dev); FIX.拿掉(m)
膜 = lambda f: pd.read_parquet(os.path.join(J.OUT, f)).reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
liq = pd.read_parquet(os.path.join(J.POOL, "流动性池掩膜_中.parquet")); perf = liq.index
liq = liq.reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
base = m.universe & liq; yrs = (perf[-1] - perf[0]).days / 365.25; idx = m.index
sh = lambda a: np.vstack([np.zeros((1, a.shape[1]), bool), a[:-1]])
U = {"A_整个流动性池": base, "D_动量20加增长30": base & sh(膜("掩膜_动量前20.parquet")) & sh(膜("掩膜_增长前30.parquet")),
     "D_动量30加增长40": base & sh(膜("掩膜_动量前30.parquet")) & sh(膜("掩膜_增长前40.parquet"))}
spy全 = data.load_benchmark("SPY")["close"].astype(float).dropna(); spy = spy全.reindex(idx).ffill()
挪 = lambda s: s.reindex(idx).ffill().shift(1).fillna(False).to_numpy(dtype=bool)
ma = spy.rolling(200, min_periods=200).mean()
me = spy全.groupby([spy全.index.year, spy全.index.month]).tail(1)
iso = spy全.index.isocalendar(); we = spy全.groupby([iso.year.values, iso.week.values]).tail(1); wma = we.rolling(30, min_periods=30).mean()
G = {"不挂开关": None, "行业版": 挪(((spy > ma) & (ma > ma.shift(20))).fillna(False)),
     "Faber月线": 挪((me > me.rolling(10, min_periods=10).mean()).astype(float).reindex(spy全.index).ffill().fillna(0).astype(bool)),
     "温斯坦周线": 挪(((we > wma) & (wma > wma.shift(1))).astype(float).reindex(spy全.index).ffill().fillna(0).astype(bool))}
reg0 = m.regime.copy() if getattr(m, "regime", None) is not None else None
res = {}
for un, u in U.items():
    for gn, g in G.items():
        for 清 in ((False,) if g is None else (True, False)):
            raw = copy.deepcopy(raw0); raw.setdefault("regime", {})["flatten_when_off"] = bool(清)
            m.universe = u; m.regime = (np.ones(len(idx), bool) if g is None else g)
            r = chain.run_chain(chain.ChainConfig.from_dict(raw), dev, data.PERF_START, data.PERF_END, m=m, total_return=True)
            L = r.ledger
            if len(L) and (set(L["symbol"].astype(str)) & hs): raise RuntimeError("留出池漏进来")
            eq = r.equity.reindex(perf).ffill(); ann = (eq.iloc[-1] / 1e6) ** (1 / yrs) - 1; dd = (eq / eq.cummax() - 1)
            水 = (eq < eq.cummax()).astype(int); 最长 = int(水.groupby((水 == 0).cumsum()).sum().max())
            yr = eq.groupby(eq.index.year).last(); yret = yr / yr.shift(1).fillna(1e6) - 1
            k = f"{un}|{gn}|{'关了就全卖' if 清 else ('只是不开新仓' if g is not None else '—')}"
            res[k] = {"每年赚pct": round(ann * 100, 2), "最惨跌pct": round(float(dd.min()) * 100, 2), "每跌一分赚几分": round(ann / abs(dd.min()), 3),
                      "最长多少天没创新高": 最长, "最差一年pct": round(float(yret.min()) * 100, 1), "赚钱的年数": f"{int((yret > 0).sum())}/{len(yret)}",
                      "笔数": int(len(L)), "平均仓位pct": round(float(r.exposure.reindex(perf).fillna(0).mean() * 100), 1),
                      "开关开着的天数pct": None if g is None else round(float(pd.Series(g, index=idx).reindex(perf).mean() * 100), 1),
                      "按年pct": {int(a): round(float(b) * 100, 1) for a, b in yret.items()}}
            print(k, {a: res[k][a] for a in ("每年赚pct", "最惨跌pct", "每跌一分赚几分", "最长多少天没创新高", "最差一年pct", "赚钱的年数", "笔数", "平均仓位pct")}, flush=True)
json.dump(res, io.open(os.path.join(J.OUT, "拿着加大盘开关.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
