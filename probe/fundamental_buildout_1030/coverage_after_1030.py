#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 补标签之后再量一遍覆盖率 —— 补前 / 补后同口径对照(2026-10-30)

三秒版:同一把尺子量两遍 —— ★ 一遍不挂覆盖层,一遍挂上。
        ★★ 两遍之间**只差补标签这一件事**,所以差值就是补标签的效果。

★ 量的四样东西(策略组要看的):
    EBIT · 净债 · EV/EBIT · EV/EBITDA
  ★★★ 其中 **EV/EBIT 不需要折旧摊销** —— 它是「EV/EBITDA 算不出」的替代口径;
     ★ 而 EV/EBITDA 的卡点(折旧摊销)★★ 本地那份 SEC dump **没有抓这个标签**,
       ★★★ 所以折旧摊销这一项是「**没查**」,不是「查了没有」—— 分开登记。
★ 「天」一律是交易日。★ 先写结果再打印。
跑法:python3 probe/fundamental_buildout_1030/coverage_after_1030.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

OUT_JSON = os.path.join(HERE, "coverage_after_1030.json")
OUT_CSV = os.path.join(HERE, "逐只票-补前补后覆盖率-1030.csv")

SECTIONS = ("2018-06-30", "2022-06-30", "2025-06-30")
#: ★★ 折旧摊销在那份 dump 里**没有被抓** —— 登记成「没查」
NOT_CHECKED = {
    "折旧摊销的同义标签": "★★★ 没查(不是查了没有)。本地那份 "
        "probe/fundamentals_sec_1030/sec_companyfacts_300_1030.json.gz 只抓了 "
        "21 个**负债/利润相关**标签,★ 里面没有任何 Depreciation* 标签;"
        "★★ 而 data.sec.gov 在本机被代理挡住(CONNECT 403)。"
        "★ 所以「折旧摊销 174/250 是不是也取窄了」这个问题**本轮无法回答**。",
    "PropertyPlantAndEquipmentNet": "★★★ 没查。同上 —— 那份 dump 里没有这个标签。"
        "★ 基-4 神奇公式的 ROC 分母要它,本轮只能用派生式顶。",
}


def measure(tag: str) -> tuple[pd.DataFrame, dict]:
    """★ 在当前(挂 / 不挂覆盖层)状态下量一遍。"""
    from engine import cache, data, fundamentals
    import ops_fund_1030 as OF

    cal = data.trading_calendar()
    perf = (cal >= pd.Timestamp(data.PERF_START)) & (cal <= pd.Timestamp(data.PERF_END))
    man = data.load_manifest()
    syms = [s for s in sorted(man) if man[s].fundamentals_path]

    ebit = OF.get("ebit_ttm", syms)
    nd = OF.get("net_debt", syms)
    eveb = OF.price_ratio("ev_ebit", syms)

    # EV/EBITDA:折旧摊销只能用本地那两个标签(dump 没抓)
    def da_daily(s: str) -> pd.Series:
        a = fundamentals.ttm(s, "DepreciationDepletionAndAmortization")
        b = fundamentals.ttm(s, "DepreciationAmortizationAndAccretionNet")
        pick = a or b
        if not pick:
            return pd.Series(np.nan, index=cal, dtype=float)
        v = pd.Series({o.period_end: o.value for o in pick}).sort_index()
        e = pd.Series({o.period_end: o.eff for o in pick}).sort_index()
        return fundamentals._to_daily(v, e, cal)

    da = pd.DataFrame({s: da_daily(s) for s in syms}).reindex_like(ebit)
    ebitda = (ebit + da).where(ebit.notna() & da.notna())
    close = cache.field("close", syms).reindex_like(ebit)
    sh = pd.DataFrame({s: fundamentals.panel("shares", (s,))[s]
                       for s in syms}).reindex_like(ebit)
    ev = close * sh + nd
    evebitda = (ev / ebitda.where(ebitda > 0)).where(
        sh.notna() & nd.notna() & (ebitda > 0) & (ev > 0))

    p = pd.Series(perf, index=cal)
    legs = {"EBIT": ebit, "净债": nd, "EV_EBIT": eveb, "EV_EBITDA": evebitda,
            "折旧摊销": da, "EBITDA": ebitda}
    cells, symcnt, sect = {}, {}, {}
    for k, df in legs.items():
        sub = df[p.values]
        cells[k] = round(float(sub.notna().to_numpy().mean()), 4)
        symcnt[k] = int((sub.notna().sum(axis=0) > 0).sum())
        sect[k] = {}
        for d in SECTIONS:
            pos = int(np.searchsorted(cal.to_numpy(),
                                      np.datetime64(pd.Timestamp(d)), "right")) - 1
            sect[k][d] = int(df.iloc[pos].notna().sum()) if pos >= 0 else None
    rows = [{"symbol": s,
             **{f"{k}_可算天数": int(df[p.values][s].notna().sum())
                for k, df in legs.items()}}
            for s in syms]
    return pd.DataFrame(rows), {"票·日可算比例": cells,
                                "至少一天算得出的票数": symcnt,
                                "断面票数": sect, "口径": tag}


def main() -> int:
    # ★★ 两遍必须在**两个进程**里跑 —— 覆盖层挂上之后没法干净卸掉
    #   (engine 的 lru_cache 已经被清过、再清回不去)。
    #   ★ 所以用子进程各跑一遍,★★ 这也顺带满足「可续跑」:
    #     哪一遍挂了只重跑那一遍。
    mode = sys.argv[1] if len(sys.argv) > 1 else "both"
    if mode in ("before", "after"):
        if mode == "after":
            import ops_fund_1030 as OF
            OF.install_overlay(with_operating_income=False)
        df, summ = measure("补标签后" if mode == "after" else "补标签前")
        part = os.path.join(HERE, f"_cov_{mode}.json")
        with open(part, "w", encoding="utf-8") as fh:
            json.dump(summ, fh, ensure_ascii=False, indent=2)
        df.to_csv(os.path.join(HERE, f"_cov_{mode}.csv"), index=False,
                  encoding="utf-8-sig")
        try:
            print(json.dumps(summ, ensure_ascii=False, indent=2))
        except Exception as e:
            print(f"(打印出错,结果已写出:{type(e).__name__}: {e})")
        return 0

    out = {}
    for m in ("before", "after"):
        part = os.path.join(HERE, f"_cov_{m}.json")
        if not os.path.exists(part):          # ★ 可续跑:已有的跳过
            r = subprocess.run([sys.executable, os.path.abspath(__file__), m],
                               cwd=ROOT, capture_output=True, text=True)
            if not os.path.exists(part):
                raise RuntimeError(f"★ {m} 那一遍挂了:\n{r.stdout[-3000:]}\n"
                                   f"{r.stderr[-3000:]}")
        out[m] = json.load(open(part, encoding="utf-8"))

    b, a = out["before"], out["after"]
    delta = {
        "票·日可算比例": {k: [b["票·日可算比例"][k], a["票·日可算比例"][k]]
                          for k in b["票·日可算比例"]},
        "至少一天算得出的票数": {k: [b["至少一天算得出的票数"][k],
                                    a["至少一天算得出的票数"][k]]
                                for k in b["至少一天算得出的票数"]},
        "断面票数(补前→补后)": {k: {d: [b["断面票数"][k][d], a["断面票数"][k][d]]
                                    for d in b["断面票数"][k]}
                                for k in b["断面票数"]},
    }
    res = {"★★★ 补前 → 补后": delta, "★★ 没查的(不是查了没有)": NOT_CHECKED,
           "补前原始": b, "补后原始": a}
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=2)
    db = pd.read_csv(os.path.join(HERE, "_cov_before.csv"))
    da_ = pd.read_csv(os.path.join(HERE, "_cov_after.csv"))
    m = db.merge(da_, on="symbol", suffixes=("_补前", "_补后"))
    m.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    try:
        print(json.dumps(delta, ensure_ascii=False, indent=2))
        print(f"\n{OUT_JSON}\n{OUT_CSV}")
    except Exception as e:
        print(f"(打印出错,结果已写出:{type(e).__name__}: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
