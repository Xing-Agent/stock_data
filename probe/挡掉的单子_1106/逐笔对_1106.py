# -*- coding: utf-8 -*-
"""
★★★ 挂闸挡掉了哪些单子 —— **逐笔对股票和日期**，★ 不用两边毛利相减。

★★ 为什么不能相减（第 43 轮 Gemini 那处算错了，我们不采信）:
   挂闸那次跑出的 578 笔**不是**不挂闸 651 笔的子集 ——
   ★ 最多持 10 只、仓位跟着净值变,★★★ 闸一挂,后面开哪些仓**全变了**。
   → ★★ 所以「挡掉 73 笔、赚了 66 万」这个算法是错的。

★★★ 正确做法:按 (股票, 进场日) 配对,分三堆:
   ① **只有不挂闸有** → 这才是真正「被闸挡掉的」
   ② **只有挂闸有**   → ★★ 闸腾出了仓位,所以多开的(★★★ 这堆最容易被忽略)
   ③ **两边都有**     → 同一笔,★ 对比它们的成绩差(应当很小)
★ engine 零改动,只读流水。
"""
import os, sys, json, glob
import pandas as pd, numpy as np

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(ROOT)
LED = "probe/挂闸_1106/ledgers_1106"
OUT = "probe/挡掉的单子_1106"


def 读(名):
    f = os.path.join(LED, f"REAL__{名}.csv")
    if not os.path.exists(f):
        return None
    d = pd.read_csv(f)
    d["entry_date"] = pd.to_datetime(d["entry_date"], errors="coerce")
    d["键"] = d["symbol"].astype(str) + "|" + d["entry_date"].dt.strftime("%Y-%m-%d")
    return d


def 一对(无闸名, 有闸名):
    a, b = 读(无闸名), 读(有闸名)
    if a is None or b is None:
        return {"★跑失败": "流水缺失", "无闸": 无闸名, "有闸": 有闸名}
    ka, kb = set(a["键"]), set(b["键"])
    只无 = a[a["键"].isin(ka - kb)]
    只有 = b[b["键"].isin(kb - ka)]
    共 = ka & kb

    def 摘(d, 名):
        if d.empty:
            return {"笔数": 0}
        g = pd.to_numeric(d["gross_pnl"], errors="coerce")
        r = pd.to_numeric(d["r_multiple_net"], errors="coerce")
        年 = d["entry_date"].dt.year.value_counts().sort_index()
        return {
            "笔数": int(len(d)),
            "毛盈亏合计美元": round(float(g.sum()), 0),
            "每笔毛盈亏中位": round(float(g.median()), 0),
            "每笔净R平均": round(float(r.mean()), 4),
            "赚钱笔占比": f"{float((g > 0).mean())*100:.1f}%",
            "★按年分布": {int(k): int(v) for k, v in 年.items()},
            "★最大一笔毛赚": round(float(g.max()), 0),
            "★最大一笔毛亏": round(float(g.min()), 0),
        }
    return {
        "①只有不挂闸有（★★★ 这才是真被闸挡掉的）": 摘(只无, "只无"),
        "②只有挂闸有（★★ 闸腾出仓位后多开的）": 摘(只有, "只有"),
        "③两边都有的笔数": len(共),
        "★★★ 读法": "★ ①的毛利 − ②的毛利 才是闸的净代价；"
                  "★★ 直接拿两边总毛利相减是错的（仓位和槽位都变了）",
    }


def main() -> int:
    报 = {"★口径": {
        "配对键": "(股票代码, 进场日)",
        "★★★为什么不相减": "挂闸后开哪些仓全变了，578 笔不是 651 笔的子集",
        "engine改动": "零",
        "★不给建议": "只列数字，不写「该不该挂」",
    }}
    for 派, 卡 in (("震荡", "技-14-原著"), ("突破", "技-6-原著"), ("大波段", "技-1")):
        for ma in (100, 200, 300):
            名 = f"{派}·{卡}·挂闸{ma}日"
            报[f"{派} 不挂闸 vs 挂闸{ma}日"] = 一对(f"{派}·{卡}·不挂闸", 名)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "挡掉的单子_报告_1106.json"), "w", encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print(json.dumps(报, ensure_ascii=False, indent=1)[:3000])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
