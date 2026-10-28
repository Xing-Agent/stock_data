"""
判据 —— 整个引擎的尺子。

大白话:一个信号赚了钱,可能是它真有用,也可能是运气好、或者是因为
它专挑波动大的票。这个文件干的事就是:把同一段时间、同一个池子里
「随机瞎买」跑 1000 次,看信号的成绩落在这 1000 次的什么位置。
落在很靠前的位置,才算真有东西。

两个数字,只看这两个:
  经验 p 值 = (1 + #{随机 ≥ 信号}) / (B + 1)
  效应量  Z = (信号均值 − 随机均值) / 随机标准差
判定线:Z ≥ 1.65 基础显著;Z ≥ 2.00 机构级。

★★ 严禁用「超过 N 次随机里的最大值」这种门槛。
   原因:最大值会随着跑的次数往上爬 —— B 调大一点结论就变了,
   那不是尺子,那是橡皮尺。本文件只用 (均值, 标准差, 排名分位) 三样,
   任何地方都不取随机分布的 max。

三套对照组,一个都不能少(缺一套 verdict 直接判不通过):
  ① 条件分层随机 stratified —— 同一天、同一个池子里随机挑票。
     管的是「是不是只要那天买什么都涨」。
  ② 块重排 Circular Block Bootstrap —— Politis & Romano (1994)。
     整段整段地搬,保留收益序列的自相关;管的是「是不是只是趋势顺风」。
  ③ 极性反转 polarity —— 同样的进场点强制做空。
     ★ 如果多空两边 Z 都是正的,说明挑的是「波动大的票」不是「会涨的票」。

出处:Efron & Tibshirani (1993) An Introduction to the Bootstrap, Ch.15-16;
      Aronson (2006) Evidence-Based Technical Analysis, Ch.6;
      Politis & Romano (1994) The Stationary Bootstrap, JASA 89(428).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Sequence

import numpy as np

B_DEFAULT = 1000
Z_BASIC = 1.65        # 基础显著
Z_INSTITUTIONAL = 2.0  # 机构级
MIN_N = 100           # 九关第六关:样本量下限


# ---------------------------------------------------------------- 结果容器

@dataclass
class BootstrapResult:
    """一套对照组跑完的结果。"""
    name: str
    n_signal: int
    B: int
    signal_mean: float
    random_mean: float
    random_std: float
    p_empirical: float
    z_effect: float
    note: str = ""

    @property
    def diff(self) -> float:
        """信号 − 随机。两窗口两池子硬关要求最弱那格的这个值仍为正。"""
        return self.signal_mean - self.random_mean

    @property
    def level(self) -> str:
        if self.z_effect >= Z_INSTITUTIONAL:
            return "机构级"
        if self.z_effect >= Z_BASIC:
            return "基础显著"
        return "不显著"

    def line(self) -> str:
        return (f"  {self.name:28s} n={self.n_signal:5d} "
                f"信号均值={self.signal_mean:+.4f} 随机均值={self.random_mean:+.4f} "
                f"σ随机={self.random_std:.4f} p={self.p_empirical:.4f} "
                f"Z={self.z_effect:+.2f} [{self.level}]"
                + (f" | {self.note}" if self.note else ""))


@dataclass
class GateVerdict:
    """三套对照组合起来的最终判定。"""
    results: dict[str, BootstrapResult] = field(default_factory=dict)
    passed: bool = False
    level: str = "不显著"
    reasons: list[str] = field(default_factory=list)

    def report(self) -> str:
        lines = ["判据结果:"]
        for r in self.results.values():
            lines.append(r.line())
        lines.append(f"  → 判定:{'通过' if self.passed else '不通过'}({self.level})")
        for why in self.reasons:
            lines.append(f"    · {why}")
        return "\n".join(lines)


# ---------------------------------------------------------------- 核心:bootstrap

def empirical_p(signal_stat: float, random_stats: Sequence[float]) -> float:
    """经验 p 值 = (1 + #{随机 ≥ 信号}) / (B + 1)。Aronson (2006) Ch.6。"""
    arr = np.asarray(random_stats, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size == 0:
        return 1.0
    ge = int(np.sum(arr >= signal_stat))
    return (1.0 + ge) / (arr.size + 1.0)


def effect_z(signal_stat: float, random_stats: Sequence[float]) -> tuple[float, float, float]:
    """效应量 Z = (E_信号 − μ_随机) / σ_随机。返回 (Z, μ_随机, σ_随机)。"""
    arr = np.asarray(random_stats, dtype=float)
    arr = arr[np.isfinite(arr)]
    if arr.size < 2:
        return float("nan"), float("nan"), float("nan")
    mu = float(np.mean(arr))
    sd = float(np.std(arr, ddof=1))
    if sd == 0 or not np.isfinite(sd):
        return float("nan"), mu, sd
    return (signal_stat - mu) / sd, mu, sd


def bootstrap_test(name: str,
                   signal_values: Sequence[float],
                   random_sampler: Callable[[np.random.Generator], Sequence[float]],
                   B: int = B_DEFAULT,
                   seed: int = 20181001,
                   statistic: Callable[[Sequence[float]], float] | None = None,
                   note: str = "") -> BootstrapResult:
    """
    跑一套对照组。
    signal_values  —— 信号实际拿到的一串结果(每笔的收益或 R 倍数)
    random_sampler —— 给一个随机数发生器,吐出「同等数量」的一串随机结果
    statistic      —— 默认取均值(每笔平均收益)
    """
    stat = statistic or (lambda v: float(np.nanmean(v)) if len(v) else float("nan"))
    sig = np.asarray(signal_values, dtype=float)
    sig = sig[np.isfinite(sig)]
    if sig.size == 0:
        return BootstrapResult(name, 0, B, float("nan"), float("nan"), float("nan"),
                               1.0, float("nan"), "信号一笔都没有,无法判定")
    s_stat = stat(sig)
    rng = np.random.default_rng(seed)
    rand_stats: list[float] = []
    for _ in range(B):
        sample = random_sampler(rng)
        if sample is None or len(sample) == 0:
            continue
        rand_stats.append(stat(np.asarray(sample, dtype=float)))
    z, mu, sd = effect_z(s_stat, rand_stats)
    return BootstrapResult(name=name, n_signal=int(sig.size), B=len(rand_stats),
                           signal_mean=s_stat, random_mean=mu, random_std=sd,
                           p_empirical=empirical_p(s_stat, rand_stats),
                           z_effect=z, note=note)


# ---------------------------------------------------------------- 三套对照组

def stratified_sampler(signal_keys: Sequence[tuple],
                       pool_by_date: dict,
                       outcome: Callable[[object, object], float],
                       ) -> Callable[[np.random.Generator], list[float]]:
    """
    ① 条件分层随机:逐笔替换 —— 同一天,从当天该池子里随机换一只票,
      持有同样长的时间。
    signal_keys —— [(date, symbol), ...] 信号实际的进场点
    pool_by_date —— {date: [当天该池子里所有合格的票]}
    outcome(date, symbol) —— 这个进场点的结果(收益 / R 倍数),拿不到返回 nan
    """
    def sampler(rng: np.random.Generator) -> list[float]:
        out: list[float] = []
        for date, _sym in signal_keys:
            pool = pool_by_date.get(date)
            if not pool:
                continue
            pick = pool[int(rng.integers(0, len(pool)))]
            v = outcome(date, pick)
            if v is not None and np.isfinite(v):
                out.append(float(v))
        return out
    return sampler


def circular_block_sampler(series: Sequence[float],
                           n_draw: int,
                           block_length: int | None = None,
                           ) -> Callable[[np.random.Generator], np.ndarray]:
    """
    ② 块重排 Circular Block Bootstrap(Politis & Romano 1994)。
    大白话:不是一个一个地抽,是「一段一段」地抽,抽到尾巴就绕回开头。
    这样随机序列还保留原序列的粘性(自相关),对照才公平。
    块长默认 n^(1/3) 向上取整 —— 标准经验法则,不是调出来的参数。
    """
    arr = np.asarray(series, dtype=float)
    arr = arr[np.isfinite(arr)]
    n = arr.size
    if n == 0:
        return lambda rng: np.array([])
    L = block_length or max(1, int(np.ceil(n ** (1.0 / 3.0))))

    def sampler(rng: np.random.Generator) -> np.ndarray:
        out = np.empty(n_draw, dtype=float)
        filled = 0
        while filled < n_draw:
            start = int(rng.integers(0, n))
            take = min(L, n_draw - filled)
            idx = (start + np.arange(take)) % n
            out[filled:filled + take] = arr[idx]
            filled += take
        return out
    return sampler


def polarity_check(long_result: BootstrapResult,
                   short_result: BootstrapResult) -> tuple[bool, str]:
    """
    ③ 极性反转的判读。
    ★ 多空两边 Z 都 ≥ 1.65 → 这不是方向性信号,是在挑波动大的票。
    返回 (是否通过, 说明)。
    """
    zl, zs = long_result.z_effect, short_result.z_effect
    if np.isfinite(zl) and np.isfinite(zs) and zl >= Z_BASIC and zs >= Z_BASIC:
        return False, (f"极性反转未过:做多 Z={zl:+.2f}、做空 Z={zs:+.2f} 都显著 "
                       f"—— 挑的是「波动大的票」,不是「会涨的票」")
    if np.isfinite(zs) and zs >= zl:
        return False, (f"极性反转未过:做空 Z={zs:+.2f} ≥ 做多 Z={zl:+.2f},"
                       f"方向站不住")
    return True, f"极性反转通过:做多 Z={zl:+.2f} 明显优于做空 Z={zs:+.2f}"


# ---------------------------------------------------------------- 合并判定

def verdict(stratified: BootstrapResult,
            block: BootstrapResult,
            polarity_long: BootstrapResult,
            polarity_short: BootstrapResult,
            min_n: int = MIN_N) -> GateVerdict:
    """三套对照组一起判。任一套没过,整体就不过。"""
    v = GateVerdict(results={
        "条件分层随机": stratified,
        "块重排(Politis&Romano)": block,
        "极性反转·做多": polarity_long,
        "极性反转·做空": polarity_short,
    })
    reasons: list[str] = []
    ok = True

    if stratified.n_signal < min_n:
        ok = False
        reasons.append(f"样本量不足:n={stratified.n_signal} < {min_n}")

    zs = []
    for label, r in (("条件分层随机", stratified), ("块重排", block)):
        if not np.isfinite(r.z_effect):
            ok = False
            reasons.append(f"{label}:Z 算不出来(随机分布退化),判不通过")
            continue
        zs.append(r.z_effect)
        if r.z_effect < Z_BASIC:
            ok = False
            reasons.append(f"{label}:Z={r.z_effect:+.2f} < {Z_BASIC},未达基础显著")
        if r.diff <= 0:
            ok = False
            reasons.append(f"{label}:信号均值不如随机均值(差值 {r.diff:+.4f})")

    pol_ok, pol_msg = polarity_check(polarity_long, polarity_short)
    reasons.append(pol_msg)
    if not pol_ok:
        ok = False

    v.passed = ok
    if ok and zs:
        v.level = "机构级" if min(zs) >= Z_INSTITUTIONAL else "基础显著"
    else:
        v.level = "不显著"
    v.reasons = reasons
    return v


__all__ = [
    "B_DEFAULT", "Z_BASIC", "Z_INSTITUTIONAL", "MIN_N",
    "BootstrapResult", "GateVerdict",
    "empirical_p", "effect_z", "bootstrap_test",
    "stratified_sampler", "circular_block_sampler", "polarity_check", "verdict",
]
