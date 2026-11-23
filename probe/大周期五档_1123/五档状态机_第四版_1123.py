# -*- coding: utf-8 -*-
"""大周期五档 · 第四版 · 照《415 定稿》（Lin 交给主 chat 和 Gemini 定）· 引擎外 · 日线
主版：转空用 B 版；筑底期用「封口的箱子」；防 V 形用 61.8%（定稿七之三的①）。对照版用参数切换。
没做（报告里写明）：双顶 / 三顶单独的确认（B 版已能覆盖转空，没另写）；「必须先有恐慌放量」对照；A 版转空；个股财报跳空。
★ 我补的：① 转涨期 → 涨势 沿用前几版的「顶底抬高、收盘 > 50 日线 > 200 日线、离半年高点 15% 以内」；
          ② 熊市各档里收盘创周期新高 → 直接回涨势；③ 转涨期里周线连续 2 周收在 200 日线下 → 退回跌势；
          ④ 「波动已收缩」= 箱子里至少有一天达标；⑤ 周波幅用「见顶那周及之前已走完的 14 周」。
"""
import os, sys, glob, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
P币 = dict(跌幅=0.40, 箱宽=0.45, 最短横=35, 针深ATR=1.5, 针深pct=0.08, 反弹最小=0.15, 用量=False, 缩量=0.5, 放量=1.2)
P指数 = dict(跌幅=0.15, 箱宽=0.18, 最短横=30, 针深ATR=1.5, 针深pct=0.035, 反弹最小=0.05, 用量=True, 缩量=0.70, 放量=1.3)

def 币日线(sym):
    if sym == "SOL":
        D = pd.read_parquet(os.path.join(ROOT, "market_ext_1105/币_持仓量和SOL_1123/SOL_Coinbase/SOL_日线.parquet")); return D
    fs = sorted(glob.glob(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/币_小时线_Coinbase/*.parquet")))
    d = pd.concat([pd.read_parquet(f) for f in fs]); d = d[d.symbol == sym]; d["t"] = pd.to_datetime(d.time_utc, utc=True); d = d.set_index("t").sort_index()
    n = d.resample("1D").size()
    D = d.resample("1D").agg({"open_adj": "first", "high_adj": "max", "low_adj": "min", "close_adj": "last", "volume_adj": "sum"}).dropna(); D.columns = ["open", "high", "low", "close", "volume"]
    D = D[n.reindex(D.index) >= 20]          # 没走完的那天不要（最后一天只有 8 个小时）
    D.index = D.index.tz_localize(None); return D
def 美股日线(sym):
    x = pd.read_csv(os.path.join(ROOT, f"market_ext_1105/指数ETF_1993起_1122/{sym}_日线_1993起.csv"), parse_dates=["date"]).set_index("date")
    a = pd.DataFrame({"open": x.open_adj, "high": x.high_adj, "low": x.low_adj, "close": x.close_adj, "volume": x.volume_adj}).dropna()
    y = pd.read_csv(os.path.join(ROOT, f"market_ext_1105/ETF和币_1120/日线/{sym}_日线.csv"), parse_dates=["date"]).set_index("date")
    b = pd.DataFrame({"open": y.open_adj, "high": y.high_adj, "low": y.low_adj, "close": y.close_adj, "volume": y.volume_adj}).dropna()
    b = b[b.index > a.index[-1]]; f = a.close.iloc[-1] / y.close_adj.reindex(a.index).dropna().iloc[-1] if len(y.close_adj.reindex(a.index).dropna()) else 1.0
    return pd.concat([a, b]).sort_index()      # 两段都是拆股复权价；接缝 2003-09

def 跑(D, P, k=3, 转空倍数=2.2, 封口=0.30, 止跌天=35, 均线变=0.025, 针收回=3, 观察=3, 横比=0.25, V=0.618, 用200=False, 压制=None, V按收复=False):
    o, h, l, c, v = (D[x].to_numpy(float) for x in ("open", "high", "low", "close", "volume")); n = len(D); idx = D.index
    pc = np.roll(c, 1); pc[0] = c[0]; tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))
    atr = pd.Series(tr).rolling(14).mean().to_numpy(); ap = atr / c
    s150 = pd.Series(c).rolling(200 if 用200 else 150).mean().to_numpy(); s200 = pd.Series(c).rolling(200).mean().to_numpy()
    e50 = pd.Series(c).ewm(span=50, adjust=False).mean().to_numpy(); e200 = pd.Series(c).ewm(span=200, adjust=False).mean().to_numpy()
    h180 = pd.Series(h).rolling(180, min_periods=60).max().to_numpy(); h365 = pd.Series(h).rolling(365, min_periods=120).max().to_numpy()
    v10 = pd.Series(v).rolling(10).mean().to_numpy(); v60 = pd.Series(v).rolling(60).mean().to_numpy(); v20 = pd.Series(v).rolling(20).mean().shift(1).to_numpy()
    W = D.resample("W").agg({"high": "max", "low": "min", "close": "last"}).dropna(); wpc = W.close.shift()
    W["atr"] = pd.concat([W.high - W.low, (W.high - wpc).abs(), (W.low - wpc).abs()], axis=1).max(axis=1).rolling(14).mean()
    watr = W.atr.reindex(idx, method="ffill").to_numpy(); wclose = W.close.reindex(idx, method="ffill").to_numpy(); wclose2 = W.close.shift(1).reindex(idx, method="ffill").to_numpy()
    SH, SL = [], []; st = ["历史不够"] * n; why = [""] * n; cur = None; EV = []
    pk = np.nan; pki = 0; L = np.nan; li = 0; H1 = np.nan; h1i = 0; 封了 = False; box = None; 缩过 = False; sos = None; watch = None; spring = None
    for i in range(n):
        j = i - k
        if j >= k:
            w = slice(j - k, j + k + 1)
            if h[j] == h[w].max(): SH.append((i, h[j], j))
            if l[j] == l[w].min(): SL.append((i, l[j], j))
        if i < 220 or len(SH) < 2 or len(SL) < 2 or not (s200[i] > 0): continue
        t = idx[i]; a = atr[i]
        hh = SH[-1][1] > SH[-2][1]; hl = SL[-1][1] > SL[-2][1]
        up = hh and hl and c[i] > e50[i] > e200[i] and c[i] > 0.85 * h180[i]
        top = c[i] > 0.80 * h365[i] and SH[-1][1] <= SH[-2][1] * 1.015 and c[i] < e50[i] and c[i] > e200[i]
        new = cur; r = ""
        def 进涨势(why_):
            nonlocal pk, pki, box, sos, watch, spring, 封了, H1, 缩过
            j0 = li if cur is not None and cur != "涨势" else i
            seg = h[j0:i + 1]; pk = seg.max(); pki = j0 + int(np.argmax(seg)); box = None; sos = None; watch = None; spring = None; 封了 = False; H1 = np.nan; 缩过 = False
            return "涨势", why_
        def 进跌势(why_, 新周期):
            nonlocal L, li, H1, h1i, 封了, box, sos, watch, spring, 缩过
            if 新周期: L = l[i]; li = i
            elif l[i] < L: L = l[i]; li = i
            H1 = np.nan; 封了 = False; box = None; sos = None; watch = None; spring = None; 缩过 = False
            return "跌势", why_
        if cur is None:
            if c[i] > s200[i]: pk = h[:i + 1].max(); pki = int(np.argmax(h[:i + 1])); new = "涨势"; r = "起始：在 200 日线上"
            else: pk = h[:i + 1].max(); pki = int(np.argmax(h[:i + 1])); L = l[pki:i + 1].min(); li = pki + int(np.argmin(l[pki:i + 1])); new = "跌势"; r = "起始：在 200 日线下"
        elif cur in ("涨势", "涨势·中继", "见顶"):
            if h[i] > pk: pk = h[i]; pki = i
            wa = watr[min(i, pki + 6)]; 门槛 = pk * (1 - 转空倍数 * wa / pk) if wa > 0 else -np.inf
            sl = [x for x in SL if x[2] < pki]; 前低 = sl[-1][1] if sl else np.nan
            if c[i] < 门槛 and c[i] < s150[i] and not np.isnan(前低) and c[i] < 前低:
                new, r = 进跌势(f"转空：收盘跌过门槛（{门槛:,.0f}）、在 150 日线下、跌破见顶前最后一个低点（{前低:,.0f}）；离最高点 {c[i] / pk - 1:.0%}", True)
                EV.append({"事": "转空", "日期": str(t.date()), "收盘": float(c[i]), "最高点": float(pk), "离顶pct": round((c[i] / pk - 1) * 100, 1)})
            elif up: new = "涨势"
            elif top: new = "见顶"
            else: new = "涨势·中继"
        elif c[i] > pk:
            new, r = 进涨势(f"收盘创周期新高（高过 {pk:,.0f}），回到涨势")
        elif cur == "跌势":
            if l[i] < L:
                L = l[i]; li = i; H1 = np.nan; 封了 = False
            else:
                if np.isnan(H1) or (h[i] > H1 and not 封了) or h[i] > H1: 
                    if np.isnan(H1) or h[i] > H1: H1 = h[i]; h1i = i; 封了 = False
                if not 封了 and H1 / L - 1 >= max(P["反弹最小"], 2.5 * ap[li] if ap[li] > 0 else 0) and l[i] <= H1 - 封口 * (H1 - L) and i > h1i: 封了 = True
            reb = (c[i] - L) / max(pk - L, 1e-9) if V按收复 else (c[i] - L) / L      # V按收复：按「收复了这轮跌幅的几成」算，指数用
            if reb >= V and wclose[i] > s200[i] and wclose2[i] > s200[i] and (压制 is None or 压制[i] != "跌势"):
                new = "转涨期"; r = f"防 V 形：从最低点（{L:,.0f}）反弹超过 {V:.1%}、周线连续 2 周站上 200 日线，离开跌势"; box = None
            elif 封了 and (pk - L) / pk >= P["跌幅"] and i - li >= 止跌天 and H1 / L - 1 <= P["箱宽"] and s150[i - 20] > 0 and abs(s150[i] / s150[i - 20] - 1) <= 均线变:
                new = "筑底期"; box = {"底": L, "顶": H1, "起": i}; 缩过 = False; sos = None; watch = None
                r = f"进筑底期：箱底 {L:,.0f}、箱顶 {H1:,.0f}（宽 {H1 / L - 1:.0%}），{i - li} 天没创新低，150 日线走平"
        elif cur == "筑底期":
            底, 顶 = box["底"], box["顶"]; 中 = (底 + 顶) / 2
            if P["用量"]:
                if v60[i] > 0 and v10[i] <= P["缩量"] * v60[i]: 缩过 = True
            else:
                m = np.nanmax(ap[max(li - 10, 0):box["起"] + 1])
                if ap[i] <= P["缩量"] * m: 缩过 = True
            if watch is not None:
                if c[i] > 底: 
                    box["底"] = min(watch["low"], l[i]); L = box["底"]; EV.append({"事": "插针收回", "日期": str(t.date()), "收盘": float(c[i]), "针尖": float(box["底"])}); watch = None
                else:
                    watch["low"] = min(watch["low"], l[i])
                    if i - watch["i"] >= 观察: new, r = 进跌势(f"跌破箱底（{底:,.0f}）{观察} 天没收回，切回跌势", False)
            elif c[i] < 底 - 1.8 * a: new, r = 进跌势(f"收盘跌破箱底（{底:,.0f}）超过 1.8 倍日波幅，直接切回跌势", False)
            elif c[i] < 底 - 0.5 * a: watch = {"i": i, "low": l[i]}
            elif l[i] < 底 and c[i] > 底 and l[i] >= 底 - P["针深ATR"] * a and l[i] >= 底 * (1 - P["针深pct"]):
                box["底"] = l[i]; L = l[i]; EV.append({"事": "插针收回", "日期": str(t.date()), "收盘": float(c[i]), "针尖": float(l[i])})
            if new == "筑底期":
                大阳 = (v[i] >= P["放量"] * v20[i] or v[i - 1] >= P["放量"] * v20[i - 1]) if P["用量"] else (tr[i] >= P["放量"] * atr[i - 1] and c[i] > o[i])
                if sos is None:
                    if c[i] > 顶 + 0.5 * a and c[i] > s150[i] and 大阳 and i - li >= max(P["最短横"], 横比 * (li - pki)) and 缩过:
                        sos = {"i": i, "hi": h[i], "lo": np.inf, "回踩": False}; why[i] = f"（冲出箱顶 {顶:,.0f}，等回踩确认）"
                else:
                    if i - sos["i"] <= 10 and c[i] < 中: sos = None; why[i] = "（冲出后 10 天内跌回箱子中线下，假突破）"
                    else:
                        if h[i] > sos["hi"] and not sos["回踩"]: sos["hi"] = h[i]
                        elif c[i] < sos["hi"] and i - sos["i"] >= 3: sos["回踩"] = True; sos["lo"] = min(sos["lo"], l[i])
                        if sos["回踩"]: sos["lo"] = min(sos["lo"], l[i])
                        if sos["回踩"] and sos["lo"] >= 中 and c[i] > sos["hi"] and s150[i] >= s150[i - 20] and (压制 is None or 压制[i] != "跌势"):
                            new = "转涨期"; r = f"转涨：冲出箱顶（{顶:,.0f}）后回踩守住中线（{中:,.0f}），再创新高，150 日线不再往下"
                        elif sos["回踩"] and sos["lo"] < 中: sos = None
        elif cur == "转涨期":
            if up: new, r = 进涨势("顶底抬高、站上 50 和 200 日线")
            elif wclose[i] < s200[i] and wclose2[i] < s200[i]: new, r = 进跌势("转涨期里周线连续 2 周收在 200 日线下，退回跌势", False)
            elif l[i] < L: new, r = 进跌势("跌破周期最低点", False)
        if new != cur and new in ("转涨期",): EV.append({"事": "转涨", "日期": str(t.date()), "收盘": float(c[i]), "离最低pct": round((c[i] / L - 1) * 100, 1), "离顶pct": round((c[i] / pk - 1) * 100, 1)})
        if new != cur and new == "筑底期": EV.append({"事": "进筑底期", "日期": str(t.date()), "收盘": float(c[i]), "离最低pct": round((c[i] / L - 1) * 100, 1), "离顶pct": round((c[i] / pk - 1) * 100, 1)})
        if new != cur and r: why[i] = r
        cur = new; st[i] = cur
    return pd.DataFrame({"close": c, "档": st, "切换原因": why}, index=idx), EV

色 = {"涨势": "#2e9e5b", "涨势·中继": "#a8dab5", "见顶": "#f2b134", "跌势": "#d64545", "筑底期": "#8f7fd6", "转涨期": "#4a90d9", "历史不够": "#dddddd"}
def 画(R, 名, 起=None, 尾=""):
    import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    for f in glob.glob("/usr/share/fonts/**/*", recursive=True):
        if os.path.isfile(f) and any(x in f.lower() for x in ("cjk", "wqy", "notosanssc")): fm.fontManager.addfont(f); plt.rcParams["font.family"] = fm.FontProperties(fname=f).get_name(); break
    if 起: R = R.loc[起:]
    fig, ax = plt.subplots(figsize=(18, 8)); ax.plot(R.index, R.close, color="#222", lw=0.9); ax.set_yscale("log")
    s = R["档"].values; a = 0
    for b in range(1, len(R) + 1):
        if b == len(R) or s[b] != s[a]: ax.axvspan(R.index[a], R.index[b - 1], color=色[s[a]], alpha=0.45, lw=0); a = b
    ax.legend(handles=[plt.Rectangle((0, 0), 1, 1, color=色[x], alpha=0.6) for x in list(色)[:6]], labels=list(色)[:6], loc="upper left", ncol=6, fontsize=12)
    ax.set_title(f"{名} 大周期五档 · 第四版（照《415 定稿》）· 每天只用当天已收盘的数据", fontsize=15); ax.grid(alpha=0.2)
    fig.tight_layout(); fig.savefig(os.path.join(HERE, "out4", f"{名}_四版_五档{尾}.png"), dpi=110); plt.close(fig)

if __name__ == "__main__":
    out = {}
    B, ev = 跑(币日线("BTC"), P币); out["BTC"] = ev
    for 名, D, P, 压 in (("BTC", 币日线("BTC"), P币, None), ("ETH", 币日线("ETH"), P币, B), ("SPY", 美股日线("SPY"), P指数, None), ("QQQ", 美股日线("QQQ"), dict(P指数, 箱宽=0.25), None)):
        压制 = None if 压 is None else 压["档"].reindex(D.index).ffill().fillna("").to_numpy()
        R, ev = 跑(D, P, 压制=压制); out[名] = ev
        R.to_csv(os.path.join(HERE, "out4", f"{名}_四版_每天的档.csv")); sw = R[R["切换原因"] != ""]; sw.to_csv(os.path.join(HERE, "out4", f"{名}_四版_切换清单.csv")); 画(R, 名)
        print("==", 名, R["档"].value_counts().to_dict(), "最后一天", str(R.index[-1].date()), R["档"].iloc[-1])
        x = sw[(sw["档"].isin(["跌势", "筑底期", "转涨期"])) | (sw["档"].shift().isin(["跌势", "筑底期", "转涨期"])) | sw["切换原因"].str.startswith("（")]
        print(x[["close", "档", "切换原因"]].to_string())
    json.dump(out, open(os.path.join(HERE, "out4", "事件.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
