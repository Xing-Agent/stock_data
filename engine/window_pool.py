"""
两窗口两池子硬关 —— 九关里的第九关,也是最难过的一关。

大白话:把数据切成四格,同一个信号在四格里各跑一遍。
  时间切两段:2018–2021 / 2022–2025
  票切两堆:  池A(代码字母序奇数位) / 池B(偶数位)
四格 = 2 段 × 2 堆。

过关要同时满足两条:
  一、四格的 Z ★ 符号必须一致 —— 有一格反号就是没过
  二、最弱那一格的「信号均值 − 随机均值」★ 仍须为正
没过不等于没用,但结论必须降级成「只在 XX 窗口 / XX 池子上成立」。

★ 每格里的随机对照必须在同格内取样 —— 用别格的票当对照等于偷看。

★ 池子为什么用奇偶拆不用随机拆:随机拆可以重抽,重抽就能抽到好看的那一次。
  奇偶拆只有唯一一种结果,没有重抽的空间。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

import numpy as np
import pandas as pd

from . import stats_gate
from .stats_gate import BootstrapResult

WINDOWS: tuple[tuple[str, str, str], ...] = (
    ("2018-2021", "2018-01-01", "2021-12-31"),
    ("2022-2025", "2022-01-01", "2025-12-31"),
)
POOLS: tuple[str, ...] = ("A", "B")


@dataclass
class CellResult:
    window: str
    pool: str
    result: BootstrapResult

    @property
    def key(self) -> str:
        return f"{self.window}×池{self.pool}"


@dataclass
class WindowPoolVerdict:
    cells: list[CellResult] = field(default_factory=list)
    passed: bool = False
    reasons: list[str] = field(default_factory=list)
    downgraded_conclusion: str = ""

    def report(self) -> str:
        lines = ["两窗口两池子硬关(四格):"]
        for c in self.cells:
            r = c.result
            lines.append(f"  {c.key:22s} n={r.n_signal:5d} "
                         f"差值={r.diff:+.4f} Z={r.z_effect:+.2f} p={r.p_empirical:.4f}")
        lines.append(f"  → 硬关:{'通过' if self.passed else '没过'}")
        for why in self.reasons:
            lines.append(f"    · {why}")
        if self.downgraded_conclusion:
            lines.append(f"  ★ 结论降级为:{self.downgraded_conclusion}")
        return "\n".join(lines)


def split_pool(symbols: list[str], which: str) -> list[str]:
    """池 A = 字母序奇数位,池 B = 偶数位。"""
    s = sorted(symbols)
    return s[0::2] if which.upper() == "A" else s[1::2]


def _cell_seed(wname: str, pool: str) -> int:
    """
    每格的随机种子偏移。★ 必须是确定性的。

    ★★ 2026-10-28 修的 bug:这里原来写的是 `hash((wname, pool)) % 10_000`。
      Python 对字符串的 hash() 是★ 逐进程随机的(PYTHONHASHSEED 默认 random),
      所以同一份代码、同一份数据,★ 每跑一次四格的 Z 和差值都不一样 ——
      硬关是「九关」里唯一的硬关,它必须能复现,否则「过没过」是可以靠重跑刷出来的。

      实测不稳定幅度(流派一 slots10,10 个不同种子):
        四格 Z 的极差 0.15 ~ 0.21,其中 2022-2025×池B 在 1.92 ~ 2.07 之间来回,
        ★ 正好跨过「机构级 Z=2.0」那条线 —— 同一条链能被标成机构级,也能被标成没到。

      改成按字符内容算的确定性哈希(FNV-1a),和进程无关。
    """
    h = 2166136261
    for ch in f"{wname}×池{pool}".encode("utf-8"):
        h = ((h ^ ch) * 16777619) & 0xFFFFFFFF
    return h % 10_000


def run_grid(signal_fn: Callable[[str, str, list[str]], tuple[list[float], Callable]],
             symbols: list[str],
             B: int = stats_gate.B_DEFAULT,
             seed: int = 20181001) -> WindowPoolVerdict:
    """
    跑完四格。

    signal_fn(start, end, cell_symbols) 必须返回:
      (信号结果列表, 随机对照取样器)
    ★ 取样器内部只允许用 cell_symbols 和 [start, end] 之间的数据 —— 同格内取样。
    """
    cells: list[CellResult] = []
    for wname, wstart, wend in WINDOWS:
        for pool in POOLS:
            cell_syms = split_pool(symbols, pool)
            values, sampler = signal_fn(wstart, wend, cell_syms)
            r = stats_gate.bootstrap_test(
                name=f"{wname}×池{pool}",
                signal_values=values,
                random_sampler=sampler,
                B=B,
                seed=seed + _cell_seed(wname, pool),
                note="同格内取样",
            )
            cells.append(CellResult(wname, pool, r))
    return judge(cells)


def judge(cells: list[CellResult]) -> WindowPoolVerdict:
    """四格结果 → 判定。两条都要满足才算过。"""
    v = WindowPoolVerdict(cells=cells)
    zs = [c.result.z_effect for c in cells]
    diffs = [c.result.diff for c in cells]
    reasons: list[str] = []
    ok = True

    if any(not np.isfinite(z) for z in zs):
        bad = [c.key for c in cells if not np.isfinite(c.result.z_effect)]
        ok = False
        reasons.append(f"有格子算不出 Z(样本太少或随机分布退化):{bad}")
    else:
        signs = {int(np.sign(z)) for z in zs}
        if len(signs) > 1:
            ok = False
            flip = [f"{c.key}(Z={c.result.z_effect:+.2f})" for c in cells
                    if np.sign(c.result.z_effect) != np.sign(zs[0])]
            reasons.append(f"★ 第一条没过:四格 Z 符号不一致,反号的格子 {flip}")
        else:
            reasons.append(f"第一条通过:四格 Z 符号一致(全为 {'正' if zs[0] > 0 else '负'})")

    if any(not np.isfinite(d) for d in diffs):
        ok = False
        reasons.append("有格子算不出差值")
    else:
        weakest = min(cells, key=lambda c: c.result.diff)
        if weakest.result.diff <= 0:
            ok = False
            reasons.append(f"★ 第二条没过:最弱格 {weakest.key} 差值 "
                           f"{weakest.result.diff:+.4f} ≤ 0")
        else:
            reasons.append(f"第二条通过:最弱格 {weakest.key} 差值 "
                           f"{weakest.result.diff:+.4f} > 0")

    v.passed = ok
    v.reasons = reasons
    if not ok:
        good = [c.key for c in cells
                if np.isfinite(c.result.z_effect)
                and c.result.z_effect >= stats_gate.Z_BASIC and c.result.diff > 0]
        if good:
            v.downgraded_conclusion = ("只在 " + "、".join(good) +
                                       " 上成立,不能当成普遍结论用")
        else:
            v.downgraded_conclusion = "四格里没有一格站得住 —— 这个信号不要用"
    return v


def cell_mask(index: pd.DatetimeIndex, window: str) -> pd.DatetimeIndex:
    """取某个窗口的交易日。"""
    for name, start, end in WINDOWS:
        if name == window:
            return index[(index >= pd.Timestamp(start)) & (index <= pd.Timestamp(end))]
    raise ValueError(f"窗口只能是 {[w[0] for w in WINDOWS]},给的是 {window}")


__all__ = ["WINDOWS", "POOLS", "CellResult", "WindowPoolVerdict",
           "split_pool", "run_grid", "judge", "cell_mask"]
