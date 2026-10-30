#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ ⑤质量复利 / ⑦融合大师 缺的那几个算子 —— 2026-10-30

══════════════════════════════════════════════════════════════════════════
★★★ 三秒版:⑤ 一直跑不了,★ 真正的原因不是「缺 EBIT 和长期负债」——
     数据 2026-10-27 就在仓库里了。★★ 真正缺的是**引擎没写这三个算子**:
         roic_consecutive_above        ← 从来没进过 config_adapter.IMPLEMENTED
         net_debt_to_ebitda_below      ← 同上
         gross_profit_to_assets_rank_above ← 在 BLOCKED_REASONS 里,
                                            写着「A 类:口径已明确,补代码即可」
     ★ 另外 ③ 的 bullish_candle_breakout_prior_high 和 ⑥ 的 fundamental_veto
       也没写。★★★ 所以「缺 EBIT」这个记法错了两层:数据有,代码没有。
══════════════════════════════════════════════════════════════════════════

★ 纪律:engine/ 一个字符都不改。走 engine/ops_exits_1029.py 立过的运行时挂钩套路
  (只往 config_adapter.IMPLEMENTED 里加 key + 包一层 matrices 的函数)。

★★ 一个新阈值都没拍。全部数值逐字来自 engine/configs/quality_compounder.yaml:
     ROIC ≥ 15.0% / years: 3 / 净负债÷EBITDA < 2.5 / GP/A 池内分位 ≥ 80 /
     ROIC 连续两季 < 12.0% / 毛利率同比 < −200bps
  ★ 口径(有息负债 / 投入资本 / 税率)也逐字照抄那份配置的注释。

★★★ 两处「原文没给、我们只能机械读」的,必须留痕(报告里列为 undefined_param):
  ① 「过去 3 年连续 ROIC ≥ 15%」—— 原文没说是「3 个年度点」还是「12 个季度点」。
     本文件默认 **3 个年度点(t / t−4季 / t−8季)**,★ 理由是 1028 审计量覆盖率时
     用的就是这个口径(「连续3年都算得出 12.0%/15.2%/26.4%」),★ 为了和那份数
     对得上。★★ 12 个季度点的严端同时实现,作敏感度(mode="quarters")。
  ② 「第一根阳线」的计数起点原文没给(配置自己标了 undefined_param)。
     ★ 本文件用**唯一不含自由参数的机械读法**:当日是阳线、且收盘 > 前一日最高,
       并且**不要求**它是回踩后的第几根 —— ★ 也就是说「第一根」这个词我们没实现,
       只实现了「阳线 + 收盘破前高」。★★★ 这是减配,不是等价,报告里必须写。
"""
from __future__ import annotations

import functools
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import cache, data, fundamentals, matrices, ops_1029   # noqa: E402

_NOTES: list[str] = []


def notes() -> list[str]:
    return list(_NOTES)


def _note(s: str) -> None:
    if s not in _NOTES:
        _NOTES.append(s)


def _as_bool(df: pd.DataFrame) -> pd.DataFrame:
    return df.fillna(False).astype(bool)


# ══════════════════════════════════════════════════════════════════════════
# 一 · 自己的季度对齐表 —— ★ 只多取几个科目,engine/fundamentals.py 一个字没动
# ══════════════════════════════════════════════════════════════════════════
#
# ★ 为什么不改 engine/fundamentals.py 的 _QCOLS:那份表是三条老链在用的,
#   动它等于动已有结论的口径。这里新建一张,走的是同一套 ttm()/quarterly()
#   (★ 所以 YTD 差分、首发版本、TTM 四季连续这三条铁律全部继承,没有第二套口径)。
_COLS = {
    "ebit": ("EBIT", "ttm"),
    "ibt": ("IncomeBeforeTax", "ttm"),
    "ni": ("NetIncome", "ttm"),
    "rev": ("Revenue", "ttm"),
    "cor": ("CostOfRevenue", "ttm"),
    "dda1": ("DepreciationDepletionAndAmortization", "ttm"),
    "dda2": ("DepreciationAmortizationAndAccretionNet", "ttm"),
    "ta": ("TotalAssets", "pt"),
    "eq": ("StockholdersEquity", "pt"),
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "pt"),
    "ltd": ("LongTermDebt", "pt"),
    "stb": ("ShortTermBorrowings", "pt"),
    "ltdc": ("LongTermDebtCurrent", "pt"),
}


@functools.lru_cache(maxsize=4096)
def frame(symbol: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols, effs = {}, {}
    for name, (metric, kind) in _COLS.items():
        ser = (fundamentals.ttm(symbol, metric) if kind == "ttm"
               else fundamentals.quarterly(symbol, metric))
        cols[name] = {o.period_end: o.value for o in ser}
        effs[name] = {o.period_end: o.eff for o in ser}
    idx = sorted({pe for d in cols.values() for pe in d})
    if not idx:
        return pd.DataFrame(), pd.DataFrame()
    v = pd.DataFrame({k: pd.Series(x, dtype=float) for k, x in cols.items()}
                     ).reindex(idx)
    # ★★★ 本轮踩到的一个**静默空**:某个科目一条记录都没有时,那一列的 dtype
    #   是 float64(全 NaN),和别的 datetime64 列混在一起做 `.max(axis=1)` 会
    #   抛 TypeError('>=' not supported between float and Timestamp);
    #   ★ 而 panel() 外面那个 except 会把它吞掉 → 整只票的日频面板变成全空。
    #   ★★ 症状是「覆盖率只有 8%」,看着像数据缺,实际是**我们自己的类型 bug**。
    #   → 这里把生效日表**显式强制成 datetime64**,一列都不许是 float。
    e = pd.DataFrame({k: pd.to_datetime(pd.Series(x), errors="coerce")
                      for k, x in effs.items()}).reindex(idx)
    for c in e.columns:
        e[c] = pd.to_datetime(e[c], errors="coerce")
    v.index = pd.DatetimeIndex(idx)
    e.index = pd.DatetimeIndex(idx)
    return v, e


def _debt(v: pd.DataFrame) -> pd.Series:
    """
    有息负债 = LongTermDebt + ShortTermBorrowings + LongTermDebtCurrent。

    ★★★ 口径说明(必须写进报告):这三个标签**缺的那只票按 0 处理**,
      但**要求至少有一个有值** —— 三个全缺 = NaN(判不合格),不猜不补。
      ★ 理由:不报 ShortTermBorrowings 的公司绝大多数是真没有短期借款
        (这是 1030 覆盖率三分类里的「甲类」情形);而三个全缺说明
        我们对这只票的资本结构**一点都看不到**,那是「乙类」(我们取数取窄),
        ★ 把它当 0 等于把自己的 bug 说成「这家公司没有负债」。
    """
    parts = [v["ltd"], v["stb"], v["ltdc"]]
    any_ok = parts[0].notna() | parts[1].notna() | parts[2].notna()
    s = sum(p.fillna(0.0) for p in parts)
    return s.where(any_ok)


def _dda(v: pd.DataFrame) -> pd.Series:
    """D&A:主用 DepreciationDepletionAndAmortization,缺的回落到另一个写法。

    ★★ 「同一样东西两种写法」本轮又一例:D&A 在 SEC 里有两个标签
       (DepreciationDepletionAndAmortization 68.4% /
        DepreciationAmortizationAndAccretionNet 9.2%),★ 只认前者会少掉一批票。
    """
    a = v["dda1"].copy()
    m = a.isna() & v["dda2"].notna()
    a[m] = v["dda2"][m]
    return a


def metric_q(symbol: str, name: str) -> tuple[pd.Series, pd.Series]:
    v, e = frame(symbol)
    if v.empty:
        return pd.Series(dtype=float), pd.Series(dtype="datetime64[ns]")

    if name == "roic_ttm":
        # NOPAT = EBIT × (1 − 税率);税率 = (IncomeBeforeTax − NetIncome) / IncomeBeforeTax
        # 投入资本 = 有息负债 + 股东权益 − 现金   ★ 逐字照抄配置注释
        tax = (v["ibt"] - v["ni"]) / v["ibt"].where(v["ibt"] != 0)
        # ★ 税率落在 [0,1] 之外的那几期判不合格(亏损期税率会算成负数或 >1)——
        #   ★ 不截断、不夹到 [0,1]:夹一下就等于我们替它编了一个税率。
        tax = tax.where((tax >= 0.0) & (tax <= 1.0))
        debt = _debt(v)
        ic = debt + v["eq"] - v["cash"]
        ic = ic.where(ic > 0)
        nopat = v["ebit"] * (1.0 - tax)
        ok = nopat.notna() & ic.notna()
        eff = e[["ebit", "ibt", "ni", "eq", "cash", "ltd", "stb", "ltdc"]].max(axis=1)
        return (nopat / ic).where(ok) * 100.0, eff        # ★ 单位:%

    if name == "net_debt_to_ebitda":
        debt = _debt(v)
        dda = _dda(v)
        ebitda = v["ebit"] + dda
        ok = debt.notna() & v["cash"].notna() & ebitda.notna() & (ebitda > 0)
        # ★ EBITDA ≤ 0 的那几期判**不合格**(不是判「杠杆很低」)——
        #   ★ 负 EBITDA 下这个比值会变成负数、看着比谁都安全,那是口径陷阱。
        eff = e[["ebit", "dda1", "dda2", "cash", "ltd", "stb", "ltdc"]].max(axis=1)
        return ((debt - v["cash"]) / ebitda.where(ebitda > 0)).where(ok), eff

    if name == "gpa_ttm":
        ok = v["rev"].notna() & v["cor"].notna() & (v["ta"] > 0)
        eff = e[["rev", "cor", "ta"]].max(axis=1)
        return ((v["rev"] - v["cor"]) / v["ta"].where(v["ta"] > 0)).where(ok), eff

    if name == "gross_margin_yoy_bps":
        gm = (v["rev"] - v["cor"]) / v["rev"].where(v["rev"] > 0)
        prev = gm.shift(4)
        ok = gm.notna() & prev.notna()
        eff = e[["rev", "cor"]].max(axis=1)
        return ((gm - prev) * 10000.0).where(ok), eff

    raise KeyError(f"派生指标 {name} 没实现 —— ★ 没有悄悄返回 NaN")


@functools.lru_cache(maxsize=64)
def panel(name: str, symbols: tuple[str, ...]) -> pd.DataFrame:
    cal = data.trading_calendar()
    cols = {}
    for s in symbols:
        # ★★★ 这里**故意不包 try**:算不出必须是「数据不够」,不许是「我们的
        #   代码抛了异常被吞掉」。★ 本轮就是被一个吞掉的 TypeError 骗了一次
        #   (覆盖率报成 8%,真值 29%)—— 所以让它炸出来。
        v, e = metric_q(s, name)
        cols[s] = fundamentals._to_daily(v, e, cal)         # ★ 复用引擎的日频铺开
    return pd.DataFrame(cols, index=cal)


def get(name: str, symbols: list[str]) -> pd.DataFrame:
    return panel(name, tuple(symbols))


# ══════════════════════════════════════════════════════════════════════════
# 二 · 「连续 N 年 ROIC ≥ X%」—— ★ 在**季度**层面判,再铺日频
# ══════════════════════════════════════════════════════════════════════════

ROIC_MODES = ("years", "quarters")


@functools.lru_cache(maxsize=64)
def roic_consecutive(symbols: tuple[str, ...], years: int, min_pct: float,
                     mode: str) -> pd.DataFrame:
    """
    mode="years"    : t / t−4季 / t−8季 …(共 years 个年度点)全部 ≥ min_pct
    mode="quarters" : 最近 years×4 个季度的 TTM ROIC 全部 ≥ min_pct(严端)
    ★ 任一需要的点算不出 → 判不合格(NaN 当不合格,和引擎的三条铁律一致)。
    """
    if mode not in ROIC_MODES:
        raise ValueError(f"mode 只能是 {ROIC_MODES}")
    cal = data.trading_calendar()
    cols = {}
    lags = ([4 * k for k in range(years)] if mode == "years"
            else list(range(years * 4)))
    for s in symbols:
        v, e = metric_q(s, "roic_ttm")
        if v.empty:
            cols[s] = pd.Series(False, index=cal)
            continue
        ok = None
        for L in lags:
            sh = v.shift(L)
            cond = sh.notna() & (sh >= min_pct)
            ok = cond if ok is None else (ok & cond)
        ser = ok.astype(float)
        cols[s] = fundamentals._to_daily(ser, e, cal).fillna(0.0) > 0.5
    return pd.DataFrame(cols, index=cal)


# ══════════════════════════════════════════════════════════════════════════
# 三 · 运行时挂钩
# ══════════════════════════════════════════════════════════════════════════

_UNIVERSE_TYPES = frozenset({
    "roic_consecutive_above", "net_debt_to_ebitda_below",
    "gross_profit_to_assets_rank_above",
    # ★ 基-4 格林布拉特方法卡的 data_requirement 原文:「金融股和公用事业通常要排除」
    #   ★★★ 它**不是** ⑤ 自己的原著条件(是另一条方法的),所以只作第三条臂的参照,
    #     ★ 主结论里不用它。实现放这里是为了让那条臂能跑。
    "exclude_sic_groups",
})
#: ★★★ 「同一样东西两种写法」的又一个变体(本轮新撞,★ 写进报告):
#:   **同一条规则按「步」注册,而注册漏了一步。**
#:   `ma_stack_bullish` 在 config_adapter.IMPLEMENTED["universe"] 里有、
#:   ★ 在 ["entry"] 里**没有** —— 而 quality_compounder.yaml 把它写在 ③ entry。
#:   ★★ 后果:⑤ 这条链在预检就被判「有没实现的规则,不许带着它跑」,
#:     ★★★ 而真实情况是**算子早就有了,只是没在那一步登记**。
#:   ★ 处置:③ 这一步直接**调用 ① 的同一份实现**,一行新算法都不写。
_ENTRY_TYPES = frozenset({"bullish_candle_breakout_prior_high",
                          "ma_stack_bullish"})
_EXIT_TYPES = frozenset({"fundamental_veto"})

_orig_uni = None
_orig_entry = None
_orig_exit = None

#: ★ 公用事业 SIC 两位 = 49(电力/燃气/自来水/卫生服务)。
#:   金融 SIC 6000–6799 直接复用 engine/ops_1029.py 的 sic_daily / 同一个区间,
#:   ★ 不自己再写一套 SIC 解析。
UTIL_SIC2 = ("49",)


def _uni(rule: dict, syms: list[str], index: pd.DatetimeIndex) -> pd.DataFrame:
    t = rule.get("type")
    p = rule.get("params", {}) or {}
    if t not in _UNIVERSE_TYPES:
        return _orig_uni(rule, syms, index)

    if t == "roic_consecutive_above":
        _note("★ roic_consecutive_above 已挂钩:NOPAT=EBIT×(1−税率),"
              "税率=(IncomeBeforeTax−NetIncome)/IncomeBeforeTax 且必须落在 [0,1];"
              "投入资本=有息负债+股东权益−现金;有息负债=LTD+STB+LTDC(三个全缺=NaN)。"
              "★ 数值 15.0% / 3 年逐字来自配置。")
        g = roic_consecutive(tuple(syms), int(p.get("years", 3)),
                             float(p["min_roic_pct"]),
                             str(p.get("mode", "years")))
        return _as_bool(g.reindex(index=index, columns=syms))

    if t == "net_debt_to_ebitda_below":
        _note("★ net_debt_to_ebitda_below 已挂钩:EBITDA=EBIT+D&A"
              "(D&A 两种写法都认);★ EBITDA ≤ 0 判不合格,不判「杠杆低」。")
        nd = get("net_debt_to_ebitda", syms)
        return _as_bool(nd.notna() & (nd < float(p["threshold"])))

    if t == "gross_profit_to_assets_rank_above":
        _note("★ gross_profit_to_assets_rank_above 已挂钩:池内横截面分位 "
              "≥ min_percentile(2026-10-28 从绝对值 0.35 改过来的那个口径,"
              "★ 一个新数都没拍)。")
        gp = get("gpa_ttm", syms)
        pct = gp.rank(axis=1, pct=True)
        lo = float(p.get("min_percentile", 80.0)) / 100.0
        return _as_bool(gp.notna() & (pct >= lo))

    if t == "exclude_sic_groups":
        _note("★ exclude_sic_groups 已挂钩(★ 跨方法借来的条件,只作参照臂)。")
        sic = ops_1029.sic_daily(tuple(syms))
        bad = pd.DataFrame(False, index=sic.index, columns=sic.columns)
        if p.get("exclude_financial", True):
            bad |= (sic >= ops_1029.SIC_FINANCE_LO) & (sic <= ops_1029.SIC_FINANCE_HI)
        for two in (p.get("exclude_sic2") or UTIL_SIC2):
            lo, hi = int(two) * 100, int(two) * 100 + 99
            bad |= (sic >= lo) & (sic <= hi)
        keep = sic.notna() & (~bad)          # ★ SIC 看不到的那天一律不合格(紧端)
        return _as_bool(keep.reindex(index=index, columns=syms))

    raise AssertionError(t)


def _entry(rule: dict, symbols: list[str]) -> pd.DataFrame:
    t = rule.get("type")
    if t not in _ENTRY_TYPES:
        return _orig_entry(rule, symbols)
    if t == "ma_stack_bullish":
        _note("★★ ma_stack_bullish 在 ③ entry 上已挂钩 —— ★ 调用的是 ① universe "
              "里**同一份**实现(matrices._universe_rule_mask),"
              "★★★ 一行新算法都没写。它原来只在 ① 登记过,③ 没登记。")
        idx = cache.field("close", symbols).index
        return _as_bool(_orig_uni(rule, list(symbols), idx))
    _note("★★ bullish_candle_breakout_prior_high 已挂钩,★ 但它是**减配实现**:"
          "只做到「当日阳线 + 收盘 > 前一日最高」,★★★ 「第一根」这个计数"
          "原文没给起点(配置自己标 undefined_param),我们没有替它拍一个。")
    o = cache.field("open", symbols)
    c = cache.field("close", symbols)
    h = cache.field("high", symbols)
    return _as_bool((c > o) & (c > h.shift(1)))


def _exit(spec: dict, symbols: list[str]) -> pd.DataFrame:
    """
    ⑥ fundamental_veto:conditions_any 任一成立 → 发离场信号。

    ★★ 口径两条(和 engine/run_fundamental.py 的 PIT 规范一致):
      ① 数据看不到(NaN)→ ★ **不触发清仓**(拿不到数据不该凭空卖掉持仓);
      ② 「连续 N 季」在**季度**层面判,不在日频判。
    """
    rules = (spec.get("rules") or []) if isinstance(spec, dict) else []
    mine = [r for r in rules if r.get("type") in _EXIT_TYPES]
    if not mine:
        return _orig_exit(spec, symbols)
    rest = {k: v for k, v in spec.items() if k != "rules"}
    rest["rules"] = [r for r in rules if r.get("type") not in _EXIT_TYPES]
    out = _orig_exit(rest, symbols) if rest["rules"] else None
    cal = data.trading_calendar()
    if out is None:
        out = pd.DataFrame(False, index=cal, columns=symbols)
    for r in mine:
        for cond in (r.get("conditions_any") or []):
            if cond.get("enabled", True) is False:
                _note(f"★ fundamental_veto 的子条件 {cond.get('metric')} "
                      f"配置里 enabled: false —— 没执行,已登记。")
                continue
            met, op = cond["metric"], cond["op"]
            val = float(cond["value"])
            cols = {}
            for s in symbols:
                v, e = metric_q(s, met)
                if v.empty:
                    cols[s] = pd.Series(False, index=cal)
                    continue
                if op == "below_for_consecutive_quarters":
                    q = int(cond["quarters"])
                    bad = (v < val)
                    hit = bad.copy()
                    for k in range(1, q):
                        hit &= bad.shift(k).fillna(False)
                    # ★ 需要的那 q 季里有算不出的 → 不触发(NaN 不清仓)
                    have = v.notna()
                    for k in range(1, q):
                        have &= v.shift(k).notna()
                    ser = (hit & have).astype(float)
                elif op == "lt":
                    ser = (v.notna() & (v < val)).astype(float)
                else:
                    raise KeyError(f"fundamental_veto 的 op={op} 没实现")
                cols[s] = fundamentals._to_daily(ser, e, cal).fillna(0.0) > 0.5
            out = out | pd.DataFrame(cols, index=cal).reindex(
                index=out.index, columns=out.columns).fillna(False)
            _note(f"★ fundamental_veto 子条件已挂钩:{met} {op} {val}")
    return _as_bool(out)


def install() -> None:
    """运行时挂钩。★ engine/ 的 matrices.py / chain.py / config_adapter.py 一字未改。"""
    global _orig_uni, _orig_entry, _orig_exit
    from engine import config_adapter
    if _orig_uni is None:
        _orig_uni = matrices._universe_rule_mask
        matrices._universe_rule_mask = _uni
    if _orig_entry is None:
        _orig_entry = matrices._entry_rule_raw
        matrices._entry_rule_raw = _entry
    if _orig_exit is None:
        _orig_exit = matrices.exit_signal_matrix
        matrices.exit_signal_matrix = _exit
    config_adapter.IMPLEMENTED["universe"] |= _UNIVERSE_TYPES
    config_adapter.IMPLEMENTED["entry"] |= _ENTRY_TYPES
    config_adapter.IMPLEMENTED["exit"] |= _EXIT_TYPES
    # ★★ BLOCKED_REASONS 里那条 GP/A「引擎还没写」的记录现在过期了 —— 删掉它,
    #   否则预检会继续把它报成 B 类「定义没定」,而它从来是 A 类。
    config_adapter.BLOCKED_REASONS.pop("gross_profit_to_assets_rank_above", None)
    _note("★★★ ⑤⑦ 的算子已挂钩(运行时):universe 三条 + entry 一条 + exit 一条。"
          "engine/ 一个字符都没改。")
