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
    n_days = max(1, len(res.equity))
    n_syms = max(1, len(matrices.universe_mask(cfg.get("universe") or {}, symbols).columns))
    rate = min(1.0, max(1e-7, n_tr / (n_days * n_syms)))
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
        note="同样进场点强制做空")
    return stats_gate.verdict(strat, block, pol_l, pol_s)


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
        c2 = cfg.copy_with(entry={"type": "random",
                                  "params": {"rate": max(1e-7, len(led) /
                                                          max(1, len(eq)) / 100),
                                             "seed": 424242},
                                  "source": "判据对照组:同环境随机进场"})
        try:
            ctrl = chain.run_chain(c2, symbols, start, end, initial_equity).ledger
        except Exception:
            ctrl = None
        out["判据"] = bootstrap_on_ledger(res, ctrl)

    if with_attribution:
        out["分步归因"] = attribution(cfg, symbols, start, end, initial_equity)
    if with_sensitivity:
        out["坑四_摩擦敏感度"] = friction_sensitivity(
            cfg, symbols, start, end, initial_equity)

    out["_result"] = res
    return out


def format_report(out: dict[str, Any]) -> str:
    lines = [f"链:{out['链名']}", f"窗口:{out['绩效窗口']}",
             f"★笔数:{out['★笔数']}  "
             f"({'笔数太少,任何结论都要打问号' if out['★笔数'] < stats_gate.MIN_N else '笔数够'})",
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
