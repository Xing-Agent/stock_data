"""第④行「它平常什么脾气」11 条特征 —— 逐条实测。

大白话:设计文档里那 11 条特征的数字全是我编的示意数。这个文件把每一条
        真的算一遍,然后回答两件事:
          一、算不算得出来 / 算出来之后有没有区分力;
          二、同一只票换个年份段,答案还是不是同一个。

★ 所有「天」一律是**交易日**(数据是日线,没有自然日的概念)。本文件里
  出现的 20 天 / 3 天 / 60 天 全部是交易日。
★ 本文件只读 engine/,不改 engine/ 下任何东西。
"""
from __future__ import annotations
import os, sys, math
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)

import engine.data as D                       # noqa: E402  只读
from engine.signals import atr as _atr        # noqa: E402  Wilder ATR
from engine.run_a0_states import zigzag_pivots  # noqa: E402  状-1 的摆动点

# ────────────────────────────────── 写死的参数(都标出处/待校准)
ZZ_K = 3.0          # ZigZag 阈值 = 3 × ATR(14) —— 沿用状-1,★ XING·待校准
ZZ_ATR_P = 14
TOP_TOL = 0.03      # 「两次触到同一个顶」的容差 3% —— ★ XING·待校准
TOP_WIN = 60        # 两个顶之间最多隔 60 个交易日才算「二次触顶」
BOT_TOL = 0.03      # 底部「还在底上」的容差 3%
GRIND_MIN = 6       # 底部盘整 ≥ 6 个交易日算磨底,≤ 5 算 V 底
BRK_LOOK = 60       # 突破看前 60 个交易日的最高价(Donchian 60,不含当根)
BRK_COOL = 10       # 两次突破之间至少隔 10 个交易日(去重)
FAKE_WIN = 3        # 突破后 3 个交易日内跌回前高以下 = 假突破
GAP_MIN = 0.01      # 跳空 > 1%
GAP_FILL_WIN = 3    # 3 个交易日内回补
VOLCL_K = 2.0       # 「大波动日」= 当日真实波幅 > 2 × 前 60 交易日中位
VOLCL_WIN = 3       # 之后 3 个交易日
MA_REACT = 50       # 50 日均线
MA_COOL = 5
MA_JUDGE = 5        # 触及后第 5 个交易日看站在均线上还是下
PEAD_DRIFT = 20     # 财报后 20 个交易日
VOL_K = 1.5         # 放量 = 成交量 > 1.5 × 50 交易日均量
DOWN_DAY = -0.01    # 大盘跌超 1%

WARM_START = "2016-01-04"


# ────────────────────────────────── 基础量(每只票算一次)
def base(sym: str) -> dict | None:
    df = D.load_daily(sym)
    if df is None or len(df) < 300:
        return None
    df = df[df.index >= WARM_START]
    a = _atr(df, ZZ_ATR_P)
    piv = zigzag_pivots(df["high"].to_numpy(float), df["low"].to_numpy(float),
                        df["close"].to_numpy(float), a.to_numpy(float),
                        k=ZZ_K, use_wick=True)
    rng = (df["high"] - df["low"])
    tr = pd.concat([rng, (df["high"] - df["close"].shift(1)).abs(),
                    (df["low"] - df["close"].shift(1)).abs()], axis=1).max(axis=1)
    return dict(
        sym=sym, df=df, idx=df.index, piv=piv,
        close=df["close"].to_numpy(float), open=df["open"].to_numpy(float),
        high=df["high"].to_numpy(float), low=df["low"].to_numpy(float),
        vol=df["volume"].to_numpy(float),
        trp=(tr / df["close"].shift(1)).to_numpy(float),      # 真实波幅%
        rngp=(rng / df["close"]).to_numpy(float),
        ret=df["close"].pct_change().to_numpy(float),
        sma50=df["close"].rolling(50, min_periods=50).mean().to_numpy(float),
        vsma50=df["volume"].rolling(50, min_periods=50).mean().to_numpy(float),
        donch=df["high"].rolling(BRK_LOOK, min_periods=BRK_LOOK).max().shift(1).to_numpy(float),
    )


def _mask(idx: pd.DatetimeIndex, years: list[int]) -> np.ndarray:
    return np.isin(idx.year.to_numpy(), years)


# ────────────────────────────────── 11 条特征
# 每个函数返回 {值名: 数值 or None, "_n": 事件数}
def f_T1_top_shape(b, m):
    """T1 它怎么做顶:重要顶部里有几成是「二次触顶后回落」。"""
    piv = b["piv"]
    hs = [(i, v) for k, (i, t, v) in enumerate(piv) if t == "H"]
    ev = []
    prev_h = None
    for i, v in hs:
        if m[i]:
            if prev_h is not None and (i - prev_h[0]) <= TOP_WIN and \
               abs(v - prev_h[1]) / prev_h[1] <= TOP_TOL:
                ev.append(1)
            else:
                ev.append(0)
        prev_h = (i, v)
    n = len(ev)
    return {"n_tops": n, "share_double_top": (sum(ev) / n) if n else None, "_n": n}


def f_T2_bottom_shape(b, m):
    """T2 它怎么做底:重要底部里有几成是「磨底」(≥6 个交易日贴在底上)。"""
    piv, lo, cl = b["piv"], b["low"], b["close"]
    runs, n = [], 0
    for i, t, v in piv:
        if t != "L" or not m[i]:
            continue
        n += 1
        j = i
        while j - 1 >= 0 and (cl[j - 1] - v) / v <= BOT_TOL:
            j -= 1
        k = i
        while k + 1 < len(cl) and (cl[k + 1] - v) / v <= BOT_TOL:
            k += 1
        runs.append(k - j + 1)
    if not n:
        return {"n_bottoms": 0, "share_grind": None, "median_bottom_days": None, "_n": 0}
    g = sum(1 for r in runs if r >= GRIND_MIN)
    return {"n_bottoms": n, "share_grind": g / n,
            "median_bottom_days": float(np.median(runs)), "_n": n}


def f_T3_swing_size(b, m):
    """T3 顶底间距:顶→底跌幅中位、底→顶涨幅中位(交替摆动点逐对)。"""
    piv = b["piv"]
    dn, up = [], []
    for (i1, t1, v1), (i2, t2, v2) in zip(piv, piv[1:]):
        if not m[i2]:
            continue
        if t1 == "H" and t2 == "L":
            dn.append(v2 / v1 - 1.0)
        elif t1 == "L" and t2 == "H":
            up.append(v2 / v1 - 1.0)
    return {"n_swings": len(dn) + len(up),
            "median_top_to_bottom": float(np.median(dn)) if dn else None,
            "median_bottom_to_top": float(np.median(up)) if up else None,
            "_n": len(dn) + len(up)}


def f_T4_fake_breakout(b, m):
    """T4 假突破率:收盘突破前 60 交易日高点后,3 个交易日内又跌回那个高点以下。"""
    cl, dh = b["close"], b["donch"]
    n = len(cl)
    tot = fake = 0
    last = -10**9
    for i in range(n):
        if not m[i] or not np.isfinite(dh[i]):
            continue
        if cl[i] > dh[i] and (i - last) > BRK_COOL:
            last = i
            tot += 1
            w = cl[i + 1:i + 1 + FAKE_WIN]
            if len(w) and np.nanmin(w) < dh[i]:
                fake += 1
    return {"n_breakouts": tot, "fake_breakout_rate": (fake / tot) if tot else None, "_n": tot}


def f_F1_gap(b, m):
    """F1 跳空习惯:每多少个交易日跳空一次(>1%),其中几成 3 个交易日内回补。"""
    op, cl, hi, lo = b["open"], b["close"], b["high"], b["low"]
    n = len(cl)
    days = int(m.sum())
    tot = fill = 0
    for i in range(1, n):
        if not m[i]:
            continue
        pc = cl[i - 1]
        g = op[i] / pc - 1.0
        if abs(g) <= GAP_MIN or not np.isfinite(g):
            continue
        tot += 1
        w = slice(i, i + GAP_FILL_WIN + 1)
        if g > 0:
            if len(lo[w]) and np.nanmin(lo[w]) <= pc:
                fill += 1
        else:
            if len(hi[w]) and np.nanmax(hi[w]) >= pc:
                fill += 1
    return {"days_per_gap": (days / tot) if tot else None,
            "gap_fill_rate": (fill / tot) if tot else None, "_n": tot}


def f_F2_vol_cluster(b, m):
    """F2 波动聚集:大波动日之后 3 个交易日的平均波幅 ÷ 平时平均波幅。"""
    trp = b["trp"]
    med = pd.Series(trp).rolling(60, min_periods=60).median().to_numpy(float)
    n = len(trp)
    big = np.zeros(n, bool)
    for i in range(n):
        if m[i] and np.isfinite(trp[i]) and np.isfinite(med[i]) and med[i] > 0:
            big[i] = trp[i] > VOLCL_K * med[i]
    after = np.zeros(n, bool)
    for i in np.flatnonzero(big):
        after[i + 1:i + 1 + VOLCL_WIN] = True
    base_m = m & np.isfinite(trp)
    a = trp[after & base_m]
    allv = trp[base_m]
    return {"n_bigdays": int(big.sum()),
            "vol_cluster_ratio": float(np.nanmean(a) / np.nanmean(allv))
            if len(a) >= 5 and len(allv) else None, "_n": int(big.sum())}


def f_F3_upper_wick(b, m):
    """F3 长上影线频率:收盘落在当日振幅下半部的交易日占比。
    ★ 这是设计文档括号里的原话定义(「收在当日下半部」)。另给一个更严的变体。"""
    hi, lo, cl, op = b["high"], b["low"], b["close"], b["open"]
    rg = hi - lo
    ok = m & np.isfinite(rg) & (rg > 0)
    if ok.sum() < 50:
        return {"upper_wick_share": None, "upper_wick_strict_share": None, "_n": int(ok.sum())}
    lower_half = cl[ok] <= (lo[ok] + 0.5 * rg[ok])
    upsh = hi[ok] - np.maximum(op[ok], cl[ok])
    strict = lower_half & (upsh >= 0.5 * rg[ok])
    return {"upper_wick_share": float(lower_half.mean()),
            "upper_wick_strict_share": float(strict.mean()), "_n": int(ok.sum())}


def f_F4_ma_reaction(b, m):
    """F4 均线反应:从上方触及 50 日均线后,第 5 个交易日还站在均线上(反弹)还是跌破(穿透)。"""
    hi, lo, cl, ma = b["high"], b["low"], b["close"], b["sma50"]
    n = len(cl)
    tot = bounce = 0
    last = -10**9
    for i in range(1, n - MA_JUDGE):
        if not m[i] or not np.isfinite(ma[i]) or not np.isfinite(ma[i - 1]):
            continue
        if cl[i - 1] > ma[i - 1] and lo[i] <= ma[i] <= hi[i] and (i - last) > MA_COOL:
            last = i
            tot += 1
            j = i + MA_JUDGE
            if np.isfinite(ma[j]) and cl[j] > ma[j]:
                bounce += 1
    return {"n_ma_touch": tot, "ma_bounce_rate": (bounce / tot) if tot else None, "_n": tot}


def f_F6_market(b, m, spy_ret: np.ndarray):
    """F6 和大盘的关系:beta(对 SPY 日收益,OLS);大盘跌超 1% 的日子它平均涨跌。"""
    r, s = b["ret"], spy_ret
    ok = m & np.isfinite(r) & np.isfinite(s)
    if ok.sum() < 100:
        return {"beta": None, "down_day_mean": None, "_n": int(ok.sum())}
    x, y = s[ok], r[ok]
    beta = float(np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1))
    d = ok & (s < DOWN_DAY)
    return {"beta": beta,
            "down_day_mean": float(np.nanmean(r[d])) if d.sum() >= 5 else None,
            "_n": int(ok.sum())}


def f_F7_volume(b, m):
    """F7 成交量的性格:放量日(>1.5× 50 交易日均量)占比,其中几成当日收涨。"""
    v, vm, cl = b["vol"], b["vsma50"], b["close"]
    ok = m & np.isfinite(v) & np.isfinite(vm) & (vm > 0)
    if ok.sum() < 100:
        return {"high_vol_share": None, "high_vol_up_share": None, "_n": int(ok.sum())}
    hv = ok & (v > VOL_K * vm)
    up = np.r_[False, cl[1:] > cl[:-1]]
    return {"high_vol_share": float(hv.sum() / ok.sum()),
            "high_vol_up_share": float(up[hv].mean()) if hv.sum() >= 10 else None,
            "_n": int(hv.sum())}


# ────────────────────────────────── F5 财报后漂移(单独,要财报日)
def earnings_dates(sym: str) -> list[pd.Timestamp]:
    """从 fundamentals.json 的 filed_at 取财报日。
    ★★ 我对这个字段的理解(请反驳):filed_at 是 10-Q/10-K **送交 SEC 的日期**,
       不是业绩发布会的日期。多数公司两者差 0–几个交易日,但有的差好几周。
       → 用它测 PEAD 是**近似**,不是精确口径。本报告会把 filed_at−period_end
         的分布报出来让人判断。

    ★★ 第二个坑(我自己踩的,1030):一份 10-Q 里**同一个 filed_at 下有多个
       period_end** —— 本期、去年同期、年初至今全在同一份申报里。我第一版
       直接 out[filed_at] = period_end,后写的覆盖先写的,于是「filed_at −
       period_end」中位算出 **401 自然日**。那不是数据问题,是我的聚合写错。
       → 改成取同一个 filed_at 下**最大的** period_end(= 本期)。
    """
    f = D.load_fundamentals(sym)
    out: dict[str, pd.Timestamp | None] = {}
    for recs in f.values():
        for r in (recs or []):
            fa, pe, form = r.get("filed_at"), r.get("period_end"), r.get("source_form")
            if not fa or form not in ("10-Q", "10-K"):
                continue
            pt = pd.Timestamp(pe) if pe else None
            cur = out.get(fa, "missing")
            if cur == "missing" or (pt is not None and (cur is None or pt > cur)):
                out[fa] = pt
    return sorted((pd.Timestamp(k), v) for k, v in out.items())


def f_F5_pead(b, m, eds):
    cl, op, idx = b["close"], b["open"], b["idx"]
    n = len(cl)
    tot = agree = 0
    lags = []
    for d, pe in eds:
        pos = idx.searchsorted(d, side="left")
        if pos <= 0 or pos >= n - PEAD_DRIFT or not m[pos]:
            continue
        g = op[pos] / cl[pos - 1] - 1.0
        dr = cl[pos + PEAD_DRIFT] / cl[pos] - 1.0
        if not (np.isfinite(g) and np.isfinite(dr)) or g == 0:
            continue
        tot += 1
        if np.sign(g) == np.sign(dr):
            agree += 1
        if pe is not None:
            lags.append((d - pe).days)
    return {"n_earnings": tot, "pead_agree_rate": (agree / tot) if tot else None,
            "median_filed_minus_periodend_cal_days": float(np.median(lags)) if lags else None,
            "_n": tot}
