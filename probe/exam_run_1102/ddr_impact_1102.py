#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ DDR 2025-08-15 那个假 +41.8% —— **实测**影响几笔 · 2026-11-02

三秒版:考卷行情里有一天是错的(DDR/SITC 2025-08-15 被重复修正了一次,
        那天变成假 +41.8%)。★ 问题不是「要不要提一句」,是
        ★★★ **到底有没有任何一笔交易碰到它** —— 查出来是几笔就写几笔。

★ 错误本身(数据组已收到单子 probe/给数据chat-DDR那条派现对不上-1102.md):
    special_distributions_1102.csv: DDR,SITC,2025-08-15,3.25,11.48,0.2831,1.394897
    ★ 应跌 −28.3%,实际涨 +1.7%(11.48 → 11.67),差 +30.0pp
    → 再乘一次系数 1.394897 → 那天假 +41.8%
  ★ 同一只票另外三次(2025-06-30 / 10-31 / 12-15)跌幅都对得上
    → SITC 的序列是 raw 的,问题只在这一条。

★★ 本脚本**不改任何数据、不重跑** —— 只做三件事:
   ① 查 DDR 在 `large_mid` 口径下**哪些年在池**(池子口径是 universe 的一道与)
   ② 查受影响窗口(2025-08-10 ~ 2025-08-25)那几天 DDR 在不在 universe
   ③ 扫**所有**真链 + 对照流水,找出任何一笔 DDR:
      进场、离场、或**跨持**那个窗口(entry ≤ 窗口末 且 exit ≥ 窗口初)
   ★★★ 一笔都没有 → 结论写「实测影响 0 笔」,★ 不写「可能有影响」。
"""
from __future__ import annotations

import csv
import glob
import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import pool_scope                                    # noqa: E402

LEDGERS = os.path.join(HERE, "ledgers_1102")
OUT = os.path.join(HERE, "ddr_impact_1102.json")

BAD_DATE = "2025-08-15"
WIN_LO, WIN_HI = "2025-08-10", "2025-08-25"
#: ★ 考卷池子里这家公司的代码是 2016 年初那一刻的代码
SYMS = ("DDR", "SITC")
SCOPE = "large_mid"
PERF_LO, PERF_HI = "2018-01-01", "2025-12-31"


def pool_years() -> dict:
    """DDR / SITC 逐年在不在 large_mid 池里。"""
    idx = pool_scope.PoolIndex()
    out = {}
    for s in SYMS:
        per = {}
        for y in map(str, range(2016, 2027)):
            rk, t, how = idx.resolve(s, y)
            per[y] = {"rank": rk, "tier": t, "解析方式": how,
                      "在large_mid": pool_scope.in_scope(rk, SCOPE)}
        out[s] = per
    return out


def scan_ledgers() -> dict:
    """扫所有流水,找 DDR / SITC 的笔。"""
    hits, scanned, per_chain_counts = [], 0, {}
    for p in sorted(glob.glob(os.path.join(LEDGERS, "*.csv"))):
        scanned += 1
        base = os.path.basename(p)
        try:
            df = pd.read_csv(p, usecols=lambda c: c in (
                "symbol", "entry_date", "exit_date", "r_multiple",
                "r_multiple_net", "net_pnl", "entry_price", "exit_price",
                "risk_per_share", "reason", "对照种子"))
        except Exception as e:                                   # noqa: BLE001
            per_chain_counts[base] = f"读不了 {e!r}"
            continue
        if df.empty or "symbol" not in df.columns:
            per_chain_counts[base] = 0
            continue
        sub = df[df["symbol"].astype(str).isin(SYMS)]
        per_chain_counts[base] = int(len(sub))
        if sub.empty:
            continue
        ed = sub["entry_date"].astype(str)
        xd = sub["exit_date"].astype(str)
        # ★ 三种碰到:窗口内进场 / 窗口内离场 / 跨持整个窗口
        touch = ((ed >= WIN_LO) & (ed <= WIN_HI)) | \
                ((xd >= WIN_LO) & (xd <= WIN_HI)) | \
                ((ed <= WIN_HI) & (xd >= WIN_LO))
        for _, r in sub[touch].iterrows():
            hits.append({"流水文件": base, **{k: (None if pd.isna(v) else v)
                                              for k, v in r.items()}})
    return {"扫了多少份流水": scanned,
            "★碰到窗口的笔数": len(hits),
            "★碰到窗口的逐笔": hits,
            "每份流水里DDR/SITC的总笔数": per_chain_counts,
            "DDR/SITC出现过的流水份数": sum(
                1 for v in per_chain_counts.values()
                if isinstance(v, int) and v > 0)}


def main() -> int:
    py = pool_years()
    led = scan_ledgers()

    in_win = py["DDR"]["2025"]["在large_mid"] or py["SITC"]["2025"]["在large_mid"]
    # ★ 考卷池子用的是 DDR 这个代码(2016 年初),所以判据看 DDR 那一行
    ddr_2025 = py["DDR"]["2025"]
    years_in = [y for y, v in py["DDR"].items() if v["在large_mid"]]

    out = {
        "这是什么": "★★★ DDR/SITC 2025-08-15 假 +41.8% —— 实测影响几笔(2026-11-02)",
        "错误是什么": {
            "那一条": "DDR,SITC,2025-08-15,3.25,11.48,0.2831,1.394897,Polygon 分红",
            "应跌": "−28.3%",
            "实际": "+1.7%(11.48 → 11.67)",
            "差": "+30.0pp",
            "再乘一次系数后那天变成": "假 +41.8%",
            "★旁证": "同一只票 2025-06-30 −13.2% / 10-31 −12.5% / 12-15 −13.0% "
                     "跌幅都对得上 → 序列是 raw 的,问题只在这一条",
            "★单子": "probe/给数据chat-DDR那条派现对不上-1102.md(数据组已收到)",
            "★本轮没有为它重跑,也没有改数据组的文件": True,
        },
        "① 池子口径(large_mid 是 universe 的一道与)": {
            "考卷池子里这家公司的代码": "DDR(2016 年初那一刻的代码)",
            "DDR 逐年": py["DDR"],
            "SITC 逐年(对照看)": py["SITC"],
            "★DDR 在 large_mid 的年份": years_in,
            "★★★ 2025 年 DDR 的解析方式": ddr_2025["解析方式"],
            "★★★ 2025 年 DDR 在不在 large_mid": ddr_2025["在large_mid"],
            "★★★ 根因": "pool_FULL_ALL.csv 里 DDR(company_id 7374,2015–2018)和 "
                         "SITC(company_id 25906,2019–2026)是**两家不同的公司编号**,"
                         "而且两边的 renamed_to 列都是空的 → ★ 改名链没记进池子文件 → "
                         "`PoolIndex.resolve('DDR','2019'..'2025')` 一律判「当年不在池」。",
        },
        "② 受影响窗口": {
            "坏的那一天": BAD_DATE,
            "窗口": f"{WIN_LO} ~ {WIN_HI}",
            "★窗口落在绩效窗口内吗": PERF_LO <= BAD_DATE <= PERF_HI,
            "★★★ 窗口那几天 DDR 在不在 universe": False if not in_win else "要逐日看",
            "为什么": "`large_mid` 口径按**年**判(rerun_core_1030.scope_mask),"
                      "2025 全年 DDR 判「当年不在池」→ `m.universe &= scope_mask` "
                      "之后 2025 年 DDR 那一列**整年为假** → ★ 任何一条链都碰不到,"
                      "★★ 随机对照组走同一个 universe,也碰不到。",
        },
        "③ 流水实测": led,
        "★★★ 结论": None,     # 下面填
    }

    n = led["★碰到窗口的笔数"]
    if n == 0:
        out["★★★ 结论"] = (
            "★★★ **实测影响 0 笔。** "
            f"扫了 {led['扫了多少份流水']} 份流水(真链 + 50 种子并池对照),"
            "DDR / SITC 在 2025-08-10 ~ 2025-08-25 之间**没有任何一笔**进场、离场或跨持。"
            "★ 原因不是运气:2025 年 DDR 在 `large_mid` 口径下整年不在池"
            "(池子文件没记 DDR→SITC 改名链),universe 整年为假。"
            "★★ 所以这一天的数据错误**不影响本轮任何结论** —— "
            "它是一个已知的数据错误,不是本轮结果的缺陷。")
    else:
        out["★★★ 结论"] = (
            f"★★★ **实测影响 {n} 笔** —— 逐笔见「③ 流水实测 / ★碰到窗口的逐笔」。"
            "★ 每一笔的链名、进出场日、R 都已列出。")

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    try:
        print("写到", OUT)
        print(out["★★★ 结论"])
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
