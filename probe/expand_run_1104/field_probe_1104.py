#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★ 只读:数一数本轮 8 条要用到的科目在老库里有多少只票有。

三秒版:先数清楚哪一样有、哪一样没有,★★ 没有的就不跑,不拿别的顶上。
★ 一个字都不写进 engine/,也不动库文件。
"""
from __future__ import annotations
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from engine import cache, data   # noqa: E402

WANT = [
    "Revenue", "CostOfRevenue", "TotalAssets", "CurrentAssets",
    "CurrentLiabilities", "Liabilities", "InventoryNet", "OperatingCashFlow",
    "NetIncome", "StockholdersEquity", "DilutedEPS",
    "WeightedAverageDilutedShares",
    "PaymentsForRepurchaseOfCommonStock",
    "PaymentsOfDividends", "PaymentsOfDividendsCommonStock",
    "ProceedsFromIssuanceOfCommonStock",
    "CashAndCashEquivalentsAtCarryingValue",
    "DebtCurrent", "ShortTermBorrowings", "LongTermDebt", "LongTermDebtCurrent",
    # ★★★ 登记为「没有」的三样 —— 本探针亲自确认,不凭印象
    "OperatingIncomeLoss", "DepreciationDepletionAndAmortization",
    "DepreciationAmortizationAndAccretionNet",
    "SellingGeneralAndAdministrativeExpense",
    "IncomeTaxesPayable", "AccruedIncomeTaxesCurrent",
]


def main() -> int:
    man = data.load_manifest()
    have_px = set(cache.symbols())
    syms = [s for s in sorted(man) if man[s].fundamentals_path and s in have_px]
    n = len(syms)
    cov = {w: 0 for w in WANT}
    sic_n, sic_vers = 0, []
    allkeys: dict[str, int] = {}
    for s in syms:
        with open(man[s].fundamentals_path, encoding="utf-8") as fh:
            raw = json.load(fh)
        fv = raw.get("financial_versions") or {}
        for k, v in fv.items():
            if v:
                allkeys[k] = allkeys.get(k, 0) + 1
        for w in WANT:
            if fv.get(w):
                cov[w] += 1
        sv = raw.get("sic_versions") or []
        if sv:
            sic_n += 1
            sic_vers.append(len(sv))
    out = {
        "★口径": "分母 = 有 fundamentals.json 且有行情的票数",
        "票数": n,
        "要用的科目覆盖率": {w: {"只数": cov[w], "占比": round(cov[w] / n, 4)}
                             for w in WANT},
        "SIC": {"有 sic_versions 的只数": sic_n, "占比": round(sic_n / n, 4),
                "版本数中位": sorted(sic_vers)[len(sic_vers) // 2] if sic_vers else None},
        "老库里全部出现过的科目(只数)": dict(sorted(allkeys.items(),
                                                   key=lambda kv: -kv[1])),
    }
    with open(os.path.join(HERE, "field_probe_1104.json"), "w",
              encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"票数 {n}")
    for w in WANT:
        print(f"  {w:46s} {cov[w]:4d}  {cov[w]/n:6.1%}")
    print(f"SIC {sic_n}/{n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
