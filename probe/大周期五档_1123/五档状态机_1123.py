# -*- coding: utf-8 -*-
"""大周期状态机 · 第三版（五档）· 照《410 + 411 拍板》（Lin 11-23 15:45~16:04）第 1~4 条 · BTC / ETH 日线 · 引擎外
五档：涨势（含「涨势·中继」）/ 见顶 / 跌势 / 筑底期 / 转涨期。涨势、见顶、地板、转空 同第二版，没动。
跌势 → 筑底期（两条路，任一）：
   甲（拍板 3：降级）收盘高过这轮跌势里最近一个反弹高点、并在 200 日线上
   乙（拍板 1）同时满足：① N1 天不创新低；② 200 日线今天 ÷ 20 天前 ≥ K200；③ 三样有一样：二次探底低点抬高 / 跌破前低后 5 天内收回 / N1 天振幅 < AMP
   冷却（拍板 2）：离周期最高点不到 180 天，一律不出跌势
筑底期 → 转涨期：进筑底期满 COOL 天；最近 2 个周线收盘都在箱顶和 200 日线之上；并收复这轮跌幅的一半
筑底期 → 跌势：① 连续 3 天收盘低于周期低点 BRK 以上；② 跌破关键位（最近 60 天里最低的已确认摆动低点）当天就切（Lin 11-23 13:58），之后反弹过 0.382 改回筑底期
假跌破保护（拍板 4）：因①切回跌势后 PROT 天内，某个周线收盘回到原低点之上、且那周的量 > 前 8 周平均 → 改回筑底期
转涨期 → 涨势：顶底抬高、收盘 > 50 日线 > 200 日线、离半年高点 < 15%（同第二版）
转涨期 → 筑底期：最近 2 个周线收盘都跌回 200 日线之下（★ 拍板没写，我补的）
跌势 / 筑底期 / 转涨期 里收盘创了周期新高 → 之前的转空作废，直接回涨势（★ 我补的：不加这条，2020-09 那次小回调会把整个 2020~21 牛市卡在筑底期）
跌破关键位切回跌势后：只有反弹过 0.382 才改回；否则要再过 N1 天才重新看甲、乙（★ 我补的：不加会一天一翻）
★ 我补的定义：箱顶 = 周期低点那天到 14 天前的最高价；200 日线用简单均线；「很快收回」= 5 天内；「放量」= 那周的量 > 前 8 周平均。
"""
import os, sys, glob, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
def mod(n, p):
    sp = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
v2 = mod("v2", os.path.join(ROOT, "probe/大周期四档_1122/四档状态机_第二版_1122.py"))

def 日线(sym):
    fs = sorted(glob.glob(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/币_小时线_Coinbase/*.parquet")))
    d = pd.concat([pd.read_parquet(f) for f in fs]); d = d[d.symbol == sym]; d["t"] = pd.to_datetime(d.time_utc, utc=True); d = d.set_index("t").sort_index()
    D = d.resample("1D").agg({"open_adj": "first", "high_adj": "max", "low_adj": "min", "close_adj": "last", "volume_adj": "sum"}).dropna(); D.columns = ["open", "high", "low", "close", "volume"]
    D.index = D.index.tz_localize(None); return D

def 跑(D, k=3, 突破幅度=0.15, 地板容差=0.02, N1=60, K200=0.985, AMP=0.35, COOL=90, BRK=0.03, PROT=14, 高点冷却=180):
    o, h, l, c = D.open.values, D.high.values, D.low.values, D.close.values; n = len(D); idx = D.index
    e50 = D.close.ewm(span=50, adjust=False).mean().values; e200 = D.close.ewm(span=200, adjust=False).mean().values
    s200 = D.close.rolling(200).mean().values
    h180 = D.high.rolling(180, min_periods=60).max().values; h365 = D.high.rolling(365, min_periods=120).max().values
    amp = (D.high.rolling(N1).max() / D.low.rolling(N1).min() - 1).values
    W = D.resample("W").agg({"close": "last", "volume": "sum"}); W["v8"] = W.volume.rolling(8).mean().shift(1)
    wk_end = {t: (W.close.iloc[j], W.close.iloc[j - 1] if j else np.nan, W.volume.iloc[j], W.v8.iloc[j]) for j, t in enumerate(W.index)}
    W4 = v2.周线摆动高点(D, 4)
    SH, SL = [], []; st = ["历史不够"] * n; why = [""] * n; cur = None; floor = np.nan
    框架起点 = idx[0]; 跌势起点 = None; 低 = np.nan; 低i = 0; 前高 = np.nan; 前高i = 0; 参考高 = np.nan
    筑底起i = None; rev = None; prot = None; lastW = (np.nan, np.nan, np.nan, np.nan); below = 0; 事件 = []
    for i in range(n):
        j = i - k
        if j >= k:
            w = slice(j - k, j + k + 1)
            if h[j] == h[w].max(): SH.append((i, h[j]))
            if l[j] == l[w].min(): SL.append((i, l[j], j))
        t = idx[i]
        if t in wk_end and t.dayofweek == 6: lastW = wk_end[t]; 周收 = True
        else: 周收 = False
        if i < 220 or len(SH) < 2 or len(SL) < 2: continue
        hh = SH[-1][1] > SH[-2][1]; hl = SL[-1][1] > SL[-2][1]
        up = hh and hl and c[i] > e50[i] > e200[i] and c[i] > 0.85 * h180[i]
        top = c[i] > 0.80 * h365[i] and SH[-1][1] <= SH[-2][1] * 1.015 and c[i] < e50[i] and c[i] > e200[i]
        半 = 低 + 0.5 * (前高 - 低) if not (np.isnan(低) or np.isnan(前高)) else np.nan
        new = cur; r = ""
        if cur is None:
            new = "涨势" if c[i] > e200[i] else "跌势"; r = "起始：看在 200 日线上还是下"
            if new == "跌势": 跌势起点 = t; 低 = l[i]; 低i = i; 前高 = D.high.iloc[:i + 1].max(); 前高i = int(np.argmax(h[:i + 1]))
        elif cur in ("涨势", "涨势·中继", "见顶"):
            if np.isnan(前高) or h[i] > 前高: 前高 = h[i]; 前高i = i
            cand = [(wk, p) for (cf, wk, p) in W4 if cf <= t and wk >= 框架起点 and D.high.loc[wk:t].max() >= p * (1 + 突破幅度)]
            if cand: floor = cand[-1][1]
            if not np.isnan(floor) and c[i] < floor * (1 - 地板容差):
                new = "跌势"; r = f"收盘跌回上一个被有效突破的前高（{floor:,.0f}）之下，框架转空"; 跌势起点 = t; 低 = l[i]; 低i = i; rev = None; prot = None; 参考高 = np.nan
            elif up: new = "涨势"
            elif top: new = "见顶"
            else: new = "涨势·中继"
            if new != cur and r == "": r = {"涨势": "顶底抬高、站上 50 和 200 日线", "见顶": "离一年高点两成以内、新高点没超过前高、跌破 50 日线", "涨势·中继": "回调，但没跌回上一个被有效突破的前高"}[new]
        elif cur in ("跌势", "筑底期", "转涨期") and not np.isnan(前高) and c[i] > 前高:
            new = "涨势"; r = f"收盘创周期新高（高过 {前高:,.0f}），之前的转空作废，回到涨势"; 前高 = h[i]; 前高i = i; rev = None; prot = None; 筑底起i = None; below = 0; 框架起点 = 跌势起点 if 跌势起点 is not None else 框架起点
        elif cur == "跌势":
            if l[i] < 低: 低 = l[i]; 低i = i
            if rev is not None: rev["low"] = min(rev["low"], l[i])
            if prot is not None and i - prot["i"] > PROT: prot = None
            if prot is not None and 周收 and lastW[0] > prot["L0"] and lastW[2] > lastW[3]:
                new = "筑底期"; r = f"假跌破保护：跌破前低（{prot['L0']:,.0f}）后 {i - prot['i']} 天，周线放量收回前低上方，当洗盘"; 事件.append(("假跌破保护", str(t.date()), float(c[i]))); 筑底起i = i; prot = None; rev = None
            elif rev is not None and h[i] >= rev["low"] + 0.382 * (rev["top"] - rev["low"]) and prot is None and c[i] > 低:
                new = "筑底期"; r = "跌破关键位后反弹过了 0.382，改回筑底期"; rev = None; 筑底起i = 筑底起i if 筑底起i is not None else i
            elif i - 前高i >= 高点冷却 and (rev is None or i - rev["i"] >= N1):
                reb = [(wk, p) for (cf, wk, p) in W4 if cf <= t and wk > 跌势起点]
                ref = reb[-1][1] if reb else np.nan
                if not np.isnan(参考高): ref = 参考高 if np.isnan(ref) else min(ref, 参考高)
                甲 = (not np.isnan(ref)) and c[i] > ref and c[i] > e200[i]
                sl2 = [x for x in SL if x[2] >= 低i]
                抬高 = len(sl2) >= 2 and sl2[-1][1] > sl2[-2][1]
                弹簧 = any((l[m] < min(l[max(0, m - N1):m]) and c[min(n - 1, m + 5)] > min(l[max(0, m - N1):m])) for m in range(max(1, i - N1), i - 5)) if i > N1 + 6 else False
                乙 = (i - 低i >= N1) and s200[i] > 0 and s200[i - 20] > 0 and s200[i] / s200[i - 20] >= K200 and (抬高 or 弹簧 or amp[i] < AMP)
                if 甲 or 乙:
                    new = "筑底期"; 筑底起i = i; rev = None
                    r = f"收盘高过这轮跌势里最近一个反弹高点（{ref:,.0f}）：只算进筑底期，不算转涨" if 甲 else f"{N1} 天不创新低、200 日线走平、" + ("低点抬高" if 抬高 else ("跌破前低后收回" if 弹簧 else f"{N1} 天振幅小于 {AMP:.0%}"))
        elif cur == "筑底期":
            below = below + 1 if c[i] < 低 * (1 - BRK) else 0
            箱顶 = h[低i:max(低i + 1, i - 13)].max()
            rec = [p for (ci, p, _) in SL if ci >= i - 60]
            if below >= 3:
                new = "跌势"; r = f"连续 3 天收盘低于周期低点（{低:,.0f}）3% 以上"; prot = {"i": i, "L0": 低}; 跌势起点 = t; 参考高 = h[低i:i + 1].max(); 低 = min(低, l[i]); 低i = i; rev = None; below = 0; 筑底起i = None
            elif rec and c[i] < min(rec) and c[i] < o[i]:
                new = "跌势"; r = f"筑底期里跌破关键位（{min(rec):,.0f}），当天切回跌势"; rev = {"top": h[max(低i, i - 120):i + 1].max(), "low": l[i], "i": i}
                if l[i] < 低: 低 = l[i]; 低i = i
            elif i - 筑底起i >= COOL and lastW[0] > max(箱顶, s200[i]) and lastW[1] > max(箱顶, s200[i]) and not np.isnan(半) and c[i] >= 半:
                new = "转涨期"; r = f"进筑底期满 {COOL} 天；周线连续 2 周站上箱顶（{箱顶:,.0f}）和 200 日线；收复跌幅一半（{半:,.0f}）"
            if l[i] < 低 and new == "筑底期": pass
        elif cur == "转涨期":
            if up:
                new = "涨势"; r = "顶底抬高、站上 50 和 200 日线"; 框架起点 = 跌势起点 if 跌势起点 is not None else 框架起点; floor = 低; 前高 = h[i]; 前高i = i; 筑底起i = None
            elif lastW[0] < s200[i] and lastW[1] < s200[i]:
                new = "筑底期"; r = "周线连续 2 周跌回 200 日线之下，退回筑底期"; 筑底起i = i
        if new != cur: why[i] = r
        cur = new; st[i] = cur
    return pd.DataFrame({"close": c, "档": st, "切换原因": why}, index=idx), 事件

色 = {"涨势": "#2e9e5b", "涨势·中继": "#a8dab5", "见顶": "#f2b134", "跌势": "#d64545", "筑底期": "#8f7fd6", "转涨期": "#4a90d9", "历史不够": "#dddddd"}
def 画(D, R, 名, 起="2017-06-01"):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    for f in glob.glob("/usr/share/fonts/**/*", recursive=True):
        if os.path.isfile(f) and any(x in f.lower() for x in ("cjk", "wqy", "notosanssc")): fm.fontManager.addfont(f); plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name(); break
    R = R.loc[起:]; fig, ax = plt.subplots(figsize=(18, 8)); ax.plot(R.index, R.close, color="#222", lw=0.9); ax.set_yscale("log")
    s = R["档"].values; a = 0
    for b in range(1, len(R) + 1):
        if b == len(R) or s[b] != s[a]: ax.axvspan(R.index[a], R.index[b - 1], color=色[s[a]], alpha=0.45, lw=0); a = b
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=色[k], alpha=0.6) for k in list(色)[:6]], labels=list(色)[:6], loc="upper left", ncol=6, fontsize=12)
    ax.set_title(f"{名} 大周期五档 · 第三版（2026-11-23）· 每天只用当天已收盘的数据", fontsize=15); ax.grid(alpha=0.2)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "out", f"{名}_三版_五档.png"), dpi=110); plt.close(fig)

if __name__ == "__main__":
    for sym in ("BTC", "ETH"):
        D = 日线(sym); R, ev = 跑(D); R.to_csv(os.path.join(HERE, "out", f"{sym}_三版_每天的档.csv"))
        sw = R[R["切换原因"] != ""]; sw.to_csv(os.path.join(HERE, "out", f"{sym}_三版_切换清单.csv")); 画(D, R, sym)
        print(sym, R["档"].value_counts().to_dict(), "今天", R["档"].iloc[-1], ev)
        x = sw[(sw["档"].isin(["跌势", "筑底期", "转涨期"])) | (sw["档"].shift().isin(["跌势", "筑底期", "转涨期"]))]
        print(x[["close", "档", "切换原因"]].to_string())
