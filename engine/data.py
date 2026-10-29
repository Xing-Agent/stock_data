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
# ★ 硬纪律第 4 条字面只点名 retirement_category == "bankruptcy"。
# ★★ 1028 Lin 已拍板:下面这 4 类(EXPR / FRC / SIVB / GTT)虽然字面不是
#   bankruptcy,但实质是破产 / 银行倒闭 / 被接管 / 财务困境退市,普通股在
#   清算里确实归零 —— 一律也按 −100% 记。按最后收盘价结算等于凭空还给策略
#   一笔钱,方向上系统性美化成绩。
#   出处:Shumway (1997, JF) The Delisting Bias in CRSP Data。
BANKRUPTCY_LIKE_CATEGORIES = (
    "bank_failure_and_holding_company_bankruptcy",
    "reporting_noncompliance_then_bankruptcy",
    "bank_receivership",
    "financial_distress_delisting",
)
# ★ Lin 拍板后:两类合并,全部按 −100%
BANKRUPTCY_CATEGORIES = ("bankruptcy",) + BANKRUPTCY_LIKE_CATEGORIES

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
        f"  ★ 其中「字面不是 bankruptcy 但实质破产/接管」的 {len(bkl)} 只:"
        f"{sorted(bkl)} —— ★ 1028 Lin 已拍板,也按 −100% 记(已生效)",
    ]
    return "\n".join(lines)


# ---------------------------------------------------------------- 日线

def _apply_split_fix(df: pd.DataFrame, symbol: str,
                     raw_rows: list[dict] | None = None) -> pd.DataFrame:
    """
    ★ 两步(2026-10-29 第二次重写:比例修正改为读源头 split_coefficient):

      ① ratio_fix  —— ★ 比例一律来自源头 daily.json 的 `split_coefficient`
                      (ratio = 1 / 系数)。把事件日之前的价格乘上 ratio、
                      成交量除以 ratio,接成连续序列。
                      ★ 我们不再自己判断「这是不是拆股、该乘几」——
                      手工清单上一轮被技术方核出错 5 条,根因就是没读这个字段。
      ② cut_series —— 数据里有断裂、而源头系数**解释不了**(系数为 1 或为空):
                      ★ 不许自己编系数,在断裂处把序列切开,只留自洽的那一段。
                      ★ 这一类仍然是手工的(engine/split_gate.EVENTS),
                      因为"切哪一刀"必须有 SEC 证据,系数字段答不了。

    ★ 为什么读了源头系数也不会双重修正:源头只加了 `split_coefficient` 这个
      **标记字段**,价格和成交量一个数都没改(实测 66 个非 1 系数事件,
      当天实际价格比值 ÷ (1/系数) ≈ 1.00 —— 说明价格确实是 raw)。
      所以修正仍然只发生在这里一次。这一条由 split_gate.self_check() 的 ⑦ 项守着。

    多个事件会自动复利:对每个事件把「该日之前」整段乘一次,
    所以 TSLA(2020-08-31 ×1/5、2022-08-25 ×1/3)最早那段恰好 ×1/15。
    """
    # ① 源头系数(主来源)+ FIX_EVENTS(手工覆盖,现在恒为空,只给 A/B 对照用)
    events = split_gate.ratio_events_from_rows(symbol, raw_rows or [])
    events += split_gate.events_for(symbol)
    for ev in events:
        ts = pd.Timestamp(ev.date)
        mask = df.index < ts
        if not mask.any():
            continue
        for col in ("open", "high", "low", "close"):
            df.loc[mask, col] = df.loc[mask, col] * ev.ratio
        # 合股会把成交量按同比例缩小,这里反向还原,保持成交额口径一致
        df.loc[mask, "volume"] = df.loc[mask, "volume"] / ev.ratio

    for ev in split_gate.cuts_for(symbol):
        ts = pd.Timestamp(ev.date)
        df = df[df.index >= ts] if ev.keep == "after" else df[df.index < ts]
    return df


@functools.lru_cache(maxsize=512)
def load_daily(symbol: str) -> pd.DataFrame:
    """
    读一只票的日线,索引是日期,列 open/high/low/close/volume/dollar_volume。
    ★ 已修拆股 —— ★ 比例读源头 `split_coefficient`,不再用手工清单(见 _apply_split_fix)。
    ★ 不做分红复权(数据源没有可信的复权列),
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
    df = _apply_split_fix(df, symbol, raw_rows=rows)
    df["dollar_volume"] = df["close"] * df["volume"]
    return df


# ---------------------------------------------------------------- 分红(总收益口径)
#
# ★★ 2026-10-29 新增,★ 默认关闭(TOTAL_RETURN_DEFAULT = False)。
#
# ★ 大白话:daily.json 每根 bar 自带 `dividend_amount`,169/250 只票有非零值,
#   而引擎以前一行代码都没读过 —— 所以我们所有的收益数字都是**纯价格收益**,
#   系统性低估(绩效窗口内年化股息率中位 2.10% / 均值 3.12%)。
#
# ★★ 这里只提供"读"和"算"的能力,★ 不改变任何现有代码路径:
#   load_daily() / price_panel() / cache.py 一个字都没动,所以默认口径仍是纯价格。
#   要用总收益口径,调用方显式调 dividends() 或 total_return_daily()。
#   ★ 口径切换必须是显式的 —— 悄悄改默认会让所有历史结论无法对账。
#
# ★★ 时点口径(PIT):`dividend_amount` 所在的那一天就是**除息日(ex-date)**,不是派息日。
#   证据(实测,不是假设):
#     · SPY 的非零分红日全部落在 3/6/9/12 月的第三个周五 —— 这正是 SPY 的除息日规则
#       (实测首尾:2014-03-21、2025-12-19,都是当月第三个周五;
#        SPY 的**派息日**在月底,和这些日期对不上)。
#     · ABT 2016-01-13 = ABT 2016 Q1 的除息日(派息日是 2016-02-16)。
#   ★ 所以"持有跨过除息日就拿到这笔分红"是正确的 PIT 口径:
#     买入日 < 除息日 ≤ 卖出日 → 收到(除息日当天买**不**算,除息日当天卖**算**)。
#   ★ 如果哪天发现这个字段其实是派息日,那么我们会把分红记早约 2~6 周 ——
#     方向上是"提前拿到钱",会轻微高估;量级 = 2~6 周的资金时间价值,相对股息本身可忽略。
#   ★ 我们**没有**用"按市值估个股息率"之类的近似 —— 拿不到就是拿不到。

#: ★ 总收益口径的默认值。★ 默认 False = 纯价格收益(与所有历史结论一致)。
TOTAL_RETURN_DEFAULT: bool = False


@functools.lru_cache(maxsize=512)
def dividends(symbol: str) -> pd.Series:
    """
    一只票的每股现金分红序列,索引 = **除息日**,只保留非零。

    ★ 直接读原始 daily.json 的 dividend_amount。拿不到 / 字段缺失 → 返回空序列
      (调用方必须把空序列当"这只票没有可用分红数据",★ 不许用估算顶上)。
    ★ 拆股:分红金额和价格在同一个 bar 上,而我们对**除息日之前**的价格做了拆股折算,
      所以分红金额也要跟着折算,否则"每股分红"和"每股价格"不在同一个口径上。
      做法与价格完全一致 —— 复用 split_gate 从源头系数算出来的同一批事件。
    """
    meta = load_manifest().get(symbol)
    if meta is None or not os.path.exists(meta.daily_path):
        return pd.Series(dtype=float)
    with open(meta.daily_path, encoding="utf-8") as fh:
        rows = (json.load(fh).get("data") or [])
    if not rows:
        return pd.Series(dtype=float)
    recs = []
    for r in rows:
        v = r.get("dividend_amount")
        if v in (None, ""):
            continue
        try:
            x = float(v)
        except (TypeError, ValueError):
            continue
        if x == 0.0 or x != x:
            continue
        recs.append((pd.Timestamp(str(r["date"])[:10]), x))
    if not recs:
        return pd.Series(dtype=float)
    s = pd.Series({d: v for d, v in recs}).sort_index()
    # ★ 和价格同口径:除息日之前的每股分红按同一批拆股系数折算
    for ev in split_gate.ratio_events_from_rows(symbol, rows):
        ts = pd.Timestamp(ev.date)
        m = s.index < ts
        if m.any():
            s.loc[m] = s.loc[m] * ev.ratio
    return s


def total_return_daily(symbol: str, index: pd.DatetimeIndex | None = None
                       ) -> pd.Series:
    """
    一只票的**总收益**日收益率序列 = (收盘价变化 + 当日每股分红) / 前一日收盘价。

    ★ 分红加在**除息日**那一天 —— 价格在除息日本来就会掉下来一个股息,
      把分红加回同一天,两者正好抵销,这是总收益的标准算法。
    """
    df = load_daily(symbol)
    if df.empty:
        return pd.Series(dtype=float)
    c = df["close"]
    if index is not None:
        c = c.reindex(index).ffill()
    d = dividends(symbol).reindex(c.index).fillna(0.0)
    prev = c.shift(1)
    return ((c - prev + d) / prev).replace([np.inf, -np.inf], np.nan).fillna(0.0)


def benchmark_total_return_daily(symbol: str, index: pd.DatetimeIndex
                                 ) -> tuple[pd.Series, bool]:
    """
    基准 ETF 的总收益日收益率 + 「分红数据拿到了没有」的标记。

    ★ 返回 (日收益序列, has_dividends)。has_dividends=False 时调用方**必须**
      在报告里写明"基准只有价格收益",★ 否则就会拿总收益的策略去比价格收益的基准 ——
      那是一个方向相反的新偏差。
    """
    for base in (BENCH_DIR, SECTOR_ETF_DIR):
        p = os.path.join(base, symbol, "daily.json")
        if not os.path.exists(p):
            continue
        with open(p, encoding="utf-8") as fh:
            rows = (json.load(fh).get("data") or [])
        df = pd.DataFrame(rows)
        if df.empty or "close" not in df.columns:
            break
        df["date"] = pd.to_datetime(df["date"])
        df = df.set_index("date").sort_index()
        if "dividend_amount" in df.columns:
            dv_raw = pd.to_numeric(df["dividend_amount"], errors="coerce").fillna(0.0)
        else:
            dv_raw = pd.Series(0.0, index=df.index)
        # ★★ 2026-10-29:这里原来也不做拆股修正 —— 和 load_benchmark() 同一个 bug。
        #   ★ 价格**和每股分红**都要按源头系数折算,否则两者不在同一个口径上:
        #     拆股后每股分红会变小,拿未折算的历史分红去除以已折算的价格 = 虚高股息。
        c_raw = pd.to_numeric(df["close"], errors="coerce")
        for ev in split_gate.ratio_events_from_rows(symbol, rows):
            ts = pd.Timestamp(ev.date)
            mask = df.index < ts
            if not mask.any():
                continue
            c_raw.loc[mask] = c_raw.loc[mask] * ev.ratio
            dv_raw.loc[mask] = dv_raw.loc[mask] * ev.ratio
        c = c_raw.reindex(index).ffill()
        dv = dv_raw[dv_raw != 0.0].reindex(index).fillna(0.0)
        has = bool((dv != 0).any())
        prev = c.shift(1)
        r = ((c - prev + dv) / prev).replace([np.inf, -np.inf], np.nan).fillna(0.0)
        return r, has
    return pd.Series(0.0, index=index), False


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
    退市结算价。★ 2026-10-29 改为以技术方核实的 delisting_settlement_price 为准。

    ★ 大白话:退市那天我们手上的仓位按多少钱平掉。三种:
      ① 技术方查到固定全现金并购价(9 只)→ 按那个价
      ② 技术方确认普通股归零(7 只)→ 0.0,真 −100%
      ③ ★ 技术方说证据拿不到(14 只,null)→ ★ 用最后收盘价,★ 不许当成 0
         (技术方原话:「null 表示证据无法确定,不等于 0」)
    细节和逐只差异见 engine/delisting_gate.py。
    """
    from . import delisting_gate
    last, _ = delisting_info(symbol)
    if last is None:
        return None
    forced = delisting_gate.forced_price(symbol)
    if forced is not None:
        return float(forced)
    return float(load_daily(symbol)["close"].iloc[-1])


# ---------------------------------------------------------------- 交易日历

@functools.lru_cache(maxsize=1)
def trading_calendar() -> pd.DatetimeIndex:
    """用 SPY 的交易日当日历(2014 起,覆盖热机和绩效窗口)。"""
    spy = load_benchmark("SPY")
    return spy.index


@functools.lru_cache(maxsize=32)
def load_benchmark(symbol: str) -> pd.DataFrame:
    """
    读基准 ETF / VIX。先找 pilot_300/benchmarks,再找板块 ETF 目录。

    ★★ 2026-10-29 修复:这个函数**以前完全不做拆股修正** —— 只有 load_daily() 做。
    ★ 后果(A0 线实测):五只行业 ETF 在 2025-12-05 有 −50% 的假跳空
      XLK −49.6% / XLB −50.2% / XLE −50.2% / XLU −50.5% / XLY −49.7%
      —— 那是 Select Sector SPDR 的 2:1 拆股。
    ★ 而这些文件里 split_coefficient **本来就写着 2.0** —— 和前面三次一样,
      字段在文件里,我们没读。这是第四次同类问题。
    ★ 现在和个股走**同一条**修正路径(engine/split_gate.ratio_events_from_rows),
      所以口径一致、不会出现"个股修了 ETF 没修"。
    """
    for base in (BENCH_DIR, SECTOR_ETF_DIR):
        p = os.path.join(base, symbol, "daily.json")
        if os.path.exists(p):
            with open(p, encoding="utf-8") as fh:
                raw = json.load(fh)
            rows = raw["data"]
            df = pd.DataFrame(rows)
            df["date"] = pd.to_datetime(df["date"])
            df = df.set_index("date").sort_index()
            cols = [c for c in ("open", "high", "low", "close", "adjusted_close", "volume")
                    if c in df.columns]
            df = df[cols].apply(pd.to_numeric, errors="coerce")
            df = df[~df.index.duplicated(keep="last")]
            # ★ 和个股同一条路径:比例读源头 split_coefficient
            for ev in split_gate.ratio_events_from_rows(symbol, rows):
                ts = pd.Timestamp(ev.date)
                mask = df.index < ts
                if not mask.any():
                    continue
                for col in ("open", "high", "low", "close", "adjusted_close"):
                    if col in df.columns:
                        df.loc[mask, col] = df.loc[mask, col] * ev.ratio
                if "volume" in df.columns:
                    df.loc[mask, "volume"] = df.loc[mask, "volume"] / ev.ratio
            return df
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
