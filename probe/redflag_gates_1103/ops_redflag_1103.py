#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 四道「财务排雷否决闸」的算子 —— 2026-11-03

══════════════════════════════════════════════════════════════════════════
★★★ 三秒版:这个文件只负责「把四道排雷闸算成一个数」。
     不数个数、不做交集、不写报告 —— 那些在 run_redflag_gates_1103.py 里。
══════════════════════════════════════════════════════════════════════════

★ 四道闸(阈值一个都没自己拍,全部照任务单给的原文):
    ① 利息覆盖不足   EBIT ÷ 利息费用 < 1                    Asquith 等 1994
    ② 利润现金流背离 (净利润 − 经营现金流) ÷ 总资产,截面最高 10%  Sloan 1996
    ③ 破产概率       Zmijewski 三变量,概率 > 50%            Zmijewski 1984
    ④ 造假概率       Beneish 八变量 M-Score > −1.78          Beneish 1999

★★★ ③ 的那个坑:Zmijewski 第二个变量是「**总负债** ÷ 总资产」
    (us-gaap:Liabilities ÷ TotalAssets),★ 不是「总**债务**(有息负债)÷ 总资产」。
    本文件用的是 `liab`(= Liabilities 科目),没有用 _debt() 那种有息负债口径。

★ 纪律:
  · engine/ 一个字符都没改。PIT 全部**原封不动复用** engine/fundamentals.py 的
    `ttm()` / `quarterly()` / `_to_daily()`(申报日+1 交易日生效 / YTD 差分还原单季 /
    TTM 四季连续 / 同一期只留首发版本)。
  · 自己只建了一张科目对齐表(照 probe/masters_57_1030/ops_q57_1030.py 的骨架),
    ★ 理由和那边一样:动 engine 的 _QCOLS 等于动已有结论的口径。

★★ 「年同比」在季度数据上怎么读:Beneish / Zmijewski 原著都是**年度**数据。
   我们只有季度 PIT,所以 t−1 年一律机械地取 **shift(4) 个季度**
   (流量用 TTM 的 shift(4),存量用 period_end 的 shift(4))。
   ★ 这是我们的机械读法,不是原著原文,报告里必须留痕。
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

from engine import data, fundamentals as F        # noqa: E402

_NOTES: list[str] = []


def notes() -> list[str]:
    return list(_NOTES)


def _note(s: str) -> None:
    if s not in _NOTES:
        _NOTES.append(s)


# ══════════════════════════════════════════════════════════════════════════
# 一 · 科目对齐表
# ══════════════════════════════════════════════════════════════════════════
#: ★ SG&A 的「旁路」科目名 —— 不在 financial_versions 里,见下面 SGA_RAW_KEY 一节
SGA_SYNTH = "SGA_FROM_RAWTAGS"

_COLS = {
    # 流量(TTM)
    "ebit": ("EBIT", "ttm"),
    "intexp": ("InterestExpense", "ttm"),
    "ni": ("NetIncome", "ttm"),
    "ocf": ("OperatingCashFlow", "ttm"),
    "rev": ("Revenue", "ttm"),
    "cor": ("CostOfRevenue", "ttm"),
    "dda1": ("DepreciationDepletionAndAmortization", "ttm"),
    "dda2": ("DepreciationAmortizationAndAccretionNet", "ttm"),
    "sga": (SGA_SYNTH, "ttm"),
    # 存量(period_end 余额)
    "ta": ("TotalAssets", "pt"),
    "liab": ("Liabilities", "pt"),           # ★★★ 总负债 —— Zmijewski 用的是这个
    "ca": ("CurrentAssets", "pt"),
    "cl": ("CurrentLiabilities", "pt"),
    "ltd": ("LongTermDebt", "pt"),
    "ppe": ("PropertyPlantAndEquipmentNet", "pt"),
    "ar": ("AccountsReceivableNetCurrent", "pt"),
}

#: 本模块要从新库里读的 SEC 科目名(给 loader 做裁剪用)
NEEDED_METRICS = {m for m, _k in _COLS.values()}


@functools.lru_cache(maxsize=4096)
def frame(symbol: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(值表, 生效日表),索引 = period_end。★ 走的是 engine 的 ttm/quarterly。"""
    cols, effs = {}, {}
    for name, (metric, kind) in _COLS.items():
        ser = (F.ttm(symbol, metric) if kind == "ttm"
               else F.quarterly(symbol, metric))
        cols[name] = {o.period_end: o.value for o in ser}
        effs[name] = {o.period_end: o.eff for o in ser}
    idx = sorted({pe for d in cols.values() for pe in d})
    if not idx:
        return pd.DataFrame(), pd.DataFrame()
    v = pd.DataFrame({k: pd.Series(x, dtype=float) for k, x in cols.items()}
                     ).reindex(idx)
    # ★★ 照抄 ops_q57_1030 踩过的那个静默空:某科目一条记录都没有时该列 dtype 是
    #    float64(全 NaN),和 datetime64 列混着 .max(axis=1) 会抛 TypeError。
    #    → 生效日表显式强制成 datetime64,一列都不许是 float。
    e = pd.DataFrame({k: pd.to_datetime(pd.Series(x), errors="coerce")
                      for k, x in effs.items()}).reindex(idx)
    for c in e.columns:
        e[c] = pd.to_datetime(e[c], errors="coerce")
    v.index = pd.DatetimeIndex(idx)
    e.index = pd.DatetimeIndex(idx)
    return v, e


def _dda(v: pd.DataFrame) -> pd.Series:
    """折旧摊销:主用 DepreciationDepletionAndAmortization,缺的回落到另一个标签。"""
    d = v["dda1"].copy()
    m = d.isna() & v["dda2"].notna()
    d[m] = v["dda2"][m]
    return d


def _dda_eff(v: pd.DataFrame, e: pd.DataFrame) -> pd.Series:
    d = e["dda1"].copy()
    m = v["dda1"].isna() & v["dda2"].notna()
    d[m] = e["dda2"][m]
    return d


# ══════════════════════════════════════════════════════════════════════════
# 二 · 四道闸的算子
# ══════════════════════════════════════════════════════════════════════════

#: Beneish 1999 八变量的系数 —— 逐字原文
BENEISH_COEF = {
    "const": -4.84, "DSRI": 0.920, "GMI": 0.528, "AQI": 0.404, "SGI": 0.892,
    "DEPI": 0.115, "SGAI": -0.172, "TATA": 4.679, "LVGI": -0.327,
}
BENEISH_THRESHOLD = -1.78

#: Zmijewski 1984 三变量系数 —— 逐字原文
ZMIJEWSKI_COEF = {"const": -4.3, "ROA": -4.5, "LEV": 5.7, "LIQ": -0.004}
ZMIJEWSKI_P_THRESHOLD = 0.50

INTCOV_THRESHOLD = 1.0
SLOAN_TOP_PCT = 0.10          # ★ 截面最高 10%


METRICS = (
    "int_cov",          # ① EBIT ÷ 利息费用
    "sloan_accrual",    # ② (NI − OCF) ÷ TA   —— 原始值,排名在 run 里做
    "zmij_prob",        # ③ Zmijewski 概率
    "m_score",          # ④ Beneish M-Score(八项全齐才给数)
    "m_score_no_sgai",  # ★ 诊断用:八项里除 SGAI 之外的七项是否全齐(1/0)
)


def metric_q(symbol: str, name: str) -> tuple[pd.Series, pd.Series]:
    """算一道闸的季度序列,返回 (值, 生效日)。★ 算不出就是 NaN —— 不猜不补。"""
    v, e = frame(symbol)
    if v.empty:
        return pd.Series(dtype=float), pd.Series(dtype="datetime64[ns]")

    # ------------------------------------------------ ① 利息覆盖 EBIT ÷ 利息费用
    if name == "int_cov":
        # ★ 利息费用 ≤ 0(没有利息支出 / 标签是净利息收入)→ 这道闸**不适用**,
        #   判「算不出」。★ 不按 0 算、不当成「覆盖率无穷大所以通过」—— 那是替它编数。
        ie = v["intexp"].where(v["intexp"] > 0)
        ok = v["ebit"].notna() & ie.notna()
        eff = e[["ebit", "intexp"]].max(axis=1)
        return (v["ebit"] / ie).where(ok), eff

    # ------------------------------------------------ ② Sloan 应计
    if name == "sloan_accrual":
        ta = v["ta"].where(v["ta"] > 0)
        ok = v["ni"].notna() & v["ocf"].notna() & ta.notna()
        eff = e[["ni", "ocf", "ta"]].max(axis=1)
        return ((v["ni"] - v["ocf"]) / ta).where(ok), eff

    # ------------------------------------------------ ③ Zmijewski 1984
    if name == "zmij_prob":
        ta = v["ta"].where(v["ta"] > 0)
        cl = v["cl"].where(v["cl"] > 0)
        roa = v["ni"] / ta
        lev = v["liab"] / ta                 # ★★★ 总负债 ÷ 总资产(不是有息负债)
        liq = v["ca"] / cl
        ok = roa.notna() & lev.notna() & liq.notna()
        x = (ZMIJEWSKI_COEF["const"]
             + ZMIJEWSKI_COEF["ROA"] * roa
             + ZMIJEWSKI_COEF["LEV"] * lev
             + ZMIJEWSKI_COEF["LIQ"] * liq)
        p = 1.0 / (1.0 + np.exp(-x))
        eff = e[["ni", "ta", "liab", "ca", "cl"]].max(axis=1)
        return p.where(ok), eff

    # ------------------------------------------------ ④ Beneish 1999
    if name in ("m_score", "m_score_no_sgai"):
        ta = v["ta"].where(v["ta"] > 0)
        rev = v["rev"].where(v["rev"] > 0)
        cl, ltd = v["cl"], v["ltd"]
        dda = _dda(v)

        def _r(s):           # t−1 年 = shift(4) 个季度(★ 我们的机械读法)
            return s.shift(4)

        # DSRI 应收账款 ÷ 营收 的同比倍数
        ars = v["ar"] / rev
        dsri = ars / _r(ars).where(_r(ars) > 0)
        # GMI 毛利率的「变差倍数」= 去年毛利率 ÷ 今年毛利率
        gm = (v["rev"] - v["cor"]) / rev
        gmi = _r(gm) / gm.where(gm != 0)
        # AQI 「软资产」占比的同比倍数,软资产 = 1 − (流动资产 + 固定资产) ÷ 总资产
        aq = 1.0 - (v["ca"] + v["ppe"]) / ta
        aqi = aq / _r(aq).where(_r(aq) != 0)
        # SGI 营收增长倍数
        sgi = v["rev"] / _r(v["rev"]).where(_r(v["rev"]) > 0)
        # DEPI 折旧率的「变慢倍数」,折旧率 = 折旧 ÷ (折旧 + 固定资产净额)
        dr = dda / (dda + v["ppe"]).where((dda + v["ppe"]) > 0)
        depi = _r(dr) / dr.where(dr > 0)
        # SGAI 销管费用率的同比倍数   ★★★ 这一项靠 SG&A 科目
        sgar = v["sga"] / rev
        sgai = sgar / _r(sgar).where(_r(sgar) > 0)
        # LVGI 杠杆的同比倍数,杠杆 = (流动负债 + 长期负债) ÷ 总资产
        lv = (cl + ltd) / ta
        lvgi = lv / _r(lv).where(_r(lv) > 0)
        # TATA 总应计 ÷ 总资产(原著用「持续经营利润 − 经营现金流」;
        #      ★ 我们库里没有「持续经营利润」这个科目,用 NetIncome —— 留痕)
        tata = (v["ni"] - v["ocf"]) / ta

        seven = [dsri, gmi, aqi, sgi, depi, lvgi, tata]
        avail7 = seven[0].notna()
        for s in seven[1:]:
            avail7 &= s.notna()
        eff_cols = ["ar", "rev", "cor", "ca", "ppe", "ta", "cl", "ltd",
                    "ni", "ocf"]
        eff = pd.concat([e[eff_cols], _dda_eff(v, e), e["sga"]], axis=1
                        ).max(axis=1)
        if name == "m_score_no_sgai":
            return avail7.astype(float), eff

        avail8 = avail7 & sgai.notna()
        c = BENEISH_COEF
        m = (c["const"] + c["DSRI"] * dsri + c["GMI"] * gmi + c["AQI"] * aqi
             + c["SGI"] * sgi + c["DEPI"] * depi + c["SGAI"] * sgai
             + c["TATA"] * tata + c["LVGI"] * lvgi)
        return m.where(avail8), eff

    raise KeyError(f"闸门指标 {name} 还没实现 —— ★ 没有悄悄返回 NaN。")


@functools.lru_cache(maxsize=1)      # ★ 只留 1 份:面板是 3,031×2,011 的大表,留多了吃内存
def panel(name: str, symbols: tuple[str, ...]) -> pd.DataFrame:
    """[日期 × 票] 日频面板。★ 故意不包 try —— 异常必须炸出来,不许伪装成「算不出」。"""
    cal = data.trading_calendar()
    cols = {}
    for s in symbols:
        v, ev = metric_q(s, name)
        cols[s] = F._to_daily(v, ev, cal)      # ★ 复用引擎的日频铺开
    return pd.DataFrame(cols, index=cal)


def get(name: str, symbols: list[str]) -> pd.DataFrame:
    return panel(name, tuple(symbols))


def clear_caches() -> None:
    frame.cache_clear()
    panel.cache_clear()
