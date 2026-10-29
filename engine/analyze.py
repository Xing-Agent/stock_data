"""
第三层:后分析层 —— 吃第二层吐出的交易流水,做全部统计。

大白话:第二层只管「跑」,这一层只管「判」。
★ Bootstrap 在交易流水层面重抽(1000 次重抽一份几千行的表),
  ★ 不是重跑 1000 遍模拟 —— 这样才快。

这一层负责输出的东西,一样都不能少:
  绝对表现:总收益、每笔 R、笔数、胜率     ★ 每个指标都带 95% 置信区间
  ★ 坑一:同时报「每笔 R 期望」和「资金占用期间收益率」
  ★ 坑二:跳空穿透止损的笔数和平均穿透幅度
  ★ 坑四:摩擦成本敏感度(0.05% / 0.15% / 0.30% 三档一起报)
  ★ 坑五:笔数显著显示 + 每个指标 95% 置信区间
  两条基准线:同环境随机进场 · ★ 同等仓位大盘(固定 Ē 合成)
  代价:最大回撤 · 最长水下持续天数 · 最长连续不赚钱笔数 · 几乎全亏的年份
  执行负荷:年化换手率 · 年均交易笔数 · 平均持仓周期
  扣除摩擦后的净收益,与毛收益同等显示
  分步归因五行,★ 每行同时报收益和最大回撤
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from . import chain, data, matrices, stats_gate

TRADING_DAYS_PER_YEAR = 252
CI_B = 1000          # 置信区间的重抽次数,和判据的 B 保持一致


# ============================================ ★ 随机对照触发率:全系统唯一口径

RANDOM_RATE_DEF = ("★ 统一口径:随机对照的触发率 = 「每个某天×某票单元掷一次骰子」的概率,"
                   "起点用 笔数/(交易日数 × 池内票数)(无量纲),"
                   "再按实际成交笔数校准到与真链一致(±8% 以内,最多 4 轮);"
                   "★ 校准只看笔数、不看成绩")


def random_control_rate(n_trades: int, n_days: int, n_syms: int) -> float:
    """
    ★★ 2026-10-29 统一口径:三处随机对照(基准一 / 判据 / 四格硬关)
       以前各用一个公式,其中判据那个写成 `笔数 / 天数 / 100` ——
       量纲不对(它把「池内票数」硬编成 100,实际池子 300 只),
       实测触发率高约 3 倍,随机对照因此比真链「做得多」,
       μ_随机 被系统性拉偏 → Z 不可信。

    大白话:引擎里的 `entry.type=random` 是对每一个「某天×某票」的格子
    掷一次骰子。所以频率对齐真信号,分母必须是**格子总数**
    = 交易日数 × 池内票数,不是天数、更不是天数 ÷ 100。

    这个函数是全系统唯一入口,★ 不许任何地方再自己写一遍公式。
    """
    cells = max(1, int(n_days)) * max(1, int(n_syms))
    return min(1.0, max(1e-7, float(n_trades) / cells))


def calibrated_random_rate(cfg: "chain.ChainConfig", symbols: list[str] | None,
                           start: str, end: str, target_trades: int,
                           initial_equity: float, seed: int = 424242,
                           max_iter: int = 4, tol: float = 0.08) -> dict[str, Any]:
    """
    ★★ 2026-10-29:随机对照触发率的**最终口径** —— 对齐「实际成交笔数」。

    为什么闭式公式不够(这是本轮才量出来的事):
      `rate = 笔数 / (天数 × 票数)` 量纲是对的,但它对齐的是「掷骰子掷出多少
      个信号」,而不是「最后成交了多少笔」。这条链有 3297 个合格进场信号,
      只成交 435 笔 —— 槽位和环境把 87% 的信号挡掉了。所以照闭式公式掷骰子,
      随机对照只成交 143 笔(真链 435 笔),★ 对照组反而「做得太少」。
      而旧的错公式(÷100)碰巧高 3 倍,成交 432 笔 —— ★ 它是错的公式蒙对了
      一次,换个池子只数或换个 slots 就不成立。

    大白话:要比「挑得准」,就得让随机对照跟真链**出手次数一样多**。
    所以做法是:先用闭式公式当起点,跑一遍看成交多少笔,按比例缩放再跑,
    最多 4 轮,取成交笔数最接近真链的那一轮。

    ★ 这不是网格搜索(纪律 6):校准的目标是**笔数**,不是成绩。
      校准过程完全不看收益、不看 Z,看了就是作弊。
    """
    n_days = max(1, len(pd.bdate_range(start, end)))
    n_syms = max(1, len(matrices.universe_mask(
        cfg.get("universe") or {}, symbols).columns))
    rate = random_control_rate(target_trades, n_days, n_syms)
    tries: list[dict[str, Any]] = []
    best: dict[str, Any] | None = None
    for it in range(max_iter):
        c2 = cfg.copy_with(entry={"type": "random",
                                  "params": {"rate": rate, "seed": seed},
                                  "source": "随机对照:同环境随机进场,频率对齐真链实际成交笔数"})
        try:
            led = chain.run_chain(c2, symbols, start, end, initial_equity).ledger
        except Exception:
            led = None
        n_ctrl = 0 if led is None else len(led)
        tries.append({"轮": it + 1, "rate": rate, "对照成交笔数": n_ctrl})
        gap = abs(n_ctrl - target_trades) / max(1, target_trades)
        if best is None or gap < best["gap"]:
            best = {"rate": rate, "n_ctrl": n_ctrl, "ledger": led, "gap": gap,
                    "iters": it + 1}
        if gap <= tol or n_ctrl == 0:
            break
        rate = min(1.0, max(1e-7, rate * target_trades / max(1, n_ctrl)))
    assert best is not None
    best["tries"] = tries
    best["闭式起点"] = random_control_rate(target_trades, n_days, n_syms)
    return best


#: ★★ 新硬纪律 A（2026-10-29 策略组拍板）：随机对照用 5 个种子并池。
#   原因（实测出来的）：单种子噪声（每笔 R σ=0.112）比效应本身还大，
#   能把 Z 从 −0.57 翻到 +0.56 —— 单种子的 Z 符号本身就是噪声。
#   ★ 5 个种子必须是写死的常量，不许随机生成 —— 否则结论不可复现。
CONTROL_SEEDS: tuple[int, ...] = (424242, 20181001, 20220101, 777013, 31337,
                                  90210, 10007, 31415926, 27182818, 65537)
#   ★★ 2026-10-29 第二次调整：5 个种子 → **10 个**。
#   理由是实测出来的：技-1 上单种子对照每笔 R 在 +0.002 .. +1.042 之间，
#   极差 1.040R、标准差 0.434R，而策略本身效应只有 0.016R
#   —— ★ 噪声比效应大 27 倍（5 种子时估的）。
#   ★ 但加种子不是重点：重点是下面那个**强制打印单种子极差**，
#   它让「噪声比效应大」这件事无法被藏住。


def pooled_random_control(cfg: "chain.ChainConfig", symbols: list[str] | None,
                          start: str, end: str, target_trades: int,
                          initial_equity: float,
                          seeds: tuple[int, ...] = CONTROL_SEEDS
                          ) -> dict[str, Any]:
    """
    ★★ 硬纪律 A：随机对照 5 种子并池。

    做法：每个种子各走一遍「按实际成交笔数校准」的流程（沿用已定口径），
    然后把 5 条对照流水**纵向拼起来**当一个对照池。

    ★ 为什么是并池而不是「跑 5 遍取平均 Z」：
      并池是把对照分布估得更准（5 倍样本），然后只算一个 Z；
      取平均 Z 是把 5 个各自带噪声的 Z 平均，它不减小对照分布的估计误差。
    ★ 校准仍然只看笔数、不看成绩（纪律 6）—— 每个种子各自校准到真链笔数，
      谁的成绩好看根本不进入选择。
    """
    per: list[dict[str, Any]] = []
    frames: list[pd.DataFrame] = []
    for sd in seeds:
        cal = calibrated_random_rate(cfg, symbols, start, end, target_trades,
                                     initial_equity, seed=sd)
        led = cal.get("ledger")
        n_ctrl = 0 if led is None or led.empty else len(led)
        rbar = (float(led["r_multiple"].dropna().mean())
                if n_ctrl else float("nan"))
        per.append({"种子": sd, "rate": cal["rate"],
                    "对照成交笔数": n_ctrl,
                    "该种子对照每笔R": rbar,
                    "校准轮次": cal["tries"]})
        if n_ctrl:
            frames.append(led)
    pool = pd.concat(frames, ignore_index=True) if frames else None
    # ★★ 2026-10-29：**强制打印单种子极差**（策略组要求，比加种子更重要）。
    #   大白话：随机对照自己换个随机种子，算出来的「每笔 R」就能差很多。
    #   如果这个差别比策略本身的效应还大，那 Z 的符号就是噪声。
    #   ★ 所以这两行无条件打到 stdout，不许只往 JSON 里埋 ——
    #     埋在 JSON 里没人看，打在屏幕上跑的人当场就能发现。
    _single = [d["该种子对照每笔R"] for d in per
               if np.isfinite(d["该种子对照每笔R"])]
    if len(_single) > 1:
        _rng = float(max(_single) - min(_single))
        _sd = float(np.std(_single, ddof=1))
        print(f"  ★随机对照单种子噪声（{len(_single)} 个种子）："
              f"每笔R 极差={_rng:+.4f} 标准差={_sd:.4f} "
              f"范围=[{min(_single):+.4f} .. {max(_single):+.4f}]")
        print(f"    ★ 读法：把这个极差和策略自己的效应量级比 —— "
              f"极差远大于效应时，Z 的符号本身就是噪声。")
    rs = (pool["r_multiple"].dropna().to_numpy(dtype=float)
          if pool is not None and not pool.empty else np.array([]))
    single = [d["该种子对照每笔R"] for d in per
              if np.isfinite(d["该种子对照每笔R"])]
    return {
        "ledger": pool,
        "种子": list(seeds),
        "逐种子": per,
        "并池总笔数": int(rs.size),
        "并池对照每笔R": float(np.mean(rs)) if rs.size else float("nan"),
        "★单种子每笔R的极差": (float(max(single) - min(single))
                                        if len(single) > 1 else float("nan")),
        "★单种子每笔R的标准差": (float(np.std(single, ddof=1))
                                          if len(single) > 1 else float("nan")),
        "口径": ("硬纪律 A：5 种子并池；每个种子各自按实际成交笔数校准，"
                 "校准只看笔数、不看成绩"),
    }


# ================================================================ 置信区间

def ci95(values, stat=np.mean, B: int = CI_B, seed: int = 20181001
         ) -> tuple[float, float, float, int]:
    """
    ★ 坑五:4000 笔和 45 笔不能放同一张排行榜。
    任何指标都带 95% 置信区间 —— 笔数少的,区间自然宽得没法下结论。
    做法:对交易流水做有放回重抽(Efron & Tibshirani 1993),取 2.5% / 97.5% 分位。
    返回 (点估计, 下界, 上界, n)。
    """
    v = np.asarray(values, dtype=float)
    v = v[np.isfinite(v)]
    n = v.size
    if n == 0:
        return float("nan"), float("nan"), float("nan"), 0
    point = float(stat(v))
    if n < 2:
        return point, float("nan"), float("nan"), n
    rng = np.random.default_rng(seed)
    draws = np.empty(B, dtype=float)
    for b in range(B):
        draws[b] = stat(v[rng.integers(0, n, n)])
    lo, hi = np.nanpercentile(draws, [2.5, 97.5])
    return point, float(lo), float(hi), n


def _fmt_ci(t: tuple[float, float, float, int], pct: bool = False) -> str:
    p, lo, hi, n = t
    f = (lambda x: f"{x:+.2%}") if pct else (lambda x: f"{x:+.3f}")
    if not np.isfinite(lo):
        return f"{f(p)} (n={n},样本太少给不出区间)"
    return f"{f(p)} [95%CI {f(lo)} .. {f(hi)}] (n={n})"


# ================================================================ 代价与收益

def drawdown(eq: pd.Series) -> tuple[float, int, Any]:
    """最大回撤、最长水下持续天数(Peter Martin 1989 Ulcer Index 体系)。"""
    peak = eq.cummax()
    dd = eq / peak - 1.0
    under = (eq < peak * (1 - 1e-12)).to_numpy()
    longest = cur = 0
    for u in under:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    return (float(dd.min()) if len(dd) else float("nan"), longest,
            dd.idxmin() if len(dd) else None)


def ulcer_index(eq: pd.Series) -> float:
    """Ulcer Index(Peter Martin 1989):水下深度的均方根。比最大回撤更能反映煎熬。"""
    dd = (eq / eq.cummax() - 1.0) * 100.0
    return float(np.sqrt(np.mean(np.square(dd)))) if len(dd) else float("nan")


def cagr(eq: pd.Series) -> float:
    if len(eq) < 2 or eq.iloc[0] <= 0 or eq.iloc[-1] <= 0:
        return float("nan")
    return float((eq.iloc[-1] / eq.iloc[0]) ** (TRADING_DAYS_PER_YEAR / len(eq)) - 1.0)


def longest_losing_streak(ledger: pd.DataFrame) -> int:
    if ledger.empty:
        return 0
    s = ledger.sort_values("exit_date")["net_pnl"].to_numpy(dtype=float)
    longest = cur = 0
    for v in s:
        cur = 0 if (np.isfinite(v) and v > 0) else cur + 1
        longest = max(longest, cur)
    return longest


def yearly_returns(eq: pd.Series) -> dict[str, float]:
    return {str(y): float(g.iloc[-1] / g.iloc[0] - 1.0)
            for y, g in eq.groupby(eq.index.year) if len(g) >= 2}


# ================================================================ 坑一:资金占用收益率

def invested_capital_return(ledger: pd.DataFrame, eq: pd.Series) -> dict[str, Any]:
    """
    ★ 坑一(现金拖累不对称):
    突破策略震荡年空仓半年,均值回归天天满仓。直接比年化收益会冤枉前者。
    所以除了「每笔 R 期望」,再报一个「资金占用期间收益率」:
    只看钱真正在场的那段时间赚了多少。

    算法:∑净盈亏 / (∑仓位名义金额×持仓天数 / 252) —— 即每「资金·年」的回报率。
    """
    if ledger.empty:
        return {"资金占用期间收益率_年化": float("nan"),
                "资金在场比例": float("nan"), "说明": "没有成交"}
    cap_years = float(ledger["capital_days"].sum()) / TRADING_DAYS_PER_YEAR
    pnl = float(ledger["net_pnl"].sum())
    return {
        "资金占用期间收益率_年化": pnl / cap_years if cap_years > 0 else float("nan"),
        "资金在场比例": float(ledger["capital_days"].sum()
                              / (eq.mean() * len(eq))) if len(eq) else float("nan"),
        "说明": "分母是「资金·年」:仓位名义金额 × 持仓天数 / 252。"
                "空仓的日子不进分母,所以不会冤枉低频策略。",
    }


# ================================================================ 坑二:跳空统计

def gap_stats(ledger: pd.DataFrame) -> dict[str, Any]:
    """★ 坑二:止损被跳空穿透的笔数和平均穿透幅度(以 R 为单位)。"""
    if ledger.empty:
        return {"说明": "没有成交"}
    stops = ledger[ledger["reason"] == "止损"]
    gap = stops[stops["gap_through"]]
    pen = gap["gap_penetration_r"].astype(float)
    return {
        "止损出场笔数": int(len(stops)),
        "★跳空穿透止损笔数": int(len(gap)),
        "跳空穿透占止损的比例": float(len(gap) / len(stops)) if len(stops) else float("nan"),
        "平均穿透幅度(R)": float(pen.mean()) if len(pen) else 0.0,
        "最深穿透(R)": float(pen.max()) if len(pen) else 0.0,
        "穿透笔的平均实际R": float(gap["r_multiple"].mean()) if len(gap) else float("nan"),
        "未穿透笔的平均实际R": float(
            stops[~stops["gap_through"]]["r_multiple"].mean()) if len(stops) else float("nan"),
        "说明": "成交价已按 min(止损价, 当日开盘价) 处理 —— 跳空时按开盘价,"
                "不许按止损价(那会系统性低估基本面困境类的亏损)。",
    }


# ================================================================ 基准二:同等仓位大盘

def exposure_matched_benchmark(res: chain.ChainResult,
                               component_match: str,
                               risk_free_annual: float | None) -> dict[str, Any]:
    """
    ★★ 基准二「同等仓位大盘」。

    大白话:一条只有三成时间在场的策略,不该拿它跟「全程满仓的标普」比。
    公平的比法是造一个「同样只有三成仓位、其余放现金」的大盘组合。

    做法:Ē = 这条链全周期的时间加权平均净敞口(★ 固定值)
         基准 = Ē × 成分匹配指数 + (1 − Ē) × 无风险利率

    ★★ Ē 必须用全周期固定值,不许按日动态跟踪实际敞口 ——
       按日跟踪等于把「什么时候该空仓」这个本事白送给基准,
       结果 alpha 会恒等于零,基准就废了。

    出处:Treynor & Mazuy (1966);Merton (1981);Jensen (1968)。
    成分匹配:大盘股→SPY · 中盘→MDY · 等权→RSP · 单行业→该行业 ETF。
    |Ē| ≤ 0.10 → 判为市场中性,基准直接用无风险利率。
    """
    e_bar = float(res.exposure.mean())
    notes: list[str] = []
    rf = risk_free_annual
    if rf is None:
        rf = 0.0
        notes.append("★ 仓库里没有无风险利率序列(只有 TLT,那是长债 ETF、不是短端利率)。"
                     "现金腿按 0% 记并在此标明 —— 不拿近似值顶上(硬纪律第 7 条)。"
                     "要做准必须另外补一条 3 个月期美债收益率序列。")
    rf_d = (1.0 + rf) ** (1 / TRADING_DAYS_PER_YEAR) - 1.0

    if abs(e_bar) <= 0.10:
        notes.append(f"|Ē|={abs(e_bar):.3f} ≤ 0.10 → 判为市场中性,基准直接用无风险利率")
        bench_ret = pd.Series(rf_d, index=res.equity.index)
        idx_sym = "(无,市场中性)"
    else:
        idx_sym = data.resolve_component_index(component_match)
        b = data.load_benchmark(idx_sym)["close"].reindex(res.equity.index).ffill()
        bench_ret = e_bar * b.pct_change().fillna(0.0) + (1.0 - e_bar) * rf_d

    beq = (1.0 + bench_ret).cumprod() * float(res.equity.iloc[0])
    mdd, under, _ = drawdown(beq)
    chain_ret = float(res.equity.iloc[-1] / res.equity.iloc[0] - 1.0)
    bench_total = float(beq.iloc[-1] / beq.iloc[0] - 1.0)
    return {
        "★Ē_全周期固定净敞口": e_bar,
        "成分匹配指数": idx_sym,
        "无风险利率_年化": rf,
        "基准总收益": bench_total,
        "基准CAGR": cagr(beq),
        "基准最大回撤": mdd,
        "基准最长水下天数": under,
        "★超额收益(链 − 同等仓位大盘)": chain_ret - bench_total,
        "警示": notes,
    }


# ================================================================ 基准一:同环境随机进场

def random_entry_benchmark(cfg: chain.ChainConfig, res: chain.ChainResult,
                           symbols: list[str] | None,
                           start: str, end: str, n_seeds: int = 5) -> dict[str, Any]:
    """
    ★ 基准一:同环境随机进场 —— 其余六步完全一样,只把第③步换成随机。
    随机的触发频率对齐真信号的实际频率,这样比的是「挑得准不准」,
    不是「做得多不多」。
    """
    n_tr = len(res.ledger)
    # ★ 2026-10-29:三处随机对照统一用 calibrated_random_rate(对齐实际成交笔数)
    cal = calibrated_random_rate(cfg, symbols, start, end, n_tr,
                                 res.initial_equity, seed=20181001)
    rate = cal["rate"]
    rets, mdds, rbar = [], [], []
    for k in range(n_seeds):
        c2 = cfg.copy_with(entry={"type": "random",
                                  "params": {"rate": rate, "seed": 20181001 + 977 * k},
                                  "source": "基准一:同环境随机进场,频率对齐真信号"})
        r2 = chain.run_chain(c2, symbols, start, end, res.initial_equity)
        rets.append(float(r2.equity.iloc[-1] / r2.equity.iloc[0] - 1.0))
        mdds.append(drawdown(r2.equity)[0])
        if not r2.ledger.empty:
            rbar.append(float(r2.ledger["r_multiple"].mean()))
    chain_ret = float(res.equity.iloc[-1] / res.equity.iloc[0] - 1.0)
    chain_r = float(res.ledger["r_multiple"].mean()) if not res.ledger.empty else float("nan")
    return {
        "随机进场_平均总收益": float(np.mean(rets)),
        "随机进场_收益标准差": float(np.std(rets, ddof=1)) if len(rets) > 1 else float("nan"),
        "随机进场_平均每笔R": float(np.nanmean(rbar)) if rbar else float("nan"),
        "随机进场_平均最大回撤": float(np.mean(mdds)),
        "随机进场_种子数": n_seeds,
        "随机进场_触发率": rate,
        "随机进场_触发率口径": RANDOM_RATE_DEF,
        "随机进场_闭式起点": cal["闭式起点"],
        "随机进场_校准轮次": cal["tries"],
        "随机进场_校准后对照笔数": cal["n_ctrl"],
        "随机进场_真链笔数": n_tr,
        "★真信号总收益 − 随机进场": chain_ret - float(np.mean(rets)),
        "★真信号每笔R − 随机进场每笔R": (chain_r - float(np.nanmean(rbar))
                                        if rbar else float("nan")),
    }


# ================================================================ 判据(流水层面重抽)

def bootstrap_on_ledger(res: chain.ChainResult,
                        pool_ledger: pd.DataFrame | None = None,
                        B: int = stats_gate.B_DEFAULT) -> stats_gate.GateVerdict:
    """
    ★ 判据在交易流水层面做,不重跑 1000 遍模拟。
    三套对照组:
      ① 条件分层随机:对照组来自「同环境随机进场」那条链的流水(同一天、同一个池子)
      ② 块重排:对真信号的 R 序列做 Circular Block Bootstrap(Politis & Romano 1994)
      ③ 极性反转:同样的进场点强制做空 —— 多空都正就是在挑波动大的票
    """
    r = res.ledger["r_multiple"].dropna().to_numpy(dtype=float) if not res.ledger.empty \
        else np.array([])
    if r.size == 0:
        empty = stats_gate.BootstrapResult("无成交", 0, B, np.nan, np.nan, np.nan,
                                           1.0, np.nan, "这条链一笔都没成交")
        return stats_gate.verdict(empty, empty, empty, empty)

    ctrl = (pool_ledger["r_multiple"].dropna().to_numpy(dtype=float)
            if pool_ledger is not None and not pool_ledger.empty else r)

    strat = stats_gate.bootstrap_test(
        "条件分层随机", r,
        lambda rng: rng.choice(ctrl, size=r.size, replace=True), B=B,
        note="对照来自同环境随机进场的流水")
    block = stats_gate.bootstrap_test(
        "块重排(Politis&Romano)", r,
        stats_gate.circular_block_sampler(ctrl, n_draw=r.size), B=B,
        note="块长 n^(1/3),保留序列自相关")
    pol_l = stats_gate.bootstrap_test(
        "极性反转·做多", r,
        stats_gate.circular_block_sampler(ctrl, n_draw=r.size), B=B)
    pol_s = stats_gate.bootstrap_test(
        "极性反转·做空", -r,
        stats_gate.circular_block_sampler(-ctrl, n_draw=r.size), B=B,
        note="同样进场点强制做空;★★ 严格镜像:Z ≡ −Z_做多,零信息量,"
             "不许当独立证据")
    v = stats_gate.verdict(strat, block, pol_l, pol_s)
    # ★★★ 2026-10-29 新增第四套:真正测「是不是在挑波动大的票」。
    #   ★ 原来的极性反转是严格镜像(信号和对照同时取负)→ 测不了这件事。
    #   ★ 这一关只**附加报告**,不改 verdict 的通过/不通过逻辑 ——
    #     改判定线是策略层的决定,不是我这一轮该擅自动的。
    v.results["波动率选择(|R|)"] = stats_gate.volatility_selection_test(
        r, ctrl, B=B)
    return v


# ================================================================ 分步归因

ATTRIBUTION_STEPS = ("买入持有", "+环境", "+选股", "+出场", "完整链")


def attribution(cfg: chain.ChainConfig, symbols: list[str] | None,
                start: str, end: str, initial_equity: float) -> pd.DataFrame:
    """
    五行分步归因。★ 每一行必须同时报收益和代价(最大回撤),不许只报收益那一半。

    一行一行往上加,看价值到底是哪一步贡献的:
      买入持有 —— 全池等权买了就不动
      +环境   —— 加大盘闸门,关闸就空仓
      +选股   —— 再加选股范围(市值 / 流动性 / 基本面)
      +出场   —— 再加止损和离场规则
      完整链 —— 最后才加真正的进场扳机和仓位规则
    (实测下来扳机只占价值的 5%,选股+环境占 70%,出场+风控占 25%,
     这张表就是用来复核这个分配的。)
    """
    flat_regime = {"rules": [], "flatten_when_off": False}
    no_stop = {"type": "pct", "params": {"pct": 0.999},
               "source": "归因中间行:等价于不设止损"}
    eq_all = {"type": "equal_weight_all",
              "params": {"max_weight": 1.0, "max_positions": 10_000},
              "source": "归因中间行:等权买入持有"}
    always = {"type": "always", "source": "归因中间行:天天都算信号"}
    open_uni = {k: v for k, v in (cfg.get("universe") or {}).items()
                if k in ("size_groups", "sectors")}

    variants = {
        "买入持有": cfg.copy_with(universe=open_uni, regime=flat_regime, entry=always,
                                  initial_stop=no_stop, trailing_stop={"type": "none"},
                                  exit={"type": "signal_only", "params": {}},
                                  sizing=eq_all),
        "+环境": cfg.copy_with(universe=open_uni, entry=always, initial_stop=no_stop,
                               trailing_stop={"type": "none"},
                               exit={"type": "signal_only", "params": {}}, sizing=eq_all),
        "+选股": cfg.copy_with(entry=always, initial_stop=no_stop,
                               trailing_stop={"type": "none"},
                               exit={"type": "signal_only", "params": {}}, sizing=eq_all),
        "+出场": cfg.copy_with(entry=always, sizing=eq_all),
        "完整链": cfg,
    }
    rows = []
    for label in ATTRIBUTION_STEPS:
        r = chain.run_chain(variants[label], symbols, start, end, initial_equity)
        mdd, under, _ = drawdown(r.equity)
        rows.append({
            "步": label,
            "净收益(扣摩擦)": float(r.equity.iloc[-1] / r.equity.iloc[0] - 1.0),
            "毛收益": float(r.equity_gross.iloc[-1] / r.equity_gross.iloc[0] - 1.0),
            "CAGR": cagr(r.equity),
            "★最大回撤": mdd,
            "最长水下天数": under,
            "笔数": len(r.ledger),
            "平均净敞口Ē": float(r.exposure.mean()),
        })
    return pd.DataFrame(rows).set_index("步")


# ================================================================ 坑四:摩擦敏感度

def friction_sensitivity(cfg: chain.ChainConfig, symbols: list[str] | None,
                         start: str, end: str, initial_equity: float,
                         m: matrices.Matrices | None = None) -> pd.DataFrame:
    """
    ★★ 坑四:统一扣固定摩擦会系统性美化高频、惩罚低频。
    所以成本做成配置项,并把三档一刀切成本下的结果一起报出来 ——
    ★ 不许自己挑一个好看的。默认那一行是「按 ADV20 分三档」的分层成本。
    """
    rows = []
    r0 = chain.run_chain(cfg, symbols, start, end, initial_equity, m=m)
    mdd, _, _ = drawdown(r0.equity)
    costs_cfg = cfg.get("costs") or {}
    if "friction_tiers" in costs_cfg:
        default_label = "★配置默认:按ADV20分三档"
    elif costs_cfg.get("one_way_bps") is not None:
        default_label = (f"★配置默认:一刀切 "
                         f"{float(costs_cfg['one_way_bps'])/100:.2f}%"
                         f"(⚠ 没分档,见坑四)")
    else:
        default_label = "★配置默认:按ADV20分三档(内置值)"
    rows.append({"摩擦口径": default_label,
                 "净收益": float(r0.equity.iloc[-1] / r0.equity.iloc[0] - 1.0),
                 "最大回撤": mdd, "笔数": len(r0.ledger),
                 "平均每笔R_扣摩擦": float(r0.ledger["r_multiple_net"].mean())
                 if not r0.ledger.empty else float("nan")})
    # ★ 配置写死了一刀切成本时,★ 仍然把「按 ADV20 分三档」那一行补上 ——
    #   坑四的结论是一刀切会系统性美化高频、惩罚低频,
    #   所以分档那一行必须在场,不能因为配置没写就看不到。
    if "friction_tiers" not in costs_cfg:
        c2 = cfg.copy_with(costs={**costs_cfg,
                                  "friction_tiers": chain.FRICTION_TIERS_DEFAULT,
                                  "source": "坑四:按 ADV20 分三档(引擎内置 5/15/30bp,"
                                            "无原著出处,见引擎说明第十节第 3 条)"})
        c2.raw["costs"].pop("one_way_bps", None)
        rt = chain.run_chain(c2, symbols, start, end, initial_equity, m=m)
        mddt, _, _ = drawdown(rt.equity)
        rows.append({"摩擦口径": "★按ADV20分三档(5/15/30bp)",
                     "净收益": float(rt.equity.iloc[-1] / rt.equity.iloc[0] - 1.0),
                     "最大回撤": mddt, "笔数": len(rt.ledger),
                     "平均每笔R_扣摩擦": float(rt.ledger["r_multiple_net"].mean())
                     if not rt.ledger.empty else float("nan")})

    for bps in chain.FRICTION_SENSITIVITY_FLAT:
        r = chain.run_chain(cfg, symbols, start, end, initial_equity, m=m,
                            flat_friction_bps=bps)
        mdd, _, _ = drawdown(r.equity)
        rows.append({"摩擦口径": f"一刀切 {bps/100:.2f}%",
                     "净收益": float(r.equity.iloc[-1] / r.equity.iloc[0] - 1.0),
                     "最大回撤": mdd, "笔数": len(r.ledger),
                     "平均每笔R_扣摩擦": float(r.ledger["r_multiple_net"].mean())
                     if not r.ledger.empty else float("nan")})
    return pd.DataFrame(rows).set_index("摩擦口径")


# ================================================================ 总装

def evaluate(cfg: chain.ChainConfig,
             res: chain.ChainResult | None = None,
             symbols: list[str] | None = None,
             start: str = data.PERF_START,
             end: str = data.PERF_END,
             initial_equity: float = 1_000_000.0,
             n_random_seeds: int = 5,
             with_attribution: bool = True,
             with_sensitivity: bool = True,
             with_gate: bool = True) -> dict[str, Any]:
    """跑完一条链的全部评估。res 给了就复用,不重跑。"""
    if res is None:
        res = chain.run_chain(cfg, symbols, start, end, initial_equity)
    eq, eqg, led = res.equity, res.equity_gross, res.ledger
    mdd, under, trough = drawdown(eq)
    years = max(1e-9, len(eq) / TRADING_DAYS_PER_YEAR)
    yr = yearly_returns(eq)
    bm = cfg.get("benchmark") or {}

    r_t = ci95(led["r_multiple"]) if not led.empty else (np.nan, np.nan, np.nan, 0)
    rn_t = ci95(led["r_multiple_net"]) if not led.empty else (np.nan, np.nan, np.nan, 0)
    g_t = ci95(led["gross_return"]) if not led.empty else (np.nan, np.nan, np.nan, 0)
    w_t = ci95((led["net_pnl"] > 0).astype(float)) if not led.empty \
        else (np.nan, np.nan, np.nan, 0)

    out: dict[str, Any] = {
        "链名": cfg.name,
        "绩效窗口": f"{eq.index[0].date()} .. {eq.index[-1].date()}"
                     f"(2016 起热机,{data.PERF_START} 才计入绩效 —— Fama 1998)",
        "★笔数": len(led),

        "绝对表现": {
            "净收益(扣摩擦)": float(eq.iloc[-1] / eq.iloc[0] - 1.0),
            "毛收益": float(eqg.iloc[-1] / eqg.iloc[0] - 1.0),
            "CAGR(净)": cagr(eq),
            "★笔数": len(led),
            "每笔R_毛(带95%CI)": _fmt_ci(r_t),
            "★每笔R_扣摩擦(带95%CI)": _fmt_ci(rn_t),
            "每笔毛收益(带95%CI)": _fmt_ci(g_t, pct=True),
            "胜率(带95%CI)": _fmt_ci(w_t, pct=True),
        },

        "坑一_现金拖累": invested_capital_return(led, eq),
        "坑二_跳空穿透止损": gap_stats(led),

        "代价": {
            "最大回撤": mdd,
            "回撤最深那天": str(trough.date()) if trough is not None else None,
            "★最长水下持续天数": under,
            "UlcerIndex(Martin 1989)": ulcer_index(eq),
            "最长连续不赚钱笔数": longest_losing_streak(led),
            "逐年收益": yr,
            "几乎全亏的年份(<-10%)": {k: v for k, v in yr.items() if v < -0.10},
        },

        "执行负荷": {
            "年化换手率": float(
                (led["notional_in"].sum() + led["notional_out"].sum())
                / 2 / eq.mean() / years) if not led.empty else 0.0,
            "年均交易笔数": float(len(led) / years),
            "平均持仓周期(交易日)": float(led["holding_days"].mean())
            if not led.empty else float("nan"),
        },

        "摩擦成本": {
            "口径": "★按 ADV20 分三档(高/中/低流动性),不一刀切",
            "分档(单边)": {
                k: f"{v/100:.3f}%" for k, v in
                ((cfg.get("costs") or {}).get("friction_tiers")
                 or ({"一刀切": (cfg.get("costs") or {})["one_way_bps"]}
                     if (cfg.get("costs") or {}).get("one_way_bps") is not None
                     else chain.FRICTION_TIERS_DEFAULT)).items()},
            "实际摩擦总额": float(led["friction_cost"].sum()) if not led.empty else 0.0,
            "毛收益 − 净收益": float(eqg.iloc[-1] / eqg.iloc[0] - eq.iloc[-1] / eq.iloc[0]),
            "出处": "SEC Rule 206(4)-1(d);GIPS 2020 Section 2.A",
        },

        "基准一_同环境随机进场": random_entry_benchmark(
            cfg, res, symbols, start, end, n_random_seeds),
        "基准二_同等仓位大盘": exposure_matched_benchmark(
            res, bm.get("component_match", "large"), bm.get("risk_free_annual")),
    }

    if with_gate:
        # ★ 2026-10-29:这里原来写的是 `len(led) / len(eq) / 100` —— 量纲不对
        #   (把池内票数硬编成 100),实测触发率高约 3 倍。
        #   现在和基准一 / 四格硬关共用同一个口径:校准到实际成交笔数一致。
        # ★★ 硬纪律 A（2026-10-29）：改成 5 种子并池，不再用单种子。
        #   沙包里的原注：这里曾经写过 `len(led)/len(eq)/100`（量纲不对），
        #   后来改成单种子按成交笔数校准；★ 现在是 5 种子并池。
        pooled = pooled_random_control(cfg, symbols, start, end, len(led),
                                       initial_equity)
        out["判据_随机对照口径"] = pooled["口径"]
        out["判据_随机对照_5种子并池"] = {
            k: v for k, v in pooled.items() if k != "ledger"}
        out["判据_随机对照笔数"] = pooled["并池总笔数"]
        ctrl = pooled["ledger"]
        out["判据"] = bootstrap_on_ledger(res, ctrl)

    if with_attribution:
        out["分步归因"] = attribution(cfg, symbols, start, end, initial_equity)
    if with_sensitivity:
        out["坑四_摩擦敏感度"] = friction_sensitivity(
            cfg, symbols, start, end, initial_equity)

    out["_result"] = res
    return out


def sample_size_banner(n: int) -> str | None:
    """
    ★★ 样本容量底线警示(2026-10-28 新纪律,见 stats_gate.SYSTEM_MIN_TRADES)。

    总笔数 < 150 时返回一行醒目警示,要打在报告**最顶上**;够了就返回 None。

    ★ 这一行存在的意义:把「这一派不成立」和「这一派没测成」分开。
      上一批流派二跑出 1 笔 —— 当时如果直接写「流派二无效」,
      就是把一个错误结论送进了横向比较表。
    """
    if n >= stats_gate.SYSTEM_MIN_TRADES:
        return None
    return (f"★★ 样本不足(N={n} 笔 < {stats_gate.SYSTEM_MIN_TRADES}):"
            f"本次结果不具统计意义,"
            f"问题在条件串联过严,不是这一派无效")


def format_report(out: dict[str, Any]) -> str:
    n = int(out["★笔数"])
    lines: list[str] = []
    banner = sample_size_banner(n)
    if banner:
        # ★ 打在最顶上,而且用分隔线围起来 —— 不许被淹在表格里
        lines += ["=" * 78, banner, "=" * 78]
    lines += [f"链:{out['链名']}", f"窗口:{out['绩效窗口']}",
              f"★笔数:{n}  "
              f"({'笔数太少,任何结论都要打问号' if n < stats_gate.MIN_N else '笔数够'};"
              f"★ 系统底线 {stats_gate.SYSTEM_MIN_TRADES},"
              f"样本充裕线 {stats_gate.SYSTEM_GOOD_TRADES})",
              ""]
    for sec in ("绝对表现", "坑一_现金拖累", "坑二_跳空穿透止损", "代价",
                "执行负荷", "摩擦成本", "基准一_同环境随机进场", "基准二_同等仓位大盘"):
        if sec not in out:
            continue
        lines.append(f"[{sec}]")
        for k, v in out[sec].items():
            if isinstance(v, float):
                lines.append(f"  {k}: {v:+.4f}")
            elif isinstance(v, dict):
                lines.append(f"  {k}: " + ", ".join(
                    f"{a}={b:+.2%}" if isinstance(b, float) else f"{a}={b}"
                    for a, b in v.items()))
            elif isinstance(v, list):
                for it in v:
                    lines.append(f"  ⚠ {it}")
            else:
                lines.append(f"  {k}: {v}")
        lines.append("")
    if "判据" in out:
        lines.append(out["判据"].report())
        lines.append("")
    if "分步归因" in out:
        lines.append("[分步归因 —— ★ 收益和代价必须一起看]")
        df = out["分步归因"].copy()
        for c in ("净收益(扣摩擦)", "毛收益", "CAGR", "★最大回撤", "平均净敞口Ē"):
            df[c] = df[c].map(lambda x: f"{x:+.2%}")
        lines.append(df.to_string())
        lines.append("")
    if "坑四_摩擦敏感度" in out:
        lines.append("[坑四 摩擦敏感度 —— ★ 三档一起报,不挑好看的]")
        df = out["坑四_摩擦敏感度"].copy()
        for c in ("净收益", "最大回撤"):
            df[c] = df[c].map(lambda x: f"{x:+.2%}")
        df["平均每笔R_扣摩擦"] = df["平均每笔R_扣摩擦"].map(lambda x: f"{x:+.3f}")
        lines.append(df.to_string())
    return "\n".join(lines)


__all__ = ["ci95", "drawdown", "ulcer_index", "cagr", "longest_losing_streak",
           "yearly_returns", "invested_capital_return", "gap_stats",
           "exposure_matched_benchmark", "random_entry_benchmark",
           "bootstrap_on_ledger", "attribution", "friction_sensitivity",
           "evaluate", "format_report"]
