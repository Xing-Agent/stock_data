"""
三条新基准线(基准三 / 四 / 五)—— 2026-10-29 策略组拍板,外部专家口径。

三秒版:旧的「同等仓位大盘」基准用全周期固定平均持仓比例 Ē 造出来,
        于是「策略那个月正好空仓、大盘那个月在跌」时,基准被假定照样挨了跌,
        策略凭空捡到一笔超额。这笔超额是闸门(择时)给的,不是选股本事。
        这个文件把那一笔单独拆出来叫「择时贡献」,并新造两条基准线
        (槽位机会成本 / 朴素基准)来回答「这条策略值不值得占一个槽」。

★ 本文件只**新增**,不改 analyze.py / chain.py / matrices.py 里任何现有函数。
  新基准线需要自定义进场矩阵时,走 chain.run_chain(..., m=...) 这个现成的入口,
  自己造 Matrices 再覆盖 entry / rank_score —— 所以共享文件一行都没动。

────────────────────────────────────────────────────────────────────────
术语(大白话)
  静态基准(= 旧的基准二):Ē × 指数 + (1−Ē) × 无风险。Ē 是全周期固定值。
  动态开关基准(基准三):闸门开着的日子记指数收益,关着的日子记无风险利率。
  择时贡献 = 动态开关基准收益 − 静态基准收益。
             它就是「闸门帮策略躲掉的那一段跌」,★ 绝不许算进选股能力。
  选股贡献 = 策略收益 − 动态开关基准收益。
  恒等式:静态基准超额 ≡ 选股贡献 + 择时贡献。
  槽位机会成本线(基准四):这个槽位不跑本策略,默认全额买 QQQ(站上 50 日线)
             / 全额现金(跌破 50 日线)。回答「值不值得占一个槽」。
  朴素基准(基准五):两条谁都写得出来的无脑规则。信息比率打不过它 → 枪毙。
────────────────────────────────────────────────────────────────────────

硬纪律落点:
  · 预热自 2014-01-02,2018-01-02 起计绩效(沿用 data.PERF_START)。
  · 静态基准的 Ē 仍是全周期固定值(旧纪律保留);它现在的作用是「第二层」,
    专门用来算择时贡献。
  · 仓库里没有短端无风险利率序列(只有 TLT,那是长债 ETF)→ 现金腿按 0% 记
    并在每个输出里标明。★ 不拿近似值顶上。
  · 仓库里没有 QQQ 日线 → 基准四用替代品,★ 每一处都标「替代品,不是 QQQ」,
    并把「需要 QQQ 日线」列进要技术提供的清单。
  · σ 近乎为零 → 信息比率 / 卡玛比率报「算不出」,不输出天文数字。
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from . import analyze, cache, chain, data, matrices

TRADING_DAYS_PER_YEAR = 252

#: σ 低于这个值就认为「算不出」,不报天文数字(硬纪律第 4 条的同一口径)
SIGMA_FLOOR = 1e-12

UNCOMPUTABLE = "算不出"

#: ★ 仓库里没有 QQQ 日线。基准四原文要求 QQQ,这里只能用替代品。
#   ★ 每一个替代品都必须自带「这不是 QQQ」的标签 —— 不许假装是 QQQ。
QQQ_MISSING_NOTE = (
    "★★ 仓库里没有 QQQ 日线(ETF 基准数据还在等技术提供)。"
    "基准四原文要求 QQQ,这里跑的是**替代品**,不是 QQQ ——"
    "结论里凡出现基准四的数字,都要带这句话。"
    "★ 「需要 QQQ 日线」已列入要技术提供的清单。")

#: ★★ 为什么替代品甲是 SPY 而不是 IVW(标普 500 成长,风格上更接近 QQQ):
#   ★ IVW 的原始 close 在 2020-10-19 有一根 −75.4% 的日线,那是**未调整的拆股**
#     (4 拆 1),而仓库里 IVW 的 adjusted_close 整列是空的 —— 没法还原。
#   ★ 拿一条带着 −75% 假跌的序列去造基准,会把基准做成一条暴跌线、
#     让所有策略凭空「跑赢基准」。所以 IVW 直接弃用,不拿它顶上。
#   ★ 任务书已允许「用现有的成分匹配指数」当替代品 → 用 SPY,并标明不是 QQQ。
SLOT_PROXY_ETF = "SPY"
SLOT_PROXY_ETF_NOTE = (
    f"替代品甲 = {SLOT_PROXY_ETF}(标普 500,现有的成分匹配指数)。"
    "★ 不是 QQQ:QQQ 是纳斯达克 100,成长/科技权重高得多,"
    "用 SPY 会系统性低估「不跑这条策略就去拿 QQQ」的机会成本。"
    "★ 风格上更接近 QQQ 的 IVW(标普 500 成长)仓库里**不可用** ——"
    "它的原始 close 在 2020-10-19 有一根 −75.4% 的未调整拆股跳空,"
    "而 adjusted_close 整列为空,无法还原。")

#: ★ 顺手量出来的、不属于本轮任务但必须上报的数据问题。
ETF_SPLIT_FINDINGS = [
    "★★ IVW 原始 close 在 2020-10-19 有 −75.4% 的未调整拆股跳空,"
    "adjusted_close 整列为空 → IVW 目前不可用于任何基准构造。",
    "★★ 五只行业 ETF(XLK / XLB / XLE / XLU / XLY)的原始 close 在 2025-12-05 "
    "同时出现 −49.6% ~ −50.5% 的跳空 —— 这是 Select Sector SPDR 系列的 2 拆 1,"
    "仓库里没调整。★ 影响面:② 环境过滤的 sector_diffusion_above(板块扩散指数 SDI)"
    "直接拿原始 close 比 50 日均线,这五只会在 2025-12-05 之后约 50 个交易日里"
    "被误判为「跌破 50 日线」→ SDI 被系统性压低 → 闸门偏紧。"
    "★ 受影响的链:cashflow_discipline / vcp_momentum(用了 SDI)。"
    "★ 影响窗口只在 2025-12-05 .. 2025-12-31(绩效窗口最后 18 个交易日),"
    "所以不至于翻转结论,但这是个真 bug,要修。",
    "★ VIX 2025-04-09 的 −35.8% 是真实行情(关税暂缓后波动率崩塌),不是拆股。",
]

#: 替代品乙:纯池内构造 —— 当日 ADV20 最大的 N 只等权。
SLOT_PROXY_TOPN = 30
SLOT_PROXY_TOPN_NOTE = (
    f"替代品乙 = 池内 ADV20 最大的 {SLOT_PROXY_TOPN} 只等权日度再平衡。"
    "★ 不是 QQQ:它是用我们这 300 只池子自己造的「大票等权」组合,"
    "既不是纳斯达克 100 的成分、也不是市值加权。"
    "★ 用成交额当大小的代理,是因为仓库里的 PIT 市值不可靠"
    "(见 README:WeightedAverageDilutedShares 不是时点股数)。")


# ================================================================ 小工具

def rf_leg(rf_annual: float | None) -> tuple[float, float, list[str]]:
    """
    无风险利率腿。返回 (日化收益, 年化, 警示)。

    大白话:仓库里根本没有短端利率序列,所以现金腿只能按 0% 记,
    并且每次都要把这件事说出来 —— 不拿 TLT(长债 ETF)之类的近似值顶上。
    """
    notes: list[str] = []
    rf = rf_annual
    if rf is None:
        rf = 0.0
        notes.append(
            "★ 仓库里没有无风险利率序列(只有 TLT,那是长债 ETF、不是短端利率)。"
            "现金腿按 0% 记并在此标明 —— 不拿近似值顶上。"
            "★ 要做准必须另外补一条 3 个月期美债收益率序列。")
    return (1.0 + rf) ** (1 / TRADING_DAYS_PER_YEAR) - 1.0, float(rf), notes


def curve(daily_ret: pd.Series, start_equity: float) -> pd.Series:
    """日收益序列 → 净值曲线。第一天不计收益(和链的净值口径一致)。"""
    r = daily_ret.copy()
    r.iloc[0] = 0.0
    return (1.0 + r).cumprod() * float(start_equity)


def total_return(eq: pd.Series) -> float:
    return float(eq.iloc[-1] / eq.iloc[0] - 1.0)


def calmar(eq: pd.Series) -> float | str:
    """
    卡玛比率 = 年化收益 / |最大回撤|(Young 1991)。
    ★ 回撤近乎为零时报「算不出」,不输出天文数字(硬纪律第 4 条同一口径)。
    """
    c = analyze.cagr(eq)
    mdd = analyze.drawdown(eq)[0]
    if not np.isfinite(c) or not np.isfinite(mdd) or abs(mdd) < 1e-9:
        return UNCOMPUTABLE
    return float(c / abs(mdd))


def information_ratio(r_chain: pd.Series, r_bench: pd.Series) -> float | str:
    """
    信息比率 = 年化(超额日收益均值 / 超额日收益标准差)。
    (Grinold & Kahn 1999;Goodwin 1998 的 IR 定义)
    ★ 超额序列 σ 近乎为零 → 报「算不出」。
    """
    d = (r_chain - r_bench).dropna()
    if d.size < 2:
        return UNCOMPUTABLE
    sd = float(d.std(ddof=1))
    if not np.isfinite(sd) or sd < SIGMA_FLOOR:
        return UNCOMPUTABLE
    return float(d.mean() / sd * np.sqrt(TRADING_DAYS_PER_YEAR))


def curve_stats(eq: pd.Series, r_chain: pd.Series | None = None,
                chain_total: float | None = None) -> dict[str, Any]:
    """一条基准曲线该报的东西:总收益 / CAGR / 最大回撤 / 卡玛 / 超额 / 信息比率。"""
    mdd, under, _ = analyze.drawdown(eq)
    out: dict[str, Any] = {
        "基准总收益": total_return(eq),
        "基准CAGR": analyze.cagr(eq),
        "基准最大回撤": mdd,
        "基准最长水下天数": under,
        "基准卡玛比率": calmar(eq),
    }
    if chain_total is not None:
        out["★超额收益(链 − 基准)"] = chain_total - out["基准总收益"]
    if r_chain is not None:
        out["★信息比率(链 vs 基准)"] = information_ratio(
            r_chain, eq.pct_change().fillna(0.0))
    return out


# ================================================================ 闸门序列

def gate_series(m: matrices.Matrices, index: pd.DatetimeIndex) -> pd.Series:
    """
    ② 环境过滤那一步的闸门状态,对齐到绩效窗口。

    大白话:闸门就是「今天整个开不开仓」那一个开关。它的条件每条链都不一样,
    全部从 YAML 的 regime 那一块读 —— 这个函数不自己定任何条件,
    只是把第一层已经算好的 regime 向量切到绩效窗口上。

    ★ matrices.regime_mask 已经 shift(1) 过(t 行的值用 t−1 收盘算),
      所以这里不再 shift,否则等于偷看/延迟两次。
    """
    g = pd.Series(m.regime, index=m.index, dtype=bool)
    return g.reindex(index).fillna(False).astype(bool)


# ================================================================ 基准二(静态,复刻)

def static_benchmark(res: chain.ChainResult, component_match: str,
                     rf_annual: float | None) -> dict[str, Any]:
    """
    ★ 旧的「基准二 同等仓位大盘」—— 这里**完全复刻** analyze.exposure_matched_benchmark
      的算法,只是额外把日收益序列吐出来(算择时贡献和信息比率要用)。

    ★ Ē 仍是全周期固定值(旧纪律保留)。它现在的角色是「第二层」:
      静态基准和动态开关基准的差额,就是择时贡献。
    """
    e_bar = float(res.exposure.mean())
    rf_d, rf, notes = rf_leg(rf_annual)
    idx = res.equity.index
    if abs(e_bar) <= 0.10:
        notes.append(f"|Ē|={abs(e_bar):.3f} ≤ 0.10 → 判为市场中性,基准直接用无风险利率")
        bench_ret = pd.Series(rf_d, index=idx)
        idx_sym = "(无,市场中性)"
        idx_ret = pd.Series(0.0, index=idx)
    else:
        idx_sym = data.resolve_component_index(component_match)
        b = data.load_benchmark(idx_sym)["close"].reindex(idx).ffill()
        idx_ret = b.pct_change().fillna(0.0)
        bench_ret = e_bar * idx_ret + (1.0 - e_bar) * rf_d
    eq = curve(bench_ret, res.equity.iloc[0])
    r_chain = res.equity.pct_change().fillna(0.0)
    out = {
        "口径": "静态基准(旧基准二):Ē × 成分匹配指数 + (1−Ē) × 无风险利率,"
                "★ Ē 用全周期固定值",
        "★Ē_全周期固定净敞口": e_bar,
        "成分匹配指数": idx_sym,
        "无风险利率_年化": rf,
        **curve_stats(eq, r_chain, total_return(res.equity)),
        "警示": notes,
    }
    out["_daily"] = bench_ret
    out["_index_daily"] = idx_ret
    out["_rf_daily"] = rf_d
    out["_e_bar"] = e_bar
    out["_market_neutral"] = abs(e_bar) <= 0.10
    out["_index_symbol"] = idx_sym
    return out


# ================================================================ 基准三:动态开关基准

def gated_dynamic_benchmark(res: chain.ChainResult, gate: pd.Series,
                            static: dict[str, Any],
                            exposure_matched: bool) -> dict[str, Any]:
    """
    ★★ 基准三「动态开关基准」(Gated Dynamic Benchmark)—— 本轮最重要的一条。

        闸门关着的日子:  Benchmark_t = 无风险利率(日化)
        闸门开着的日子:  Benchmark_t = 成分匹配指数当日收益

    大白话:旧基准假定「策略平均三成仓位,那就全程三成仓位挨涨挨跌」。
    可策略真正空仓的那几个月,大盘正好在崩 —— 旧基准替策略挨了那一跌,
    策略白捡一笔超额。这条基准改成「策略开闸我才持指数,关闸我也去拿无风险」,
    于是闸门躲跌这件事两边都有,剩下的差额才是**纯选股能力**。

    两个口径都算,因为它们回答的不是同一个问题:

      原文口径(exposure_matched=False):开闸那天记**满仓指数**。
        这是专家原话。它量的是「允许开仓的日子里,你选的票比全额指数强多少」。
        ★ 它和静态基准的敞口不一样(Ē vs 1.0),所以它和静态基准的差额
          里混了敞口差,不能直接当择时贡献用。

      同敞口口径(exposure_matched=True):开闸那天记 Ē × 指数 + (1−Ē) × 无风险。
        ★ 这个口径和静态基准只差「关闸那几天怎么记」这一件事,
          所以它和静态基准的差额**就是纯粹的择时贡献**,
          而且闸门从不关的链(buy_and_hold)差额恒等于 0 ——
          ★ 这正是 sanity check 能认出代码坏没坏的那个检查点。

    ★ 择时贡献一律用同敞口口径算(加法恒等式才成立),
      纯选股能力的判定一律报两个口径,不许只报好看的那个。
    """
    idx = res.equity.index
    rf_d = static["_rf_daily"]
    idx_ret = static["_index_daily"]
    e_bar = static["_e_bar"]
    g = gate.reindex(idx).fillna(False).astype(bool)

    if static["_market_neutral"]:
        # |Ē| ≤ 0.10 已判为市场中性,静态基准本来就是纯无风险 → 两条重合
        open_leg = pd.Series(rf_d, index=idx)
    elif exposure_matched:
        open_leg = e_bar * idx_ret + (1.0 - e_bar) * rf_d
    else:
        open_leg = idx_ret.copy()

    bench_ret = pd.Series(np.where(g.to_numpy(), open_leg.to_numpy(), rf_d),
                          index=idx)
    eq = curve(bench_ret, res.equity.iloc[0])
    r_chain = res.equity.pct_change().fillna(0.0)
    label = ("同敞口口径(开闸记 Ē×指数+(1−Ē)×无风险)" if exposure_matched
             else "原文口径(开闸记满仓指数)")
    out = {
        "口径": f"动态开关基准 · {label};关闸记无风险利率",
        "闸门来源": "该链 YAML 里 ② 环境过滤那一步(七步链的第二步),逐条从配置读",
        "开闸天数": int(g.sum()),
        "关闸天数": int((~g).sum()),
        "关闸占比": float((~g).mean()),
        **curve_stats(eq, r_chain, total_return(res.equity)),
    }
    if static["_market_neutral"]:
        out["警示"] = ["|Ē| ≤ 0.10 已判市场中性 → 动态开关基准与静态基准重合,"
                       "择时贡献恒为 0(不是 bug,是市场中性那条规则的后果)"]
    out["_daily"] = bench_ret
    return out


# ================================================================ 基准四:槽位机会成本线

def _topn_adv_equal_weight(symbols: list[str], index: pd.DatetimeIndex,
                           n: int = SLOT_PROXY_TOPN) -> pd.Series:
    """
    替代品乙:池内 ADV20 最大的 n 只等权,日度再平衡,返回日收益序列。
    ★ 权重用 t−1 的 ADV20 排名决定(不偷看当天)。
    """
    close = cache.field("close", symbols)
    adv = matrices.adv_matrix(20, symbols)
    ret = close.pct_change()
    rank = adv.shift(1).rank(axis=1, ascending=False)
    pick = rank <= n
    w = pick.astype(float)
    w = w.div(w.sum(axis=1).replace(0.0, np.nan), axis=0)
    port = (w * ret).sum(axis=1, min_count=1)
    return port.reindex(index).fillna(0.0)


def slot_replacement_benchmark(res: chain.ChainResult,
                               proxy_daily: pd.Series,
                               proxy_level: pd.Series,
                               rf_annual: float | None,
                               ma: int = 50,
                               proxy_note: str = "") -> dict[str, Any]:
    """
    ★ 基准四「槽位机会成本线」(Slot Replacement Benchmark)。

        该槽位如果不跑本策略,默认全额投入:
          站上 50 日均线 → 持有 QQQ(★ 仓库没有 QQQ,这里是替代品)
          跌破 50 日均线 → 持有现金 / 短债(无风险利率)

    大白话:这条线回答的不是「跑得比大盘好不好」,而是
    「这条策略值不值得占一个仓位槽」—— 占了槽就等于不去跑这条无脑的
    『涨了拿着、跌破走开』,所以它是机会成本。

    ★ 比较指标用卡玛比率(年化收益/最大回撤)和信息比率,★ 不只看总收益。
    ★ 均线信号 shift(1):t 日的仓位用 t−1 收盘算的均线,不偷看当天。
    """
    idx = res.equity.index
    rf_d, rf, notes = rf_leg(rf_annual)
    if proxy_note:
        notes.insert(0, proxy_note)
    notes.insert(0, QQQ_MISSING_NOTE)

    lvl = proxy_level.reindex(
        proxy_level.index.union(idx)).ffill()
    above = (lvl > lvl.rolling(ma, min_periods=ma).mean()).shift(1)
    above = above.reindex(idx).fillna(False).astype(bool)
    pr = proxy_daily.reindex(idx).fillna(0.0)
    bench_ret = pd.Series(np.where(above.to_numpy(), pr.to_numpy(), rf_d),
                          index=idx)
    eq = curve(bench_ret, res.equity.iloc[0])
    r_chain = res.equity.pct_change().fillna(0.0)
    eq_chain = res.equity
    out = {
        "口径": f"槽位机会成本线:站上 {ma} 日均线 → 全额持替代品;跌破 → 无风险利率。"
                "★ 原文要求 QQQ,仓库没有 → 用替代品,不是 QQQ",
        "在场天数": int(above.sum()),
        "离场天数": int((~above).sum()),
        "无风险利率_年化": rf,
        **curve_stats(eq, r_chain, total_return(eq_chain)),
        "★链卡玛比率": calmar(eq_chain),
        "★值不值得占一个槽": _slot_verdict(eq_chain, eq, r_chain, bench_ret),
        "警示": notes,
    }
    out["_daily"] = bench_ret
    return out


def _slot_verdict(eq_chain: pd.Series, eq_bench: pd.Series,
                  r_chain: pd.Series, r_bench: pd.Series) -> str:
    """★ 判定只看卡玛比率和信息比率,不看总收益(硬纪律第 6 条:总收益是混沌量)。"""
    ck, cb = calmar(eq_chain), calmar(eq_bench)
    ir = information_ratio(r_chain, r_bench)
    if isinstance(ck, str) or isinstance(cb, str) or isinstance(ir, str):
        return (f"算不出(链卡玛={ck} 基准卡玛={cb} 信息比率={ir})—— "
                f"σ 或回撤近乎为零,不给结论")
    if ck > cb and ir > 0:
        return f"值得(链卡玛 {ck:+.3f} > 替代品 {cb:+.3f},信息比率 {ir:+.3f} > 0)"
    if ck <= cb and ir <= 0:
        return f"不值得(链卡玛 {ck:+.3f} ≤ 替代品 {cb:+.3f},信息比率 {ir:+.3f} ≤ 0)"
    return (f"两个指标打架(链卡玛 {ck:+.3f} vs 替代品 {cb:+.3f};"
            f"信息比率 {ir:+.3f})—— 不下结论")


# ================================================================ 基准五:朴素基准

NAIVE_MEANREV = "朴素-均值回归版"
NAIVE_RSI2 = "朴素-RSI版"

NAIVE_DEFS = {
    NAIVE_MEANREV: "全池每日收盘,做多过去 5 天跌幅最深的那 5% 的股票,持有 3 天出场",
    NAIVE_RSI2: "全池每日收盘,做多 RSI(2) < 5 的前 3 只,持有 2 天或 5 日线平仓(先到先算)",
}


#: ★ 槽位数大于这个值就不算「真的槽位约束」了(equal_weight_all 那种链
#   在配置里写 slots: 1000 只是个占位数,引擎的 equal_all 分支根本不看它)。
SLOTS_REAL_MAX = 100

#: ★ 占位槽位数。用 10 不是挑出来的:config_adapter 对「slots 没写」的链
#   本来就默认 10,这里沿用同一个默认值,不另立一个数。
SLOTS_PLACEHOLDER = 10


def _naive_slots(slots: int, equal_all: bool) -> tuple[int, str]:
    """
    朴素基准该用几个槽。

    ★ 原则:槽位约束照抄被比的那条链(任务书明写「这两条也要受同样的槽位约束」)。
    ★ 例外(实测逼出来的):被比的链用 equal_weight_all 时,配置里的 slots
      只是个占位数(buy_and_hold 写的是 1000),引擎根本不看它。
      - 照抄 1000 → 每槽 0.1% 本金,朴素基准被压成空壳(实测总收益 +15%、
        回撤 1.7%、卡玛虚高到 3.6),对照组废掉。
      - 跟着改成 equal_weight_all → 每天把**全部现金**压到 3~15 只票上,
        八年复利出 +7918% / +65629% 这种数字(实测),那是杠杆幻觉不是基准。
      ★ 所以这种链一律退回占位槽位 10(= config_adapter 对「slots 没写」
        的默认值,不是我们另挑的数),并在输出里标明。
    """
    if equal_all or int(slots) > SLOTS_REAL_MAX:
        return (SLOTS_PLACEHOLDER,
                f"★ 被比的链没有真的槽位约束"
                f"(sizing={'equal_weight_all' if equal_all else f'slots={slots}'})"
                f" → 朴素基准退回占位槽位 {SLOTS_PLACEHOLDER}"
                f"(= 引擎对「slots 没写」的默认值,不是我们另挑的数)")
    return int(slots), ""


def _naive_sizing(slots: int) -> dict:
    """朴素基准的仓位:固定比例等额占槽,每槽 1/slots。"""
    return {"type": "fixed_fraction",
            "params": {"max_positions": int(slots),
                       "max_weight": 1.0 / max(1, int(slots))},
            "source": "朴素基准:等额占槽,★ 槽位数照抄被比的那条链"}


def _naive_costs(costs: dict) -> tuple[dict, str]:
    """
    朴素基准的摩擦成本:照抄被比的那条链。

    ★ 例外:被比的链写的是 one_way_bps: 0(buy_and_hold 那种「对数用的基线链」
      就是 0),★ 照抄 0 会把一条日频换手的朴素线美化成永动机 ——
      坑四的结论正是「一刀切成本会系统性美化高频」,0 成本是它的极端情形。
      这种情况改用引擎内置的「按 ADV20 分三档」,并在输出里标明。
    """
    c = dict(costs or {})
    if c.get("one_way_bps") is not None and float(c["one_way_bps"]) <= 0.0:
        c.pop("one_way_bps", None)
        c["friction_tiers"] = dict(chain.FRICTION_TIERS_DEFAULT)
        c["source"] = ("★ 被比的链写的是 0 摩擦(对数用的基线链)—— 朴素基准是"
                       "日频换手,照抄 0 成本会把它美化成永动机(坑四的极端情形),"
                       "所以改用引擎内置的按 ADV20 分三档")
        return c, c["source"]
    return c, ""


def _naive_raw(kind: str, slots: int, costs: dict,
               equal_all: bool = False) -> dict:
    """
    朴素基准的七步配置。★ 进场矩阵由本文件直接覆盖(见 naive_baseline),
    所以这里 entry 写 never —— 不是「悄悄忽略」,是显式占位。

    ★ 槽位约束和成本扣减都照抄被比的那条链(否则不公平对比)。
    """
    base: dict[str, Any] = {
        "meta": {"name": f"基准五_{kind}_slots{slots}",
                 "purpose": "基准五 朴素基准;专家原话:复杂算法打不过无脑基准就枪毙"},
        "universe": {},                      # ★ 全池,不做任何筛选
        "regime": {"rules": [], "flatten_when_off": False},   # ★ 无闸门
        "entry": {"type": "never",
                  "source": "朴素基准:进场矩阵由 bench_lines 按原文定义直接覆盖"},
        "initial_stop": {"type": "pct", "params": {"pct": 0.999},
                         "source": "朴素基准定义:原文没给止损 → 等价于不设止损,"
                                   "★ 不自己编一个止损参数"},
        "trailing_stop": {"type": "none"},
        "sizing": _naive_sizing(slots),
        "costs": dict(costs or {}),
    }
    if kind == NAIVE_MEANREV:
        base["exit"] = {"type": "signal_only",
                        "params": {"time_stop_days": 3},
                        "source": "朴素基准定义:持有 3 天出场"}
    elif kind == NAIVE_RSI2:
        base["exit"] = {"type": "rules",
                        "rules": [{"type": "close_above_ma", "params": {"ma": 5},
                                   "source": "朴素基准定义:5 日线平仓"}],
                        "params": {"time_stop_days": 2},
                        "source": "朴素基准定义:持有 2 天或 5 日线平仓(先到先算)"}
    else:
        raise ValueError(f"朴素基准只有两版:{NAIVE_MEANREV} / {NAIVE_RSI2};给的是 {kind!r}")
    return base


#: 朴素基准的持仓天数(原文给的):均值回归版 3 天,RSI 版最多 2 天。
NAIVE_HOLD_DAYS = {NAIVE_MEANREV: 3, NAIVE_RSI2: 2}


def residual_jump_blackout(symbols: list[str], index: pd.DatetimeIndex,
                           hold_days: int) -> tuple[pd.DataFrame, list]:
    """
    ★★ 把「已知的假跳变 bar」周围的进场信号屏蔽掉。

    大白话:仓库这 300 只票里,还剩 30 根没修的拆股跳变(比如 BNED 2024-06-12
    一天 ×74、PROP 2020-02-28 一天 ×28.6)。这不是我发现的新问题 ——
    engine/split_gate.py 自己的 residual_jumps() 就是专门列这份「我们还欠多少」
    的清单,自检每次都打出来。

    ★ 为什么偏偏是朴素-均值回归基准会被它炸穿:这条基准的定义就是
    「买过去 5 天跌得最深的那 5%」—— 而即将做反向拆股(1 合 N)的仙股,
    拆股前恰恰就是跌得最深的那一批。于是基准系统性地专门去捡这些
    「第二天价格 ×74」的假 bar。实测:不剔除 → 八年 +47493%;剔除 → 见报告。
    ★ 所以这个数不剔除就没有任何参考价值,必须两版都报。

    ★ 剔除口径不是新参数:阈值用的就是 split_gate.residual_jumps() 的默认
      3 倍(引擎自己定的那条线),窗口用的是这条基准自己的持仓天数 + 2 天
      (信号日 → 次日开盘成交 → 持满 N 天 → 次日开盘平,一共跨 N+2 根)。
    ★ 这是「剔除已知坏数据」,不是择时:它只拦进场,不改任何价格。
    """
    from . import split_gate
    jumps = split_gate.residual_jumps(3.0)
    block = pd.DataFrame(False, index=index, columns=symbols)
    w = int(hold_days) + 2
    for sym, d, _ratio in jumps:
        if sym not in block.columns:
            continue
        ts = pd.Timestamp(d)
        if ts not in index:
            # 跳变日不在交易日历里(理论上不会)→ 用最近的位置
            pos = index.searchsorted(ts)
        else:
            pos = int(index.get_loc(ts))
        lo, hi = max(0, pos - w), min(len(index) - 1, pos + w)
        block.iloc[lo:hi + 1, block.columns.get_loc(sym)] = True
    return block, jumps


def _naive_entry_and_rank(kind: str, symbols: list[str]
                          ) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    朴素基准的进场矩阵和排序分数。

    ★ 这两条是「状态」不是「事件」—— 原文写的是「每日收盘筛一遍」,
      所以不走 _event_only(那会把第二天还在榜上的票吃掉)。
    ★ 当天收盘算、次日开盘成交,由第二层统一负责,这里不 shift。
    """
    close = cache.field("close", symbols)
    if kind == NAIVE_MEANREV:
        ret5 = close / close.shift(5) - 1.0
        # 池内横截面升序百分位:0.05 就是「跌幅最深的 5%」
        pct = ret5.rank(axis=1, pct=True, ascending=True)
        entry = (pct <= 0.05) & ret5.notna()
        score = -ret5                       # 跌得越深排越前
    else:
        rsi = matrices.rsi_matrix(2, symbols)
        qual = (rsi < 5.0) & rsi.notna()
        # 「前 3 只」= 合格票里 RSI(2) 最低的 3 只
        masked = rsi.where(qual)
        rank = masked.rank(axis=1, ascending=True, method="first")
        entry = qual & (rank <= 3)
        score = -masked.fillna(np.inf)      # RSI 越低排越前
    return entry.fillna(False), score


def naive_baseline(kind: str, symbols: list[str], slots: int, costs: dict,
                   res_ref: chain.ChainResult,
                   start: str = data.PERF_START, end: str = data.PERF_END,
                   m_cache: dict | None = None,
                   equal_all: bool = False,
                   drop_fake_jumps: bool = True) -> dict[str, Any]:
    """
    ★ 基准五「朴素基准」。专家原话逻辑:任何复杂算法写出来的策略,
      若不能在信息比率上击败「无脑基准」,直接枪毙。

    ★ 两条朴素线照样受同样的槽位约束和成本扣减(否则不公平对比)——
      slots 和 costs 都从被比的那条链抄过来。
    """
    slots_eff, slots_note = _naive_slots(slots, equal_all)
    costs_eff, costs_note = _naive_costs(costs)
    raw = _naive_raw(kind, slots_eff, costs_eff)
    cfg = chain.ChainConfig(raw)            # ★ 已是执行器原生形状,不过适配层
    key = (kind, bool(drop_fake_jumps))
    m = (m_cache or {}).get(key)
    jump_note = ""
    if m is None:
        m = matrices.build(raw, symbols)
        entry, score = _naive_entry_and_rank(kind, list(m.symbols))
        if drop_fake_jumps:
            block, jumps = residual_jump_blackout(
                list(m.symbols), entry.index, NAIVE_HOLD_DAYS[kind])
            n_before = int(entry.to_numpy(dtype=bool).sum())
            entry = entry & ~block
            n_after = int(entry.to_numpy(dtype=bool).sum())
            jump_note = (
                f"★ 已剔除「已知假跳变 bar」附近的进场信号:"
                f"split_gate.residual_jumps(3.0) 列出 {len(jumps)} 根残余跳变,"
                f"屏蔽后进场信号格子 {n_before} → {n_after}"
                f"(砍掉 {n_before - n_after} 格,{(n_before-n_after)/max(1,n_before):.2%})。"
                f"★ 不剔除的话这条基准专门去捡 BNED ×74 / PROP ×28.6 这种假 bar。")
        m.entry = entry.reindex(index=m.index, columns=m.symbols).to_numpy(dtype=bool)
        m.rank_score = score.reindex(index=m.index,
                                     columns=m.symbols).to_numpy(dtype=float)
        m._bench_jump_note = jump_note          # type: ignore[attr-defined]
        if m_cache is not None:
            m_cache[key] = m
    else:
        jump_note = getattr(m, "_bench_jump_note", "")
    res = chain.run_chain(cfg, symbols, start, end, res_ref.initial_equity, m=m)
    eq = res.equity
    r_naive = eq.pct_change().fillna(0.0)
    r_chain = res_ref.equity.pct_change().fillna(0.0)
    ir = information_ratio(r_chain, r_naive)
    out = {
        "定义(原文)": NAIVE_DEFS[kind],
        "槽位约束": f"fixed_fraction,{slots_eff} 槽各 {1.0/max(1,slots_eff):.1%}",
        "摩擦成本口径": {k: v for k, v in costs_eff.items() if k != "source"}
                        or "引擎默认(按 ADV20 分三档)",
        "假跳变剔除": ("已剔除(口径见下)" if drop_fake_jumps else
                       "★ 未剔除 —— 这一版只用来量假跳变有多大,不作判定依据"),
        "警示": [x for x in (slots_note, costs_note, jump_note) if x],
        "朴素基准笔数": int(len(res.ledger)),
        "朴素基准总收益": total_return(eq),
        "朴素基准CAGR": analyze.cagr(eq),
        "朴素基准最大回撤": analyze.drawdown(eq)[0],
        "朴素基准卡玛比率": calmar(eq),
        "★集中度自检": _concentration(res.ledger),
        "★链 − 朴素基准(总收益)": total_return(res_ref.equity) - total_return(eq),
        "★信息比率(链 vs 朴素基准)": ir,
        "★专家裁决线": _naive_verdict(res_ref.equity, eq, ir),
    }
    out["_daily"] = r_naive
    out["_ledger_n"] = int(len(res.ledger))
    return out


def _concentration(ledger: pd.DataFrame, top: int = 10) -> dict[str, Any]:
    """
    ★ 集中度自检:前 top 笔赚了多少、占总盈利多少、最大单笔毛收益是几倍。

    大白话:这是用来回答「这条基准的成绩是不是几笔异常 bar 扛起来的」。
    ★ 不带任何参数的事实陈述 —— 看到「前 10 笔占 90%」就知道这个数不能用。
    """
    if ledger is None or ledger.empty:
        return {"说明": "没有成交"}
    pnl = ledger["net_pnl"].astype(float)
    pos = pnl[pnl > 0].sum()
    topn = pnl.nlargest(top).sum()
    g = ledger["gross_return"].astype(float)
    worst = ledger.nlargest(3, "gross_return")[
        ["symbol", "entry_date", "exit_date", "gross_return"]]
    return {
        f"前{top}笔净盈亏": float(topn),
        f"前{top}笔占总盈利比例": float(topn / pos) if pos > 0 else float("nan"),
        "最大单笔毛收益": float(g.max()),
        "毛收益 > +100% 的笔数": int((g > 1.0).sum()),
        "最赚的三笔": [{"票": r["symbol"], "进": str(pd.Timestamp(r["entry_date"]).date()),
                        "出": str(pd.Timestamp(r["exit_date"]).date()),
                        "毛收益": float(r["gross_return"])}
                       for _, r in worst.iterrows()],
        "怎么读": "★ 前 10 笔占总盈利过半 → 这条曲线是几笔异常 bar 扛起来的,数字不可用;"
                  "占比低(一两成以内)→ 是一个铺得开的效应,数字可用",
    }


def _naive_verdict(eq_chain: pd.Series, eq_naive: pd.Series,
                   ir: float | str) -> str:
    """专家原话:信息比率打不过无脑基准 → 直接枪毙。"""
    ck, cn = calmar(eq_chain), calmar(eq_naive)
    if isinstance(ir, str):
        return f"算不出(信息比率 {ir})—— σ 近乎为零,不给结论"
    if ir <= 0:
        return (f"★ 枪毙:信息比率 {ir:+.3f} ≤ 0,"
                f"复杂算法打不过无脑基准(链卡玛={ck} 朴素卡玛={cn})")
    return (f"过线:信息比率 {ir:+.3f} > 0(链卡玛={ck} 朴素卡玛={cn})—— "
            f"★ 只说明打得过无脑基准,不等于这一派成立")


# ================================================================ 基准家族

FAMILY_TREND = "trend"
FAMILY_MEANREV = "meanrev"

#: ★ 均值回归策略不许再用单边多头指数当基准(专家明确说那是「基准错配」)。
FAMILY_PLAN = {
    FAMILY_TREND: {
        "该看哪几条": ["基准二_静态基准", "基准三_动态开关基准", "基准四_槽位机会成本线"],
        "说明": "趋势/突破类:单边多头指数是合适的对照 → 动态开关 + 静态 + 槽位",
    },
    FAMILY_MEANREV: {
        "该看哪几条": ["① 底线 = 无风险利率", "② 技能 = 朴素基准"],
        "说明": "★ 均值回归类:拿 SPY 考核是「基准错配」(专家原话)→ 改成双轨:"
                "① 底线 = 无风险利率(跑不过现金就没意义)"
                "② 技能 = 朴素基准(打不过无脑规则就枪毙)。"
                "★ 静态 / 动态开关 / 槽位三条照样算出来**只作参考**,不作判定依据。",
    },
}


def benchmark_family(cfg: chain.ChainConfig) -> str:
    """
    从 YAML 读 benchmark.family(trend / meanrev)。★ 不硬编码策略名。

    ★ 没标注就报错,不猜 —— 猜错会让均值回归策略继续被错配的基准考核,
      而那正是这一轮要修的事。
    """
    fam = ((cfg.get("benchmark") or {}).get("family"))
    if fam is None:
        raise ValueError(
            f"链 {cfg.name} 的 YAML 里没有 benchmark.family —— "
            f"★ 必须显式写 trend 或 meanrev。不猜:猜错就等于继续拿单边多头指数"
            f"考核均值回归策略(专家说这是「基准错配」)。")
    fam = str(fam).strip().lower()
    if fam not in FAMILY_PLAN:
        raise ValueError(f"benchmark.family 只认 trend / meanrev,给的是 {fam!r}")
    return fam


# ================================================================ 总装

def bench_suite(cfg: chain.ChainConfig, res: chain.ChainResult,
                symbols: list[str],
                m: matrices.Matrices | None = None,
                start: str = data.PERF_START, end: str = data.PERF_END,
                m_cache: dict | None = None,
                with_naive: bool = True) -> dict[str, Any]:
    """
    一条链的三条新基准线 + 旧静态基准 + 择时/选股拆分,一次全算出来。

    ★ 按 YAML 的 benchmark.family 自动选基准组合(trend / meanrev),不硬编码。
    """
    bm = cfg.get("benchmark") or {}
    fam = benchmark_family(cfg)
    m = m or matrices.build(cfg.raw, symbols)
    gate = gate_series(m, res.equity.index)
    chain_total = total_return(res.equity)
    r_chain = res.equity.pct_change().fillna(0.0)

    static = static_benchmark(res, bm.get("component_match", "large"),
                              bm.get("risk_free_annual"))
    dyn_lit = gated_dynamic_benchmark(res, gate, static, exposure_matched=False)
    dyn_exp = gated_dynamic_benchmark(res, gate, static, exposure_matched=True)

    # ★ 择时贡献一律用同敞口口径 —— 只有它和静态基准只差「关闸怎么记」这一件事,
    #   所以加法恒等式成立,而且闸门从不关的链差额恒等于 0(sanity check 的锚)。
    timing = dyn_exp["基准总收益"] - static["基准总收益"]
    picking = chain_total - dyn_exp["基准总收益"]
    static_excess = chain_total - static["基准总收益"]
    picking_lit = chain_total - dyn_lit["基准总收益"]

    # ---- 基准四:两个替代品都算(★ 都不是 QQQ)
    slot_rf = bm.get("risk_free_annual")
    etf = data.load_benchmark(SLOT_PROXY_ETF)["close"]
    slot_a = slot_replacement_benchmark(
        res, etf.reindex(res.equity.index).ffill().pct_change().fillna(0.0),
        etf, slot_rf, ma=50, proxy_note=SLOT_PROXY_ETF_NOTE)
    topn = _topn_adv_equal_weight(symbols, res.equity.index)
    topn_level = curve(topn, 100.0)
    slot_b = slot_replacement_benchmark(
        res, topn, topn_level, slot_rf, ma=50, proxy_note=SLOT_PROXY_TOPN_NOTE)

    # ---- 基准五:朴素基准(按家族选版本;两版都算出来便于横向看)
    slots = int(((cfg.get("sizing") or {}).get("params") or {})
                .get("max_positions", 10))
    equal_all = (cfg.get("sizing") or {}).get("type") == "equal_weight_all"
    costs = cfg.get("costs") or {}
    naive: dict[str, Any] = {}
    if with_naive:
        for kind in (NAIVE_MEANREV, NAIVE_RSI2):
            naive[kind] = naive_baseline(kind, symbols, slots, costs, res,
                                         start, end, m_cache,
                                         equal_all=equal_all,
                                         drop_fake_jumps=True)
            naive[kind + "_★未剔假跳变(只量artifact有多大)"] = naive_baseline(
                kind, symbols, slots, costs, res, start, end, m_cache,
                equal_all=equal_all, drop_fake_jumps=False)
        naive["★本家族该用哪一版"] = (
            NAIVE_MEANREV if fam == FAMILY_MEANREV else
            "两版都只作参考(趋势/突破类的判定看动态开关 + 静态 + 槽位)")

    # ---- ★ 均值回归家族的双轨:① 底线 = 无风险利率 ② 技能 = 朴素基准
    rf_d, rf_a, rf_notes = rf_leg(bm.get("risk_free_annual"))
    rf_curve = curve(pd.Series(rf_d, index=res.equity.index), res.equity.iloc[0])
    rf_total = total_return(rf_curve)
    ir_rf = information_ratio(r_chain, pd.Series(rf_d, index=res.equity.index))
    dual = {
        "① 底线_无风险利率": {
            "口径": "跑不过现金就没意义。★ 仓库没有短端利率序列 → 按 0% 记并标明",
            "无风险利率_年化": rf_a,
            "底线总收益": rf_total,
            "★超额(链 − 无风险)": chain_total - rf_total,
            "★信息比率(链 vs 无风险)": ir_rf,
            "过不过底线": ("过" if chain_total - rf_total > 0 else "★ 不过 —— 连现金都跑不过"),
            "警示": rf_notes,
        },
        "② 技能_朴素基准": (
            {k: v for k, v in naive[NAIVE_MEANREV].items()
             if not k.startswith("_")} if with_naive else "未跑"),
        "说明": FAMILY_PLAN[FAMILY_MEANREV]["说明"],
    }

    out: dict[str, Any] = {
        "链名": cfg.name,
        "★笔数": int(len(res.ledger)),
        "样本警示": analyze.sample_size_banner(len(res.ledger)),
        "链总收益": chain_total,
        "链CAGR": analyze.cagr(res.equity),
        "链最大回撤": analyze.drawdown(res.equity)[0],
        "链卡玛比率": calmar(res.equity),
        "基准家族": fam,
        "基准家族_该看哪几条": FAMILY_PLAN[fam]["该看哪几条"],
        "基准家族_说明": FAMILY_PLAN[fam]["说明"],
        "闸门统计": {"开闸天数": dyn_exp["开闸天数"],
                     "关闸天数": dyn_exp["关闸天数"],
                     "关闸占比": dyn_exp["关闸占比"],
                     "闸门条件来源": "该链 YAML 的 ② regime 那一块"},
        "基准二_静态基准": {k: v for k, v in static.items()
                            if not k.startswith("_")},
        "基准三_动态开关基准_原文口径": {k: v for k, v in dyn_lit.items()
                                        if not k.startswith("_")},
        "基准三_动态开关基准_同敞口口径": {k: v for k, v in dyn_exp.items()
                                          if not k.startswith("_")},
        "★静态基准超额": static_excess,
        "★择时贡献": timing,
        "★选股贡献": picking,
        "★选股贡献_原文口径": picking_lit,
        "★加法恒等式自检": {
            "静态基准超额": static_excess,
            "选股贡献 + 择时贡献": picking + timing,
            "残差": static_excess - (picking + timing),
            "说明": "★ 残差必须是 0(浮点误差级别)。不是 0 就是代码坏了。",
        },
        "★判定_这条策略会不会选股": _picking_verdict(
            picking, picking_lit, static_excess, timing,
            int(len(res.ledger))),
        "基准四_槽位机会成本线_替代品甲": {k: v for k, v in slot_a.items()
                                          if not k.startswith("_")},
        "基准四_槽位机会成本线_替代品乙": {k: v for k, v in slot_b.items()
                                          if not k.startswith("_")},
        "基准五_朴素基准": {k: ({kk: vv for kk, vv in v.items()
                                 if not kk.startswith("_")}
                                if isinstance(v, dict) else v)
                            for k, v in naive.items()},
        "★均值回归双轨(基准错配的修法)": dual,
        "★基准四数据缺口": QQQ_MISSING_NOTE,
        "★顺手量到的数据问题": ETF_SPLIT_FINDINGS,
    }
    out["_curves"] = {"静态": static["_daily"], "动态原文": dyn_lit["_daily"],
                      "动态同敞口": dyn_exp["_daily"], "槽位甲": slot_a["_daily"],
                      "槽位乙": slot_b["_daily"], "链": r_chain}
    return out


#: ★ 「超额 ≈ 0」的判定线。专家的裁决是「超额≈0 就说明这条策略根本不会选股」,
#   ★ 但「≈0」他没给数。这里用的是**我们自己定的一条展示线**:
#     |选股贡献| ≤ 2pp(八年累计),相当于年化 0.25pp 以内。
#   ★ 这不是调出来的参数(没有搜过别的值),但它确实是我们定的 —— 报告里要写明。
PICKING_ZERO_BAND = 0.02


def _picking_verdict(picking: float, picking_lit: float,
                     static_excess: float, timing: float, n: int) -> str:
    """
    ★ 必须为每条链明确回答这一句:在动态开关基准下超额是不是 ≈0?
      ≈0 → 这条策略根本不会选股,它所有的超额 100% 来自闸门这一道开关。
    """
    if n == 0:
        return "一笔都没成交,不给结论"
    share = (abs(timing) / abs(static_excess)
             if abs(static_excess) > 1e-12 else float("nan"))
    head = (f"选股贡献 {picking:+.2%}(原文口径 {picking_lit:+.2%});"
            f"择时贡献 {timing:+.2%};静态基准超额 {static_excess:+.2%}。")
    if abs(picking) <= PICKING_ZERO_BAND:
        tail = (f"★ 动态开关基准下超额 ≈ 0(|{picking:+.2%}| ≤ "
                f"{PICKING_ZERO_BAND:.0%} 展示线)→ **这条策略基本不会选股**,"
                f"它的超额几乎全部来自闸门这一道开关。")
    elif picking < 0:
        tail = ("★ 动态开关基准下超额为**负** → 这条策略不但不会选股,"
                "开闸的日子里它选的票还跑输了同敞口指数。")
    else:
        tail = ("动态开关基准下超额为正 → 开闸的日子里它选的票确实跑赢了同敞口指数;"
                "★ 这一条能不能算「成立」仍要看四格硬关和样本量,这里只答选股这一问。")
    if np.isfinite(share):
        tail += f"(择时占静态基准超额绝对值的 {share:.0%})"
    if n < 150:
        tail += " ★ 样本不足(<150 笔),不代表无效。"
    return head + tail


__all__ = ["rf_leg", "curve", "total_return", "calmar", "information_ratio",
           "curve_stats", "gate_series", "static_benchmark",
           "gated_dynamic_benchmark", "slot_replacement_benchmark",
           "naive_baseline", "benchmark_family", "bench_suite",
           "NAIVE_MEANREV", "NAIVE_RSI2", "FAMILY_TREND", "FAMILY_MEANREV",
           "QQQ_MISSING_NOTE", "ETF_SPLIT_FINDINGS",
           "SLOT_PROXY_ETF", "SLOT_PROXY_TOPN",
           "PICKING_ZERO_BAND", "UNCOMPUTABLE"]
