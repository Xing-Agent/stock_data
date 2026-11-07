# -*- coding: utf-8 -*-
"""
★★★ 回看期覆盖层 —— ★ 让 `ranking` 的回看期能变（红线②：原著没给的数必须跑相邻三点）。

★★ 为什么需要覆盖层（★★★ engine/ 一个字节都不许改）：
  · `rank_score_matrix` 里，`spec` 是字符串时走 `rs_rank_matrix(126, symbols)`
    —— ★★ **126 写死在代码里**，配置改不到。
  · ATR 那一支里 `lb = 60` 也写死。
→ ★ 所以这里做**进程内覆盖层**：包一层 `rank_score_matrix`，
  ★★ 认一个新配置键 `ranking.primary.rs_lookback`，认不出就**原样转回原函数**。
  ★★★ 这和《93》第②层那批跑批用的是同一套做法（照抄 接新财报库_1106.py 的模式）。

★ 自证：装完打印「原函数 / 覆盖函数」的 id，确认真的换掉了。
"""
from __future__ import annotations
import sys, os
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT)
from engine import matrices as M                              # noqa: E402

_原 = M.rank_score_matrix


def _覆盖(spec, symbols, cfg=None):
    """★ 处理两种自定义键；★★ 其余一律原样转回原函数。
      · `rs_lookback`  → 相对强度排名，回看期可变
      · `mom_lookback` → ★★★ 波动调整动量 (Close_t/Close_{t−n}−1) ÷ ATR%20，
        ★ 回看期可变（引擎那一支把 n 写死成 60，配置改不到）
    """
    if isinstance(spec, dict):
        prim = (spec.get("primary") or {})
        # ★★★ 随机排序（Gemini 第 50 轮点的决定性对照）——
        #   ★ 用来看「买入触发本身有没有用」还是「全靠排序在撑」。
        #   ★★ 每个 (日期 × 票) 格子一个固定随机数（按种子可复现），engine 零改动。
        seed = prim.get("random_seed")
        if seed is not None:
            import numpy as _np
            close = M.cache.field("close", symbols)
            rng = _np.random.default_rng(int(seed))
            s = pd.DataFrame(rng.random(close.shape), index=close.index,
                             columns=close.columns)
            # ★ 只在有价格的格子上给分数，缺价的留 NaN（和其他挑法一致）
            return s.where(close.notna())
        # ★★ 波动率倒数（Gemini 第 50 轮：学术上有依据 Frazzini & Pedersen 2014）
        ivw = prim.get("inv_vol_window")
        if ivw is not None:
            n = int(ivw)
            assert 5 <= n <= 500, f"★ inv_vol_window 不合理：{n}"
            close = M.cache.field("close", symbols)
            vol = close.pct_change().rolling(n, min_periods=n).std()
            s = 1.0 / vol.replace(0.0, float("nan"))
            order = str(prim.get("order", "desc")).lower()
            return -s if order == "asc" else s
        mlb = prim.get("mom_lookback")
        if mlb is not None:
            n = int(mlb)
            assert 5 <= n <= 1000, f"★ mom_lookback 不合理：{n}"
            close = M.cache.field("close", symbols)
            mom = close / close.shift(n) - 1.0
            # ★★ 分母照抄引擎那一支的默认口径 close_t（engine/matrices.py:1181）
            atr_pct = M.atr_matrix(20, symbols) / close
            s = mom / atr_pct.replace(0.0, float("nan"))
            order = str(prim.get("order", "desc")).lower()
            return -s if order == "asc" else s
        lb = prim.get("rs_lookback")
        if lb is not None:
            n = int(lb)
            assert 5 <= n <= 1000, f"★ rs_lookback 不合理：{n}"
            # ★★ 用引擎自己的 rs_rank_matrix —— 口径和 126 那一支逐字节同源
            s = M.rs_rank_matrix(n, symbols)
            order = str(prim.get("order", "desc")).lower()
            return -s if order == "asc" else s
    return _原(spec, symbols, cfg)


def install() -> dict:
    """★ 装覆盖层，返回自证。"""
    before = id(M.rank_score_matrix)
    M.rank_score_matrix = _覆盖
    return {"★原函数id": before, "★覆盖后id": id(M.rank_score_matrix),
            "★真的换掉了": id(M.rank_score_matrix) != before,
            "★原函数还留着": _原 is not None,
            "★★★engine改动": "零（只在进程内替换函数指针）",
            "★认不出的spec怎么办": "原样转回原函数，不自己猜"}
