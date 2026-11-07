# -*- coding: utf-8 -*-
"""
★★★ 随机同档覆盖层 —— ★ 把「随机排序」这把尺子限定在**同一个成本档位内抽**。
   ★★ 《115》6.3 第 ③ 档；★★★ 《117》第二节把它从第三顶成第一。

★★★★★ 为什么必须修（#86，不是一个想法，是一处错）：
  · `engine/chain.py:150 _liquidity_tiers()` 按**当日横截面 ADV20 的 1/3、2/3** 切三档,
    成本 高 5 / 中 15 / 低 30 bps（`costs.friction_tiers`）。
  · 而三条代表链的 `ranking` 全是 **ADV20 desc** → ★★★ **排序变量和成本档位同源**。
  → ★★ ADV20 排序系统性落在 5 bps 那一档；旧的「全池均匀随机」落在 5/15/30 的混合。
  → ★★★★★ **任何 ADV20 排序的臂，即使选股本事为零，也会在净口径上赢旧随机对照。**

★★★ 本覆盖层做的事（★ 只有一件）：
   随机分数**只打在 `tier == 目标档` 的格子上**，其余留 NaN（和缺价格的格子一样不被选）。
   → ★★ 于是随机对照和 ADV20 **买的是同一个成本档位里的票**，
     ★★★ 它回答的问题也更准：「**在同样买得起的票里**，ADV20 这个排序有没有用」。

★★★★★ 档位用的是 **engine 自己那个函数**（`chain._liquidity_tiers`），
   ★ 喂它的 adv20 也是 engine 自己那一句（`matrices.adv_matrix(20, syms).to_numpy(float)`,
     见 `engine/matrices.py:1385`）→ ★★★ **档位定义和引擎逐字节同源，我没有另立一套**。

★★★ engine 零改动：只在进程内替换 `matrices.rank_score_matrix` 的函数指针，
   ★ 认不出的 spec **原样退回原函数**（不自己猜）。

★★★★★ 自证（#80 的教训：要证明「它起作用了」，不是「我按了开关」）：
   本模块的 `自证()` 返回**格子级证据**：打分格子总数 · 其中 tier==目标档的比例（必须 1.0）
   · 旧口径（全池随机）下这些格子的档位分布 —— ★★ 三样一起落盘。
   ★★★ 而**结果级**的证明在驱动器里：新随机臂的「每笔摩擦 R」必须贴上 ADV20
     （预先登记的带 0.85~1.20），旧随机臂是 1.61~2.21 倍。
"""
from __future__ import annotations
import os, sys
import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from engine import matrices as M                                  # noqa: E402
from engine import chain as C                                     # noqa: E402

_原 = None
_自证 = {"调用次数": 0, "明细": []}
# ★ 档位矩阵按 symbols 缓存（★★ 一条臂里会被调用多次，重算一遍要几十秒）
_TIER_CACHE: dict[tuple, object] = {}


def _档位(symbols: list[str]):
    """★★★ 用 engine 自己的函数算档位 —— 我不另立一套定义。"""
    key = (len(symbols), symbols[0], symbols[-1])
    hit = _TIER_CACHE.get(key)
    if hit is not None:
        return hit
    adv = M.adv_matrix(20, symbols)                 # ★ engine/matrices.py:1385 同一句
    tiers = C._liquidity_tiers(adv.to_numpy(dtype=float))   # ★★★ engine 的函数本体
    out = pd.DataFrame(tiers, index=adv.index, columns=adv.columns)
    _TIER_CACHE[key] = out
    return out


def _覆盖(spec, symbols, cfg=None):
    """★ 只认 `ranking.primary` 里 random_seed + random_cost_tier 这一对；其余原样转回。"""
    if isinstance(spec, dict):
        prim = (spec.get("primary") or {})
        seed = prim.get("random_seed")
        tier_want = prim.get("random_cost_tier")
        if seed is not None and tier_want is not None:
            # ★★★ 1107 第 10 次唤醒补：接受**档位列表**（红线② 的 tier0∪tier1 那一档）
            要 = [int(x) for x in (tier_want if isinstance(tier_want, (list, tuple))
                                   else [tier_want])]
            assert 要 and all(x in (0, 1, 2) for x in 要), \
                f"★ random_cost_tier 只认 0/1/2 或它们的列表，给的是 {tier_want!r}"
            close = M.cache.field("close", symbols)
            tiers = _档位(symbols).reindex(index=close.index, columns=close.columns)
            rng = np.random.default_rng(int(seed))
            s = pd.DataFrame(rng.random(close.shape), index=close.index,
                             columns=close.columns)
            # ★★★ 两个条件都要：有价格（和旧口径一致）+ 在目标成本档位里
            可选 = close.notna() & tiers.isin(要)
            s = s.where(可选)
            # ★ 自证：格子级证据，★★ 只在第一次调用时统计（省时间）
            if _自证["调用次数"] == 0:
                有价 = int(close.notna().to_numpy().sum())
                打分 = int(可选.to_numpy().sum())
                分布 = {int(k): int(v) for k, v in
                        pd.Series(tiers.to_numpy().ravel()).value_counts().items()}
                旧口径分布 = {int(k): int(v) for k, v in
                          pd.Series(tiers.where(close.notna()).to_numpy().ravel()
                                    ).dropna().astype(int).value_counts().items()}
                _自证["明细"].append({
                    "★目标成本档位": 要,
                    "★★★档位定义来自": "engine/chain.py:_liquidity_tiers（engine 的函数本体）",
                    "★★★喂它的adv20来自": "engine/matrices.py:adv_matrix(20) —— 和 1385 行同一句",
                    "有价格的格子": 有价,
                    "★★★本臂打分的格子": 打分,
                    "★★★打分格子里 tier∈目标 的比例": 1.0 if 打分 else None,
                    "★★★打分格子占有价格子的比例": round(打分 / 有价, 6) if 有价 else None,
                    "★★旧口径(全池随机)会打分的格子": 有价,
                    "★★旧口径那些格子的档位分布": 旧口径分布,
                    "全矩阵档位分布(含缺价)": 分布,
                })
            _自证["调用次数"] += 1
            return s
    return _原(spec, symbols, cfg)


def install() -> dict:
    """★ 装覆盖层（★★ 叠在已装的覆盖层之上，原样退回那一层）。"""
    global _原
    before = M.rank_score_matrix
    if _原 is None:
        _原 = before
    M.rank_score_matrix = _覆盖
    return {"★上一层函数id": id(before), "★覆盖后id": id(M.rank_score_matrix),
            "★真的换掉了": id(M.rank_score_matrix) != id(before),
            "★上一层还留着": _原 is not None,
            "★★★engine改动": "零（只替换进程内函数指针）",
            "★认不出的spec怎么办": "原样转回上一层，不自己猜",
            "★★★档位定义": "engine/chain.py:_liquidity_tiers 本体（没另立一套）"}


def 自证() -> dict:
    return dict(_自证)
