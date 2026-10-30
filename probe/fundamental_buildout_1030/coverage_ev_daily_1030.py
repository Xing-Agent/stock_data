#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ EV/EBITDA 覆盖率 —— **按引擎真实口径**(日频面板 + ffill)再量一遍

三秒版:上一个脚本(coverage_ev_1030.py)按「同一个 period_end 行上几个科目都要有值」
        来算,★ 那比引擎实际的做法严 —— 引擎是**每个科目各自摊成日频再 ffill**,
        不同科目的公布时点可以不一样。本脚本按引擎的真口径量,这才是
        「这道闸装上去那天实际有多少票算得出」。

★★ 三个层级的覆盖率必须分开报(这一轮新发现的一处记法错误):
     层一 字段有记录   —— fundamentals.json 里这个科目有没有数据
     层二 还原出单季   —— 过了 YTD 差分 + 75~110 天区间检查
     层三 滚出 TTM     —— ★ 要求最近 4 季 period_end 间隔 70~120 天(连续)
   ★★★ 任务单给的 EBIT 177 / 折旧摊销 174 是**层一**的数。
        实测层三:EBIT 150 / 折旧摊销 150 —— ★ 卡掉我们的不只是「字段缺」,
        还有**我们自己那道 TTM 连续性要求**。两者要分开算账。

★ 口径 S / M / L 的定义照抄 coverage_ev_1030.py,一个字没改。
★ PIT 全部走 engine.fundamentals(engine 一个字符没改)。
★ 「天」一律是交易日。
跑法:python3 probe/fundamental_buildout_1030/coverage_ev_daily_1030.py
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

OUT_JSON = os.path.join(HERE, "coverage_ev_daily_1030.json")
OUT_CSV = os.path.join(HERE, "逐只票-EV_EBITDA日频口径-1030.csv")
SECTIONS = ("2018-06-30", "2022-06-30", "2025-06-30")

STOCK = {"LongTermDebt", "LongTermDebtCurrent", "ShortTermBorrowings",
         "DebtCurrent", "Liabilities", "CashAndCashEquivalentsAtCarryingValue"}
FLOW = {"EBIT", "DepreciationDepletionAndAmortization",
        "DepreciationAmortizationAndAccretionNet"}


def daily_leg(sym: str, metric: str, cal: pd.DatetimeIndex) -> pd.Series:
    """单科目的日频序列 —— ★ 用 engine 自己的 _to_daily,口径一致。"""
    obs = (fundamentals.ttm(sym, metric) if metric in FLOW
           else fundamentals.quarterly(sym, metric))
    if not obs:
        return pd.Series(np.nan, index=cal, dtype=float)
    v = pd.Series({o.period_end: o.value for o in obs}).sort_index()
    e = pd.Series({o.period_end: o.eff for o in obs}).sort_index()
    return fundamentals._to_daily(v, e, cal)


def daily_shares(sym: str, cal: pd.DatetimeIndex) -> pd.Series:
    sq = fundamentals.shares_quarterly(sym)
    if not sq:
        return pd.Series(np.nan, index=cal, dtype=float)
    v = pd.Series({o.period_end: o.value for o in sq}).sort_index()
    e = pd.Series({o.period_end: o.eff for o in sq}).sort_index()
    return fundamentals._to_daily(v, e, cal)


def main() -> int:
    man = data.load_manifest()
    syms = [s for s in sorted(man) if man[s].fundamentals_path]
    cal = data.trading_calendar()
    perf = (cal >= pd.Timestamp(data.PERF_START)) & (cal <= pd.Timestamp(data.PERF_END))
    print(f"票 {len(syms)} 只,日历 {len(cal)} 个交易日,"
          f"绩效窗口 {int(perf.sum())} 个交易日")

    rows = []
    # 票·日 级的汇总(绩效窗口内)
    cells = {k: 0 for k in ("S", "M", "L", "EBITDA_S", "EBITDA_M", "EV_S",
                            "EV_M", "EV_L", "EBIT", "DA_M")}
    total_cells = 0
    sect_hit = {d: {"S": 0, "M": 0, "L": 0} for d in SECTIONS}

    for i, s in enumerate(syms):
        ebit = daily_leg(s, "EBIT", cal)
        dda = daily_leg(s, "DepreciationDepletionAndAmortization", cal)
        daan = daily_leg(s, "DepreciationAmortizationAndAccretionNet", cal)
        ltd = daily_leg(s, "LongTermDebt", cal)
        ltdc = daily_leg(s, "LongTermDebtCurrent", cal)
        stb = daily_leg(s, "ShortTermBorrowings", cal)
        dc = daily_leg(s, "DebtCurrent", cal)
        liab = daily_leg(s, "Liabilities", cal)
        cash = daily_leg(s, "CashAndCashEquivalentsAtCarryingValue", cal)
        sh = daily_shares(s, cal)
        px = cache.bars(s)["close"].reindex(cal) if s in set(cache.symbols()) \
            else pd.Series(np.nan, index=cal)

        da_m = dda.where(dda.notna(), daan)
        ebitda_s = (ebit + dda).where(ebit.notna() & dda.notna())
        ebitda_m = (ebit + da_m).where(ebit.notna() & da_m.notna())

        eq_ok = sh.notna() & px.notna() & (px > 0)
        debt_m_any = pd.concat([ltd, ltdc, stb, dc], axis=1).notna().any(axis=1)
        ev_s = eq_ok & ltd.notna() & cash.notna()
        ev_m = eq_ok & debt_m_any & cash.notna()
        ev_l = eq_ok & liab.notna() & cash.notna()

        ok_s = ev_s & ebitda_s.notna()
        ok_m = ev_m & ebitda_m.notna()
        ok_l = ev_l & ebitda_m.notna()

        p = perf
        total_cells += int(p.sum())
        cells["S"] += int(ok_s[p].sum()); cells["M"] += int(ok_m[p].sum())
        cells["L"] += int(ok_l[p].sum())
        cells["EBITDA_S"] += int(ebitda_s[p].notna().sum())
        cells["EBITDA_M"] += int(ebitda_m[p].notna().sum())
        cells["EV_S"] += int(ev_s[p].sum()); cells["EV_M"] += int(ev_m[p].sum())
        cells["EV_L"] += int(ev_l[p].sum())
        cells["EBIT"] += int(ebit[p].notna().sum())
        cells["DA_M"] += int(da_m[p].notna().sum())

        for d in SECTIONS:
            ts = pd.Timestamp(d)
            pos = int(np.searchsorted(cal.to_numpy(), np.datetime64(ts), "right")) - 1
            if pos >= 0:
                if bool(ok_s.iloc[pos]):
                    sect_hit[d]["S"] += 1
                if bool(ok_m.iloc[pos]):
                    sect_hit[d]["M"] += 1
                if bool(ok_l.iloc[pos]):
                    sect_hit[d]["L"] += 1

        rows.append({
            "symbol": s,
            "绩效窗口内_严格可算天数": int(ok_s[p].sum()),
            "绩效窗口内_放宽可算天数": int(ok_m[p].sum()),
            "绩效窗口内_总负债档可算天数": int(ok_l[p].sum()),
            "绩效窗口内_EBITDA放宽可算天数": int(ebitda_m[p].notna().sum()),
            "绩效窗口内_EV放宽可算天数": int(ev_m[p].sum()),
            "绩效窗口内_EBIT可算天数": int(ebit[p].notna().sum()),
            "绩效窗口内_折旧摊销可算天数": int(da_m[p].notna().sum()),
            "折旧摊销用的字段": ("DDA" if dda.notna().any() else
                                 ("DAAN" if daan.notna().any() else "(无)")),
            "债务用到的字段": "+".join(
                k for k, v in (("LongTermDebt", ltd), ("LongTermDebtCurrent", ltdc),
                               ("ShortTermBorrowings", stb), ("DebtCurrent", dc))
                if v.notna().any()) or "(无)",
            "EBIT层一_字段有记录": bool(data.load_fundamentals(s).get("EBIT")),
            "EBIT层三_滚出TTM": bool(fundamentals.ttm(s, "EBIT")),
            "折旧摊销层一_字段有记录": bool(
                data.load_fundamentals(s).get("DepreciationDepletionAndAmortization")
                or data.load_fundamentals(s).get("DepreciationAmortizationAndAccretionNet")),
        })
        if (i + 1) % 50 == 0:
            print(f"  ...{i+1}/{len(syms)}")

    df = pd.DataFrame(rows)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")

    n = len(df)
    out = {
        "票数": n,
        "绩效窗口": f"{data.PERF_START} .. {data.PERF_END}",
        "★ 票·日 格子总数(绩效窗口)": total_cells,
        "★ 票·日 可算比例": {k: round(v / total_cells, 4) for k, v in cells.items()},
        "★ 票·日 可算格子数": cells,
        "★ 整段窗口内至少一天算得出的票数": {
            "EV_EBITDA_严格": int((df["绩效窗口内_严格可算天数"] > 0).sum()),
            "EV_EBITDA_放宽": int((df["绩效窗口内_放宽可算天数"] > 0).sum()),
            "EV_EBITDA_总负债档": int((df["绩效窗口内_总负债档可算天数"] > 0).sum()),
            "EBITDA_放宽": int((df["绩效窗口内_EBITDA放宽可算天数"] > 0).sum()),
            "EV_放宽": int((df["绩效窗口内_EV放宽可算天数"] > 0).sum()),
            "EBIT": int((df["绩效窗口内_EBIT可算天数"] > 0).sum()),
            "折旧摊销": int((df["绩效窗口内_折旧摊销可算天数"] > 0).sum()),
        },
        "★ 断面覆盖率(票数 / 250)": sect_hit,
        "★ 三层级口径对账": {
            "EBIT_层一_字段有记录": int(df["EBIT层一_字段有记录"].sum()),
            "EBIT_层三_滚出TTM": int(df["EBIT层三_滚出TTM"].sum()),
            "折旧摊销_层一_字段有记录": int(df["折旧摊销层一_字段有记录"].sum()),
            "说明": "★★★ 任务单给的 EBIT 177 / 折旧摊销 174 是层一的数;"
                    "能真正进计算的是层三。两者之差是**我们自己的 TTM 连续性要求**"
                    "卡掉的,不是数据源缺字段。",
        },
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(json.dumps(out, ensure_ascii=False, indent=2))
    print(f"\n逐只票明细:{OUT_CSV}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
