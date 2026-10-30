"""
A0 十二条里的两条状态判定 —— 状-4 威科夫区间结构 / 状-6 共振计数。

大白话:这两条**不产生交易信号**,所以不回测、不出收益、不出胜率 ——
出收益就是编。它们只回答「现在是什么状态」,所以产出是分布统计。

  状-4:五类结构事件各出现多少次、分布是否合理
  状-6:共振分数 0-6 的分布;校准目标 = 「平均共振强度不应普遍 ≥ 4」
        (手册第 465 行 + 附录 D.9 验证一)

★ 两条都有「手册没写死」的地方,全部在各自 yaml 的注释里逐条列明,
  并在本脚本的输出里带上 待回去问 字段。★ 没有自己拍数:
  凡是必须选一个读法的地方,都把**两种/三种读法并列跑出来**,
  让这个选择的影响看得见。

跑法:python3 -m engine.run_a0_states

★★ 2026-10-29 跑出那份结果的口径备注（重跑前必读）：
  本脚本第一次出结果是 12:26:07 启动的进程，读的是 11:28:11 构建的 parquet 缓存。
  ★ 跑完之后，拆股比例改读源头 split_coefficient 的根因修复（1b6b28e，12:50:12）
    落地，并于 12:52:17 重建了缓存 —— 所以**现在重跑会得到不同的数字**。
  ★ 已实测影响面：214 / 11144 笔 = 1.92%，涉及 ACOR / AMRS / PROP / PRTY /
    SQBG / UHAL / WPG / TSLA。其中两处余量极薄、必须重跑才能确认：
      · 技-12 RSI<10 是唯一过了四格硬关的版本，最弱格差值只有 +0.0005，受影响 56 笔
      · 技-2 法伯最弱格差值 −0.0014，受影响 40 笔
  ★ 旧口径的原件在 1b6b28e 的 results_1029_A0* .json 与 ledgers_1029_A0十二条/ 里，
    要复现得先 `git checkout da10a76 -- engine/data.py engine/split_gate.py` 再重建缓存。
"""

from __future__ import annotations

import json
import os
import time

import numpy as np
import pandas as pd

from . import cache, data, matrices, stages

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "results_1029_A0状态两条_新拆股口径.json")

#: 状-6 的评估日 —— 取绩效窗口内每个日历月的最后一个交易日。
#   ★ 为什么不是每一天:共振计数是「此刻哪些价位重要」的快照,
#     相邻交易日的价位列表高度重叠,逐日统计等于把同一个观测数几百遍,
#     会把分布的标准误假性缩小。★ 月末抽样是执行细节,已标明。
EVAL_FREQ = "月末"

#: 手册给死的:均线取 20/50/150/200 日;斐波那契取 0.382/0.5/0.618;MACD 12/26/9
MA_SET = (20, 50, 150, 200)
FIB_SET = (0.382, 0.5, 0.618)


# ===========================================================================
# 状-1 的摆动点 —— 状-4 和 状-6 都要用它,而它的参数在附录 D.8 里是「待校准」
# ===========================================================================

def zigzag_pivots(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                  atr: np.ndarray, k: float = 3.0,
                  use_wick: bool = True) -> list[tuple[int, str, float]]:
    """
    状-1 的 ZigZag 摆动点。

    ★★ 附录 D.8 把这一条标为「待校准」,而且有**两处**:
      一、ZigZag 阈值 3 × ATR(14) —— 一个待校准的数
      二、「摆动点取影线还是收盘」 —— ★ 这不是一个待校准的数,
          是一个**还没做的定义选择**。取影线和取收盘会得出不同的摆动点,
          进而得出不同的区间边界、不同的事件计数、不同的斐波那契锚点。
    ★ 所以 use_wick 两个取值都要跑,不许只跑一个。

    ══════════════════════════════════════════════════════════════════════
    ★★★ 2026-10-30 修一个**静默失败**:k ≥ 6 时整函数返回空列表
    ══════════════════════════════════════════════════════════════════════
    症状(实测 299 只票 / 2016-01-04 起 / use_wick=True):
        k=4 → 11.7% 的票得 0 个摆动点
        k=5 → 42.1%      k=6 → 70.9%      k=8 → 92.6%      k=12 → 98.7%

    ★★★ 病根(**只在 bootstrap 那一段**,方向还没定的时候):
      原来写的是 `if direction >= 0:` 和 `if direction <= 0:` 两个**独立**的 if,
      ★ 于是 `direction == 0` 时**两段在同一根 bar 里都执行**:
          第一段把 ext_v 往上记成当根最高价,
        ★★ 第二段紧接着又把 ext_v 覆盖成当根**最低价**(lo < ext_v 几乎恒成立)。
      ★★★ 跟踪极值被**每根 bar 重置一次** → 跳出条件退化成
           「**单根 bar 振幅 ≥ k × ATR**」。
      ★ 而方向一直定不下来,所以整条序列一个摆动点都出不来。

    ★★ 直接证据(两条曲线重合,不是推理):
        「单根 bar 振幅 ≥ k×ATR」的天数占比(中位)
          k=2 → 2.3866%   k=3 → 0.3182%   k=4 → 0.0398%
          k=5 → 0.0000%   k=6 → 0.0000%   ……
      ★ 失败率在 k=4 起飞、k=6 过七成,和上面这条概率曲线**同一个 k 上塌**。

    ★ 修法:方向未定时**同时**记住跑到过的最高和最低(两个独立的游标),
      谁先满足 k×ATR 的反转就定方向。★★ 方向定了之后的逻辑、严格交替、
      取更极端 —— ★ 一个字都没改。出处:probe/snapshot_features_1030/
      zigzag_bug_1030.py 的 `zz_fixed()`(本函数在它基础上补回 use_wick 和 NaN 保护)。

    ★★★ 顺带一条待办的处置:附录 D.8 的「ZigZag 阈值 3×ATR 待校准」
      —— ★ 在修好之前这件事**根本做不了**:往上调阈值,所有下游判据会
      **静默**变成 0 个事件,看起来像「这个阈值很严格」,实际是函数坏了。
      修好之后才第一次可校准。
    """
    hi_src = high if use_wick else close
    lo_src = low if use_wick else close
    n = len(close)
    piv: list[tuple[int, str, float]] = []
    # 方向未定时先找第一个够大的摆动
    direction = 0            # +1 = 正在找高点, -1 = 正在找低点
    # ★★ bootstrap 的两个**独立**游标 —— 这就是修好的那一处。
    #   ★ 不能共用一个 ext_v:共用就会被对侧分支每根 bar 覆盖掉(见上面病根)。
    hi_i, hi_v = 0, hi_src[0] if np.isfinite(hi_src[0]) else np.nan
    lo_i, lo_v = 0, lo_src[0] if np.isfinite(lo_src[0]) else np.nan
    ext_i, ext_v = 0, close[0] if np.isfinite(close[0]) else np.nan
    for i in range(1, n):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        thr = k * a
        h, lo = hi_src[i], lo_src[i]
        if not (np.isfinite(h) and np.isfinite(lo)):
            continue
        if direction == 0:
            # ★ NaN 保护:第一根有效 bar 直接把两个游标坐实(原版靠
            #   `if not np.isfinite(ext_v)` 那一行兜底,这里按游标各兜一次)
            if not np.isfinite(hi_v) or h > hi_v:
                hi_i, hi_v = i, h
            if not np.isfinite(lo_v) or lo < lo_v:
                lo_i, lo_v = i, lo
            # ★ hi_i < i / lo_i < i:摆动点必须在**之前**的某根 bar 上,
            #   不许拿当根 bar 自己的高低差当一个反转(那正是旧版的退化形态)
            if (hi_v - lo) >= thr and hi_i < i:
                piv.append((hi_i, "H", float(hi_v)))
                direction, ext_i, ext_v = -1, i, lo
            elif (h - lo_v) >= thr and lo_i < i:
                piv.append((lo_i, "L", float(lo_v)))
                direction, ext_i, ext_v = 1, i, h
            continue
        if direction > 0:
            if not np.isfinite(ext_v) or h > ext_v:
                ext_i, ext_v = i, h
            if (ext_v - lo) >= thr:
                piv.append((ext_i, "H", float(ext_v)))
                direction, ext_i, ext_v = -1, i, lo
        else:
            if not np.isfinite(ext_v) or lo < ext_v:
                ext_i, ext_v = i, lo
            if (h - ext_v) >= thr:
                piv.append((ext_i, "L", float(ext_v)))
                direction, ext_i, ext_v = 1, i, h
    # 严格交替(同类连续时保留更极端的)
    out: list[tuple[int, str, float]] = []
    for p in piv:
        if out and out[-1][1] == p[1]:
            keep = p if ((p[1] == "H" and p[2] > out[-1][2]) or
                         (p[1] == "L" and p[2] < out[-1][2])) else out[-1]
            out[-1] = keep
        else:
            out.append(p)
    return out


# ===========================================================================
# 状-4 · 威科夫区间结构
# ===========================================================================

# ===========================================================================
# 每只票的基础量 —— 算一次,六种读法共用
#   ★ 为什么要这一层:状-4 和 状-6 各要跑 6 种读法(摆动点 2 种 × 容差 3 档)。
#     不缓存的话 load_daily / ATR / 均线 / MACD / stages 会被重算 6 遍,
#     而这些量和读法无关。★ 只有 ZigZag 摆动点和 use_wick 有关,单独缓存。
# ===========================================================================

_BASE: dict[str, dict] = {}
_PIV: dict[tuple[str, bool], list] = {}


def base_of(sym: str) -> dict | None:
    if sym in _BASE:
        return _BASE[sym]
    df = data.load_daily(sym)
    if df.empty or len(df) < 260:
        _BASE[sym] = None
        return None
    close = df["close"].to_numpy(float)
    high = df["high"].to_numpy(float)
    low = df["low"].to_numpy(float)
    vol = df["volume"].to_numpy(float)
    idx = df.index
    prev = np.concatenate([[np.nan], close[:-1]])
    tr = np.maximum.reduce([high - low, np.abs(high - prev), np.abs(low - prev)])
    atr = matrices._wilder(pd.DataFrame({"x": pd.Series(tr, index=idx)}),
                           14)["x"].to_numpy(float)
    ser = pd.Series(close, index=idx)
    mas = {m: ser.rolling(m, min_periods=m).mean().to_numpy(float) for m in MA_SET}
    ema12 = ser.ewm(span=12, adjust=False).mean()
    ema26 = ser.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    hist = (macd - macd.ewm(span=9, adjust=False).mean()).to_numpy(float)
    st = stages.stage_series(df[["close"]]).to_numpy(object)
    per = idx.to_period("M")
    is_me = np.empty(len(idx), dtype=bool)
    is_me[:-1] = per[1:] != per[:-1]
    is_me[-1] = True
    in_perf = np.asarray((idx >= pd.Timestamp(data.PERF_START)) &
                         (idx <= pd.Timestamp(data.PERF_END)), dtype=bool)
    _BASE[sym] = {"idx": idx, "close": close, "high": high, "low": low,
                  "vol": vol, "atr": atr, "mas": mas, "hist": hist,
                  "stage": st, "is_me": is_me, "in_perf": in_perf,
                  "chop": (st == stages.CHOP)}
    return _BASE[sym]


def piv_of(sym: str, use_wick: bool) -> list:
    key = (sym, use_wick)
    if key not in _PIV:
        b = base_of(sym)
        _PIV[key] = [] if b is None else zigzag_pivots(
            b["high"], b["low"], b["close"], b["atr"], k=3.0, use_wick=use_wick)
    return _PIV[key]


#: 五类事件 —— 手册原文的名字,一字不改
WYCKOFF_EVENTS = ("下刺收回", "上冲回落", "低点抬高", "触及未破", "缩量测试")

#: ★「触及未破」需要一个「多近算触及」的容差,★ 手册没给这个数。
#   本次并列跑三档,让这个选择的影响看得见。
#   ★ 不许借用 状-6 的 ±0.5×ATR(14) 顶上 —— 那是另一条的参数,
#     跨条目搬过来就等于我们自己定了一个数还假托有出处。
TOUCH_TOL_GRID = (0.25, 0.50, 1.00)


def wyckoff_events_one(sym: str, use_wick: bool, touch_tol: float) -> dict:
    """ååªç¥¨ï¼å¨ãéè¡ãåºé´åæ°äºç±»ç»æäºä»¶ã"""
    b = base_of(sym)
    if b is None:
        return {}
    close, high, low = b["close"], b["high"], b["low"]
    vol, atr, chop = b["vol"], b["atr"], b["chop"]
    perf_mask = b["in_perf"]
    piv = piv_of(sym, use_wick)
    piv_i = np.array([p[0] for p in piv], dtype=int)

    counts = {e: 0 for e in WYCKOFF_EVENTS}
    vol_q = {e: [] for e in WYCKOFF_EVENTS}
    ranges = 0
    i = 0
    while i < len(chop):
        if not chop[i]:
            i += 1
            continue
        j = i
        while j + 1 < len(chop) and chop[j + 1]:
            j += 1
        # åºé´ [i, j]ãâ è¾¹çæ¥èª ç¶-1 çæå¨ç¹ï¼æåï¼åºé´è¾¹çæ¥èªç¶-1 çæå¨ç¹ï¼
        inside = [p for p in piv if i <= p[0] <= j]
        if len(inside) >= 2 and perf_mask[i:j + 1].any():
            ranges += 1
            floor = float(np.nanmin([p[2] for p in inside]))
            ceil = float(np.nanmax([p[2] for p in inside]))
            piv_at = {p[0]: p for p in inside}
            last_touch_vol = None
            prev_piv_low = None
            for t in range(i, j + 1):
                if not perf_mask[t]:
                    continue
                a = atr[t]
                if not np.isfinite(a) or a <= 0:
                    continue
                w = vol[max(0, t - 19):t + 1]
                vq = float(np.nanmean(w <= vol[t])) if np.isfinite(vol[t]) else np.nan
                # â  ä¸åºæ¶åï¼æä½ä»·ç ´åºæ²¿ãæ¶çæ¶åå°åºæ²¿ä¹ä¸
                #   â æååãéè¦æ¥åæ°æ®å¤æ­ãä¸åºå½å¤©æ¶åããââ
                #     æä»¬åªææ¥çº¿ï¼ç¨ãå½æ¥æä½ç ´ãå½æ¥æ¶çåãè¿ä¸ªæ¥çº¿è¯»æ³ã
                if low[t] < floor and close[t] > floor:
                    counts["下刺收回"] += 1
                    vol_q["下刺收回"].append(vq)
                # â¡ ä¸å²åè½
                if high[t] > ceil and close[t] < ceil:
                    counts["上冲回落"] += 1
                    vol_q["上冲回落"].append(vq)
                # â¢ ä½ç¹æ¬é«ï¼æå¨ä½ç¹æ¯åä¸ä¸ªæå¨ä½ç¹é«
                p = piv_at.get(t)
                if p is not None and p[1] == "L":
                    if prev_piv_low is not None and p[2] > prev_piv_low:
                        counts["低点抬高"] += 1
                        vol_q["低点抬高"].append(vq)
                    prev_piv_low = p[2]
                # â£ è§¦åæªç ´ï¼æä½ä»·è¿å°åºæ²¿ä¸æ¹ touch_tolÃATR ä¹åï¼ä½æ²¡ç ´
                if floor <= low[t] <= floor + touch_tol * a:
                    counts["触及未破"] += 1
                    vol_q["触及未破"].append(vq)
                    # â¤ ç¼©éæµè¯ = è§¦åæªç ´ï¼ä¸æäº¤éä½äº**åæ¬¡åç±»äºä»¶**
                    #    â è¿ä¸ªå®ä¹æ¯æååæç»æ­»çï¼ä¸æ¯æä»¬å®ç
                    if last_touch_vol is not None and vol[t] < last_touch_vol:
                        counts["缩量测试"] += 1
                        vol_q["缩量测试"].append(vq)
                    last_touch_vol = vol[t]
        i = j + 1
    return {"事件计数": counts, "震荡区间数": ranges,
            "各类事件的当日成交量分位均值":
                {e: (float(np.nanmean(v)) if len(v) else None)
                 for e, v in vol_q.items()}}


def run_wyckoff(syms: list[str]) -> dict:
    out = {
        "条目": "状-4 · 威科夫区间结构",
        "口径": ("不回测 —— 本条不产生交易信号。只数五类结构事件并看分布。"
                 "区间 = stages.py 的 CHOP(震荡)连续段;"
                 "区间边界 = 该段内 状-1 摆动点的最低/最高(手册:区间边界来自状-1 的摆动点)。"),
        "手册锁死的边界": ("不输出 吸筹/派发/洗牌/主力 中的任何一个;"
                           "附录 D.6 在数据契约层禁掉了 phase 字段 —— 本产出里没有这类标签。"),
        "要回去问": [
            "★ 区间边界依赖 状-1,而 状-1 在附录 D.8 里是「待校准」,"
            "且其中「摆动点取影线还是收盘」是一个**还没做的定义选择**,不是一个数。"
            "→ 本次两种读法并列跑。",
            "★「触及未破」需要「多近算触及」的容差,手册没给 → 本次三档并列跑。"
            "★ 没有借用 状-6 的 ±0.5×ATR(14) 顶上。",
            "★ 手册写「需要日内数据判断『下刺当天收回』」,我们只有日线 —— "
            "本次用日线读法(当日最低破、当日收盘回)。这是能力缺口,不是参数缺口。",
        ],
        "各读法": [],
    }
    for use_wick in (True, False):
        for tol in TOUCH_TOL_GRID:
            t0 = time.time()
            tot = {e: 0 for e in WYCKOFF_EVENTS}
            ranges = 0
            vq_acc = {e: [] for e in WYCKOFF_EVENTS}
            nsym = 0
            for s in syms:
                r = wyckoff_events_one(s, use_wick, tol)
                if not r:
                    continue
                nsym += 1
                ranges += r["震荡区间数"]
                for e in WYCKOFF_EVENTS:
                    tot[e] += r["事件计数"][e]
                    v = r["各类事件的当日成交量分位均值"][e]
                    if v is not None:
                        vq_acc[e].append(v)
            n_ev = sum(tot.values())
            out["各读法"].append({
                "摆动点取": "影线(high/low)" if use_wick else "收盘(close)",
                "触及未破容差": f"{tol} × ATR(14)",
                "覆盖票数": nsym,
                "震荡区间数": ranges,
                "五类事件计数": tot,
                "事件总数": n_ev,
                "各类占比": {e: (round(tot[e] / n_ev, 4) if n_ev else None)
                              for e in WYCKOFF_EVENTS},
                "每个震荡区间平均事件数": (round(n_ev / ranges, 2) if ranges else None),
                "各类事件的当日成交量分位均值":
                    {e: (round(float(np.mean(v)), 4) if v else None)
                     for e, v in vq_acc.items()},
                "耗时秒": round(time.time() - t0, 1),
            })
            print(f"  状-4 摆动点={'影线' if use_wick else '收盘'} 容差={tol}: "
                  f"区间 {ranges} 个,事件 {n_ev} 个 {tot}")
    return out


# ===========================================================================
# 状-6 · 共振计数
# ===========================================================================

#: 六类来源 —— 手册原文的名字
CONFLUENCE_SOURCES = ("成交密集区", "前高前低", "均线", "整数关口",
                      "斐波那契回撤", "状态匹配的背离")

#: ★ 容差 ±0.5×ATR(14) 在附录 D.8 里就是「待校准」,而手册自己说「容差决定一切」。
#   → 三档并列跑,把「容差决定一切」这句话量化出来。
TOL_GRID = (0.25, 0.50, 1.00)

# ★ MA_SET / FIB_SET 的定义已上提到文件头的常量区(base_of 要用)。


def _round_levels(px: float) -> list[float]:
    """
    「整数关口」—— ★ 手册没给粒度($10 / $5 / $1 / 还是按量级?)。
    本次读法:按价格量级取「一位有效数字」的整数关口
      px<10 → 每 1 元;10..100 → 每 10 元;100..1000 → 每 100 元 …
    ★ 这是我们定的读法,不是原著。
    """
    if not np.isfinite(px) or px <= 0:
        return []
    step = 10.0 ** np.floor(np.log10(px))
    base = np.floor(px / step) * step
    return [float(base), float(base + step)]


def confluence_one(sym: str, tol_k: float, use_wick: bool) -> list[int]:
    """单只票:在每个评估日算一次共振计数,返回所有价位的 0-6 分数列表。"""
    b = base_of(sym)
    if b is None:
        return []
    close, high, low, vol = b["close"], b["high"], b["low"], b["vol"]
    atr, mas, hist, st = b["atr"], b["mas"], b["hist"], b["stage"]
    piv = piv_of(sym, use_wick)
    # 评估日 = 绩效窗口内每个日历月的最后一个交易日
    eval_i = np.flatnonzero(b["is_me"] & b["in_perf"])

    scores: list[int] = []
    for t in eval_i:
        a = atr[t]
        px = close[t]
        if not (np.isfinite(a) and a > 0 and np.isfinite(px)):
            continue
        tol = tol_k * a
        src: dict[str, list[float]] = {s: [] for s in CONFLUENCE_SOURCES}

        # ① 成交密集区:★ 手册没给定义。本次读法 = 过去 252 根按收盘价分箱
        #   (箱宽 = 1×ATR14)累加成交量,取量最大的 3 个箱的箱心。
        #   ★ 箱宽和「前 3 个」都是我们定的,不是原著。
        w0 = max(0, t - 251)
        cw, vw = close[w0:t + 1], vol[w0:t + 1]
        ok = np.isfinite(cw) & np.isfinite(vw)
        if ok.sum() > 30:
            lo_e, hi_e = np.nanmin(cw[ok]), np.nanmax(cw[ok])
            if hi_e > lo_e:
                nb = max(3, int(np.ceil((hi_e - lo_e) / a)))
                edges = np.linspace(lo_e, hi_e, nb + 1)
                which = np.clip(np.digitize(cw[ok], edges) - 1, 0, nb - 1)
                agg = np.zeros(nb)
                np.add.at(agg, which, vw[ok])
                top = np.argsort(agg)[-3:]
                src["成交密集区"] = [float((edges[b] + edges[b + 1]) / 2) for b in top]

        # ② 前高前低:最近 6 个摆动点
        recent = [p for p in piv if p[0] < t][-6:]
        src["前高前低"] = [float(p[2]) for p in recent]

        # ③ 均线:20/50/150/200(手册给死)
        src["均线"] = [float(mas[m][t]) for m in MA_SET
                       if np.isfinite(mas[m][t])]

        # ④ 整数关口
        src["整数关口"] = _round_levels(px)

        # ⑤ 斐波那契回撤 0.382/0.5/0.618(手册给死);★ 锚定哪一段手册没给,
        #    本次用「最近一对相邻的摆动高/低」。★ 这个锚是我们定的。
        if len(recent) >= 2:
            p1, p2 = recent[-2], recent[-1]
            hi_p, lo_p = max(p1[2], p2[2]), min(p1[2], p2[2])
            if hi_p > lo_p:
                src["斐波那契回撤"] = [float(hi_p - f * (hi_p - lo_p))
                                        for f in FIB_SET]

        # ⑥ 状态匹配的背离(手册锁死的条件化规则):
        #    上涨状态只计底背离、下跌状态只计顶背离、震荡两者都计、
        #    过渡或混合状态两者都不计。★ 背离只是来源,不是触发器。
        stg = st[t]
        allow_bot = stg in (stages.STAGE_2, stages.BULL_PULLBACK, stages.CHOP)
        allow_top = stg in (stages.STAGE_4, stages.BEAR_RALLY, stages.CHOP)
        if stg not in (stages.STAGE_WARMUP,):
            lv: list[float] = []
            for p in recent:
                k0 = p[0]
                if not np.isfinite(hist[k0]):
                    continue
                if p[1] == "L" and allow_bot and hist[k0] > 0:
                    lv.append(float(p[2]))       # 价格新低 + 柱状图转正 = 底背离
                if p[1] == "H" and allow_top and hist[k0] < 0:
                    lv.append(float(p[2]))       # 价格新高 + 柱状图转负 = 顶背离
            src["状态匹配的背离"] = lv

        # 候选价位 = 六类来源的并集;每个候选价位数「有几类来源落在容差内」
        cand = [v for vs in src.values() for v in vs if np.isfinite(v)]
        for L in cand:
            c = 0
            for s in CONFLUENCE_SOURCES:
                if any(abs(v - L) <= tol for v in src[s] if np.isfinite(v)):
                    c += 1
            scores.append(int(c))
    return scores


def run_confluence(syms: list[str]) -> dict:
    out = {
        "条目": "状-6 · 共振计数",
        "口径": (f"不回测 —— 本条不产生交易信号。只出 0-6 分数的分布。"
                 f"评估日 = 绩效窗口内每个日历月的最后一个交易日({EVAL_FREQ}抽样)。"
                 f"★ 为什么不逐日:相邻交易日的价位列表高度重叠,逐日统计等于"
                 f"把同一个观测数几百遍,会把分布的标准误假性缩小。"),
        "校准目标": "平均共振强度不应普遍 ≥ 4(手册第 465 行 + 附录 D.9 验证一)",
        "手册给死的参数": "均线 20/50/150/200;斐波那契 0.382/0.5/0.618;MACD 12/26/9;背离条件化",
        "手册锁死的边界": ("不说这个价位会守住;背离只是来源不是触发器;"
                           "不加任何指数衰减的新鲜度权重(附录 D.6)—— "
                           "分数保持 0-6 整数、可数可追溯。"),
        "要回去问": [
            "★ 容差 ±0.5×ATR(14) 在附录 D.8 里就是「待校准」,而手册自己说"
            "「容差决定一切」—— 所以 状-6 从定义上就不该被归进「原著完整、不需要补阈值」。"
            "→ 本次 0.25 / 0.5 / 1.0 三档并列跑。",
            "★「成交密集区」没有定义。本次读法 = 过去 252 根按收盘价分箱"
            "(箱宽 1×ATR14)累加成交量取前 3 个箱 —— ★ 箱宽和「前 3」都是我们定的。",
            "★「整数关口」粒度没给。本次读法 = 按价格量级取一位有效数字 —— ★ 我们定的。",
            "★ 斐波那契锚定哪一段摆动没给;且它依赖 状-1,而 状-1 待校准。",
        ],
        "各读法": [],
    }
    for use_wick in (True, False):
        for tol in TOL_GRID:
            t0 = time.time()
            allsc: list[int] = []
            for s in syms:
                allsc.extend(confluence_one(s, tol, use_wick))
            arr = np.array(allsc, dtype=int)
            if arr.size == 0:
                continue
            dist = {str(k): int((arr == k).sum()) for k in range(7)}
            frac = {str(k): round(float((arr == k).mean()), 4) for k in range(7)}
            mean = float(arr.mean())
            ge4 = float((arr >= 4).mean())
            out["各读法"].append({
                "摆动点取": "影线(high/low)" if use_wick else "收盘(close)",
                "容差": f"±{tol} × ATR(14)",
                "价位样本数": int(arr.size),
                "0-6分布_计数": dist,
                "0-6分布_占比": frac,
                "平均共振强度": round(mean, 4),
                "中位数": float(np.median(arr)),
                "★≥4的占比": round(ge4, 4),
                "★校准目标是否达到": (
                    "达到(平均 < 4)" if mean < 4.0
                    else "★ 没达到:平均共振强度 ≥ 4,按手册这个指标已失去区分度"),
                "耗时秒": round(time.time() - t0, 1),
            })
            print(f"  状-6 摆动点={'影线' if use_wick else '收盘'} 容差=±{tol}ATR: "
                  f"n={arr.size} 均值={mean:.3f} ≥4占比={ge4:.1%} 分布={frac}")
    return out


def main(argv=None) -> int:
    print(data.cohort_report())
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    print(f"\n全池 {len(syms)} 只,绩效窗口 {data.PERF_START} .. {data.PERF_END}\n")
    out = {
        "跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "全池只数": len(syms),
        "绩效窗口": f"{data.PERF_START} .. {data.PERF_END}(2016 起热机)",
        "★为什么不回测": ("状-4 和 状-6 都是状态判定,不给进场点、不给止损、不给仓位。"
                          "对它们跑回测会凭空造出一个它们没有的东西 —— "
                          "所以本脚本只出分布统计,不出任何收益或胜率数字。"),
    }
    print("状-4 · 威科夫区间结构")
    out["状-4"] = run_wyckoff(syms)
    print("状-6 · 共振计数")
    out["状-6"] = run_confluence(syms)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
    print(f"\n原始数字已写:{OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
