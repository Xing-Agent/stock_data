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

# ============================================================================
# ★★★ 新硬纪律 A(2026-10-29,策略组拍板):随机对照 **5 种子并池**
#
# 大白话(三秒):以前整个随机分布是**一个种子**生出来的。实测那一个种子
#   本身的噪声(每笔 R 的 σ ≈ 0.112)**比我们要测的效应还大** ——
#   ★ 换个种子能把 Z 从 −0.57 翻到 +0.56,正负号都能翻。
#   那就不是尺子,是抽签。
#
# ★ 改法:跑 5 个种子,每个种子 B 次重抽,★ 把 5×B 个随机统计量**并成一池**,
#   再用这一池算 μ / σ / 经验 p。于是种子本身的运气被摊掉。
#
# ★ 为什么必须改(还有第二个理由):★ 基准一(同环境随机进场)**已经**用 5 个
#   种子了。同一份报告里判据用单种子、基准一用 5 种子 —— ★ 两套口径,
#   这正是我们刚刚修过的那个毛病(同一件事两个算法)。现在统一。
#
# ★ 仍然沿用的口径(没变):随机对照必须按【实际成交笔数】校准,不是按信号数;
#   ★ 校准只看笔数、不看成绩(见 analyze.random_entry_benchmark)。
#
# ★ 仍然严禁:取随机分布的最大值(见本文件开头)。并池只改 μ/σ 的估计精度,
#   ★ 不改判定线(Z ≥ 1.65 / 2.00),也不改「不许取 max」这一条。
# ============================================================================
SEEDS_DEFAULT = (20181001, 20181002, 20181003, 20181004, 20181005)
N_SEEDS_DEFAULT = len(SEEDS_DEFAULT)

# ============================================================================
# ★★ 新纪律(2026-10-28):全系统全周期有效交易笔数的统计底线
#
# 原话(外部专家给的,我们认为成立):
#   「在多条件级联模型中,单条件的边际松紧必须以
#     『全系统全周期有效交易笔数 ≥ 150 到 300 笔』为统计底线。
#     失去样本容量的所谓纯正严格度,在实盘中只是一具无法运行的量化标本。」
#
# 大白话:一条链再「忠于原著」,只要跑完没几笔,它就不是一条策略,
#   是一个标本 —— 看着严谨,实盘上根本不动。所以条件串得够不够严,
#   不能只看单条件的道理对不对,要看串完之后还剩不剩得下样本。
#
# ★ 落地:链执行器跑完之后,总笔数 < SYSTEM_MIN_TRADES 时,
#   ★ 报告顶部必须打一行醒目警示(见 analyze.sample_size_banner)。
#
# ★★ 为什么要有这一条:上一批流派二跑出 1 笔。如果当时直接写「流派二无效」,
#   那就是一个**错误结论**进了横向比较表。
#   ★「不成立」和「样本不足」是两件完全不同的事,必须严格分开。
# ============================================================================
SYSTEM_MIN_TRADES = 150        # 底线
SYSTEM_GOOD_TRADES = 300       # 上沿:到这个量级才算样本充裕


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
    # ★★ 2026-10-28 补的一道防线:σ随机 不能只判「等于 0」。
    #   实测踩到过:随机对照退化(1000 次重抽几乎抽出同一个值),
    #   σ 不是正好 0 而是 4e−16 这种浮点噪声,算出来 Z = 3.5e15,
    #   报表上会显示成「机构级」—— ★ 那是个假的显著。
    #   所以改成:σ 必须相对于参与计算的数量级有意义,否则判为「算不出」。
    scale = max(abs(mu), abs(float(signal_stat)), 1.0)
    if not np.isfinite(sd) or sd <= 1e-9 * scale:
        return float("nan"), mu, sd
    return (signal_stat - mu) / sd, mu, sd


def bootstrap_test(name: str,
                   signal_values: Sequence[float],
                   random_sampler: Callable[[np.random.Generator], Sequence[float]],
                   B: int = B_DEFAULT,
                   seed: int | None = None,
                   seeds: Sequence[int] | None = None,
                   statistic: Callable[[Sequence[float]], float] | None = None,
                   note: str = "") -> BootstrapResult:
    """
    跑一套对照组。
    signal_values  —— 信号实际拿到的一串结果(每笔的收益或 R 倍数)
    random_sampler —— 给一个随机数发生器,吐出「同等数量」的一串随机结果
    statistic      —— 默认取均值(每笔平均收益)

    ★★★ 新硬纪律 A(2026-10-29,策略组拍板):★ 随机对照 **5 种子并池**。
      默认跑 SEEDS_DEFAULT 这 5 个种子、每个 B 次,把 5×B 个随机统计量并成一池,
      ★ 用这一池算 μ / σ / 经验 p。
      大白话:以前整个随机分布由一个种子生成,实测那一个种子的噪声比效应本身
      还大(换种子能把 Z 从 −0.57 翻到 +0.56),正负号都能翻 —— 那是抽签不是尺子。

    ★ seeds 可以显式给(比如种子稳定性检查要逐个种子跑);
    ★ seed=<单个整数> 仍然认,但那是**单种子口径**,只应该在
      「专门研究种子敏感性」时用 —— 正式结论一律走默认的 5 种子并池。
    """
    stat = statistic or (lambda v: float(np.nanmean(v)) if len(v) else float("nan"))
    sig = np.asarray(signal_values, dtype=float)
    sig = sig[np.isfinite(sig)]
    if seeds is None:
        seeds = (int(seed),) if seed is not None else SEEDS_DEFAULT
    seeds = tuple(int(s) for s in seeds)
    if sig.size == 0:
        return BootstrapResult(name, 0, B, float("nan"), float("nan"), float("nan"),
                               1.0, float("nan"), "信号一笔都没有,无法判定")
    s_stat = stat(sig)
    rand_stats: list[float] = []
    per_seed: list[float] = []       # ★ 每个种子自己的 μ,用来量化种子噪声
    for sd_i in seeds:
        rng = np.random.default_rng(sd_i)
        this_seed: list[float] = []
        for _ in range(B):
            sample = random_sampler(rng)
            if sample is None or len(sample) == 0:
                continue
            this_seed.append(stat(np.asarray(sample, dtype=float)))
        rand_stats.extend(this_seed)
        if this_seed:
            per_seed.append(float(np.mean(this_seed)))
    z, mu, sd = effect_z(s_stat, rand_stats)
    # ★ 把「种子之间的离散度」记进 note —— 这是新纪律 A 的证据链:
    #   如果 seed_spread 比 |信号均值 − 随机均值| 还大,就说明单种子口径
    #   根本测不出这个效应,★ 必须并池。
    extra = ""
    if len(per_seed) >= 2:
        spread = float(np.std(per_seed, ddof=1))
        extra = (f"5种子并池(B={B}×{len(seeds)}={len(rand_stats)});"
                 f"★种子间μ离散σ={spread:.4f}"
                 f"(信号−随机={s_stat - mu:+.4f})")
        if abs(s_stat - mu) < spread:
            extra += " ★★ 种子噪声 > 效应本身 —— 单种子口径在这条上根本测不出来"
    return BootstrapResult(name=name, n_signal=int(sig.size), B=len(rand_stats),
                           signal_mean=s_stat, random_mean=mu, random_std=sd,
                           p_empirical=empirical_p(s_stat, rand_stats),
                           z_effect=z,
                           note=(note + (";" if note and extra else "") + extra))


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


def volatility_selection_test(signal_values: Sequence[float],
                              control_values: Sequence[float],
                              B: int = B_DEFAULT,
                              seeds: Sequence[int] | None = None
                              ) -> BootstrapResult:
    """
    ★★★ 2026-10-29 新增:真正测「是不是在挑波动大的票」的那一关。

    ================== 为什么要新增这一关 ==================
    ★★ 原来的「③ 极性反转」**测不了它声称要测的东西** ——
      analyze 里把信号和对照**同时取负**(signal=−r,control=−ctrl),
      于是 μ→−μ、σ 不变,★ 数学上 Z_做空 ≡ −Z_做多,**严格镜像**。
      · 所以「做空 Z = +4.47」从来不是一个独立结果,★ 它就是「做多 Z = −4.47」
        的另一种写法,不许当成正面证据。
      · 而且 polarity_check 里那条「多空两边 Z 都 ≥ 1.65 → 挑的是波动大的票」
        的分支 ★★ 永远不可能成立(zs = −zl,两个不可能同时 ≥ 1.65)——
        ★ 那是一段**死代码**,重建说明里列为「三套对照组缺一不可」的第三套,
        实际上一直是空的。

    ★ 正确的测法:方向性信号 vs 波动率选择,区别在**绝对值**上 ——
      · 真方向性:signed R 显著 > 随机,|R| 不特别高
      · 挑波动大的票:★ |R| 显著 > 随机,而 signed R 不显著
      所以这一关测的是 **mean(|R|) 信号 vs 随机**,和 signed 那一关并列看。

    ★ 读法(报告里必须按这个读):
      signed 不显著 + |R| 显著偏高  → ★★ 典型的「挑波动大的票」,不是 alpha
      signed 显著   + |R| 也偏高    → 方向性成立,但吃的是高波动溢价,要看回撤
      signed 显著   + |R| 不偏高    → ★ 最干净的方向性 alpha
      两个都不显著                  → 什么都没挑到
    """
    sig = np.abs(np.asarray(signal_values, dtype=float))
    ctrl = np.abs(np.asarray(control_values, dtype=float))
    sig = sig[np.isfinite(sig)]
    ctrl = ctrl[np.isfinite(ctrl)]
    if sig.size == 0 or ctrl.size == 0:
        return BootstrapResult("波动率选择(|R|)", int(sig.size), 0,
                               float("nan"), float("nan"), float("nan"),
                               1.0, float("nan"), "没有可用样本")
    return bootstrap_test(
        "波动率选择(|R|)", sig,
        circular_block_sampler(ctrl, n_draw=sig.size), B=B, seeds=seeds,
        note="★ 测「是不是在挑波动大的票」:Z 高 = 信号挑到的票振幅系统性大于随机。"
             "★ 这一关取代原来那个严格镜像、因此没有信息量的极性反转")


def polarity_check(long_result: BootstrapResult,
                   short_result: BootstrapResult) -> tuple[bool, str]:
    """
    ③ 极性反转的判读。

    ★★★ 2026-10-29 必须知道的事实:analyze 里信号和对照是**同时取负**的,
      所以 ★ Z_做空 ≡ −Z_做多,**严格镜像、零信息量**。
      · 「做空 Z = +4.47」就是「做多 Z = −4.47」的另一种写法,
        ★ 报告里不许把它当成一个独立的正面结果。
      · 下面那条「两边都 ≥ 1.65」的分支 ★ 永远不可能成立 —— 死代码,保留只为留痕。
      · 所以这一关实际上退化成「Z_做多 > 0 吗」,★ 它并没有在测
        「是不是挑波动大的票」。
      ★ 真正测那件事的是上面新增的 volatility_selection_test(|R| 口径)。
    """
    zl, zs = long_result.z_effect, short_result.z_effect
    # ★ 2026-10-28:Z 算不出来(随机分布退化)时不许说「通过」——
    #   两边都是 nan 还写「做多明显优于做空」是在凭空给结论。
    if not (np.isfinite(zl) and np.isfinite(zs)):
        return False, ("极性反转判不了:做多/做空至少有一边的 Z 算不出来"
                       "(随机分布退化,σ随机 ≈ 0)—— ★ 判不通过,不是通过")
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
    "SYSTEM_MIN_TRADES", "SYSTEM_GOOD_TRADES",
    "BootstrapResult", "GateVerdict",
    "empirical_p", "effect_z", "bootstrap_test",
    "stratified_sampler", "circular_block_sampler", "polarity_check", "verdict",
]
