#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 覆盖率三分类(甲/乙/丙)—— 2026-10-30

三秒版:EBIT 70.8% / LongTermDebt 56.0%。★ 缺的那部分不是「数据源没给」,
        是**我们只认一个 us-gaap 标签**。本文件把缺的逐只归到三类并给三个数。

★★★ 分类口径(跑之前定稿,★ 一个新阈值都没拍):
  丙 = 这个方法对这类公司本来就不适用 —— SIC 6000–6799(银行/保险/券商/REIT)。
       ★ 理由不是「数据缺」:质量复利的 ROIC(投入资本 = 有息负债+权益−现金)和
         净负债/EBITDA 这两个判据,在银行上**没有经济含义**(存款是它的原材料,
         不是杠杆)。→ 要写进方法卡的「不适用」。
  乙 = 这家公司**确有**长期债务,只是用了别的 us-gaap 标签报 → ★ 我们取数取窄了。
       判据二选一(都来自本地已有数据,不是推断):
         乙-1 有 `LongTermDebtCurrent` 记录(= 长期债务的当期到期部分存在,
              那么非当期部分必然也曾存在)
         乙-2 非当期负债 NCL = (TotalAssets − StockholdersEquity) − CurrentLiabilities
              > 0 且占总资产比例 **落在 140 只「有 LongTermDebt」票的同一区间内**
              (★ 区间是从那 140 只实测出来的,不是我们拍的)
  甲 = 这家公司确实没有这一项 → 正确答案是 0,不是缺。
       判据:NCL ≤ 0(把负债全算成流动负债都还有余)—— ★ 这是恒等式,不是估计。
  ★ 剩下判不了的单列一类「丁·本地证据不足」,★★ 不塞进甲 ——
    把判不了的塞进甲就等于把我们自己的 bug 说成「公司本来就没有」。

★★ 本地无法连 SEC(代理 403),所以「乙」是**本地可证的下限**,不是上限。
   ★ 这件事必须写在报告里,不许把下限当成终值。

跑法:python3 probe/masters_57_1030/coverage_triage_1030.py
"""
from __future__ import annotations

import collections
import glob
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import data, fundamentals, pool_scope          # noqa: E402

PILOT = os.path.join(ROOT, "pilot_300")
OUT = os.path.join(HERE, "coverage_triage_1030.json")

#: ★ 评估断面(和 1028 审计报告同三个断面,便于横向比)
SNAPSHOTS = ("2018-06-30", "2022-06-30", "2025-06-30")


def load_meta() -> dict:
    """每只票:各字段的记录数 / PIT 合格数 / source_tag 集合 / 最新 SIC。"""
    out = {}
    for f in sorted(glob.glob(os.path.join(PILOT, "*", "fundamentals.json"))):
        sym = os.path.basename(os.path.dirname(f))
        with open(f, encoding="utf-8") as fh:
            d = json.load(fh)
        fv = d.get("financial_versions") or {}
        rec = {"记录数": {}, "PIT合格数": {}, "标签": {}}
        for k, v in fv.items():
            v = v or []
            rec["记录数"][k] = len(v)
            rec["PIT合格数"][k] = sum(1 for r in v if r.get("pit_eligible"))
            rec["标签"][k] = sorted({(r.get("source_tag") or r.get("source_type") or "?")
                                     for r in v})
        sv = d.get("sic_versions") or []
        sic = None
        if sv:
            sic = sorted(sv, key=lambda x: (x.get("accepted_at") or x.get("filed_at") or ""))[-1]
        rec["SIC"] = (sic or {}).get("sic_code")
        rec["SIC说明"] = (sic or {}).get("sic_description")
        rec["derived_EBIT"] = ((d.get("coverage") or {}).get("derived_metrics")
                               or {}).get("EBIT", {})
        out[sym] = rec
    return out


def is_financial(sic) -> bool:
    return bool(sic) and str(sic).isdigit() and 6000 <= int(sic) <= 6799


def ncl_ratio(sym: str) -> tuple[float | None, dict]:
    """
    非当期负债占总资产 —— ★ 走引擎自己的 PIT 层(fundamentals.quarter_frame),
    不另写一套取数。NCL = (TotalAssets − StockholdersEquity) − CurrentLiabilities。
    ★ 取「最后一个三项同时有值的季度」,报那一期的比值。
    """
    try:
        vals, _ef = fundamentals.quarter_frame(sym)
    except Exception as exc:                                    # noqa: BLE001
        return None, {"错": f"{type(exc).__name__}: {exc}"}
    if vals.empty:
        return None, {"错": "quarter_frame 为空"}
    need = ["ta", "eq", "cl"]
    ok = vals[need].notna().all(axis=1) & (vals["ta"] > 0)
    if not ok.any():
        return None, {"错": "TA/EQ/CL 三项没有同时有值的季度"}
    row = vals[ok].iloc[-1]
    ncl = float(row["ta"] - row["eq"] - row["cl"])
    return ncl / float(row["ta"]), {
        "期末": str(vals[ok].index[-1].date()),
        "TotalAssets": float(row["ta"]), "StockholdersEquity": float(row["eq"]),
        "CurrentLiabilities": float(row["cl"]), "NCL": ncl,
    }


def main() -> int:
    meta = load_meta()
    syms = sorted(meta)
    print(f"有 fundamentals.json 的票:{len(syms)} 只")

    # ── ① 标签审计:我们对每个字段实际只认了哪些 us-gaap 标签
    tag_audit: dict[str, collections.Counter] = {}
    for s in syms:
        for k, tg in meta[s]["标签"].items():
            tag_audit.setdefault(k, collections.Counter()).update(tg)
    print("\n★★★ 标签审计(每个字段实际收到的 us-gaap 标签,★ 这是取窄的证据):")
    for k in ("LongTermDebt", "LongTermDebtCurrent", "ShortTermBorrowings",
              "DebtCurrent", "Liabilities", "EBIT"):
        print(f"  {k:22s} {dict(tag_audit.get(k, {}))}")

    have_ltd = [s for s in syms if meta[s]["记录数"].get("LongTermDebt", 0) > 0]
    miss_ltd = [s for s in syms if meta[s]["记录数"].get("LongTermDebt", 0) == 0]
    have_ebit = [s for s in syms if meta[s]["记录数"].get("EBIT", 0) > 0]
    miss_ebit = [s for s in syms if meta[s]["记录数"].get("EBIT", 0) == 0]
    print(f"\nLongTermDebt 有 {len(have_ltd)} / 缺 {len(miss_ltd)}"
          f"  ({len(have_ltd)/len(syms):.1%})")
    print(f"EBIT         有 {len(have_ebit)} / 缺 {len(miss_ebit)}"
          f"  ({len(have_ebit)/len(syms):.1%})")

    # ── ② 从「有 LongTermDebt 的 140 只」实测出 NCL 占比的区间(★ 不是我们拍的)
    print("\n★ 先量「有 LongTermDebt 的那 140 只」的 NCL/TA 分布(用来当乙类的判据区间)")
    ref = {}
    for s in have_ltd:
        r, d = ncl_ratio(s)
        if r is not None:
            ref[s] = r
    arr = np.array(sorted(ref.values()))
    q = {f"p{p}": float(np.percentile(arr, p)) for p in (1, 5, 10, 25, 50, 75, 95, 99)}
    print(f"  可算出的 {len(arr)} 只:{ {k: round(v, 4) for k, v in q.items()} }")
    LO = q["p1"]          # ★ 区间下界 = 那 140 只的 1 分位(实测值,不是拍的)
    print(f"  ★ 乙-2 的下界取 p1 = {LO:.4f} —— ★ 这是从有数据那 140 只测出来的,"
          f"不是我们拍的一个数")

    # ── ③ 逐只归类
    rows = []
    for s in sorted(miss_ltd):
        m = meta[s]
        r, d = ncl_ratio(s)
        ltdc = m["记录数"].get("LongTermDebtCurrent", 0)
        stb = m["记录数"].get("ShortTermBorrowings", 0)
        dc = m["记录数"].get("DebtCurrent", 0)
        fin = is_financial(m["SIC"])
        if fin:
            cls, why = "丙", f"SIC {m['SIC']} {m['SIC说明']} —— 金融业,方法不适用"
        elif ltdc > 0:
            cls, why = "乙", (f"乙-1:有 LongTermDebtCurrent {ltdc} 条 —— "
                              f"长期债务的当期到期部分存在,非当期部分必然也存在")
        elif r is None:
            cls, why = "丁", f"本地算不出 NCL:{d.get('错')}"
        elif r <= 0:
            cls, why = "甲", f"NCL/TA = {r:.4f} ≤ 0 —— 恒等式口径下确实没有非当期负债"
        elif r >= LO:
            cls, why = "乙", (f"乙-2:NCL/TA = {r:.4f} ≥ p1({LO:.4f}),"
                              f"落在有 LongTermDebt 那 140 只的同一区间内"
                              + (f";另有 ShortTermBorrowings {stb} 条" if stb else "")
                              + (f";另有 DebtCurrent {dc} 条" if dc else ""))
        else:
            cls, why = "丁", f"NCL/TA = {r:.4f} 介于 0 和 p1 之间 —— 本地证据不足"
        rows.append({"票": s, "类": cls, "SIC": m["SIC"], "SIC说明": m["SIC说明"],
                     "NCL占总资产": None if r is None else round(r, 6),
                     "LongTermDebtCurrent记录": ltdc,
                     "ShortTermBorrowings记录": stb, "DebtCurrent记录": dc,
                     "理由": why, "NCL明细": d})

    cnt = collections.Counter(x["类"] for x in rows)
    print(f"\n★★★ 缺 LongTermDebt 的 {len(rows)} 只,三分类(+ 丁):")
    for k in ("甲", "乙", "丙", "丁"):
        print(f"  {k}  {cnt.get(k,0):3d} 只")
    print("\n★ 丙类里再分一刀(给策略组看,★ 本轮不替它拍板):")
    sub = collections.Counter()
    for x in rows:
        if x["类"] == "丙":
            c = int(x["SIC"])
            sub["REIT(6798/6500/6552/6531/6792)" if c in (6798, 6500, 6552, 6531, 6792)
                else "银行/保险/券商/资管"] += 1
    for k, v in sub.most_common():
        print(f"    {k:34s} {v}")

    print("\n★ 甲类逐只(这些票的正确答案是 0,不是缺):")
    for x in rows:
        if x["类"] == "甲":
            print(f"    {x['票']:7s} {x['NCL占总资产']}  {x['SIC说明']}")
    print("\n★ 丁类逐只(本地证据不足 —— ★ 不许塞进甲):")
    for x in rows:
        if x["类"] == "丁":
            print(f"    {x['票']:7s} {x['NCL占总资产']}  {x['理由'][:70]}")

    # ── ④ 同样给 EBIT 缺的 73 只一个说法
    ebit_rows = []
    for s in sorted(miss_ebit):
        m = meta[s]
        ibt = m["记录数"].get("IncomeBeforeTax", 0)
        ie = m["记录数"].get("InterestExpense", 0)
        dv = m.get("derived_EBIT") or {}
        fin = is_financial(m["SIC"])
        if fin:
            cls, why = "丙", f"SIC {m['SIC']} {m['SIC说明']} —— 金融业,方法不适用"
        elif ibt > 0 and ie == 0:
            cls, why = "乙", ("乙:有 IncomeBeforeTax 但没有 InterestExpense —— "
                              "★ 公式 IncomeBeforeTax+InterestExpense 的第二项缺标签。"
                              "★★ 无息负债公司的正确答案是 InterestExpense=0 → "
                              "EBIT=IncomeBeforeTax,所以这一格要么是甲要么是乙,"
                              "★ 本地分不开 —— 归乙(保守:算成我们的问题)")
        elif ibt == 0:
            cls, why = "丁", "连 IncomeBeforeTax 都没有 —— 本地证据不足"
        else:
            cls, why = "丁", f"两项都有但 derived 0 条:{dv.get('skipped_by_reason')}"
        ebit_rows.append({"票": s, "类": cls, "SIC": m["SIC"], "SIC说明": m["SIC说明"],
                          "IncomeBeforeTax记录": ibt, "InterestExpense记录": ie,
                          "derived": dv, "理由": why})
    c2 = collections.Counter(x["类"] for x in ebit_rows)
    print(f"\n★★ 缺 EBIT 的 {len(ebit_rows)} 只:" +
          "  ".join(f"{k} {c2.get(k,0)}" for k in ("甲", "乙", "丙", "丁")))

    # ── ⑤ 装上门槛之后 ⑤⑦ 实际能跑在几只票上 + 有没有系统性偏斜
    print("\n★★★ 装上覆盖率门槛之后的池子(⑤⑦ 实际能跑的票)")
    pool = {}
    for label, need in (("只要 EBIT", ("EBIT",)),
                        ("只要 LongTermDebt", ("LongTermDebt",)),
                        ("★ EBIT + LongTermDebt 都要(ROIC 口径)",
                         ("EBIT", "LongTermDebt")),
                        ("★ 再加 CostOfRevenue(GP/A 口径)",
                         ("EBIT", "LongTermDebt", "CostOfRevenue"))):
        keep = [s for s in syms
                if all(meta[s]["记录数"].get(k, 0) > 0 for k in need)]
        fins = sum(1 for s in keep if is_financial(meta[s]["SIC"]))
        fin_all = sum(1 for s in syms if is_financial(meta[s]["SIC"]))
        pool[label] = {"只数": len(keep), "占比": round(len(keep)/len(syms), 4),
                       "其中金融": fins, "全池金融只数": fin_all,
                       "金融保留率": round(fins/fin_all, 4) if fin_all else None,
                       "票": keep}
        print(f"  {label:36s} {len(keep):3d} 只 ({len(keep)/len(syms):5.1%})"
              f"  其中金融 {fins:2d}/{fin_all}")

    # 行业偏斜:按 SIC 两位大类比对「全池」和「门槛后」
    def sic2(s):
        c = meta[s]["SIC"]
        return (str(c)[:2] if c and str(c).isdigit() else "??")
    base = collections.Counter(sic2(s) for s in syms)
    kept = collections.Counter(sic2(s) for s in
                               pool["★ EBIT + LongTermDebt 都要(ROIC 口径)"]["票"])
    skew = []
    for k in sorted(base):
        b, kk = base[k], kept.get(k, 0)
        skew.append({"SIC两位": k, "全池": b, "门槛后": kk,
                     "保留率": round(kk/b, 4)})
    print("\n★ 行业偏斜(SIC 两位大类,★ 保留率 0 的就是被整类挡掉的):")
    for r in sorted(skew, key=lambda x: x["保留率"]):
        if r["全池"] >= 3:
            print(f"    SIC {r['SIC两位']}  全池 {r['全池']:3d} → 门槛后 "
                  f"{r['门槛后']:3d}  保留 {r['保留率']:6.1%}")

    out = {
        "口径": {
            "分类规则": "丙=SIC 6000–6799 金融(方法不适用);"
                        "乙-1=有 LongTermDebtCurrent;"
                        "乙-2=NCL/TA ≥ 有LTD那140只的 p1(实测值);"
                        "甲=NCL ≤ 0(恒等式);丁=本地证据不足(★ 不塞进甲)",
            "NCL定义": "(TotalAssets − StockholdersEquity) − CurrentLiabilities,"
                        "走 engine.fundamentals.quarter_frame 的 PIT 层",
            "★★ 本地无法连 SEC": "代理 403 —— 所以「乙」是本地可证的**下限**,不是上限",
            "乙-2下界p1": LO,
            "参照组分布": q,
        },
        "标签审计": {k: dict(v) for k, v in tag_audit.items()},
        "总数": {"有fundamentals": len(syms),
                  "LongTermDebt有": len(have_ltd), "LongTermDebt缺": len(miss_ltd),
                  "EBIT有": len(have_ebit), "EBIT缺": len(miss_ebit)},
        "LongTermDebt缺的三分类计数": dict(cnt),
        "LongTermDebt缺的逐只": rows,
        "EBIT缺的三分类计数": dict(c2),
        "EBIT缺的逐只": ebit_rows,
        "门槛后池子": pool,
        "行业偏斜": skew,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n→ {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
