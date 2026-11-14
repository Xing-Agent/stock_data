#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把微仓全接每条策略的 out/*.json 汇成一张表。「跑不了」和「有数」分开记。"""
import csv, glob, io, json, os
H = os.path.dirname(os.path.abspath(__file__))
rows, bad = [], []
for f in sorted(glob.glob(os.path.join(H, "out", "*.json"))):
    r = json.load(io.open(f, encoding="utf-8"))
    if "跑失败" in r:
        bad.append({"策略": r["名"], "原因": r["跑失败"].split("\n")[0][:120]})
        continue
    z, w = r["正常版"], r["微仓版_全部信号"]
    d = r.get("3_被丢信号") or {}
    a = [x["复合年化pct"] for x in r.get("4_起始日挪动", []) if x["复合年化pct"] is not None]
    rows.append({"策略": r["名"], "正常版笔数": z.get("笔数"), "全部信号笔数": w.get("笔数"),
                 "信号成交率pct": r.get("1_信号成交率pct"),
                 "正常版每笔均收益pct": z.get("每笔均收益pct"), "全部信号每笔均收益pct": w.get("每笔均收益pct"),
                 "正常版减全部信号pct": (None if z.get("每笔均收益pct") is None or w.get("每笔均收益pct") is None
                                  else round(z["每笔均收益pct"] - w["每笔均收益pct"], 2)),
                 "排序提升度_对得上那批pct": r.get("2_排序提升度pct"), "对得上的笔数": r.get("对得上的笔数"),
                 "被丢信号笔数": d.get("笔数"), "被丢信号每笔均收益pct": d.get("每笔均收益pct"),
                 "被丢信号胜率pct": d.get("胜率pct"),
                 "微仓版同时持仓峰值": r.get("微仓版同时持仓上限占用"),
                 "1000个位子顶满过": (r.get("微仓版同时持仓上限占用") or 0) >= 990,
                 "起始日挪动_年化最低pct": min(a) if a else None, "起始日挪动_年化最高pct": max(a) if a else None,
                 "起始日挪动_年化标准差pct": r.get("4_年化标准差pct"), "窗口": r.get("窗口")})
for name, data in (("微仓全接_汇总_1114.csv", rows), ("微仓全接_跑不了_1114.csv", bad)):
    with io.open(os.path.join(H, name), "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(data[0].keys())); w.writeheader(); w.writerows(data)
print(len(rows), len(bad))
