# -*- coding: utf-8 -*-
"""
★★★ 给并池 3,834 只重建排名表（B 路 1107）

大白话：大中盘那道筛按「当年成交额排名」决定谁能买。原来那张表是老池 2,807 只建的，
新并进来的 1,027 只（含苹果微软）在表里一行都没有 → 全被筛掉。这里用并池面板重建一张。

★ 排名定义**照抄** probe/newpool_1106/建排名表_1106.py（它又照抄 engine/pool_scope.py:23）：
  当年第一个交易日之前、回看 60 个交易日的日均成交额；有效天数 < 30 的不排；
  1–500 大 · 501–2000 中 · 2001+ 小。

★★★ 只有一处不同（③ 我们定的，代价写明）：
  **面板第一年**(2016 版 = 2016;2004 版 = 2004)的基准日之前没有 60 天可回看。
  2016 版:基准日是 2016-01-04，而考卷那批数据正好从这一天才开始 → 往前没有 60 天可回看。
  → 2016 年里**往前回看不够**的票，改用 **2016 年头 60 个交易日**的日均成交额来排。
  ★ 代价：这些票在 2016 年的「成交额排名」上提前看了约一个季度。
    排名只决定「能不能进大中盘这个池子」，不碰价格信号；巨头的成交额排名一个季度内不会变档，
    但小票可能会。所以在 fallback 列里逐行标了出来，不冒充原规则。
"""
from __future__ import annotations
import csv, io, json, os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
# ★ 用法:python3 建排名表_并池_1107.py [2016|2004]   (默认 2016 = 第一版;2004 = 22 年面板)
窗 = (sys.argv[1] if len(sys.argv) > 1 else "2016")
PANEL = os.path.join(ROOT, "probe", "并池_1107" if 窗 == "2016" else "并池2004_1107", "ohlcv_panel_newpool.parquet")
OUTCSV = os.path.join(HERE, "pool_并池3834_1107.csv" if 窗 == "2016" else "pool_并池2004_1107.csv")
首年 = 2016 if 窗 == "2016" else 2004
LOOKBACK = 60


def tier_of(rank: int) -> str:
    return "大" if rank <= 500 else ("中" if rank <= 2000 else "小")


def main() -> int:
    dv = pd.read_parquet(PANEL)["dollar_volume"]
    idx = dv.index
    rows, 年 = [], {}
    for year in range(idx.min().year, idx.max().year + 1):
        ys = idx[idx.year == year]
        if len(ys) == 0:
            continue
        base = ys[0]
        hist = idx[idx < base][-LOOKBACK:]
        if len(hist) >= LOOKBACK:
            adv = dv.loc[hist].mean(skipna=True)
            ok = dv.loc[hist].notna().sum() >= LOOKBACK // 2
        else:
            adv = pd.Series(dtype=float); ok = pd.Series(dtype=bool)
        fb = set()
        if year == 首年:
            fwd = ys[:LOOKBACK]
            adv_f = dv.loc[fwd].mean(skipna=True)
            ok_f = dv.loc[fwd].notna().sum() >= LOOKBACK // 2
            need = [s for s in dv.columns if not bool(ok.get(s, False))]
            for s in need:
                if bool(ok_f.get(s, False)):
                    adv.loc[s] = adv_f[s]; ok.loc[s] = True; fb.add(s)
        if len(adv) == 0:
            年[str(year)] = "跳过（往前不足 60 天）"; continue
        adv = adv[ok.reindex(adv.index).fillna(False).astype(bool) & adv.notna() & (adv > 0)]
        adv = adv.sort_values(ascending=False)
        for i, (sym, v) in enumerate(adv.items(), 1):
            rows.append({"year": year, "base_date": base.strftime("%Y-%m-%d"), "rank": i,
                         "tier": tier_of(i), "symbol": sym, "avg_dollar_volume_60d": round(float(v), 1),
                         "dollar_vol_price": "close",
                         "seg_id": "", "company_id": "", "seg_start": "", "seg_end": "",
                         "end_type": ("★fallback:用2016头60日排" if sym in fb else ""),
                         "renamed_to": "", "old_symbol": "", "old_size": ""})
        年[str(year)] = {"排名只数": int(len(adv)), "其中2016前看排的": len(fb) if year == 2016 else 0}
    with io.open(OUTCSV, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    p = pd.DataFrame(rows)
    big = ["AAPL", "MSFT", "AMZN", "NVDA", "JPM", "BRK.B", "AVGO", "NFLX", "META", "TSLA"]
    巨头 = {s: p[(p.symbol == s)].set_index("year")["rank"].to_dict() for s in big}
    rep = {"★口径": __doc__.strip(), "行数": len(rows), "逐年": 年,
           "★巨头逐年排名（自证）": 巨头,
           "★巨头每年都在大盘(≤500)": {s: {"不在大盘的年份": [y for y, v in d.items() if v > 500], "有排名的年数": len(d)}
                                       for s, d in 巨头.items()}}
    io.open(os.path.join(HERE, f"建排名表_并池_报告_{窗}_1107.json"), "w", encoding="utf-8").write(
        json.dumps(rep, ensure_ascii=False, indent=1, default=str))
    print(json.dumps({"行数": len(rows), "逐年": 年, "巨头": rep["★巨头每年都在大盘(≤500)"]}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
