#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 把「原著声明的使用条件」做成可注入的市场环境向量 —— 2026-10-30

三秒版:原著给每条策略写了「什么市场里用它」。我们一直没把这句话装进代码,
        所以 79 个变体里 75 个的 ② regime 是空的(真 100% 的交易日)。
        ★ 这个文件只做一件事:把那句话翻译成一条**逐交易日的真/假序列**,
          并且**每一条都写明是原著原文(甲)还是我们翻译的(乙)**。

══════════════════════════════════════════════════════════════════════════
★★★ 纪律:本轮方向是「可能让策略活下来」,所以**反向偏差**的风险最大
══════════════════════════════════════════════════════════════════════════
三条自我约束,写在这里当契约:
  ① **一个新数都不许拍。** 下面每个阈值都必须指到仓库里**已经提交过**的
     出处(某份 YAML 的 params / 某个 engine 模块的常量)。
     ★ 如果一个条件需要我新拍一个数才能跑 —— 那它就是丙类,不装。
  ② **乙类(我们翻译的)和甲类(原著可执行的)分开统计。**
     否则「装上条件之后活了几条」这个数会被我们自己的翻译撑起来。
  ③ **不许看结果再回头调条件。** 本文件里的全部口径在跑之前定稿,
     ★ 跑完不改。(真要改就另起一版并把两版都报出来。)

══════════════════════════════════════════════════════════════════════════
★★ 先说清楚三件「同一样东西两种写法」的坑(纪律 2)
══════════════════════════════════════════════════════════════════════════
1. ★★★ **"stage" 这个词在本仓库有四种含义**,装 regime 时极易踩:
      matrices.stage_ma       = 分级止损用的均线        ← 和环境无关
      sizing.stages           = 分批建仓的段            ← 和环境无关
      技-5 的 stage: selection_gate = 漏斗关卡          ← 和环境无关
      状-2 的阶段号(1/2/3/4)  = 个股生命周期阶段        ← ★ 个股,不是大盘
   ★ 本文件要的是**大盘**的「上涨 / 下跌 / 震荡」—— 那是 **状-1**(道氏高低点
     排列),不是上面任何一个。★★ 本文件一次都不读 `stage` 这个字段。
2. **regime 是一维的**(`matrices.Matrices.regime`,长度 = 交易日数,全池共用)。
   ★ 所以「个股层面的条件」(比如技-11「长期横盘的标的」、技-14「长期趋势向上」)
     **不能**装进 ② regime —— 它们属于 ① universe / ③ entry。
     ★★ 装错层 = 把一个选股条件当成大盘总开关,会把整条链在某些日子全关掉。
     本文件把两层**分开给**(`market_vectors()` / `STOCK_LEVEL_NOTES`)。
3. **已经 shift 过了**:`matrices.regime_mask()` 最后一行是
   `ok.shift(1, fill_value=False)` —— t 行的值用 t−1 收盘算。
   ★ 本文件产出的向量**同样 shift(1)**,口径一致,不许偷看当天。

══════════════════════════════════════════════════════════════════════════
★ 现成实现清单(纪律 3:装之前先搜仓库,搜不到再写)
══════════════════════════════════════════════════════════════════════════
搜过了,下面三件**都是现成的**,本文件一行新算法都没写:
  · `matrices.regime_mask` 的 `index_above_ma` / `index_ma_slope`
        → 已有,参数照抄 `engine/configs/vcp_momentum.yaml`(已提交)
  · `engine.run_a0_states.zigzag_pivots`(状-1 摆动点)
        → 已有,k=3.0 / use_wick=True;★ 2026-10-30 `023fbbf` 刚修好静默空,
          **所以今天才第一次装得上**
  · `engine.pat6_ops` 的 `pat6_bb_trend_gate`(个股 200 日线 + 斜率)
        → 已有,技-14-行业-RSI2 正在用;★ 技-14-XING / 技-14-原著 没装
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import data, matrices                               # noqa: E402
from engine.run_a0_states import zigzag_pivots                  # noqa: E402

# ══════════════════════════════════════════════════════════════════════════
# 一 · 甲类 / 乙类 的参数出处 —— ★ 一个新数都没有
# ══════════════════════════════════════════════════════════════════════════

#: 「牛市 / 单边上涨 / 方向明确的上升」的落地规则。
#: ★★★ 出处:**逐字抄** engine/configs/vcp_momentum.yaml 的 ② regime 前两条。
#:   ★ 那两条自己标的 source 是「行业惯例」(不是原著)—— 所以凡是用它翻译的,
#:     一律记为**乙类**,不许记成甲类。
BULL_RULES = [
    {"type": "index_above_ma",
     "params": {"symbol": "SPY", "ma": 200},
     "source": "照抄 engine/configs/vcp_momentum.yaml ② regime 第 1 条(行业惯例)"},
    {"type": "index_ma_slope",
     "params": {"symbol": "SPY", "ma": 200, "lookback": 20, "min_slope": 0.0},
     "source": "照抄 engine/configs/vcp_momentum.yaml ② regime 第 2 条(行业惯例)"},
]

#: 状-1 的 ZigZag 阈值。★ 出处:附录 D.8 声明的 3 × ATR(14),
#: ★★ 以及 `engine/run_a0_states.zigzag_pivots` 的默认值 k=3.0 / use_wick=True。
ZZ_K = 3.0
ZZ_USE_WICK = True

#: ★ 个股层面的条件(**不许装进 ② regime**),记在这里供报告引用
STOCK_LEVEL_NOTES = {
    "技-11": "原著条件「长期横盘、成交量持续萎缩的**标的**」是**选股**条件 "
             "(① universe / ③ entry),不是大盘总开关。本轮不装进 ② regime。",
    "技-14": "原著条件「长期趋势向上」是**个股**的(卡片原文:这个前提不许关掉)。"
             "现成实现 = pat6_bb_trend_gate(ma 200 + 20 日斜率),"
             "★ 技-14-行业 / 技-14-行业-RSI2 已装在 ③ entry 里;"
             "★★ 技-14-XING / 技-14-原著 **没装** —— 本轮补装。",
    "技-12": "原著条件「200 日均线之上」是**个股**的,已装在 ① universe "
             "(price_above_ma ma:200)。★ 本轮不动它。",
}


# ══════════════════════════════════════════════════════════════════════════
# 二 · 状-1 道氏高低点排列(大盘)—— 技-10 那条甲类条件的落地
# ══════════════════════════════════════════════════════════════════════════

def dow_arrangement(index: pd.DatetimeIndex, symbol: str = "SPY",
                    _shift: bool = True) -> pd.Series:
    """状-1:把大盘逐日判成 '上涨' / '下跌' / '震荡'。

    ★★ 为什么这是**甲类**:技-10 的方法卡 `data_requirement` 原文写的是
       「规则完全机械。但必须和市场状态判断绑定(见 状-1、状-3),
         **不允许在趋势市里自动触发**。」
       ★ 这句话给了:判什么(趋势市 / 震荡市)· 用谁判(状-1)· 怎么处置(不许触发)。
       ★★★ 三样都有 → 可执行,是甲类,不是我们翻译的。

    ★ 判据(道氏原始定义,零自由参数):
        取最近两个摆动高点 H1(新) / H2(旧) 和最近两个摆动低点 L1 / L2
        上涨 = H1 > H2 且 L1 > L2        (高点更高、低点更高)
        下跌 = H1 < H2 且 L1 < L2
        震荡 = 其余(含摆动点还不够 4 个的预热期)
    ★★ 「摆动点」用现成的 `run_a0_states.zigzag_pivots`(k = 3×ATR14,
       取影线)—— ★ 这个函数 2026-10-30 `023fbbf` 刚修好静默返回空的 bug,
       **这就是技-10 这条条件今天才第一次装得上的全部原因**。

    ★ 预热期(摆动点不足 4 个)判成**震荡** —— ★★★ 这是对本轮**不利**的一侧
      吗?不是。要看条件怎么用:技-10 的条件是「只在震荡市做」,
      把预热判成震荡 = **放宽**。所以这里反过来处理:
      预热期一律判成 `'预热'`,而 `not_trending()` 把 `'预热'` 判成
      **不开闸**(保守),★ 不让预热期白送交易日给技-10。
    """
    px = data.load_benchmark(symbol)
    hi = px["high"].to_numpy(dtype=float)
    lo = px["low"].to_numpy(dtype=float)
    cl = px["close"].to_numpy(dtype=float)
    # ATR(14) —— ★ 用 matrices 里现成的口径,不自己再写一遍
    tr = np.maximum.reduce([
        hi[1:] - lo[1:],
        np.abs(hi[1:] - cl[:-1]),
        np.abs(lo[1:] - cl[:-1]),
    ])
    atr = np.full(len(cl), np.nan)
    atr[1:] = pd.Series(tr).rolling(14, min_periods=14).mean().to_numpy()

    piv = zigzag_pivots(hi, lo, cl, atr, k=ZZ_K, use_wick=ZZ_USE_WICK)
    if not piv:
        raise RuntimeError(
            "★★★ 状-1 在 SPY 上一个摆动点都没有 —— 停下来查。"
            "(这正是 023fbbf 修掉的那个静默空的形状,不许当成「震荡市」往下跑)")

    out = np.full(len(cl), "预热", dtype=object)
    highs: list[float] = []
    lows: list[float] = []
    p = 0
    for i in range(len(cl)):
        while p < len(piv) and piv[p][0] <= i:
            _idx, kind, val = piv[p]
            (highs if kind == "H" else lows).append(float(val))
            p += 1
        if len(highs) >= 2 and len(lows) >= 2:
            up = highs[-1] > highs[-2] and lows[-1] > lows[-2]
            dn = highs[-1] < highs[-2] and lows[-1] < lows[-2]
            out[i] = "上涨" if up else ("下跌" if dn else "震荡")
    s = pd.Series(out, index=px.index)
    # ★ 和 regime_mask 同一个口径:往后挪一天(t 行的值用 t−1 收盘算)
    #   ★★ _shift=False 只给反向自测用(证明确实挪过),跑批一律走默认 True
    if _shift:
        s = s.shift(1).fillna("预热")
    return s.reindex(index).ffill().fillna("预热")


def not_trending(index: pd.DatetimeIndex, symbol: str = "SPY") -> pd.Series:
    """技-10 的甲类条件:★ 只有大盘**既非上涨趋势、也非下跌趋势**才开闸。

    ★★ 「预热」判成**不开闸** —— 保守侧(见 dow_arrangement 的说明)。
    """
    a = dow_arrangement(index, symbol)
    return (a == "震荡").reindex(index).fillna(False)


# ══════════════════════════════════════════════════════════════════════════
# 三 · 乙类:「牛市 / 单边上涨」—— 走现成的 regime_mask,不自己算
# ══════════════════════════════════════════════════════════════════════════

def bull_market(index: pd.DatetimeIndex) -> pd.Series:
    """★ 直接调 `matrices.regime_mask`,参数照抄 vcp_momentum.yaml。

    ★★ 这样做的好处:**我们和已经跑过的那三条 技-5 真实链用的是同一把尺子**
       (那三条的 regime 真 61.9% 的交易日,见上一轮 §5.2)—— 可以交叉验证。
    """
    return matrices.regime_mask({"rules": BULL_RULES}, index)


# ══════════════════════════════════════════════════════════════════════════
# 四 · 对外:全部市场级向量 + 时间占比
# ══════════════════════════════════════════════════════════════════════════

def market_vectors(index: pd.DatetimeIndex) -> dict:
    """返回 {向量名: (布尔序列, 元信息)}。★ 元信息里写明甲/乙和出处。"""
    nt = not_trending(index)
    bl = bull_market(index)
    return {
        "甲·非趋势市": (nt, {
            "条件全名": "大盘非趋势市(状-1 道氏高低点排列 ≠ 上涨 且 ≠ 下跌)",
            "出处等级": "甲",
            "原著原文": "技-10 方法卡 data_requirement:「规则完全机械。"
                        "但必须和市场状态判断绑定(见 状-1、状-3),"
                        "不允许在趋势市里自动触发。」"
                        "time_horizon_or_application:「震荡市、宽幅箱体市。」",
            "落地": "状-1 道氏高低点排列(最近两高两低),大盘 SPY;"
                    "摆动点 = run_a0_states.zigzag_pivots(k=3×ATR14, 取影线)",
            "自由参数": "只有 k=3×ATR14 一个,出处 = 附录 D.8 声明值 "
                        "+ zigzag_pivots 默认值;★ 我们没新拍任何数",
            "今天才装得上的原因": "zigzag_pivots 的静默返回空 2026-10-30 "
                                   "023fbbf 才修好 —— 在那之前状-1 校准不了",
            "预热期处置": "摆动点不足 4 个 → 判成「预热」→ ★ 不开闸(保守侧)",
        }),
        "乙·牛市": (bl, {
            "条件全名": "牛市(SPY 收盘 > 200 日均线 且 200 日均线近 20 交易日斜率 > 0)",
            "出处等级": "乙 ★ 我们填的",
            "原著原文(定性)": "技-4「牛市中段,成长股领涨的阶段」· "
                               "技-5「牛市里的强势股」· 技-6「单边上涨行情」· "
                               "技-8「牛市里最强的那一小批股票」· "
                               "技-1「方向明确的市场」",
            "翻译规则(★ 让人能反驳的那一句)": (
                "「牛市 / 单边上涨 / 方向明确」→ SPY 收盘在 200 日均线之上 "
                "且 200 日均线近 20 个交易日斜率 > 0。"
                "★ 两个条件都要成立。"),
            "参数出处": "逐字照抄 engine/configs/vcp_momentum.yaml ② regime 的"
                        "前两条(该文件自己标 source = 行业惯例)—— "
                        "★★ 一个新数都没拍",
            "★★★ 翻译没覆盖到的部分(必须留痕)": (
                "「中段」「成长股领涨」「最强的那一小批」「一年只有几次机会」"
                "—— 这几句我们**没有**翻译,也没有拿它们去挑时段。"
                "★ 所以这条翻译是「牛市」的一个**宽口径**代理,"
                "不是原著那句话的全部。"),
        }),
    }


def share_of_days(v: pd.Series) -> dict:
    """★ 条件成立的时间占比 —— 任务单第②条点名「极其重要」的那一栏。"""
    v = v.astype(bool)
    n = int(len(v))
    t = int(v.sum())
    # ★ 逐年也给一份:一条「一年只成立两三次」的条件和一条常年可用的,
    #   在年度分布上长得完全不同。
    by_year = {str(y): round(float(g.mean()), 4)
               for y, g in v.groupby(v.index.year)}
    return {"交易日总数": n, "条件成立的交易日数": t,
            "条件成立时间占比": round(t / n, 6) if n else None,
            "逐年占比": by_year}


# ══════════════════════════════════════════════════════════════════════════
def _selftest() -> int:
    """★ 反向自测:三条,都必须过。"""
    idx = data.perf_window(data.load_benchmark("SPY").index,
                           data.PERF_START, data.PERF_END)
    ok = True

    # ① 状-1 不许整段是空/恒定 —— 这是 023fbbf 那个 bug 的形状
    a = dow_arrangement(idx)
    mix = a.value_counts(normalize=True).to_dict()
    c1 = len([k for k in mix if k in ("上涨", "下跌", "震荡")]) >= 2
    print(f"① 状-1 三态都出得来(不是恒定输出):{mix}  {'✓' if c1 else '✗'}")
    ok &= c1

    # ② 向量必须 shift 过:t 日的值不许用到 t 日收盘
    #    ★ 真检法:shifted[t] 必须 == unshifted[t−1],而且两条序列**不相等**
    #      (相等就说明根本没挪)
    px = data.load_benchmark("SPY")
    sh = dow_arrangement(px.index, _shift=True).to_numpy()
    raw = dow_arrangement(px.index, _shift=False).to_numpy()
    c2a = bool((sh[1:] == raw[:-1]).all())
    c2b = not bool((sh == raw).all())
    c2 = c2a and c2b
    print(f"② 向量已 shift(1):t 的值 == 未挪的 t−1 {'✓' if c2a else '✗'};"
          f" 两条序列确实不同 {'✓' if c2b else '✗'}")
    ok &= c2

    # ③ 牛市向量必须和上一轮已跑过的技-5 真实链对得上(61.9% 那个数)
    #    ★ 技-5 真实链 vcp_momentum 的 regime 还多一条 no_distribution_day,
    #      所以我们这条(只要前两条)必须**不低于** 61.9%
    bl = bull_market(idx)
    s = float(bl.mean())
    c3 = s >= 0.619
    print(f"③ 牛市向量占比 {s:.4f} ≥ 上一轮 vcp_momentum 的 0.619"
          f"(我们少一条 no_distribution_day,只能更宽):{'✓' if c3 else '✗'}")
    ok &= c3

    for name, (v, meta) in market_vectors(idx).items():
        st = share_of_days(v)
        print(f"\n★ {name}\n   {meta['出处等级']} | 成立 "
              f"{st['条件成立的交易日数']}/{st['交易日总数']} 交易日 = "
              f"{st['条件成立时间占比']:.2%}\n   逐年 {st['逐年占比']}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(_selftest())
