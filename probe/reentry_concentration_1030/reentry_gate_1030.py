#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 「重新进场」的冷却期 / 次数上限 —— 运行时挂钩(2026-10-30)

══════════════════════════════════════════════════════════════════════════
★★★ 三秒版 —— 这个文件做的事和任务书写的**方向相反**,原因必须先看懂:
  任务书说「43 份配置一条都没有再回去的机制,要给它装上」。
  ★★★ 核过了:**引擎里本来就有。** chain.py 第 ⑤ 步是
        cands = [j for j in ... if j not in pos and m.entry[i,j] and m.universe[i,j] ...]
     ★ 它每天都重新查一遍进场条件,**只排除「现在还持着的」**。
     → 「原进场条件重新成立 + 仓位空着 → 再进一次」= 引擎的默认行为。
  ★★ 实测佐证:17/18 条链的流水里都有重进(趋势跟随 205 只票里 129 只重进过;
     技-14 原著版 5,235 笔重进 vs 270 笔首次)。
  ★★★ 所以缺的**不是重新进场**,缺的是**冷却期和次数上限这两个约束**。
     → 本文件把这两个约束装上,量的是「**管住**重进」的效果,
       ★ 而 M=0 那一档正好就是「**没有**重新进场」的反事实 ——
         也就是任务书以为我们现在所处的那个世界。
══════════════════════════════════════════════════════════════════════════

★ 怎么做到 engine/ 一个字符都不改:
  照 probe/v2_rerun_1030/rerun_core_1030.py 的先例 —— ★ 只改 `m.universe`
  这个 dataclass 字段(那份先例就是 `m.universe = m.universe & mask`)。
  ★★ 第 ⑤ 步唯一的闸口就是 `m.universe[i,j]`,所以把某些「票日」格子按成 False,
     那只票那天就产不出候选 → 次日开盘也就不会买。

★★★ 为什么要迭代到不动点:封掉几笔之后**名额会空出来**,空出来的名额会被
  别的票占掉,于是产生新的进场 —— 新的进场又要重新接受同一套约束检查。
  ★ 所以:跑 → 从流水里找出违约的进场 → 把对应格子加进封禁表 → 再跑,
    直到流水里**一笔违约都没有**。★ 封禁表只增不减 → 必然收敛。
  ★★★ 没收敛就 `raise` —— 不许拿一个还违约的流水当结果报上去
     (「没查」和「查了没问题」必须分开)。

★★★ 我自己填的数(一律标「XING 填的」,**不许标原著**):
     ① 冷却期 N ∈ {3, 5, 10} 个交易日          ← XING 填的
     ② 同一只票一轮里最多重进 M ∈ {0, 1, 2, 3} 次 ← XING 填的
     ③ ★★ 「一轮」原著/任务书都没定义 —— 本文件取**整个回测期**
        (2014–2025)为一轮,★ 这是最严的一端、且不含任何自由参数;
        ★★ 另给「一轮 = 一个日历年」作敏感度(同样机械、无自由参数)。
        ★★★ 这个取舍是我们定的,报告里必须写明。
"""
from __future__ import annotations

import numpy as np
import pandas as pd

#: ★★★ XING 填的,不是原著。邻近三点,判据是「三点必须全部同向」而不是挑最好的
COOLDOWN_GRID = (3, 5, 10)
CAP_GRID = (1, 2, 3)

MAX_ITERS = 25


def _entry_day_locs(led: pd.DataFrame, idx: pd.DatetimeIndex,
                    symbols: list[str]) -> list[tuple[int, int]]:
    """流水 → [(票列号, 进场日行号)]。★ 用 get_indexer,不手搓日期对齐。"""
    if not len(led):
        return []
    col = {s: j for j, s in enumerate(symbols)}
    ei = idx.get_indexer(pd.DatetimeIndex(led["entry_date"]))
    out = []
    for sym, a in zip(led["symbol"].to_numpy(), ei):
        j = col.get(sym)
        if j is not None and a >= 0:
            out.append((int(j), int(a)))
    return out


def _exit_day_locs(led: pd.DataFrame, idx: pd.DatetimeIndex,
                   symbols: list[str]) -> list[tuple[int, int]]:
    if not len(led):
        return []
    col = {s: j for j, s in enumerate(symbols)}
    xi = idx.get_indexer(pd.DatetimeIndex(led["exit_date"]))
    out = []
    for sym, a in zip(led["symbol"].to_numpy(), xi):
        j = col.get(sym)
        if j is not None and a >= 0:
            out.append((int(j), int(a)))
    return out


def violations(led: pd.DataFrame, idx: pd.DatetimeIndex, symbols: list[str],
               cooldown: int | None, cap: int | None,
               round_mode: str = "whole") -> list[tuple[int, int]]:
    """
    ★ 返回「这些(票,信号日行号)格子必须封掉」的清单。

    cooldown : 离场后 N 个交易日内不许重进(None = 不设)
    cap      : 同票一轮里最多重进 M 次(None = 不设;0 = 一次都不许重进)
    round_mode: "whole" = 整个回测期为一轮;"year" = 一个日历年为一轮

    ★★ 封的是**信号日**:第 ⑤ 步在第 i 天产生候选、第 i+1 天开盘成交,
       所以要拦掉第 d 天的成交,封的是第 d−1 天的格子。
    """
    if not len(led):
        return []
    bad: set[tuple[int, int]] = set()
    n = len(idx)
    d = led.copy()
    d["_ei"] = idx.get_indexer(pd.DatetimeIndex(d["entry_date"]))
    d["_xi"] = idx.get_indexer(pd.DatetimeIndex(d["exit_date"]))
    col = {s: j for j, s in enumerate(symbols)}
    d["_j"] = d["symbol"].map(col)
    d = d[d["_j"].notna() & (d["_ei"] >= 0)].copy()
    d["_j"] = d["_j"].astype(int)
    d = d.sort_values(["_j", "_ei"], kind="mergesort")

    for j, g in d.groupby("_j", sort=False):
        ei = g["_ei"].to_numpy(int)
        xi = g["_xi"].to_numpy(int)

        # ── ① 冷却期:离场 e 之后 N 个交易日内不许重进
        #    禁止成交日 e+1 .. e+N  →  封信号日 e .. e+N-1
        if cooldown is not None and cooldown > 0:
            for e in xi:
                if e < 0:
                    continue
                for i in range(e, min(n, e + int(cooldown))):
                    bad.add((j, i))

        # ── ② 次数上限:一轮里最多重进 M 次 → 一轮里最多 1+M 次进场
        if cap is not None:
            if round_mode == "whole":
                groups = [np.arange(len(ei))]
            elif round_mode == "year":
                yrs = np.array([idx[a].year for a in ei])
                groups = [np.where(yrs == y)[0] for y in sorted(set(yrs.tolist()))]
            else:
                raise ValueError(f"★ 不认识的 round_mode={round_mode!r}")
            for sel in groups:
                keep = int(cap) + 1          # 首次 + M 次重进
                if len(sel) <= keep:
                    continue
                # 超额的那些进场一律封掉:从第 keep 笔的信号日起全封到本轮末
                last_ok = ei[sel[keep - 1]]
                if round_mode == "whole":
                    hi = n
                else:
                    y = idx[ei[sel[0]]].year
                    hi = int(np.searchsorted(
                        np.array([dt.year for dt in idx]), y, side="right"))
                for i in range(int(last_ok), hi):
                    bad.add((j, i))
    return sorted(bad)


def run_constrained(cfg, symbols, m, run_chain, *, cooldown=None, cap=None,
                    round_mode="whole", **run_kw):
    """
    ★ 跑一条带约束的链,迭代到不动点。
    返回 (结果, 诊断)。★★ m 会被改(m.universe),所以外面要传**副本**。
    """
    base_uni = m.universe.copy()
    idx = m.index
    blocked: set[tuple[int, int]] = set()
    hist = []
    res = None
    for it in range(MAX_ITERS):
        uni = base_uni.copy()
        if blocked:
            rr = np.fromiter((b[1] for b in blocked), int, len(blocked))
            cc = np.fromiter((b[0] for b in blocked), int, len(blocked))
            uni[rr, cc] = False
        m.universe = uni
        res = run_chain(cfg, symbols, m=m, **run_kw)
        v = violations(res.ledger, idx, list(m.symbols), cooldown, cap, round_mode)
        new = [x for x in v if x not in blocked]
        hist.append({"轮": it + 1, "笔数": int(len(res.ledger)),
                     "本轮查出违约格子": len(v), "新增封禁": len(new),
                     "累计封禁": len(blocked) + len(new)})
        if not new:
            return res, {"收敛": True, "迭代轮数": it + 1, "累计封禁格子": len(blocked),
                         "迭代轨迹": hist}
        blocked.update(new)
    # ★★★ 没收敛不许报结果
    raise RuntimeError(
        f"★ 冷却期={cooldown} 上限={cap} 迭代 {MAX_ITERS} 轮仍未收敛 —— "
        f"轨迹 {hist[-3:]}。★ 不拿一份还违约的流水当结果。")
