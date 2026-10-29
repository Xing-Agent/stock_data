#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查:「已剔除假跳变」这句话到底剔掉了多少 · 2026-10-29 晚

为什么要有这个文件(真实案例,当晚发现):
  朴素基准(基准五)报出 +450.75%,被当成「15 条链没有一条打得过它」的依据。
  ★ 而自己重算发现:它 96.0% 的收益来自 24 只在「已知数据断裂清单」上的票,
    最大单笔 SQBG +145,942.7%(2020-07 反向拆股)。

  ★★ bench_lines 其实**做了**剔除,所以当时没人怀疑。问题在剔的是什么:
     剔的是 split_gate.residual_jumps(3.0) —— ★ 那是「单根 bar」级别的清单,
     实测只有 10 根、涉及 8 只票;
     而污染是 ★「整只票」级别的 —— 已知断裂清单上有 30 只,池子里 24 只,
     它们贡献 48,979 根 bar = 池子的 8.05%。

  ★★★ 两个数一对比:剔掉 0.0016%,而污染是 8.05% —— 差 4,898 倍。
  ★★★ 更糟的是:30 只里有 22 只在残余跳变清单里**一根都没有** ——
     ★ 包括 SQBG(+145,942%)和 FTLF(+499.62 倍)这两只最严重的。

一句话教训:
  ★★ 「残余跳变清单(单根 bar)」和「已知数据断裂清单(整只票)」是两个
     不同的东西,前者挡不住后者。
  ★ 凡是报告里写「已剔除假跳变」的地方,都必须说清剔的是哪一个。
"""
from __future__ import annotations

import importlib.util
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_ENGINE = os.path.dirname(_HERE)
_REPO = os.path.dirname(_ENGINE)

#: 剔除覆盖率低于这个值 → FAIL。
#: ★ 这不是一个挑出来的阈值:它要求「剔除清单至少碰到过断裂清单上的每一只票」。
#: ★★ 允许单根 bar 口径剔得少,但不允许整只票一根都没碰到 ——
#:    因为「一根都没碰到」意味着那只票的全部 bar 都原样进了回测。
MIN_SYMBOL_COVERAGE = 1.0

#: 2026-10-29 晚的实测值,留作回归基线
EXPECTED = {
    "残余跳变根数": 10, "残余跳变涉及票数": 8,
    "断裂清单票数": 30, "池子里的断裂票数": 24,
    "一根都没列到的票数": 22,
    "断裂票占池子bar比例": 0.0805, "剔除占池子bar比例": 0.0000164,
}


def _known() -> set:
    p = os.path.join(_HERE, "anchor_health.py")
    spec = importlib.util.spec_from_file_location("ah", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)                                  # type: ignore
    return m.known_break_symbols()


def check() -> dict:
    import sys
    if _REPO not in sys.path:
        sys.path.insert(0, _REPO)
    from engine import split_gate                               # noqa: PLC0415

    jumps = split_gate.residual_jumps(3.0)
    jump_syms = {t[0] for t in jumps}
    known = _known()

    pool_dir = os.path.join(_REPO, "pilot_300")
    pool = [d for d in os.listdir(pool_dir)
            if os.path.isdir(os.path.join(pool_dir, d)) and d != "benchmarks"]
    total = contaminated = 0
    for s in pool:
        p = os.path.join(pool_dir, s, "daily.json")
        if not os.path.exists(p):
            continue
        try:
            n = len(json.load(open(p, encoding="utf-8")).get("data") or [])
        except Exception:
            continue
        total += n
        if s in known:
            contaminated += n

    uncovered = sorted(known - jump_syms)
    in_pool = [s for s in known if s in pool]
    cov = 1.0 - len(uncovered) / max(1, len(known))

    out: dict = {
        "残余跳变根数": len(jumps),
        "残余跳变涉及票数": len(jump_syms),
        "断裂清单票数": len(known),
        "池子里的断裂票数": len(in_pool),
        "一根都没列到的票": uncovered,
        "票级覆盖率": round(cov, 4),
        "断裂票占池子bar比例": round(contaminated / max(1, total), 4),
        "剔除占池子bar比例": round(len(jumps) / max(1, total), 7),
        "话": [],
    }
    out["★倍数差"] = round(contaminated / max(1, len(jumps)))

    if cov < MIN_SYMBOL_COVERAGE:
        out["级别"] = "FAIL"
        out["话"].append(
            f"★★ FAIL 「已剔除假跳变」剔的是**单根 bar**({len(jumps)} 根、"
            f"{len(jump_syms)} 只票),而污染是**整只票**级别的"
            f"({len(known)} 只,池子里 {len(in_pool)} 只)。"
            f"★ 票级覆盖率只有 {cov:.0%} —— "
            f"★★ {len(uncovered)} 只票在剔除清单里**一根都没有**,"
            f"它们的全部 bar 原样进了回测。")
        out["话"].append(
            f"    · 剔掉 {len(jumps) / max(1, total) * 100:.4f}% 的 bar,"
            f"而断裂票占 {contaminated / max(1, total) * 100:.2f}% "
            f"→ ★★★ 差 {out['★倍数差']:,} 倍。")
        worst = [s for s in ("SQBG", "FTLF") if s in uncovered]
        if worst:
            out["话"].append(
                f"    · ★★★ 其中 {' / '.join(worst)} 一根都没列到 —— "
                f"而 SQBG 单笔能到 +145,942.7%、FTLF 能到 +499.62 倍。")
        out["话"].append(
            f"    · ★ 一根都没列到的 {len(uncovered)} 只:"
            f"{', '.join(uncovered)}")
        out["话"].append(
            "    · ★ 怎么办:凡是报告里写「已剔除假跳变」的地方,"
            "必须说清剔的是单根 bar 还是整只票;"
            "★★ 买跌类策略和朴素基准一律同时报「剔除断裂清单票之后的数」。")
    else:
        out["级别"] = "OK"
        out["话"].append(
            f"✅ 剔除清单碰到了断裂清单上的每一只票({len(known)} 只)。")
    return out


def _selftest() -> None:
    r = check()
    for line in r["话"]:
        print("  ", line)
    assert r["级别"] == "FAIL", r
    assert r["票级覆盖率"] < 0.5, r
    assert "SQBG" in r["一根都没列到的票"], r
    print(f"\n  实测:{r['残余跳变根数']} 根 / {r['残余跳变涉及票数']} 只 剔除"
          f"  vs  {r['断裂清单票数']} 只断裂、池子里 {r['池子里的断裂票数']} 只"
          f"  → 差 {r['★倍数差']:,} 倍")
    print("checks/jump_removal_coverage 自测通过 —— ★★★ 在真实的 split_gate "
          "和真实池子上确认:「已剔除假跳变」这句话剔掉的是 0.0016%,"
          "而污染是 8.05%,且最严重的 SQBG / FTLF 一根都没剔到。")


if __name__ == "__main__":
    _selftest()
