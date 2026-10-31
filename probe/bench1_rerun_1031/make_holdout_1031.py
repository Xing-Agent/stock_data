#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 第一件 · 锁死「股票维度」的留出池 —— 2026-10-31

三秒版:留出池的唯一价值是「我们没见过」。时间维度(2022–2025)已经被反复看过、
        污染无法恢复,所以策略组拍板走丙(甲+乙):**换成股票维度**。
        本脚本做四件事:① 扫全部流水取「碰过的票」全集(★ 先按 company_id 做改名归一)
        ② 大+中池 − 碰过的 = 候选留出池;候选不足就按确定性哈希切 20%
        ③ 名单落盘 + SHA-256 锁死
        ④ 剩下的 = 研发池,本轮只在它上面跑

★★ 改名归一怎么做:`probe/history_start_1030/pit_history_start_1030.csv.gz`
   自带 company_id,同一家公司改过名的几个 ticker 共用一个 company_id
   (例:FB 和 META 同一个 company_id)。
   ★ 池子文件 pool_FULL_ALL.csv 也有 company_id,两边同源,可以直接对。
   ★ 不这么做的后果:池子写 ANTM、流水写 ELV,会把跑过的票误判成「没碰过」。

★★★ 已实测的关键事实(写进报告):引擎实际能跑的票只有 **300 只**
   (`engine/data.full_universe().pool('ALL')` ∩ `engine/cache.symbols()`),
   不是池子文件那 74,268 行(= 只×年)。所以「大+中池」在实际跑批里
   = 这 300 只里属于大+中的那些。留出池只能从这 300 只里切。
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import cache, data, pool_scope  # noqa: E402

PIT = os.path.join(ROOT, "probe", "history_start_1030",
                   "pit_history_start_1030.csv.gz")
OUT_LIST = os.path.join(HERE, "holdout_symbols_1031.csv")
OUT_JSON = os.path.join(HERE, "holdout_1031.json")

#: ★ 哈希切分用的固定盐 —— 写死,不许改(改了等于重新挑一次)
HOLDOUT_SALT = "XING-holdout-1031"
HOLDOUT_FRAC = 0.20


def say(*a):
    try:
        print(*a, flush=True)
    except Exception:
        pass


# ══════════════════════════════════════════════════════════════════════════
# 一 · 改名归一:ticker -> company_id
# ══════════════════════════════════════════════════════════════════════════

def ticker_to_company() -> tuple[dict[str, set[str]], dict[str, set[str]]]:
    """-> (ticker -> {company_id}, company_id -> {ticker})。

    ★ 一个 ticker 可能被不同公司先后用过 → 值是集合,调用方必须处理歧义。
    """
    t2c: dict[str, set[str]] = defaultdict(set)
    c2t: dict[str, set[str]] = defaultdict(set)
    with gzip.open(PIT, "rt", encoding="utf-8-sig", newline="") as fh:
        for r in csv.DictReader(fh):
            cid = (r.get("company_id") or "").strip()
            tk = (r.get("ticker") or "").strip().upper()
            if not cid or not tk:
                continue
            t2c[tk].add(cid)
            c2t[cid].add(tk)
            rf = (r.get("renamed_from") or "").strip().upper()
            if rf:
                t2c[rf].add(cid)
                c2t[cid].add(rf)
    return t2c, c2t


# ══════════════════════════════════════════════════════════════════════════
# 二 · 扫全部流水 -> 碰过的 ticker 全集
# ══════════════════════════════════════════════════════════════════════════

def ledger_files() -> list[str]:
    """★ 纪律:`*ledger*` 一把捞会多出 54 个 breakeven 副本 —— 这里**照样全收**,
    因为我们要的是「出现过的 symbol 全集」,副本不会改变并集,
    但要把数报出来(副本数 / 去重后文件数)。"""
    out = []
    for base in (os.path.join(ROOT, "engine"), os.path.join(ROOT, "probe")):
        for dp, _dn, fns in os.walk(base):
            for fn in fns:
                if not fn.endswith(".csv"):
                    continue
                p = os.path.join(dp, fn)
                if ("ledger" in dp.lower() or "ledger" in fn.lower()
                        or fn.startswith(("REAL__", "CTRL__"))):
                    out.append(p)
    return sorted(out)


def touched_tickers(files: list[str]) -> tuple[set[str], dict]:
    seen: set[str] = set()
    per_file: dict[str, int] = {}
    bad = []
    for p in files:
        try:
            with open(p, newline="", encoding="utf-8-sig") as fh:
                rd = csv.reader(fh)
                hdr = next(rd, None)
                if not hdr:
                    continue
                low = [h.strip().lower() for h in hdr]
                col = None
                for cand in ("symbol", "ticker", "sym"):
                    if cand in low:
                        col = low.index(cand)
                        break
                if col is None:
                    continue
                n = 0
                for row in rd:
                    if len(row) > col:
                        s = row[col].strip().upper()
                        if s:
                            seen.add(s)
                            n += 1
                per_file[os.path.relpath(p, ROOT)] = n
        except Exception as e:                       # noqa: BLE001
            bad.append((os.path.relpath(p, ROOT), repr(e)))
    return seen, {"每文件笔数": per_file, "读不了的文件": bad}


# ══════════════════════════════════════════════════════════════════════════
# 三 · 确定性哈希切分
# ══════════════════════════════════════════════════════════════════════════

def hash_pick(sym: str) -> float:
    h = hashlib.sha256(f"{HOLDOUT_SALT}|{sym}".encode()).hexdigest()
    return int(h[:16], 16) / float(1 << 64)


def main() -> int:
    # ---- 引擎实际能跑的票
    runnable = sorted(set(data.full_universe().pool("ALL")) & set(cache.symbols()))

    # ---- 大+中口径:这 300 只里,**哪些年**在 rank<=2000
    idx = pool_scope.PoolIndex()
    assert idx.rows == pool_scope.POOL_KNOWN_ROWS, \
        f"★ 池子行数 {idx.rows} ≠ 已知 {pool_scope.POOL_KNOWN_ROWS},停"
    years = sorted({y for (_s, y) in idx.rank})
    large_mid, never_lm, lm_years = [], [], {}
    # ★★ 改名陷阱的实测证据:哪些票**只能**靠 company_id 对上(按 symbol 对会直接丢)
    only_by_rename, any_rename = [], []
    for s in runnable:
        ys, hows = [], set()
        for y in years:
            rk, _t, how = idx.resolve(s, y)
            if rk is not None:
                hows.add(how)
            if pool_scope.in_scope(rk, "large_mid"):
                ys.append(y)
        if "改名对上" in hows:
            any_rename.append(s)
            if "直接" not in hows:
                only_by_rename.append(s)
        if ys:
            large_mid.append(s)
            lm_years[s] = ys
        else:
            never_lm.append(s)

    # ---- 碰过的票(改名归一前 / 后)
    files = ledger_files()
    raw_touched, diag = touched_tickers(files)
    t2c, c2t = ticker_to_company()

    def cids(sym: str) -> set[str]:
        return t2c.get(sym.upper(), set())

    touched_cids: set[str] = set()
    for s in raw_touched:
        touched_cids |= cids(s)

    # ★ 归一后判定:这只票的任一 company_id 在流水里出现过 → 碰过
    touched_norm, untouched = [], []
    rename_rescued = []           # ★ 只有归一之后才判成「碰过」的票
    for s in large_mid:
        direct = s.upper() in raw_touched
        viacid = bool(cids(s) & touched_cids)
        if direct or viacid:
            touched_norm.append(s)
            if not direct and viacid:
                alias = sorted({a for c in cids(s) for a in c2t.get(c, set())}
                               & raw_touched)
                rename_rescued.append({"票": s, "流水里用的代码": alias})
        else:
            untouched.append(s)

    # ---- 候选留出池
    cand = sorted(untouched)
    need = max(1, round(len(large_mid) * HOLDOUT_FRAC))
    if len(cand) >= need:
        mode = "甲-纯未碰过"
        holdout = cand[:need] if len(cand) > need else cand
        already_run_in_holdout = 0
    else:
        # ★★★ 候选不足 → 按确定性哈希从大+中池切 20%,并诚实报出其中跑过多少只
        mode = "候选不足 → 确定性哈希切 20%"
        scored = sorted(large_mid, key=lambda s: (hash_pick(s), s))
        holdout = sorted(scored[:need])
        already_run_in_holdout = sum(1 for s in holdout if s in set(touched_norm))

    dev = sorted(set(large_mid) - set(holdout))

    payload = {
        "口径戳": pool_scope.stamp("large_mid", {
            "本文件是什么": "★★★ 股票维度的留出池名单(2026-10-31 锁死,本轮不许改)",
            "为什么是股票维度": "时间维度(2022–2025)已被反复看过 → 污染无法恢复;"
                                "策略组拍板走丙 = 甲(换股票维度) + 乙(规格表写明"
                                "「本批策略未经时间维度的样本外验证」)",
        }),
        "切法": mode,
        "哈希盐(写死)": HOLDOUT_SALT,
        "留出比例": HOLDOUT_FRAC,
        "引擎实际能跑的票数": len(runnable),
        "其中属于大+中的": len(large_mid),
        "其中从没进过大+中的": len(never_lm),
        "从没进过大+中的名单": never_lm,
        "扫了多少份流水": len(files),
        "流水里出现过的代码数(归一前)": len(raw_touched),
        "★大+中里·碰过的": len(touched_norm),
        "★大+中里·一直没碰过的": len(untouched),
        "一直没碰过的名单": untouched,
        "★改名归一救回来的票(不归一会误判成没碰过)": rename_rescued,
        "★★改名陷阱_实测": {
            "说明": "池子文件按 (symbol, year) 直接对 vs 按 company_id 对。"
                    "下面这些票**只能**靠 company_id 对上 —— 只按 symbol 对"
                    "会把它们判成「当年不在池」,于是整只票掉出大+中池。",
            "至少有一年要靠改名才对上的票数": len(any_rename),
            "完全只能靠改名对上的票": only_by_rename,
            "例子": "ANTM 2018 rank 95(直接)= ELV 2018 rank 95(改名对上)—— 同一家",
        },
        "★★★留出池只数": len(holdout),
        "★★★留出池里其实已经跑过的只数": already_run_in_holdout,
        "★★★留出池里其实已经跑过的比例": (round(already_run_in_holdout / len(holdout), 4)
                                          if holdout else None),
        "研发池只数": len(dev),
        "留出池名单": holdout,
        "研发池名单": dev,
    }

    # ★ 纪律④:先写盘,再打印
    with open(OUT_LIST, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["symbol", "在留出池", "我们是否已经跑过", "在大中池的年份"])
        hs = set(holdout)
        tn = set(touched_norm)
        for s in large_mid:
            w.writerow([s, "是" if s in hs else "否",
                        "跑过" if s in tn else "没碰过",
                        "|".join(lm_years.get(s, []))])

    with open(OUT_LIST, "rb") as fh:
        sha = hashlib.sha256(fh.read()).hexdigest()
    payload["★★★留出池名单文件"] = os.path.relpath(OUT_LIST, ROOT)
    payload["★★★SHA-256"] = sha
    payload["诊断"] = diag

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, default=str)

    try:
        say(f"引擎能跑 {len(runnable)} 只 · 大+中 {len(large_mid)} 只 · "
            f"从没进大+中 {len(never_lm)} 只")
        say(f"扫了 {len(files)} 份流水,出现过 {len(raw_touched)} 个代码")
        say(f"大+中里:碰过 {len(touched_norm)} · 一直没碰过 {len(untouched)}")
        say(f"改名归一救回 {len(rename_rescued)} 只")
        say(f"切法 = {mode}")
        say(f"★ 留出池 {len(holdout)} 只,其中已经跑过 {already_run_in_holdout} 只 "
            f"({already_run_in_holdout/len(holdout):.1%})" if holdout else "")
        say(f"★ 研发池 {len(dev)} 只")
        say(f"★ SHA-256 = {sha}")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
