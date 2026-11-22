# -*- coding: utf-8 -*-
"""日内区间做空（《377》拍板 日1~日3）· BTC/ETH 永续 · 引擎外脚本
默认规则 = 拍板文件【日2】。拍板没给、我自己补的定义（都在报告里标出，跑相邻三点）：
  - 「碰到顶部」= 1 小时 K 线最高价 >= 箱顶 - K×箱高，K 默认 0.10（另跑 0.05 / 0.15）
  - 「长上影」= 上影线 >= 整根振幅的一半
  - 顺势对照：15 分钟收盘站上箱顶（前一根还在箱内）、同样放量；止损 = min(这根最低, 箱顶) - 0.15×ATR15；
    第一目标 = 箱顶 + 0.5×箱高（平一半、推保本），第二目标 = 箱顶 + 0.85×箱高；时间止损同做空版
"""
import os, sys, json, glob
import numpy as np, pandas as pd
ROOT = os.environ.get("XING_ROOT", "/home/claude/xing-agent-stock_data")
D = os.path.join(ROOT, "market_ext_1105/币_15分钟线和资金费_1122")
HERE = os.path.dirname(os.path.abspath(__file__))
START = "2020-01-01"

def wilder(x, n):
    return pd.Series(x).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()

def atr_adx(df, n=14):
    h, l, c = df.high, df.low, df.close
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    up, dn = h.diff(), -l.diff()
    pdm = np.where((up > dn) & (up > 0), up, 0.0); mdm = np.where((dn > up) & (dn > 0), dn, 0.0)
    pdi = 100 * pd.Series(pdm, index=df.index).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean() / atr
    mdi = 100 * pd.Series(mdm, index=df.index).ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean() / atr
    dx = 100 * (pdi - mdi).abs() / (pdi + mdi)
    adx = dx.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    return atr, adx

def load(sym):
    fs = sorted(glob.glob(os.path.join(D, "永续15分钟_Binance", f"{sym}_*.parquet")))
    d = pd.concat([pd.read_parquet(f) for f in fs])
    d["t"] = pd.to_datetime(d.time_utc, utc=True); d = d.set_index("t").sort_index()[["open", "high", "low", "close", "volume"]]
    d = d[~d.index.duplicated()]
    fr = pd.read_csv(os.path.join(D, "资金费_Binance", f"{sym}USDT_资金费.csv"))
    fr["t"] = pd.to_datetime(fr.time_utc, utc=True).dt.round("1h"); fr = fr.set_index("t").funding_rate
    fr = fr[~fr.index.duplicated()]
    return d, fr

def prep(sym, N=24, K=0.10):
    d, fr = load(sym)
    H1 = d.resample("1h").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    a1, adx1 = atr_adx(H1)
    top = H1.high.rolling(N).max(); bot = H1.low.rolling(N).min(); hh = top - bot
    hv = H1.high.values; tv = top.values; hhv = hh.values
    touch = np.full(len(H1), np.nan)
    for i in range(N - 1, len(H1)):
        touch[i] = (hv[i - N + 1:i + 1] >= tv[i] - K * hhv[i]).sum()
    F = pd.DataFrame({"top": top, "bot": bot, "atr1": a1, "adx1": adx1, "atr1m": a1.rolling(50).mean(), "touch": touch})
    F.index = F.index + pd.Timedelta(hours=1)          # 这一小时走完以后才能用
    F = F.reindex(d.index, method="ffill")
    D1 = d.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna()
    _, adxd = atr_adx(D1)
    s20, s50, s200 = D1.close.rolling(20).mean(), D1.close.rolling(50).mean(), D1.close.rolling(200).mean()
    tier = pd.Series("其他", index=D1.index)
    tier[(D1.close < s200) & (s200 < s200.shift(5))] = "200日线下且向下"
    tier[(D1.close < s50) & (D1.close > s200)] = "50日线下200日线上"
    tier[(D1.close > s20) & (s20 > s50) & (adxd > 28)] = "日线强多头"
    tier[s200.isna()] = "历史不够"
    tier.index = tier.index + pd.Timedelta(days=1)
    d["tier"] = tier.reindex(d.index, method="ffill").values
    a15, _ = atr_adx(d)
    d["atr15"] = a15; d["vma"] = d.volume.rolling(20).mean().shift(1)
    d = d.join(F)
    frs = fr.reindex(d.index)                         # 结算那一刻的费率（落在整 8 小时的那根）
    d["fr_now"] = frs.values
    d["fr_last"] = fr.reindex(d.index, method="ffill").shift(1).values   # 进场时能看到的上一次费率
    et = d.index.tz_convert("America/New_York")
    wd, hr = et.weekday.values, et.hour.values
    d["wkend"] = ((wd == 4) & (hr >= 16)) | (wd == 5) | ((wd == 6) & (hr < 18))
    return d[d.index >= START]

def run(d, side="空", ts1=16, ts2=64, fr_mode="-0.02", maxday=2, skip_bull=True, fee=0.0005):
    o, h, l, c, v = (d[x].values for x in ("open", "high", "low", "close", "volume"))
    top, bot, atr1, adx1, atr1m, touch, atr15, vma = (d[x].values for x in ("top", "bot", "atr1", "adx1", "atr1m", "touch", "atr15", "vma"))
    frn, frl, wk, tier = d.fr_now.values, d.fr_last.values, d.wkend.values, d.tier.values
    day = d.index.strftime("%Y-%m-%d").values; ts = d.index
    sg = -1.0 if side == "空" else 1.0
    T = []; pos = None; exc = np.nan; exc_top = np.nan
    boxn = {}; dcount = {}; dR = {}; streak = 0; pause_until = None
    for i in range(60, len(c)):
        # ---- 管持仓 ----
        if pos is not None:
            p = pos; p["n"] += 1; done = False
            if not np.isnan(frn[i]):                        # 结算：空头收正费率
                p["fund"] += (-sg) * frn[i] * o[i] * p["rem"] / p["R"]
            S = p["stop"]
            hit_gap = (o[i] >= S) if side == "空" else (o[i] <= S)
            hit = (h[i] >= S) if side == "空" else (l[i] <= S)
            def leg(px, frac):
                p["pnl"] += frac * (sg * (px - p["E"]) / p["R"]); p["cost"] += frac * fee * (p["E"] + px) / p["R"]; p["rem"] -= frac
            if hit_gap:
                leg(o[i], p["rem"]); p["why"] = "止损" if not p["tp1"] else "保本"; done = True
            elif hit:
                slip = max(0.0002, 0.075 * (h[i] - l[i]) / c[i])
                leg(S * (1 - sg * slip), p["rem"]); p["why"] = "止损" if not p["tp1"] else "保本"; done = True
            else:
                r1 = (l[i] <= p["t1"]) if side == "空" else (h[i] >= p["t1"])
                r2 = (l[i] <= p["t2"]) if side == "空" else (h[i] >= p["t2"])
                if not p["tp1"] and r1:
                    leg(p["t1"], 0.5); p["tp1"] = True; p["stop"] = p["E"]; p["n1"] = 0
                if p["tp1"] and r2:
                    leg(p["t2"], p["rem"]); p["why"] = "第二目标"; done = True
                elif p["tp1"]:
                    p["n1"] += 1
                    if p["n1"] >= ts2: leg(c[i], p["rem"]); p["why"] = "到时间(过中轴后)"; done = True
                elif p["n"] >= ts1:
                    leg(c[i], p["rem"]); p["why"] = "到时间(没到中轴)"; done = True
            if done:
                net = p["pnl"] - p["cost"] + p["fund"]
                T.append({"进": str(ts[p["i"]]), "出": str(ts[i]), "年": int(day[p["i"]][:4]), "档": p["tier"], "毛R": p["pnl"], "成本R": p["cost"], "资金费R": p["fund"],
                          "净R": net, "不含资金费净R": p["pnl"] - p["cost"], "怎么出": p["why"], "根数": p["n"], "止损距pct": p["R"] / p["E"] * 100})
                dR[day[p["i"]]] = dR.get(day[p["i"]], 0) + net
                streak = streak + 1 if net < 0 else 0
                if streak >= 3: pause_until = ts[i] + pd.Timedelta(hours=24); streak = 0
                pos = None
            continue
        # ---- 找进场 ----
        tp, bt = top[i], bot[i]
        if np.isnan(tp) or np.isnan(adx1[i]) or np.isnan(atr1m[i]) or np.isnan(vma[i]): continue
        if side == "空":
            if h[i] > tp:
                exc = max(exc, h[i]) if exc_top == tp else h[i]; exc_top = tp
            else:
                exc_top = np.nan
        H = tp - bt; mid = (tp + bt) / 2
        if not (1.5 * atr1[i] <= H <= 4 * atr1[i]) or adx1[i] >= 22 or touch[i] < 2: continue
        if atr1[i] > 1.5 * atr1m[i] or wk[i]: continue
        if skip_bull and tier[i] == "日线强多头": continue
        if pause_until is not None and ts[i] < pause_until: continue
        if dcount.get(day[i], 0) >= maxday or dR.get(day[i], 0) <= -2: continue
        if boxn.get(tp, 0) >= 2: continue
        if v[i] < 1.3 * vma[i]: continue
        if side == "空":
            f = frl[i]
            if fr_mode == "-0.02" and not (f >= -0.0002): continue
            if fr_mode == "-0.005" and not (f >= -0.00005): continue
            if fr_mode == "+0.01" and not (f > 0.0001): continue
            if not (h[i] > tp and c[i] < tp): continue
            if exc - tp > 0.35 * H: continue
            rng = h[i] - l[i]
            if not (c[i] < o[i] or (rng > 0 and (h[i] - max(o[i], c[i])) >= 0.5 * rng)): continue
            stop = exc + 0.15 * atr15[i]; R = stop - c[i]
            if R > 0.35 * H or R / c[i] < 0.0045: continue
            if c[i] - mid < 1.2 * R: continue
            t1, t2 = mid, bt + 0.15 * H
        else:
            if not (c[i] > tp and c[i - 1] <= tp): continue
            if c[i] - tp > 0.35 * H: continue
            stop = min(l[i], tp) - 0.15 * atr15[i]; R = c[i] - stop
            if R > 0.35 * H or R / c[i] < 0.0045: continue
            t1, t2 = tp + 0.5 * H, tp + 0.85 * H
            if t1 - c[i] < 1.2 * R: continue
        pos = {"i": i, "E": c[i], "stop": stop, "R": R, "t1": t1, "t2": t2, "tp1": False, "n": 0, "n1": 0, "rem": 1.0, "pnl": 0.0, "cost": 0.0, "fund": 0.0, "why": "", "tier": tier[i]}
        boxn[tp] = boxn.get(tp, 0) + 1; dcount[day[i]] = dcount.get(day[i], 0) + 1
    return pd.DataFrame(T)

def 汇总(t):
    if len(t) == 0: return {"笔数": 0}
    r = t["净R"]; w = r[r > 0].sum(); ls = -r[r < 0].sum(); eq = r.cumsum()
    fund = t["资金费R"].sum(); tot = r.sum()
    return {"笔数": int(len(t)), "每笔净R": round(r.mean(), 3), "每笔毛R": round(t["毛R"].mean(), 3), "每笔成本R": round(t["成本R"].mean(), 3), "每笔资金费R": round(t["资金费R"].mean(), 4),
            "不含资金费每笔净R": round(t["不含资金费净R"].mean(), 3), "胜率pct": round((r > 0).mean() * 100, 1), "利润因子": round(w / ls, 2) if ls > 0 else None,
            "累计净R": round(tot, 1), "最大回撤R": round(float((eq - eq.cummax()).min()), 1), "资金费占利润pct": round(fund / tot * 100, 1) if tot > 0 else None,
            "止损距中位pct": round(t["止损距pct"].median(), 2)}

if __name__ == "__main__":
    out = {"时间段": f"{START} → 2026-11-22（Binance USDT 永续，15 分钟线）", "成本": "吃单单边 0.05%；止损滑点 max(0.02%, 0.075×那根振幅÷收盘)"}
    base = {}
    for sym in ("BTC", "ETH"):
        d = prep(sym); base[sym] = d
        res = {}
        def 记(name, t):
            t.to_csv(os.path.join(HERE, "out", f"{sym}_{name}.csv"), index=False)
            res[name] = {"全部": 汇总(t), "分年": {int(y): 汇总(g) for y, g in t.groupby("年")} if len(t) else {}, "分档": {k: 汇总(g) for k, g in t.groupby("档")} if len(t) else {},
                         "怎么出": t["怎么出"].value_counts().to_dict() if len(t) else {}}
            print(sym, name, res[name]["全部"], flush=True)
        记("空_默认", run(d))
        记("空_不滤强多头(只为分档报)", run(d, skip_bull=False))
        记("空_到中轴前8根", run(d, ts1=8))
        记("空_资金费门槛-0.005", run(d, fr_mode="-0.005"))
        记("空_资金费要大于+0.01", run(d, fr_mode="+0.01"))
        记("空_每天最多3笔", run(d, maxday=3))
        记("顺势对照_多", run(d, side="多"))
        记("顺势对照_多_不滤强多头", run(d, side="多", skip_bull=False))
        for K in (0.05, 0.15):
            记(f"空_碰顶K{K}", run(prep(sym, K=K)))
        out[sym] = res
    json.dump(out, open(os.path.join(HERE, "out", "日内区间_币_结果.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
