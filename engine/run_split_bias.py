"""
★ 一份错的拆股清单,到底能把结果带偏多少?—— 2026-10-29

════════════════════════════════════════════════════════════════════════
★ 大白话(三秒版)
════════════════════════════════════════════════════════════════════════
同一条链(流派一 趋势跟随,样本最多),用三套「脏活口径」各跑一遍,
★ 除了口径,其他一个字都不改。看笔数 / 每笔 R / 总收益 / 最大回撤 /
两窗口两池子硬关的四格 Z 差多少。

  A 旧版   = 我们那份错的 8 条拆股清单 + 旧的「破产类一律 −100%」
             ★ 这是 1028 之前所有结果用的口径
  B 只换拆股闸 = 技术核实后的拆股闸 + ★ 旧的退市口径不动
             ★ A→B 的差,★ 就是「用错清单」这一件事造成的偏差,
               不掺退市口径的影响 —— 这是 Lin 问的那个问题的答案
  C 新版   = 技术核实后的拆股闸 + 技术核实后的退市结算价
             ★ B→C 的差是退市结算口径换代的影响,单独报

跑法:python -m engine.run_split_bias
"""

from __future__ import annotations

import json
import os
import time

import numpy as np
import pandas as pd
import yaml

from . import (analyze, cache, chain, data, delisting_gate, matrices,
               split_gate, stats_gate, window_pool)

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(HERE, "configs")
OUT_JSON = os.path.join(HERE, "results_1029_拆股清单偏差.json")
LEDGER_DIR = os.path.join(HERE, "ledgers_1029_拆股偏差")

CHAIN_YAML = "trend_following.yaml"     # ★ 样本最多的那条
SLOTS = 10                              # ★ 固定一档,免得把敏感度混进来当差异


# ═══════════════════════════════ 旧口径(从 git 历史取回) ═══════════════════════════════
# ★ 这就是 commit 65f6b81 之前 engine/split_gate.py 里那 8 条,一字不改地搬过来。
#   ratio = 事件当天价格 / 前一天价格 的理论值。

_OLD = split_gate.SplitEvent
OLD_FIX_EVENTS = (
    _OLD("ACOR", "2021-11-30", "ratio_fix", ratio=10.0, label="10合1(★ 错)"),
    _OLD("ACOR", "2023-06-05", "ratio_fix", ratio=20.0, label="20合1(✅ 对)"),
    _OLD("PROP", "2020-05-14", "ratio_fix", ratio=4.0, label="4合1(★ 不是拆股)"),
    _OLD("SQBG", "2020-07-27", "ratio_fix", ratio=1200.0, label="1200合1(★ 错,实际 1合40)"),
    _OLD("UHAL", "2022-11-10", "ratio_fix", ratio=0.1, label="1拆10(★ 不是拆股)"),
    _OLD("WPG", "2020-12-22", "ratio_fix", ratio=8.0, label="8合1(★ 错,实际 1合9)"),
)
# ★ 旧版把这两只整只剔了 —— AMRS 还是破产股,是样本里最该留的那一类
OLD_EXCLUDED = frozenset({"AMRS", "PRTY"})


def _old_forced_price(symbol: str) -> float | None:
    """旧的退市口径:retirement_category 属于破产 / 实质破产类 → 一律 0.0。"""
    try:
        m = data.load_manifest()[symbol]
    except KeyError:
        return None
    return 0.0 if (m.delisted and m.is_bankruptcy) else None


# ═══════════════════════════════ 口径切换 ═══════════════════════════════

REGIMES = {
    "A_旧版_错清单+旧退市口径": dict(old_split=True, old_delist=True),
    "B_只换拆股闸_退市口径不动": dict(old_split=False, old_delist=True),
    "C_新版_拆股闸+退市结算价都换": dict(old_split=False, old_delist=False),
}

_NEW_FIX = split_gate.FIX_EVENTS
_NEW_CUT = split_gate.CUT_EVENTS
_NEW_EXCL = split_gate.EXCLUDED_SYMBOLS
_NEW_FORCED = delisting_gate.forced_price


def _apply_regime(name: str, old_split: bool, old_delist: bool) -> None:
    """把全局口径切到某一版,★ 并把所有缓存清干净(不清就会串味)。"""
    if old_split:
        split_gate.FIX_EVENTS = OLD_FIX_EVENTS
        split_gate.CUT_EVENTS = ()
        split_gate.EXCLUDED_SYMBOLS = OLD_EXCLUDED
    else:
        split_gate.FIX_EVENTS = _NEW_FIX
        split_gate.CUT_EVENTS = _NEW_CUT
        split_gate.EXCLUDED_SYMBOLS = _NEW_EXCL

    delisting_gate.forced_price = _old_forced_price if old_delist else _NEW_FORCED

    # ★ 缓存全清 —— 这几个 lru_cache 不清,换了口径也读的是上一版的数
    data.load_manifest.cache_clear()
    data.load_daily.cache_clear()
    data.price_panel.cache_clear()
    delisting_gate.load.cache_clear()
    matrices._VCP_CACHE.clear()
    cache._PANEL = None
    tag = name.split("_")[0]
    cache.PANEL_PARQUET = os.path.join(cache.CACHE_DIR, f"bias_{tag}_panel.parquet")
    cache.META_PARQUET = os.path.join(cache.CACHE_DIR, f"bias_{tag}_meta.parquet")
    cache.build(verbose=False)
    cache._PANEL = None          # 强制从刚烤好的 parquet 读回来


def _restore() -> None:
    _apply_regime("C_新版_拆股闸+退市结算价都换", old_split=False, old_delist=False)
    cache.PANEL_PARQUET = os.path.join(cache.CACHE_DIR, "ohlcv_panel.parquet")
    cache.META_PARQUET = os.path.join(cache.CACHE_DIR, "panel_meta.parquet")
    cache._PANEL = None


# ═══════════════════════════════ 跑一版 ═══════════════════════════════

def _cfg() -> chain.ChainConfig:
    with open(os.path.join(CONFIG_DIR, CHAIN_YAML), encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    raw["slots"] = SLOTS
    raw["source_slots"] = f"固定 slots={SLOTS} —— ★ 只为让三版可比,不是挑最优"
    return chain.ChainConfig.from_dict(raw)


def _four_cell(cfg: chain.ChainConfig, syms: list[str],
               B: int = 200) -> window_pool.WindowPoolVerdict:
    """两窗口两池子硬关的四格。★ 对照必须在同格内取样。"""
    def signal_fn(start, end, cell_symbols):
        cs = [s for s in cell_symbols if s in cache.symbols()]
        try:
            r = chain.run_chain(cfg, cs, start, end)
            vals = r.ledger["r_multiple"].dropna().to_numpy(float)
        except Exception:
            vals = np.array([])
        if vals.size == 0:
            return [], (lambda rng: np.array([np.nan]))
        rate = max(1e-7, min(1.0, vals.size / max(1, len(r.equity) * len(cs))))
        c2 = cfg.copy_with(entry={"type": "random",
                                  "params": {"rate": rate, "seed": 20181001},
                                  "source": "同格内随机进场对照"})
        try:
            ctrl = chain.run_chain(c2, cs, start, end
                                   ).ledger["r_multiple"].dropna().to_numpy(float)
        except Exception:
            ctrl = np.array([])
        if ctrl.size == 0:
            ctrl = vals
        return list(vals), stats_gate.circular_block_sampler(ctrl, n_draw=vals.size)

    return window_pool.run_grid(signal_fn, syms, B=B)


def run_regime(name: str, flags: dict) -> dict:
    t0 = time.time()
    print("=" * 78)
    print(f"★ 跑口径:{name}")
    _apply_regime(name, **flags)
    syms = cache.symbols()
    cfg = _cfg()
    res = chain.run_chain(cfg, syms)
    led = res.ledger
    mdd, uw, trough = analyze.drawdown(res.equity)

    r = led["r_multiple"].dropna().to_numpy(float)
    rn = led["r_multiple_net"].dropna().to_numpy(float)
    tot = float(res.equity.iloc[-1] / res.equity.iloc[0] - 1.0)

    print(f"  池子 {len(syms)} 只 / 笔数 {len(led)} / 总收益 {tot:+.2%} / "
          f"最大回撤 {mdd:.2%} / 每笔R(净) {np.mean(rn) if rn.size else float('nan'):+.3f}")

    v = _four_cell(cfg, syms)
    print(f"  四格硬关:{'过' if v.passed else '没过'} | "
          + " | ".join(f"{c.key} Z={c.result.z_effect:+.2f}(n={c.result.n_signal})"
                       for c in v.cells))

    os.makedirs(LEDGER_DIR, exist_ok=True)
    led.to_csv(os.path.join(LEDGER_DIR, f"{name}.csv"), index=False,
               encoding="utf-8-sig")

    # ★ 被改动的那 9 只票各贡献了多少笔、多少钱 —— 差异要能指到具体的票
    touched = sorted({e.symbol for e in split_gate.EVENTS} | {"AMRS", "PRTY"})
    per_sym = {}
    for s in touched:
        sub = led[led["symbol"] == s]
        per_sym[s] = {"笔数": int(len(sub)),
                      "净盈亏": round(float(sub["net_pnl"].sum()), 2) if len(sub) else 0.0,
                      "平均R(净)": (round(float(sub["r_multiple_net"].mean()), 4)
                                    if len(sub) else None)}

    # ★ 「证据拿不到只能用最后收盘价」的 14 只贡献了多少 —— Lin 点名要单独统计
    m = cache.panel_meta()
    fb = list(m[m.get("settlement_fallback_last_close", False) == True].index)  # noqa: E712
    fb_led = led[led["symbol"].isin(fb)]
    zero_syms = list(m[m.get("bankruptcy_minus100", False) == True].index)      # noqa: E712
    z_led = led[led["symbol"].isin(zero_syms)]

    return {
        "口径": name,
        "池子只数": len(syms),
        "笔数": int(len(led)),
        "总收益": round(tot, 6),
        "最大回撤": round(float(mdd), 6),
        "最长水下天数": int(uw),
        "每笔R_价格口径": round(float(np.mean(r)), 4) if r.size else None,
        "每笔R_扣摩擦": round(float(np.mean(rn)), 4) if rn.size else None,
        "每笔R中位_扣摩擦": round(float(np.median(rn)), 4) if rn.size else None,
        "胜率": round(float((rn > 0).mean()), 4) if rn.size else None,
        "四格硬关通过": bool(v.passed),
        "四格": [{"格": c.key, "n": int(c.result.n_signal),
                  "Z": round(float(c.result.z_effect), 4),
                  "p": round(float(c.result.p_empirical), 4),
                  "差值": round(float(c.result.diff), 4)} for c in v.cells],
        "四格Z最小": round(min(float(c.result.z_effect) for c in v.cells), 4),
        "被改动的9只票各自贡献": per_sym,
        "退市结算_证据拿不到的票": {
            "只数": len(fb), "名单": fb, "笔数": int(len(fb_led)),
            "净盈亏": round(float(fb_led["net_pnl"].sum()), 2) if len(fb_led) else 0.0,
        },
        "退市结算_记0的票": {
            "只数": len(zero_syms), "名单": zero_syms, "笔数": int(len(z_led)),
            "净盈亏": round(float(z_led["net_pnl"].sum()), 2) if len(z_led) else 0.0,
        },
        "用时秒": round(time.time() - t0, 1),
    }


# ═══════════════════════════════ 主程序 ═══════════════════════════════

def main(argv=None) -> int:
    print("=" * 78)
    print("★ 一份错的拆股清单,到底能把结果带偏多少?")
    print(f"  链:{CHAIN_YAML}(slots={SLOTS},固定)  绩效窗口:"
          f"{data.PERF_START}..{data.PERF_END}")
    print("=" * 78)

    out = {"生成时间": "2026-10-29", "链": CHAIN_YAML, "slots": SLOTS, "口径": []}
    try:
        for name, flags in REGIMES.items():
            out["口径"].append(run_regime(name, flags))
            print()
    finally:
        _restore()

    a, b, c = out["口径"]

    def d(x, y, k, pct=False):
        if x[k] is None or y[k] is None:
            return None
        v = y[k] - x[k]
        return round(v, 6)

    out["A到B_只换拆股闸的影响"] = {k: d(a, b, k) for k in
                                    ("笔数", "总收益", "最大回撤", "每笔R_扣摩擦",
                                     "胜率", "四格Z最小")}
    out["B到C_只换退市结算口径的影响"] = {k: d(b, c, k) for k in
                                          ("笔数", "总收益", "最大回撤", "每笔R_扣摩擦",
                                           "胜率", "四格Z最小")}
    out["A到C_两件一起换"] = {k: d(a, c, k) for k in
                              ("笔数", "总收益", "最大回撤", "每笔R_扣摩擦",
                               "胜率", "四格Z最小")}
    out["结论_会不会得出不同结论"] = {
        "四格硬关": f"A {'过' if a['四格硬关通过'] else '没过'} → "
                    f"B {'过' if b['四格硬关通过'] else '没过'} → "
                    f"C {'过' if c['四格硬关通过'] else '没过'}",
        "判据是否翻转": bool(a["四格硬关通过"] != c["四格硬关通过"]),
    }

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)

    print("=" * 78)
    print("★ 三版对照")
    print("=" * 78)
    hdr = f"{'口径':38s} {'池子':>4s} {'笔数':>5s} {'总收益':>9s} {'最大回撤':>9s} {'每笔R净':>8s} {'硬关':>5s} {'Z最小':>7s}"
    print(hdr)
    for x in out["口径"]:
        print(f"{x['口径']:38s} {x['池子只数']:>4d} {x['笔数']:>5d} "
              f"{x['总收益']:>+9.2%} {x['最大回撤']:>9.2%} "
              f"{x['每笔R_扣摩擦'] if x['每笔R_扣摩擦'] is not None else float('nan'):>+8.3f} "
              f"{'过' if x['四格硬关通过'] else '没过':>5s} {x['四格Z最小']:>+7.2f}")
    print()
    print(f"★ A→B(只换拆股闸):{out['A到B_只换拆股闸的影响']}")
    print(f"★ B→C(只换退市口径):{out['B到C_只换退市结算口径的影响']}")
    print(f"★ 判据有没有翻转:{out['结论_会不会得出不同结论']}")
    print()
    print(f"原始数字写在 {OUT_JSON}")
    print(f"交易流水写在 {LEDGER_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
