# -*- coding: utf-8 -*-
"""
★★★ 接新基准 —— ★ 让引擎读到 2004 年起的 SPY / QQQ / IWM / 行业 ETF / GOOGL。

★★ 为什么需要（★ 两个坑）：
 ① 引擎的 `load_benchmark` 只找 `pilot_300/benchmarks` 和 `reference_etfs_20261025`，
   ★★ 那里的 SPY 只有 **2014-01-02 起** → ★★★ 交易日历被卡在 2014，窗口拉不回去。
 ② ★★ 新交付 `market_etf_1106/` 里的文件是 **.json.gz**，
   ★★★ 而 `load_benchmark` 用的是普通 `open` —— **读不了 gz**。

★ 做法：进程内替换 `data.load_benchmark`，★★ 新目录优先、支持 gz、
★★★ **没命中就原样退回原函数**（不许悄悄返回空）。engine 一个字节都不改。

★★ 口径：复用原函数的全部脏活（拆股修正走 `split_gate.ratio_events_from_rows`），
   ★ 只换「从哪儿读」和「怎么解压」。
"""
from __future__ import annotations
import gzip, io, json, os, sys
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from engine import data as edata, split_gate                   # noqa: E402

新目录 = [os.path.join(ROOT, "market_etf_1106"),
        os.path.join(ROOT, "market_extra_1107")]
_原 = edata.load_benchmark
_命中 = {}


def _读(p: str) -> dict:
    o = gzip.open(p, "rt", encoding="utf-8") if p.endswith(".gz") \
        else io.open(p, encoding="utf-8")
    with o as fh:
        return json.load(fh)


def _覆盖(symbol: str) -> pd.DataFrame:
    for base in 新目录:
        for fn in ("daily.json.gz", "daily.json"):
            p = os.path.join(base, symbol, fn)
            if not os.path.exists(p):
                continue
            raw = _读(p)
            rows = raw["data"]
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            cols = [c for c in ("open", "high", "low", "close",
                                "adjusted_close", "volume") if c in df.columns]
            df = df[cols].apply(pd.to_numeric, errors="coerce")
            df = df[~df.index.duplicated(keep="last")]
            # ★★ 拆股修正：走和原函数**同一条**路径，口径一致
            for ev in split_gate.ratio_events_from_rows(symbol, rows):
                ts = pd.Timestamp(ev.date)
                mask = df.index < ts
                if not mask.any():
                    continue
                for c in ("open", "high", "low", "close", "adjusted_close"):
                    if c in df.columns:
                        df.loc[mask, c] = df.loc[mask, c] / ev.ratio
                if "volume" in df.columns:
                    df.loc[mask, "volume"] = df.loc[mask, "volume"] * ev.ratio
            _命中[symbol] = {"来源": os.path.basename(base),
                           "起": str(df.index.min().date()),
                           "止": str(df.index.max().date()), "根数": len(df)}
            return df
    # ★★★ 没命中 → 原样退回原函数（不许悄悄返回空）
    _命中[symbol] = {"来源": "★ 退回老库"}
    return _原(symbol)


def install() -> dict:
    before = id(edata.load_benchmark)
    edata.load_benchmark = _覆盖
    if hasattr(edata, "trading_calendar"):
        try:
            edata.trading_calendar.cache_clear()
        except Exception:
            pass
    spy = _覆盖("SPY")
    return {"★原函数id": before, "★覆盖后id": id(edata.load_benchmark),
            "★真的换掉了": id(edata.load_benchmark) != before,
            "★★★SPY": {"起": str(spy.index.min().date()),
                     "止": str(spy.index.max().date()), "根数": len(spy)},
            "★★★engine改动": "零（进程内替换函数指针）",
            "★没命中怎么办": "原样退回原函数，不悄悄返回空"}


def 命中表() -> dict:
    return dict(_命中)
