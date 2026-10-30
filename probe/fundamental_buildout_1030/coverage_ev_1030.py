#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ EV/EBITDA 覆盖率的上限在哪 —— 逐只票记清「用了哪个字段、算的是哪个口径」

三秒版:记录里写「EV/EBITDA 算不出」。本文件把覆盖率推到**能推的上限**,
        并且**不混口径** —— 三档口径分开报,每只票记下它是靠哪个字段算出来的。

══════════════════════════════════════════════════════════════════════════
★★★ 三档口径的定义(★ 跑之前定稿,跑完不改)
══════════════════════════════════════════════════════════════════════════
    EV = 股权市值代理 + 债务 − 现金
    EBITDA = EBIT + 折旧摊销
  ★ 股权市值代理 = 摊薄股数(过完 share_gate 三道闸) × 当日收盘价。
    ★★ 这**不是 PIT 市值**(README 明说仓库没有 PIT 市值)—— 是规模代理。
       三档口径都用同一个代理,所以档位之间的差只来自债务 / 折旧摊销。

  口径 S(严格):债务 = LongTermDebt;折旧摊销 = DepreciationDepletionAndAmortization
     ★ = 只用首选字段,等价于记录里那个 34.8% 的口径。

  口径 M(放宽 · 同义字段):
     债务 = Σ(LongTermDebt, LongTermDebtCurrent, ShortTermBorrowings, DebtCurrent)
            —— ★ 只要**至少一项**有值就算得出,有值的相加、没值的当 0。
     折旧摊销 = DepreciationDepletionAndAmortization
                ↓ 缺则落到 DepreciationAmortizationAndAccretionNet
     ★★ 这一档是「同义字段替代」,口径**仍然是净债**,★ 但有一处必须承认的失真:
        「没值的当 0」= 假设该公司没有这一类债务。对短期借款这类科目,
        不报和为零在 SEC 口径里确实常常是同一件事(没有就不报),
        ★ 但我们**无法区分**「真没有」和「报在别的标签里」。
        → 所以本档每只票都记下 `债务用到的字段清单`,报告里逐只可查。

  口径 L(最宽 · ★ 口径已经变了,不是同义替代):
     债务 = Liabilities(**总负债**,含应付、递延、租赁、准备金……)
     ★★★ 这不是净债。用它算出来的东西**不叫 EV/EBITDA**,
        它系统性地把 EV 做大(方向单一、不是噪声)。
     ★ 本档只用来回答「如果愿意换口径,覆盖率能到多少」,
       ★★ **不许**拿它的数去装原著那条「EV/EBITDA 后 20% / 修复至前 40%」。

★ EBITDA 的卡点:EBIT(派生 = IncomeBeforeTax + InterestExpense,仓库已派生好)
  和折旧摊销的**交集**。本文件把两边分开报,这样「买数据该买哪个」是明确的。

★ PIT:全部走 engine.fundamentals(filing_date+1 交易日 / YTD 差分还原 /
  同期只留首发版)—— ★ engine 一个字符没改。
★ 「天」一律是交易日。
跑法:python3 probe/fundamental_buildout_1030/coverage_ev_1030.py
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import cache, data, fundamentals  # noqa: E402

OUT_JSON = os.path.join(HERE, "coverage_ev_1030.json")
OUT_CSV = os.path.join(HERE, "逐只票-EV_EBITDA口径与字段-1030.csv")

#: ★ 断面日 —— 照抄 deep_value.yaml 注释里用的那三个,便于逐项对差
SECTIONS = ("2018-06-30", "2022-06-30", "2025-06-30")

DEBT_S = ("LongTermDebt",)
DEBT_M = ("LongTermDebt", "LongTermDebtCurrent", "ShortTermBorrowings",
          "DebtCurrent")
DA_S = ("DepreciationDepletionAndAmortization",)
DA_M = ("DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet")


def _ser(sym: str, metric: str, kind: str) -> pd.Series:
    """某科目的季度序列(存量)或 TTM 序列(流量),索引 = period_end。"""
    obs = (fundamentals.ttm(sym, metric) if kind == "ttm"
           else fundamentals.quarterly(sym, metric))
    if not obs:
        return pd.Series(dtype=float)
    return pd.Series({o.period_end: o.value for o in obs}).sort_index()


def _eff(sym: str, metric: str, kind: str) -> pd.Series:
    obs = (fundamentals.ttm(sym, metric) if kind == "ttm"
           else fundamentals.quarterly(sym, metric))
    if not obs:
        return pd.Series(dtype="datetime64[ns]")
    return pd.Series({o.period_end: o.eff for o in obs}).sort_index()


def per_symbol(sym: str, cal: pd.DatetimeIndex) -> dict:
    """★ 一只票的三档口径结果 + 用到的字段 —— 逐只可查,不汇总掉。"""
    out: dict = {"symbol": sym}

    # ---- 分子分母的零件,每个都记「有多少个季度有值」
    parts: dict[str, pd.Series] = {}
    effs: dict[str, pd.Series] = {}
    for metric, kind in (("EBIT", "ttm"),
                         ("DepreciationDepletionAndAmortization", "ttm"),
                         ("DepreciationAmortizationAndAccretionNet", "ttm"),
                         ("LongTermDebt", "pt"),
                         ("LongTermDebtCurrent", "pt"),
                         ("ShortTermBorrowings", "pt"),
                         ("DebtCurrent", "pt"),
                         ("Liabilities", "pt"),
                         ("CashAndCashEquivalentsAtCarryingValue", "pt")):
        parts[metric] = _ser(sym, metric, kind)
        effs[metric] = _eff(sym, metric, kind)
        out[f"季度数_{metric}"] = int(parts[metric].notna().sum())

    sh = fundamentals.shares_quarterly(sym)
    shares = pd.Series({o.period_end: o.value for o in sh}).sort_index() if sh \
        else pd.Series(dtype=float)
    shares_eff = pd.Series({o.period_end: o.eff for o in sh}).sort_index() if sh \
        else pd.Series(dtype="datetime64[ns]")
    out["季度数_摊薄股数"] = int(shares.notna().sum())

    idx = sorted({pe for s in list(parts.values()) + [shares] for pe in s.index})
    if not idx:
        out["任一档可算_季度数"] = 0
        return out
    idx = pd.DatetimeIndex(idx)

    def al(s: pd.Series) -> pd.Series:
        return s.reindex(idx) if len(s) else pd.Series(np.nan, index=idx)

    ebit = al(parts["EBIT"])
    dda = al(parts["DepreciationDepletionAndAmortization"])
    daan = al(parts["DepreciationAmortizationAndAccretionNet"])
    cash = al(parts["CashAndCashEquivalentsAtCarryingValue"])
    shq = al(shares)

    # ---- 折旧摊销:两档
    da_s = dda
    da_m = dda.copy()
    da_m_src = pd.Series(np.where(dda.notna(), "DDA",
                                  np.where(daan.notna(), "DAAN", "")), index=idx)
    m = dda.isna() & daan.notna()
    da_m[m] = daan[m]

    # ---- 债务:三档。★ M 档 = 有值的相加(至少一项有值),没值的当 0
    debt_s = al(parts["LongTermDebt"])
    cols_m = {k: al(parts[k]) for k in DEBT_M}
    any_m = pd.concat(cols_m.values(), axis=1).notna().any(axis=1)
    debt_m = pd.concat(cols_m.values(), axis=1).sum(axis=1, min_count=1)
    debt_m = debt_m.where(any_m)
    debt_m_src = pd.Series(
        ["+".join(k for k, v in cols_m.items() if pd.notna(v.iloc[i])) or ""
         for i in range(len(idx))], index=idx)
    debt_l = al(parts["Liabilities"])

    # ---- EBITDA 两档
    ebitda_s = (ebit + da_s).where(ebit.notna() & da_s.notna())
    ebitda_m = (ebit + da_m).where(ebit.notna() & da_m.notna())

    # ---- EV 三档(股权腿:股数有值即算得出;价格在断面上取)
    ev_ok_s = shq.notna() & debt_s.notna() & cash.notna()
    ev_ok_m = shq.notna() & debt_m.notna() & cash.notna()
    ev_ok_l = shq.notna() & debt_l.notna() & cash.notna()

    ok_s = ev_ok_s & ebitda_s.notna()
    ok_m = ev_ok_m & ebitda_m.notna()
    ok_l = ev_ok_l & ebitda_m.notna()

    out.update({
        "季度数_EBITDA_严格": int(ebitda_s.notna().sum()),
        "季度数_EBITDA_放宽": int(ebitda_m.notna().sum()),
        "季度数_EV_严格": int(ev_ok_s.sum()),
        "季度数_EV_放宽": int(ev_ok_m.sum()),
        "季度数_EV_总负债档": int(ev_ok_l.sum()),
        "季度数_EVEBITDA_严格": int(ok_s.sum()),
        "季度数_EVEBITDA_放宽": int(ok_m.sum()),
        "季度数_EVEBITDA_总负债档": int(ok_l.sum()),
        "折旧摊销_用的字段": "/".join(sorted(set(x for x in da_m_src if x))) or "(无)",
        "债务_用到的字段": "/".join(sorted(set(
            f for x in debt_m_src for f in x.split("+") if f))) or "(无)",
        "EBIT有值但折旧摊销缺_季度数": int((ebit.notna() & da_m.isna()).sum()),
        "折旧摊销有值但EBIT缺_季度数": int((da_m.notna() & ebit.isna()).sum()),
    })

    # ---- 断面上的可算性(用生效日口径:断面那天看得到的最近一期)
    def ale(s: pd.Series) -> pd.Series:
        """★ 生效日序列专用对齐 —— 空序列也必须是 datetime64 dtype,
        否则下面的 max(axis=1) 会在 float(NaN) 和 Timestamp 之间比大小而报错。"""
        base = pd.Series(pd.NaT, index=idx, dtype="datetime64[ns]")
        if len(s):
            base.loc[s.index.intersection(idx)] = pd.to_datetime(
                s.reindex(s.index.intersection(idx)))
        return base

    eff_all = {
        "EBIT": ale(effs["EBIT"]),
        "DDA": ale(effs["DepreciationDepletionAndAmortization"]),
        "DAAN": ale(effs["DepreciationAmortizationAndAccretionNet"]),
        "LTD": ale(effs["LongTermDebt"]),
        "LTDC": ale(effs["LongTermDebtCurrent"]),
        "STB": ale(effs["ShortTermBorrowings"]),
        "DC": ale(effs["DebtCurrent"]),
        "LIAB": ale(effs["Liabilities"]),
        "CASH": ale(effs["CashAndCashEquivalentsAtCarryingValue"]),
        "SH": ale(shares_eff),
    }

    def visible(ok: pd.Series, eff_cols: list[str], asof: pd.Timestamp) -> bool:
        """★ 这一天看得到的最近一期里,这一档算不算得出。"""
        e = pd.concat([eff_all[c] for c in eff_cols], axis=1).max(axis=1)
        vis = ok & e.notna() & (pd.to_datetime(e) <= asof)
        return bool(vis.any())

    for d in SECTIONS:
        ts = pd.Timestamp(d)
        out[f"断面{d}_严格"] = visible(ok_s, ["EBIT", "DDA", "LTD", "CASH", "SH"], ts)
        out[f"断面{d}_放宽"] = visible(ok_m, ["EBIT", "DDA", "DAAN", "LTD", "LTDC",
                                              "STB", "DC", "CASH", "SH"], ts)
        out[f"断面{d}_总负债档"] = visible(ok_l, ["EBIT", "DDA", "DAAN", "LIAB",
                                                  "CASH", "SH"], ts)
    out["任一档可算_季度数"] = int((ok_s | ok_m | ok_l).sum())
    return out


def main() -> int:
    man = data.load_manifest()
    syms = [s for s in sorted(man) if man[s].fundamentals_path]
    have_px = set(cache.symbols())
    cal = data.trading_calendar()
    print(f"有 fundamentals.json 的票 {len(syms)} 只;其中有价格缓存的 "
          f"{len([s for s in syms if s in have_px])} 只")

    rows = []
    for i, s in enumerate(syms):
        rows.append(per_symbol(s, cal))
        if (i + 1) % 50 == 0:
            print(f"  ...{i+1}/{len(syms)}")
    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    n = len(df)
    summary = {
        "票数": n,
        "★ 口径定义": {
            "S_严格": "债务=LongTermDebt;折旧摊销=DepreciationDepletionAndAmortization",
            "M_放宽同义": "债务=Σ(LongTermDebt,LongTermDebtCurrent,ShortTermBorrowings,"
                          "DebtCurrent) 至少一项有值;折旧摊销=DDA→DAAN 回落",
            "L_总负债": "★★ 债务=Liabilities(总负债)—— 口径已改变,不是净债,"
                        "不许用来装原著那条分位闸",
            "股权腿": "★ 摊薄股数 × 收盘价 = 规模代理,不是 PIT 市值",
        },
        "★ 整段窗口内至少有一个季度算得出的票数": {
            "EV_EBITDA_严格": int((df["季度数_EVEBITDA_严格"] > 0).sum()),
            "EV_EBITDA_放宽": int((df["季度数_EVEBITDA_放宽"] > 0).sum()),
            "EV_EBITDA_总负债档": int((df["季度数_EVEBITDA_总负债档"] > 0).sum()),
            "EBITDA_严格": int((df["季度数_EBITDA_严格"] > 0).sum()),
            "EBITDA_放宽": int((df["季度数_EBITDA_放宽"] > 0).sum()),
            "EV_严格": int((df["季度数_EV_严格"] > 0).sum()),
            "EV_放宽": int((df["季度数_EV_放宽"] > 0).sum()),
            "EV_总负债档": int((df["季度数_EV_总负债档"] > 0).sum()),
            "EBIT": int((df["季度数_EBIT"] > 0).sum()),
            "折旧摊销_DDA": int((df["季度数_DepreciationDepletionAndAmortization"] > 0).sum()),
            "折旧摊销_DAAN": int((df["季度数_DepreciationAmortizationAndAccretionNet"] > 0).sum()),
            "LongTermDebt": int((df["季度数_LongTermDebt"] > 0).sum()),
            "LongTermDebtCurrent": int((df["季度数_LongTermDebtCurrent"] > 0).sum()),
            "ShortTermBorrowings": int((df["季度数_ShortTermBorrowings"] > 0).sum()),
            "DebtCurrent": int((df["季度数_DebtCurrent"] > 0).sum()),
            "Liabilities": int((df["季度数_Liabilities"] > 0).sum()),
            "Cash": int((df["季度数_CashAndCashEquivalentsAtCarryingValue"] > 0).sum()),
            "摊薄股数": int((df["季度数_摊薄股数"] > 0).sum()),
        },
        "★ 断面覆盖率(票数 / 250)": {
            d: {
                "严格": int(df[f"断面{d}_严格"].sum()),
                "放宽": int(df[f"断面{d}_放宽"].sum()),
                "总负债档": int(df[f"断面{d}_总负债档"].sum()),
            } for d in SECTIONS
        },
        "★ 卡点拆解(整段窗口)": {
            "EBIT 有值但折旧摊销一期都没有的票": int(
                ((df["季度数_EBIT"] > 0) & (df["季度数_EBITDA_放宽"] == 0)).sum()),
            "折旧摊销有值但 EBIT 一期都没有的票": int(
                ((df["季度数_DepreciationDepletionAndAmortization"]
                  + df["季度数_DepreciationAmortizationAndAccretionNet"] > 0)
                 & (df["季度数_EBIT"] == 0)).sum()),
            "两个都没有的票": int(
                ((df["季度数_EBIT"] == 0)
                 & (df["季度数_DepreciationDepletionAndAmortization"] == 0)
                 & (df["季度数_DepreciationAmortizationAndAccretionNet"] == 0)).sum()),
        },
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(summary, fh, ensure_ascii=False, indent=2)
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    print(f"\n逐只票明细:{OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
