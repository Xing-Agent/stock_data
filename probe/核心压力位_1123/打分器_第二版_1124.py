# -*- coding: utf-8 -*-
"""核心压力位打分器 · 第二版 · BTC / ETH（《428》第四节说的三处改法）· 引擎外
① 同一大类只计一次：一个带里的压力按大类归并（水平位 / 趋势线 / 斐波 / 均线和 VWAP / 缺口），「核心」= 至少跨 N 大类（N = 2 / 3 / 4 各跑）。
   筹码峰、4 小时前高、整数关口不算大类，只当加分（不参与「跨几类」）。
② 扳机两种，分开统计：
   「冲进没过」= 某根 1 小时线最高进了核心带、收盘收回带下沿之下、上影线 ≥ 整根一半（同第一版）；止损 = 那根最高 + 缓冲。
   「假突破收回」= 1 小时收盘站上核心带上沿，之后 48 根内又有一根收盘收回带下沿之下；止损 = 这段假突破的最高价 + 缓冲。← Lin 2026-09-21 那笔是这种
   都是信号那根收盘后、下一根开盘进；跳空越过止损按开盘价记。
③ 按大周期档分开报（五档第四版，日线；ETH 用 BTC 的档）。
出场三种并排：到 2R / 到 3R / 拿满 240 小时。成本单边 0.05%。缓冲 0.2 倍 1 小时 ATR。
对照：把每个核心带整体挪 ±2.5 倍日线 ATR。
锁数据：2022–2025 的单子单独存，不打印、不进统计。
每天的压力位沿用第一版算好的（只用前一天及以前的日线、小时线）。"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); FEE = 0.0005
sp = importlib.util.spec_from_file_location("v1", os.path.join(HERE, "打分器_1123.py")); V1 = importlib.util.module_from_spec(sp); sp.loader.exec_module(V1)
大类 = {"前高": "水平", "支撑变压力": "水平", "大阴线起点": "水平", "趋势线": "趋势线", "斐波0.5": "斐波", "斐波0.618": "斐波", "斐波0.382": "斐波", "均线": "均线", "锚定VWAP": "均线", "缺口": "缺口"}
def 核心(z, N): return len({大类[k] for k in z["有"] if k in 大类}) >= N
def 回放(H, 带, N=3, 扳机="没过", 缓冲=0.2, 挪=0.0, 窗=48):
    o, h, l, c = (H[x].to_numpy(float) for x in ("open", "high", "low", "close")); n = len(H); t = H.index
    pc = np.roll(c, 1); pc[0] = c[0]; a1 = pd.Series(np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc)))).rolling(14).mean().to_numpy()
    day = t.normalize(); R = []; busy = -1; arm = None
    def 记(i, stop, z, b):
        e = o[i + 1]; r = stop - e
        if r <= 0 or r / e < 0.001: return None
        res = {"t": t[i + 1], "进": e, "止损": stop, "R占价pct": r / e * 100, "几类": len({大类[k] for k in z["有"] if k in 大类}), "分": z["分"], "档": b["档"], "带下沿": z["lo"], "带上沿": z["hi"], "有": "|".join(z["有"])}
        for nm, tg in (("2R", 2), ("3R", 3), ("拿满", None)):
            out = None; end = min(n - 1, i + 240)
            for j in range(i + 1, end + 1):
                if h[j] >= stop: out = -(o[j] - e) / r if o[j] > stop else -1.0; res["出_" + nm] = "止损"; break
                if tg and l[j] <= e - tg * r: out = float(tg); res["出_" + nm] = "目标"; break
            if out is None: out = (e - c[end]) / r; res["出_" + nm] = "到时间"
            res["R_" + nm] = out - 2 * FEE * e / r; res["到头_" + nm] = j if out is not None and "止损" == res["出_" + nm] else end
        res["之后240小时最多跌pct"] = (l[i + 1:min(n, i + 241)].min() / e - 1) * 100
        return res
    for i in range(20, n - 2):
        b = 带.get(day[i])
        if b is None: continue
        Z = [z for z in b["zones"] if 核心(z, N)]
        if 扳机 == "没过":
            if i <= busy: continue
            rng = h[i] - l[i]
            if rng <= 0 or (h[i] - max(o[i], c[i])) < 0.5 * rng: continue
            for z in Z:
                lo = z["lo"] + 挪 * b["atr"]; hi = z["hi"] + 挪 * b["atr"]
                if lo > 0 and lo <= h[i] <= hi + 0.5 * b["atr"] and c[i] < lo and h[i - 1] < hi + 0.5 * b["atr"]:
                    res = 记(i, h[i] + 缓冲 * a1[i], z, b)
                    if res: R.append(res); busy = res["到头_拿满"]
                    break
        else:
            if arm is not None:
                arm["peak"] = max(arm["peak"], h[i])
                if c[i] < arm["lo"]:
                    if i > busy:
                        res = 记(i, arm["peak"] + 缓冲 * a1[i], arm["z"], arm["b"])
                        if res: res["假突破走了几小时"] = i - arm["i0"]; res["假突破最高比上沿高pct"] = (arm["peak"] / arm["hi"] - 1) * 100; R.append(res); busy = res["到头_拿满"]
                    arm = None
                elif i - arm["i0"] > 窗: arm = None
            if arm is None:
                for z in Z:
                    lo = z["lo"] + 挪 * b["atr"]; hi = z["hi"] + 挪 * b["atr"]
                    if lo > 0 and c[i] > hi and c[i - 1] <= hi and c[i] <= hi + 1.5 * b["atr"]:
                        arm = {"lo": lo, "hi": hi, "peak": h[i], "i0": i, "z": z, "b": b}; break
    return pd.DataFrame(R)
def S(x, col="R_3R"):
    if not len(x): return {"笔数": 0}
    r = x[col]; r3 = r.sort_values().iloc[:-3] if len(r) > 6 else r
    return {"笔数": int(len(x)), "每笔净R": round(float(r.mean()), 3), "胜率pct": round(float((r > 0).mean() * 100), 1), "利润因子": round(float(r[r > 0].sum() / max(1e-9, -r[r < 0].sum())), 2), "去掉最赚3笔后": round(float(r3.mean()), 3),
            "止损离进场pct_中位": round(float(x["R占价pct"].median()), 2), "t": round(float(r.mean() / (r.std() / np.sqrt(len(r)))), 2) if len(r) > 5 and r.std() > 0 else None}
def 开(T): return T[~((T.t >= "2022-01-01") & (T.t <= "2025-12-31"))] if len(T) else T
if __name__ == "__main__":
    out = {}
    for sym in ("BTC", "ETH"):
        H = V1.小时线(sym); 带 = pd.read_pickle(os.path.join(HERE, "out", f"{sym}_每天的带.pkl")); H = H[H.index < max(带) + pd.Timedelta(days=1)]; o = {}
        for N in (2, 3, 4):
            nz = [sum(1 for z in b["zones"] if 核心(z, N)) for b in 带.values()]; o[f"跨{N}类_有核心带的天数占比pct"] = round(float(np.mean([x > 0 for x in nz]) * 100), 1); o[f"跨{N}类_平均每天几个"] = round(float(np.mean(nz)), 2)
            for trg in ("没过", "假突破"):
                T0 = 回放(H, 带, N=N, 扳机=trg); T = 开(T0)
                if N == 3 and len(T0): T0[(T0.t >= "2022-01-01") & (T0.t <= "2025-12-31")].to_csv(os.path.join(HERE, "out", f"二版_{sym}_{trg}_锁住的_不许看.csv"), index=False); T.to_csv(os.path.join(HERE, "out", f"二版_{sym}_{trg}_单子.csv"), index=False)
                C = 开(pd.concat([回放(H, 带, N=N, 扳机=trg, 挪=2.5), 回放(H, 带, N=N, 扳机=trg, 挪=-2.5)]))
                k = f"跨{N}类·{trg}"; o[k] = {"真位置": {c: S(T, c) for c in ("R_2R", "R_3R", "R_拿满")}, "对照": {c: S(C, c) for c in ("R_2R", "R_3R", "R_拿满")}}
                if len(T): o[k]["按档_3R"] = {str(a): S(g) for a, g in T.groupby("档")}; o[k]["按档_拿满"] = {str(a): S(g, "R_拿满") for a, g in T.groupby("档")}
                if len(C): o[k]["对照_按档_3R"] = {str(a): S(g) for a, g in C.groupby("档")}
                print(sym, k, "真", o[k]["真位置"]["R_3R"], "| 对照", {x: o[k]["对照"]["R_3R"].get(x) for x in ("笔数", "每笔净R")}, "| 按档", {a: (v["笔数"], v.get("每笔净R")) for a, v in o[k].get("按档_3R", {}).items()}, flush=True)
        out[sym] = o
    json.dump(out, open(os.path.join(HERE, "out", "二版_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    T = pd.read_csv(os.path.join(HERE, "out", "二版_BTC_假突破_单子.csv"), parse_dates=["t"]); print(T[T.t >= "2026-01-01"][["t", "进", "止损", "R占价pct", "几类", "档", "带下沿", "带上沿", "R_3R", "R_拿满", "出_拿满", "之后240小时最多跌pct"]].round(2).to_string())
