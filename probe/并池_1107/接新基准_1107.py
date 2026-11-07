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

def _扫数据目录() -> list:
    """★★★ 自动扫出所有 `market_*` 数据目录 —— ★ 不靠我记得去写。

    ★★ 为什么改成自动（★★★ 今天同一类错第五次）：
      我手写了 `["market_etf_1106", "market_extra_1107"]` 两个，
      ★ 漏了 **`market_macro_1105`**（VIX 和 DTB3 其实 11-06 就补到 2004 了）
      和 **`market_etf_1107`**（四只风格 ETF）。
      ★★ 于是我调 `load_benchmark('VIX')` 读到了**老目录**里 2014 起的那份，
      ★★★ 就对外说了「VIX 只有 2014 起」—— 而我那天下午刚立了规矩㊺。
    → ★ 结论：**这种错不该靠纪律修，该靠结构修。**
      ★★ 新目录丢进仓库根目录就自动被认，★★★ 我漏不掉。

    ★★★ 排序这件我要自己改一句（★ #68 的教训：不许写没验过的自我担保）：
      我本来写的是「目录名倒序 → 新交付优先」—— ★★ **这句不准**。
      实际倒序结果是 `macro_1105 > extra_1107 > ext_1105 > etf_1107 > etf_1106`，
      ★ `etf_1107` 并没有排在 `ext_1105` 前面。
      ★★ 现在这几个目录之间**没有同名票重叠**（VIX 只在 macro、IWD 只在 etf_1107、
      SPY 只在 etf_1106），所以顺序**此刻不影响结果**；
      ★★★ 但哪天出现重叠，这个顺序就是**任意的** —— 到时候必须显式定优先级，
      不能靠目录名的字典序。★ 这一条写在这里，免得以后当成「已经处理好了」。
    """
    out = []
    for d in sorted(os.listdir(ROOT), reverse=True):
        if not d.startswith("market_"):
            continue
        full = os.path.join(ROOT, d)
        if os.path.isdir(full):
            out.append(full)
    return out


新目录 = _扫数据目录()
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
    global 新目录
    新目录 = _扫数据目录()          # ★ 每次装都重扫，免得中途有新交付
    before = id(edata.load_benchmark)
    edata.load_benchmark = _覆盖
    if hasattr(edata, "trading_calendar"):
        try:
            edata.trading_calendar.cache_clear()
        except Exception:
            pass
    自证 = {}
    for s in ("SPY", "VIX", "DTB3", "IWD", "IWF", "QQQ", "IWM"):
        try:
            d = _覆盖(s)
            自证[s] = f"{d.index.min().date()} → {d.index.max().date()} · {len(d)} 根"
        except Exception as e:
            自证[s] = f"★ 读不到：{type(e).__name__}"
    return {"★原函数id": before, "★覆盖后id": id(edata.load_benchmark),
            "★真的换掉了": id(edata.load_benchmark) != before,
            "★★★自动扫到的数据目录": [os.path.basename(x) for x in 新目录],
            "★★★基准自证": 自证,
            "★★★engine改动": "零（进程内替换函数指针）",
            "★没命中怎么办": "原样退回原函数，不悄悄返回空"}


def 命中表() -> dict:
    return dict(_命中)
