# -*- coding: utf-8 -*-
"""日内区间做空第二版 · 骨架版（《380》拍板【区1】）· BTC/ETH 永续 · 引擎外
骨架四样：① 摆动点画箱子 ② 箱顶碰大周期阻力 ③ 扳机=第二次冲不过前高 ④ 止损=max(H1,H2)+0.12×ATR(1H)
这一版先出：骨架、骨架去掉②、三种扳机并排（都用摆动点箱子），扣成本前 / 后都报。「逐条加回」「三种箱子」「挂单价」在下一轮。
拍板没写死、我补的（都要在报告里标出）：
  - 「冲到箱顶」= 15 分钟最高价 ≥ 箱顶 − 0.25×ATR(1H)
  - 「第二次冲」= 从 L1 反弹回 H1−L1 的一半以上才算一次冲；H2 那根离 H1 在 4~16 根 15 分钟线之间；跌破 L1 的阴线最晚在 H1 后 24 根内
  - 「上下交替检验」= 用到的两个高点之间至少有一个用到的低点（或反过来），而且从最早那个摆动点到现在，没有 1 小时收盘跑出 箱顶+0.5×ATR / 箱底−0.5×ATR
  - 出场沿用第一版：中轴平一半、止损推成本；第二目标 = 箱底 + 0.15×箱高；到中轴前最多 16 根、之后最多 64 根
  - 扳机乙「连续上影」= 连着 2 根 15 分钟线，最高价在箱顶 ±0.25×ATR 内、上影 ≥ 振幅一半、收在箱顶下
  - 扳机丙「两步确认」= 一根冲破箱顶又收回（不看量），之后 1~3 根内有收盘跌破那根最低点
"""
import os, sys, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("v1", os.path.join(HERE, "日内区间_币_1122.py")); v1 = importlib.util.module_from_spec(sp); sp.loader.exec_module(v1)
START = "2020-01-01"

def swings(x, k=3, kind="h"):
    n = len(x); out = np.zeros(n, bool)
    for i in range(k, n - k):
        w = x[i - k:i + k + 1]
        if kind == "h" and x[i] == w.max() and (w == x[i]).sum() == 1: out[i] = True
        if kind == "l" and x[i] == w.min() and (w == x[i]).sum() == 1: out[i] = True
    return out

def prep(sym, anchor="最近", box="摆动点"):
    d, fr = v1.load(sym)
    H1 = d.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    a1, _ = v1.atr_adx(H1)
    hi, lo, cl, A = H1.high.values, H1.low.values, H1.close.values, a1.values
    sh, sl = swings(hi, 3, "h"), swings(lo, 3, "l"); n = len(H1)
    top = np.full(n, np.nan); bot = np.full(n, np.nan)
    for t in range(100, n):
        if np.isnan(A[t]): continue
        lo_i = t - 96; ok_end = t - 3                      # 摆动点要右边 3 根走完才确认
        hs = [i for i in range(ok_end, lo_i, -1) if sh[i]]; ls = [i for i in range(ok_end, lo_i, -1) if sl[i]]
        if len(hs) < 2 or len(ls) < 2: continue
        def cluster(ix, px, hi_side=None):
            # 以窗口里最高的摆动高点（最低的摆动低点）为准去找同一水平的其他点；先试过以「最近一个」为准，箱子外面常常还有更高的高点，九成被「没跑出去」砍掉
            base = ix[0] if anchor == "最近" else (max(ix, key=lambda i: px[i]) if hi_side else min(ix, key=lambda i: px[i])); use = [base]
            for i in ix:
                if i == base: continue
                if abs(px[i] - px[base]) <= 0.35 * A[t] and all(abs(i - j) >= 6 for j in use): use.append(i)
            return use
        uh, ul = cluster(hs, hi, True), cluster(ls, lo, False)
        if len(uh) < 2 or len(ul) < 2: continue
        tp = hi[uh].mean(); bt = lo[ul].mean()
        if tp - bt <= A[t]: continue
        first = min(min(uh), min(ul))
        if t - first < 24: continue
        if not (any(min(uh) < j < max(uh) for j in ul) or any(min(ul) < j < max(ul) for j in uh)): continue
        seg = cl[first:t + 1]
        if (seg > tp + 0.5 * A[t]).any() or (seg < bt - 0.5 * A[t]).any(): continue
        top[t], bot[t] = tp, bt
    F = pd.DataFrame({"top": top, "bot": bot, "atr1": A}, index=H1.index)
    # 大周期阻力
    D1 = d.resample("1D").agg({"high": "max", "low": "min", "close": "last"}).dropna()
    pdh = D1.high.shift(1); p3h = D1.high.rolling(3).max().shift(1)
    ma = {k: D1.close.rolling(k).mean().shift(1) for k in (20, 50, 200)}
    H4 = H1.resample("4h").agg({"high": "max"}).dropna(); h4 = H4.high.values; s4 = swings(h4, 3, "h")
    R = pd.DataFrame({"pdh": pdh, "p3h": p3h, "m20": ma[20], "m50": ma[50], "m200": ma[200]})
    R.index = R.index                                        # 当天 0 点起可用（都是 shift 过的）
    Rh = R.reindex(H1.index, method="ffill")
    res_ok = np.zeros(n, bool); h4t = H4.index
    for t in range(n):
        if np.isnan(top[t]): continue
        tp, a = top[t], A[t]; lv = [Rh.iloc[t][c] for c in ("pdh", "p3h", "m20", "m50", "m200")]
        j = h4t.searchsorted(H1.index[t]) - 1 - 3            # 已确认的 4 小时摆动高点
        if j > 0: lv += [h4[i] for i in range(max(0, j - 60), j + 1) if s4[i]]
        res_ok[t] = any((not np.isnan(x)) and abs(x - tp) <= 0.5 * a for x in lv)
    F["res"] = res_ok
    if box == "前一天":                                   # 箱子三：前一天的最高 / 最低（每天都有）；箱顶本身就是大周期阻力
        pdl = D1.low.shift(1).reindex(H1.index, method="ffill").values; pdh_ = Rh["pdh"].values
        F["top"] = pdh_; F["bot"] = pdl; F["res"] = True
        F = F.shift(0)
    F.index = F.index + pd.Timedelta(hours=1)
    d = d.join(F.reindex(d.index, method="ffill"))
    _, adxd = v1.atr_adx(D1.assign(open=D1.close)); c = D1.close
    s20, s50, s200 = c.rolling(20).mean(), c.rolling(50).mean(), c.rolling(200).mean()
    tier = pd.Series("其他", index=D1.index)
    tier[(c < s200) & (s200 < s200.shift(5))] = "200日线下且向下"; tier[(c < s50) & (c > s200)] = "50日线下200日线上"
    tier[(c > s20) & (s20 > s50) & (adxd > 28)] = "日线强多头"; tier[s200.isna()] = "历史不够"
    tier.index = tier.index + pd.Timedelta(days=1); d["tier"] = tier.reindex(d.index, method="ffill").values
    d["fr_now"] = fr.reindex(d.index).values
    return d[d.index >= START]

def run(d, trig="甲", need_res=True, ts1=16, ts2=64, fee=0.0005):
    o, h, l, c = (d[x].values for x in ("open", "high", "low", "close"))
    top, bot, A, res, tier, frn = d.top.values, d.bot.values, d.atr1.values, d.res.fillna(False).values.astype(bool), d.tier.values, d.fr_now.values
    ts = d.index; T = []; pos = None; st = 0; H1 = L1 = H2 = np.nan; i1 = 0; bounced = False; cnt = {"有箱子的根数": 0, "箱顶碰阻力的根数": 0, "出信号": 0}
    pier = None; wick_run = 0
    for i in range(60, len(c)):
        if pos is not None:
            p = pos; p["n"] += 1; done = False
            if not np.isnan(frn[i]): p["fund"] += frn[i] * o[i] * p["rem"] / p["R"]
            S = p["stop"]
            def leg(px, frac):
                p["pnl"] += frac * (p["E"] - px) / p["R"]; p["cost"] += frac * fee * (p["E"] + px) / p["R"]; p["rem"] -= frac
            if o[i] >= S: leg(o[i], p["rem"]); done = True; p["why"] = "止损" if not p["tp1"] else "保本"
            elif h[i] >= S:
                leg(S * (1 + max(0.0002, 0.075 * (h[i] - l[i]) / c[i])), p["rem"]); done = True; p["why"] = "止损" if not p["tp1"] else "保本"
            else:
                if not p["tp1"] and l[i] <= p["t1"]: leg(p["t1"], 0.5); p["tp1"] = True; p["stop"] = p["E"]; p["n1"] = 0
                if p["tp1"] and l[i] <= p["t2"]: leg(p["t2"], p["rem"]); done = True; p["why"] = "第二目标"
                elif p["tp1"]:
                    p["n1"] += 1
                    if p["n1"] >= ts2: leg(c[i], p["rem"]); done = True; p["why"] = "到时间(过中轴后)"
                elif p["n"] >= ts1: leg(c[i], p["rem"]); done = True; p["why"] = "到时间(没到中轴)"
            if done:
                T.append({"进": str(ts[p["i"]]), "年": ts[p["i"]].year, "档": p["tier"], "毛R": p["pnl"], "成本R": p["cost"], "净R": p["pnl"] - p["cost"] + p["fund"], "怎么出": p["why"], "止损距pct": p["R"] / p["E"] * 100, "碰阻力": p["res"]})
                pos = None; st = 0; pier = None; wick_run = 0
            continue
        tp, bt, a = top[i], bot[i], A[i]
        if np.isnan(tp) or np.isnan(a): st = 0; pier = None; wick_run = 0; continue
        cnt["有箱子的根数"] += 1
        if res[i]: cnt["箱顶碰阻力的根数"] += 1
        if need_res and not res[i]: st = 0; pier = None; wick_run = 0; continue
        mid = (tp + bt) / 2; E = stop = None
        if trig == "甲":
            if st == 0:
                if h[i] >= tp - 0.25 * a: H1 = h[i]; i1 = i; L1 = l[i]; st = 1; bounced = False; H2 = -np.inf
            else:
                if h[i] > H1: H1 = h[i]; i1 = i; L1 = l[i]; bounced = False; H2 = -np.inf
                elif i - i1 > 24: st = 0
                else:
                    if not bounced:
                        L1 = min(L1, l[i])
                        if H1 - L1 >= 0.35 * a and h[i] >= L1 + 0.5 * (H1 - L1) and l[i] > L1: bounced = True; H2 = h[i]; i2 = i
                    else:
                        if h[i] > H2 and c[i] >= L1: H2 = h[i]; i2 = i
                        if c[i] < L1 and c[i] < o[i]:
                            if 4 <= i2 - i1 <= 16: E = c[i]; stop = max(H1, H2) + 0.12 * a
                            st = 0
        elif trig == "乙":
            rng = h[i] - l[i]
            okb = (tp - 0.25 * a <= h[i] <= tp + 0.25 * a) and rng > 0 and (h[i] - max(o[i], c[i])) >= 0.5 * rng and c[i] < tp
            wick_run = wick_run + 1 if okb else 0
            if wick_run >= 2: E = c[i]; stop = tp + 0.25 * a; wick_run = 0
        else:
            if pier is not None:
                pier["k"] += 1; pier["hi"] = max(pier["hi"], h[i])
                if c[i] < pier["lo"]: E = c[i]; stop = pier["hi"] + 0.12 * a; pier = None
                elif pier["k"] >= 3: pier = None
            if E is None and pier is None and h[i] > tp and c[i] < tp: pier = {"lo": l[i], "hi": h[i], "k": 0}
        if E is None: continue
        R = stop - E
        if R <= 0 or E <= mid: continue
        cnt["出信号"] += 1
        pos = {"i": i, "E": E, "stop": stop, "R": R, "t1": mid, "t2": bt + 0.15 * (tp - bt), "tp1": False, "n": 0, "n1": 0, "rem": 1.0, "pnl": 0.0, "cost": 0.0, "fund": 0.0, "why": "", "tier": tier[i], "res": bool(res[i])}
    return pd.DataFrame(T), cnt

def S(t):
    if len(t) == 0: return {"笔数": 0}
    r = t["净R"]; g = t["毛R"]; w = r[r > 0].sum(); ls = -r[r < 0].sum(); eq = r.cumsum()
    return {"笔数": int(len(t)), "每笔毛R": round(g.mean(), 3), "每笔净R": round(r.mean(), 3), "毛胜率pct": round((g > 0).mean() * 100, 1), "净胜率pct": round((r > 0).mean() * 100, 1),
            "利润因子": round(w / ls, 2) if ls > 0 else None, "累计净R": round(r.sum(), 1), "最大回撤R": round(float((eq - eq.cummax()).min()), 1), "每笔成本R": round(t["成本R"].mean(), 3), "止损距中位pct": round(t["止损距pct"].median(), 2)}

if __name__ == "__main__":
    out = {"时间段": f"{START} → 2026-11-22，Binance USDT 永续 15 分钟线"}
    for sym in ("BTC", "ETH"):
        d = prep(sym); res = {}
        # 核 Gemini 说的「24 根 1 小时高低差平均约 5 倍 ATR」
        d0 = v1.prep(sym); ratio = ((d0.top - d0.bot) / d0.atr1).dropna()
        res["24根高低差是几倍ATR"] = {"平均": round(float(ratio.mean()), 2), "中位": round(float(ratio.median()), 2), "落在1.5到4倍的占比pct": round(float(((ratio >= 1.5) & (ratio <= 4)).mean() * 100), 1)}
        dd = {"摆动点": d, "摆动点_以最高点为准": prep(sym, anchor="最高"), "前一天高低点": prep(sym, box="前一天")}
        res["有箱子的时间占比pct"] = {k: round(float(x.top.notna().mean() * 100), 1) for k, x in dd.items()}
        runs = {}
        for bx in dd:
            for tr, tn in (("甲", "第二次冲不过"), ("乙", "到位不破连续上影"), ("丙", "两步确认")):
                runs[f"{bx}｜{tn}"] = (bx, dict(trig=tr))
                if bx == "摆动点": runs[f"{bx}｜{tn}｜去掉大周期阻力"] = (bx, dict(trig=tr, need_res=False))
        for name, (bx, kw) in runs.items():
            t, cnt = run(dd[bx], **kw); t.to_csv(os.path.join(HERE, "out", f"二版_{sym}_{name}.csv"), index=False)
            res[name] = {"全部": S(t), "漏斗": cnt, "分年": {int(y): S(g) for y, g in t.groupby("年")} if len(t) else {}, "分档": {k: S(g) for k, g in t.groupby("档")} if len(t) else {},
                         "怎么出": t["怎么出"].value_counts().to_dict() if len(t) else {}}
            print(sym, name, res[name]["全部"], cnt, flush=True)
        out[sym] = res
        json.dump(out, open(os.path.join(HERE, "out", "日内区间_二版骨架_结果.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("DONE")
