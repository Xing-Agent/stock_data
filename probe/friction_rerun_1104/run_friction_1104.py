#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 摩擦口径统一(三档)· 研发池 45 条链重跑 —— 2026-11-04

★★★ 三秒版(为什么又跑一遍):
    配置里的摩擦从「一刀切单边 5bp」换成了「按流动性分三档 5 / 15 / 30bp」
    (commit 55088733,★ engine 代码零改动,只改 yaml)。
    → 这一轮只干一件事:用**同一份 engine、同一套口径、同一套种子**把
      `probe/bench1_rerun_1102/` 那 45 条链再跑一遍,
      ★★★ 去验证《手册 23》预先登记里写死的两条可伪证的预言。

★★★ 和 1102 那份脚本的差别(★ 逐条列全,全是路径/诊断,★★ 口径一个字没动):
    ① 输出改到 probe/friction_rerun_1104/(不覆盖 1102)
    ② ★★★ 指纹检查改了口径 —— **必须改**,理由写死在这里:
       1102 用的是「133 个题目文件的汇总指纹」,而这一轮**故意改了 39 份配置**,
       那个汇总指纹必然对不上。
       ★ 所以拆成两个:
         · **engine 代码指纹**(133 份里不在 engine/configs 下的 83 份)
           → ★★★ 逐份 sha256 必须和《V2题目指纹-20261101.json》**一字不差**,
             对不上就 raise,整轮作废。(代码零改动 → 这一条必须过)
         · **configs 指纹**(engine/configs 下的 50 份)
           → ★ 跑前跑后各记一次;改前的值从 git `55088733^` 现算,
             ★★ 不信任提交信息里那个数(见 README 的留痕第 1 条)。
    ③ 每条链多记四个只读诊断(本轮对照表要用):
       净盈亏(美元)= sum(net_pnl) · 摩擦总额 = sum(friction_cost) ·
       名义金额 = sum(notional_in + notional_out) · 三档笔数分布
       —— ★ 真链和对照组各记一份。
    ④ 把「对 1031」那一段换成「对 1102」(同一个写法,只换数据源)
    ★ 其余(45 条链名单 · 研发池 198 只 · 50 个写死种子 · ±5% 容差 ·
      对照组同池 · 大+中口径 · 绩效窗口)**一字未动**,直接复用 1102 的脚本。

★★★ 铁律(写死在脚本里,不靠人记):
    · **只在研发池(198 只)跑**;留出池 49 只一笔不许进(硬断言,原样保留)
    · **考卷(exam_1042,封存段)一次都不跑、不读** —— 本脚本不 import、不打开任何
      exam_* 路径;★ 全文出现 "exam" 的地方只有本行这段说明(可 grep 核)
    · **engine/ 下一个字节都不许改** —— 本脚本只读 engine,并在跑前跑后核代码指纹

跑法:
   python3 probe/friction_rerun_1104/run_friction_1104.py --limit 3   # 量耗时
   python3 probe/friction_rerun_1104/run_friction_1104.py             # 全量(可续跑)
   ★★★ 不提供 --only(1031 踩过:全量汇总被静默覆盖成 3 条)
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
B1102 = os.path.join(ROOT, "probe", "bench1_rerun_1102")
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
#: ★★★ 改前的逐链结果 = 1102 那一轮(★ 只读,不重跑)
B1102_JSON = os.path.join(B1102, "bench1_rerun_1102.json")
#: ★ 改前的流水 —— ★★ 1102 的汇总 JSON 里**没有**美元数(净盈亏/摩擦总额),
#   所以那两列只能从 1102 的流水现算。★★★ 这是读,不是重跑。
B1102_LEDGERS = os.path.join(B1102, "ledgers_1102")

PER_CHAIN = os.path.join(HERE, "per_chain")
LEDGERS = os.path.join(HERE, "ledgers_1104")
OUT = os.path.join(HERE, "friction_rerun_1104.json")

# ══════════════════════════════════════════════════════════════════════════
# ★★★ 第 0 步 · 指纹:engine 代码(硬停)+ configs(记账)
# ══════════════════════════════════════════════════════════════════════════

FINGERPRINT_JSON = os.path.join(ROOT, "手册", "V2题目指纹-20261101.json")
#: ★ 改前的 commit —— configs 的「改前指纹」从它现算
BEFORE_COMMIT = "55088733^"

#: ★★★ 指纹拼法(写死,★ 自己定的,因为提交信息里那个 16 位数的拼法没留在库里)
FP_RECIPE = ("逐份 sha256;按**仓库相对路径**排序;每份拼成 '<path>:<sha256>\\n';"
             "整串 sha256 后取前 16 位 hex")


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def _digest(pairs: dict) -> str:
    """pairs: {仓库相对路径: sha256hex} -> 16 位 hex。★ 拼法见 FP_RECIPE。"""
    h = hashlib.sha256()
    for k in sorted(pairs):
        h.update(f"{k}:{pairs[k]}\n".encode())
    return h.hexdigest()[:16]


def _manifest_split() -> tuple[dict, dict]:
    """《V2题目指纹》133 份拆成 (engine 代码 83 份, configs 50 份) 的登记值。"""
    with open(FINGERPRINT_JSON, encoding="utf-8") as fh:
        man = json.load(fh)
    entries = man["逐份"]
    if len(entries) != man["文件数"]:
        raise RuntimeError(f"★ 指纹清单自己对不上:{len(entries)} ≠ {man['文件数']}")
    code = {e["file"]: e["sha256"] for e in entries
            if not e["file"].startswith("engine/configs/")}
    cfg = {e["file"]: e["sha256"] for e in entries
           if e["file"].startswith("engine/configs/")}
    return code, cfg


def verify_code_fingerprint() -> dict:
    """★★★ engine 代码必须一字不差(本轮承诺「engine 零改动」)。对不上 **raise**。"""
    reg_code, _ = _manifest_split()
    missing, mismatch, actual = [], [], {}
    for f, want in reg_code.items():
        p = os.path.join(ROOT, f)
        if not os.path.exists(p):
            missing.append(f)
            continue
        a = _sha256_file(p)
        actual[f] = a
        if a != want:
            mismatch.append({"file": f, "登记": want, "实算": a})
    if missing or mismatch:
        raise RuntimeError(
            f"★★★ engine 代码被动过 —— 缺 {len(missing)} 个 / 对不上 "
            f"{len(mismatch)} 个:缺{missing[:5]} 变{[m['file'] for m in mismatch][:5]}"
            " —— ★ 整轮作废,停。")
    return {
        "范围": "《V2题目指纹-20261101.json》133 份里不在 engine/configs 下的那些",
        "文件数": len(reg_code),
        "逐份与登记值全部一致": True,
        "指纹": _digest(actual),
        "登记值重算出的指纹": _digest(reg_code),
        "拼法": FP_RECIPE,
    }


def configs_fingerprint() -> dict:
    """★ configs 的指纹:改后(工作区)· 改前(git 55088733^)· 登记值(11-01 冻结)。

    ★★ 不 raise —— 这一轮**就是故意改它**。只记账 + 报哪几份变了。
    """
    _, reg_cfg = _manifest_split()
    now, before = {}, {}
    for f in reg_cfg:
        p = os.path.join(ROOT, f)
        now[f] = _sha256_file(p) if os.path.exists(p) else "★不存在"
        r = subprocess.run(["git", "-C", ROOT, "show", f"{BEFORE_COMMIT}:{f}"],
                           capture_output=True)
        before[f] = (hashlib.sha256(r.stdout).hexdigest()
                     if r.returncode == 0 else "★取不到")
    changed = sorted(f for f in reg_cfg if now[f] != before[f])
    # ★ 顺手实测登记里那两句:现在显式三档几份、还写 one_way_bps 几份
    tiers, flat, neither = [], [], []
    for f in sorted(reg_cfg):
        raw = yaml.safe_load(open(os.path.join(ROOT, f), encoding="utf-8")) or {}
        c = (raw.get("costs") or {})
        if "friction_tiers" in c:
            tiers.append(f)
        elif "one_way_bps" in c:
            flat.append(f)
        else:
            neither.append(f)
    return {
        "文件数": len(reg_cfg),
        "★指纹_改前(git 55088733^ 现算)": _digest(before),
        "★指纹_改后(工作区)": _digest(now),
        "★指纹_11-01冻结登记值": _digest(reg_cfg),
        "改前改后不同的份数": len(changed),
        "改前改后不同的名单": changed,
        "★显式写 friction_tiers 的份数": len(tiers),
        "★还写 one_way_bps 的份数": len(flat),
        "★还写 one_way_bps 的名单": flat,
        "★两个字段都没写(靠默认值)的份数": len(neither),
        "★两个字段都没写的名单": neither,
        "拼法": FP_RECIPE,
    }


# ══════════════════════════════════════════════════════════════════════════
# ★ 本轮新增的只读诊断:美元口径的四个数
# ══════════════════════════════════════════════════════════════════════════

def _money(df) -> dict:
    """★ 只读诊断:这份流水的净盈亏 / 摩擦总额 / 名义金额 / 三档笔数分布。

    ★★ 缺列就写「没有这一列」,★★★ 不许瞎补、不许估。
    """
    try:
        n = int(len(df))
        if n == 0:
            return {"笔数": 0, "净盈亏": 0.0, "摩擦总额": 0.0, "名义金额": 0.0,
                    "三档笔数": {}, "★空流水": True}
        out: dict = {"笔数": n}
        for key, col in (("净盈亏", "net_pnl"), ("摩擦总额", "friction_cost"),
                         ("毛盈亏", "gross_pnl")):
            out[key] = (float(pd.to_numeric(df[col], errors="coerce").sum())
                        if col in df.columns else None)
            if col not in df.columns:
                out[f"★没有{col}列"] = True
        if {"notional_in", "notional_out"} <= set(df.columns):
            out["名义金额"] = float(
                pd.to_numeric(df["notional_in"], errors="coerce").sum()
                + pd.to_numeric(df["notional_out"], errors="coerce").sum())
        else:
            out["名义金额"] = None
            out["★没有notional列"] = True
        out["每笔净R"] = (float(np.nanmean(df["r_multiple_net"].astype(float)))
                          if "r_multiple_net" in df.columns else None)
        out["三档笔数"] = (df["liquidity_tier"].value_counts().to_dict()
                           if "liquidity_tier" in df.columns else {})
        out["单边bps取值"] = (sorted(set(
            pd.to_numeric(df["friction_bps"], errors="coerce").dropna().tolist()))
            if "friction_bps" in df.columns else None)
        return out
    except Exception:
        return {"★算美元数出错": traceback.format_exc(limit=3)}


def _degen_counts(df) -> dict:
    """★ 只读诊断(1102 原样保留):这份流水里有几笔是退化 R。"""
    try:
        n = int(len(df))
        if n == 0:
            return {"笔数": 0, "退化R笔数": 0, "有r_degenerate列": "空流水"}
        if "r_degenerate" not in df.columns:
            return {"笔数": n, "退化R笔数": None, "有r_degenerate列": False}
        col = df["r_degenerate"].astype(bool)
        return {"笔数": n, "退化R笔数": int(col.sum()),
                "退化R占比": float(col.mean()), "有r_degenerate列": True}
    except Exception:
        return {"★数退化R出错": traceback.format_exc(limit=3)}


#: ★ chain_list() 填:被闸挡下、没进「逐链」的链(连理由)
BLOCKED_ROSTER: list[dict] = []

N_SEEDS = 50
SCOPE = "large_mid"

#: ★ 止损槽位的全部别名(照抄 engine/checks/four_slot_complete.py 的 SLOTS["止损"])
STOP_ALIASES = ("initial_stop", "stop_init", "stop_initial", "初始止损",
                "trailing_stop", "stop_trail", "stop_trailing", "移动止损")
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
# 一 · 留出池 / 研发池(★ 1102 原样)
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
# 二 · 把「大+中口径」加给**所有** run_chain(含对照组)(★ 1102 原样)
# ══════════════════════════════════════════════════════════════════════════

_ORIG_RUN_CHAIN = chain.run_chain


def _scoped_run_chain(cfg, symbols=None, start=data.PERF_START, end=data.PERF_END,
                      initial_equity=1_000_000.0, m=None,
                      flat_friction_bps=None, total_return=None):
    if m is None:
        m = matrices.build(cfg.raw, symbols)
        RC.apply_scope(m, SCOPE)
    return _ORIG_RUN_CHAIN(cfg, symbols, start, end, initial_equity, m=m,
                           flat_friction_bps=flat_friction_bps,
                           total_return=total_return)


# ══════════════════════════════════════════════════════════════════════════
# 三 · 旧值 / 链表(★ 1102 原样,只把「上一轮」换成 1102)
# ══════════════════════════════════════════════════════════════════════════

def old_bench1() -> dict[str, dict]:
    d = json.load(open(OLD_BENCH, encoding="utf-8"))
    return {r["链"]: r for r in d["逐链"]}


def bench1_1102() -> dict[str, dict]:
    """★★★ 改前(= 一刀切 5bp)的逐链结果,按链名索引。★ 只读,不重跑。"""
    d = json.load(open(B1102_JSON, encoding="utf-8"))
    return {r["链"]: r for r in d["逐链"]}


gates_pass = GR.gates_pass


def chain_list() -> list[tuple]:
    prev = json.load(open(OLD_RERUN, encoding="utf-8"))
    prows = [r for r in prev["逐链"] if "★跑不了" not in r]
    GR.selftest(prows)
    keep = {r["链"] for r in prows if gates_pass(r)}
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
    """★ 1102 原样:从**配置本体**判「有没有止损」,不按链名猜。"""
    reasons = []
    for k in STOP_ALIASES:
        v = raw.get(k)
        if isinstance(v, dict):
            t = (v.get("type") or "").strip().lower()
            if v.get("stages") or v.get("rules"):
                return False, f"{k} 有 stages/rules"
            if t and t != "none":
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
# 四 · 一条链(★ 1102 原样 + 本轮四个只读诊断)
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
    costs = (raw.get("costs") or {})

    # ---- 真链:研发池 × 大+中口径
    m = matrices.build(cfg.raw, dev)
    scope_diag = RC.apply_scope(m, SCOPE)
    res = _ORIG_RUN_CHAIN(cfg, dev, data.PERF_START, data.PERF_END, m=m)
    led = res.ledger

    # ★★★ 硬断言:留出池一笔都不许进
    if len(led):
        leaked = sorted(set(led["symbol"].astype(str)) & hold)
        if leaked:
            raise RuntimeError(f"★★★ 留出池漏进来了 {len(leaked)} 只:{leaked[:10]}")

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
        "★本轮摩擦口径": ("三档 friction_tiers " + json.dumps(
            costs.get("friction_tiers"), ensure_ascii=False)
            if "friction_tiers" in costs
            else (f"一刀切 one_way_bps={costs.get('one_way_bps')}"
                  if "one_way_bps" in costs
                  else "★两个字段都没写 → 走 FRICTION_TIERS_DEFAULT")),
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
        "旧种子数": o.get("随机进场_种子数"),
        "universe收窄": scope_diag,
        "★真链退化R": _degen_counts(led),
        # ★★★ 本轮新增:美元口径
        "★真链美元": _money(led),
    }

    if err is not None:
        rec["★基准一"] = None
        rec["★对照笔数偏差"] = None
        rec["★前提破了_禁止下游"] = err
        rec["★新基准一值"] = None
        rec["★对照组美元"] = None
    else:
        pool = b1.pop("★对照流水并池", None)
        rec["★基准一"] = {k: (None if isinstance(v, float) and not np.isfinite(v)
                              else v) for k, v in b1.items()}
        rec["★对照笔数偏差"] = rec["★基准一"].get("★对照笔数偏差")
        rec["★新基准一值"] = rec["★基准一"].get("★真信号每笔R − 随机进场每笔R")
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
            rec["★对照组退化R_50种子并池"] = _degen_counts(pool)
            rec["★对照组美元"] = _money(pool)
            os.makedirs(LEDGERS, exist_ok=True)
            pool.to_csv(os.path.join(LEDGERS,
                                     f"CTRL__{safe_name(label)}.csv"), index=False)
        else:
            rec["★对照组退化R_50种子并池"] = {"★没拿到并池流水": True}
            rec["★对照组美元"] = {"★没拿到并池流水": True}

    # ---- ★★★ 和 1102(= 摩擦改**前**)逐条对照 —— 只读
    p = (prev or {}).get(label) or {}
    if p:
        d: dict = {
            "1102笔数": p.get("笔数"),
            "1102每笔净R": p.get("每笔净R"),
            "1102每笔毛R": p.get("每笔毛R"),
            "1102基准一": p.get("★新基准一值"),
            "1102对照笔数偏差": p.get("★对照笔数偏差"),
            "1102种子数": p.get("种子数"),
        }
        n_now = rec.get("★新基准一值")
        d["笔数差"] = ((rec["笔数"] - p["笔数"]) if p.get("笔数") is not None
                       else None)
        if rec.get("每笔净R") is not None and p.get("每笔净R") is not None:
            d["每笔净R差"] = rec["每笔净R"] - p["每笔净R"]
        else:
            d["每笔净R差"] = None
        if n_now is not None and p.get("★新基准一值") is not None:
            d["基准一差"] = n_now - p["★新基准一值"]
            d["★基准一符号是否翻转(1102→1104)"] = bool(
                (n_now > 0) != (p["★新基准一值"] > 0))
        else:
            d["基准一差"] = None
            d["★基准一符号是否翻转(1102→1104)"] = None
        rec["★对1102(摩擦改前)"] = d
    else:
        rec["★对1102(摩擦改前)"] = {"★1102里没有这条链": True}

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
    args = ap.parse_args()

    os.makedirs(PER_CHAIN, exist_ok=True)
    dev, hold, hjson = load_pools()

    # ---- ★★★ 第 0 步:engine 代码指纹(对不上直接抛,不接)+ configs 记账
    fp_code_before = verify_code_fingerprint()
    fp_cfg_before = configs_fingerprint()

    try:
        _say(subprocess.run(["free", "-m"], capture_output=True, text=True).stdout)
        _say(f"CPU 核数 {os.cpu_count()} · 串行单进程 · 种子 {N_SEEDS} · "
             f"容差 ±{analyze.CONTROL_TOL:.0%} · 口径 {SCOPE}")
        _say(f"★ 研发池 {len(dev)} 只 · 留出池 {len(hold)} 只(本轮一笔都不跑)")
        _say(f"★ engine 代码指纹 {fp_code_before['指纹']}(逐份与登记值一致)")
        _say(f"★ configs 指纹 改前 {fp_cfg_before['★指纹_改前(git 55088733^ 现算)']}"
             f" → 改后 {fp_cfg_before['★指纹_改后(工作区)']}"
             f"(变了 {fp_cfg_before['改前改后不同的份数']} 份 · "
             f"显式三档 {fp_cfg_before['★显式写 friction_tiers 的份数']} 份 · "
             f"还写 one_way_bps {fp_cfg_before['★还写 one_way_bps 的份数']} 份)")
    except Exception:
        pass

    chain.run_chain = _scoped_run_chain       # ★ 对照组也进大+中 + 研发池
    pat6_ops.install()
    ops_exits_1029.install()

    old = old_bench1()
    prev = bench1_1102()          # ★★★ 1102 = 摩擦改**前**
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
        with open(dst, "w", encoding="utf-8") as fh:   # ★ 先写盘,再打印
            json.dump(rec, fh, ensure_ascii=False, indent=1, default=str)
        rows.append(rec)
        try:
            mm = rec.get("★真链美元") or {}
            _say(f"[{i}/{len(variants)}] {label[:46]:46s} "
                 f"{rec.get('笔数', 0):5d}笔 "
                 f"净${(mm.get('净盈亏') or 0):>12,.0f} "
                 f"摩擦${(mm.get('摩擦总额') or 0):>11,.0f} "
                 f"净R={rec.get('每笔净R')} "
                 f"基准一={rec.get('★新基准一值')} "
                 f"{rec.get('耗时秒')}s"
                 + ("  ★前提破了" if rec.get("★前提破了_禁止下游") else "")
                 + ("  ★跑不了" if rec.get("★跑不了") else ""))
        except Exception:
            pass

    ok = [r for r in rows if r.get("★新基准一值") is not None]
    broke = [r for r in rows if r.get("★前提破了_禁止下游")]
    crash = [r for r in rows if r.get("★跑不了")]
    nostop = [r for r in rows
              if r.get("★无止损_R退化成收益率_不可和有止损同列排序")]
    flip = [r["链"] for r in rows
            if (r.get("★对1102(摩擦改前)") or {})
            .get("★基准一符号是否翻转(1102→1104)")]

    out = {
        "口径戳": pool_scope.stamp(SCOPE, {
            "本轮做法": "★★★ 摩擦口径统一成三档(5/15/30bp 单边,进出各扣一次,"
                        "档位按进场日锁定)后的研发池 45 条链重跑 —— "
                        "★ 容差 ±5% 硬断言 · 50 个写死种子 · 对照组同池 · "
                        "★★★ 只在研发池上跑,考卷一次没跑。★★ engine 代码零改动。",
            "种子来源": "analyze.CONTROL_SEEDS[:50] —— ★ 只有这一条路",
            "容差": analyze.CONTROL_TOL,
            "★研发池只数": len(dev),
            "★留出池只数": len(hold),
            "★留出池名单文件": hjson.get("★★★留出池名单文件"),
            "★留出池SHA256": hjson.get("★★★SHA-256"),
            "覆盖": f"{len(variants)} 条(= bench1_rerun_1102 的同一套链)",
        }),
        "汇总": {
            "链数": len(rows),
            "算出基准一的": len(ok),
            "★前提破裂_算不出基准一的": len(broke),
            "跑不了的": len(crash),
            "前提破裂名单": [r["链"] for r in broke],
            "跑不了名单": [r["链"] for r in crash],
            "★对照笔数偏差_最大绝对值": (
                max(abs(r["★对照笔数偏差"]) for r in ok
                    if r.get("★对照笔数偏差") is not None) if ok else None),
            "★无止损(R退化成收益率)的链数": len(nostop),
            "★相对1102基准一符号翻转的条数": len(flip),
            "★相对1102基准一符号翻转名单": flip,
        },
        "★指纹_engine代码_跑前": fp_code_before,
        "★指纹_configs_跑前": fp_cfg_before,
        "逐链": rows,
        "★被闸挡下_不出数的链": BLOCKED_ROSTER,
        "总耗时秒": round(time.time() - t0, 1),
    }
    # ---- ★ 跑完再核一遍(★★ 代码变了 → 整轮作废,但**先把结果写盘**再抛)
    try:
        out["★指纹_engine代码_跑后"] = verify_code_fingerprint()
    except Exception:
        out["★指纹_engine代码_跑后"] = {"★★★跑完核代码指纹不通过_整轮作废":
                                        traceback.format_exc(limit=5)}
    try:
        out["★指纹_configs_跑后"] = configs_fingerprint()
    except Exception:
        out["★指纹_configs_跑后"] = {"★出错": traceback.format_exc(limit=5)}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    try:
        _say(f"\n共 {out['总耗时秒']}s · 算出 {len(ok)} · 前提破 {len(broke)} · "
             f"跑不了 {len(crash)}")
        _say(f"★ engine 代码指纹 跑前={fp_code_before['指纹']} "
             f"跑后={out['★指纹_engine代码_跑后'].get('指纹')}")
        _say(f"★ configs 指纹 跑后={out['★指纹_configs_跑后'].get('★指纹_改后(工作区)')}")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
