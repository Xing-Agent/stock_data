"""
状态轴三版并跑 —— 状-1 / 状-2 / 状-3 / 状-5,每条跑「原著版 / 行业版 / XING版」。

================================================================================
三秒版
================================================================================
这个文件回答一个问题:**同一条状态判定规则,换成原著的参数、行业的参数、
我们自己的参数,判出来的结果差多少。**

它不出交易信号、不跑回测、不给 Z 值。产出只有三样:
  ① 各状态占比    ② 状态持续天数分布    ③ 状态翻转频率

★ 为什么要三版并跑:原著写死的、行业做好的、我们自己优化的,是三种不同的东西。
  混成一个「默认参数」之后就说不清哪个数字是谁的责任。

★ 硬纪律(本文件逐条守着):
  一、原著没写死的地方不许我们填 —— 填不了就输出「跑不了」,这本身是产出。
  二、原著给区间的,跑严格端 / 中值 / 宽松端三组。
  三、拿不到就说拿不到,不许用近似值顶上。
  四、所有「我们自己定的」实现口径,在 IMPL_NOTES 里逐条登记,报告原样打出。

跑法:python -m engine.state_axis_run_1029
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import cache, data

# ============================================================================
# ★ 实现口径登记簿 —— 凡是「卡片/原著/行业都没写、但代码必须有答案」的,记这里
# ============================================================================

IMPL_NOTES: list[str] = []


def _note(s: str) -> None:
    if s not in IMPL_NOTES:
        IMPL_NOTES.append(s)


WARMUP = "WARMUP"
START = "2018-01-01"          # 预热 2016-2017,2018-01-01 起计
WEEK = 5                      # 一周按 5 个交易日折算


# ============================================================================
# 公用:分布统计 —— 四条状态判定的唯一产出形态
# ============================================================================

def _runs(seq: np.ndarray) -> list[tuple[str, int, int]]:
    """把状态序列切成连续段,返回 [(状态, 起点下标, 长度)]。"""
    out: list[tuple[str, int, int]] = []
    if len(seq) == 0:
        return out
    cur, start = seq[0], 0
    for i in range(1, len(seq)):
        if seq[i] != cur:
            out.append((cur, start, i - start))
            cur, start = seq[i], i
    out.append((cur, start, len(seq) - start))
    return out


def distribution(panel: dict[str, np.ndarray], states: tuple[str, ...]
                 ) -> dict:
    """
    panel: {symbol: 状态数组(已切到 2018+)}
    产出:各状态占比 / 持续天数分布 / 翻转频率。★ WARMUP 不算状态,单独记。
    """
    counts = {s: 0 for s in states}
    warm = 0
    total = 0
    runlen: dict[str, list[int]] = {s: [] for s in states}
    flips = 0
    flip_days = 0

    for sym, arr in panel.items():
        if len(arr) == 0:
            continue
        total += len(arr)
        for s in states:
            counts[s] += int((arr == s).sum())
        warm += int((arr == WARMUP).sum())
        live = arr[arr != WARMUP]
        if len(live) == 0:
            continue
        flip_days += len(live)
        rs = _runs(live)
        flips += max(0, len(rs) - 1)
        for st, _, ln in rs:
            if st in runlen:
                runlen[st].append(ln)

    live_total = max(1, total - warm)
    out = {
        "symbol_days_total": total,
        "warmup_days": warm,
        "warmup_share": round(warm / max(1, total), 4),
        "live_symbol_days": total - warm,
        "state_share": {s: round(counts[s] / live_total, 4) for s in states},
        "state_days": {s: counts[s] for s in states},
        "flips_total": flips,
        "flips_per_1000_days": round(1000.0 * flips / max(1, flip_days), 2),
        "run_length": {},
    }
    all_runs: list[int] = []
    for s in states:
        v = np.asarray(runlen[s], dtype=float)
        all_runs.extend(runlen[s])
        out["run_length"][s] = _rl_stats(v)
    out["run_length"]["__all__"] = _rl_stats(np.asarray(all_runs, dtype=float))
    return out


def _rl_stats(v: np.ndarray) -> dict:
    if len(v) == 0:
        return {"n": 0}
    return {
        "n": int(len(v)),
        "mean": round(float(v.mean()), 2),
        "p10": round(float(np.percentile(v, 10)), 1),
        "median": round(float(np.median(v)), 1),
        "p90": round(float(np.percentile(v, 90)), 1),
        "max": int(v.max()),
        "share_le_3d": round(float((v <= 3).mean()), 4),
        "share_ge_60d": round(float((v >= 60).mean()), 4),
    }


# ============================================================================
# 状-1 道氏高低点排列
# ============================================================================
#
# 两个参数:(a) ZigZag 阈值  (b) 摆动点取影线还是收盘
#
#   原著版  摆动点取收盘价;折返确认 = 回撤前序主趋势 ≥33% 且持续 ≥3 周
#           出处(待核实):Rhea《The Dow Theory》(1932) Ch.6 "Closing Prices
#           Used" / Ch.4 次级折返浪 33%~66%、3 周至 3 个月
#   行业版  2.5 × ATR(14) 动态阈值(2.0~3.0 的中值),摆动点取收盘价
#   XING版  3 × ATR(14),摆动点取影线
#
# ★ 因果性:一个摆动点在极值那天成立,但只有在「折返被确认」那天才可知。
#   本实现一律按「确认日」才允许使用,绝不在极值当天就用它。

DOW_STATES = ("uptrend", "downtrend", "range")


@dataclass
class DowSpec:
    name: str
    pivot_source: str          # "close" | "shadow"
    mode: str                  # "atr" | "retrace"
    atr_mult: float = 3.0
    retrace_frac: float = 0.33
    min_bars: int = 0
    note: str = ""


DOW_VERSIONS = {
    "原著版": DowSpec("原著版", "close", "retrace", retrace_frac=0.33,
                      min_bars=3 * WEEK,
                      note="回撤 ≥33% 且持续 ≥3 周;不用 ATR 乘数"),
    "行业版": DowSpec("行业版", "close", "atr", atr_mult=2.5,
                      note="2.0~3.0×ATR(14) 取中值 2.5;结构判定用收盘价"),
    "XING版": DowSpec("XING版", "shadow", "atr", atr_mult=3.0,
                      note="手册现行口径:3×ATR(14),摆动点取影线"),
}


def _zigzag(hi: np.ndarray, lo: np.ndarray, cl: np.ndarray,
            atr: np.ndarray, spec: DowSpec
            ) -> tuple[list[tuple[int, float, int]], np.ndarray]:
    """
    返回 (pivots, state)。
    pivots: [(确认日下标, 极值价, 类型)] 类型 +1=摆动高 −1=摆动低
    ★ 一个 pivot 只在它的「确认日」及以后才可用。
    """
    n = len(cl)
    up_src = hi if spec.pivot_source == "shadow" else cl
    dn_src = lo if spec.pivot_source == "shadow" else cl

    # 找第一个有效起点
    i0 = 0
    while i0 < n and (not np.isfinite(cl[i0])
                      or (spec.mode == "atr" and not np.isfinite(atr[i0]))):
        i0 += 1
    if i0 >= n - 2:
        return [], np.full(n, WARMUP, dtype=object)

    pivots: list[tuple[int, float, int]] = []
    # ★ 方向先定成 +1(找摆动高)。预热期可能先出一个无意义的首 pivot,
    #   但它落在 2014~2017 的预热段里,不进计分窗口。
    direction = +1
    ext, ext_i = up_src[i0], i0
    anchor = dn_src[i0]                 # 前序主趋势的起点 = 上一个 pivot 价

    for i in range(i0 + 1, n):
        h, l = up_src[i], dn_src[i]
        if not (np.isfinite(h) and np.isfinite(l)):
            continue
        if spec.mode == "atr":
            if not np.isfinite(atr[i]):
                continue
            thr_up = thr_dn = spec.atr_mult * atr[i]
        else:
            thr_up = thr_dn = spec.retrace_frac * abs(ext - anchor)
        need = 0 if spec.mode == "atr" else spec.min_bars

        if direction > 0:               # 在找摆动高点
            if h > ext:
                ext, ext_i = h, i
            if thr_dn > 0 and (ext - l) >= thr_dn and (i - ext_i) >= need:
                pivots.append((i, float(ext), +1))
                anchor = ext
                direction = -1
                ext, ext_i = l, i
        else:                           # 在找摆动低点
            if l < ext:
                ext, ext_i = l, i
            if thr_up > 0 and (h - ext) >= thr_up and (i - ext_i) >= need:
                pivots.append((i, float(ext), -1))
                anchor = ext
                direction = +1
                ext, ext_i = h, i

    # 逐日排列判定:最近两个摆动高 + 最近两个摆动低
    state = np.full(n, WARMUP, dtype=object)
    highs: list[float] = []
    lows: list[float] = []
    pi = 0
    cur = WARMUP
    for i in range(n):
        while pi < len(pivots) and pivots[pi][0] <= i:
            _, px, kind = pivots[pi]
            (highs if kind > 0 else lows).append(px)
            pi += 1
        if len(highs) >= 2 and len(lows) >= 2:
            hh = highs[-1] > highs[-2]
            hl = lows[-1] > lows[-2]
            lh = highs[-1] < highs[-2]
            ll = lows[-1] < lows[-2]
            if hh and hl:
                cur = "uptrend"
            elif lh and ll:
                cur = "downtrend"
            else:
                cur = "range"
        state[i] = cur
    return pivots, state


def run_dow(symbols: list[str]) -> dict:
    p = cache.load()
    hi, lo, cl = p["high"], p["low"], p["close"]
    atr = _atr14(hi, lo, cl)
    idx = cl.index
    keep = idx >= pd.Timestamp(START)
    out = {}
    for vname, spec in DOW_VERSIONS.items():
        panel: dict[str, np.ndarray] = {}
        npiv = []
        for s in symbols:
            _, st = _zigzag(hi[s].to_numpy(), lo[s].to_numpy(),
                            cl[s].to_numpy(), atr[s].to_numpy(), spec)
            panel[s] = st[keep]
            npiv.append(int(sum(1 for x in _ if True)) if False else 0)
        d = distribution(panel, DOW_STATES)
        d["spec"] = {"pivot_source": spec.pivot_source, "mode": spec.mode,
                     "atr_mult": spec.atr_mult,
                     "retrace_frac": spec.retrace_frac,
                     "min_bars": spec.min_bars, "note": spec.note}
        out[vname] = d
        out[vname]["_panel"] = panel
    return out


def _atr14(hi: pd.DataFrame, lo: pd.DataFrame, cl: pd.DataFrame) -> pd.DataFrame:
    pc = cl.shift(1)
    tr = pd.DataFrame(
        np.fmax(np.fmax((hi - lo).to_numpy(), (hi - pc).abs().to_numpy()),
                (lo - pc).abs().to_numpy()),
        index=cl.index, columns=cl.columns)
    return tr.ewm(alpha=1.0 / 14, adjust=False, min_periods=14).mean()


# ============================================================================
# 状-2 温斯坦四阶段
# ============================================================================
#
#   原著版  ★ 跑不了。Weinstein 原著未写死任何数值,只有定性表述。
#           按纪律:原著没写死的地方不许我们填 → 只输出「跑不了」+ 原文引文。
#   行业版  走平 = |SMA150 的 20 日相对变化率| ≤ 0.15%
#           底盘 = 价格在 ±10% 振幅箱体内 ≥20~30 个交易日(取中值 25)
#   XING版  走平 0.5%/周(近 10 周);最短持续 ≥4 周;强制 1→2→3→4 循环
#
# ★★ 本节最重要的产出:「强制 1→2→3→4 循环」是不是在系统性误杀真实阶段二。

STAGE_STATES = ("1", "2", "3", "4", "transition")

ORIGINAL_QUOTE_W = (
    'Weinstein 原文只有定性表述:"The 30-week MA loses its downward slope '
    'and starts to flatten out.";阶段一持续时间只给 "a few months to '
    'several years"。→ 无可执行阈值。')


@dataclass
class StageSpec:
    name: str
    flat_mode: str             # "pct_per_week" | "pct_20d"
    flat_thr: float
    min_bars: int
    box_bars: int = 0          # >0 时 FLAT 还要求箱体条件
    box_amp: float = 0.0
    note: str = ""


STAGE_VERSIONS = {
    "行业版": StageSpec("行业版", "pct_20d", 0.15, 25, box_bars=25,
                        box_amp=0.20,
                        note="走平 |SMA150 20日变化率| ≤0.15%;底盘 ±10% 箱体 ≥25 日"),
    "XING版": StageSpec("XING版", "pct_per_week", 0.5, 4 * WEEK,
                        note="走平 0.5%/周(近10周);最短持续 ≥4 周"),
}

_note("状-2 行业版的「最短持续」原文只给了底盘 ≥20~30 日,"
      "本实现把 25 日同时用作所有阶段的最短持续(为了和 XING 版可比)。")
_note("状-2 行业版「±10% 振幅箱体」实现为:近 25 根收盘价 (max−min)/mean ≤ 0.20。")
_note("状-2 的 FLAT 消解规则(FLAT 到底是阶段一还是阶段三)是 XING 口径:"
      "前序确认阶段为 4 或无 → 阶段一;前序为 2 → 阶段三。原著未写死。")


def _raw_stage(cl: np.ndarray, ma: np.ndarray, spec: StageSpec) -> np.ndarray:
    """逐日原始标签:FLAT / ADV / DEC / TRANS / WARMUP(不含持续与拓扑约束)。"""
    n = len(cl)
    out = np.full(n, WARMUP, dtype=object)
    if spec.flat_mode == "pct_per_week":
        lag = 10 * WEEK
        slope = np.full(n, np.nan)
        slope[lag:] = (ma[lag:] / ma[:-lag] - 1.0) * 100.0 / 10.0
    else:
        lag = 20
        slope = np.full(n, np.nan)
        slope[lag:] = (ma[lag:] / ma[:-lag] - 1.0) * 100.0

    if spec.box_bars:
        box_ok = np.zeros(n, dtype=bool)
        s = pd.Series(cl)
        amp = (s.rolling(spec.box_bars).max() - s.rolling(spec.box_bars).min()
               ) / s.rolling(spec.box_bars).mean()
        box_ok = (amp <= spec.box_amp).to_numpy()
    else:
        box_ok = np.ones(n, dtype=bool)

    for i in range(n):
        if not (np.isfinite(cl[i]) and np.isfinite(ma[i])
                and np.isfinite(slope[i])):
            continue
        sl = slope[i]
        if abs(sl) <= spec.flat_thr:
            out[i] = "FLAT" if box_ok[i] else "TRANS"
        elif sl > spec.flat_thr and cl[i] > ma[i]:
            out[i] = "ADV"
        elif sl < -spec.flat_thr and cl[i] < ma[i]:
            out[i] = "DEC"
        else:
            out[i] = "TRANS"
    return out


def _confirm_sequence(raw: np.ndarray, min_bars: int
                      ) -> tuple[np.ndarray, list[dict]]:
    """
    把原始标签压成「已确认阶段」序列。
    返回 (逐日阶段, 确认事件列表)。
    事件 = {i: 确认日下标, stage: 1/2/3/4, prev, prev2}
    """
    n = len(raw)
    daily = np.full(n, WARMUP, dtype=object)
    events: list[dict] = []
    confirmed: list[str] = []          # 已确认阶段序列
    cur_raw, run = None, 0
    cur_stage = WARMUP

    for i in range(n):
        r = raw[i]
        if r == WARMUP:
            daily[i] = WARMUP
            cur_raw, run = None, 0
            continue
        if r == cur_raw:
            run += 1
        else:
            cur_raw, run = r, 1

        if run == min_bars and r in ("FLAT", "ADV", "DEC"):
            if r == "ADV":
                stage = "2"
            elif r == "DEC":
                stage = "4"
            else:
                last = confirmed[-1] if confirmed else None
                if last == "2":
                    stage = "3"
                elif last in ("1", "3"):
                    stage = last
                else:
                    stage = "1"
            if not confirmed or confirmed[-1] != stage:
                events.append({
                    "i": i, "stage": stage,
                    "prev": confirmed[-1] if confirmed else None,
                    "prev2": confirmed[-2] if len(confirmed) >= 2 else None,
                })
                confirmed.append(stage)
            cur_stage = stage
        daily[i] = cur_stage if cur_stage != WARMUP else "transition"
        if cur_stage == WARMUP:
            daily[i] = "transition"
    return daily, events


def _topology(ev: dict) -> tuple[bool, bool, bool, str]:
    """
    返回 (强制循环放行, Gemini三条路径放行, 三条路径+3→2 放行, 路径标签)。

    强制循环   只放行 4→1→2(阶段一必须来自阶段四)
    三条路径   Gemini 建议:4→1→2(标准反转) / 2→1→2(上升中继) / 4→2(特赦跳级)
    ★ 第四版  三条路径 + 3→2。
      为什么要有第四版:在标准温斯坦实现里,「阶段二之后的走平」按定义解成
      阶段三(顶部),不可能解成阶段一 —— 所以 Gemini 说的「中继基底 2→1→2」
      在数据上根本不存在,它实际长成 2→3→2。Gemini 的三条路径漏了这一条。
    """
    if ev["stage"] != "2":
        return True, True, True, "n/a"
    prev, prev2 = ev["prev"], ev["prev2"]
    if prev is None:
        return True, True, True, "首个阶段二(无前序)"
    if prev == "1" and prev2 in ("4", None):
        return True, True, True, "4→1→2"
    if prev == "1" and prev2 == "2":
        return False, True, True, "2→1→2"
    if prev == "1" and prev2 == "3":
        return False, True, True, "3→1→2"
    if prev == "4":
        return False, True, True, "4→2"
    if prev == "3":
        return False, False, True, "3→2"
    return False, False, False, f"{prev}→2"


_note("状-2 强制循环的严格读法:阶段二只在前序为阶段一、且该阶段一来自阶段四"
      "(4→1→2)时放行。3→1→2 这条路径也被强制循环挡掉,"
      "本实现把它单独记成一类(Gemini 的三条路径里没有它,但它被三条路径的"
      "「前序为阶段一」放行,因此计入三路径版)。")


def run_stage(symbols: list[str]) -> dict:
    p = cache.load()
    cl = p["close"]
    ma = cl.rolling(150, min_periods=150).mean()
    idx = cl.index
    keep = idx >= pd.Timestamp(START)
    spy = data.load_benchmark("SPY")["close"].reindex(idx).ffill().to_numpy()

    out: dict = {
        "原著版": {
            "runnable": False,
            "reason": "原著未给出可执行阈值 —— 按纪律不许我们填",
            "quote": ORIGINAL_QUOTE_W,
        }
    }

    cycle_test: dict = {}
    for vname, spec in STAGE_VERSIONS.items():
        panel_forced: dict[str, np.ndarray] = {}
        panel_three: dict[str, np.ndarray] = {}
        panel_four: dict[str, np.ndarray] = {}
        all_events: list[dict] = []
        for s in symbols:
            raw = _raw_stage(cl[s].to_numpy(), ma[s].to_numpy(), spec)
            daily, events = _confirm_sequence(raw, spec.min_bars)
            # 两个拓扑版本的逐日输出:被挡掉的阶段二降级为 transition
            df_, dt_, dq_ = daily.copy(), daily.copy(), daily.copy()
            for k, ev in enumerate(events):
                f_ok, t_ok, q_ok, lab = _topology(ev)
                ev["path"] = lab
                ev["forced_ok"] = f_ok
                ev["three_ok"] = t_ok
                ev["four_ok"] = q_ok
                ev["symbol"] = s
                ev["date"] = str(idx[ev["i"]].date())
                if ev["stage"] == "2":
                    j = events[k + 1]["i"] if k + 1 < len(events) else len(daily)
                    ev["episode_bars"] = int(j - ev["i"])
                    ev["in_window"] = bool(idx[ev["i"]] >= pd.Timestamp(START))
                    c = cl[s].to_numpy()
                    t, t60 = ev["i"], ev["i"] + 60
                    if t60 < len(c) and np.isfinite(c[t]) and c[t] > 0:
                        fwd = (c[t60] / c[t] - 1.0) if np.isfinite(c[t60]) else np.nan
                        bm = (spy[t60] / spy[t] - 1.0)
                        ev["fwd60"] = None if not np.isfinite(fwd) else round(float(fwd), 6)
                        ev["fwd60_excess"] = (None if not np.isfinite(fwd)
                                              else round(float(fwd - bm), 6))
                    else:
                        ev["fwd60"] = None
                        ev["fwd60_excess"] = None
                    if not f_ok:
                        df_[t:j] = "transition"
                    if not t_ok:
                        dt_[t:j] = "transition"
                    if not q_ok:
                        dq_[t:j] = "transition"
            panel_forced[s] = df_[keep]
            panel_three[s] = dt_[keep]
            panel_four[s] = dq_[keep]
            all_events.extend(events)

        out[vname] = {
            "runnable": True,
            "spec": {"flat_mode": spec.flat_mode, "flat_thr": spec.flat_thr,
                     "min_bars": spec.min_bars, "box_bars": spec.box_bars,
                     "box_amp": spec.box_amp, "note": spec.note},
            "强制循环": distribution(panel_forced, STAGE_STATES),
            "三条路径": distribution(panel_three, STAGE_STATES),
            "三条路径+3→2": distribution(panel_four, STAGE_STATES),
        }
        out[vname]["_panel"] = panel_forced
        cycle_test[vname] = all_events
    out["_cycle_events"] = cycle_test
    return out


# ============================================================================
# 状-3 Al Brooks 冲量与修正
# ============================================================================
#
#   原著版  ★ 只跑得了一半。Brooks 给了「单根 K 线」的阈值区间,
#           没给 20 根窗口的聚合规则,也没给重叠度阈值。
#           → 原著版不输出 trend/range/mixed 三态,只输出:
#             趋势棒占比 / 十字星占比 / 微型通道长度分布,
#             且按纪律跑严格端 0.50 / 中值 0.42 / 宽松端 0.33 三组。
#   行业版  趋势棒 ≥0.50;修正棒 ≤0.30;重叠度 ≥50% 为横盘;回看 20 根
#   XING版  实体占比 0.6 / 0.4;重叠度 0.4 / 0.6;回看 20 根

BROOKS_STATES = ("trend", "range", "mixed")

_note("状-3 的「同色连续性」手册只写了名字、没给阈值。本实现口径:"
      "连续性 = 窗口内主导颜色占比;趋势态要求 ≥0.60,震荡态要求 ≤0.60。"
      "★ 这是我们定的,不是原著也不是行业 —— 列入「要回去问的」。")
_note("状-3 重叠度定义:相邻两根 K 线 [low,high] 区间的交集长度 / 两者并集长度,"
      "窗口内取均值。")


def _bar_metrics(hi: np.ndarray, lo: np.ndarray, op: np.ndarray,
                 cl: np.ndarray) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    rng = hi - lo
    with np.errstate(invalid="ignore", divide="ignore"):
        body = np.abs(cl - op) / np.where(rng > 0, rng, np.nan)
    lo_p, hi_p = np.roll(lo, 1), np.roll(hi, 1)
    lo_p[0] = np.nan
    hi_p[0] = np.nan
    inter = np.minimum(hi, hi_p) - np.maximum(lo, lo_p)
    union = np.maximum(hi, hi_p) - np.minimum(lo, lo_p)
    with np.errstate(invalid="ignore", divide="ignore"):
        ov = np.clip(inter, 0, None) / np.where(union > 0, union, np.nan)
    up = (cl > op).astype(float)
    up[~np.isfinite(cl) | ~np.isfinite(op)] = np.nan
    return body, ov, up


def _micro_channel(hi: np.ndarray, lo: np.ndarray) -> np.ndarray:
    """逐日微型通道长度:连续 N 根不回补前一根低点(上行)或高点(下行)。"""
    n = len(hi)
    out = np.zeros(n, dtype=int)
    up_run = dn_run = 0
    for i in range(1, n):
        if not (np.isfinite(hi[i]) and np.isfinite(lo[i])
                and np.isfinite(hi[i - 1]) and np.isfinite(lo[i - 1])):
            up_run = dn_run = 0
            continue
        up_run = up_run + 1 if lo[i] > lo[i - 1] else 0
        dn_run = dn_run + 1 if hi[i] < hi[i - 1] else 0
        out[i] = max(up_run, dn_run)
        if out[i] > 0:
            out[i] += 1          # N 根 K 线构成 N-1 次不回补,长度按 K 线根数计
    return out


@dataclass
class BrooksSpec:
    name: str
    body_trend: float
    body_range: float
    ov_trend: float
    ov_range: float
    look: int = 20
    cont_trend: float = 0.60
    cont_range: float = 0.60
    note: str = ""


BROOKS_VERSIONS = {
    "行业版": BrooksSpec("行业版", 0.50, 0.30, 0.50, 0.50,
                         note="趋势棒 ≥0.50 / 修正棒 ≤0.30;重叠度 ≥50% 横盘"),
    "XING版": BrooksSpec("XING版", 0.60, 0.40, 0.40, 0.60,
                         note="手册现行口径"),
}

BROOKS_ORIGINAL_GROUPS = {
    "严格端 1/2": {"body_trend": 0.50, "body_doji": 0.25},
    "中值":      {"body_trend": 0.42, "body_doji": 0.29},
    "宽松端 1/3": {"body_trend": 0.33, "body_doji": 0.33},
}

BROOKS_QUOTE = ('Brooks《Trading Price Action Trends》(2012) Ch.1 + Glossary:'
                '趋势棒实体 > 柱体全长的 "about a third or half"(1/3~1/2);'
                '十字星实体 < "about a third or a quarter"(1/4~1/3);'
                '微型通道 "three to ten or more bars"。')


def run_brooks(symbols: list[str]) -> dict:
    p = cache.load()
    hi, lo, op, cl = p["high"], p["low"], p["open"], p["close"]
    idx = cl.index
    keep = np.asarray(idx >= pd.Timestamp(START))
    out: dict = {}

    # 先把逐根量算出来(三版共用)
    cache_m: dict[str, tuple] = {}
    for s in symbols:
        b, o, u = _bar_metrics(hi[s].to_numpy(), lo[s].to_numpy(),
                               op[s].to_numpy(), cl[s].to_numpy())
        mc = _micro_channel(hi[s].to_numpy(), lo[s].to_numpy())
        cache_m[s] = (b, o, u, mc)

    # ---- 原著版:只出单根统计 + 微型通道,三组区间端点 ----
    orig: dict = {"runnable": "部分",
                  "reason": "原著给了单根 K 线的阈值区间,但没给 20 根窗口的"
                            "聚合规则、也没给重叠度阈值 → 不输出三态",
                  "quote": BROOKS_QUOTE, "groups": {}}
    for gname, g in BROOKS_ORIGINAL_GROUPS.items():
        tb = db = tot = 0
        for s in symbols:
            b = cache_m[s][0][keep]
            v = b[np.isfinite(b)]
            tot += len(v)
            tb += int((v > g["body_trend"]).sum())
            db += int((v < g["body_doji"]).sum())
        orig["groups"][gname] = {
            "body_trend_thr": g["body_trend"], "body_doji_thr": g["body_doji"],
            "bars": tot,
            "trend_bar_share": round(tb / max(1, tot), 4),
            "doji_bar_share": round(db / max(1, tot), 4),
        }
    mcv = np.concatenate([cache_m[s][3][keep] for s in symbols])
    orig["micro_channel"] = {
        "bars": int(len(mcv)),
        "share_ge_3": round(float((mcv >= 3).mean()), 4),
        "share_ge_4": round(float((mcv >= 4).mean()), 4),
        "share_ge_10": round(float((mcv >= 10).mean()), 4),
        "max": int(mcv.max()),
        "p99": round(float(np.percentile(mcv, 99)), 1),
        "note": "原著物理下沿 3 根;XING 卡片报出门槛 N≥4;行业版 3 根",
    }
    out["原著版"] = orig

    # ---- 行业版 / XING 版:三态 ----
    for vname, spec in BROOKS_VERSIONS.items():
        panel: dict[str, np.ndarray] = {}
        raw_stat = {"body": [], "ov": [], "cont": []}
        for s in symbols:
            b, o, u, _ = cache_m[s]
            sb = pd.Series(b).rolling(spec.look, min_periods=spec.look).mean().to_numpy()
            so = pd.Series(o).rolling(spec.look, min_periods=spec.look).mean().to_numpy()
            su = pd.Series(u).rolling(spec.look, min_periods=spec.look).mean().to_numpy()
            cont = np.fmax(su, 1.0 - su)
            st = np.full(len(b), WARMUP, dtype=object)
            ok = np.isfinite(sb) & np.isfinite(so) & np.isfinite(cont)
            tr = ok & (sb >= spec.body_trend) & (so <= spec.ov_trend) & (cont >= spec.cont_trend)
            rg = ok & (sb <= spec.body_range) & (so >= spec.ov_range) & (cont <= spec.cont_range)
            st[ok] = "mixed"
            st[tr] = "trend"
            st[rg] = "range"
            panel[s] = st[keep]
            raw_stat["body"].append(sb[keep][np.isfinite(sb[keep])])
            raw_stat["ov"].append(so[keep][np.isfinite(so[keep])])
            raw_stat["cont"].append(cont[keep][np.isfinite(cont[keep])])
        d = distribution(panel, BROOKS_STATES)
        d["spec"] = {"body_trend": spec.body_trend, "body_range": spec.body_range,
                     "ov_trend": spec.ov_trend, "ov_range": spec.ov_range,
                     "look": spec.look, "cont_trend": spec.cont_trend,
                     "note": spec.note}
        for k in ("body", "ov", "cont"):
            v = np.concatenate(raw_stat[k])
            d[f"raw_{k}"] = {"mean": round(float(v.mean()), 4),
                             "p10": round(float(np.percentile(v, 10)), 4),
                             "median": round(float(np.median(v)), 4),
                             "p90": round(float(np.percentile(v, 90)), 4)}
        d["_panel"] = panel
        out[vname] = d
    return out


# ============================================================================
# 状-5 相对强度 —— ★ 三版是三种不同的算法,不是同一参数的不同取值
# ============================================================================
#
#   原著版 A  Weinstein / Mansfield RS
#             R = P / SPX;RS = (R / SMA52周(R) − 1) × 100;零轴分水岭
#   原著版 B  O'Neil RS Rating(★ 加权公式标为【行业近似,非原著写死】)
#             Score = 0.4×(P0/P63) + 0.2×(P0/P126) + 0.2×(P0/P189) + 0.2×(P0/P252)
#             → 百分位 1-99;买入候选 ≥80
#             ★★ 局限:我们只有 300 只票 → 只能算「池内百分位」,不是全市场百分位
#   XING版    大盘回调 ≥5% 窗口内的抗跌度;回看 24 个月;窗口 <4 返回样本不足

RS_QUOTE_A = ('Mansfield RS:R_t = Price_t / SPX_t;'
              'RS_t = (R_t / SMA52周(R_t) − 1) × 100;零轴为多空分水岭。'
              'Gemini 标为【原著写死】。')
RS_QUOTE_B = ('O\'Neil RS Rating 加权公式 0.4/0.2/0.2/0.2。'
              '★ IBD 从未公开过确切公式,该权重是业界广为流传的近似 → '
              '本报告标为【行业近似,非原著写死】。RS ≥ 80 门槛本身原著里有。')


def _spy_drawdown_windows(spy: pd.Series, thr: float
                          ) -> list[tuple[int, int, int, float]]:
    """
    找大盘从阶段高点回调 ≥thr 的窗口。
    返回 [(峰值下标, 谷底下标, 可知日下标, 大盘跌幅)]。
    ★ 可知日 = 回升到峰值(或创新高)那天 —— 在那之前这个窗口还没结束,不许用。
    """
    v = spy.to_numpy()
    n = len(v)
    out = []
    peak_i, peak = 0, v[0]
    in_dd = False
    trough_i, trough = 0, v[0]
    for i in range(1, n):
        if not np.isfinite(v[i]):
            continue
        if not in_dd:
            if v[i] >= peak:
                peak_i, peak = i, v[i]
            elif v[i] <= peak * (1.0 - thr):
                in_dd = True
                trough_i, trough = i, v[i]
        else:
            if v[i] < trough:
                trough_i, trough = i, v[i]
            if v[i] >= peak:
                out.append((peak_i, trough_i, i, trough / peak - 1.0))
                in_dd = False
                peak_i, peak = i, v[i]
    return out


RS_STATES = ("resilient", "inline", "weaker", "insufficient_sample")


def _xing_rs(cl_sym: np.ndarray, wins: list, idx: pd.DatetimeIndex,
             look_months: int, resilient_rule: str,
             ma50: np.ndarray | None) -> np.ndarray:
    """逐日 XING 相对强度分级。只用「可知日 ≤ t」且落在回看期内的窗口。"""
    n = len(cl_sym)
    out = np.full(n, "insufficient_sample", dtype=object)
    look = pd.DateOffset(months=look_months)
    # 预算每个窗口对本票的分类
    cls: list[tuple[int, pd.Timestamp, str]] = []
    for pk, tr, kn, mkt in wins:
        a, b = cl_sym[pk], cl_sym[tr]
        if not (np.isfinite(a) and np.isfinite(b) and a > 0):
            continue
        st = b / a - 1.0
        if resilient_rule == "xing":
            res = (st > 0) or (abs(st) < abs(mkt) / 3.0)
        else:                                  # gemini 建议:≤50% 且不破 50 日线
            above = (ma50 is not None and np.isfinite(ma50[tr])
                     and np.isfinite(cl_sym[tr]) and cl_sym[tr] > ma50[tr])
            res = (st > 0) or (abs(st) <= abs(mkt) * 0.5 and above)
        if res:
            lab = "resilient"
        elif abs(st) > abs(mkt) * 1.5:
            lab = "weaker"
        else:
            lab = "inline"
        cls.append((kn, idx[kn], lab))

    for i in range(n):
        if not np.isfinite(cl_sym[i]):
            continue
        lo_dt = idx[i] - look
        c = {"resilient": 0, "inline": 0, "weaker": 0}
        tot = 0
        for kn, dt, lab in cls:
            if kn <= i and dt >= lo_dt:
                c[lab] += 1
                tot += 1
        if tot < 4:
            out[i] = "insufficient_sample"
        else:
            out[i] = max(c, key=lambda k: (c[k], k == "inline"))
    return out


def run_rs(symbols: list[str]) -> dict:
    p = cache.load()
    cl = p["close"][symbols]
    idx = cl.index
    keep = np.asarray(idx >= pd.Timestamp(START))
    spy = data.load_benchmark("SPY")["close"].reindex(idx).ffill()

    out: dict = {}

    # ---- 原著版 A:Mansfield RS ----
    r = cl.div(spy, axis=0)
    rsm = (r / r.rolling(252, min_periods=252).mean() - 1.0) * 100.0
    selA = (rsm > 0)
    out["原著版A_Mansfield"] = {
        "runnable": True, "algo": "RS=(R/SMA252(R)−1)×100,选 RS>0",
        "quote": RS_QUOTE_A, "citation_status": "【待核实】",
        "selected_share": round(float(selA.to_numpy()[keep][
            np.isfinite(rsm.to_numpy()[keep])].mean()), 4),
        "nan_share": round(float((~np.isfinite(rsm.to_numpy()[keep])).mean()), 4),
    }

    # ---- 原著版 B:O'Neil 式 RS Rating(池内百分位) ----
    sc = (0.4 * cl / cl.shift(63) + 0.2 * cl / cl.shift(126)
          + 0.2 * cl / cl.shift(189) + 0.2 * cl / cl.shift(252))
    pct = sc.rank(axis=1, pct=True) * 100.0
    selB = (pct >= 80.0)
    out["原著版B_ONeil"] = {
        "runnable": True,
        "algo": "Score=0.4×P0/P63+0.2×P0/P126+0.2×P0/P189+0.2×P0/P252 → 池内百分位,选 ≥80",
        "quote": RS_QUOTE_B, "citation_status": "【疑似不实】(加权公式),门槛 80 为【待核实】",
        "limitation": "★ 只有 300 只票 → 池内百分位,不是全市场百分位。不许当全市场用。",
        "selected_share": round(float(selB.to_numpy()[keep][
            np.isfinite(pct.to_numpy()[keep])].mean()), 4),
        "nan_share": round(float((~np.isfinite(pct.to_numpy()[keep])).mean()), 4),
    }

    # ---- XING 版 + Gemini 建议版 ----
    ma50 = cl.rolling(50, min_periods=50).mean()
    for tag, thr, rule in (("XING版", 0.05, "xing"),
                           ("Gemini建议版", 0.04, "gemini")):
        wins = _spy_drawdown_windows(spy, thr)
        panel: dict[str, np.ndarray] = {}
        nan_runs: list[int] = []
        nan_days = tot_days = 0
        for s in symbols:
            st = _xing_rs(cl[s].to_numpy(), wins, idx, 24, rule,
                          ma50[s].to_numpy())
            st = st[keep]
            panel[s] = st
            tot_days += len(st)
            nan_days += int((st == "insufficient_sample").sum())
            cur = 0
            mx = 0
            for x in st:
                cur = cur + 1 if x == "insufficient_sample" else 0
                mx = max(mx, cur)
            nan_runs.append(mx)
        d = distribution(panel, RS_STATES)
        d["windows_total"] = len(wins)
        d["windows"] = [{"peak": str(idx[a].date()), "trough": str(idx[b].date()),
                         "knowable": str(idx[c].date()),
                         "mkt_drawdown": round(float(m), 4)}
                        for a, b, c, m in wins]
        d["insufficient_share"] = round(nan_days / max(1, tot_days), 4)
        d["longest_insufficient_run"] = {
            "max": int(max(nan_runs)) if nan_runs else 0,
            "median_per_symbol": float(np.median(nan_runs)) if nan_runs else 0,
        }
        d["_panel"] = panel
        d["_sel"] = {s: (panel[s] == "resilient") for s in symbols}
        out[tag] = d

    # ---- 三种算法选出来的票重叠多少 ----
    kA = selA.to_numpy()[keep]
    kB = selB.to_numpy()[keep]
    kX = np.column_stack([out["XING版"]["_sel"][s] for s in symbols])
    okA = np.isfinite(rsm.to_numpy()[keep])
    okB = np.isfinite(pct.to_numpy()[keep])

    def _ov(x, y, mx, my):
        """逐日 Jaccard + 条件重叠率,只在两边都算得出来的格子上比。"""
        m = mx & my
        j, p_xy, p_yx, nd = [], [], [], 0
        for i in range(x.shape[0]):
            a = x[i] & m[i]
            b = y[i] & m[i]
            u = int((a | b).sum())
            ia = int((a & b).sum())
            if u == 0:
                continue
            nd += 1
            j.append(ia / u)
            if a.sum():
                p_xy.append(ia / int(a.sum()))
            if b.sum():
                p_yx.append(ia / int(b.sum()))
        return {"days": nd,
                "jaccard_mean": round(float(np.mean(j)), 4) if j else None,
                "share_of_X_also_in_Y": round(float(np.mean(p_xy)), 4) if p_xy else None,
                "share_of_Y_also_in_X": round(float(np.mean(p_yx)), 4) if p_yx else None}

    # ★ 补充:XING 版「抗跌」到底选出了什么票 —— 行业分布 + 和 A 版的基准率对比
    meta = cache.panel_meta()
    res_days = {s: int((out["XING版"]["_panel"][s] == "resilient").sum())
                for s in symbols}
    never = [s for s in symbols
             if (out["XING版"]["_panel"][s] == "insufficient_sample").all()]
    sec: dict[str, int] = {}
    for s, n in res_days.items():
        if n:
            k = str(meta.loc[s, "sector"]) if s in meta.index else "?"
            sec[k] = sec.get(k, 0) + n
    tot = max(1, sum(sec.values()))
    out["_xing_detail"] = {
        "从未攒够 4 个窗口的票数": len(never),
        "抗跌日数最多的 15 只": sorted(res_days.items(), key=lambda kv: -kv[1])[:15],
        "抗跌日的行业分布": {k: round(v / tot, 4) for k, v in
                             sorted(sec.items(), key=lambda kv: -kv[1])},
        "Mansfield RS>0 的基准占比(全池全窗口)":
            out["原著版A_Mansfield"]["selected_share"],
    }

    okX = np.ones_like(kX, dtype=bool)
    out["_overlap"] = {
        "A_Mansfield vs B_ONeil": _ov(kA, kB, okA, okB),
        "A_Mansfield vs XING": _ov(kA, kX, okA, okX),
        "B_ONeil vs XING": _ov(kB, kX, okB, okX),
        "note": "只在两种算法当天都算得出结果的格子上比;XING 版的"
                "insufficient_sample 算「没选中」而不是「算不出」—— "
                "样本不足是它自己的合法输出。",
    }
    return out
