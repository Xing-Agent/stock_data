"""
状-2 温斯坦四阶段:阶段号对「之前走过的路」有多敏感

================================================================================
三秒版
================================================================================
一句话:阶段三(顶部,该卖)和阶段一(底部,该买)在**当天的读数上长得一样**
       (都是「均线走平」),区分它们只能靠「之前是涨上来的还是跌下来的」。
       ★ 本文件问:这个「之前」靠不靠得住?换个起点重算,阶段号会不会变?

三个问题(按重要性):
  一、★★★ 同一只票、同一个交易日、同一份原始读数,起点不同会不会编出不同的阶段号?
      → 测法:**换起点重算**。把同一只票的收盘序列从不同起点切开喂进去,
        比同一个交易日的阶段号。
  二、★★★ 顶底会混淆到什么程度?走平格子里有多少是靠路径定的一/三?
      最危险的区段(刚从长期趋势里出来)占多少?编反了对 技-3 的每笔 R 有多大影响?
  三、★★ 有没有一条**只用当天和历史、不用未来**的判据,能标出「这一格阶段号存疑」?

★ 硬纪律(本文件逐条守着):
  一、不改任何现有文件。`engine/` 一行未碰 —— 用 importlib 只读加载上一轮 probe。
  二、`probe/phaseshift_1030/` / `probe/timeframe_rs_1030/` 只读。
  三、串行跑,单进程。
  四、阈值一个都不动(全部沿用 tri.STAGE_VERSIONS['XING版'])。
  五、凡「天」一律写明是**交易日**还是自然日。
  六、★ 复算对账:必须复现上一轮的 90.50% / 86.42% / 134294 / 10850 / 10258。
      对不上就 raise,不许往下跑。

跑法:python3 probe/stage_path_1030/run_probe.py
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

from engine import cache                                          # noqa: E402
from engine import state_axis_tri_1029 as tri                     # noqa: E402

OUT_JSON = os.path.join(_HERE, "results_1030_阶段号对路径有多敏感.json")

# ---------------------------------------------------------------------------
# 上一轮的两个 probe 只读加载 —— ★ 为了让标签构造和上一轮**逐行一致**
# ---------------------------------------------------------------------------
_spec = importlib.util.spec_from_file_location(
    "_tf_probe_1030", os.path.join(_REPO, "probe", "timeframe_rs_1030", "run_probe.py"))
prev = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(prev)           # ★ 只 import,不跑它的 main()

SPEC = tri.STAGE_VERSIONS["XING版"]

# ---------------------------------------------------------------------------
# 时间尺度声明 —— 凡「天」都在这里写明
# ---------------------------------------------------------------------------
TIME_SCALE = {
    "起点偏移量 o": "**交易日**(在日线网格上往右切掉多少格)",
    "日线版的「150 日」": "150 个**交易日**",
    "日线最短持续「4 周」": "20 个**连续交易日**(= SPEC.min_bars)",
    "周线版的「30 周」": "30 根**周线 bar**",
    "周线最短持续「4 周」": "4 根**连续周线 bar**",
    "「距上次已确认趋势阶段多久」": "**交易日**",
    "「长期趋势」的长度门槛": "**交易日**",
    "可比窗口": "2018-01-02 ~ 2025-12-31,共 2,011 个**交易日**(= tri.START 之后)",
}

# ★★ 字段含义声明 —— 今天已经三次「把自己工具的语义读反了」,所以逐个写明白
FIELD_SEMANTICS = {
    "raw(原始读数)": "tri._raw_stage / prev.raw_stage_bars 的输出,"
                     "取值 FLAT / ADV / DEC / TRANS / WARMUP。"
                     "★ 我的理解:FLAT = 「SMA150 近 10 周的变化率绝对值 ≤0.5%/周」"
                     "= 大白话的「均线走平」。它**不含**任何阶段号信息。",
    "label(阶段号)": "tri._confirm_sequence 的逐日输出,取值 1/2/3/4/transition/WARMUP。"
                     "★ 我的理解:它是「已确认阶段」,一旦确认就一直挂着到下次确认,"
                     "不是「今天的原始读数」。",
    "「走平格子」": "★ 我的定义:**label ∈ {1,3}** 的格子。"
                   "理由:_confirm_sequence 里只有 raw==FLAT 连续满 20 个交易日才会"
                   "确认出 1 或 3(ADV→2,DEC→4),所以 label 1/3 就是"
                   "「走平被确认了」。★ 注意这和「今天 raw==FLAT」不是一回事 ——"
                   "阶段号会挂着,所以我**两个数都报**(见 二·1)。",
    "「阶段号靠路径定」": "★ 我的定义:把同一份 raw 序列的**已确认历史前缀**换掉"
                        "(= 换起点),这一格的 label 会变。"
                        "机制在 _confirm_sequence 里就一行:FLAT 确认时"
                        "`last=='2' → 3` / `last in ('1','3') → 保持` / `else → 1`。",
    "r_multiple_net": "台账列,★ 我的理解:单笔净 R 倍数(已扣摩擦)。"
                      "「每笔 R」= 这一列的算术平均。",
}

MY_NOTES: list[str] = []


def _note(s: str) -> None:
    if s not in MY_NOTES:
        MY_NOTES.append(s)


_note("★ 本文件「换起点重算」的实现是【我们填的】:把收盘序列从第 o 个**交易日**"
      "切开(cl[o:]),从切点重新算 SMA150、重新算 raw、重新跑 _confirm_sequence。"
      "★ 这样做的后果是**预热也跟着往后挪** —— 所以只在「所有起点都已出标签」"
      "的格子上比,不可比的格子一律剔掉并报出剔了多少。")
_note("★ 一个必须声明的事实:换起点**不改 raw 序列**(除了切点后头 200 个交易日的"
      "预热段)。所以起点能改的只有**已确认历史的前缀** —— 这正是我们要测的东西,"
      "不多也不少。")

# 起点偏移(**交易日**)
STARTS_REQUIRED = (0, 60, 120, 250)       # ★ 任务里点名的四个
STARTS_DENSE = tuple(range(0, 781, 20))   # ★ 上界扫描:0..780,每 20 个交易日一个
# 780 的来历:池子 2014-01-02 起共 3018 个交易日,可比窗口从第 1008 个
# (2018-01-02)开始;日线口径预热需要 150+50+20 = 220 个交易日,
# 1008-220 = 788 → 取 780 作整。再往后切,2018 年初就出不了标签了。


# ============================================================================
# 一 · 标签构造(和上一轮逐行一致)+ 换起点版
# ============================================================================

def _downgrade_transition(lab: np.ndarray, events: list[dict]) -> np.ndarray:
    """★ 和上一轮一字不差:生产三路径放不行的阶段二降级成 transition。"""
    arr = lab.copy()
    for k, ev in enumerate(events):
        _f, _g, ok, _lab = tri._topology(ev)
        if ev["stage"] == "2" and not ok:
            j = events[k + 1]["i"] if k + 1 < len(events) else len(lab)
            seg = arr[ev["i"]:j]
            arr[ev["i"]:j] = np.where(seg == tri.WARMUP, tri.WARMUP, "transition")
    return arr


def daily_labels(cl_col: np.ndarray, offset: int = 0
                 ) -> tuple[np.ndarray, np.ndarray, list[dict]]:
    """
    日线 150 个**交易日**口径的阶段标签,从第 offset 个交易日起算。

    返回 (label 全长数组, raw 全长数组, events)。
    ★ offset 之前的位置填 None(= 这个起点下根本没有数据,不可比)。
    """
    n = len(cl_col)
    sub = cl_col[offset:]
    ma = pd.Series(sub).rolling(150, min_periods=150).mean().to_numpy()
    raw = prev.raw_stage_bars(sub, ma, SPEC.flat_thr, 10 * tri.WEEK, 10.0)
    lab, events = tri._confirm_sequence(raw, SPEC.min_bars)
    lab = _downgrade_transition(lab, events)

    full_lab = np.full(n, None, dtype=object)
    full_raw = np.full(n, None, dtype=object)
    full_lab[offset:] = lab
    full_raw[offset:] = raw
    ev = [{"i": int(e["i"]) + offset, "stage": e["stage"],
           "prev": e["prev"], "prev2": e["prev2"]} for e in events]
    return full_lab, full_raw, ev


def weekly_labels(wk_col: np.ndarray, idx_w, idx_d, offset_weeks: int = 0
                  ) -> np.ndarray:
    """周线 30 根 bar 口径,铺回日线格(和上一轮逐行一致)。"""
    sub = wk_col[offset_weeks:]
    ma = pd.Series(sub).rolling(30, min_periods=30).mean().to_numpy()
    raw = prev.raw_stage_bars(sub, ma, SPEC.flat_thr, 10, 10.0)
    lab, events = tri._confirm_sequence(raw, 4)
    lab = _downgrade_transition(lab, events)
    full = np.full(len(wk_col), None, dtype=object)
    full[offset_weeks:] = lab
    ser = pd.Series(full, index=idx_w).reindex(idx_d, method="ffill")
    return ser.to_numpy(dtype=object)


# ============================================================================
# 零 · 复算对账 —— ★ 对不上就停
# ============================================================================

def reconcile(cl: pd.DataFrame, syms: list[str]) -> dict:
    """复现上一轮的 90.50% / 86.42% / 134294 / 10850 / 10258。对不上 → raise。"""
    idx_d = cl.index
    wk = prev.weekly_close(cl)
    idx_w = wk.index
    keep = np.asarray(idx_d >= pd.Timestamp(tri.START))

    tot_cmp = tot_same = 0
    both = od = ow = 0
    for s in syms:
        d, _raw, _ev = daily_labels(cl[s].to_numpy(), 0)
        w = weekly_labels(wk[s].to_numpy(), idx_w, idx_d, 0)
        m = keep & (d != tri.WARMUP) & (w != tri.WARMUP) & (d != None) & (w != None)  # noqa: E711
        tot_cmp += int(m.sum())
        tot_same += int((m & (d == w)).sum())
        ia = (d == "2") & m
        ib = (w == "2") & m
        both += int((ia & ib).sum())
        od += int((ia & ~ib).sum())
        ow += int((ib & ~ia).sum())

    five = round(tot_same / max(1, tot_cmp), 4)
    jac = round(both / max(1, both + od + ow), 4)
    out = {
        "可比格子": tot_cmp,
        "全五档一致率(本轮)": five, "上一轮报的": 0.9050,
        "阶段二二值 Jaccard(本轮)": jac, "上一轮报的 ": 0.8642,
        "逐位(本轮)": [both, od, ow], "上一轮报的  ": [134294, 10850, 10258],
        "不一致格子数(本轮)": tot_cmp - tot_same, "上一轮报的   ": 54313,
    }
    bad = []
    if five != 0.9050:
        bad.append(f"全五档一致率 {five} != 0.9050")
    if jac != 0.8642:
        bad.append(f"Jaccard {jac} != 0.8642")
    if [both, od, ow] != [134294, 10850, 10258]:
        bad.append(f"逐位 {[both, od, ow]} != [134294, 10850, 10258]")
    if tot_cmp - tot_same != 54313:
        bad.append(f"不一致格子 {tot_cmp - tot_same} != 54313")
    if bad:
        raise RuntimeError("★★ 复算对不上上一轮,停下来查,不往下跑:\n  "
                           + "\n  ".join(bad))
    out["结论"] = "★ 逐位对上 → 本轮标签和上一轮同源,数字可比"
    return out


# ============================================================================
# 二 · 问题一:换起点重算,阶段号会变吗
# ============================================================================

def restart_test(cl: pd.DataFrame, syms: list[str], starts: tuple[int, ...]
                 ) -> dict:
    """
    ★★★ 核心测试:同一只票、同一交易日、同一份 raw,起点不同 → 阶段号会不同吗。

    只在「全部起点都已出标签(非 WARMUP / 非 None)」的格子上比。
    """
    idx_d = cl.index
    keep = np.asarray(idx_d >= pd.Timestamp(tri.START))

    n_cmp = n_diff = 0
    n_dropped = 0
    pair_ctr: Counter = Counter()          # (基线标签, 另一起点标签) → 格子数
    base_ctr: Counter = Counter()          # 基线标签 → 可比格子数
    base_diff_ctr: Counter = Counter()     # 基线标签 → 会变的格子数
    sym_diff: Counter = Counter()
    year_diff: Counter = Counter()
    year_cmp: Counter = Counter()
    fragile: dict[str, np.ndarray] = {}    # 每票:这一格是否随起点改变(全长布尔)
    years = np.asarray(idx_d.year)

    for s in syms:
        labs = []
        for o in starts:
            lab, _raw, _ev = daily_labels(cl[s].to_numpy(), o)
            labs.append(lab)
        base = labs[0]
        ok = keep & (base != tri.WARMUP) & (base != None)        # noqa: E711
        for lab in labs[1:]:
            ok = ok & (lab != tri.WARMUP) & (lab != None)        # noqa: E711
        n_dropped += int((keep & (base != tri.WARMUP) & (base != None)).sum()   # noqa: E711
                         - ok.sum())
        diff = np.zeros(len(base), dtype=bool)
        for lab in labs[1:]:
            d = ok & (base != lab)
            diff |= d
            if d.any():
                for t in np.flatnonzero(d):
                    pair_ctr[(str(base[t]), str(lab[t]))] += 1
        fragile[s] = diff
        n_cmp += int(ok.sum())
        n_diff += int(diff.sum())
        sym_diff[s] = int(diff.sum())
        for lv in ("1", "2", "3", "4", "transition"):
            m = ok & (base == lv)
            base_ctr[lv] += int(m.sum())
            base_diff_ctr[lv] += int((m & diff).sum())
        for y in np.unique(years):
            ym = years == y
            year_cmp[int(y)] += int((ok & ym).sum())
            year_diff[int(y)] += int((diff & ym).sum())

    return {
        "起点(交易日偏移)": list(starts),
        "可比格子(所有起点都已出标签)": n_cmp,
        "★★★ 阶段号随起点改变的格子": n_diff,
        "★★★ 占可比格子的比例": round(n_diff / max(1, n_cmp), 6),
        "因预热错位剔掉的格子": n_dropped,
        "按基线标签拆": {k: {"可比": base_ctr[k], "会变": base_diff_ctr[k],
                            "会变的比例": round(base_diff_ctr[k] / max(1, base_ctr[k]), 6)}
                        for k in ("1", "2", "3", "4", "transition")},
        "标签对(基线→另一起点)": {f"{a}→{b}": c for (a, b), c
                                  in pair_ctr.most_common(20)},
        "涉及几只票": int(sum(1 for v in sym_diff.values() if v > 0)),
        "最集中的 10 只票": dict(sym_diff.most_common(10)),
        "按自然年": {str(y): {"可比": year_cmp[y], "会变": year_diff[y],
                             "比例": round(year_diff[y] / max(1, year_cmp[y]), 6)}
                    for y in sorted(year_cmp)},
        "_fragile": fragile,
    }


def start_curve(cl: pd.DataFrame, syms: list[str]) -> dict:
    """
    ★★★ 逐起点曲线 + 「手上有多少交易日历史」校准曲线。

    这一节回答「问题一」真正的形状:不是「敏不敏感」,是**要多少历史才稳**。
      · 逐起点:每个起点单独和基线(起点 0)比,看从哪个起点开始才出现变号
      · 校准:把每一格按「算它的时候手上有多少个**交易日**的历史」分桶,
              报该桶里阶段号和全历史不同的比例。
        ★ 两套分桶都报:全部格子 / 只看走平格子(label ∈ {1,3})。
    """
    idx_d = cl.index
    keep = np.asarray(idx_d >= pd.Timestamp(tri.START))
    base = {}
    for s in syms:
        base[s], _r, _e = daily_labels(cl[s].to_numpy(), 0)

    BK = ((0, 250), (250, 400), (400, 550), (550, 700), (700, 1000),
          (1000, 10 ** 9))
    rows = []
    c_all = {b: 0 for b in BK}
    w_all = {b: 0 for b in BK}
    c_fl = {b: 0 for b in BK}
    w_fl = {b: 0 for b in BK}

    for o in STARTS_DENSE:
        ncmp = ndiff = 0
        for s in syms:
            lab, _r, _e = daily_labels(cl[s].to_numpy(), o)
            b = base[s]
            ok = (keep & (b != tri.WARMUP) & (b != None)                # noqa: E711
                  & (lab != tri.WARMUP) & (lab != None))                # noqa: E711
            d = ok & (b != lab)
            ncmp += int(ok.sum())
            ndiff += int(d.sum())
            if o == 0:
                continue
            flat = ok & np.isin(lab.astype(str), ["1", "3"])
            hist = np.arange(len(b)) - o          # ★ 这一格当时手上有多少交易日历史
            for lo, hi in BK:
                m1 = ok & (hist >= lo) & (hist < hi)
                c_all[(lo, hi)] += int(m1.sum())
                w_all[(lo, hi)] += int((m1 & d).sum())
                m2 = flat & (hist >= lo) & (hist < hi)
                c_fl[(lo, hi)] += int(m2.sum())
                w_fl[(lo, hi)] += int((m2 & d).sum())
        rows.append({"起点偏移(交易日)": o, "可比格子": ncmp,
                     "与基线不同的格子": ndiff,
                     "比例": round(ndiff / max(1, ncmp), 6)})

    def _tab(c, w):
        return [{"手上历史(交易日)": f"{lo}~{hi if hi < 10**9 else '∞'}",
                 "格子": c[(lo, hi)], "阶段号与全历史不同": w[(lo, hi)],
                 "错号率": round(w[(lo, hi)] / max(1, c[(lo, hi)]), 4)}
                for lo, hi in BK]

    tot_fl = sum(c_fl.values())
    tot_fw = sum(w_fl.values())
    gates = []
    for N in (250, 400, 550, 700, 1000):
        f = sum(c_fl[(lo, hi)] for lo, hi in BK if hi <= N)
        w = sum(w_fl[(lo, hi)] for lo, hi in BK if hi <= N)
        gates.append({"判据": f"走平格子 + 手上历史 <{N} 个交易日 → 标「存疑」",
                      "覆盖率(占走平格子)": round(f / max(1, tot_fl), 4),
                      "标出的格子数": f,
                      "精确率(标出的里面真的错号)": round(w / max(1, f), 4),
                      "召回率": round(w / max(1, tot_fw), 4)})
    return {
        "逐起点(每个起点单独和起点 0 比)": rows,
        "★ 第一次出现变号的起点": next((r["起点偏移(交易日)"] for r in rows
                                       if r["与基线不同的格子"] > 0), None),
        "校准曲线_全部格子": _tab(c_all, w_all),
        "★★★ 校准曲线_只看走平格子": _tab(c_fl, w_fl),
        "走平格子合计(所有起点累计)": tot_fl, "其中错号": tot_fw,
        "基线错号率": round(tot_fw / max(1, tot_fl), 4),
        "★★★ 判据(只用当天和历史,无未来)": gates,
    }


def weekly_restart(cl: pd.DataFrame, syms: list[str]) -> dict:
    """
    ★★ 周线口径也做一遍换起点 —— 这一节专门为了**回答上一轮**:
    上一轮那 65% 的「真分歧」是 1↔3 这一对。如果周线口径在**实际起点**
    (2014)上就已经对起点敏感,那上一轮的真分歧里会混进「实现不稳」的成分。
    跑完就能说清:是不是。
    """
    idx_d = cl.index
    wk = prev.weekly_close(cl)
    idx_w = wk.index
    keep = np.asarray(idx_d >= pd.Timestamp(tri.START))
    base = {s: weekly_labels(wk[s].to_numpy(), idx_w, idx_d, 0) for s in syms}
    rows = []
    frag_tot = 0
    frag = {s: np.zeros(len(idx_d), dtype=bool) for s in syms}
    for o in range(0, 157, 8):              # ★ 单位:**周线 bar**
        ncmp = ndiff = 0
        for s in syms:
            lab = weekly_labels(wk[s].to_numpy(), idx_w, idx_d, o)
            b = base[s]
            ok = (keep & (b != tri.WARMUP) & (b != None)                # noqa: E711
                  & (lab != tri.WARMUP) & (lab != None))                # noqa: E711
            d = ok & (b != lab)
            frag[s] |= d
            ncmp += int(ok.sum())
            ndiff += int(d.sum())
        rows.append({"起点偏移(周线 bar)": o, "可比格子": ncmp,
                     "与基线不同": ndiff,
                     "比例": round(ndiff / max(1, ncmp), 6)})
    frag_tot = int(sum(int(v.sum()) for v in frag.values()))
    first = next((r["起点偏移(周线 bar)"] for r in rows if r["与基线不同"] > 0), None)
    return {
        "周线 bar 总数": len(idx_w),
        "逐起点": rows,
        "★ 第一次出现变号的起点(周线 bar)": first,
        "任一起点下变号的格子合计": frag_tot,
        "★★★ 对上一轮的意思": (
            f"周线口径在起点偏移 <{first} 根周线 bar 之内**一格都不变**。"
            "实际起点(2014-01-02,可比窗口前有约 208 根周线 bar)远在这个门槛的"
            "安全侧 → ★ 上一轮那 65% 的 1↔3「真分歧」**不是**实现不稳造成的,"
            "是两套口径各自的已确认历史**真的不一样**。上一轮的读法成立。"
            if first else "全窗口内零变号"),
    }


def noprev_cells(cl: pd.DataFrame, syms: list[str]) -> dict:
    """
    ★★★ 最危险的一类:`prev is None` 的阶段一 ——
    代码在「没有任何已确认历史」时把走平默认编成**阶段一(底部,该买)**。
    这不是「判断」,是**缺省值**;而缺省方向是「买」。
    """
    idx_d = cl.index
    keep = np.asarray(idx_d >= pd.Timestamp(tri.START))
    per_sym: Counter = Counter()
    dates: list = []
    for s in syms:
        lab, _raw, ev = daily_labels(cl[s].to_numpy(), 0)
        ev_i = np.array([e["i"] for e in ev], dtype=int)
        for t in np.flatnonzero(keep & (lab != tri.WARMUP) & (lab != None)):  # noqa: E711
            if str(lab[t]) != "1":
                continue
            k = int(np.searchsorted(ev_i, t, side="right")) - 1
            if k >= 0 and ev[k]["prev"] is None:
                per_sym[s] += 1
                dates.append(idx_d[t])
    dd = pd.Series(dates)
    return {
        "★ 机制": "_confirm_sequence 里 FLAT 确认时:last=='2'→3 / "
                 "last in ('1','3')→保持 / ★ else(含 last is None)→**1**。"
                 "所以「没有历史」和「历史是阶段四」走的是同一条分支,都编成阶段一。",
        "★★★ 格子数": int(sum(per_sym.values())),
        "占走平格子": None,       # 由 main 填(需要 flat 的分母)
        "涉及票数": len(per_sym),
        "最集中 10 只": dict(per_sym.most_common(10)),
        "日期范围": [str(dd.min().date()), str(dd.max().date())] if len(dd) else [],
        "中位日期": str(dd.median().date()) if len(dd) else None,
        "按自然年": {str(k): int(v) for k, v in
                    dd.dt.year.value_counts().sort_index().items()} if len(dd) else {},
    }


# ============================================================================
# 三 · 问题二:顶底混淆到什么程度
# ============================================================================

def flat_anatomy(cl: pd.DataFrame, syms: list[str],
                 fragile: dict[str, np.ndarray]) -> dict:
    """
    走平格子的解剖:
      ① 阶段号(一 or 三)靠路径定的占多少
      ② 其中「刚从长期趋势里出来、方向还没确立」的占多少
      ③ 每一格的诊断量(给问题三当特征用)
    """
    idx_d = cl.index
    keep = np.asarray(idx_d >= pd.Timestamp(tri.START))

    tot_cmp = 0
    cnt_label13 = 0            # label ∈ {1,3}
    cnt_raw_flat_now = 0       # 今天 raw==FLAT 且 label ∈ {1,3}
    cnt_lab3 = cnt_lab1 = 0
    cnt_path_carried = 0       # ★ 换掉已确认前缀就会变号的(= label 3,或 1 但前序是 3 链)
    cnt_1_from_4 = cnt_1_from_none = cnt_1_from_13 = 0
    cnt_3_from_2 = 0
    fresh: dict[int, int] = {20: 0, 40: 0, 60: 0}      # 长期趋势刚结束 N 交易日内
    fresh_long: dict[int, int] = {20: 0, 40: 0, 60: 0}
    diag_rows: list[tuple] = []        # (sym, t, label, 距确认的交易日, 距上次趋势确认, 前序趋势长度, fragile)

    LONG_TREND = 60            # ★「长期趋势」门槛:已确认的阶段二/四 ≥60 个**交易日**

    for s in syms:
        lab, raw, events = daily_labels(cl[s].to_numpy(), 0)
        frg = fragile[s]
        ok = keep & (lab != tri.WARMUP) & (lab != None)          # noqa: E711
        tot_cmp += int(ok.sum())

        # 每格归属到哪个已确认事件
        ev_i = np.array([e["i"] for e in events], dtype=int)
        ev_stage = [e["stage"] for e in events]
        ev_prev = [e["prev"] for e in events]
        # 事件 k 的持续长度(交易日)= 下一个事件下标 - 本事件下标
        ev_len = [(ev_i[k + 1] if k + 1 < len(ev_i) else len(lab)) - ev_i[k]
                  for k in range(len(ev_i))]
        # 每个事件之前,最近一次已确认的「趋势阶段」(2 或 4)的下标与长度
        last_trend_i: list[int | None] = []
        last_trend_len: list[int | None] = []
        cur_i = cur_len = None
        for k in range(len(ev_i)):
            last_trend_i.append(cur_i)
            last_trend_len.append(cur_len)
            if ev_stage[k] in ("2", "4"):
                cur_i, cur_len = int(ev_i[k]), int(ev_len[k])

        for t in np.flatnonzero(ok):
            L = str(lab[t])
            if L not in ("1", "3"):
                continue
            cnt_label13 += 1
            if raw[t] == "FLAT":
                cnt_raw_flat_now += 1
            k = int(np.searchsorted(ev_i, t, side="right")) - 1
            if k < 0:
                continue
            prev_stage = ev_prev[k]
            since_conf = int(t - ev_i[k])
            lt_i, lt_len = last_trend_i[k], last_trend_len[k]
            since_trend = int(t - lt_i) if lt_i is not None else -1
            if L == "3":
                cnt_lab3 += 1
                cnt_path_carried += 1
                if prev_stage == "2":
                    cnt_3_from_2 += 1
            else:
                cnt_lab1 += 1
                if prev_stage == "4":
                    cnt_1_from_4 += 1
                elif prev_stage is None:
                    cnt_1_from_none += 1
                elif prev_stage in ("1", "3"):
                    cnt_1_from_13 += 1
            # ★「刚从长期趋势里出来」:本次走平确认后 N 个交易日内,
            #   且紧前面那个已确认阶段是趋势阶段(2/4)
            if prev_stage in ("2", "4"):
                plen = int(ev_len[k - 1]) if k >= 1 else 0
                for N in fresh:
                    if since_conf <= N:
                        fresh[N] += 1
                        if plen >= LONG_TREND:
                            fresh_long[N] += 1
            diag_rows.append((s, int(t), L, since_conf, since_trend,
                              int(ev_len[k - 1]) if k >= 1 else 0,
                              bool(frg[t])))

    return {
        "可比格子": tot_cmp,
        "★★ label ∈ {一,三} 的格子(= 走平被确认)": cnt_label13,
        "占可比格子": round(cnt_label13 / max(1, tot_cmp), 4),
        "其中今天 raw 也还是 FLAT 的": cnt_raw_flat_now,
        "其中今天 raw 已经不是 FLAT 了(阶段号还挂着)": cnt_label13 - cnt_raw_flat_now,
        "阶段三": cnt_lab3, "阶段一": cnt_lab1,
        "★★★ 一/三 之分完全由路径决定的格子": cnt_label13,
        "★★★ 占走平格子": 1.0,
        "★ 其中「若把已确认前缀清空就会变号」的(= 全部阶段三)": cnt_path_carried,
        "★ 占走平格子": round(cnt_path_carried / max(1, cnt_label13), 4),
        "阶段三的前序": {"前序=阶段二": cnt_3_from_2,
                        "前序≠阶段二(靠 1/3 继承链)": cnt_lab3 - cnt_3_from_2},
        "阶段一的前序": {"前序=阶段四": cnt_1_from_4, "前序=无(序列开头)": cnt_1_from_none,
                        "前序=阶段一/三(继承)": cnt_1_from_13},
        "★★★ 刚从趋势里出来 N 个交易日内的走平格子": {
            str(N): {"格子": fresh[N], "占走平格子": round(fresh[N] / max(1, cnt_label13), 4),
                     "其中前序趋势≥60 个交易日(长期趋势)": fresh_long[N],
                     "占走平格子": round(fresh_long[N] / max(1, cnt_label13), 4)}
            for N in sorted(fresh)},
        "「长期趋势」门槛": f"{LONG_TREND} 个**交易日**(★ 我们填的,不是原著)",
        "_diag": diag_rows,
    }


# ============================================================================
# 四 · 问题二之三:编反了对 技-3 有多大影响
# ============================================================================

LEDGER_DIR = os.path.join(_REPO, "engine", "ledgers_1029_技术派六条三版")
RES_JSON = os.path.join(_REPO, "engine", "results_1029_技术派六条三版.json")


def tech3_dependency() -> dict:
    """
    ★★★ 第一问:技-3 到底读不读 状-2 的阶段号。
    用**运行时哨兵**证明(不是只靠 grep):把 tri 里出阶段号的三个函数全换成
    「一被调用就抛异常」,然后把 技-3 七条配置的进场/离场算子全跑一遍。
    跑得通 → 这条链上根本没碰过阶段号。
    """
    import copy
    from engine import chain, data, pat6_ops                      # noqa: WPS433
    from engine.pat6_run import signal_funnel                     # noqa: WPS433
    import yaml                                                   # noqa: WPS433

    tripped: list[str] = []

    def _tripwire(name):
        def f(*a, **k):
            tripped.append(name)
            raise AssertionError(f"★ 技-3 调到了 状-2 的 {name}")
        return f

    pat6_ops.install()        # ★ 技-3 的算子是运行时挂钩上去的,不装就跑不了
    saved = {n: getattr(tri, n) for n in ("_raw_stage", "_confirm_sequence",
                                          "run_stage")}
    cfgs = ["技-3-原著.yaml", "技-3-原著-底盘9周.yaml", "技-3-原著-机械日线.yaml",
            "技-3-行业.yaml", "技-3-XING.yaml"]
    out = {}
    syms = cache.symbols()
    try:
        for n in saved:
            setattr(tri, n, _tripwire(n))
        for c in cfgs:
            raw = yaml.safe_load(open(os.path.join(_REPO, "engine", "configs", c),
                                      encoding="utf-8"))
            cfg = chain.ChainConfig.from_dict(copy.deepcopy(raw))
            res = chain.run_chain(cfg, syms)
            led = res.ledger
            fn = signal_funnel(raw, [s for s in syms if s in cache.symbols()],
                               data.PERF_START)
            steps = fn.get("逐关") or []
            out[c] = {"笔数": int(len(led)),
                      "★ 信号数(漏斗末关累计)": steps[-1]["累计"] if steps else None,
                      "每笔R净": round(float(led["r_multiple_net"].mean()), 6)
                      if len(led) else None,
                      "_ledger": led}
    finally:
        for n, f in saved.items():
            setattr(tri, n, f)

    return {
        "★ 这一节干什么": "运行时哨兵:把 状-2 出阶段号的三个函数换成「一调用就抛」,"
                          "再把 技-3 的五份配置整链跑一遍。跑得通 = 这条链没碰阶段号。",
        "哨兵被触发": tripped,
        "结论": ("★★★ 技-3 五份配置全链跑通,一次都没调到 状-2 的阶段号 —— "
                 "技-3 **不消费**阶段号" if not tripped
                 else f"★★ 哨兵被触发:{tripped}"),
        "各配置实跑": out,
    }


def tech3_counterfactual(cl: pd.DataFrame, syms: list[str],
                         fragile: dict[str, np.ndarray],
                         ledgers: dict[str, pd.DataFrame]) -> dict:
    """
    ★★ 第二问(反事实):假如 技-3 **真的**按原著那样用阶段号做闸门
    (只在阶段一/二买),那把一↔三翻过来,每笔 R 会变成多少。
    ★ 这是「假如」,不是现状 —— 现状见 tech3_dependency()。
    """
    idx_d = cl.index
    pos = {d: i for i, d in enumerate(idx_d)}
    labels: dict[str, np.ndarray] = {}
    for s in syms:
        lab, _raw, _ev = daily_labels(cl[s].to_numpy(), 0)
        labels[s] = lab

    res = json.load(open(RES_JSON, encoding="utf-8"))
    sig = {}
    for r in res["各版结果"]:
        if "技-3" in r["报表名"]:
            f = r.get("信号漏斗") or {}
            steps = f.get("逐关") or []
            sig[r["报表名"]] = {"笔数": r["笔数"], "每笔R净": r["每笔R净"],
                               "信号数": steps[-1]["累计"] if steps else None}

    out = {}
    for fn, led0 in ledgers.items():
        led = led0.copy()
        led["entry_date"] = pd.to_datetime(led["entry_date"])
        stg = []
        for s, d in zip(led["symbol"], led["entry_date"]):
            t = pos.get(pd.Timestamp(d))
            stg.append(str(labels[s][t]) if (t is not None and s in labels) else "NA")
        led = led.assign(进场日阶段号=stg)
        frg = []
        for s, d in zip(led["symbol"], led["entry_date"]):
            t = pos.get(pd.Timestamp(d))
            frg.append(bool(fragile[s][t]) if (t is not None and s in fragile) else False)
        led = led.assign(阶段号随起点变=frg)

        def _r(sub):
            return (round(float(sub["r_multiple_net"].mean()), 4)
                    if len(sub) else None)

        in12 = led[led["进场日阶段号"].isin(["1", "2"])]
        in3 = led[led["进场日阶段号"] == "3"]
        # ★ 翻转:原本 1 的变 3(被挡掉)、原本 3 的变 1(被放进来)
        flip = led[led["进场日阶段号"].isin(["3", "2"])]
        out[fn] = {
            "全部笔数": int(len(led)),
            "全部每笔R净": _r(led),
            "进场日阶段号分布": led["进场日阶段号"].value_counts().to_dict(),
            "阶段号随起点会变的笔数": int(led["阶段号随起点变"].sum()),
            "★ 若按阶段一/二闸门(真标签)": {"笔数": int(len(in12)), "每笔R净": _r(in12)},
            "★ 若按阶段一/二闸门(一↔三翻转后)": {"笔数": int(len(flip)),
                                                "每笔R净": _r(flip)},
            "顺带:进场日在阶段三的": {"笔数": int(len(in3)), "每笔R净": _r(in3)},
        }
    return {"★ 这一节是「假如」": "技-3 现状不读阶段号(见上一节)。本节测的是"
                                 "**假如**按原著在阶段号上加闸门,翻转一↔三的后果。",
            "★ 台账出处": "本轮现跑(和上一节哨兵同一次 run_chain),不是读 1029 的 csv",
            "1029 那一轮报的笔数/每笔R/信号数(出处 results_1029_技术派六条三版.json,"
            "★ 供对账用;缓存 10-29 16:45 重建过,所以不是每一条都对得上)": sig,
            "逐配置": out}


# ============================================================================
# 五 · 问题三:运行时能不能认出「这一格阶段号不可靠」
# ============================================================================

def runtime_flag(diag: list[tuple]) -> dict:
    """
    判据候选都只用**当天和历史**:
      甲:距本次走平确认 ≤N 个交易日,且前序是趋势阶段 → 存疑
      乙:距上一次已确认的趋势阶段(2/4)> R 个交易日 → 存疑(= 1/3 继承链太长)
      丙:本票自起点以来还没确认过任何趋势阶段 → 存疑
      丁:甲 or 丙
    真值(ground truth)= 该格阶段号在换起点扫描下**真的**变过。
    """
    rows = [r for r in diag]          # (sym,t,L,since_conf,since_trend,prev_len,frg)
    n = len(rows)
    y = np.array([r[6] for r in rows], dtype=bool)
    since_conf = np.array([r[3] for r in rows])
    since_trend = np.array([r[4] for r in rows])      # -1 = 从没确认过趋势阶段
    out = {"走平格子总数": n, "其中真的随起点变过(真值为正)": int(y.sum()),
           "真值正例率(基线)": round(float(y.mean()), 6)}

    def _score(pred: np.ndarray, name: str) -> dict:
        tp = int((pred & y).sum())
        return {"判据": name, "覆盖率(标出多少格)": round(float(pred.mean()), 4),
                "标出的格子数": int(pred.sum()),
                "精确率(标出的里面真的有问题)": round(tp / max(1, int(pred.sum())), 4),
                "召回率(真有问题的里面标出了多少)": round(tp / max(1, int(y.sum())), 4)}

    cands = []
    for N in (20, 40, 60, 120):
        cands.append(_score(since_conf <= N, f"甲:距走平确认 ≤{N} 个交易日"))
    for R in (60, 120, 250, 500):
        cands.append(_score(since_trend > R, f"乙:距上次已确认趋势阶段 >{R} 个交易日"))
    cands.append(_score(since_trend < 0, "丙:自起点以来没确认过任何趋势阶段"))
    cands.append(_score((since_trend < 0) | (since_conf <= 60),
                        "丁:丙 或 距走平确认 ≤60 个交易日"))
    out["候选判据"] = cands
    best = max(cands, key=lambda c: c["精确率(标出的里面真的有问题)"])
    out["★ 精确率最高的候选"] = best
    return out


# ============================================================================
def main() -> int:
    t0 = time.time()
    commit = subprocess.run(["git", "rev-parse", "HEAD"], cwd=_REPO,
                            capture_output=True, text=True).stdout.strip()
    p = cache.load()
    cl = p["close"]
    syms = list(cl.columns)
    print(f"池子 {len(syms)} 只 × {len(cl)} 个交易日 "
          f"({cl.index[0].date()} ~ {cl.index[-1].date()})")

    print("零 · 复算对账 …")
    rec = reconcile(cl, syms)
    print("   " + rec["结论"])

    print("一 · 换起点重算(任务点名的四个起点)…")
    r_req = restart_test(cl, syms, STARTS_REQUIRED)
    print(f"   随起点改变:{r_req['★★★ 阶段号随起点改变的格子']} / "
          f"{r_req['可比格子(所有起点都已出标签)']} = "
          f"{r_req['★★★ 占可比格子的比例']:.4%}")

    print(f"一' · 换起点重算(密扫 {len(STARTS_DENSE)} 个起点,求上界)…")
    r_dense = restart_test(cl, syms, STARTS_DENSE)
    print(f"   随起点改变:{r_dense['★★★ 阶段号随起点改变的格子']} / "
          f"{r_dense['可比格子(所有起点都已出标签)']} = "
          f"{r_dense['★★★ 占可比格子的比例']:.4%}")

    frg = r_dense.pop("_fragile")
    r_req.pop("_fragile")

    print("一'' · 逐起点曲线 + 历史长度校准 …")
    curve = start_curve(cl, syms)
    print(f"   第一次出现变号的起点:{curve['★ 第一次出现变号的起点']} 个交易日")

    print("一''' · 周线口径换起点(为了回答上一轮)…")
    wkr = weekly_restart(cl, syms)
    print(f"   周线第一次出现变号的起点:"
          f"{wkr['★ 第一次出现变号的起点(周线 bar)']} 根周线 bar")

    print("二 · 走平格子解剖 …")
    flat = flat_anatomy(cl, syms, frg)
    diag = flat.pop("_diag")

    print("二''' · 「没有历史 → 默认编成阶段一」那一类 …")
    npv = noprev_cells(cl, syms)
    npv["占走平格子"] = round(
        npv["★★★ 格子数"] / max(1, flat["★★ label ∈ {一,三} 的格子(= 走平被确认)"]), 4)

    print("二' · 技-3 依赖性(运行时哨兵)…")
    try:
        dep = tech3_dependency()
    except Exception as e:                                        # noqa: BLE001
        dep = {"★ 跑挂了": f"{type(e).__name__}: {e}"}
    print("   " + str(dep.get("结论", dep)))

    print("二'' · 技-3 反事实(假如用阶段号当闸门)…")
    leds = {k: v.pop("_ledger") for k, v in (dep.get("各配置实跑") or {}).items()}
    cf = (tech3_counterfactual(cl, syms, frg, leds) if leds
          else {"★ 跑不了": "上一节没拿到台账"})

    print("三 · 运行时判据 …")
    rt = runtime_flag(diag)

    res = {
        "git_commit": commit,
        "池子": f"{len(syms)} 只 × {len(cl)} 个交易日",
        "可比窗口": f"{tri.START} 起,2,011 个交易日",
        "时间尺度声明": TIME_SCALE,
        "★★ 字段含义声明(我是这样理解的,可反驳)": FIELD_SEMANTICS,
        "零_复算对账": rec,
        "一_换起点_四个起点": r_req,
        "一_换起点_密扫上界": r_dense,
        "一_逐起点曲线与历史长度校准": curve,
        "一_周线口径换起点": wkr,
        "二_走平格子解剖": flat,
        "二_没有历史就默认编成阶段一": npv,
        "二_技-3依赖性": dep,
        "二_技-3反事实": cf,
        "三_运行时判据": rt,
        "本文件自己填的口径": MY_NOTES,
        "耗时秒": round(time.time() - t0, 1),
    }
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2, default=str)
    print(f"写出 {OUT_JSON}(用了 {res['耗时秒']} 秒)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
