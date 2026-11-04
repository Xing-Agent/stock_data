#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 扩库全跑(1104)的覆盖层 —— 8 条新策略要用的算子,全部新建在 probe/ 下

三秒版(大白话):
  这个文件只干一件事:★ 把这一轮 8 条策略要用的「筛选条件」做成 engine 认得的
  零件,★★ 然后在**运行时**挂到 engine 上去 —— ★★★ engine/ 下一个字节都不改。

══════════════════════════════════════════════════════════════════════════
★★★ 本文件的四条自律(照 probe/fundamental_buildout_1030/ops_fund_1030.py 的套路)
══════════════════════════════════════════════════════════════════════════
  ① **只读 engine,不改 engine**:只替换两个派发函数
     (`matrices._universe_rule_mask` / `matrices.exit_signal_matrix`),
     ★ 不认的规则一律原样回传给 engine 原函数。
  ② ★★★ **这一轮一个数据覆盖层都不挂。** —— ★ 和 1030 那一轮不同:
     那一轮换了 EBIT / 长期负债两列;★★ 本轮用到的科目**老库里本来就有**,
     所以 `data.load_fundamentals` **原封不动**。
     → ★★★ 本轮结果里没有任何「换源」造成的差异,这是代码上可查的。
  ③ ★★★ **算不出来就是 NaN,一律判不合格** —— ★ 不用近似值、默认值、
     历史值顶替。★★ 唯一一处「缺了按 0 算」是**明确禁止**的:
     本文件里没有任何 `fillna(0)` 用在**科目值**上(只用在布尔掩膜上)。
  ④ **口径归属如实标**:每个算子的 `_note()` 里写清它是**原著**还是**我们的**。

══════════════════════════════════════════════════════════════════════════
★★ 市值口径(本轮全部横截面比值的分母)
══════════════════════════════════════════════════════════════════════════
  市值 = 收盘价 × 摊薄股数(过完 engine 三道股数闸)
  ★★★ 这是**规模代理,不是 PIT 市值** —— ★ 和 ops_fund_1030 的 EV 股权腿
    同一个口径,★★ 本轮沿用,并在报告里照实标。
"""
from __future__ import annotations

import functools
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import (cache, config_adapter, data,  # noqa: E402
                    fundamentals, matrices)

_notes: list[str] = []


def notes() -> list[str]:
    return list(_notes)


def _note(s: str) -> None:
    if s not in _notes:
        _notes.append(s)


# ══════════════════════════════════════════════════════════════════════════
# 一 · 季度级原始科目(★ 只取本轮要用的,一个不多)
# ══════════════════════════════════════════════════════════════════════════
#
# ★ kind: "ttm" = 流量科目(YTD 差分还原后滚 4 季,走 engine 坑③)
#         "pt"  = 存量科目(资产负债表余额,不滚)
_COLS = {
    "ta":     ("TotalAssets", "pt"),
    "ca":     ("CurrentAssets", "pt"),
    "liab":   ("Liabilities", "pt"),
    "eq":     ("StockholdersEquity", "pt"),
    "inv":    ("InventoryNet", "pt"),
    "cash":   ("CashAndCashEquivalentsAtCarryingValue", "pt"),
    "rev":    ("Revenue", "ttm"),
    "cor":    ("CostOfRevenue", "ttm"),
    "ni":     ("NetIncome", "ttm"),
    "ocf":    ("OperatingCashFlow", "ttm"),
    "eps":    ("DilutedEPS", "ttm"),
    "buyback": ("PaymentsForRepurchaseOfCommonStock", "ttm"),
    "div":    ("PaymentsOfDividends", "ttm"),
    "divc":   ("PaymentsOfDividendsCommonStock", "ttm"),
    "issue":  ("ProceedsFromIssuanceOfCommonStock", "ttm"),
}


@functools.lru_cache(maxsize=4096)
def frame(symbol: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(值表, 生效日表),索引 = period_end。★ 照 ops_fund_1030.frame 的套路。"""
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
    v = pd.DataFrame({k: pd.Series(x, dtype=float)
                      for k, x in cols.items()}).reindex(idx)
    # ★★ 照 ops_fund_1030 踩过的坑:生效日每一列强制 datetime64,
    #   否则全 NaN 的列是 float64,.max(axis=1) 会在 float 和 Timestamp 间比大小
    e = pd.DataFrame({k: pd.to_datetime(pd.Series(x), errors="coerce")
                      for k, x in effs.items()}).reindex(idx)
    for c in e.columns:
        e[c] = pd.to_datetime(e[c], errors="coerce")
    v.index = pd.DatetimeIndex(idx)
    e.index = pd.DatetimeIndex(idx)
    return v, e


def _yoy(x: pd.Series) -> pd.Series:
    """同比变化率。★ 4 个季度前;★★ 基期 ≤ 0 的一律 NaN(不猜方向)。"""
    base = x.shift(4)
    return ((x / base) - 1.0).where(x.notna() & (base > 0))


def _dividends(v: pd.DataFrame) -> pd.Series:
    """★★★ 分红口径 —— 这是预言一里登记为「不确定」的那一项。

    ★ 做法:`PaymentsOfDividends`(全部分红,含优先股)**优先**;
      ★★ 它缺的期用 `PaymentsOfDividendsCommonStock`(普通股分红)补。
    ★★★ **不相加** —— 两个科目有重叠语义(后者是前者的子集),
      相加等于把同一笔分红算两遍。
    ★ 两个都没有 → NaN = 算不出来,★★ 不按 0 算。
      理由:「没报分红科目」和「真的不分红」在这份库里**分不开**,
      ★★★ 按 0 算会把「缺数据」变成「数据错」(把缺数据的公司
      误判成「不回报股东」,从而把它排到最差那一端)。
    """
    d = v["div"].copy()
    m = d.isna() & v["divc"].notna()
    d[m] = v["divc"][m]
    return d


def metric_q(symbol: str, name: str) -> tuple[pd.Series, pd.Series]:
    """季度级派生指标(不含价格的那一半)。★ 算不出就是 NaN,不猜不补。"""
    v, e = frame(symbol)
    if v.empty:
        return pd.Series(dtype=float), pd.Series(dtype="datetime64[ns]")

    def eff(cols: list[str]) -> pd.Series:
        return e[cols].max(axis=1)

    # ---------------- ① Sloan 应计(★★ 现金流量表法 = 我们的版本)
    if name == "accrual_cf_avg_ta":
        # ★★ 应计 = (净利润 − 经营现金流) ÷ **平均总资产**
        #   ★ 平均总资产 = (本期总资产 + 4 季前总资产) / 2
        #   ★★★ 出处:Hribar & Collins (2002, JAR) 的现金流量表法
        #     —— ★ 这是**后人的改法**,不是 Sloan (1996) 原著的资产负债表法。
        #   ★ 「÷ 平均总资产」这一处按预先登记的原著口径(原著用平均总资产)。
        ta_prev = v["ta"].shift(4)
        avg_ta = (v["ta"] + ta_prev) / 2.0
        ok = v["ni"].notna() & v["ocf"].notna() & (avg_ta > 0)
        return ((v["ni"] - v["ocf"]) / avg_ta.where(avg_ta > 0)).where(ok), \
            eff(["ni", "ocf", "ta"])

    # ---------------- ② 资产扩张
    if name == "asset_growth_yoy":
        # ★ 原著版(Cooper/Gulen/Schill 2008):总资产同比增速
        return _yoy(v["ta"]), eff(["ta"])

    if name == "operating_asset_growth_yoy":
        # ★★★ 我们的版本,★ 而且是**口径降级版** —— 必须照实标:
        #   预先登记写的是「净经营资产」,★★ 但真正的净经营资产要把
        #   **经营负债**从总负债里剔出来(= 总负债 − 全部有息负债),
        #   ★★★ 而有息负债那几个科目在老库里覆盖率都残缺
        #     (长期负债 56.0% / 长期负债当期 59.2% / 短期借款 35.2% /
        #      一年内到期债务 19.2%),★ 四个还互为补充、谁盖谁说不清。
        #   → ★★★ 所以这里跑的是**经营资产(= 总资产 − 现金)增速**,
        #     ★ 真正的「净经营资产增速」本轮记为**算不出来**,
        #     ★★ 缺的是「有息负债科目」。★★★ 两者不混成一个数。
        oa = v["ta"] - v["cash"]
        ok = v["ta"].notna() & v["cash"].notna()
        return _yoy(oa.where(ok)), eff(["ta", "cash"])

    # ---------------- ⑤ 存货异常
    if name == "inventory_abnormal":
        # ★ 存货增速 − 收入增速。★★ 两个都算得出才算(缺一个 = NaN)
        gi, gr = _yoy(v["inv"]), _yoy(v["rev"])
        return (gi - gr).where(gi.notna() & gr.notna()), \
            eff(["inv", "rev"])

    # ---------------- ⑥ 毛利质量(Novy-Marx 2013)
    if name == "gross_profitability_ta":
        # ★ 原著版:毛利 ÷ 总资产;毛利 = 收入 − 营业成本(TTM)
        gp = v["rev"] - v["cor"]
        ok = v["rev"].notna() & v["cor"].notna() & (v["ta"] > 0)
        return (gp / v["ta"].where(v["ta"] > 0)).where(ok), \
            eff(["rev", "cor", "ta"])

    if name == "gross_profitability_avg_ta":
        # ★★ 我们的版本:分母换成**平均总资产**(只改这一处)
        gp = v["rev"] - v["cor"]
        avg_ta = (v["ta"] + v["ta"].shift(4)) / 2.0
        ok = v["rev"].notna() & v["cor"].notna() & (avg_ta > 0)
        return (gp / avg_ta.where(avg_ta > 0)).where(ok), \
            eff(["rev", "cor", "ta"])

    # ---------------- ⑧ 盈利加速(融合面,★★★ 我们组合的)
    if name == "earnings_acceleration":
        # ★★ 「加速」= 本期同比增速 > 上一期同比增速,★ 收入和每股收益**都要**。
        #   ★★★ 这是**符号条件,没有阈值** —— ★ 原书那个「20% 以上」
        #     本轮**没有拍**(出处还没回原文核,见《18》第 3 条),
        #     ★★ 所以跑的是无自由参数的「加速」读法,不是原书整条。
        gr, ge = _yoy(v["rev"]), _yoy(v["eps"])
        acc = ((gr > gr.shift(1)) & (ge > ge.shift(1))).astype(float)
        ok = (gr.notna() & gr.shift(1).notna()
              & ge.notna() & ge.shift(1).notna())
        return acc.where(ok), eff(["rev", "eps"])

    # ---------------- 分子/分母要配价格的,先把「不含价格的那一半」给出来
    if name == "ncav":
        # ④ Net-Net:净流动资产 = 流动资产 − **全部负债**
        #   ★★★ 出处:《聪明的投资者》1949 版 —— ★ 流动资产减**全部**负债,
        #     不是只减流动负债。
        ok = v["ca"].notna() & v["liab"].notna()
        return (v["ca"] - v["liab"]).where(ok), eff(["ca", "liab"])

    if name == "equity":
        return v["eq"], eff(["eq"])
    if name == "ocf_ttm":
        return v["ocf"], eff(["ocf"])
    if name == "ni_ttm":
        return v["ni"], eff(["ni"])
    if name == "shares_q":
        return v["sh"], eff(["sh"])

    if name == "net_shareholder_payout":
        # ⑦ 股东回报的分子 = 回购 + 分红 − 增发(★ 三项全是正数口径:
        #   实测 PaymentsFor... / PaymentsOf... 99.9% 是正值 = 付出去的现金)
        # ★★★ **三项必须全有**才算得出 —— ★ 缺一项 = NaN。
        #   ★★ 这一条是本轮可算率最低的,照实报,不放宽。
        d = _dividends(v)
        ok = v["buyback"].notna() & d.notna() & v["issue"].notna()
        return (v["buyback"] + d - v["issue"]).where(ok), \
            eff(["buyback", "div", "divc", "issue"])

    raise KeyError(f"派生指标 {name} 没实现 —— ★ 没有悄悄返回 NaN")


@functools.lru_cache(maxsize=64)
def _panel(name: str, symbols: tuple[str, ...]) -> pd.DataFrame:
    cal = data.trading_calendar()
    cols = {}
    for s in symbols:
        # ★ 故意不包 try:算不出必须是「数据不够」,不许是「我们的代码抛了被吞掉」
        vv, ee = metric_q(s, name)
        cols[s] = fundamentals._to_daily(vv, ee, cal)
    return pd.DataFrame(cols, index=cal)


def get(name: str, symbols: list[str]) -> pd.DataFrame:
    return _panel(name, tuple(symbols))


def mktcap(symbols: list[str]) -> pd.DataFrame:
    """★★ 规模代理 = 收盘价 × 摊薄股数。★★★ 不是 PIT 市值,报告里照实标。"""
    close = cache.field("close", symbols)
    sh = get("shares_q", symbols).reindex_like(close)
    mc = close * sh
    return mc.where(mc > 0)


# ══════════════════════════════════════════════════════════════════════════
# 二 · ★★ SIC 行业码(按时点取,★★★ 不许用最新版本回填历史)
# ══════════════════════════════════════════════════════════════════════════

@functools.lru_cache(maxsize=1)
def _sic_daily_all() -> dict[str, pd.Series]:
    """每只票一条日频 SIC 码序列。

    ★★★ PIT 口径:用每个版本的 `observed_from`(= SEC 第一次这么披露的时间),
      ★ 再走 engine 的 `effective_date()` 推到**下一个交易日**才生效
      —— 和财报 filing+1 同一条规矩。
    ★★ 第一个版本生效**之前**是 NaN —— ★★★ 绝不拿后来的版本回填历史
      (那就是偷看未来的行业归属)。
    """
    man = data.load_manifest()
    cal = data.trading_calendar()
    out: dict[str, pd.Series] = {}
    for sym, meta in man.items():
        if not meta.fundamentals_path:
            continue
        try:
            with open(meta.fundamentals_path, encoding="utf-8") as fh:
                raw = json.load(fh)
        except OSError:
            continue
        vers = raw.get("sic_versions") or []
        recs = []
        for r in vers:
            ts = r.get("observed_from") or r.get("accepted_at")
            code = r.get("sic_code")
            if not ts or not code:
                continue
            e = fundamentals.effective_date(pd.Timestamp(ts).tz_localize(None))
            if e is None:
                continue
            try:
                recs.append((e, int(str(code).strip())))
            except ValueError:
                continue
        if not recs:
            continue
        recs.sort(key=lambda x: x[0])
        ser = pd.Series(np.nan, index=cal, dtype=float)
        arr = cal.to_numpy()
        for e, code in recs:
            pos = int(np.searchsorted(arr, np.datetime64(e), side="left"))
            if pos < len(cal):
                ser.iloc[pos] = float(code)
        out[sym] = ser.ffill()
    return out


def sic_panel(symbols: list[str]) -> pd.DataFrame:
    allsic = _sic_daily_all()
    cal = data.trading_calendar()
    return pd.DataFrame({s: allsic.get(s, pd.Series(np.nan, index=cal))
                         for s in symbols}, index=cal)


def sic_in_ranges(symbols: list[str],
                  ranges: list[list[int]]) -> pd.DataFrame:
    """★ 行业闸:SIC 落在给定区间内 = 合格。★★ 没有 SIC = 不合格(不放行)。"""
    p = sic_panel(symbols)
    ok = pd.DataFrame(False, index=p.index, columns=p.columns)
    for lo, hi in ranges:
        ok = ok | ((p >= float(lo)) & (p <= float(hi)))
    return ok & p.notna()


# ══════════════════════════════════════════════════════════════════════════
# 三 · 横截面分位工具
# ══════════════════════════════════════════════════════════════════════════

def _as_bool(df: pd.DataFrame) -> pd.DataFrame:
    return df.fillna(False).astype(bool)


def _rank_bottom(val: pd.DataFrame, pct: float) -> pd.DataFrame:
    """池内横截面**最小**的 pct%。★ 算不出的格子判不合格。"""
    r = val.rank(axis=1, pct=True, na_option="keep")
    return _as_bool(val.notna() & (r <= pct / 100.0))


def _rank_top(val: pd.DataFrame, pct: float) -> pd.DataFrame:
    """池内横截面**最大**的 pct%。★ 算不出的格子判不合格。"""
    r = val.rank(axis=1, pct=True, na_option="keep")
    return _as_bool(val.notna() & (r >= 1.0 - pct / 100.0))


# ---------------------------------------------------------------- 各条的「分数」

def score(name: str, syms: list[str]) -> pd.DataFrame:
    """把每一条的横截面打分面板算出来(★ 日频,★★ 算不出 = NaN)。"""
    if name == "accrual_cf":
        return get("accrual_cf_avg_ta", syms)
    if name == "asset_growth":
        return get("asset_growth_yoy", syms)
    if name == "operating_asset_growth":
        return get("operating_asset_growth_yoy", syms)
    if name == "inventory_abnormal":
        return get("inventory_abnormal", syms)
    if name == "gp_ta":
        return get("gross_profitability_ta", syms)
    if name == "gp_avg_ta":
        return get("gross_profitability_avg_ta", syms)

    mc = mktcap(syms)
    if name == "lsv_bm":
        return (get("equity", syms).reindex_like(mc) / mc)
    if name == "lsv_cp":
        return (get("ocf_ttm", syms).reindex_like(mc) / mc)
    if name == "lsv_ep":
        return (get("ni_ttm", syms).reindex_like(mc) / mc)
    if name == "shareholder_yield":
        return (get("net_shareholder_payout", syms).reindex_like(mc) / mc)
    if name == "netnav_ratio":
        # ★ 市值 ÷ 净流动资产。★★ 净流动资产 ≤ 0 的格子 NaN(判不合格)——
        #   ★★★ 负的净流动资产会让比值变负、排到「最便宜」那一端,那是口径陷阱。
        nc = get("ncav", syms).reindex_like(mc)
        return mc / nc.where(nc > 0)
    raise KeyError(name)


# ══════════════════════════════════════════════════════════════════════════
# 四 · ① universe 新算子
# ══════════════════════════════════════════════════════════════════════════

_UNIVERSE_TYPES = frozenset({
    "accrual_cf_decile_bottom",
    "asset_growth_decile_bottom",
    "operating_asset_growth_decile_bottom",
    "lsv_single_decile_cheapest",
    "lsv_rank_median_decile_cheapest",
    "netnav_discount_below",
    "inventory_abnormal_decile_bottom",
    "gross_profitability_quintile_top",
    "shareholder_yield_rank_top",
    "shareholder_yield_minus_asset_growth_rank_top",
    "earnings_acceleration",
    "sic_industry_in",
})
_EXIT_TYPES = frozenset({"screen_dropout"})

_orig_uni = None
_orig_exit = None

_LSV_KEY = {"bm": "lsv_bm", "cp": "lsv_cp", "ep": "lsv_ep"}


def _uni(rule: dict, syms: list[str],
         index: pd.DatetimeIndex) -> pd.DataFrame:    # noqa: C901
    t = rule.get("type")
    p = rule.get("params", {}) or {}
    if t not in _UNIVERSE_TYPES:
        return _orig_uni(rule, syms, index)

    def fin(df: pd.DataFrame) -> pd.DataFrame:
        return _as_bool(df).reindex(index=index, columns=syms).fillna(False)

    if t == "accrual_cf_decile_bottom":
        _note("★ accrual_cf_decile_bottom:应计 =(净利润 − 经营现金流)÷ 平均总资产,"
              "池内**十分位最低**那一档。★★★ 归属 = **我们的版本(行业改进)** —— "
              "现金流量表法出自 Hribar & Collins (2002),不是 Sloan (1996) 原著的"
              "资产负债表法。★ 原著版见报告「算不出来」那一列。")
        return fin(_rank_bottom(score("accrual_cf", syms),
                                float(p["decile_pct"])))

    if t == "asset_growth_decile_bottom":
        _note("★ asset_growth_decile_bottom:总资产同比增速,池内**十分位最低**。"
              "★★ 归属 = **原著版**(Cooper/Gulen/Schill 2008 的资产增长效应)——"
              "★ 只用总资产一个科目,一个数没添。")
        return fin(_rank_bottom(score("asset_growth", syms),
                                float(p["decile_pct"])))

    if t == "operating_asset_growth_decile_bottom":
        _note("★★★ operating_asset_growth_decile_bottom:**经营资产(总资产 − 现金)**"
              "同比增速,池内十分位最低。★★ 归属 = **我们的版本,且是口径降级版** —— "
              "★ 预先登记写的是「净经营资产」,但真正的净经营资产要剔经营负债,"
              "而有息负债科目在老库里覆盖率残缺(56.0%/59.2%/35.2%/19.2%,四个互补)"
              "→ ★★★ 真口径记为**算不出来**,跑的是这个降级口径,两者不混。")
        return fin(_rank_bottom(score("operating_asset_growth", syms),
                                float(p["decile_pct"])))

    if t == "lsv_single_decile_cheapest":
        ind = str(p["indicator"]).lower()
        _note(f"★ lsv_single_decile_cheapest(indicator={ind}):**单指标**十分位,"
              "买最便宜那一档。★★★ 归属 = **原著版**(LSV 1994)—— "
              "★ 原著明确是**各跑一次、不合成分数**,所以三个指标是三条独立的臂。"
              "★★ 比值一律写成「收益/价格」形式(账面/市值 · 现金流/市值 · 盈利/市值),"
              "这样负的分子自然排到**最贵**那一端 —— ★★★ 不会掉进「负 PE 最便宜」的陷阱。")
        return fin(_rank_top(score(_LSV_KEY[ind], syms),
                             float(p["decile_pct"])))

    if t == "lsv_rank_median_decile_cheapest":
        _note("★★ lsv_rank_median_decile_cheapest:三个指标各自的池内名次,**取中位数**,"
              "再取最便宜的十分位。★★★ 归属 = **我们的版本** —— "
              "★ 原著明确没有合成分数,这一处是我们加的(只改这一处)。"
              "★★ 三个指标必须**都算得出**才给名次(缺一个 = 这格不合格)。")
        parts = [score(k, syms) for k in ("lsv_bm", "lsv_cp", "lsv_ep")]
        ranks = [x.rank(axis=1, pct=True, na_option="keep") for x in parts]
        both = parts[0].notna() & parts[1].notna() & parts[2].notna()
        # ★ 第一版用的是 `stack(dropna=False)` → ★★ 这个 pandas 版本直接 ValueError
        #   (★★★ 好在它是**报错**,不是悄悄给个错数 —— 3 个格子跑挂、已登记)。
        #   ★ 改成逐格取三个名次的中位数,★★ 口径一字没变。
        med = pd.DataFrame(
            np.median(np.stack([r.to_numpy(dtype=float) for r in ranks]), axis=0),
            index=ranks[0].index, columns=ranks[0].columns)
        med = med.where(both)
        return fin(_rank_top(med, float(p["decile_pct"])))

    if t == "netnav_discount_below":
        _note("★ netnav_discount_below:市值 ÷ 净流动资产 < 门槛。"
              "★★ 净流动资产 = 流动资产 − **全部负债**"
              "(★★★ 出处《聪明的投资者》**1949 版**,不是 1934)。"
              "★ 净流动资产 ≤ 0 判不合格。"
              "★★ 市值 = 收盘价 × 摊薄股数 = **规模代理,不是 PIT 市值**。")
        r = score("netnav_ratio", syms)
        return fin(r.notna() & (r < float(p["max_ratio"])))

    if t == "inventory_abnormal_decile_bottom":
        _note("★ inventory_abnormal_decile_bottom:(存货同比增速 − 收入同比增速),"
              "池内**十分位最低**。★★ 归属 = **原著版**。"
              "★★★ 服务业本来就没有存货 → 这些票是**算不出来**,"
              "不是「分数差」,两者分开记。")
        return fin(_rank_bottom(score("inventory_abnormal", syms),
                                float(p["decile_pct"])))

    if t == "sic_industry_in":
        _note("★★ sic_industry_in:SIC 行业闸,**按时点取**"
              "(每个版本用 observed_from + 1 个交易日生效,"
              "★★★ 第一版生效之前是 NaN —— 绝不拿最新版本回填历史)。"
              "★ 归属 = **我们的版本**(第 5 条的那一处改动)。"
              "★★ 没有 SIC 的票判**不合格**(不放行)。")
        return fin(sic_in_ranges(syms, [list(x) for x in p["sic_ranges"]]))

    if t == "gross_profitability_quintile_top":
        den = str(p.get("denominator", "total_assets"))
        key = "gp_ta" if den == "total_assets" else "gp_avg_ta"
        _note(f"★ gross_profitability_quintile_top(denominator={den}):"
              "毛利 ÷ 总资产(毛利 = 收入 − 营业成本,TTM),"
              "池内**五分位最高**那一档。"
              "★★★ 原著是**五分位**(不是十分位),而且买的是**毛利率最高**那一端"
              "(Novy-Marx 2013 的毛利率溢价)。"
              "★★ denominator=total_assets 是**原著版**;"
              "avg_total_assets 是**我们的版本**(只改这一处)。")
        return fin(_rank_top(score(key, syms), float(p["quintile_pct"])))

    if t == "shareholder_yield_rank_top":
        _note("★ shareholder_yield_rank_top:(回购 + 分红 − 增发)÷ 市值,"
              "池内排名**最高** N%。★★ 归属 = **原著版**。"
              "★★★ 三项**必须全有**才算得出,缺一项 = 算不出来 —— "
              "★ 不按 0 补(「没报这个科目」和「真的没有」在这份库里分不开)。"
              "★★ 分红口径:PaymentsOfDividends 优先、缺的用 "
              "PaymentsOfDividendsCommonStock 补,★★★ **不相加**(会算两遍)。")
        return fin(_rank_top(score("shareholder_yield", syms),
                             float(p["rank_top_pct"])))

    if t == "shareholder_yield_minus_asset_growth_rank_top":
        _note("★★ shareholder_yield_minus_asset_growth_rank_top:"
              "股东回报率 − 总资产同比增速,池内排名最高 N%。"
              "★★★ 归属 = **我们的版本**(「资产扩张惩罚」是我们合并出来的新形状,"
              "★ 原著没有这一项)。★★ 两项都要算得出。")
        sy = score("shareholder_yield", syms)
        ag = score("asset_growth", syms).reindex_like(sy)
        comb = (sy - ag).where(sy.notna() & ag.notna())
        return fin(_rank_top(comb, float(p["rank_top_pct"])))

    if t == "earnings_acceleration":
        _note("★★ earnings_acceleration:收入同比增速和每股收益同比增速"
              "**两个都在往上走**(本期同比 > 上期同比)。"
              "★★★ 这是**符号条件、没有阈值** —— ★ 原书那个「20% 以上」"
              "本轮**没有拍**(出处还没回原文核),所以跑的是无自由参数读法。"
              "★ 归属 = **我们组合的**(融合条目,没有单一原著)。")
        a = get("earnings_acceleration", syms)
        return fin(a.notna() & (a > 0.5))

    raise AssertionError(t)


# ══════════════════════════════════════════════════════════════════════════
# 五 · ⑥ 离场:筛选条件不再成立就走(★ 唯一不含自由参数的读法)
# ══════════════════════════════════════════════════════════════════════════

_SCREEN_CACHE: dict = {}


def set_screen(name: str, mask: pd.DataFrame) -> None:
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
                f"★ 没有悄悄当成「从不离场」。用 ops_expand_1104.set_screen() 登记。")
        drop = ~_as_bool(m.reindex(index=out.index,
                                   columns=out.columns).fillna(False))
        out = out | drop
    _note("★ screen_dropout:**筛选条件不再成立的那天收盘就走**。"
          "★★ 这是这几条机械筛选方法唯一**不含自由参数**的离场读法 —— "
          "★★★ 原著的再平衡频率(一年一次?)方法卡没给,本轮没有拍它。")
    return out


# ══════════════════════════════════════════════════════════════════════════
# 六 · install
# ══════════════════════════════════════════════════════════════════════════

def install() -> None:
    """★★★ 运行时挂钩。★ 幂等。★★ 不挂任何数据覆盖层(本轮不需要)。"""
    global _orig_uni, _orig_exit
    if _orig_uni is None:
        # ★ 派发器真名是 `_universe_rule_mask`(带下划线)——
        #   ★★ ops_fund_1030 踩过的坑:写错名字不会报错,只是静默没挂上。
        _orig_uni = matrices._universe_rule_mask
        matrices._universe_rule_mask = _uni
    if _orig_exit is None:
        _orig_exit = matrices.exit_signal_matrix
        matrices.exit_signal_matrix = _exit
    config_adapter.IMPLEMENTED["universe"] |= _UNIVERSE_TYPES
    config_adapter.IMPLEMENTED["exit"] |= _EXIT_TYPES
    _note("★★★ 扩库 1104 新算子已挂钩(运行时):① 十二个 + ⑥ 一个。"
          "★ engine/matrices.py · chain.py · config_adapter.py · data.py · "
          "fundamentals.py **一个字节没改**。"
          "★★★ 本轮**没挂任何数据覆盖层** —— data.load_fundamentals 原封不动。")


def diagnostics() -> dict:
    return {"算子备注": notes()}
