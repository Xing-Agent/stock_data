"""
九关体检 —— 一条命令跑完。

跑法:
    python -m engine.run_gates engine/configs/你的配置.yaml
    python -m engine.run_gates engine/configs/你的配置.yaml --pool A

九关在体检「一个进场扳机」够不够资格进链:
  一·自测        空表 / 全 NaN / 数据不足,不许崩也不许凭空出信号
  二·因果性      截断法:算今天只许用今天及以前的数据
  三·事件还是状态 进场信号必须是事件,不能是粘住好多天的状态
  四·频率        一年出太多 = 没筛东西,太少 = 样本攒不够
  五·逐年 + 样本内外
  六·样本量      n ≥ 100
  七·随机对照    三套对照组(判据)
  八·日历聚集    信号不能全挤在某几个月 / 某几天
  ★ 九·两窗口两池子(硬关)

★ 第九关是硬关:没过就必须把结论降级成「只在 XX 窗口 / XX 池子上成立」。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from . import cache, chain, data, matrices, stats_gate, window_pool

HORIZON = 20          # 判据用的持有期:20 个交易日(约一个月),固定值不调
MIN_PER_YEAR = 5      # 第四关下限:一年至少 5 个信号,否则样本攒不够
MAX_PER_YEAR = 2000   # 第四关上限:一年超过这个数说明基本没筛东西


@dataclass
class GateOutcome:
    no: int
    name: str
    passed: bool
    hard: bool = False
    detail: str = ""
    extra: Any = None

    def line(self) -> str:
        tag = "✅通过" if self.passed else ("❌没过(硬关)" if self.hard else "⚠没过")
        return f"第{self.no}关 {self.name:16s} {tag}"


@dataclass
class GateReport:
    chain_name: str
    outcomes: list[GateOutcome] = field(default_factory=list)

    @property
    def all_passed(self) -> bool:
        return all(o.passed for o in self.outcomes)

    @property
    def hard_failed(self) -> list[GateOutcome]:
        return [o for o in self.outcomes if o.hard and not o.passed]

    def report(self) -> str:
        lines = [f"九关体检:{self.chain_name}", "=" * 72]
        for o in self.outcomes:
            lines.append(o.line())
            for ln in (o.detail or "").splitlines():
                lines.append(f"        {ln}")
        lines.append("=" * 72)
        failed = [o for o in self.outcomes if not o.passed]
        if not failed:
            lines.append("★ 九关全过。这个扳机可以进链。")
        else:
            lines.append(f"★ 没过 {len(failed)} 关:"
                         f"{[f'第{o.no}关{o.name}' for o in failed]}")
            if self.hard_failed:
                lines.append("★★ 其中有硬关没过 —— 结论必须降级,不能当普遍结论用。")
        return "\n".join(lines)


# ================================================================ 信号 → 前瞻收益

def _entry_points(entry: pd.DataFrame, uni: pd.DataFrame,
                  start: str, end: str) -> list[tuple[int, int]]:
    """取绩效窗口内的全部进场点,返回 [(行号, 列号), ...]。"""
    idx = entry.index
    lo = int(idx.searchsorted(pd.Timestamp(start)))
    hi = int(idx.searchsorted(pd.Timestamp(end), side="right"))
    sig = (entry.to_numpy(dtype=bool) & uni.to_numpy(dtype=bool))
    sig[:lo] = False
    sig[hi:] = False
    return list(zip(*np.nonzero(sig)))


def _fwd_matrix(close: np.ndarray, open_: np.ndarray, horizon: int) -> np.ndarray:
    """
    每个 (日, 票) 的前瞻收益:次日开盘买,持有 horizon 个交易日,按收盘卖。
    ★ 次日开盘买 —— 信号在当天收盘后产生,不许用当天收盘价成交。
    拿不到完整窗口的位置是 nan(不补、不猜)。
    """
    n = close.shape[0]
    p_in = np.full_like(close, np.nan)
    p_in[:-1] = open_[1:]
    p_out = np.full_like(close, np.nan)
    if n > horizon:
        p_out[:-horizon] = close[horizon:]
    with np.errstate(invalid="ignore", divide="ignore"):
        r = p_out / p_in - 1.0
    r[~np.isfinite(r)] = np.nan
    r[p_in <= 0] = np.nan
    return r


# ================================================================ 各关

def gate1_selftest(cfg: chain.ChainConfig) -> GateOutcome:
    """一·自测:空表 / 全 NaN / 数据不足,不许崩,也不许凭空出信号。"""
    spec = cfg.get("entry") or {}
    probs = []
    idx = pd.bdate_range("2020-01-01", periods=300)

    def make(vals):
        df = pd.DataFrame({"open": vals, "high": vals, "low": vals,
                           "close": vals, "volume": 1.0}, index=idx[:len(vals)])
        df["dollar_volume"] = df["close"] * df["volume"]
        return df

    cases = {
        "空表": make([]),
        "全NaN": make([np.nan] * 300),
        "数据不足(5根)": make([10.0, 11.0, 10.5, 11.2, 11.1]),
        "一条直线(无波动)": make([10.0] * 300),
    }
    ok = True
    for label, df in cases.items():
        try:
            # 单票矩阵版:借用 matrices 的纯函数路径
            from . import signals
            s = signals.make_entry(spec)(df) if len(df) else pd.Series(dtype=bool)
            n = int(np.nansum(s.to_numpy(dtype=bool))) if len(s) else 0
            if label in ("空表", "全NaN", "数据不足(5根)") and n > 0:
                ok = False
                probs.append(f"{label}:凭空出了 {n} 个信号")
            else:
                probs.append(f"{label}:没崩,出 {n} 个信号")
        except Exception as e:
            ok = False
            probs.append(f"{label}:崩了 —— {type(e).__name__}: {e}")
    return GateOutcome(1, "自测", ok, detail="\n".join(probs))


def gate2_causality(cfg: chain.ChainConfig, symbols: list[str]) -> GateOutcome:
    """
    二·因果性(截断法):把数据在某一天截断,重算一遍。
    截断前那段的信号必须和用全量数据算出来的一模一样 ——
    只要有一个不一样,就说明算今天用到了今天以后的数据。
    """
    cut = "2022-06-30"
    full = matrices.entry_trigger(cfg.get("entry") or {}, symbols)
    cl = cache.field("close", symbols)
    keep = cl.index <= pd.Timestamp(cut)

    # 用截断后的数据重算:临时把缓存面板裁短
    orig = cache._PANEL
    try:
        cache._PANEL = {k: v.loc[keep] for k, v in cache.load().items()}
        trunc = matrices.entry_trigger(cfg.get("entry") or {}, symbols)
    finally:
        cache._PANEL = orig

    a = full.loc[trunc.index].to_numpy(dtype=bool)
    b = trunc.to_numpy(dtype=bool)
    diff = int(np.sum(a != b))
    ok = diff == 0
    return GateOutcome(
        2, "因果性", ok,
        detail=(f"在 {cut} 截断后重算,与全量数据的信号比对:\n"
                f"不一致的格子数 = {diff} / {a.size}"
                + ("(完全一致 → 没有偷看未来)" if ok else
                   " ★ 有不一致 → 算今天用到了今天以后的数据,必须查")))


def gate3_event_not_state(cfg: chain.ChainConfig, symbols: list[str]) -> GateOutcome:
    """
    三·事件还是状态:进场信号必须是事件。
    判法:看信号的「连续成立长度」。如果平均连续好几天,那是状态不是事件。
    """
    e = matrices.entry_trigger(cfg.get("entry") or {}, symbols).to_numpy(dtype=bool)
    if e.sum() == 0:
        return GateOutcome(3, "事件还是状态", False, detail="一个信号都没有")
    runs = []
    for j in range(e.shape[1]):
        col = e[:, j]
        cur = 0
        for v in col:
            if v:
                cur += 1
            elif cur:
                runs.append(cur)
                cur = 0
        if cur:
            runs.append(cur)
    mean_run = float(np.mean(runs)) if runs else 0.0
    ok = mean_run <= 1.5
    return GateOutcome(
        3, "事件还是状态", ok,
        detail=(f"信号平均连续成立 {mean_run:.2f} 天(事件应该接近 1.0)\n"
                f"最长连续 {max(runs) if runs else 0} 天,"
                f"判定线 ≤ 1.5 天"
                + ("" if ok else " ★ 这是个粘住的状态,不是事件 —— "
                                 "会把同一件事重复计数,必须改成只在转折那天触发")))


def gate4_frequency(cfg: chain.ChainConfig, symbols: list[str],
                    start: str, end: str) -> GateOutcome:
    """四·频率:一年出太多 = 没筛东西,太少 = 样本攒不够。"""
    e = matrices.entry_trigger(cfg.get("entry") or {}, symbols)
    u = matrices.universe_mask(cfg.get("universe") or {}, symbols)
    pts = _entry_points(e, u.reindex_like(e).fillna(False), start, end)
    years = max(1e-9, (pd.Timestamp(end) - pd.Timestamp(start)).days / 365.25)
    per_year = len(pts) / years
    ok = MIN_PER_YEAR <= per_year <= MAX_PER_YEAR
    return GateOutcome(
        4, "频率", ok,
        detail=(f"全池一年平均出 {per_year:.1f} 个信号"
                f"(合格区间 {MIN_PER_YEAR} ~ {MAX_PER_YEAR})\n"
                f"窗口内总信号数 {len(pts)},票数 {len(symbols)}"),
        extra=pts)


def gate5_by_year_and_oos(fwd: np.ndarray, pts: list[tuple[int, int]],
                          index: pd.DatetimeIndex) -> GateOutcome:
    """
    五·逐年 + 样本内外:
    逐年看每笔平均收益;再把前 60% 时间当样本内、后 40% 当样本外,两边都要为正。
    """
    if not pts:
        return GateOutcome(5, "逐年+样本内外", False, detail="没有信号")
    rows = [(index[i].year, fwd[i, j]) for i, j in pts if np.isfinite(fwd[i, j])]
    if not rows:
        return GateOutcome(5, "逐年+样本内外", False, detail="没有可用的前瞻收益")
    df = pd.DataFrame(rows, columns=["year", "ret"])
    by_year = df.groupby("year")["ret"].agg(["mean", "count"])
    pos_years = int((by_year["mean"] > 0).sum())
    n_years = len(by_year)

    ys = sorted(by_year.index)
    split = ys[int(len(ys) * 0.6)] if len(ys) > 2 else ys[-1]
    ins = df[df["year"] < split]["ret"]
    oos = df[df["year"] >= split]["ret"]
    ok = (len(ins) > 0 and len(oos) > 0 and ins.mean() > 0 and oos.mean() > 0
          and pos_years >= np.ceil(n_years / 2))
    lines = [f"逐年每笔平均收益({n_years} 年里 {pos_years} 年为正):"]
    for y, r in by_year.iterrows():
        lines.append(f"    {y}: {r['mean']:+.2%}  (n={int(r['count'])})")
    lines.append(f"样本内(<{split}) {ins.mean():+.2%} (n={len(ins)}) | "
                 f"样本外(≥{split}) {oos.mean():+.2%} (n={len(oos)})")
    if not ok:
        lines.append("★ 要求:过半年份为正,且样本内外都为正")
    return GateOutcome(5, "逐年+样本内外", ok, detail="\n".join(lines))


def gate6_sample_size(pts: list[tuple[int, int]], fwd: np.ndarray) -> GateOutcome:
    """六·样本量:n ≥ 100。★ 坑五:笔数少的,置信区间宽到没法下结论。"""
    n = sum(1 for i, j in pts if np.isfinite(fwd[i, j]))
    ok = n >= stats_gate.MIN_N
    return GateOutcome(6, "样本量", ok,
                       detail=f"可用样本 n={n}(下限 {stats_gate.MIN_N})"
                              + ("" if ok else " ★ 样本太少,任何结论都不要下"))


def gate7_random_control(fwd: np.ndarray, pts: list[tuple[int, int]],
                         uni: np.ndarray, B: int) -> GateOutcome:
    """
    七·随机对照:三套对照组(判据)。
      ① 条件分层随机:同一天、同一个池子里随机挑票
      ② 块重排 Circular Block Bootstrap(Politis & Romano 1994)
      ③ 极性反转:同样的进场点强制做空
    """
    vals = np.array([fwd[i, j] for i, j in pts if np.isfinite(fwd[i, j])])
    if vals.size == 0:
        e = stats_gate.BootstrapResult("无信号", 0, B, np.nan, np.nan, np.nan, 1.0, np.nan)
        return GateOutcome(7, "随机对照", False, detail="没有可用信号",
                           extra=stats_gate.verdict(e, e, e, e))

    rows = sorted({i for i, _ in pts})
    # ① 同一天、同一个池子里随机换一只票
    pool_by_row = {i: np.flatnonzero(uni[i] & np.isfinite(fwd[i])) for i in rows}
    counts = {}
    for i, _ in pts:
        counts[i] = counts.get(i, 0) + 1

    def strat(rng):
        out = []
        for i, k in counts.items():
            pool = pool_by_row.get(i)
            if pool is None or pool.size == 0:
                continue
            out.extend(fwd[i, rng.choice(pool, size=k, replace=True)])
        return out

    flat = fwd[np.isfinite(fwd)]
    s = stats_gate.bootstrap_test("条件分层随机", vals, strat, B=B,
                                  note="同一天、同一个池子里随机挑票")
    b = stats_gate.bootstrap_test("块重排(Politis&Romano)", vals,
                                  stats_gate.circular_block_sampler(flat, vals.size),
                                  B=B, note="块长 n^(1/3)")
    pl = stats_gate.bootstrap_test("极性反转·做多", vals,
                                   stats_gate.circular_block_sampler(flat, vals.size), B=B)
    ps = stats_gate.bootstrap_test("极性反转·做空", -vals,
                                   stats_gate.circular_block_sampler(-flat, vals.size),
                                   B=B, note="同样进场点强制做空")
    v = stats_gate.verdict(s, b, pl, ps)
    return GateOutcome(7, "随机对照", v.passed, detail=v.report(), extra=v)


def gate8_calendar_clustering(pts: list[tuple[int, int]],
                              index: pd.DatetimeIndex) -> GateOutcome:
    """
    八·日历聚集:信号不能全挤在某几个月 / 某几天。
    判法:看月份分布和「单日信号占比」的最大值。
    全挤在一起说明这不是一个可重复的规律,是几次特定事件。
    """
    if not pts:
        return GateOutcome(8, "日历聚集", False, detail="没有信号")
    dates = [index[i] for i, _ in pts]
    months = pd.Series([d.month for d in dates]).value_counts(normalize=True)
    days = pd.Series([d.date() for d in dates]).value_counts(normalize=True)
    top_month = float(months.max())
    top_day = float(days.max())
    n_months = int(months.size)
    ok = (top_month <= 0.30) and (top_day <= 0.10) and n_months >= 8
    return GateOutcome(
        8, "日历聚集", ok,
        detail=(f"信号最集中的那个月占 {top_month:.1%}(上限 30%)\n"
                f"信号最集中的那一天占 {top_day:.1%}(上限 10%)\n"
                f"一年里有信号的月份数 {n_months}(下限 8)"
                + ("" if ok else " ★ 太集中 —— 这更像几次特定事件,不是可重复的规律")))


def gate9_window_pool(cfg: chain.ChainConfig, symbols: list[str], B: int) -> GateOutcome:
    """★ 九·两窗口两池子(硬关)。每格的随机对照必须在同格内取样。"""
    e_all = matrices.entry_trigger(cfg.get("entry") or {}, symbols)
    u_all = matrices.universe_mask(cfg.get("universe") or {}, symbols)
    u_all = u_all.reindex(columns=e_all.columns).fillna(False)
    close = cache.field("close", list(e_all.columns)).to_numpy(dtype=float)
    open_ = cache.field("open", list(e_all.columns)).to_numpy(dtype=float)
    fwd_all = _fwd_matrix(close, open_, HORIZON)
    colpos = {s: k for k, s in enumerate(e_all.columns)}

    def signal_fn(start, end, cell_symbols):
        cols = [colpos[s] for s in cell_symbols if s in colpos]
        if not cols:
            return [], (lambda rng: [])
        cols = np.array(cols)
        sub_e = e_all.iloc[:, cols]
        sub_u = u_all.iloc[:, cols]
        pts = _entry_points(sub_e, sub_u, start, end)
        fwd = fwd_all[:, cols]
        vals = np.array([fwd[i, j] for i, j in pts if np.isfinite(fwd[i, j])])

        idx = e_all.index
        lo = int(idx.searchsorted(pd.Timestamp(start)))
        hi = int(idx.searchsorted(pd.Timestamp(end), side="right"))
        # ★ 同格内取样:只用这一格的票 + 这一格的日期
        cell = fwd[lo:hi]
        cell = cell[np.isfinite(cell)]
        if cell.size == 0 or vals.size == 0:
            return vals, (lambda rng: [])
        return vals, stats_gate.circular_block_sampler(cell, max(1, vals.size))

    v = window_pool.run_grid(signal_fn, symbols, B=B)
    return GateOutcome(9, "两窗口两池子", v.passed, hard=True,
                       detail=v.report(), extra=v)


# ================================================================ 总装

def run_all(cfg: chain.ChainConfig,
            symbols: list[str] | None = None,
            start: str = data.PERF_START,
            end: str = data.PERF_END,
            B: int = stats_gate.B_DEFAULT) -> GateReport:
    syms = symbols or data.full_universe().pool("ALL")
    rep = GateReport(cfg.name)

    rep.outcomes.append(gate1_selftest(cfg))
    rep.outcomes.append(gate2_causality(cfg, syms))
    rep.outcomes.append(gate3_event_not_state(cfg, syms))

    g4 = gate4_frequency(cfg, syms, start, end)
    rep.outcomes.append(g4)
    pts = g4.extra or []

    e = matrices.entry_trigger(cfg.get("entry") or {}, syms)
    u = matrices.universe_mask(cfg.get("universe") or {}, syms)
    u = u.reindex(columns=e.columns).fillna(False)
    cols = list(e.columns)
    close = cache.field("close", cols).to_numpy(dtype=float)
    open_ = cache.field("open", cols).to_numpy(dtype=float)
    fwd = _fwd_matrix(close, open_, HORIZON)

    rep.outcomes.append(gate5_by_year_and_oos(fwd, pts, e.index))
    rep.outcomes.append(gate6_sample_size(pts, fwd))
    rep.outcomes.append(gate7_random_control(fwd, pts, u.to_numpy(dtype=bool), B))
    rep.outcomes.append(gate8_calendar_clustering(pts, e.index))
    rep.outcomes.append(gate9_window_pool(cfg, syms, B))
    return rep


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="九关体检:一条命令跑完")
    ap.add_argument("config")
    ap.add_argument("--start", default=data.PERF_START)
    ap.add_argument("--end", default=data.PERF_END)
    ap.add_argument("--pool", default="ALL", choices=["ALL", "A", "B"])
    ap.add_argument("-B", type=int, default=stats_gate.B_DEFAULT)
    a = ap.parse_args(argv)

    cfg = chain.ChainConfig.load(a.config)
    print(data.cohort_report())
    print()
    rep = run_all(cfg, data.full_universe().pool(a.pool), a.start, a.end, a.B)
    print(rep.report())
    return 0 if not rep.hard_failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
