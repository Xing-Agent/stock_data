#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 排雷五道闸 + Merton 违约距离 + F-Score 的算子(2026-11-04 第一步「只数个数」)

══════════════════════════════════════════════════════════════════════════
★★★ 三秒版(大白话)
     这个文件只干一件事:★ 把「六个体检指标」各算成一个数(每只票、每一天)。
     ★★ 它**不数个数、不做交集、不写报告** —— 那些在 run_gate_count_1104.py 里。
     ★★★ 它也**不跑回测、不碰收益** —— 第一步一个收益数字都不出现。
══════════════════════════════════════════════════════════════════════════

★★★ 本文件的四条自律(照 probe/expand_run_1104/ops_expand_1104.py 的套路)
  ① **只读 engine,一个字节不改**。★★★ 而且比上一轮更保守:
     ★ 本文件**连 engine 的派发函数都不替换** —— 不 monkeypatch 任何东西。
     ★★ 理由:第一步是纯计数,不需要走 engine 的链路;
        少挂一个钩子就少一个「我们动过 engine」的疑点。
  ② ★★★ **一个数据覆盖层都不挂。** `data.load_fundamentals` 原封不动。
     ★ 特别说明:我**没有**调用 `probe/fundamental_buildout_1030/ops_fund_1030.py`
       的 `install()` —— 那个函数默认会**整列替换 EBIT / 长期负债**(SEC 主表覆盖层)。
     ★★ 本轮只**调用它的纯计算函数**(`price_ratio` / `get`),不触发它的 install。
     ★★★ 所以本轮的 EBIT 是**老库原生的那个**(= 税前利润 + 利息费用,派生值),
       ★ 这一处必须跟着每个数走。
  ③ ★★★ **算不出来就是 NaN,一律记进「算不出来」那一列** ——
     ★ 不用近似值、默认值、历史值顶替;★★ 本文件里没有任何 `fillna(0)`
       用在**科目值**上(只用在布尔掩膜上)。
  ④ **口径归属如实标**:每个闸的 `_note()` 里写清是**原著**还是**我们的机械读法**。

══════════════════════════════════════════════════════════════════════════
★★ 五道闸的出处(★ 阈值一个都没自己拍)
══════════════════════════════════════════════════════════════════════════
  ① 利息覆盖   EBIT ÷ 利息费用 < 1                      Asquith 等 1994
  ② Sloan 应计 (净利润 − 经营现金流) ÷ 总资产,截面最高 10%   Sloan 1996
  ③ Zmijewski  三变量,概率 > 50%(★★ 用**总负债**)       Zmijewski 1984
  ④ Beneish    八变量 M-Score > −1.78                    Beneish 1999
  ⑤ Altman Z   1968 原版五变量 < 1.81(★★★ 只限上市制造业)  Altman 1968
  ⑥ Merton     违约距离(★★ 本轮**不当闸用**,只看它会剔谁)  Merton 1974

★★★ ①②③④ 的公式**逐字照搬** `probe/redflag_gates_1103/ops_redflag_1103.py`
   —— ★ 一个系数、一个阈值都没改。★★ 照搬而不是 import 的理由:
   那个文件的 `frame()` 为 PP&E / SG&A 这类老库没有的科目**不包 try**,
   ★★★ 而本轮跑的是老库,必须让「缺科目」变成 NaN(算不出来)、
   而不是让它抛异常把整轮跑挂。★ 公式本身一字未动,可逐行对照。

★★★ Beneish 的系数 —— 「第 25 轮核过的版本」在仓库里的出处(★ 我找到了,不是凭记忆):
   · `手册/Gemini原文归档/第28轮-七流派漏了什么-1104.md:44`
     逐字记着:「★★ 它这次给的系数有错: TATA 写成 4.037(**应为 4.679**),
     LVGI 写成 +0.0327(**应为 −0.327**)。用第 25 轮核过的版本」
   · `手册/33-基本面与融合面全清单-按流派-大白话-1104.md:140` 指向同一句
   · 已实现并提交的那份:`probe/redflag_gates_1103/ops_redflag_1103.py:137-140`
   ★★ 三处对得上 → 本文件用的就是这一版,见 `BENEISH_COEF`。

══════════════════════════════════════════════════════════════════════════
★★ 「年同比」在季度数据上怎么读(★ 照搬 1103 的机械读法)
══════════════════════════════════════════════════════════════════════════
  Beneish / Zmijewski / Altman 原著都是**年度**数据。我们只有季度 PIT,
  所以 t−1 年一律机械地取 **shift(4) 个季度**。
  ★ 这是我们的机械读法,不是原著原文 —— 留痕。
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

from engine import cache, data, fundamentals as F        # noqa: E402

_NOTES: list[str] = []


def notes() -> list[str]:
    return list(_NOTES)


def _note(s: str) -> None:
    if s not in _NOTES:
        _NOTES.append(s)


# ══════════════════════════════════════════════════════════════════════════
# 一 · 科目对齐表
# ══════════════════════════════════════════════════════════════════════════
#: ★ kind: "ttm" = 流量(YTD 差分还原后滚 4 季)/ "pt" = 存量(余额,不滚)
_COLS = {
    # 流量
    "ebit":   ("EBIT", "ttm"),
    "intexp": ("InterestExpense", "ttm"),
    "ni":     ("NetIncome", "ttm"),
    "ocf":    ("OperatingCashFlow", "ttm"),
    "rev":    ("Revenue", "ttm"),
    "cor":    ("CostOfRevenue", "ttm"),
    "eps":    ("DilutedEPS", "ttm"),
    "dda1":   ("DepreciationDepletionAndAmortization", "ttm"),
    "dda2":   ("DepreciationAmortizationAndAccretionNet", "ttm"),
    # ★★★ 下面两个老库**没有** —— 留在表里是为了让「缺什么」有实测数字,
    #   ★ 而不是嘴上说缺。它们缺 → Beneish 的 AQI/DEPI/SGAI 算不出来。
    "ppe":    ("PropertyPlantAndEquipmentNet", "pt"),
    "sga":    ("SellingGeneralAndAdministrativeExpense", "ttm"),
    # ★★ 特里·史密斯要的那个科目,同样留在表里取实测覆盖率
    "oil":    ("OperatingIncomeLoss", "ttm"),
    # 存量
    "ta":     ("TotalAssets", "pt"),
    "liab":   ("Liabilities", "pt"),          # ★★★ 总负债 —— Zmijewski / Altman 用这个
    "ca":     ("CurrentAssets", "pt"),
    "cl":     ("CurrentLiabilities", "pt"),
    "ltd":    ("LongTermDebt", "pt"),
    "ar":     ("AccountsReceivableNetCurrent", "pt"),
    "eq":     ("StockholdersEquity", "pt"),
    "re":     ("RetainedEarningsAccumulatedDeficit", "pt"),   # ★ Altman X2
}

#: ★ 老库里没有登记流量/存量的科目 —— 必须显式登记,否则 quarterly() 会 raise。
#  ★★ 这是**显式声明口径**,不是绕过 engine 的护栏(护栏正是靠这个登记生效的)。
#  ★★★ engine/fundamentals.py 文件本身一个字节没改 —— 只是运行时往集合里 add。
def _register_metrics() -> None:
    F.STOCK_METRICS.add("PropertyPlantAndEquipmentNet")
    F.FLOW_METRICS.add("SellingGeneralAndAdministrativeExpense")
    F.FLOW_METRICS.add("OperatingIncomeLoss")


_register_metrics()


@functools.lru_cache(maxsize=4096)
def frame(symbol: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """(值表, 生效日表),索引 = period_end。★ 走的是 engine 的 ttm/quarterly。"""
    cols, effs = {}, {}
    for name, (metric, kind) in _COLS.items():
        try:
            ser = (F.ttm(symbol, metric) if kind == "ttm"
                   else F.quarterly(symbol, metric))
        except KeyError:
            # ★ 只有「字段没分类」会走到这儿,上面已全部登记 → 实际不该发生。
            #   ★★ 留着是为了「缺科目」永远表现成 NaN,不是跑挂。
            ser = ()
        cols[name] = {o.period_end: o.value for o in ser}
        effs[name] = {o.period_end: o.eff for o in ser}
    sq = F.shares_quarterly(symbol)
    cols["sh"] = {o.period_end: o.value for o in sq}
    effs["sh"] = {o.period_end: o.eff for o in sq}

    idx = sorted({pe for d in cols.values() for pe in d})
    if not idx:
        return pd.DataFrame(), pd.DataFrame()
    v = pd.DataFrame({k: pd.Series(x, dtype=float) for k, x in cols.items()}
                     ).reindex(idx)
    # ★★ 照 1103/1104 踩过的坑:生效日表每一列**强制 datetime64**,
    #   否则全 NaN 的列是 float64,.max(axis=1) 会在 float 和 Timestamp 间比大小。
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
# 二 · 系数与阈值(★★★ 一个都没自己拍)
# ══════════════════════════════════════════════════════════════════════════

#: Beneish 1999 八变量 —— ★★★ 第 25 轮核过的版本(出处见文件头)
BENEISH_COEF = {
    "const": -4.84, "DSRI": 0.920, "GMI": 0.528, "AQI": 0.404, "SGI": 0.892,
    "DEPI": 0.115, "SGAI": -0.172, "TATA": 4.679, "LVGI": -0.327,
}
BENEISH_THRESHOLD = -1.78

#: Zmijewski 1984 三变量 —— 逐字原文
ZMIJEWSKI_COEF = {"const": -4.3, "ROA": -4.5, "LEV": 5.7, "LIQ": -0.004}
ZMIJEWSKI_P_THRESHOLD = 0.50

#: Altman 1968 原版五变量 —— 逐字原文
ALTMAN_COEF = {"X1": 1.2, "X2": 1.4, "X3": 3.3, "X4": 0.6, "X5": 0.999}
ALTMAN_THRESHOLD = 1.81

#: ★★★ 「上市制造业」= SIC 2000–3999。★ 这是 SIC 体系对 Manufacturing 的定义区间,
#  不是我们拍的数。★★ 落在区间外的票 → Altman Z **不适用** → 记「算不出来」。
MANUFACTURING_SIC = (2000, 3999)

INTCOV_THRESHOLD = 1.0
SLOAN_TOP_PCT = 0.10          # ★ 截面最高 10%(★★ 排名法,不是静态线)

#: Merton:年化窗口与到期期限
MERTON_VOL_WINDOW = 252       # ★ 1 年 = 252 个交易日(行业惯例)
MERTON_T = 1.0                # ★ Merton 1974 / KMV 惯例:1 年


# ══════════════════════════════════════════════════════════════════════════
# 三 · 季度级指标
# ══════════════════════════════════════════════════════════════════════════

METRICS_Q = (
    "int_cov",            # ① EBIT ÷ 利息费用
    "sloan_accrual",      # ② (NI − OCF) ÷ TA     —— 原始值,排名在 run 里做
    "zmij_prob",          # ③ Zmijewski 概率
    "m_score",            # ④ Beneish M-Score(八项全齐才给数)
    "m_score_avail7",     # ★ 诊断:除 SGAI 外七项是否全齐
    "m_score_avail_dsri_gmi_sgi_tata",  # ★ 诊断:不需要 PP&E/SG&A 的那四项
    "altman_num",         # ⑤ Altman 的「不含市值那一半」(X1,X2,X3,X5 已加权求和)
    "altman_tl",          # ⑤ X4 的分母 = 总负债
    "roa_piotroski",      # ★ 预言六要比的 ROA = 净利润 ÷ **期初**总资产
    "equity",             # ★ 误杀名单:净资产
    "ocf_ttm",            # ★ 误杀名单:经营现金流
    "debt_face_kmv",      # ⑥ Merton 的违约点 = 流动负债 + 0.5 × 长期负债
    "liab_total",         # ⑥ 对照口径:总负债
    "shares_q",
    "oil_ttm",            # ★ 特里·史密斯那个科目的覆盖率证据
    "ppe_pt",             # ★ 神奇公式 v2 那个科目的覆盖率证据
    "sga_ttm",            # ★ Beneish SGAI 那个科目的覆盖率证据
)


def metric_q(symbol: str, name: str) -> tuple[pd.Series, pd.Series]:   # noqa: C901
    """算一个指标的季度序列,返回 (值, 生效日)。★ 算不出就是 NaN —— 不猜不补。"""
    v, e = frame(symbol)
    if v.empty:
        return pd.Series(dtype=float), pd.Series(dtype="datetime64[ns]")

    def eff(cols: list[str]) -> pd.Series:
        return e[cols].max(axis=1)

    # ---------------------------------------------- 原始科目(覆盖率证据用)
    if name == "oil_ttm":
        return v["oil"], eff(["oil"])
    if name == "ppe_pt":
        return v["ppe"], eff(["ppe"])
    if name == "sga_ttm":
        return v["sga"], eff(["sga"])
    if name == "equity":
        return v["eq"], eff(["eq"])
    if name == "ocf_ttm":
        return v["ocf"], eff(["ocf"])
    if name == "shares_q":
        return v["sh"], eff(["sh"])
    if name == "liab_total":
        return v["liab"], eff(["liab"])

    # ---------------------------------------------- ① 利息覆盖
    if name == "int_cov":
        # ★ 利息费用 ≤ 0(没有利息支出 / 标签是净利息收入)→ 这道闸**不适用**,
        #   判「算不出」。★★ 不按 0 算、不当成「覆盖率无穷大所以通过」——
        #   ★★★ 那是替它编数。(★ 逐字照搬 1103)
        ie = v["intexp"].where(v["intexp"] > 0)
        ok = v["ebit"].notna() & ie.notna()
        return (v["ebit"] / ie).where(ok), eff(["ebit", "intexp"])

    # ---------------------------------------------- ② Sloan 应计
    if name == "sloan_accrual":
        ta = v["ta"].where(v["ta"] > 0)
        ok = v["ni"].notna() & v["ocf"].notna() & ta.notna()
        return ((v["ni"] - v["ocf"]) / ta).where(ok), eff(["ni", "ocf", "ta"])

    # ---------------------------------------------- ③ Zmijewski 1984
    if name == "zmij_prob":
        ta = v["ta"].where(v["ta"] > 0)
        cl = v["cl"].where(v["cl"] > 0)
        roa = v["ni"] / ta
        lev = v["liab"] / ta             # ★★★ 总负债 ÷ 总资产(不是有息负债)
        liq = v["ca"] / cl
        ok = roa.notna() & lev.notna() & liq.notna()
        x = (ZMIJEWSKI_COEF["const"] + ZMIJEWSKI_COEF["ROA"] * roa
             + ZMIJEWSKI_COEF["LEV"] * lev + ZMIJEWSKI_COEF["LIQ"] * liq)
        p = 1.0 / (1.0 + np.exp(-x))
        return p.where(ok), eff(["ni", "ta", "liab", "ca", "cl"])

    # ---------------------------------------------- ④ Beneish 1999
    if name in ("m_score", "m_score_avail7",
                "m_score_avail_dsri_gmi_sgi_tata"):
        ta = v["ta"].where(v["ta"] > 0)
        rev = v["rev"].where(v["rev"] > 0)
        cl, ltd = v["cl"], v["ltd"]
        dda = _dda(v)

        def _r(s):                       # ★ t−1 年 = shift(4) 个季度(机械读法)
            return s.shift(4)

        ars = v["ar"] / rev
        dsri = ars / _r(ars).where(_r(ars) > 0)
        gm = (v["rev"] - v["cor"]) / rev
        gmi = _r(gm) / gm.where(gm != 0)
        aq = 1.0 - (v["ca"] + v["ppe"]) / ta           # ★★ 要 PP&E
        aqi = aq / _r(aq).where(_r(aq) != 0)
        sgi = v["rev"] / _r(v["rev"]).where(_r(v["rev"]) > 0)
        dr = dda / (dda + v["ppe"]).where((dda + v["ppe"]) > 0)   # ★★ 要 PP&E
        depi = _r(dr) / dr.where(dr > 0)
        sgar = v["sga"] / rev                           # ★★ 要 SG&A
        sgai = sgar / _r(sgar).where(_r(sgar) > 0)
        lv = (cl + ltd) / ta
        lvgi = lv / _r(lv).where(_r(lv) > 0)
        # ★ TATA 原著分子是「持续经营利润 − 经营现金流」;老库没有「持续经营利润」
        #   科目,用 NetIncome 代 —— ★★ 留痕(照搬 1103 的同一处让步)。
        tata = (v["ni"] - v["ocf"]) / ta

        eff_cols = ["ar", "rev", "cor", "ca", "ppe", "ta", "cl", "ltd",
                    "ni", "ocf"]
        ev = pd.concat([e[eff_cols], _dda_eff(v, e), e["sga"]], axis=1).max(axis=1)

        if name == "m_score_avail_dsri_gmi_sgi_tata":
            # ★ 四项:不需要 PP&E、不需要 SG&A —— 用来证明「缺的到底是哪两样」
            a = dsri.notna() & gmi.notna() & sgi.notna() & tata.notna() & lvgi.notna()
            return a.astype(float), ev

        seven = [dsri, gmi, aqi, sgi, depi, lvgi, tata]
        avail7 = seven[0].notna()
        for s in seven[1:]:
            avail7 &= s.notna()
        if name == "m_score_avail7":
            return avail7.astype(float), ev

        avail8 = avail7 & sgai.notna()
        c = BENEISH_COEF
        m = (c["const"] + c["DSRI"] * dsri + c["GMI"] * gmi + c["AQI"] * aqi
             + c["SGI"] * sgi + c["DEPI"] * depi + c["SGAI"] * sgai
             + c["TATA"] * tata + c["LVGI"] * lvgi)
        return m.where(avail8), ev

    # ---------------------------------------------- ⑤ Altman 1968
    if name == "altman_num":
        # ★★★ Z = 1.2·X1 + 1.4·X2 + 3.3·X3 + 0.6·X4 + 0.999·X5
        #   X1 = 营运资本 ÷ 总资产     X2 = 留存收益 ÷ 总资产
        #   X3 = EBIT ÷ 总资产         X4 = **股权市值** ÷ 总负债
        #   X5 = 营收 ÷ 总资产
        # ★ 这里只给「不含 X4」的那四项加权和;X4 要配日频价格,在 run 里合。
        ta = v["ta"].where(v["ta"] > 0)
        x1 = (v["ca"] - v["cl"]) / ta
        x2 = v["re"] / ta
        x3 = v["ebit"] / ta
        x5 = v["rev"] / ta
        ok = x1.notna() & x2.notna() & x3.notna() & x5.notna()
        a = ALTMAN_COEF
        s = a["X1"] * x1 + a["X2"] * x2 + a["X3"] * x3 + a["X5"] * x5
        return s.where(ok), eff(["ca", "cl", "re", "ebit", "rev", "ta"])

    if name == "altman_tl":
        return v["liab"].where(v["liab"] > 0), eff(["liab"])

    # ---------------------------------------------- ★ 预言六要比的 ROA
    if name == "roa_piotroski":
        # ★★ 口径**和 engine 的 F-Score 自己用的那个一模一样**
        #   (engine/fundamentals.py:351 `ta0 = v["ta"].shift(4)`)——
        #   ★★★ 这样「F-Score 剔掉谁」和「谁的 ROA 高」用的是同一个 ROA,
        #   ★ 不会因为换了 ROA 口径而把结论变成口径差。
        ta0 = v["ta"].shift(4)
        ok = v["ni"].notna() & (ta0 > 0)
        return (v["ni"] / ta0.where(ta0 > 0)).where(ok), eff(["ni", "ta"])

    # ---------------------------------------------- ⑥ Merton 的负债面
    if name == "debt_face_kmv":
        # ★★ 违约点 = 流动负债 + 0.5 × 长期负债
        #   ★★★ 归属 = **行业惯例(KMV / Moody's 的 default point)**,
        #     ★ 不是 Merton 1974 原文 —— 原文是「单一零息债券的面值」,
        #       现实里没有这个东西,所以行业用这个代理。★★ 留痕。
        ok = v["cl"].notna() & v["ltd"].notna()
        return (v["cl"] + 0.5 * v["ltd"]).where(ok), eff(["cl", "ltd"])

    raise KeyError(f"指标 {name} 还没实现 —— ★ 没有悄悄返回 NaN。")


@functools.lru_cache(maxsize=32)
def _panel(name: str, symbols: tuple[str, ...]) -> pd.DataFrame:
    cal = data.trading_calendar()
    cols = {}
    for s in symbols:
        # ★ 故意不包 try:算不出必须是「数据不够」,不许是「我们的代码抛了被吞掉」
        vv, ee = metric_q(s, name)
        cols[s] = F._to_daily(vv, ee, cal)
    return pd.DataFrame(cols, index=cal)


def get(name: str, symbols: list[str]) -> pd.DataFrame:
    return _panel(name, tuple(symbols))


def clear_caches() -> None:
    frame.cache_clear()
    _panel.cache_clear()


# ══════════════════════════════════════════════════════════════════════════
# 四 · 市值(规模代理)
# ══════════════════════════════════════════════════════════════════════════

def mktcap(symbols: list[str]) -> pd.DataFrame:
    """★★ 规模代理 = 收盘价 × 摊薄股数(过完 engine 三道股数闸)。

    ★★★ 这**不是 PIT 市值** —— 仓库没有 PIT 市值(README 明说)。
    ★ 和 `ops_fund_1030` 的 EV 股权腿、`ops_expand_1104.mktcap` 同一个口径,
      ★★ 本轮沿用,并在报告里照实标。
    """
    close = cache.field("close", symbols)
    sh = get("shares_q", symbols).reindex_like(close)
    mc = close * sh
    return mc.where(mc > 0)


# ══════════════════════════════════════════════════════════════════════════
# 五 · ★★ SIC 行业码(按时点取,★★★ 不许用最新版本回填历史)
# ══════════════════════════════════════════════════════════════════════════

@functools.lru_cache(maxsize=1)
def _sic_daily_all() -> dict[str, pd.Series]:
    """每只票一条日频 SIC 码序列。

    ★★★ PIT 口径:用每个版本的 `observed_from`(= SEC 第一次这么披露的时间),
      ★ 再走 engine 的 `effective_date()` 推到**下一个交易日**才生效
      —— 和财报 filing+1 同一条规矩。
    ★★ 第一个版本生效**之前**是 NaN —— ★★★ 绝不拿后来的版本回填历史
      (那就是偷看未来的行业归属)。
    ★ 做法逐字照搬 `probe/expand_run_1104/ops_expand_1104._sic_daily_all`。
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
        except (OSError, UnicodeDecodeError, json.JSONDecodeError):
            continue
        recs = []
        for r in (raw.get("sic_versions") or []):
            ts = r.get("observed_from") or r.get("accepted_at")
            code = r.get("sic_code")
            if not ts or not code:
                continue
            eff = F.effective_date(pd.Timestamp(ts).tz_localize(None))
            if eff is None:
                continue
            try:
                recs.append((eff, int(str(code).strip())))
            except ValueError:
                continue
        if not recs:
            continue
        recs.sort(key=lambda x: x[0])
        ser = pd.Series(np.nan, index=cal, dtype=float)
        arr = cal.to_numpy()
        for eff, code in recs:
            pos = int(np.searchsorted(arr, np.datetime64(eff), side="left"))
            if pos < len(cal):
                ser.iloc[pos] = float(code)
        out[sym] = ser.ffill()
    return out


def sic_panel(symbols: list[str]) -> pd.DataFrame:
    allsic = _sic_daily_all()
    cal = data.trading_calendar()
    return pd.DataFrame({s: allsic.get(s, pd.Series(np.nan, index=cal))
                         for s in symbols}, index=cal)


#: ★ SIC 一位 division → 大白话板块名(★★ 只用来做附表一的分组,不参与任何闸)
SIC_DIVISIONS = (
    (100, 999, "农林渔牧"),
    (1000, 1499, "采矿"),
    (1500, 1799, "建筑"),
    (2000, 3999, "★ 制造业(Altman 1968 适用)"),
    (4000, 4999, "运输·通信·水电燃气"),
    (5000, 5199, "批发"),
    (5200, 5999, "零售"),
    (6000, 6799, "金融·保险·房地产"),
    (7000, 8999, "服务业"),
    (9100, 9729, "公共管理"),
)


def sic_division_name(code: float | None) -> str:
    if code is None or not np.isfinite(code):
        return "★★ 没有 SIC(算不出来)"
    c = int(code)
    for lo, hi, nm in SIC_DIVISIONS:
        if lo <= c <= hi:
            return nm
    return f"其他(SIC {c})"


def is_manufacturing(symbols: list[str]) -> pd.DataFrame:
    """★★★ 上市制造业 = SIC 2000–3999。★ 没有 SIC 的票 → False(= 不适用)。"""
    p = sic_panel(symbols)
    lo, hi = MANUFACTURING_SIC
    return (p >= float(lo)) & (p <= float(hi)) & p.notna()


# ══════════════════════════════════════════════════════════════════════════
# 六 · ⑥ Merton 违约距离(★★ 本轮不当闸用,只看它会剔谁)
# ══════════════════════════════════════════════════════════════════════════

def merton_distance_to_default(symbols: list[str],
                               debt_metric: str = "debt_face_kmv"
                               ) -> tuple[pd.DataFrame, dict]:
    """Merton (1974) 违约距离 —— ★ 用的是行业里那个「naive DD」闭式解。

    ★★★ 大白话:把一家公司的**股票**看成「对公司资产的一份看涨期权」。
       ★ 股价波动越大、负债越重、市值越薄 → 资产离「还不上钱」那条线越近。
       ★★ 违约距离 = 还差几个标准差才撞线。★★★ 数越小越危险。

    ★★ 公式(逐字照 Bharath & Shumway 2008 的 naive DD,★ 这是行业标准简化版):
        E   = 股权市值 = 收盘价 × 摊薄股数          ★ 规模代理,不是 PIT 市值
        F   = 违约点(见 `debt_face_kmv` 的注释)
        σ_E = 过去 252 个交易日**对数收益**的年化标准差
        σ_V = E/(E+F)·σ_E + F/(E+F)·(0.05 + 0.25·σ_E)     ★★ naive 的资产波动率
        μ   = 过去 252 个交易日的**股权简单收益**(naive 的资产漂移)
        DD  = [ ln((E+F)/F) + (μ − 0.5·σ_V²)·T ] / (σ_V·√T),  T = 1 年

    ★★★ 归属:**原著 + 行业简化**,不是纯原著 ——
      ★ Merton 1974 要的是「资产价值 V 和资产波动率 σ_V」,这两个**看不见**;
      ★★ naive DD 是行业里公认的可算代理(B&S 2008 实测它不输完整迭代解)。
      ★★★ 报告里必须这么标,不许标成「Merton 原著」。

    ★ 返回 (DD 面板, 诊断)。★★ 算不出 = NaN = 记进「算不出来」。
    """
    _note("★★★ ⑥ Merton 违约距离:**本轮不当闸用** —— ★ 只并排列出来看它会剔谁。"
          "★★ 阈值**没有定** —— 按任务单要求只给分布。"
          "★★★ 口径 = Merton 1974 的 naive DD(Bharath & Shumway 2008),"
          "★ 标「原著 + 行业简化」,不标纯原著:原著要的资产价值/资产波动率看不见。"
          "★★ 股权市值 = 收盘价 × 摊薄股数 = **规模代理,不是 PIT 市值**。")

    close = cache.field("close", symbols)
    E = mktcap(symbols)
    Fd = get(debt_metric, symbols).reindex_like(close)
    Fd = Fd.where(Fd > 0)                    # ★ 违约点 ≤ 0 → 不适用(算不出来)

    logret = np.log(close / close.shift(1))
    n = MERTON_VOL_WINDOW
    # ★ min_periods = n:★★ 不拿不足一年的窗口凑一个「大概的波动率」
    sig_e = logret.rolling(n, min_periods=n).std() * np.sqrt(252.0)
    mu = (close / close.shift(n)) - 1.0      # ★ 过去一年的简单收益

    tot = E + Fd
    w_e = E / tot.where(tot > 0)
    w_f = Fd / tot.where(tot > 0)
    sig_v = w_e * sig_e + w_f * (0.05 + 0.25 * sig_e)
    sig_v = sig_v.where(sig_v > 0)

    dd = ((np.log(tot / Fd) + (mu - 0.5 * sig_v ** 2) * MERTON_T)
          / (sig_v * np.sqrt(MERTON_T)))
    ok = E.notna() & Fd.notna() & sig_e.notna() & mu.notna() & sig_v.notna()
    dd = dd.where(ok)

    diag = {
        "★口径": "naive DD(Bharath & Shumway 2008)—— ★ Merton 1974 的可算代理",
        "违约点口径": ("流动负债 + 0.5 × 长期负债(KMV default point,**行业惯例**)"
                       if debt_metric == "debt_face_kmv" else "总负债"),
        "波动率窗口(交易日)": MERTON_VOL_WINDOW,
        "T(年)": MERTON_T,
        "★股权市值": "收盘价 × 摊薄股数 —— ★★ 规模代理,不是 PIT 市值",
        "★★阈值": "★★★ 本轮**没有定阈值** —— 只给分布(照任务单)",
    }
    return dd, diag


# ══════════════════════════════════════════════════════════════════════════
# 七 · 原始科目覆盖率(★ 「缺什么」要有实测数字,不是嘴上说缺)
# ══════════════════════════════════════════════════════════════════════════

def raw_coverage(symbols: list[str], names: tuple[str, ...]) -> dict:
    """符号级覆盖率:250 只里有多少只**真的有**这个科目的可用期。"""
    out = {}
    for nm in names:
        have = 0
        for s in symbols:
            vv, _ = metric_q(s, nm)
            if len(vv) and vv.notna().any():
                have += 1
        out[nm] = {"有数据的票数": have, "总票数": len(symbols),
                   "符号级覆盖率%": round(100.0 * have / max(1, len(symbols)), 1)}
    return out
