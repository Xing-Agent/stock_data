"""
数据层 —— 把仓库里的 json/csv 读成引擎能用的表,并在读的时候就把该修的修掉。

大白话:这个文件是「唯一的进水口」。所有脏活都在这里做完,
后面的判据、九关、链执行器拿到的都是干净数据,不用各自再处理一遍。

它负责四件事:
  1. 读清单(manifest.csv),知道有哪些票、哪些退市了、怎么退的
  2. 读日线,顺手把 8 根未记录的拆股修掉 / 把判不准的票剔除
  3. 退市结算:破产类强制按 −100% 记(不许用最后一天的收盘价)
  4. 读大盘/板块 ETF 和市场广度,给环境过滤用

硬纪律落点:
  · 预热截断:数据从 2016 起读(热机),PERF_START = 2018-01-01 才计入绩效
  · 全池含退市股,绝不只用活着的票
  · 破产类退市按 −100%(Shumway 1997, JF, The Delisting Bias in CRSP Data)
"""

from __future__ import annotations

import csv
import functools
import json
import os
from dataclasses import dataclass, field
from typing import Iterable

import numpy as np
import pandas as pd

from . import split_gate

# ---------------------------------------------------------------- 路径与常量

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PILOT = os.path.join(REPO_ROOT, "pilot_300")
MANIFEST_CSV = os.path.join(PILOT, "manifest.csv")
BREADTH_CSV = os.path.join(PILOT, "breadth_top500.csv")
BENCH_DIR = os.path.join(PILOT, "benchmarks")
SECTOR_ETF_DIR = os.path.join(REPO_ROOT, "reference_etfs_20261025")

WARMUP_START = "2016-01-01"   # 热机起点:指标可以用这之后的数据
PERF_START = "2018-01-01"     # ★ 绩效起点(Fama 1998):这之前的任何盈亏都不计入
PERF_END = "2025-12-31"       # 日线数据到这里为止

# 破产类退市 —— 按 −100% 结算。
# ★ 硬纪律第 4 条只点名了 retirement_category == "bankruptcy"(8 只),
#   严格按字面执行。但数据里还有另外 3 类实质上也是破产/接管:
#   bank_failure_and_holding_company_bankruptcy / reporting_noncompliance_then_bankruptcy
#   / bank_receivership。这 3 类默认 **不** 按 −100%(照字面办),
#   但会在 cohort 报告里单独列出来提醒 —— 需要 Lin 拍板是否一起算。
BANKRUPTCY_CATEGORIES = ("bankruptcy",)
BANKRUPTCY_LIKE_CATEGORIES = (
    "bank_failure_and_holding_company_bankruptcy",
    "reporting_noncompliance_then_bankruptcy",
    "bank_receivership",
    "financial_distress_delisting",
)

ONE_WAY_COST_BPS = 5.0   # 单边 0.05% = 5 个基点(SEC Rule 206(4)-1(d);GIPS 2020 §2.A)


# ---------------------------------------------------------------- 清单

@dataclass
class SymbolMeta:
    symbol: str
    name: str
    origin: str
    size_group: str          # large / mid / small
    sector: str
    delisted: bool
    retirement_category: str
    daily_path: str
    fundamentals_path: str | None
    download_end_date: str

    @property
    def is_bankruptcy(self) -> bool:
        return self.retirement_category in BANKRUPTCY_CATEGORIES

    @property
    def is_bankruptcy_like(self) -> bool:
        return self.retirement_category in BANKRUPTCY_LIKE_CATEGORIES


@functools.lru_cache(maxsize=1)
def load_manifest() -> dict[str, SymbolMeta]:
    """读 manifest.csv。返回 {symbol: SymbolMeta},已经把 8 根拆股里判不准的票剔除。"""
    out: dict[str, SymbolMeta] = {}
    with open(MANIFEST_CSV, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            sym = row["symbol"].strip()
            if sym in split_gate.EXCLUDED_SYMBOLS:
                continue
            if row["origin"] == "pilot_50":
                daily = os.path.normpath(os.path.join(PILOT, row["data_path"]))
                fdir = os.path.dirname(daily)
            else:
                daily = os.path.join(PILOT, sym, "daily.json")
                fdir = os.path.join(PILOT, sym)
            fpath = os.path.join(fdir, "fundamentals.json")
            out[sym] = SymbolMeta(
                symbol=sym,
                name=row["name"],
                origin=row["origin"],
                size_group=row["size_group"],
                sector=row["sector"],
                delisted=row["delisted"].strip().lower() == "true",
                retirement_category=row["retirement_category"].strip(),
                daily_path=daily,
                fundamentals_path=fpath if os.path.exists(fpath) else None,
                download_end_date=row["download_end_date"],
            )
    return out


def cohort_report() -> str:
    """把池子的构成讲清楚,跑任何东西之前先打一遍,免得偷偷用了活下来的票。"""
    m = load_manifest()
    exp = [s for s in m.values() if s.origin == "expansion_250"]
    delisted = [s for s in m.values() if s.delisted]
    bk = [s.symbol for s in m.values() if s.is_bankruptcy]
    bkl = [s.symbol for s in m.values() if s.is_bankruptcy_like]
    lines = [
        "池子构成:",
        f"  可用代码总数 {len(m)}(manifest 300 行,减去拆股闸剔除的 "
        f"{sorted(split_gate.EXCLUDED_SYMBOLS)})",
        f"  其中 expansion_250 {len(exp)} 只 / pilot_50 {len(m) - len(exp)} 只",
        f"  退市股 {len(delisted)} 只(★ 全部保留,不许只用活着的票)",
        f"  按 −100% 结算的破产类 {len(bk)} 只:{sorted(bk)}",
        f"  ⚠ 实质破产/接管但 category 字面不是 bankruptcy 的 {len(bkl)} 只:"
        f"{sorted(bkl)} —— 默认按最后收盘价结算,需 Lin 拍板是否也按 −100%",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- 日线

def _apply_split_fix(df: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """把未记录的拆股修回去:事件日之前的全部价格乘上 ratio,接成连续序列。"""
    for ev in split_gate.events_for(symbol):
        ts = pd.Timestamp(ev.date)
        mask = df.index < ts
        if not mask.any():
            continue
        for col in ("open", "high", "low", "close"):
            df.loc[mask, col] = df.loc[mask, col] * ev.ratio
        # 合股会把成交量按同比例缩小,这里反向还原,保持成交额口径一致
        df.loc[mask, "volume"] = df.loc[mask, "volume"] / ev.ratio
    return df


@functools.lru_cache(maxsize=512)
def load_daily(symbol: str) -> pd.DataFrame:
    """
    读一只票的日线,索引是日期,列 open/high/low/close/volume/dollar_volume。
    ★ 已修拆股。★ 不做分红复权(数据源没有可信的复权列),
      这一点会在结果里标明 —— 不用近似值顶上(硬纪律第 7 条)。
    """
    meta = load_manifest()[symbol]
    with open(meta.daily_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    rows = raw.get("data") or []
    if not rows:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume", "dollar_volume"])
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    keep = ["open", "high", "low", "close", "volume"]
    for c in keep:
        if c not in df.columns:
            df[c] = np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[keep].astype(float)
    df = df[~df.index.duplicated(keep="last")]
    df = _apply_split_fix(df, symbol)
    df["dollar_volume"] = df["close"] * df["volume"]
    return df


def delisting_info(symbol: str) -> tuple[pd.Timestamp | None, bool]:
    """返回(最后一根 K 线日期, 是否按 −100% 结算)。没退市的返回 (None, False)。"""
    meta = load_manifest()[symbol]
    if not meta.delisted:
        return None, False
    df = load_daily(symbol)
    if df.empty:
        return None, meta.is_bankruptcy
    return df.index[-1], meta.is_bankruptcy


def delisting_exit_price(symbol: str) -> float | None:
    """
    退市结算价。
    ★ 破产类:强制 0.0(等价于 −100%),不许用最后一天收盘价
      —— Shumway (1997, JF) The Delisting Bias in CRSP Data。
    其余(并购/自愿清算等):用最后一天收盘价。
    """
    last, forced = delisting_info(symbol)
    if last is None:
        return None
    if forced:
        return 0.0
    return float(load_daily(symbol)["close"].iloc[-1])


# ---------------------------------------------------------------- 交易日历

@functools.lru_cache(maxsize=1)
def trading_calendar() -> pd.DatetimeIndex:
    """用 SPY 的交易日当日历(2014 起,覆盖热机和绩效窗口)。"""
    spy = load_benchmark("SPY")
    return spy.index


@functools.lru_cache(maxsize=32)
def load_benchmark(symbol: str) -> pd.DataFrame:
    """读基准 ETF / VIX。先找 pilot_300/benchmarks,再找板块 ETF 目录。"""
    for base in (BENCH_DIR, SECTOR_ETF_DIR):
        p = os.path.join(base, symbol, "daily.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                raw = json.load(fh)
            df = pd.DataFrame(raw["data"])
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            cols = [c for c in ("open", "high", "low", "close", "adjusted_close", "volume")
                    if c in df.columns]
            df = df[cols].apply(pd.to_numeric, errors="coerce")
            return df[~df.index.duplicated(keep="last")]
    raise FileNotFoundError(
        f"仓库里没有 {symbol} 的日线。可用的是:"
        f"{sorted(available_benchmarks())} —— 拿不到就是拿不到,不用别的顶上(硬纪律第 7 条)"
    )


def available_benchmarks() -> list[str]:
    out = []
    for base in (BENCH_DIR, SECTOR_ETF_DIR):
        if not os.path.isdir(base):
            continue
        for name in os.listdir(base):
            if os.path.exists(os.path.join(base, name, "daily.json")):
                out.append(name)
    return sorted(set(out))


# 成分匹配表(两条基准线里的「基准二」用)
COMPONENT_INDEX = {
    "large": "SPY",
    "mid": "MDY",      # ★ 仓库里没有 MDY —— 用到会直接报错,不拿 IWM/RSP 顶替
    "small": "IWM",
    "equal_weight": "RSP",
}


def resolve_component_index(key: str) -> str:
    """把 large/mid/small/equal_weight 或板块名翻成实际 ETF 代码,拿不到就报错。"""
    sym = COMPONENT_INDEX.get(key, key)
    avail = set(available_benchmarks())
    if sym not in avail:
        raise FileNotFoundError(
            f"成分匹配要求 {key} -> {sym},但仓库里没有 {sym} 的日线。\n"
            f"★ 已有:{sorted(avail)}\n"
            f"★ 拿不到就说拿不到,不许用近似指数顶上(硬纪律第 7 条)。"
            f"要么补 {sym} 的数据,要么把配置里的 component_match 改成已有的。"
        )
    return sym


# ---------------------------------------------------------------- 市场广度

@functools.lru_cache(maxsize=1)
def load_breadth() -> pd.DataFrame:
    """读 breadth_top500.csv(2005 起,含退市股)。第一行是注释,跳过。"""
    df = pd.read_csv(BREADTH_CSV, comment="#")
    df["date"] = pd.to_datetime(df["date"])
    return df.set_index("date").sort_index()


# ---------------------------------------------------------------- 基本面(PIT)

@functools.lru_cache(maxsize=512)
def load_fundamentals(symbol: str) -> dict[str, list[dict]]:
    meta = load_manifest()[symbol]
    if not meta.fundamentals_path:
        return {}
    with open(meta.fundamentals_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return raw.get("financial_versions") or {}


@functools.lru_cache(maxsize=4096)
def _metric_series(symbol: str, metric: str) -> tuple[tuple[pd.Timestamp, float], ...]:
    """
    把一个基本面指标整理成 (可用时间, 值) 的有序序列。
    ★ 可用时间用 accepted_at(SEC 实际受理时间),不是财报期末 ——
      这样「算今天只许用今天及以前的数据」才成立。
    """
    versions = load_fundamentals(symbol).get(metric) or []
    pts: list[tuple[pd.Timestamp, float]] = []
    for v in versions:
        ts = v.get("accepted_at") or v.get("filed_at")
        val = v.get("value")
        if ts is None or val in (None, ""):
            continue
        try:
            pts.append((pd.Timestamp(ts).tz_localize(None), float(val)))
        except (ValueError, TypeError):
            continue
    pts.sort(key=lambda x: x[0])
    return tuple(pts)


def fundamental_as_of(symbol: str, metric: str, asof: pd.Timestamp) -> float | None:
    """取 asof 当天(含)能看到的最新一版指标值。看不到就返回 None,不猜。"""
    pts = _metric_series(symbol, metric)
    val = None
    for ts, v in pts:
        if ts <= asof:
            val = v
        else:
            break
    return val


# ---------------------------------------------------------------- 池子(奇偶拆分)

@dataclass
class Universe:
    """一个可用代码集合 + 它的池子划分。"""
    symbols: list[str] = field(default_factory=list)

    def pool(self, which: str) -> list[str]:
        """
        ★ 池 A = 代码字母序奇数位,池 B = 偶数位。
        为什么用奇偶不用随机拆:随机拆可以重抽,重抽就能抽到好看的那一次。
        奇偶拆只有一种结果,想作弊也没地方作。
        """
        s = sorted(self.symbols)
        if which.upper() == "A":
            return s[0::2]    # 第 1、3、5… 位(1 起算的奇数位)
        if which.upper() == "B":
            return s[1::2]    # 第 2、4、6… 位
        if which.upper() in ("ALL", "*"):
            return s
        raise ValueError(f"池子只能是 A / B / ALL,给的是 {which}")


def full_universe(size_groups: Iterable[str] | None = None,
                  sectors: Iterable[str] | None = None) -> Universe:
    m = load_manifest()
    syms = []
    for s in m.values():
        if size_groups and s.size_group not in set(size_groups):
            continue
        if sectors and s.sector not in set(sectors):
            continue
        syms.append(s.symbol)
    return Universe(sorted(syms))


# ---------------------------------------------------------------- 价格面板

@functools.lru_cache(maxsize=8)
def price_panel(field_name: str = "close", symbols: tuple[str, ...] | None = None) -> pd.DataFrame:
    """
    拼一张宽表:行 = 交易日,列 = 代码。退市之后是 NaN。
    ★ 破产类退市票,在最后一根 K 线之后补一行 0.0,
      这样引擎不管在哪天持有它,都会吃到 −100%。
    """
    cal = trading_calendar()
    syms = list(symbols) if symbols else sorted(load_manifest())
    data: dict[str, pd.Series] = {}
    for sym in syms:
        df = load_daily(sym)
        if df.empty:
            continue
        s = df[field_name].reindex(cal)
        last, forced = delisting_info(sym)
        if last is not None and forced:
            after = cal[cal > last]
            if len(after):
                s.loc[after[0]] = 0.0     # ★ −100% 结算日
        data[sym] = s
    return pd.DataFrame(data, index=cal)


def perf_window(index: pd.DatetimeIndex,
                start: str = PERF_START, end: str = PERF_END) -> pd.DatetimeIndex:
    """★ 预热截断:只有这个窗口里的日子才计入绩效。"""
    return index[(index >= pd.Timestamp(start)) & (index <= pd.Timestamp(end))]


if __name__ == "__main__":
    print(cohort_report())
    print()
    print(split_gate.summary())
    print()
    cal = trading_calendar()
    print(f"交易日历 {cal[0].date()} .. {cal[-1].date()},共 {len(cal)} 个交易日")
    print(f"绩效窗口 {PERF_START} .. {PERF_END},共 {len(perf_window(cal))} 个交易日")
    u = full_universe()
    print(f"全池 {len(u.symbols)} 只 | 池A {len(u.pool('A'))} 只 | 池B {len(u.pool('B'))} 只")
    print(f"可用基准/板块 ETF:{available_benchmarks()}")
