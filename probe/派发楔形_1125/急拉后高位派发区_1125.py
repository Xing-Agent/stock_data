# -*- coding: utf-8 -*-
"""急拉后高位派发区 · 照《459 拍板》第 2 条 · BTC / ETH · 4 小时线 · 引擎外。2022–2025 封存。
急拉：到某天为止，1~3 天涨幅（收盘对 k 天前收盘）≥ 急拉倍 × 日线 ATR；或 5~10 天涨 ≥ 20%。取满足条件的那天为急拉日，起涨点 = 这段的起点收盘。
首顶 = 急拉日起 2 天内最高。横盘：首顶之后 25~120 根 4 小时线；期间没有收盘站上首顶 + 0.4 ATR（4 小时 ATR，取首顶那根）；
     至少 2 次冲高回落（含首顶：离区间最高不超过 1 ATR 的分形高点，左右各 3 根）且末次「三根合计量」< 首次；横盘振幅（最高 − 最低）≤ 急拉幅度的一半。
成立：4 小时收盘 < 横盘区最低点（首顶之后到上一根的最低）− 跌破倍 × ATR。
单子：右侧 = 成立那根的下一根开盘空，止损 = 最后一个顶 + 0.3 ATR。左侧 = 横盘条件已满足后，第 2 个及以后的顶确认（右边第 3 根收盘）时下一根开盘空，止损 = 区间最高 + 0.3 ATR；
     「又反上来就平」= 之后收盘高过那个顶就平。合并 = 左侧 0.3 份 + 右侧 0.7 份（没跌破就只有左侧那 0.3 份）。
出场：止损 / 3R / 最多 60 根。成本单边 0.05%。开关：五档状态机可空（跌势、见顶、筑底期且冲出过箱顶）。"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, os.path.join(HERE, f)); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
K = mod("k", "看九月那段_1125.py"); FL = mod("fl", "反抽加过滤_1125.py"); F0 = FL.F0; FEE = 0.0005
def 扫(sym, 急拉倍=2.5, 跌破倍=0.3, N=3):
    X = K.指标(K.四小时(sym)); X.index = X.index.tz_localize(None) if X.index.tz is not None else X.index
    o, h, l, c, v, atr = (X[x].to_numpy(float) for x in ("open", "high", "low", "close", "volume", "atr")); n = len(X); t = X.index
    D = X.resample("1D").agg({"high": "max", "low": "min", "close": "last"}).dropna(); pc = D.close.shift(1); da = pd.concat([D.high - D.low, (D.high - pc).abs(), (D.low - pc).abs()], axis=1).max(axis=1).rolling(14).mean().shift(1)
    sp_ = pd.Series(False, index=D.index); base = pd.Series(np.nan, index=D.index)
    for k in (1, 2, 3):
        m = (D.close - D.close.shift(k)) >= 急拉倍 * da; base[m & ~sp_] = D.close.shift(k)[m & ~sp_]; sp_ |= m
    for k in (5, 7, 10):
        m = (D.close / D.close.shift(k) - 1) >= 0.20; base[m & ~sp_] = D.close.shift(k)[m & ~sp_]; sp_ |= m
    可, 档 = FL.状态可空(sym); PAT, TR = [], []; last_end = -1
    def 出(i, e, stop, 平位=None):
        r = stop - e
        if r <= 0 or r / e < 0.002: return None
        out = None; end = min(n - 1, i + 59)
        for j in range(i, end + 1):
            if h[j] >= stop: out = -(max(o[j], stop) - e) / r if j > i else -1.0; break
            if l[j] <= e - 3 * r: out = 3.0; break
            if 平位 is not None and c[j] > 平位: out = (e - c[j]) / r; break
        if out is None: out = (e - c[end]) / r
        return out - 2 * FEE * e / r
    vol3 = lambda j: v[max(0, j - 1):j + 2].sum()
    for d in D.index[sp_.to_numpy()]:
        i0 = X.index.searchsorted(d); i1 = min(n - 1, X.index.searchsorted(d + pd.Timedelta(days=2)))
        if i0 <= last_end or i1 - i0 < 6: continue
        f = i0 + int(np.argmax(h[i0:i1])); A = atr[f]; top0 = h[f]; 幅 = top0 - base[d]
        if not (A > 0 and 幅 > 0): continue
        tops = [f]; ok_at = None; brk = None; lefts = []
        for j in range(f + 1, min(n - 1, f + 121)):
            if c[j] > top0 + 0.4 * A: break
            k = j - N; hi = h[f:j + 1].max(); lo_prev = l[f + 1:j].min() if j > f + 1 else l[j]
            newtop = False
            if k > f + N and h[k] == h[k - N:k + N + 1].max() and h[k] >= hi - 1.0 * A and k not in tops: tops.append(k); newtop = True
            good = j - f + 1 >= 25 and len(tops) >= 2 and vol3(tops[-1]) < vol3(tops[0]) and (hi - l[f + 1:j + 1].min()) <= 0.5 * 幅
            if good and ok_at is None: ok_at = j
            if good and newtop and len(lefts) < 2: lefts.append((j, tops[-1]))
            if ok_at is not None and c[j] < lo_prev - 跌破倍 * A: brk = j; break
        if ok_at is None: continue
        last_end = brk or ok_at; dd = t[ok_at].normalize() - pd.Timedelta(days=1); 允许 = bool(可.get(dd, False))
        P = dict(sym=sym, 急拉日=d, 首顶=t[f], 首顶价=top0, 起涨点=base[d], 成立横盘=t[ok_at], 顶数=len(tops), 跌破=(t[brk] if brk else None), 当时的档=档.get(dd, ""), 状态机可空=允许,
                 横盘后20天最多跌pct=(l[ok_at:min(n, ok_at + 120)].min() / c[ok_at] - 1) * 100, 横盘后20天最多涨pct=(h[ok_at:min(n, ok_at + 120)].max() / c[ok_at] - 1) * 100)
        if brk: P["跌破后20天最多跌pct"] = (l[brk:min(n, brk + 120)].min() / c[brk] - 1) * 100; P["跌破后20天最多涨pct"] = (h[brk:min(n, brk + 120)].max() / c[brk] - 1) * 100; P["跌破后回到起涨点"] = bool(l[brk:min(n, brk + 120)].min() <= base[d])
        PAT.append(P); rl = None; rr = None
        if lefts and lefts[0][0] + 1 < n and (brk is None or lefts[0][0] < brk):
            j, tk = lefts[0]; e = o[j + 1]; stop = h[f:j + 1].max() + 0.3 * A; rl = 出(j + 1, e, stop); rl2 = 出(j + 1, e, stop, 平位=h[tk])
            if rl is not None: TR.append(dict(sym=sym, 类="左侧", t=t[j + 1], 首顶=t[f], 可空=允许, R=rl, R_反上来就平=rl2))
        if brk and brk + 1 < n:
            rr = 出(brk + 1, o[brk + 1], h[tops[-1]] + 0.3 * A)
            if rr is not None: TR.append(dict(sym=sym, 类="右侧", t=t[brk + 1], 首顶=t[f], 可空=允许, R=rr))
        if rl is not None or rr is not None:
            TR.append(dict(sym=sym, 类="合并（左 0.3 + 右 0.7）", t=t[(lefts[0][0] if rl is not None else brk) + 1], 首顶=t[f], 可空=允许, R=0.3 * (rl or 0) + 0.7 * (rr or 0)))
    return pd.DataFrame(PAT), pd.DataFrame(TR)
def S(x):
    x = x.rename(columns={"R": "R_3R"}); return F0.统计(x)
if __name__ == "__main__":
    for tag, kw in (("默认", {}), ("急拉2.0", {"急拉倍": 2.0}), ("急拉3.0", {"急拉倍": 3.0}), ("跌破0.2", {"跌破倍": 0.2}), ("跌破0.45", {"跌破倍": 0.45})):
        r = [扫(s, **kw) for s in ("BTC", "ETH")]; P = pd.concat([a for a, _ in r], ignore_index=True); T = pd.concat([b for _, b in r], ignore_index=True)
        lk = (P.首顶 >= "2022-01-01") & (P.首顶 <= "2025-12-31"); P[lk].to_csv(os.path.join(HERE, "out", f"封存_派发区形态_{tag}.csv"), index=False); P = P[~lk]; P.to_csv(os.path.join(HERE, "out", f"派发区形态_{tag}.csv"), index=False)
        lk = (T.首顶 >= "2022-01-01") & (T.首顶 <= "2025-12-31"); T[lk].to_csv(os.path.join(HERE, "out", f"封存_派发区单子_{tag}.csv"), index=False); T = T[~lk]; T.to_csv(os.path.join(HERE, "out", f"派发区单子_{tag}.csv"), index=False)
        b = P[P.跌破.notna()]; res = {"形态数": len(P), "跌破的": len(b), "状态机可空的": int(P.状态机可空.sum()), "可空里跌破的": int((P.状态机可空 & P.跌破.notna()).sum()),
               "横盘后20天 跌/涨 中位": [round(P.横盘后20天最多跌pct.median(), 1), round(P.横盘后20天最多涨pct.median(), 1)], "跌破后20天 跌/涨 中位": [round(b.跌破后20天最多跌pct.median(), 1), round(b.跌破后20天最多涨pct.median(), 1)] if len(b) else None,
               "跌破后回到起涨点的比例": round(float(b.跌破后回到起涨点.mean()), 2) if len(b) else None, "按年": P.groupby(P.首顶.dt.year).size().to_dict()}
        for g, x in T.groupby("类"):
            res[g] = {"不加开关": S(x), "状态机可空": S(x[x.可空]), "不加·2017-2021": S(x[x.t < "2022-01-01"]), "不加·2026": S(x[x.t >= "2026-01-01"])}
            if g == "左侧": res[g]["反上来就平·不加开关"] = F0.统计(x.rename(columns={"R_反上来就平": "R_3R"})[["R_3R"]]); res[g]["反上来就平·可空"] = F0.统计(x[x.可空].rename(columns={"R_反上来就平": "R_3R"})[["R_3R"]])
        json.dump(res, open(os.path.join(HERE, "out", f"派发区_汇总_{tag}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str); print(tag, json.dumps(res, ensure_ascii=False, default=str), flush=True)
        if tag == "默认": pd.set_option("display.width", 250); print(P[P.首顶 >= "2026-08-01"][["sym", "首顶", "首顶价", "起涨点", "成立横盘", "顶数", "跌破", "当时的档", "状态机可空"]].to_string())
