#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ ⑮ 空结果闸 —— 一道检「**有没有值**」的闸,不是检「值对不对」。

三秒版:一个函数**什么都不返回**,也可以一声不响地跑完。
        下游拿到空列表,照样算出一个「0 个事件」,报告上看起来像
        「这个阈值很严格」。★★★ 这不是严格,这是函数坏了。

══════════════════════════════════════════════════════════════════════════
★★★ 为什么必须单开这一道闸(2026-10-30 真实事故)
══════════════════════════════════════════════════════════════════════════
`engine/run_a0_states.py: zigzag_pivots()` 在 k ≥ 6 时**静默返回空列表**:
    k=4 → 11.7% 的票得 0 个摆动点
    k=5 → 42.1%      k=6 → 70.9%      k=8 → 92.6%      k=12 → 98.7%
病根在 bootstrap:`direction == 0` 时两个 if 分支在同一根 bar 里都执行,
跟踪极值被每根 bar 重置 → 跳出条件退化成「单根 bar 振幅 ≥ k×ATR」,
而那个概率在 k=5 就已经是 0.0000%。★ 状-1 / 状-4 / 状-6 全压在它上面。

★★★ 而现有 14 道闸**一道都抓不到它**,原因很具体:
    · ① 恒定输出:它查判据的**输出分布**,空列表根本进不了分布
    · ② 集中度 / ④ 阈值 vs 分布 / ⑩ R 分母:都要**先有数**才查得了
    · ⑪ 四槽位 / ⑨ 加仓 schema:查**配置**,不查运行结果
    · ⑫ 静默截断:查的是**数据序列**被切了多少,不是**函数返回**空
  ★★ 一句话:★★★ 我们的闸全都在检「值对不对」,没有一道在检「有没有值」。
     这道闸补的就是这个洞。

══════════════════════════════════════════════════════════════════════════
★ 判据
══════════════════════════════════════════════════════════════════════════
一个「每只票算一遍、返回一串事件」的函数,在**任何**参数档位上,
「返回空」的票占比都不许超过 MAX_EMPTY_SHARE。
★ 为什么是占比而不是「不许为空」:个别票历史太短、整段 NaN,空是合理的;
  ★★ 过半的票同时为空,那就不是数据的事,是函数的事。

★ 阈值出处:zigzag 这件事上,修好之后 k=2..12 **每一档都是 0.0%**,
  而坏的时候 k=4 就 11.7%。★ 所以 0.10 这个线既离「修好」很远、
  又离「坏了」很近 —— 它能在 k=4 那一档就把事故抓住,而不是等到 k=6 过七成。
★★ 这个阈值是我们自己拍的(不是原著),★ 已标注,见 THRESHOLD_SOURCE。
"""
from __future__ import annotations

import os
import sys

import numpy as np

#: ★ 任何参数档位上,「返回空」的票占比上限
MAX_EMPTY_SHARE = 0.10

THRESHOLD_SOURCE = (
    "★ 我们自己拍的(丙类),不是原著。定法见本文件 docstring:"
    "修好后 k=2..12 每档都是 0.0%,坏的时候 k=4 已经 11.7% —— "
    "0.10 能在 k=4 那一档就抓住,不必等到 k=6 过七成。"
    "★ 阈值本身待外部模型对齐后再定。")

_ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.dirname(_ENGINE)


class EmptyResultError(ValueError):
    """★ 某个参数档位上过多的票返回空 —— 这是静默失败,不许放过。"""


# ────────────────────────────────────────────────────────────────────────
# 一 · 闸本体
# ────────────────────────────────────────────────────────────────────────

def empty_share(fn, cases: list, params: list, *,
                max_empty: float = MAX_EMPTY_SHARE) -> dict:
    """
    fn(case, param) -> 一串事件(len() 得出个数)。
    cases  = 每只票的输入(这里是 (high, low, close, atr))
    params = 参数档位(这里是 k 的取值)

    返回 {参数档: 空的占比},并把超线的档位列在 "★超线的" 里。
    """
    out: dict = {"每档空占比": {}, "★超线的": [], "上限": max_empty,
                 "阈值出处": THRESHOLD_SOURCE, "样本票数": len(cases)}
    for p in params:
        n_empty = 0
        for c in cases:
            try:
                got = fn(c, p)
            except Exception:                                      # noqa: BLE001
                got = []
            if got is None or len(got) == 0:
                n_empty += 1
        share = n_empty / max(1, len(cases))
        out["每档空占比"][str(p)] = round(share, 4)
        if share > max_empty:
            out["★超线的"].append(
                f"参数 {p}:{share:.1%} 的票返回空(> 上限 {max_empty:.0%})")
    out["过闸"] = not out["★超线的"]
    return out


def assert_not_empty(fn, cases, params, *, name: str,
                     max_empty: float = MAX_EMPTY_SHARE) -> dict:
    r = empty_share(fn, cases, params, max_empty=max_empty)
    if not r["过闸"]:
        raise EmptyResultError(
            f"[{name}] ★★ FAIL 静默返回空:\n  " + "\n  ".join(r["★超线的"]) +
            f"\n★ 这是「有没有值」的问题,不是「值对不对」的问题 —— "
            f"现有 14 道闸一道都抓不到它,所以才有这道闸。")
    return r


# ────────────────────────────────────────────────────────────────────────
# 二 · ★★★ 反向自测:证明**修之前会 FAIL、修之后 PASS**
# ────────────────────────────────────────────────────────────────────────

def _zigzag_BUGGY(high, low, close, atr, k=3.0, use_wick=True):
    """★★ 2026-10-30 修好**之前**的 zigzag_pivots —— 原样留在这里当反向样本。

    ★ 病根就在这两行:`if direction >= 0:` 和 `if direction <= 0:` 是两个
      **独立**的 if,direction == 0 时**都会执行**,后一段把前一段记下的
      跟踪极值覆盖掉 → 跳出条件退化成「单根 bar 振幅 ≥ k×ATR」。
    ★★ 不要「顺手把它也修好」—— 它的存在就是为了让这道闸有东西可以 FAIL。
    """
    hi_src = high if use_wick else close
    lo_src = low if use_wick else close
    n = len(close)
    piv = []
    direction = 0
    ext_i, ext_v = 0, close[0] if np.isfinite(close[0]) else np.nan
    for i in range(1, n):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        thr = k * a
        h, lo = hi_src[i], lo_src[i]
        if not (np.isfinite(h) and np.isfinite(lo)):
            continue
        if direction >= 0:
            if np.isfinite(ext_v) and h > ext_v:
                ext_i, ext_v = i, h
            if np.isfinite(ext_v) and (ext_v - lo) >= thr:
                piv.append((ext_i, "H", float(ext_v)))
                direction, ext_i, ext_v = -1, i, lo
                continue
        if direction <= 0:
            if np.isfinite(ext_v) and lo < ext_v:
                ext_i, ext_v = i, lo
            if np.isfinite(ext_v) and (h - ext_v) >= thr:
                piv.append((ext_i, "L", float(ext_v)))
                direction, ext_i, ext_v = 1, i, h
        if not np.isfinite(ext_v):
            ext_i, ext_v = i, h if direction >= 0 else lo
    out = []
    for p in piv:
        if out and out[-1][1] == p[1]:
            keep = p if ((p[1] == "H" and p[2] > out[-1][2]) or
                         (p[1] == "L" and p[2] < out[-1][2])) else out[-1]
            out[-1] = keep
        else:
            out.append(p)
    return out


#: ★ 自测用的参数档 —— 坏的时候 k=6/8/12 分别是 70.9% / 92.6% / 98.7%
SELFTEST_KS = (2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 12.0)

#: ★ 自测抽多少只票。全 300 只要跑 ~40 秒 × 2 版 × 7 档,太久;
#  ★★ 固定取**字母序前 N 只**(不是随机)—— 可复现,且不许挑样本。
SELFTEST_N = 40


def _cases(n: int = SELFTEST_N):
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    import pandas as pd
    from engine import data as D
    syms = sorted(D.load_manifest())[:n * 3]
    out = []
    for s in syms:
        df = D.load_daily(s)
        if df is None or len(df) < 300:
            continue
        df = df[df.index >= "2016-01-04"]
        pc = df["close"].shift(1)
        tr = pd.concat([df["high"] - df["low"],
                        (df["high"] - pc).abs(),
                        (df["low"] - pc).abs()], axis=1).max(axis=1)
        a = tr.rolling(14).mean().to_numpy(float)
        out.append(tuple(df[c].to_numpy(float) for c in ("high", "low", "close"))
                   + (a,))
        if len(out) >= n:
            break
    return out


def _selftest() -> None:
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    from engine.run_a0_states import zigzag_pivots as FIXED

    cases = _cases()
    print(f"★ 样本 {len(cases)} 只票(字母序前 {SELFTEST_N} 只,固定、不随机)"
          f" · k 档 {SELFTEST_KS}")

    def call(fn):
        return lambda c, k: fn(c[0], c[1], c[2], c[3], k=k, use_wick=True)

    # ① ★★★ 修之前:必须 FAIL
    bad = empty_share(call(_zigzag_BUGGY), cases, list(SELFTEST_KS))
    print(f"  修之前(_zigzag_BUGGY)每档空占比 {bad['每档空占比']}")
    assert not bad["过闸"], (
        "★★ 反向自测本身坏了:修之前的版本竟然过了这道闸 —— "
        "那说明闸没在判东西(或样本太小)。")
    print(f"  ✓ 修之前 FAIL,超线的档:{len(bad['★超线的'])} 个 "
          f"→ {bad['★超线的'][0]}")

    # ② ★ 修之后:必须 PASS
    good = assert_not_empty(call(FIXED), cases, list(SELFTEST_KS),
                            name="run_a0_states.zigzag_pivots")
    print(f"  修之后(engine 现状)每档空占比 {good['每档空占比']}")
    print("  ✓ 修之后 PASS —— 每一档的空占比都在上限以内")

    # ③ ★ 顺带守住「摆动点个数要随 k 单调下降」:
    #   ★★ 坏的时候这条也不成立(整列 0,不是下降,是塌)
    med = []
    for k in SELFTEST_KS:
        ns = [len(FIXED(c[0], c[1], c[2], c[3], k=k, use_wick=True)) for c in cases]
        med.append(float(np.median(ns)))
    print(f"  摆动点中位数随 k:{dict(zip(SELFTEST_KS, med))}")
    assert all(med[i] >= med[i + 1] for i in range(len(med) - 1)), (
        f"★ 摆动点个数没有随 k 单调下降:{med} —— 停下来查")
    assert med[-1] > 0, "★ 最高档 k=12 的中位摆动点数仍然是 0 —— 没修好"
    print("  ✓ 随 k 单调下降,且最高档 k=12 仍有摆动点")


if __name__ == "__main__":
    _selftest()
    print("\n✅ ⑮ 空结果闸自测通过")
