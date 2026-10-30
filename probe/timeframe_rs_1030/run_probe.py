"""
验两个假设:① 状-2 是不是「用日线算了一个周线定义的东西」
            ② 状-5 相对强度算不出来,是不是因为我们选的算法结构上稀疏

================================================================================
三秒版
================================================================================
一句话:**只换时间框架和算法结构,一个阈值都不调**,看「说不清 / 算不出」
       的占比会不会掉下来。掉下来 → 是口径选错;不掉 → 是判据本身没用。

★ 硬纪律(本文件逐条守着):
  一、不改任何现有实现 —— 全部新增一档,旧的原样留着当对照。
  二、不改 matrices.py / chain.py / config_adapter.py —— 本文件只 import,不写回。
  三、串行跑。
  四、阈值一个都不动:周线版用的走平阈值就是配置里 XING 版那个 0.5%/周。
  五、凡「天」「周」一律写明是交易日还是自然周。

跑法:python3 probe/timeframe_rs_1030/run_probe.py
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

import numpy as np
import pandas as pd

_REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _REPO)

from engine import cache, data                                   # noqa: E402
from engine import state_axis_tri_1029 as tri                     # noqa: E402
from engine.checks import constant_output as co                   # noqa: E402

OUT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "results_1030_周线与原著RS.json")

# ============================================================================
# ★ 本文件自己填的口径登记簿 —— 凡是「原著/配置都没给、但代码必须有答案」的
# ============================================================================

MY_NOTES: list[str] = []


def _note(s: str) -> None:
    if s not in MY_NOTES:
        MY_NOTES.append(s)


# ---------------------------------------------------------------------------
# 时间尺度声明 —— ★ 第三条检查(time_scale_unit)要求的那种显式声明
# ---------------------------------------------------------------------------
TIME_SCALE = {
    "日线版的「150 日」": "150 个**交易日**(不是自然日)",
    "日线版走平的测量窗口「10 周」": "10 × 5 = 50 个**交易日**",
    "日线版最短持续「4 周」": "4 × 5 = 20 个**交易日**",
    "周线版的「30 周」": "30 根**周线 bar**(= 30 个自然周,有交易的周才成 bar)",
    "周线版走平的测量窗口「10 周」": "10 根**周线 bar**",
    "周线版最短持续「4 周」": "4 根**周线 bar**",
    "周线 bar 的收盘定义": "该自然周内**最后一个有交易的日线收盘**"
                           "(通常是周五;遇假期/停牌则为该周最后一个交易日)",
    "状-5 回看期「24 个月」": "24 个**自然月**(pd.DateOffset(months=24))",
    "状-5 原著口径的 63/126/189/252": "**交易日**位移(≈3/6/9/12 个自然月)",
    "事件重合的容差「±4 周」": "±20 个**交易日**",
}


# ============================================================================
# 一 · 假设一:状-2 日线 150 日 vs 周线 30 周
# ============================================================================
#
# ★★ 先说一件必须先说的事(见报告第〇节):
#   「99.6% 落在 mixed」这个数**不是状-2 的**,是**状-3(Al Brooks)**的。
#   状-2 的输出里根本没有 mixed 这个取值(它的五个取值是 1/2/3/4/transition),
#   而 1029 实测状-2 XING 版的分布是 1=18.9% / 2=25.7% / 3=33.4% / 4=22.0% /
#   transition=0.02%。
#   → 这一节照样跑周线版(温斯坦原著确实是周线定义的,这个质疑本身成立),
#     但要回答的「一句话」问题必须换成:**周线口径下 transition(说不清)占多少**。

def weekly_close(cl: pd.DataFrame) -> pd.DataFrame:
    """
    日线收盘 → 周线收盘。★ 周线收盘 = 该自然周内最后一个**有交易的**日线收盘。

    用 resample("W-FRI").last():按自然周分箱、取箱内最后一个非 NaN。
    ★ 刻意不用 ffill 去填「整周没有数据」的空箱 —— 那种空箱是
      预热前 / 停牌 / 退市后,必须留成 NaN,不许当成「横着没动」。
    """
    return cl.resample("W-FRI").last()


_note("周线重采样用 pandas resample(\"W-FRI\").last():按自然周分箱、"
      "取箱内最后一个有交易日的收盘。整周无交易 → 该周 bar 为 NaN(不填充)。"
      "★ 这是【我们填的】工程口径,原著只说「看周线图」,没规定缺周怎么办。")


def raw_stage_bars(cl: np.ndarray, ma: np.ndarray, thr_per_week: float,
                   lag_bars: int, weeks_per_lag: float,
                   box_bars: int = 0, box_amp: float = 0.0) -> np.ndarray:
    """
    ★ tri._raw_stage 的「bar 数可调」版 —— 算术和它**逐行一致**,
      唯一的差别是走平斜率的回看长度用 bar 数传进来,而不是写死 10*WEEK。

    thr_per_week  : 走平阈值,单位 %/周(= 配置里 XING 版那个 0.5,不许改)
    lag_bars      : 斜率回看多少根 bar
    weeks_per_lag : 这 lag_bars 根 bar 等于多少周(日线 50 根 = 10 周;
                    周线 10 根 = 10 周)—— 用来把变化率折算成 %/周

    ★ 自测 _selftest_raw_equiv() 证明:日线参数下本函数 == tri._raw_stage。
    """
    n = len(cl)
    out = np.full(n, tri.WARMUP, dtype=object)
    slope = np.full(n, np.nan)
    if n > lag_bars:
        slope[lag_bars:] = (ma[lag_bars:] / ma[:-lag_bars] - 1.0) * 100.0 / weeks_per_lag

    if box_bars:
        s = pd.Series(cl)
        amp = (s.rolling(box_bars).max() - s.rolling(box_bars).min()
               ) / s.rolling(box_bars).mean()
        box_ok = (amp <= box_amp).to_numpy()
    else:
        box_ok = np.ones(n, dtype=bool)

    for i in range(n):
        if not (np.isfinite(cl[i]) and np.isfinite(ma[i]) and np.isfinite(slope[i])):
            continue
        sl = slope[i]
        if abs(sl) <= thr_per_week:
            out[i] = "FLAT" if box_ok[i] else "TRANS"
        elif sl > thr_per_week and cl[i] > ma[i]:
            out[i] = "ADV"
        elif sl < -thr_per_week and cl[i] < ma[i]:
            out[i] = "DEC"
        else:
            out[i] = "TRANS"
    return out


def _selftest_raw_equiv(cl: pd.DataFrame, syms: list[str]) -> dict:
    """★ 证明我这份 raw_stage_bars 在日线参数下和原实现逐格相同 —— 不然后面全白跑。"""
    spec = tri.STAGE_VERSIONS["XING版"]
    ma = cl.rolling(150, min_periods=150).mean()
    bad = 0
    tot = 0
    for s in syms[:40]:
        a = tri._raw_stage(cl[s].to_numpy(), ma[s].to_numpy(), spec)
        b = raw_stage_bars(cl[s].to_numpy(), ma[s].to_numpy(),
                           spec.flat_thr, 10 * tri.WEEK, 10.0)
        tot += len(a)
        bad += int((a != b).sum())
    return {"比了多少格": tot, "不一致的格子": bad,
            "结论": "逐格一致 → 我这份复制件忠实" if bad == 0 else "★★ 不一致,后面结论作废"}


def run_stage_two_timeframes(syms: list[str]) -> dict:
    """日线 150 日版 vs 周线 30 周版,并排跑。★ 阈值和拓扑规则完全不动。"""
    p = cache.load()
    cl = p["close"][syms]
    spec = tri.STAGE_VERSIONS["XING版"]          # ★ 走平 0.5%/周、最短持续 4 周

    res: dict = {
        "自测_复制件是否忠实": _selftest_raw_equiv(cl, syms),
        "阈值来源": {
            "走平阈值": f"{spec.flat_thr}%/周 —— 直接取 "
                        f"tri.STAGE_VERSIONS['XING版'].flat_thr,★ 一个数都没改",
            "最短持续": "4 周(日线 = 20 个交易日;周线 = 4 根周线 bar)",
            "阶段跳转": f"生产三路径 {tri.STAGE2_PATHS_PRODUCTION} + 左端截断放行,"
                        f"★ 两套口径用同一套,没分叉",
            "★ 走平阈值的口径属性": "【XING 填的】—— 温斯坦原著没给斜率阈值"
                                   "(v13 六附已确认)。本次只换时间框架,"
                                   "★ 刻意不调它。",
        },
    }

    # ---------------- 日线 150 日版(= 现行生产口径,原样跑) ----------------
    idx_d = cl.index
    keep_d = idx_d >= pd.Timestamp(tri.START)
    ma_d = cl.rolling(150, min_periods=150).mean()
    panel_d: dict[str, np.ndarray] = {}
    ev_d: list[dict] = []
    for s in syms:
        raw = raw_stage_bars(cl[s].to_numpy(), ma_d[s].to_numpy(),
                             spec.flat_thr, 10 * tri.WEEK, 10.0)
        daily, events = tri._confirm_sequence(raw, spec.min_bars)
        arr = daily.copy()
        for k, ev in enumerate(events):
            _f, _g, ok, lab = tri._topology(ev)
            if ev["stage"] == "2":
                j = events[k + 1]["i"] if k + 1 < len(events) else len(daily)
                if not ok:
                    seg = arr[ev["i"]:j]
                    arr[ev["i"]:j] = np.where(seg == tri.WARMUP, tri.WARMUP, "transition")
                elif idx_d[ev["i"]] >= pd.Timestamp(tri.START):
                    ev_d.append({"symbol": s, "date": idx_d[ev["i"]], "path": lab})
        panel_d[s] = arr[keep_d]

    # ---------------- 周线 30 周版 ----------------
    wk = weekly_close(cl)
    idx_w = wk.index
    keep_w = idx_w >= pd.Timestamp(tri.START)
    ma_w = wk.rolling(30, min_periods=30).mean()          # ★ 30 根周线 bar
    panel_w: dict[str, np.ndarray] = {}
    ev_w: list[dict] = []
    panel_w_on_daily: dict[str, np.ndarray] = {}
    for s in syms:
        raw = raw_stage_bars(wk[s].to_numpy(), ma_w[s].to_numpy(),
                             spec.flat_thr, 10, 10.0)      # 10 根周线 bar = 10 周
        weekly, events = tri._confirm_sequence(raw, 4)     # 最短持续 4 根周线 bar
        arr = weekly.copy()
        for k, ev in enumerate(events):
            _f, _g, ok, lab = tri._topology(ev)
            if ev["stage"] == "2":
                j = events[k + 1]["i"] if k + 1 < len(events) else len(weekly)
                if not ok:
                    seg = arr[ev["i"]:j]
                    arr[ev["i"]:j] = np.where(seg == tri.WARMUP, tri.WARMUP, "transition")
                elif idx_w[ev["i"]] >= pd.Timestamp(tri.START):
                    ev_w.append({"symbol": s, "date": idx_w[ev["i"]], "path": lab})
        panel_w[s] = arr[keep_w]
        # ★ 为了和日线逐格比,把周线标签铺回日线格:一周的标签管这一周
        #   （用周线 bar 日期当右端,ffill 到下一根 bar 之前)
        ser = pd.Series(arr, index=idx_w).reindex(idx_d, method="ffill")
        panel_w_on_daily[s] = ser.to_numpy(dtype=object)[keep_d]

    res["日线150日版"] = tri.distribution(panel_d, tri.STAGE_STATES)
    res["日线150日版"]["单位"] = "票 × **交易日**"
    res["周线30周版"] = tri.distribution(panel_w, tri.STAGE_STATES)
    res["周线30周版"]["单位"] = "票 × **周线 bar**(自然周)"
    res["周线30周版_铺回日线格"] = tri.distribution(panel_w_on_daily, tri.STAGE_STATES)
    res["周线30周版_铺回日线格"]["单位"] = "票 × **交易日**(周线标签 ffill 到日线)"

    # ---------------- 复算 v13 那个 19.1% 重合 ----------------
    res["阶段二重合_复算"] = stage2_overlap(ev_d, ev_w, panel_d, panel_w_on_daily)
    return res


def stage2_overlap(ev_d: list[dict], ev_w: list[dict],
                   panel_d: dict, panel_w_on_daily: dict) -> dict:
    """
    ★ 复算 v13 八附 8.2 那个「各自标记 328 个点,只有 89 个重合 = 19.1%」。

    ★★ v13 **没写**它的「重合」是怎么配对的 —— 是同日同票?还是允许几天误差?
      所以这里给两种算法,两个数都报,★ 并且写明容差是我们填的:
        口径甲(事件级,±4 周容差):两边各自的阶段二确认点,
                同一只票、日期相差 ≤20 个交易日 → 算一次重合。配对是一对一贪心。
        口径乙(逐格级,无容差):逐票逐交易日比「当天是不是阶段二」,
                算 Jaccard = 两边都是 / 至少一边是。
    """
    out: dict = {
        "★ 容差口径属性": "±4 周(20 个交易日)这个容差是【我们填的】—— "
                          "v13 没说它的重合是怎么配对的。无容差的数另给(口径乙)。",
        "两边各自标记了多少个阶段二确认点(2018 起,已过拓扑闸)": {
            "日线150日版": len(ev_d), "周线30周版": len(ev_w)},
    }

    # 口径甲:事件级一对一贪心配对
    by_sym_w: dict[str, list[pd.Timestamp]] = {}
    for e in ev_w:
        by_sym_w.setdefault(e["symbol"], []).append(e["date"])
    for s in by_sym_w:
        by_sym_w[s].sort()
    tol = pd.Timedelta(days=28)      # ★ 20 个交易日 ≈ 28 个自然日
    matched = 0
    used: dict[str, set] = {}
    for e in sorted(ev_d, key=lambda x: (x["symbol"], x["date"])):
        cands = by_sym_w.get(e["symbol"], [])
        u = used.setdefault(e["symbol"], set())
        best, bd = None, None
        for k, dt in enumerate(cands):
            if k in u:
                continue
            gap = abs(dt - e["date"])
            if gap <= tol and (bd is None or gap < bd):
                best, bd = k, gap
        if best is not None:
            u.add(best)
            matched += 1
    denom = len(ev_d) + len(ev_w) - matched
    out["口径甲_事件级_±4周容差"] = {
        "重合的事件对数": matched,
        "重合率(Jaccard = 重合 / 两边并集)": round(matched / max(1, denom), 4),
        "日线标的点里有多少在周线也标了": round(matched / max(1, len(ev_d)), 4),
        "周线标的点里有多少在日线也标了": round(matched / max(1, len(ev_w)), 4),
    }

    # 口径乙:逐格级
    both = only_d = only_w = neither = 0
    for s in panel_d:
        a = panel_d[s]
        b = panel_w_on_daily[s]
        m = (a != tri.WARMUP) & (b != tri.WARMUP) & (b != None)      # noqa: E711
        ia = (a == "2") & m
        ib = (b == "2") & m
        both += int((ia & ib).sum())
        only_d += int((ia & ~ib).sum())
        only_w += int((ib & ~ia).sum())
        neither += int((m & ~ia & ~ib).sum())
    u = both + only_d + only_w
    out["口径乙_逐格级_无容差"] = {
        "单位": "票 × **交易日**",
        "两边都判阶段二": both, "只有日线判": only_d, "只有周线判": only_w,
        "两边都不判": neither,
        "重合率(Jaccard)": round(both / max(1, u), 4),
        "日线判的格子里有多少周线也判": round(both / max(1, both + only_d), 4),
        "周线判的格子里有多少日线也判": round(both / max(1, both + only_w), 4),
    }
    out["v13 原话"] = "各自标记 328 个点,只有 89 个重合 = 19.1%(89/(328+328-89)=15.7%;" \
                      "89/328=27.1%)★ 19.1% 这个数本身对不上 v13 自己给的 328/89 —— " \
                      "按哪个公式都算不出 19.1%,这一点要回去问。"
    return out


# ============================================================================
# 二 · 假设二:状-5 相对强度 —— 现有「抗跌性」口径 vs 新增「分位排名」口径
# ============================================================================
#
# 现有口径(XING 版)为什么结构上稀疏:_xing_rs() 里 `if tot < 4` 要求
# **回看 24 个自然月内至少 4 个大盘回调 ≥5% 的窗口**。大盘不保证 24 个月来 4 次
# → 大半时间凑不够 → insufficient_sample。这是结构,不是数据缺。

ONEIL_WEIGHTS_XING = (0.25, 0.25, 0.25, 0.25)
ONEIL_WEIGHTS_FOLKLORE = (0.4, 0.2, 0.2, 0.2)
LAGS = (63, 126, 189, 252)        # ★ 交易日位移

_note("状-5 新增『原著口径』用的是【等权 0.25/0.25/0.25/0.25】。"
      "★ 权重是 XING 填的 —— 欧奈尔/IBD 从未公开过 RS Rating 的确切权重,"
      "原著未给出确切权重。流传的 0.4/0.2/0.2/0.2 是业界近似,"
      "本次作为第二档并排报出,★ 但不许标成『原著的』。")
_note("状-5 新增口径的分位是【池内分位】(300 只票) —— "
      "★ 原著要的是**全市场分位**(IBD 口径是全美上市股)。"
      "池内分位和全市场分位不是一回事:池内 ≥80 分位恒定是 20% 的票,"
      "全市场 ≥80 分位放到我们这 300 只票上可能是 5% 也可能是 60%。"
      "★ 这一档的『算不出占比接近 0』是真的,但『≥80 就是强势股』不能照搬。")
_note("状-5 分位排名的并列处理:pandas rank(pct=True) 默认 average —— "
      "并列取平均名次。★ 我们填的(原著未给)。")


def run_rs_two_definitions(syms: list[str]) -> dict:
    """现有「抗跌性」口径 vs 新增「12 个月加权收益 → 池内分位」口径。"""
    p = cache.load()
    cl = p["close"][syms]
    idx = cl.index
    keep = np.asarray(idx >= pd.Timestamp(tri.START))
    spy = data.load_benchmark("SPY")["close"].reindex(idx).ffill()

    res: dict = {}

    # ---------------- 甲:现有口径(原样跑,不改一行) ----------------
    wins = tri._spy_drawdown_windows(spy, 0.05)
    ma50 = cl.rolling(50, min_periods=50).mean()
    panel_x: dict[str, np.ndarray] = {}
    for s in syms:
        st = tri._xing_rs(cl[s].to_numpy(), wins, idx, 24, "xing",
                          ma50[s].to_numpy())
        panel_x[s] = st[keep]
    dx = tri.distribution(panel_x, tri.RS_STATES)
    dx["单位"] = "票 × **交易日**"
    dx["算不出占比"] = dx["state_share"]["insufficient_sample"]
    dx["为什么稀疏"] = (f"要求回看 24 个**自然月**内至少 4 个大盘回调 ≥5% 的窗口;"
                       f"整个 2014-2025 一共只找到 {len(wins)} 个这样的窗口 → "
                       f"★ 结构性稀疏,不是数据缺。")
    dx["窗口总数(2014-2025 全样本)"] = len(wins)
    dx["窗口清单"] = [{"峰": str(idx[a].date()), "谷": str(idx[b].date()),
                       "可知日": str(idx[c].date()), "大盘跌幅": round(float(m), 4)}
                      for a, b, c, m in wins]
    res["甲_现有抗跌性口径"] = dx

    # ---------------- 乙:新增「12 个月加权收益 → 池内分位」 ----------------
    def _pctile(weights: tuple) -> tuple[pd.DataFrame, pd.DataFrame]:
        sc = sum(w * cl / cl.shift(L) for w, L in zip(weights, LAGS))
        return sc, sc.rank(axis=1, pct=True) * 100.0

    for tag, w in (("乙_原著口径_等权_池内分位", ONEIL_WEIGHTS_XING),
                   ("丙_业界流传权重_池内分位", ONEIL_WEIGHTS_FOLKLORE)):
        sc, pct = _pctile(w)
        pv = pct.to_numpy()[keep]
        ok = np.isfinite(pv)
        # ★ 做成和甲可比的四态:强(≥80)/ 中 / 弱(≤20)/ 算不出
        lab = np.full(pv.shape, "insufficient_sample", dtype=object)
        lab[ok & (pv >= 80.0)] = "resilient"
        lab[ok & (pv <= 20.0)] = "weaker"
        lab[ok & (pv > 20.0) & (pv < 80.0)] = "inline"
        panel = {s: lab[:, i] for i, s in enumerate(syms)}
        d = tri.distribution(panel, tri.RS_STATES)
        d["单位"] = "票 × **交易日**"
        d["算法"] = (f"Score = Σ w·(P0/P_lag),w={w},lag={LAGS}(**交易日**)"
                     f" → 当日全池横截面分位(百分位)")
        d["权重口径属性"] = ("【XING 填的 —— 等权】原著未给出确切权重"
                             if w == ONEIL_WEIGHTS_XING else
                             "【业界流传近似,非原著】0.4/0.2/0.2/0.2")
        d["分位口径属性"] = "★ **池内分位**(300 只票),不是原著要的**全市场分位**"
        d["分档"] = "≥80 分位 → resilient;≤20 → weaker;其余 inline"
        d["算不出占比"] = d["state_share"]["insufficient_sample"]
        d["算不出的原因"] = ("只有一条:成立不足 252 个**交易日**(≈12 个自然月)"
                            "的那段预热期 —— 和大盘有没有回调无关。")
        d["_panel"] = panel
        res[tag] = d

    # ---------------- 两套口径的结论一致性 ----------------
    pe = res["乙_原著口径_等权_池内分位"]["_panel"]
    res["甲乙一致性"] = rs_agreement(panel_x, pe, syms)
    pf = res["丙_业界流传权重_池内分位"]["_panel"]
    res["乙丙一致性(只是换权重)"] = rs_agreement(pe, pf, syms)
    for k in ("乙_原著口径_等权_池内分位", "丙_业界流传权重_池内分位"):
        res[k].pop("_panel", None)
    return res


def rs_agreement(pa: dict, pb: dict, syms: list[str]) -> dict:
    """两套相对强度口径的结论一致性。★ 只在两边都算得出来的格子上比。"""
    NA = "insufficient_sample"
    same = tot = 0
    sa = sb = both = 0
    a_na = b_na = either_na = n_all = 0
    for s in syms:
        a, b = pa[s], pb[s]
        n = min(len(a), len(b))
        a, b = a[:n], b[:n]
        n_all += n
        a_na += int((a == NA).sum())
        b_na += int((b == NA).sum())
        m = (a != NA) & (b != NA) & (a != tri.WARMUP) & (b != tri.WARMUP)
        either_na += int((~m).sum())
        tot += int(m.sum())
        same += int((a[m] == b[m]).sum())
        ia, ib = (a == "resilient") & m, (b == "resilient") & m
        sa += int(ia.sum())
        sb += int(ib.sum())
        both += int((ia & ib).sum())
    u = sa + sb - both
    return {
        "单位": "票 × **交易日**",
        "总格子": n_all,
        "甲算不出的格子": a_na, "乙算不出的格子": b_na,
        "至少一边算不出(不可比)": either_na,
        "两边都算得出的格子(可比)": tot,
        "三态标签完全一致的比例": round(same / max(1, tot), 4),
        "判「强」的格子": {"甲": sa, "乙": sb, "两边都判强": both},
        "判「强」的重合率(Jaccard)": round(both / max(1, u), 4),
        "甲判强的里面乙也判强": round(both / max(1, sa), 4),
        "乙判强的里面甲也判强": round(both / max(1, sb), 4),
    }


# ============================================================================
# 附录甲 · 99.6% 的真正归属:状-3(Al Brooks),不是状-2
# ============================================================================
#
# ★ 不在本次任务范围内,但必须量一下 —— 因为任务里那个 99.6% 指错了人。
#   状-2 的取值里**根本没有 mixed**(它是 1/2/3/4/transition)。
#   99.57% mixed 是状-3 XING 版。
#
# ★ 而状-3 的口径错配**不是日线 vs 周线**,是**单根 vs 窗口**:
#   Brooks 的「趋势棒实体 ≥0.60」是**单根 K 线**的阈值,
#   现行实现把它套在**20 根 K 线实体占比的滚动均值**上。
#   20 根的均值几乎不可能达到 0.60 → 恒定输出 mixed。
# ★ 这一节只做一件事:阈值一个不动,把窗口从 20 根换成 1 根(= 原著自己的单位),
#   看 mixed 掉到多少。★ 它不是本次要拍板的东西,是给下一轮定位用的。

def appendix_brooks_single_bar(syms: list[str]) -> dict:
    p = cache.load()
    hi, lo, op, cl = p["high"], p["low"], p["open"], p["close"]
    idx = cl.index
    keep = np.asarray(idx >= pd.Timestamp(tri.START))
    out: dict = {
        "★ 这一节为什么存在": "任务里「状-2 的 99.6% mixed」指错了人 —— "
                             "状-2 没有 mixed 这个取值,99.57% mixed 是状-3。",
        "★ 口径错配的类型": "不是日线 vs 周线,是**单根 K 线阈值 vs 20 根滚动均值**。",
        "阈值来源": "直接取 tri.BROOKS_VERSIONS['XING版'],★ 一个数都没改,只换窗口长度。",
    }
    spec = tri.BROOKS_VERSIONS["XING版"]
    for look in (20, 5, 1):
        panel: dict[str, np.ndarray] = {}
        for s in syms:
            b, o, u = tri._bar_metrics(hi[s].to_numpy(), lo[s].to_numpy(),
                                       op[s].to_numpy(), cl[s].to_numpy())
            if look == 1:
                sb, so, su = b, o, u
            else:
                sb = pd.Series(b).rolling(look, min_periods=look).mean().to_numpy()
                so = pd.Series(o).rolling(look, min_periods=look).mean().to_numpy()
                su = pd.Series(u).rolling(look, min_periods=look).mean().to_numpy()
            cont = np.fmax(su, 1.0 - su)
            st = np.full(len(b), tri.WARMUP, dtype=object)
            ok = np.isfinite(sb) & np.isfinite(so) & np.isfinite(cont)
            tr = ok & (sb >= spec.body_trend) & (so <= spec.ov_trend) & (cont >= spec.cont_trend)
            rg = ok & (sb <= spec.body_range) & (so >= spec.ov_range) & (cont <= spec.cont_range)
            st[ok] = "mixed"
            st[tr] = "trend"
            st[rg] = "range"
            panel[s] = st[keep]
        d = tri.distribution(panel, tri.BROOKS_STATES)
        key = f"窗口{look}根K线" + ("(= 现行生产口径)" if look == 20
                                     else "(= 原著自己的单位)" if look == 1 else "")
        out[key] = {"单位": "票 × **交易日**", "state_share": d["state_share"],
                    "mixed 占比": d["state_share"]["mixed"],
                    "flips_per_1000_days": d["flips_per_1000_days"]}
    return out


# ============================================================================
# 三 · 恒定输出检测 —— ★ 两套新口径跑完都要过这一遍
# ============================================================================

def constant_output_gate(res2: dict, res5: dict) -> dict:
    """任一取值占比 > 95% 或算不出 > 50% → 报警。★ 判据直接用 checks 里那套。"""
    report: dict[str, list[str]] = {}
    targets = [
        ("假设一·日线150日版", res2["日线150日版"]["state_share"], None),
        ("假设一·周线30周版", res2["周线30周版"]["state_share"], None),
        ("假设一·周线30周版_铺回日线格",
         res2["周线30周版_铺回日线格"]["state_share"], None),
        ("假设二·甲_现有抗跌性口径", res5["甲_现有抗跌性口径"]["state_share"], None),
        ("假设二·乙_原著口径_等权_池内分位",
         res5["乙_原著口径_等权_池内分位"]["state_share"], None),
        ("假设二·丙_业界流传权重_池内分位",
         res5["丙_业界流传权重_池内分位"]["state_share"], None),
    ]
    for name, shares, nan in targets:
        report[name] = co.check_shares(name, shares, nan_share=nan) or ["通过"]
    return {
        "阈值出处": f"DOMINANT_SHARE={co.DOMINANT_SHARE}、NAN_SHARE={co.NAN_SHARE}"
                    f" —— 直接取 engine/checks/constant_output.py,没自己定",
        "逐条": report,
        "报警条数": sum(1 for v in report.values() if v != ["通过"]),
    }


# ============================================================================
def main() -> int:
    t0 = time.time()
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    idx = cache.load()["close"].index
    win = idx[idx >= pd.Timestamp(tri.START)]
    print(f"池子 {len(syms)} 只 × 计分窗口 {len(win)} 个交易日 "
          f"({win[0].date()} ~ {win[-1].date()}),预热从 {idx[0].date()} 起")
    print("★ 串行跑,不并行。")

    print("\n[1/3] 假设一:状-2 日线 150 日 vs 周线 30 周 …")
    res2 = run_stage_two_timeframes(syms)
    print("     复制件忠实性:", res2["自测_复制件是否忠实"]["结论"])
    print("     日线 transition 占比:",
          res2["日线150日版"]["state_share"]["transition"])
    print("     周线 transition 占比:",
          res2["周线30周版"]["state_share"]["transition"])

    print("\n[2/3] 假设二:状-5 抗跌性 vs 分位排名 …")
    res5 = run_rs_two_definitions(syms)
    print("     甲 算不出占比:", res5["甲_现有抗跌性口径"]["算不出占比"])
    print("     乙 算不出占比:", res5["乙_原著口径_等权_池内分位"]["算不出占比"])

    print("\n[2.5/3] 附录甲:99.6% 的真正归属(状-3,单根 vs 20 根窗口)…")
    resA = appendix_brooks_single_bar(syms)
    for k, v in resA.items():
        if isinstance(v, dict) and "mixed 占比" in v:
            print(f"     {k}: mixed = {v['mixed 占比']}")

    print("\n[3/3] 恒定输出检测 …")
    gate = constant_output_gate(res2, res5)
    print("     报警条数:", gate["报警条数"])
    for k, v in gate["逐条"].items():
        print(f"     {k}: {v[0][:100]}")

    out = {
        "meta": {
            "git_commit": subprocess.run(
                ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
                cwd=_REPO).stdout.strip(),
            "symbols": len(syms),
            "scoring_days": len(win),
            "scoring_start": str(win[0].date()),
            "scoring_end": str(win[-1].date()),
            "warmup_start": str(idx[0].date()),
            "并行": "★ 无 —— 全程串行单进程",
            "改了哪些现有文件": "★ 一个都没改。本文件只 import engine.*,"
                               "不写回;matrices.py / chain.py / config_adapter.py 未碰。",
        },
        "时间尺度声明": TIME_SCALE,
        "假设一_状2_日线vs周线": res2,
        "假设二_状5_抗跌性vs分位排名": res5,
        "附录甲_99.6%的真正归属_状3单根vs窗口": resA,
        "恒定输出检测": gate,
        "本文件自己填的口径": MY_NOTES,
    }

    def _j(o):
        if isinstance(o, dict):
            return {k: _j(v) for k, v in o.items() if not k.startswith("_panel")}
        if isinstance(o, (list, tuple)):
            return [_j(x) for x in o]
        if isinstance(o, np.integer):
            return int(o)
        if isinstance(o, np.floating):
            return float(o)
        if isinstance(o, np.bool_):
            return bool(o)
        return o

    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(_j(out), f, ensure_ascii=False, indent=1, default=str)
    print(f"\n写好 {OUT_JSON},用了 {time.time()-t0:.1f} 秒")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
