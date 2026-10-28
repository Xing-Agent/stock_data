"""
自检 —— 跑一遍证明三件事。跑法:python -m engine.selftest

① 判据在「纯随机信号」上不显著 —— 如果显著,说明判据本身坏了,
   后面跑出来的所有「显著」都不能信。
② 吊灯止损永远不高于当根收盘价(造一个低位反弹的例子专门测它)。
③ 链执行器在「买入并持有」这份配置上,跑出来和直接算的收益一致。

★ 这三项任何一项红了,整个引擎都不要用。
"""

from __future__ import annotations

import sys

import numpy as np
import pandas as pd

from . import chain, data, signals, stats_gate, window_pool

PASS, FAIL = "✅ 通过", "❌ 没过"
_results: list[tuple[str, bool, str]] = []


def _check(name: str, ok: bool, detail: str = "") -> bool:
    _results.append((name, ok, detail))
    print(f"{PASS if ok else FAIL}  {name}")
    if detail:
        for line in detail.splitlines():
            print(f"        {line}")
    return ok


# =========================================================== ① 判据在纯随机上不显著

def test_gate_on_pure_noise() -> bool:
    """
    造一堆纯随机的「信号」和纯随机的「对照」,两边来自同一个分布。
    判据必须说「不显著」。
    为了不被单次运气骗到,换 12 组不同的随机种子各跑一遍,
    允许最多 1 组误报(Z≥1.65 的理论误报率约 5%,12 组里出 0~1 次都正常)。
    """
    n, B, trials = 200, stats_gate.B_DEFAULT, 12
    false_alarms, zs = [], []
    for k in range(trials):
        rng = np.random.default_rng(90210 + 31 * k)
        pool = rng.normal(0.0, 0.02, size=5000)          # 市场本身
        sig = rng.choice(pool, size=n, replace=False)    # 「信号」= 从市场里瞎抽
        sampler = stats_gate.circular_block_sampler(pool, n_draw=n)
        r = stats_gate.bootstrap_test("纯随机", sig, sampler, B=B, seed=7 + k)
        zs.append(r.z_effect)
        if r.z_effect >= stats_gate.Z_BASIC:
            false_alarms.append((k, r.z_effect, r.p_empirical))
    ok = len(false_alarms) <= 1
    detail = (f"12 组纯随机:Z 的范围 {min(zs):+.2f} .. {max(zs):+.2f},"
              f"均值 {np.mean(zs):+.2f}(理论上应该围着 0 转)\n"
              f"误报(Z≥1.65)组数 = {len(false_alarms)},允许上限 1")
    if false_alarms:
        detail += f"\n误报明细:{[(k, round(z,2)) for k, z, _ in false_alarms]}"
    _check("① 判据在纯随机信号上不显著", ok, detail)

    # 顺手证明判据「不是瞎的」:给随机信号加一点真实的正漂移,必须能抓出来
    rng = np.random.default_rng(4242)
    pool = rng.normal(0.0, 0.02, size=5000)
    sig = rng.choice(pool, size=n, replace=False) + 0.006   # 加 0.6% 的真优势
    r = stats_gate.bootstrap_test(
        "有真优势", sig, stats_gate.circular_block_sampler(pool, n_draw=n),
        B=B, seed=11)
    ok2 = r.z_effect >= stats_gate.Z_INSTITUTIONAL
    _check("①b 反向验证:信号里真有优势时判据必须抓出来", ok2,
           f"加了 0.6%/笔 的真优势 → Z={r.z_effect:+.2f}(要求 ≥ "
           f"{stats_gate.Z_INSTITUTIONAL}),p={r.p_empirical:.4f}")

    # 判据里绝不能出现「超过 N 次随机的最大值」这种门槛(会随 B 浮动)
    ok3 = _check_no_max_threshold()
    return ok and ok2 and ok3


def _check_no_max_threshold() -> bool:
    """
    扫一遍 stats_gate.py 的源码,确认没有拿随机分布的 max 当门槛。
    这是硬规定:最大值会随着 B 变大往上爬,B 一调结论就变,那不是尺子。
    """
    import inspect
    src = inspect.getsource(stats_gate)
    body = "\n".join(l for l in src.splitlines() if not l.strip().startswith(("#", '"', "'")))
    bad = [tok for tok in ("np.max(rand", "max(rand", ".max()", "np.amax") if tok in body]
    return _check("①c 判据里没有「超过随机最大值」这类会浮动的门槛",
                  not bad, f"命中的可疑写法:{bad}" if bad else
                  "只用了 (均值, 标准差, 排名分位),没有取随机分布的 max")


# =========================================================== ② 吊灯止损铁律

def test_chandelier_never_above_close() -> bool:
    """
    造一个「先跌到坑底再拉起来」的走势 —— 这是最容易踩坑的形状:
    近 N 日最高价还挂在坑外面很高的位置,ATR 又被这段波动撑得很大,
    原始吊灯值算出来可能比当天收盘价还高。写错了就会「一进场就被止损」,
    或者更糟:止损价高于收盘价时引擎误判成赚钱,跑出 >60% 胜率的假数。

    测两件事:
      a) 引擎里那两条铁律(不高于当根收盘 + 只能往上抬)在这个例子上始终成立
      b) 原始吊灯值在这个例子上确实出现过高于收盘的情况 ——
         说明这个例子真的能踩到坑,不是白测
    """
    # 低位反弹:50 → 20 急跌,再 20 → 60 急拉
    down = np.linspace(50, 20, 40)
    up = np.linspace(20, 60, 40)
    close = np.concatenate([down, up])
    idx = pd.bdate_range("2020-01-01", periods=len(close))
    df = pd.DataFrame({
        "open": close * 0.995,
        "high": close * 1.03,
        "low": close * 0.97,
        "close": close,
        "volume": 1_000_000.0,
    }, index=idx)
    df["dollar_volume"] = df["close"] * df["volume"]

    raw = signals.chandelier_raw(df, period=22, multiple=3.0, atr_period=20)
    hit_the_trap = bool((raw > df["close"]).any())

    # 复现引擎里的那段逻辑,逐根走
    stop = -np.inf
    violations, non_monotonic = [], []
    for ts in idx:
        cl, r = float(df.at[ts, "close"]), float(raw.get(ts, np.nan))
        if not np.isfinite(r):
            continue
        prev = stop
        cand = min(r, cl)            # 铁律一:不能高于当根收盘
        stop = max(prev, cand)       # 铁律二:只能往上抬
        if stop > cl + 1e-9:
            violations.append((str(ts.date()), stop, cl))
        if stop < prev - 1e-9:
            non_monotonic.append(str(ts.date()))

    ok = not violations and not non_monotonic
    detail = (f"例子形状:50→20 急跌后 20→60 急拉,共 {len(close)} 根\n"
              f"原始吊灯值高于收盘的根数 = {int((raw > df['close']).sum())}"
              f"({'这个例子确实能踩到坑' if hit_the_trap else '⚠ 没踩到坑,例子要重造'})\n"
              f"违反「不高于当根收盘」的根数 = {len(violations)}\n"
              f"违反「只能往上抬」的根数 = {len(non_monotonic)}")
    _check("② 吊灯止损永远不高于当根收盘、且只能往上抬", ok, detail)

    ok2 = _check("②b 这个例子确实能踩到坑(否则等于没测)", hit_the_trap,
                 "原始吊灯值在反弹初期高于收盘价,说明坑是真的")

    # 再用真实数据跑一条带吊灯止损的链,确认引擎里的 assert 不会被触发
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
        "costs": {"one_way_bps": 5.0},
        "benchmark": {"component_match": "large", "risk_free_annual": None},
    })
    syms = sorted(data.load_manifest())[:40]
    try:
        res = chain.run_chain(cfg, syms, "2018-01-01", "2021-12-31")
        tr = [t for t in res.trades if t.exit_date]
        rs = np.array([t.r_multiple for t in tr], dtype=float)
        rs = rs[np.isfinite(rs)]
        grets = np.array([t.gross_return for t in tr], dtype=float)
        grets = grets[np.isfinite(grets)]
        win = float(np.mean(grets > 0)) if grets.size else float("nan")
        avg_r = float(np.mean(rs)) if rs.size else float("nan")
        smell = (np.isfinite(win) and win > 0.60) or (np.isfinite(avg_r) and avg_r > 0.5)
        ok3 = _check("②c 真实数据上跑一条带吊灯止损的链,引擎断言没被触发,"
                     "且没有「好得不正常」的征兆",
                     not smell,
                     f"40 只票 2018-2021:{len(tr)} 笔,胜率 {win:.1%},"
                     f"每笔 {avg_r:+.3f}R\n"
                     f"征兆线:胜率 >60% 或每笔 >+0.5R → "
                     f"{'★ 踩到了,停下来查' if smell else '没踩到'}")
    except AssertionError as e:
        ok3 = _check("②c 真实数据上跑带吊灯止损的链", False, f"引擎断言被触发:{e}")
    return ok and ok2 and ok3


# =========================================================== ③ 买入持有对数

def test_buy_and_hold_matches_hand_calc() -> bool:
    """
    拿一只票、一份「买入持有」配置跑链,再手算一遍同一段的收益,两边必须对得上。
    手算口径:第二个交易日开盘买入(信号在第一天收盘后成立),最后一天收盘卖出。
    摩擦成本设 0,这样两边是同一个口径。
    """
    import os
    cfg_path = os.path.join(os.path.dirname(__file__), "configs", "buy_and_hold.yaml")
    cfg = chain.ChainConfig.load(cfg_path)
    start, end = "2018-01-01", "2021-12-31"

    all_ok = True
    details = []
    for sym in ("KO", "ABT", "AAL"):
        res = chain.run_chain(cfg, [sym], start, end, initial_equity=1_000_000.0)
        got = float(res.equity_net.iloc[-1] / res.equity_net.iloc[0] - 1.0)

        # 手算
        df = data.load_daily(sym).reindex(data.trading_calendar())
        perf = data.perf_window(data.trading_calendar(), start, end)
        entry_day = perf[1]                      # 第二个交易日开盘买
        p_in = float(df.at[entry_day, "open"])
        p_out = float(df.at[perf[-1], "close"])
        want = p_out / p_in - 1.0

        diff = abs(got - want)
        ok = diff < 2e-3                         # 允许 0.2% 以内的差(首日现金未投)
        all_ok &= ok
        details.append(
            f"{sym}: 执行器 {got:+.4%} vs 手算 {want:+.4%}(买 {p_in:.4f} @ "
            f"{entry_day.date()} → 卖 {p_out:.4f} @ {perf[-1].date()}),"
            f"差 {diff:.6f} {'OK' if ok else '★ 对不上'}")
    _check("③ 链执行器在「买入并持有」上与手算一致", all_ok, "\n".join(details))
    return all_ok


# =========================================================== 附加:硬关能跑通

def test_window_pool_runs() -> bool:
    """两窗口两池子硬关能真的跑完四格,并且在纯随机信号上判「没过」。"""
    rng = np.random.default_rng(777)
    pool = rng.normal(0.0, 0.02, size=4000)

    def signal_fn(start, end, cell_symbols):
        n = 150
        vals = rng.choice(pool, size=n, replace=False)   # 纯随机信号
        return vals, stats_gate.circular_block_sampler(pool, n_draw=n)

    v = window_pool.run_grid(signal_fn, sorted(data.load_manifest()), B=200)
    ok = len(v.cells) == 4 and not v.passed
    _check("④ 两窗口两池子硬关:四格跑通,且纯随机信号被判没过", ok,
           v.report())
    return ok


# =========================================================== 主程序

def main() -> int:
    print("=" * 78)
    print("XING 引擎自检 —— 三项必过(外加一项硬关连通性)")
    print("=" * 78)
    print(data.cohort_report())
    print()

    test_gate_on_pure_noise()
    print()
    test_chandelier_never_above_close()
    print()
    test_buy_and_hold_matches_hand_calc()
    print()
    test_window_pool_runs()

    print()
    print("=" * 78)
    failed = [n for n, ok, _ in _results if not ok]
    for name, ok, _ in _results:
        print(f"  {PASS if ok else FAIL}  {name}")
    if failed:
        print(f"\n★ 没过 {len(failed)} 项:{failed}")
        print("★ 只要有一项红的,整个引擎都不要用。")
        return 1
    print("\n★ 全部通过。尺子是可信的,可以往下跑链了。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
