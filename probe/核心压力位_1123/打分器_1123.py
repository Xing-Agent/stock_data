# -*- coding: utf-8 -*-
"""核心压力位打分器 + 窄止损的第一笔（左侧）· 第一版 · 照《410+411 拍板》第 5~7 条、《422 拍板》防自欺六条 · 引擎外 · BTC / ETH
每天（UTC）开始前，只用前一天及以前已收盘的数据，算出上方 25% 以内有哪些压力位，相差 0.5 倍日线 ATR 以内的并成一个带、打分：
  水平位：日线前高 2.5；支撑变压力（被收盘跌破的日线摆动低点）2.5；跌破平台那根大阴线的起点 1.5★；4 小时前高 1.0；整数关口 0.5
  趋势线：最近两个依次降低的日线摆动高点连线延长到今天 2.0
  斐波：最近一段大跌（250 天内最高的摆动高点 → 之后最低点）的 0.5 / 0.618 各 1.8，0.382 是 1.2
  均线和 VWAP：50 日 / 200 日 / 20 周均线，挤在一个带里只算一条 1.5；从这轮最高点、从跌破日起算的锚定 VWAP 1.5★
  缺口：日线上没补完的向下空档（FVG：前一根的最低 > 后一根的最高）1.5
  筹码峰：最近 180 天小时成交量按价格分桶，上方量最大的 3 个桶 2.0
核心 = 总分 ≥ 5（跌势里 4.5）、至少 3 样、跨至少 2 大类。同一样在一个带里只计一次。
★ = 拍板说要加但没给权重，我先放 1.5。
第一笔（左侧）：某根 1 小时线最高价进了核心带、收盘收回带下沿之下、上影线 ≥ 整根一半 → 下一根开盘空。
止损 = 那根最高价 + 缓冲 × 1 小时 ATR（缓冲 0 / 0.2 / 0.5）；跳空越过止损按开盘价记。
出场（先用最朴素的，三种并排）：到 2R 平 / 到 3R 平 / 拿满 240 小时；都带止损。成本单边 0.05%。
随机对照：把每个核心带整体挪 ±2.5 倍日线 ATR（上、下各一份），同样的扳机、同样的止损。
锁数据：2022-01-01 ~ 2025-12-31 的单子照算、单独存，**不打印、不进任何统计**。
"""
import os, sys, glob, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); FEE = 0.0005
sp = importlib.util.spec_from_file_location("m4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py")); M4 = importlib.util.module_from_spec(sp); sp.loader.exec_module(M4)
W = {"前高": 2.5, "支撑变压力": 2.5, "大阴线起点": 1.5, "4小时前高": 1.0, "整数关口": 0.5, "趋势线": 2.0, "斐波0.5": 1.8, "斐波0.618": 1.8, "斐波0.382": 1.2, "均线": 1.5, "锚定VWAP": 1.5, "缺口": 1.5, "筹码峰": 2.0}
CAT = {"前高": "水平", "支撑变压力": "水平", "大阴线起点": "水平", "4小时前高": "水平", "整数关口": "水平", "趋势线": "趋势线", "斐波0.5": "斐波", "斐波0.618": "斐波", "斐波0.382": "斐波", "均线": "均线", "锚定VWAP": "均线", "缺口": "缺口", "筹码峰": "筹码"}

def 小时线(sym):
    fs = sorted(glob.glob(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/币_小时线_Coinbase/*.parquet")))
    d = pd.concat([pd.read_parquet(f) for f in fs]); d = d[d.symbol == sym]; d["t"] = pd.to_datetime(d.time_utc, utc=True).dt.tz_localize(None); d = d.set_index("t").sort_index()
    H = pd.DataFrame({"open": d.open_adj, "high": d.high_adj, "low": d.low_adj, "close": d.close_adj, "volume": d.volume_adj}).dropna(); return H[~H.index.duplicated()]

def 每天的带(H, D, 档, k=5, 并=0.5):
    o, h, l, c, v = (D[x].to_numpy(float) for x in ("open", "high", "low", "close", "volume")); n = len(D); idx = D.index
    pc = np.roll(c, 1); pc[0] = c[0]; tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc))); atr = pd.Series(tr).rolling(14).mean().to_numpy()
    s50 = pd.Series(c).rolling(50).mean().to_numpy(); s200 = pd.Series(c).rolling(200).mean().to_numpy(); w20 = pd.Series(c).rolling(140).mean().to_numpy()
    H4 = H.resample("4h").agg({"high": "max", "low": "min", "close": "last"}).dropna(); h4h = H4.high.to_numpy(); h4t = H4.index
    p4 = [j for j in range(3, len(H4) - 3) if h4h[j] == h4h[j - 3:j + 4].max()]; p4t = np.array([h4t[j + 3] for j in p4]); p4v = np.array([h4h[j] for j in p4])
    hv = H.volume.to_numpy(float); hp = ((H.high + H.low + H.close) / 3).to_numpy(float); ht = H.index.values
    SH, SL = [], []; out = {}
    for i in range(n):
        j = i - k
        if j >= k:
            if h[j] == h[j - k:j + k + 1].max(): SH.append((i, j, h[j]))
            if l[j] == l[j - k:j + k + 1].min(): SL.append((i, j, l[j]))
        if i < 260 or not (atr[i] > 0): continue
        px = c[i]; a = atr[i]; top = px * 1.25; lv = []
        for (ci, jj, p) in SH:
            if jj >= i - 250 and px < p <= top: lv.append((p, "前高"))
        for (ci, jj, p) in SL:
            if jj >= i - 250 and px < p <= top and (c[jj + 1:i + 1] < p).any(): lv.append((p, "支撑变压力"))
        sh = [(jj, p) for (ci, jj, p) in SH if jj >= i - 250]
        if len(sh) >= 2 and sh[-1][1] < sh[-2][1]:
            (j1, p1), (j2, p2) = sh[-2], sh[-1]; tl = p2 + (p2 - p1) / (j2 - j1) * (i + 1 - j2)
            if px < tl <= top: lv.append((tl, "趋势线"))
        if sh:
            jh, ph = max(sh, key=lambda x: x[1]); lo = l[jh:i + 1].min()
            if ph > lo * 1.1:
                for f, nm in ((0.382, "斐波0.382"), (0.5, "斐波0.5"), (0.618, "斐波0.618")):
                    p = lo + f * (ph - lo)
                    if px < p <= top: lv.append((p, nm))
                # 锚定 VWAP：从这轮最高点那天起
                seg = slice(jh, i + 1); tv = (c[seg] * v[seg]).sum() / max(v[seg].sum(), 1e-9)
                if px < tv <= top: lv.append((tv, "锚定VWAP"))
        for p in (s50[i], s200[i], w20[i]):
            if p > 0 and px < p <= top: lv.append((p, "均线"))
        for jj in range(max(1, i - 120), i):                      # 向下空档：jj-1 的最低 > jj+1 的最高，且之后收盘没回到空档上沿
            if jj + 1 <= i and l[jj - 1] > h[jj + 1]:
                zl, zh = h[jj + 1], l[jj - 1]
                if (h[jj + 2:i + 1] < zh).all() if jj + 2 <= i else True:
                    mid = (zl + zh) / 2
                    if px < mid <= top: lv.append((mid, "缺口"))
                if (o[jj] - c[jj]) > 1.5 * atr[jj] and px < o[jj] <= top: lv.append((o[jj], "大阴线起点"))
        step = 10 ** np.floor(np.log10(px)); step = step if px / step >= 2 else step / 2
        p = np.ceil(px / step) * step
        while p <= top: lv.append((p, "整数关口")); p += step
        t1 = idx[i] + pd.Timedelta(days=1); m = (p4t <= t1) & (p4t >= t1 - pd.Timedelta(days=30))
        for p in p4v[m]:
            if px < p <= top: lv.append((float(p), "4小时前高"))
        a0 = np.searchsorted(ht, np.datetime64(t1 - pd.Timedelta(days=180))); a1 = np.searchsorted(ht, np.datetime64(t1))
        if a1 - a0 > 500:
            bins = np.arange(px, top + a * 0.5, a * 0.5)
            if len(bins) > 3:
                hist, ed = np.histogram(hp[a0:a1], bins=bins, weights=hv[a0:a1])
                for b in np.argsort(hist)[-3:]:
                    if hist[b] > 0: lv.append(((ed[b] + ed[b + 1]) / 2, "筹码峰"))
        lv.sort(); zones = []; cur = []
        for p, nm in lv:
            if cur and p - cur[0][0] > 并 * a: zones.append(cur); cur = []
            cur.append((p, nm))
        if cur: zones.append(cur)
        need = 4.5 if 档[i] == "跌势" else 5.0; Z = []
        for z in zones:
            kinds = {}
            for p, nm in z: kinds.setdefault("均线" if nm == "均线" else nm, p)
            sc = sum(W[x] for x in kinds); cats = {CAT[x] for x in kinds}
            Z.append({"lo": z[0][0], "hi": z[-1][0], "分": round(sc, 1), "几样": len(kinds), "几类": len(cats), "有": sorted(kinds), "核心": bool(sc >= need and len(kinds) >= 3 and len(cats) >= 2)})
        out[idx[i] + pd.Timedelta(days=1)] = {"zones": Z, "atr": a, "档": 档[i]}
    return out

def 回放(H, 带, 缓冲=0.2, 挪=0.0):
    o, h, l, c = (H[x].to_numpy(float) for x in ("open", "high", "low", "close")); n = len(H); t = H.index
    pc = np.roll(c, 1); pc[0] = c[0]; a1 = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14).mean().to_numpy()
    day = t.normalize(); R = []; busy_until = -1
    for i in range(20, n - 2):
        if i <= busy_until: continue
        b = 带.get(day[i])
        if b is None: continue
        rng = h[i] - l[i]
        if rng <= 0 or (h[i] - max(o[i], c[i])) < 0.5 * rng: continue
        for z in b["zones"]:
            if not z["核心"]: continue
            lo = z["lo"] + 挪 * b["atr"]; hi = z["hi"] + 挪 * b["atr"]
            if 挪 != 0 and not (lo > 0): continue
            if h[i] >= lo and h[i] <= hi + 0.5 * b["atr"] and c[i] < lo and h[i - 1] < hi + 0.5 * b["atr"]:
                e = o[i + 1]; stop = h[i] + 缓冲 * a1[i]; r = stop - e
                if r <= 0 or r / e < 0.001: continue
                res = {"t": t[i + 1], "进": e, "止损": stop, "R占价pct": r / e * 100, "分": z["分"], "几样": z["几样"], "档": b["档"], "有": "|".join(z["有"])}
                for nm, tg in (("2R", 2), ("3R", 3), ("拿满", None)):
                    out = None; end = min(n - 1, i + 240)
                    for j in range(i + 1, end + 1):
                        if h[j] >= stop: out = -(max(o[j], stop) - e) / r if o[j] > stop else -1.0; res["出_" + nm] = "止损"; break
                        if tg and l[j] <= e - tg * r: out = float(tg); res["出_" + nm] = "目标"; break
                    if out is None: out = (e - c[end]) / r; res["出_" + nm] = "到时间"
                    res["R_" + nm] = out - 2 * FEE * e / r
                    if nm == "拿满": busy_until = j if "止损" == res["出_拿满"] else end
                R.append(res); break
    return pd.DataFrame(R)

def S(x, col="R_3R"):
    if not len(x): return {"笔数": 0}
    r = x[col]; top3 = r.sort_values().iloc[:-3] if len(r) > 6 else r
    return {"笔数": int(len(x)), "每笔净R": round(float(r.mean()), 3), "胜率pct": round(float((r > 0).mean() * 100), 1), "利润因子": round(float(r[r > 0].sum() / max(1e-9, -r[r < 0].sum())), 2),
            "去掉最赚3笔后每笔": round(float(top3.mean()), 3), "止损占价pct_中位": round(float(x["R占价pct"].median()), 2), "t": round(float(r.mean() / (r.std() / np.sqrt(len(r)))), 2) if len(r) > 5 and r.std() > 0 else None}

if __name__ == "__main__":
    out = {}
    for sym in ("BTC", "ETH"):
        D = M4.币日线(sym); H = 小时线(sym); H = H[H.index < D.index[-1] + pd.Timedelta(days=1)]
        R4, _ = M4.跑(M4.币日线("BTC"), M4.P币); 档 = R4["档"].reindex(D.index).ffill().fillna("历史不够").to_numpy()      # ETH 用 BTC 的档（Lin：方向跟 BTC）
        带 = 每天的带(H, D, 档)
        nz = [sum(1 for z in b["zones"] if z["核心"]) for b in 带.values()]; o = {"有核心带的天数占比pct": round(float(np.mean([x > 0 for x in nz]) * 100), 1), "平均每天几个核心带": round(float(np.mean(nz)), 2)}
        pd.to_pickle(带, os.path.join(HERE, "out", f"{sym}_每天的带.pkl"))
        for buf in (0.0, 0.2, 0.5):
            T = 回放(H, 带, 缓冲=buf); lock = (T.t >= "2022-01-01") & (T.t <= "2025-12-31")
            T[lock].to_csv(os.path.join(HERE, "out", f"{sym}_锁住的单子_缓冲{buf}_不许看.csv"), index=False); T = T[~lock]; T.to_csv(os.path.join(HERE, "out", f"{sym}_单子_缓冲{buf}.csv"), index=False)
            C = pd.concat([回放(H, 带, 缓冲=buf, 挪=+2.5), 回放(H, 带, 缓冲=buf, 挪=-2.5)]); C = C[~((C.t >= "2022-01-01") & (C.t <= "2025-12-31"))]
            o[f"缓冲{buf}"] = {"真位置": {k: S(T, k) for k in ("R_2R", "R_3R", "R_拿满")}, "挪开的对照": {k: S(C, k) for k in ("R_2R", "R_3R", "R_拿满")}}
            if buf == 0.2:
                o["按档_3R"] = {str(a): S(g) for a, g in T.groupby("档")}; o["按分数_3R"] = {str(a): S(g) for a, g in T.groupby(pd.cut(T["分"], [0, 6, 8, 99], labels=["5~6", "6~8", "8 以上"]))}
                o["按时间_3R"] = {str(a): S(g) for a, g in T.groupby(T.t.dt.year)}; o["对照_按档_3R"] = {str(a): S(g) for a, g in C.groupby("档")}
        out[sym] = o; print("==", sym, json.dumps(o, ensure_ascii=False, default=str)[:6000])
    json.dump(out, open(os.path.join(HERE, "out", "汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
