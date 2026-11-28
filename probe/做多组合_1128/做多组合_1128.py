# -*- coding: utf-8 -*-
"""《533》第三批 · 做多组合（《527 拍板》第 1 条后半）：大方向 + 等待区 + 扳机 + 盈亏比够。引擎外，日线。
两套：回踩一套、V 形反转一套。品种：研发池个股（流动性池同一条规则：收盘 ≥5、20 日均成交额 ≥1,000 万、满 60 天），
  第一段 2015–2021（newpool 面板），第二段 2005–2014（并池2004 面板）；美股 2022 年以后不读。
对照：① 随机进场：在「同样满足大方向和等待区」的 K 线里随机挑同样多笔，止损目标同一套，1,000 次，看我们排第几分位（过 95 分位才算比随机强）；
      ② 扣掉大盘：每笔收益减去同一段持有期 SPY 的涨幅。

回踩一套（照技术面大师卡第五节「等待区（顺势回踩）」和「扳机」，卡是 4 小时 / 1 小时，这里全部用日线——写明）：
  大方向：收盘在 200 日线上、50 日线在 200 日线上、200 日线比 20 天前高（卡写「日线和 4 小时定方向」，没给数，我定的）。另试加「SPY 在 200 日线上」。
  这一段上涨：最近一个已确认的摆动低点（左右各 5 根）到其后已确认的摆动高点，高度 ≥ 3 倍 ATR（我定的，另试 2、4）。
  等待区：三项（回踩用时 ≤ 上涨用时、回踩缩量、回踩期间收盘守住 EMA20）都好 → 从回撤 0.382 起等；两项 → 0.5；一项或没有 → 0.618；回撤超过 0.786 作废；创新高作废。
  扳机：等待区里出 ① 长下影收回（下影 ≥ 实体 2 倍、收在上半截）或 ② 看涨吞没 → 那根收盘进。
  止损：扳机那根最低 − 0.5 ATR。第一目标 = 这段的摆动高点；盈亏比：到第一目标 ≥ 1.3 倍风险才做（卡里闸③，另试 1.0、1.5）。
  出场：到第一目标平一半、止损移到成本；剩下一半到第二目标（摆动高点 + 0.618 × 这段高度，我定的）或拿满 60 天。
V 形一套：用《491》的 V 形事件（《465》第 2 条转涨触发，个股跌幅门槛 20%）+ 进场 ②（盘涨后小阴线次日突破），止损同《491》；
  第一目标 = 大跌起点 H 的 0.618 位（L + 0.618×(H−L)，我定的），盈亏比 ≥ 1.3；出场同上，第二目标 = H。
  随机对照：在同一批 V 形事件触发后 60 根以内的 K 线里随机挑进场，止损 = 进场前 5 天最低和 EMA10 的较低者 − 0.4 ATR，目标同一套。"""
import os, sys, json, importlib.util
import numpy as np, pandas as pd
from numba import njit
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out"); os.makedirs(OUT, exist_ok=True)
HOLD = json.load(open(os.path.join(ROOT, "probe/新策略_1106/holdout_newpool_1106.json"), encoding="utf-8"))
FEE = 0.0005


def 面板(seg):
    f = os.path.join(ROOT, "probe/newpool_1106/ohlcv_panel_newpool.parquet" if seg == "一" else "probe/并池2004_1107/ohlcv_panel_newpool.parquet")
    W = pd.read_parquet(f); W = W.loc["2014-01-01":"2021-12-31"] if seg == "一" else W.loc["2004-01-01":"2014-12-31"]
    names = [s for s in HOLD["研发池名单"] if s in W["close"].columns] if seg == "一" else None
    if names is None:
        ex = set(HOLD["留出池名单"]); uni = set()
        for y in range(2005, 2015): uni |= set(pd.read_csv(os.path.join(ROOT, f"universe_1107/universe_{y}.csv.gz")).ticker)
        names = [s for s in W["close"].columns if s not in ex and s in uni]          # 第二段：这十年里进过成交额名单的普通股、去掉留出池
    return {k: W[k][names].astype("float64") for k in ("open", "high", "low", "close", "volume")}


def 流动(P, start):
    c, v = P["close"], P["volume"]; adv = (c * v).rolling(20, min_periods=20).mean(); bars = c.notna().cumsum(); idx = c.index
    perf = idx[idx >= pd.Timestamp(start)]; q = pd.Series(perf.quarter, index=perf); 调 = [perf[0]] + [d for d, a, b in zip(perf[1:], q.values[1:], q.values[:-1]) if a != b]
    M = pd.DataFrame(False, index=idx, columns=c.columns); 在 = np.zeros(c.shape[1], bool)
    for k, d in enumerate(调):
        i = idx.get_loc(d); cc, aa, nn = c.iloc[i - 1].to_numpy(), adv.iloc[i - 1].to_numpy(), bars.iloc[i - 1].to_numpy()
        在 = np.where(在, (cc >= 4) & (aa >= 8e6) & (nn >= 60), (cc >= 5) & (aa >= 1e7) & (nn >= 60)) & np.isfinite(cc)
        end = 调[k + 1] if k + 1 < len(调) else None; M.loc[perf[(perf >= d) & ((perf < end) if end is not None else True)]] = 在
    return M


@njit(cache=True)
def 走(o, h, l, c, i, E, S, T1, T2, 拿):
    """第 i 根收盘进；到 T1 平一半、止损移到成本；剩下到 T2 或拿满。返回 (R, 出场根)。"""
    n = len(c); R = E - S; 半 = False; pnl = 0.0; s = S; end = min(n - 1, i + 拿)
    for j in range(i + 1, end + 1):
        if np.isnan(c[j]): continue
        if l[j] <= s:
            px = min(s, o[j]) if not np.isnan(o[j]) else s
            return (pnl + (0.5 if 半 else 1.0) * (px - E)) / R, j
        if not 半 and h[j] >= T1:
            pnl += 0.5 * (T1 - E); 半 = True; s = E
        if 半 and h[j] >= T2:
            return (pnl + 0.5 * (T2 - E)) / R, j
    return (pnl + (0.5 if 半 else 1.0) * (c[end] - E)) / R, end


def 摆(h, l, k=5):
    n = len(h); SH = np.zeros(n, bool); SL = np.zeros(n, bool)
    for j in range(k, n - k):
        if h[j] == np.nanmax(h[j - k:j + k + 1]): SH[j] = True
        if l[j] == np.nanmin(l[j - k:j + k + 1]): SL[j] = True
    return SH, SL


def 回踩(sym, o, h, l, c, v, ok, spy_ok, 高度=3.0, 比=1.3, 带大盘=False):
    n = len(c); pc = np.roll(c, 1); pc[0] = c[0]
    atr = pd.Series(np.fmax(h - l, np.fmax(abs(h - pc), abs(l - pc)))).rolling(14).mean().to_numpy()
    s50 = pd.Series(c).rolling(50).mean().to_numpy(); s200 = pd.Series(c).rolling(200).mean().to_numpy(); e20 = pd.Series(c).ewm(span=20, adjust=False).mean().to_numpy()
    SH, SL = 摆(h, l); sh = np.where(SH)[0]; sl = np.where(SL)[0]
    sig, cand = [], []
    for i in range(220, n - 1):
        if not ok[i] or np.isnan(c[i]): continue
        if not (c[i] > s200[i] and s50[i] > s200[i] and s200[i] > s200[i - 20]): continue
        if 带大盘 and not spy_ok[i]: continue
        hs = sh[sh + 5 <= i]
        if not len(hs): continue
        b = hs[-1]; ls_ = sl[(sl < b)]
        if not len(ls_): continue
        a = ls_[-1]; H, L = h[b], l[a]; A = atr[i]
        if not (H - L >= 高度 * A) or np.nanmax(h[b + 1:i + 1]) >= H: continue
        好 = int((i - b) <= (b - a)) + int(np.nanmean(v[b + 1:i + 1]) < np.nanmean(v[a:b + 1])) + int(np.nanmin(c[b + 1:i + 1] - e20[b + 1:i + 1]) >= 0)
        z = 0.382 if 好 == 3 else 0.5 if 好 == 2 else 0.618; 回 = (H - l[i]) / (H - L)
        if not (回 >= z and 回 <= 0.786): continue
        T1, T2 = H, H + 0.618 * (H - L)
        cand.append((i, T1, T2, A))
        body = abs(c[i] - o[i]); 下影 = min(o[i], c[i]) - l[i]
        扳 = (下影 >= 2 * body and c[i] >= (h[i] + l[i]) / 2) or (c[i] > o[i] and c[i - 1] < o[i - 1] and c[i] >= o[i - 1] and o[i] <= c[i - 1])
        if 扳:
            E = c[i]; S = l[i] - 0.5 * A
            if E - S > 0 and (T1 - E) / (E - S) >= 比: sig.append((i, E, S, T1, T2))
    return sig, cand, atr


def 跑段(seg, 参数):
    P = 面板(seg); M = 流动(P, "2015-01-01" if seg == "一" else "2005-01-01"); idx = P["close"].index
    spy = P["close"]["SPY"] if "SPY" in P["close"] else None
    sp = importlib.util.spec_from_file_location("M4", os.path.join(ROOT, "probe/大周期五档_1123/五档状态机_第四版_1123.py")); M4 = importlib.util.module_from_spec(sp); sp.loader.exec_module(M4)
    S = M4.美股日线("SPY")["close"].reindex(idx).ffill().to_numpy(); spy_ok = S > pd.Series(S).rolling(200).mean().to_numpy()
    trades, cands = [], []
    for k, sym in enumerate(P["close"].columns):
        o, h, l, c, v = (P[x][sym].to_numpy() for x in ("open", "high", "low", "close", "volume"))
        if np.isfinite(c).sum() < 300: continue
        ok = M[sym].to_numpy()
        sig, cand, atr = 回踩(sym, o, h, l, c, v, ok, spy_ok, **参数)
        busy = -1
        for (i, E, St, T1, T2) in sig:
            if i <= busy: continue
            r, j = 走(o, h, l, c, i, E, St, T1, T2, 60); busy = j
            trades.append(dict(sym=sym, 日=idx[i], R=r - 2 * FEE * E / (E - St), 收益pct=r * (E - St) / E * 100 - 0.1, 大盘pct=(S[j] / S[i] - 1) * 100, 天=j - i))
        for (i, T1, T2, A) in cand:
            E = c[i]; St = l[i] - 0.5 * A
            if E - St <= 0 or T1 <= E: continue
            r, j = 走(o, h, l, c, i, E, St, T1, T2, 60); cands.append((r - 2 * FEE * E / (E - St), r * (E - St) / E * 100 - 0.1, (S[j] / S[i] - 1) * 100, idx[i].year))
    return pd.DataFrame(trades), np.array(cands)


if __name__ == "__main__":
    rng = np.random.default_rng(533)
    rows = []
    for seg in ("一", "二"):
        for nm, kw in (("默认", {}), ("高度2ATR", {"高度": 2.0}), ("高度4ATR", {"高度": 4.0}), ("盈亏比1.0", {"比": 1.0}), ("盈亏比1.5", {"比": 1.5}), ("加大盘开关", {"带大盘": True})):
            T, C = 跑段(seg, kw); C = C[np.isfinite(C).all(axis=1)] if len(C) else C; T = T[np.isfinite(T.R)]; n = len(T)
            np.save(os.path.join(OUT, f"候选_{seg}_{nm}.npy"), C)
            if n == 0 or len(C) == 0: rows.append(dict(段=seg, 参数=nm, 笔数=n)); continue
            ours = T.R.mean(); 随 = np.array([C[rng.choice(len(C), n, replace=True), 0].mean() for _ in range(1000)])
            w = T.R[T.R > 0].sum(); lo = -T.R[T.R < 0].sum()
            rows.append(dict(段="2015-2021" if seg == "一" else "2005-2014", 参数=nm, 笔数=n, 每笔R=round(ours, 3), 赚钱=round((T.R > 0).mean() * 100, 1), 利润因子=round(w / lo, 2) if lo else None, 最深一笔R=round(T.R.min(), 2),
                             每笔收益pct=round(T.收益pct.mean(), 2), 同期大盘pct=round(T.大盘pct.mean(), 2), 扣大盘后pct=round((T.收益pct - T.大盘pct).mean(), 2),
                             随机_候选K线数=len(C), 随机_中位R=round(float(np.median(随)), 3), 随机_95分位R=round(float(np.percentile(随, 95)), 3), 排在随机第几分位=round(float((随 < ours).mean() * 100), 1),
                             随机_扣大盘后pct=round(float((C[:, 1] - C[:, 2]).mean()), 2)))
            T.to_csv(os.path.join(OUT, f"回踩_{seg}_{nm}.csv"), index=False); print(rows[-1], flush=True)
    pd.DataFrame(rows).to_csv(os.path.join(OUT, "回踩汇总.csv"), index=False); print("DONE")
