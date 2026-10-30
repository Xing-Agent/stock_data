#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 大+中池上「真重跑」的核心件 —— 2026-10-30

三秒版:上一轮是**拿现成流水按池子重切**;这一版是**重新跑回测**。
        差别只有一件事,但它很要紧:**`max_positions` 的名额是共享的** ——
        全池回测里被小盘票占掉的名额,重切的时候看不见。

★★ 怎么做到「不改 engine 一行」:
   `chain.run_chain(cfg, symbols, m=...)` 本来就收一个现成的矩阵包 `m`。
   所以这里的做法是:
     ① 照常 `matrices.build(cfg.raw, syms)` 把第一层全算好;
     ② ★ 把「池子口径」当成 ① universe 的**再一道与**:`m.universe &= scope_mask`;
     ③ 把改过的 `m` 喂回 `run_chain`。
   ★ 名额分配发生在 `chain.py` 的 ⑤「今天收盘产生明天的候选」那一段:
        cands = [j for j ... if m.entry[i,j] and m.universe[i,j] ...]
        slots = max_slots - len(pos);候选多于名额 → 按 rank_score 取前几只
     ★★ 所以把小盘从 `m.universe` 里拿掉,名额就**真的**在只有大+中的世界里
        重新分配了 —— 这正是重切做不到的那一件事。
   ★ `engine/` 一个字符都没改(照 `engine/pool_scope.py` 的先例)。

★★ 池子口径必须**按年**判,不能按票判:
   同一只票 2018 年是中盘、2023 年掉成小盘(300 只回测池里有 139 只
   至少有一年不在大+中档)。所以 scope_mask 是 [交易日 × 票] 的,
   每一天查「这只票**当年**的排名在不在 1–2000」。
   ★ 代码对照用 `pool_scope.PoolIndex`(company_id + 年份双条件),
     ★★ 不许按 symbol 直接对 —— 池子存当年年初代码(ANTM)、
        流水存最终代码(ELV)。

★ 「天」一律是**交易日**。
"""
from __future__ import annotations

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import pool_scope  # noqa: E402


# ══════════════════════════════════════════════════════════════════════════
# 一 · 池子口径掩膜 [交易日 × 票]
# ══════════════════════════════════════════════════════════════════════════

_IDX_CACHE: dict = {}


def pool_index() -> pool_scope.PoolIndex:
    if "idx" not in _IDX_CACHE:
        idx = pool_scope.PoolIndex()
        if idx.rows != pool_scope.POOL_KNOWN_ROWS:
            raise RuntimeError(
                f"★ 池子行数 {idx.rows} ≠ 已知 {pool_scope.POOL_KNOWN_ROWS} —— 停下来查")
        if idx.tier_mismatch:
            raise RuntimeError(f"★ rank 带 vs tier 列 不一致 {len(idx.tier_mismatch)} 行 —— 停")
        _IDX_CACHE["idx"] = idx
    return _IDX_CACHE["idx"]


def scope_mask(symbols, index, scope: str) -> tuple[np.ndarray, dict]:
    """[交易日 × 票] 的布尔掩膜:这一天这只票在不在该口径的池子里。

    ★ 「当年不在池」和「代码歧义」都判成**不在**(保守口径,和上一轮一致)。
    返回 (掩膜, 诊断)。
    """
    idx = pool_index()
    years = np.array([str(d.year) for d in index])
    uniq_years = sorted(set(years.tolist()))
    mask = np.zeros((len(index), len(symbols)), dtype=bool)
    how_cnt: dict[str, int] = {}
    per_year = {}
    for y in uniq_years:
        rowsel = (years == y)
        n_in = 0
        for j, s in enumerate(symbols):
            rk, _t, how = idx.resolve(s, y)
            how_cnt[how] = how_cnt.get(how, 0) + 1
            if pool_scope.in_scope(rk, scope):
                mask[rowsel, j] = True
                n_in += 1
        per_year[y] = n_in
    diag = {
        "口径": scope,
        "票×年 解析方式计数": how_cnt,
        "每年在池只数": per_year,
        "掩膜为真的票日比例": round(float(mask.mean()), 6),
    }
    return mask, diag


def apply_scope(m, scope: str) -> dict:
    """★ 把池子口径作为 ① universe 的再一道与,直接改 m(dataclass,可改)。"""
    mask, diag = scope_mask(m.symbols, m.index, scope)
    before = int(m.universe.sum())
    m.universe = m.universe & mask
    after = int(m.universe.sum())
    diag["universe 票日 收窄前"] = before
    diag["universe 票日 收窄后"] = after
    diag["universe 票日 砍掉比例"] = round(1 - after / before, 6) if before else None
    return diag


# ══════════════════════════════════════════════════════════════════════════
# 二 · 指标 —— ★ 口径和上一轮 `按链-大中池-1030.csv` 完全一致,便于逐项对差
# ══════════════════════════════════════════════════════════════════════════

TRADING_DAYS_PER_YEAR = 252          # ★ 交易日


def chain_metrics(led) -> dict:
    """从流水算出和上一轮同口径的几个数。★ 全部对子集有定义。"""
    n = len(led)
    if n == 0:
        return {"笔数": 0, "每笔净R": None, "胜率": None, "净盈亏": 0.0,
                "占用资金年化": None, "盈利笔数": 0}
    rn = led["r_multiple_net"].astype(float).to_numpy()
    rn = rn[np.isfinite(rn)]
    npnl = led["net_pnl"].astype(float).to_numpy()
    capdays = led["capital_days"].astype(float).to_numpy()
    cd = float(np.nansum(capdays))
    return {
        "笔数": int(n),
        "每笔净R": float(rn.mean()) if rn.size else None,
        "每笔净R_中位": float(np.median(rn)) if rn.size else None,
        "胜率": float((npnl > 0).mean()),
        "盈利笔数": int((npnl > 0).sum()),
        "净盈亏": float(np.nansum(npnl)),
        "占用资金年化": (float(np.nansum(npnl) / cd * TRADING_DAYS_PER_YEAR)
                         if cd > 0 else None),
        "平均持有交易日": float(led["holding_days"].astype(float).mean()),
        "总持有交易日": float(led["holding_days"].astype(float).sum()),
    }


def signal_counts(m) -> dict:
    """★ 纪律 7:报笔数必须同时报信号数。

    这里给**两个**数,口径写死:
      合格进场信号(口径内) = Σ (entry & universe)  —— 「今天收盘想买、且这只票今天能碰」
      ★ 不含 regime 闸和名额竞争 —— 那两道是「能不能买到」,不是「想不想买」。
    """
    return {
        "合格进场信号(entry&universe)": int((m.entry & m.universe).sum()),
        "原始进场触发(entry)": int(m.entry.sum()),
    }
