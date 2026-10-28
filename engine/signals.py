"""
指标与进场扳机 —— 链的第③步用这里的东西,九关也用这里的东西。

大白话:这里只放「怎么算指标」和「哪天算一个信号」。
它不管买多少、不管什么时候卖 —— 那些在 chain.py 里。

★ 所有指标都是「只用今天及以前的数据」算出来的(因果性)。
  实现办法:算完直接 shift(0) 用在当天收盘后,下单在次日开盘 ——
  这样绝不可能偷看未来。chain.py 负责次日开盘执行。

★ 参数一律写死在配置里,并标明出处;不许网格搜索(硬纪律第 6 条)。
"""

from __future__ import annotations

from typing import Callable

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- 指标


def true_range(df: pd.DataFrame) -> pd.Series:
    prev_close = df["close"].shift(1)
    a = df["high"] - df["low"]
    b = (df["high"] - prev_close).abs()
    c = (df["low"] - prev_close).abs()
    return pd.concat([a, b, c], axis=1).max(axis=1)


def atr(df: pd.DataFrame, period: int = 20) -> pd.Series:
    """Wilder ATR。出处:Wilder (1978) New Concepts in Technical Trading Systems。"""
    tr = true_range(df)
    return tr.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def sma(s: pd.Series, period: int) -> pd.Series:
    return s.rolling(period, min_periods=period).mean()


def donchian_high(df: pd.DataFrame, period: int) -> pd.Series:
    """前 period 根的最高价(★ 不含当根,避免自我触发)。"""
    return df["high"].rolling(period, min_periods=period).max().shift(1)


def donchian_low(df: pd.DataFrame, period: int) -> pd.Series:
    return df["low"].rolling(period, min_periods=period).min().shift(1)


def rsi(s: pd.Series, period: int = 14) -> pd.Series:
    """Wilder RSI。出处:Wilder (1978)。"""
    d = s.diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    au = up.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    ad = dn.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()
    rs = au / ad.replace(0.0, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)


def roc(s: pd.Series, period: int) -> pd.Series:
    return s / s.shift(period) - 1.0


def rolling_median_dollar_volume(df: pd.DataFrame, period: int = 63) -> pd.Series:
    return df["dollar_volume"].rolling(period, min_periods=period).median()


def chandelier_raw(df: pd.DataFrame, period: int, multiple: float,
                   atr_period: int) -> pd.Series:
    """
    吊灯止损的「原始值」= 近 period 根最高价(含当根) − multiple × ATR。
    出处:Chuck LeBeau,见 LeBeau & Lucas (1992) Computer Analysis of
    the Futures Markets;Elder (2002) 亦述。
    ★ 注意:这里只给原始值。 「不能高于当根收盘 + 只能往上抬」这两条
      在 chain.py 的持仓循环里强制执行 —— 那个 bug 两天内被三个人独立踩到。
    """
    hh = df["high"].rolling(period, min_periods=1).max()
    return hh - multiple * atr(df, atr_period)


# ---------------------------------------------------------------- 进场扳机

SignalFn = Callable[[pd.DataFrame], pd.Series]


def _bool(s: pd.Series) -> pd.Series:
    return s.fillna(False).astype(bool)


def make_entry(spec: dict) -> SignalFn:
    """
    按配置造一个进场扳机。返回的函数吃一只票的日线,吐一串 True/False。
    True 的含义:★ 当天收盘后成立,次日开盘买入。

    支持的 type:
      donchian_breakout  —— 收盘突破前 N 日最高(Donchian / 海龟,参数 20 或 55)
      ma_cross           —— 快均线上穿慢均线
      rsi_oversold       —— RSI 跌破阈值后回升(Wilder 1978)
      roc_momentum       —— N 日涨幅排在自身历史高位(动量)
      always             —— 每天都成立(用来做「买入持有」和分步归因的中间行)
      random             —— 随机进场(★ 基准一专用,频率对齐真信号)
      never              —— 永不进场
    """
    t = spec.get("type", "never")
    p = spec.get("params", {}) or {}

    if t == "donchian_breakout":
        n = int(p.get("lookback", 20))

        def f(df: pd.DataFrame) -> pd.Series:
            hi = donchian_high(df, n)
            raw = df["close"] > hi
            # ★ 必须是「事件」:只在由不成立变成成立的那一天为 True(九关第三关)
            return _bool(raw & ~raw.shift(1).fillna(False))
        return f

    if t == "ma_cross":
        fast, slow = int(p.get("fast", 50)), int(p.get("slow", 200))

        def f(df: pd.DataFrame) -> pd.Series:
            a, b = sma(df["close"], fast), sma(df["close"], slow)
            raw = a > b
            return _bool(raw & ~raw.shift(1).fillna(False))
        return f

    if t == "rsi_oversold":
        n, thr = int(p.get("period", 14)), float(p.get("threshold", 30.0))

        def f(df: pd.DataFrame) -> pd.Series:
            r = rsi(df["close"], n)
            return _bool((r > thr) & (r.shift(1) <= thr))
        return f

    if t == "roc_momentum":
        n = int(p.get("lookback", 126))
        q = float(p.get("self_quantile", 0.8))
        win = int(p.get("rank_window", 252))

        def f(df: pd.DataFrame) -> pd.Series:
            m = roc(df["close"], n)
            thr = m.rolling(win, min_periods=win).quantile(q)
            raw = m > thr
            return _bool(raw & ~raw.shift(1).fillna(False))
        return f

    if t == "always":
        return lambda df: pd.Series(True, index=df.index)

    if t == "never":
        return lambda df: pd.Series(False, index=df.index)

    if t == "random":
        rate = float(p.get("rate", 0.01))
        seed = int(p.get("seed", 20181001))

        def f(df: pd.DataFrame) -> pd.Series:
            rng = np.random.default_rng(seed + (abs(hash(str(df.index[0]))) % 9973))
            return pd.Series(rng.random(len(df)) < rate, index=df.index)
        return f

    raise ValueError(f"不认识的进场扳机 type={t}。"
                     f"支持:donchian_breakout / ma_cross / rsi_oversold / "
                     f"roc_momentum / always / random / never")


# ---------------------------------------------------------------- 给判据用的前瞻收益

def forward_return(df: pd.DataFrame, entry_idx: int, horizon: int) -> float:
    """
    一次进场点的结果:次日开盘买,持有 horizon 个交易日,按收盘卖。
    ★ 次日开盘买 —— 信号在当天收盘后产生,不许用当天收盘价成交。
    拿不到完整窗口就返回 nan(不补、不猜)。
    """
    i = entry_idx + 1
    j = i + horizon
    if i >= len(df) or j > len(df):
        return float("nan")
    p_in = df["open"].iloc[i]
    p_out = df["close"].iloc[j - 1]
    if not np.isfinite(p_in) or not np.isfinite(p_out) or p_in <= 0:
        return float("nan")
    return float(p_out / p_in - 1.0)


__all__ = ["true_range", "atr", "sma", "donchian_high", "donchian_low", "rsi", "roc",
           "rolling_median_dollar_volume", "chandelier_raw", "make_entry",
           "forward_return"]
