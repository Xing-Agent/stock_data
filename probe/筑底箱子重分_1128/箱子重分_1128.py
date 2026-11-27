# -*- coding: utf-8 -*-
"""《499》=《487 拍板》第 2~5 件 · 引擎外 · 日线 · 在状态机第四版的全部筑底箱子上跑
品种：BTC、ETH（2017–2026，不封）；SPY、QQQ（1993/1999–2021）、SOXX（2001–2021）。美股 2022 年以后不读。
箱子：状态机「进筑底期」到离开筑底期。箱底箱顶照状态机算法算回原值（切换原因里写的是取整数，SOXX 上会错，见《492》）。
出箱方向：离开筑底期后的档 = 涨势 / 涨势·中继 / 转涨期 → 向上；跌势 → 破位（同《486》）。

第 2 件：离大顶天数 = 进箱那天，离过去两年（币 730 根、美股 504 根）最高收盘隔了几根。门槛：币 180（150/210），美股 120（90/150）。
         判对 = 过门槛（算筑底）且最后向上，或没过门槛（算熊市中段）且最后破位。另报「出箱前哪天过了门槛」。
第 3 件：两个对照各自单独替掉门槛：
         量能萎缩 = 进箱那天近 20 天均量 < 这段下跌（大顶到进箱）里最大的 20 天均量 × 0.45（另试 0.35、0.55）；
         首箱豁免 = 大顶之后的第一个筑底箱子不算筑底。
第 4 件：再派发 = 箱内最新波段高点比箱内最高波段高点低 ≥1.5 ATR 且 150 日线向下（同《486》，含它的撤销条件）；
         再加一条：最新的波段低点离箱底 ≤ 0.5 / 0.8 / 1.2 ATR，且收盘在 150 日线下。
第 5 件：均线退路 A 版（只在筑底期里）：50 日线比 10 天前低、收盘在 150 日线下、当天或前一天的最高价碰进
         [min(EMA20, 50 日线) − 0.2 ATR, max(EMA20, 50 日线) + 0.2 ATR] 那一带、当天是阴线且收盘跌破前一天最低 → 当天收盘空，
         止损 = 近 5 天最高 + 0.4 ATR（另试 0.3、0.5），半仓。
         出场拍板没写（我补的，另试一组）：打止损 / 到 3 倍风险 / 拿满 60 天（另试：2 倍风险、40 天）。同一时间只拿一笔。单边 0.05%。
         B 版：拍板原文不在仓库里，没跑。
"""
import os, sys, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
M4 = mod("M4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py")); SC = mod("SC", os.path.join(ROOT, "probe/历史扫描定级别_1123/扫描_1123.py"))
封 = pd.Timestamp("2021-12-31"); 币 = ("BTC", "ETH"); FEE = 0.0005


def 读(sym):
    D = M4.币日线(sym) if sym in 币 else SC.soxx() if sym == "SOXX" else M4.美股日线(sym)
    R = pd.read_csv(os.path.join(ROOT, f"probe/大周期五档_1123/out4/{sym}_四版_每天的档.csv"), index_col=0, parse_dates=True)
    if sym not in 币: D = D.loc[:封]; R = R.loc[:封]
    D = D.loc[D.index.isin(R.index)]; return D, R.reindex(D.index)


def 箱子们(sym, 派=1.5, 底距=None):
    D, R = 读(sym); o, h, l, c, v = (D[x].to_numpy(float) for x in ("open", "high", "low", "close", "volume")); n = len(c); idx = D.index
    st = R["档"].to_numpy(); why = R["切换原因"].fillna("").to_numpy()
    pc = np.roll(c, 1); pc[0] = c[0]; atr = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14).mean().bfill().to_numpy()
    s150 = pd.Series(c).rolling(150).mean().to_numpy(); v20 = pd.Series(v).rolling(20).mean().to_numpy()
    SH = [j for j in range(5, n - 5) if h[j] == h[j - 5:j + 6].max()]; SL = [j for j in range(5, n - 5) if l[j] == l[j - 5:j + 6].min()]
    回看 = 730 if sym in 币 else 504
    顶位 = np.array([max(0, i - 回看) + int(np.argmax(c[max(0, i - 回看):i + 1])) for i in range(n)])
    boxes = []; box = None; 派日 = np.zeros(n, bool)
    for i in range(1, n):
        if why[i].startswith("进筑底期"):
            s0 = max([q for q in range(i) if st[q] == "跌势" and st[q - 1] != "跌势"] or [0]); li = s0 + int(np.argmin(l[s0:i + 1])); 顶 = h[li + 1:i + 1].max() if li < i else h[i]
            tp = 顶位[i]; 量比 = v20[i] / np.nanmax(v20[tp:i + 1]) if i > tp else np.nan
            box = dict(品种=sym, 起=i, 进箱=str(idx[i].date()), 箱底=l[li], 箱顶=顶, 大顶日=str(idx[tp].date()), 大顶价=c[tp], 离大顶=i - tp, 量比=量比, 派=False, 派天=0, 首派=None, 派日=[])
        if box is not None and st[i] != "筑底期":
            box.update(止=i, 出箱=str(idx[i].date()), 天数=i - box["起"], 出箱后=st[i], 方向="向上" if st[i] in ("涨势", "涨势·中继", "转涨期") else "破位" if st[i] == "跌势" else st[i]); boxes.append(box); box = None
        if box is None: continue
        hs = [j for j in SH if box["起"] - 60 <= j and j + 5 <= i]; ls = [j for j in SL if box["起"] - 60 <= j and j + 5 <= i]
        if len(hs) >= 2:
            top = max(h[j] for j in hs); last = h[hs[-1]]
            ok = last <= top - 派 * atr[i] and s150[i] < s150[i - 20]
            if ok and 底距 is not None: ok = len(ls) >= 1 and (l[ls[-1]] - box["箱底"]) <= 底距 * atr[i] and c[i] < s150[i]
            if ok: box["派"] = True
            if h[hs[-1]] > h[hs[-2]] or (len(ls) >= 2 and l[ls[-1]] > l[ls[-2]] and ls[-1] > hs[-1]): box["派"] = False
            if 底距 is not None and box["派"] and not (len(ls) >= 1 and (l[ls[-1]] - box["箱底"]) <= 底距 * atr[i] and c[i] < s150[i]): box["派"] = False
        if box["派"]:
            box["派天"] += 1; 派日[i] = True; box["派日"].append(i)
            if box["首派"] is None: box["首派"] = str(idx[i].date())
    if box is not None: box.update(止=n - 1, 出箱="还在箱里", 天数=n - 1 - box["起"], 出箱后="", 方向="还在箱里"); boxes.append(box)
    # 首箱：大顶之后的第一个箱子
    for b in boxes: b["首箱"] = not any(o_["起"] < b["起"] and o_["起"] >= idx.get_loc(pd.Timestamp(b["大顶日"])) for o_ in boxes)
    return D, R, boxes, 派日, atr


def 第2到4件():
    rows = []; 派表 = []
    for s in ("BTC", "ETH", "SPY", "QQQ", "SOXX"):
        D, R, B, _, _ = 箱子们(s); idx = D.index
        for b in B:
            r = {k: b[k] for k in ("品种", "进箱", "出箱", "天数", "方向", "箱底", "箱顶", "大顶日", "大顶价", "离大顶", "量比", "首箱", "派天", "首派")}
            门们 = (150, 180, 210) if s in 币 else (90, 120, 150)
            for g in 门们:
                r[f"过门槛{g}"] = b["离大顶"] >= g
                r[f"过门槛{g}的日子"] = str(idx[b["起"] + g - b["离大顶"]].date()) if b["离大顶"] < g and b["起"] + g - b["离大顶"] <= b["止"] else ("进箱就过了" if b["离大顶"] >= g else "出箱前没过")
            for q in (0.35, 0.45, 0.55): r[f"量缩{q}"] = bool(b["量比"] < q) if not np.isnan(b["量比"]) else False
            rows.append(r)
        for 档名, 底距 in (("不加", None), ("0.5", 0.5), ("0.8", 0.8), ("1.2", 1.2)):
            _, _, B2, 派日, _ = 箱子们(s, 底距=底距)
            for b in B2:
                派表.append(dict(品种=s, 进箱=b["进箱"], 方向=b["方向"], 天数=b["天数"], 再派发档=档名, 派天=b["派天"], 首派=b["首派"],
                                 派日_2018_06_08到11_16=int(sum(1 for i in b["派日"] if pd.Timestamp("2018-06-08") <= idx[i] <= pd.Timestamp("2018-11-16"))) if s == "BTC" else None))
    T = pd.DataFrame(rows); T.to_csv(os.path.join(OUT, "全部箱子.csv"), index=False)
    P = pd.DataFrame(派表); P.to_csv(os.path.join(OUT, "再派发四档.csv"), index=False)
    return T, P


def 均线退路A(sym, 止损=0.4, 目标R=3.0, 拿=60):
    D, R, B, _, atr = 箱子们(sym); o, h, l, c = (D[x].to_numpy(float) for x in ("open", "high", "low", "close")); n = len(c); idx = D.index
    st = R["档"].to_numpy(); s50 = pd.Series(c).rolling(50).mean().to_numpy(); s150 = pd.Series(c).rolling(150).mean().to_numpy(); e20 = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy()
    箱of = {}
    for b in B:
        for i in range(b["起"], b["止"]): 箱of[i] = b
    out = []; busy = -1
    for i in range(160, n - 1):
        if st[i] != "筑底期" or i <= busy or i not in 箱of: continue
        if not (s50[i] < s50[i - 10] and c[i] < s150[i]): continue
        lo_b = min(e20[i], s50[i]) - 0.2 * atr[i]; hi_b = max(e20[i], s50[i]) + 0.2 * atr[i]
        if not (max(h[i], h[i - 1]) >= lo_b and max(h[i], h[i - 1]) <= hi_b): continue
        if not (c[i] < o[i] and c[i] < l[i - 1]): continue
        E = c[i]; S = h[i - 4:i + 1].max() + 止损 * atr[i]; Rk = S - E
        if Rk <= 0: continue
        res = None; end = min(i + 拿, n - 1)
        for j in range(i + 1, end + 1):
            if h[j] >= S: res = -(max(o[j], S) - E) / Rk; break
            if l[j] <= E - 目标R * Rk: res = 目标R; break
        if res is None: res = (E - c[end]) / Rk
        busy = j; b = 箱of[i]
        out.append(dict(品种=sym, 日=str(idx[i].date()), 进箱=b["进箱"], 箱子方向=b["方向"], R=res - 2 * FEE * E / Rk, 收益pct=(res * Rk - 2 * FEE * E) / E * 100, 风险pct=Rk / E * 100, 拿了几天=j - i))
    return out


if __name__ == "__main__":
    pd.set_option("display.width", 260); pd.set_option("display.max_rows", 400); pd.set_option("display.max_columns", 40)
    T, P = 第2到4件()
    print(T.drop(columns=[c for c in T.columns if c.endswith("的日子")]).round(2).to_string(index=False))
    rows = []
    for s in ("BTC", "ETH", "SPY", "QQQ", "SOXX"):
        for kn, kw in (("默认", {}), ("止损0.3", {"止损": 0.3}), ("止损0.5", {"止损": 0.5}), ("目标2R", {"目标R": 2.0}), ("拿40天", {"拿": 40})):
            rows += [dict(r, 参数=kn) for r in 均线退路A(s, **kw)]
    A = pd.DataFrame(rows); A.to_csv(os.path.join(OUT, "均线退路A_逐笔.csv"), index=False)
    print(A[A.参数 == "默认"].round(2).to_string(index=False))
    print("DONE")
