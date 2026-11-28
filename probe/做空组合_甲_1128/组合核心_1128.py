# -*- coding: utf-8 -*-
"""《570》第二批 · 做空组合（《527 拍板》第 1 条前半）· 核心函数 · 引擎外（engine/ 一个字节没动）

六个条件（逐个加，每加一个报还剩多少笔）：
  ① 大势向下：标普（SPY）收在 200 日线下，且 50 日线在 200 日线下（用前一天收盘判，不偷看）。
             美股个股另加：这只票自己也收在 200 日线下。加密的「大盘」用 BTC 自己（BTC、ETH 都看 BTC）。
  ② 顶部形态：双顶 / 多顶。两个分形高点（左右各 N 根）相隔 8~80 根，高度相差 ≤ 容差×ATR，
             两顶之间的最低点（= 颈线）比低的那个顶至少低 1 ATR；第二个顶是近 40 根里的最高（或差不到容差）。
             ★ 拍板没给数，我定的：容差 1.0 ATR（另试 0.5、1.5）。头肩顶没单独写（两肩 + 头会被当成多顶的一部分认出来一部分）。
  ③ 背离（拍板原文）：MACD 柱（12,26,9），第二个顶的柱子 ≤ 第一个顶的 0.65 倍，第一个顶的柱子 > 0，两顶之间柱子穿过零轴。
             顶的柱子取那根及前 2 根里最大的。
  ④ 跌破颈线：第二个顶确认后 40 根内，收盘 < 颈线。之前收盘先高过两顶最高 → 形态作废。
  ⑤ 无量弱反抽：跌破后 20 根内反抽到颈线附近（最高 ≥ 颈线 − 1.0 ATR），期间没有收盘站回颈线；
             反抽那几根（跌破后最低点 → 碰颈线那根）的平均量 < κ × 跌破前 20 根平均量（写法甲）；
             另一种写法乙：< κ × 跌破那根到跌破后最低点这段下跌的平均量（「跌放量、抽缩量」）。
             碰到之后 5 根内出现「收盘跌破前一根最低」→ 下一根开盘空。★ 我定的：κ = 0.8（另试 0.6、1.0）；碰线距离 1.0 ATR。
  ⑥ 下面 1.5R 以内没有支撑：进场价往下 1.5 倍风险以内没有前低（分形低点，左右各 N 根，回看 LB 根，进场前已确认）。
             ★ 我定的：回看 250 根（另试 120、500）。只看前低，成交密集区、缺口没算（写进报告）。
进场（每一步用它自己自然的进场，好让笔数能数）：
  ①：随机进场（就是对照组本身）。
  ②③：第二个顶确认（右边第 N 根收盘）后下一根开盘空，止损 = 两顶最高 + 0.3 ATR（左侧空）。
  ④：跌破那根的下一根开盘空，止损 = 两顶最高 + 0.3 ATR。
  ⑤⑥：反抽失败那根的下一根开盘空，止损 = 两顶最高 + 0.3 ATR（另试：反抽高点 + 0.3 ATR）。
出场：止损（盘中碰到，跳空按开盘）/ 3 倍风险目标 / 最多 60 根；④⑤⑥ 另加 Lin 11-28 定的「收盘重新站回颈线就走」（那根收盘平）。
成本单边 0.05%。同一只票同一时间只拿一笔。
"""
import numpy as np, pandas as pd

FEE = 0.0005
默认 = dict(N=5, 容差=1.0, 背离比=0.65, 跌破窗=40, 反抽窗=20, 碰线=1.0, κ=0.8, 支撑R=1.5, LB=250, 止损法="顶上方", 目标=3.0, 最长=60)


坏点 = {"根数": 0}


def 洗(X):
    """数据坏点：最低价 < 0.6 × min(开, 收) 或 最高价 > 1.6 × max(开, 收) 的根，高低改成开收盘（例：PG 2008-11-25 最低记成 1.00）。"""
    X = X.copy(); lo = np.minimum(X.open, X.close); hi = np.maximum(X.open, X.close)
    b1 = X.low < 0.6 * lo; b2 = X.high > 1.6 * hi; 坏点["根数"] += int((b1 | b2).sum())
    X.loc[b1, "low"] = lo[b1]; X.loc[b2, "high"] = hi[b2]; return X


def 指标(X):
    X = 洗(X); h, l, c = X.high, X.low, X.close; pc = c.shift(1)
    X["atr"] = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1).rolling(14).mean()
    m = c.ewm(span=12, adjust=False).mean() - c.ewm(span=26, adjust=False).mean(); X["hist"] = m - m.ewm(span=9, adjust=False).mean()
    X["s200"] = c.rolling(200).mean(); return X


def 出场(o, h, l, c, i, e, stop, 目标=3.0, 最长=60, 颈=None):
    """i = 进场那根（开盘进）。返回 (R, 出场根, 出场价, 怎么走的)。"""
    r = stop - e; n = len(c); end = min(n - 1, i + 最长 - 1)
    for j in range(i, end + 1):
        if h[j] >= stop:
            px = max(o[j], stop) if j > i else stop; return (e - px) / r - 2 * FEE * e / r, j, px, "止损"
        if l[j] <= e - 目标 * r: return 目标 - 2 * FEE * e / r, j, e - 目标 * r, "目标"
        if 颈 is not None and c[j] > 颈: return (e - c[j]) / r - 2 * FEE * e / r, j, c[j], "站回颈线"
    return (e - c[end]) / r - 2 * FEE * e / r, end, c[end], "拿满"


def 扫(sym, X, 大势, P=None):
    """X：带 open/high/low/close/volume 的 K 线（已 指标()）；大势：同索引的布尔（已经是前一根能知道的）。
    返回每个形态一行，各步是否满足 + 各步的单子。"""
    P = {**默认, **(P or {})}; N = P["N"]
    o, h, l, c, v, atr, hist = (X[k].to_numpy(float) for k in ("open", "high", "low", "close", "volume", "atr", "hist"))
    reg = 大势.reindex(X.index).fillna(False).to_numpy(bool); n = len(c); t = X.index
    v20 = pd.Series(v).rolling(20).mean().shift(1).to_numpy()
    SH = [j for j in range(N, n - N) if h[j] == h[j - N:j + N + 1].max()]
    SL = np.array([j for j in range(N, n - N) if l[j] == l[j - N:j + N + 1].min()], dtype=int)
    rows = []; 忙到 = -1
    for q, k in enumerate(SH):
        conf = k + N
        if conf + 2 >= n or conf <= 忙到 or not (atr[k] > 0): continue
        A = atr[k]
        # ② 找第一个顶
        p1 = None
        for p in reversed(SH[:q]):
            if k - p > 80: break
            if k - p < 8: continue
            if abs(h[p] - h[k]) <= P["容差"] * A and h[p:k + 1].max() <= max(h[p], h[k]) + 1e-12:
                p1 = p; break
        if p1 is None: continue
        if h[k] < h[max(0, k - 40):k + 1].max() - P["容差"] * A: continue
        tr = p1 + int(np.argmin(l[p1:k + 1])); 颈 = l[tr]
        if min(h[p1], h[k]) - 颈 < 1.0 * A: continue
        顶 = max(h[p1], h[k])
        hv1 = np.nanmax(hist[max(0, p1 - 2):p1 + 1]); hv2 = np.nanmax(hist[max(0, k - 2):k + 1])
        背离 = bool(hv1 > 0 and hv2 <= P["背离比"] * hv1 and np.nanmin(hist[p1:k + 1]) < 0)
        R = dict(sym=sym, 顶1=t[p1], 顶2=t[k], 确认=t[conf], 颈线=颈, 顶=顶, 背离=背离, 大势_确认=bool(reg[conf + 1]), ATR=A)
        # 左侧单（②③ 用）
        e = o[conf + 1]; st = 顶 + 0.3 * atr[conf]
        if st > e and (st - e) / e >= 0.002:
            rr, jx, px, how = 出场(o, h, l, c, conf + 1, e, st, P["目标"], P["最长"])
            R.update(左_atr=atr[conf], 左_t=t[conf + 1], 左_进=e, 左_止损=st, 左_R=rr, 左_出=t[jx], 左_出价=px, 左_怎么走=how)
        # ④ 跌破
        b = None
        for j in range(conf, min(n - 2, conf + P["跌破窗"])):
            if c[j] > 顶: break
            if c[j] < 颈: b = j; break
        R["跌破"] = b is not None
        if b is not None:
            R["大势_跌破"] = bool(reg[b + 1]); e = o[b + 1]; st = 顶 + 0.3 * atr[b]
            if st > e and (st - e) / e >= 0.002:
                rr, jx, px, how = 出场(o, h, l, c, b + 1, e, st, P["目标"], P["最长"], 颈=颈)
                R.update(破_atr=atr[b], 破_t=t[b + 1], 破_进=e, 破_止损=st, 破_R=rr, 破_出=t[jx], 破_出价=px, 破_怎么走=how, 破_i=b + 1)
            # ⑤ 反抽
            jt = None
            for j in range(b + 1, min(n - 2, b + 1 + P["反抽窗"])):
                if c[j] > 颈: break
                if h[j] >= 颈 - P["碰线"] * atr[b]: jt = j; break
            R["反抽"] = jt is not None
            if jt is not None:
                lo = b + int(np.argmin(l[b:jt + 1])); 量 = v[lo:jt + 1].mean(); base = v20[b]
                R["反抽量比"] = float(量 / base) if base > 0 else np.nan
                跌段 = v[b:lo + 1].mean(); R["反抽量比_跌段"] = float(量 / 跌段) if 跌段 > 0 else np.nan   # 另一种写法：和跌破那段下跌的量比
                m = None
                for j in range(jt + 1, min(n - 1, jt + 6)):
                    if c[j] > 颈: break
                    if c[j] < l[j - 1]: m = j; break
                R["反抽失败"] = m is not None
                if m is not None:
                    R["大势_反抽"] = bool(reg[m + 1]); e = o[m + 1]
                    st = (顶 + 0.3 * atr[m]) if P["止损法"] == "顶上方" else (h[jt:m + 1].max() + 0.3 * atr[m])
                    if st > e and (st - e) / e >= 0.002:
                        rr, jx, px, how = 出场(o, h, l, c, m + 1, e, st, P["目标"], P["最长"], 颈=颈)
                        r_ = st - e; sl = SL[(SL + N <= m) & (SL >= m - P["LB"])]; below = l[sl][l[sl] < e]
                        近 = (e - below.max()) / r_ if len(below) else np.inf
                        R.update(抽_atr=atr[m], 抽_t=t[m + 1], 抽_进=e, 抽_止损=st, 抽_R=rr, 抽_出=t[jx], 抽_出价=px, 抽_怎么走=how, 抽_i=m + 1, 抽_支撑R=近)
                        忙到 = max(忙到, jx)
            if "破_出" in R and "抽_出" not in R: 忙到 = max(忙到, X.index.get_loc(R["破_出"]))
        rows.append(R)
    return pd.DataFrame(rows)


def 统计(x, pct=None):
    x = pd.Series(x).dropna()
    if not len(x): return {"笔": 0}
    eq = x.cumsum(); dd = float((eq - eq.cummax()).min())
    d = {"笔": int(len(x)), "每笔R": round(float(x.mean()), 3), "赚钱占比": round(float((x > 0).mean()), 2),
         "利润因子": round(float(x[x > 0].sum() / max(1e-9, -x[x <= 0].sum())), 2), "最深亏损R": round(min(0.0, dd), 1),
         "t": round(float(x.mean() / x.std() * np.sqrt(len(x))), 2) if len(x) > 2 and x.std() > 0 else None}
    if pct is not None:
        p = pd.Series(pct).dropna(); d["每笔%"] = round(float(p.mean()), 2); d["最差一笔%"] = round(float(p.min()), 1)
    if len(x) < 30: d["备注"] = "样本不够，下不了结论"
    return d


# ---------- 随机对照 ----------
def 随机对照(池, 样本, 次数=1000, 目标=3.0, 最长=60, 种子=0):
    """池：dict sym -> (o,h,l,c,atr, 可进的根号数组)。样本：我们这批单子的 (风险/ATR, 颈线离进场/ATR 或 nan) 列表。
    每次：从所有可进的根里均匀抽同样笔数，下一根开盘空；风险、颈线距离从我们的单子里随机抽一组。返回每次的平均 R。"""
    rng = np.random.default_rng(种子)
    syms = list(池); cnt = np.array([len(池[s][5]) for s in syms]); cum = np.cumsum(cnt); tot = cum[-1]
    big = {k: np.concatenate([池[s][q] for s in syms]) for q, k in enumerate(("o", "h", "l", "c", "a"))}
    off = np.concatenate([[0], np.cumsum([len(池[s][0]) for s in syms])])
    gi = np.concatenate([池[s][5] + off[q] for q, s in enumerate(syms)]); gend = np.concatenate([np.full(len(池[s][5]), off[q + 1] - 1) for q, s in enumerate(syms)])
    S = np.asarray(样本, float); n = len(S); out = np.empty(次数)
    o, h, l, c, a = big["o"], big["h"], big["l"], big["c"], big["a"]; ar = np.arange(最长)
    for it in range(次数):
        pick = rng.integers(0, tot, n); i0 = gi[pick] + 1; end = np.minimum(gend[pick], i0 + 最长 - 1)
        ss = S[rng.integers(0, len(S), n)]; e = o[i0]; r = ss[:, 0] * a[i0 - 1]; 颈 = e + ss[:, 1] * a[i0 - 1]
        ok = (r > 0) & (i0 <= end); e, r, 颈, i0, end = e[ok], r[ok], 颈[ok], i0[ok], end[ok]
        W = i0[:, None] + ar[None, :]; valid = W <= end[:, None]; W = np.minimum(W, end[:, None])
        H, L, C, O = h[W], l[W], c[W], o[W]; st = (e + r)[:, None]
        hit = (H >= st) & valid; tg = (L <= (e - 目标 * r)[:, None]) & valid; nk = (C > 颈[:, None]) & valid & ~np.isnan(颈)[:, None]
        BIG = 最长 + 5
        fh = np.where(hit.any(1), hit.argmax(1), BIG); ft = np.where(tg.any(1), tg.argmax(1), BIG); fn = np.where(nk.any(1), nk.argmax(1), BIG)
        first = np.minimum(np.minimum(fh, ft), fn); res = np.empty(len(e)); rows = np.arange(len(e))
        a1 = first == fh; px = np.where(fh == 0, st[:, 0], np.maximum(O[rows, np.minimum(fh, 最长 - 1)], st[:, 0]))
        res[a1 & (first < BIG)] = ((e - px) / r)[a1 & (first < BIG)]
        a2 = (first == ft) & ~a1; res[a2] = 目标
        a3 = (first == fn) & ~a1 & ~a2; res[a3] = ((e - C[rows, np.minimum(fn, 最长 - 1)]) / r)[a3]
        a4 = first >= BIG; lastc = C[rows, (end - i0)]; res[a4] = ((e - lastc) / r)[a4]
        res -= 2 * FEE * e / r; out[it] = res.mean()
    return out


def 分位(ours, rnd):
    return round(float((rnd < ours).mean() * 100), 1)
