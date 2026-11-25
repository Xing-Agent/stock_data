# -*- coding: utf-8 -*-
"""反抽 20 日线没过再空 · 照《459 拍板》第 1、3 条加开关和过滤 · BTC / ETH · 引擎外
开关（三种并排）：「均线」= 原来的（收在 120 日线下、120 日线向下）；「状态机」= 五档第四版当天的档 ∈ {跌势, 见顶}，或 筑底期且进筑底期以来收盘冲出过箱顶（Lin 11-25）；「不加」。
过滤（《459》第 3 条，全部满足才空）：① 反弹天数 ≥ 比例 × 之前下跌天数，且 ≥ 4 天；② 碰线前 3 根日线里没有「实体 > 1.5 日 ATR 且收在当天振幅上 1/4」的大阳线；
      ③ 20 日线走平或向下（比 5 天前不高出 0.5%）；④ 只做 20 日线走平或向下以来的前 2 次反抽。
扳机：碰线（4 小时最高 ≥ 20 日线 − 0.25 日 ATR，近 6 根内）且这根 4 小时线收在 20 日线下、是看跌吞没或长上影（收在振幅下 30%）；期间收盘没有高出 20 日线 1 日 ATR。
止损 = 近 30 根 4 小时最高 + 0.3 × 4 小时 ATR。出场：止损 / 3R / 最多 60 根。成本单边 0.05%。2022–2025 封存。"""
import os, re, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sp = importlib.util.spec_from_file_location("k", os.path.join(HERE, "看九月那段_1125.py")); K = importlib.util.module_from_spec(sp); sp.loader.exec_module(K)
sp = importlib.util.spec_from_file_location("f", os.path.join(HERE, "反抽中轨没过_1125.py")); F0 = importlib.util.module_from_spec(sp); sp.loader.exec_module(F0)
FEE = 0.0005
def 状态可空(sym):
    R = pd.read_csv(os.path.join(ROOT, f"probe/大周期五档_1123/out4/{sym}_四版_每天的档.csv"), index_col=0, parse_dates=True); ok = []; top = None; 冲 = False
    for d, r in R.iterrows():
        why = str(r["切换原因"]) if isinstance(r["切换原因"], str) else ""
        m = re.search(r"箱顶 ([\d,]+)", why)
        if why.startswith("进筑底期") and m: top = float(m.group(1).replace(",", "")); 冲 = False
        if r["档"] != "筑底期": top = None; 冲 = False
        if top is not None and r["close"] > top: 冲 = True
        ok.append(r["档"] in ("跌势", "见顶") or (r["档"] == "筑底期" and 冲))
    return pd.Series(ok, index=R.index), R["档"]
def 跑(sym, 开关="状态机", 过滤=True, 比例=0.8):
    X = K.指标(K.四小时(sym)); X.index = X.index.tz_localize(None) if X.index.tz is not None else X.index
    o, h, l, c, a4 = (X[x].to_numpy(float) for x in ("open", "high", "low", "close", "atr")); n = len(X); t = X.index
    D = X.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last"}).dropna(); pc = D.close.shift(1)
    D["atr"] = pd.concat([D.high - D.low, (D.high - pc).abs(), (D.low - pc).abs()], axis=1).max(axis=1).rolling(14).mean(); D["ma"] = D.close.rolling(20).mean()
    m120 = D.close.rolling(120).mean(); 可, 档 = 状态可空(sym)
    reg = {"均线": (D.close < m120) & (m120 < m120.shift(20)), "状态机": 可.reindex(D.index).fillna(False), "不加": pd.Series(True, index=D.index)}[开关]
    平 = D.ma <= D.ma.shift(5) * 1.005; 段号 = (平 != 平.shift()).cumsum()
    rng_d = (D.high - D.low).replace(0, np.nan); 大阳 = ((D.close - D.open) > 1.5 * D.atr.shift(1)) & ((D.close - D.low) / rng_d >= 0.75); 近大阳 = 大阳.rolling(3).max().fillna(0).astype(bool)
    dl, dh = D.low.to_numpy(), D.high.to_numpy(); didx = D.index
    day = t.normalize(); pos = didx.searchsorted(day) - 1                     # 前一个已收盘日线在 D 里的位置
    R = []; busy = -1; 次数 = {}
    for i in range(200, n - 2):
        p = pos[i]
        if p < 130 or not bool(reg.iloc[p]): continue
        ma = D.ma.iloc[p]; ad = D.atr.iloc[p]
        if not (ma > 0 and ad > 0): continue
        rng = h[i] - l[i]
        if rng <= 0 or i <= busy: continue
        吞没 = c[i] < o[i] and c[i - 1] > o[i - 1] and c[i] <= o[i - 1] and o[i] >= c[i - 1]; 长上影 = (c[i] - l[i]) / rng <= 0.3 and (h[i] - max(o[i], c[i])) >= 0.4 * rng
        if not (吞没 or 长上影): continue
        if not (h[max(0, i - 6):i + 1].max() >= ma - 0.25 * ad and c[i] < ma and c[max(0, i - 12):i + 1].max() <= ma + 1.0 * ad): continue
        if 过滤:
            j0 = p - 40 + int(np.argmin(dl[p - 40:p + 1])); j1 = max(0, j0 - 60) + int(np.argmax(dh[max(0, j0 - 60):j0 + 1])); 弹 = p - j0; 跌 = j0 - j1
            if not (弹 >= 4 and 弹 >= 比例 * 跌): continue
            if bool(近大阳.iloc[p]): continue
            if not bool(平.iloc[p]): continue
            k_ = int(段号.iloc[p])
            if 次数.get(k_, 0) >= 2: continue
        e = o[i + 1]; stop = h[max(0, i - 30):i + 1].max() + 0.3 * a4[i]; r = stop - e
        if r <= 0 or r / e < 0.003: continue
        out = None; end = min(n - 1, i + 60)
        for j in range(i + 1, end + 1):
            if h[j] >= stop: out = -(max(o[j], stop) - e) / r if j > i + 1 else -1.0; break
            if l[j] <= e - 3 * r: out = 3.0; break
        if out is None: out = (e - c[end]) / r
        if 过滤: 次数[k_] = 次数.get(k_, 0) + 1
        busy = j; R.append(dict(sym=sym, t=t[i + 1], 档=档.get(didx[p], ""), 进=e, 止损=stop, R_3R=out - 2 * FEE * e / r, 最多顺R=(e - l[i + 1:min(n, i + 61)].min()) / r))
    return pd.DataFrame(R)
if __name__ == "__main__":
    out = {}
    for 开关 in ("均线", "状态机", "不加"):
        for 过滤, 比例 in ((False, 0.8), (True, 0.6), (True, 0.8), (True, 1.0)):
            tag = f"开关={开关}·" + (f"过滤·比例{比例}" if 过滤 else "不过滤")
            T = pd.concat([跑(s, 开关, 过滤, 比例) for s in ("BTC", "ETH")], ignore_index=True)
            if not len(T): out[tag] = {"全部": {"笔": 0}}; print(tag, "0 笔"); continue
            lock = (T.t >= "2022-01-01") & (T.t <= "2025-12-31"); T[lock].to_csv(os.path.join(HERE, "out", f"封存_反抽过滤_{tag}.csv"), index=False); T = T[~lock]; T.to_csv(os.path.join(HERE, "out", f"反抽过滤_{tag}.csv"), index=False)
            o_ = {"全部": F0.统计(T), "2017-2021": F0.统计(T[T.t < "2022-01-01"]), "2026": F0.统计(T[T.t >= "2026-01-01"]), "BTC": F0.统计(T[T.sym == "BTC"]), "ETH": F0.统计(T[T.sym == "ETH"])}
            out[tag] = o_; print(tag, {k: (v.get("笔"), v.get("每笔R"), v.get("胜率"), v.get("利润因子")) for k, v in o_.items()}, flush=True)
            if 开关 == "状态机" and 过滤 and 比例 == 0.8: print(T[(T.sym == "BTC") & (T.t >= "2026-09-01")].round(2).to_string())
    json.dump(out, open(os.path.join(HERE, "out", "反抽过滤_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
