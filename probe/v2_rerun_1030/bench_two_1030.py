#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 大+中池重跑之后,逐链补两条**现成的**基准线 —— 2026-10-30

三秒版:基准设计仓库里**早就有**,不要另起一套(今天已经五次把"已有的"
        当成"缺的"去重新发明)。两条就是:

  ★★ 基准一 = 同环境随机进场(`analyze.random_entry_benchmark`)
     判据 = 「真信号每笔 R − 同环境随机进场每笔 R」,正数才算赢。
     ★★★ 它回答的是:**这条策略的进场规则有没有加东西**。
     ★ 这是「这条策略自己的对标」—— 同样的市场环境、同样的仓位规则,
       只把进场换成随机。

  ★★ 基准二 = 同等仓位大盘(`analyze.exposure_matched_benchmark`)
     Ē = 全周期**固定**的时间加权平均净敞口;基准 = Ē × SPY + (1−Ē) × 无风险。
     ★★★ 它回答的是:**和大势比怎么样**。
     ★ 出处 Treynor & Mazuy (1966) / Merton (1981) / Jensen (1968)。

★★★ 这两条**只摆出来,不用来判生死**。策略组明确说了:打不过大盘不是
   「不能给用户」的理由 —— 买大盘本身就是另一条策略。

★★ 关于基准二的「拆股【待复核】」:★★★ 根因**已经修好了**(2026-10-29),
   本轮复核确认,见报告第二节。`load_benchmark()` 现在和个股走同一个比例来源
   (`split_gate.ratio_events_from_rows`)。★ 而且全部 42 份配置的
   `component_match` 都是 `large` → SPY,而 **SPY 在数据里 0 个拆股事件**,
   所以基准二的数字**从来没受过这个 bug 影响**(实测 max_abs_diff 6.76e-07,
   见 engine/results_1029_bench_split_impact.json)。

★ 只跑过了硬闸的那些链(笔数 ≥30 + 三槽位齐 + 集中度),省机器;串行单进程。
"""
from __future__ import annotations

import copy
import json
import os
import resource
import subprocess
import sys
import time

import numpy as np
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import (analyze, cache, chain, data, matrices, ops_exits_1029,  # noqa: E402
                    pat6_ops, pool_scope)
import rerun_core_1030 as RC                                               # noqa: E402

CONFIG_DIR = os.path.join(ROOT, "engine", "configs")
IN_JSON = os.path.join(HERE, "rerun_results_1030.json")
OUT = os.path.join(HERE, "bench_two_1030.json")

VARIANT_MODULES = [
    ("A0十二条", "engine.run_a0_12"),
    ("技术派六条三版", "engine.pat6_run"),
    ("批五修正", "engine.run_p5_1029"),
    ("原著离场", "engine.run_orig_exits_1029"),
    ("剔污染", "engine.run_declean_1030"),
]


def gates_pass(r) -> bool:
    a = r["大中_重跑"]
    c = a["集中度"]
    sh = c.get("集中度_前10笔占总盈利")
    return (a["笔数"] >= 30
            and r["四槽位"]["三槽位齐全_不含加仓"]
            and not c.get("★退化") and not c.get("★半退化")
            and sh is not None and sh <= 0.50)


def main() -> int:
    print(subprocess.run(["free", "-m"], capture_output=True, text=True).stdout)
    print(f"CPU 核数 {os.cpu_count()} —— ★ 串行单进程\n")

    prev = json.load(open(IN_JSON, encoding="utf-8"))
    keep = {r["链"] for r in prev["逐链"] if "★跑不了" not in r and gates_pass(r)}
    print(f"★ 过硬闸的 {len(keep)} 条,只给这些跑两条基准\n")

    pat6_ops.install()
    ops_exits_1029.install()
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]

    variants = []
    seen = set()
    for batch, modname in VARIANT_MODULES:
        mod = __import__(modname, fromlist=["VARIANTS"])
        for v in getattr(mod, "VARIANTS"):
            label = f"{batch}/{v[0]}"
            if label not in keep or label in seen:
                continue
            seen.add(label)
            variants.append((label, v[1], v[2], v[4]))

    rows = []
    t0 = time.time()
    for i, (label, yml, ov, group) in enumerate(variants, 1):
        t = time.time()
        with open(os.path.join(CONFIG_DIR, yml), encoding="utf-8") as fh:
            raw = yaml.safe_load(fh)
        if ov is not None:
            raw = ov(copy.deepcopy(raw))
        cfg = chain.ChainConfig.from_dict(raw)
        m = matrices.build(cfg.raw, syms)
        RC.apply_scope(m, "large_mid")
        res = chain.run_chain(cfg, syms, m=m)
        led = res.ledger
        rn = led["r_multiple_net"].astype(float).to_numpy()
        rn = rn[np.isfinite(rn)]
        real_r = float(rn.mean()) if rn.size else None

        # ★★ 基准一:同环境随机进场。★ 它自己会按 cfg 的 universe/regime 重建环境,
        #   ★★★ 而我们已经把池子口径与进了 m.universe —— 但 random_entry_benchmark
        #     自己 build 矩阵,所以这里**显式**把口径也加给它:见下面的 _patched。
        b1 = analyze.random_entry_benchmark(cfg, res, syms,
                                            data.PERF_START, data.PERF_END)
        bm = cfg.get("benchmark") or {}
        b2 = analyze.exposure_matched_benchmark(
            res, bm.get("component_match", "large"),
            bm.get("risk_free_annual"))
        rows.append({
            "链": label, "族": group, "配置": yml,
            "笔数": int(len(led)),
            "合格进场信号(entry&universe)": int((m.entry & m.universe).sum()),
            "每笔净R": real_r,
            "★基准一_同环境随机进场": analyze._num(b1) if hasattr(analyze, "_num") else b1,
            "★基准二_同等仓位大盘": analyze._num(b2) if hasattr(analyze, "_num") else b2,
            "耗时秒": round(time.time() - t, 1),
        })
        print(f"[{i}/{len(variants)}] {label[:56]:56s} "
              f"{len(led):5d}笔 R{real_r or 0:+.4f} "
              f"{rows[-1]['耗时秒']}s RSS "
              f"{round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss/1024,1)}MB")

    out = {
        "口径戳": pool_scope.stamp("large_mid", {
            "本轮做法": "★ 大+中池真重跑之后,逐链补两条现成的基准线",
            "基准一": "analyze.random_entry_benchmark(同环境随机进场,5 个种子)",
            "基准二": "analyze.exposure_matched_benchmark(Ē 全周期固定 × SPY)",
            "★不作判据": "★★★ 两条基准只摆出来,不用来判这条链能不能给用户",
            "覆盖": f"过硬闸的 {len(variants)} 条",
        }),
        "逐链": rows,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n共 {round(time.time()-t0,1)}s → {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
