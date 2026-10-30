#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 基本面建设的运行时挂钩 —— 补标签覆盖层 + 四个新算子(2026-10-30)

三秒版:两件事。
  ① **补标签覆盖层** —— 把 `tag_backfill_1030.py` 产出的同义标签记录
     接到 `data.load_fundamentals` 上,★ 让 engine 的 PIT 流水线原封不动地
     把它们当普通记录处理(YTD 差分 / 首发版 / filing+1 交易日 全部继承)。
  ② **四个新算子** —— 基-2 / 基-5 / 基-6 / 基-4 / 基-12 子集要用的分位闸门。

★ engine/ 一个字符都不改。套路照 engine/ops_exits_1029.install() 和
  probe/masters_57_1030/ops_q57_1030.py(★ 那两个文件只读,没动)。

══════════════════════════════════════════════════════════════════════════
★★ 覆盖层的三条铁律
══════════════════════════════════════════════════════════════════════════
  ① **只加不改**:同一个 (period_start, period_end) 本地已有记录时,
     ★ 一律用本地那条(它有 accepted_at,带时分秒),★★ 覆盖层只补本地没有的期。
  ② **口径不同的不混**:`EBIT_OperatingIncomeLoss`(营业利润)★★★ 默认**不挂**。
     ★ 实测它和 EBIT 在 12,553 个重叠期上:绝对相对差中位 4.1%、p90 43.7%、
       ★★ 31.6% 的期差超过 10% —— ★★★ 这不是同义字段,是另一个指标。
     ★ 要挂必须显式 `install(with_operating_income=True)`,★★ 并单列成一条臂。
  ③ **生效基准如实标**:覆盖层记录只有 `filed`(日期,无时分)。
     ★ 实测在 4,788 个两边都有的期上:93.5% 同一天、304 期 dump 的 filed
       **晚于**本地 accepted_at(= 更保守,无偷看风险),
       ★★★ 只有 **2 期**(BKNG 223 天 / 另一期 8 天)dump 的 filed 更早 ——
       ★ 这 2 期是本覆盖层**唯一的偷看风险点**,已登记在册。
"""
from __future__ import annotations

import functools
import gzip
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import cache, config_adapter, data, fundamentals, matrices  # noqa: E402

OVERLAY = os.path.join(HERE, "tag_overlay_1030.json.gz")

_notes: list[str] = []


def notes() -> list[str]:
    return list(_notes)


def _note(s: str) -> None:
    if s not in _notes:
        _notes.append(s)


# ══════════════════════════════════════════════════════════════════════════
# 一 · 补标签覆盖层
# ══════════════════════════════════════════════════════════════════════════

@functools.lru_cache(maxsize=1)
def _overlay() -> dict:
    with gzip.open(OVERLAY, "rt", encoding="utf-8") as fh:
        return json.load(fh)


_orig_load_fund = None
_WITH_OIL = False
#: ★ 哪些指标名走覆盖层(★ 显式白名单,不许「全部字段都覆盖」)
_OVERLAY_METRICS = ("LongTermDebt", "EBIT", "LongTermDebtTotal")

# ══════════════════════════════════════════════════════════════════════════
# 一-B · ★★★ 数据组那份 SEC PIT 主表(2026-10-30 换用)
# ══════════════════════════════════════════════════════════════════════════
#
# ★★★ 这一段是**替换**,不是「只加不改」—— ★ 和上面那个覆盖层的逻辑**相反**,
#   必须讲清楚为什么:
#
#   ★★ 基-6(EV/EBIT 分位)和基-4(神奇公式)做的是**横截面排名**。
#   ★★★ 如果一部分票的 EBIT 是「营业利润」、另一部分是「税前+利息」,
#     那这个排名就是**拿苹果和橘子比大小** —— ★ 而且不是噪声:
#     实测两个口径差超 10% 的期数占 31.58%。
#   → ★★★ **对横截面排名,口径一致性比覆盖率更重要。**
#     所以 EBIT / 长期负债**整列换成数据组那一份**(全池同一个口径),
#     ★★ 不做「我们的优先、它的补缺」那种混着用。
#
# ★★ 但它自己内部仍然是**混口径**的(README 二节):
#     47,002 行 reported_operating_income(88.7%)
#      6,016 行 derived_pretax_plus_interest(11.3%,★ 推算的)
#   ★ 所以另外提供 `reported_only=True` 的敏感度臂 —— ★★ 只用报表上的营业利润,
#     看混口径那 11.3% 有多大影响。
_SEC_OVERLAY = os.path.join(HERE, "sec_overlay_1030.json.gz")
_SEC_METRICS = ("EBIT", "LongTermDebt")
_SEC_MODE: str | None = None
_SEC_REPORTED_ONLY = False
#: ★ 数据组点名要剔的 4 只(★★★ 绝对不许填 0)
SEC_DROP_4 = ("TXT", "PCAR", "MTR", "TMHC")


@functools.lru_cache(maxsize=1)
def _sec_overlay() -> dict:
    with gzip.open(_SEC_OVERLAY, "rt", encoding="utf-8") as fh:
        return json.load(fh)


def _sec_merged(symbol: str) -> dict:
    base = dict(_orig_load_fund(symbol))
    if symbol in SEC_DROP_4:
        # ★★★ 数据组点名:这 4 只**剔除**,★ 不许填 0 ——
        #   填 0 会把 TXT / PCAR 误判成「零负债的好公司」。
        #   ★ 这里把两列清空 = 任何用到它们的闸门都判这只票不合格。
        for mt in _SEC_METRICS:
            base[mt] = []
        return base
    ov = _sec_overlay().get(symbol) or {}
    for mt in _SEC_METRICS:
        recs = ov.get(mt) or []
        if _SEC_REPORTED_ONLY and mt == "EBIT":
            recs = [r for r in recs
                    if r.get("basis") == "reported_operating_income"]
        base[mt] = [dict(r, metric=mt) for r in recs]     # ★★ 替换,不是追加
    return base


def install_sec_overlay(reported_only: bool = False) -> None:
    """★★★ 换用数据组那份主表(**替换** EBIT / 长期负债两列)。"""
    global _orig_load_fund, _SEC_MODE, _SEC_REPORTED_ONLY
    _SEC_REPORTED_ONLY = bool(reported_only)
    if _orig_load_fund is None:
        _orig_load_fund = data.load_fundamentals
    data.load_fundamentals = _sec_merged
    _SEC_MODE = "reported_only" if reported_only else "all_basis"
    for fn in (fundamentals.quarterly, fundamentals.ttm,
               fundamentals.quarter_frame, fundamentals.panel,
               fundamentals.shares_quarterly):
        fn.cache_clear()
    frame.cache_clear()
    panel.cache_clear()
    _note("★★★ 已换用数据组的 SEC PIT 主表(sec_ltd_ebit_pit_1030.csv.gz):"
          "EBIT / 长期负债两列**整列替换**,★ 全池同一个口径(横截面排名的前提)。"
          f"★★ 当前模式 = {_SEC_MODE}"
          "(all_basis = 含 11.3% 推算行;reported_only = 只用报表营业利润)。"
          "★★★ 注意这和我们原有的 EBIT **不是同一个指标**:原有 100% 是"
          "「税前+利息」推导,这份首选「营业利润」—— 实测两口径差超 10% 的"
          "期数占 31.58%。")
    _note("★★★ TXT / PCAR / MTR / TMHC 四只已**剔除**(两列清空)—— "
          "★ 数据组点名,★★ 绝对不许填 0:TXT/PCAR 有负债但没取到,"
          "填 0 等于把『缺数据』变成『数据错』(会误判成零负债的好公司)。")
    _note("★★ 没负债的 13 只(BMI/ISRG/VEEV/ABMD/OFLX/VNDA/TRUE/ENTA/LIXT/"
          "MPWR/COLM/FF/WLKP)长期负债按 **0** 算 —— ★ 这是「真的没有」,"
          "不是「缺数据」(数据组点名;BBW / MSB 因为连 EBIT 也没有,"
          "★ 没能按 0 补上,已登记)。")
    _note("★★ PIT:这份表只有 `filed`(日期)。★★★ 做**闸门**用 `filed` 是安全的 —— "
          "SEC 的 filed 是递交日,业绩通常更早已通过 8-K 公布,所以 filed "
          "**晚于**真实可得日 → 偏保守、不会偷看。★ 本轮五条链全部是闸门,"
          "没有任何「财报日前后」的事件窗口。")


def _merged(symbol: str) -> dict:
    base = dict(_orig_load_fund(symbol))
    ov = _overlay().get(symbol) or {}
    for metric in _OVERLAY_METRICS:
        add = ov.get(metric) or []
        if not add:
            continue
        have = {(str(r.get("period_start")), str(r.get("period_end")))
                for r in (base.get(metric) or [])}
        keep = [dict(r, metric=metric) for r in add
                if (str(r.get("period_start")), str(r.get("period_end"))) not in have]
        base[metric] = list(base.get(metric) or []) + keep
    if _WITH_OIL:
        add = ov.get("EBIT_OperatingIncomeLoss") or []
        base["EBIT_OperatingIncomeLoss"] = [dict(r, metric="EBIT_OperatingIncomeLoss")
                                            for r in add]
    return base


def install_overlay(with_operating_income: bool = False) -> None:
    """★ 把覆盖层接上。★★ 幂等 —— 重复调用不会叠加。"""
    global _orig_load_fund, _WITH_OIL
    _WITH_OIL = bool(with_operating_income)
    if _orig_load_fund is None:
        _orig_load_fund = data.load_fundamentals
        data.load_fundamentals = _merged
    # ★ engine 那几个 lru_cache 必须清掉,否则读的还是补之前的
    for fn in (fundamentals.quarterly, fundamentals.ttm,
               fundamentals.quarter_frame, fundamentals.panel,
               fundamentals.shares_quarterly):
        fn.cache_clear()
    # ★ 新指标要登记流量/存量,否则 quarterly() 会 raise(那个 raise 是对的)
    fundamentals.STOCK_METRICS.add("LongTermDebtTotal")
    if _WITH_OIL:
        fundamentals.FLOW_METRICS.add("EBIT_OperatingIncomeLoss")
    _note("★★ 补标签覆盖层已挂上(只加不改:本地已有的期一律用本地那条)。"
          f"★ 口径不同的营业利润档 {'已挂(单列臂)' if _WITH_OIL else '未挂'}。")


# ══════════════════════════════════════════════════════════════════════════
# 二 · 派生指标:P/B · P/E · EV/EBIT · ROC(神奇公式)
# ══════════════════════════════════════════════════════════════════════════

_COLS = {
    "eq": ("StockholdersEquity", "pt"),
    "ta": ("TotalAssets", "pt"),
    "ca": ("CurrentAssets", "pt"),
    "cl": ("CurrentLiabilities", "pt"),
    "ig": ("IntangiblesAndGoodwill", "pt"),
    "cash": ("CashAndCashEquivalentsAtCarryingValue", "pt"),
    "ltdt": ("LongTermDebtTotal", "pt"),
    "ltd": ("LongTermDebt", "pt"),
    "ltdc": ("LongTermDebtCurrent", "pt"),
    "stb": ("ShortTermBorrowings", "pt"),
    "ebit": ("EBIT", "ttm"),
    "eps": ("DilutedEPS", "ttm"),
    "ocf": ("OperatingCashFlow", "ttm"),
    "capex": ("PaymentsToAcquirePropertyPlantAndEquipment", "ttm"),
    "capex2": ("PaymentsToAcquireProductiveAssets", "ttm"),
}


@functools.lru_cache(maxsize=4096)
def frame(symbol: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    cols, effs = {}, {}
    for name, (metric, kind) in _COLS.items():
        try:
            ser = (fundamentals.ttm(symbol, metric) if kind == "ttm"
                   else fundamentals.quarterly(symbol, metric))
        except KeyError:
            ser = ()
        cols[name] = {o.period_end: o.value for o in ser}
        effs[name] = {o.period_end: o.eff for o in ser}
    sq = fundamentals.shares_quarterly(symbol)
    cols["sh"] = {o.period_end: o.value for o in sq}
    effs["sh"] = {o.period_end: o.eff for o in sq}
    idx = sorted({pe for d in cols.values() for pe in d})
    if not idx:
        return pd.DataFrame(), pd.DataFrame()
    v = pd.DataFrame({k: pd.Series(x, dtype=float) for k, x in cols.items()}
                     ).reindex(idx)
    # ★★ 照 ops_q57 踩过的那个坑:生效日表每一列**强制 datetime64**,
    #   否则全 NaN 的列是 float64,.max(axis=1) 会在 float 和 Timestamp 间比大小
    e = pd.DataFrame({k: pd.to_datetime(pd.Series(x), errors="coerce")
                      for k, x in effs.items()}).reindex(idx)
    for c in e.columns:
        e[c] = pd.to_datetime(e[c], errors="coerce")
    v.index = pd.DatetimeIndex(idx)
    e.index = pd.DatetimeIndex(idx)
    return v, e


def _net_debt(v: pd.DataFrame) -> pd.Series:
    """净债 = 长期债务总额(含当期)+ 短期借款 − 现金。

    ★ 长期债务总额优先用新指标 LongTermDebtTotal(T 梯子),缺了回落到
      LongTermDebt(非当期)+ LongTermDebtCurrent。
    ★★ 短期借款缺的按 0(不报短期借款的公司绝大多数是真没有),
      ★★★ 但长期债务那一项**必须有值** —— 全缺 = NaN,不猜不补。
    """
    ltd_total = v["ltdt"].copy()
    alt = v["ltd"].fillna(0.0) + v["ltdc"].fillna(0.0)
    alt = alt.where(v["ltd"].notna() | v["ltdc"].notna())
    ltd_total = ltd_total.where(ltd_total.notna(), alt)
    nd = ltd_total + v["stb"].fillna(0.0) - v["cash"]
    return nd.where(ltd_total.notna() & v["cash"].notna())


def metric_q(symbol: str, name: str) -> tuple[pd.Series, pd.Series]:
    """季度级派生指标(不含价格的那一半)。★ 算不出就是 NaN,不猜不补。"""
    v, e = frame(symbol)
    if v.empty:
        return pd.Series(dtype=float), pd.Series(dtype="datetime64[ns]")

    if name == "bvps":                      # 每股净资产(P/B 的分母)
        ok = v["eq"].notna() & (v["sh"] > 0)
        return (v["eq"] / v["sh"].where(v["sh"] > 0)).where(ok), \
            e[["eq", "sh"]].max(axis=1)

    if name == "eps_ttm":
        return v["eps"], e[["eps"]].max(axis=1)

    if name == "ebit_ttm":
        return v["ebit"], e[["ebit"]].max(axis=1)

    if name == "net_debt":
        nd = _net_debt(v)
        return nd, e[["ltdt", "ltd", "ltdc", "stb", "cash"]].max(axis=1)

    if name == "roc_greenblatt":
        # ★★ ROC = EBIT / (净营运资金 + 净固定资产)
        # ★★★ 净固定资产是**派生式**(标「我们算的」):
        #     TotalAssets − CurrentAssets − (无形+商誉)
        #   ★ 失真方向单一:把递延税/长期应收/使用权资产也算进去 → 分母偏大
        #     → ROC 系统性偏低。★ 不是噪声,报告里必须写。
        nwc = v["ca"] - v["cl"]
        nfa = v["ta"] - v["ca"] - v["ig"]
        den = nwc + nfa
        ok = (v["ebit"].notna() & nwc.notna() & nfa.notna() & (den > 0))
        return (v["ebit"] / den.where(den > 0)).where(ok) * 100.0, \
            e[["ebit", "ca", "cl", "ta", "ig"]].max(axis=1)

    if name == "fcf_ttm_local":
        cap = v["capex"].copy()
        m = cap.isna() & v["capex2"].notna()
        cap[m] = v["capex2"][m]
        ok = v["ocf"].notna() & cap.notna()
        return (v["ocf"] - cap).where(ok), e[["ocf", "capex", "capex2"]].max(axis=1)

    if name == "shares_yoy_pct":
        base = v["sh"].shift(4)
        ok = v["sh"].notna() & base.notna() & (base > 0)
        return ((v["sh"] / base - 1.0) * 100.0).where(ok), e[["sh"]].max(axis=1)

    raise KeyError(f"派生指标 {name} 没实现 —— ★ 没有悄悄返回 NaN")


@functools.lru_cache(maxsize=64)
def panel(name: str, symbols: tuple[str, ...]) -> pd.DataFrame:
    cal = data.trading_calendar()
    cols = {}
    for s in symbols:
        # ★ 故意不包 try:算不出必须是「数据不够」,不许是「我们的代码抛了被吞掉」
        vv, ee = metric_q(s, name)
        cols[s] = fundamentals._to_daily(vv, ee, cal)
    return pd.DataFrame(cols, index=cal)


def get(name: str, symbols: list[str]) -> pd.DataFrame:
    return panel(name, tuple(symbols))


# ---------------------------------------------------------------- 含价格的比值

def price_ratio(name: str, symbols: list[str]) -> pd.DataFrame:
    """P/B · P/E · EV/EBIT —— ★ 分母 ≤ 0 的格子一律 NaN(判不合格)。"""
    close = cache.field("close", symbols)
    if name == "pb":
        bv = get("bvps", symbols).reindex_like(close)
        return close / bv.where(bv > 0)
    if name == "pe":
        eps = get("eps_ttm", symbols).reindex_like(close)
        return close / eps.where(eps > 0)
    if name == "ev_ebit":
        sh = pd.DataFrame({s: fundamentals.panel("shares", (s,))[s]
                           for s in symbols}).reindex_like(close)
        nd = get("net_debt", symbols).reindex_like(close)
        ebit = get("ebit_ttm", symbols).reindex_like(close)
        ev = close * sh + nd
        ok = sh.notna() & nd.notna() & (ebit > 0) & (ev > 0)
        return (ev / ebit.where(ebit > 0)).where(ok)
    raise KeyError(name)


# ══════════════════════════════════════════════════════════════════════════
# 三 · 新算子(① universe)
# ══════════════════════════════════════════════════════════════════════════

_UNIVERSE_TYPES = frozenset({
    "pb_below", "pe_rank_bottom", "ev_ebit_rank_bottom",
    "magic_formula_rank_top", "share_count_declining", "fcf_positive",
})
_EXIT_TYPES = frozenset({"screen_dropout"})

_orig_uni = None
_orig_exit = None


def _as_bool(df: pd.DataFrame) -> pd.DataFrame:
    return df.fillna(False).astype(bool)


def _rank_bottom(val: pd.DataFrame, pct: float) -> pd.DataFrame:
    """池内横截面**后** pct%(小的那一端)。★ 算不出的格子判不合格。"""
    r = val.rank(axis=1, pct=True, na_option="keep")
    return _as_bool(val.notna() & (r <= pct / 100.0))


def _uni(rule: dict, syms: list[str], index: pd.DatetimeIndex) -> pd.DataFrame:
    t = rule.get("type")
    p = rule.get("params", {}) or {}
    if t not in _UNIVERSE_TYPES:
        return _orig_uni(rule, syms, index)

    if t == "pb_below":
        _note("★ pb_below 已挂钩:P/B = 收盘价 / 每股净资产"
              "(每股净资产 = StockholdersEquity / 摊薄股数)。"
              "★★ 阈值 1.0 不是拍的数 —— 「跌破净资产」这四个字本身就是 1.0。"
              "★ 净资产 ≤ 0 的格子判不合格(不判「极度便宜」)。")
        pb = price_ratio("pb", syms)
        return _as_bool(pb.notna() & (pb < float(p["threshold"]))
                        ).reindex(index=index, columns=syms).fillna(False)

    if t == "pe_rank_bottom":
        _note("★ pe_rank_bottom 已挂钩:P/E = 收盘价 / DilutedEPS_ttm,池内后 N%。"
              "★★ EPS ≤ 0 判**不合格** —— 原著的低 PE 组本来就不含亏损股,"
              "★ 把负 PE 排进「最便宜」那一端是口径陷阱。")
        pe = price_ratio("pe", syms)
        return _rank_bottom(pe, float(p["rank_bottom_pct"])
                            ).reindex(index=index, columns=syms).fillna(False)

    if t == "ev_ebit_rank_bottom":
        _note("★ ev_ebit_rank_bottom 已挂钩:EV/EBIT 池内后 N%。"
              "★★ EV 的股权腿 = 摊薄股数 × 收盘价 = **规模代理,不是 PIT 市值**;"
              "★ 净债走补标签后的 LongTermDebtTotal;★ EBIT ≤ 0 判不合格。"
              "★★★ 这一条不需要折旧摊销 —— 它正是「EV/EBITDA 算不出」的替代口径。")
        ee = price_ratio("ev_ebit", syms)
        return _rank_bottom(ee, float(p["rank_bottom_pct"])
                            ).reindex(index=index, columns=syms).fillna(False)

    if t == "magic_formula_rank_top":
        _note("★ magic_formula_rank_top 已挂钩:两个排名之和取前 N%。"
              "★★ ROC 的净固定资产是**派生式**(TotalAssets − CurrentAssets − 无形+商誉),"
              "★★★ 分母系统性偏大 → ROC 系统性偏低,★ 标「我们算的」。")
        roc = get("roc_greenblatt", syms)
        ee = price_ratio("ev_ebit", syms)
        r1 = roc.rank(axis=1, pct=True, ascending=False, na_option="keep")
        r2 = ee.rank(axis=1, pct=True, ascending=True, na_option="keep")
        both = roc.notna() & ee.notna()
        comb = (r1 + r2).where(both)
        rr = comb.rank(axis=1, pct=True, na_option="keep")
        keep = both & (rr <= float(p["rank_top_pct"]) / 100.0)
        return _as_bool(keep).reindex(index=index, columns=syms).fillna(False)

    if t == "share_count_declining":
        _note("★ share_count_declining 已挂钩:摊薄股数同比变化 < 0。"
              "★★ 这是**符号条件**,不含阈值 —— ★ 「大量回购」那个阈值原著没给,"
              "★★★ 本轮没有拍它,所以跑的是**无自由参数子集**,不是基-12 整条。")
        y = get("shares_yoy_pct", syms)
        return _as_bool(y.notna() & (y < 0.0)
                        ).reindex(index=index, columns=syms).fillna(False)

    if t == "fcf_positive":
        _note("★ fcf_positive 已挂钩:FCF_ttm = OCF_ttm − 资本开支_ttm > 0。"
              "★ 资本开支主用 PPE、缺的回落到 ProductiveAssets"
              "(和 engine/fundamentals.py:_capex 同一口径)。")
        f = get("fcf_ttm_local", syms)
        return _as_bool(f.notna() & (f > 0.0)
                        ).reindex(index=index, columns=syms).fillna(False)

    raise AssertionError(t)


# ══════════════════════════════════════════════════════════════════════════
# 四 · 新算子(⑥ 离场):筛选条件不再成立就走
# ══════════════════════════════════════════════════════════════════════════

_SCREEN_CACHE: dict = {}


def set_screen(name: str, mask: pd.DataFrame) -> None:
    """★ 把某条链的 ① universe 掩膜登记进来,供 screen_dropout 用。"""
    _SCREEN_CACHE[name] = mask


def _exit(spec: dict, symbols: list[str]) -> pd.DataFrame:
    rules = list((spec or {}).get("rules") or [])
    mine = [r for r in rules if r.get("type") in _EXIT_TYPES]
    if not mine:
        return _orig_exit(spec, symbols)
    rest = dict(spec or {})
    rest["rules"] = [r for r in rules if r.get("type") not in _EXIT_TYPES]
    out = _orig_exit(rest, symbols)
    for r in mine:
        nm = (r.get("params") or {}).get("screen")
        m = _SCREEN_CACHE.get(nm)
        if m is None:
            raise KeyError(
                f"★★★ screen_dropout 要的筛选掩膜 {nm!r} 没登记 —— "
                f"★ 没有悄悄当成「从不离场」。登记用 ops_fund_1030.set_screen()。")
        drop = ~_as_bool(m.reindex(index=out.index, columns=out.columns).fillna(False))
        out = out | drop
        _note("★ screen_dropout 已挂钩:**筛选条件不再成立的那天收盘就走**。"
              "★★ 这是这几条机械底仓方法唯一**不含自由参数**的离场读法 —— "
              "★★★ 原著的再平衡频率(一年一次?)方法卡没给,"
              "★ 本轮没有拍它,已列进要问 Gemini 的清单。")
    return out


# ══════════════════════════════════════════════════════════════════════════
# 五 · install
# ══════════════════════════════════════════════════════════════════════════

def install(with_operating_income: bool = False,
            source: str = "sec_table", reported_only: bool = False) -> None:
    """★ source = "sec_table"(★★★ 默认,数据组那份)/ "my_backfill"(我上一轮那份)。

    ★★ 两份都留着的理由:★★★ 交叉校验。实测 6,961 个重叠期里 **98.85% 完全一致**,
      ★ 只有 50 期(15 只)差超 5% —— ★★ 而那 50 期里 38 期用的是
      `noncurrent_incl_capital_lease`(含融资租赁 → 口径差,不是错)。
    ★★★ 两边各自的真问题也对出来了,见报告 §二-B。
    """
    global _orig_uni, _orig_exit
    if source == "sec_table":
        install_sec_overlay(reported_only=reported_only)
    elif source == "my_backfill":
        install_overlay(with_operating_income)
    else:
        raise ValueError(f"★ source 只认 sec_table / my_backfill,给的是 {source!r}")
    if _orig_uni is None:
        # ★ 派发器的真名是 `_universe_rule_mask`(带下划线)——
        #   ★★ 「同一样东西两种写法」又一例:我第一版写的是 `universe_rule_matrix`,
        #   那个名字**不存在**,挂上去不会报错、只是没挂上 → 静默失效。
        #   ★ 照 ops_q57_1030.py:437 的写法改正。
        _orig_uni = matrices._universe_rule_mask
        matrices._universe_rule_mask = _uni
    if _orig_exit is None:
        _orig_exit = matrices.exit_signal_matrix
        matrices.exit_signal_matrix = _exit
    config_adapter.IMPLEMENTED["universe"] |= _UNIVERSE_TYPES
    config_adapter.IMPLEMENTED["exit"] |= _EXIT_TYPES
    _note("★★★ 基本面新算子已挂钩(运行时):① 六条 + ⑥ 一条。"
          "★ engine/matrices.py · chain.py · config_adapter.py 一个字符没改。")


def diagnostics() -> dict:
    return {"算子备注": notes()}
