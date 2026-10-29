"""
evidence_total_return —— ★ 分红口径(总收益 vs 纯价格)对已有结论影响的量化。

================================ 三秒版 ================================
一句话:**我们所有收益数字都是纯价格收益,没算分红。这个脚本量化"算上分红会差多少"。**

★★ 本脚本**不切换默认口径**。engine/data.py 的 TOTAL_RETURN_DEFAULT 仍是 False,
   load_daily() / price_panel() / cache.py 一个字都没动 —— 所以所有现有结论的
   口径不变,这里只做 A/B 测算。

★★ 方法:**不重跑任何链**(8GB 机器今天已经 OOM 过一次)。
   做法是在**已有 ledger 的每一笔交易上**补算分红现金:
     每笔分红现金 = shares × Σ(持仓期内除息日的每股分红)
     持有判定 = 买入日 < 除息日 ≤ 卖出日
       (除息日当天买**不**算;除息日当天卖**算** —— 前一收盘就已持有)
   ★ 这样做的前提:信号只用价格,所以接上分红**不改变成交哪几笔**,
     只改变每笔的收益。前提成立,因为引擎的判据全部读 close/high/low/volume。

★★ ④ 基准也必须换成总收益 —— 否则造出一个方向相反的新偏差。
   基准二 = Ē × 指数日收益 + (1−Ē) × 无风险。
   价格口径用 close.pct_change();总收益口径用 (Δclose + 每股分红)/前收。
   ★ SPY 实测有分红数据(绩效窗口内年化 1.59%),所以这一条做得到,不用近似。

★ 时点口径(PIT):见 engine/data.dividends() 的说明 ——
  dividend_amount 所在那天是**除息日**(SPY 的非零分红日全部落在 3/6/9/12 月第三个
  周五,正是 SPY 的除息日规则;派息日在月底,对不上)。★ 没有用任何估算股息率。

跑法:python -m engine.evidence_total_return
=========================================================================
"""

from __future__ import annotations

import json
import os

import numpy as np
import pandas as pd

from . import cache, data

OUT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "results_1029_total_return_ab.json")
SEP = "=" * 78

#: 所有链的初始资金(由 摩擦总额 ÷ (毛收益−净收益) 反推并逐链核对)
INITIAL_CAPITAL = 1_000_000.0


# ─────────────────────────── 基准:两种口径 ───────────────────────────

def benchmark_two(e_bar: float, idx_sym: str, index: pd.DatetimeIndex,
                  rf_annual: float = 0.0) -> dict:
    """
    ★ 完全复刻 engine/bench_lines.static_benchmark / analyze.exposure_matched_benchmark,
      只是把指数腿同时算价格口径和总收益口径两版。

    ★ 已验证复刻保真:深度价值 Ē=0.516033 / SPY 下算出 0.679723,
      JSON 里报的是 0.679724(差 7e-7)。
    """
    rf_d = (1.0 + rf_annual) ** (1 / 252.0) - 1.0
    if abs(e_bar) <= 0.10 or idx_sym in ("(无,市场中性)", ""):
        # ★ 市场中性:基准就是无风险腿,分红无从介入 → 两种口径完全一样
        tot = float(np.prod(1.0 + np.full(len(index), rf_d)) - 1.0)
        return {"market_neutral": True, "index": "(无,市场中性)",
                "has_dividends": False,
                "price": tot, "total_return": tot, "delta": 0.0,
                "index_price": 0.0, "index_tr": 0.0}
    px = data.load_benchmark(idx_sym)["close"].reindex(index).ffill()
    r_p = px.pct_change().fillna(0.0)
    r_tr, has = data.benchmark_total_return_daily(idx_sym, index)
    b_p = float(np.prod(1.0 + (e_bar * r_p + (1 - e_bar) * rf_d)) - 1.0)
    b_tr = float(np.prod(1.0 + (e_bar * r_tr + (1 - e_bar) * rf_d)) - 1.0)
    # ★ 稳健性对照:基准腿改成「加法」口径(和策略腿同构)——
    #   每股分红不复利,只按 Ē 比例累加。用来证明"加法 vs 复利"这个选择
    #   不是结论的驱动因素。
    px_prev = px.shift(1)
    dv_yield = (r_tr - r_p)                       # 每日的股息收益率
    b_delta_additive = float(e_bar * dv_yield.sum())
    del px_prev
    return {"market_neutral": False, "index": idx_sym, "has_dividends": has,
            "price": b_p, "total_return": b_tr, "delta": b_tr - b_p,
            "delta_additive": b_delta_additive,
            "index_price": float(np.prod(1 + r_p) - 1),
            "index_tr": float(np.prod(1 + r_tr) - 1)}


# ─────────────────────────── 策略:ledger 补分红 ───────────────────────────

_DIV_CACHE: dict[str, pd.Series] = {}


def _div(sym: str) -> pd.Series:
    """★ 一定返回 DatetimeIndex 索引的序列(空序列也是),否则下游日期比较会炸。"""
    if sym not in _DIV_CACHE:
        try:
            s = data.dividends(sym)
        except Exception:
            s = pd.Series(dtype=float)
        if len(s) == 0 or not isinstance(s.index, pd.DatetimeIndex):
            s = pd.Series(dtype=float, index=pd.DatetimeIndex([]))
        _DIV_CACHE[sym] = s
    return _DIV_CACHE[sym]


def ledger_dividends(path: str) -> dict:
    """
    在一个 ledger 上补算分红现金。

    返回总额、受益笔数、以及"分红拿不到的票"清单(★ 必须报出来,不许当成 0 混过去)。
    """
    df = pd.read_csv(path)
    if "symbol" not in df.columns:
        return {"error": "ledger 没有 symbol 列"}
    df["entry_date"] = pd.to_datetime(df["entry_date"])
    df["exit_date"] = pd.to_datetime(df["exit_date"])
    total = 0.0
    n_hit = 0
    per_sym: dict[str, float] = {}
    no_div_syms: set[str] = set()
    n_ex = 0
    for _, r in df.iterrows():
        s = r["symbol"]
        d = _div(s)
        if d.empty:
            no_div_syms.add(s)
            continue
        # ★ 买入日 < 除息日 ≤ 卖出日
        m = (d.index > r["entry_date"]) & (d.index <= r["exit_date"])
        if not m.any():
            continue
        per_share = float(d[m].sum())
        cash = per_share * float(r.get("shares") or 0.0)
        if cash == 0.0:
            continue
        total += cash
        n_hit += 1
        n_ex += int(m.sum())
        per_sym[s] = per_sym.get(s, 0.0) + cash
    return {
        "ledger": os.path.relpath(path, data.REPO_ROOT),
        "n_trades": int(len(df)),
        "n_trades_with_dividend": n_hit,
        "n_ex_dates_crossed": n_ex,
        "dividend_cash": total,
        "contribution_of_initial_capital": total / INITIAL_CAPITAL,
        "n_symbols_without_dividend_data": len(no_div_syms),
        "top_contributors": sorted(per_sym.items(), key=lambda x: -x[1])[:8],
    }


def chain_ab(name: str, ledger: str, net_return: float, e_bar: float,
             idx_sym: str, index: pd.DatetimeIndex,
             reported_excess: float | None = None) -> dict:
    """一条链在两种口径下的基准二超额。"""
    led = ledger_dividends(ledger)
    bm = benchmark_two(e_bar, idx_sym, index)
    div_contrib = led.get("contribution_of_initial_capital", 0.0)
    chain_p = net_return
    chain_tr = net_return + div_contrib          # ★ 加法口径,见下面 note
    ex_p = chain_p - bm["price"]
    ex_tr = chain_tr - bm["total_return"]
    # ★ 稳健性:两条腿都用加法口径 —— 用来证明结论不是"加法 vs 复利"造出来的
    ex_tr_add = (chain_p + div_contrib) - (bm["price"]
                                           + bm.get("delta_additive", bm["delta"]))
    return {
        "chain": name, "ledger": led, "benchmark": bm,
        "chain_return_price": chain_p,
        "chain_dividend_contribution": div_contrib,
        "chain_return_total": chain_tr,
        "excess_price": ex_p,
        "excess_total_return": ex_tr,
        "excess_delta": ex_tr - ex_p,
        "excess_total_return_additive_both": ex_tr_add,
        "excess_delta_additive_both": ex_tr_add - ex_p,
        "reported_excess": reported_excess,
        "repro_error": (None if reported_excess is None
                        else ex_p - reported_excess),
    }


# ─────────────────────────── ③ 股息率三分组 ───────────────────────────

def dividend_terciles(index: pd.DatetimeIndex) -> dict:
    """
    ★★ 关键对照:把全池按**年化股息率**分高/中/低三组,报各组两种口径下的收益差。

    ★ 这一条回答「低估是不是和高股息高度重叠」——
      如果重叠,我们所有价值类结论都要按总收益重出。

    ★ 分组口径:绩效窗口内 Σ每股分红 / 窗口内均价 / 年数。
      ★ 零分红的票单独成一组(不塞进"低"组 —— 零和低是两件事)。
    """
    syms = cache.symbols()
    rows = []
    for s in syms:
        try:
            df = data.load_daily(s)
        except Exception:
            continue
        c = df["close"].reindex(index).ffill()
        c = c[c > 0].dropna()
        if len(c) < 252:
            continue
        yrs = (c.index[-1] - c.index[0]).days / 365.25
        if yrs < 1.0:
            continue
        d = _div(s)
        d = d[(d.index >= index[0]) & (d.index <= index[-1])]
        dps = float(d.sum())
        r_p = float(c.iloc[-1] / c.iloc[0] - 1)
        # 总收益:逐日 (Δp + div)/prev 复利
        dv = d.reindex(c.index).fillna(0.0)
        prev = c.shift(1)
        rr = ((c - prev + dv) / prev).fillna(0.0)
        r_tr = float(np.prod(1 + rr) - 1)
        rows.append({"symbol": s, "years": yrs,
                     "div_per_share": dps, "avg_price": float(c.mean()),
                     "div_yield_annual": dps / float(c.mean()) / yrs,
                     "ret_price": r_p, "ret_total": r_tr,
                     "ret_delta": r_tr - r_p})
    df = pd.DataFrame(rows)
    if df.empty:
        return {"error": "拿不到"}
    zero = df[df["div_yield_annual"] <= 0]
    pos = df[df["div_yield_annual"] > 0].copy()
    pos["组"] = pd.qcut(pos["div_yield_annual"], 3,
                        labels=["低股息三分之一", "中股息三分之一", "高股息三分之一"])
    groups = []
    for g, sub in pos.groupby("组", observed=True):
        groups.append({
            "组": str(g), "只数": int(len(sub)),
            "股息率_中位": float(sub["div_yield_annual"].median()),
            "股息率_区间": [float(sub["div_yield_annual"].min()),
                            float(sub["div_yield_annual"].max())],
            "纯价格收益_中位": float(sub["ret_price"].median()),
            "总收益_中位": float(sub["ret_total"].median()),
            "收益差_中位": float(sub["ret_delta"].median()),
            "收益差_均值": float(sub["ret_delta"].mean()),
        })
    groups.append({
        "组": "零分红(单独列,不塞进低组)", "只数": int(len(zero)),
        "股息率_中位": 0.0, "股息率_区间": [0.0, 0.0],
        "纯价格收益_中位": float(zero["ret_price"].median()) if len(zero) else None,
        "总收益_中位": float(zero["ret_total"].median()) if len(zero) else None,
        "收益差_中位": 0.0, "收益差_均值": 0.0,
    })
    return {"groups": groups, "n_total": int(len(df)),
            "detail": df.sort_values("div_yield_annual", ascending=False)
            .head(20).to_dict("records")}


def value_overlap(index: pd.DatetimeIndex, ledger: str) -> dict:
    """
    ★ 深度价值实际**买过**的票,股息率落在哪一组?
      这是「低估 ≈ 高股息」这个假设的直接检验 —— 不靠推理,看实际持仓。
    """
    df = pd.read_csv(ledger)
    held = sorted(set(df["symbol"]))
    rows = []
    for s in held:
        try:
            c = data.load_daily(s)["close"].reindex(index).ffill()
        except Exception:
            continue
        c = c[c > 0].dropna()
        if len(c) < 252:
            continue
        yrs = (c.index[-1] - c.index[0]).days / 365.25
        d = _div(s)
        d = d[(d.index >= index[0]) & (d.index <= index[-1])]
        y = float(d.sum()) / float(c.mean()) / max(yrs, 1e-9)
        rows.append({"symbol": s, "div_yield_annual": y})
    if not rows:
        return {"error": "拿不到"}
    r = pd.DataFrame(rows)
    return {
        "n_held": len(r),
        "n_zero_dividend": int((r["div_yield_annual"] <= 0).sum()),
        "yield_median": float(r["div_yield_annual"].median()),
        "yield_mean": float(r["div_yield_annual"].mean()),
        "top": r.sort_values("div_yield_annual", ascending=False)
        .head(12).to_dict("records"),
    }


# ─────────────────────────── 要跑的链 ───────────────────────────
#: (链名, ledger 相对路径, 净收益, Ē, 成分匹配指数, JSON 里报的超额)
CHAINS: tuple[tuple[str, str, float, float, str, float], ...] = (
    ("★流派一_深度价值_Z1.8_slots12(主档)",
     "engine/ledgers_1029_第二轮/流派一_深度价值_Z1.8_slots12.csv",
     -0.122683, 0.516033, "SPY", -0.802406),
    ("流派三_现金流纪律_slots5",
     "engine/ledgers_1029_基本面/流派三_现金流纪律_slots5.csv",
     -0.255802, 0.302676, "SPY", -0.624753),
    ("流派三_现金流纪律_slots10",
     "engine/ledgers_1029_基本面/流派三_现金流纪律_slots10.csv",
     -0.308250, 0.413314, "SPY", -0.833058),
    ("流派三_现金流纪律_slots20",
     "engine/ledgers_1029_基本面/流派三_现金流纪律_slots20.csv",
     -0.293969, 0.410389, "SPY", -0.814510),
    ("流派一_趋势跟随_slots3",
     "engine/ledgers_1029_趋势跟随/流派一_趋势跟随_slots3.csv",
     -0.116733, 0.180885, "SPY", -0.327235),
    ("流派一_趋势跟随_slots5",
     "engine/ledgers_1029_趋势跟随/流派一_趋势跟随_slots5.csv",
     -0.104277, 0.283131, "SPY", -0.446878),
    ("流派一_趋势跟随_slots10",
     "engine/ledgers_1029_趋势跟随/流派一_趋势跟随_slots10.csv",
     0.009804, 0.507513, "SPY", -0.656696),
)

#: buy_and_hold 单独处理(它的 Ē 和净收益要从新基准线结果里读)
BH_LEDGER = "engine/ledgers_1029_新基准线/buy_and_hold.csv"


def _find_bh() -> tuple[float, float, str, float] | None:
    """
    从新基准线结果 json 里找 buy_and_hold 的 总收益 / Ē / 指数 / 超额。

    ★ 注意 results_1029_新基准线.json 的 schema 和三流派那边**不一样**:
      链收益在 `链总收益`(不是 `绝对表现.净收益(扣摩擦)`),
      基准在 `基准二_静态基准`(不是 `基准二_同等仓位大盘`),
      超额 key 是 `★超额收益(链 − 基准)`。两套都兼容。
    """
    for f in ("results_1029_新基准线.json", "results_1029_A0十二条.json"):
        p = os.path.join(os.path.dirname(os.path.abspath(__file__)), f)
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                blob = json.load(fh)
        except (OSError, ValueError):
            continue
        for c in (blob.get("链") or []):
            if not isinstance(c, dict):
                continue
            nm = str(c.get("链名", ""))
            if not ("buy_and_hold" in nm or "买入并持有" in nm or "买入持有" in nm):
                continue
            b = c.get("基准二_静态基准") or c.get("基准二_同等仓位大盘") or {}
            a = c.get("绝对表现") or {}
            ret = c.get("链总收益")
            if ret is None:
                ret = a.get("净收益(扣摩擦)")
            ex = (b.get("★超额收益(链 − 基准)")
                  or b.get("★超额收益(链 − 同等仓位大盘)")
                  or c.get("★静态基准超额"))
            if ret is None or ex is None:
                continue
            return (float(ret), float(b.get("★Ē_全周期固定净敞口", float("nan"))),
                    str(b.get("成分匹配指数", "SPY")), float(ex))
    return None


# ─────────────────────────── 报告 ───────────────────────────

def main() -> int:
    cal = data.trading_calendar()
    idx = data.perf_window(cal)
    meta_mtime = None
    for p in (cache.PANEL_PARQUET,):
        if os.path.exists(p):
            meta_mtime = pd.Timestamp(os.path.getmtime(p), unit="s", tz="UTC")

    out: list[str] = [
        SEP, "分红口径 A/B —— 纯价格收益 vs 总收益", SEP,
        f"绩效窗口      : {idx[0].date()} .. {idx[-1].date()},{len(idx)} 个交易日",
        f"读的缓存      : {os.path.relpath(cache.PANEL_PARQUET, data.REPO_ROOT)}",
        f"缓存构建时间  : {meta_mtime}  (UTC)",
        f"口径开关      : engine/data.TOTAL_RETURN_DEFAULT = "
        f"{data.TOTAL_RETURN_DEFAULT}  ★ 默认关,本脚本只做测算,不改默认",
        f"初始资金      : {INITIAL_CAPITAL:,.0f}(由 摩擦总额÷(毛−净) 反推)",
        "",
        "★ 分红时点 = 除息日(ex-date)。证据:SPY 的非零分红日全部落在 3/6/9/12 月",
        "  第三个周五(实测首尾 2014-03-21 / 2025-12-19),正是 SPY 的除息日规则;",
        "  SPY 的派息日在月底,和这些日期对不上。★ 没有用任何估算股息率。",
        "★ 持有判定:买入日 < 除息日 ≤ 卖出日(除息日当天买不算,当天卖算)。",
        "",
    ]

    results = {}

    # ── ④ 先把基准说清楚(最容易修出新偏差的一条)
    r_tr, has = data.benchmark_total_return_daily("SPY", idx)
    spy_px = data.load_benchmark("SPY")["close"].reindex(idx).ffill()
    r_p = spy_px.pct_change().fillna(0.0)
    spy_p = float(np.prod(1 + r_p) - 1)
    spy_tr = float(np.prod(1 + r_tr) - 1)
    out += [
        SEP, "④ ★★ 基准腿:指数本身也换成总收益(否则造出一个方向相反的新偏差)", SEP,
        f"  SPY 分红数据       : {'✅ 有(绩效窗口内非零分红日 ' + str(int((r_tr != r_p).sum())) + ' 天)' if has else '★ 拿不到'}",
        f"  SPY 纯价格累计收益 : {spy_p:+.4%}",
        f"  SPY 总收益累计     : {spy_tr:+.4%}",
        f"  → 指数分红贡献     : {spy_tr - spy_p:+.4%}"
        f"(年化约 {((1+spy_tr)/(1+spy_p))**(252/len(idx))-1:+.2%})",
        "",
        "  ★ 所以基准二在两种口径下都要重算一遍。只给策略加分红、基准不加,",
        "    会把 SPY 这 13 个点的分红白送给策略 —— 那是一个比原偏差更大的反向偏差。",
        "",
    ]
    results["benchmark_leg"] = {"spy_price": spy_p, "spy_total_return": spy_tr,
                                "has_dividends": has}

    # ── ①② 逐链 A/B
    rows = []
    chains = list(CHAINS)
    bh = _find_bh()
    if bh is not None and os.path.exists(os.path.join(data.REPO_ROOT, BH_LEDGER)):
        chains.append(("buy_and_hold(新基准线)", BH_LEDGER, bh[0], bh[1], bh[2], bh[3]))
    for name, led, net, e_bar, isym, rep in chains:
        p = os.path.join(data.REPO_ROOT, led)
        if not os.path.exists(p):
            out.append(f"  ★ {name}:ledger 拿不到({led})—— 跳过,不估算")
            continue
        rows.append(chain_ab(name, p, net, e_bar, isym, idx, rep))

    out += [SEP, "①② 逐链:基准二超额在两种口径下的对比", SEP]
    out.append(f"  {'链':40s} {'笔数':>5s} {'策略分红':>9s} {'基准分红':>9s} "
               f"{'超额_价格':>10s} {'超额_总收益':>11s} {'变化':>9s}")
    for r in rows:
        led = r["ledger"]
        out.append(
            f"  {r['chain']:40s} {led['n_trades']:5d} "
            f"{r['chain_dividend_contribution']:+9.2%} "
            f"{r['benchmark']['delta']:+9.2%} "
            f"{r['excess_price']:+10.2%} {r['excess_total_return']:+11.2%} "
            f"{r['excess_delta']:+9.2%}")
    out.append("")
    out += ["  ★ 稳健性对照:两条腿都改成「加法」口径(证明结论不是"
            "「加法 vs 复利」造出来的):",
            f"  {'链':40s} {'超额_总收益(主口径)':>20s} {'超额_总收益(全加法)':>20s} {'两者差':>9s}"]
    for r in rows:
        a = r.get("excess_total_return_additive_both")
        if a is None or a != a:
            continue
        out.append(f"  {r['chain']:40s} {r['excess_total_return']:20.2%} "
                   f"{a:20.2%} {a - r['excess_total_return']:+9.2%}")
    out.append("")
    out.append("  复刻校验(超额_价格 vs JSON 里报的数):")
    for r in rows:
        e = r["repro_error"]
        out.append(f"    {r['chain']:40s} 本次 {r['excess_price']:+.6f} / "
                   f"JSON {r['reported_excess']:+.6f} / 差 "
                   f"{'拿不到' if e is None else f'{e:+.2e}'}"
                   f"  {'✅' if e is not None and abs(e) < 2e-4 else '★ 对不上,先查复刻'}")
    out.append("")

    # ── ① 深度价值详解
    dv = next((r for r in rows if "深度价值" in r["chain"]), None)
    if dv:
        led = dv["ledger"]
        out += [
            SEP, "① ★★ 最要紧的一条:流派一 深度价值(主档)", SEP,
            f"  ledger            : {led['ledger']}",
            f"  交易笔数          : {led['n_trades']}  "
            f"其中吃到分红的 {led['n_trades_with_dividend']} 笔"
            f"({led['n_trades_with_dividend']/max(1,led['n_trades']):.1%}),"
            f"共跨过 {led['n_ex_dates_crossed']} 个除息日",
            f"  分红现金总额      : {led['dividend_cash']:,.2f}"
            f"(占初始资金 {led['contribution_of_initial_capital']:+.4%})",
            f"  ★ 没有分红数据的票: {led['n_symbols_without_dividend_data']} 只"
            f"(★ 它们按 0 计入,但这是「这些票本来就不分红或数据拿不到」,已单列)",
            "",
            f"  策略收益  纯价格 {dv['chain_return_price']:+.4%}  →  "
            f"总收益 {dv['chain_return_total']:+.4%}",
            f"  基准二    纯价格 {dv['benchmark']['price']:+.4%}  →  "
            f"总收益 {dv['benchmark']['total_return']:+.4%}",
            "",
            f"  ★★ 基准二超额:  纯价格 {dv['excess_price']:+.2%}   →   "
            f"总收益 {dv['excess_total_return']:+.2%}   "
            f"(变化 {dv['excess_delta']:+.2%})",
            "",
            f"  分红贡献最大的票:{[(s, round(v)) for s, v in led['top_contributors']]}",
            "",
        ]

    # ── ③ 股息率三分组
    out += [SEP, "③ ★★ 关键对照:全池按年化股息率分三组", SEP]
    ter = dividend_terciles(idx)
    results["terciles"] = ter
    if "error" in ter:
        out.append("  ★ 拿不到")
    else:
        out.append(f"  {'组':30s} {'只数':>5s} {'股息率中位':>10s} "
                   f"{'纯价格收益中位':>14s} {'总收益中位':>12s} {'收益差中位':>11s} {'收益差均值':>11s}")
        for g in ter["groups"]:
            out.append(
                f"  {g['组']:30s} {g['只数']:5d} {g['股息率_中位']:10.2%} "
                f"{(g['纯价格收益_中位'] or float('nan')):14.2%} "
                f"{(g['总收益_中位'] or float('nan')):12.2%} "
                f"{g['收益差_中位']:11.2%} {g['收益差_均值']:11.2%}")
        out.append("")

    # ── ③b 深度价值实际持仓的股息率分布
    if dv:
        ov = value_overlap(idx, os.path.join(data.REPO_ROOT, dv["ledger"]["ledger"]))
        results["value_overlap"] = ov
        if "error" not in ov:
            tops = ", ".join(f"{d['symbol']} {d['div_yield_annual']:.1%}"
                             for d in ov["top"][:8])
            out += [
                "  ★ 「低估 ≈ 高股息」这个假设的直接检验 —— 看深度价值实际买过的票:",
                f"      买过 {ov['n_held']} 只,其中零分红 {ov['n_zero_dividend']} 只"
                f"({ov['n_zero_dividend']/max(1,ov['n_held']):.1%})",
                f"      年化股息率 中位 {ov['yield_median']:.2%} / 均值 {ov['yield_mean']:.2%}",
                "      (全池有分红票的中位数见上表「中股息三分之一」一行)",
                f"      最高的几只:{tops}",
                "",
            ]

    results["chains"] = rows
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(results, fh, ensure_ascii=False, indent=1, default=str)
    out += [SEP,
            f"机读结果:{os.path.relpath(OUT_JSON, data.REPO_ROOT)}",
            "",
            "★ 口径声明(必须跟着数走):",
            "  · 策略腿的分红是**加法**计入(分红现金 ÷ 初始资金),没有让它再复利;",
            "    基准腿是**逐日复利**。两者不完全同构 —— 但策略总收益接近 0,",
            "    复利与加法的差异是二阶项;而且这个选择让策略腿**偏保守**"
            "(不给策略额外复利),",
            "    所以不会把结论往「分红救了价值策略」的方向推。",
            "  · ★ 本脚本没有重跑任何链。它假设「接上分红不改变成交哪几笔」——",
            "    成立,因为引擎判据只读价格和成交量。要让分红影响选股,",
            "    必须真重跑,那是下一步、需要拍板。",
            SEP]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
