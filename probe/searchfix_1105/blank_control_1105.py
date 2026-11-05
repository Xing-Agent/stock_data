# -*- coding: utf-8 -*-
"""
自查项 1 · 空白对照（2026-11-05）
预先登记：手册/47-修搜索-预先登记-1105.md §三

★★★ 要验的那件事（Lin 11-04 定、11-05 保留）：
  「拿**纯瞎买**的假策略去考，赢的比例要在 **50% 左右**。」

★ 道理：修好的搜索如果有偏向（比如系统性把对照组调得比真链弱），
  那么**连瞎买都能赢** —— ★★ 那这道闸就废了，整轮作废。
★★★ 所以这一步是在考**我们的考官**，不是考策略。

做法：
  · 拿一条已经跑通的链当骨架，★ 把它的「③什么时候买」换成**纯随机**；
  · 换 **20 个不同的种子** → 20 条「假策略」；
  · 每一条都走一遍完整的基准一（★★ 和真策略**一模一样**的那道闸）；
  · 数「赢随机」的比例。

★★★ 关键一条：假策略的种子和对照组的种子**必须不重叠**，
  否则它会和自己比,必然打平 —— ★ 这里用 CONTROL_SEEDS 之外的种子。
"""
from __future__ import annotations

import json
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

OUT = os.path.join(HERE, "blank_control_results_1105.json")

# ★ 骨架用扩3-ours：★★ 它笔数居中（334），既不是极少也不是极多
SKELETON = "扩3-ours"
N_FAKE = 20
# ★★★ 假策略的种子 —— 刻意避开 analyze.CONTROL_SEEDS（对照组用的那一批）
_BAD = set(int(s) for s in analyze.CONTROL_SEEDS)
FAKE_SEEDS = [s for s in range(900001, 900200) if s not in _BAD][:N_FAKE]


def main() -> int:
    assert not (set(FAKE_SEEDS) & _BAD), "★★★ 假策略种子和对照组种子撞了,必须换"
    R.OX.install()
    man = data.load_manifest()
    have_px = set(cache.symbols())
    syms = [s for s in sorted(man) if man[s].fundamentals_path and s in have_px]
    start, end = R.DEV

    raw = R._load(SKELETON)
    c0 = R.apply_grid(raw, SKELETON, 30, None)
    cfg0 = chain.ChainConfig.from_dict(json.loads(json.dumps(c0)))
    uni = matrices.universe_mask(cfg0.raw.get("universe") or {}, syms)
    R.OX.set_screen(SKELETON, uni)

    # ★ 先拿真链跑一遍，只为了知道「该出手多少次」—— ★★ 假策略要对齐这个频率，
    #   否则它和真链比的就是「做得多不多」，不是「挑得准不准」。
    res0 = chain.run_chain(cfg0, syms, start, end, 1_000_000.0)
    n_target = len(res0.ledger)
    n_days = max(1, len(matrices.pd.bdate_range(start, end)))
    rate0 = analyze.random_control_rate(n_target, n_days, max(1, len(uni.columns)))
    print(f"★ 骨架 {SKELETON}:真链 {n_target} 笔 → 假策略起始触发率 {rate0:.4g}", flush=True)

    out = []
    for i, sd in enumerate(FAKE_SEEDS):
        t0 = time.time()
        cfg = cfg0.copy_with(entry={
            "type": "random",
            "params": {"rate": rate0, "seed": int(sd)},
            "source": "★★★ 自查项1 空白对照:纯瞎买的假策略(不是策略,是考官的考题)"})
        try:
            res = chain.run_chain(cfg, syms, start, end, 1_000_000.0)
            if res.ledger.empty:
                out.append({"种子": sd, "★跑挂了": "假策略 0 笔"}); continue
            b1 = analyze.random_entry_benchmark(cfg, res, syms, start, end)
            diff = b1["★真信号每笔R − 随机进场每笔R"]
            out.append({
                "种子": sd, "假策略笔数": len(res.ledger),
                "对照平均笔数": b1["随机进场_对照笔数均值"],
                "★对照笔数偏差": b1["★对照笔数偏差"],
                "★基准一差额": diff,
                "★赢了吗": bool(diff > 0),
                "耗时秒": round(time.time() - t0, 1)})
            print(f"[{i+1}/{len(FAKE_SEEDS)}] 种子{sd} 笔数={len(res.ledger)} "
                  f"差额={diff:+.5f} {'★赢' if diff>0 else '输'} "
                  f"{out[-1]['耗时秒']}s", flush=True)
        except Exception as e:
            out.append({"种子": sd, "★跑挂了": f"{type(e).__name__}: {str(e)[:200]}"})
            print(f"[{i+1}/{len(FAKE_SEEDS)}] 种子{sd} ★跑挂了 {type(e).__name__}",
                  flush=True)

    ok = [r for r in out if "★赢了吗" in r]
    nwin = sum(1 for r in ok if r["★赢了吗"])
    frac = nwin / len(ok) if ok else None
    verdict = ("★★★ 过 —— 瞎买的赢面在 50% 左右,说明这道闸没有偏向"
               if frac is not None and 0.30 <= frac <= 0.70 else
               "★★★ **不过** —— 瞎买的赢面偏离 50% 太多,★ 这道闸有偏向,**整轮作废**")
    doc = {
        "跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "★这是什么": "自查项 1 · 空白对照 —— ★★★ 考的是考官,不是策略",
        "★预先登记": "手册/47-修搜索-预先登记-1105.md §三",
        "骨架": SKELETON, "真链笔数": n_target,
        "假策略个数": len(FAKE_SEEDS),
        "★假策略种子": FAKE_SEEDS,
        "★★★种子有没有和对照组撞": "没有 —— 刻意避开 analyze.CONTROL_SEEDS",
        "能判的": len(ok), "赢的": nwin, "★赢面": frac,
        "★★★判定": verdict,
        "★容差": analyze.CONTROL_TOL,
        "逐条": out,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2, default=str)
    print(f"\n★★★ 能判 {len(ok)} 条 · 赢 {nwin} 条 · 赢面 "
          f"{'—' if frac is None else f'{frac:.0%}'}\n{verdict}", flush=True)
    print("★ 写到", OUT, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
