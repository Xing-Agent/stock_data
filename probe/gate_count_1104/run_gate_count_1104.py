#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 排雷 / F-Score 挂不挂 · 第一步「只数个数」—— 2026-11-04

══════════════════════════════════════════════════════════════════════════
★★★ 三秒版(大白话)
     每条策略先选出一批候选票,★ 然后把五道排雷闸挨个套上去,
     ★★ 数「少了几只」。★★★ 本脚本**一个收益数字都不算** ——
     没有回测、没有流水、没有 R、没有胜率。
══════════════════════════════════════════════════════════════════════════

★★ 跑批纪律(逐条照 `手册/39-排雷挂不挂-预先登记-1104.md` 第三节)
  ① ★★★ **只用研发池。`exam_1042/` 一个文件都不读** ——
     ★ 自证方式是**实测路径命中数**,不是声明:见输出里
       `★考卷未碰自证`(逐只票打开 manifest 里的真实路径,数 exam_1042 命中数)。
  ② ★★★ **engine/ 一个字节不改** —— 本轮连派发函数都没替换(见 ops 文件头)。
  ③ ★★★ **库冻结窗口**:跑前跑后各记一次 `fundamentals_ext/_MANIFEST.sha256`。
  ④ ★★★ **只数个数** —— 本脚本里没有任何收益/R/胜率的计算路径。
  ⑤ ★★★ 「**算不出来**」和「**被剔掉**」**分两列记**,不混。
  ⑥ ★★★ 报告里**不许写「建议挂 / 不挂」** —— 只给数字。
  ⑦ 产物写到 `probe/gate_count_1104/`,★ 先写文件再打印,不用 nohup。

跑法:python3 probe/gate_count_1104/run_gate_count_1104.py
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE,
          os.path.join(ROOT, "probe", "v2_rerun_1030"),
          os.path.join(ROOT, "probe", "fundamental_buildout_1030"),
          os.path.join(ROOT, "probe", "expand_run_1104")):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import cache, data, fundamentals as F, matrices   # noqa: E402
import ops_gate_1104 as G                                      # noqa: E402
import ops_fund_1030 as OF                                     # noqa: E402
import ops_expand_1104 as OX                                   # noqa: E402
import rerun_core_1030 as RC                                   # noqa: E402

DEV = ("2018-01-01", "2020-12-31")   # ★ 研发池窗口(★ 和 probe/expand_run_1104 一致)
SCOPE = "large_mid"                   # ★ 大+中池(成交额排名 1–2000)
MANIFEST_SHA = os.path.join(ROOT, "fundamentals_ext", "_MANIFEST.sha256")
OUT_JSON = os.path.join(HERE, "gate_count_1104.json")

#: ★★★ 跑前写死的库指纹(出处:手册/39 第三节 ③)
EXPECTED_SHA = "45ac22b4a096924e5bcda97ad77d585699778f2d3be5417ebe8bc1297acf60a6"

#: ★ Piotroski F-Score 的门槛。★★★ 出处:engine/configs/deep_value.yaml 自己
#  已登记的那条审计结论 —— 原文主组合是 **8–9 对 0–1**,「≥5」是第 5 节
#  稳健性检验里的数、不是主口径。★★ 所以本轮**两个门槛都跑、并排列**,
#  ★★★ 不挑一个(红线②:禁止单点估计)。
FSCORE_THRESHOLDS = (5.0, 7.0)

GATES = ("①利息覆盖<1", "②应计最高10%", "③Zmijewski>50%",
         "④M-Score>−1.78", "⑤AltmanZ<1.81")


# ══════════════════════════════════════════════════════════════════════════
# 一 · 跑批前后的自证
# ══════════════════════════════════════════════════════════════════════════

def sha_of_manifest() -> str:
    h = hashlib.sha256()
    with open(MANIFEST_SHA, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def exam_untouched_proof(syms: list[str]) -> dict:
    """★★★ 考卷未碰的**实测**自证 —— ★ 不是声明,是逐只票数路径命中数。"""
    man = data.load_manifest()
    roots, exam_hits, missing = {}, [], []
    for s in syms:
        p = man[s].fundamentals_path or ""
        if not p:
            missing.append(s)
            continue
        rel = os.path.relpath(p, ROOT)
        roots[rel.split(os.sep)[0]] = roots.get(rel.split(os.sep)[0], 0) + 1
        if "exam_1042" in rel:
            exam_hits.append(s)
    return {
        "★★★ 本轮 250 只票的基本面文件根目录分布": roots,
        "★★★ exam_1042 路径命中数": len(exam_hits),
        "★ 命中的票(应为空)": exam_hits,
        "★ 没有基本面路径的票": missing,
        "★★ 本脚本源码里有没有 exam_1042 这个路径":
            "★★★ 没有任何 open()/路径拼接指向它 —— "
            "注释里出现这几个字只是说明文字。",
        "★★ 行情面板来源": "engine/cache(pilot_300 / pilot_50 口径),"
                            "★ 和 probe/expand_run_1104 同一条",
    }


# ══════════════════════════════════════════════════════════════════════════
# 二 · 调仓日
# ══════════════════════════════════════════════════════════════════════════

def rebalance_dates(cal: pd.DatetimeIndex) -> list[pd.Timestamp]:
    """★★★ 调仓日 = 研发池窗口内**每个季度的第一个交易日**。

    ★ 归属:**我们的机械读法,不是原著**。
      ★★ 理由必须写清:本轮这几条策略的配置里,离场写的都是
         `screen_dropout`(条件不再成立就走),而**原著的再平衡频率
         方法卡一律没给**(见 基-2 / 基-5 / 基-6 配置里 exit 那一段的注释:
         「★★★ 原著的再平衡频率(一年一次?季度?)方法卡没给 ——
          本轮没有拍这个数」)。
      ★★★ 所以「调仓日」这个概念本身在原著里没有锚 —— ★ 本轮选季度初,
         是因为它和财报节奏对齐、且是**唯一不含自由参数的常用读法**;
         ★★ 换成月初/年初会把个数改掉,这一处敏感性**没测**,照实登记。
    """
    lo, hi = pd.Timestamp(DEV[0]), pd.Timestamp(DEV[1])
    sub = cal[(cal >= lo) & (cal <= hi)]
    out = []
    seen = set()
    for d in sub:
        k = (d.year, (d.month - 1) // 3 + 1)
        if k not in seen:
            seen.add(k)
            out.append(d)
    return out


# ══════════════════════════════════════════════════════════════════════════
# 三 · 策略候选池(★ 每条都是一张 [日期 × 票] 的布尔面板)
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


#: ★★★ 跑不了的策略 —— ★ 照实登记「跑不了 + 缺什么」,不拿近似口径顶替
CANNOT_RUN: dict[str, dict] = {}


def strategy_screens(syms: list[str], cal: pd.DatetimeIndex,
                     scope: pd.DataFrame) -> dict[str, pd.DataFrame]:
    """返回 {策略名: 候选掩膜}。★★ 跑不了的记进 CANNOT_RUN,不进这个字典。"""
    out: dict[str, pd.DataFrame] = {}

    def fin(m: pd.DataFrame) -> pd.DataFrame:
        return _as_bool(m).reindex(index=cal, columns=syms).fillna(False) & scope

    # ---------------------------------------------- 0 全研发池(基线)
    # ★★★ 这不是一条策略 —— ★ 它是「**一条策略都不挂、整个池子直接套五道闸**」
    #   的基线,★★ 用来回答任务单那个问题:「五道合起来到底剔掉百分之几」。
    #   ★★★ Gemini 说的「七成」是**全市场口径**,所以要比就得和这一行比,
    #   ★ 不能和某条策略筛完之后的候选池比。
    out["0·全研发池(不挂任何策略·基线)"] = scope.copy()

    # ---------------------------------------------- 1 施洛斯极度分散
    # ★ 出处:probe/fundamental_buildout_1030/configs_1030/基-2-施洛斯极度分散.yaml
    #   universe: pb_below threshold 1.0(★★ 「跌破净资产」= 1.0,无自由参数)
    pb = OF.price_ratio("pb", syms)
    out["1·施洛斯极度分散"] = fin(pb.notna() & (pb < 1.0))

    # ---------------------------------------------- 2 低 PE 逆向(德雷曼)
    # ★ 出处:基-5-低市盈率逆向.yaml universe: pe_rank_bottom 20
    #   ★★ EPS ≤ 0 判不合格(price_ratio 里已处理)
    pe = OF.price_ratio("pe", syms)
    out["2·低PE逆向"] = fin(_rank_bottom(pe, 20.0))

    # ---------------------------------------------- 3 收购者倍数(卡莱尔)
    # ★ 出处:基-6-收购者倍数.yaml universe: ev_ebit_rank_bottom 20
    eve = OF.price_ratio("ev_ebit", syms)
    out["3·收购者倍数"] = fin(_rank_bottom(eve, 20.0))

    # ---------------------------------------------- 4 神奇公式
    # ★★★ v2 跑不了 —— ★ 缺 PropertyPlantAndEquipmentNet(实测见「缺口」一节)
    CANNOT_RUN["4·神奇公式 v2"] = {
        "判定": "★★★ 跑不了",
        "缺的是哪一样": "**PropertyPlantAndEquipmentNet(厂房设备净值)——"
                        "老库符号级覆盖率 0.0%(0/250)**。",
        "为什么这一样是硬卡点": "★ 手册/19 定的 v2 口径:净固定资产 = "
                                "**厂房设备净值**(这一处标的是「原著」)。"
                                "★★ 这个科目一个格子都没有 → v2 的分母算不出来。",
        "★为什么不拿别的顶上": "★★★ 用 v1 那个派生式净固定资产"
                               "(总资产 − 流动资产 − 无形商誉)顶上 = **那就是 v1**,"
                               "★ 标成 v2 会把「我们算的」标成「原著」—— 红线①。",
        "★★并排给的参照": "★ 下面另跑一条 **v1**(magic_formula_rank_top 20),"
                           "★★★ 明确标成 v1,**不是 v2 的代替品**。",
    }
    # ★ v1 作为并排参照(★★ 标清是 v1)
    roc = OF.get("roc_greenblatt", syms).reindex_like(eve)
    r_roc = roc.rank(axis=1, pct=True, ascending=False, na_option="keep")
    r_ev = eve.rank(axis=1, pct=True, ascending=True, na_option="keep")
    both = roc.notna() & eve.notna()
    comb = (r_roc + r_ev).where(both)
    out["4b·神奇公式 v1(参照)"] = fin(_rank_bottom(comb, 20.0))

    # ---------------------------------------------- 5 Net-Net
    # ★ 出处:probe/expand_run_1104/configs_1104/扩4-orig.yaml
    #   netnav_discount_below max_ratio 2/3(★★ 《聪明的投资者》1949 版)
    mc = OX.mktcap(syms)
    ncav = OX.get("ncav", syms).reindex_like(mc)
    ratio = mc / ncav.where(ncav > 0)
    out["5·Net-Net"] = fin(ratio.notna() & (ratio < 2.0 / 3.0))

    # ---------------------------------------------- 6 回购 / 股东回报
    # ★ 出处:扩7-orig.yaml shareholder_yield_rank_top 20
    sy = OX.score("shareholder_yield", syms)
    out["6·股东回报率(回购+分红−增发)"] = fin(_rank_top(sy, 20.0))

    # ---------------------------------------------- 7 特里·史密斯
    CANNOT_RUN["7·特里·史密斯"] = {
        "判定": "★★★ 跑不了",
        "缺的是哪一样": "**① OperatingIncomeLoss(营业利润)—— 老库符号级覆盖率 "
                        "0.0%(0/250);② PropertyPlantAndEquipmentNet —— 同样 0.0%**。",
        "为什么这一样是硬卡点": "★ 方法卡(METHOD_LIBRARY/基-16.md)原文筛选条件第一条是"
                                "「**长期高资本回报率(不靠杠杆做出来的)**」—— "
                                "★★ 「不靠杠杆」就是要用**投入资本**做分母,"
                                "而投入资本要营业利润 + 固定资产;"
                                "★★★ 两样都 0% → 这条策略的第一个条件就算不出来。",
        "★另一处卡点(和数据无关)": "★★★ 这条策略**仓库里没有已登记的配置文件** —— "
                                    "`engine/configs/` 和各 probe 的 configs 目录里都没有 基-16。"
                                    "★ 所以就算科目齐了,也得先走预先登记(红线③),"
                                    "★★ 本轮不临场发明。",
    }

    # ---------------------------------------------- 8 GARP(茨威格)
    # ★★★ 这一条**没有已登记配置** → 本轮用「临时翻译版」,★ 并且标死:
    #   ★★ 口径逐字来自 METHOD_LIBRARY/基-8.md 正文「怎么买」那一句,
    #      三个条件**全部无自由参数**(0.5 / 2 倍是原文给的数,不是我们拍的);
    #   ★★★ 它**没有预先登记**,所以只能用来数个数,
    #      ★ 不许进任何收益结论、不许当成上架版本。
    eps_yoy = _yoy_panel(syms, "eps")
    rev_yoy = _yoy_panel(syms, "rev")
    accel = OX.get("earnings_acceleration", syms)
    pe_ok = pe.where(pe > 0)
    mean_pe = pe_ok.mean(axis=1)
    garp = (eps_yoy.notna() & (eps_yoy > 0)
            & accel.notna() & (accel > 0.5)
            & rev_yoy.notna() & (rev_yoy >= eps_yoy)
            & pe_ok.notna()
            & pe_ok.ge(0.5 * mean_pe, axis=0)
            & pe_ok.le(2.0 * mean_pe, axis=0))
    out["8·GARP(临时翻译版)"] = fin(garp)

    # ---------------------------------------------- 9 龙头动量
    # ★ 出处:engine/configs/vcp_momentum.yaml ① 段
    #   ★★★ 行业 RS(mansfield against: SECTOR)这一条**本轮关掉** ——
    #     ★ engine 自己 raise 并要求「必须显式关掉并在报告里写明」(matrices.py:347-361),
    #       理由:仓库只有行业归属的**当前快照、非 PIT**,用它跑等于偷看未来。
    #     ★★ 本轮照它的要求显式关掉,★★★ 并在报告里写明「这一版关掉了行业 RS」。
    m_adv = matrices._universe_rule_mask(
        {"type": "adv_rank_exclude_bottom",
         "params": {"adv_period": 20, "exclude_bottom_pct": 20}}, syms, cal)
    m_rs = matrices._universe_rule_mask(
        {"type": "mansfield_rs_positive",
         "params": {"against": "SPY", "lookback": 250}}, syms, cal)
    out["9·龙头动量(关掉行业RS)"] = fin(_as_bool(m_adv) & _as_bool(m_rs))

    # ---------------------------------------------- 10 趋势跟随
    # ★ 出处:engine/configs/trend_following.yaml ① 段
    #   (adv_rank_exclude_bottom 20 + price_above_ma 200)
    m_ma = matrices._universe_rule_mask(
        {"type": "price_above_ma", "params": {"ma": 200}}, syms, cal)
    out["10·趋势跟随(唐奇安族选股面)"] = fin(_as_bool(m_adv) & _as_bool(m_ma))

    return out


def _yoy_panel(syms: list[str], which: str) -> pd.DataFrame:
    """EPS / 营收 的 TTM 同比增速(★ 基期 ≤ 0 一律 NaN,不猜方向)。"""
    cal = data.trading_calendar()
    cols = {}
    metric = "DilutedEPS" if which == "eps" else "Revenue"
    for s in syms:
        ser = F.ttm(s, metric)
        if not ser:
            cols[s] = pd.Series(np.nan, index=cal)
            continue
        v = pd.Series({o.period_end: o.value for o in ser}, dtype=float).sort_index()
        e = pd.Series({o.period_end: o.eff for o in ser}).sort_index()
        base = v.shift(4)
        y = ((v / base) - 1.0).where(v.notna() & (base > 0))
        cols[s] = F._to_daily(y, pd.to_datetime(e), cal)
    return pd.DataFrame(cols, index=cal)


# ══════════════════════════════════════════════════════════════════════════
# 四 · 六道闸的「可评估 / 触发剔除 / 算不出来」三件套
# ══════════════════════════════════════════════════════════════════════════

def gate_panels(syms: list[str], cal: pd.DatetimeIndex, scope: pd.DataFrame):
    """返回 (闸→(可评估, 触发剔除)), 诊断, Merton 面板, Merton 诊断,
    制造业掩膜, AltmanZ 原始面板(★ 最后两个给「算不出来」拆两类用)。"""
    g, diag = {}, {}

    # ① 利息覆盖 < 1
    d = G.get("int_cov", syms).reindex(index=cal, columns=syms)
    g[GATES[0]] = (d.notna() & scope, _as_bool(d < G.INTCOV_THRESHOLD) & scope)

    # ② Sloan 应计:★★ 池内横截面最高 10%(★★★ 排名法,不是静态线)
    d = G.get("sloan_accrual", syms).reindex(index=cal, columns=syms)
    # ★★★ 排名**只在在池、且算得出**的格子之间做 —— ★ 否则不在池的票会占掉名次。
    dd = d.where(scope)
    pct = dd.rank(axis=1, pct=True, na_option="keep")
    g[GATES[1]] = (dd.notna() & scope,
                   _as_bool(dd.notna() & (pct > 1.0 - G.SLOAN_TOP_PCT)) & scope)
    diag["②应计的排名口径"] = ("★★★ 截面最高 10% 是**在池内、且算得出**的那些票之间排的 —— "
                               "★ 算不出的票不参与排名(报告里留痕)。"
                               "★★ 这是原著的排名法,★★★ 所以它**结构上必然剔掉约 10%**。")

    # ③ Zmijewski > 50%
    d = G.get("zmij_prob", syms).reindex(index=cal, columns=syms)
    g[GATES[2]] = (d.notna() & scope, _as_bool(d > G.ZMIJEWSKI_P_THRESHOLD) & scope)

    # ④ Beneish M-Score > −1.78
    d = G.get("m_score", syms).reindex(index=cal, columns=syms)
    g[GATES[3]] = (d.notna() & scope, _as_bool(d > G.BENEISH_THRESHOLD) & scope)
    a7 = G.get("m_score_avail7", syms).reindex(index=cal, columns=syms)
    a4 = G.get("m_score_avail_dsri_gmi_sgi_tata", syms
               ).reindex(index=cal, columns=syms)
    diag["④ M-Score 可算性拆解"] = {
        "八项全齐(= 这道闸能用)的票·日": int((_as_bool(d.notna()) & scope).sum().sum()),
        "除 SGAI 外七项全齐的票·日": int((_as_bool(a7 > 0.5) & scope).sum().sum()),
        "不需要 PP&E / SG&A 的五项(DSRI·GMI·SGI·TATA·LVGI)全齐的票·日":
            int((_as_bool(a4 > 0.5) & scope).sum().sum()),
        "★★★ 读法": "★ 五项齐但八项不齐 → 卡住的就是**需要 PP&E 和 SG&A 的那三项**"
                     "(AQI · DEPI · SGAI)。★★ 这是「缺什么」的实测证据。",
    }

    # ⑤ Altman Z < 1.81(★★★ 只限上市制造业)
    num = G.get("altman_num", syms).reindex(index=cal, columns=syms)
    tl = G.get("altman_tl", syms).reindex(index=cal, columns=syms)
    mve = G.mktcap(syms).reindex(index=cal, columns=syms)
    z = num + G.ALTMAN_COEF["X4"] * (mve / tl)
    z = z.where(num.notna() & tl.notna() & mve.notna())
    manu = G.is_manufacturing(syms).reindex(index=cal, columns=syms).fillna(False)
    # ★★★ 非制造业 → **不适用** → 记「算不出来」,★ 不记通过、不记剔掉
    z_app = z.where(manu)
    g[GATES[4]] = (z_app.notna() & scope,
                   _as_bool(z_app < G.ALTMAN_THRESHOLD) & scope)
    diag["⑤ AltmanZ 的「算不出来」要拆两类"] = (
        "★★★ 一类是「**非制造业 → 不适用**」(SIC 不在 2000–3999),"
        "★ 一类是「制造业但科目缺」。★★ 下面逐策略表里分开报。")

    merton, mdiag = G.merton_distance_to_default(syms)
    merton = merton.reindex(index=cal, columns=syms)
    # ★★ 第二个违约点口径 = **总负债**(★ 和 Zmijewski 那道闸用的同一个科目)。
    #   ★★★ 为什么要跑第二个:主口径要 LongTermDebt,老库符号级覆盖率只有 54.4%,
    #   ★ 而总负债有 76.0% —— ★★ 两个口径并排,才看得出「算不出来」有多少是
    #   口径选择造成的、有多少是真缺数据。★★★ 两者都不当闸用。
    merton_tl, mdiag_tl = G.merton_distance_to_default(syms, "liab_total")
    merton_tl = merton_tl.reindex(index=cal, columns=syms)
    diag["⑥ Merton 两个违约点口径"] = {
        "主口径": mdiag["违约点口径"], "对照口径": mdiag_tl["违约点口径"],
        "★★★ 两个都不当闸用": "★ 只看分布和它会剔谁(照任务单)。",
    }
    return g, diag, merton, mdiag, manu, z, merton_tl


# ══════════════════════════════════════════════════════════════════════════
# 五 · 主表:每条策略 × 每道闸 剔掉几只
# ══════════════════════════════════════════════════════════════════════════

def count_table(screens: dict, gates: dict, merton: pd.DataFrame,
                manu: pd.DataFrame, z_all: pd.DataFrame,
                dates: list[pd.Timestamp]) -> dict:
    rows: dict[str, list[dict]] = {}
    for name, sc in screens.items():
        per = []
        for d in dates:
            cand = sc.loc[d]
            n0 = int(cand.sum())
            rec = {"调仓日": str(d.date()), "★不挂时几只": n0}
            dropped_any = pd.Series(False, index=cand.index)
            for gname in GATES:
                ev, tr = gates[gname]
                drop = cand & tr.loc[d]
                rec[f"{gname} 剔"] = int(drop.sum())
                if gname == GATES[4]:
                    # ★★ AltmanZ 的两列:算不出来拆成「非制造业不适用」/「制造业缺数」
                    nonmanu = int((cand & ~manu.loc[d]).sum())
                    manu_na = int((cand & manu.loc[d] & z_all.loc[d].isna()).sum())
                    rec["★★ AltmanZ算不出来(合计)"] = nonmanu + manu_na
                    rec["  └ 非制造业·不适用"] = nonmanu
                    rec["  └ 制造业但科目缺"] = manu_na
                else:
                    rec[f"{gname} 算不出来"] = int((cand & ~ev.loc[d]).sum())
                dropped_any = dropped_any | drop
            rec["★★★ 五道合起来剔"] = int(dropped_any.sum())
            rec["剩几只"] = n0 - int(dropped_any.sum())
            # ★★ 第六列:Merton(★★★ 本轮不当闸,只记「算得出几只 / 分布」)
            md = merton.loc[d][cand]
            rec["⑥Merton 算得出几只"] = int(md.notna().sum())
            rec["⑥Merton 中位数"] = (round(float(md.median()), 3)
                                     if md.notna().any() else None)
            per.append(rec)
        rows[name] = per
    return rows


def _agg(per: list[dict]) -> dict:
    """★ 把一条策略的 12 个调仓日加总(★★ 比例 = 合计剔 ÷ 合计不挂时只数)。"""
    tot0 = sum(r["★不挂时几只"] for r in per)
    tot_union = sum(r["★★★ 五道合起来剔"] for r in per)
    out = {"★12 个调仓日合计·不挂时只数": tot0,
           "★★★ 12 个调仓日合计·五道合起来剔": tot_union,
           "★★★ 五道合起来剔掉的比例%":
               (round(100.0 * tot_union / tot0, 2) if tot0 else None),
           "★ 平均每个调仓日·不挂时只数": round(tot0 / max(1, len(per)), 2),
           "★ 平均每个调仓日·剩几只":
               round(sum(r["剩几只"] for r in per) / max(1, len(per)), 2)}
    for gname in GATES:
        out[f"{gname} 合计剔"] = sum(r[f"{gname} 剔"] for r in per)
        out[f"{gname} 剔掉占不挂时%"] = (
            round(100.0 * out[f"{gname} 合计剔"] / tot0, 2) if tot0 else None)
    out["★★ AltmanZ算不出来 合计"] = sum(
        r["★★ AltmanZ算不出来(合计)"] for r in per)
    out["★★ AltmanZ算不出来 占不挂时%"] = (
        round(100.0 * out["★★ AltmanZ算不出来 合计"] / tot0, 2) if tot0 else None)
    out["  └ 非制造业·不适用 合计"] = sum(r["  └ 非制造业·不适用"] for r in per)
    out["  └ 制造业但科目缺 合计"] = sum(r["  └ 制造业但科目缺"] for r in per)
    for gname in GATES[:4]:
        out[f"{gname} 算不出来 合计"] = sum(r[f"{gname} 算不出来"] for r in per)
    return out


# ══════════════════════════════════════════════════════════════════════════
# 六 · F-Score(★ 只对深度价值类)+ 预言六的 ROA 对比
# ══════════════════════════════════════════════════════════════════════════

DEEP_VALUE = ("1·施洛斯极度分散", "2·低PE逆向", "3·收购者倍数", "5·Net-Net")
#: ★★ 预言六说的是「质量成长」—— 本池里能跑的质量成长只有 GARP 这一条
QUALITY_GROWTH = ("8·GARP(临时翻译版)",)


def fscore_section(screens: dict, syms: list[str], cal, scope,
                   dates: list[pd.Timestamp]) -> dict:
    fs = F.get("f_score", syms).reindex(index=cal, columns=syms)
    av = F.get("f_score_available", syms).reindex(index=cal, columns=syms)
    roa = G.get("roa_piotroski", syms).reindex(index=cal, columns=syms)
    out = {
        "★口径": "★ engine/fundamentals.py 原生 `f_score`(★★ 9 项必须全算得出,"
                 "否则 NaN)—— ★★★ engine 一个字节没改,直接调用。",
        "★★门槛为什么跑两个": "★★★ engine/configs/deep_value.yaml 自己登记的审计结论:"
                              "原文主组合是 **8–9 对 0–1**,「≥5」是第 5 节稳健性检验里的数、"
                              "不是主口径 → ★ 红线②:两个门槛并排,不挑一个。",
        "★ROA 口径": "净利润_TTM ÷ **期初**总资产 —— ★★ 和 engine 的 F-Score "
                      "自己用的那个 ROA **完全同一个口径**(engine/fundamentals.py:351),"
                      "★★★ 这样对比不会变成口径差。",
        "逐策略": {},
        "★★★预言六检验": {},
    }
    for name in DEEP_VALUE + QUALITY_GROWTH:
        sc = screens.get(name)
        if sc is None:
            continue
        per = []
        for d in dates:
            cand = sc.loc[d]
            n0 = int(cand.sum())
            rec = {"调仓日": str(d.date()), "★不挂时几只": n0,
                   "★★ F-Score算不出来":
                       int((cand & ~_as_bool(av.loc[d] > 0.5)).sum())}
            for th in FSCORE_THRESHOLDS:
                keep = cand & _as_bool(fs.loc[d] >= th)
                drop = cand & _as_bool(fs.loc[d].notna() & (fs.loc[d] < th))
                rec[f"F≥{th:.0f} 剔"] = int(drop.sum())
                rec[f"F≥{th:.0f} 剩"] = int(keep.sum())
            per.append(rec)
        out["逐策略"][name] = per

    # ★★★ 预言六:被 F-Score 剔掉的那批 vs 留下的那批,比 ROA 中位数
    for th in FSCORE_THRESHOLDS:
        scopes = {"★全研发池(在池 & F-Score 算得出)": scope}
        for name in QUALITY_GROWTH + DEEP_VALUE:
            if name in screens:
                scopes[name] = screens[name]
        res = {}
        for lbl, mask in scopes.items():
            dr, kp = [], []
            for d in dates:
                m = mask.loc[d] & _as_bool(av.loc[d] > 0.5)
                f_, r_ = fs.loc[d], roa.loc[d]
                dr.extend(r_[m & (f_ < th)].dropna().tolist())
                kp.extend(r_[m & (f_ >= th)].dropna().tolist())
            res[lbl] = {
                "被剔掉那批·只数(票·调仓日)": len(dr),
                "被剔掉那批·ROA中位数": round(float(np.median(dr)), 4) if dr else None,
                "留下那批·只数(票·调仓日)": len(kp),
                "留下那批·ROA中位数": round(float(np.median(kp)), 4) if kp else None,
                "★★★ 被剔掉那批的 ROA 中位数 > 留下那批?":
                    (bool(np.median(dr) > np.median(kp)) if dr and kp else None),
            }
        out["★★★预言六检验"][f"门槛 F≥{th:.0f}"] = res
    return out


# ══════════════════════════════════════════════════════════════════════════
# 七 · 附表一:按板块统计被剔掉的只数(★ 用 sic_versions,★★ 按时点取)
# ══════════════════════════════════════════════════════════════════════════

def sector_table(screens: dict, gates: dict, syms: list[str],
                 dates: list[pd.Timestamp]) -> dict:
    sic = G.sic_panel(syms)
    out: dict[str, dict] = {}
    union_cols = {}
    for name, sc in screens.items():
        cnt: dict[str, dict] = {}
        for d in dates:
            cand = sc.loc[d]
            if not cand.any():
                continue
            codes = sic.loc[d]
            dropped = pd.Series(False, index=cand.index)
            for gname in GATES:
                dropped = dropped | (cand & gates[gname][1].loc[d])
            for s in cand.index[cand]:
                div = G.sic_division_name(codes.get(s, np.nan))
                e = cnt.setdefault(div, {"候选票·调仓日": 0, "被剔掉": 0})
                e["候选票·调仓日"] += 1
                e["被剔掉"] += int(bool(dropped[s]))
        for div, e in cnt.items():
            e["剔掉比例%"] = (round(100.0 * e["被剔掉"] / e["候选票·调仓日"], 2)
                              if e["候选票·调仓日"] else None)
        out[name] = dict(sorted(cnt.items(), key=lambda x: -x[1]["被剔掉"]))
        union_cols[name] = None
    out["★口径"] = ("★★ SIC 按**时点**取(每个版本用 `observed_from` + 1 个交易日生效,"
                    "★★★ 第一版生效之前是 NaN —— **绝不拿最新版本回填历史**)。"
                    "★ 没有 SIC 的格子单独列成一行,不并进任何板块。")
    return out


# ══════════════════════════════════════════════════════════════════════════
# 八 · 附表二:★★★ 被误杀名单(净资产为负、但经营现金流为正)
# ══════════════════════════════════════════════════════════════════════════

def miskill_list(syms: list[str], cal, scope, gates: dict, merton: pd.DataFrame,
                 manu: pd.DataFrame, z_all: pd.DataFrame,
                 screens: dict, dates: list[pd.Timestamp],
                 merton_tl: pd.DataFrame) -> dict:
    eq = G.get("equity", syms).reindex(index=cal, columns=syms)
    ocf = G.get("ocf_ttm", syms).reindex(index=cal, columns=syms)
    sic = G.sic_panel(syms).reindex(index=cal, columns=syms)
    rows = []
    by_sym: dict[str, set] = {}
    for d in dates:
        m = scope.loc[d] & (eq.loc[d] < 0) & (ocf.loc[d] > 0)
        for s in m.index[m.fillna(False)]:
            hit = [gname for gname in GATES if bool(gates[gname][1].loc[d, s])]
            na = [gname for gname in GATES if not bool(gates[gname][0].loc[d, s])]
            in_strats = [nm for nm, sc in screens.items() if bool(sc.loc[d, s])]
            rows.append({
                "代码": s, "年份": int(d.year), "调仓日": str(d.date()),
                "净资产": round(float(eq.loc[d, s]), 0),
                "经营现金流_TTM": round(float(ocf.loc[d, s]), 0),
                "SIC(按时点)": (int(sic.loc[d, s])
                                 if np.isfinite(sic.loc[d, s]) else None),
                "是制造业(AltmanZ 适用)": bool(manu.loc[d, s]),
                "★★★ 被哪几道闸剔掉": hit or ["(一道都没剔)"],
                "★★ 哪几道闸算不出来": na or ["(都算得出)"],
                "★ AltmanZ 原始值":
                    (round(float(z_all.loc[d, s]), 3)
                     if np.isfinite(z_all.loc[d, s]) else None),
                "★★★ Merton 违约距离(主口径·KMV违约点)":
                    (round(float(merton.loc[d, s]), 3)
                     if np.isfinite(merton.loc[d, s]) else None),
                "★★ Merton 违约距离(对照口径·总负债)":
                    (round(float(merton_tl.loc[d, s]), 3)
                     if np.isfinite(merton_tl.loc[d, s]) else None),
                "★ 这一天进了哪几条策略的候选": in_strats or ["(没进任何一条)"],
            })
            by_sym.setdefault(s, set()).add(int(d.year))
    return {
        "★口径": "★★★ **净资产(StockholdersEquity)< 0 且 经营现金流_TTM > 0**,"
                 "★ 在池(大+中)且在 12 个调仓日上。"
                 "★★ 两项都必须算得出 —— 缺一项不算进名单(不猜)。",
        "★★★ 去重后几只": len(by_sym),
        "★ 逐只(代码 → 年份)": {s: sorted(y) for s, y in sorted(by_sym.items())},
        "★ 票·调仓日条数": len(rows),
        "逐条": rows,
    }


# ══════════════════════════════════════════════════════════════════════════
# 九 · ★★★ Merton vs Altman:那批「净资产为负但现金流为正」的公司
# ══════════════════════════════════════════════════════════════════════════

def _dist(arr: np.ndarray, qs=(1, 5, 10, 25, 50, 75, 90, 95, 99)) -> dict:
    if not arr.size:
        return {}
    return {f"p{q}": round(float(np.percentile(arr, q)), 3) for q in qs}


def merton_vs_altman(mis: dict, merton: pd.DataFrame, merton_tl: pd.DataFrame,
                     z_all: pd.DataFrame, syms: list[str], cal, scope,
                     dates: list[pd.Timestamp]) -> dict:
    # ★ 全池分布(★★ 阈值不定,只给分布 —— 照任务单)
    def pool_vals(pan: pd.DataFrame) -> np.ndarray:
        vals = []
        for d in dates:
            vals.extend(pan.loc[d][scope.loc[d]].dropna().tolist())
        return np.asarray(vals, dtype=float)

    arr, arr_tl = pool_vals(merton), pool_vals(merton_tl)
    n_cells = int(sum(int(scope.loc[d].sum()) for d in dates))

    sub = mis.get("逐条") or []
    key, key_tl = ("★★★ Merton 违约距离(主口径·KMV违约点)",
                   "★★ Merton 违约距离(对照口径·总负债)")
    mv = [r[key] for r in sub if r[key] is not None]
    mv_tl = [r[key_tl] for r in sub if r[key_tl] is not None]
    zv = [r["★ AltmanZ 原始值"] for r in sub if r["★ AltmanZ 原始值"] is not None]
    manu_sub = [r for r in sub if r["是制造业(AltmanZ 适用)"]]
    z_kill = [r for r in manu_sub if r["★ AltmanZ 原始值"] is not None
              and r["★ AltmanZ 原始值"] < G.ALTMAN_THRESHOLD]
    return {
        "★★★ 全池 Merton 违约距离分布(12 个调仓日 × 在池票)": {
            "在池票·调仓日总格子数": n_cells,
            "主口径(KMV违约点)": {
                "算得出的格子数": int(arr.size),
                "可算率%": round(100.0 * arr.size / max(1, n_cells), 1),
                "分位数": _dist(arr),
                "最小": round(float(arr.min()), 3) if arr.size else None,
                "最大": round(float(arr.max()), 3) if arr.size else None,
                "★★ 负值(= 已在违约点以下)占比%":
                    (round(100.0 * float((arr < 0).mean()), 2) if arr.size else None),
            },
            "对照口径(总负债)": {
                "算得出的格子数": int(arr_tl.size),
                "可算率%": round(100.0 * arr_tl.size / max(1, n_cells), 1),
                "分位数": _dist(arr_tl),
                "最小": round(float(arr_tl.min()), 3) if arr_tl.size else None,
                "最大": round(float(arr_tl.max()), 3) if arr_tl.size else None,
                "★★ 负值占比%": (round(100.0 * float((arr_tl < 0).mean()), 2)
                                 if arr_tl.size else None),
            },
            "★★★ 阈值": "★ **本轮没有定阈值** —— 照任务单只给分布。",
        },
        "★★★ 误杀名单那批的 Merton": {
            "名单条数(票·调仓日)": len(sub),
            "主口径算得出的条数": len(mv),
            "主口径·它们的分位数": _dist(np.asarray(mv, dtype=float),
                                        (10, 25, 50, 75, 90)) if mv else {},
            "★★ 主口径·它们的中位数 落在全池哪个分位":
                (round(float((arr < np.median(mv)).mean() * 100.0), 1)
                 if mv and arr.size else None),
            "对照口径算得出的条数": len(mv_tl),
            "对照口径·它们的分位数": _dist(np.asarray(mv_tl, dtype=float),
                                          (10, 25, 50, 75, 90)) if mv_tl else {},
            "★★ 对照口径·它们的中位数 落在全池哪个分位":
                (round(float((arr_tl < np.median(mv_tl)).mean() * 100.0), 1)
                 if mv_tl and arr_tl.size else None),
        },
        "★★★ 同一批票 Altman 怎么判": {
            "其中是制造业(AltmanZ 才适用)的条数": len(manu_sub),
            "★★ 非制造业 → AltmanZ 不适用的条数": len(sub) - len(manu_sub),
            "制造业里 AltmanZ 算得出的条数": len(zv),
            "★★★ 制造业里被 AltmanZ < 1.81 剔掉的条数": len(z_kill),
            "它们的 AltmanZ 中位数":
                (round(float(np.median(zv)), 3) if zv else None),
        },
        "★★★ 怎么读(大白话)":
            "★ Altman 的 X2 是「留存收益 ÷ 总资产」、X1 是「营运资本 ÷ 总资产」——"
            "★★ 一家把钱全拿去回购的公司,留存收益和净资产会是**负的**,"
            "★★★ 这两项直接把 Z 拉到安全线以下,**哪怕它每年现金流很好**。"
            "★ Merton 不看这两项,它只看「市值还剩多厚、股价抖不抖、欠多少」——"
            "★★ 所以只要市场还给这家公司一个像样的市值,Merton 就不会判它危险。"
            "★★★ 上面三组数就是在量这件事,★ 阈值没定,所以**不下「谁对谁错」的结论**。",
    }


# ══════════════════════════════════════════════════════════════════════════


def _num(x):
    if isinstance(x, dict):
        return {str(k): _num(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_num(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return None if not np.isfinite(float(x)) else float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, float):
        return None if not np.isfinite(x) else x
    return x


def main() -> int:
    t0 = time.time()
    sha_before = sha_of_manifest()

    man = data.load_manifest()
    have_px = set(cache.symbols())
    # ★★★ 只用研发池那 250 只(有财报 + 有行情)—— ★ 和 probe/expand_run_1104 逐行一致
    syms = [s for s in sorted(man) if man[s].fundamentals_path and s in have_px]
    cal = data.trading_calendar()
    _sm, _ = RC.scope_mask(syms, cal, SCOPE)
    scope = pd.DataFrame(_sm, index=cal, columns=syms)
    dates = rebalance_dates(cal)

    proof = exam_untouched_proof(syms)

    (gates, gdiag, merton, mdiag, manu, z_all,
     merton_tl) = gate_panels(syms, cal, scope)
    screens = strategy_screens(syms, cal, scope)

    table = count_table(screens, gates, merton, manu, z_all, dates)
    agg = {k: _agg(v) for k, v in table.items()}
    fsec = fscore_section(screens, syms, cal, scope, dates)
    sect = sector_table(screens, gates, syms, dates)
    mis = miskill_list(syms, cal, scope, gates, merton, manu, z_all,
                       screens, dates, merton_tl)
    mva = merton_vs_altman(mis, merton, merton_tl, z_all, syms, cal,
                           scope, dates)

    cov = G.raw_coverage(syms, ("oil_ttm", "ppe_pt", "sga_ttm", "equity",
                                "ocf_ttm", "altman_num", "altman_tl",
                                "int_cov", "sloan_accrual", "zmij_prob",
                                "m_score", "debt_face_kmv"))

    # ★ 全池在池只数(给分母用)
    pool_per_date = {str(d.date()): int(scope.loc[d].sum()) for d in dates}

    sha_after = sha_of_manifest()
    out = {
        "跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "★★★ 这一轮只做什么": "★ **只数个数** —— 没有回测、没有流水、"
                               "没有 R、没有胜率、没有任何收益数字。",
        "窗口": f"{DEV[0]} .. {DEV[1]}(研发池)",
        "池子口径": f"{SCOPE}(大+中,成交额排名 1–2000)",
        "回测票池只数": len(syms),
        "调仓日": [str(d.date()) for d in dates],
        "★调仓日口径": rebalance_dates.__doc__,
        "每个调仓日在池只数": pool_per_date,
        "★★★库冻结窗口": {
            "跑前": sha_before, "跑后": sha_after,
            "两次一致": sha_before == sha_after,
            "跑前值和预先登记写死的一致": sha_before == EXPECTED_SHA,
            "预先登记写死的值": EXPECTED_SHA,
        },
        "★★★考卷未碰自证": proof,
        "★★★数据覆盖层": "★ **一个都没挂** —— `data.load_fundamentals` 原封不动。"
                          "★★ 特别是**没有**调用 ops_fund_1030.install()"
                          "(它默认会整列替换 EBIT / 长期负债)。"
                          "★★★ 所以本轮 EBIT = 老库原生的派生值(税前利润 + 利息费用),"
                          "★ 这一处跟着每个数走。",
        "★★★engine 零改动": "★ 本轮**连派发函数都没替换** —— 只 import 和调用,"
                             "★★ 唯一的运行时动作是往 FLOW_METRICS / STOCK_METRICS "
                             "里 add 三个科目名(PP&E / SG&A / 营业利润),"
                             "★★★ 这是**显式声明口径**,engine 文件本身一个字节没改。",
        "★算子备注": G.notes(),
        "★★★跑不了的策略(照实登记)": CANNOT_RUN,
        "★★原始科目覆盖率(「缺什么」的实测证据)": cov,
        "★闸门诊断": gdiag,
        "★Merton 诊断": mdiag,
        "★★★一·主表逐调仓日": table,
        "★★★一b·主表合计": agg,
        "★★★二·F-Score 与预言六": fsec,
        "★★★三-1·附表一 按板块": sect,
        "★★★三-2·附表二 被误杀名单": mis,
        "★★★四·Merton vs Altman": mva,
        "耗时秒": round(time.time() - t0, 1),
    }
    os.makedirs(HERE, exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:          # ★ 先写文件
        json.dump(_num(out), fh, ensure_ascii=False, indent=2, default=str)
    try:                                                        # ★ 再打印
        print(f"★ 写了:{OUT_JSON}")
        print(f"★ 库指纹 跑前={sha_before[:8]} 跑后={sha_after[:8]} "
              f"一致={sha_before == sha_after}")
        print(f"★ exam_1042 命中数 = {proof['★★★ exam_1042 路径命中数']}")
        print(f"★ 调仓日 {len(dates)} 个;策略 {len(screens)} 条可跑,"
              f"{len(CANNOT_RUN)} 条跑不了")
        for k, v in agg.items():
            print(f"  {k:34s} 不挂={v['★12 个调仓日合计·不挂时只数']:5d} "
                  f"五道合起来剔={v['★★★ 12 个调仓日合计·五道合起来剔']:5d} "
                  f"({v['★★★ 五道合起来剔掉的比例%']}%)")
        print(f"★ 误杀名单去重后 {mis['★★★ 去重后几只']} 只 / "
              f"{mis['★ 票·调仓日条数']} 条")
        print(f"★ 耗时 {out['耗时秒']}s")
    except Exception as e:
        print(f"(打印出错,结果已写出:{type(e).__name__}: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
