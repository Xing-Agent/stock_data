#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""经验核对 · 第 8 条（2026-11-18）

原话（Gemini，v3全·335，针对 15 分钟线）：「多等这 3~4 根 K 线……你避开了 80% 以上的假动作和被插针扫损的风险」
这里先在美股日线上验同一个逻辑。它也直接决定《216》「真跌破 = 实体跌破 + 之后 3 根收盘都没回到平台内」里的「3 根」。

怎么数：
  事件 = 收盘第一次跌到支撑平台下沿之下至少 0.25×ATR（实体跌破）。平台下沿、ATR 都按跌破前一天定，之后不变。
  「假动作」= 跌破之后 N 个交易日内，有一天收盘回到平台下沿之上（N 原话没给 → 10 / 20 / 40 三档）。
  等 0 根：跌破当天就算数。等 1 / 2 / 3 / 4 根：之后连续这么多根收盘都没回到下沿之上，才算数。
  对每一种等法数：还剩多少事件；剩下的里面假动作占几成；跌破当天就算数的那些假动作，被「多等」挡掉了几成；
  代价：等完的时候，价格比跌破当天的收盘又低了多少（中位）。
范围：研发池、当天在流动性池中档里的票；2015–2025。只读面板，不跑引擎。
"""
import io, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE)
import numpy as np, pandas as pd
from 结构定义_1118 import atr14, 支撑平台

hold = json.load(io.open(os.path.join(ROOT, "probe/新策略_1106/holdout_newpool_1106.json"), encoding="utf-8"))
mk = pd.read_parquet(os.path.join(ROOT, "probe/流动性池_1114/流动性池掩膜_中.parquet"))
P = pd.read_parquet(os.path.join(ROOT, "probe/newpool_1106/ohlcv_panel_newpool.parquet"))
if not isinstance(P.columns, pd.MultiIndex):
    P.columns = pd.MultiIndex.from_tuples([eval(c) for c in P.columns])
syms = [s for s in hold["研发池名单"] if s in mk.columns and ("close", s) in P.columns and mk[s].any()]
bad = set(pd.read_csv(os.path.join(ROOT, "probe/含分红重出_1116/一天跳三倍_清单_1118.csv"))["代码"].astype(str))
syms = [s for s in syms if s not in bad]
idx = P.index
mkv = mk.reindex(index=idx).fillna(False)
ev = []
for s in syms:
    h, l, c = (P[(k, s)].to_numpy(dtype=float) for k in ("high", "low", "close"))
    if np.isfinite(c).sum() < 300:
        continue
    a = atr14(h, l, c)
    lo, hi, cnt = 支撑平台(l, c, a)
    inpool = mkv[s].to_numpy(dtype=bool)
    T = len(c)
    t = 60
    while t < T - 45:
        if inpool[t] and np.isfinite(lo[t]) and np.isfinite(a[t - 1]) and c[t] < lo[t] - 0.25 * a[t - 1] and c[t - 1] >= lo[t] - 0.25 * a[t - 1]:
            L, A = lo[t], a[t - 1]
            fut = c[t + 1:t + 45]
            if np.isfinite(fut).all():
                back = np.where(fut >= L)[0]
                first_back = int(back[0]) + 1 if len(back) else 999      # 第几根收回（1 = 跌破后第一根）
                ev.append((s, idx[t], float(c[t]), L, A, first_back,
                           [float(c[t + k] / c[t] - 1) for k in (1, 2, 3, 4)], float((c[t] - L) / A)))
                t += 5        # 同一只票 5 根之内的再次跌破不重复数
                continue
        t += 1
E = pd.DataFrame(ev, columns=["代码", "跌破日", "跌破收盘", "平台下沿", "ATR", "第几根收回", "之后1到4根相对跌破收盘", "跌破深度_ATR倍数"])
E.drop(columns=["之后1到4根相对跌破收盘"]).to_csv(os.path.join(HERE, "第8条_事件明细_1118.csv"), index=False, encoding="utf-8-sig")
res = {"原话": "多等这 3~4 根 K 线……你避开了 80% 以上的假动作和被插针扫损的风险（Gemini，针对 15 分钟线；这里是美股日线）",
       "范围": "研发池内流动性池中档，2015–2025，已拿掉价格一天跳三倍的可疑票", "票数": len(syms), "实体跌破事件数": int(len(E)), "各档": {}}
fb = E["第几根收回"].to_numpy()
drift = np.array(E["之后1到4根相对跌破收盘"].tolist())
for N in (10, 20, 40):
    假0 = (fb <= N)
    行 = {}
    for w in (0, 1, 2, 3, 4):
        留 = fb > w                      # 等了 w 根都没收回 → 算数
        假 = 留 & (fb <= w + N)          # 算数之后 N 根内又收回
        行[f"等{w}根"] = {"算数的事件数": int(留.sum()), "占全部跌破pct": round(float(留.mean() * 100), 1),
                        "其中假动作pct": round(float(假.sum() / max(留.sum(), 1) * 100), 1),
                        "跌破当天就算数的假动作里_被多等挡掉pct": round(float((假0 & ~留).sum() / max(假0.sum(), 1) * 100), 1) if w else 0.0,
                        "代价_等完时比跌破收盘又低了pct_中位": round(float(np.median(drift[留, w - 1]) * 100), 2) if w else 0.0}
    res["各档"][f"之后{N}个交易日内收回算假动作"] = 行
res["按年"] = {str(y): {"事件数": int((E["跌破日"].dt.year == y).sum()),
                       "等0根_20日内假动作pct": round(float((fb[(E["跌破日"].dt.year == y).to_numpy()] <= 20).mean() * 100), 1),
                       "3根内就收回pct": round(float((fb[(E["跌破日"].dt.year == y).to_numpy()] <= 3).mean() * 100), 1)}
             for y in sorted(E["跌破日"].dt.year.unique())}
io.open(os.path.join(HERE, "第8条_结果_1118.json"), "w", encoding="utf-8").write(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps({k: v for k, v in res.items() if k != "按年"}, ensure_ascii=False, indent=1))
print({k: (v["事件数"], v["等0根_20日内假动作pct"], v["3根内就收回pct"]) for k, v in res["按年"].items()})
