#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 组合级集中度安全带(轻量版)—— 只从现有流水算,不改引擎(2026-10-30)

══════════════════════════════════════════════════════════════════════════
★★★ 三秒版:
  ① 「最严重的同向共振」已经量出来了:**2020-03-09,7 只票同日止损,
     合计亏掉初始资金的 7.13%**(技-10 持仓5天那条链)。★ 不是评审举例的 20%,
     但量级对得上 —— ★★ 而且这不是模型,是流水里真有的一天。
  ② 「同一行业占几成」那个 100% 全是**小分母**造出来的(2/2、3/3)——
     ★★★ 真正的事实是**这批链同时持仓本来就只有 2~7 个**,
     所以「5 只同时爆」在我们的流水里不是常态而是尾部。
  ③ 行业闸的代价:★ 被挡掉的那些笔原本是赚还是亏,本文件逐 N 报出来。
══════════════════════════════════════════════════════════════════════════

★★★ 这是**一阶反事实**,不是真重跑 —— 必须写进报告:
   把流水按时间重放,某笔进场会让同一 SIC 两位的在场仓位超过 N 就把它标成
   「被挡掉」。★ 真实世界里被挡掉会**腾出名额和资金**给别的票,
   那部分二阶效应这里**没有**。★★ 任务书明确要求「轻量版、不改引擎」,
   所以留在一阶,并且把这个局限写在最前面。

★ 行业分类**不重写**:用 engine/ops_1029.sic_daily(已有的严格 PIT SIC 面板)。
★★★ 我自己填的数:行业上限 N ∈ {2, 3, 4} —— **XING 填的,不是原著**。
"""
from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import ledger_facts_1030 as LF                                       # noqa: E402

#: ★★★ XING 填的,不是原著。邻近三点,要求三点同向才算说得清
IND_CAP_GRID = (2, 3, 4)

OUT = os.path.join(HERE, "industry_cap_1030.json")


def concurrent_count_dist(leds: dict[str, pd.DataFrame]) -> dict:
    """
    ★ 同时持仓**只数**的分布 —— 这一条是用来拆掉上面那个 100% 的假象的:
      占比 100% 如果来自 3/3,那它说明的是「同时只持 3 只」,不是「行业押注」。
    """
    rows = []
    for name, d in leds.items():
        ev = []
        for a, b in zip(d["entry_date"], d["exit_date"]):
            ev.append((a, +1)); ev.append((b, -1))
        ev.sort(key=lambda x: (x[0], -x[1]))
        cur, series = 0, []
        for _, delta in ev:
            cur += delta
            series.append(cur)
        s = np.array(series)
        rows.append({"链": name, "同时持仓_最大": int(s.max()),
                     "同时持仓_中位数": float(np.median(s)),
                     "同时持仓≥5的时点占比": float((s >= 5).mean())})
    return {"逐链": rows}


def cap_counterfactual(leds: dict[str, pd.DataFrame], sic2: dict[str, int],
                       caps=IND_CAP_GRID) -> dict:
    """
    逐链 × 逐 N:按时间重放,挡掉会让同 SIC2 在场数超过 N 的进场。
    ★ 报出:挡掉几笔、被挡的笔**原本是赚还是亏**、总R 变多少。
    """
    rows = []
    for name, d in leds.items():
        d = d.sort_values("entry_date", kind="mergesort").reset_index(drop=True)
        no_stop = LF._no_stop(name)
        base_r = d["r_multiple_net"].astype(float)
        base_total = float(base_r[np.isfinite(base_r)].sum())
        rec = {"链": name, "无止损链(R=收益率)": no_stop,
               "基线笔数": int(len(d)), "基线总净R": base_total,
               "基线净盈亏": float(d["net_pnl"].sum()), "逐N": {}}
        for N in caps:
            live: list[tuple[pd.Timestamp, int]] = []   # (exit_date, sic2)
            blocked_idx = []
            for i, r in d.iterrows():
                ed = r["entry_date"]
                live = [x for x in live if x[0] > ed]
                c = sic2.get(r["symbol"])
                if c is None:
                    # ★ SIC 查不到 → **不挡**(紧端:不拿「查不到」当「同行业」)
                    live.append((r["exit_date"], -1))
                    continue
                same = sum(1 for x in live if x[1] == c)
                if same >= N:
                    blocked_idx.append(i)
                    continue                   # ★ 被挡掉 → 不进场、不占在场
                live.append((r["exit_date"], c))
            bl = d.loc[blocked_idx]
            kept = d.drop(index=blocked_idx)
            br = bl["r_multiple_net"].astype(float)
            br = br[np.isfinite(br)]
            kr = kept["r_multiple_net"].astype(float)
            kr = kr[np.isfinite(kr)]
            rec["逐N"][f"N={N}"] = {
                "挡掉笔数": int(len(bl)),
                "挡掉占比": float(len(bl) / len(d)) if len(d) else None,
                "★被挡掉的笔_原本赚的笔数": int((br > 0).sum()),
                "★被挡掉的笔_原本亏的笔数": int((br <= 0).sum()),
                "★被挡掉的笔_原本赚的占比": float((br > 0).mean()) if br.size else None,
                "被挡掉的笔_原本总净R": float(br.sum()) if br.size else None,
                "被挡掉的笔_原本净盈亏": float(bl["net_pnl"].sum()) if len(bl) else 0.0,
                "留下的总净R": float(kr.sum()) if kr.size else None,
                "总净R变化(留下 − 基线)": (float(kr.sum()) - base_total) if kr.size else None,
            }
        rows.append(rec)
    return {"逐链": rows}


def worst_day_under_cap(leds: dict[str, pd.DataFrame], sic2: dict[str, int],
                        caps=IND_CAP_GRID) -> dict:
    """
    ★★ 必答三问第 2 问:N 取多少才挡得住最惨那一天?
    做法:在每个 N 的反事实流水上,重算「同日止损共振」,看最惨那天变成多少。
    """
    rows = []
    for name, d in leds.items():
        d = d.sort_values("entry_date", kind="mergesort").reset_index(drop=True)
        base = d[d["reason"] == "止损"]
        if not len(base):
            continue
        g = base.groupby("exit_date")["net_pnl"].agg(["size", "sum"])
        w = g.sort_values("sum").head(1)
        rec = {"链": name,
               "基线最惨一天": {"日期": str(w.index[0].date()),
                                "同时止损笔数": int(w["size"].iloc[0]),
                                "占初始资金": float(w["sum"].iloc[0] / LF.INITIAL_EQUITY)},
               "逐N": {}}
        for N in caps:
            live: list[tuple[pd.Timestamp, int]] = []
            keep = []
            for i, r in d.iterrows():
                ed = r["entry_date"]
                live = [x for x in live if x[0] > ed]
                c = sic2.get(r["symbol"])
                if c is None:
                    live.append((r["exit_date"], -1)); keep.append(i); continue
                if sum(1 for x in live if x[1] == c) >= N:
                    continue
                live.append((r["exit_date"], c)); keep.append(i)
            k = d.loc[keep]
            ks = k[k["reason"] == "止损"]
            if not len(ks):
                rec["逐N"][f"N={N}"] = {"说明": "闸后一笔止损都不剩"}
                continue
            gg = ks.groupby("exit_date")["net_pnl"].agg(["size", "sum"])
            ww = gg.sort_values("sum").head(1)
            rec["逐N"][f"N={N}"] = {
                "最惨一天": str(ww.index[0].date()),
                "同时止损笔数": int(ww["size"].iloc[0]),
                "占初始资金": float(ww["sum"].iloc[0] / LF.INITIAL_EQUITY),
                "同日止损笔数最大值": int(gg["size"].max()),
            }
        rows.append(rec)
    return {"逐链": rows}


def main() -> int:
    leds = LF.load_all()
    syms = sorted({s for d in leds.values() for s in d["symbol"].unique()})
    sic2 = LF.sic_two_digit_map(syms)
    out = {"口径": {
        "流水": "engine/ledgers_1030_剔污染/*剔除版.csv(18 条链)",
        "行业": "engine/ops_1029.sic_daily 的严格 PIT SIC,取每票最后一个有值码的两位",
        "SIC两位覆盖": f"{len(sic2)}/{len(syms)}",
        "★XING填的数": {"同行业仓位上限N": list(IND_CAP_GRID)},
        "★★★局限": ("这是**一阶反事实**:被挡掉的笔腾出来的名额与资金"
                      "没有被重新分配给别的票。真重跑才有那部分二阶效应。"),
        "SIC查不到怎么办": "不挡(紧端:不拿「查不到」当「同行业」)",
    }}
    out["零_同时持仓只数分布"] = concurrent_count_dist(leds)
    out["一_行业闸反事实"] = cap_counterfactual(leds, sic2)
    out["二_闸后最惨一天"] = worst_day_under_cap(leds, sic2)
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    try:
        print("已写", OUT)
    except Exception as exc:
        print("打印出错(结果已写出):", repr(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
