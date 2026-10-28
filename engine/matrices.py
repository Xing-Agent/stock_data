"""
第一层:计算层 —— 全部向量化,只用 pandas,不碰任何回测库。

大白话:这一层把「全池所有票、所有交易日」的判断一次性算成几张大表(矩阵),
行是日期,列是代码。第二层的逐日循环只负责查表,不再算指标。
这样慢的地方只慢一次。

吐出来的三张布尔矩阵:
    universe_mask    这只票今天能不能碰(流动性 / 股价 / 基本面闸门 / 均线位置)
    regime_mask      今天整个开不开仓(大盘闸门,★ 一列,全池共用)
    entry_trigger    今天收盘后成不成立一个买点

另外预存好给第二层查的矩阵:
    atr / chandelier_raw / ma / rs_rank(相对强弱排名)/ adv20(20 日平均成交额)

★ 因果性:所有矩阵在 t 行的值,只用到 t 日及以前的数据。
  第二层拿 t 行的信号,在 t+1 日开盘成交 —— 不可能偷看未来。

★ 时钟错位(坑三):基本面闸门按 SEC 受理时间(accepted_at)逐日对齐,
  ★ 不许「月初统一拉一次最新值」—— 那会让 4 月 1 日用上 4 月 20 日才发布的财报。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import numpy as np
import pandas as pd

from . import cache, data

# ---------------------------------------------------------------- 基础指标(矩阵版)


def _wilder(x: pd.DataFrame, period: int) -> pd.DataFrame:
    return x.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def atr_matrix(period: int = 20, symbols: list[str] | None = None) -> pd.DataFrame:
    """Wilder ATR,全池一次算完。出处:Wilder (1978)。"""
    p = cache.load()
    h, l, c = (p["high"], p["low"], p["close"])
    if symbols:
        h, l, c = h[symbols], l[symbols], c[symbols]
    pc = c.shift(1)
    tr = pd.DataFrame(
        np.fmax(np.fmax((h - l).to_numpy(), (h - pc).abs().to_numpy()),
                (l - pc).abs().to_numpy()),
        index=c.index, columns=c.columns)
    return _wilder(tr, period)


def sma_matrix(period: int, symbols: list[str] | None = None) -> pd.DataFrame:
    c = cache.field("close", symbols)
    return c.rolling(period, min_periods=period).mean()


def adv_matrix(period: int = 20, symbols: list[str] | None = None) -> pd.DataFrame:
    """ADV20:近 period 日平均成交额。摩擦成本分档(坑四)就靠它。"""
    dv = cache.field("dollar_volume", symbols)
    return dv.rolling(period, min_periods=max(5, period // 2)).mean()


def median_dollar_volume(period: int = 63, symbols: list[str] | None = None) -> pd.DataFrame:
    dv = cache.field("dollar_volume", symbols)
    return dv.rolling(period, min_periods=period).median()


def chandelier_raw_matrix(lookback: int = 22, multiple: float = 3.0,
                          atr_period: int = 20,
                          symbols: list[str] | None = None) -> pd.DataFrame:
    """
    吊灯止损的「原始值」= 近 lookback 根最高价(含当根) − multiple × ATR。
    出处:Chuck LeBeau 吊灯出场,见 LeBeau & Lucas (1992)。
    ★ 这里只给原始值。两条铁律(不能高于当根收盘 + 只能往上抬)
      由第二层在持仓循环里强制执行 —— 那个 bug 两天内被三个人独立踩到。
    """
    h = cache.field("high", symbols)
    hh = h.rolling(lookback, min_periods=1).max()
    return hh - multiple * atr_matrix(atr_period, symbols)


def rs_rank_matrix(lookback: int = 126, symbols: list[str] | None = None) -> pd.DataFrame:
    """相对强弱排名:每天把全池按 lookback 日涨幅排个百分位(0~1,1 最强)。"""
    c = cache.field("close", symbols)
    mom = c / c.shift(lookback) - 1.0
    return mom.rank(axis=1, pct=True)


def rsi_matrix(period: int = 14, symbols: list[str] | None = None) -> pd.DataFrame:
    """Wilder RSI。出处:Wilder (1978)。"""
    c = cache.field("close", symbols)
    d = c.diff()
    au = _wilder(d.clip(lower=0.0), period)
    ad = _wilder((-d).clip(lower=0.0), period)
    rs = au / ad.replace(0.0, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)


# ---------------------------------------------------------------- ① universe_mask

def _fundamental_mask(metric: str, op: str, value: float,
                      index: pd.DatetimeIndex, symbols: list[str]) -> pd.DataFrame:
    """
    基本面闸门,★ 严格 PIT 且逐日对齐:
    某一天只看那天之前 SEC 已经受理(accepted_at)的最新那一版。
    ★ 看不到数据的那天算「不合格」 —— 不猜、不补、不用近似值顶上。
    """
    out = pd.DataFrame(False, index=index, columns=symbols)
    cal = index.to_numpy()
    for sym in symbols:
        pts = data._metric_series(sym, metric)
        if not pts:
            continue
        ts = np.array([p[0] for p in pts], dtype="datetime64[ns]")
        vs = np.array([p[1] for p in pts], dtype=float)
        pos = np.searchsorted(ts, cal, side="right") - 1
        val = np.where(pos >= 0, vs[np.clip(pos, 0, len(vs) - 1)], np.nan)
        with np.errstate(invalid="ignore"):
            if op == "ge":
                m = val >= value
            elif op == "le":
                m = val <= value
            elif op == "gt":
                m = val > value
            elif op == "lt":
                m = val < value
            else:
                raise ValueError(f"基本面闸门 op 只能是 ge/le/gt/lt,给的是 {op}")
        out[sym] = np.nan_to_num(m, nan=False).astype(bool)
    return out


def hv_matrix(period: int = 20, symbols: list[str] | None = None) -> pd.DataFrame:
    """年化历史波动率(%):近 period 日对数收益标准差 × sqrt(252) × 100。"""
    c = cache.field("close", symbols)
    lr = np.log(c / c.shift(1))
    return lr.rolling(period, min_periods=period).std() * np.sqrt(252) * 100.0


def _universe_rule_mask(rule: dict, syms: list[str], index: pd.DatetimeIndex
                        ) -> pd.DataFrame:
    """把「流派配置」那套 universe 规则翻成布尔矩阵。认不出来的直接报错。"""
    t = rule.get("type")
    p = rule.get("params", {}) or {}
    close = cache.field("close", syms)

    if t == "price_above_ma":
        return _as_bool(close > sma_matrix(int(p["ma"]), syms))

    if t in ("adv_rank_exclude_bottom", "dollar_volume_rank_exclude_bottom"):
        # 剔除当日成交额排名最后 N% 的票(池内横截面排名)
        adv = adv_matrix(int(p.get("adv_period", 20)), syms)
        pct = adv.rank(axis=1, pct=True)
        return _as_bool(pct > float(p.get("exclude_bottom_pct", 20)) / 100.0)

    if t == "return_rank_top":
        # 只留近 lookback 日涨幅排前 N% 的票
        rs = rs_rank_matrix(int(p.get("lookback", 60)), syms)
        return _as_bool(rs >= 1.0 - float(p.get("top_pct", 15)) / 100.0)

    if t == "ma_stack_bullish":
        # 几条均线依次向下排列(50 > 150 > 200),可选再要求价格在最上面
        mas = [int(x) for x in (p.get("mas") or [50, 150, 200])]
        m = [sma_matrix(n, syms) for n in mas]
        ok = _as_bool(m[0].notna())
        for a, b in zip(m[:-1], m[1:]):
            ok &= _as_bool(a > b)
        if p.get("require_price_above_all", True):
            for x in m:
                ok &= _as_bool(close > x)
        return ok

    if t == "hv_below":
        hv = hv_matrix(int(p.get("period", 20)), syms)
        return _as_bool(hv < float(p["max_hv_annualized_pct"]))

    from .config_adapter import BLOCKED_REASONS
    why = BLOCKED_REASONS.get(t, "引擎还没实现这条规则")
    raise NotImplementedError(
        f"universe 规则 {t} 还没法跑 —— {why}\n"
        f"★ 没有悄悄忽略它:悄悄忽略会让配置里写了的闸门没被执行,"
        f"跑出来的成绩凭空变好而且没人知道。")


def universe_mask(spec: dict, symbols: list[str] | None = None) -> pd.DataFrame:
    """① 选股范围:能不能碰。返回 [日期 × 票] 布尔矩阵。"""
    spec = spec or {}
    meta = data.load_manifest()
    syms = symbols or cache.symbols()
    # 静态筛:市值分组 / 行业
    if spec.get("size_groups"):
        want = set(spec["size_groups"])
        syms = [s for s in syms if meta[s].size_group in want]
    if spec.get("sectors"):
        want = set(spec["sectors"])
        syms = [s for s in syms if meta[s].sector in want]

    close = cache.field("close", syms)
    mask = close.notna() & (close > 0)

    if spec.get("min_price") is not None:
        mask &= close >= float(spec["min_price"])
    if spec.get("min_dollar_volume") is not None:
        mdv = median_dollar_volume(int(spec.get("dollar_volume_period", 63)), syms)
        mask &= mdv.fillna(-1.0) >= float(spec["min_dollar_volume"])
    if spec.get("above_ma"):
        n = int(spec["above_ma"])
        mask &= close > sma_matrix(n, syms)
    if spec.get("min_rs_rank") is not None:
        rs = rs_rank_matrix(int(spec.get("rs_lookback", 126)), syms)
        mask &= rs.fillna(-1.0) >= float(spec["min_rs_rank"])
    for g in (spec.get("fundamental_gates") or []):
        mask &= _fundamental_mask(g["metric"], g.get("op", "ge"), float(g["value"]),
                                 close.index, syms)
    # 「流派配置」那套 rules 列表形式:全部规则都要成立
    for rule in (spec.get("rules") or []):
        mask &= _universe_rule_mask(rule, syms, close.index)
    return mask.fillna(False)


# ---------------------------------------------------------------- ② regime_mask

def regime_mask(spec: dict, index: pd.DatetimeIndex) -> pd.Series:
    """
    ② 环境过滤:今天整个开不开仓。返回一条布尔序列(全池共用)。
    所有规则都成立才算「可以做」。
    ★ 已经往后挪了一天:t 行的值 = 用 t-1 日收盘算出来的闸门,
      所以第二层在 t 日用它开仓不会偷看当天。
    """
    spec = spec or {}
    ok = pd.Series(True, index=index)
    for rule in (spec.get("rules") or []):
        t = rule.get("type", "none")
        if t == "none":
            continue
        if t == "index_above_ma":
            sym, n = rule.get("symbol", "SPY"), int(rule.get("ma", 200))
            b = data.load_benchmark(sym)["close"].reindex(index).ffill()
            ok &= (b > b.rolling(n, min_periods=n).mean()).fillna(False)
        elif t == "breadth_above":
            s = data.load_breadth()[rule["field"]].reindex(index).ffill()
            ok &= (s > float(rule["value"])).fillna(False)
        elif t == "vix_below":
            s = data.load_benchmark("VIX")["close"].reindex(index).ffill()
            ok &= (s < float(rule["value"])).fillna(False)
        elif t == "index_above_ma_scaled":
            # 大盘在 (均线 × factor) 上方 —— factor<1 表示容忍小幅跌破
            p = rule.get("params", rule)
            sym, n = p.get("symbol", "SPY"), int(p.get("ma", 200))
            f = float(p.get("factor", 1.0))
            b = data.load_benchmark(sym)["close"].reindex(index).ffill()
            ok &= (b > b.rolling(n, min_periods=n).mean() * f).fillna(False)
        elif t == "index_ma_slope":
            # 大盘均线自己在往上走(近 lookback 日的斜率 > min_slope)
            p = rule.get("params", rule)
            sym, n = p.get("symbol", "SPY"), int(p.get("ma", 200))
            lb = int(p.get("lookback", 20))
            ms = float(p.get("min_slope", 0.0))
            b = data.load_benchmark(sym)["close"].reindex(index).ffill()
            ma = b.rolling(n, min_periods=n).mean()
            ok &= ((ma - ma.shift(lb)) / ma.shift(lb) > ms).fillna(False)
        elif t in ("no_distribution_day", "no_large_down_day"):
            # 近 window 天里没有单日大跌(派发日 / 大阴线)
            p = rule.get("params", rule)
            sym = p.get("symbol", "SPY")
            w = int(p.get("window", 5))
            thr = float(p.get("single_day_drop_pct", 1.5)) / 100.0
            b = data.load_benchmark(sym)["close"].reindex(index).ffill()
            big_down = b.pct_change() <= -thr
            ok &= ~_as_bool(big_down.rolling(w, min_periods=1).max().astype(bool))
        else:
            raise ValueError(f"不认识的环境过滤规则 type={t}")
    return ok.shift(1, fill_value=False).fillna(False).astype(bool)


# ---------------------------------------------------------------- ③ entry_trigger

def _as_bool(df: pd.DataFrame) -> pd.DataFrame:
    """
    ★ 坑:pandas 3.0 里 bool 表 .shift() 会变成 object dtype,
      再对它取 `~` 结果是错的(object 的按位取反不是逻辑取反)。
      所有移位后的布尔表都必须过这一道,强制回 bool。
    """
    return df.fillna(False).astype(bool)


def _event_only(raw: pd.DataFrame) -> pd.DataFrame:
    """
    ★ 九关第三关:进场信号必须是「事件」,不能是粘住好多天的「状态」。
    做法:只在由不成立变成成立的那一天为 True。
    """
    r = _as_bool(raw)
    prev = _as_bool(r.shift(1, fill_value=False))
    return r & ~prev


def _entry_rule_raw(rule: dict, symbols: list[str]) -> pd.DataFrame:
    """
    「流派配置」那套 entry 规则,返回「状态」矩阵(还没转成事件)。
    多条规则是「都要成立」,最后由 entry_trigger 统一转成事件。
    """
    t = rule.get("type")
    p = rule.get("params", {}) or {}
    close = cache.field("close", symbols)

    if t in ("donchian_close_breakout", "donchian_breakout"):
        n = int(p.get("lookback", 20))
        hi = cache.field("high", symbols).rolling(n, min_periods=n).max().shift(1)
        return _as_bool(close > hi)

    if t == "atr_squeeze":
        # 突破前刚缩过波动:快 ATR / 慢 ATR 均值 < max_ratio
        fast = int(p.get("atr_fast", 10))
        slow_ma = int(p.get("atr_slow_ma", 50))
        ratio_max = float(p.get("max_ratio", 0.85))
        off = int(p.get("offset_days", 1))
        af = atr_matrix(fast, symbols)
        ratio = af / af.rolling(slow_ma, min_periods=slow_ma).mean()
        return _as_bool(ratio.shift(off) < ratio_max)

    if t == "volume_dryup":
        # 缩量:快均量 / 慢均量 < max_ratio
        v = cache.field("volume", symbols)
        f = int(p.get("fast_period", 5))
        sl = int(p.get("slow_period", 50))
        r = (v.rolling(f, min_periods=f).mean()
             / v.rolling(sl, min_periods=sl).mean())
        return _as_bool(r < float(p.get("max_ratio", 0.6)))

    from .config_adapter import BLOCKED_REASONS
    why = BLOCKED_REASONS.get(t, "引擎还没实现这条规则")
    raise NotImplementedError(
        f"entry 规则 {t} 还没法跑 —— {why}\n"
        f"★ 没有悄悄忽略它。")


def entry_trigger(spec: dict, symbols: list[str]) -> pd.DataFrame:
    """③ 进场扳机。返回 [日期 × 票] 布尔矩阵,True = 当天收盘后成立,次日开盘买。"""
    spec = spec or {"type": "never"}
    if spec.get("rules"):
        # 多条规则都要成立,然后整体转成「事件」(只在转折那天触发)
        close = cache.field("close", symbols)
        raw = pd.DataFrame(True, index=close.index, columns=close.columns)
        for rule in spec["rules"]:
            raw &= _entry_rule_raw(rule, symbols)
        return _event_only(raw)
    t = spec.get("type", "never")
    p = spec.get("params", {}) or {}
    close = cache.field("close", symbols)

    if t == "donchian_breakout":
        n = int(p.get("lookback", 20))
        hi = cache.field("high", symbols).rolling(n, min_periods=n).max().shift(1)
        return _event_only(close > hi)

    if t == "ma_cross":
        fast, slow = int(p.get("fast", 50)), int(p.get("slow", 200))
        return _event_only(sma_matrix(fast, symbols) > sma_matrix(slow, symbols))

    if t == "rsi_oversold":
        n, thr = int(p.get("period", 14)), float(p.get("threshold", 30.0))
        r = rsi_matrix(n, symbols)
        return _as_bool(r > thr) & _as_bool(r.shift(1) <= thr)

    if t == "roc_momentum":
        n, q = int(p.get("lookback", 126)), float(p.get("self_quantile", 0.8))
        rs = rs_rank_matrix(n, symbols)
        return _event_only(rs > q)

    if t == "pullback_to_ma":
        n = int(p.get("ma", 50))
        ma = sma_matrix(n, symbols)
        return _event_only(_as_bool(close <= ma) & _as_bool(close.shift(1) > ma.shift(1)))

    if t == "always":
        return pd.DataFrame(True, index=close.index, columns=close.columns)
    if t == "never":
        return pd.DataFrame(False, index=close.index, columns=close.columns)

    if t == "random":
        rate = float(p.get("rate", 0.01))
        rng = np.random.default_rng(int(p.get("seed", 20181001)))
        return pd.DataFrame(rng.random(close.shape) < rate,
                            index=close.index, columns=close.columns)

    raise ValueError(f"不认识的进场扳机 type={t}。支持:donchian_breakout / ma_cross / "
                     f"rsi_oversold / roc_momentum / pullback_to_ma / always / "
                     f"random / never")


# ---------------------------------------------------------------- 打包

@dataclass
class Matrices:
    """第二层要查的全部表,一次算好。"""
    symbols: list[str]
    index: pd.DatetimeIndex
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    universe: np.ndarray
    regime: np.ndarray            # 一维,长度 = 交易日数
    entry: np.ndarray
    atr: np.ndarray
    chandelier: np.ndarray
    adv20: np.ndarray
    rs_rank: np.ndarray
    last_bar: np.ndarray          # 每只票最后一根有价格的 bar 的行号(含 0 价 bar)
    zero_bar: np.ndarray          # 破产类 0 价 bar 的行号;没有则 -1
    col: dict[str, int] = None    # type: ignore

    def __post_init__(self):
        self.col = {s: i for i, s in enumerate(self.symbols)}


def build(cfg: dict, symbols: list[str] | None = None) -> Matrices:
    """按一份七步配置,把第一层全部算好。"""
    uni_spec = cfg.get("universe") or {}
    uni = universe_mask(uni_spec, symbols)
    syms = list(uni.columns)
    if not syms:
        raise ValueError("选股范围把所有票都筛掉了,检查 ① universe 那一块")
    idx = uni.index

    st = (cfg.get("trailing_stop") or {}).get("params", {}) or {}
    isp = (cfg.get("initial_stop") or {}).get("params", {}) or {}
    atr_p = int(isp.get("atr_period", st.get("atr_period", 20)))

    close = cache.field("close", syms)
    meta = cache.panel_meta()
    last_bar = np.array([int(np.flatnonzero(close[s].notna().to_numpy())[-1])
                         if close[s].notna().any() else -1 for s in syms])
    zb = []
    for s in syms:
        z = meta.at[s, "zero_bar"] if s in meta.index else None
        if z is None or pd.isna(z):
            zb.append(-1)
        else:
            zb.append(int(idx.get_loc(pd.Timestamp(z))))

    return Matrices(
        symbols=syms,
        index=idx,
        open=cache.field("open", syms).to_numpy(dtype=float),
        high=cache.field("high", syms).to_numpy(dtype=float),
        low=cache.field("low", syms).to_numpy(dtype=float),
        close=close.to_numpy(dtype=float),
        universe=uni.to_numpy(dtype=bool),
        regime=regime_mask(cfg.get("regime") or {}, idx).to_numpy(dtype=bool),
        entry=entry_trigger(cfg.get("entry") or {}, syms).to_numpy(dtype=bool),
        atr=atr_matrix(atr_p, syms).to_numpy(dtype=float),
        chandelier=chandelier_raw_matrix(
            int(st.get("lookback", 22)), float(st.get("multiple", 3.0)),
            atr_p, syms).to_numpy(dtype=float),
        adv20=adv_matrix(20, syms).to_numpy(dtype=float),
        rs_rank=rs_rank_matrix(
            int(uni_spec.get("rs_lookback", 126)), syms).to_numpy(dtype=float),
        last_bar=last_bar,
        zero_bar=np.array(zb),
    )


__all__ = ["Matrices", "build", "universe_mask", "regime_mask", "entry_trigger",
           "atr_matrix", "sma_matrix", "adv_matrix", "chandelier_raw_matrix",
           "rs_rank_matrix", "rsi_matrix", "median_dollar_volume"]
