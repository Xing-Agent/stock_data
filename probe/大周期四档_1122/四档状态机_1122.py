# -*- coding: utf-8 -*-
"""大周期四档状态机 · 第一版（《395 拍板》周 1；规则来自 Gemini《393》回答「第一步」那张表）· BTC、ETH 日线 · 引擎外
每天只给一档，只用当天已经收盘的数据，历史不回头改。
四档的原始条件（Gemini 的写法，数都是它的推荐、没有出处）：
  涨势：日线最近两个已确认的摆动高点、低点都在抬高；收盘 > 50 日 EMA > 200 日 EMA；离 180 天最高点 < 15%
  见顶：离 365 天最高点 < 20%；最近一个已确认高点没能超过前一个高点的 1.015 倍；收盘跌破 50 日 EMA 但在 200 日 EMA 上
  跌势：日线高点、低点都在降低；收盘 < 50 日 EMA 且 50 日 EMA 向下；已跌破顶部那个箱体的下沿
  筑底：从周期最高点跌了 > 60%；横了 >= 12 周；站回 50 日 EMA 并出现第一个更高的低点
  回退：筑底 / 见顶期，实体跌破关键位、之后反弹不到 0.382 → 直接切回跌势
我补的（Gemini 和拍板没写死的；都只跑了这一个点）：
  - 摆动点：左右各 3 天（Gemini 给的），要晚 3 天才确认
  - 「顶部箱体下沿」= 进入「见顶」那天起到现在的最低收盘价；没经过「见顶」直接转弱的，用最近 90 天里离一年高点 20% 以内那些天的最低价
  - 「跌破」= 收盘低于下沿 2% 以上（Gemini 代码里的数）
  - 「周期最高点」= 过去 4 年（1460 天）的最高价
  - 「横了 12 周」= 过去 84 天的最高最低相差 <= 45%，且 84 天前到现在净涨跌在 ±25% 以内
  - 「关键位」= 最近 60 天里已确认的最低摆动低点；「反弹不到 0.382」= 跌破后 5 天内的最高价没回到（跌破前那个摆动高点到最低点）的 0.382
  - 状态只在下面这些路径上切换：涨势→见顶；见顶→跌势 / 涨势（收盘创 365 天新高）；跌势→筑底 / 涨势；筑底→涨势 / 跌势；
    另外加一条「涨势→跌势」的直通路（没走见顶就满足跌势全部条件），不然 2021 年 5 月那种急跌会一直标成涨势
  - 没有用持仓量（还没有数据）、周线 RSI 背离、资金费率
"""
import os, sys, glob, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))

def 日线(sym):
    fs = sorted(glob.glob(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/币_小时线_Coinbase/*.parquet")))
    d = pd.concat([pd.read_parquet(f) for f in fs]); d = d[d.symbol == sym]; d["t"] = pd.to_datetime(d.time_utc, utc=True); d = d.set_index("t").sort_index()
    D = d.resample("1D").agg({"open_adj": "first", "high_adj": "max", "low_adj": "min", "close_adj": "last"}).dropna(); D.columns = ["open", "high", "low", "close"]
    D.index = D.index.tz_localize(None); return D

def 跑(D, k=3):
    o, h, l, c = D.open.values, D.high.values, D.low.values, D.close.values; n = len(D)
    e50 = D.close.ewm(span=50, adjust=False).mean().values; e200 = D.close.ewm(span=200, adjust=False).mean().values
    h180 = D.high.rolling(180, min_periods=60).max().values; h365 = D.high.rolling(365, min_periods=120).max().values
    hcyc = D.high.rolling(1460, min_periods=200).max().values
    h84 = D.high.rolling(84).max().values; l84 = D.low.rolling(84).min().values
    SH, SL = [], []      # 已确认的摆动点 (确认日下标, 价格)
    st = ["历史不够"] * n; cur = None; box_low = np.nan; 原因 = [""] * n; pend = None
    for i in range(n):
        j = i - k
        if j >= k:
            w = slice(j - k, j + k + 1)
            if h[j] == h[w].max(): SH.append((i, h[j]))
            if l[j] == l[w].min(): SL.append((i, l[j]))
        if i < 220 or len(SH) < 2 or len(SL) < 2: continue
        hh = SH[-1][1] > SH[-2][1]; hl = SL[-1][1] > SL[-2][1]
        up = hh and hl and c[i] > e50[i] > e200[i] and c[i] > 0.85 * h180[i]
        top = c[i] > 0.80 * h365[i] and SH[-1][1] <= SH[-2][1] * 1.015 and c[i] < e50[i] and c[i] > e200[i]
        dn结构 = (not hh) and (not hl) and c[i] < e50[i] and e50[i] < e50[i - 5]
        dd = c[i] / hcyc[i] - 1
        横 = (h84[i] / l84[i] - 1) <= 0.45 and abs(c[i] / c[i - 84] - 1) <= 0.25
        bot = dd < -0.60 and 横 and c[i] > e50[i] and hl
        new = cur; why = ""
        if cur is None:
            new = "涨势" if c[i] > e200[i] else "跌势"; why = "起始：看在 200 日线上还是下"
        elif cur == "涨势":
            if top: new = "见顶"; why = "离一年高点两成以内、新高点没超过前高、跌破 50 日线"; box_low = c[i]
            elif dn结构 and c[i] < e200[i]:
                near = [l[t] for t in range(max(0, i - 90), i) if c[t] > 0.80 * h365[t]]
                if near and c[i] < min(near) * 0.98: new = "跌势"; why = "没经过见顶，直接走成顶底降低并跌破高位区的最低点"
        elif cur == "见顶":
            box_low = min(box_low, c[i - 1]) if not np.isnan(box_low) else c[i - 1]
            if c[i] >= h365[i - 1]: new = "涨势"; why = "收盘创一年新高，见顶不成立"
            elif c[i] < box_low * 0.98 and c[i] < e50[i]: new = "跌势"; why = "跌破顶部箱体下沿 2% 以上"
        elif cur == "跌势":
            if bot: new = "筑底"; why = "从周期高点跌超六成、横了 12 周、站回 50 日线、低点抬高"
            elif up: new = "涨势"; why = "顶底抬高、站上 50 和 200 日线（没到「跌六成」那一档，直接转涨）"
        elif cur == "筑底":
            if up: new = "涨势"; why = "顶底抬高、站上 50 和 200 日线"
            else:
                rec = [p for (ci, p) in SL if ci >= i - 60]
                if pend is None and rec and c[i] < min(rec) and c[i] < o[i]:
                    pend = {"i": i, "lvl": min(rec), "top": SH[-1][1], "low": l[i]}
                if pend is not None:
                    pend["low"] = min(pend["low"], l[i])
                    if i - pend["i"] >= 5:
                        reb = (h[pend["i"] + 1:i + 1].max() - pend["low"]) / max(pend["top"] - pend["low"], 1e-9)
                        if reb < 0.382 and c[i] < pend["lvl"]: new = "跌势"; why = "跌破关键位后 5 天反弹不到 0.382，切回跌势"
                        pend = None
        if new != cur: 原因[i] = why; pend = None if new != "筑底" else pend
        cur = new; st[i] = cur
    return pd.DataFrame({"close": c, "档": st, "切换原因": 原因}, index=D.index)

if __name__ == "__main__":
    for sym in ("BTC", "ETH"):
        D = 日线(sym); R = 跑(D); R.to_csv(os.path.join(HERE, "out", f"{sym}_每天的档.csv"))
        sw = R[R["切换原因"] != ""]; sw.to_csv(os.path.join(HERE, "out", f"{sym}_切换清单.csv"))
        print(sym, R["档"].value_counts().to_dict()); print(sw[["close", "档", "切换原因"]].to_string()[:6000])
