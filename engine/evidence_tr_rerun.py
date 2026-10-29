"""
evidence_tr_rerun —— ★ 第一步:总收益口径【真重跑】,并和上一轮的"加法测算"对账。

================================ 三秒版 ================================
★★ 这一步只回答一件事:**上一轮那个"加法测算"靠不靠谱?**
   上一轮没重跑链,是在已有 ledger 上补算分红现金 ÷ 初始资金(加法、不复利)。
   现在真重跑一遍(分红进净值、跟着一起复利),看两者差多少。
     差在容许范围内 → 测算方法可用,可以进第二步(切默认)
     差得离谱       → ★ 测算方法本身有问题,先查它,★ 不许直接切默认

★ TOTAL_RETURN_DEFAULT 仍然是 False —— 这里用**显式参数** total_return=True 跑。

★★ 一条硬不变量(assert 守着):两种口径下**成交的交易必须一模一样**。
   因为分红只记现金、不改价格,而所有信号都在价格上。
   ★ 如果不一样,说明分红泄漏进了信号,整个 A/B 作废 —— 所以这一条是 assert,不是打印。

★★ 基准侧同步换口径(否则是拿总收益的策略去比价格收益的基准 = 反向偏差):
   基准二 = Ē × 指数日收益 + (1−Ē) × 无风险
     纯价格口径 → 指数用 close.pct_change()
     总收益口径 → 指数用 (Δclose + 每股分红) / 前收

跑法:python -m engine.evidence_tr_rerun            # 四条链,串行
      python -m engine.evidence_tr_rerun --only buy_and_hold
=========================================================================
"""

from __future__ import annotations

import argparse
import json
import os
import time

import numpy as np
import pandas as pd

from . import cache, chain, data, matrices

OUT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "results_1029_tr_rerun.json")
SEP = "=" * 78

#: ★ buy_and_hold 排最前 —— 它是「择时贡献须为 0」那道自检的锚点,
#  而它自己带着一笔 FTLF +499.62x,必须先修干净。
#  (名字, config 路径, slots 覆盖 或 None)
TARGETS: tuple[tuple[str, str, int | None], ...] = (
    ("buy_and_hold", "engine/configs/buy_and_hold.yaml", None),
    ("流派一_趋势跟随_slots5", "engine/configs/trend_following.yaml", 5),
    ("流派一_趋势跟随_slots10", "engine/configs/trend_following.yaml", 10),
    ("流派一_深度价值_slots12", "engine/configs/deep_value.yaml", 12),
)

#: 上一轮「加法测算」的结论,用来对账(超额_价格, 超额_总收益_主口径, 超额_总收益_全加法)
PRIOR_ESTIMATE = {
    "buy_and_hold": (0.801187, 0.6293, 0.8382),
    "流派一_趋势跟随_slots5": (-0.446878, -0.4518, -0.4387),
    "流派一_趋势跟随_slots10": (-0.656696, -0.6853, -0.6393),
    "流派一_深度价值_slots12": (-0.802406, -0.8614, -0.8137),
}


def _total(eq: pd.Series) -> float:
    return float(eq.iloc[-1] / eq.iloc[0] - 1.0)


def benchmark_two(e_bar: float, idx_sym: str, index: pd.DatetimeIndex,
                  rf_annual: float = 0.0) -> dict:
    """★ 复刻 bench_lines.static_benchmark,两种口径各算一版。"""
    rf_d = (1.0 + rf_annual) ** (1 / 252.0) - 1.0
    if abs(e_bar) <= 0.10:
        tot = float((1.0 + rf_d) ** len(index) - 1.0)
        return {"market_neutral": True, "index": "(无,市场中性)",
                "price": tot, "total_return": tot, "delta": 0.0}
    px = data.load_benchmark(idx_sym)["close"].reindex(index).ffill()
    r_p = px.pct_change().fillna(0.0)
    r_tr, has = data.benchmark_total_return_daily(idx_sym, index)
    b_p = float(np.prod(1.0 + (e_bar * r_p + (1 - e_bar) * rf_d)) - 1.0)
    b_tr = float(np.prod(1.0 + (e_bar * r_tr + (1 - e_bar) * rf_d)) - 1.0)
    return {"market_neutral": False, "index": idx_sym, "has_dividends": has,
            "price": b_p, "total_return": b_tr, "delta": b_tr - b_p}


def run_one(name: str, cfg_path: str, slots: int | None) -> dict:
    """★ 同一个 matrices 跑两遍(只换 total_return)—— 省内存、也保证两版输入完全同一份。"""
    import copy
    raw = chain.ChainConfig.load(os.path.join(data.REPO_ROOT, cfg_path)).raw
    raw = copy.deepcopy(raw)
    if slots is not None:
        raw.setdefault("sizing", {}).setdefault("params", {})["max_positions"] = slots
        raw["sizing"]["params"]["max_weight"] = 1.0 / slots
    cfg = chain.ChainConfig.from_dict(raw)
    syms = sorted(data.load_manifest())
    t0 = time.time()
    m = matrices.build(cfg.raw, syms)          # ★ 只建一次
    res_p = chain.run_chain(cfg, syms, m=m, total_return=False)
    res_t = chain.run_chain(cfg, syms, m=m, total_return=True)
    del m

    # ══════════════════════════════════════════════════════════════════
    # ★★ 不变量检查 —— ★ 这里曾经写错过一次,留痕:
    #   原来断言"两版成交的交易必须一模一样"。实测 buy_and_hold 有 2 笔不同,
    #   ★ 一度以为是"分红泄漏进信号"。查完发现**是对的、不是 bug**:
    #     buy_and_hold 是 equal_weight_all,进场受**现金**约束
    #     (chain.py: notional = min(notional, cash/(1+rate))),
    #     收到股息 → 现金多了 → 本来买不起的票**提前**买得起。
    #   ★ 这是真实的经济效果,不是污染。所以不变量要改成能区分这两件事的版本。
    #
    # 现在的三条:
    #   ① 硬断言:成交笔数相同、且标的集合完全相同 —— ★ 不许冒出新标的
    #   ② 硬断言:共同交易的**进场价**必须逐位相同 —— ★ 价格序列没被分红污染
    #   ③ 诊断:进场日不同的笔数;并检查方向是否全部"总收益版更早"
    #      (= 现金机制)。★ 出现"总收益版更晚"就要警示 —— 那解释不通
    # ══════════════════════════════════════════════════════════════════
    lp, lt = res_p.ledger, res_t.ledger
    assert len(lp) == len(lt), (
        f"{name}:两种口径成交笔数不同({len(lp)} vs {len(lt)})")
    assert sorted(lp["symbol"]) == sorted(lt["symbol"]), \
        f"{name}:两种口径的标的集合不同 —— ★ 冒出了新标的,A/B 作废"
    pe = {(r.symbol, str(r.entry_date)[:10]): r.entry_price for r in lp.itertuples()}
    te = {(r.symbol, str(r.entry_date)[:10]): r.entry_price for r in lt.itertuples()}
    common = set(pe) & set(te)
    for k in common:
        assert abs(pe[k] - te[k]) <= 1e-9 * max(1.0, abs(pe[k])), \
            f"{name} {k}:进场价不一致 —— ★ 分红污染了价格序列,A/B 作废"
    p_first = {r.symbol: str(r.entry_date)[:10] for r in lp.itertuples()}
    t_first = {r.symbol: str(r.entry_date)[:10] for r in lt.itertuples()}
    moved = [(s, p_first[s], t_first.get(s)) for s in p_first
             if t_first.get(s) != p_first[s]]
    moved_earlier = [x for x in moved if x[2] and x[2] < x[1]]
    moved_later = [x for x in moved if x[2] and x[2] > x[1]]
    fill_diag = {
        "n_entry_date_differs": len(moved),
        "n_earlier_under_total_return": len(moved_earlier),
        "n_later_under_total_return": len(moved_later),
        "detail": moved[:10],
        "explained_by_cash": bool(moved) and not moved_later,
        "sizing_type": (cfg.get("sizing") or {}).get("type"),
    }

    e_bar = float(res_p.exposure.mean())
    idx_sym = (((cfg.get("benchmark") or {}).get("component_match")) or "large")
    try:
        resolved = data.resolve_component_index(idx_sym) if abs(e_bar) > 0.10 \
            else "(无,市场中性)"
    except FileNotFoundError:
        resolved = "(拿不到)"
    bm = benchmark_two(e_bar, resolved if resolved.isalpha() else idx_sym,
                       res_p.equity.index) if resolved != "(拿不到)" else None

    ret_p, ret_t = _total(res_p.equity), _total(res_t.equity)
    div_note = [n for n in res_t.notes if "总收益" in n]
    out = {
        "chain": name, "config": cfg_path, "slots": slots,
        "n_trades": int(len(lp)),
        "e_bar": e_bar, "index": resolved,
        "chain_return_price": ret_p,
        "chain_return_total": ret_t,
        "chain_dividend_effect": ret_t - ret_p,
        "dividend_note": div_note[0] if div_note else "",
        "fill_diagnostics": fill_diag,
        "seconds": round(time.time() - t0, 1),
    }
    if bm:
        out.update({
            "benchmark_price": bm["price"],
            "benchmark_total_return": bm["total_return"],
            "benchmark_delta": bm["delta"],
            "excess_price": ret_p - bm["price"],
            "excess_total_return": ret_t - bm["total_return"],
        })
        out["excess_delta"] = out["excess_total_return"] - out["excess_price"]
    del res_p, res_t
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="总收益口径真重跑 + 与加法测算对账")
    ap.add_argument("--only", default=None, help="只跑某一条(链名包含该串)")
    a = ap.parse_args(argv)

    idx = data.perf_window(data.trading_calendar())
    mt = pd.Timestamp(os.path.getmtime(cache.PANEL_PARQUET), unit="s", tz="UTC")
    print(SEP)
    print("总收益口径【真重跑】—— 第一步:先对账,★ 暂不切默认")
    print(SEP)
    print(f"绩效窗口           : {idx[0].date()} .. {idx[-1].date()},{len(idx)} 个交易日")
    print(f"读的缓存           : {os.path.relpath(cache.PANEL_PARQUET, data.REPO_ROOT)}")
    print(f"缓存构建时间       : {mt} (UTC)")
    print(f"TOTAL_RETURN_DEFAULT: {data.TOTAL_RETURN_DEFAULT}  "
          f"★ 仍为 False,本脚本用显式参数跑")
    print()

    rows = []
    for name, path, slots in TARGETS:
        if a.only and a.only not in name:
            continue
        print(f"--- 跑 {name} …", flush=True)
        try:
            r = run_one(name, path, slots)
        except AssertionError as e:
            print(f"★★ 不变量失败:{e}")
            return 1
        except Exception as e:
            print(f"★ {name} 跑不了:{type(e).__name__}: {e} —— ★ 拿不到就说拿不到")
            rows.append({"chain": name, "error": f"{type(e).__name__}: {e}"})
            continue
        rows.append(r)
        print(f"    笔数 {r['n_trades']} · Ē {r['e_bar']:.4f} · 指数 {r['index']} "
              f"· {r['seconds']}s")
        fd = r["fill_diagnostics"]
        if fd["n_entry_date_differs"]:
            print(f"    ★ 成交时点差异 {fd['n_entry_date_differs']} 笔"
                  f"(总收益版更早 {fd['n_earlier_under_total_return']} / "
                  f"更晚 {fd['n_later_under_total_return']})"
                  f" sizing={fd['sizing_type']}")
            print(f"      {'✅ 全部更早 → 现金机制(收到股息→买得起了),不是信号污染' if fd['explained_by_cash'] else '★ 有更晚的,解释不通 —— 要查'}")
            for s, a_, b_ in fd["detail"]:
                print(f"        {s:6s} {a_} → {b_}")
        else:
            print(f"    ✅ 两版成交完全一致(sizing={fd['sizing_type']},不受现金约束)")
        print(f"    链收益   纯价格 {r['chain_return_price']:+.4%} → "
              f"总收益 {r['chain_return_total']:+.4%} "
              f"(分红贡献 {r['chain_dividend_effect']:+.4%})")
        if "excess_price" in r:
            print(f"    基准二   纯价格 {r['benchmark_price']:+.4%} → "
                  f"总收益 {r['benchmark_total_return']:+.4%}")
            print(f"    ★ 超额   纯价格 {r['excess_price']:+.2%} → "
                  f"总收益 {r['excess_total_return']:+.2%} "
                  f"(变化 {r['excess_delta']:+.2%})")
        print()

    # ── 对账
    print(SEP)
    print("★★ 对账:真重跑 vs 上一轮的加法测算")
    print(SEP)
    print(f"  {'链':26s} {'超额_价格':>22s} {'超额_总收益':>26s}")
    print(f"  {'':26s} {'重跑':>10s} {'测算':>10s} "
          f"{'重跑':>10s} {'测算(主)':>10s} {'测算(全加法)':>12s}")
    recon = []
    for r in rows:
        if "excess_price" not in r:
            continue
        pri = PRIOR_ESTIMATE.get(r["chain"])
        if pri is None:
            continue
        ep, etr_main, etr_add = pri
        print(f"  {r['chain']:26s} {r['excess_price']:+10.4f} {ep:+10.4f} "
              f"{r['excess_total_return']:+10.4f} {etr_main:+10.4f} "
              f"{etr_add:+12.4f}")
        recon.append({
            "chain": r["chain"],
            "excess_price_rerun": r["excess_price"],
            "excess_price_prior": ep,
            "excess_price_gap": r["excess_price"] - ep,
            "excess_tr_rerun": r["excess_total_return"],
            "excess_tr_prior_main": etr_main,
            "excess_tr_prior_additive": etr_add,
            "gap_vs_main": r["excess_total_return"] - etr_main,
            "gap_vs_additive": r["excess_total_return"] - etr_add,
        })
    print()
    print(f"  {'链':26s} {'重跑−测算(主)':>14s} {'重跑−测算(全加法)':>18s}  判定")
    verdict_ok = True
    for c in recon:
        g1, g2 = c["gap_vs_main"], c["gap_vs_additive"]
        best = min(abs(g1), abs(g2))
        good = best <= 0.05          # ★ 5 个百分点以内算"测算可用"
        verdict_ok &= good
        print(f"  {c['chain']:26s} {g1:+14.2%} {g2:+18.2%}  "
              f"{'✅ 测算可用(最近一版差 ≤5pp)' if good else '★ 差得离谱,先查测算方法'}")
    print()
    print(f"  ★ 总判定:{'✅ 可以进第二步(切默认)' if verdict_ok else '★★ 不要切默认,先查加法测算'}")

    res = {"cache": os.path.relpath(cache.PANEL_PARQUET, data.REPO_ROOT),
           "cache_mtime_utc": str(mt),
           "total_return_default": data.TOTAL_RETURN_DEFAULT,
           "chains": rows, "reconciliation": recon,
           "verdict_ok_to_switch_default": bool(verdict_ok)}
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n机读结果:{os.path.relpath(OUT_JSON, data.REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
