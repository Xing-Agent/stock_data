# -*- coding: utf-8 -*-
"""★★★ 持仓画像 —— ★ Lin 1107 19:38 问的核心一问：**突破信号到底有没有自己走到巨头上？**

★★ 怎么量（口径照抄 engine，不自己发明）：
   `engine/pool_scope.py:90  TIER_BANDS = {"大": (1,500), "中": (501,2000), "小": (2001,None)}`
   ★ 排名定义也照抄：**当年年初回看 60 个交易日的日均成交额排名**（池表 `rank` 列，天生按时点）。
   → ★★★ 所以画像用的是「**进场那一年**这只票在排名表里的 rank / tier」，不是今天的市值。

★★★ 必须分开说的两件（★ 否则这张画像会被读成「信号自己走到巨头上」）：
   ① **排序旋钮**（`ranking`）—— 45 条链全是 `ADV20 降序` = **先买成交额最大的**。
      ★★ 槽位不够时它决定买哪几只 → ★★★ 它**天生**把持仓往大票推，这不是信号的功劳。
   ② **进场扳机**（信号本身）—— 它只决定「哪些票今天合格」。
   → ★★ 所以这一份同时出三栏：
      · **成交的**（实际买到的，受①②共同作用）
      · **合格信号**（信号判定合格、还没过排序这一关的全体）← ★★★ 这一栏才是「信号自己」
      · **可买全池**（当年池子本身的大中小构成）← ★ 分母，用来看①②有没有偏离
   ★★★ 只看第一栏就回答 Lin 那一问 = 把排序旋钮的功劳记在信号头上。

★ 另外报**利润归属**：巨头那几笔占了几成笔数、几成利润（★ 1107 量过技-1 挂闸100日：
  巨头 13.5% 的笔数 → **89% 的利润**；★★ 这次在并池 3,858 只上重量）。
"""
from __future__ import annotations
import io, json, os, sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
POOL = os.path.join(ROOT, "probe", "并池2004_1107", "pool_MERGED2004_ALL_1107.csv")
巨头名单 = ["AAPL", "MSFT", "AMZN", "GOOG", "GOOGL", "META", "NVDA",
         "BRK.B", "JPM", "AVGO", "NFLX", "TSLA"]
_池: pd.DataFrame | None = None


def 档(rank) -> str:
    """★ 照抄 engine/pool_scope.py:90 的 TIER_BANDS，不自己定边界。"""
    if rank is None or (isinstance(rank, float) and not np.isfinite(rank)):
        return "当年不在池"
    r = int(rank)
    if r <= 500:
        return "大(1-500)"
    if r <= 2000:
        return "中(501-2000)"
    return "小(2001+)"


def 池表() -> pd.DataFrame:
    global _池
    if _池 is None:
        d = pd.read_csv(POOL, usecols=["year", "symbol", "rank", "tier"])
        d["year"] = d["year"].astype(int)
        _池 = d.set_index(["year", "symbol"])
    return _池


def 查rank(sym: str, 年: int):
    try:
        return int(池表().loc[(年, sym), "rank"])
    except Exception:
        return None


def 画像(ledger_csv: str, 标签: str = "") -> dict:
    """★ 一条臂的持仓画像（**成交的**那一栏）。"""
    d = pd.read_csv(ledger_csv)
    if not len(d):
        return {"★笔数": 0}
    d["entry_date"] = pd.to_datetime(d["entry_date"])
    d["年"] = d["entry_date"].dt.year
    d["rank"] = [查rank(s, y) for s, y in zip(d["symbol"].astype(str), d["年"])]
    d["档"] = d["rank"].map(档)
    d["净盈亏"] = d["net_pnl"].astype(float)

    笔数占比 = (d["档"].value_counts(normalize=True)).round(4).to_dict()
    # ★★★ 利润占比：★ 分母用「正利润之和」会把亏损笔藏掉 → 用**净利润之和**，
    #   ★★ 并且同时报每一档的净利润绝对值，免得「占比 200%」这种读不懂的数。
    净 = d.groupby("档")["净盈亏"].sum()
    总净 = float(d["净盈亏"].sum())
    巨 = d["symbol"].astype(str).isin(巨头名单)
    return {
        "★臂": 标签 or os.path.basename(ledger_csv),
        "★笔数": int(len(d)),
        "★★★笔数占比_按档": 笔数占比,
        "★各档净盈亏": {k: round(float(v), 2) for k, v in 净.items()},
        "★总净盈亏": round(总净, 2),
        "★★★各档净盈亏占总净的比例": (
            {k: round(float(v) / 总净, 4) for k, v in 净.items()} if abs(总净) > 1e-9
            else "★ 总净盈亏≈0，占比没有意义"),
        "★★★巨头那几只": {
            "名单": 巨头名单,
            "笔数": int(巨.sum()), "笔数占比": round(float(巨.mean()), 4),
            "净盈亏": round(float(d.loc[巨, "净盈亏"].sum()), 2),
            "★占总净的比例": (round(float(d.loc[巨, "净盈亏"].sum()) / 总净, 4)
                          if abs(总净) > 1e-9 else None),
            "★买到的是哪几只": sorted(set(d.loc[巨, "symbol"].astype(str))),
        },
        "★当年不在池却成交了的笔数": int((d["档"] == "当年不在池").sum()),
        "★口径": "档位照抄 engine/pool_scope.py TIER_BANDS；rank 取**进场那一年**的排名",
    }


def 可买全池画像(年列: list[int]) -> dict:
    """★ 分母那一栏：池子本身的大中小构成（★★ 不经过信号、也不经过排序）。"""
    d = 池表().reset_index()
    d = d[d["year"].isin(年列)]
    d["档"] = d["rank"].map(档)
    return {"★年份": [int(x) for x in sorted(set(年列))],
            "★只×年": int(len(d)),
            "★★★笔数占比_按档": d["档"].value_counts(normalize=True).round(4).to_dict(),
            "★说明": "★★★ 这是**分母** —— 池子里本来就有多少大/中/小"}
