# -*- coding: utf-8 -*-
"""★★★ 《128》口径① —— 止损反事实：**股数不变**，把被砍掉的单子放回去活完。

★★ 三秒版：那些被硬止损砍掉的单子，★ 如果**不砍**、用**同样的股数**继续拿着，
   ★★★ 一直拿到策略自己的离场门（`close_below_lowest_low(10)`）才卖 —— 是多亏还是少亏？

★★★★★ 为什么必须有这一口径（★ 和口径② 的区别）：
  ★ 口径②（放宽止损重跑）已经做了，结论是「三点同向地更差」。
  ★★ 但那是因为引擎的仓位 = 风险额 ÷(进场价−止损价) → **止损一放宽就自动缩仓**，
    ★★★ 所以它同时改了两件事：**砍不砍** 和 **买多少**。
  → ★ 本口径**把仓位钉死**，只问「砍不砍」这一件 —— ★★★ 这才对得上
    Lin 的原话「大周期在涨的时候，止损各方面不用怕太多」。

★ 口径（规矩㊼）：全收益不影响本计算（只看价格路径）；窗口 B 段；
  ★★ 真规则来自配置：`exit.rules[0] = close_below_lowest_low, lookback=10`
  ★★★ 不许按均线（《128》第一节已更正我早先报错的机制名）。
"""
from __future__ import annotations
import io
import json
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe/并池_1107"))

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "反事实_股数不变_1108.json")
LED = os.path.join(ROOT, "probe/重测_1107/ledgers_1107",
                   "REAL__B_2015到2025·并池2004·大波段·技-1·A原样.csv")
窗口止 = pd.Timestamp("2025-12-31")
LOOKBACK = 10          # ★★★ 来自配置，不是我定的


def main() -> int:
    import 接新基准_1107 as BM
    BM.install()
    from engine import cache, data

    led = pd.read_csv(LED, parse_dates=["entry_date", "exit_date"])
    止 = led[led["reason"].astype(str) == "止损"].copy()
    print(f"★ 这条臂共 {len(led)} 笔 · 其中止损 {len(止)} 笔", flush=True)

    # ★★ 面板：直接读并池面板，★ 比逐只读文件快得多
    pan = pd.read_parquet(os.path.join(ROOT, "probe/并池2004_1107/ohlcv_panel_newpool.parquet"))
    print(f"★ 面板 {pan.shape}", flush=True)
    if isinstance(pan.columns, pd.MultiIndex):
        收 = pan["close"] if "close" in pan.columns.get_level_values(0) else None
        低 = pan["low"] if "low" in pan.columns.get_level_values(0) else None
        开 = pan["open"] if "open" in pan.columns.get_level_values(0) else None
    else:
        raise SystemExit("★★★ 面板不是 MultiIndex —— 停，先看清结构再算（不猜）")

    rows, 缺 = [], []
    for _, r in 止.iterrows():
        t = str(r["symbol"])
        if t not in 收.columns:
            缺.append(t)
            continue
        c = 收[t].dropna()
        lo = 低[t].reindex(c.index)
        op = 开[t].reindex(c.index)
        d0 = pd.Timestamp(r["exit_date"]).normalize()
        fut = c.index[c.index > d0]
        if not len(fut):
            continue
        # ★★★ 真规则：收盘 < 过去 LOOKBACK 日最低价 → 次日开盘卖
        最低 = lo.rolling(LOOKBACK).min().shift(1)
        触发 = c.index[(c.index > d0) & (c < 最低) & (c.index <= 窗口止)]
        if len(触发):
            卖日候选 = c.index[c.index > 触发[0]]
            卖日 = 卖日候选[0] if len(卖日候选) else 触发[0]
            卖价 = float(op.get(卖日, c.get(卖日, np.nan)))
            到期 = False
        else:
            卖日 = c.index[c.index <= 窗口止][-1]
            卖价 = float(c.loc[卖日])
            到期 = True                     # ★ 窗口末还没触发
        if not np.isfinite(卖价):
            continue
        实际卖价 = float(r["exit_price"]) if "exit_price" in r and pd.notna(r["exit_price"]) else np.nan
        股数 = float(r["shares"]) if "shares" in r and pd.notna(r["shares"]) else np.nan
        if not np.isfinite(实际卖价) or not np.isfinite(股数):
            continue
        rows.append({"symbol": t, "原离场日": d0, "反事实卖出日": 卖日,
                     "原卖价": 实际卖价, "反事实卖价": 卖价, "股数": 股数,
                     "多出来的盈亏": (卖价 - 实际卖价) * 股数,
                     "多拿了几天": int((卖日 - d0).days), "窗口末未触发": 到期})

    df = pd.DataFrame(rows)
    报 = {"【本次口径】": ("全收益不影响本计算（只看价格路径）· 窗口 B 2015~2025 · "
                   f"池 并池2004 · ★★★ 离场真规则 close_below_lowest_low(lookback={LOOKBACK})"),
         "★★★这一口径问什么": "**股数钉死，只问「砍不砍」** —— 和口径②（放宽止损+自动缩仓）是两个问题",
         "★止损笔数": int(len(止)), "★能重放的": int(len(df)),
         "★面板里找不到的票": sorted(set(缺))[:10], "★找不到的只数": len(set(缺))}
    if len(df):
        到期占比 = float(df["窗口末未触发"].mean())
        报.update({
            "★★★不砍的话多出来的总盈亏": round(float(df["多出来的盈亏"].sum()), 0),
            "★★★其中多赚的笔数": int((df["多出来的盈亏"] > 0).sum()),
            "★★★其中多亏的笔数": int((df["多出来的盈亏"] < 0).sum()),
            "★每笔中位": round(float(df["多出来的盈亏"].median()), 1),
            "★平均多拿了几天": round(float(df["多拿了几天"].mean()), 1),
            "★★窗口末仍未触发占比": f"{到期占比*100:.1f}%",
            "★★★这一口径作不作废": (
                f"**作废**（窗口末未触发 {到期占比*100:.1f}% > 20%，《128》第四节跑前写死）"
                if 到期占比 > 0.20 else
                f"★ 有效（窗口末未触发 {到期占比*100:.1f}% < 20%）"),
        })
        报["★★对照_原策略这条臂的净盈亏"] = 578729
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(报, ensure_ascii=False, indent=1, default=str))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
