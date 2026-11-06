# -*- coding: utf-8 -*-
"""
★★★ 给新池建排名表 —— 和 pool_FULL_ALL.csv 同 schema,让 pool_scope 能直接读。

★ 为什么要这张表:engine 的池子口径(pool_scope)是按**当年成交额排名**筛的
  (large_mid = 1–2,000 名)。新池 2,807 只没有这张表,所以筛不了。

★★ 排名定义**照抄老池**,一个字不改(engine/pool_scope.py:23 原文):
   「排名都是当年年初回看 **60 个交易日**的日均成交额排名」
   → ★★★ 天生按时点,不需要历史股数。

★★ 写出来的列和老池一致(多余的列留空,不编):
   year, base_date, rank, tier, symbol, avg_dollar_volume_60d, dollar_vol_price,
   seg_id, company_id, seg_start, seg_end, end_type, renamed_to, old_symbol, old_size

★★★ tier 的带宽也照抄老池:1–500 大 · 501–2000 中 · 2001+ 小
   (pool_scope.py 说 rank<=2000 与 tier in (大,中) 在老池里恒等 —— 我们保持恒等)
"""
from __future__ import annotations
import csv, io, json, os
import numpy as np, pandas as pd

OUT = "probe/newpool_1106"
PANEL = os.path.join(OUT, "ohlcv_panel_newpool.parquet")
LOOKBACK = 60


def tier_of(rank: int) -> str:
    return "大" if rank <= 500 else ("中" if rank <= 2000 else "小")


def main() -> int:
    wide = pd.read_parquet(PANEL)
    dv = wide["dollar_volume"]
    idx = dv.index
    rows, 年统计 = [], {}
    for year in range(idx.min().year, idx.max().year + 1):
        ys = idx[idx.year == year]
        if len(ys) == 0:
            continue
        base = ys[0]                              # ★ 当年第一个交易日
        hist = idx[idx < base][-LOOKBACK:]        # ★ 回看 60 个交易日(严格在 base 之前)
        if len(hist) < LOOKBACK:
            年统计[str(year)] = f"★ 跳过:base 之前只有 {len(hist)} 个交易日,不足 {LOOKBACK}"
            continue
        adv = dv.loc[hist].mean(axis=0, skipna=True)
        # ★ 回看窗口里有效天数不足一半的不排名 —— ★★ 不拿残缺样本去排
        valid = dv.loc[hist].notna().sum(axis=0)
        adv = adv[(valid >= LOOKBACK // 2) & adv.notna() & (adv > 0)]
        adv = adv.sort_values(ascending=False)
        for i, (sym, v) in enumerate(adv.items(), 1):
            rows.append({
                "year": year, "base_date": base.strftime("%Y-%m-%d"),
                "rank": i, "tier": tier_of(i), "symbol": sym,
                "avg_dollar_volume_60d": round(float(v), 1),
                "dollar_vol_price": "close",      # ★ 老池用 vwap;我们没有 vwap,如实标 close
                "seg_id": "", "company_id": "", "seg_start": "", "seg_end": "",
                "end_type": "", "renamed_to": "", "old_symbol": "", "old_size": "",
            })
        年统计[str(year)] = {"排名只数": int(len(adv)),
                            "大": int(sum(1 for i in range(1, len(adv) + 1) if i <= 500)),
                            "中": int(sum(1 for i in range(1, len(adv) + 1)
                                          if 500 < i <= 2000)),
                            "小": int(max(0, len(adv) - 2000))}
    p = os.path.join(OUT, "pool_NEWPOOL_ALL_1106.csv")
    with io.open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    rep = {"★口径": {
        "排名定义": "当年第一个交易日之前、回看 60 个交易日的日均成交额(照抄 pool_scope.py:23)",
        "★为什么不需要历史股数": "成交额排名天生按时点",
        "tier 带宽": "1–500 大 · 501–2000 中 · 2001+ 小(与 rank<=2000 恒等,照抄老池)",
        "★和老池的一处差异": "老池 dollar_vol_price=vwap;我们没有 vwap,用 close,已在列里如实标",
        "★不排名的": f"回看窗口有效天数 < {LOOKBACK//2} 的不给排名(不拿残缺样本排)",
    }, "行数": len(rows), "逐年": 年统计}
    io.open(os.path.join(OUT, "建排名表_报告_1106.json"), "w", encoding="utf-8").write(
        json.dumps(rep, ensure_ascii=False, indent=1))
    print(f"★ {p} · {len(rows)} 行")
    for y, v in 年统计.items():
        print(f"   {y}: {v}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
