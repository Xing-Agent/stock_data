"""
pat6_ops —— 技-3 / 技-4 / 技-5 / 技-6 / 技-11 / 技-14 六条形态的算子。

大白话(三秒):这六条形态以前引擎里没有(或者只有我们自己改过的版本)。
这个文件把「原著怎么写的」「行业怎么做的」「我们现在怎么做的」三种写法
各实现一遍,★ 一个数都不许由代码自己填 —— 阈值全部必须由配置传进来,
没传就报错。

★★ 为什么单开一个文件、不改 matrices.py:
  matrices.py / chain.py 是另外两条线正在动的文件(A0 十二条 / 新基准线)。
  这个文件用**运行时挂钩**的方式把新算子接上去(install()),
  ★ 一行别人的代码都不碰。

★ 命名纪律:本文件所有新算子的 type 一律 pat6_ 前缀,
  和别人以后要加的算子撞不上。

★ 阈值纪律(本文件的核心约束):
  _need(p, "k") —— 配置没写这个参数就直接报错,不给默认值。
  ★ 理由:今天已经踩过一次「配置写了条件、引擎悄悄忽略」的坑,
    也踩过一次「原著阈值是单根 K 线口径、被套到 20 根均值上」的坑。
    默认值是这两种坑的温床。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import cache, matrices

# ---------------------------------------------------------------- 记录与缓存

_NOTES: list[str] = []
_CACHE: dict = {}


def note(s: str) -> None:
    if s not in _NOTES:
        _NOTES.append(s)


def notes() -> list[str]:
    return list(_NOTES)


def _need(p: dict, k: str, who: str):
    """配置里必须显式写这个参数 —— 没写就报错,★ 不给默认值。"""
    if k not in p or p[k] is None:
        raise NotImplementedError(
            f"{who} 的参数 {k} 必须在配置里显式写出来 —— ★ 引擎不替它选一个数。\n"
            f"★ 理由:默认值会让「原著给的是区间 / 原著根本没给」这件事消失不见。")
    return p[k]


def _bool(df: pd.DataFrame) -> pd.DataFrame:
    return df.fillna(False).astype(bool)


# ================================================================
# 基础指标 —— 全池一次算完
# ================================================================

def sma_vol(period: int, symbols: list[str]) -> pd.DataFrame:
    v = cache.field("volume", symbols)
    return v.rolling(int(period), min_periods=int(period)).mean()


def bollinger(period: int, k: float, symbols: list[str]):
    """
    布林带。★ 原著标准(Bollinger 2001):中轨 = period 日 SMA,带宽 = ±k×σ,
    σ 用**总体标准差**(ddof=0)—— 这是 Bollinger 自己的定义。
    返回 (mid, upper, lower, pctb, bandwidth)。
    """
    close = cache.field("close", symbols)
    n, k = int(period), float(k)
    mid = close.rolling(n, min_periods=n).mean()
    sd = close.rolling(n, min_periods=n).std(ddof=0)
    up, lo = mid + k * sd, mid - k * sd
    width = (up - lo)
    pctb = (close - lo) / width.replace(0.0, np.nan)
    bw = width / mid.replace(0.0, np.nan)
    return mid, up, lo, pctb, bw


def adx(period: int, symbols: list[str]) -> pd.DataFrame:
    """Wilder ADX。出处:Wilder (1978) New Concepts in Technical Trading Systems。"""
    key = ("adx", tuple(symbols), int(period))
    if key in _CACHE:
        return _CACHE[key]
    h = cache.field("high", symbols)
    l = cache.field("low", symbols)
    c = cache.field("close", symbols)
    n = int(period)
    up = h.diff()
    dn = -l.diff()
    plus = up.where((up > dn) & (up > 0), 0.0)
    minus = dn.where((dn > up) & (dn > 0), 0.0)
    tr = pd.DataFrame(
        np.maximum(np.maximum((h - l).abs().to_numpy(float),
                              (h - c.shift(1)).abs().to_numpy(float)),
                   (l - c.shift(1)).abs().to_numpy(float)),
        index=h.index, columns=h.columns)
    a = 1.0 / n
    atr_ = tr.ewm(alpha=a, adjust=False, min_periods=n).mean()
    pdi = 100.0 * plus.ewm(alpha=a, adjust=False, min_periods=n).mean() / atr_
    mdi = 100.0 * minus.ewm(alpha=a, adjust=False, min_periods=n).mean() / atr_
    dx = 100.0 * (pdi - mdi).abs() / (pdi + mdi).replace(0.0, np.nan)
    out = dx.ewm(alpha=a, adjust=False, min_periods=n).mean()
    _CACHE[key] = out
    return out


def mfi(period: int, symbols: list[str]) -> pd.DataFrame:
    """
    资金流量指数 MFI。★ 技-14 原著版 Method III 要的「一个无相关性的指标」
    —— Bollinger 自己点名 MFI 或成交量积累派发线。
    """
    key = ("mfi", tuple(symbols), int(period))
    if key in _CACHE:
        return _CACHE[key]
    h = cache.field("high", symbols)
    l = cache.field("low", symbols)
    c = cache.field("close", symbols)
    v = cache.field("volume", symbols)
    tp = (h + l + c) / 3.0
    rmf = tp * v
    d = tp.diff()
    pos = rmf.where(d > 0, 0.0).rolling(int(period), min_periods=int(period)).sum()
    neg = rmf.where(d < 0, 0.0).rolling(int(period), min_periods=int(period)).sum()
    out = 100.0 - 100.0 / (1.0 + pos / neg.replace(0.0, np.nan))
    _CACHE[key] = out
    return out


def ma_slope_pct(period: int, lookback: int, symbols: list[str]) -> pd.DataFrame:
    """SMA(period) 的 lookback 日相对变化率(%)。技-3 的「上翘」用它。"""
    ma = matrices.sma_matrix(int(period), symbols)
    return (ma / ma.shift(int(lookback)) - 1.0) * 100.0


# ================================================================
# 技-3 温斯坦 —— 周线口径 vs 机械日线口径
# ================================================================

def _week_id(index: pd.DatetimeIndex) -> np.ndarray:
    """每个交易日属于哪一个 ISO 周(连号)。"""
    iso = index.isocalendar()
    y = np.asarray(iso["year"], dtype=np.int64)
    w = np.asarray(iso["week"], dtype=np.int64)
    key = y * 100 + w
    _, inv = np.unique(key, return_inverse=True)
    return inv


def weekly_frames(symbols: list[str]):
    """
    把日线聚合成周线(周内最后一个交易日代表这一周)。
    返回 (weekly_df 字典, 每周最后一个交易日的日线行号, week_id)。
    ★ 因果性:周线那一根在**周内最后一个交易日收盘**才完整,
      所以信号只允许挂在那一天,次日开盘成交。
    """
    key = ("weekly", tuple(symbols))
    if key in _CACHE:
        return _CACHE[key]
    h = cache.field("high", symbols)
    l = cache.field("low", symbols)
    c = cache.field("close", symbols)
    v = cache.field("volume", symbols)
    wid = _week_id(h.index)
    g = pd.Series(wid, index=h.index)
    wk = {
        "high": h.groupby(g).max(),
        "low": l.groupby(g).min(),
        "close": c.groupby(g).last(),
        "volume": v.groupby(g).sum(),
    }
    # 每周最后一个交易日在日线里的行号
    last_rows = pd.Series(np.arange(len(h.index)), index=h.index).groupby(g).max()
    out = (wk, last_rows.to_numpy(), wid)
    _CACHE[key] = out
    return out


def weinstein_weekly_breakout(symbols: list[str], base_weeks: int,
                              vol_mult: float, vol_avg_weeks: int,
                              require_vol: bool = True) -> pd.DataFrame:
    """
    ★★ 技-3 原著版「忠实周线版」。

    原文(Weinstein 1988, Ch.4 "The Buying Process", §"Volume Is a Must", p.74
    —— ★ 待核实):"a one-week volume spike that is at least twice the average
    volume of the past few weeks"。
    ★★ 关键:这是**周线口径**。一周累计成交量 ≥ 前几周周均量的 vol_mult 倍。

    实现:
      ① 周线收盘 > 前 base_weeks 根周线的最高价(= 突破底盘上沿,周线口径)
      ② 本周累计成交量 ≥ vol_mult × 前 vol_avg_weeks 周的周成交量均值
    信号只挂在该周最后一个交易日(日线行),次日开盘成交。
    """
    wk, last_rows, wid = weekly_frames(symbols)
    wc, wh, wv = wk["close"], wk["high"], wk["volume"]
    bw = int(base_weeks)
    prior_hi = wh.rolling(bw, min_periods=bw).max().shift(1)
    brk = wc > prior_hi
    if require_vol:
        avg = wv.rolling(int(vol_avg_weeks), min_periods=int(vol_avg_weeks)).mean().shift(1)
        brk = brk & (wv >= float(vol_mult) * avg)
    close = cache.field("close", symbols)
    out = np.zeros((len(close.index), len(symbols)), dtype=bool)
    b = brk.fillna(False).to_numpy(bool)
    for wi in range(b.shape[0]):
        out[last_rows[wi], :] = b[wi, :]
    return pd.DataFrame(out, index=close.index, columns=close.columns)


# ================================================================
# 技-4 欧奈尔杯柄 —— 逐票扫形态
# ================================================================

def _cup_one(high, low, close, p) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """
    单票扫杯柄。返回 (突破事件, 枢纽价, 柄部最高价)。

    地标(全部来自 O'Neil 原文的结构描述,★ 没有自由参数):
      ilp 杯左唇 = 窗口内杯底之前的最高价
      lo  杯底   = 窗口内最低价
      iph 柄高   = 杯底之后的最高价(= 枢纽点所在那根)
      柄         = iph 之后到 t−1
    死数(全部由配置传入,★ 引擎不填):
      杯深区间 / 柄深上限 / 杯最短长度 / 杯最长长度 / 柄长区间 / 枢纽加价
    ★ 另外用到一条「原文有、但不是数值」的结构约束:
      "the handle area should form in the upper half of the overall base"
      → 柄高 ≥ (左唇 + 杯底) / 2。★ 这不是我们填的数,是原文的结构描述。
    """
    n = len(close)
    dmin, dmax = float(p["cup_depth_min"]), float(p["cup_depth_max"])
    hmax = float(p["handle_max_depth"])
    cmin, cmax = int(p["cup_min_bars"]), int(p["cup_max_bars"])
    hbmin, hbmax = int(p["handle_min_bars"]), int(p["handle_max_bars"])
    piv_abs = p.get("pivot_offset_abs")
    piv_pct = p.get("pivot_offset_pct")

    ev = np.zeros(n, dtype=bool)
    pivot = np.full(n, np.nan)
    hhigh = np.full(n, np.nan)
    for t in range(cmax + 2, n):
        w0 = t - cmax
        if not np.isfinite(close[t]):
            continue
        segl = low[w0:t]
        if not np.isfinite(segl).all():
            continue
        lo = w0 + int(np.nanargmin(segl))
        if lo - w0 < 2 or t - lo < hbmin + 2:
            continue
        ilp = w0 + int(np.nanargmax(high[w0:lo]))
        lp = high[ilp]
        iph = lo + 1 + int(np.nanargmax(high[lo + 1:t]))
        ph = high[iph]
        handle_len = (t - 1) - iph
        if not (hbmin <= handle_len <= hbmax):
            continue
        if iph - ilp < cmin:
            continue
        hl = np.nanmin(low[iph:t])
        if ph <= 0 or (ph - hl) / ph > hmax:
            continue
        if lp <= 0:
            continue
        depth = (lp - low[lo]) / lp
        if not (dmin <= depth <= dmax):
            continue
        # 原文结构约束:柄在整个基底的上半部
        if ph < 0.5 * (lp + low[lo]):
            continue
        pv = ph + float(piv_abs) if piv_abs is not None else ph * (1.0 + float(piv_pct))
        if close[t] > pv:
            ev[t] = True
            pivot[t] = pv
            hhigh[t] = ph
    return ev, pivot, hhigh


def cup_with_handle(symbols: list[str], p: dict):
    """全池杯柄。返回 (突破事件矩阵, 枢纽价矩阵, 柄高矩阵)。逐票缓存。"""
    pk = tuple(sorted((k, str(v)) for k, v in p.items()))
    h = cache.field("high", symbols)
    l = cache.field("low", symbols)
    c = cache.field("close", symbols)
    idx = h.index
    ev = np.zeros((len(idx), len(symbols)), dtype=bool)
    pv = np.full((len(idx), len(symbols)), np.nan)
    hh = np.full((len(idx), len(symbols)), np.nan)
    ha, la, ca = h.to_numpy(float), l.to_numpy(float), c.to_numpy(float)
    for j, s in enumerate(symbols):
        key = ("cup", s, pk)
        if key not in _CACHE:
            _CACHE[key] = _cup_one(ha[:, j], la[:, j], ca[:, j], p)
        ev[:, j], pv[:, j], hh[:, j] = _CACHE[key]
    return (pd.DataFrame(ev, index=idx, columns=h.columns),
            pd.DataFrame(pv, index=idx, columns=h.columns),
            pd.DataFrame(hh, index=idx, columns=h.columns))


# ================================================================
# 技-6 达瓦斯箱体 —— ★★ 原著的离散事件规则(3 日规则)
# ================================================================

def _darvas_one(high, low, close, confirm_days: int):
    """
    单票跑达瓦斯 3 日规则。

    原文(Darvas 1960, Ch.4 "Developing the Box Theory", p.23-27 —— ★ 待核实):
      "I defined the top of the box as the highest price a stock reached as long
       as it did not penetrate that high for three consecutive days... The bottom
       of the box was defined as the lowest price reached after the top had been
       established, provided that price was not touched or broken for three
       consecutive days."

    ★★ 原著写死的只有「连续 3 天」这一个数。**振幅百分比没有任何区间。**

    返回 (box_top, box_bottom, box_alive, box_start) 四个逐日数组:
      箱体确立(箱顶箱底都确认)之后,逐日带着当时有效的箱顶箱底;
      价格收盘突破箱顶或跌破箱底 → 本箱作废,重新找新箱顶。
    """
    n = len(close)
    cd = int(confirm_days)
    top = np.full(n, np.nan)
    bot = np.full(n, np.nan)
    alive = np.zeros(n, dtype=bool)
    start = np.full(n, -1, dtype=np.int64)

    phase = "seek_top"
    cand_px = np.nan
    cnt = 0
    cur_top = cur_bot = np.nan
    cur_start = -1
    boxes: list[tuple[int, int, float, float]] = []   # (确立日, 结束日, top, bot)

    for i in range(n):
        if not np.isfinite(high[i]) or not np.isfinite(low[i]) or not np.isfinite(close[i]):
            continue
        if phase == "seek_top":
            if not np.isfinite(cand_px) or high[i] > cand_px:
                cand_px, cnt = high[i], 0          # 创新高 → 候选箱顶刷新,重新数
            else:
                cnt += 1
                if cnt >= cd:                      # 连续 cd 天没有穿破 → 箱顶确认
                    cur_top = cand_px
                    phase, cand_px, cnt = "seek_bottom", np.nan, 0
        elif phase == "seek_bottom":
            if high[i] > cur_top:                  # 还没等到箱底就先破了箱顶
                phase, cand_px, cnt = "seek_top", high[i], 0
                cur_top = np.nan
                continue
            if not np.isfinite(cand_px) or low[i] < cand_px:
                cand_px, cnt = low[i], 0
            else:
                cnt += 1
                if cnt >= cd:                      # 连续 cd 天没有触破 → 箱底确认
                    cur_bot = cand_px
                    cur_start = i
                    phase, cand_px, cnt = "in_box", np.nan, 0
                    boxes.append([i, n - 1, float(cur_top), float(cur_bot)])
        if phase == "in_box":
            top[i], bot[i], alive[i], start[i] = cur_top, cur_bot, True, cur_start
            if close[i] > cur_top or close[i] < cur_bot:
                boxes[-1][1] = i
                phase, cand_px, cnt = "seek_top", high[i], 0
                cur_top = cur_bot = np.nan
                cur_start = -1
    return top, bot, alive, start, [tuple(b) for b in boxes]


def darvas_boxes(symbols: list[str], confirm_days: int = 3):
    """全池跑达瓦斯 3 日规则。逐票缓存。返回 (top, bot, alive, start, boxes 字典)。"""
    h = cache.field("high", symbols)
    l = cache.field("low", symbols)
    c = cache.field("close", symbols)
    idx = h.index
    T, N = len(idx), len(symbols)
    top = np.full((T, N), np.nan)
    bot = np.full((T, N), np.nan)
    alive = np.zeros((T, N), dtype=bool)
    start = np.full((T, N), -1, dtype=np.int64)
    boxes: dict[str, list] = {}
    ha, la, ca = h.to_numpy(float), l.to_numpy(float), c.to_numpy(float)
    for j, s in enumerate(symbols):
        key = ("darvas", s, int(confirm_days))
        if key not in _CACHE:
            _CACHE[key] = _darvas_one(ha[:, j], la[:, j], ca[:, j], confirm_days)
        top[:, j], bot[:, j], alive[:, j], start[:, j], boxes[s] = _CACHE[key]
    f = lambda a: pd.DataFrame(a, index=idx, columns=h.columns)   # noqa: E731
    return f(top), f(bot), f(alive), f(start), boxes


def darvas_breakout(symbols: list[str], confirm_days: int,
                    max_amplitude: float | None,
                    min_box_bars: int) -> pd.DataFrame:
    """
    收盘突破箱顶 = 进场事件。
    max_amplitude / min_box_bars 是**行业版的安全阀**,不是箱体的定义:
      ★ 振幅上限来自止损距离风控(箱体太宽 → 止损太远,单笔风险超预算),
        ★ 不许写成「原著要求振幅小于 X」。
      ★ 原著版传 None / 0 → 不加这两道。
    """
    top, bot, alive, start, _ = darvas_boxes(symbols, confirm_days)
    close = cache.field("close", symbols)
    ok = alive & (close > top)
    if max_amplitude is not None:
        amp = (top - bot) / top
        ok = ok & (amp <= float(max_amplitude))
    if int(min_box_bars) > 0:
        rows = pd.DataFrame(np.arange(len(close.index))[:, None]
                            * np.ones((1, len(symbols))),
                            index=close.index, columns=close.columns)
        age = rows - start
        ok = ok & (age >= int(min_box_bars))
    return _bool(ok)


def narrow_range_box(symbols: list[str], bars: int, max_range_pct: float):
    """
    ★ XING 现有写法:「N 天内高低点区间收窄到 X%」。
    实现照我们在 状-2 行业版 / 状-4 用过的口径:
      近 bars 根的 (max(High) − min(Low)) / mean(Close) ≤ max_range_pct
    返回 (是不是窄幅箱体, 箱顶, 箱底) —— 全部只用到 t 及以前。
    """
    h = cache.field("high", symbols)
    l = cache.field("low", symbols)
    c = cache.field("close", symbols)
    n = int(bars)
    hi = h.rolling(n, min_periods=n).max()
    lo = l.rolling(n, min_periods=n).min()
    mu = c.rolling(n, min_periods=n).mean()
    narrow = ((hi - lo) / mu) <= float(max_range_pct)
    return _bool(narrow), hi, lo


def narrow_box_breakout(symbols: list[str], bars: int,
                        max_range_pct: float) -> pd.DataFrame:
    """XING 版进场:前 N 天是窄幅箱体,今天收盘突破那个箱顶。"""
    narrow, hi, lo = narrow_range_box(symbols, bars, max_range_pct)
    close = cache.field("close", symbols)
    return _bool(narrow.shift(1).fillna(False) & (close > hi.shift(1)))


# ================================================================
# 技-11 威科夫弹簧 —— 下刺深度 / 收复 / 缩量,以及 1/2/3 号分流
# ================================================================

def spring_events(symbols: list[str], p: dict):
    """
    行业版弹簧(Bob Evans → Pruden 2007 Ch.4 → Williams 1993 Ch.3 一脉的量化版)。

    返回 (事件矩阵, 诊断 DataFrame)。诊断逐事件记录:
      下刺深度(ATR 倍数 / 百分比)、当日量比、量是否低于前两日、收复用了几根。

    ★ 全部阈值由配置传入。★ 原著(1931 函授课程)三项全未写死 ——
      所以这一版的 source 一律是「后人量化版」,★ 不许标原著。
    """
    from . import ops_1029
    lb = int(_need(p, "lookback", "pat6_spring"))
    min_age = int(_need(p, "min_bars_before", "pat6_spring"))
    atr_n = int(_need(p, "atr_period", "pat6_spring"))
    dmin = float(_need(p, "depth_min_atr", "pat6_spring"))
    dmax = float(_need(p, "depth_max_atr", "pat6_spring"))
    hard = float(_need(p, "depth_hard_cap_atr", "pat6_spring"))
    rec_mult = float(_need(p, "reclaim_atr_multiple", "pat6_spring"))
    rec_bars = int(_need(p, "reclaim_max_bars", "pat6_spring"))
    vmax = float(_need(p, "vol_test_max_ratio", "pat6_spring"))
    vslow = int(_need(p, "vol_slow_period", "pat6_spring"))
    v_below_prior2 = bool(_need(p, "vol_below_prior_two", "pat6_spring"))
    if dmax > hard:
        raise ValueError(f"下刺深度上限 {dmax} 超过硬帽 {hard} —— 配置自相矛盾")

    sl, age = ops_1029.swing_low_20(tuple(symbols), lb)
    low = cache.field("low", symbols)
    close = cache.field("close", symbols)
    vol = cache.field("volume", symbols)
    atr = matrices.atr_matrix(atr_n, symbols)
    sv = vol.rolling(vslow, min_periods=vslow).mean().shift(1)

    sla, aga = sl.to_numpy(float), age.to_numpy(float)
    la, ca = low.to_numpy(float), close.to_numpy(float)
    va, sva, aa = vol.to_numpy(float), sv.to_numpy(float), atr.to_numpy(float)
    T, N = la.shape
    ev = np.zeros((T, N), dtype=bool)
    rows = []
    for j in range(N):
        for t in range(T):
            prior = sla[t, j]
            if not np.isfinite(prior) or aga[t, j] < min_age:
                continue
            if not (np.isfinite(la[t, j]) and la[t, j] < prior):
                continue                             # 没有下刺
            a = aa[t, j]
            if not np.isfinite(a) or a <= 0:
                continue
            dep = prior - la[t, j]
            dep_atr = dep / a
            if dep_atr > hard:
                continue                             # 超过硬帽 → 真实破位,不是弹簧
            if not (dmin <= dep_atr <= dmax):
                continue
            # 缩量测试
            if not np.isfinite(sva[t, j]) or sva[t, j] <= 0:
                continue
            vr = va[t, j] / sva[t, j]
            if vr > vmax:
                continue
            if v_below_prior2:
                if t < 2 or not (va[t, j] < min(va[t - 1, j], va[t - 2, j])):
                    continue
            # 收复:当日起最多 rec_bars 根内收盘收复到 前低 + rec_mult×ATR
            thr = prior + rec_mult * a
            hit = -1
            for k in range(0, rec_bars + 1):
                if t + k >= T:
                    break
                if np.isfinite(ca[t + k, j]) and ca[t + k, j] >= thr:
                    hit = t + k
                    break
            if hit < 0:
                continue
            ev[hit, j] = True
            rows.append({"symbol": symbols[j], "break_row": t, "signal_row": hit,
                         "prior_low": prior, "low": la[t, j],
                         "pen_pct": dep / prior, "dep_atr": dep_atr,
                         "vol_ratio": vr, "reclaim_bars": hit - t})
    return (pd.DataFrame(ev, index=low.index, columns=low.columns),
            pd.DataFrame(rows))


def spring_two_day(symbols: list[str], p: dict):
    """
    ★★ 技-11 两日结构版 —— 批五修正(2026-10-29)。

    大白话(三秒):老版本把「下刺收复那一天」和「缩量测试那一天」当成同一天,
    还要求下刺收复当天缩量 —— 这在物理上自相矛盾:既然止损盘被打爆、
    主力在吸货,那一天只能是放量。这一版把两天拆开。

    Day 1(Spring 发生日):
      · 盘中跌破前 lookback 日低点(该低点至少 min_bars_before 天老)
      · 当日收盘收复:Close ≥ 前低 + reclaim_atr_multiple × ATR
      · ★★ 当日成交量【不低于】spring_vol_min_ratio × SMA(vol_slow_period)
        —— ★ 这是和老版本【方向相反】的那一条。
      · depth_hard_cap_atr 为 None 时**不设深度上限**(深度分档另行实测)

    Day 2 ~ Day N(Test 测试日,N = test_max_bars):
      · 回踩:Low_t > 前低(守住了被下刺的那条线)
      · 且 Close_t ≤ Spring 日收盘(确实是回踩,不是继续冲高)
      · 且 Vol_t ≤ test_vol_max_ratio × SMA(vol_slow_period)
        —— ★★ 原著体系里「极度缩量」要的是【这一天】,不是 Spring 当天

    进场:Test 日收盘确认 → 次日开盘(信号挂在 Test 日那一行)。

    ★★ 归属:Wyckoff 1931 原著只有 Terminal Shakeout,【没有 1/2/3 号分类】,
      两日结构是 Bob Evans(1930s-50s)口头归纳 → Pruden(2007) /
      Williams(1993) 整理出版的【后人量化版,无统计支持】,
      ★ 不是【原著写死】。所有引文【待核实】。
    ★ 「回踩」的那两条判据(Low_t > 前低、Close_t ≤ Spring 日收盘)是
      ★★【我们自己定的可执行化口径】—— 原著只有散文描述,没有任何可执行阈值。

    返回 (事件矩阵, 诊断 DataFrame)。
    """
    from . import ops_1029
    lb = int(_need(p, "lookback", "pat6_spring_two_day"))
    min_age = int(_need(p, "min_bars_before", "pat6_spring_two_day"))
    atr_n = int(_need(p, "atr_period", "pat6_spring_two_day"))
    rec_mult = float(_need(p, "reclaim_atr_multiple", "pat6_spring_two_day"))
    v_min = float(_need(p, "spring_vol_min_ratio", "pat6_spring_two_day"))
    test_n = int(_need(p, "test_max_bars", "pat6_spring_two_day"))
    test_vmax = float(_need(p, "test_vol_max_ratio", "pat6_spring_two_day"))
    vslow = int(_need(p, "vol_slow_period", "pat6_spring_two_day"))
    if "depth_hard_cap_atr" not in p:
        raise NotImplementedError(
            "pat6_spring_two_day 必须显式写 depth_hard_cap_atr —— "
            "不设上限就写 null,★ 引擎不替它选一边。")
    hard = p["depth_hard_cap_atr"]
    hard = float(hard) if hard is not None else None

    sl, age = ops_1029.swing_low_20(tuple(symbols), lb)
    low = cache.field("low", symbols)
    close = cache.field("close", symbols)
    vol = cache.field("volume", symbols)
    atr = matrices.atr_matrix(atr_n, symbols)
    sv = vol.rolling(vslow, min_periods=vslow).mean().shift(1)

    sla, aga = sl.to_numpy(float), age.to_numpy(float)
    la, ca = low.to_numpy(float), close.to_numpy(float)
    va, sva, aa = vol.to_numpy(float), sv.to_numpy(float), atr.to_numpy(float)
    T, N = la.shape
    ev = np.zeros((T, N), dtype=bool)
    rows = []
    for j in range(N):
        for t in range(T):
            prior = sla[t, j]
            if not np.isfinite(prior) or aga[t, j] < min_age:
                continue
            if not (np.isfinite(la[t, j]) and la[t, j] < prior):
                continue                             # 没有下刺
            a = aa[t, j]
            if not np.isfinite(a) or a <= 0:
                continue
            dep_atr = (prior - la[t, j]) / a
            if hard is not None and dep_atr > hard:
                continue
            # Day 1 收复
            if not (np.isfinite(ca[t, j]) and ca[t, j] >= prior + rec_mult * a):
                continue
            # ★★ Day 1 必须有量 —— 和老版本方向相反的那一条
            if not np.isfinite(sva[t, j]) or sva[t, j] <= 0:
                continue
            vr1 = va[t, j] / sva[t, j]
            if not (vr1 >= v_min):
                continue
            # Day 2..N 缩量测试
            hit, vr2 = -1, np.nan
            for k in range(1, test_n + 1):
                u = t + k
                if u >= T:
                    break
                if not (np.isfinite(la[u, j]) and np.isfinite(ca[u, j])
                        and np.isfinite(sva[u, j]) and sva[u, j] > 0):
                    continue
                if la[u, j] <= prior:
                    continue                         # 又破了 → 不是守住的回踩
                if ca[u, j] > ca[t, j]:
                    continue                         # 不是回踩
                r2 = va[u, j] / sva[u, j]
                if r2 <= test_vmax:
                    hit, vr2 = u, r2
                    break
            if hit < 0:
                continue
            ev[hit, j] = True
            rows.append({"symbol": symbols[j], "spring_row": t, "test_row": hit,
                         "prior_low": prior, "spring_low": la[t, j],
                         "dep_atr": dep_atr, "pen_pct": (prior - la[t, j]) / prior,
                         "spring_vol_ratio": vr1, "test_vol_ratio": vr2,
                         "test_lag": hit - t})
    return (pd.DataFrame(ev, index=low.index, columns=low.columns),
            pd.DataFrame(rows))


def spring_day1_pool(symbols: list[str], lookback: int, min_age: int,
                     atr_period: int, vol_slow: int,
                     reclaim_atr_multiple: float,
                     spring_vol_min_ratio: float) -> pd.DataFrame:
    """
    ★ Day 1(Spring 发生日)的**母集**,★ 不设任何深度上限 ——
      专门给「下刺深度分档」那道实测用:要看 >1.5ATR 到底该不该禁,
      就不能先把它筛掉。
    """
    from . import ops_1029
    sl, age = ops_1029.swing_low_20(tuple(symbols), int(lookback))
    low = cache.field("low", symbols)
    close = cache.field("close", symbols)
    vol = cache.field("volume", symbols)
    atr = matrices.atr_matrix(int(atr_period), symbols)
    sv = vol.rolling(int(vol_slow), min_periods=int(vol_slow)).mean().shift(1)

    sla, aga = sl.to_numpy(float), age.to_numpy(float)
    la, ca = low.to_numpy(float), close.to_numpy(float)
    va, sva, aa = vol.to_numpy(float), sv.to_numpy(float), atr.to_numpy(float)
    T, N = la.shape
    rows = []
    for j in range(N):
        for t in range(T):
            prior = sla[t, j]
            if not np.isfinite(prior) or aga[t, j] < min_age:
                continue
            if not (np.isfinite(la[t, j]) and la[t, j] < prior):
                continue
            a = aa[t, j]
            if not (np.isfinite(a) and a > 0):
                continue
            if not (np.isfinite(ca[t, j])
                    and ca[t, j] >= prior + float(reclaim_atr_multiple) * a):
                continue
            if not (np.isfinite(sva[t, j]) and sva[t, j] > 0):
                continue
            vr = va[t, j] / sva[t, j]
            if vr < float(spring_vol_min_ratio):
                continue
            rows.append({"symbol": symbols[j], "row": t, "date": low.index[t],
                         "dep_atr": (prior - la[t, j]) / a,
                         "pen_pct": (prior - la[t, j]) / prior,
                         "vol_ratio": vr})
    return pd.DataFrame(rows)


def spring_triage(symbols: list[str], lookback: int, min_age: int,
                  atr_period: int, vol_slow: int,
                  micro_pen_pct: float, micro_vol_ratio: float,
                  terminal_pen_pct: float, terminal_vol_ratio: float
                  ) -> pd.DataFrame:
    """
    ★★ Spring 1/2/3 号分流 —— 只分类,不加任何筛选。

    口径(★ 这个分界是我们按专家散文定的,不是原文给的数,报告里必须这样写):
      #3 微观弹簧:跌破幅度 ≤ micro_pen_pct 且 量比 ≤ micro_vol_ratio
      #1 终极洗盘:跌破幅度 > terminal_pen_pct 或 量比 ≥ terminal_vol_ratio
      #2 常规洗盘:其余
    筛选条件只有「下刺 + 当日收盘收复到前低之上」—— 三号共用同一个母集,
    ★ 这样三号的笔数才可比。
    """
    from . import ops_1029
    sl, age = ops_1029.swing_low_20(tuple(symbols), int(lookback))
    low = cache.field("low", symbols)
    close = cache.field("close", symbols)
    vol = cache.field("volume", symbols)
    atr = matrices.atr_matrix(int(atr_period), symbols)
    sv = vol.rolling(int(vol_slow), min_periods=int(vol_slow)).mean().shift(1)

    sla, aga = sl.to_numpy(float), age.to_numpy(float)
    la, ca = low.to_numpy(float), close.to_numpy(float)
    va, sva, aa = vol.to_numpy(float), sv.to_numpy(float), atr.to_numpy(float)
    T, N = la.shape
    rows = []
    for j in range(N):
        for t in range(T):
            prior = sla[t, j]
            if not np.isfinite(prior) or aga[t, j] < min_age:
                continue
            if not (np.isfinite(la[t, j]) and la[t, j] < prior):
                continue
            if not (np.isfinite(ca[t, j]) and ca[t, j] > prior):
                continue                         # 当日必须收回到前低之上
            if not np.isfinite(sva[t, j]) or sva[t, j] <= 0:
                continue
            pen = (prior - la[t, j]) / prior
            vr = va[t, j] / sva[t, j]
            a = aa[t, j]
            if pen <= micro_pen_pct and vr <= micro_vol_ratio:
                cls = "#3 微观弹簧"
            elif pen > terminal_pen_pct or vr >= terminal_vol_ratio:
                cls = "#1 终极洗盘"
            else:
                cls = "#2 常规洗盘"
            rows.append({"symbol": symbols[j], "row": t,
                         "date": low.index[t], "号": cls,
                         "pen_pct": pen, "vol_ratio": vr,
                         "dep_atr": (prior - la[t, j]) / a if np.isfinite(a) and a > 0 else np.nan,
                         "close": ca[t, j]})
    return pd.DataFrame(rows)


# ================================================================
# 技-14 布林带
# ================================================================

def bb_tag_lower(symbols: list[str], p: dict) -> pd.DataFrame:
    """★ XING 现有写法:收盘跌破下轨就买。Bollinger 本人点名反对(Rule 4)。"""
    _, _, lo, _, _ = bollinger(int(_need(p, "period", "pat6_bb_tag_lower")),
                               float(_need(p, "k", "pat6_bb_tag_lower")), symbols)
    return _bool(cache.field("close", symbols) < lo)


def bb_reclaim(symbols: list[str], p: dict) -> pd.DataFrame:
    """
    行业版三步进场:
      ① 当日盘中跌破下轨,或前一日收盘已在下轨之下(%b < 0)
      ② 当日收盘强力收复到下轨之上,且收阳线实体(Close > Lower and Close > Open)
      ③ 2 日 RSI 从 < rsi_low 向上回升到 > rsi_back
    """
    n = int(_need(p, "period", "pat6_bb_reclaim"))
    k = float(_need(p, "k", "pat6_bb_reclaim"))
    rsi_n = int(_need(p, "rsi_period", "pat6_bb_reclaim"))
    r_lo = float(_need(p, "rsi_low", "pat6_bb_reclaim"))
    r_back = float(_need(p, "rsi_back", "pat6_bb_reclaim"))
    _, _, lo, pctb, _ = bollinger(n, k, symbols)
    close = cache.field("close", symbols)
    op = cache.field("open", symbols)
    low = cache.field("low", symbols)
    rsi = matrices.rsi_matrix(rsi_n, symbols)
    step1 = (low < lo) | (pctb.shift(1) < 0.0)
    step2 = (close > lo) & (close > op)
    step3 = (rsi.shift(1) < r_lo) & (rsi > r_back)
    return _bool(step1 & step2 & step3)


def bb_trend_filters(symbols: list[str], p: dict) -> pd.DataFrame:
    """
    行业版必配的三道趋势过滤器:
      ① 收盘在 200 日均线上方,且 200 日线 20 日斜率 ≥ 0
      ② ADX(14) ≤ adx_max(ADX > 25 是强趋势,此时碰下轨是顺势做空点)
      ③ 带宽突变熔断:(BW_t − BW_{t−3}) / BW_{t−3} ≤ bw_jump_max
    """
    ma_n = int(_need(p, "ma_period", "pat6_bb_trend_filters"))
    slope_lb = int(_need(p, "slope_lookback", "pat6_bb_trend_filters"))
    adx_n = int(_need(p, "adx_period", "pat6_bb_trend_filters"))
    adx_max = float(_need(p, "adx_max", "pat6_bb_trend_filters"))
    bb_n = int(_need(p, "period", "pat6_bb_trend_filters"))
    bb_k = float(_need(p, "k", "pat6_bb_trend_filters"))
    jump_lb = int(_need(p, "bw_jump_lookback", "pat6_bb_trend_filters"))
    jump_max = float(_need(p, "bw_jump_max", "pat6_bb_trend_filters"))
    close = cache.field("close", symbols)
    ma = matrices.sma_matrix(ma_n, symbols)
    f1 = (close > ma) & (ma_slope_pct(ma_n, slope_lb, symbols) >= 0.0)
    f2 = adx(adx_n, symbols) <= adx_max
    _, _, _, _, bw = bollinger(bb_n, bb_k, symbols)
    f3 = ((bw / bw.shift(jump_lb) - 1.0) <= jump_max)
    return _bool(f1 & f2 & f3)


def bb_reversal(symbols: list[str], p: dict) -> pd.DataFrame:
    """
    ★ 批五修正:专家给的 Reversal_Trigger,逐字落地 ——
      (Low < LowerBand) and (Close > LowerBand) and (Close > Open)
    ★ 和老的 pat6_bb_reclaim 的差别:① 第一步只要**当日盘中**破轨
      (老版本还放行「前一日收盘已在轨下」);② 不带 RSI 回升那一步
      (RSI 那一步在新组合里由 pat6_rsi_oversold 单独承担)。
    """
    n = int(_need(p, "period", "pat6_bb_reversal"))
    k = float(_need(p, "k", "pat6_bb_reversal"))
    _, _, lo, _, _ = bollinger(n, k, symbols)
    close = cache.field("close", symbols)
    op = cache.field("open", symbols)
    low = cache.field("low", symbols)
    return _bool((low < lo) & (close > lo) & (close > op))


def rsi_oversold(symbols: list[str], p: dict) -> pd.DataFrame:
    """
    ★ 批五修正:Oversold_Trigger = RSI(rsi_period) ≤ max_rsi。
    出处:Connors & Alvarez《Short Term Trading Strategies That Work》(2008)
    的 RSI(2) 体系【待核实】。★ RSI 用 Wilder 平滑(matrices.rsi_matrix)。
    """
    n = int(_need(p, "rsi_period", "pat6_rsi_oversold"))
    mx = float(_need(p, "max_rsi", "pat6_rsi_oversold"))
    return _bool(matrices.rsi_matrix(n, symbols) <= mx)


def bb_trend_gate(symbols: list[str], p: dict) -> pd.DataFrame:
    """
    ★ 批五修正:只剩 Trend_Gate 这一道 ——
      Close > SMA(ma_period) and Slope(slope_lookback) of SMA ≥ 0。
    ★★ ADX(14) ≤ 25 那一道【已废除】:专家自认那是「教科书里流传最广但
      未经解耦的教条毒药」—— ADX 不分方向,强牛市里的深度急跌(黄金坑)
      会把 ADX 瞬间推到 30~45,于是 ADX≤25 精准切掉了弹性最大的买点,
      放行的反而是毫无动能的死水横盘。
    """
    ma_n = int(_need(p, "ma_period", "pat6_bb_trend_gate"))
    slope_lb = int(_need(p, "slope_lookback", "pat6_bb_trend_gate"))
    close = cache.field("close", symbols)
    ma = matrices.sma_matrix(ma_n, symbols)
    return _bool((close > ma) & (ma_slope_pct(ma_n, slope_lb, symbols) >= 0.0))


def bb_bw_jump_gate(symbols: list[str], p: dict) -> pd.DataFrame:
    """
    ★ 批五修正:带宽突变熔断单独拆出来 —— (BW_t − BW_{t−lb}) / BW_{t−lb} ≤ max。
    ★ 专家没说废这一道,所以单独拆出来做「带它 / 不带它」的对照。
    """
    bb_n = int(_need(p, "period", "pat6_bb_bw_jump_gate"))
    bb_k = float(_need(p, "k", "pat6_bb_bw_jump_gate"))
    lb = int(_need(p, "bw_jump_lookback", "pat6_bb_bw_jump_gate"))
    mx = float(_need(p, "bw_jump_max", "pat6_bb_bw_jump_gate"))
    _, _, _, _, bw = bollinger(bb_n, bb_k, symbols)
    return _bool((bw / bw.shift(lb) - 1.0) <= mx)


def w_bottom_divergence(symbols: list[str], p: dict) -> pd.DataFrame:
    """
    ★★ 技-14「原著版」= Bollinger 自己认可的 Method III (Reversals) 近似。

    原著 Rule 4(Bollinger 2001, Ch.12, p.119 —— ★ 待核实):
      "Tags of the bands are just that, tags not signals."
    他认可的反转用法必须由 **W 底形态 + 一个无相关性的指标底背离** 构成。

    近似实现(★ 全部是结构比较,只有「找上一个波谷的回看窗口」是数值):
      · 波谷用分型(半宽 half_width)认定,确认日 = 波谷 + half_width
      · 对确认的波谷 L2,在 [min_gap, max_gap] 根之前找上一个波谷 L1
      · W 底判据(Bollinger 的 W4):Low(L2) < Low(L1) 但 %b(L2) > %b(L1)
        —— 价格创了新低,相对下轨的位置反而更高;
        ★ 并且照原文再加两条结构条件(都不是数值):
          L1 必须刺破下轨(%b(L1) < 0),L2 必须守在下轨之上(%b(L2) > 0)
      · 无相关指标底背离:MFI(L2) > MFI(L1)
    ★ 这是「近似」,不是原著原文的算法 —— 报告里必须这样写。
    """
    hw = int(_need(p, "fractal_half_width", "pat6_w_bottom"))
    gmin = int(_need(p, "min_gap_bars", "pat6_w_bottom"))
    gmax = int(_need(p, "max_gap_bars", "pat6_w_bottom"))
    bb_n = int(_need(p, "period", "pat6_w_bottom"))
    bb_k = float(_need(p, "k", "pat6_w_bottom"))
    mfi_n = int(_need(p, "mfi_period", "pat6_w_bottom"))

    low = cache.field("low", symbols)
    _, _, _, pctb, _ = bollinger(bb_n, bb_k, symbols)
    mf = mfi(mfi_n, symbols)
    w = 2 * hw + 1
    is_l = (low == low.rolling(w, center=True, min_periods=w).min()) & low.notna()

    la = low.to_numpy(float)
    pa = pctb.to_numpy(float)
    ma = mf.to_numpy(float)
    lb = is_l.to_numpy(bool)
    T, N = la.shape
    ev = np.zeros((T, N), dtype=bool)
    for j in range(N):
        piv = np.flatnonzero(lb[:, j])
        for a in range(1, len(piv)):
            i2 = piv[a]
            for b in range(a - 1, -1, -1):
                i1 = piv[b]
                gap = i2 - i1
                if gap > gmax:
                    break
                if gap < gmin:
                    continue
                if not (np.isfinite(la[i2, j]) and np.isfinite(la[i1, j])):
                    continue
                if not (np.isfinite(pa[i2, j]) and np.isfinite(pa[i1, j])):
                    continue
                if not (np.isfinite(ma[i2, j]) and np.isfinite(ma[i1, j])):
                    continue
                if la[i2, j] < la[i1, j] and pa[i2, j] > pa[i1, j] \
                        and pa[i1, j] < 0.0 and pa[i2, j] > 0.0 \
                        and ma[i2, j] > ma[i1, j]:
                    c = i2 + hw                    # ★ 分型要等 hw 根才确认
                    if c < T:
                        ev[c, j] = True
                    break
    return pd.DataFrame(ev, index=low.index, columns=low.columns)


# ================================================================
# 挂钩 —— 把上面的算子接到引擎的 ③ 进场 / ⑥ 离场上
# ================================================================

_ENTRY_TYPES = {
    "pat6_weinstein_weekly_breakout",
    "pat6_daily_base_breakout",
    "pat6_volume_x_sma",
    "pat6_flat_base",
    "pat6_ma_slope_up",
    "pat6_cup_with_handle",
    "pat6_darvas_breakout",
    "pat6_narrow_box_breakout",
    "pat6_spring",
    "pat6_spring_two_day",
    "pat6_bb_tag_lower",
    "pat6_bb_reclaim",
    "pat6_bb_trend_filters",
    "pat6_bb_reversal",
    "pat6_rsi_oversold",
    "pat6_bb_trend_gate",
    "pat6_bb_bw_jump_gate",
    "pat6_w_bottom_divergence",
}
_EXIT_TYPES = {
    "pat6_close_above_bb_mid",
    "pat6_close_above_bb_upper",
    "pat6_close_below_darvas_bottom",
}

_orig_entry = None
_orig_exit = None


def _entry(rule: dict, symbols: list[str]):
    t = rule.get("type")
    p = rule.get("params", {}) or {}
    if t not in _ENTRY_TYPES:
        return _orig_entry(rule, symbols)

    if t == "pat6_weinstein_weekly_breakout":
        return _bool(weinstein_weekly_breakout(
            symbols,
            base_weeks=int(_need(p, "base_weeks", t)),
            vol_mult=float(_need(p, "volume_multiple", t)),
            vol_avg_weeks=int(_need(p, "volume_avg_weeks", t)),
            require_vol=bool(p.get("require_volume", True))))

    if t == "pat6_daily_base_breakout":
        n = int(_need(p, "base_bars", t))
        high = cache.field("high", symbols)
        close = cache.field("close", symbols)
        return _bool(close > high.rolling(n, min_periods=n).max().shift(1))

    if t == "pat6_volume_x_sma":
        per = int(_need(p, "period", t))
        mult = float(_need(p, "multiple", t))
        off = int(p.get("baseline_offset_days", 1))
        v = cache.field("volume", symbols)
        return _bool(v >= mult * sma_vol(per, symbols).shift(off))

    if t == "pat6_flat_base":
        narrow, _, _ = narrow_range_box(symbols, int(_need(p, "bars", t)),
                                        float(_need(p, "max_range_pct", t)))
        return _bool(narrow.shift(1).fillna(False))

    if t == "pat6_ma_slope_up":
        s = ma_slope_pct(int(_need(p, "ma_period", t)),
                         int(_need(p, "slope_lookback", t)), symbols)
        return _bool(s >= float(_need(p, "min_slope_pct", t)))

    if t == "pat6_cup_with_handle":
        need = ["cup_depth_min", "cup_depth_max", "handle_max_depth",
                "cup_min_bars", "cup_max_bars", "handle_min_bars",
                "handle_max_bars"]
        for k in need:
            _need(p, k, t)
        if p.get("pivot_offset_abs") is None and p.get("pivot_offset_pct") is None:
            raise NotImplementedError(
                f"{t} 必须显式写 pivot_offset_abs(原著 +$0.10)或 "
                f"pivot_offset_pct(行业缓冲)—— ★ 引擎不替它选一边。")
        ev, _, _ = cup_with_handle(symbols, p)
        return _bool(ev)

    if t == "pat6_darvas_breakout":
        return darvas_breakout(
            symbols,
            confirm_days=int(_need(p, "confirm_days", t)),
            max_amplitude=p.get("max_amplitude"),
            min_box_bars=int(p.get("min_box_bars", 0)))

    if t == "pat6_narrow_box_breakout":
        return narrow_box_breakout(symbols, int(_need(p, "bars", t)),
                                   float(_need(p, "max_range_pct", t)))

    if t == "pat6_spring":
        ev, _ = spring_events(symbols, p)
        return _bool(ev)

    if t == "pat6_spring_two_day":
        ev, _ = spring_two_day(symbols, p)
        return _bool(ev)

    if t == "pat6_bb_reversal":
        return bb_reversal(symbols, p)
    if t == "pat6_rsi_oversold":
        return rsi_oversold(symbols, p)
    if t == "pat6_bb_trend_gate":
        return bb_trend_gate(symbols, p)
    if t == "pat6_bb_bw_jump_gate":
        return bb_bw_jump_gate(symbols, p)

    if t == "pat6_bb_tag_lower":
        return bb_tag_lower(symbols, p)
    if t == "pat6_bb_reclaim":
        return bb_reclaim(symbols, p)
    if t == "pat6_bb_trend_filters":
        return bb_trend_filters(symbols, p)
    if t == "pat6_w_bottom_divergence":
        return w_bottom_divergence(symbols, p)
    raise AssertionError(t)


def _exit(spec: dict, symbols: list[str]):
    spec = spec or {}
    mine = [r for r in (spec.get("rules") or []) if r.get("type") in _EXIT_TYPES]
    rest = {k: v for k, v in spec.items() if k != "rules"}
    rest["rules"] = [r for r in (spec.get("rules") or [])
                     if r.get("type") not in _EXIT_TYPES]
    out = _orig_exit(rest, symbols)
    close = cache.field("close", symbols)
    for r in mine:
        p = r.get("params", {}) or {}
        t = r["type"]
        if t in ("pat6_close_above_bb_mid", "pat6_close_above_bb_upper"):
            mid, up, _, _, _ = bollinger(int(_need(p, "period", t)),
                                         float(_need(p, "k", t)), symbols)
            band = mid if t.endswith("mid") else up
            out = out | _bool(close > band)
        elif t == "pat6_close_below_darvas_bottom":
            _, bot, alive, _, _ = darvas_boxes(
                symbols, int(_need(p, "confirm_days", t)))
            out = out | _bool(alive & (close < bot))
    return out


def install() -> None:
    """运行时挂钩。★ 不改 matrices.py 一个字符。"""
    global _orig_entry, _orig_exit
    from . import config_adapter
    if _orig_entry is None:
        _orig_entry = matrices._entry_rule_raw
        matrices._entry_rule_raw = _entry
    if _orig_exit is None:
        _orig_exit = matrices.exit_signal_matrix
        matrices.exit_signal_matrix = _exit
    config_adapter.IMPLEMENTED["entry"] |= _ENTRY_TYPES
    config_adapter.IMPLEMENTED["exit"] |= _EXIT_TYPES
    note("pat6 算子已挂钩(运行时),matrices.py / chain.py / config_adapter.py "
         "三个文件一个字符都没改。")
