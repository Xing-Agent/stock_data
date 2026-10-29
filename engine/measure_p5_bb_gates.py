"""
measure_p5_bb_gates —— 第三件的配套实测:新旧过滤器各放行了哪一桶触轨事件。

大白话(三秒):旧版三道过滤器只放过 19.3% 的触轨事件,而放过的那一桶偏偏是
后续表现最差的。这个脚本把【新组合放行的那一桶】按同样的口径算一遍,
★ 看是不是修好了。

口径(和 pat6_measure.q4「★按环境切开」那一节完全一致,否则不可比):
  · 分母 = 全部触轨日×票(收盘 < 布林下轨,20 日 / ±2.0σ)
  · 每一桶报:日×票数、占全部触轨的比例、20 日继续下跌比例、20 日中位/均值收益
  · ★ 这里量的是【环境闸门放行了什么】,★ 不是交易成绩 ——
    交易成绩在 results_1029_批五修正.json 里

跑法:python3 -m engine.measure_p5_bb_gates
"""

from __future__ import annotations

import json
import os
import resource
import subprocess
import time

import numpy as np
import pandas as pd

from . import cache, data, matrices, pat6_ops

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "results_1029_批五布林闸门.json")


def main() -> int:
    t0 = time.time()
    print(subprocess.run(["free", "-m"], capture_output=True, text=True).stdout)
    pat6_ops.install()
    syms = cache.symbols()
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                          capture_output=True, text=True).stdout.strip()
    close = cache.field("close", syms)
    idx = close.index
    pm = np.asarray((idx >= pd.Timestamp(data.PERF_START))
                    & (idx <= pd.Timestamp(data.PERF_END)))
    ca = close.to_numpy(float)

    _, _, lo, _, _ = pat6_ops.bollinger(20, 2.0, syms)
    tag = np.asarray((close < lo).fillna(False).to_numpy(bool)) & pm[:, None]

    B = lambda df: np.asarray(df.fillna(False).to_numpy(bool))      # noqa: E731
    trend = B(pat6_ops.bb_trend_gate(syms, dict(ma_period=200, slope_lookback=20)))
    adx_ok = B(pat6_ops.adx(14, syms) <= 25.0)
    rsi_ok = B(pat6_ops.rsi_oversold(syms, dict(rsi_period=2, max_rsi=10.0)))
    bw_ok = B(pat6_ops.bb_bw_jump_gate(
        syms, dict(period=20, k=2.0, bw_jump_lookback=3, bw_jump_max=0.20)))
    rev = B(pat6_ops.bb_reversal(syms, dict(period=20, k=2.0)))
    reclaim = B(pat6_ops.bb_reclaim(syms, dict(period=20, k=2.0, rsi_period=2,
                                               rsi_low=10.0, rsi_back=15.0)))

    fwd = {}
    for H in (5, 20, 60):
        nxt = np.full_like(ca, np.nan)
        nxt[:-H, :] = ca[H:, :]
        fwd[H] = nxt / ca - 1.0

    def bucket(mask, name, base=None) -> dict:
        """
        ★ base 是分母口径:
          默认 tag = **收盘**触轨(Close < 下轨)—— 和 pat6_measure.q4 一致,
          环境闸门那几桶用它;
          ★ 进场扳机那几桶必须用 tag_low = **盘中**触轨(Low < 下轨)——
          因为「收复」要求 Close > 下轨,和「收盘 < 下轨」在同一天**互斥**,
          ★ 用收盘触轨当分母会得到恒等于 0 的假结果。
        """
        b = tag if base is None else base
        m = mask & b
        d = {"桶": name, "分母口径": "收盘触轨" if base is None else "盘中触轨",
             "日×票": int(m.sum()),
             "★占该分母的比例": round(float(m.sum() / max(1, b.sum())), 4)}
        for H in (5, 20, 60):
            r = fwd[H]
            mm = m & np.isfinite(r)
            rr = r[mm]
            d[f"{H}日继续下跌比例"] = round(float((rr < 0).mean()), 4) if rr.size else None
            d[f"★{H}日中位收益"] = round(float(np.median(rr)), 5) if rr.size else None
            d[f"{H}日均值收益"] = round(float(rr.mean()), 5) if rr.size else None
            d[f"{H}日n"] = int(rr.size)
        return d

    rows = [
        bucket(np.ones_like(tag), "全部触轨(分母)"),
        bucket(trend & adx_ok, "★旧版环境:SMA200 上方 且 ADX(14)≤25"),
        bucket(trend & ~adx_ok, "★旧版挡住的:SMA200 上方 但 ADX>25(「黄金坑」就在这里)"),
        bucket(trend & rsi_ok, "★★新版环境:SMA200 上方 且 RSI(2)≤10"),
        bucket(trend & rsi_ok & bw_ok, "★★新版环境 + 带宽熔断"),
        bucket(trend & adx_ok & bw_ok, "旧版环境 + 带宽熔断(= 旧三道)"),
        bucket(trend & rsi_ok & ~adx_ok,
               "★ 新版放行、旧版被 ADX 挡住的那一块(交集差)"),
        bucket(trend & adx_ok & ~rsi_ok,
               "★ 旧版放行、新版被 RSI2 挡住的那一块(交集差)"),
    ]
    low = cache.field("low", syms)
    tag_low = np.asarray((low < lo).fillna(False).to_numpy(bool)) & pm[:, None]
    entry_rows = [
        bucket(np.ones_like(tag_low), "全部盘中触轨(Low < 下轨)(分母)", tag_low),
        bucket(reclaim, "旧版进场扳机 pat6_bb_reclaim(三步)", tag_low),
        bucket(rev, "新版进场扳机 pat6_bb_reversal(Low<轨 且 Close>轨 且 Close>Open)",
               tag_low),
        bucket(reclaim & trend & adx_ok & bw_ok, "★旧版完整进场(扳机 + 三道过滤器)",
               tag_low),
        bucket(rev & trend & rsi_ok & bw_ok, "★★新版完整进场(带带宽熔断)", tag_low),
        bucket(rev & trend & rsi_ok, "★★新版完整进场(不带带宽熔断)", tag_low),
    ]

    out = {
        "git_commit": head,
        "缓存构建时间": time.strftime(
            "%Y-%m-%d %H:%M:%S",
            time.localtime(os.stat(cache.PANEL_PARQUET).st_mtime)),
        "统计窗口": [data.PERF_START, data.PERF_END],
        "全部收盘触轨日×票": int(tag.sum()),
        "★口径": "分母 = 全部触轨日×票(收盘 < 布林下轨 20/2.0σ);"
                  "★ 这里量的是环境闸门放行了什么,★ 不是交易成绩",
        "逐桶_环境闸门": rows,
        "逐桶_完整进场": entry_rows,
        "怎么读": "★ 旧版的病是:三道一起只放过约 19% 的触轨事件,"
                  "而「SMA200 上方 且 ADX≤25」那一桶的后续收益恰恰是最低的;"
                  "★ 新版要看两件事 —— ① 放行比例变没变;"
                  "② 放行的那一桶后续收益有没有比旧版高。",
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(json.dumps(out, ensure_ascii=False, indent=1))
    print(f"\n写好 {OUT_JSON}({time.time()-t0:.0f} 秒;峰值 RSS "
          f"{resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
