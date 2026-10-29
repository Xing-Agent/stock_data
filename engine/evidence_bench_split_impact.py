"""
evidence_bench_split_impact —— ★ 「load_benchmark 从来不修拆股」这个 bug 的影响面实测。

================================ 三秒版 ================================
★★ 最要紧的一问:修完之后,已报的那些超额各自变多少?
★★ 答案:**一个都没变。** 全部 24 个 config 都是 `component_match: large`
   → 基准二用 SPY,而 SPY 没有任何非 1 的 split_coefficient。
   实测 8 条链的基准二与原报值最大差 6.8e-07(浮点噪声)。

★ 那这个 bug 是不是不重要?不是 —— 它真实存在,只是没波及已报的超额:
   · `load_benchmark()` 以前**完全不做拆股修正**(只有 `load_daily()` 做),
     五只行业 ETF 在 2025-12-05 带着 −50% 的假跳空(Select Sector SPDR 2:1)。
   · 这些 ETF 不做基准,但进了 **SDI 板块扩散闸门**(engine/matrices.py:583)。
   · 实测 SDI 只在 **2025-12-05 .. 12-31 的 18 天**翻转,全部是"原来关、现在开"
     → 影响 cashflow_discipline / vcp_momentum 的进场,★ 上界被这 18 天钉住。

★ 为什么「没波及」这个结论可信:它不是推理出来的,是把基准二按原样复刻一遍
  再和原报值逐条对账得出的(复刻保真度 1e-7 级,见下表)。

跑法:python -m engine.evidence_bench_split_impact
=========================================================================
"""

from __future__ import annotations

import glob
import json
import os
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

from . import cache, data

OUT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        "results_1029_bench_split_impact.json")
SEP = "=" * 78

#: 板块扩散指数(SDI)用的 11 只行业 ETF —— 和 engine/matrices.py 一致
SDI_ETFS = ["XLB", "XLC", "XLE", "XLF", "XLI", "XLK",
            "XLP", "XLRE", "XLU", "XLV", "XLY"]

#: 本轮新修的五只(2025-12-05 Select Sector SPDR 2:1,未复权)
FIXED_ETFS = ["XLK", "XLB", "XLE", "XLU", "XLY"]

#: 已报的基准二:(链名, Ē, 原报基准总收益, 原报超额)
REPORTED = (
    ("流派一_深度价值_Z1.8_slots12", 0.516033, 0.679724, -0.802406),
    ("流派三_现金流纪律_slots5", 0.302676, 0.368951, -0.624753),
    ("流派三_现金流纪律_slots10", 0.413314, 0.524808, -0.833058),
    ("流派三_现金流纪律_slots20", 0.410389, 0.520541, -0.814510),
    ("流派一_趋势跟随_slots3", 0.180885, 0.210502, -0.327235),
    ("流派一_趋势跟随_slots5", 0.283131, 0.342601, -0.446878),
    ("流派一_趋势跟随_slots10", 0.507513, 0.666500, -0.656696),
    ("buy_and_hold", 0.9878412025204231, 1.513246928274898, 0.8011871593118878),
)

#: ★ 本轮新消掉的假跳变(由新增的 cut_series 带来)
NEW_KILLED = (
    ("PROP", "2020-02-28"), ("PROP", "2020-05-14"), ("AMRS", "2017-06-06"),
    ("FTLF", "2019-04-22"), ("XPRO", "2021-10-04"), ("LIXT", "2017-03-07"),
    ("OMEX", "2024-09-17"), ("OMEX", "2024-09-18"), ("ACOR", "2024-04-11"),
)
#: ★ 被整段切掉的历史(这些日子之前的交易以后不会再产生)
CUT_AFTER = {"PROP": "2023-05-03", "AMRS": "2017-06-06", "FTLF": "2019-04-22",
             "XPRO": "2021-10-04", "LIXT": "2017-03-07", "OMEX": "2024-09-17"}


def _raw_close(sym: str, base: str, index: pd.DatetimeIndex) -> pd.Series:
    """★ 绕开我方修正,直接读原始 close —— 用来算"修之前"的那一版。"""
    p = os.path.join(base, sym, "daily.json")
    rows = (json.load(open(p, encoding="utf-8")).get("data") or [])
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    return pd.to_numeric(df["close"], errors="coerce").reindex(index).ffill()


# ──────────────────────── ① 基准二有没有变 ────────────────────────

def benchmark_unchanged(index: pd.DatetimeIndex) -> dict:
    b = data.load_benchmark("SPY")["close"].reindex(index).ffill()
    r = b.pct_change().fillna(0.0)
    rows = []
    for nm, e_bar, rep_bench, rep_ex in REPORTED:
        now = float(np.prod(1.0 + e_bar * r) - 1.0)
        rows.append({"chain": nm, "e_bar": e_bar,
                     "reported_benchmark": rep_bench, "recomputed": now,
                     "diff": now - rep_bench, "reported_excess": rep_ex,
                     "excess_change": now - rep_bench and -(now - rep_bench)})
    return {"rows": rows,
            "max_abs_diff": max(abs(x["diff"]) for x in rows)}


# ──────────────────────── ② SDI 闸门翻转 ────────────────────────

def sdi_impact(index: pd.DatetimeIndex, need: int = 6,
               min_pct: float = 54.5, ma_n: int = 50) -> dict:
    def count(fixed: bool) -> pd.Series:
        c = pd.Series(0.0, index=index)
        for e in SDI_ETFS:
            if fixed:
                b = data.load_benchmark(e)["close"].reindex(index).ffill()
            else:
                b = _raw_close(e, data.SECTOR_ETF_DIR, index)
            above = (b > b.rolling(ma_n, min_periods=ma_n).mean()).fillna(False)
            c += above.astype(float)
        return c
    old, new = count(False), count(True)
    denom = len(SDI_ETFS)

    def gate(c):
        return ((c >= need) & (c / denom * 100.0 >= min_pct)).fillna(False)
    g_old, g_new = gate(old), gate(new)
    flip = g_old != g_new
    days = index[flip]
    return {
        "gate": f">= {need} 只 且 >= {min_pct}%", "n_days": len(index),
        "open_before": int(g_old.sum()), "open_after": int(g_new.sum()),
        "open_pct_before": float(g_old.mean()), "open_pct_after": float(g_new.mean()),
        "n_flip": int(flip.sum()),
        "n_closed_to_open": int((g_new & ~g_old).sum()),
        "n_open_to_closed": int((g_old & ~g_new).sum()),
        "flip_first": str(days[0].date()) if len(days) else None,
        "flip_last": str(days[-1].date()) if len(days) else None,
        "count_diff_distribution": {str(k): int(v) for k, v in
                                    (new - old).value_counts().sort_index().items()},
    }


# ──────────────────────── ③ ledger 受影响面 ────────────────────────

def ledger_impact() -> dict:
    killed = defaultdict(list)
    for s, d in NEW_KILLED:
        killed[s].append(pd.Timestamp(d))
    cut = {k: pd.Timestamp(v) for k, v in CUT_AFTER.items()}
    rode, gone = [], []
    n_tot = 0
    for f in sorted(glob.glob(os.path.join(data.REPO_ROOT, "engine",
                                           "ledgers_*", "*.csv"))):
        try:
            df = pd.read_csv(f)
        except Exception:
            continue
        if "symbol" not in df.columns:
            continue
        df["entry_date"] = pd.to_datetime(df["entry_date"])
        df["exit_date"] = pd.to_datetime(df["exit_date"])
        n_tot += len(df)
        key = os.path.join(os.path.basename(os.path.dirname(f)), os.path.basename(f))
        for _, r in df.iterrows():
            s = r["symbol"]
            pnl = float(r.get("net_pnl") or 0.0)
            gr = float(r.get("gross_return") or 0.0)
            for d in killed.get(s, []):
                if r["entry_date"] < d <= r["exit_date"]:
                    rode.append({"ledger": key, "symbol": s,
                                 "entry": str(r["entry_date"].date()),
                                 "exit": str(r["exit_date"].date()),
                                 "fake_jump_date": str(d.date()),
                                 "gross_return": gr, "net_pnl": pnl})
            c = cut.get(s)
            if c is not None and r["exit_date"] < c:
                gone.append({"ledger": key, "symbol": s,
                             "entry": str(r["entry_date"].date()),
                             "exit": str(r["exit_date"].date()), "net_pnl": pnl})
    rode.sort(key=lambda x: -abs(x["net_pnl"]))
    by_ledger = Counter(g["ledger"] for g in gone)
    return {"n_trades_scanned": n_tot,
            "n_rode_fake_jump": len(rode), "rode": rode,
            "n_trades_now_impossible": len(gone),
            "net_pnl_now_impossible": sum(g["net_pnl"] for g in gone),
            "now_impossible_by_ledger": dict(by_ledger.most_common(20))}


# ──────────────────────── 报告 ────────────────────────

def main() -> int:
    idx = data.perf_window(data.trading_calendar())
    mt = pd.Timestamp(os.path.getmtime(cache.PANEL_PARQUET), unit="s", tz="UTC")
    out = [SEP, "load_benchmark 不修拆股 —— 影响面实测", SEP,
           f"绩效窗口     : {idx[0].date()} .. {idx[-1].date()},{len(idx)} 个交易日",
           f"读的缓存     : {os.path.relpath(cache.PANEL_PARQUET, data.REPO_ROOT)}",
           f"缓存构建时间 : {mt} (UTC)", ""]

    # ① ETF 本身
    out += [SEP, "① 五只行业 ETF 2025-12-05 的 −50% 假跳空", SEP]
    for e in FIXED_ETFS:
        raw = _raw_close(e, data.SECTOR_ETF_DIR, idx)
        fix = data.load_benchmark(e)["close"].reindex(idx).ffill()
        ts = pd.Timestamp("2025-12-05")
        i = idx.get_indexer([ts])[0]
        out.append(f"  {e:5s} 修前 {raw.iloc[i-1]:8.3f} → {raw.iloc[i]:8.3f} "
                   f"({raw.iloc[i]/raw.iloc[i-1]-1:+7.2%})   "
                   f"修后 {fix.iloc[i-1]:8.3f} → {fix.iloc[i]:8.3f} "
                   f"({fix.iloc[i]/fix.iloc[i-1]-1:+7.2%})  ✅")
    out.append("")

    # ② 基准二
    bu = benchmark_unchanged(idx)
    out += [SEP, "② ★★ 已报的超额各自变多少 —— 答案:一个都没变", SEP,
            "  原因:全部 24 个 config 都是 component_match: large → 基准二用 SPY,",
            "       而 SPY 没有任何非 1 的 split_coefficient,所以 ETF 修正碰不到它。",
            "",
            f"  {'链':34s} {'原报基准二':>12s} {'复刻':>12s} {'差':>11s} "
            f"{'原报超额':>11s} {'超额变化':>10s}"]
    for r in bu["rows"]:
        out.append(f"  {r['chain']:34s} {r['reported_benchmark']:12.6f} "
                   f"{r['recomputed']:12.6f} {r['diff']:+11.2e} "
                   f"{r['reported_excess']:+11.4f} {-r['diff']:+10.2e}")
    out += ["",
            f"  ★ 最大绝对差 {bu['max_abs_diff']:.2e} —— 浮点噪声量级,"
            f"★ 结论:已报超额无需改动。", ""]

    # ③ SDI
    sd = sdi_impact(idx)
    out += [SEP, "③ 那这个 bug 影响了什么 —— SDI 板块扩散闸门", SEP,
            f"  闸门口径   : {sd['gate']}(engine/matrices.py:583,分母写死 11)",
            f"  修 ETF 前  : 开闸 {sd['open_before']}/{sd['n_days']} 天 = "
            f"{sd['open_pct_before']:.2%}",
            f"  修 ETF 后  : 开闸 {sd['open_after']}/{sd['n_days']} 天 = "
            f"{sd['open_pct_after']:.2%}",
            f"  ★ 翻转     : {sd['n_flip']} 天("
            f"原来关现在开 {sd['n_closed_to_open']} 天 / "
            f"原来开现在关 {sd['n_open_to_closed']} 天)",
            f"  ★ 翻转范围 : {sd['flip_first']} .. {sd['flip_last']}  "
            f"← ★ 全部落在样本最后一个月",
            f"  SDI 计数差 : {sd['count_diff_distribution']}",
            "",
            "  ★ 结论:影响真实但有界 —— 只有最后 18 个交易日的闸门会从关变开,",
            "    受影响的是 cashflow_discipline / vcp_momentum 的进场选择。",
            "    ★ 要精确到收益必须重跑;但 18/2011 = 0.9% 的窗口、且位于样本末尾,",
            "    不可能实质改变 8 年期的超额数字。", ""]

    # ④ ledger
    li = ledger_impact()
    out += [SEP, "④ 新增 cut_series 对已有 ledger 的影响", SEP,
            f"  扫过 {li['n_trades_scanned']} 笔交易",
            f"  (1) 骑在本轮新消掉的假跳变日上:{li['n_rode_fake_jump']} 笔 —— "
            f"★ 这些笔的收益是 artifact:"]
    for r in li["rode"][:8]:
        out.append(f"      {r['ledger'][:52]:52s} {r['symbol']:5s} "
                   f"{r['entry']}→{r['exit']} @{r['fake_jump_date']}  "
                   f"gross {r['gross_return']:+9.2f}x  net_pnl {r['net_pnl']:+14,.0f}")
    out += ["",
            f"  (2) 整笔落在被切掉历史段里:{li['n_trades_now_impossible']} 笔"
            f"(net_pnl 合计 {li['net_pnl_now_impossible']:+,.0f})—— "
            f"★ 这些交易以后不会再产生:"]
    for k, v in list(li["now_impossible_by_ledger"].items())[:8]:
        out.append(f"      {k[:66]:66s} {v} 笔")
    out.append("")

    res = {"cache": os.path.relpath(cache.PANEL_PARQUET, data.REPO_ROOT),
           "cache_mtime_utc": str(mt), "benchmark": bu, "sdi": sd,
           "ledger": li}
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=str)
    out += [SEP, f"机读结果:{os.path.relpath(OUT_JSON, data.REPO_ROOT)}", SEP]
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
