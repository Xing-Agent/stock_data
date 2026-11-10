"""
「后面怎么走」同类统计 · 第二轮（按 Gemini 1110 审稿重做）

大白话：第一轮只数「先往上还是先往下」，量不出趋势的好处。趋势的好处在「对的时候赚得多」，
所以这一轮改成看「之后 20 天、60 天到底涨跌多少」的分布，并且扣掉同期大盘（SPY）的涨跌。

★ 口径（跑之前写死）：
  池子：研发池 2,216 只（B 类 8 只剔除；考卷、留出池不碰）。信号日 2010-01-01 ~ 2025-09-30。
  价格：拆股复权（不含分红；Gemini 说会偏低 1~2 个百分点，对各组一视同仁）。
  每个「股票×交易日」记：
     五状态（engine.stages）· 收盘 > 150 日线？ · 过去 60 天涨幅 · 当天放量创 20 日新高？
     大盘环境：★ 数据里没有 SPY → 用「研发池等权指数」代替（每天全池平均涨跌连乘）；指数 > 自身 200 日线 = 大盘好
     结果：T+20、T+60 收益；同期等权指数收益；T+20 内最大浮盈 / 最大浮亏（盘中高低，相对 T 收盘）
  动量前 20%：同一天全池按 60 天涨幅排名，前 20%。
  去重：同一只票、同一组条件，一次计数后 20 个交易日内不再计（只数「第一枪」）。
  看的数：次数 · 20 天后上涨的比例 · 平均 / 中位数 · 好的 1/4（75 分位）· 差的 1/4（25 分位）·
          扣掉同期大盘后的平均 · 60 天后的平均 / 中位数 · 20 天内最大浮盈 / 浮亏的中位数
"""
from __future__ import annotations

import gzip
import json
import os
import sys
import time

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, REPO)
from engine.stages import compute_stages  # noqa: E402

HERE = os.path.dirname(os.path.abspath(__file__))
START, END = "2010-01-01", "2025-09-30"
B8 = {"META", "NUAN", "ED", "BGS", "ENTA", "EXPR", "ECL", "PODD"}
SCODE = {"STAGE_2": 0, "BULL_PULLBACK": 1, "CHOP": 2, "BEAR_RALLY": 3, "STAGE_4": 4}
SNAME = {v: k for k, v in SCODE.items()}


def load(sym):
    df = pd.DataFrame(json.load(gzip.open(os.path.join(REPO, f"market_ext_1105/{sym}/daily.json.gz")))["data"])
    if df.empty:
        return None
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    sc = df["split_coefficient"].fillna(1.0).replace(0, 1.0).astype(float)
    fac = sc[::-1].cumprod()[::-1].shift(-1).fillna(1.0)
    for c in ("open", "high", "low", "close"):
        df[c] = df[c].astype(float) / fac
    df["volume"] = df["volume"].astype(float) * fac
    df = df.dropna(subset=["close"])
    return df[df["close"] > 0]


def spy_frame(syms):
    rets = []
    for s in syms:
        df = load(s)
        if df is None or len(df) < 60:
            continue
        r = df["close"].pct_change()
        rets.append(r[(r.abs() < 0.6)].rename(s))
    c = (1 + pd.concat(rets, axis=1).mean(axis=1).fillna(0)).cumprod()
    return pd.DataFrame({"spy_up": c > c.rolling(200).mean(),
                         "spy20": c.shift(-20) / c - 1, "spy60": c.shift(-60) / c - 1})


def one(sym, spy):
    df = load(sym)
    if df is None or len(df) < 260:
        return None
    c, h, l, v = df["close"], df["high"], df["low"], df["volume"]
    st = compute_stages(df[["close"]])["stage"].map(SCODE)
    f = pd.DataFrame(index=df.index)
    f["stage"] = st
    f["a150"] = c > c.rolling(150).mean()
    f["mom60"] = c / c.shift(60) - 1
    f["brk"] = (c > h.shift(1).rolling(20).max()) & (v > 1.5 * v.shift(1).rolling(20).mean())
    f["r20"] = c.shift(-20) / c - 1
    f["r60"] = c.shift(-60) / c - 1
    hi20 = h[::-1].rolling(20, min_periods=20).max()[::-1].shift(-1)
    lo20 = l[::-1].rolling(20, min_periods=20).min()[::-1].shift(-1)
    f["mfe"] = hi20 / c - 1
    f["mae"] = lo20 / c - 1
    f = f.join(spy, how="left")
    f = f[(f.index >= START) & (f.index <= END)].dropna(subset=["stage", "mom60", "r20", "r60", "spy20", "spy60"])
    # 一天内涨跌超过 ±60% 的多半是坏数据 → 去掉那一段
    f = f[(f["r20"].abs() < 3) & (f["r60"].abs() < 5)]
    f["sym"] = sym
    return f.reset_index().rename(columns={"index": "date"})


def main():
    hold = json.load(open(os.path.join(REPO, "probe/新策略_1106/holdout_newpool_1106.json"), encoding="utf-8"))
    syms = [s for s in sorted(hold["研发池名单"]) if s.split("__")[0] not in B8]
    spy = spy_frame(syms)
    print('等权指数好了', flush=True)
    t0 = time.time()
    parts = []
    for i, s in enumerate(syms):
        try:
            r = one(s, spy)
        except Exception as e:  # noqa: BLE001
            print("跳过", s, e, flush=True)
            continue
        if r is not None and len(r):
            parts.append(r)
        if (i + 1) % 300 == 0:
            print(f"{i + 1}/{len(syms)} {time.time() - t0:.0f}s", flush=True)
    d = pd.concat(parts, ignore_index=True)
    d["stage"] = d["stage"].astype(int)
    d["mom_top20"] = d.groupby("date")["mom60"].rank(pct=True) >= 0.8
    d["ex20"] = d["r20"] - d["spy20"]
    d["ex60"] = d["r60"] - d["spy60"]
    cols = ["date", "sym", "stage", "a150", "mom_top20", "brk", "spy_up", "r20", "r60", "ex20", "ex60", "mfe", "mae"]
    d[cols].to_pickle(os.path.join(HERE, "第二轮_样本.pkl"))
    print("完成", len(d), f"{time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()
