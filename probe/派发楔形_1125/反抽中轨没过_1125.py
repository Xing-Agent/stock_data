# -*- coding: utf-8 -*-
"""跌势里反抽到日线 20 日线（布林中轨）没过再空 · 照《450 拍板》第 3 条写细 · BTC / ETH · 引擎外
大周期开关（《442》第 3 条的币版）：前一天收盘在 120 日线下，且 120 日线比 20 天前低。
到位：价格先在中轨下方收了至少 3 天，之后某天最高 ≥ 中轨 − 0.25 日 ATR。
没过（按收盘认）：到位当天或之后 2 天内，有一天收在中轨下方；期间任何一天收盘 > 中轨 + 缓冲 × 日 ATR → 作废。
扳机（4 小时）：从到位那天起，到「没过」确认那天收盘后的 2 天内，第一根「看跌吞没」或「长上影（收在振幅下 30%）」且最高 ≥ 中轨 − 0.5 日 ATR 的 4 小时线
       —— 要求这根收盘时日线条件已经满足（当天日线还没收的，用这根 4 小时收盘 < 中轨代替）。下一根开盘空。
量（可开关）：反弹段（最近一个 4 小时低点到扳机）平均量 < 之前下跌段（前高到那个低点）平均量的 80%。
止损 = 这轮反弹最高 + 0.3 × 4 小时 ATR。出场：止损 / 到 3R / 最多 60 根 4 小时线；另记 2R、最多顺了几 R。成本单边 0.05%。
对照：同样的大周期、同样的 4 小时扳机形状，但不在中轨附近（离中轨 > 1.5 日 ATR）。
2022–2025 封存，单独存、不打印、不进统计。"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("k", os.path.join(HERE, "看九月那段_1125.py")); K = importlib.util.module_from_spec(sp); sp.loader.exec_module(K)
FEE = 0.0005
def 跑(sym, 缓冲=1.0, 看量=False, 均线="sma20"):
    X = K.指标(K.四小时(sym)); X.index = X.index.tz_localize(None) if X.index.tz is not None else X.index
    o, h, l, c, v, a4 = (X[x].to_numpy(float) for x in ("open", "high", "low", "close", "volume", "atr")); n = len(X); t = X.index
    D = X.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna(); pc = D.close.shift(1)
    D["atr"] = pd.concat([D.high - D.low, (D.high - pc).abs(), (D.low - pc).abs()], axis=1).max(axis=1).rolling(14).mean()
    D["ma"] = D.close.rolling(20).mean() if 均线 == "sma20" else D.close.ewm(span=int(均线[3:]), adjust=False).mean()
    m120 = D.close.rolling(120).mean(); D["跌势"] = (D.close < m120) & (m120 < m120.shift(20)); D["下方"] = (D.close < D.ma).rolling(3).sum() == 3
    day = t.normalize(); dm = D.ma.shift(1).reindex(day).to_numpy(); da = D.atr.shift(1).reindex(day).to_numpy(); reg = D["跌势"].shift(1).reindex(day).fillna(False).to_numpy(); 下 = D["下方"].shift(1).reindex(day).fillna(False).to_numpy()
    dclose_prev = D.close.shift(1).reindex(day).to_numpy()
    R = []; busy = -1; armed = -10**9; arm_hi = 0.0; 曾在下方 = False
    def 记(i, 类):
        e = o[i + 1]; hi = h[max(0, i - 30):i + 1].max(); stop = hi + 0.3 * a4[i]; r = stop - e
        if r <= 0 or r / e < 0.003: return None
        res = dict(sym=sym, 类=类, t=t[i + 1], 进=e, 止损=stop)
        for nm, tg in (("3R", 3), ("2R", 2)):
            out = None; end = min(n - 1, i + 60)
            for j in range(i + 1, end + 1):
                if h[j] >= stop: out = -(max(o[j], stop) - e) / r if j > i + 1 else -1.0; break
                if l[j] <= e - tg * r: out = float(tg); break
            if out is None: out = (e - c[end]) / r
            res["R_" + nm] = out - 2 * FEE * e / r; res["到头"] = j
        res["最多顺R"] = (e - l[i + 1:min(n, i + 61)].min()) / r; return res
    for i in range(200, n - 2):
        if not reg[i] or not (dm[i] > 0) or not (da[i] > 0): continue
        if 下[i]: 曾在下方 = True
        rng = h[i] - l[i]
        if rng <= 0: continue
        吞没 = c[i] < o[i] and c[i - 1] > o[i - 1] and c[i] <= o[i - 1] and o[i] >= c[i - 1]
        长上影 = (c[i] - l[i]) / rng <= 0.3 and (h[i] - max(o[i], c[i])) >= 0.4 * rng
        if not (吞没 or 长上影): continue
        近 = h[max(0, i - 6):i + 1].max() >= dm[i] - 0.25 * da[i]              # 最近一天碰到过中轨
        没过 = c[i] < dm[i] and h[max(0, i - 12):i + 1].max() <= dm[i] + 缓冲 * da[i] + 1e-9 and c[max(0, i - 12):i + 1].max() <= dm[i] + 缓冲 * da[i]
        if 近 and 没过 and 曾在下方:
            if 看量:
                j0 = i - 30 + int(np.argmin(l[i - 30:i + 1])); j1 = max(0, j0 - 30) + int(np.argmax(h[max(0, j0 - 30):j0 + 1]))
                if j0 >= i or j1 >= j0 or not (v[j0:i + 1].mean() < 0.8 * v[j1:j0 + 1].mean()): continue
            if i > busy:
                res = 记(i, "中轨没过")
                if res: R.append(res); busy = res["到头"]; 曾在下方 = False
        elif abs(h[i] - dm[i]) > 1.5 * da[i] and c[i] < dm[i]:
            res = 记(i, "对照")
            if res: R.append(res)
    return pd.DataFrame(R)
def 统计(x, col="R_3R"):
    x = x[col].dropna()
    if not len(x): return {"笔": 0}
    return {"笔": int(len(x)), "每笔R": round(float(x.mean()), 2), "胜率": round(float((x > 0).mean()), 2), "利润因子": round(float(x[x > 0].sum() / max(1e-9, -x[x <= 0].sum())), 2), "去掉最赚3笔": round(float(x.sort_values().iloc[:-3].mean()), 2) if len(x) > 5 else None, "t": round(float(x.mean() / x.std() * np.sqrt(len(x))), 1) if len(x) > 2 and x.std() > 0 else None}
if __name__ == "__main__":
    out = {}
    for tag, kw in (("默认", {}), ("缓冲0.5", {"缓冲": 0.5}), ("缓冲1.5", {"缓冲": 1.5}), ("看量", {"看量": True}), ("EMA20", {"均线": "ema20"}), ("EMA21", {"均线": "ema21"})):
        T = pd.concat([跑(s, **kw) for s in ("BTC", "ETH")], ignore_index=True); lock = (T.t >= "2022-01-01") & (T.t <= "2025-12-31")
        T[lock].to_csv(os.path.join(HERE, "out", f"封存_反抽_{tag}.csv"), index=False); T = T[~lock]; T.to_csv(os.path.join(HERE, "out", f"反抽_{tag}.csv"), index=False)
        o_ = {}
        for g, x in T.groupby("类"):
            o_[g] = {"全部": 统计(x), "2R": 统计(x, "R_2R"), "2017-2021": 统计(x[x.t < "2022-01-01"]), "2026": 统计(x[x.t >= "2026-01-01"]), "BTC": 统计(x[x.sym == "BTC"]), "ETH": 统计(x[x.sym == "ETH"])}
        out[tag] = o_; print(tag, json.dumps(o_, ensure_ascii=False), flush=True)
        if tag == "默认": print(T[(T.类 == "中轨没过") & (T.sym == "BTC") & (T.t >= "2026-10-01")].round(2).to_string())
    json.dump(out, open(os.path.join(HERE, "out", "反抽_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
