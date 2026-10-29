"""
原著离场规则专用算子 —— 2026-10-29。

三秒版:我们一直只实现了「怎么买」,没实现「怎么卖」。
这个文件把原著写死的离场规则补上:TD 序列的四重离场、TD 风险位止损、
海龟汤的「新低下方 1 tick」止损。时间止损引擎本来就有(exit.rules.time_stop),
不用在这里重写。

★ 挂钩方式照 pat6_ops.py 那一套:**运行时挂钩**,
  matrices.py / chain.py / config_adapter.py 三个文件一个字符都不改。

★ 本文件的铁律,和 ops_a0.py 一样:
  一、每个算子上面写清楚「哪个数来自原著、哪个是执行细节、哪个是我们加的」。
  二、★ 原著没给的数,这里**不给默认值** —— 调用方不传就抛错。
  三、不许网格搜索。

★★ 出处纪律(本次特别强调):本文件里的规则来自外部模型的整理,
  **结论部分已交叉核对,但章节号和页码一律当【待核实】** ——
  所以下面任何一处都不写页码、不写章节号。谁要引用,自己去核。
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from . import cache, matrices

_NOTES: list[str] = []


def notes() -> list[str]:
    return list(_NOTES)


def _note(s: str) -> None:
    if s not in _NOTES:
        _NOTES.append(s)


def _as_bool(df: pd.DataFrame) -> pd.DataFrame:
    return df.fillna(False).astype(bool)


_CACHE: dict[tuple, pd.DataFrame] = {}


def cache_info() -> dict:
    return {"缓存条数": len(_CACHE),
            "说明": "键含全部参数与票清单,参数改了不会误命中"}


def _need(p: dict, key: str, who: str) -> float:
    if p.get(key) is None:
        raise NotImplementedError(
            f"{who} 需要参数 {key},但配置里没写 —— "
            f"★ 引擎不替它拍一个数。要跑必须在配置里显式写出来并标明出处。")
    return float(p[key])


# ===========================================================================
# 技-13 TD 序列 · 四重离场
#
# 大白话:原来我们买进去之后**只有一条止损**,结果平均拿了 80~90 天,
#   而这套计数法的意图是 2~5 天的短线。下面四条就是原著的离场,全部装上。
#
# ★ 出处:外部模型整理的「原著四重离场」。★ 结论部分已交叉核对;
#   ★ 章节号与页码【待核实】—— 所以配置的 source 栏里不写任何页码。
# ===========================================================================

def td_countdown_13_exit(symbols: list[str], *, setup_count: int,
                         ref_lag: int, countdown: int,
                         cd_lag: int) -> pd.DataFrame:
    """
    离场①:Countdown 13 离场。

    Buy Setup `setup_count` 完成之后开始顺向计数,每当
    **该日收盘价 ≥ cd_lag 根 K 线前的最高价** 记一个(不要求连续),
    数到第 `countdown` 个那天 → 全部平仓。

    ★ 和 ops_a0.td_buy_countdown 的区别(必须看清,否则会张冠李戴):
      · ops_a0 那个是 **Buy** Countdown:close ≤ low[t−2],它是**进场**信号。
      · 这里这个是**离场**用的顺向计数:close ≥ high[t−2]。
      ★ 条件方向相反。本函数照任务书给的文字写死:「该日收盘价 ≥ 2 根 K 线
        前的最高价」。
    ★ 「新的 Setup 完成会把计数重置」沿用 ops_a0.td_buy_countdown 的写法 ——
      ★ 这是流传版本的做法,不是原著原文,报告里单列。
    """
    from . import ops_a0
    key = ("td_cd13_exit", tuple(symbols), setup_count, ref_lag, countdown, cd_lag)
    if key in _CACHE:
        return _CACHE[key]
    close = cache.field("close", symbols)
    high = cache.field("high", symbols)
    setup_done = ops_a0.td_buy_setup(symbols, int(setup_count), int(ref_lag))
    tick = _as_bool(close >= high.shift(int(cd_lag)))
    out = pd.DataFrame(False, index=close.index, columns=close.columns)
    for col in close.columns:
        sd = setup_done[col].to_numpy(dtype=bool)
        tk = tick[col].to_numpy(dtype=bool)
        res = np.zeros(len(sd), dtype=bool)
        active, cnt = False, 0
        for i in range(len(sd)):
            if sd[i]:
                active, cnt = True, 0
            if active and tk[i]:
                cnt += 1
                if cnt >= int(countdown):
                    res[i] = True
                    active, cnt = False, 0
        out[col] = res
    _note(f"技-13 离场①:Countdown {countdown} 离场 —— Setup {setup_count} 完成后"
          f"顺向计数,close ≥ high[t−{cd_lag}] 记一个,数到 {countdown} 全平。"
          f"★ 注意条件方向与 ops_a0 的 Buy Countdown 相反(那个是 close ≤ low[t−2])")
    _CACHE[key] = _as_bool(out)
    return _CACHE[key]


def td_price_flip_exit(symbols: list[str], *, ref_lag: int) -> pd.DataFrame:
    """
    离场②:TD Price Flip 离场。
    多头持仓中,出现 `Close_t < Close_{t−ref_lag}` 即离场。
    ★ ref_lag = 4 与 Setup 的比较口径同源(原著整套用的都是「比 4 根前」)。
    ★ 按收盘价判定,全程不碰盘中最高/最低价(硬纪律第 5 条)。
    """
    close = cache.field("close", symbols)
    _note(f"技-13 离场②:TD Price Flip —— Close_t < Close_t−{ref_lag} 即离场"
          f"(按收盘价判定)")
    return _as_bool(close < close.shift(int(ref_lag)))


def td_sell_setup_exit(symbols: list[str], *, count: int,
                       ref_lag: int) -> pd.DataFrame:
    """
    离场④:反向 Setup 9 离场。
    持仓期走出完整 Sell Setup:连续 `count` 根收盘价**高于** `ref_lag` 根前的
    收盘价 → 在第 `count` 根那天强制平仓。

    ★ 这是 ops_a0.td_buy_setup 的镜像(那个是 close < close[t−4])。
    ★ 旧配置 技-13.yaml 的 exit.source 里写着「本次没有装这一条,因为
      『反向计数』在手册里没给完整定义(是 Sell Setup 9 还是 Sell Countdown 13?)」
      —— 本轮按任务书取 **Sell Setup 9**,★ 这个取舍写在报告里。
    """
    key = ("td_sell_setup", tuple(symbols), count, ref_lag)
    if key in _CACHE:
        return _CACHE[key]
    close = cache.field("close", symbols)
    cond = _as_bool(close > close.shift(int(ref_lag)))
    run = cond.astype(int)
    for col in cond.columns:
        v = cond[col].to_numpy(dtype=bool)
        r = np.zeros(len(v), dtype=int)
        acc = 0
        for i in range(len(v)):
            acc = acc + 1 if v[i] else 0
            r[i] = acc
        run[col] = r
    _note(f"技-13 离场④:反向 Sell Setup {count} 离场(连续 {count} 根收盘价"
          f"高于 {ref_lag} 根前)。★ 原著「反向计数」的两种读法里取的是 Setup 9")
    _CACHE[key] = _as_bool(run == int(count))
    return _CACHE[key]


#: 本模块接管的离场规则类型
_EXIT_TYPES = {
    "td_countdown_13_exit",
    "td_price_flip_exit",
    "td_sell_setup_exit",
}

#: 本模块接管的初始止损类型
_STOP_TYPES = {
    "td_risk_level_stop",
    "day_low_minus_tick",
}


# ===========================================================================
# 技-13 离场③ —— TD Risk Level 止损(写死的公式)
#
#   Stop = Setup 期间最低那根 Bar 的 True Low − 该 Bar 的 True Range
#
#   True Low(t)   = min(Low_t, Close_{t−1})
#   True High(t)  = max(High_t, Close_{t−1})
#   True Range(t) = True High(t) − True Low(t)      (Wilder 1978 的真实波幅)
#
#   ★ 「最低那根」= Setup 那 9 根里 **True Low 最小**的那一根。
#     原文只写「最低那根 Bar」;在 True Low 口径下自然就是 True Low 最小的那根,
#     ★ 这个读法写在这里,不藏。
# ===========================================================================

def _td_risk_level(m, j: int, k: int, setup_lookback: int) -> float:
    """
    k = 信号那一根(进场日 i 的前一根)。Setup 窗口 = k−setup_lookback+1 .. k。
    ★ 取不到前一根收盘价(窗口贴着数据起点)时返回 nan —— 不拿近似值顶上。
    """
    n = int(setup_lookback)
    a = k - n + 1
    if a - 1 < 0:
        return float("nan")
    lo = m.low[a:k + 1, j].astype(float)
    hi = m.high[a:k + 1, j].astype(float)
    pc = m.close[a - 1:k, j].astype(float)       # 每根的「前一根收盘」
    ok = np.isfinite(lo) & np.isfinite(hi) & np.isfinite(pc)
    if not ok.any():
        return float("nan")
    tl = np.minimum(lo, pc)
    th = np.maximum(hi, pc)
    tr = th - tl
    tl = np.where(ok, tl, np.inf)
    idx = int(np.argmin(tl))
    if not np.isfinite(tl[idx]) or not np.isfinite(tr[idx]):
        return float("nan")
    return float(tl[idx] - tr[idx])


_orig_one_stop = None
_orig_exit = None
_fallback_counter = {"td_risk_level_stop_算不出": 0}


def _one_stop(m, j: int, i: int, entry_px: float, spec: dict) -> float:
    """包一层 chain._one_stop:先认本模块的两种止损,其余原样交回去。"""
    kind = (spec or {}).get("type")
    p = (spec or {}).get("params", {}) or {}
    k = max(0, i - 1)

    if kind == "td_risk_level_stop":
        v = _td_risk_level(m, j, k, int(_need(p, "setup_lookback",
                                              "td_risk_level_stop")))
        if not np.isfinite(v):
            _fallback_counter["td_risk_level_stop_算不出"] += 1
            # ★ 算不出就返回 nan —— chain 会把这个信号丢掉(stop 不合法 = 不开仓)。
            #   ★ 不许退回一个「差不多」的止损:那会让报告里的止损口径
            #     和配置写的不是同一个东西。
            return float("nan")
        return v

    if kind == "day_low_minus_tick":
        # ★ 技-10 原著:「买入后挂在当日创出的新 20 日最低价下方 1 tick」。
        #   ★ tick 必须由配置显式写(原著写的是 1 tick,美股最小报价单位 = $0.01)。
        #   ★ structure_lookback = 回看几根取最低:引擎的执行比原著晚一天,
        #     假突破那根在 k−1、确认那根在 k,所以回看 3 根能稳稳覆盖住 ——
        #     ★ 这个 3 和旧配置 技-10.yaml 完全一致,本轮唯一的改动是那 1 tick。
        n = int(p.get("structure_lookback", 1))
        tick = _need(p, "tick", "day_low_minus_tick")
        lo = m.low[max(0, k - n + 1):k + 1, j].astype(float)
        lo = lo[np.isfinite(lo)]
        if not lo.size:
            return float("nan")
        return float(lo.min()) - float(tick)

    return _orig_one_stop(m, j, i, entry_px, spec)


def _exit(spec: dict, symbols: list[str]) -> pd.DataFrame:
    """包一层 matrices.exit_signal_matrix:本模块的规则自己算,其余交回去。"""
    spec = spec or {}
    mine = [r for r in (spec.get("rules") or [])
            if r.get("type") in _EXIT_TYPES
            and r.get("enabled", True) is not False]
    rest = {k: v for k, v in spec.items() if k != "rules"}
    rest["rules"] = [r for r in (spec.get("rules") or [])
                     if r.get("type") not in _EXIT_TYPES]
    out = _orig_exit(rest, symbols)
    for r in mine:
        t = r["type"]
        p = r.get("params", {}) or {}
        if t == "td_countdown_13_exit":
            out = out | td_countdown_13_exit(
                symbols,
                setup_count=int(_need(p, "setup_count", t)),
                ref_lag=int(_need(p, "ref_lag", t)),
                countdown=int(_need(p, "countdown", t)),
                cd_lag=int(_need(p, "cd_lag", t)))
        elif t == "td_price_flip_exit":
            out = out | td_price_flip_exit(
                symbols, ref_lag=int(_need(p, "ref_lag", t)))
        elif t == "td_sell_setup_exit":
            out = out | td_sell_setup_exit(
                symbols, count=int(_need(p, "count", t)),
                ref_lag=int(_need(p, "ref_lag", t)))
        else:                                    # pragma: no cover
            raise AssertionError(t)
    return _as_bool(out)


def install() -> None:
    """
    运行时挂钩。★ matrices.py / chain.py / config_adapter.py 一个字符都不改。

    ★ 可以和 pat6_ops.install() 同时用,顺序无关:两边都是「自己认的先拿走,
      剩下的原样交回上一层」,所以是可组合的。
    """
    global _orig_one_stop, _orig_exit
    from . import chain, config_adapter
    if _orig_one_stop is None:
        _orig_one_stop = chain._one_stop
        chain._one_stop = _one_stop
    if _orig_exit is None:
        _orig_exit = matrices.exit_signal_matrix
        matrices.exit_signal_matrix = _exit
    config_adapter.IMPLEMENTED["exit"] |= _EXIT_TYPES
    config_adapter.IMPLEMENTED["initial_stop"] |= _STOP_TYPES
    _note("原著离场算子已挂钩(运行时):TD 四重离场的三条规则 + "
          "TD 风险位止损 + 海龟汤「新低下方 1 tick」止损。"
          "matrices.py / chain.py / config_adapter.py 三个文件没改。")


def diagnostics() -> dict:
    return {"算子备注": notes(),
            "算不出而被丢掉的信号数": dict(_fallback_counter),
            "缓存": cache_info()}
