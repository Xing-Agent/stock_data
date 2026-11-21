# -*- coding: utf-8 -*-
"""持有多单、日线转跌后怎么减:五种做法并排 · 只用日线 · 引擎外脚本
「转跌」照《341 Gemini 原文》B 组规则 6.1;第⑤种照规则 6.2 / 6.3 / 7 / 8(小时线才能判的两处从略,见文末说明)。
只比「卖得好不好」,不管之后什么时候买回来。
"""
import os, io, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
P1 = os.path.join(ROOT, "probe/波段做空_1121/圣杯空头版_日线_1121.py")
B = {"__file__": P1}; exec(compile(io.open(P1, encoding="utf-8").read().replace("\nmain()\n", "\n"), "b1", "exec"), B)
load, ind, 组, 段 = B["load"], B["ind"], B["组"], B["段"]
SYMS = 组["指数"] + 组["行业"]

def 事件(x):
    c = x.c
    ema_break = (c < x.ema20 - 0.3 * x.atr) & (x.v >= 1.2 * x.vma20)
    swing_break = c < x.l.shift(1).rolling(10).min()
    持有中 = (c.shift(1) > x.ema20.shift(1)) & (c.shift(1) > x.sma50.shift(1))      # 前一天还在 20、50 日线上方,算「手里有多单」
    ev = np.where(((ema_break | swing_break) & 持有中).values)[0]; out = []; last = -99
    for t in ev:
        if t < 220 or t - last < 20 or t + 61 >= len(x): continue
        out.append(t); last = t
    return out

def 走(x, t, 先卖, 限价fn, 硬底, 最多等=None, 别等了=None, H=60):
    """先在 t 日收盘卖 先卖;剩下的:某天最高碰到限价就卖(开盘就高过按开盘),最低碰到硬底就全卖(跳空按开盘),
    同一天两个都碰算先碰硬底。返回 H 天内的卖出均价(没卖掉的部分按第 H 天收盘记)和各部分怎么走的。"""
    P = x.c.iloc[t]; got = 先卖 * P; left = 1.0 - 先卖; how = "先卖" if 先卖 >= 1 else None
    j = t + 1
    while left > 1e-9 and j <= t + H:
        o, h, l, c = x.o.iloc[j], x.h.iloc[j], x.l.iloc[j], x.c.iloc[j]
        lim = 限价fn(j) if 限价fn else None
        if 硬底 is not None and o <= 硬底: got += left * o; left = 0; how = "破底(跳空)"; break
        if 硬底 is not None and l <= 硬底: got += left * 硬底; left = 0; how = "破底"; break
        if lim is not None and h >= lim: got += left * max(o, lim); left = 0; how = "等到反弹"; break
        if 别等了 and 别等了(j): got += left * c; left = 0; how = "别等了信号"; break
        if 最多等 and j - t >= 最多等: got += left * c; left = 0; how = f"满{最多等}天"; break
        j += 1
    if left > 1e-9: got += left * x.c.iloc[t + H]; how = "到期还拿着"
    return got / P - 1, how or "先卖"

def 一个事件(x, spy, t):
    P, atr = x.c.iloc[t], x.atr.iloc[t]
    low10 = x.l.iloc[t - 9:t + 1].min()
    ema = lambda j: x.ema20.iloc[j - 1]
    r = {"日": x.index[t]}
    for H in (20, 60):
        r[f"拿着不动_{H}"] = x.c.iloc[t + H] / P - 1
        r[f"之后最深_{H}"] = x.l.iloc[t + 1:t + H + 1].min() / P - 1
        r[f"当天全卖_{H}"] = 0.0
        r[f"减仓三步_{H}"], r[f"减仓三步怎么走_{H}"] = 走(x, t, 0.5, ema, low10 - 0.5 * atr, H=H)
        r[f"全等反弹_{H}"], r[f"全等反弹怎么走_{H}"] = 走(x, t, 0.0, ema, low10 - 0.5 * atr, H=H)
        # ⑤ B 组
        ext = (x.ema20.iloc[t] - P) / atr
        trim, mult = (0.70, 0.25) if ext <= 1.0 else ((0.50, 0.20) if ext <= 2.0 else ((0.30 if x.rsi.iloc[t] < 30 else 0.50), 0.15))
        pk = t - 19 + int(np.argmax(x.h.values[t - 19:t + 1])); peak = x.h.iloc[pk]
        tp = (x.h + x.l + x.c) / 3
        avwap = (tp.iloc[pk:t + 1] * x.v.iloc[pk:t + 1]).sum() / x.v.iloc[pk:t + 1].sum()
        cand = [avwap, x.l.iloc[t] + 0.5 * (peak - x.l.iloc[t])] + ([x.ema20.iloc[t]] if x.ema20.iloc[t] >= x.sma50.iloc[t] else [])
        v = sorted(z for z in cand if z >= P + 0.35 * atr)
        zone = (v[0] + v[1]) / 2 if len(v) >= 2 and v[1] - v[0] <= 0.5 * atr else (v[0] if v else P + 0.5 * atr)
        lim = zone - 0.2 * atr; stop = x.l.iloc[t] - mult * atr
        def abort(j, x=x, spy=spy):
            rng = x.h.iloc[j] - x.l.iloc[j]
            a82 = x.c.iloc[j] < x.l.iloc[j - 1] and (x.c.iloc[j] - x.l.iloc[j]) / max(rng, 1e-6) <= 0.15 and rng >= 1.2 * x.atr.iloc[j]
            d = x.index[j]
            a84 = d in spy.index and spy.c.loc[d] < spy.ema20.loc[d] and (spy.c.shift(1).loc[d] - spy.c.loc[d]) >= 1.5 * spy.atr.loc[d]
            return a82 or a84
        r[f"B组那套_{H}"], r[f"B组怎么走_{H}"] = 走(x, t, trim, lambda j, lim=lim: lim, stop, 最多等=5, 别等了=abort, H=H)
        r["B组先卖"] = trim
    return r

def main():
    spy = ind(load("SPY")); rows = []; base = []
    for s in SYMS:
        x = ind(load(s))
        for t in 事件(x):
            r = 一个事件(x, spy, t); r["票"] = s; rows.append(r)
        for H in (20, 60):
            f = x.c.shift(-H) / x.c - 1
            base.append(pd.DataFrame({"日": x.index, "H": H, "r": f.values, "票": s}).dropna())
    df = pd.DataFrame(rows); bs = pd.concat(base)
    df.to_csv(os.path.join(HERE, "减仓五种_逐事件.csv"), index=False)
    名 = ["拿着不动", "当天全卖", "减仓三步", "全等反弹", "B组那套"]; res = {}
    for pn, (a, b) in 段.items():
        m = df[(df["日"] >= a) & (df["日"] <= b)]
        for H in (20, 60):
            k = {"转跌次数": int(len(m))}
            bb = bs[(bs["日"] >= a) & (bs["日"] <= b) & (bs["H"] == H)]["r"]
            k["平时任意一天之后的涨跌_平均pct"] = round(100 * bb.mean(), 2)
            k["转跌后最深跌到_中位pct"] = round(100 * m[f"之后最深_{H}"].median(), 2)
            for n in 名:
                v = m[f"{n}_{H}"]; hold = m[f"拿着不动_{H}"]
                k[n] = {"比转跌当天收盘_平均pct": round(100 * v.mean(), 2), "中位pct": round(100 * v.median(), 2),
                        "最差一成_pct": round(100 * v.quantile(0.1), 2), "最差一次_pct": round(100 * v.min(), 2),
                        "比拿着不动好的次数占比pct": round(100 * (v > hold).mean(), 1) if n != "拿着不动" else None}
            for n, c in [("减仓三步", "减仓三步怎么走"), ("全等反弹", "全等反弹怎么走"), ("B组那套", "B组怎么走")]:
                k[n]["剩下那部分怎么走的"] = m[f"{c}_{H}"].value_counts().to_dict()
            k["B组先卖比例分布"] = m["B组先卖"].value_counts().to_dict()
            res[f"{pn}|{H}天"] = k
        # 分年:拿着不动 vs 当天全卖(60 天)
        res[f"{pn}|分年|转跌后60天拿着不动的平均pct"] = {int(y): [int(len(v)), round(100 * v["拿着不动_60"].mean(), 1)] for y, v in m.groupby(m["日"].dt.year)}
    json.dump(res, io.open(os.path.join(HERE, "减仓五种_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    for k, v in res.items():
        print("==", k)
        if "分年" in k: print(v); continue
        print({a: b for a, b in v.items() if not isinstance(b, dict)})
        for n in 名: print("  ", n, v[n])

main()
