# -*- coding: utf-8 -*-
"""★ 《100》3.5 第 1 件:4 档环境在 2016-01-04~2025-12-31 的各档天数和占比 —— 先看有没有哪格样本太少。
门槛相邻三点:均线 100/200/300 × 实际波动回看 10/20/40 × 中位数回看 126/252/504(全组合 27 个)。
★ 档位按「昨收」口径(即环境闸当天生效时看到的那一档)。"""
import io, json, os, sys, itertools
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import numpy as np, pandas as pd
import 台_1107 as T
T.data.PERF_START = T.START
s = T.data.load_benchmark("SPY")["close"].dropna()
idx = s.index[(s.index >= T.START) & (s.index <= T.data.PERF_END)]
out = {"窗口": f"{idx[0].date()} ~ {idx[-1].date()}", "交易日": len(idx), "组合": {}}
档序 = ["顺风", "震荡放大", "阴跌", "暴跌", "未定"]
for ma, vl, ml in itertools.product((100, 200, 300), (10, 20, 40), (126, 252, 504)):
    d = T.二乘二(s.index, ma, vl, ml)["档"].shift(1).reindex(idx)
    c = d.value_counts()
    # 段数(连续同档算一段)和最短段
    seg = (d != d.shift()).cumsum()
    段 = d.groupby(seg).agg(["first", "size"])
    k = f"均线{ma}·波动{vl}·中位{ml}"
    out["组合"][k] = {
        "天数": {a: int(c.get(a, 0)) for a in 档序},
        "占比": {a: round(float(c.get(a, 0)) / len(idx), 4) for a in 档序},
        "段数": {a: int((段["first"] == a).sum()) for a in 档序[:4]},
        "平均段长(天)": {a: round(float(段[段["first"] == a]["size"].mean()), 1) if (段["first"] == a).any() else None for a in 档序[:4]},
    }
中 = "均线200·波动20·中位252"
相邻 = {"均线": [f"均线{x}·波动20·中位252" for x in (100, 200, 300)],
      "波动回看": [f"均线200·波动{x}·中位252" for x in (10, 20, 40)],
      "中位回看": [f"均线200·波动20·中位{x}" for x in (126, 252, 504)]}
out["★中心点"] = 中
out["★相邻三点(其余两个旋钮固定在中心)"] = {g: {k: out["组合"][k]["占比"] for k in ks} for g, ks in 相邻.items()}
最少 = min(((k, a, v["天数"][a]) for k, v in out["组合"].items() for a in 档序[:4]), key=lambda x: x[2])
out["★27 个组合里最少的一格"] = {"组合": 最少[0], "档": 最少[1], "天数": 最少[2]}
out["★暴跌档天数 · 27 组合范围"] = [min(v["天数"]["暴跌"] for v in out["组合"].values()), max(v["天数"]["暴跌"] for v in out["组合"].values())]
io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "档位占比_1107.json"), "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
for g, ks in 相邻.items():
    for k in ks:
        v = out["组合"][k]; print(k, v["天数"], v["段数"], v["平均段长(天)"])
print(out["★27 个组合里最少的一格"], out["★暴跌档天数 · 27 组合范围"])
