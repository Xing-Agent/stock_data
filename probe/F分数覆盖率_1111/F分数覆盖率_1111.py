# -*- coding: utf-8 -*-
"""
Piotroski F 分数九项 —— 在全池基本面库里的「真实覆盖率」。

大白话:这个脚本不是看「字段名在不在」,是看「这一项到底算不算得出来」。
一项算得出来,要同时满足:
  1) 它要用的每个科目,在 2015-01-01 ~ 2025-12-31 这段里**真的有非空数值**;
  2) 同比项(③⑤⑥⑦⑧⑨)还得**至少有两个相邻财年**都有数 —— 只有一期没法比同比;
  3) 要用两个科目的项(比如 ROA = 净利润/总资产),这两个科目得落在**同一个财年**上,
     不能一个有 2018、一个只有 2022 就算过。

输出:九项各自的覆盖率、九项全齐的只数和占比,外加两只票的逐项判定明细(供手工核对)。

硬规矩:只读 fundamentals_ext/,不碰 engine/ 下任何东西。取不到就报「取不到」,不填估计值。

用法:
    python3 probe/F分数覆盖率_1111/F分数覆盖率_1111.py --sample 200   # 200 只抽样(默认)
    python3 probe/F分数覆盖率_1111/F分数覆盖率_1111.py --all          # 全池
"""
from __future__ import annotations

import argparse
import gzip
import json
import os
import random
import sys
import time
from collections import Counter
from concurrent.futures import ProcessPoolExecutor

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
FUND = os.path.join(ROOT, "fundamentals_ext")
PRICE = os.path.join(ROOT, "market_ext_1105")   # 价格池,只用来做个交集参考

PERF_START = "2015-01-01"
PERF_END = "2025-12-31"
SEED = 20261111                                  # 固定随机种子,抽样可复现

# ---------------------------------------------------------------- 字段名解析
#
# ★ 口径说明(中途改过判据,原因写在这):
#   任务单说「匹配时用包含而不是精确相等」。实测发现**纯包含会串线**:
#   小写后 "revenue" 是 "costofrevenue"、"deferredrevenuecurrent" 的子串,
#   "longtermdebt" 是 "longtermdebtcurrent"(当期到期部分,不是长期负债)的子串。
#   所以改成**两段式**:先在规范化后的科目名上找精确相等,找不到才退回包含。
#   这样 Revenue / LongTermDebt 能精确命中,股数那类(sharesoutstanding)仍靠包含兜住。
#
# 规范化 = 去掉 "us-gaap:" / "dei:" 这类前缀,去掉 "|USD" / "|shares" 这类后缀,再转小写。


def _norm(key: str) -> str:
    k = key.split(":")[-1]
    k = k.split("|")[0]
    return k.strip().lower()


def _resolve(index: dict, want: str) -> str | None:
    """index: {规范化名 -> 原始 key}。先精确,再包含(包含时取名字最短的,避免挂到长变体上)。"""
    if want in index:
        return index[want]

    hits = [n for n in index if want in n]
    if not hits:
        return None
    return index[min(hits, key=len)]


# ---------------------------------------------------------------- 年度观测抽取

def _years_from_financial_versions(recs: list) -> set:
    """financial_versions 里一条 metric 的记录列表 -> 有非空数值的财年集合。

    只认 fiscal_period == 'FY'(库里 meta 说 fiscal_year/fiscal_period 是按期间日期和
    财年末推出来的**经济期间**,所以 FY 就是年度那个点,不管它登在 10-K 还是 10-Q 上)。
    """
    out = set()
    for r in recs or []:
        if r.get("fiscal_period") != "FY":
            continue
        v = r.get("value")
        if v is None or v == "":
            continue
        pe = r.get("period_end")
        fy = r.get("fiscal_year")
        if not pe or fy is None:
            continue
        if not (PERF_START <= str(pe)[:10] <= PERF_END):
            continue
        try:
            float(v)
        except (TypeError, ValueError):
            continue
        out.add(int(fy))
    return out


def _years_from_raw_tags(rows: list, fields: list) -> set:
    """raw_tags 里一条 tag 的行列表(数组形式)-> 有非空数值的财年集合。"""
    try:
        i_val, i_end, i_fy, i_fp = (fields.index(x) for x in ("val", "end", "fy", "fp"))
    except ValueError:
        return set()
    out = set()
    for r in rows or []:
        if len(r) <= max(i_val, i_end, i_fy, i_fp):
            continue
        if r[i_fp] != "FY":
            continue
        v = r[i_val]
        if v is None or v == "":
            continue
        end = r[i_end]
        if not end or not (PERF_START <= str(end)[:10] <= PERF_END):
            continue
        try:
            float(v)
        except (TypeError, ValueError):
            continue
        if r[i_fy] is None:
            continue
        out.add(int(r[i_fy]))
    return out


# ---------------------------------------------------------------- 九项定义
#
# 每项:要哪些科目(都要齐)、是不是同比项(同比项要两个相邻财年)。
# 第⑧项特殊:毛利率可以走 grossprofit,也可以走 revenue - costofrevenue,二者取其一。

NEED = {
    "①ROA>0":        (["netincome", "totalassets"], False),
    "②经营现金流>0":   (["operatingcashflow"], False),
    "③ROA同比改善":   (["netincome", "totalassets"], True),
    "④现金流>净利润":  (["operatingcashflow", "netincome"], False),
    "⑤长期杠杆下降":   (["longtermdebt", "totalassets"], True),
    "⑥流动比率上升":   (["currentassets", "currentliabilities"], True),
    "⑦未增发稀释":     (["__shares__"], True),
    "⑧毛利率同比改善":  (["revenue", "__gross__"], True),
    "⑨资产周转同比改善": (["revenue", "totalassets"], True),
}

# 单科目字段(直接解析一个名字)
PLAIN = ["netincome", "totalassets", "operatingcashflow", "longtermdebt",
         "currentassets", "currentliabilities", "grossprofit", "costofrevenue", "revenue"]
# 股数:任务单给了两个备选名,任一有值即可
SHARES_ALT = ["sharesoutstanding", "commonstockshares"]
# 旁证:引擎实际用的摊薄股数科目,只做参考统计,不参与判定
SHARES_REF = "weightedaveragedilutedshares"


def _ok(years_sets: list, yoy: bool) -> bool:
    """给定每个所需科目的「有数财年集合」,判断这一项算不算得出来。

    非同比项:交集 >= 1 个财年。
    同比项  :交集里要有**相邻两年**(t 和 t-1),不然没法做同比。
    """
    if not years_sets or any(not s for s in years_sets):
        return False
    common = set.intersection(*years_sets)
    if not common:
        return False
    if not yoy:
        return True
    return any((y - 1) in common for y in common)


def judge(symbol: str) -> dict | None:
    """算一只票的九项判定。返回 None 表示连库都没有。"""
    path = os.path.join(FUND, symbol, "fundamentals.json.gz")
    if not os.path.exists(path):
        return None
    try:
        with gzip.open(path, "rt") as f:
            d = json.load(f)
    except (OSError, ValueError):
        return None

    fv = d.get("financial_versions") or {}
    rt = d.get("raw_tags") or {}
    rtf = d.get("raw_tags_fields") or []

    fv_idx = {_norm(k): k for k in fv}
    rt_idx = {_norm(k): k for k in rt}

    def years(want: str) -> set:
        """一个科目的有数财年:两边库都查,取并集(并集才是「真能取到」)。"""
        out = set()
        k = _resolve(fv_idx, want)
        if k is not None:
            out |= _years_from_financial_versions(fv[k])
        k = _resolve(rt_idx, want)
        if k is not None:
            out |= _years_from_raw_tags(rt[k], rtf)
        return out

    Y = {w: years(w) for w in PLAIN}
    # 股数:两个备选名的财年取并集
    Y["__shares__"] = set().union(*(years(w) for w in SHARES_ALT))
    # 毛利率分子:grossprofit 直接有,或 costofrevenue 有(配 revenue 自己减)
    Y["__gross__"] = Y["grossprofit"] | Y["costofrevenue"]

    res = {}
    for name, (fields, yoy) in NEED.items():
        res[name] = _ok([Y[f] for f in fields], yoy)

    return {
        "symbol": symbol,
        "items": res,
        "all9": all(res.values()),
        "years": {k: sorted(v) for k, v in Y.items()},
        "shares_ref_years": sorted(years(SHARES_REF)),
    }


# ---------------------------------------------------------------- 自证打印

def 自证(symbols: list):
    print("=" * 78)
    print("【自证】逐项判定明细 —— 下面每只票的每一项都写清了「用了哪些科目、各自哪些财年有数」,")
    print("        可以直接 zcat fundamentals_ext/<T>/fundamentals.json.gz 手工核。")
    print("=" * 78)
    for s in symbols:
        r = judge(s)
        if r is None:
            print(f"\n--- {s}:库里没有这只,取不到 ---")
            continue
        print(f"\n--- {s} ---  九项全齐: {'是' if r['all9'] else '否'}")
        for name, (fields, yoy) in NEED.items():
            detail = []
            for f in fields:
                ys = r["years"][f]
                detail.append(f"{f}={ys if ys else '取不到'}")
            tag = "同比(要相邻两年)" if yoy else "当期(要≥1年)"
            print(f"  {name:<14} {'通过' if r['items'][name] else '不通过'}  [{tag}]  " + " ; ".join(detail))
        print(f"  (旁证·不参与判定) {SHARES_REF} 有数财年 = {r['shares_ref_years'] or '取不到'}")


# ---------------------------------------------------------------- 主流程

def 跑(symbols: list, 标题: str, workers: int):
    t0 = time.time()
    cnt = Counter()
    all9 = 0
    无库 = 0
    done = 0
    with ProcessPoolExecutor(max_workers=workers) as ex:
        for r in ex.map(judge, symbols, chunksize=16):
            done += 1
            if r is None:
                无库 += 1
                continue
            for name, ok in r["items"].items():
                if ok:
                    cnt[name] += 1
            if r["all9"]:
                all9 += 1
            if done % 500 == 0:
                print(f"    ...{done}/{len(symbols)}  ({time.time()-t0:.0f}s)", flush=True)

    n = len(symbols)
    print()
    print("=" * 78)
    print(f"【{标题}】分母 = {n} 只")
    print(f"  绩效窗口 {PERF_START} ~ {PERF_END};同比项要求至少两个相邻财年都有数")
    print(f"  其中「连 fundamentals.json.gz 都没有」: {无库} 只(这部分九项一律不通过)")
    print("=" * 78)
    for name in NEED:
        c = cnt[name]
        print(f"  {name:<14} {c:>5} / {n}  = {c/n*100:5.1f}%")
    print("-" * 78)
    print(f"  ★ 九项全齐      {all9:>5} / {n}  = {all9/n*100:5.1f}%")
    print(f"  (耗时 {time.time()-t0:.0f}s)")
    return {"n": n, "无库": 无库, "每项": dict(cnt), "九项全齐": all9,
            "耗时秒": round(time.time() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=200, help="抽样只数(默认 200)")
    ap.add_argument("--all", action="store_true", help="跑全池")
    ap.add_argument("--交集", action="store_true",
                    help="再跑一遍「财报库 ∩ 价格池」(真正能回测的池子)")
    ap.add_argument("--诊断", action="store_true",
                    help="统计缺口成因:空库 / 窗口外 / 只缺毛利科目")
    ap.add_argument("--workers", type=int, default=min(16, (os.cpu_count() or 4)))
    ap.add_argument("--json", default=os.path.join(HERE, "F分数覆盖率_1111.json"))
    a = ap.parse_args()

    pool = sorted(d for d in os.listdir(FUND)
                  if os.path.isdir(os.path.join(FUND, d)))
    有库 = [d for d in pool
           if os.path.exists(os.path.join(FUND, d, "fundamentals.json.gz"))]

    print("=" * 78)
    print("Piotroski F 分数九项 —— 真实覆盖率(看有没有值,不是看字段名在不在)")
    print("=" * 78)
    print(f"  fundamentals_ext 下 ticker 目录数        : {len(pool)}")
    print(f"  其中有 fundamentals.json.gz 的           : {len(有库)}")
    if os.path.isdir(PRICE):
        价 = set(os.listdir(PRICE))
        print(f"  价格池 market_ext_1105 目录数            : {len(价)}")
        print(f"  两边交集(真正能回测的池子)              : {len(set(有库) & 价)}")
    print()

    out = {"窗口": [PERF_START, PERF_END], "种子": SEED,
           "fundamentals_ext_目录数": len(pool), "有库只数": len(有库)}

    # ---- 自证:固定两只票 + 抽样里的头一只
    自证(["AAPL", "KO"])

    # ---- 抽样
    rnd = random.Random(SEED)
    smp = rnd.sample(pool, min(a.sample, len(pool)))
    print()
    print(f"★★★ 抽样说明:下面这组结果是从 {len(pool)} 个 ticker 目录里"
          f"用固定随机种子 SEED={SEED} 随机抽的 {len(smp)} 只,**不是全池**。")
    out["抽样"] = 跑(smp, f"抽样 {len(smp)} 只 —— 不是全池", a.workers)
    out["抽样_种子"] = SEED

    # ---- 全池
    if a.all:
        print()
        print(f"★★★ 下面是**全池** {len(pool)} 只的结果(分母含没有财报库的那些)。")
        out["全池"] = 跑(pool, f"全池 {len(pool)} 只", a.workers)

    with open(a.json, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print(f"\n结果已写 {a.json}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
