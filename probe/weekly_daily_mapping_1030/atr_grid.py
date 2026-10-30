"""
★ ATR 折算比的口径网格 —— 任务单给的「周线 ATR 比 √5 × 日线 ATR 低 12~18%」
  在我的匹配口径下复算不出来(我算出 +3.2%,方向还相反)。
★ 所以这里把所有合理的口径配对都跑一遍,看是哪一种口径给出 −12~18%。

★★ 纪律:任务单说这一条「已被 Gemini 独立验住,我也复验过」。
   ★ 我不能因为自己算出不一样就断定对方错 —— 更可能是**两边口径不同**。
   所以这里穷举口径,把「哪个口径给哪个数」摆出来,让差异有归属。

跑法:python3 probe/weekly_daily_mapping_1030/atr_grid.py
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from engine import cache  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "atr_grid_1030.json")
PERF_START, PERF_END = "2018-01-01", "2025-12-31"


def _wilder(x, period):
    return x.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def _sma(x, period):
    return x.rolling(period, min_periods=period).mean()


def _tr(h, l, c):
    pc = c.shift(1)
    return pd.concat([(h - l).abs(), (h - pc).abs(), (l - pc).abs()]
                     ).groupby(level=0).max()


def main() -> None:
    syms = cache.symbols()
    h, l, c = (cache.field(k, syms) for k in ("high", "low", "close"))
    H = h.resample("W-FRI").max().dropna(how="all")
    L = l.resample("W-FRI").min().dropna(how="all")
    C = c.resample("W-FRI").last().dropna(how="all")

    tr_d, tr_w = _tr(h, l, c), _tr(H, L, C)

    rows = []
    # ★ 两种平滑 × 周线期数 × 日线期数
    for smooth_name, smooth in (("Wilder", _wilder), ("SMA", _sma)):
        for pw in (10, 14, 20):
            aw = smooth(tr_w, pw)
            for pd_ in (pw, pw * 5):          # 同期数 / 同日历跨度
                ad = smooth(tr_d, pd_)
                ad_fri = ad.reindex(aw.index, method="ffill")
                ratio = (aw / (np.sqrt(5.0) * ad_fri)).loc[PERF_START:PERF_END]
                a = ratio.to_numpy(float).ravel()
                a = a[np.isfinite(a)]
                if a.size == 0:
                    continue
                med = float(np.percentile(a, 50))
                rows.append({
                    "平滑": smooth_name,
                    "周线ATR期数": pw,
                    "日线ATR期数": pd_,
                    "日历跨度是否匹配": pd_ == pw * 5,
                    "比值中位": round(med, 4),
                    "★周线ATR比√5×日线ATR_低百分之几": round((1 - med) * 100, 2),
                    "p25": round(float(np.percentile(a, 25)), 4),
                    "p75": round(float(np.percentile(a, 75)), 4),
                    "n": int(a.size),
                })

    # ★ 另一个常见口径:不用 TrueRange,用「周内高低幅」vs「日内高低幅」
    rng_w = (H - L)
    rng_d = (h - l)
    for p in (14, 20):
        aw = _sma(rng_w, p)
        ad = _sma(rng_d, p * 5).reindex(aw.index, method="ffill")
        ratio = (aw / (np.sqrt(5.0) * ad)).loc[PERF_START:PERF_END]
        a = ratio.to_numpy(float).ravel()
        a = a[np.isfinite(a)]
        med = float(np.percentile(a, 50))
        rows.append({
            "平滑": "SMA(高低幅,不是TrueRange)",
            "周线ATR期数": p, "日线ATR期数": p * 5,
            "日历跨度是否匹配": True,
            "比值中位": round(med, 4),
            "★周线ATR比√5×日线ATR_低百分之几": round((1 - med) * 100, 2),
            "p25": round(float(np.percentile(a, 25)), 4),
            "p75": round(float(np.percentile(a, 75)), 4),
            "n": int(a.size),
        })

    hit = [r for r in rows if 12.0 <= r["★周线ATR比√5×日线ATR_低百分之几"] <= 18.0]
    res = {
        "题目": "ATR 折算比的口径网格 —— 哪一种口径给出「低 12~18%」",
        "窗口": f"{PERF_START} ~ {PERF_END}",
        "票数": len(syms),
        "逐口径": rows,
        "★落在 12~18% 区间的口径": hit,
        "★落在该区间的口径数": len(hit),
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    df = pd.DataFrame(rows)
    print(df.to_string(index=False))
    print(f"\n★ 落在 12~18% 的口径数:{len(hit)}")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
