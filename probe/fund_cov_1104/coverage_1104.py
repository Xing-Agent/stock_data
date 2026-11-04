#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 任务二 · 在新库上重算神奇公式(基-4)的「可算率」(2026-11-04)

三秒版:同一把尺子,量两遍 —— ★ 一遍分子用 EBIT(不挂营业利润),
       ★★ 一遍分子换成营业利润(单列臂)。两列并排,看可算率各是多少。
       ★★★ **只量覆盖率/可算率,不跑回测、不算收益。**

★ 口径逐字照搬 手册/19-神奇公式v2-预先登记-1103.md 第二节:
    · 「格子」= 一个(公司 × 期间),期间用 period_end
    · 共同基准 = 「流动资产 ∩ 流动负债」都有的格子
    · 抽样 = fundamentals_ext 下的公司按名字排序,random.seed(20261103) 抽 400 家
  ★★ 另外加跑一遍**全库 4,015 家**(登记那轮库里只有 3,653 家,★ 抽样换了人,
     所以两边都给,不许只给一个数就说「对上了」)。

★ 记录去重口径照搬 tag_backfill_1030.py:dump_series() —— 键 = (period_start,
  period_end),同键留 **首发版**(filed 最早那条)。

★ 结果先写文件再打印。engine/ 没有 import,也没有改动;exam_1042/ 一只没碰。
跑法:python3 probe/fund_cov_1104/coverage_1104.py
"""
from __future__ import annotations

import csv
import gzip
import hashlib
import json
import os
import random
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
EXT_DIR = os.path.join(ROOT, "fundamentals_ext")
MANIFEST_SHA = os.path.join(EXT_DIR, "_MANIFEST.sha256")

OUT_JSON = os.path.join(HERE, "coverage_1104.json")
OUT_DIFF = os.path.join(HERE, "营业利润vsEBIT-逐期-1104.csv")
OUT_FIELD = os.path.join(HERE, "逐字段覆盖率-1104.csv")

SEED = 20261103
N_SAMPLE = 400

#: ★ 要量的科目 → 在库里的 us-gaap 标签
TAGS = {
    "ca": "CurrentAssets",
    "cl": "CurrentLiabilities",
    "ta": "TotalAssets",
    "ig": "IntangiblesAndGoodwill",
    "cash": "CashAndCashEquivalentsAtCarryingValue",
    "ppe": "PropertyPlantAndEquipmentNet",
    "stb": "ShortTermBorrowings",
    "dc": "DebtCurrent",
    "ltdc": "LongTermDebtCurrent",
    "ebit": "EBIT",
    "oil": "OperatingIncomeLoss",
    "liab": "Liabilities",
    "sga": "SellingGeneralAndAdministrativeExpense",
    "icop": "IncomeLossFromContinuingOperations",
    "gp": "GrossProfit",
    "msec": "MarketableSecuritiesCurrent",
}


def fingerprint() -> str:
    h = hashlib.sha256()
    with open(MANIFEST_SHA, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def ext_symbols() -> list[str]:
    out = []
    for name in sorted(os.listdir(EXT_DIR)):
        if name.startswith(("_", ".")):
            continue
        if os.path.exists(os.path.join(EXT_DIR, name, "fundamentals.json.gz")):
            out.append(name)
    return out


def first_filed(recs: list[dict]) -> dict:
    """{(period_start, period_end): rec} —— ★ 同键留首发版(filed 最早)。"""
    out: dict[tuple, dict] = {}
    for r in recs:
        v = r.get("value")
        end = r.get("period_end")
        filed = r.get("filed_at") or r.get("sec_filed_date")
        if v in (None, "") or not end or not filed:
            continue
        try:
            val = float(v)
        except (TypeError, ValueError):
            continue
        key = (r.get("period_start") or "", end)
        cur = out.get(key)
        if cur is None or filed < cur["filed"]:
            out[key] = {"val": val, "end": end,
                        "start": r.get("period_start"), "filed": filed}
    return out


def load_company(sym: str) -> dict[str, dict]:
    p = os.path.join(EXT_DIR, sym, "fundamentals.json.gz")
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        fv = (json.load(fh).get("financial_versions") or {})
    return {k: first_filed(fv.get(tag) or []) for k, tag in TAGS.items()}


# ══════════════════════════════════════════════════════════════════════════
# 一 · 一家公司的格子统计
# ══════════════════════════════════════════════════════════════════════════

def tally(sym: str, series: dict[str, dict], acc: dict, diff_rows: list) -> None:
    ends = {k: {key[1] for key in d} for k, d in series.items()}

    base = ends["ca"] & ends["cl"]                  # ★ 共同基准
    acc["基准格子"] += len(base)
    for k in TAGS:
        if ends[k]:
            acc["公司有该字段"][k] += 1
        acc["字段在基准格子里"][k] += len(base & ends[k])

    stb_union = ends["stb"] | ends["dc"] | ends["ltdc"]
    acc["字段在基准格子里"]["短期有息三者并集"] += len(base & stb_union)

    # ── 可算率:两条臂(分子 EBIT / 分子 营业利润) ─────────────────
    for arm, num in (("不挂营业利润", ends["ebit"]), ("挂营业利润", ends["oil"])):
        a = acc["可算"][arm]
        a["v1_现行"] += len(base & num & ends["ta"] & ends["ig"])
        a["v2_严格"] += len(base & num & ends["cash"] & ends["ppe"] & stb_union)
        a["v2_短借按0"] += len(base & num & ends["cash"] & ends["ppe"])
        a["只看分子_天花板"] += len(base & num)

    # ── 营业利润 vs EBIT:重叠期上的相对差 ──────────────────────────
    for key, r in series["oil"].items():
        b = series["ebit"].get(key)
        if b is None or b["val"] == 0:
            continue
        rel = (r["val"] - b["val"]) / abs(b["val"])
        diff_rows.append({"symbol": sym, "period_end": key[1],
                          "period_start": key[0],
                          "EBIT": b["val"], "OperatingIncomeLoss": r["val"],
                          "相对差": rel})


def new_acc() -> dict:
    from collections import Counter
    return {
        "基准格子": 0,
        "公司有该字段": Counter(),
        "字段在基准格子里": Counter(),
        "可算": {arm: {"v1_现行": 0, "v2_严格": 0, "v2_短借按0": 0,
                       "只看分子_天花板": 0}
                 for arm in ("不挂营业利润", "挂营业利润")},
    }


def pct(n: int, d: int) -> float | None:
    return round(100.0 * n / d, 1) if d else None


def summarize(acc: dict, n_co: int) -> dict:
    base = acc["基准格子"]
    out = {"公司家数": n_co, "共同基准格子(流动资产∩流动负债)": base}
    out["逐字段覆盖率"] = {
        name: {"公司口径%": pct(acc["公司有该字段"][k], n_co),
               "格子口径%": pct(acc["字段在基准格子里"][k], base)}
        for k, name in [(k, f"{k}({TAGS[k]})") for k in TAGS]
    }
    out["逐字段覆盖率"]["短期有息三者并集(stb∪dc∪ltdc)"] = {
        "公司口径%": None,
        "格子口径%": pct(acc["字段在基准格子里"]["短期有息三者并集"], base)}
    out["可算率"] = {
        arm: {k: {"格子": v, "占基准%": pct(v, base)}
              for k, v in d.items()}
        for arm, d in acc["可算"].items()}
    return out


# ══════════════════════════════════════════════════════════════════════════
# 二 · 主流程
# ══════════════════════════════════════════════════════════════════════════

def run(symbols: list[str], collect_diff: bool) -> tuple[dict, list]:
    acc = new_acc()
    rows: list = []
    for i, s in enumerate(symbols, 1):
        try:
            series = load_company(s)
        except Exception as exc:                        # noqa: BLE001
            print(f"  ★ 读不了 {s}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        tally(s, series, acc, rows if collect_diff else [])
        if i % 500 == 0:
            print(f"  …{i}/{len(symbols)}", file=sys.stderr)
    return summarize(acc, len(symbols)), rows


def diff_stats(rows: list) -> dict:
    if not rows:
        return {"结论": "★★★ 算不出来 —— 没有任何重叠期"}
    a = sorted(abs(r["相对差"]) for r in rows)
    n = len(a)
    p90 = a[min(n - 1, int(round(0.90 * (n - 1))))]
    over10 = sum(1 for x in a if x > 0.10)
    return {"重叠期数": n,
            "绝对相对差_中位%": round(100 * statistics.median(a), 1),
            "绝对相对差_p90%": round(100 * p90, 1),
            "绝对差超10%的期数占比%": round(100 * over10 / n, 1),
            "超10%的期数": over10}


def main() -> None:
    fp0 = fingerprint()
    syms = ext_symbols()

    rnd = random.Random(SEED)
    sample = sorted(rnd.sample(syms, N_SAMPLE))

    print(f"★ 库指纹(跑前) {fp0}\n★ 实体 {len(syms)} 家;抽样 {len(sample)} 家",
          file=sys.stderr)

    print("★ [1/2] 抽样 400 家…", file=sys.stderr)
    s400, _ = run(sample, collect_diff=False)
    print("★ [2/2] 全库…", file=sys.stderr)
    sall, rows = run(syms, collect_diff=True)

    fp1 = fingerprint()

    rep = {
        "报告": "任务二 · 神奇公式(基-4)可算率重算 —— 新库 fundamentals_ext",
        "★只量什么": "只量覆盖率 / 可算率。★★ 没跑回测、没算收益、没碰 exam_1042/。",
        "库指纹_跑前": fp0, "库指纹_跑后": fp1, "库指纹一致": fp0 == fp1,
        "口径出处": {
            "格子/基准/抽样": "手册/19-神奇公式v2-预先登记-1103.md 第二节",
            "首发版去重": "probe/fundamental_buildout_1030/tag_backfill_1030.py:127 dump_series()",
            "相对差公式": "probe/fundamental_buildout_1030/tag_backfill_1030.py:303 "
                          "(营业利润 − EBIT) / |EBIT|",
        },
        "A_抽样400家(同 seed 20261103)": s400,
        "B_全库": sall,
        "C_营业利润vsEBIT_重叠期差异": {
            "全库": diff_stats(rows),
            "登记值(1030,188只票)": {
                "重叠期数": 12553, "绝对相对差_中位%": 4.1,
                "绝对相对差_p90%": 43.7, "绝对差超10%的期数占比%": 31.6,
                "出处": "probe/fundamental_buildout_1030/ops_fund_1030.py:21-22 · "
                        "probe/fundamental_buildout_1030/E3口径对差-逐期-1030.csv",
            },
        },
        "D_登记值(跑前写死,不许改)": {
            "出处": "手册/19-神奇公式v2-预先登记-1103.md 第二节",
            "基准格子": 13613, "公司家数": 400, "库当时家数": 3653,
            "v1%": 20.1, "v2严格%": 21.8, "v2变体_短借按0%": 36.9,
            "EBIT天花板%": 38.0,
        },
        "E_那条预言(跑前写死)": {
            "★出处": "手册/贴Gemini-27-EBIT代理与一批待核原文.md:26-29 和 :129 —— "
                      "★★★ 不在 手册/19 里(19 没有这三个数)",
            "营业利润覆盖率%": 91.6,
            "v2 可算率 从→到": [21.5, 41.9],
            "短期借款按0 从→到": [34.5, 84.3],
        },
    }

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(rep, fh, ensure_ascii=False, indent=2)

    with open(OUT_DIFF, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=["symbol", "period_end", "period_start",
                                           "EBIT", "OperatingIncomeLoss", "相对差"])
        w.writeheader()
        w.writerows(rows)

    with open(OUT_FIELD, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["字段", "抽样400_公司口径%", "抽样400_格子口径%",
                    "全库_公司口径%", "全库_格子口径%"])
        for k in s400["逐字段覆盖率"]:
            a, b = s400["逐字段覆盖率"][k], sall["逐字段覆盖率"][k]
            w.writerow([k, a["公司口径%"], a["格子口径%"],
                        b["公司口径%"], b["格子口径%"]])

    print(json.dumps(rep, ensure_ascii=False, indent=2))
    print(f"\n★ 已写 {OUT_JSON}\n★ 已写 {OUT_DIFF}\n★ 已写 {OUT_FIELD}")


if __name__ == "__main__":
    main()
