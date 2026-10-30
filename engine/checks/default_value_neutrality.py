#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ ⑯ 缺省值不许表态 —— 「没有历史」的格子不许被编成**任何有方向含义**的状态。

三秒版:我们对一只票**什么都还不知道**的时候,输出必须是「说不清」。
        如果缺省值是「底部 / 该买」,那就是**缺省值替我们表了态,而且表的是看多**。

══════════════════════════════════════════════════════════════════════════
★★★ 为什么必须有这一道(2026-10-30 真实事故,★ 而且这个值已经出门了)
══════════════════════════════════════════════════════════════════════════
`engine/state_axis_tri_1029.py: _confirm_sequence()` 里:
    last = confirmed[-1] if confirmed else None
    ...
    else:  stage = "1"          # ★★★ 病在这一行
★★ `last is None`(**从来没确认过任何阶段**)和 `last == "4"`
   (**刚从第四阶段出来**)共用同一条 else —— 后者推阶段一是对的,前者不是。

★ 实测规模(XING 版 spec,计分窗口 2018-01-01 起 / 2,011 个交易日):
      16,360 格(票·交易日)/ **58 只票**,迁移**全部**是 `1 → transition`
      阶段一占比 18.81% → 15.95%;transition 0.04% → 2.90%
  ★★ 含 ED / EXC / DTE 这种上市几十年的公用事业股 —— 从 2014 数据起点
     一直走平、从没确认过趋势阶段,整段被缺省成「底部」。
  ★★★ 换起点不变 → 它不是编错号,是**缺省值在表态**。

★★ 而这个值通过 `engine/state2_topology_1029.py` 给运营的逐日状态 CSV
   **已经交付出去了** —— 别的 bug 是内部数字错,★★★ 这一个是对外说了一句
   我们没有依据的看多。★ 产品侧两条红线正好管它:
     ① 不给方向  ② 每定义一个状态必须同时回答「怎么出来」
   —— 一个「从来没进去过」的状态被缺省成「底部」,两条都踩。

★★★ 为什么断言写成「不许有方向含义」而不是「阶段一占比不许超过 X%」:
   ★ 占比那种写法只能守住**这一次**这个数;★★ 「没有历史 → 不许表态」
     守住的是**这一类**。★ 这个 bug 是一类错,不是一处错。

★ 顺手扫过、**没有**同类问题的地方(留痕,免得下次重扫):
    · `state_axis_tri_1029.stage2_path_label()` —— `prev is None` 单独走,
      返回「首个阶段二(无前序)」★ 这是同一个情形**做对了**的样子
    · `engine/stages.py` —— 缺省只有 CHOP / WARMUP,★ 没有任何方向性阶段
"""
from __future__ import annotations

import os
import sys

import numpy as np

_ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ROOT = os.path.dirname(_ENGINE)

#: ★★ 有方向含义的状态 —— 任何一个都是「我们在说市场要往哪走」。
#   出处:Weinstein 四阶段。1 = 筑底(看多)· 2 = 上涨 · 3 = 做头 · 4 = 下跌。
DIRECTIONAL_STATES = ("1", "2", "3", "4")

#: ★ 允许的「说不清」状态
NEUTRAL_STATES = ("transition", "WARMUP")


class DefaultValueSpeaksError(ValueError):
    """★ 缺省值表了态 —— 不许放过。"""


# ────────────────────────────────────────────────────────────────────────
# 一 · 闸本体
# ────────────────────────────────────────────────────────────────────────

def check_no_history_neutral(raw, daily, *, min_bars: int,
                             name: str = "<未命名>") -> dict:
    """
    raw   = 原始标签序列(WARMUP / FLAT / ADV / DEC)
    daily = 逐日**已确认阶段**序列

    判据:在**第一次出现 ADV 或 DEC 的确认**之前,daily 里不许出现任何
      `DIRECTIONAL_STATES`。★ 为什么锚在 ADV/DEC 上:阶段二和阶段四是
      **数据直接说的**(在涨 / 在跌);阶段一和阶段三只能**从序列推**,
      ★★ 所以在没有任何 ADV/DEC 打底之前,推不出任何方向。
    """
    raw = np.asarray(raw, dtype=object)
    daily = np.asarray(daily, dtype=object)
    n = len(raw)

    # 第一次 ADV/DEC 连续满 min_bars 的那一格 = 序列真正起得来的最早位置
    first_trend = None
    cur, run = None, 0
    for i in range(n):
        r = raw[i]
        if r == "WARMUP":
            cur, run = None, 0
            continue
        run = run + 1 if r == cur else 1
        cur = r
        if run >= min_bars and r in ("ADV", "DEC"):
            first_trend = i
            break

    end = n if first_trend is None else first_trend
    pre = daily[:end]
    bad_idx = [int(i) for i in range(end) if pre[i] in DIRECTIONAL_STATES]
    out = {
        "名": name, "总格数": int(n),
        "第一次ADV/DEC确认于": first_trend,
        "无历史区段格数": int(end),
        "★无历史区段里被编成方向性阶段的格数": len(bad_idx),
        "被编成了什么": sorted({str(pre[i]) for i in bad_idx}),
        "过闸": not bad_idx,
    }
    return out


def assert_neutral(raw, daily, *, min_bars: int, name: str) -> dict:
    r = check_no_history_neutral(raw, daily, min_bars=min_bars, name=name)
    if not r["过闸"]:
        raise DefaultValueSpeaksError(
            f"[{name}] ★★ FAIL 缺省值表了态:在第一次 ADV/DEC 确认之前,"
            f"有 {r['★无历史区段里被编成方向性阶段的格数']} 格被编成了 "
            f"{r['被编成了什么']} —— ★ 那几格我们**没有任何依据**下方向判断,"
            f"只能是「说不清」(transition)。")
    return r


# ────────────────────────────────────────────────────────────────────────
# 二 · ★★★ 反向自测:证明修之前 FAIL、修之后 PASS
# ────────────────────────────────────────────────────────────────────────

def _confirm_BUGGY(raw, min_bars, WARMUP="WARMUP"):
    """★★ 修好**之前**的 `_confirm_sequence`,原样留档。
    ★ 病根:最后那个 `else: stage = "1"` 被 `last is None` 和 `last == "4"` 共用。
    ★★ 不要「顺手修好它」—— 它存在的理由就是让这道闸有东西可以 FAIL。
    """
    n = len(raw)
    daily = np.full(n, WARMUP, dtype=object)
    confirmed: list[str] = []
    cur_raw, run = None, 0
    cur_stage = WARMUP
    for i in range(n):
        r = raw[i]
        if r == WARMUP:
            daily[i] = WARMUP
            cur_raw, run = None, 0
            continue
        run = run + 1 if r == cur_raw else 1
        cur_raw = r
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
                confirmed.append(stage)
            cur_stage = stage
        daily[i] = cur_stage if cur_stage != WARMUP else "transition"
    return daily


#: ★ 自测用的票 —— 事故里变号最多的几只,★ 固定名单、不随机。
#  出处:probe/v2_rerun_1030/stage2_default_bull_1030.json 的「逐票」前几名。
SELFTEST_SYMBOLS = ("NEU", "ED", "AGNC", "EXC", "PPG", "BDN", "DTE", "UHAL")


def _selftest() -> None:
    if _ROOT not in sys.path:
        sys.path.insert(0, _ROOT)
    from engine import cache
    from engine import state_axis_tri_1029 as tri

    p = cache.load()
    cl = p["close"]
    ma = cl.rolling(150, min_periods=150).mean()
    spec = tri.STAGE_VERSIONS["XING版"]
    syms = [s for s in SELFTEST_SYMBOLS if s in cl.columns]
    print(f"★ 样本 {len(syms)} 只(固定名单,不随机):{syms}")
    print(f"★ spec = XING版({spec.note})· min_bars = {spec.min_bars} 个交易日")

    n_fail_before = n_pass_after = 0
    for s in syms:
        raw = tri._raw_stage(cl[s].to_numpy(), ma[s].to_numpy(), spec)
        # ① 修之前:必须 FAIL
        d_bad = _confirm_BUGGY(raw, spec.min_bars, WARMUP=tri.WARMUP)
        rb = check_no_history_neutral(raw, d_bad, min_bars=spec.min_bars, name=s)
        if not rb["过闸"]:
            n_fail_before += 1
        # ② 修之后:必须 PASS
        d_ok, _ = tri._confirm_sequence(raw, spec.min_bars)
        assert_neutral(raw, d_ok, min_bars=spec.min_bars, name=s)
        n_pass_after += 1
        if s == syms[0]:
            print(f"   例 {s}:无历史区段 {rb['无历史区段格数']} 格 —— "
                  f"修之前有 {rb['★无历史区段里被编成方向性阶段的格数']} 格被编成 "
                  f"{rb['被编成了什么']};修之后 0 格")

    assert n_fail_before == len(syms), (
        f"★★ 反向自测本身坏了:只有 {n_fail_before}/{len(syms)} 只票在修之前 FAIL "
        f"—— 那说明闸没在判东西,或者样本挑错了。")
    print(f"  ✓ 修之前 {n_fail_before}/{len(syms)} 只票 FAIL")
    print(f"  ✓ 修之后 {n_pass_after}/{len(syms)} 只票 PASS")
    print("  ★ 断言的形状是「没有历史的格子不许被编成任何有方向含义的阶段」—— "
          "★★ 守的是这一类,不是某个占比。")


if __name__ == "__main__":
    _selftest()
    print("\n✅ ⑯ 缺省值不许表态 自测通过")
