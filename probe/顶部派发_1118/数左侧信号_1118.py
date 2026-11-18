#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""顶部派发 · 先数次数，并回答「左侧到底早多少、值不值」（2026-11-18 · Lin 同意）

Lin 的要求：「跌破支撑」已经是右侧了，左侧应该是「差不多的时候」就走。所以把信号拆成三层，不混：
  纯左侧      两个前提 + 高位停留 + 量上派发 + 指标顶背离，**不看任何跌破**
  早一点的右侧  两个前提 + 收盘跌破 20 日线且 20 日线向下（Gemini 的「左侧减仓档」，其实已经带了跌破）
  右侧确认    两个前提 + 收盘跌破 50 日线 1.5% 以上（Gemini 的「右侧确认档」）
数全部是 Gemini 的推荐（《309》原文），不是原著；这里先用它的中间值，只数次数和提前量，不跑收益。

两个前提：过去 120 天最低到最高涨过 >= 35%；收盘离过去 252 天最高价 <= 15%。
高位停留：最近 60 天里，有 >= 20 天收盘在「离 252 天最高价 15% 以内」。
量上派发：最近 25 天个股派发日 >= 4 个，或者 20 天涨跌量比 < 0.85。
   个股派发日 = 当天跌幅 >= max(1%, 0.5×ATR/昨收)，且成交量 > 前一天、> 20 日均量的 1.1 倍；之后收盘比那天高出 5% 以上，那个派发日作废。
指标顶背离（不带跌破确认）：两个收盘价波峰（前后各 3 天最高，3 天后确认）相隔 10~60 天；第二峰 >= 第一峰的 99%；
   第一峰 RSI14 >= 70；第二峰 RSI14 比第一峰低 5 以上。信号记在第二峰确认那天。
没照做的两处：高位停留里「区间成交量 >= 前一波上涨成交量的 75%」没加；「上冲回落 / 放量滞涨」没当成跌破 20 日线的前置。
回答三个数：左侧比右侧早几天；早的这几天价格高多少；左侧之后 60 天内真跌破的占几成、没跌破的后来怎样。
范围：研发池内流动性池中档，2015–2025，已拿掉价格一天跳三倍的可疑票。只读面板。
"""
import io, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
import numpy as np, pandas as pd

hold = json.load(io.open(os.path.join(ROOT, "probe/新策略_1106/holdout_newpool_1106.json"), encoding="utf-8"))
mk = pd.read_parquet(os.path.join(ROOT, "probe/流动性池_1114/流动性池掩膜_中.parquet"))
P = pd.read_parquet(os.path.join(ROOT, "probe/newpool_1106/ohlcv_panel_newpool.parquet"))
if not isinstance(P.columns, pd.MultiIndex):
    P.columns = pd.MultiIndex.from_tuples([eval(c) for c in P.columns])
bad = set(pd.read_csv(os.path.join(ROOT, "probe/含分红重出_1116/一天跳三倍_清单_1118.csv"))["代码"].astype(str))
syms = [s for s in hold["研发池名单"] if s in mk.columns and ("close", s) in P.columns and mk[s].any() and s not in bad]
H, L, C, V = (P[k][syms].astype(float) for k in ("high", "low", "close", "volume"))
idx = C.index
pool = mk.reindex(index=idx, columns=syms).fillna(False).to_numpy(dtype=bool)

pc = C.shift(1)
tr = pd.concat([H - L, (H - pc).abs(), (L - pc).abs()]).groupby(level=0).max().reindex(idx)
atr = tr.rolling(14, min_periods=14).mean()
hi252 = H.rolling(252, min_periods=120).max()
前提A = (H.rolling(120, min_periods=60).max() / L.rolling(120, min_periods=60).min() - 1) >= 0.35
近高 = C >= 0.85 * hi252
前提 = (前提A & 近高).to_numpy()
停留 = (近高.rolling(60, min_periods=20).sum() >= 20).to_numpy()
ret = C / pc - 1
vol20 = V.rolling(20, min_periods=20).mean()
dd = ((ret <= -np.maximum(0.01, 0.5 * atr / pc)) & (V > V.shift(1)) & (V > 1.1 * vol20)).to_numpy()
cv = C.to_numpy()
T, N = cv.shape
ddcnt = np.zeros((T, N), dtype=np.int16)
for k in range(0, 25):                        # 第 t-k 天是派发日，且之后没被「高出 5%」作废
    d = np.zeros((T, N), dtype=bool); d[k:] = dd[:T - k]
    ck = np.full((T, N), np.nan); ck[k:] = cv[:T - k]
    ddcnt += (d & (cv <= 1.05 * ck)).astype(np.int16)
up = (V * (ret > 0)).rolling(20, min_periods=20).sum(); dn = (V * (ret < 0)).rolling(20, min_periods=20).sum()
量 = ((ddcnt >= 4) | ((up / dn) < 0.85).to_numpy())
dlt = C.diff(); g = dlt.clip(lower=0).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean(); ls = (-dlt.clip(upper=0)).ewm(alpha=1 / 14, adjust=False, min_periods=14).mean()
rsi = (100 - 100 / (1 + g / ls)).to_numpy()
背离 = np.zeros((T, N), dtype=bool)
pk = (C == C.rolling(7, center=True, min_periods=7).max()).to_numpy()
for j in range(N):
    ps = np.where(pk[:, j])[0]
    for b in range(1, len(ps)):
        t1, t2 = ps[b - 1], ps[b]
        if 10 <= t2 - t1 <= 60 and t2 + 3 < T and cv[t2, j] >= 0.99 * cv[t1, j] and rsi[t1, j] >= 70 and rsi[t2, j] <= rsi[t1, j] - 5:
            背离[t2 + 3:min(T, t2 + 3 + 10), j] = True      # 确认后 10 天内都算「背离还在」
sma20 = C.rolling(20, min_periods=20).mean(); sma50 = C.rolling(50, min_periods=50).mean()
破20 = ((C < sma20) & (sma20 < sma20.shift(5))).to_numpy()
破50 = (C < sma50 * 0.985).to_numpy()

sig = {"纯左侧_不看跌破": 前提 & 停留 & 量 & 背离 & pool,
       "只要两个前提加背离": 前提 & 背离 & pool,
       "只要两个前提加量": 前提 & 量 & pool,
       "早一点的右侧_跌破20日线": 前提 & 破20 & pool,
       "右侧确认_跌破50日线1.5pct": 前提 & 破50 & pool}


def 首发(m, 冷静=20):
    """同一只票 `冷静` 天内只算第一次。返回 (日, 票) 下标。"""
    out = []
    for j in range(N):
        ts = np.where(m[:, j])[0]; last = -10 ** 9
        for t in ts:
            if t - last > 冷静:
                out.append((t, j))
            last = t
    return out

per = (idx >= pd.Timestamp("2015-01-01"))
res = {"范围": "研发池内流动性池中档，2015–2025", "票数": N, "对比": "只看形状的那版（双顶 / 三重顶 / 头肩顶）同一范围 11 年确认了约 5.76 万次", "各层": {}}
ev = {}
for k, m in sig.items():
    m = m & per[:, None]
    e = 首发(m); ev[k] = e
    res["各层"][k] = {"信号票日数": int(m.sum()), "次数_同一只票20天内只算一次": len(e), "涉及票数": len({j for _, j in e}),
                    "是形状版次数的pct": round(len(e) / 57636 * 100, 1)}
右 = sig["右侧确认_跌破50日线1.5pct"]
for 左名 in ("纯左侧_不看跌破", "只要两个前提加背离", "早一点的右侧_跌破20日线"):
    lead, 高出, 没破后60天, 破了后60天 = [], [], [], []
    破 = 0; n = 0
    for t, j in ev[左名]:
        if t + 61 >= T or not np.isfinite(cv[t, j]):
            continue
        n += 1
        w = np.where(右[t + 1:t + 61, j])[0]
        r60 = cv[t + 60, j] / cv[t, j] - 1
        if len(w):
            破 += 1; d = int(w[0]) + 1
            lead.append(d); 高出.append(cv[t, j] / cv[t + d, j] - 1); 破了后60天.append(r60)
        else:
            没破后60天.append(r60)
    res["各层"][左名]["提前量"] = {
        "能往后看 60 天的次数": n,
        "之后 60 天内真的跌破 50 日线的pct": round(破 / max(n, 1) * 100, 1),
        "比右侧确认早几天_中位": float(np.median(lead)) if lead else None,
        "早走比等到跌破多卖到的价格pct_中位": round(float(np.median(高出)) * 100, 1) if 高出 else None,
        "没跌破的那些_之后60天涨跌pct_中位": round(float(np.nanmedian(没破后60天)) * 100, 1) if 没破后60天 else None,
        "没跌破的那些_之后60天涨超10pct的占比": round(float((np.array(没破后60天) > 0.10).mean()) * 100, 1) if 没破后60天 else None,
        "全部左侧信号_之后60天涨跌pct_中位": round(float(np.nanmedian(破了后60天 + 没破后60天)) * 100, 1)}
# 对照：池内任意一天之后 60 天的涨跌中位
rr = (C.shift(-60) / C - 1).to_numpy()
res["对照_池内任意一天之后60天涨跌pct_中位"] = round(float(np.nanmedian(rr[pool & per[:, None]])) * 100, 1)
res["对照_满足两个前提的任意一天之后60天涨跌pct_中位"] = round(float(np.nanmedian(rr[前提 & pool & per[:, None]])) * 100, 1)
# 对照：满足两个前提、当天还没跌破 50 日线的任意一天，之后 60 天内跌破 50 日线的比例（每只票每 20 天取一天，免得同一段重复数）
base = 首发(前提 & pool & per[:, None] & ~右, 冷静=20)
nb = pb = 0
for t, j in base:
    if t + 61 < T:
        nb += 1; pb += int(右[t + 1:t + 61, j].any())
res["对照_满足两个前提且还没跌破的任意一天_之后60天内跌破50日线的pct"] = round(pb / max(nb, 1) * 100, 1)
res["对照_上面这个的样本数"] = nb
io.open(os.path.join(HERE, "数左侧信号_结果_1118.json"), "w", encoding="utf-8").write(json.dumps(res, ensure_ascii=False, indent=1))
print(json.dumps(res, ensure_ascii=False, indent=1))
