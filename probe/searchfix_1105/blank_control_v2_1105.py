# -*- coding: utf-8 -*-
"""
自查项 1 · 空白对照 · 第二版（2026-11-05）

★★★ 为什么要有第二版 —— ★ 第一版「过了」，但**过得没有意义**：

  ① ★★★ **样本太少**：20 条假策略，7 条赢（35%）。
     ★ 95% 置信区间 = **[18%, 57%]** —— ★★ 这么宽的区间，
       **真实赢面不管是 35% 还是 55%，这个检验都看不出来**。
     ★★★ 我预先登记的合格带「30%~70%」本身就太松 —— **几乎不可能不过**。

  ② ★★★ **只测了一个笔数档**：20 条假策略的笔数全在 **18~33 笔**之间。
     ★ 而技术面那 45 条链是 **111 ~ 3,989 笔**。
     ★★ 也就是说：★★★ **这道闸在「几百上千笔」那个档位上，根本没被验过。**

★ 第二版修这两件：
  · **每档 40 条**（★ 两档共 80 条）→ ★★ n=40 时能分辨约 ±16%，
    两档合并 n=80 能分辨约 ±11%（★ 比 ±22% 强一倍）
  · **两个笔数档**：**低档 ≈ 25 笔**（沿用第一版口径）· **高档 ≈ 400 笔**
    → ★★★ 高档那一档才对得上技术面 45 条所在的区间

★★ 口径不变：假策略种子刻意避开 analyze.CONTROL_SEEDS；容差 ±5% 不动。
"""
from __future__ import annotations

import json
import math
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "expand_run_1104"))

from engine import analyze, cache, chain, data, matrices      # noqa: E402
from probe.searchfix_1105 import fix_search_1105 as FIX       # noqa: E402

FIX.install()
import run_expand_1104 as R                                   # noqa: E402

OUT = os.path.join(HERE, "blank_control_v2_results_1105.json")
SKELETON = "扩3-ours"
N_PER_BAND = 40
_BAD = set(int(s) for s in analyze.CONTROL_SEEDS)
SEEDS = [s for s in range(910001, 910400) if s not in _BAD][:N_PER_BAND]


def _wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    ph, z = k / n, 1.96
    d = 1 + z * z / n
    c = (ph + z * z / (2 * n)) / d
    h = z * math.sqrt(ph * (1 - ph) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def main() -> int:
    R.OX.install()
    man = data.load_manifest()
    have_px = set(cache.symbols())
    syms = [s for s in sorted(man) if man[s].fundamentals_path and s in have_px]
    start, end = R.DEV

    raw = R._load(SKELETON)
    cfg0 = chain.ChainConfig.from_dict(
        json.loads(json.dumps(R.apply_grid(raw, SKELETON, 30, None))))
    uni = matrices.universe_mask(cfg0.raw.get("universe") or {}, syms)
    R.OX.set_screen(SKELETON, uni)
    n_days = max(1, len(matrices.pd.bdate_range(start, end)))
    n_syms = max(1, len(uni.columns))

    # ★ 两个笔数档的触发率:低档沿用第一版(rate0);高档往上调到约 400 笔。
    #   ★★ 怎么调:先试探几个 rate,取最接近 400 笔的那个 —— ★★★ 这一步只看笔数,不看成绩。
    rate_lo = analyze.random_control_rate(478, n_days, n_syms)
    print(f"★ 低档 rate = {rate_lo:.4g}(第一版口径,实测约 25 笔)", flush=True)

    probe_seed = 987654321 % (2**31)
    best, tries = None, []
    rate = rate_lo * 8
    for _ in range(8):
        c = cfg0.copy_with(entry={"type": "random",
                                  "params": {"rate": rate, "seed": probe_seed},
                                  "source": "★ 高档探路(只看笔数)"})
        n = len(chain.run_chain(c, syms, start, end, 1_000_000.0).ledger)
        tries.append({"轮": len(tries) + 1, "rate": rate, "n": n})
        print(f"   探路 rate={rate:.4g} → {n} 笔", flush=True)
        if best is None or abs(n - 400) < abs(best[1] - 400):
            best = (rate, n)
        if abs(n - 400) / 400 <= 0.10:
            break
        try:
            rate = FIX.next_rate_bracket(tries, 400, "n")
        except FIX.SaturatedNoUpperBracket:
            print("   ★★★ 高档探路:找不到上端点(槽位锁死),就用目前最接近的", flush=True)
            break
    rate_hi, n_hi = best
    print(f"★ 高档 rate = {rate_hi:.4g}(约 {n_hi} 笔)", flush=True)

    bands = [("低档(约 25 笔)", rate_lo), (f"高档(约 {n_hi} 笔)", rate_hi)]
    out = {}
    for band, rate_b in bands:
        rows = []
        for i, sd in enumerate(SEEDS):
            t0 = time.time()
            cfg = cfg0.copy_with(entry={
                "type": "random", "params": {"rate": rate_b, "seed": int(sd)},
                "source": "★★★ 自查项1 空白对照 v2:纯瞎买的假策略(考的是考官)"})
            try:
                res = chain.run_chain(cfg, syms, start, end, 1_000_000.0)
                if res.ledger.empty:
                    rows.append({"种子": sd, "★跑挂了": "假策略 0 笔"}); continue
                b1 = analyze.random_entry_benchmark(cfg, res, syms, start, end)
                diff = b1["★真信号每笔R − 随机进场每笔R"]
                rows.append({"种子": sd, "假策略笔数": len(res.ledger),
                             "对照平均笔数": b1["随机进场_对照笔数均值"],
                             "★对照笔数偏差": b1["★对照笔数偏差"],
                             "★基准一差额": diff, "★赢了吗": bool(diff > 0),
                             "耗时秒": round(time.time() - t0, 1)})
                print(f"[{band}] [{i+1}/{len(SEEDS)}] 种子{sd} "
                      f"笔数={len(res.ledger)} 差额={diff:+.5f} "
                      f"{'★赢' if diff > 0 else '输'}", flush=True)
            except Exception as e:
                rows.append({"种子": sd, "★跑挂了": f"{type(e).__name__}: {str(e)[:200]}"})
                print(f"[{band}] [{i+1}/{len(SEEDS)}] 种子{sd} ★跑挂 "
                      f"{type(e).__name__}", flush=True)
        ok = [r for r in rows if "★赢了吗" in r]
        k = sum(1 for r in ok if r["★赢了吗"])
        lo, hi = _wilson(k, len(ok))
        out[band] = {"rate": rate_b, "能判的": len(ok), "赢的": k,
                     "★赢面": (k / len(ok) if ok else None),
                     "★95%置信区间": [lo, hi], "逐条": rows}
        print(f"\n★★★ {band}:赢 {k}/{len(ok)} = "
              f"{(k/len(ok) if ok else float('nan')):.0%} · "
              f"95%CI [{lo:.0%}, {hi:.0%}]\n", flush=True)

    allok = [r for b in out.values() for r in b["逐条"] if "★赢了吗" in r]
    K = sum(1 for r in allok if r["★赢了吗"])
    LO, HI = _wilson(K, len(allok))
    doc = {
        "跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "★这是什么": "自查项 1 · 空白对照 v2 —— ★★★ 考的是考官,不是策略",
        "★为什么要 v2": ("★ v1 过了但没意义:n=20,95%CI=[18%,57%];"
                         "★★ 且只测了 18~33 笔这一档,"
                         "★★★ 而技术面 45 条是 111~3,989 笔"),
        "骨架": SKELETON, "每档条数": N_PER_BAND,
        "★★★种子有没有和对照组撞": "没有 —— 刻意避开 analyze.CONTROL_SEEDS",
        "★容差": analyze.CONTROL_TOL,
        "分档": {k: {kk: vv for kk, vv in v.items() if kk != "逐条"}
                 for k, v in out.items()},
        "合并": {"能判的": len(allok), "赢的": K,
                 "★赢面": (K / len(allok) if allok else None),
                 "★95%置信区间": [LO, HI]},
        "★★★判定": ("★★★ 过 —— 50% 落在置信区间里,这道闸看不出偏向"
                     if LO <= 0.5 <= HI else
                     "★★★ **不过** —— 50% 落在置信区间之外,★ 这道闸有偏向,**整轮作废**"),
        "逐档明细": out,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2, default=str)
    print(f"★★★ 合并:赢 {K}/{len(allok)} = {K/max(1,len(allok)):.0%} · "
          f"95%CI [{LO:.0%}, {HI:.0%}]\n{doc['★★★判定']}", flush=True)
    print("★ 写到", OUT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
