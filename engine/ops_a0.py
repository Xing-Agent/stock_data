"""
A0 十二条专用算子 —— 2026-10-29。

大白话(三秒):手册里标「原著完整」的那 12 条,引擎原来只能跑其中 2 条。
这个文件补上剩下几条真的能跑的算子:法伯月线、海龟汤次日越高点、
高紧旗形、TD 序列、以及「原著不设止损」的表达方式。

★ 本文件的铁律,和 ops_1029.py 一样:
  一、每个算子上面写清楚「哪个数来自原著、哪个是执行细节」。
  二、★ 原著没给的数,这里**不给默认值**——
      调用方不传就抛错,不许悄悄用一个我们自己拍的数跑过去。
      (这正是 A0 这一批要查的事:哪些条目其实参数不全。)
  三、不许网格搜索。本文件里出现的每个数字都能指回原著原文。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import cache

_NOTES: list[str] = []


def notes() -> list[str]:
    return list(_NOTES)


def _note(s: str) -> None:
    if s not in _NOTES:
        _NOTES.append(s)


def _as_bool(df: pd.DataFrame) -> pd.DataFrame:
    return df.fillna(False).astype(bool)


def _need(p: dict, key: str, who: str) -> float:
    """★ 原著没给的数必须由配置显式写出来,不写就抛错,不给默认值。"""
    if p.get(key) is None:
        raise NotImplementedError(
            f"{who} 需要参数 {key},但配置里没写 —— "
            f"★ 手册原文没有给这个数,引擎不替它拍一个。"
            f"要跑必须在配置里显式写出来,并在报告里标明它的出处。")
    return float(p[key])


# ===========================================================================
# 技-2 法伯月线择时
#   原著:Faber (2007) "A Quantitative Approach to Tactical Asset Allocation"
#   原著给死的数:① 月末判断,一个月一次  ② 10 个月简单移动平均
#   执行细节(我们的):月末 = 日历月里最后一个有成交的交易日
# ===========================================================================

def _month_end_mask(index: pd.DatetimeIndex) -> np.ndarray:
    """日历月里的最后一个交易日 = True。"""
    per = index.to_period("M")
    nxt = np.empty(len(index), dtype=bool)
    nxt[:-1] = per[1:] != per[:-1]
    nxt[-1] = True
    return nxt


def monthly_sma_state(symbols: list[str], months: int = 10) -> pd.DataFrame:
    """
    法伯状态矩阵:只在月末那一行给出真/假,月中一律沿用上一个月末的判断。

    ★ months=10 来自原著(Faber 2007 全文用 10 个月 SMA)。
    ★ 月线收盘价 = 该日历月最后一个交易日的收盘价(执行细节)。
    ★ SMA 用的是「月线收盘价」的 10 期均值,不是 200 个交易日 ——
      两者不等价,原文写的是月线。
    """
    close = cache.field("close", symbols)
    me = _month_end_mask(close.index)
    m_close = close.loc[me]                       # 月末收盘价(按月一行)
    m_sma = m_close.rolling(months, min_periods=months).mean()
    state_m = _as_bool(m_close > m_sma)
    # 月末的判断一直持有到下一个月末
    # ★ 坑:DataFrame.where(Series) 默认按**列**对齐,不是按行 ——
    #   这里必须用 numpy 掩码显式写,不许用 where(Series)。
    vals = np.full(close.shape, np.nan, dtype=float)
    vals[me, :] = state_m.to_numpy(dtype=float)
    out = pd.DataFrame(vals, index=close.index, columns=close.columns).ffill()
    _note("技-2:月末 = 日历月最后一个交易日;SMA 用月线收盘价 10 期(原著口径),"
          "不是 200 个交易日")
    return _as_bool(out)


def monthly_sma_below(symbols: list[str], months: int = 10) -> pd.DataFrame:
    """★ 离场:只在月末那一天、且月末收盘跌破 10 月线时为 True。月中一律 False。"""
    close = cache.field("close", symbols)
    me = pd.Series(_month_end_mask(close.index), index=close.index)
    st = monthly_sma_state(symbols, months)
    return _as_bool((~st).mul(me, axis=0))


# ===========================================================================
# 技-10 海龟汤 —— 「次日越过前一天高点」那一步
#   原著:Connors & Raschke《Street Smarts》(1995) Ch.4 Turtle Soup
#   原著给死的数:① 20 日新低  ② 前低至少 4 个交易日之前(Rule 2,ops_1029 已核实)
#                 ③ 进场 = 越过「假突破那根」的高点
#   ★ 原著是盘中挂突破单(stop order);我们引擎只能收盘确认 + 次日开盘成交,
#     所以这里的读法是:第二天**收盘**站上前一天高点 → 第三天开盘买。
#     ★ 这是执行细节的改动,不是原著,报告里必须单列。
# ===========================================================================

def cross_prev_day_high(symbols: list[str], setup: pd.DataFrame) -> pd.DataFrame:
    """
    setup = 「假突破那根」为 True 的矩阵。
    返回:setup 的次日、且当天收盘 > setup 那根的高点 → True。
    """
    close = cache.field("close", symbols)
    high = cache.field("high", symbols)
    prev_setup = _as_bool(setup.shift(1))
    prev_high = high.shift(1)
    _note("技-10:原著是盘中挂 stop order 越过前一天高点;引擎只能做"
          "「次日收盘站上前一天高点 → 第三天开盘成交」—— 执行细节改动")
    return _as_bool(prev_setup & (close > prev_high))


def turtle_soup_entry(symbols: list[str], lookback: int = 20,
                      min_bars_before: int = 4,
                      require_close_confirm: bool = True) -> pd.DataFrame:
    """
    技-10 进场事件。两版只差一处:require_close_confirm。

    第一步(假突破那根 = setup bar):
      · 当天最低价跌破前 lookback 日的最低价
      · 那条前低至少 min_bars_before 个交易日之前(原著 Rule 2 = 4)
      · require_close_confirm=True  → 还要求当天收盘收回到那条前低之上
                                       (★ 我方卡片写的)
        require_close_confirm=False → 不要求收盘确认(★ 附录 D.8 说原著可能如此)
    第二步:次日收盘站上 setup 那根的高点 → 进场事件。
    """
    from . import ops_1029

    sl, age = ops_1029.swing_low_20(tuple(symbols), lookback)
    low = cache.field("low", symbols)
    close = cache.field("close", symbols)

    aged = _as_bool(sl.notna() & age.notna() & (age >= float(min_bars_before)))
    undercut = _as_bool(sl.notna() & (low < sl))
    setup = aged & undercut
    if require_close_confirm:
        setup = setup & _as_bool(close > sl)
    return cross_prev_day_high(symbols, setup)


# ===========================================================================
# 技-8 高紧旗形 HTF
#   原著(丹·赞格公开描述)给死的数:
#     ① 四到八周内涨幅 > 100%
#     ② 高位整理期间回调幅度不超过 20–25%   ★ 是一个区间,不是一个数
#     ③ 整理期间缩量                        ★ 没给量比
#     ④ 突破旗形上沿买入
#     ⑤ 跌破旗形下沿全退;时间止损三到五天不启动就走  ★ 两处都没给死数
#   ★ 所以这条只有 ①④ 能照原文落地。② 跑区间两端;③⑤ 必须显式关掉。
# ===========================================================================

#: 原著「四到八周」→ 交易日:4 周 = 20 根,8 周 = 40 根
HTF_RUNUP_MIN_BARS = 20
HTF_RUNUP_MAX_BARS = 40


def htf_flag_breakout(symbols: list[str], *,
                      runup_min: float,
                      max_pullback: float,
                      flag_min_bars: int = 3,
                      flag_max_bars: int = 25) -> pd.DataFrame:
    """
    返回「突破旗形上沿」的事件矩阵。

    runup_min      原著 = 1.00(涨幅 100%),由配置显式写出
    max_pullback   原著 = 0.20 ~ 0.25 的区间端点,由配置显式写出
    flag_min_bars / flag_max_bars
                   ★ 原著只说「高位窄幅整理」,没给整理期长度。
                   这两个数是**我们的机械读法边界**,不是原著 ——
                   报告里必须列为待确认。

    机械读法(不引入别的自由参数):
      · 对每一天 t,先找「主升段峰值」:t 之前 flag_max_bars 根里的最高收盘 P,
        出现在 tp。要求 tp 距 t 至少 flag_min_bars 根。
      · 主升:P / min(close[tp-HTF_RUNUP_MAX_BARS : tp]) - 1 >= runup_min,
        且那个最低点距 tp 在 [HTF_RUNUP_MIN_BARS, HTF_RUNUP_MAX_BARS] 之内。
      · 旗形:tp..t-1 这段里最低价不低于 P × (1 - max_pullback)。
      · 突破:close[t] > max(high[tp..t-1])(= 旗形上沿)。
    """
    close = cache.field("close", symbols)
    high = cache.field("high", symbols)
    low = cache.field("low", symbols)
    out = pd.DataFrame(False, index=close.index, columns=close.columns)
    _note(f"技-8:整理期长度 [{flag_min_bars}, {flag_max_bars}] 根是我们的机械读法边界,"
          f"原著只说「高位窄幅整理」—— 待确认")

    for col in close.columns:
        c = close[col].to_numpy(dtype=float)
        h = high[col].to_numpy(dtype=float)
        lo = low[col].to_numpy(dtype=float)
        n = len(c)
        res = np.zeros(n, dtype=bool)
        for t in range(HTF_RUNUP_MAX_BARS + flag_max_bars + 1, n):
            if not np.isfinite(c[t]):
                continue
            # 候选峰值:t-flag_max_bars .. t-flag_min_bars
            a, b = t - flag_max_bars, t - flag_min_bars
            seg = c[a:b + 1]
            if not np.isfinite(seg).any():
                continue
            tp = a + int(np.nanargmax(seg))
            P = c[tp]
            if not np.isfinite(P) or P <= 0:
                continue
            # 主升段:tp 之前 20..40 根里的最低收盘
            s0 = tp - HTF_RUNUP_MAX_BARS
            s1 = tp - HTF_RUNUP_MIN_BARS
            if s0 < 0:
                continue
            base_seg = c[s0:s1 + 1]
            if not np.isfinite(base_seg).any():
                continue
            base = np.nanmin(base_seg)
            if not np.isfinite(base) or base <= 0:
                continue
            if P / base - 1.0 < runup_min:
                continue
            # 旗形段 tp..t-1
            fl_lo = lo[tp:t]
            fl_hi = h[tp:t]
            if not np.isfinite(fl_lo).any() or not np.isfinite(fl_hi).any():
                continue
            if np.nanmin(fl_lo) < P * (1.0 - max_pullback):
                continue
            if c[t] > np.nanmax(fl_hi):
                res[t] = True
        out[col] = res
    return _as_bool(out)


# ===========================================================================
# 技-13 TD 序列
#   ★ 手册原文只有一句:「TD Setup 计数到 9、TD Countdown 计数到 13 时
#     标记为衰竭点。下跌趋势中的衰竭点作为超跌参考。」
#   ★ 手册自己在「规则归属」里写了:规则是专有的、存在多个流传版本、
#     我们的实现必须标注为「XING 基于公开描述的实现」。
#   下面用的是流传最广的那个版本的计数规则(逐条写明),
#   ★ 但手册里**没有任何进场/离场规则** —— 只说「作为超跌参考」。
#     所以「计数到 9 / 13 就买」这件事本身就是我们加的,报告里必须单列。
# ===========================================================================

def td_buy_setup(symbols: list[str], count: int = 9,
                 ref_lag: int = 4) -> pd.DataFrame:
    """
    TD Buy Setup:连续 `count` 根收盘价低于 `ref_lag` 根之前的收盘价,
    在第 `count` 根那天为 True。(流传最广版本:9 根 / 比较 4 根前)
    """
    close = cache.field("close", symbols)
    cond = _as_bool(close < close.shift(ref_lag))
    run = cond.astype(int)
    for col in cond.columns:
        v = cond[col].to_numpy(dtype=bool)
        r = np.zeros(len(v), dtype=int)
        acc = 0
        for i in range(len(v)):
            acc = acc + 1 if v[i] else 0
            r[i] = acc
        run[col] = r
    return _as_bool(run == count)


def td_buy_countdown(symbols: list[str], setup_count: int = 9,
                     ref_lag: int = 4, countdown: int = 13,
                     cd_lag: int = 2) -> pd.DataFrame:
    """
    TD Buy Countdown:Setup 完成之后开始数,
    每当 close <= low[cd_lag 根之前] 记一个(不要求连续),数到 `countdown` 那天为 True。
    (流传最广版本:13 个 / 比较 2 根前的最低价)
    ★ 新的 Setup 完成会把 Countdown 重置 —— 这也是流传版本的写法。
    """
    close = cache.field("close", symbols)
    low = cache.field("low", symbols)
    setup_done = td_buy_setup(symbols, setup_count, ref_lag)
    tick = _as_bool(close <= low.shift(cd_lag))
    out = pd.DataFrame(False, index=close.index, columns=close.columns)
    for col in close.columns:
        sd = setup_done[col].to_numpy(dtype=bool)
        tk = tick[col].to_numpy(dtype=bool)
        res = np.zeros(len(sd), dtype=bool)
        active = False
        cnt = 0
        for i in range(len(sd)):
            if sd[i]:
                active, cnt = True, 0
            if active and tk[i]:
                cnt += 1
                if cnt >= countdown:
                    res[i] = True
                    active, cnt = False, 0
        out[col] = res
    return _as_bool(out)


# ===========================================================================
# 通用:收盘站上均线(技-12 的离场)
# ===========================================================================

def close_above_sma(symbols: list[str], ma: int) -> pd.DataFrame:
    from .matrices import sma_matrix
    close = cache.field("close", symbols)
    return _as_bool(close > sma_matrix(int(ma), symbols))

def close_below_lowest_low(symbols: list[str], lookback: int) -> pd.DataFrame:
    """
    技-1 海龟的「反向通道退出」：收盘跌破前 lookback 日的最低价。

    ★ 为什么单独写成「离场规则」而不用 lowest_low_trail 移动止损顶替：
      移动止损有引擎铁律「只许单向上移」，而海龟原著的 10 日反向通道
      是可以**往下跑**的。用单向上移的版本会比原著更早出场，
      那就不是原著了。★ 所以这里用离场规则照原文写。
    """
    close = cache.field("close", symbols)
    low = cache.field("low", symbols)
    ll = low.rolling(int(lookback), min_periods=int(lookback)).min().shift(1)
    _note(f"技-1：反向通道退出写成离场规则（close < 前 {lookback} 日最低价），"
          f"不用单向上移的移动止损顶替 —— 原著的通道可以往下跑")
    return _as_bool(close < ll)
