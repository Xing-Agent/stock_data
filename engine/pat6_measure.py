"""
pat6_measure —— 六条形态的「实测题」,不跑链,只量东西。

大白话:这个文件回答的全是「我们是不是做错了」这类问题 ——
不需要跑交易、不需要算 Z,只需要把两种写法都算出来,摆在一起数一数。

六道题:
  ① 技-6 原著 3 日规则 vs 我们的百分比收窄版 —— 箱体数量与位置重叠多少
  ② 技-3 忠实周线版 vs 机械日线版 —— 信号数差多少倍
  ③ 技-5 缩量三端 —— 门禁通过的日×票、以及真实链的笔数(笔数由 pat6_run 给)
  ④ 技-14 走带(Walking the Bands)—— 触下轨之后继续跌的比例、连续贴轨最长天数
  ⑤ 技-11 Spring 1/2/3 号分流 —— 各多少个、各自 60 日后续表现
  ⑥ 技-4 枢纽点 +$0.10 占股价的比例分布 —— 「原著对但过时了」那一类

★ 绩效/统计窗口一律 2018-01-02 起(和跑链一致),预热用 2014 起的数据。
跑法:python3 -m engine.pat6_measure
"""

from __future__ import annotations

import json
import os
import resource
import subprocess
import time

import numpy as np
import pandas as pd

from . import cache, data, matrices, ops_1029, pat6_ops

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "results_1029_技术派六条实测.json")


def _perf_mask(index) -> np.ndarray:
    return np.asarray((index >= pd.Timestamp(data.PERF_START))
                      & (index <= pd.Timestamp(data.PERF_END)))


def _q(a, qs=(0, 10, 25, 50, 75, 90, 100)) -> dict:
    a = np.asarray(a, dtype=float)
    a = a[np.isfinite(a)]
    if a.size == 0:
        return {"n": 0}
    return {"n": int(a.size), "均值": float(a.mean()),
            **{f"p{p}": float(np.percentile(a, p)) for p in qs}}


# ===========================================================================
# ① 技-6:原著 3 日规则 vs 百分比收窄版 —— 箱体数量与位置重叠
# ===========================================================================

def q1_darvas_overlap(syms: list[str], bars: int = 25,
                      max_range_pct: float = 0.20) -> dict:
    top, bot, alive, start, boxes = pat6_ops.darvas_boxes(syms, 3)
    narrow, nhi, nlo = pat6_ops.narrow_range_box(syms, bars, max_range_pct)
    idx = alive.index
    pm = _perf_mask(idx)

    A = alive.to_numpy(bool)[pm, :]              # 原著箱体「活着」的日×票
    B = narrow.to_numpy(bool)[pm, :]             # 百分比版「窄幅」的日×票
    inter = int((A & B).sum())
    ua, ub = int(A.sum()), int(B.sum())
    jac = inter / max(1, ua + ub - inter)

    # 箱体「段」数:原著按状态机数;百分比版按连续 True 段数
    def _segments(m: np.ndarray) -> int:
        d = np.diff(m.astype(np.int8), axis=0, prepend=np.zeros((1, m.shape[1]), np.int8))
        return int((d == 1).sum())

    n_a_seg, n_b_seg = _segments(A), _segments(B)

    # 原著箱体里有多少「完全没被百分比版覆盖」的
    cov_a = float((A & B).sum() / max(1, ua))
    cov_b = float((A & B).sum() / max(1, ub))

    # 振幅分布:原著箱体的 (top−bot)/top —— ★ 原著对振幅一个字都没写,
    #   所以这个分布本身就是答案:原著箱体的振幅跨度有多大。
    amp = ((top - bot) / top).to_numpy(float)[pm, :]
    amp = amp[A]
    n_boxes = sum(len(v) for v in boxes.values())
    # 行业版那道 18% 安全阀会砍掉多少原著箱体日
    over18 = float((amp > 0.18).mean()) if amp.size else float("nan")

    return {
        "题目": "技-6:原著 3 日规则认出来的箱体 vs 我们的「N 天内区间收窄到 X%」版,"
                "数量和位置重叠多少",
        "口径": {"原著": "连续 3 天未被穿破 → 箱顶;箱顶确立后同法认箱底(Darvas 1960 Ch.4)",
                 "XING": f"近 {bars} 根 (max(High)−min(Low))/mean(Close) ≤ {max_range_pct}"},
        "原著箱体_日×票": ua,
        "XING窄幅_日×票": ub,
        "交集_日×票": inter,
        "★Jaccard重叠率": round(jac, 4),
        "原著箱体日被XING覆盖的比例": round(cov_a, 4),
        "XING窄幅日落在原著箱体里的比例": round(cov_b, 4),
        "原著箱体段数_绩效窗口内起始": n_a_seg,
        "XING窄幅段数_绩效窗口内起始": n_b_seg,
        "原著箱体总数_全历史含预热": n_boxes,
        "★原著箱体振幅分布_(top−bot)/top": _q(amp),
        "★振幅>18%的原著箱体日占比": round(over18, 4) if np.isfinite(over18) else None,
        "怎么读": "Jaccard 低 = 两种写法认出来的根本不是同一批结构。"
                  "★ 振幅分布跨度大,正说明原著不该有振幅上限 —— "
                  "行业版那道 18% 是风控安全阀,不是箱体定义。",
    }


# ===========================================================================
# ② 技-3:忠实周线版 vs 机械日线版 —— 信号数
# ===========================================================================

def q2_weinstein_weekly_vs_daily(syms: list[str]) -> dict:
    idx = cache.field("close", syms).index
    pm = _perf_mask(idx)
    close = cache.field("close", syms)
    high = cache.field("high", syms)
    vol = cache.field("volume", syms)

    def n(df):
        return int(np.asarray(df.fillna(False).to_numpy(bool))[pm, :].sum())

    rows = []
    for bw, bd, tag in ((13, 63, "底盘 13 周 / 63 日(≈3 个月)"),
                        (9, 42, "底盘 9 周 / 42 日(≈2 个月)")):
        wk_brk = pat6_ops.weinstein_weekly_breakout(syms, bw, 2.0, 4, require_vol=False)
        wk_all = pat6_ops.weinstein_weekly_breakout(syms, bw, 2.0, 4, require_vol=True)
        d_brk = close > high.rolling(bd, min_periods=bd).max().shift(1)
        d_vol = vol >= 2.0 * pat6_ops.sma_vol(50, syms).shift(1)
        d_all = d_brk & d_vol
        rows.append({
            "底盘": tag,
            "周线_只要突破": n(wk_brk),
            "周线_突破+周量≥2×前4周均量": n(wk_all),
            "周线_放量这一关的通过率": round(n(wk_all) / max(1, n(wk_brk)), 4),
            "日线_只要突破": n(d_brk),
            "日线_突破+单日量≥2×SMA50": n(d_all),
            "日线_放量这一关的通过率": round(n(d_all) / max(1, n(d_brk)), 4),
            "★信号数之比_周线÷日线": round(n(wk_all) / max(1, n(d_all)), 3),
        })
    # 单日量 ≥2×SMA50 这件事本身在池子里有多罕见
    rate_day = float(np.asarray((vol >= 2.0 * pat6_ops.sma_vol(50, syms).shift(1))
                                .fillna(False).to_numpy(bool))[pm, :].mean())
    wk, last_rows, wid = pat6_ops.weekly_frames(syms)
    wv = wk["volume"]
    wavg = wv.rolling(4, min_periods=4).mean().shift(1)
    rate_week = float((wv >= 2.0 * wavg).to_numpy(bool).mean())
    return {
        "题目": "技-3:原著「放量 ≥2 倍」是周线口径 —— 忠实周线版 vs 机械日线版,"
                "信号数差多少",
        "原文": 'Weinstein 1988 Ch.4 p.74【待核实】:"a one-week volume spike that is '
                'at least twice the average volume of the past few weeks"',
        "逐档": rows,
        "★「量≥2倍」这件事本身的发生率": {
            "单日量 ≥2×SMA50(日)": round(rate_day, 4),
            "一周累计量 ≥2×前4周周均量(周)": round(rate_week, 4),
            "怎么读": "同一个「2 倍」,换了口径之后发生率差一个量级 —— "
                      "这就是 状-3 撞过的那个坑。",
        },
    }


# ===========================================================================
# ③ 技-5:缩量三端的门禁通过量
# ===========================================================================

def q3_vcp_dryup_ends(syms: list[str]) -> dict:
    idx = cache.field("close", syms).index
    pm = _perf_mask(idx)
    rows = []
    base = dict(swing_method="fractal_2_1_2", fractal_half_width=2,
                base_min_days=15, base_max_days=65,
                range_metric="(High_k - Low_k) / High_k", forbid_atr_ratio=True,
                first_contraction_max_depth=0.33, decay_coefficient=0.50,
                min_contractions=2, max_contractions=4)
    gate, _ = matrices.vcp_matrices(base, syms)
    g = np.asarray(gate.to_numpy(bool))[pm, :].sum()
    for r in (0.50, 0.55, 0.60):
        duo = matrices._entry_rule_raw(
            {"type": "vcp_volume_duo",
             "params": {"slow_period": 50, "min_day_lookback": 5,
                        "dryup_day_ratio": r, "breakout_vs_slow": None}}, syms)
        d = np.asarray(duo.fillna(False).to_numpy(bool))[pm, :]
        both = np.asarray((gate & duo).fillna(False).to_numpy(bool))[pm, :]
        rows.append({"缩量阈值": r,
                     "缩量门禁单独通过_日×票": int(d.sum()),
                     "几何收缩×缩量_日×票": int(both.sum()),
                     "缩量门禁在几何收缩之上的通过率":
                         round(int(both.sum()) / max(1, int(g)), 4)})
    return {
        "题目": "技-5:原著说「低于 50 日均量 40%~50%」= 缩量比 0.50~0.60。"
                "我们用的 0.60 正好是最宽松那一端。三端各剩多少",
        "原文": 'Minervini 2017 Ch.5【待核实】:"one or two days where volume is '
                '40% to 50% below the 50-day average"',
        "几何收缩门禁单独通过_日×票": int(g),
        "逐端": rows,
        "笔数": "★ 实际成交笔数见 results_1029_技术派六条三版.json —— "
                "那里三端都在剥掉闸门的链和真实链(vcp_momentum)上各跑了一遍",
    }


# ===========================================================================
# ④ 技-14:走带(Walking the Bands)实测
# ===========================================================================

def q4_walking_the_bands(syms: list[str], period: int = 20,
                         k: float = 2.0) -> dict:
    mid, up, lo, pctb, bw = pat6_ops.bollinger(period, k, syms)
    close = cache.field("close", syms)
    idx = close.index
    pm = _perf_mask(idx)
    tag = (close < lo)                                   # 收盘跌破下轨
    ca = close.to_numpy(float)
    ta = np.asarray(tag.fillna(False).to_numpy(bool))
    ma = np.asarray((close > matrices.sma_matrix(200, syms)).fillna(False)
                    .to_numpy(bool))
    ax = np.asarray((pat6_ops.adx(14, syms) > 25.0).fillna(False).to_numpy(bool))

    out = {"题目": "技-14:Bollinger 警告的「走带」—— 触下轨之后继续跌的比例,"
                   "以及连续贴下轨的最长天数分布",
           "原文": 'Bollinger 2001 Ch.12 Rule 4【待核实】:"A tag of the lower '
                   'Bollinger Band is NOT in-and-of-itself a buy signal.";'
                   '他反复警告 Walking the Bands。',
           "口径": f"布林带 {period} 日 / ±{k}σ(原著标准);触轨 = 收盘 < 下轨"}

    # ---- 触轨之后 h 天的涨跌
    fwd = {}
    for h in (1, 3, 5, 10, 20, 60):
        nxt = np.full_like(ca, np.nan)
        nxt[:-h, :] = ca[h:, :]
        r = nxt / ca - 1.0
        sel = ta & pm[:, None] & np.isfinite(r)
        rr = r[sel]
        fwd[f"{h}日"] = {"n": int(rr.size),
                         "★继续下跌的比例": round(float((rr < 0).mean()), 4)
                         if rr.size else None,
                         "中位收益": round(float(np.median(rr)), 5) if rr.size else None,
                         "均值收益": round(float(rr.mean()), 5) if rr.size else None}
    out["触下轨之后的涨跌"] = fwd

    # ---- 连续贴下轨的长度分布(每一段算一次)
    runs = []
    for j in range(ta.shape[1]):
        col = ta[:, j] & pm
        i = 0
        T = len(col)
        while i < T:
            if col[i]:
                s = i
                while i < T and col[i]:
                    i += 1
                runs.append(i - s)
            else:
                i += 1
    runs = np.asarray(runs, dtype=float)
    out["★连续贴下轨天数分布_每段一条"] = _q(runs)
    out["★连续贴下轨天数分布_段数"] = int(runs.size)
    out["连续贴轨 ≥5 天的段数占比"] = (round(float((runs >= 5).mean()), 4)
                                       if runs.size else None)
    out["连续贴轨 ≥10 天的段数占比"] = (round(float((runs >= 10).mean()), 4)
                                        if runs.size else None)
    out["最长一段贴轨天数"] = int(runs.max()) if runs.size else 0

    # ---- 按「行业版那三道趋势过滤器想挡住的环境」切开
    sel = ta & pm[:, None]
    nxt20 = np.full_like(ca, np.nan)
    nxt20[:-20, :] = ca[20:, :]
    r20 = nxt20 / ca - 1.0
    buckets = {
        "在200日线上方 且 ADX≤25(行业版放行的环境)": sel & ma & ~ax,
        "在200日线上方 但 ADX>25(行业版挡住:强趋势)": sel & ma & ax,
        "在200日线下方 且 ADX≤25(行业版挡住:趋势向下)": sel & ~ma & ~ax,
        "在200日线下方 且 ADX>25(行业版挡住:强下跌趋势)": sel & ~ma & ax,
    }
    bb = {}
    for name, msk in buckets.items():
        m2 = msk & np.isfinite(r20)
        rr = r20[m2]
        bb[name] = {"触轨日×票": int(msk.sum()),
                    "占全部触轨": round(float(msk.sum() / max(1, sel.sum())), 4),
                    "20日继续下跌比例": round(float((rr < 0).mean()), 4) if rr.size else None,
                    "20日中位收益": round(float(np.median(rr)), 5) if rr.size else None}
    out["★按环境切开_验证作者的警告"] = bb
    out["怎么读"] = ("「继续下跌比例」接近或高于 50% = 触下轨本身不是买点,"
                     "这是用我们自己的数据复核作者的 Rule 4。"
                     "贴轨段长的尾部(p90 / 最长)就是「走带」。")
    return out


# ===========================================================================
# ⑤ 技-11:Spring 1/2/3 号分流 + 60 日后续表现
# ===========================================================================

def q5_spring_triage(syms: list[str]) -> dict:
    tri = pat6_ops.spring_triage(
        syms, lookback=20, min_age=4, atr_period=14, vol_slow=50,
        micro_pen_pct=0.02, micro_vol_ratio=0.65,
        terminal_pen_pct=0.02, terminal_vol_ratio=1.5)
    close = cache.field("close", syms)
    ca = close.to_numpy(float)
    cols = {s: i for i, s in enumerate(close.columns)}
    idx = close.index
    pm = _perf_mask(idx)

    tri = tri[tri["row"].map(lambda r: bool(pm[r]))].copy()
    fwd = {}
    for h in (20, 60):
        v = []
        for _, r in tri.iterrows():
            i, j = int(r["row"]), cols[r["symbol"]]
            k = i + h
            v.append(ca[k, j] / ca[i, j] - 1.0 if k < len(idx) else np.nan)
        tri[f"fwd{h}"] = v
    rows = []
    for cls, g in tri.groupby("号"):
        d = {"号": cls, "个数": int(len(g)),
             "占比": round(len(g) / max(1, len(tri)), 4),
             "跌破幅度_中位": round(float(g["pen_pct"].median()), 5),
             "量比_中位": round(float(g["vol_ratio"].median()), 4),
             "下刺ATR倍数_中位": round(float(g["dep_atr"].median()), 4)}
        for h in (20, 60):
            a = g[f"fwd{h}"].dropna().to_numpy(float)
            d[f"★{h}日后续_均值"] = round(float(a.mean()), 5) if a.size else None
            d[f"{h}日后续_中位"] = round(float(np.median(a)), 5) if a.size else None
            d[f"{h}日后续_上涨比例"] = round(float((a > 0).mean()), 4) if a.size else None
            d[f"{h}日后续_n"] = int(a.size)
        rows.append(d)
    rows.sort(key=lambda r: r["号"])
    return {
        "题目": "技-11:按下刺深度与量比把信号分成 Spring #1/#2/#3,各多少个、"
                "各自后续表现(20 / 60 日)",
        "母集口径": "跌破前 20 日绝对低点(该低点至少 4 天老)且当日收盘收回到前低之上。"
                    "★ 三号共用同一个母集,所以笔数可比。",
        "★分界是我们定的": "#3 跌破 ≤2% 且 量比 ≤0.65;#1 跌破 >2% 或 量比 ≥1.5;"
                            "#2 其余。★ 这个分界来自专家的散文描述,"
                            "**不是原文给的数** —— 原著(1931 函授课程)三项全未写死。",
        "母集总数": int(len(tri)),
        "逐号": rows,
        "怎么读": "我们现在的实现(liquidity_sweep.yaml)不区分三号 —— "
                  "如果 #1 的后续明显差于 #3,那说明我们一直在「接飞刀」的那部分里下注。",
    }


def q5b_spring_one_factor(syms: list[str]) -> dict:
    """
    ★ ⑤ 的交叉检查:三号分流的分界里混了两个因子(下刺深度 + 量比)。
    这里把两个因子**分开**看,免得把「量大」的效应说成「刺得深」的效应。
    """
    tri = pat6_ops.spring_triage(
        syms, lookback=20, min_age=4, atr_period=14, vol_slow=50,
        micro_pen_pct=0.02, micro_vol_ratio=0.65,
        terminal_pen_pct=0.02, terminal_vol_ratio=1.5)
    close = cache.field("close", syms)
    ca = close.to_numpy(float)
    cols = {s: i for i, s in enumerate(close.columns)}
    idx = close.index
    pm = _perf_mask(idx)
    tri = tri[tri["row"].map(lambda r: bool(pm[r]))].copy()
    v = []
    for _, r in tri.iterrows():
        i, j = int(r["row"]), cols[r["symbol"]]
        k = i + 60
        v.append(ca[k, j] / ca[i, j] - 1.0 if k < len(idx) else np.nan)
    tri["fwd60"] = v

    def _by(col, edges, names):
        rows = []
        for (lo, hi), nm in zip(edges, names):
            g = tri[(tri[col] >= lo) & (tri[col] < hi)]
            a = g["fwd60"].dropna().to_numpy(float)
            rows.append({"档": nm, "个数": int(len(g)),
                         "60日均值": round(float(a.mean()), 5) if a.size else None,
                         "60日中位": round(float(np.median(a)), 5) if a.size else None,
                         "60日上涨比例": round(float((a > 0).mean()), 4) if a.size else None})
        return rows

    return {
        "题目": "⑤ 的交叉检查:把「下刺深度」和「量比」两个因子分开看",
        "为什么要做": "★ ⑤ 里 #1 终极洗盘的中位跌破幅度只有 1.28%,量比中位 1.84 —— "
                      "说明 #1 这一档其实主要是**被量比挑出来的**,不是被深度挑出来的。"
                      "不分开看,就会把「量大」的效应误报成「刺得深」的效应。",
        "按下刺深度分档_pen_pct": _by(
            "pen_pct", [(0, 0.005), (0.005, 0.01), (0.01, 0.02), (0.02, 0.05),
                        (0.05, 1e9)],
            ["<0.5%", "0.5~1%", "1~2%", "2~5%", "≥5%"]),
        "按量比分档_vol_ratio": _by(
            "vol_ratio", [(0, 0.5), (0.5, 0.65), (0.65, 1.0), (1.0, 1.5),
                          (1.5, 1e9)],
            ["<0.50", "0.50~0.65", "0.65~1.00", "1.00~1.50", "≥1.50"]),
        "怎么读": "哪一个因子的分档之间差得更开,后续表现就主要由它决定。",
    }


# ===========================================================================
# ⑥ 技-4:枢纽点 +$0.10 占股价的比例分布
# ===========================================================================

def q6_pivot_ten_cents(syms: list[str]) -> dict:
    p = dict(cup_depth_min=0.15, cup_depth_max=0.33, handle_max_depth=0.12,
             cup_min_bars=35, cup_max_bars=325, handle_min_bars=3,
             handle_max_bars=25, pivot_offset_abs=0.10)
    ev, pv, hh = pat6_ops.cup_with_handle(syms, p)
    idx = ev.index
    pm = _perf_mask(idx)
    close = cache.field("close", syms)

    # ★ 口径一:在**每一个被认出来的杯柄结构**上,0.10 占柄部最高点多少
    #   (不只是成功突破的那些 —— 不然会偏向高价股)
    p0 = dict(p)
    p0["pivot_offset_abs"] = 0.0          # 0 缓冲 → 只要收盘过柄高就算
    ev0, pv0, hh0 = pat6_ops.cup_with_handle(syms, p0)
    a0 = np.asarray(ev0.to_numpy(bool)) & pm[:, None]
    h0 = hh0.to_numpy(float)[a0]
    ratio = 0.10 / h0
    # ★ 口径二:0.10 这道缓冲到底挡掉了多少信号
    a10 = np.asarray(ev.to_numpy(bool)) & pm[:, None]
    n0, n10 = int(a0.sum()), int(a10.sum())

    ca = close.to_numpy(float)
    px = ca[a0]
    bucket = {}
    for lo, hi, name in ((0, 10, "股价 <$10"), (10, 50, "$10~$50"),
                         (50, 100, "$50~$100"), (100, 300, "$100~$300"),
                         (300, 1e9, "≥$300")):
        m = (px >= lo) & (px < hi)
        if m.sum():
            bucket[name] = {"n": int(m.sum()),
                            "0.10占柄高比例_中位": round(float(np.median(ratio[m])), 6),
                            "0.10占柄高比例_均值": round(float(ratio[m].mean()), 6)}
    return {
        "题目": "技-4:原著写死的「枢纽点 = 柄部最高点 +$0.10」在我们池子里"
                "相对股价的占比分布",
        "原文": 'O\'Neil 2009 Ch.2 p.59-66【待核实】:"The proper buy point is '
                '10 cents above the peak of the handle."',
        "★这一条的性质": "「原著对但过时了」—— ★ 单列一类,不要和「我们填错了」混在一起。"
                          "1988/2009 年的票价结构下 10 美分是有意义的缓冲;"
                          "今天同一个绝对数在池子里的实际含义相差几十倍。",
        "被认出的杯柄突破数_无缓冲": n0,
        "被认出的杯柄突破数_加$0.10缓冲": n10,
        "★$0.10 这道缓冲挡掉的信号占比": round(1.0 - n10 / max(1, n0), 4),
        "★0.10/柄部最高点 的分布": _q(ratio),
        "按股价分档": bucket,
        "怎么读": "分布跨度越大,说明这个绝对数在今天越没有统一含义。"
                  "行业版把它改成 +0.1% 的相对缓冲,正是为了修这件事。",
    }


# ===========================================================================

def main() -> int:
    t0 = time.time()
    print(subprocess.run(["free", "-m"], capture_output=True, text=True).stdout)
    pat6_ops.install()
    syms = cache.symbols()
    print(f"池子 {len(syms)} 只;统计窗口 {data.PERF_START} .. {data.PERF_END}")
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                          capture_output=True, text=True).stdout.strip()

    out = {"git_commit": head, "池子只数": len(syms),
           "统计窗口": [data.PERF_START, data.PERF_END]}
    for name, fn in (("①技-6_达瓦斯箱体重叠", q1_darvas_overlap),
                     ("②技-3_周线vs日线信号数", q2_weinstein_weekly_vs_daily),
                     ("③技-5_缩量三端", q3_vcp_dryup_ends),
                     ("④技-14_走带实测", q4_walking_the_bands),
                     ("⑤技-11_Spring分流", q5_spring_triage),
                     ("⑤b技-11_Spring单因子交叉检查", q5b_spring_one_factor),
                     ("⑥技-4_枢纽点10美分", q6_pivot_ten_cents)):
        t = time.time()
        print(f"\n跑 {name} ...")
        out[name] = fn(syms)
        print(f"  用了 {time.time()-t:.1f} 秒;"
              f"RSS {resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024:.0f} MB")
        print(json.dumps(out[name], ensure_ascii=False, indent=1)[:2600])

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n写好 {OUT_JSON}(总共 {time.time()-t0:.0f} 秒)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
