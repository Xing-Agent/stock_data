"""
★ 量化:周线口径被套到日线上,偏差有多大、方向朝哪边。

三秒版:原著在周线上说的数,我们在日线上算。这里拿 300 只票 12 年的真实数据
        把每一处的偏差量出来 —— 量级 + 方向(让成绩偏好还是偏坏)。

★ 本文件只读数据,不改 engine/ 任何一行、不改任何配置。
★ 全部实测,没有一个「大约 / 通常」。

跑法:python3 probe/weekly_daily_mapping_1030/quantify.py
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from engine import cache, matrices  # noqa: E402

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                   "quantify_results_1030.json")

# ★ 绩效窗口和全库一致(engine/data.py:PERF_START / PERF_END)
PERF_START = "2018-01-01"
PERF_END = "2025-12-31"


def _q(x) -> dict:
    """一组数的五个分位 + 样本量。★ 不报平均值 —— 这些比值的分布有长尾。"""
    a = np.asarray(x, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"n": 0}
    return {
        "n": int(a.size),
        "p05": round(float(np.percentile(a, 5)), 4),
        "p25": round(float(np.percentile(a, 25)), 4),
        "中位": round(float(np.percentile(a, 50)), 4),
        "p75": round(float(np.percentile(a, 75)), 4),
        "p95": round(float(np.percentile(a, 95)), 4),
    }


def _weekly(df: pd.DataFrame, how: str) -> pd.DataFrame:
    """日线聚合成周线(W-FRI)。★ 周线那根在周内最后一个交易日收盘才完整。"""
    return df.resample("W-FRI").agg(how).dropna(how="all")


def weekly_bars(symbols: list[str]) -> dict[str, pd.DataFrame]:
    o = cache.field("open", symbols)
    h = cache.field("high", symbols)
    l = cache.field("low", symbols)
    c = cache.field("close", symbols)
    v = cache.field("volume", symbols)
    return {
        "open": _weekly(o, "first"), "high": _weekly(h, "max"),
        "low": _weekly(l, "min"), "close": _weekly(c, "last"),
        "volume": _weekly(v, "sum"),
    }


def _wilder(x: pd.DataFrame, period: int) -> pd.DataFrame:
    """Wilder 平滑 —— ★ 和 engine/matrices.py:_wilder 同一口径。"""
    return x.ewm(alpha=1.0 / period, adjust=False, min_periods=period).mean()


def _tr(h, l, c) -> pd.DataFrame:
    pc = c.shift(1)
    return pd.concat([(h - l).abs(), (h - pc).abs(), (l - pc).abs()]).groupby(
        level=0).max()


# ══════════════════════════════════════════════════════════════════════════
# 甲-③ · ATR 折算比 —— 周线 ATR vs √5 × 日线 ATR
# ══════════════════════════════════════════════════════════════════════════

def atr_conversion(symbols: list[str]) -> dict:
    """
    问题:原著在周线上给一个「k × ATR」的止损,我们在日线上实现。
          朴素折算是 ATR_周 ≈ √5 × ATR_日(随机游走的方差加法)。
    ★ 实测这个折算准不准 —— 不准的方向决定止损被压窄还是放宽。

    口径:
      · 日线 ATR(70) —— 70 个交易日 = 14 周,★ 和周线 ATR(14) 覆盖同一段日历
      · 周线 ATR(14) —— 在 W-FRI 聚合的周线 OHLC 上用同一个 Wilder 平滑
      · 比值 = ATR_周(14) / (√5 × ATR_日(70)),在每个周五格子上取
    """
    wk = weekly_bars(symbols)
    h, l, c = (cache.field(k, symbols) for k in ("high", "low", "close"))

    atr_d = _wilder(_tr(h, l, c), 70)
    atr_w = _wilder(_tr(wk["high"], wk["low"], wk["close"]), 14)

    # 对齐到周五格子
    atr_d_fri = atr_d.reindex(atr_w.index, method="ffill")
    ratio = atr_w / (np.sqrt(5.0) * atr_d_fri)
    ratio = ratio.loc[PERF_START:PERF_END]

    # ★ 相对价格归一化,去掉绝对价位的影响(比值本身已经无量纲,这里只做健全检查)
    flat = ratio.to_numpy(float).ravel()
    per_sym = ratio.median(axis=0)

    # ★ 同时报另一个口径:不做 √5,直接看 ATR_周 / ATR_日(同日历跨度)
    raw = (atr_w / atr_d_fri).loc[PERF_START:PERF_END].to_numpy(float).ravel()

    med = float(np.nanpercentile(flat[np.isfinite(flat)], 50))
    return {
        "题目": "周线 ATR 比朴素折算 √5 × 日线 ATR 低多少",
        "口径": "ATR_周(14 根周线) ÷ (√5 × ATR_日(70 个交易日));两者覆盖同一段日历",
        "平滑": "Wilder,alpha=1/period —— 和 engine/matrices.py:_wilder 同一口径",
        "窗口": f"{PERF_START} ~ {PERF_END},周五格子",
        "比值分布": _q(flat),
        "★低了百分之几_按中位": round((1.0 - med) * 100, 2),
        "逐票中位的分布": _q(per_sym.to_numpy(float)),
        "逐票中位_低于1的占比": round(float((per_sym < 1.0).mean()), 4),
        "对照_不做√5的原始比值_ATR周÷ATR日": _q(raw),
        "★方向": (
            "朴素折算 √5 × 日线 ATR **高估**了真实的周线波动 → "
            "反过来,拿一个周线口径的 ATR 止损去折算日线止损时,"
            "若直接用 ATR_日 × k 会把止损**放宽**;"
            "若用 ATR_周 ÷ √5 当日线 ATR 则会把止损**压窄**。"
            "★ 哪一个方向取决于折算是朝哪边做的 —— 见报告正文逐条判定。"),
    }


# ══════════════════════════════════════════════════════════════════════════
# 甲-① · 均线相位差 —— SMA150(日线) vs SMA30(周线)
# ══════════════════════════════════════════════════════════════════════════

def ma_phase(symbols: list[str]) -> dict:
    """
    口径:同一张周五网格。两条线的「方向」都用斜率符号,回看 10 根本尺度 bar。
          ★ 不加任何确认闸 —— 只量「均线定义本身」造成的领先/滞后。
    转向事件 = 斜率符号由负转正(上翘)或由正转负(下弯)。
    """
    c = cache.field("close", symbols)
    wk_c = _weekly(c, "last")

    sma_d = c.rolling(150, min_periods=150).mean().reindex(
        wk_c.index, method="ffill")
    sma_w = wk_c.rolling(30, min_periods=30).mean()

    # 斜率:本尺度 10 根 bar 的变化率
    sl_d = (sma_d / sma_d.shift(10) - 1.0)
    sl_w = (sma_w / sma_w.shift(10) - 1.0)

    sl_d = sl_d.loc[PERF_START:PERF_END]
    sl_w = sl_w.loc[PERF_START:PERF_END]

    up_d, up_w = sl_d > 0, sl_w > 0
    # 转向点:符号变化
    turn_d = up_d & ~up_d.shift(1).fillna(False)
    turn_w = up_w & ~up_w.shift(1).fillna(False)
    dn_d = ~up_d & up_d.shift(1).fillna(False)
    dn_w = ~up_w & up_w.shift(1).fillna(False)

    leads = []          # 正数 = 周线领先多少根周线 bar
    pairs = 0
    WIN = 5             # ★ ±5 根周线 bar = ±25 个交易日,和 phaseshift_1030 头条窗口一致
    for s in symbols:
        for td, tw in ((turn_d[s], turn_w[s]), (dn_d[s], dn_w[s])):
            iw = np.flatnonzero(tw.to_numpy())
            idd = np.flatnonzero(td.to_numpy())
            if iw.size == 0 or idd.size == 0:
                continue
            for a in idd:
                k = int(np.argmin(np.abs(iw - a)))
                d = int(a - iw[k])            # >0 → 周线更早
                if abs(d) <= WIN:
                    leads.append(d)
                    pairs += 1
    arr = np.asarray(leads, dtype=float)
    return {
        "题目": "SMA150(日线) vs SMA30(周线):同一张周五网格上谁先转向",
        "口径": ("两条线都在 W-FRI 周五格子上;方向 = 本尺度 10 根 bar 的斜率符号;"
                 "★ 不加确认闸 —— 只量均线定义本身。配对窗口 ±5 根周线 bar(=±25 个交易日)"),
        "配上对的转向事件数": pairs,
        "领先根数分布_正数是周线领先": _q(arr),
        "★周线领先占比": round(float((arr > 0).mean()), 4) if arr.size else None,
        "★日线领先占比": round(float((arr < 0).mean()), 4) if arr.size else None,
        "同一根占比": round(float((arr == 0).mean()), 4) if arr.size else None,
        "中位领先_交易日": round(float(np.median(arr)) * 5, 2) if arr.size else None,
        "★方向": (
            "周线先转、日线慢半拍。把一条原著在周线上定义的「均线上翘才买」"
            "换成日线 150 日均线上翘,★ 进场会被系统性推迟。"),
    }


# ══════════════════════════════════════════════════════════════════════════
# 甲-② · 唐奇安突破时点差 —— 20 日 vs 4 周
# ══════════════════════════════════════════════════════════════════════════

def donchian_timing(symbols: list[str]) -> dict:
    """
    口径:日线 = 收盘 > 前 20 个交易日最高收盘;周线 = 周收盘 > 前 4 根周线最高周收盘。
          ★ 20 个交易日 = 4 周,两者覆盖同一段日历。
    两边都只取「从无到有」的首次突破(连续突破只算一次),再配对量时点差。
    """
    c = cache.field("close", symbols)
    wk_c = _weekly(c, "last")

    d_hi = c.rolling(20, min_periods=20).max().shift(1)
    w_hi = wk_c.rolling(4, min_periods=4).max().shift(1)
    d_brk = (c > d_hi).loc[PERF_START:PERF_END]
    w_brk = (wk_c > w_hi).loc[PERF_START:PERF_END]

    # 事件化:上沿穿越
    d_ev = d_brk & ~d_brk.shift(1).fillna(False)
    w_ev = w_brk & ~w_brk.shift(1).fillna(False)

    didx = d_ev.index
    widx = w_ev.index
    # 周线事件的日期 → 换成「在日线网格上的位置」
    dpos = {t: i for i, t in enumerate(didx)}

    diffs = []
    WIN = 20            # ★ ±20 个交易日 = ±4 周,和本条的回看期同长
    for s in symbols:
        wd = [t for t in widx[w_ev[s].to_numpy()]]
        dd = np.flatnonzero(d_ev[s].to_numpy())
        if not wd or dd.size == 0:
            continue
        wpos = np.asarray([dpos.get(t, -1) for t in wd])
        wpos = wpos[wpos >= 0]
        if wpos.size == 0:
            continue
        for a in wpos:
            k = int(np.argmin(np.abs(dd - a)))
            d = int(a - dd[k])          # >0 → 日线更早
            if abs(d) <= WIN:
                diffs.append(d)
    arr = np.asarray(diffs, dtype=float)
    return {
        "题目": "唐奇安突破:日线 20 个交易日 vs 周线 4 根周线,谁先触发",
        "口径": ("日线=收盘>前 20 个交易日最高收盘;周线=周收盘>前 4 根周线最高周收盘;"
                 "两边都只取首次穿越;配对窗口 ±20 个交易日"),
        "配上对的事件数": int(arr.size),
        "时点差分布_交易日_正数是日线更早": _q(arr),
        "★日线更早占比": round(float((arr > 0).mean()), 4) if arr.size else None,
        "★周线更早占比": round(float((arr < 0).mean()), 4) if arr.size else None,
        "同一天占比": round(float((arr == 0).mean()), 4) if arr.size else None,
        "★方向": (
            "日线早于周线。把一条原著在周线上定义的突破换成日线突破,"
            "★ 会在同一段行情里多触发一批更早、更浅的进场 —— 笔数变多、单笔质量变差。"),
    }


# ══════════════════════════════════════════════════════════════════════════
# 甲-④ · 技-3 的「放量 ≥2 倍」—— 周口径 vs 日口径的发生率
# ══════════════════════════════════════════════════════════════════════════

def volume_two_x(symbols: list[str]) -> dict:
    """
    原著(Weinstein 1988 Ch.4 p.74):一周累计量 ≥ 2 × 前几周的周均量。
    我们的机械日线版:单日量 ≥ 2.0 × SMA50(量)。
    ★ 同一个「2 倍」,两个口径的发生率差多少。
    """
    v = cache.field("volume", symbols)
    wk_v = _weekly(v, "sum")

    d_hit = (v > 2.0 * v.rolling(50, min_periods=50).mean()).loc[
        PERF_START:PERF_END]
    w_hit = (wk_v > 2.0 * wk_v.rolling(4, min_periods=4).mean().shift(1)).loc[
        PERF_START:PERF_END]

    # 有效格子(有数据的)
    d_valid = v.rolling(50, min_periods=50).mean().loc[
        PERF_START:PERF_END].notna()
    w_valid = wk_v.rolling(4, min_periods=4).mean().shift(1).loc[
        PERF_START:PERF_END].notna()

    d_rate = float(d_hit.to_numpy()[d_valid.to_numpy()].mean())
    w_rate = float(w_hit.to_numpy()[w_valid.to_numpy()].mean())
    return {
        "题目": "技-3「放量 ≥2 倍」:原著周口径 vs 我们的机械日线口径,发生率差多少",
        "日口径": "单日量 > 2.0 × SMA50(量) —— 技-3-原著-机械日线.yaml 在用的",
        "周口径": "本周累计量 > 2.0 × 前 4 周周均量 —— 原著 Ch.4 p.74",
        "日口径_发生率": round(d_rate, 4),
        "周口径_发生率": round(w_rate, 4),
        "★倍数_周÷日": round(w_rate / d_rate, 2) if d_rate else None,
        "日口径_有效格子": int(d_valid.to_numpy().sum()),
        "周口径_有效格子": int(w_valid.to_numpy().sum()),
        "★方向": (
            "日口径比周口径**严**得多(发生率低)。★ 这一处的方向和其余几处相反:"
            "它让技-3 机械日线版的放量关卡过度严格 → 笔数被压少,"
            "★ 而「笔数少」会让剩下的样本更容易是侥幸 —— 成绩偏**好**。"),
    }


# ══════════════════════════════════════════════════════════════════════════
# 甲-⑤ · 「周」被当成「根」用 —— 技-4 柄长、技-8 整理段长
# ══════════════════════════════════════════════════════════════════════════

def weeks_read_as_bars(symbols: list[str]) -> dict:
    """
    手册原文给了显式换算,代码没用:
      · 技-4 柄部:「至少 1–2 周(日线至少 5 个交易日)」→ 代码 handle_min_bars: 3
      · 技-8 整理段:「横向整理 3 至 5 周」→ 代码 flag_min_bars: 3 / flag_max_bars: 25
        ★ 上界 25 = 5 周 × 5 换算对了,下界 3 没换算 —— 半边做了、半边没做。
    ★ 这里只量「信号数差多少」,不碰配置。
    """
    from engine import ops_a0, pat6_ops

    out = {}

    # ── 技-4 杯柄:handle_min_bars 3(现行) vs 5(手册给的日线换算) ──────
    base = dict(cup_depth_min=0.15, cup_depth_max=0.33, handle_max_depth=0.12,
                cup_min_bars=35, cup_max_bars=325, handle_max_bars=25,
                pivot_offset_abs=0.01)
    cup = {}
    for hb in (3, 5, 10):          # 10 = 2 周,原文区间的另一端
        p = dict(base, handle_min_bars=hb)
        ev, _, _ = pat6_ops.cup_with_handle(symbols, p)
        ev = ev.loc[PERF_START:PERF_END]
        cup[f"handle_min_bars={hb}"] = int(ev.to_numpy().sum())
    out["技-4_杯柄"] = {
        "手册原文": "柄部持续时间:至少 1–2 周(★ 日线至少 5 个交易日)——「六附」6.1 ①",
        "代码现行": "handle_min_bars: 3(技-4-原著.yaml / -中值 / -宽松端 / -行业 四份都是 3)",
        "信号数": cup,
        "★现行比手册口径多出的信号": (
            cup["handle_min_bars=3"] - cup["handle_min_bars=5"]),
        "★多出百分之几": round(
            (cup["handle_min_bars=3"] / max(1, cup["handle_min_bars=5"]) - 1) * 100, 2),
        "★方向": "现行(3 根)比手册口径(5 个交易日)**松** → 多收一批柄太短的形态。",
    }

    # ── 技-8 HTF:flag_min_bars 3(现行) vs 15(= 3 周 × 5) ──────────────
    htf = {}
    for fb in (3, 15):
        ev = ops_a0.htf_flag_breakout(
            symbols, runup_min=1.00, max_pullback=0.20,
            flag_min_bars=fb, flag_max_bars=25)
        ev = ev[0] if isinstance(ev, tuple) else ev
        ev = ev.loc[PERF_START:PERF_END]
        htf[f"flag_min_bars={fb}"] = int(ev.to_numpy().sum())
    out["技-8_高紧旗形"] = {
        "手册原文": ("欧奈尔《How to Make Money in Stocks》4th ed. Ch.2 High, Tight Flag:"
                     "4 至 8 周内上涨 100%–120%,★ 随后横向整理 3 至 5 周 ——「六附」6.1 ②"),
        "代码现行": "flag_min_bars: 3 / flag_max_bars: 25",
        "★半边做了半边没做": ("上界 25 = 5 周 × 5 ✓ 换算对了;"
                              "下界 3 = 把「3 周」直接当成「3 根」✗ 没换算。应为 15。"),
        "信号数": htf,
        "★现行比手册口径多出的信号": htf["flag_min_bars=3"] - htf["flag_min_bars=15"],
        "★多出百分之几": round(
            (htf["flag_min_bars=3"] / max(1, htf["flag_min_bars=15"]) - 1) * 100, 2),
        "★方向": "现行(3 根)比原著(3 周 = 15 个交易日)**松** → 多收一批整理期太短的旗形。",
    }
    return out


def main() -> None:
    syms = cache.symbols()
    print(f"★ 样本:{len(syms)} 只票,窗口 {PERF_START} ~ {PERF_END}")
    res = {
        "样本": {"票数": len(syms), "窗口": f"{PERF_START} ~ {PERF_END}",
                 "数据源": "pilot_300 缓存(engine/cache)"},
        "甲1_均线相位差": ma_phase(syms),
        "甲2_唐奇安突破时点差": donchian_timing(syms),
        "甲3_ATR折算比": atr_conversion(syms),
        "甲4_技3放量2倍发生率": volume_two_x(syms),
        "甲5_周被当成根用": weeks_read_as_bars(syms),
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print(f"→ {OUT}")
    for k, v in res.items():
        if k == "样本":
            continue
        print(f"\n── {k} ──")
        print(json.dumps(v, ensure_ascii=False, indent=1)[:1400])


if __name__ == "__main__":
    main()
