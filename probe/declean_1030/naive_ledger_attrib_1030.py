#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
朴素基准(基准五)自己的流水归属 —— 两版并排 · 2026-10-30

为什么要有这个文件(本轮跑出来一个反直觉的数,必须解释清楚才敢写进报告):
  ★ 把断裂清单上的票**整只**剔掉之后,朴素-均值回归基准**没有塌**,
    它从 +450.75% 涨到 +1052.52%。
  ★★ 这和上一轮那份**不含资金约束**的审计(probe/naive_audit_1029)方向相反 ——
     那一份算出「污染票占总收益 96.0%」。两份不矛盾,量的是两个不同的东西:
       · 1029 那一份:**每笔等权**的横截面平均,23,144 笔里一笔
         SQBG +145,942.7% 就能把平均值和「占总收益」整个占住;
       · 本文件 / bench_lines:**10 个槽位 + 现金约束**的净值路径 ——
         一笔 +145,942% 只有在「那天刚好抢到槽」时才吃得到,
         而污染票天天霸占「跌得最深」榜首,把槽位占着的那些
         **未修正向拆股的永久假跌**(买进去不会回来)是净亏的。
  ★ 所以要回答「朴素基准还能不能当基准」,必须看它**自己的流水**:
    污染票在它的净值里是赚的还是亏的、占几成笔数、占几成盈亏。

★ 本文件只跑朴素基准那两条线(各两版),不跑任何策略链;串行单进程。
跑法:python3 probe/declean_1030/naive_ledger_attrib_1030.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

from engine import bench_lines, cache, chain, data, matrices   # noqa: E402

OUT = os.path.join(_HERE, "naive_ledger_attrib_1030.json")


def known_break_symbols() -> set:
    p = os.path.join(_REPO, "engine", "checks", "anchor_health.py")
    spec = importlib.util.spec_from_file_location("ah", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)                                  # type: ignore
    return m.known_break_symbols()


def run_naive(kind: str, syms: list[str], slots: int = 10,
              one_way_bps: float = 5.0) -> chain.ChainResult:
    """★ 和 bench_lines.naive_baseline 同一条路:同样的配置、同样的进场矩阵覆盖。"""
    raw = bench_lines._naive_raw(kind, slots, {"one_way_bps": one_way_bps})
    cfg = chain.ChainConfig(raw)
    m = matrices.build(raw, syms)
    entry, score = bench_lines._naive_entry_and_rank(kind, list(m.symbols))
    block, jumps = bench_lines.residual_jump_blackout(
        list(m.symbols), entry.index, bench_lines.NAIVE_HOLD_DAYS[kind])
    entry = entry & ~block                 # ★ 单根 bar 剔除那一档照样开着
    m.entry = entry.reindex(index=m.index, columns=m.symbols).to_numpy(dtype=bool)
    m.rank_score = score.reindex(index=m.index,
                                 columns=m.symbols).to_numpy(dtype=float)
    return chain.run_chain(cfg, syms, m=m), len(jumps)


def attrib(res, known: set) -> dict:
    led = res.ledger
    eq = res.equity
    bad = led["symbol"].astype(str).isin(known)
    pnl = led["net_pnl"].astype(float)
    gr = led["gross_return"].astype(float)
    pos = pnl[pnl > 0].sum()
    wins = sorted(pnl[pnl > 0].tolist(), reverse=True)
    top = led.assign(bad_flag=bad).sort_values("gross_return",
                                               ascending=False).head(5)
    return {
        "总收益": float(eq.iloc[-1] / eq.iloc[0] - 1.0),
        "笔数": int(len(led)),
        "污染票笔数": int(bad.sum()),
        "污染票笔数占比": float(bad.mean()) if len(led) else None,
        "★污染票净盈亏": float(pnl[bad].sum()),
        "★干净票净盈亏": float(pnl[~bad].sum()),
        "全部净盈亏": float(pnl.sum()),
        "★污染票占净盈亏": (float(pnl[bad].sum() / pnl.sum())
                           if pnl.sum() else None),
        "污染票占总盈利(只数正的)": (float(pnl[bad & (pnl > 0)].sum() / pos)
                                   if pos > 0 else None),
        "污染票平均每笔毛收益率": (float(gr[bad].mean()) if bad.any() else None),
        "干净票平均每笔毛收益率": (float(gr[~bad].mean()) if (~bad).any() else None),
        "前10笔占总盈利": (sum(wins[:10]) / sum(wins)) if wins else None,
        "最大五笔": [{"symbol": str(r.symbol), "毛收益率": float(r.gross_return),
                      "净盈亏": float(r.net_pnl),
                      "在断裂清单上": bool(r.bad_flag)}
                     for r in top.itertuples()],
    }


def main() -> int:
    known = known_break_symbols()
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    clean = [s for s in syms if s not in known]
    out: dict = {"池子": {"污染版": len(syms), "剔除版": len(clean),
                          "剔掉": sorted(set(syms) & known)}}
    for kind in (bench_lines.NAIVE_MEANREV, bench_lines.NAIVE_RSI2):
        out[kind] = {}
        for tag, pool in (("污染版", syms), ("剔除版", clean)):
            res, njumps = run_naive(kind, pool)
            a = attrib(res, known)
            a["单根bar剔除_残余跳变根数"] = njumps
            out[kind][tag] = a
            print(f"{kind} {tag}:总收益 {a['总收益']:+.2%} | {a['笔数']} 笔 | "
                  f"污染票 {a['污染票笔数']} 笔"
                  f"({(a['污染票笔数占比'] or 0):.1%})| "
                  f"污染票净盈亏 {a['★污染票净盈亏']:+,.0f} | "
                  f"占净盈亏 {a['★污染票占净盈亏']}")
            print(f"    最大五笔:{a['最大五笔']}")
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n写好 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
