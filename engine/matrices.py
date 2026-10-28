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


def ema_matrix(period: int, symbols: list[str] | None = None) -> pd.DataFrame:
    """指数均线。VCP 的 ⑤ EMA10 跟踪与 ⑥ 收盘跌破 EMA10 离场都用它。"""
    c = cache.field("close", symbols)
    return c.ewm(span=period, adjust=False, min_periods=period).mean()


def ret_std_matrix(period: int, symbols: list[str] | None = None) -> pd.DataFrame:
    """近 period 日「日收益率」的标准差。流派二的 σ5 / σ20 点火门禁用它。"""
    c = cache.field("close", symbols)
    return c.pct_change().rolling(period, min_periods=period).std()


def mansfield_rs_matrix(against: str = "SPY", lookback: int = 250,
                        symbols: list[str] | None = None) -> pd.DataFrame:
    """
    Mansfield 相对强弱(RSM):
        RS_t  = Close / 指数Close
        RSM_t = (RS_t / SMA_lookback(RS_t) − 1) × 100
    RSM > 0 = 这只票近来跑得比指数自己的长期均值强。
    出处:Stan Weinstein《Secrets for Profiting in Bull and Bear Markets》(1988)
          里的 Mansfield 相对强弱;Minervini 的趋势模板沿用。
    """
    c = cache.field("close", symbols)
    b = data.load_benchmark(against)["close"].reindex(c.index).ffill()
    rs = c.div(b, axis=0)
    return (rs / rs.rolling(lookback, min_periods=lookback).mean() - 1.0) * 100.0


# ---------------------------------------------------------------- VCP 几何收缩
# ★★ 流派二 ③ 第①关:跨 15~65 天的「选拔门禁」状态机。
#   专家第二轮给齐了全部死数(分型半宽 2 / D1≤30% / 递减 0.65 / 2~4 次 /
#   15~65 天 / 振幅分母用该段高点 / 禁用 ATR 比值),这里一个数都没动。
#
# ★ 但有一处专家没说、而代码必须有答案的:「形态成立之后,这个门禁开多久」。
#   引擎的机械读法(★ 已登记为待专家确认的实现口径):
#     门禁从「最后一次收缩的那个分型低点被确认」那天开始开着,
#     到「再出现一个被确认的分型低点」(= 形成了新的一段收缩,旧形态被取代)
#     或「基底总长超过 65 个交易日」为止,取两者更早的那个。
#
# ★ 因果性:5 根分型(High_t = max(High[t−2..t+2]))本身用到了 t+1 / t+2,
#   所以一个分型在 t 成立、但只有到 t+2 才「可知」。下面一律按 t+2 才允许使用,
#   绝不在 t 当天就用它 —— 否则是偷看未来 2 天。

_VCP_CACHE: dict = {}

# ★ 凡是「被显式关掉的规则」都往这里记一条,报告里必须原样打出来 ——
#   关掉可以(有时数据就是不支持),悄悄关掉不行。
_DISABLED_LOG: list[str] = []


def disabled_log() -> list[str]:
    return list(_DISABLED_LOG)


def _alternating_pivots(is_h: np.ndarray, is_l: np.ndarray,
                        high: np.ndarray, low: np.ndarray) -> list[tuple[int, str, float]]:
    """把分型高/低点整理成严格交替的 H,L,H,L… 序列(同类连续时保留更极端的那个)。"""
    raw: list[tuple[int, str, float]] = []
    for t in np.flatnonzero(is_h | is_l):
        if is_h[t]:
            raw.append((int(t), "H", float(high[t])))
        if is_l[t]:
            raw.append((int(t), "L", float(low[t])))
    out: list[tuple[int, str, float]] = []
    for p in raw:
        if out and out[-1][1] == p[1]:
            # 同类连续:高点留更高的,低点留更低的
            keep = p if ((p[1] == "H" and p[2] > out[-1][2]) or
                         (p[1] == "L" and p[2] < out[-1][2])) else out[-1]
            out[-1] = keep
        else:
            out.append(p)
    return out


def _vcp_one_symbol(high: np.ndarray, low: np.ndarray, n: int,
                    is_h: np.ndarray, is_l: np.ndarray, p: dict
                    ) -> tuple[np.ndarray, np.ndarray]:
    """单只票:返回 (门禁是否开着的布尔数组, 最后一段收缩幅度 D_last 数组)。"""
    hw = int(p["fractal_half_width"])
    d1_max = float(p["first_contraction_max_depth"])
    decay = float(p["decay_coefficient"])
    k_min, k_max = int(p["min_contractions"]), int(p["max_contractions"])
    t_min, t_max = int(p["base_min_days"]), int(p["base_max_days"])

    piv = _alternating_pivots(is_h, is_l, high, low)
    gate = np.zeros(n, dtype=bool)
    d_last = np.full(n, np.nan, dtype=float)

    # 收缩段 = 一个分型高点 → 紧跟其后的那个分型低点
    contr: list[tuple[int, int, int, float]] = []   # (序列位置, H行号, L行号, 深度)
    for i in range(len(piv) - 1):
        if piv[i][1] == "H" and piv[i + 1][1] == "L":
            h_px, l_px = piv[i][2], piv[i + 1][2]
            if h_px > 0 and l_px < h_px:
                # ★ 振幅公式是死数:(High_k − Low_k) / High_k,分母统一用该段高点
                contr.append((i, piv[i][0], piv[i + 1][0], (h_px - l_px) / h_px))

    # 每一段收缩低点被确认的那天(= 低点行号 + hw),以及下一个被确认的低点
    confirm = [c[2] + hw for c in contr]

    for e in range(len(contr)):
        best = None
        for m in range(k_max, k_min - 1, -1):      # 先试长链(4T),再退到 2T
            s = e - m + 1
            if s < 0:
                continue
            seq = contr[s:e + 1]
            # 必须是序列里连续的几段收缩(H L H L …),中间不能断
            if any(seq[k][0] != seq[k - 1][0] + 2 for k in range(1, len(seq))):
                continue
            if seq[0][3] > d1_max:                 # D_1 ≤ 30.0%
                continue
            if any(seq[k][3] > decay * seq[k - 1][3] for k in range(1, len(seq))):
                continue                            # D_k ≤ 0.65 × D_{k−1}
            best = seq
            break
        if best is None:
            continue
        base_start = best[0][1]                     # 基底起点 = 第一段的分型高点
        lo_day = max(confirm[e], base_start + t_min)
        hi_day = base_start + t_max                 # 基底总长 ≤ 65 个交易日
        nxt = confirm[e + 1] if e + 1 < len(confirm) else n
        hi_day = min(hi_day, nxt - 1, n - 1)
        if lo_day > hi_day:
            continue
        gate[lo_day:hi_day + 1] = True
        d_last[lo_day:hi_day + 1] = best[-1][3]
    return gate, d_last


def vcp_matrices(params: dict, symbols: list[str]) -> tuple[pd.DataFrame, pd.DataFrame]:
    """全池跑 VCP 选拔门禁。返回 (门禁布尔矩阵, D_last 矩阵)。结果带缓存。"""
    p = dict(params or {})
    if p.get("forbid_atr_ratio") and p.get("range_metric", "").startswith("ATR"):
        raise ValueError("配置写了 forbid_atr_ratio 却又用 ATR 比值当振幅 —— 自相矛盾")
    key = (tuple(symbols), tuple(sorted((k, str(v)) for k, v in p.items())))
    if key in _VCP_CACHE:
        return _VCP_CACHE[key]

    hw = int(p.get("fractal_half_width", 2))
    p.setdefault("fractal_half_width", hw)
    h = cache.field("high", symbols)
    l = cache.field("low", symbols)
    w = 2 * hw + 1
    # 5 根居中窗口的最高/最低 —— 分型定义本身
    is_h = (h == h.rolling(w, center=True, min_periods=w).max()) & h.notna()
    is_l = (l == l.rolling(w, center=True, min_periods=w).min()) & l.notna()

    ha, la = h.to_numpy(float), l.to_numpy(float)
    hb, lb = is_h.to_numpy(bool), is_l.to_numpy(bool)
    n = len(h)
    g = np.zeros((n, len(symbols)), dtype=bool)
    d = np.full((n, len(symbols)), np.nan, dtype=float)
    for j in range(len(symbols)):
        g[:, j], d[:, j] = _vcp_one_symbol(ha[:, j], la[:, j], n,
                                           hb[:, j], lb[:, j], p)
    out = (pd.DataFrame(g, index=h.index, columns=h.columns),
           pd.DataFrame(d, index=h.index, columns=h.columns))
    _VCP_CACHE[key] = out
    return out


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

    if t == "return_rank_percentile":
        # 近 lookback 日涨幅的池内横截面百分位 ≥ min_percentile
        rs = rs_rank_matrix(int(p.get("lookback", 60)), syms)
        return _as_bool(rs >= float(p.get("min_percentile", 85.0)) / 100.0)

    if t == "mansfield_rs_positive":
        against = str(p.get("against", "SPY")).upper()
        if against == "SECTOR":
            # ★ 不许悄悄顶替:行业归属只有「当前快照」、非 PIT,
            #   用今天的行业标签跑 2016 年整段都在用未来信息(审计 §3-C)。
            raise NotImplementedError(
                "mansfield_rs_positive(against: SECTOR)还不能跑 —— "
                "仓库只有 sector_classification_current_non_pit.csv"
                "(元数据自己写明 non_pit_current_classification),"
                "用它跑回测等于整段用未来信息;且 XLC 只有 2018-06 起、"
                "XLRE 只有 2015-10 起,2016–2018 这两个行业根本算不出。"
                "\n★ 要跑必须显式把这一条 enabled: false 关掉,并在报告里写明"
                "「这一版关掉了行业 RS」 —— 不许悄悄忽略。见审计报告 §3-C。")
        rsm = mansfield_rs_matrix(against, int(p.get("lookback", 250)), syms)
        return _as_bool(rsm > 0.0)

    if t == "momentum_dual_gate":
        # 若干子条件按 logic 组合(专家第二轮明确为 AND)
        logic = str(rule.get("logic", "AND")).upper()
        comps = [c for c in (rule.get("components") or [])
                 if c.get("enabled", True) is not False]
        skipped = [c.get("name") or c.get("type")
                   for c in (rule.get("components") or [])
                   if c.get("enabled", True) is False]
        if skipped:
            _DISABLED_LOG.append(f"universe.momentum_dual_gate 子条件被显式关掉:{skipped}")
        if not comps:
            raise ValueError("momentum_dual_gate 的子条件全被关掉了 —— 这一关等于没有")
        out = None
        for c in comps:
            mm = _universe_rule_mask(c, syms, index)
            out = mm if out is None else (out & mm if logic == "AND" else out | mm)
        return out

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


# ---------------------------------------------------------------- 广度(两个口径)
# ★★ 1028 闸门新方案第三条改动:广度要看「这条链自己的选股范围」,不看全市场。
#   大白话:我们买的是哪一撮票,就该看那一撮票自己的健康度。
#   外部专家原话:「严禁看着航母的灯塔,开着驱逐舰去触礁。」
#
# ★ 工程上的坑(必须处理,不许给一个不可信的数):
#   有些链某天范围很窄(比如只剩 12 只)。12 只算出来的广度噪音极大 ——
#   一只票跳 8 个百分点。所以范围里不足 min_names 只时,★ 这道标尺直接不生效
#   (按正常仓位 / 正常开闸处理),而不是给一个不可信的广度数。
#   失效的天数会统计出来,报告里必须打出来。

BREADTH_MIN_NAMES = 30     # ★ 我们定的(敏感度展示):少于这个只数,广度标尺不生效


def chain_breadth(uni: pd.DataFrame, ma: int = 50) -> tuple[pd.Series, pd.Series]:
    """
    ★ 本链自己范围的广度:今天这个 universe_mask 里,
      有多少比例的票站在自己 ma 日线上方。

    返回 (广度百分比 0~100, 当日可算的只数)。
    ★ 分母 = 当天在 mask 里、且均线算得出来的票数(不满 ma 根的票不进分母)。
    ★ 因果性:这里给的是 t 日收盘算出来的值,调用方必须自己 shift(1)。
    """
    syms = list(uni.columns)
    close = cache.field("close", syms)
    ma_df = sma_matrix(ma, syms)
    usable = _as_bool(uni) & close.notna() & ma_df.notna()
    above = usable & _as_bool(close > ma_df)
    n = usable.sum(axis=1)
    k = above.sum(axis=1)
    pct = (k / n.where(n > 0)) * 100.0
    return pct, n


def market_breadth(field_name: str, index: pd.DatetimeIndex
                   ) -> tuple[pd.Series, pd.Series]:
    """全市场广度(breadth_top500.csv,每天最活跃 500 只,含退市股)。"""
    b = data.load_breadth()
    pct = b[field_name].reindex(index).ffill()
    n = b.get("universe_n", pd.Series(500, index=b.index)).reindex(index).ffill()
    return pct, n


def breadth_size_multiplier(pct: pd.Series, n: pd.Series,
                            threshold: float, low_mult: float,
                            min_names: int = BREADTH_MIN_NAMES
                            ) -> tuple[pd.Series, dict]:
    """
    ★★ 改动二:广度降级成「风险预算标尺」—— 只管仓位,不管开关。
      广度 ≥ threshold → 单笔风险 ×1.0(正常)
      广度 <  threshold → 单笔风险 ×low_mult,★ 但照常允许开仓

    ★ low_mult 这个数外部专家没给出处 —— 所以调用方必须同时报
      「不减仓(1.0)」和「减半(0.5)」两版,不许只报其中一版。

    ★ 范围不足 min_names 只的那些天:标尺不生效(×1.0),并计入失效天数。
    ★ 已 shift(1):t 行的乘数 = 用 t−1 日收盘算出来的广度,不偷看当天。
    """
    ok = (n >= int(min_names)) & pct.notna()
    mult = pd.Series(1.0, index=pct.index, dtype=float)
    mult[ok & (pct < float(threshold))] = float(low_mult)
    mult = mult.shift(1).fillna(1.0)
    diag = {
        "标尺口径": f"广度 < {threshold:.0f}% → 单笔风险 ×{low_mult}",
        "最少只数要求": int(min_names),
        "总交易日": int(len(pct)),
        "★标尺失效天数(范围不足只数)": int((~ok).sum()),
        "★标尺失效占比": float((~ok).mean()),
        "减半的天数": int((mult == low_mult).sum()) if low_mult != 1.0 else 0,
        "当日只数_中位数": float(n.median()),
        "当日只数_最小": float(n.min()) if len(n) else float("nan"),
    }
    return mult, diag


# ---------------------------------------------------------------- ② regime_mask

def regime_mask(spec: dict, index: pd.DatetimeIndex,
                chain_breadth_pct: pd.Series | None = None,
                chain_breadth_n: pd.Series | None = None) -> pd.Series:
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
        elif t == "breadth_above_chain":
            # ★★ 改动三 + 改动一的对照(G4):本链自己范围的广度当「开关」。
            #   ★ 范围不足 min_names 只的那天,这道闸门不生效(当天按开闸处理)——
            #     而不是用一个 12 只算出来的、噪音极大的广度数去关掉整条链。
            if chain_breadth_pct is None:
                raise ValueError(
                    "breadth_above_chain 需要本链自己的 universe_mask 才能算广度 —— "
                    "必须由 matrices.build() 传进来,不许退回全市场广度顶替。")
            p = rule.get("params", rule)
            thr = float(p.get("value", p.get("threshold", 50.0)))
            mn = int(p.get("min_names", BREADTH_MIN_NAMES))
            n = chain_breadth_n if chain_breadth_n is not None \
                else pd.Series(0, index=index)
            usable = (n >= mn) & chain_breadth_pct.notna()
            # 不可用的那天 → True(闸门不生效),可用的那天按阈值判
            ok &= (~usable | (chain_breadth_pct > thr)).fillna(True)
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
        # 缩量:SMA_fast(Vol)(t−off) ≤ max_ratio × SMA_slow(Vol)(t−off)
        v = cache.field("volume", symbols)
        f = int(p.get("fast_period", 5))
        sl = int(p.get("slow_period", 50))
        off = int(p.get("offset_days", 0))
        r = (v.rolling(f, min_periods=f).mean()
             / v.rolling(sl, min_periods=sl).mean())
        # ★ 原文写的是 ≤(不是 <),且分子分母都取 t−1 —— 照原文
        return _as_bool(r.shift(off) <= float(p.get("max_ratio", 0.6)))

    if t == "vcp_volume_tripod":
        # ======================================================================
        # ★★ VCP 成交量三条件(专家 2026-10-28 修正版)
        #
        # 大白话:上一版把「突破前要缩量」和「突破当天要放量」掐在同一个数上,
        #   要求成交量一天之内从「不到均量 6 成」跳到「均量以上」——
        #   这是个自毁的写法,八年只剩 1 笔。专家已承认。
        #   修正后分成三件事:① 前面出现过一天地量(筹码沉淀日)
        #                   ② 前 5 日均量整体收敛(是收敛,不是冰冻)
        #                   ③ 突破当天温和放量(对慢均量、也对自己前 5 日均量)
        #
        # ★ 来源标注:行业惯例(专家 2026-10-28 修正版)。
        #   ★ 不许标「原著写死」—— 专家自己说了原著是定性描述。
        # ======================================================================
        v = cache.field("volume", symbols)
        f = int(p.get("fast_period", 5))          # 5
        sl = int(p.get("slow_period", 50))        # 50
        look = int(p.get("min_day_lookback", 5))  # 突破前 5 天内
        sma_f = v.rolling(f, min_periods=f).mean()
        sma_s = v.rolling(sl, min_periods=sl).mean()
        # ★ 全部基准量都取 t−1(SMA50_Volume[t-1] / SMA5_Volume[t-1]),
        #   突破日当天的量不许进自己的分母 —— 否则是偷看当天。
        sma_f1, sma_s1 = sma_f.shift(1), sma_s.shift(1)

        # 条件1 突破前 5 天内至少有 1 天 Volume ≤ 0.60 × SMA50_Volume[t−1]
        #   Volume[t-5:t] 是 t−5 .. t−1 这 5 天(不含突破日 t)
        vmin5 = v.rolling(look, min_periods=look).min().shift(1)
        c1 = _as_bool(vmin5 <= float(p.get("dryup_day_ratio", 0.60)) * sma_s1)

        # 条件2 SMA5_Volume[t−1] ≤ 0.85 × SMA50_Volume[t−1](收敛,不是冰冻)
        c2 = _as_bool(sma_f1 <= float(p.get("converge_ratio", 0.85)) * sma_s1)

        # 条件3 突破日温和放量:对慢均量 ≥1.00,且对自己前 5 日均量 ≥1.20
        c3 = (_as_bool(v >= float(p.get("breakout_vs_slow", 1.00)) * sma_s1)
              & _as_bool(v >= float(p.get("breakout_vs_fast", 1.20)) * sma_f1))
        return c1 & c2 & c3

    if t == "sigma_squeeze":
        # σ_fast < max_ratio × σ_slow,在突破当天评估(不满足就放弃本次突破)
        f = int(p.get("fast_period", 5))
        sl = int(p.get("slow_period", 20))
        sf = ret_std_matrix(f, symbols)
        ss = ret_std_matrix(sl, symbols)
        return _as_bool(sf < float(p.get("max_ratio", 0.65)) * ss)

    if t == "breakout_volume_band":
        # 突破当天成交量 / SMA_slow(Volume)(t−off) 落在 [min_ratio, max_ratio]
        v = cache.field("volume", symbols)
        sl = int(p.get("slow_period", 50))
        off = int(p.get("offset_days", 1))
        base = v.rolling(sl, min_periods=sl).mean().shift(off)
        r = v / base
        return (_as_bool(r >= float(p.get("min_ratio", 1.0)))
                & _as_bool(r <= float(p.get("max_ratio", 1.8))))

    if t == "vcp_contraction":
        # ★ 第①关:几何收缩选拔门禁(状态机,见本文件上方说明)
        gate, _ = vcp_matrices(p, symbols)
        return _as_bool(gate)

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


# ---------------------------------------------------------------- ⑥ 离场规则矩阵
# ★★ 这一块以前是空的 —— 配置里 exit.rules 写了「收盘跌破 MA50 / EMA10 就走」,
#   执行器只读 exit.params 的止盈和时间止损,★ 这两条离场规则根本没被执行。
#   这正是「悄悄忽略」最危险的样子:配置里写了、引擎没干,而且没人知道。
#   现在补上:离场规则预算成一张 [日期 × 票] 矩阵,True = 当天收盘满足离场条件,
#   第二层挂到 pending_exit、次日开盘平。

def exit_signal_matrix(spec: dict, symbols: list[str]) -> pd.DataFrame:
    """⑥ 离场:把 exit.rules 翻成「当天收盘要不要走」的布尔矩阵。"""
    close = cache.field("close", symbols)
    out = pd.DataFrame(False, index=close.index, columns=close.columns)
    for rule in ((spec or {}).get("rules") or []):
        t = rule.get("type")
        p = rule.get("params", {}) or {}
        if t == "close_below_trailing_stop":
            continue          # 这一条由第二层的止损循环原生负责,不在这里算
        if t == "close_below_ma":
            out |= _as_bool(close < sma_matrix(int(p["ma"]), symbols))
        elif t == "close_below_ema":
            out |= _as_bool(close < ema_matrix(int(p["ema"]), symbols))
        else:
            raise NotImplementedError(
                f"离场规则 {t} 还没实现 —— ★ 没有悄悄忽略它。"
                f"支持:close_below_ma / close_below_ema / close_below_trailing_stop")
    return out


# ---------------------------------------------------------------- 排序打分矩阵
# ★★ 这一块以前也是空的 —— 配置里 ranking 写了排序公式,执行器只认
#   "rs_rank" 这个字符串,拿到一个 dict 就退化成「按代码字母序」。
#   槽位只有 3 个的时候,按字母序挑和按动量挑是两条完全不同的策略。

def rank_score_matrix(spec, symbols: list[str], cfg: dict | None = None
                      ) -> pd.DataFrame:
    """
    候选多于槽位时的排序分数(★ 越大越优先)。
    认得两种公式(都是专家第二轮给的,原文照搬):
      流派一:(Close_t / Close_{t−60} − 1) / ATR%20(t)      → 大的优先
      流派二:D_last = (High_last − Low_last) / High_last    → ★ 小的优先,取负
    """
    close = cache.field("close", symbols)
    if spec is None or isinstance(spec, str):
        return rs_rank_matrix(126, symbols)
    prim = (spec.get("primary") or {})
    f = str(prim.get("formula", ""))
    order = str(prim.get("order", "desc")).lower()

    if "ATR_pct_20" in f or "ATR%20" in f:
        lb = 60
        mom = close / close.shift(lb) - 1.0
        denom = str(spec.get("atr_pct_denominator", "close_t"))
        if denom == "close_t":
            atr_pct = atr_matrix(20, symbols) / close
        elif denom == "sma20_close":
            atr_pct = atr_matrix(20, symbols) / sma_matrix(20, symbols)
        else:
            raise ValueError(f"atr_pct_denominator 只认 close_t / sma20_close,"
                             f"给的是 {denom}")
        score = mom / atr_pct.replace(0.0, np.nan)
    elif "D_last" in f:
        vcp_p = _find_vcp_params(cfg or {})
        if vcp_p is None:
            # ★ 只有「基准一 同环境随机进场」和归因中间行会走到这里 ——
            #   那些变体把进场扳机换掉了,根本没有 VCP 形态,D_last 无从定义。
            #   退回「ADV20 大的优先」,★ 并记一条,报告里打出来。
            _DISABLED_LOG.append(
                "排序 D_last 在「随机进场基准 / 归因中间行」里无从定义"
                "(那些变体没有 VCP 形态)→ 这些变体改按 ADV20 排序。"
                "★ 正式链不受影响。")
            return adv_matrix(20, symbols)
        _, d_last = vcp_matrices(vcp_p, symbols)
        score = d_last
    else:
        raise NotImplementedError(
            f"排序公式还没实现:{f!r} —— ★ 没有悄悄退化成按字母序排。")
    return -score if order == "asc" else score


def _find_vcp_params(cfg: dict) -> dict | None:
    for rule in ((cfg.get("entry") or {}).get("rules") or []):
        if rule.get("type") == "vcp_contraction":
            return rule.get("params") or {}
    return None


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
    exit_sig: np.ndarray          # ⑥ 离场规则:当天收盘要不要走
    rank_score: np.ndarray        # 候选多于槽位时的排序分数(越大越优先)
    ema_trail: np.ndarray         # ⑤ EMA 跟踪止损用的 EMA(没配就全是 NaN)
    last_bar: np.ndarray          # 每只票最后一根有价格的 bar 的行号(含 0 价 bar)
    zero_bar: np.ndarray          # 破产类 0 价 bar 的行号;没有则 -1
    size_mult: np.ndarray = None  # type: ignore  # ★ 广度风险预算标尺,一维,每天一个乘数
    breadth_diag: dict = None     # type: ignore  # ★ 标尺失效天数等诊断
    col: dict[str, int] = None    # type: ignore

    def __post_init__(self):
        self.col = {s: i for i, s in enumerate(self.symbols)}
        if self.size_mult is None:
            self.size_mult = np.ones(len(self.index), dtype=float)
        if self.breadth_diag is None:
            self.breadth_diag = {}


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

    # ⑤ 里如果有 ema_trail 这一级,把对应的 EMA 一次算好
    ema_n = None
    for st in ((cfg.get("trailing_stop") or {}).get("stages") or []):
        if st.get("type") == "ema_trail":
            ema_n = int((st.get("params", {}) or {}).get("ema", 10))
    ema_t = (ema_matrix(ema_n, syms).to_numpy(dtype=float) if ema_n
             else np.full((len(idx), len(syms)), np.nan))

    # ---- ★★ 广度:两个口径,一个当开关(regime),一个当仓位标尺(sizing)
    reg_spec = cfg.get("regime") or {}
    need_chain_breadth = any(r.get("type") == "breadth_above_chain"
                             for r in (reg_spec.get("rules") or []))
    bspec = (cfg.get("sizing") or {}).get("breadth_risk_scaler")
    if bspec and str(bspec.get("source", "chain")) == "chain":
        need_chain_breadth = True

    cb_pct = cb_n = None
    if need_chain_breadth:
        ma_for_breadth = 50
        for r in (reg_spec.get("rules") or []):
            if r.get("type") == "breadth_above_chain":
                ma_for_breadth = int((r.get("params", r) or {}).get("ma", 50))
        if bspec:
            ma_for_breadth = int(bspec.get("ma", ma_for_breadth))
        cb_pct, cb_n = chain_breadth(uni, ma_for_breadth)

    size_mult = np.ones(len(idx), dtype=float)
    bdiag: dict = {}
    if bspec:
        src = str(bspec.get("source", "chain"))
        thr = float(bspec["threshold"])
        low = float(bspec["low_risk_mult"])
        mn = int(bspec.get("min_names", BREADTH_MIN_NAMES))
        if src == "chain":
            pct, nn = cb_pct, cb_n
            bdiag["广度口径"] = f"★ 本链自己范围(universe_mask)里站上 MA{ma_for_breadth} 的比例"
        elif src == "market":
            fld = str(bspec.get("field", "pct_above_ma50"))
            pct, nn = market_breadth(fld, idx)
            bdiag["广度口径"] = f"全市场({fld},breadth_top500.csv)"
        else:
            raise ValueError(
                f"breadth_risk_scaler.source 只认 chain / market,给的是 {src}")
        mult, d = breadth_size_multiplier(pct, nn, thr, low, mn)
        size_mult = mult.reindex(idx).fillna(1.0).to_numpy(dtype=float)
        bdiag.update(d)

    return Matrices(
        symbols=syms,
        index=idx,
        open=cache.field("open", syms).to_numpy(dtype=float),
        high=cache.field("high", syms).to_numpy(dtype=float),
        low=cache.field("low", syms).to_numpy(dtype=float),
        close=close.to_numpy(dtype=float),
        universe=uni.to_numpy(dtype=bool),
        regime=regime_mask(reg_spec, idx, cb_pct, cb_n).to_numpy(dtype=bool),
        entry=entry_trigger(cfg.get("entry") or {}, syms).to_numpy(dtype=bool),
        atr=atr_matrix(atr_p, syms).to_numpy(dtype=float),
        chandelier=chandelier_raw_matrix(
            int(st.get("lookback", 22)), float(st.get("multiple", 3.0)),
            atr_p, syms).to_numpy(dtype=float),
        adv20=adv_matrix(20, syms).to_numpy(dtype=float),
        rs_rank=rs_rank_matrix(
            int(uni_spec.get("rs_lookback", 126)), syms).to_numpy(dtype=float),
        exit_sig=exit_signal_matrix(cfg.get("exit") or {}, syms).to_numpy(dtype=bool),
        rank_score=rank_score_matrix(
            (cfg.get("sizing") or {}).get("rank_by"), syms, cfg).to_numpy(dtype=float),
        ema_trail=ema_t,
        last_bar=last_bar,
        zero_bar=np.array(zb),
        size_mult=size_mult,
        breadth_diag=bdiag,
    )


__all__ = ["Matrices", "build", "universe_mask", "regime_mask", "entry_trigger",
           "atr_matrix", "sma_matrix", "adv_matrix", "chandelier_raw_matrix",
           "rs_rank_matrix", "rsi_matrix", "median_dollar_volume"]
