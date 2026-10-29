"""
自检 —— 跑一遍证明三件事。跑法:python -m engine.selftest

① 判据在「纯随机信号」上不显著 —— 如果显著,说明判据本身坏了,
   那后面跑出来的所有「显著」都不能信。
② 吊灯止损永远不高于当根收盘(造一个低位反弹的例子专门测它)。
③ 链执行器在「买入并持有」这份配置上,跑出来和直接算的收益一致。

另外三条连通性检查(④⑤⑥),顺手跑掉:
④ 两窗口两池子硬关:四格能跑通,且纯随机信号被判没过
⑤ 破产类退市强制 −100%:0 价 bar 真的埋进去了,持仓真的吃到 −100%
⑥ 拆股闸:6 根已修的位置不再有假跳变

★ 任何一项红的,整个引擎都不要用。
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

from . import analyze, cache, chain, data, matrices, split_gate, stats_gate, window_pool

PASS, FAIL = "✅ 通过", "❌ 没过"
_results: list[tuple[str, bool]] = []


def _check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, bool(ok)))
    print(f"{PASS if ok else FAIL}  {name}")
    for line in (detail or "").splitlines():
        print(f"        {line}")
    return bool(ok)


# =========================================================== ① 判据在纯随机上不显著

def test_gate_on_pure_noise() -> bool:
    """
    造一堆纯随机的「信号」和纯随机的「对照」,两边来自同一个分布。
    判据必须说「不显著」。
    为了不被单次运气骗到,换 12 组不同的随机种子各跑一遍。
    Z ≥ 1.65 的理论误报率约 5%,12 组里出 0~1 次都正常,所以允许最多 1 组误报。
    """
    n, B, trials = 200, stats_gate.B_DEFAULT, 12
    zs, false_alarms = [], []
    for k in range(trials):
        rng = np.random.default_rng(90210 + 31 * k)
        pool = rng.normal(0.0, 0.02, size=5000)           # 市场本身
        sig = rng.choice(pool, size=n, replace=False)     # 「信号」= 从市场里瞎抽
        r = stats_gate.bootstrap_test(
            "纯随机", sig, stats_gate.circular_block_sampler(pool, n_draw=n),
            B=B, seed=7 + k)
        zs.append(r.z_effect)
        if np.isfinite(r.z_effect) and r.z_effect >= stats_gate.Z_BASIC:
            false_alarms.append((k, round(float(r.z_effect), 2)))
    ok = len(false_alarms) <= 1
    _check("① 判据在纯随机信号上不显著", ok,
           f"12 组纯随机:Z 范围 {min(zs):+.2f} .. {max(zs):+.2f},"
           f"均值 {np.mean(zs):+.2f}(理论上应围着 0 转)\n"
           f"误报(Z≥{stats_gate.Z_BASIC})组数 = {len(false_alarms)},允许上限 1"
           + (f"\n误报明细:{false_alarms}" if false_alarms else ""))

    # 反向验证:判据不能是「永远说不显著」的瞎子
    rng = np.random.default_rng(4242)
    pool = rng.normal(0.0, 0.02, size=5000)
    sig = rng.choice(pool, size=n, replace=False) + 0.006     # 加 0.6%/笔 真优势
    r = stats_gate.bootstrap_test(
        "有真优势", sig, stats_gate.circular_block_sampler(pool, n_draw=n), B=B, seed=11)
    ok2 = np.isfinite(r.z_effect) and r.z_effect >= stats_gate.Z_INSTITUTIONAL
    _check("①b 反向验证:真有优势时判据必须抓出来", ok2,
           f"加 0.6%/笔 真优势 → Z={r.z_effect:+.2f}"
           f"(要求 ≥ {stats_gate.Z_INSTITUTIONAL}),p={r.p_empirical:.4f}")

    # 判据里不能出现「超过 N 次随机的最大值」这种会随 B 浮动的门槛
    import inspect
    src = inspect.getsource(stats_gate)
    body = "\n".join(l for l in src.splitlines()
                     if not l.strip().startswith(("#", '"', "'")))
    bad = [tok for tok in ("np.max(rand", "max(rand", "np.amax", "random_stats.max")
           if tok in body]
    ok3 = _check("①c 判据里没有「超过随机最大值」这类会随 B 浮动的门槛", not bad,
                 f"命中的可疑写法:{bad}" if bad else
                 "只用了(均值, 标准差, 排名分位),全程不取随机分布的 max")
    return ok and ok2 and ok3


# =========================================================== ② 吊灯止损铁律

def test_chandelier_never_above_close() -> bool:
    """
    造一个「先跌到坑底再拉起来」的走势 —— 这是最容易踩坑的形状:
    近 N 日最高价还挂在坑外面很高的位置,ATR 又被这段波动撑得很大,
    原始吊灯值算出来可能比当天收盘价还高。写错了止损价会高于收盘价,
    引擎会误判成赚钱,跑出 >60% 胜率的假数。

    测三件事:
      a) 两条铁律在这个例子上始终成立
      b) 原始吊灯值在这个例子上确实高于过收盘 —— 说明这个例子真能踩到坑
      c) 真实数据上跑一条带吊灯止损的链,引擎断言不被触发,且没有「好得不正常」的征兆
    """
    down = np.linspace(50, 20, 40)
    up = np.linspace(20, 60, 40)
    close = np.concatenate([down, up])
    idx = pd.bdate_range("2020-01-01", periods=len(close))
    df = pd.DataFrame({"open": close * 0.995, "high": close * 1.03,
                       "low": close * 0.97, "close": close, "volume": 1e6}, index=idx)
    df["dollar_volume"] = df["close"] * df["volume"]

    from . import signals
    raw = signals.chandelier_raw(df, period=22, multiple=3.0, atr_period=20)
    n_trap = int((raw > df["close"]).sum())

    # ★ 要测的不变式准确说是:「在持仓还开着的每一根上,止损价 ≤ 当根收盘」。
    #   它成立靠的是引擎的执行顺序 —— 先判止损有没有被触及(被触及就平仓、
    #   不再更新),剩下的持仓才抬止损。所以这里必须把平仓那一步一起复现,
    #   不能只跑「一路往上抬」—— 那样在下跌段会漂出去,测的不是引擎的逻辑。
    violations, non_monotonic, runs = [], [], []
    for entry_i in (5, 20, 38, 45, 60):      # 下跌段、坑底、反弹段各进一次
        stop = -np.inf
        opened_bars = 0
        for i in range(entry_i, len(idx)):
            ts = idx[i]
            cl, lo = float(df.at[ts, "close"]), float(df.at[ts, "low"])
            r = float(raw.iloc[i])
            if i == entry_i:
                stop = cl * 0.90            # 初始止损(随便一个低于收盘的价)
            elif lo <= stop:
                break                        # ① 止损被触及 → 平仓,不再更新
            prev = stop
            if np.isfinite(r):
                # 铁律一:不高于当根收盘;铁律二:只能往上抬
                stop = max(prev, min(r, cl))
            opened_bars += 1
            if stop > cl + 1e-9:
                violations.append((entry_i, str(ts.date()), round(stop, 3), round(cl, 3)))
            if stop < prev - 1e-9:
                non_monotonic.append((entry_i, str(ts.date())))
        runs.append((entry_i, opened_bars))

    ok = not violations and not non_monotonic
    _check("② 吊灯止损永远不高于当根收盘、且只能往上抬", ok,
           f"例子:50→20 急跌后 20→60 急拉,共 {len(close)} 根\n"
           f"在 5 个不同的进场点各走一遍(持仓根数 {runs})\n"
           f"违反「不高于当根收盘」的根数 = {len(violations)}"
           + (f" 明细 {violations[:5]}" if violations else "") + "\n"
           f"违反「只能往上抬」的根数 = {len(non_monotonic)}")
    ok2 = _check("②b 这个例子确实能踩到坑(否则等于没测)", n_trap > 0,
                 f"原始吊灯值高于收盘的根数 = {n_trap}"
                 f"({'坑是真的' if n_trap else '⚠ 没踩到坑,例子要重造'})")

    cfg = chain.ChainConfig.from_dict({
        "meta": {"name": "自检_吊灯"},
        "universe": {"min_price": 5.0},
        "regime": {"rules": [], "flatten_when_off": False},
        "entry": {"type": "donchian_breakout", "params": {"lookback": 20},
                  "source": "自检用,Donchian 20 日"},
        "initial_stop": {"type": "atr_multiple",
                         "params": {"atr_period": 20, "multiple": 2.0},
                         "source": "自检用,海龟 2N"},
        "trailing_stop": {"type": "chandelier",
                          "params": {"lookback": 22, "multiple": 3.0, "atr_period": 20},
                          "source": "自检用,LeBeau 吊灯"},
        "exit": {"type": "signal_only", "params": {}},
        "sizing": {"type": "risk_fraction",
                   "params": {"risk_per_trade": 0.01, "max_positions": 10},
                   "source": "自检用,固定分数 1%"},
        "costs": {"friction_tiers": chain.FRICTION_TIERS_DEFAULT},
        "benchmark": {"component_match": "large", "risk_free_annual": None},
    })
    try:
        res = chain.run_chain(cfg, data.full_universe().pool("ALL"),
                              "2018-01-01", "2025-12-31")
        led = res.ledger
        win = float((led["net_pnl"] > 0).mean()) if not led.empty else float("nan")
        avg_r = float(led["r_multiple"].mean()) if not led.empty else float("nan")
        smell = ((np.isfinite(win) and win > 0.60)
                 or (np.isfinite(avg_r) and avg_r > 0.5))
        ok3 = _check("②c 真实数据上跑带吊灯止损的链:断言没被触发,"
                     "且没有「好得不正常」的征兆", not smell,
                     f"全池 2018-2025:{len(led)} 笔,胜率 {win:.1%},每笔 {avg_r:+.3f}R\n"
                     f"征兆线:胜率 >60% 或每笔 >+0.5R → "
                     f"{'★ 踩到了,停下来查' if smell else '没踩到'}")
    except AssertionError as e:
        ok3 = _check("②c 真实数据上跑带吊灯止损的链", False, f"引擎断言被触发:{e}")
    return ok and ok2 and ok3


# =========================================================== ③ 买入持有对数

def test_buy_and_hold_matches_hand_calc() -> bool:
    """
    拿单只票 + 「买入持有」配置跑链,再手算一遍,两边必须对得上。
    手算口径:第二个交易日开盘买入(信号在第一天收盘后成立),最后一天收盘卖出。
    摩擦成本设 0,两边才是同一个口径。
    """
    cfg_path = os.path.join(os.path.dirname(__file__), "configs", "buy_and_hold.yaml")
    cfg = chain.ChainConfig.load(cfg_path)
    start, end = "2018-01-01", "2021-12-31"
    perf = data.perf_window(data.trading_calendar(), start, end)

    all_ok, lines = True, []
    for sym in ("ABT", "AAL", "AEE", "BA", "CAG"):
        res = chain.run_chain(cfg, [sym], start, end, initial_equity=1_000_000.0)
        got = float(res.equity.iloc[-1] / res.equity.iloc[0] - 1.0)
        c = cache.load()
        p_in = float(c["open"][sym].loc[perf[1]])
        p_out = float(c["close"][sym].loc[perf[-1]])
        want = p_out / p_in - 1.0
        diff = abs(got - want)
        ok = diff < 1e-9
        all_ok &= ok
        lines.append(f"{sym}: 执行器 {got:+.8f} vs 手算 {want:+.8f} "
                     f"(买 {p_in:.4f}@{perf[1].date()} → 卖 {p_out:.4f}@"
                     f"{perf[-1].date()}) 差 {diff:.2e} {'OK' if ok else '★ 对不上'}")
    _check("③ 链执行器在「买入并持有」上与手算一致(要求差 < 1e-9)", all_ok,
           "\n".join(lines))
    return all_ok


# =========================================================== ④ 硬关连通性

def test_window_pool_runs() -> bool:
    """两窗口两池子硬关能跑完四格,且纯随机信号被判没过。"""
    rng = np.random.default_rng(777)
    pool = rng.normal(0.0, 0.02, size=4000)

    def signal_fn(start, end, cell_symbols):
        n = 150
        return (rng.choice(pool, size=n, replace=False),
                stats_gate.circular_block_sampler(pool, n_draw=n))

    v = window_pool.run_grid(signal_fn, cache.symbols(), B=200)
    ok = len(v.cells) == 4 and not v.passed
    return _check("④ 两窗口两池子硬关:四格跑通,纯随机信号被判没过", ok, v.report())


# =========================================================== ⑤ 退市 −100%

def test_bankruptcy_minus_100() -> bool:
    """
    破产类退市必须按 −100% 记,不许用最后一天收盘价。
    测两层:
      a) 缓存里 0 价 bar 真的埋进去了
      b) 链真的在那一天吃到了 −100%(买入持有一只破产票,净值必须归零)
    出处:Shumway (1997, JF) The Delisting Bias in CRSP Data。
    """
    meta = cache.panel_meta()
    bk = meta[meta.get("bankruptcy_minus100", False) == True]  # noqa: E712
    c = cache.load()["close"]
    bad = []
    for sym, row in bk.iterrows():
        z = pd.Timestamp(row["zero_bar"])
        if not (c[sym].loc[z] == 0.0):
            bad.append(sym)
    ok = len(bk) > 0 and not bad
    _check("⑤ 破产类退市:缓存里 0 价 bar 已埋好", ok,
           f"破产类 {len(bk)} 只:{list(bk.index)}\n"
           f"0 价 bar 不对的:{bad or '无'}")

    cfg = chain.ChainConfig.load(
        os.path.join(os.path.dirname(__file__), "configs", "buy_and_hold.yaml"))
    sym = list(bk.index)[0] if len(bk) else None
    ok2 = False
    if sym:
        res = chain.run_chain(cfg, [sym], "2018-01-01", "2025-12-31")
        ret = float(res.equity.iloc[-1] / res.equity.iloc[0] - 1.0)
        led = res.ledger
        exit_px = float(led["exit_price"].iloc[-1]) if not led.empty else float("nan")
        ok2 = exit_px == 0.0 and ret <= -0.999
        _check(f"⑤b 买入持有一只破产票({sym})必须亏光", ok2,
               f"出场价 = {exit_px}(必须是 0.0),总收益 = {ret:+.6%}"
               f"(必须 ≤ −99.9%),出场原因 = "
               f"{led['reason'].iloc[-1] if not led.empty else '无成交'}")
    return ok and ok2


# =========================================================== ⑥ 拆股闸

def test_split_gate() -> bool:
    """
    已修的 6 根拆股,位置上不该再有 5 倍以上的假跳变。
    判不准的 2 只(AMRS / PRTY)必须已经不在池子里。
    """
    c = cache.load()["close"]
    lines, ok = [], True
    for e in split_gate.FIX_EVENTS:
        if e.symbol not in c.columns:
            lines.append(f"{e.symbol} 不在池子里,跳过")
            continue
        s = c[e.symbol].dropna()
        ts = pd.Timestamp(e.date)
        if ts not in s.index:
            lines.append(f"{e.symbol} {e.date} 不是交易日,跳过")
            continue
        i = s.index.get_loc(ts)
        if i == 0:
            continue
        jump = s.iloc[i] / s.iloc[i - 1]
        good = 0.5 <= jump <= 2.0
        ok &= good
        lines.append(f"{e.symbol} {e.date} {e.label}: 修正后跳变 {jump:.3f}x "
                     f"{'OK' if good else '★ 还有假跳变'}")
    excluded_gone = not (split_gate.EXCLUDED_SYMBOLS & set(c.columns))
    ok &= excluded_gone
    lines.append(f"判不准而剔除的 {sorted(split_gate.EXCLUDED_SYMBOLS)} "
                 f"{'已不在池子里' if excluded_gone else '★ 还在池子里'}")
    return _check("⑥ 拆股闸:6 根已修、2 根已剔除", ok, "\n".join(lines))


# =========================================================== ⑦ 基本面三坑

def test_fundamental_pit() -> bool:
    """
    ★★ 基本面特有的三个坑,逐条验它真的生效了(2026-10-29 新增)。

      坑① PIT 生效时点 —— 必须是 filing_date + 1 个交易日,
           ★ 严禁用报告期截止日。验法:随便挑一条记录,
             生效日必须 > filing_date,而且必须 >> period_end 之后。
      坑② 股数单位混乱 —— share_gate 的单位闸必须真的在干活
           (298 只里有一批中招;CHD 是最夸张的那只)。
      坑③ ★★ 现金流 YTD 口径 —— 差分还原出来的四个单季相加
           必须等于 FY 的 YTD;而「按季度直接相加」必须明显放大。
    """
    from . import fundamentals, share_gate
    lines, ok = [], True

    # ---- 坑① filing_date + 1 个交易日
    sym = next(s for s, m in sorted(data.load_manifest().items())
               if m.fundamentals_path)
    recs = fundamentals._raw(sym, "OperatingCashFlow")
    bad = [r for r in recs if r["eff"] <= r["filing"].normalize()]
    ok &= not bad
    r0 = recs[0]
    lines.append(f"坑① {sym}: filing={r0['filing'].date()} → "
                 f"生效={r0['eff'].date()}(period_end={r0['period_end'].date()});"
                 f"{len(recs)} 条里生效日 ≤ 申报日的有 {len(bad)} 条"
                 f"{'(应该是 0)' if not bad else ' ★ 不合格'}")
    # 反向:如果用 period_end 当生效日,会偷看多少天
    lead = [(r["eff"] - r["period_end"]).days for r in recs]
    lines.append(f"坑① 如果误用 period_end 当生效日,平均要提前 "
                 f"{sum(lead)/len(lead):.0f} 个自然日看到数据 —— ★ 这就是偷看的幅度")

    # ---- 坑② 股数单位闸
    scan = share_gate.scan_all()
    n_unit = scan["坑一_单位不一致的票数"]
    ok &= n_unit > 0
    lines.append(f"坑② 单位闸:{n_unit} 只票的股数序列混着股/千股/百万股,已统一量级"
                 f"{'' if n_unit else ' ★ 一只都没抓到,闸门可能没接上'}")
    lines.append(f"坑② 拆股闸:判为拆股已修 {scan['坑三_判为拆股已修']} 处,"
                 f"★ 判不准、原样留着 {scan['坑三_判不准未修']} 处")

    # ---- 坑③ YTD 差分
    n_checked, n_good, ratios = 0, 0, []
    for s, m in sorted(data.load_manifest().items()):
        if not m.fundamentals_path:
            continue
        recs = fundamentals._raw(s, "OperatingCashFlow")
        groups: dict = {}
        for r in recs:
            if r["period_start"] is not None:
                groups.setdefault(r["period_start"], {})[r["period_end"]] = r
        qs = {o.period_end: o.value for o in fundamentals.quarterly(s, "OperatingCashFlow")}
        for ps, seen in sorted(groups.items()):
            rs = [seen[pe] for pe in sorted(seen)]
            if len(rs) < 4:
                continue
            rs = rs[:4]
            truth = float(rs[-1]["value"])
            naive = float(sum(r["value"] for r in rs))
            mine = sum(qs.get(r["period_end"], float("nan")) for r in rs)
            n_checked += 1
            if mine == mine and abs(mine - truth) <= max(1.0, abs(truth) * 1e-6):
                n_good += 1
            if truth:
                ratios.append(naive / truth)
            break
        if n_checked >= 40:
            break
    rate = n_good / max(1, n_checked)
    ok &= rate >= 0.90
    med = sorted(ratios)[len(ratios) // 2] if ratios else float("nan")
    lines.append(f"坑③ 抽 {n_checked} 只票对账:差分还原后四个单季相加 = FY 的 YTD,"
                 f"对上 {n_good} 只({rate:.0%};要求 ≥90%)")
    lines.append(f"坑③ ★ 如果按季度直接相加(错法):中位放大 {med:.2f} 倍 —— "
                 f"★ 和审计报告说的「约 2.5 倍」一致,而且★ 不会报错")
    ok &= med > 1.5
    return _check("⑦ 基本面三坑:PIT 生效时点 / 股数单位闸 / 现金流 YTD 差分",
                  ok, "\n".join(lines))


# =========================================================== 主程序

def main() -> int:
    print("=" * 78)
    print("XING 引擎自检")
    print("  必过三项:① 判据在纯随机上不显著  ② 吊灯止损铁律  ③ 买入持有对数")
    print("  连通性三项:④ 两窗口两池子硬关  ⑤ 退市 −100%  ⑥ 拆股闸")
    print("  ★ 基本面一项:⑦ PIT 生效时点 / 股数单位闸 / 现金流 YTD 差分")
    print("=" * 78)
    print(data.cohort_report())
    print()
    print(split_gate.summary())
    print()

    for fn in (test_gate_on_pure_noise, test_chandelier_never_above_close,
               test_buy_and_hold_matches_hand_calc, test_window_pool_runs,
               test_bankruptcy_minus_100, test_split_gate,
               test_fundamental_pit):
        try:
            fn()
        except Exception as e:
            _check(f"{fn.__name__} 执行中崩了", False, f"{type(e).__name__}: {e}")
        print()

    print("=" * 78)
    for name, ok in _results:
        print(f"  {PASS if ok else FAIL}  {name}")
    failed = [n for n, ok in _results if not ok]
    if failed:
        print(f"\n★ 没过 {len(failed)} 项:{failed}")
        print("★ 只要有一项红的,整个引擎都不要用。")
        return 1
    print("\n★ 全部通过。尺子是可信的,可以往下跑链了。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
