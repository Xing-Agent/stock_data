#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 老池 45 条链 · 可比口径重跑 —— 2026-11-02

★★★ 三秒版(为什么又跑一遍):
    上一轮(1031)那 45 条是 **10-31 11:22** 跑完的,
    而「退化 R」的修复是同一天 **14:25** 才提交(commit 95e293b)。
    → 那 45 条是**修好之前**的数;考卷(1,042 只)用的是**修好之后**的 engine。
      两把尺子不一样 → 差值没意义。
    ★ 本轮**一行代码、一个参数都不改**,只是用现在这一版 engine 重跑一遍,
      让老池和考卷能用同一把尺子量。

★★★ 和 1031 那份脚本的差别(★ 只有这几处,全是路径/诊断,不碰口径):
    ① 输出改到 probe/bench1_rerun_1102/(不覆盖 1031)
    ② 跑前 + 跑完各核一次 **133 个题目文件的指纹**(对不上就停)
    ③ 每条链多记一个诊断:真链 / 对照组各有几笔 `r_degenerate == True`
       —— ★ 这是本轮要回答的第三个问题,只读不改。
    ★ 其余(45 条链名单 · 研发池 198 只 · 50 个写死种子 · ±5% 容差 ·
      对照组同池 · 大+中口径)一字未动,直接复用 1031 的脚本。

★ 原脚本的说明照原样留在下面 ——————————————————————————————

三秒版:基准一 =「真信号每笔 R − 同环境随机进场每笔 R」。
        它的前提是「对照组出手次数和真链一样多」。
        本轮:容差 ±5% 硬断言 · 50 个写死种子 · 对照组和真链同池 ·
        ★★★ **只在研发池(198 只)上跑,留出池(49 只)一笔都不许进。**

★★ engine 的五处修复在上一轮已改完并提交(commit ec833c2),本脚本只负责跑。
   ★ 已 grep 确认:BenchmarkPremiseBroken / CONTROL_TOL=0.05 /
     CONTROL_SEEDS(50) / 两段校准 / evaluate 的 n_random_seeds=50 全部在位,
     自生成种子那条路(20181001 + 977*k)已删。

★★★ 本脚本自己做两件 engine 没做的事:
   ① **把池子口径加给对照组** —— `random_entry_benchmark` 内部
      `chain.run_chain(..., m=None)` 会自己 build 矩阵拿到全池;
      旧的 45 个基准一就是这么来的(真链在大+中、对照在全池含小微盘),
      ★ 而小票是净利润主要来源 → 对照组成绩天然被撑高。
      ★ 上一轮注释里承诺的 `_patched` 实测不存在,所以在这里包一层。
   ② **把研发池口径加给所有 run_chain** —— 留出池不许进 universe,
      并且**每条链都断言一次**:成交流水里不许出现任何留出池里的票。

★★ 跑批纪律(今天为这几件各丢过一次跑批):
   ① 不用 `nohup … &`(实测子进程几分钟后被杀且没有 traceback)—— 用正式后台机制
   ② 可续跑:每条链跑完立刻 dump 一份 JSON;重跑跳过已有结果
   ③ 先 --limit 2/3 量耗时,把总时间估出来再开全量
   ④ **先写盘再打印**;所有 print 包在 try 里

跑法:
   python3 probe/bench1_rerun_1102/run_bench1_1102.py --limit 3   # 量耗时
   python3 probe/bench1_rerun_1102/run_bench1_1102.py             # 全量(可续跑)
   ★★★ 不要用 --only 做部分重跑 —— 上一轮踩过:45 条的全量汇总被静默
      覆盖成只有 3 条。本轮直接把 --only 删掉了。
"""
from __future__ import annotations

import argparse
import copy
import hashlib
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
#: ★ 1031 那一轮的目录 —— gate_roster_1031 / holdout_1031 都在那里,★ 原样复用
B1031 = os.path.join(ROOT, "probe", "bench1_rerun_1031")
for p in (ROOT, V2, B1031, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import (analyze, cache, chain, data, matrices, ops_exits_1029,  # noqa: E402
                    pat6_ops, pool_scope, stats_gate)
import rerun_core_1030 as RC                                               # noqa: E402
import gate_roster_1031 as GR                                              # noqa: E402

CONFIG_DIR = os.path.join(ROOT, "engine", "configs")
OLD_BENCH = os.path.join(V2, "bench_two_1030.json")
OLD_RERUN = os.path.join(V2, "rerun_results_1030.json")
#: ★★★ 留出池/研发池名单**原样用 1031 那一份** —— 同一套池子才可比
HOLDOUT_JSON = os.path.join(B1031, "holdout_1031.json")
#: ★ 1031 的逐链结果 —— 本轮只读它来做「修复前 vs 修复后」的对照
B1031_JSON = os.path.join(B1031, "bench1_rerun_1031.json")

PER_CHAIN = os.path.join(HERE, "per_chain")
LEDGERS = os.path.join(HERE, "ledgers_1102")
OUT = os.path.join(HERE, "bench1_rerun_1102.json")

# ══════════════════════════════════════════════════════════════════════════
# ★★★ 第 0 步 · 核题目指纹(133 个文件)—— 对不上就停,整轮作废
#   ★ 拼法与 probe/exam_run_1102/run_exam_1102.py 完全一致(抄的同一段)
# ══════════════════════════════════════════════════════════════════════════

FINGERPRINT_JSON = os.path.join(ROOT, "手册", "V2题目指纹-20261101.json")
EXPECT_FP = "ea289aba709287e33b761f55b569c171cdac0e06b5e87d0b4399e51408c39ee6"


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def verify_fingerprint() -> dict:
    """★ 重算 133 个题目文件的 SHA-256,按文件名排序拼 hex 再 SHA-256。

    -> 诊断 dict。对不上 **raise**(调用方不要接)。
    """
    with open(FINGERPRINT_JSON, encoding="utf-8") as fh:
        man = json.load(fh)
    entries = man["逐份"]
    if len(entries) != man["文件数"]:
        raise RuntimeError(f"★ 指纹清单自己对不上:{len(entries)} ≠ {man['文件数']}")
    missing, mismatch, actual = [], [], {}
    for e in entries:
        p = os.path.join(ROOT, e["file"])
        if not os.path.exists(p):
            missing.append(e["file"])
            continue
        a = _sha256_file(p)
        actual[e["file"]] = a
        if a != e["sha256"]:
            mismatch.append({"file": e["file"], "清单": e["sha256"], "实算": a})
    if missing or mismatch:
        raise RuntimeError(
            f"★★★ 题目被动过 —— 缺 {len(missing)} 个 / 对不上 {len(mismatch)} 个。"
            f"缺:{missing[:5]} 对不上:{[m['file'] for m in mismatch][:5]}"
            " —— ★ 整轮作废,停。")
    agg = hashlib.sha256()
    for name in sorted(actual):
        agg.update(actual[name].encode())
    got = agg.hexdigest()
    if got != EXPECT_FP:
        raise RuntimeError(f"★★★ 汇总指纹对不上:{got} ≠ {EXPECT_FP} —— 停。")
    return {
        "汇总指纹": got,
        "是否一致": got == EXPECT_FP,
        "核了多少个文件": len(entries),
        "逐份全部一致": True,
        "拼法": "逐份 sha256 的 hex,按文件名排序直接拼接,再 sha256",
    }


def _degen_counts(df) -> dict:
    """★ 只读诊断:这份流水里有几笔是退化 R(r_degenerate == True)。

    ★ 修复前的流水没有这一列 —— 那种情况返回「没有这一列」,不许瞎补。
    """
    try:
        n = int(len(df))
        if n == 0:
            return {"笔数": 0, "退化R笔数": 0, "有r_degenerate列": "空流水"}
        if "r_degenerate" not in df.columns:
            return {"笔数": n, "退化R笔数": None, "有r_degenerate列": False}
        col = df["r_degenerate"].astype(bool)
        return {
            "笔数": n,
            "退化R笔数": int(col.sum()),
            "退化R占比": float(col.mean()),
            "有r_degenerate列": True,
        }
    except Exception:
        return {"★数退化R出错": traceback.format_exc(limit=3)}

#: ★ chain_list() 填:被闸挡下、没进「逐链」的链(连理由)
BLOCKED_ROSTER: list[dict] = []

N_SEEDS = 50
SCOPE = "large_mid"

#: ★ 止损槽位的全部别名(照抄 engine/checks/four_slot_complete.py 的 SLOTS["止损"])
STOP_ALIASES = ("initial_stop", "stop_init", "stop_initial", "初始止损",
                "trailing_stop", "stop_trail", "stop_trailing", "移动止损")

#: ★★★ 「等价于不设止损」的第二种写法 —— 2026-10-31 实测新查出来的第 28 处
#   `buy_and_hold.yaml` 的 initial_stop 不是 `type: none`,而是
#   `{type: pct, params: {pct: 0.999}}`,它自己的 source 写着「等价于不设止损」。
#   ★ 机械地问「有没有止损」会答「有」→ 会把它漏出无止损名单。
#   ★ 判据:pct 型止损,pct ≥ 这个阈值 = 等价于不设。
EQUIV_NO_STOP_PCT = 0.90

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
# 一 · 留出池 / 研发池
# ══════════════════════════════════════════════════════════════════════════

def load_pools() -> tuple[list[str], set[str], dict]:
    with open(HOLDOUT_JSON, encoding="utf-8") as fh:
        d = json.load(fh)
    dev = list(d["研发池名单"])
    hold = set(d["留出池名单"])
    if set(dev) & hold:
        raise RuntimeError("★ 研发池和留出池有交集,停")
    return dev, hold, d


# ══════════════════════════════════════════════════════════════════════════
# 二 · 把「大+中口径」加给**所有** run_chain(含对照组)
# ══════════════════════════════════════════════════════════════════════════

_ORIG_RUN_CHAIN = chain.run_chain


def _scoped_run_chain(cfg, symbols=None, start=data.PERF_START, end=data.PERF_END,
                      initial_equity=1_000_000.0, m=None,
                      flat_friction_bps=None, total_return=None):
    """m 没给时自己 build 并把大+中口径与进 universe —— ★ 对照组也走这条路。

    ★ 研发池口径是通过**传进来的 symbols 本身**实现的(调用方只传 198 只),
      `random_entry_benchmark` 会把 symbols 原样传下来,所以对照组同样只在研发池上。
    """
    if m is None:
        m = matrices.build(cfg.raw, symbols)
        RC.apply_scope(m, SCOPE)
    return _ORIG_RUN_CHAIN(cfg, symbols, start, end, initial_equity, m=m,
                           flat_friction_bps=flat_friction_bps,
                           total_return=total_return)


# ══════════════════════════════════════════════════════════════════════════
# 三 · 旧值 / 链表
# ══════════════════════════════════════════════════════════════════════════

def old_bench1() -> dict[str, dict]:
    d = json.load(open(OLD_BENCH, encoding="utf-8"))
    return {r["链"]: r for r in d["逐链"]}


def bench1_1031() -> dict[str, dict]:
    """★ 1031 那一轮(= 退化 R **修复前**)的逐链结果,按链名索引。"""
    d = json.load(open(B1031_JSON, encoding="utf-8"))
    return {r["链"]: r for r in d["逐链"]}


#: ★★★ 闸门判据只有**一份**,在 gate_roster_1031 里(它自己 import 时自测)。
#   ★ 以前这里抄了一份 bench_two_1030.gates_pass —— 抄两份就是排查报告 §五
#     那张「同一样东西两种写法」表上的第 12 行。现在两边都走同一份。
gates_pass = GR.gates_pass


def chain_list() -> list[tuple]:
    prev = json.load(open(OLD_RERUN, encoding="utf-8"))
    prows = [r for r in prev["逐链"] if "★跑不了" not in r]
    GR.selftest(prows)
    keep = {r["链"] for r in prows if gates_pass(r)}
    # ★★★ 被挡下的链**不许悄悄消失** —— 名单和理由一起写进结果 JSON,
    #   由 make_tables_1031 的「表五」逐条印出来。
    global BLOCKED_ROSTER
    BLOCKED_ROSTER = [{"链": r["链"], **GR.verdict(r)}
                      for r in prows if not gates_pass(r)]
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
    return label.replace("/", "_").replace(" ", "")


def no_stop(raw: dict) -> tuple[bool, str]:
    """★ 从**配置本体**判「有没有止损」,不按链名猜。

    -> (是否无止损, 怎么判的)。★ 无止损 → 1R = 进场价 → R 退化成收益率,
       **不能和有止损的链放一列排序**。
    """
    reasons = []
    for k in STOP_ALIASES:
        v = raw.get(k)
        if isinstance(v, dict):
            t = (v.get("type") or "").strip().lower()
            if v.get("stages") or v.get("rules"):
                return False, f"{k} 有 stages/rules"
            if t and t != "none":
                # ★ 第二种写法:pct 型但 pct 大到等价于不设
                if t == "pct":
                    pct = ((v.get("params") or {}).get("pct"))
                    try:
                        if pct is not None and float(pct) >= EQUIV_NO_STOP_PCT:
                            reasons.append(
                                f"{k} 写的是 pct={pct}(≥{EQUIV_NO_STOP_PCT})"
                                f" → ★ 等价于不设止损,但写法不是 type: none")
                            continue
                    except (TypeError, ValueError):
                        pass
                return False, f"{k}.type = {t}"
        elif v:
            return False, f"{k} 非空"
    return True, ("、".join(reasons) if reasons
                  else "止损槽位全是 type: none 或缺失")


# ══════════════════════════════════════════════════════════════════════════
# 四 · 一条链
# ══════════════════════════════════════════════════════════════════════════

def run_one(label: str, yml: str, ov, group: str, dev: list[str],
            hold: set[str], old: dict, prev: dict | None = None) -> dict:
    t = time.time()
    with open(os.path.join(CONFIG_DIR, yml), encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if ov is not None:
        raw = ov(copy.deepcopy(raw))
    cfg = chain.ChainConfig.from_dict(raw)
    ns, ns_why = no_stop(raw)

    # ---- 真链:研发池 × 大+中口径
    m = matrices.build(cfg.raw, dev)
    scope_diag = RC.apply_scope(m, SCOPE)
    res = _ORIG_RUN_CHAIN(cfg, dev, data.PERF_START, data.PERF_END, m=m)
    led = res.ledger

    # ★★★ 硬断言:留出池一笔都不许进(纪律④「不许为了顺便看一眼而破坏它」)
    if len(led):
        leaked = sorted(set(led["symbol"].astype(str)) & hold)
        if leaked:
            raise RuntimeError(f"★★★ 留出池漏进来了 {len(leaked)} 只:{leaked[:10]}")

    # ---- 基准一
    err = None
    b1 = None
    try:
        b1 = analyze.random_entry_benchmark(cfg, res, dev, data.PERF_START,
                                            data.PERF_END, n_seeds=N_SEEDS,
                                            keep_ledger=True)
    except analyze.BenchmarkPremiseBroken as e:
        err = {"类": "BenchmarkPremiseBroken", "说明": str(e)}

    o = old.get(label, {}).get("★基准一_同环境随机进场") or {}
    old_b1 = o.get("★真信号每笔R − 随机进场每笔R")

    rec: dict = {
        "链": label, "族": group, "配置": yml,
        "池子口径": SCOPE,
        "★跑在哪个池": f"研发池 {len(dev)} 只(留出池 {len(hold)} 只已排除)",
        "对照组是否同池": True,
        "★无止损_R退化成收益率_不可和有止损同列排序": ns,
        "★无止损_怎么判的": ns_why,
        "笔数": int(len(led)),
        "旧笔数(全大中池)": old.get(label, {}).get("笔数"),
        "合格进场信号(entry&universe)": int((m.entry & m.universe).sum()),
        "每笔净R": (float(np.nanmean(led["r_multiple_net"].astype(float)))
                    if len(led) else None),
        "每笔毛R": (float(np.nanmean(led["r_multiple"].astype(float)))
                    if len(led) else None),
        "种子数": N_SEEDS,
        "旧基准一(作废·仅用于看污染有多大)": old_b1,
        "旧对照笔数": o.get("随机进场_校准后对照笔数"),
        "旧对照笔数偏差": ((o["随机进场_校准后对照笔数"] - o["随机进场_真链笔数"])
                           / o["随机进场_真链笔数"]
                           if o.get("随机进场_真链笔数") else None),
        "旧种子数": o.get("随机进场_种子数"),
        "universe收窄": scope_diag,
        # ★★★ 本轮新增的唯一诊断:真链这边有没有退化 R(实测,不引用上一轮的说法)
        "★真链退化R": _degen_counts(led),
    }

    if err is not None:
        # ★★★ 前提破了 → 这条链的基准一**不出数**(禁止下游计算和渲染)
        rec["★基准一"] = None
        rec["★对照笔数偏差"] = None
        rec["★前提破了_禁止下游"] = err
        rec["★和旧值的差"] = None
        rec["★符号是否翻转"] = None
    else:
        pool = b1.pop("★对照流水并池", None)
        rec["★基准一"] = {k: (None if isinstance(v, float) and not np.isfinite(v)
                              else v) for k, v in b1.items()}
        new_b1 = rec["★基准一"].get("★真信号每笔R − 随机进场每笔R")
        rec["★对照笔数偏差"] = rec["★基准一"].get("★对照笔数偏差")
        rec["★新基准一值"] = new_b1
        if new_b1 is not None and old_b1 is not None:
            rec["★和旧值的差"] = new_b1 - old_b1
            rec["★符号是否翻转"] = bool((new_b1 > 0) != (old_b1 > 0))
        else:
            rec["★和旧值的差"] = None
            rec["★符号是否翻转"] = None
        # ---- 判据 Z(用这 50 个种子的并池对照流水当零分布)
        try:
            v = analyze.bootstrap_on_ledger(res, pool_ledger=pool)
            rec["★判据Z_用50种子并池对照"] = {
                k: (float(r.z_effect) if np.isfinite(r.z_effect) else None)
                for k, r in v.results.items()}
        except Exception:
            rec["★判据Z_用50种子并池对照"] = None
            rec["★判据Z_出错"] = traceback.format_exc(limit=3)
        if pool is not None and not pool.empty:
            leaked = sorted(set(pool["symbol"].astype(str)) & hold)
            if leaked:
                raise RuntimeError(f"★★★ 对照组漏进留出池 {len(leaked)} 只:{leaked[:10]}")
            # ★★★ 本轮新增的唯一诊断之二:对照组(50 个种子并池)里有几笔退化 R
            rec["★对照组退化R_50种子并池"] = _degen_counts(pool)
            os.makedirs(LEDGERS, exist_ok=True)
            pool.to_csv(os.path.join(LEDGERS,
                                     f"CTRL__{safe_name(label)}.csv"), index=False)
        else:
            rec["★对照组退化R_50种子并池"] = {"★没拿到并池流水": True}

    # ---- ★ 和 1031(退化 R 修复**前**)逐条对照 —— 只读,不参与任何计算口径
    p = (prev or {}).get(label) or {}
    if p:
        d: dict = {
            "1031笔数": p.get("笔数"),
            "1031每笔净R": p.get("每笔净R"),
            "1031基准一": p.get("★新基准一值"),
            "1031对照笔数偏差": p.get("★对照笔数偏差"),
            "1031种子数": p.get("种子数"),
        }
        n_now = rec.get("★新基准一值")
        d["笔数差"] = ((rec["笔数"] - p["笔数"]) if p.get("笔数") is not None
                       else None)
        if rec.get("每笔净R") is not None and p.get("每笔净R") is not None:
            d["每笔净R差"] = rec["每笔净R"] - p["每笔净R"]
        if n_now is not None and p.get("★新基准一值") is not None:
            d["基准一差"] = n_now - p["★新基准一值"]
            d["★基准一符号是否翻转(1031→1102)"] = bool(
                (n_now > 0) != (p["★新基准一值"] > 0))
        else:
            d["基准一差"] = None
            d["★基准一符号是否翻转(1031→1102)"] = None
        rec["★对1031(修复前)"] = d
    else:
        rec["★对1031(修复前)"] = {"★1031里没有这条链": True}

    os.makedirs(LEDGERS, exist_ok=True)
    led.to_csv(os.path.join(LEDGERS, f"REAL__{safe_name(label)}.csv"), index=False)

    rec["耗时秒"] = round(time.time() - t, 1)
    rec["峰值RSS_MB"] = round(_rss_mb(), 1)
    return rec


# ══════════════════════════════════════════════════════════════════════════
# 五 · main
# ══════════════════════════════════════════════════════════════════════════

def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条(量耗时用)")
    # ★★★ 故意**不提供** --only:上一轮用它做部分重跑,45 条的全量汇总
    #   被静默覆盖成只有 3 条。要补跑就靠 per_chain/ 的可续跑机制。
    args = ap.parse_args()

    os.makedirs(PER_CHAIN, exist_ok=True)
    dev, hold, hjson = load_pools()

    # ---- ★★★ 第 0 步:核题目指纹(对不上直接抛,不接)
    fp_before = verify_fingerprint()

    try:
        _say(subprocess.run(["free", "-m"], capture_output=True, text=True).stdout)
        _say(f"CPU 核数 {os.cpu_count()} · 串行单进程 · 种子 {N_SEEDS} · "
             f"容差 ±{analyze.CONTROL_TOL:.0%} · 口径 {SCOPE}")
        _say(f"★ 研发池 {len(dev)} 只 · 留出池 {len(hold)} 只(本轮一笔都不跑)")
    except Exception:
        pass

    chain.run_chain = _scoped_run_chain       # ★ 对照组也进大+中 + 研发池
    pat6_ops.install()
    ops_exits_1029.install()

    old = old_bench1()
    prev = bench1_1031()          # ★ 1031 = 退化 R 修复**前**
    variants = chain_list()
    if args.limit:
        variants = variants[:args.limit]
    _say(f"★ 本轮要跑 {len(variants)} 条\n")

    rows, t0 = [], time.time()
    for i, (label, yml, ov, group) in enumerate(variants, 1):
        dst = os.path.join(PER_CHAIN, f"{safe_name(label)}.json")
        if os.path.exists(dst):                       # ★ 纪律②:可续跑
            try:
                rows.append(json.load(open(dst, encoding="utf-8")))
                _say(f"[{i}/{len(variants)}] 跳过(已有结果) {label[:60]}")
            except Exception:
                os.remove(dst)
            else:
                continue
        try:
            rec = run_one(label, yml, ov, group, dev, hold, old, prev)
        except Exception:
            rec = {"链": label, "族": group, "配置": yml,
                   "★跑不了": traceback.format_exc(limit=8)}
        # ★★ 纪律④:**先写盘**,再打印
        with open(dst, "w", encoding="utf-8") as fh:
            json.dump(rec, fh, ensure_ascii=False, indent=1, default=str)
        rows.append(rec)
        try:
            _say(f"[{i}/{len(variants)}] {label[:50]:50s} "
                 f"{rec.get('笔数', 0):5d}笔 "
                 f"基准一={rec.get('★新基准一值')} "
                 f"对照偏差={rec.get('★对照笔数偏差')} "
                 f"翻转={rec.get('★符号是否翻转')} "
                 f"{rec.get('耗时秒')}s RSS{rec.get('峰值RSS_MB')}MB"
                 + ("  ★前提破了" if rec.get("★前提破了_禁止下游") else "")
                 + ("  ★跑不了" if rec.get("★跑不了") else ""))
        except Exception:
            pass

    ok = [r for r in rows if r.get("★新基准一值") is not None]
    broke = [r for r in rows if r.get("★前提破了_禁止下游")]
    crash = [r for r in rows if r.get("★跑不了")]
    flip = [r for r in ok if r.get("★符号是否翻转")]
    nostop = [r for r in rows
              if r.get("★无止损_R退化成收益率_不可和有止损同列排序")]

    # ---- ★★★ 本轮三个问题的汇总(全部实测,★ 不引用上一轮的说法)
    def _dg(r, key):
        v = (r.get(key) or {}).get("退化R笔数")
        return v if isinstance(v, int) else None

    real_dg = {r["链"]: _dg(r, "★真链退化R") for r in rows}
    ctrl_dg = {r["链"]: _dg(r, "★对照组退化R_50种子并池") for r in rows}
    real_hit = {k: v for k, v in real_dg.items() if v}
    ctrl_hit = {k: v for k, v in ctrl_dg.items() if v}
    flip_1031 = [r["链"] for r in rows
                 if (r.get("★对1031(修复前)") or {})
                 .get("★基准一符号是否翻转(1031→1102)")]

    out = {
        "口径戳": pool_scope.stamp(SCOPE, {
            "本轮做法": "★★★ 老池 45 条链 · 可比口径重跑(退化 R 修复**后**的 engine)"
                        " —— 容差 ±5% 硬断言 · 50 个写死种子 · 对照组同池 · "
                        "★ 只在研发池上跑。★★★ 代码与参数一行未改。",
            "种子来源": "analyze.CONTROL_SEEDS[:50] —— ★ 只有这一条路",
            "容差": analyze.CONTROL_TOL,
            "★研发池只数": len(dev),
            "★留出池只数": len(hold),
            "★留出池名单文件": hjson.get("★★★留出池名单文件"),
            "★留出池SHA256": hjson.get("★★★SHA-256"),
            "★留出池里其实已经跑过的只数": hjson.get("★★★留出池里其实已经跑过的只数"),
            "覆盖": f"{len(variants)} 条(= bench_two_1030 那 45 条的同一口径)",
        }),
        "汇总": {
            "链数": len(rows),
            "算出基准一的": len(ok),
            "★前提破裂_算不出基准一的": len(broke),
            "跑不了的": len(crash),
            "★符号翻转的": len(flip),
            "符号翻转名单": [r["链"] for r in flip],
            "前提破裂名单": [r["链"] for r in broke],
            "跑不了名单": [r["链"] for r in crash],
            "★对照笔数偏差_最大绝对值": (
                max(abs(r["★对照笔数偏差"]) for r in ok) if ok else None),
            "★无止损(R退化成收益率)的链数": len(nostop),
            "★无止损名单(不可和有止损同列排序)": [
                {"链": r["链"], "怎么判的": r.get("★无止损_怎么判的")}
                for r in nostop],
            # ---- ★★★ 本轮要回答的三个问题
            "★★★真链退化R_有几条链出现": len(real_hit),
            "★★★真链退化R_总笔数": sum(real_hit.values()),
            "★★★真链退化R_名单": real_hit,
            "★对照组退化R_有几条链出现": len(ctrl_hit),
            "★对照组退化R_总笔数": sum(ctrl_hit.values()),
            "★对照组退化R_名单": ctrl_hit,
            "★★★相对1031(修复前)符号翻转的条数": len(flip_1031),
            "★★★相对1031(修复前)符号翻转名单": flip_1031,
        },
        "★题目指纹_跑前": fp_before,
        "逐链": rows,
        # ★★★ 被闸挡下、没进「逐链」的链 —— 连理由一起留下,不许悄悄消失
        "★被闸挡下_不出数的链": BLOCKED_ROSTER,
        "总耗时秒": round(time.time() - t0, 1),
    }
    # ---- ★ 跑完再核一遍指纹(★★ 变了 → 整轮作废,但**先把结果写盘**再抛)
    try:
        out["★题目指纹_跑后"] = verify_fingerprint()
    except Exception:
        out["★题目指纹_跑后"] = {"★★★跑完核指纹不通过_整轮作废":
                                 traceback.format_exc(limit=5)}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    try:
        _say(f"\n共 {out['总耗时秒']}s · 算出 {len(ok)} · 前提破 {len(broke)} · "
             f"跑不了 {len(crash)} · 翻转 {len(flip)}")
        _say(f"★ 指纹(跑前)={fp_before['汇总指纹']} 一致={fp_before['是否一致']}")
        _say(f"★ 指纹(跑后)={out['★题目指纹_跑后'].get('汇总指纹')} "
             f"一致={out['★题目指纹_跑后'].get('是否一致')}")
        _say(f"★★★ 真链退化 R:{len(real_hit)} 条链 / "
             f"{sum(real_hit.values())} 笔 · 对照组:{len(ctrl_hit)} 条链 / "
             f"{sum(ctrl_hit.values())} 笔")
        _say(f"★★★ 相对 1031(修复前)符号翻转:{len(flip_1031)} 条")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
