"""
链执行器 —— 吃一份七步配置,吐一份完整结果。

★ 为什么要有这个文件(整件事的核心):
  以前我们测的是「一个进场条件」。但实测发现:
      进场扳机只占价值的 5%
      选股范围 + 环境过滤占 70%
      出场 + 风控占 25%
  所以必须改成测「一整条链」。

★ 每个大师 = 一份配置文件(YAML/JSON),不是一个新程序。
  要跑 20 多条链,写 20 多个脚本是错的 —— 这个文件就是那唯一的脚本。

七步:
  ① universe      选股范围:在哪些票里找(市值 / 流动性 / 基本面闸门 / 行业)
  ② regime        环境过滤:什么时候整个不做(大盘闸门)
  ③ entry         进场扳机:什么时候买
  ④ initial_stop  初始止损:第一道止损放哪
  ⑤ trailing_stop 移动止损:持仓中怎么抬
  ⑥ exit          离场:止盈 / 时间止损 / 跟踪止损触发
  ⑦ sizing        仓位:每笔冒多少风险

成交约定(因果性):
  · 信号在 t 日收盘后成立 → t+1 日开盘成交
  · 止损被触及 → 当日成交,跳空开盘低于止损价则按开盘价成交(不占便宜)
  · 止盈 / 时间止损按收盘判断 → 次日开盘成交
  · 退市:破产类按 0 结算(−100%),其余按最后收盘价
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from . import data, signals

TRADING_DAYS_PER_YEAR = 252


# ================================================================ 配置

@dataclass
class ChainConfig:
    raw: dict[str, Any]

    @classmethod
    def load(cls, path: str) -> "ChainConfig":
        with open(path, encoding="utf-8") as fh:
            if path.endswith((".yaml", ".yml")):
                import yaml
                cfg = yaml.safe_load(fh)
            else:
                cfg = json.load(fh)
        return cls(cfg).validate()

    @classmethod
    def from_dict(cls, cfg: dict) -> "ChainConfig":
        return cls(cfg).validate()

    def validate(self) -> "ChainConfig":
        need = ["universe", "regime", "entry", "initial_stop",
                "trailing_stop", "exit", "sizing"]
        missing = [k for k in need if k not in self.raw]
        if missing:
            raise ValueError(f"配置缺了这几步(七步一步都不能少):{missing}")
        # 硬纪律第 6 条:参数必须标出处
        for step in need:
            blk = self.raw[step] or {}
            if isinstance(blk, dict) and blk.get("params") and not blk.get("source"):
                raise ValueError(
                    f"★ 第 {step} 步有参数但没写 source。参数只能来自原著或行业惯例,"
                    f"并在配置里标明出处(硬纪律第 6 条,禁止网格搜索)。")
        return self

    def get(self, k: str, default=None):
        return self.raw.get(k, default)

    @property
    def name(self) -> str:
        return (self.raw.get("meta") or {}).get("name", "unnamed_chain")

    def copy_with(self, **overrides) -> "ChainConfig":
        import copy
        cfg = copy.deepcopy(self.raw)
        for k, v in overrides.items():
            cfg[k] = v
        return ChainConfig(cfg)   # 改写过的内部变体不再强制 validate


# ================================================================ 交易与结果

@dataclass
class Trade:
    symbol: str
    entry_date: pd.Timestamp
    entry_price: float
    shares: float
    initial_stop: float
    exit_date: pd.Timestamp | None = None
    exit_price: float = float("nan")
    reason: str = ""

    @property
    def risk_per_share(self) -> float:
        return abs(self.entry_price - self.initial_stop)

    @property
    def gross_pnl(self) -> float:
        return (self.exit_price - self.entry_price) * self.shares

    @property
    def gross_return(self) -> float:
        if self.entry_price <= 0:
            return float("nan")
        return self.exit_price / self.entry_price - 1.0

    @property
    def r_multiple(self) -> float:
        """每笔赚了几个 R(R = 进场时冒的那点风险)。"""
        r = self.risk_per_share
        if r <= 0 or not np.isfinite(r):
            return float("nan")
        return (self.exit_price - self.entry_price) / r

    @property
    def holding_days(self) -> int:
        if self.exit_date is None:
            return 0
        return int(np.busday_count(self.entry_date.date(), self.exit_date.date()))


@dataclass
class ChainResult:
    name: str
    equity_net: pd.Series
    equity_gross: pd.Series
    exposure: pd.Series          # 每日净敞口(持仓市值 / 权益)
    trades: list[Trade]
    notes: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)


# ================================================================ 预处理

class _Book:
    """把每只票需要的东西一次算完,循环里只查表。"""

    def __init__(self, cfg: ChainConfig, symbols: list[str], calendar: pd.DatetimeIndex):
        self.cal = calendar
        self.symbols: list[str] = []
        self.open: dict[str, np.ndarray] = {}
        self.high: dict[str, np.ndarray] = {}
        self.low: dict[str, np.ndarray] = {}
        self.close: dict[str, np.ndarray] = {}
        self.entry: dict[str, np.ndarray] = {}
        self.eligible: dict[str, np.ndarray] = {}
        self.chand: dict[str, np.ndarray] = {}
        self.atr: dict[str, np.ndarray] = {}
        self.last_bar: dict[str, int] = {}
        self.delist_px: dict[str, float] = {}

        uni = cfg.get("universe") or {}
        st = (cfg.get("trailing_stop") or {}).get("params", {}) or {}
        istop = (cfg.get("initial_stop") or {}).get("params", {}) or {}
        atr_p = int(istop.get("atr_period", st.get("atr_period", 20)))
        ch_p = int(st.get("lookback", 22))
        ch_m = float(st.get("multiple", 3.0))
        entry_fn = signals.make_entry(cfg.get("entry") or {"type": "never"})
        meta = data.load_manifest()

        size_groups = uni.get("size_groups")
        sectors = uni.get("sectors")
        min_dv = uni.get("min_dollar_volume")
        min_px = uni.get("min_price")
        dv_period = int(uni.get("dollar_volume_period", 63))
        fgates = uni.get("fundamental_gates") or []

        for sym in symbols:
            m = meta[sym]
            if size_groups and m.size_group not in set(size_groups):
                continue
            if sectors and m.sector not in set(sectors):
                continue
            df = data.load_daily(sym)
            if df.empty or len(df) < 60:
                continue
            r = df.reindex(calendar)
            n = len(calendar)
            valid = r["close"].notna().to_numpy()
            if valid.sum() < 60:
                continue

            elig = valid.copy()
            if min_px is not None:
                elig &= (r["close"].to_numpy(dtype=float) >= float(min_px))
            if min_dv is not None:
                dv = signals.rolling_median_dollar_volume(
                    df.assign(dollar_volume=df["dollar_volume"]), dv_period
                ).reindex(calendar).to_numpy(dtype=float)
                elig &= np.nan_to_num(dv, nan=-1.0) >= float(min_dv)
            for g in fgates:
                elig &= self._fundamental_mask(sym, g, calendar)

            self.symbols.append(sym)
            self.open[sym] = r["open"].to_numpy(dtype=float)
            self.high[sym] = r["high"].to_numpy(dtype=float)
            self.low[sym] = r["low"].to_numpy(dtype=float)
            self.close[sym] = r["close"].to_numpy(dtype=float)
            self.entry[sym] = entry_fn(df).reindex(calendar).fillna(False).to_numpy(dtype=bool)
            self.eligible[sym] = elig
            self.atr[sym] = signals.atr(df, atr_p).reindex(calendar).to_numpy(dtype=float)
            self.chand[sym] = signals.chandelier_raw(
                df, ch_p, ch_m, atr_p).reindex(calendar).to_numpy(dtype=float)
            idx = np.flatnonzero(valid)
            self.last_bar[sym] = int(idx[-1]) if len(idx) else n - 1
            px = data.delisting_exit_price(sym)
            self.delist_px[sym] = px if px is not None else float("nan")

    @staticmethod
    def _fundamental_mask(sym: str, gate: dict, cal: pd.DatetimeIndex) -> np.ndarray:
        """
        基本面闸门,★ 严格 PIT:某天只看那天之前 SEC 已经受理的版本。
        看不到数据 → 当天不合格(不猜、不用近似值顶上)。
        """
        metric, op = gate["metric"], gate.get("op", "ge")
        thr = float(gate["value"])
        out = np.zeros(len(cal), dtype=bool)
        pts = data._metric_series(sym, metric)
        if not pts:
            return out
        ts = np.array([p[0] for p in pts])
        vs = np.array([p[1] for p in pts], dtype=float)
        pos = np.searchsorted(ts, cal.to_numpy(), side="right") - 1
        have = pos >= 0
        val = np.where(have, vs[np.clip(pos, 0, len(vs) - 1)], np.nan)
        with np.errstate(invalid="ignore"):
            if op == "ge":
                out = val >= thr
            elif op == "le":
                out = val <= thr
            elif op == "gt":
                out = val > thr
            elif op == "lt":
                out = val < thr
            else:
                raise ValueError(f"基本面闸门 op 只能是 ge/le/gt/lt,给的是 {op}")
        return np.nan_to_num(out, nan=False).astype(bool)


def _regime_mask(cfg: ChainConfig, cal: pd.DatetimeIndex) -> np.ndarray:
    """
    ② 环境过滤 —— 什么时候整个不做。全部规则都要成立才算「可以做」。
    支持:
      index_above_ma   大盘指数在 N 日均线之上
      breadth_above    市场广度字段高于阈值
      vix_below        VIX 低于阈值
      none             不过滤
    """
    rules = (cfg.get("regime") or {}).get("rules") or []
    ok = np.ones(len(cal), dtype=bool)
    for rule in rules:
        t = rule.get("type", "none")
        if t == "none":
            continue
        if t == "index_above_ma":
            sym, n = rule.get("symbol", "SPY"), int(rule.get("ma", 200))
            b = data.load_benchmark(sym).reindex(cal)
            ma = signals.sma(b["close"], n)
            ok &= np.nan_to_num((b["close"] > ma).to_numpy(), nan=False).astype(bool)
        elif t == "breadth_above":
            fld, v = rule["field"], float(rule["value"])
            s = data.load_breadth()[fld].reindex(cal).ffill()
            ok &= np.nan_to_num((s > v).to_numpy(dtype=float), nan=-1.0) > 0
        elif t == "vix_below":
            v = float(rule["value"])
            s = data.load_benchmark("VIX")["close"].reindex(cal).ffill()
            ok &= np.nan_to_num(s.to_numpy(dtype=float), nan=1e9) < v
        else:
            raise ValueError(f"不认识的环境过滤规则 type={t}")
    # ★ 环境信号也在收盘后成立,次日才生效 —— 不许用当天的闸门做当天的决定
    return np.concatenate([[False], ok[:-1]])


# ================================================================ 主循环

def run_chain(cfg: ChainConfig,
              symbols: list[str] | None = None,
              start: str = data.PERF_START,
              end: str = data.PERF_END,
              initial_equity: float = 1_000_000.0) -> ChainResult:
    """跑一条链。返回净值曲线、每日敞口、全部成交。"""
    cal_all = data.trading_calendar()
    book = _Book(cfg, symbols or sorted(data.load_manifest()), cal_all)
    regime = _regime_mask(cfg, cal_all)

    perf = data.perf_window(cal_all, start, end)
    if len(perf) == 0:
        raise ValueError(f"绩效窗口 {start}..{end} 里没有交易日")
    i0 = int(cal_all.get_loc(perf[0]))
    i1 = int(cal_all.get_loc(perf[-1]))

    cost = float((cfg.get("costs") or {}).get("one_way_bps", data.ONE_WAY_COST_BPS)) / 10_000.0
    sz = cfg.get("sizing") or {}
    sz_type = sz.get("type", "risk_fraction")
    szp = sz.get("params", {}) or {}
    risk_frac = float(szp.get("risk_per_trade", 0.01))
    max_pos = int(szp.get("max_positions", 10))
    max_w = float(szp.get("max_weight", 1.0 / max(1, max_pos)))

    istop = cfg.get("initial_stop") or {}
    isp = istop.get("params", {}) or {}
    istop_type = istop.get("type", "atr_multiple")
    istop_mult = float(isp.get("multiple", 2.0))
    istop_pct = float(isp.get("pct", 0.10))

    trail_type = (cfg.get("trailing_stop") or {}).get("type", "none")

    ex = cfg.get("exit") or {}
    exp_ = ex.get("params", {}) or {}
    target_r = exp_.get("profit_target_r")
    time_stop = exp_.get("time_stop_days")
    target_r = float(target_r) if target_r is not None else None
    time_stop = int(time_stop) if time_stop is not None else None

    equal_all = sz_type == "equal_weight_all"

    cash = initial_equity
    cash_gross = initial_equity
    pos: dict[str, dict] = {}
    trades: list[Trade] = []
    eq_net, eq_gross, expo = [], [], []
    pending_exit: dict[str, str] = {}
    pending_entry: list[str] = []
    notes: list[str] = []
    traded_notional = 0.0

    for i in range(i0, i1 + 1):
        day = cal_all[i]

        # ---- 1) 昨天收盘决定的离场,今天开盘执行
        for sym in list(pending_exit):
            if sym in pos:
                px = book.open[sym][i]
                if not np.isfinite(px):
                    px = _px(book, sym, i, "close")
                net, gross, notional = _close_pos(
                    pos, sym, day, float(px), pending_exit[sym], trades, cost)
                cash += net
                cash_gross += gross
                traded_notional += notional
            pending_exit.pop(sym, None)

        # ---- 2) 昨天收盘的信号,今天开盘买入
        queue = [s for s in pending_entry
                 if s not in pos and np.isfinite(book.open[s][i]) and book.open[s][i] > 0]
        remaining = len(queue)
        for sym in queue:
            if not equal_all and len(pos) >= max_pos:
                break
            entry_px = float(book.open[sym][i])
            equity_now = cash + sum(
                p["shares"] * _px(book, s, i, "open") for s, p in pos.items())
            stop0 = _initial_stop(book, sym, i, entry_px, istop_type,
                                  istop_mult, istop_pct)
            if not np.isfinite(stop0) or stop0 >= entry_px:
                remaining -= 1
                continue
            if equal_all:
                # 等权买入持有:把手上的现金平摊给还没买的那几只
                notional = cash / max(1, remaining)
                shares = notional / entry_px
            elif sz_type == "risk_fraction":
                shares = (equity_now * risk_frac) / (entry_px - stop0)
                shares = min(shares, equity_now * max_w / entry_px)
            elif sz_type == "fixed_fraction":
                shares = equity_now * max_w / entry_px
            else:
                raise ValueError(f"不认识的仓位 type={sz_type}")
            notional = shares * entry_px
            budget = cash / (1 + cost)
            if notional > budget:
                notional = budget
                shares = notional / entry_px
            remaining -= 1
            if shares <= 0 or notional <= 0:
                continue
            cash -= notional * (1 + cost)
            cash_gross -= notional
            traded_notional += notional
            pos[sym] = {"shares": shares, "entry": entry_px, "stop": stop0,
                        "init_stop": stop0, "entry_i": i,
                        "trade": Trade(sym, day, entry_px, shares, stop0)}
        pending_entry = []

        # ---- 3) 持仓当日:先查止损是否被触及
        for sym in list(pos):
            p = pos[sym]
            lo, op_, cl = book.low[sym][i], book.open[sym][i], book.close[sym][i]
            if i >= book.last_bar[sym]:
                dpx = book.delist_px[sym]
                px = (float(dpx) if np.isfinite(dpx)
                      else float(cl if np.isfinite(cl) else p["entry"]))
                net, gross, notional = _close_pos(
                    pos, sym, day, px, "退市结算", trades, cost)
                cash += net
                cash_gross += gross
                traded_notional += notional
                continue
            if np.isfinite(lo) and lo <= p["stop"]:
                fill = min(p["stop"], op_) if np.isfinite(op_) else p["stop"]
                net, gross, notional = _close_pos(
                    pos, sym, day, float(fill), "止损", trades, cost)
                cash += net
                cash_gross += gross
                traded_notional += notional

        # ---- 4) 还活着的持仓:抬止损 + 收盘判离场
        for sym, p in pos.items():
            cl = book.close[sym][i]
            if not np.isfinite(cl):
                continue
            if trail_type == "chandelier":
                raw = book.chand[sym][i]
                if np.isfinite(raw):
                    # ★★ 两条铁律:不能高于当根收盘;只能往上抬
                    cand = min(raw, cl)
                    p["stop"] = max(p["stop"], cand)
                    assert p["stop"] <= cl + 1e-9, (
                        f"吊灯止损高于当根收盘:{sym} {day.date()} "
                        f"stop={p['stop']} close={cl}")
            r_now = ((cl - p["entry"]) / (p["entry"] - p["init_stop"])
                     if p["entry"] > p["init_stop"] else float("nan"))
            if target_r is not None and np.isfinite(r_now) and r_now >= target_r:
                pending_exit[sym] = "止盈"
            elif time_stop is not None and (i - p["entry_i"]) >= time_stop:
                pending_exit[sym] = "时间止损"

        # ---- 5) 今天收盘产生明天的进场信号
        regime_next = bool(regime[i + 1]) if i + 1 < len(cal_all) else False
        if regime_next:
            cands = [s for s in book.symbols
                     if s not in pos and book.entry[s][i] and book.eligible[s][i]
                     and i < book.last_bar[s]]
            slots = max(0, max_pos - len(pos))
            if not equal_all and len(cands) > slots:
                # 名额不够时按代码字母序取前几只 —— 规则固定、可复现,
                # 不按「哪只好看」挑(那就是偷看结果)
                cands = sorted(cands)[:slots]
            pending_entry = cands
        else:
            # 环境关闸:清掉全部持仓(次日开盘)
            if (cfg.get("regime") or {}).get("flatten_when_off", True):
                for sym in pos:
                    pending_exit.setdefault(sym, "环境关闸")

        # ---- 6) 记净值与敞口
        mv = sum(p["shares"] * _px(book, s, i, "close") for s, p in pos.items())
        e_net = cash + mv
        e_gross = cash_gross + mv
        eq_net.append(e_net)
        eq_gross.append(e_gross)
        expo.append(mv / e_net if e_net > 0 else 0.0)

    # 收尾:还没平的仓按最后一天收盘价记
    last = cal_all[i1]
    for sym in list(pos):
        px = _px(book, sym, i1, "close")
        _close_pos(pos, sym, last, float(px), "期末平仓", trades, cost)
    # 注:期末平仓只为了让每笔成交统计完整;净值曲线最后一点已按收盘市值记过了

    res = ChainResult(
        name=cfg.name,
        equity_net=pd.Series(eq_net, index=perf, dtype=float),
        equity_gross=pd.Series(eq_gross, index=perf, dtype=float),
        exposure=pd.Series(expo, index=perf, dtype=float),
        trades=trades,
        notes=notes,
    )
    res.metrics["traded_notional"] = traded_notional
    res.metrics["initial_equity"] = initial_equity
    return res


def _px(book: _Book, sym: str, i: int, field_name: str) -> float:
    arr = getattr(book, field_name)[sym]
    v = arr[i]
    if np.isfinite(v):
        return float(v)
    j = min(i, book.last_bar[sym])
    while j >= 0 and not np.isfinite(book.close[sym][j]):
        j -= 1
    return float(book.close[sym][j]) if j >= 0 else 0.0


def _initial_stop(book: _Book, sym: str, i: int, entry_px: float,
                  kind: str, mult: float, pct: float) -> float:
    if kind == "atr_multiple":
        a = book.atr[sym][i - 1] if i > 0 else np.nan
        if not np.isfinite(a):
            return float("nan")
        return entry_px - mult * float(a)
    if kind == "pct":
        return entry_px * (1.0 - pct)
    if kind == "chandelier":
        raw = book.chand[sym][i - 1] if i > 0 else np.nan
        return float(min(raw, entry_px * 0.999)) if np.isfinite(raw) else float("nan")
    raise ValueError(f"不认识的初始止损 type={kind}")


def _close_pos(pos: dict, sym: str, day: pd.Timestamp, px: float,
               reason: str, trades: list[Trade], cost: float
               ) -> tuple[float, float, float]:
    """平掉一个仓位。返回 (净回款, 毛回款, 成交金额)。"""
    p = pos.pop(sym)
    t: Trade = p["trade"]
    t.exit_date, t.exit_price, t.reason = day, px, reason
    trades.append(t)
    notional = p["shares"] * px
    return notional * (1 - cost), notional, notional


# ================================================================ 指标

def _drawdown(eq: pd.Series) -> tuple[float, int, pd.Timestamp | None]:
    """最大回撤、最长水下持续天数(Peter Martin 1989 Ulcer Index 体系)。"""
    peak = eq.cummax()
    dd = eq / peak - 1.0
    mdd = float(dd.min()) if len(dd) else float("nan")
    under = (eq < peak).to_numpy()
    longest, cur = 0, 0
    for u in under:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    trough = dd.idxmin() if len(dd) else None
    return mdd, longest, trough


def _ulcer_index(eq: pd.Series) -> float:
    """Ulcer Index(Peter Martin 1989):水下深度的均方根,比最大回撤更能反映「煎熬」。"""
    peak = eq.cummax()
    dd = (eq / peak - 1.0) * 100.0
    return float(np.sqrt(np.mean(np.square(dd)))) if len(dd) else float("nan")


def _cagr(eq: pd.Series) -> float:
    if len(eq) < 2 or eq.iloc[0] <= 0:
        return float("nan")
    yrs = len(eq) / TRADING_DAYS_PER_YEAR
    return float((eq.iloc[-1] / eq.iloc[0]) ** (1 / yrs) - 1.0)


def _longest_losing_streak(trades: list[Trade]) -> int:
    """最长连续多少笔不赚钱。"""
    longest = cur = 0
    for t in sorted(trades, key=lambda x: (x.exit_date or x.entry_date)):
        if np.isfinite(t.gross_return) and t.gross_return > 0:
            cur = 0
        else:
            cur += 1
            longest = max(longest, cur)
    return longest


def _yearly(eq: pd.Series) -> dict[str, float]:
    out = {}
    for y, g in eq.groupby(eq.index.year):
        if len(g) >= 2:
            out[str(y)] = float(g.iloc[-1] / g.iloc[0] - 1.0)
    return out


# ---------------------------------------------------------------- 基准二:同等仓位大盘

def exposure_matched_benchmark(res: ChainResult,
                               component_match: str,
                               risk_free_annual: float | None,
                               ) -> dict[str, Any]:
    """
    ★★ 基准二「同等仓位大盘」—— 这条是新的,必须做。

    大白话:一条只有三成时间在场的策略,不该拿它跟「全程满仓的标普」比。
    公平的比法是:做一个「同样只有三成仓位、其余放现金」的大盘组合。

    做法:Ē = 这条链全周期的时间加权平均净敞口(★ 固定值)
         基准 = Ē × 成分匹配指数 + (1 − Ē) × 无风险利率

    ★★ Ē 必须用全周期固定值,不许按日动态跟踪实际敞口 ——
       按日跟踪等于把「什么时候该空仓」这个本事白送给基准,
       结果 alpha 会恒等于零,基准就废了。

    出处:Treynor & Mazuy (1966);Merton (1981);Jensen (1968)。
    成分匹配:大盘股→SPY · 中盘→MDY · 等权→RSP · 单行业→该行业 ETF。
    |Ē| ≤ 0.10 → 判为市场中性,基准直接用无风险利率。
    """
    e_bar = float(res.exposure.mean())
    notes: list[str] = []
    rf_annual = risk_free_annual
    if rf_annual is None:
        rf_annual = 0.0
        notes.append("★ 仓库里没有无风险利率序列(只有 TLT,那是长债 ETF 不是短端利率)。"
                     "现金腿按 0% 记,并在此标明 —— 不拿近似值顶上(硬纪律第 7 条)。"
                     "要做准必须补一条 3 个月期美债收益率序列。")
    rf_daily = (1.0 + rf_annual) ** (1 / TRADING_DAYS_PER_YEAR) - 1.0

    if abs(e_bar) <= 0.10:
        notes.append(f"|Ē|={abs(e_bar):.3f} ≤ 0.10 → 判为市场中性,基准直接用无风险利率")
        bench_ret = pd.Series(rf_daily, index=res.equity_net.index)
        idx_sym = "(无,市场中性)"
    else:
        idx_sym = data.resolve_component_index(component_match)
        b = data.load_benchmark(idx_sym)["close"].reindex(res.equity_net.index).ffill()
        r_idx = b.pct_change().fillna(0.0)
        bench_ret = e_bar * r_idx + (1.0 - e_bar) * rf_daily

    bench_eq = (1.0 + bench_ret).cumprod() * float(res.equity_net.iloc[0])
    mdd, under, _ = _drawdown(bench_eq)
    return {
        "E_bar_固定净敞口": e_bar,
        "成分匹配指数": idx_sym,
        "无风险利率_年化": rf_annual,
        "基准总收益": float(bench_eq.iloc[-1] / bench_eq.iloc[0] - 1.0),
        "基准CAGR": _cagr(bench_eq),
        "基准最大回撤": mdd,
        "基准最长水下天数": under,
        "超额收益_对同等仓位大盘": float(
            res.equity_net.iloc[-1] / res.equity_net.iloc[0] - bench_eq.iloc[-1] / bench_eq.iloc[0]),
        "说明": notes,
        "_equity": bench_eq,
    }


# ---------------------------------------------------------------- 基准一:同环境随机进场

def random_entry_benchmark(cfg: ChainConfig, res: ChainResult,
                           symbols: list[str] | None,
                           start: str, end: str,
                           n_seeds: int = 5) -> dict[str, Any]:
    """
    ★ 基准一:同环境随机进场 —— 其余六步完全一样,只把第③步换成随机。
    随机的触发频率对齐真信号的实际频率,这样比的是「挑得准不准」,
    不是「做得多不多」。
    """
    n_tr = len(res.trades)
    days = max(1, len(res.equity_net))
    rate = min(1.0, max(1e-6, n_tr / days / max(1, 1)))
    rets, mdds = [], []
    for k in range(n_seeds):
        c2 = cfg.copy_with(entry={"type": "random",
                                  "params": {"rate": rate, "seed": 20181001 + 977 * k},
                                  "source": "基准一:同环境随机进场,频率对齐真信号"})
        r2 = run_chain(c2, symbols, start, end,
                       initial_equity=float(res.metrics["initial_equity"]))
        rets.append(float(r2.equity_net.iloc[-1] / r2.equity_net.iloc[0] - 1.0))
        mdds.append(_drawdown(r2.equity_net)[0])
    return {
        "随机进场_平均总收益": float(np.mean(rets)),
        "随机进场_收益标准差": float(np.std(rets, ddof=1)) if len(rets) > 1 else float("nan"),
        "随机进场_平均最大回撤": float(np.mean(mdds)),
        "随机进场_跑了几个种子": n_seeds,
        "真信号减随机进场": float(
            res.equity_net.iloc[-1] / res.equity_net.iloc[0] - 1.0 - np.mean(rets)),
        "随机进场触发率": rate,
    }


# ---------------------------------------------------------------- 分步归因

ATTRIBUTION_STEPS = ("买入持有", "+环境", "+选股", "+出场", "完整链")


def attribution(cfg: ChainConfig, symbols: list[str] | None,
                start: str, end: str,
                initial_equity: float = 1_000_000.0) -> pd.DataFrame:
    """
    五行分步归因。★ 每一行必须同时报收益和代价(最大回撤),不许只报收益那一半。

    一行一行加东西,看价值是哪一步贡献的:
      买入持有 —— 全池等权买了就不动
      +环境   —— 加上大盘闸门,关闸就空仓
      +选股   —— 再加上选股范围(市值/流动性/基本面)
      +出场   —— 再加上止损和离场规则
      完整链 —— 最后才加真正的进场扳机和仓位规则
    """
    flat = {"rules": [], "flatten_when_off": True}
    no_stop = {"type": "pct", "params": {"pct": 0.999},
               "source": "归因中间行:等价于不设止损"}
    none_trail = {"type": "none"}
    no_exit = {"type": "signal_only", "params": {}}
    eq_all = {"type": "equal_weight_all",
              "params": {"max_weight": 1.0 / 60.0, "max_positions": 60},
              "source": "归因中间行:等权买入持有,权重上限 1/60"}
    always = {"type": "always", "source": "归因中间行:天天都算信号"}
    open_uni = {k: v for k, v in (cfg.get("universe") or {}).items()
                if k in ("size_groups", "sectors")}

    variants = {
        "买入持有": cfg.copy_with(universe=open_uni, regime=flat, entry=always,
                                  initial_stop=no_stop, trailing_stop=none_trail,
                                  exit=no_exit, sizing=eq_all),
        "+环境": cfg.copy_with(universe=open_uni, entry=always,
                               initial_stop=no_stop, trailing_stop=none_trail,
                               exit=no_exit, sizing=eq_all),
        "+选股": cfg.copy_with(entry=always, initial_stop=no_stop,
                               trailing_stop=none_trail, exit=no_exit, sizing=eq_all),
        "+出场": cfg.copy_with(entry=always, sizing=eq_all),
        "完整链": cfg,
    }
    rows = []
    for label in ATTRIBUTION_STEPS:
        r = run_chain(variants[label], symbols, start, end, initial_equity)
        mdd, under, _ = _drawdown(r.equity_net)
        rows.append({
            "步": label,
            "净收益(扣摩擦)": float(r.equity_net.iloc[-1] / r.equity_net.iloc[0] - 1.0),
            "毛收益": float(r.equity_gross.iloc[-1] / r.equity_gross.iloc[0] - 1.0),
            "CAGR": _cagr(r.equity_net),
            "★最大回撤": mdd,
            "最长水下天数": under,
            "笔数": len(r.trades),
            "平均净敞口Ē": float(r.exposure.mean()),
        })
    return pd.DataFrame(rows).set_index("步")


# ---------------------------------------------------------------- 完整评估

def evaluate(cfg: ChainConfig,
             symbols: list[str] | None = None,
             start: str = data.PERF_START,
             end: str = data.PERF_END,
             initial_equity: float = 1_000_000.0,
             n_random_seeds: int = 5,
             with_attribution: bool = True) -> dict[str, Any]:
    """跑一条链并输出全部要求的东西,一样都不少。"""
    res = run_chain(cfg, symbols, start, end, initial_equity)
    eq, eqg = res.equity_net, res.equity_gross
    trades = [t for t in res.trades if t.exit_date is not None]
    rs = np.array([t.r_multiple for t in trades], dtype=float)
    rs = rs[np.isfinite(rs)]
    grets = np.array([t.gross_return for t in trades], dtype=float)
    grets = grets[np.isfinite(grets)]
    mdd, under, trough = _drawdown(eq)
    years = max(1e-9, len(eq) / TRADING_DAYS_PER_YEAR)
    avg_eq = float(eq.mean())
    yearly = _yearly(eq)
    bad_years = {y: v for y, v in yearly.items() if v < -0.10}

    bench_cfg = cfg.get("benchmark") or {}
    out: dict[str, Any] = {
        "链名": cfg.name,
        "绩效窗口": f"{eq.index[0].date()} .. {eq.index[-1].date()}"
                     f"(★ 2016 起热机,{data.PERF_START} 才计入绩效)",

        "绝对表现": {
            "净收益(扣摩擦)": float(eq.iloc[-1] / eq.iloc[0] - 1.0),
            "毛收益": float(eqg.iloc[-1] / eqg.iloc[0] - 1.0),
            "CAGR(净)": _cagr(eq),
            "笔数": len(trades),
            "每笔平均R": float(np.mean(rs)) if rs.size else float("nan"),
            "R中位数": float(np.median(rs)) if rs.size else float("nan"),
            "胜率": float(np.mean(grets > 0)) if grets.size else float("nan"),
        },

        "代价": {
            "最大回撤": mdd,
            "回撤最深那天": str(trough.date()) if trough is not None else None,
            "★最长水下持续天数": under,
            "UlcerIndex(Martin 1989)": _ulcer_index(eq),
            "最长连续不赚钱笔数": _longest_losing_streak(trades),
            "逐年收益": yearly,
            "几乎全亏的年份(<-10%)": bad_years,
        },

        "执行负荷": {
            "年化换手率": float(res.metrics["traded_notional"] / avg_eq / years)
            if avg_eq > 0 else float("nan"),
            "年均交易笔数": float(len(trades) / years),
            "平均持仓周期(交易日)": float(np.mean([t.holding_days for t in trades]))
            if trades else float("nan"),
        },

        "摩擦成本": {
            "单边": f"{float((cfg.get('costs') or {}).get('one_way_bps', data.ONE_WAY_COST_BPS))/100:.3f}%",
            "毛减净": float(eqg.iloc[-1] / eqg.iloc[0] - eq.iloc[-1] / eq.iloc[0]),
            "出处": "SEC Rule 206(4)-1(d);GIPS 2020 Section 2.A",
        },

        "基准一_同环境随机进场": random_entry_benchmark(
            cfg, res, symbols, start, end, n_random_seeds),

        "基准二_同等仓位大盘": {k: v for k, v in exposure_matched_benchmark(
            res, bench_cfg.get("component_match", "large"),
            bench_cfg.get("risk_free_annual")).items() if k != "_equity"},
    }
    if with_attribution:
        out["分步归因"] = attribution(cfg, symbols, start, end, initial_equity)
    out["_result"] = res
    return out


def format_report(out: dict[str, Any]) -> str:
    lines = [f"链:{out['链名']}", f"窗口:{out['绩效窗口']}", ""]
    for section in ("绝对表现", "代价", "执行负荷", "摩擦成本",
                    "基准一_同环境随机进场", "基准二_同等仓位大盘"):
        lines.append(f"[{section}]")
        for k, v in out[section].items():
            if isinstance(v, float):
                lines.append(f"  {k}: {v:+.4f}" if abs(v) < 100 else f"  {k}: {v:,.2f}")
            elif isinstance(v, dict):
                lines.append(f"  {k}: " + ", ".join(f"{a}={b:+.2%}" for a, b in v.items()))
            elif isinstance(v, list):
                for item in v:
                    lines.append(f"  ⚠ {item}")
            else:
                lines.append(f"  {k}: {v}")
        lines.append("")
    if "分步归因" in out:
        lines.append("[分步归因 —— 收益和代价必须一起看]")
        df = out["分步归因"].copy()
        for c in ("净收益(扣摩擦)", "毛收益", "CAGR", "★最大回撤", "平均净敞口Ē"):
            df[c] = df[c].map(lambda x: f"{x:+.2%}")
        lines.append(df.to_string())
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="链执行器:吃一份七步配置,吐完整结果")
    ap.add_argument("config", help="配置文件路径(.yaml / .json)")
    ap.add_argument("--start", default=data.PERF_START)
    ap.add_argument("--end", default=data.PERF_END)
    ap.add_argument("--pool", default="ALL", choices=["ALL", "A", "B"])
    ap.add_argument("--seeds", type=int, default=5, help="基准一跑几个随机种子")
    ap.add_argument("--no-attribution", action="store_true")
    ap.add_argument("--equity", type=float, default=1_000_000.0)
    a = ap.parse_args(argv)

    cfg = ChainConfig.load(a.config)
    syms = data.full_universe().pool(a.pool)
    print(data.cohort_report())
    print()
    out = evaluate(cfg, syms, a.start, a.end, a.equity, a.seeds,
                   with_attribution=not a.no_attribution)
    print(format_report(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
