#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 第一件 · 修基准一并重跑全库 —— 2026-10-30

三秒版:基准一 =「真信号每笔 R − 同环境随机进场每笔 R」。
        它的前提是「对照组出手次数和真链一样多」,这个前提以前**破了没人管**。
        本轮:容差 ±8%→±5%、达不到就 raise、种子 5→50 且只走 CONTROL_SEEDS 一条路,
        然后逐链重跑、和旧值对差。

★★ engine 本轮**确实改了**(`engine/analyze.py`),因为那三处缺陷就在它里面:
   ① `calibrated_random_rate` 加硬断言(BenchmarkPremiseBroken)
   ② 容差 CONTROL_TOL = 0.05
   ③ `CONTROL_SEEDS` 扩到 50 个写死常量;`random_entry_benchmark` 删掉
      自生成 `20181001 + 977*k` 那一行 → ★ 两条路变一条(第 9 处两种写法已消)

★★★ 本脚本自己只做一件 engine 没法做的事:**把池子口径也加给对照组**。
   `random_entry_benchmark` 内部 `chain.run_chain(..., m=None)` 会自己 build 矩阵,
   拿到的是**全池**;而真链跑在大+中池上。
   ★ `probe/v2_rerun_1030/bench_two_1030.py:119-120` 的注释写着「这里**显式**把
     口径也加给它:见下面的 _patched」—— ★★★ 实测 grep:**那个 `_patched` 不存在**。
     所以旧的 45 条基准一,真链在大+中池、对照组在全池,**环境不同**。
   ★ 本脚本用 run_chain 包一层来修(engine 里加这个钩子属于另一件事,已登记)。

★★ 跑批纪律(照抄任务书,逐条做到):
   ① 不用 nohup & —— 用正式后台机制跑这个脚本
   ② ★ 可续跑:每条链跑完立刻 dump 一份 JSON;重跑时跳过已有结果
   ③ ★ 先 --limit 2/3 量实际耗时,把总时间估出来再开全库
   ④ ★ 先写结果再打印;所有 print 包在 try 里

跑法:
   python3 probe/gates_rebuild_1030/run_bench1_1030.py --limit 3     # 量耗时
   python3 probe/gates_rebuild_1030/run_bench1_1030.py               # 全库(可续跑)
   python3 probe/gates_rebuild_1030/run_bench1_1030.py --seeds-only  # 只换种子不改池子口径(做差值分解)
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import resource
import subprocess
import sys
import time
import traceback

import numpy as np
import pandas as pd
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
V2 = os.path.join(ROOT, "probe", "v2_rerun_1030")
for p in (ROOT, V2):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import (analyze, cache, chain, data, matrices, ops_exits_1029,  # noqa: E402
                    pat6_ops, pool_scope, stats_gate)
import rerun_core_1030 as RC                                               # noqa: E402

CONFIG_DIR = os.path.join(ROOT, "engine", "configs")
OLD_BENCH = os.path.join(V2, "bench_two_1030.json")
OLD_RERUN = os.path.join(V2, "rerun_results_1030.json")

PER_CHAIN = os.path.join(HERE, "per_chain")          # ★ 可续跑的落盘点
LEDGERS = os.path.join(HERE, "ledgers_1030")         # ★ 第三件要用的流水
OUT = os.path.join(HERE, "bench1_fixed_1030.json")

N_SEEDS = 50
SCOPE = "large_mid"

VARIANT_MODULES = [
    ("A0十二条", "engine.run_a0_12"),
    ("技术派六条三版", "engine.pat6_run"),
    ("批五修正", "engine.run_p5_1029"),
    ("原著离场", "engine.run_orig_exits_1029"),
    ("剔污染", "engine.run_declean_1030"),
]


def _say(*a):
    """★ 纪律④:打印一律包在 try 里 —— 一个拼错的键不许把跑批炸掉。"""
    try:
        print(*a, flush=True)
    except Exception:
        try:
            print("★ 打印本身出错(已吞掉,不影响结果):"
                  + traceback.format_exc(limit=1), flush=True)
        except Exception:
            pass


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


# ══════════════════════════════════════════════════════════════════════════
# 一 · 把池子口径加给**所有** run_chain(含对照组)
# ══════════════════════════════════════════════════════════════════════════

_ORIG_RUN_CHAIN = chain.run_chain
_SCOPE_ON = True


def _scoped_run_chain(cfg, symbols=None, start=data.PERF_START, end=data.PERF_END,
                      initial_equity=1_000_000.0, m=None,
                      flat_friction_bps=None, total_return=None):
    """m 没给时自己 build 并把池子口径与进 universe —— ★ 对照组也走这条路。"""
    if m is None and _SCOPE_ON:
        m = matrices.build(cfg.raw, symbols)
        RC.apply_scope(m, SCOPE)
    return _ORIG_RUN_CHAIN(cfg, symbols, start, end, initial_equity, m=m,
                           flat_friction_bps=flat_friction_bps,
                           total_return=total_return)


# ══════════════════════════════════════════════════════════════════════════
# 二 · 旧值 / 链表
# ══════════════════════════════════════════════════════════════════════════

def old_bench1() -> dict[str, dict]:
    d = json.load(open(OLD_BENCH, encoding="utf-8"))
    return {r["链"]: r for r in d["逐链"]}


def gates_pass(r) -> bool:
    """★ 照抄 bench_two_1030.gates_pass,一个字不改(同一样东西一个口径)。"""
    a = r["大中_重跑"]
    c = a["集中度"]
    sh = c.get("集中度_前10笔占总盈利")
    return (a["笔数"] >= 30
            and r["四槽位"]["三槽位齐全_不含加仓"]
            and not c.get("★退化") and not c.get("★半退化")
            and sh is not None and sh <= 0.50)


def chain_list() -> list[tuple]:
    prev = json.load(open(OLD_RERUN, encoding="utf-8"))
    keep = {r["链"] for r in prev["逐链"] if "★跑不了" not in r and gates_pass(r)}
    out, seen = [], set()
    for batch, modname in VARIANT_MODULES:
        mod = __import__(modname, fromlist=["VARIANTS"])
        for v in getattr(mod, "VARIANTS"):
            label = f"{batch}/{v[0]}"
            if label not in keep or label in seen:
                continue
            seen.add(label)
            out.append((label, v[1], v[2], v[4]))
    return out


def safe_name(label: str) -> str:
    return label.replace("/", "_").replace(" ", "").replace("·", "·")


# ══════════════════════════════════════════════════════════════════════════
# 三 · 一条链
# ══════════════════════════════════════════════════════════════════════════

def run_one(label: str, yml: str, ov, group: str, syms: list[str],
            seeds_only: bool) -> dict:
    global _SCOPE_ON
    t = time.time()
    with open(os.path.join(CONFIG_DIR, yml), encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if ov is not None:
        raw = ov(copy.deepcopy(raw))
    cfg = chain.ChainConfig.from_dict(raw)

    # ---- 真链:大+中池(和 v2_rerun 完全同一条路)
    m = matrices.build(cfg.raw, syms)
    RC.apply_scope(m, SCOPE)
    res = _ORIG_RUN_CHAIN(cfg, syms, data.PERF_START, data.PERF_END, m=m)
    led = res.ledger

    # ---- 基准一:★ 对照组是否也套池子口径,由 seeds_only 决定
    _SCOPE_ON = not seeds_only
    err = None
    b1 = None
    try:
        b1 = analyze.random_entry_benchmark(cfg, res, syms, data.PERF_START,
                                            data.PERF_END, n_seeds=N_SEEDS,
                                            keep_ledger=True)
    except analyze.BenchmarkPremiseBroken as e:
        err = {"类": "BenchmarkPremiseBroken", "说明": str(e)}
    finally:
        _SCOPE_ON = True

    rec: dict = {
        "链": label, "族": group, "配置": yml,
        "池子口径": SCOPE,
        "对照组是否同池": (not seeds_only),
        "笔数": int(len(led)),
        "合格进场信号(entry&universe)": int((m.entry & m.universe).sum()),
        "每笔净R": (float(np.nanmean(led["r_multiple_net"].astype(float)))
                    if len(led) else None),
        "每笔毛R": (float(np.nanmean(led["r_multiple"].astype(float)))
                    if len(led) else None),
        "种子数": N_SEEDS,
    }

    if err is not None:
        # ★★★ 前提破了 → 这条链的基准一**不出数**(禁止下游计算和渲染)
        rec["★基准一"] = None
        rec["★前提破了_禁止下游"] = err
    else:
        pool = b1.pop("★对照流水并池", None)
        rec["★基准一"] = {k: (None if isinstance(v, float) and not np.isfinite(v)
                              else v) for k, v in b1.items()}
        # ---- 判据 Z:用这 50 个种子的并池对照流水当零分布(第二件要用)
        try:
            v = analyze.bootstrap_on_ledger(res, pool_ledger=pool)
            zs = {k: (float(r.z_effect) if np.isfinite(r.z_effect) else None)
                  for k, r in v.results.items()}
            rec["★判据Z_用50种子并池对照"] = zs
            rec["★判据通过(旧 verdict 逻辑)"] = bool(v.passed)
        except Exception:
            rec["★判据Z_用50种子并池对照"] = None
            rec["★判据Z_出错"] = traceback.format_exc(limit=3)
        # ---- 对照并池流水存一份(第三件的面板回归要它)
        if pool is not None and not pool.empty:
            os.makedirs(LEDGERS, exist_ok=True)
            pool.to_csv(os.path.join(LEDGERS,
                                     f"CTRL__{safe_name(label)}.csv"), index=False)

    # ---- 真链流水存一份(第三件的面板回归要它)
    os.makedirs(LEDGERS, exist_ok=True)
    led.to_csv(os.path.join(LEDGERS, f"REAL__{safe_name(label)}.csv"), index=False)

    rec["耗时秒"] = round(time.time() - t, 1)
    rec["峰值RSS_MB"] = round(_rss_mb(), 1)
    return rec


# ══════════════════════════════════════════════════════════════════════════
# 四 · main
# ══════════════════════════════════════════════════════════════════════════

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条(量耗时用)")
    ap.add_argument("--seeds-only", action="store_true",
                    help="对照组**不**套池子口径(= 只改种子和容差)→ 做差值分解")
    args = ap.parse_args()

    os.makedirs(PER_CHAIN, exist_ok=True)
    tag = "seedsonly" if args.seeds_only else "scoped"

    try:
        _say(subprocess.run(["free", "-m"], capture_output=True, text=True).stdout)
        _say(f"CPU 核数 {os.cpu_count()} —— ★ 串行单进程 · 种子 {N_SEEDS} · "
             f"容差 ±{analyze.CONTROL_TOL:.0%} · 口径 {tag}")
    except Exception:
        pass

    chain.run_chain = _scoped_run_chain       # ★ 对照组也进大+中池
    pat6_ops.install()
    ops_exits_1029.install()
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]

    variants = chain_list()
    if args.limit:
        variants = variants[:args.limit]
    _say(f"★ 本轮要跑 {len(variants)} 条\n")

    rows, t0 = [], time.time()
    for i, (label, yml, ov, group) in enumerate(variants, 1):
        dst = os.path.join(PER_CHAIN, f"{tag}__{safe_name(label)}.json")
        if os.path.exists(dst):                       # ★ 纪律②:可续跑
            try:
                rows.append(json.load(open(dst, encoding="utf-8")))
                _say(f"[{i}/{len(variants)}] 跳过(已有结果) {label[:60]}")
            except Exception:
                os.remove(dst)
            else:
                continue
        try:
            rec = run_one(label, yml, ov, group, syms, args.seeds_only)
        except Exception:
            rec = {"链": label, "族": group, "配置": yml,
                   "★跑不了": traceback.format_exc(limit=6)}
        # ★★ 纪律④:**先写盘**,再打印
        with open(dst, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, ensure_ascii=False, indent=1, default=str)
        rows.append(rec)
        try:
            b = rec.get("★基准一") or {}
            _say(f"[{i}/{len(variants)}] {label[:52]:52s} "
                 f"{rec.get('笔数', 0):5d}笔 "
                 f"基准一={b.get('★真信号每笔R − 随机进场每笔R')} "
                 f"对照偏差={b.get('★对照笔数偏差')} "
                 f"{rec.get('耗时秒')}s RSS{rec.get('峰值RSS_MB')}MB"
                 + ("  ★前提破了" if rec.get("★前提破了_禁止下游") else "")
                 + ("  ★跑不了" if rec.get("★跑不了") else ""))
        except Exception:
            pass

    out = {
        "口径戳": pool_scope.stamp(SCOPE, {
            "本轮做法": "★★★ 修好基准一(容差 ±5% 硬断言 · 50 个写死种子 · "
                        "对照组同池)之后逐链重跑",
            "种子来源": "analyze.CONTROL_SEEDS[:50] —— ★ 只有这一条路",
            "容差": analyze.CONTROL_TOL,
            "对照组是否同池": (not args.seeds_only),
            "覆盖": f"{len(variants)} 条(= bench_two_1030 那 45 条的同一口径)",
        }),
        "逐链": rows,
        "总耗时秒": round(time.time() - t0, 1),
    }
    with open(OUT if not args.seeds_only
              else OUT.replace(".json", "_seedsonly.json"),
              "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    try:
        _say(f"\n共 {out['总耗时秒']}s")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
