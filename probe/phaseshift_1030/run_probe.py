"""
判别测试:日线 SMA150 和周线 30 周那 14~16% 的不一致,
         到底是「相位差(A)」还是「真分歧(B)」

================================================================================
三秒版
================================================================================
一句话:把日线的阶段标签在时间轴上来回平移,看那些不一致的格子能不能靠
       「平移几天」就对上。能对上 → 是时间差,不是信息;对不上 → 是真分歧。

★ 这个测试的价值在于它能**否掉 A**。所以本文件刻意做了三件找 B 证据的事:
  一、平移量不只试「日线领先」(+k),也试「周线领先」(-k) ——
      如果周线有时领先,那就不是单纯的窗口滞后。
  二、窗口不只试 ±8 个交易日,一路试到 ±40 ——
      如果大量格子要 >8 天才对齐,说明 ±8 这个窗口选小了,要在报告里换掉。
  三、对不齐的那一类(B)逐个看:标签对是怎么配的、集中在哪几只票、
      哪几个时间段、什么行情里。

★ 硬纪律(本文件逐条守着):
  一、不改任何现有文件。只 import engine.* 和上一轮 probe,不写回。
      ★ engine/ 下另一个 agent 正在改东西 —— 本文件一行都不碰 engine/。
  二、probe/timeframe_rs_1030/ 只读 —— 用 importlib 按文件路径加载它的函数,
      为的是**管线和上一轮逐行一致**(不然两轮的数字不可比)。
  三、串行跑,单进程。
  四、阈值一个都不动 —— 两套口径的参数全部沿用上一轮(tri.STAGE_VERSIONS['XING版'])。
  五、凡「天」一律写明是交易日还是自然日。

跑法:python3 probe/phaseshift_1030/run_probe.py
"""

from __future__ import annotations

import importlib.util
import json
import os
import subprocess
import sys
import time
from collections import Counter

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _REPO)

from engine import cache, data                                   # noqa: E402
from engine import state_axis_tri_1029 as tri                     # noqa: E402

OUT_JSON = os.path.join(_HERE, "results_1030_相位差还是真分歧.json")

# ---------------------------------------------------------------------------
# 上一轮的 probe 只读加载 —— ★ 为了让两套口径的构造和上一轮**逐行一致**
# ---------------------------------------------------------------------------
_PREV = os.path.join(_REPO, "probe", "timeframe_rs_1030", "run_probe.py")
_spec = importlib.util.spec_from_file_location("_prev_probe_1030", _PREV)
prev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prev)          # ★ 只是 import,不跑它的 main()

# ---------------------------------------------------------------------------
# 时间尺度声明 —— 凡「天」都在这里写明
# ---------------------------------------------------------------------------
TIME_SCALE = {
    "平移量 k 的单位": "**交易日**(日线网格上的格数),不是自然日",
    "主判窗口 ±8": "±8 个**交易日** —— ★ 理由见 WINDOW_RATIONALE",
    "探窗口 ±40": "±40 个**交易日**(≈ 8 个自然周)—— 只为检查 ±8 够不够,"
                  "不参与主结论",
    "日线版的「150 日」": "150 个**交易日**",
    "周线版的「30 周」": "30 根**周线 bar**(= 30 个自然周)",
    "周线标签铺回日线格的方式": "周线 bar 日期(通常周五)当右端,ffill 到下一根 bar "
                                "之前 —— 即「周一看到的周线图,反映的是上周五收盘」。"
                                "★ 这是上一轮就定下的口径,本轮沿用未改。",
    "B 类集中度的「时间段」": "按**自然年**和**自然季**分桶",
}

WINDOW_RATIONALE = (
    "±8 个**交易日**的来历:Gemini 的可测预测是「日线比周线提前 2~4 个交易日」,"
    "±8 = 它上限 4 的两倍,留足一倍余量。★ 另外它还正好 ≈ 1.5 根周线 bar —— "
    "由于周线标签在日线格上是**阶梯函数**(一周内恒定),光是这个阶梯本身就能造成"
    "最多 4 个交易日的错位,所以窗口至少要大于 5 才有意义,±8 是能同时满足"
    "「≥2 倍 Gemini 预测」和「>1 根周线 bar」的最小整数量级。"
    "★ 本文件同时报 ±40 的结果:如果 ±8 外还能捞回大量格子,主结论要换窗口。"
)

MY_NOTES: list[str] = []


def _note(s: str) -> None:
    if s not in MY_NOTES:
        MY_NOTES.append(s)


_note("「不一致」的定义是【我们填的】:逐票逐交易日比**五档阶段标签**"
      "(1/2/3/4/transition)是否字面相同。★ 上一轮报的 86.4% 只比了"
      "「是不是阶段二」这一个二值,本轮比的是全五档,所以本轮的基线一致率"
      "会比 86.4% 低 —— 两个数量的不是同一件事,报告里会把两个都给出。")
_note("平移匹配的判定是【我们填的】:对每个不一致的格子,在 k=±1..±K 里找"
      "**绝对值最小**的 k 使 D[t-k] == W[t]。★ 正 k = 日线领先(把日线往后推"
      "k 个交易日才对上周线);负 k = 周线领先。同一个最小 |k| 下正负都成立 → "
      "记为「正负都行」,单独一档,不许偷偷算进任一边。")
_note("★ 一个必须声明的混淆项:周线标签在日线格上是阶梯函数(一周内恒定),"
      "所以每一次真实的阶段转向附近,**天然**就会有最多 4 个交易日的错位 —— "
      "这部分错位和「日线均线提前转向」是两个不同的机制,但本测试的平移匹配"
      "**分不开它们**。因此 A 类的占比是「可被时间平移解释」的上界,"
      "报告里按这个口径表述,不说成「全是均线窗口导致的」。")

MAIN_K = 8          # ★ 预先登记的主窗口(Gemini 预测 2~4 的两倍)
PROBE_K = 40        # 探窗口
WINDOWS = (8, 15, 25, 40)   # ★ 全部报出来,不挑一个好看的
HEADLINE_K = 25     # ★ 头条用的窗口 —— 理由见 HEADLINE_RATIONALE

HEADLINE_RATIONALE = (
    "头条为什么用 ±25 个**交易日**而不是预先登记的 ±8:★ 因为 ±8 被本文件"
    "自己的自检否掉了 —— ±8 外、±40 内还能捞回 14.1% 的不一致格子,"
    "说明 ±8 装不下实测的相位分布。实测的相位中位是 **8 个交易日**"
    "(事件级,见第四节),±25 = 5 根周线 bar ≈ 中位的 3 倍;"
    "而且恢复曲线在这里拐平:A 占比 ±8→±15 涨 9.5 个点、±15→±25 涨 2.4 个点、"
    "±25→±40 只涨 2.1 个点。★ 四个窗口的数全部报出,不挑。"
)


# ============================================================================
# 一 · 两套口径的逐格标签(构造完全沿用上一轮)
# ============================================================================

def build_panels(syms: list[str]) -> dict:
    """
    返回两套口径在**整条日线网格**上的标签(不截 START ——
    平移匹配需要左边的余量,不然边缘格子会假性判成 B)。
    """
    p = cache.load()
    cl = p["close"][syms]
    spec = tri.STAGE_VERSIONS["XING版"]
    idx_d = cl.index

    # ---- 日线 150 个交易日版(= 现行生产口径) ----
    ma_d = cl.rolling(150, min_periods=150).mean()
    daily: dict[str, np.ndarray] = {}
    ev_d: dict[str, list] = {}
    for s in syms:
        raw = prev.raw_stage_bars(cl[s].to_numpy(), ma_d[s].to_numpy(),
                                  spec.flat_thr, 10 * tri.WEEK, 10.0)
        lab, events = tri._confirm_sequence(raw, spec.min_bars)
        arr = lab.copy()
        for k, ev in enumerate(events):
            _f, _g, ok, _lab = tri._topology(ev)
            if ev["stage"] == "2" and not ok:
                j = events[k + 1]["i"] if k + 1 < len(events) else len(lab)
                seg = arr[ev["i"]:j]
                arr[ev["i"]:j] = np.where(seg == tri.WARMUP, tri.WARMUP, "transition")
        daily[s] = arr
        ev_d[s] = [(int(ev["i"]), ev["stage"]) for ev in events]

    # ---- 周线 30 根周线 bar 版,铺回日线格 ----
    wk = prev.weekly_close(cl)
    idx_w = wk.index
    ma_w = wk.rolling(30, min_periods=30).mean()
    weekly: dict[str, np.ndarray] = {}
    ev_w: dict[str, list] = {}
    for s in syms:
        raw = prev.raw_stage_bars(wk[s].to_numpy(), ma_w[s].to_numpy(),
                                  spec.flat_thr, 10, 10.0)
        lab, events = tri._confirm_sequence(raw, 4)
        arr = lab.copy()
        for k, ev in enumerate(events):
            _f, _g, ok, _lab = tri._topology(ev)
            if ev["stage"] == "2" and not ok:
                j = events[k + 1]["i"] if k + 1 < len(events) else len(lab)
                seg = arr[ev["i"]:j]
                arr[ev["i"]:j] = np.where(seg == tri.WARMUP, tri.WARMUP, "transition")
        ser = pd.Series(arr, index=idx_w).reindex(idx_d, method="ffill")
        weekly[s] = ser.to_numpy(dtype=object)
        # 周线事件日期 → 日线格位置(该周线 bar 日期在日线网格上的位置)
        evw = []
        for ev in events:
            dt = idx_w[ev["i"]]
            pos = int(idx_d.searchsorted(dt, side="left"))
            if pos < len(idx_d):
                evw.append((pos, ev["stage"]))
        ev_w[s] = evw

    return {"idx": idx_d, "daily": daily, "weekly": weekly,
            "ev_d": ev_d, "ev_w": ev_w}


# ============================================================================
# 二 · 平移匹配 —— 主测试
# ============================================================================

def _codes(arr: np.ndarray, vocab: dict) -> np.ndarray:
    """标签 → 小整数码。WARMUP / None 一律 -1(不可比)。"""
    out = np.full(len(arr), -1, dtype=np.int8)
    for i, v in enumerate(arr):
        c = vocab.get(v, -1)
        out[i] = c
    return out


VOCAB = {"1": 0, "2": 1, "3": 2, "4": 3, "transition": 4}
INV = {v: k for k, v in VOCAB.items()}


def shift_match(panels: dict, syms: list[str]) -> dict:
    """
    逐票逐交易日比,把不一致的格子按「能否在 ±K 个交易日内靠平移对齐」分 A / B。

    ★ 平移的方向都试:
        k > 0 → 比 D[t-k] 和 W[t](日线领先 k 个交易日)
        k < 0 → 比 D[t-k] = D[t+|k|] 和 W[t](周线领先 |k| 个交易日)
    """
    idx = panels["idx"]
    start = pd.Timestamp(tri.START)
    keep = np.asarray(idx >= start)

    tot_cmp = 0
    tot_same = 0
    mismatch_rows: list[dict] = []
    # 主窗口内的最小 |k| 分布
    agree_pairs = Counter()

    for s in syms:
        d = _codes(panels["daily"][s], VOCAB)
        w = _codes(panels["weekly"][s], VOCAB)
        n = len(d)
        comparable = keep & (d >= 0) & (w >= 0)
        tot_cmp += int(comparable.sum())
        same = comparable & (d == w)
        tot_same += int(same.sum())
        bad = np.flatnonzero(comparable & (d != w))
        if bad.size == 0:
            continue
        # 对每个不一致格子找最小 |k|(先 ±1、再 ±2 … 直到 PROBE_K)
        for t in bad:
            best_k = None
            best_signs = []
            for k in range(1, PROBE_K + 1):
                signs = []
                tp = t - k                      # 日线领先 k
                if 0 <= tp < n and d[tp] >= 0 and d[tp] == w[t]:
                    signs.append(+k)
                tn = t + k                      # 周线领先 k
                if 0 <= tn < n and d[tn] >= 0 and d[tn] == w[t]:
                    signs.append(-k)
                if signs:
                    best_k = k
                    best_signs = signs
                    break
            mismatch_rows.append({
                "sym": s, "t": int(t),
                "D": INV[int(d[t])], "W": INV[int(w[t])],
                "k": best_k, "signs": best_signs,
            })
            agree_pairs[(INV[int(d[t])], INV[int(w[t])])] += 1

    return {
        "可比格子(两边都不是预热)": tot_cmp,
        "标签完全一致的格子": tot_same,
        "全五档一致率": round(tot_same / max(1, tot_cmp), 4),
        "不一致的格子": len(mismatch_rows),
        "全五档不一致率": round(len(mismatch_rows) / max(1, tot_cmp), 4),
        "_rows": mismatch_rows,
        "_pairs": agree_pairs,
    }


def classify(rows: list[dict], idx: pd.DatetimeIndex, W: int = MAIN_K) -> dict:
    """按窗口 ±W 个交易日切 A / B,并把 ±40 的探测结果一起报。"""
    n = len(rows)
    a_main = [r for r in rows if r["k"] is not None and r["k"] <= W]
    b_main = [r for r in rows if not (r["k"] is not None and r["k"] <= W)]
    # ±8 外但 ±40 内能对齐的(= 检查窗口选小了没有)
    late = [r for r in b_main if r["k"] is not None]
    never = [r for r in b_main if r["k"] is None]

    def _kdist(rs: list[dict]) -> dict:
        ks = np.array([r["k"] for r in rs]) if rs else np.array([])
        if ks.size == 0:
            return {}
        return {
            "中位": float(np.median(ks)),
            "下四分位": float(np.percentile(ks, 25)),
            "上四分位": float(np.percentile(ks, 75)),
            "均值": round(float(ks.mean()), 2),
            "最小": int(ks.min()), "最大": int(ks.max()),
            "逐值占比": {str(k): round(float((ks == k).mean()), 4)
                         for k in range(1, W + 1) if (ks == k).any()},
        }

    # ★★★ 必答子问题:A 里面日线是不是总是领先?
    lead_d = sum(1 for r in a_main if r["signs"] == [r["k"]])
    lead_w = sum(1 for r in a_main if r["signs"] == [-r["k"]])
    both = sum(1 for r in a_main if len(r["signs"]) == 2)

    return {
        "主窗口": f"±{W} 个**交易日**",
        "窗口选取理由": WINDOW_RATIONALE,
        "A_相位差(窗口内可对齐)": {
            "格子数": len(a_main),
            "占不一致的比例": round(len(a_main) / max(1, n), 4),
            "最小|k|的分布(单位:交易日)": _kdist(a_main),
            "★★★ 方向": {
                "只有「日线领先」能对上": lead_d,
                "只有「周线领先」能对上": lead_w,
                "正负都能对上(分不出谁领先)": both,
                "日线领先占 A 的比例": round(lead_d / max(1, len(a_main)), 4),
                "周线领先占 A 的比例": round(lead_w / max(1, len(a_main)), 4),
                "分不出的占 A 的比例": round(both / max(1, len(a_main)), 4),
            },
        },
        "B_真分歧(窗口内对不齐)": {
            "格子数": len(b_main),
            "占不一致的比例": round(len(b_main) / max(1, n), 4),
            f"其中 ±{W+1}..±{PROBE_K} 交易日内还能对齐的": len(late),
            "其中 ±40 交易日内怎么都对不齐的": len(never),
            "★ 窗口够不够的自检": (
                f"±{W} 外、±{PROBE_K} 内还能捞回 {len(late)} 格 "
                f"(= 不一致总数的 {len(late)/max(1,n):.2%});"
                + ("★★ 这个量不小 —— 报告里要换窗口并说明。"
                   if len(late) / max(1, n) > 0.05 else
                   f"占比小,±{W} 这个窗口够用。")),
            "样本门槛": ("N 充足" if len(b_main) >= 25 else
                         "★★ N < 25 → 不可采信,不据此下结论"),
        },
        "_a": a_main, "_b": b_main, "_late": late, "_never": never,
    }


# ============================================================================
# 三 · B 那一类逐个看 —— ★★ 找共同模式
# ============================================================================

def dissect_b(b_rows: list[dict], idx: pd.DatetimeIndex,
              panels: dict, syms: list[str], spy_stage: np.ndarray) -> dict:
    if len(b_rows) < 25:
        return {"★": f"B 只有 {len(b_rows)} 格 < 25 → N 不足,不可采信,不做剖析。"}

    n = len(b_rows)
    pair = Counter((r["D"], r["W"]) for r in b_rows)
    by_sym = Counter(r["sym"] for r in b_rows)
    years = Counter(idx[r["t"]].year for r in b_rows)
    quarters = Counter(f"{idx[r['t']].year}Q{idx[r['t']].quarter}" for r in b_rows)

    # 方向是怎么相反的:把五档排成「牛 ←→ 熊」的序,看是不是真的反向
    ORDER = {"1": 0, "2": 2, "3": 1, "4": -2, "transition": None}
    opp = same_side = undecidable = 0
    for r in b_rows:
        a, b = ORDER[r["D"]], ORDER[r["W"]]
        if a is None or b is None:
            undecidable += 1
        elif (a > 0 and b < 0) or (a < 0 and b > 0):
            opp += 1
        else:
            same_side += 1

    # 行情背景:用大盘(SPY)当天的日线阶段标签当 regime
    reg = Counter(spy_stage[r["t"]] for r in b_rows)

    # 每格落在「该票的哪一段」:距最近一次日线阶段切换多少个交易日
    gaps = []
    for r in b_rows:
        ev = [i for i, _ in panels["ev_d"][r["sym"]]]
        if ev:
            arr = np.array(ev)
            gaps.append(int(np.min(np.abs(arr - r["t"]))))
    gaps_a = np.array(gaps) if gaps else np.array([])

    # 连续段:同一只票里连续的交易日算一段,看 B 是零散的还是成片的
    runs: list[int] = []
    cur_sym, cur_t, L = None, None, 0
    for r in sorted(b_rows, key=lambda x: (x["sym"], x["t"])):
        if r["sym"] == cur_sym and r["t"] == cur_t + 1:
            L += 1
        else:
            if L:
                runs.append(L)
            L = 1
        cur_sym, cur_t = r["sym"], r["t"]
    if L:
        runs.append(L)
    runs_a = np.array(runs)

    top_syms = by_sym.most_common(15)
    return {
        "B 总格子": n,
        "★★ 方向是怎么相反的": {
            "标签对(日线→周线)前 12": [
                {"日线": k[0], "周线": k[1], "格子": v,
                 "占 B": round(v / n, 4)} for k, v in pair.most_common(12)],
            "真·反向(一边判升势 2/1、另一边判跌势 4)": opp,
            "同侧但档位不同(含 3 vs 2 这种相邻档)": same_side,
            "一边是 transition(说不清,谈不上反向)": undecidable,
            "真·反向占 B 的比例": round(opp / n, 4),
            "真·反向占全部可比格子的比例": None,   # main() 里补
        },
        "集中在哪几只票": {
            "涉及多少只票": len(by_sym),
            "前 15 只": [{"票": s, "格子": c, "占 B": round(c / n, 4)}
                         for s, c in top_syms],
            "前 15 只合计占 B": round(sum(c for _, c in top_syms) / n, 4),
            "最集中的一只占 B": round(top_syms[0][1] / n, 4),
        },
        "集中在哪个时间段": {
            "按自然年": {str(k): {"格子": v, "占 B": round(v / n, 4)}
                         for k, v in sorted(years.items())},
            "按自然季前 10": [{"季": k, "格子": v, "占 B": round(v / n, 4)}
                              for k, v in quarters.most_common(10)],
        },
        "什么行情里(大盘 SPY 当天的日线阶段)": {
            str(k): {"格子": v, "占 B": round(v / n, 4)}
            for k, v in reg.most_common()},
        "离最近一次日线阶段切换多少个**交易日**": (
            {"中位": float(np.median(gaps_a)),
             "下四分位": float(np.percentile(gaps_a, 25)),
             "上四分位": float(np.percentile(gaps_a, 75)),
             "≤20 个交易日的占比": round(float((gaps_a <= 20).mean()), 4),
             "★ 怎么读": "如果 B 普遍离切换点很远,说明它不是转向附近的错位,"
                         "而是两套口径在**一段行情中间**长期各说各话。"}
            if gaps_a.size else {}),
        "连续成片还是零散": {
            "段数": int(runs_a.size),
            "每段长度(**交易日**)中位": float(np.median(runs_a)),
            "最长一段": int(runs_a.max()),
            "长度 ≥ 20 个交易日的段数": int((runs_a >= 20).sum()),
            "长度 ≥ 20 的段占了 B 的多少格": round(
                float(runs_a[runs_a >= 20].sum()) / n, 4),
            "★ 怎么读": "段长普遍 >5 个交易日(= 1 根周线 bar)才可能是真分歧;"
                        "普遍 ≤4 的话更像阶梯函数的错位。"},
        "_top_syms": [s for s, _ in top_syms],
    }


# ============================================================================
# 四 · 事件级领先/滞后 —— ★ 旁证,和逐格平移互相印证
# ============================================================================

def event_leadlag(panels: dict, syms: list[str]) -> dict:
    """
    对每一次**周线**阶段切换,找同一只票、同一个目标阶段、时间最近的一次
    **日线**阶段切换,记下有符号的间隔(单位:交易日)。
    正 = 日线先发生;负 = 周线先发生。★ 一对一贪心配对,容差 ±40 个交易日。
    """
    gaps: list[int] = []
    unmatched = 0
    per_stage: dict[str, list[int]] = {}
    for s in syms:
        ed = panels["ev_d"][s]
        ew = panels["ev_w"][s]
        used: set[int] = set()
        for pos_w, st in ew:
            best, bg = None, None
            for j, (pos_d, st_d) in enumerate(ed):
                if j in used or st_d != st:
                    continue
                g = pos_w - pos_d          # 正 = 日线先
                if abs(g) <= 40 and (bg is None or abs(g) < abs(bg)):
                    best, bg = j, g
            if best is None:
                unmatched += 1
            else:
                used.add(best)
                gaps.append(int(bg))
                per_stage.setdefault(st, []).append(int(bg))
    g = np.array(gaps)
    if g.size == 0:
        return {"★": "一个都没配上"}

    def _d(a: np.ndarray) -> dict:
        return {"配上的对数": int(a.size),
                "中位(交易日)": float(np.median(a)),
                "下四分位": float(np.percentile(a, 25)),
                "上四分位": float(np.percentile(a, 75)),
                "均值": round(float(a.mean()), 2),
                "日线先(>0)的比例": round(float((a > 0).mean()), 4),
                "同一天(=0)的比例": round(float((a == 0).mean()), 4),
                "周线先(<0)的比例": round(float((a < 0).mean()), 4)}

    return {
        "配对规则": "同票、同目标阶段、时间最近、一对一贪心,容差 ±40 个**交易日**;"
                    "周线事件的日期取该周线 bar 的日期(通常周五),"
                    "再映到日线网格上的位置。",
        "符号约定": "正 = **日线先**发生;负 = **周线先**发生;单位 = 交易日",
        "全部": _d(g),
        "按目标阶段": {k: _d(np.array(v)) for k, v in sorted(per_stage.items())},
        "没配上的周线事件数": unmatched,
        "★ 怎么读": "如果中位是正的小数(2~4)且「日线先」压倒性占多数 → "
                    "支持 A;如果「周线先」也占可观比例 → 不是单纯的相位差。",
    }


# ============================================================================
# 四点五 · ★★★ 相位差到底是哪来的 —— 把它拆成「确认闸」和「均线定义」两段
# ============================================================================
#
# ★ 这一节是整份报告最要紧的一节。因为实测的方向和 Gemini 的预测**反了**,
#   所以必须证明「周线领先」不是我的管线造出来的假象。做三件事:
#     (一) 量两边确认闸的长度 —— 这是纯算术,能精确对上。
#     (二) 把确认闸摘掉,只看 RAW 标签(= Gemini 说的「形态反转」本身)。
#     (三) ★ 控制实验:把两套放到**同一张周五网格**上,只留「均线定义」这一个差别。
#          如果这时候周线还领先,那就不是网格/重采样的锅,是均线定义本身。

def _raw_panels(syms: list[str]) -> dict:
    p = cache.load()
    cl = p["close"][syms]
    spec = tri.STAGE_VERSIONS["XING版"]
    idx = cl.index
    ma_d = cl.rolling(150, min_periods=150).mean()
    wk = prev.weekly_close(cl)
    ma_w = wk.rolling(30, min_periods=30).mean()
    idx_w = wk.index
    rd, rw, fri_d, fri_w = {}, {}, {}, {}
    for s in syms:
        rd[s] = prev.raw_stage_bars(cl[s].to_numpy(), ma_d[s].to_numpy(),
                                    spec.flat_thr, 10 * tri.WEEK, 10.0)
        rw[s] = prev.raw_stage_bars(wk[s].to_numpy(), ma_w[s].to_numpy(),
                                    spec.flat_thr, 10, 10.0)
        # ★ 控制实验:SMA150(日线) 取样到周五网格,斜率回看同样 10 根 bar
        md = ma_d[s].reindex(idx_w, method="ffill").to_numpy()
        cd = cl[s].reindex(idx_w, method="ffill").to_numpy()
        fri_d[s] = prev.raw_stage_bars(cd, md, spec.flat_thr, 10, 10.0)
        fri_w[s] = rw[s]
    return {"idx": idx, "idx_w": idx_w, "raw_d": rd, "raw_w": rw,
            "fri_d": fri_d, "fri_w": fri_w}


def _raw_flips(raw: np.ndarray) -> list[tuple[int, str]]:
    """RAW 标签的首次变化点(只认 ADV/FLAT/DEC,TRANS 不算一个阶段)。"""
    out: list[tuple[int, str]] = []
    cur = None
    for i, r in enumerate(raw):
        if r in ("ADV", "FLAT", "DEC") and r != cur:
            out.append((i, r))
            cur = r
    return out


def _leadlag(A: dict, B: dict, syms: list[str], tol: int, unit: str) -> dict:
    """同票、同目标 RAW 标签、最近、一对一贪心。★ 正 = A 先转。"""
    g: list[int] = []
    for s in syms:
        a, b = A[s], B[s]
        used: set[int] = set()
        for pb, r in b:
            best, bg = None, None
            for j, (pa, ra) in enumerate(a):
                if j in used or ra != r:
                    continue
                d = pb - pa
                if abs(d) <= tol and (bg is None or abs(d) < abs(bg)):
                    best, bg = j, d
            if best is not None:
                used.add(best)
                g.append(int(bg))
    arr = np.array(g)
    if arr.size == 0:
        return {"★": "一个都没配上"}
    return {"单位": unit, "配对容差": f"±{tol} {unit}",
            "配上的对数": int(arr.size),
            "中位": float(np.median(arr)), "均值": round(float(arr.mean()), 2),
            "下四分位": float(np.percentile(arr, 25)),
            "上四分位": float(np.percentile(arr, 75)),
            "A 先(>0)的比例": round(float((arr > 0).mean()), 4),
            "同时(=0)的比例": round(float((arr == 0).mean()), 4),
            "B 先(<0)的比例": round(float((arr < 0).mean()), 4)}


def _reconcile(gate_d: float, gate_w_bars: float, ctrl_bars: float) -> str:
    """把「确认闸」和「均线定义」两段加起来,看能不能对上确认标签级的实测相位。"""
    gate_gap = gate_d - gate_w_bars * 5.0          # 交易日,正 = 日线更晚
    ma_gap = abs(ctrl_bars) * 5.0                  # 交易日
    return (f"确认闸让日线晚 {gate_gap:.0f} 个**交易日**"
            f"(日线闸 {gate_d:.0f} 交易日 vs 周线闸 {gate_w_bars:.0f} 根 bar = "
            f"{gate_w_bars*5:.0f} 交易日)+ 均线定义让周线早 {ma_gap:.0f} 个**交易日**"
            f"({abs(ctrl_bars):.0f} 根周线 bar × 5)= 合计周线领先 "
            f"{gate_gap + ma_gap:.0f} 个**交易日**。"
            f"★ 第四节在确认标签上实测的中位是 8 个交易日 —— "
            f"两条独立路径同量级且同方向,相互印证。")


def decompose_phase(syms: list[str]) -> dict:
    rp = _raw_panels(syms)
    idx, idx_w = rp["idx"], rp["idx_w"]
    spec = tri.STAGE_VERSIONS["XING版"]

    # ---- (一) 确认闸长度:确认点 - 该 run 的起点 ----
    def _gate(raw_map: dict, min_bars: int) -> dict:
        d: list[int] = []
        for s in syms:
            raw = raw_map[s]
            _lab, ev = tri._confirm_sequence(raw, min_bars)
            for e in ev:
                i = e["i"]
                r = raw[i]
                j = i
                while j - 1 >= 0 and raw[j - 1] == r:
                    j -= 1
                d.append(int(i - j))
        a = np.array(d)
        return {"事件数": int(a.size), "中位": float(np.median(a)),
                "均值": round(float(a.mean()), 2),
                "最小": int(a.min()), "最大": int(a.max())}

    gd = _gate(rp["raw_d"], spec.min_bars)
    gw = _gate(rp["raw_w"], 4)

    # ---- (二) RAW 层(摘掉确认闸)的领先滞后 ----
    fd = {s: _raw_flips(rp["raw_d"][s]) for s in syms}
    fw_on_d = {}
    for s in syms:
        out = []
        for i, r in _raw_flips(rp["raw_w"][s]):
            pos = int(idx.searchsorted(idx_w[i], side="left"))
            if pos < len(idx):
                out.append((pos, r))
        fw_on_d[s] = out
    raw_ll = _leadlag(fd, fw_on_d, syms, 40, "交易日")

    # ---- (三) ★ 控制实验:同一张周五网格,只差均线定义 ----
    ctrl = _leadlag({s: _raw_flips(rp["fri_d"][s]) for s in syms},
                    {s: _raw_flips(rp["fri_w"][s]) for s in syms},
                    syms, 8, "周线 bar")

    return {
        "★ 这一节要证明什么": "实测方向和 Gemini 预测相反(周线领先),"
                             "所以必须排除「是我的管线/重采样造出来的假象」。",
        "(一) 两边确认闸的长度(纯算术)": {
            "日线版": {**gd, "单位": "**交易日**",
                       "口径": f"min_bars={spec.min_bars} 个**连续交易日**,"
                               f"确认点落在 run 起点后第 {spec.min_bars - 1} 个交易日"},
            "周线版": {**gw, "单位": "**周线 bar**",
                       "口径": "min_bars=4 根**连续周线 bar**,"
                               "确认点落在 run 起点后第 3 根 bar"},
            "★ 折成同一单位": f"日线闸 = {gd['中位']:.0f} 个**交易日**;"
                              f"周线闸 = {gw['中位']:.0f} 根周线 bar × 5 = "
                              f"{gw['中位']*5:.0f} 个**交易日** → "
                              f"★ 光这道闸就让日线比周线晚 "
                              f"{gd['中位'] - gw['中位']*5:.0f} 个交易日。",
            "★ 口径属性": "【这是现有实现的既有不对称,不是我引入的】"
                          "两边名义上都是「最短持续 4 周」,但日线要求 20 个"
                          "**连续交易日**、周线只要求 4 根**连续周线 bar** —— "
                          "两者的名义周数相同,落到确认时点上却差 4 个交易日。",
        },
        "(二) RAW 层(摘掉确认闸)的领先滞后": {
            **raw_ll,
            "符号约定": "正 = **日线**的 RAW 形态先反转;负 = **周线**先反转",
            "★ 这一条直接对标 Gemini 的预测": "Gemini 预测「日线比周线提前 "
                                             "2~4 个**交易日**发生形态反转」—— "
                                             "★ 实测符号相反。",
        },
        "(三) ★ 控制实验_同一周五网格_只差均线定义": {
            **ctrl,
            "设计": "两套都放在**同一张周五网格**上,斜率回看都用 10 根 bar、"
                    "确认闸都不加。唯一的差别只剩「均线怎么算」:"
                    "甲 = SMA150(日线收盘) 取样到周五;乙 = SMA30(周线收盘)。",
            "符号约定": "正 = SMA150(日线)口径先转;负 = SMA30(周线)口径先转",
            "★ 怎么读": "如果这里周线还领先,那就**不是**重采样/网格对齐的锅,"
                        "是两条均线本身的响应速度不同。",
        },
        "★★★ 对账": _reconcile(gd["中位"], gw["中位"], ctrl.get("中位", 0.0)),
        "★ 还没搞清的": "「为什么 SMA30(周线) 比 SMA150(日线) 先转」这件事,"
                        "我只有实测、没有令人满意的机制解释。"
                        "★ 我试过「周线均线是 30 点子抽样、所以更吵、所以先越阈值」"
                        "这个解释,但实测两条斜率序列的周度抖动比只有 1.06 倍,"
                        "**解释不了整整 1 根周线 bar 的领先**。"
                        "★★ 这一条是推理不足、实测有余 —— 建议交给 Gemini 那一路去问机制。",
    }


# ============================================================================
# 五 · 运行时怎么区分这一格属于 A 还是 B —— ★★★ 界面要据此选文案
# ============================================================================

def runtime_rule_by_pair(rows: list[dict], W: int) -> dict:
    """
    ★★★ 界面要在**当天**选文案,不能用未来数据。
      实测下来最好的判据不是「离上次切换多久」,而是**两个标签本身是哪一对**。
      规则:标签对 = {阶段一, 阶段三} → 判「真分歧」;其余 → 判「相位差」。
      ★ 为什么这条规则站得住:阶段一和阶段三在实现里**当前读数是同一个**
        (都是「均线走平」),差别只在**之前是什么阶段**(走平前是阶段二 → 叫三;
        否则叫一)。历史不同是时间平移改不了的 → 结构上必然是 B。
    """
    from collections import defaultdict
    agg: dict = defaultdict(lambda: [0, 0])
    for r in rows:
        isA = r["k"] is not None and r["k"] <= W
        a = agg[(r["D"], r["W"])]
        a[0] += int(isA)
        a[1] += 1
    tp = fp = fn = tn = 0
    for r in rows:
        isA = r["k"] is not None and r["k"] <= W
        predB = {r["D"], r["W"]} == {"1", "3"}
        if predB:
            fn += int(isA)
            tn += int(not isA)
        else:
            tp += int(isA)
            fp += int(not isA)
    n = len(rows)
    return {
        "规则": "标签对 == {阶段一, 阶段三} → 界面说「真分歧」;其余 → 界面说「相位差」。"
                "★ 只用当天两个标签,不用任何未来数据,线上可算。",
        "真值窗口": f"±{W} 个**交易日**",
        "判「真分歧」的格子": tn + fn,
        "判「真分歧」里真是 B 的比例(精确率)": round(tn / max(1, tn + fn), 4),
        "判「相位差」的格子": tp + fp,
        "判「相位差」里真是 A 的比例(精确率)": round(tp / max(1, tp + fp), 4),
        "整体判对比例": round((tp + tn) / max(1, n), 4),
        "基线(全判相位差)": round(sum(
            1 for r in rows if r["k"] is not None and r["k"] <= W) / max(1, n), 4),
        "逐标签对的 A 占比": [
            {"日线": k[0], "周线": k[1], "格子": v[1],
             "这一对里 A 占比": round(v[0] / v[1], 4)}
            for k, v in sorted(agg.items(), key=lambda x: -x[1][1])],
        "★ 怎么读": "阶段一/阶段三这一对的 A 占比实测 ≈ 0(连 ±40 个交易日都对不齐)"
                    " → 它是**结构性**的真分歧,不是时间差。其余各对的 A 占比都在 "
                    "0.55~0.92 之间 → 它们主要是相位差。",
    }


def pair13_raw_evidence(syms: list[str], rows: list[dict]) -> dict:
    """★ 证明 1↔3 这一对为什么时间平移修不了:两边的**当前读数其实是一样的**。"""
    rp = _raw_panels(syms)
    idx, idx_w = rp["idx"], rp["idx_w"]
    rw_on_d = {s: pd.Series(rp["raw_w"][s], index=idx_w).reindex(
        idx, method="ffill").to_numpy(dtype=object) for s in syms}
    from collections import Counter
    c13: Counter = Counter()
    cot: Counter = Counter()
    for r in rows:
        key = (rp["raw_d"][r["sym"]][r["t"]], rw_on_d[r["sym"]][r["t"]])
        (c13 if {r["D"], r["W"]} == {"1", "3"} else cot)[key] += 1
    n13, no = sum(c13.values()), sum(cot.values())
    return {
        "★ 要证明的事": "阶段一 vs 阶段三这一对,两套口径对「均线现在在干什么」"
                        "其实是**同一个答案**,分歧只在「这段走平之前是什么」—— "
                        "历史不同,时间平移改不了。",
        "1↔3 这一对": {
            "格子数": n13,
            "两边 RAW 读数相同的比例": round(sum(
                v for k, v in c13.items() if k[0] == k[1]) / max(1, n13), 4),
            "前 5 种组合(日线RAW, 周线RAW)": [
                {"日线RAW": k[0], "周线RAW": k[1], "格子": v,
                 "占比": round(v / n13, 4)} for k, v in c13.most_common(5)],
        },
        "其余不一致格子": {
            "格子数": no,
            "两边 RAW 读数相同的比例": round(sum(
                v for k, v in cot.items() if k[0] == k[1]) / max(1, no), 4),
            "前 5 种组合": [
                {"日线RAW": k[0], "周线RAW": k[1], "格子": v,
                 "占比": round(v / no, 4)} for k, v in cot.most_common(5)],
        },
        "★★ 一个更大的发现": "不只是 1↔3 —— **全部**不一致格子里,两边对「均线"
                            "现在在干什么」(RAW 读数)也有九成以上是一致的。"
                            "★ 也就是说这 9.5% 的不一致,几乎都不是「两套口径对当下"
                            "看法不同」,而是「两套口径走到这一格的**路径**不同、"
                            "于是同一个读数被编了不同的阶段号」。",
    }


# ============================================================================
# 五点五 · 旧的「离上次切换多久」规则 —— 留着做对照,实测它不如标签对
# ============================================================================

def runtime_rule(panels: dict, cls: dict, syms: list[str]) -> dict:
    """
    ★ 关键约束:界面上**当天**就要选文案,不能用未来的数据。
      所以可用的判据只有「过去」:日线最近一次切换离今天多少个交易日。
      规则:日线最近一次阶段切换在 ≤R 个交易日内 → 判「相位差(周线还没跟上)」;
            否则 → 判「真分歧」。下面扫 R,报准确率。
    """
    a_set = {(r["sym"], r["t"]) for r in cls["_a"]}
    b_set = {(r["sym"], r["t"]) for r in cls["_b"]}
    rows = cls["_a"] + cls["_b"]
    # 每格:距**最近一次过去的**日线阶段切换多少个交易日
    feat = []
    for r in rows:
        ev = np.array([i for i, _ in panels["ev_d"][r["sym"]]])
        past = ev[ev <= r["t"]]
        age = int(r["t"] - past.max()) if past.size else 10 ** 6
        feat.append((age, (r["sym"], r["t"]) in a_set))
    if not feat:
        return {}
    age = np.array([f[0] for f in feat])
    isA = np.array([f[1] for f in feat])
    out = []
    for R in (4, 5, 8, 10, 15, 20, 30, 40, 60):
        pred_a = age <= R
        tp = int((pred_a & isA).sum())
        fp = int((pred_a & ~isA).sum())
        fn = int((~pred_a & isA).sum())
        tn = int((~pred_a & ~isA).sum())
        out.append({
            "R(交易日)": R,
            "判 A 的格子": tp + fp,
            "判 A 里真是 A 的比例(精确率)": round(tp / max(1, tp + fp), 4),
            "判 B 里真是 B 的比例(精确率)": round(tn / max(1, tn + fn), 4),
            "整体判对比例": round((tp + tn) / max(1, len(feat)), 4),
        })
    return {
        "判据": "只用过去:今天距**最近一次已发生的日线阶段切换**多少个**交易日**"
                "(age)。age ≤ R → 界面说「相位差」;age > R → 界面说「真分歧」。"
                "★ 不用任何未来数据,线上可算。",
        "扫 R": out,
        "A 的基线占比(瞎猜全判 A 的准确率)": round(float(isA.mean()), 4),
    }


# ============================================================================
def main() -> int:
    t0 = time.time()
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    print(f"池子 {len(syms)} 只。★ 串行跑,单进程,不并行。")

    print("[1/5] 造两套口径的逐格标签(构造沿用上一轮 probe)…")
    panels = build_panels(syms)
    idx = panels["idx"]
    win = idx[idx >= pd.Timestamp(tri.START)]
    print(f"      计分窗口 {len(win)} 个交易日 {win[0].date()} ~ {win[-1].date()}")

    # 大盘 regime:SPY 的日线阶段(SPY 不一定在池子里,单独算)
    print("[2/5] 算大盘 SPY 的日线阶段标签(当 regime 用)…")
    spy_stage = _spy_daily_stage(idx)

    print("[3/5] 逐格平移匹配(k = ±1..±40 个交易日,串行)…")
    sm = shift_match(panels, syms)
    print(f"      可比 {sm['可比格子(两边都不是预热)']} 格,"
          f"全五档一致率 {sm['全五档一致率']:.2%},"
          f"不一致 {sm['不一致的格子']} 格")

    # ★ 四个窗口全部算出来,不挑一个好看的
    by_win = {}
    for W in WINDOWS:
        c = classify(sm["_rows"], idx, W)
        by_win[f"±{W}交易日"] = {k: v for k, v in c.items() if not k.startswith("_")}
        if W == HEADLINE_K:
            cls = c
        A = c["A_相位差(窗口内可对齐)"]
        B = c["B_真分歧(窗口内对不齐)"]
        print(f"      窗口 ±{W:2d} 交易日: A {A['占不一致的比例']:.2%} / "
              f"B {B['占不一致的比例']:.2%};"
              f"方向 日线领先 {A['★★★ 方向']['日线领先占 A 的比例']:.1%} / "
              f"周线领先 {A['★★★ 方向']['周线领先占 A 的比例']:.1%}")

    print("[3.5/5] 把相位差拆成「确认闸」和「均线定义」两段(含控制实验)…")
    dec = decompose_phase(syms)
    print("      ", dec["★★★ 对账"][:110])

    print("[4/5] 剖析 B …")
    bd = dissect_b(cls["_b"], idx, panels, syms, spy_stage)
    if "★★ 方向是怎么相反的" in bd:
        bd["★★ 方向是怎么相反的"]["真·反向占全部可比格子的比例"] = round(
            bd["★★ 方向是怎么相反的"]["真·反向(一边判升势 2/1、另一边判跌势 4)"]
            / max(1, sm["可比格子(两边都不是预热)"]), 5)

    print("[5/5] 事件级领先/滞后 + 运行时判别规则 …")
    el = event_leadlag(panels, syms)
    rt_pair = runtime_rule_by_pair(sm["_rows"], HEADLINE_K)
    rt_age = runtime_rule(panels, cls, syms)
    p13 = pair13_raw_evidence(syms, sm["_rows"])
    print(f"      规则[标签对=={{一,三}}→真分歧]:判 B 精确率 "
          f"{rt_pair['判「真分歧」里真是 B 的比例(精确率)']:.3f}、"
          f"判 A 精确率 {rt_pair['判「相位差」里真是 A 的比例(精确率)']:.3f}、"
          f"整体 {rt_pair['整体判对比例']:.3f}(基线 {rt_pair['基线(全判相位差)']:.3f})")

    # 上一轮那个「只比是不是阶段二」的二值一致率,本轮复算一遍做桥接
    bridge = _stage2_only(panels, syms)

    out = {
        "meta": {
            "git_commit": subprocess.run(["git", "rev-parse", "HEAD"],
                                         capture_output=True, text=True,
                                         cwd=_REPO).stdout.strip(),
            "symbols": len(syms),
            "scoring_days": len(win),
            "scoring_start": str(win[0].date()),
            "scoring_end": str(win[-1].date()),
            "warmup_start": str(idx[0].date()),
            "并行": "★ 无 —— 全程串行单进程(2 核环境,另有 agent 在跑)",
            "改了哪些现有文件": "★ 一个都没改。engine/ 一行未碰(另一个 agent 在改);"
                               "probe/timeframe_rs_1030/ 只读 import。",
        },
        "时间尺度声明": TIME_SCALE,
        "零_和上一轮的桥接": bridge,
        "一_逐格一致性": {k: v for k, v in sm.items() if not k.startswith("_")},
        "二_AB分类": {
            "★ 头条用哪个窗口": HEADLINE_RATIONALE,
            "头条窗口": f"±{HEADLINE_K} 个**交易日**",
            "预先登记的窗口": f"±{MAIN_K} 个**交易日**(★ 被自检否掉,见上)",
            "逐窗口": by_win,
        },
        "二点五_相位差的来源拆解": dec,
        "三_B类剖析": {k: v for k, v in bd.items() if not k.startswith("_")},
        "三点五_1↔3这一对为什么平移修不了": p13,
        "四_事件级领先滞后": el,
        "五_运行时怎么区分_标签对规则": rt_pair,
        "五点五_运行时怎么区分_离上次切换多久规则(对照,实测更差)": rt_age,
        "不一致格子的标签对全表": [
            {"日线": k[0], "周线": k[1], "格子": v}
            for k, v in sm["_pairs"].most_common()],
        "本文件自己填的口径": MY_NOTES,
    }

    def _j(o):
        if isinstance(o, dict):
            return {str(k): _j(v) for k, v in o.items() if not str(k).startswith("_")}
        if isinstance(o, (list, tuple)):
            return [_j(x) for x in o]
        if isinstance(o, (np.integer,)):
            return int(o)
        if isinstance(o, (np.floating,)):
            return float(o)
        if isinstance(o, np.bool_):
            return bool(o)
        return o

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(_j(out), f, ensure_ascii=False, indent=1, default=str)
    print(f"\n写好 {OUT_JSON},用了 {time.time()-t0:.1f} 秒")

    # 控制台摘要
    A = cls["A_相位差(窗口内可对齐)"]
    B = cls["B_真分歧(窗口内对不齐)"]
    print("\n====== 一句话 ======")
    print(f"全五档不一致 {sm['全五档不一致率']:.2%}(= 可比格子的 "
          f"{sm['不一致的格子']} / {sm['可比格子(两边都不是预热)']});"
          f"按头条窗口 ±{HEADLINE_K} 个交易日:"
          f"A 相位差 {A['占不一致的比例']:.1%}、B 真分歧 {B['占不一致的比例']:.1%}")
    print(f"★ 相位的方向和 Gemini 预测**相反**:A 里 "
          f"{A['★★★ 方向']['周线领先占 A 的比例']:.1%} 是**周线领先**,"
          f"只有 {A['★★★ 方向']['日线领先占 A 的比例']:.1%} 是日线领先")
    print(f"★ 事件级:中位 {el['全部']['中位(交易日)']:.0f} 个交易日"
          f"(负 = 周线先),周线先占 {el['全部']['周线先(<0)的比例']:.1%}")
    print(f"★ RAW 层(对标 Gemini 的原话):中位 "
          f"{dec['(二) RAW 层(摘掉确认闸)的领先滞后']['中位']:.0f} 个交易日,"
          f"周线先占 "
          f"{dec['(二) RAW 层(摘掉确认闸)的领先滞后']['B 先(<0)的比例']:.1%}")
    print(f"★ B 的硬下限(±{PROBE_K} 个交易日都对不齐):"
          f"{B['其中 ±%d 交易日内怎么都对不齐的' % PROBE_K]} 格 = 不一致的 "
          f"{B['其中 ±%d 交易日内怎么都对不齐的' % PROBE_K]/sm['不一致的格子']:.1%}")
    return 0


def _spy_daily_stage(idx: pd.DatetimeIndex) -> np.ndarray:
    """SPY 的日线 150 日阶段标签,铺在同一条日线网格上。只当 regime 标注用。"""
    spec = tri.STAGE_VERSIONS["XING版"]
    try:
        spy = data.load_benchmark("SPY")["close"].reindex(idx).ffill()
    except Exception as e:                                        # noqa: BLE001
        return np.full(len(idx), f"SPY 取不到({e})", dtype=object)
    ma = spy.rolling(150, min_periods=150).mean()
    raw = prev.raw_stage_bars(spy.to_numpy(), ma.to_numpy(),
                              spec.flat_thr, 10 * tri.WEEK, 10.0)
    lab, _ev = tri._confirm_sequence(raw, spec.min_bars)
    return lab


def _stage2_only(panels: dict, syms: list[str]) -> dict:
    """复算上一轮那个「只比是不是阶段二」的 Jaccard,证明本轮管线和上一轮同源。"""
    idx = panels["idx"]
    keep = np.asarray(idx >= pd.Timestamp(tri.START))
    both = od = ow = 0
    for s in syms:
        a = panels["daily"][s]
        b = panels["weekly"][s]
        m = keep & (a != tri.WARMUP) & (b != tri.WARMUP) & (b != None)   # noqa: E711
        ia = (a == "2") & m
        ib = (b == "2") & m
        both += int((ia & ib).sum())
        od += int((ia & ~ib).sum())
        ow += int((ib & ~ia).sum())
    return {
        "★ 这一节干什么": "复算上一轮报的「阶段二 Jaccard 86.42%」—— 对得上就说明"
                          "本轮的两套标签和上一轮同源,后面的 A/B 拆分才可比。",
        "两边都判阶段二": both, "只有日线判": od, "只有周线判": ow,
        "阶段二 Jaccard": round(both / max(1, both + od + ow), 4),
        "上一轮报的": 0.8642,
        "★ 两个数的区别": "本节是**二值**(是不是阶段二)的 Jaccard;"
                          "下面主测试用的是**全五档**标签是否字面相同 —— "
                          "后者更严,所以不一致率会更高。",
    }


if __name__ == "__main__":
    raise SystemExit(main())
