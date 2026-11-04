#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 符号级可算率 —— ★ 这是《35》预言一**真正用的那个口径**,必须单独报

三秒版(大白话):
  预言一里的「可算率应 ≥95%」那些数,是拿**「250 只票里有多少只有这个科目」**
  写出来的。★★ 但真跑的时候,分母是**(交易日 × 票)的格子**,
  ★★★ 两个口径的数系统性不一样 —— 所以两个都得报,判预言要用它自己的口径。

★ 为什么会不一样(根因,不是借口):
  TTM 流量科目(收入 / 营业成本 / 经营现金流 / 回购 / 分红 / 增发)
  要**凑满 4 个连续季度的 YTD 差分**才出第一个值,★★ 而老库里很多票的
  记录是 2018 年以后才开始、或者 2022 年就断了 —— ★★★ 所以「这只票有这个科目」
  不等于「2018–2020 每一天都算得出来」。
  ★ 实测对照(窗口内日频 vs 符号级):
      总资产(存量)  97.8% vs 99.2%   ← ★ 存量科目几乎不掉
      营业成本(TTM) 45.2% vs 68.4%   ← ★★★ 流量科目掉一大截
      增发(TTM)     23.7% vs 50.4%
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import cache, data   # noqa: E402

#: ★ 每条臂「符号级算得出」要的科目(★★ 全部都要有才算得出,缺一个 = 算不出来)
NEED = {
    "扩1-orig(原著·资产负债表法)": ["CurrentAssets", "CurrentLiabilities",
                                     "CashAndCashEquivalentsAtCarryingValue",
                                     "DepreciationDepletionAndAmortization",
                                     "IncomeTaxesPayable"],
    "扩1-ours(现金流量表法)": ["NetIncome", "OperatingCashFlow", "TotalAssets"],
    "扩2-orig(总资产增速)": ["TotalAssets"],
    "扩2-ours(经营资产增速)": ["TotalAssets",
                               "CashAndCashEquivalentsAtCarryingValue"],
    "扩3-orig-bm(账面/市值)": ["StockholdersEquity",
                               "WeightedAverageDilutedShares"],
    "扩3-orig-cp(现金流/价)": ["OperatingCashFlow",
                               "WeightedAverageDilutedShares"],
    "扩3-orig-ep(盈利/价)": ["NetIncome", "WeightedAverageDilutedShares"],
    "扩3-ours(名次中位数)": ["StockholdersEquity", "OperatingCashFlow",
                             "NetIncome", "WeightedAverageDilutedShares"],
    "扩4(Net-Net 两版同口径)": ["CurrentAssets", "Liabilities",
                                "WeightedAverageDilutedShares"],
    "扩5-orig(存货异常)": ["InventoryNet", "Revenue"],
    "扩6(毛利质量 两版同口径)": ["Revenue", "CostOfRevenue", "TotalAssets"],
    "扩7-orig(股东回报)": ["PaymentsForRepurchaseOfCommonStock",
                           "__DIV__", "ProceedsFromIssuanceOfCommonStock"],
    "扩8-ours(盈利加速那一半)": ["Revenue", "DilutedEPS"],
}


def main() -> int:
    man = data.load_manifest()
    have = set(cache.symbols())
    syms = [s for s in sorted(man) if man[s].fundamentals_path and s in have]
    n = len(syms)
    fvs = {}
    for s in syms:
        with open(man[s].fundamentals_path, encoding="utf-8") as fh:
            fvs[s] = json.load(fh).get("financial_versions") or {}

    def ok(s: str, metric: str) -> bool:
        fv = fvs[s]
        if metric == "__DIV__":
            # ★★★ 这就是预言一里登记为「不确定」的那一项:
            #   两个分红科目**并集**(不相加 —— 后者是前者子集)
            return bool(fv.get("PaymentsOfDividends")
                        or fv.get("PaymentsOfDividendsCommonStock"))
        return bool(fv.get(metric))

    out = {
        "★口径": "分母 = 250(有 fundamentals.json 且有行情的票)。"
                  "★★ 「算得出」= 要用的科目**全都有**(缺一个就算不出来)。"
                  "★★★ 这是《35》预言一写死时用的那个口径。",
        "票数": n,
        "逐条": {},
        "★★★分红科目能不能补上(预言一的不确定项)": {},
    }
    for arm, need in NEED.items():
        good = [s for s in syms if all(ok(s, m) for m in need)]
        out["逐条"][arm] = {
            "要的科目": need,
            "符号级可算只数": len(good),
            "★符号级可算率": round(len(good) / n, 4),
        }
    d1 = {s for s in syms if fvs[s].get("PaymentsOfDividends")}
    d2 = {s for s in syms if fvs[s].get("PaymentsOfDividendsCommonStock")}
    out["★★★分红科目能不能补上(预言一的不确定项)"] = {
        "PaymentsOfDividends 单独": {"只数": len(d1), "占比": round(len(d1) / n, 4)},
        "PaymentsOfDividendsCommonStock 单独":
            {"只数": len(d2), "占比": round(len(d2) / n, 4)},
        "★并集(= 真正能用到的分红覆盖)":
            {"只数": len(d1 | d2), "占比": round(len(d1 | d2) / n, 4)},
        "交集": {"只数": len(d1 & d2), "占比": round(len(d1 & d2) / n, 4)},
        "★★结论": "★★★ 另一个分红科目**确实能补上一大截**(37.6% → 68.0%),"
                   "★ 但**补不到 ≥80%**。"
                   "★★ 而且股东回报整条的瓶颈不在分红,在**增发**(50.4%):"
                   "三项全齐只有 28.0%。",
    }
    with open(os.path.join(HERE, "symbol_cov_1104.json"), "w",
              encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    for arm, v in out["逐条"].items():
        print(f"{arm:34s} {v['符号级可算只数']:4d}  {v['★符号级可算率']:6.1%}")
    print(json.dumps(out["★★★分红科目能不能补上(预言一的不确定项)"],
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
