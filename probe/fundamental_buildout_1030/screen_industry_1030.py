#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 五条链的筛选条件 —— 行业分布的前后对比(2026-10-30)

三秒版:★★ 纪律要求「凡是做行业筛选的,都要报一次行业分布的前后对比」。
        ★ 本轮五条链**没有一条**写了行业规则,★★★ 但它们的筛选条件
          **事实上**在做行业筛选 —— 这件事只能量出来,不能靠配置看出来。
        ★ 所以这里报:全池 → 过完 ① 选股条件之后,每个 SIC 两位还剩几只。

★ 「还剩几只」的口径:★★ 绩效窗口内**至少有一天**进过该链候选池的票数。
★ SIC 取 PIT 版 sic_versions 的最早一条(整段窗口定一个,★ 只用于分布统计,
  ★★ 不进任何闸门 —— 进闸门必须用逐日 PIT 的那套,见 engine/ops_1029.sic_daily)。
★ 先写结果再打印。
跑法:python3 probe/fundamental_buildout_1030/screen_industry_1030.py
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import cache, data, matrices  # noqa: E402
import ops_fund_1030 as OF                # noqa: E402

OUT_JSON = os.path.join(HERE, "screen_industry_1030.json")
OUT_CSV = os.path.join(HERE, "行业分布-筛选前后-1030.csv")
CONFIG_DIR = os.path.join(HERE, "configs_1030")
CHAINS = {
    "基-2": "基-2-施洛斯极度分散.yaml",
    "基-5": "基-5-低市盈率逆向.yaml",
    "基-6": "基-6-收购者倍数.yaml",
    "基-4": "基-4-神奇公式.yaml",
    "基-12": "基-12-无自由参数子集.yaml",
}
SIC_NAME = {
    "40": "铁路", "49": "公用事业", "60": "银行", "67": "控股与投资(含REIT)",
    "37": "汽车与运输设备", "63": "保险", "62": "券商", "28": "化工与制药",
    "73": "商业服务(含软件)", "48": "通信", "65": "地产", "45": "航空",
    "30": "塑料", "36": "电子元件", "20": "食品", "38": "仪器", "35": "机械",
    "13": "油气开采", "50": "批发(耐用品)", "51": "批发(非耐用品)",
    "58": "餐饮", "59": "零售(杂)", "61": "非银信贷", "23": "服装",
}


def sic2(sym: str) -> str:
    p = data.load_manifest()[sym].fundamentals_path
    if not p:
        return "??"
    with open(p, encoding="utf-8") as fh:
        sv = json.load(fh).get("sic_versions") or []
    if not sv:
        return "??"
    code = str(sorted(sv, key=lambda x: str(x.get("accepted_at")))[0]
               .get("sic_code") or "")
    return code[:2] if len(code) >= 2 else "??"


def main() -> int:
    OF.install(with_operating_income=False)
    man = data.load_manifest()
    have = set(cache.symbols())
    syms = [s for s in sorted(man) if man[s].fundamentals_path and s in have]
    sic = {s: sic2(s) for s in syms}

    lo, hi = pd.Timestamp("2018-01-01"), pd.Timestamp("2020-12-31")
    rows = []
    per_chain = {}
    for cid, fn in CHAINS.items():
        raw = yaml.safe_load(open(os.path.join(CONFIG_DIR, fn), encoding="utf-8"))
        uni = matrices.universe_mask(raw.get("universe") or {}, syms)
        sub = uni.loc[(uni.index >= lo) & (uni.index <= hi)]
        kept = set(sub.columns[sub.any(axis=0)])
        per_chain[cid] = {"过筛的票数": len(kept), "全池": len(syms)}
        for s in syms:
            rows.append({"链": cid, "symbol": s, "SIC2": sic[s],
                         "过筛": s in kept})
    df = pd.DataFrame(rows)
    tab = (df.groupby(["链", "SIC2"])
             .agg(全池=("symbol", "size"), 过筛=("过筛", "sum")).reset_index())
    tab["保留率"] = (tab["过筛"] / tab["全池"]).round(3)
    tab["行业名"] = tab["SIC2"].map(SIC_NAME).fillna("")
    out = {
        "窗口": "2018-01-01 .. 2020-12-31(研发池)",
        "口径": "★ 绩效窗口内至少有一天进过该链候选池 = 「过筛」",
        "每条链": per_chain,
        "重点行业(★ 1030 已查实偏斜的那几类)": {
            cid: {f"SIC {k} {SIC_NAME.get(k,'')}": [
                int(tab[(tab['链'] == cid) & (tab['SIC2'] == k)]['全池'].sum()),
                int(tab[(tab['链'] == cid) & (tab['SIC2'] == k)]['过筛'].sum())]
                for k in ("40", "49", "60", "67", "37", "63")}
            for cid in CHAINS},
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    tab.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    try:
        print(json.dumps(out, ensure_ascii=False, indent=2))
    except Exception as e:
        print(f"(打印出错,结果已写出:{type(e).__name__}: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
