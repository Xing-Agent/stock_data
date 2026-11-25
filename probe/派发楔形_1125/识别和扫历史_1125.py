# -*- coding: utf-8 -*-
"""派发楔形（急拉后顶压平、底抬高）· 识别 + 扫历史 · 照《450 拍板》· BTC / ETH · 4 小时线 · 引擎外 · 只读
每一步只用当时已经收盘的 K 线。2022-01-01 ~ 2025-12-31 的单独存 out/封存_*.csv，不打印、不进统计。
认定（在第 t 根 4 小时线收盘时判）：
  急拉日：当天最高 − 前收 ≥ 急拉倍 × 日线 ATR14，且量 ≥ 1.5 × 20 日均量（1.5 是我补的）。首顶 = 急拉日起 2 天内的最高点。
  盖子：之后没有 4 小时收盘站上 首顶 + 0.4 ATR（站上 = 作废）。
  顶：首顶之后、离首顶不超过 1.5 ATR 的分形高点（左右各 3 根）；含首顶至少 3 个；末顶 − 首顶 ≥ 下限 × ATR。
  底：首顶之后最低的那个分形低点当起点，之后的分形低点至少 2 个且一个比一个高。下轨 = 起点低点和最后一个低点的连线。
  量：末顶「前后各一根共三根」的量 < 首顶的 75%。RSI：末顶 < 首顶。长度：首顶起 ≥ 最少根，≤ 120 根。
  （「阴线总量 > 阳线总量」Lin 11-25 定先拿掉；另记「量最大 10 根里收跌的占比」。）ATR 都用首顶那根的 4 小时 ATR14。
单子：
  左侧：形态已成立（上面全满足）之后，某根 4 小时线最高进了盖子（≥ 首顶 − 1 ATR）、收在振幅下 1/3 → 下一根开盘空。止损 = 形态最高 + 0.3 ATR。
        退出另一种（Lin）：之后任何一根收盘高过进场那根的最高 → 平。
  右侧·追：4 小时收盘 < 下轨 − 跌破倍 × ATR 且 < 最后一个低点，阴线实体 ≥ 振幅 60% → 下一根开盘空。止损 = 最后一个顶 + 0.3 ATR。
  右侧·反抽：跌破之后 30 天内，日线最高碰到 20 日线（≥ 中轨 − 0.25 日 ATR），且当天收在中轨下，或收在中轨上但 2 天内又收回中轨下 → 确认那天的下一根 4 小时开盘空。
        止损 = 这轮反弹最高 + 0.3 ATR。每个形态最多 3 次。
  出场统一：止损 / 到 3R / 拿满 60 根 4 小时线（10 天），成本单边 0.05%。同时记 2R。
"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("k", os.path.join(HERE, "看九月那段_1125.py")); K = importlib.util.module_from_spec(sp); sp.loader.exec_module(K)
FEE = 0.0005
def 扫(sym, 急拉倍=2.5, 最少根=36, 下限=-0.8, 跌破倍=0.35, 中轨缓冲=1.0, N=3):
    X = K.指标(K.四小时(sym)); X.index = X.index.tz_localize(None) if X.index.tz is not None else X.index
    o, h, l, c, v, atr, rsi = (X[x].to_numpy(float) for x in ("open", "high", "low", "close", "volume", "atr", "rsi")); n = len(X); t = X.index
    D = X.resample("1D").agg({"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}).dropna()
    pc = D.close.shift(1); D["atr"] = pd.concat([D.high - D.low, (D.high - pc).abs(), (D.low - pc).abs()], axis=1).max(axis=1).rolling(14).mean(); D["ma"] = D.close.rolling(20).mean(); D["v20"] = D.volume.rolling(20).mean().shift(1)
    spike = D[((D.high - pc) >= 急拉倍 * D.atr.shift(1)) & (D.volume >= 1.5 * D.v20)].index
    def 出(i, e, stop):
        r = stop - e
        if r <= 0 or r / e < 0.002: return None
        res = {}
        for nm, tg in (("3R", 3), ("2R", 2)):
            out = None; end = min(n - 1, i + 59)
            for j in range(i, end + 1):
                if h[j] >= stop: out = -(max(o[j], stop) - e) / r if j > i else -1.0; break
                if l[j] <= e - tg * r: out = float(tg); break
            if out is None: out = (e - c[end]) / r
            res["R_" + nm] = out - 2 * FEE * e / r
        res["最多顺R"] = (e - l[i:min(n, i + 60)].min()) / r; return res
    PAT, TR = [], []; last_end = -1
    for d in spike:
        i0 = X.index.searchsorted(d); i1 = min(n - 1, X.index.searchsorted(d + pd.Timedelta(days=2)))
        if i0 <= last_end or i1 - i0 < 6: continue
        f = i0 + int(np.argmax(h[i0:i1])); A = atr[f]; top0 = h[f]
        if not (A > 0): continue
        vol3 = lambda j: v[max(0, j - 1):j + 2].sum()
        ok_at = None; brk = None; left = []; tops = [f]; lows = []
        for j in range(f + 1, min(n - 1, f + 121)):
            if c[j] > top0 + 0.4 * A: break                                   # 站上盖子，作废
            k = j - N                                                          # 这一根收盘时，第 j−N 根的分形才确认
            if k > f + N:
                if h[k] == h[k - N:k + N + 1].max() and h[k] >= top0 - 1.5 * A and k not in tops: tops.append(k)
                if l[k] == l[k - N:k + N + 1].min(): lows.append(k)
            good = False
            if len(tops) >= 3 and len(lows) >= 3 and j - f + 1 >= 最少根:
                a = min(lows, key=lambda q: l[q]); 后 = [q for q in lows if q > a]
                if len(后) >= 2 and all(l[后[m]] > l[后[m - 1]] for m in range(1, len(后))) and l[后[0]] > l[a]:
                    lt = tops[-1]
                    if 下限 * A <= h[lt] - top0 <= 0.4 * A and vol3(lt) < 0.75 * vol3(f) and rsi[lt] < rsi[f]:
                        good = True; b = 后[-1]; slope = (l[b] - l[a]) / (b - a); line = l[b] + slope * (j - b)
            if good and ok_at is None: ok_at = j
            if ok_at is not None and good:
                rng = h[j] - l[j]
                if rng > 0 and h[j] >= top0 - 1.0 * A and (c[j] - l[j]) / rng <= 1 / 3 and len(left) < 2 and (not left or j - left[-1] > 6): left.append(j)
                body = o[j] - c[j]
                if c[j] < line - 跌破倍 * A and c[j] < l[b] and rng > 0 and body >= 0.6 * rng: brk = j; break
        if ok_at is None: continue
        last_end = brk or ok_at; Z = slice(f, (brk or ok_at) + 1); big = np.argsort(v[Z])[-10:] + f
        P = dict(sym=sym, 急拉日=d, 首顶=t[f], 首顶价=top0, 成立=t[ok_at], 顶数=len(tops), 末顶减首顶ATR=(h[tops[-1]] - top0) / A, 跌破=(t[brk] if brk else None), 根数=(brk or ok_at) - f + 1,
                 量最大10根收跌占比=float(np.mean(c[big] < o[big])), 阴阳总量比=float(v[Z][c[Z] < o[Z]].sum() / max(1e-9, v[Z][c[Z] >= o[Z]].sum())))
        end = brk if brk else min(n - 1, f + 121)
        P["成立后20天最多跌pct"] = (l[ok_at:min(n, ok_at + 120)].min() / c[ok_at] - 1) * 100; P["成立后20天最多涨pct"] = (h[ok_at:min(n, ok_at + 120)].max() / c[ok_at] - 1) * 100
        if brk: P["跌破后20天最多跌pct"] = (l[brk:min(n, brk + 120)].min() / c[brk] - 1) * 100; P["跌破后20天最多涨pct"] = (h[brk:min(n, brk + 120)].max() / c[brk] - 1) * 100
        PAT.append(P)
        hi_all = h[f:end + 1].max()
        for j in left:
            if j + 1 >= n or (brk and j >= brk): continue
            e = o[j + 1]; r = 出(j + 1, e, hi_all if j >= end else max(h[f:j + 1].max(), top0) + 0.3 * A)
            if r:
                # Lin 的退出：之后收盘高过进场那根最高就平
                R2 = None; stop = max(h[f:j + 1].max(), top0) + 0.3 * A; rr = stop - e
                for q in range(j + 1, min(n, j + 61)):
                    if h[q] >= stop: R2 = -1.0; break
                    if l[q] <= e - 3 * rr: R2 = 3.0; break
                    if c[q] > h[j]: R2 = (e - c[q]) / rr; break
                if R2 is None: R2 = (e - c[min(n - 1, j + 60)]) / rr
                TR.append(dict(sym=sym, 类="左侧", t=t[j + 1], 首顶=t[f], 进=e, **r, R_反上来就平=R2 - 2 * FEE * e / rr))
        if brk and brk + 1 < n:
            e = o[brk + 1]; r = 出(brk + 1, e, h[tops[-1]] + 0.3 * A)
            if r: TR.append(dict(sym=sym, 类="右侧·追", t=t[brk + 1], 首顶=t[f], 进=e, **r))
            d0 = t[brk].normalize(); days = D.index[(D.index > d0) & (D.index <= d0 + pd.Timedelta(days=30))]; cnt = 0; pend = None; lastd = None
            for dd in days:
                r_ = D.loc[dd]
                if not (r_.ma > 0): continue
                if r_.close > r_.ma + 中轨缓冲 * r_.atr: break
                sig = False
                if pend is not None:
                    if r_.close < r_.ma: sig = True; pend = None
                    elif (dd - pend).days >= 2: pend = None
                elif r_.high >= r_.ma - 0.25 * r_.atr:
                    if r_.close < r_.ma: sig = True
                    else: pend = dd
                if sig and (lastd is None or (dd - lastd).days >= 3):
                    q = X.index.searchsorted(dd + pd.Timedelta(days=1))
                    if q >= n: break
                    e = o[q]; hi = h[max(0, q - 30):q].max(); r = 出(q, e, hi + 0.3 * A)
                    if r: cnt += 1; lastd = dd; TR.append(dict(sym=sym, 类=f"右侧·反抽{cnt}", t=t[q], 首顶=t[f], 进=e, **r))
                    if cnt >= 3: break
    return pd.DataFrame(PAT), pd.DataFrame(TR)
def 统计(x, col="R_3R"):
    x = x[col].dropna()
    if not len(x): return {"笔": 0}
    return {"笔": int(len(x)), "每笔R": round(float(x.mean()), 2), "胜率": round(float((x > 0).mean()), 2), "利润因子": round(float(x[x > 0].sum() / max(1e-9, -x[x <= 0].sum())), 2), "t": (round(float(x.mean() / x.std() * np.sqrt(len(x))), 1) if len(x) > 2 and x.std() > 0 else None)}
if __name__ == "__main__":
    kw = {}
    for a in sys.argv[1:]:
        k_, v_ = a.split("="); kw[k_] = float(v_) if "." in v_ or "-" in v_ else int(v_)
    tag = "_".join(f"{k}{v}" for k, v in kw.items()) or "默认"; P = []; T = []
    for s in ("BTC", "ETH"):
        p, tr = 扫(s, **kw); P.append(p); T.append(tr)
    P = pd.concat(P, ignore_index=True); T = pd.concat(T, ignore_index=True)
    lockP = (P.首顶 >= "2022-01-01") & (P.首顶 <= "2025-12-31"); P[lockP].to_csv(os.path.join(HERE, "out", f"封存_形态_{tag}.csv"), index=False); P = P[~lockP]; P.to_csv(os.path.join(HERE, "out", f"形态_{tag}.csv"), index=False)
    if len(T):
        lockT = (T.首顶 >= "2022-01-01") & (T.首顶 <= "2025-12-31"); T[lockT].to_csv(os.path.join(HERE, "out", f"封存_单子_{tag}.csv"), index=False); T = T[~lockT]; T.to_csv(os.path.join(HERE, "out", f"单子_{tag}.csv"), index=False)
    res = {"参数": kw, "形态数": int(len(P)), "其中跌破的": int(P.跌破.notna().sum()) if len(P) else 0}
    if len(P):
        res["成立后20天 最多跌 / 最多涨 中位pct"] = [round(float(P.成立后20天最多跌pct.median()), 1), round(float(P.成立后20天最多涨pct.median()), 1)]
        b = P[P.跌破.notna()]
        if len(b): res["跌破后20天 最多跌 / 最多涨 中位pct"] = [round(float(b.跌破后20天最多跌pct.median()), 1), round(float(b.跌破后20天最多涨pct.median()), 1)]
        res["按年"] = P.groupby(P.首顶.dt.year).size().to_dict()
    if len(T):
        T["大类"] = T.类.str.replace(r"\d", "", regex=True)
        for g, x in T.groupby("大类"):
            res[g] = {"3R": 统计(x), "2R": 统计(x, "R_2R"), "2017-2021": 统计(x[x.t < "2022-01-01"]), "2026": 统计(x[x.t >= "2026-01-01"])}
            if g == "左侧": res[g]["反上来就平"] = 统计(x, "R_反上来就平")
    json.dump(res, open(os.path.join(HERE, "out", f"汇总_{tag}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print(json.dumps(res, ensure_ascii=False, default=str))
    if tag == "默认":
        pd.set_option("display.width", 250); print(P[P.首顶 >= "2026-09-01"].to_string()); print(T[T.首顶 >= "2026-09-01"].round(2).to_string() if len(T) else "")
