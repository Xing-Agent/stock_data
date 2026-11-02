#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 开考 —— 用冻结版在 1,042 只从没碰过的股票上跑一次 · 2026-11-02

三秒版:老池 300 只的成绩我们都看过了,不能再当考试用。
        这一份是 1,042 只**从没碰过**的美股,★★★ 只能考一次。
        ★ 跑之前 engine 一行都没改,跑完再核一遍指纹。

★★ 本脚本的结构照 probe/bench1_rerun_1031/run_bench1_1031.py 写
   (可续跑 · 先写盘再打印 · 不用 nohup · 先量耗时)。

★★★ 和上一轮**完全一致**的口径(一个数都没动):
   · 基准一 = 同环境随机进场,`analyze.CONTROL_SEEDS[:50]` 50 个写死种子
   · 容差 `analyze.CONTROL_TOL` = ±5%,硬断言(前提破了就 raise,不出数)
   · 池子口径 `large_mid`(成交额排名 1–2000),按**年**判,走 pool_scope.PoolIndex
   · 摩擦 `data.ONE_WAY_COST_BPS`,绩效窗口 data.PERF_START .. PERF_END
   · 链表 = 上一轮那 45 条的同一份(同一个 gate_roster_1031 判据)

★★★ 「不改 engine 一行」是怎么做到的 —— 本脚本只在**运行时**改三样外部指针:
   ① data.PILOT / data.MANIFEST_CSV  → 指向 exam_1042(考卷行情在那儿)
      ★ data.BENCH_DIR / BREADTH_CSV **不动**(SPY/VIX/宽度是指数级数据,
        不属于股票池;交易日历也是 SPY 给的,换了就不是同一把尺子)
   ② cache.PANEL_PARQUET / META_PARQUET → 指向本目录下另一份 parquet
      ★ 绝不覆盖 engine/cache/ohlcv_panel.parquet(那是老池的,要留着对照)
   ③ chain.run_chain → 包一层,让**对照组也进** large_mid 口径
      ★ 这一层照抄上一轮 run_bench1_1031._scoped_run_chain,没有改动
   ★ engine/*.py 和 engine/**/*.yaml 一个字节都没写过(跑完核指纹验证)。

跑法:
   python3 probe/exam_run_1102/run_exam_1102.py --limit 3   # 量耗时
   python3 probe/exam_run_1102/run_exam_1102.py             # 全量(可续跑)
"""
from __future__ import annotations

import argparse
import copy
import csv
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
BENCH1 = os.path.join(ROOT, "probe", "bench1_rerun_1031")
for p in (ROOT, V2, BENCH1, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

# ══════════════════════════════════════════════════════════════════════════
# ★★★ 第 0 步 · 核题目指纹 —— 对不上就停,不许跑
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
    """★ 重算 133 个文件的 SHA-256,按文件名顺序拼 hex 再 SHA-256。

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
            " —— ★ 这一轮不算样本外,停。")
    agg = hashlib.sha256()
    for name in sorted(actual):
        agg.update(actual[name].encode())
    got = agg.hexdigest()
    if got != EXPECT_FP:
        raise RuntimeError(f"★★★ 汇总指纹对不上:{got} ≠ {EXPECT_FP} —— 停。")

    # ★ 另记一笔(不挡跑批,但必须留痕):清单之外、磁盘上还有的 engine .py/.yaml
    manset = {e["file"] for e in entries}
    disk = set()
    for dp, dn, fn in os.walk(os.path.join(ROOT, "engine")):
        dn[:] = [d for d in dn if d != "__pycache__"]
        for f in fn:
            if f.endswith((".py", ".yaml")):
                disk.add(os.path.relpath(os.path.join(dp, f), ROOT))
    return {
        "汇总指纹": got,
        "是否一致": got == EXPECT_FP,
        "核了多少个文件": len(entries),
        "逐份全部一致": True,
        "★清单外但磁盘上有的_engine_py_yaml": sorted(disk - manset),
        "拼法": "逐份 sha256 的 hex,按文件名排序直接拼接,再 sha256",
    }


# ══════════════════════════════════════════════════════════════════════════
# 一 · 把数据指针指到考卷(★ engine 文件一行不改)
# ══════════════════════════════════════════════════════════════════════════

EXAM_DIR = os.path.join(ROOT, "exam_1042")
EXAM_LIST = os.path.join(ROOT, "probe", "exam_1101", "exam_list_1101.csv")
EXAM_LIST_SHA = "0b8cd4652acf967590b00fca2b417e9685235453756d7a8ca916c15eccbd5895"

PER_CHAIN = os.path.join(HERE, "per_chain")
LEDGERS = os.path.join(HERE, "ledgers_1102")
CACHE_DIR = os.path.join(HERE, "cache_exam")
OUT = os.path.join(HERE, "exam_run_1102.json")

N_SEEDS = 50
SCOPE = "large_mid"
DEGEN_REL = 1e-4          # ★ 退化 R 判据,照抄 degenerate_r_1031.py,没有改

#: ★ 止损槽位别名 —— 照抄上一轮 run_bench1_1031.STOP_ALIASES
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

BLOCKED_ROSTER: list[dict] = []


def _say(*a):
    """★ 跑批纪律:打印一律包在 try 里,一个拼错的键不许把跑批炸掉。"""
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


def point_at_exam() -> dict:
    """★★★ 运行时把 data / cache 的指针指到考卷。返回留痕 dict。"""
    from engine import cache, data

    before = {"PILOT": data.PILOT, "MANIFEST_CSV": data.MANIFEST_CSV,
              "PANEL_PARQUET": cache.PANEL_PARQUET}
    data.PILOT = EXAM_DIR
    data.MANIFEST_CSV = os.path.join(EXAM_DIR, "manifest.csv")
    data.load_manifest.cache_clear()
    os.makedirs(CACHE_DIR, exist_ok=True)
    cache.CACHE_DIR = CACHE_DIR
    cache.PANEL_PARQUET = os.path.join(CACHE_DIR, "ohlcv_panel_exam.parquet")
    cache.META_PARQUET = os.path.join(CACHE_DIR, "panel_meta_exam.parquet")
    cache._PANEL = None
    return {
        "改前": before,
        "改后": {"PILOT": data.PILOT, "MANIFEST_CSV": data.MANIFEST_CSV,
                 "PANEL_PARQUET": cache.PANEL_PARQUET},
        "★没动的": {"BENCH_DIR(SPY/VIX/交易日历)": data.BENCH_DIR,
                    "BREADTH_CSV(市场宽度)": data.BREADTH_CSV,
                    "摩擦_单边bps": data.ONE_WAY_COST_BPS,
                    "绩效窗口": f"{data.PERF_START} .. {data.PERF_END}"},
    }


def load_exam_symbols() -> tuple[list[str], dict]:
    """读考卷名单并核 SHA-256。★ 对不上就 raise。"""
    got = _sha256_file(EXAM_LIST)
    if got != EXAM_LIST_SHA:
        raise RuntimeError(f"★★★ 考卷名单被动过:{got} ≠ {EXAM_LIST_SHA} —— 停。")
    with open(EXAM_LIST, newline="", encoding="utf-8-sig") as fh:
        rows = list(csv.DictReader(fh))
    col = "symbol" if "symbol" in rows[0] else list(rows[0])[0]
    syms = [r[col].strip() for r in rows if r[col].strip()]
    if len(syms) != 1042:
        raise RuntimeError(f"★ 考卷名单 {len(syms)} 行 ≠ 1042 —— 停。")
    return syms, {"名单文件": os.path.relpath(EXAM_LIST, ROOT),
                  "名单SHA256": got, "行数": len(syms)}


def old_pool_symbols() -> set[str]:
    """★ 老池名单(pilot_300 的 manifest)—— 用来硬断言:考卷流水里不许出现它们。"""
    p = os.path.join(ROOT, "pilot_300", "manifest.csv")
    with open(p, newline="", encoding="utf-8-sig") as fh:
        return {r["symbol"].strip() for r in csv.DictReader(fh)}


# ══════════════════════════════════════════════════════════════════════════
# 二 · 老池成绩(并列报用)—— 上一轮基准一全库重跑,同一套口径
# ══════════════════════════════════════════════════════════════════════════

OLD_BENCH1 = os.path.join(BENCH1, "bench1_rerun_1031.json")
OLD_DEGEN = os.path.join(BENCH1, "degenerate_r_1031.json")
OLD_RERUN = os.path.join(V2, "rerun_results_1030.json")


def old_results() -> tuple[dict, set]:
    d = json.load(open(OLD_BENCH1, encoding="utf-8"))
    by = {r["链"]: r for r in d["逐链"]}
    try:
        g = json.load(open(OLD_DEGEN, encoding="utf-8"))
        degen_bad = set(g.get("★基准一不可用的链") or [])
    except Exception:
        degen_bad = set()
    return by, degen_bad


# ══════════════════════════════════════════════════════════════════════════
# 三 · 链表(★ 和上一轮同一份判据)
# ══════════════════════════════════════════════════════════════════════════

def chain_list() -> list[tuple]:
    import gate_roster_1031 as GR
    prev = json.load(open(OLD_RERUN, encoding="utf-8"))
    prows = [r for r in prev["逐链"] if "★跑不了" not in r]
    GR.selftest(prows)
    keep = {r["链"] for r in prows if GR.gates_pass(r)}
    global BLOCKED_ROSTER
    BLOCKED_ROSTER = [{"链": r["链"], **GR.verdict(r)}
                      for r in prows if not GR.gates_pass(r)]
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
    """★ 照抄上一轮 run_bench1_1031.no_stop,一个字没改。"""
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
# 四 · 退化 R 扫描(★ 判据照抄 degenerate_r_1031.py)
# ══════════════════════════════════════════════════════════════════════════

def scan_degenerate(df: pd.DataFrame) -> dict:
    if df is None or df.empty or "risk_per_share" not in df.columns:
        return {"笔数": int(0 if df is None else len(df)), "退化笔数": 0,
                "退化比例": 0.0}
    rps = pd.to_numeric(df["risk_per_share"], errors="coerce").abs()
    ep = pd.to_numeric(df.get("entry_price"), errors="coerce").abs()
    rel = rps / ep.replace(0, np.nan)
    bad = (rel < DEGEN_REL) | rps.isna() | (rps == 0)
    r = pd.to_numeric(df.get("r_multiple"), errors="coerce")
    out = {
        "笔数": int(len(df)),
        "退化笔数": int(bad.sum()),
        "退化比例": float(bad.mean()),
        "最小 risk_per_share": (None if rps.dropna().empty else float(rps.min())),
        "最大 |R|": (None if r.dropna().empty else float(r.abs().max())),
        "每笔R_原样": (None if r.dropna().empty else float(r.mean())),
        "每笔R_剔掉退化笔": (None if r[~bad].dropna().empty
                            else float(r[~bad].mean())),
    }
    if int(bad.sum()):
        cols = [c for c in ("symbol", "entry_date", "entry_price",
                            "initial_stop", "risk_per_share", "r_multiple")
                if c in df.columns]
        out["退化笔样例"] = df.loc[bad, cols].head(3).to_dict("records")
    return out


# ══════════════════════════════════════════════════════════════════════════
# 五 · 一条链
# ══════════════════════════════════════════════════════════════════════════

def run_one(label: str, yml: str, ov, group: str, syms: list[str],
            oldpool: set[str], old: dict, old_degen: set) -> dict:
    from engine import analyze, chain, data, matrices
    import rerun_core_1030 as RC

    t = time.time()
    CONFIG_DIR = os.path.join(ROOT, "engine", "configs")
    with open(os.path.join(CONFIG_DIR, yml), encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    if ov is not None:
        raw = ov(copy.deepcopy(raw))
    cfg = chain.ChainConfig.from_dict(raw)
    ns, ns_why = no_stop(raw)

    # ---- 真链:考卷 1,042 只 × 大+中口径
    m = matrices.build(cfg.raw, syms)
    scope_diag = RC.apply_scope(m, SCOPE)
    res = _ORIG_RUN_CHAIN(cfg, syms, data.PERF_START, data.PERF_END, m=m)
    led = res.ledger

    # ★★★ 硬断言:老池的票一只都不许出现在考卷流水里(反向的「不许混池」)
    if len(led):
        leaked = sorted(set(led["symbol"].astype(str)) & oldpool)
        if leaked:
            raise RuntimeError(f"★★★ 老池票漏进考卷 {len(leaked)} 只:{leaked[:10]}")

    err, b1 = None, None
    try:
        b1 = analyze.random_entry_benchmark(cfg, res, syms, data.PERF_START,
                                           data.PERF_END, n_seeds=N_SEEDS,
                                           keep_ledger=True)
    except analyze.BenchmarkPremiseBroken as e:
        err = {"类": "BenchmarkPremiseBroken", "说明": str(e)}

    o = old.get(label, {}) or {}
    o_b1 = o.get("★基准一") or {}
    old_b1_val = o_b1.get("★真信号每笔R − 随机进场每笔R")

    rec: dict = {
        "链": label, "族": group, "配置": yml,
        "池子口径": SCOPE,
        "★跑在哪个池": f"考卷 {len(syms)} 只(从没碰过)",
        "对照组是否同池": True,
        "★无止损_R退化成收益率_不可和有止损同列排序": ns,
        "★无止损_怎么判的": ns_why,
        # ── 考卷成绩
        "笔数": int(len(led)),
        "每笔净R": (float(np.nanmean(led["r_multiple_net"].astype(float)))
                    if len(led) else None),
        "每笔毛R": (float(np.nanmean(led["r_multiple"].astype(float)))
                    if len(led) else None),
        "胜率": (float((led["net_pnl"].astype(float) > 0).mean())
                 if len(led) else None),
        "合格进场信号(entry&universe)": int((m.entry & m.universe).sum()),
        "种子数": N_SEEDS,
        "universe收窄": scope_diag,
        # ── 老池成绩(上一轮 基准一全库重跑,研发池 198 只,同一套口径)
        "老池_笔数": o.get("笔数"),
        "老池_每笔净R": o.get("每笔净R"),
        "老池_基准一": old_b1_val,
        "老池_对照笔数偏差": (o.get("★基准一") or {}).get("★对照笔数偏差"),
        "老池_跑在哪个池": o.get("★跑在哪个池"),
        "★老池这条链的基准一本来就被退化R判为不可用": label in old_degen,
    }

    if err is not None:
        rec["★基准一"] = None
        rec["★新基准一值"] = None
        rec["★对照笔数偏差"] = None
        rec["★前提破了_禁止下游"] = err
        rec["★和老池的差"] = None
        rec["★符号是否翻转"] = None
    else:
        pool = b1.pop("★对照流水并池", None)
        rec["★基准一"] = {k: (None if isinstance(v, float) and not np.isfinite(v)
                              else v) for k, v in b1.items()}
        new_b1 = rec["★基准一"].get("★真信号每笔R − 随机进场每笔R")
        rec["★新基准一值"] = new_b1
        rec["★对照笔数偏差"] = rec["★基准一"].get("★对照笔数偏差")
        if new_b1 is not None and old_b1_val is not None:
            rec["★和老池的差"] = new_b1 - old_b1_val
            rec["★符号是否翻转"] = bool((new_b1 > 0) != (old_b1_val > 0))
        else:
            rec["★和老池的差"] = None
            rec["★符号是否翻转"] = None
        if pool is not None and not pool.empty:
            leaked = sorted(set(pool["symbol"].astype(str)) & oldpool)
            if leaked:
                raise RuntimeError(
                    f"★★★ 对照组漏进老池票 {len(leaked)} 只:{leaked[:10]}")
            os.makedirs(LEDGERS, exist_ok=True)
            pool.to_csv(os.path.join(LEDGERS, f"CTRL__{safe_name(label)}.csv"),
                        index=False)
            rec["★退化R_对照流水"] = scan_degenerate(pool)
        else:
            rec["★退化R_对照流水"] = None

    rec["★退化R_真链流水"] = scan_degenerate(led)
    # ★★ 退化 R 在哪一边出现,这条链的基准一就不可用(判据和上一轮一致)
    dr_real = (rec.get("★退化R_真链流水") or {}).get("退化笔数") or 0
    dr_ctrl = (rec.get("★退化R_对照流水") or {}).get("退化笔数") or 0
    rec["★退化R_本轮是否出现"] = bool(dr_real or dr_ctrl)
    rec["★基准一是否被退化R判为不可用"] = bool(dr_real or dr_ctrl)

    os.makedirs(LEDGERS, exist_ok=True)
    led.to_csv(os.path.join(LEDGERS, f"REAL__{safe_name(label)}.csv"), index=False)

    rec["耗时秒"] = round(time.time() - t, 1)
    rec["峰值RSS_MB"] = round(_rss_mb(), 1)
    return rec


# ══════════════════════════════════════════════════════════════════════════
# 六 · main
# ══════════════════════════════════════════════════════════════════════════

_ORIG_RUN_CHAIN = None


def main() -> int:
    global _ORIG_RUN_CHAIN
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="只跑前 N 条(量耗时用)")
    ap.add_argument("--summary-only", action="store_true",
                    help="不跑链,只从 per_chain 里重建全量汇总")
    args = ap.parse_args()
    # ★★★ 刻意**不提供** --only:上一轮 45 条的汇总被 --only 覆盖成 3 条。

    # ---- 第 0 步:核指纹(★ 对不上直接抛,不接)
    fp_before = verify_fingerprint()
    _say(f"★ 指纹(跑前)= {fp_before['汇总指纹']}  一致={fp_before['是否一致']}")

    syms, list_diag = load_exam_symbols()
    oldpool = old_pool_symbols()
    overlap = sorted(set(syms) & oldpool)
    _say(f"★ 考卷 {len(syms)} 只 · 和老池代码重名 {len(overlap)} 个:{overlap[:10]}")

    ptr = point_at_exam()
    from engine import cache, chain, data, matrices, ops_exits_1029, pat6_ops, pool_scope
    import rerun_core_1030 as RC

    # ---- 烤考卷缓存(可续跑:parquet 在就不重烤)
    if not os.path.exists(cache.PANEL_PARQUET):
        _say("★ 第一次跑,先烤考卷价格缓存(只烤一次)…")
        t0 = time.time()
        cache.build(verbose=False)
        _say(f"  烤好,{time.time()-t0:.1f}s")
    cache._PANEL = None
    pan = cache.load(verbose=False)
    _say(f"★ 考卷缓存:{pan['close'].shape[1]} 只 × {pan['close'].shape[0]} 天")

    # ★★★ 缓存里拿不到的票:**engine 自己的规则**剔掉的(cache.build 里那条
    #   「有效 bar 不足 60 根,跳过」),★ 不是我改的门槛。
    #   ★ 不剔会在 cache.field() 里 KeyError —— 所以这里只做「交集」,
    #     并把被剔的 17 只连理由一起写进结果,不许悄悄消失。
    have = set(pan["close"].columns)
    dropped = [s for s in syms if s not in have]
    if dropped:
        meta_df = cache.panel_meta()
        drop_diag = [{"代码": s,
                      "engine给的理由": str(meta_df.loc[s, "status"])
                      if s in meta_df.index else "(缓存元数据里没有这一行)",
                      "有效bar根数": (int(meta_df.loc[s, "n_bars"])
                                      if s in meta_df.index else None)}
                     for s in dropped]
        syms = [s for s in syms if s in have]
        _say(f"★ engine 自己剔掉 {len(dropped)} 只(有效 bar < 60 根),"
             f"剩 {len(syms)} 只参加考试:{dropped}")
    else:
        drop_diag = []
    list_diag["★engine自己剔掉的(有效bar<60根)"] = drop_diag
    list_diag["★实际参加考试的只数"] = len(syms)

    os.makedirs(PER_CHAIN, exist_ok=True)
    try:
        _say(subprocess.run(["free", "-m"], capture_output=True, text=True).stdout)
        _say(f"CPU 核数 {os.cpu_count()} · 串行单进程 · 种子 {N_SEEDS} · "
             f"容差 ±{analyze_tol():.0%} · 口径 {SCOPE}")
    except Exception:
        pass

    _ORIG_RUN_CHAIN = chain.run_chain

    def _scoped_run_chain(cfg, symbols=None, start=data.PERF_START,
                          end=data.PERF_END, initial_equity=1_000_000.0, m=None,
                          flat_friction_bps=None, total_return=None):
        """★ 照抄上一轮:m 没给时自己 build 并把大+中口径与进 universe
        —— 对照组也走这条路。"""
        if m is None:
            m = matrices.build(cfg.raw, symbols)
            RC.apply_scope(m, SCOPE)
        return _ORIG_RUN_CHAIN(cfg, symbols, start, end, initial_equity, m=m,
                               flat_friction_bps=flat_friction_bps,
                               total_return=total_return)

    chain.run_chain = _scoped_run_chain
    pat6_ops.install()
    ops_exits_1029.install()

    old, old_degen = old_results()
    variants = chain_list()
    all_n = len(variants)
    if args.limit:
        variants = variants[:args.limit]
    _say(f"★ 本轮要跑 {len(variants)} 条(全量 {all_n} 条)\n")

    rows, t0 = [], time.time()
    if args.summary_only:
        for label, yml, ov, group in chain_list():
            dst = os.path.join(PER_CHAIN, f"{safe_name(label)}.json")
            if os.path.exists(dst):
                rows.append(json.load(open(dst, encoding="utf-8")))
    else:
        for i, (label, yml, ov, group) in enumerate(variants, 1):
            dst = os.path.join(PER_CHAIN, f"{safe_name(label)}.json")
            if os.path.exists(dst):                       # ★ 可续跑
                try:
                    rows.append(json.load(open(dst, encoding="utf-8")))
                    _say(f"[{i}/{len(variants)}] 跳过(已有结果) {label[:60]}")
                except Exception:
                    os.remove(dst)
                else:
                    continue
            try:
                rec = run_one(label, yml, ov, group, syms, oldpool, old, old_degen)
            except Exception:
                rec = {"链": label, "族": group, "配置": yml,
                       "★跑不了": traceback.format_exc(limit=12)}
            # ★★ 先写盘,再打印
            with open(dst, "w", encoding="utf-8") as fh:
                json.dump(rec, fh, ensure_ascii=False, indent=1, default=str)
            rows.append(rec)
            try:
                _say(f"[{i}/{len(variants)}] {label[:46]:46s} "
                     f"{rec.get('笔数', 0):5d}笔 "
                     f"基准一={rec.get('★新基准一值')} "
                     f"偏差={rec.get('★对照笔数偏差')} "
                     f"翻转={rec.get('★符号是否翻转')} "
                     f"退化R={(rec.get('★退化R_真链流水') or {}).get('退化笔数')} "
                     f"{rec.get('耗时秒')}s RSS{rec.get('峰值RSS_MB')}MB"
                     + ("  ★前提破了" if rec.get("★前提破了_禁止下游") else "")
                     + ("  ★跑不了" if rec.get("★跑不了") else ""))
            except Exception:
                pass

    # ---- 汇总(★ 全量才写 OUT;部分跑写另一个名字,不许覆盖全量汇总)
    ok = [r for r in rows if r.get("★新基准一值") is not None]
    broke = [r for r in rows if r.get("★前提破了_禁止下游")]
    crash = [r for r in rows if r.get("★跑不了")]
    flip = [r for r in ok if r.get("★符号是否翻转")]
    nostop = [r for r in rows
              if r.get("★无止损_R退化成收益率_不可和有止损同列排序")]
    thin = [r for r in rows if r.get("笔数") is not None and r["笔数"] < 30]
    degen = [r for r in rows if r.get("★退化R_本轮是否出现")]
    tol_over = [r for r in ok
                if r.get("★对照笔数偏差") is not None
                and abs(r["★对照笔数偏差"]) > 0.05]

    out = {
        "这是什么": "★★★ 开考 —— 冻结版在 1,042 只从没碰过的美股上跑一次(2026-11-02)",
        "★★★只能考一次": "考完发现问题,修好的版本不能再拿这一份考卷考。",
        "题目指纹_跑前": fp_before,
        "考卷名单": list_diag,
        "数据指针": ptr,
        "口径戳": pool_scope.stamp(SCOPE, {
            "本轮做法": "★★★ 冻结版在考卷 1,042 只上跑一次 —— 容差 ±5% 硬断言 · "
                        "50 个写死种子 · 对照组同池 · ★ 一个参数都没改",
            "种子来源": "analyze.CONTROL_SEEDS[:50] —— ★ 只有这一条路",
            "容差": analyze_tol(),
            "★考卷只数": len(syms),
            "★老池只数(不混进来)": len(oldpool),
            "覆盖": f"{len(variants)} 条(= 上一轮基准一全库重跑那 {all_n} 条的同一份链表)",
            "老池成绩来源": os.path.relpath(OLD_BENCH1, ROOT)
                            + "(研发池 198 只,同一套口径)",
        }),
        "汇总": {
            "链数": len(rows),
            "算出基准一的": len(ok),
            "★前提破裂_算不出基准一的": len(broke),
            "跑不了的": len(crash),
            "★符号翻转的": len(flip),
            "符号翻转名单": [r["链"] for r in flip],
            "前提破裂名单": [{"链": r["链"],
                             "说明": (r.get("★前提破了_禁止下游") or {}).get("说明")}
                            for r in broke],
            "跑不了名单": [r["链"] for r in crash],
            "★笔数小于30_不给统计结论的": len(thin),
            "★笔数小于30名单": [{"链": r["链"], "笔数": r["笔数"]} for r in thin],
            "★退化R再出现的链数": len(degen),
            "★退化R名单": [
                {"链": r["链"],
                 "真链退化笔数": (r.get("★退化R_真链流水") or {}).get("退化笔数"),
                 "对照退化笔数": (r.get("★退化R_对照流水") or {}).get("退化笔数")}
                for r in degen],
            "★对照笔数偏差_最大绝对值": (
                max(abs(r["★对照笔数偏差"]) for r in ok
                    if r.get("★对照笔数偏差") is not None) if ok else None),
            "★对照笔数偏差超±5%的链数": len(tol_over),
            "★对照笔数偏差超±5%名单": [
                {"链": r["链"], "偏差": r["★对照笔数偏差"]} for r in tol_over],
            "★无止损(R退化成收益率)的链数": len(nostop),
            "★无止损名单(不可和有止损同列排序)": [
                {"链": r["链"], "怎么判的": r.get("★无止损_怎么判的")}
                for r in nostop],
        },
        "逐链": rows,
        "★被闸挡下_不出数的链": BLOCKED_ROSTER,
        "总耗时秒": round(time.time() - t0, 1),
    }

    # ---- 跑完再核一遍指纹
    try:
        fp_after = verify_fingerprint()
    except Exception:
        fp_after = {"★跑完核指纹出错": traceback.format_exc(limit=5)}
    out["题目指纹_跑后"] = fp_after

    dst = OUT if (not args.limit and not args.summary_only) else \
        os.path.join(HERE, f"exam_run_1102_partial_{len(rows)}条.json")
    with open(dst, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    try:
        _say(f"\n写到 {dst}")
        _say(f"共 {out['总耗时秒']}s · 算出 {len(ok)} · 前提破 {len(broke)} · "
             f"跑不了 {len(crash)} · 翻转 {len(flip)} · 笔数<30 {len(thin)} · "
             f"退化R {len(degen)}")
        _say(f"★ 指纹(跑后)= {fp_after.get('汇总指纹')} "
             f"一致={fp_after.get('是否一致')}")
    except Exception:
        pass
    return 0


def analyze_tol() -> float:
    from engine import analyze
    return analyze.CONTROL_TOL


if __name__ == "__main__":
    sys.exit(main())
