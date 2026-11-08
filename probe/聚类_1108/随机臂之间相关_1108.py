# -*- coding: utf-8 -*-
"""★★★★★ 10 条随机臂**彼此之间**有多相关 —— ★ 用来解释《随机臂也聚类》那个「比值 < 1」。

★★★ 为什么要量它：★ 实测发现 6 格里有 3 格的「跨臂标准差 ÷ 单臂聚类标准误」**小于 1**
  （0.58 ~ 0.63）。★★ 10 个**独立**估计量、真均值相同时，这个比值应该 **≈1**；
  ★★★ 小于 1 只能是「10 条臂彼此**正相关**」—— ★ 它们在同一个池子、同一批日子、
    同一套进出场规则下交易，天然共享大盘那一块。
★★ 对照关系（10 条臂、平均两两相关 ρ）：跨臂SD ≈ 单臂SE × sqrt(1 − ρ) → **ρ ≈ 1 − 比值²**。
  ★★★ 本份就是去量真实的 ρ，看它和这个推出来的 ρ 对不对得上。
★ 日收益来自 probe/重测_1107/日净值_赛道配对_1108/（★ 本容器重跑的 84 条臂）。
★★★★★ 描述性，不设门槛，不改任何已报结论。
"""
from __future__ import annotations
import glob, json, os
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
os.chdir(ROOT)
NAV = "probe/重测_1107/日净值_赛道配对_1108"
比值 = {"B_2015到2025·大波段": 2.79, "B_2015到2025·突破": 0.63, "B_2015到2025·震荡": 1.76,
       "A_2004到2014·大波段": 0.61, "A_2004到2014·突破": 0.58, "A_2004到2014·震荡": 1.52}
OUT = os.path.join(HERE, "随机臂之间相关_报告_1108.json")

报 = {"★这一份是什么": "量 10 条随机臂日收益彼此的平均两两相关，解释「跨臂SD ÷ 单臂SE < 1」",
     "★★★不是什么": "★ 描述性，不设门槛，不改任何已报结论", "结果": {}}

for 窗 in ("B_2015到2025", "A_2004到2014"):
    for 族, fn in (("大波段", "技-1"), ("突破", "技-6-原著"), ("震荡", "技-14-原著")):
        cols = {}
        真 = None
        for p in sorted(glob.glob(os.path.join(NAV, f"{窗}·并池2004·{族}·{fn}·*.csv"))):
            名 = os.path.basename(p)[:-4].split("·")[-1]
            eq = pd.read_csv(p, parse_dates=["date"]).set_index("date")["equity"].astype(float)
            r = eq.pct_change().dropna()
            if 名 == "A原样":
                真 = r
            elif 名.startswith("R随机"):
                cols[名] = r
        if len(cols) < 5 or 真 is None:
            报["结果"][f"{窗}·{族}"] = {"★算不出来": f"只找到 {len(cols)} 条随机臂"}
            continue
        M = pd.DataFrame(cols).dropna()
        C = M.corr().to_numpy()
        iu = np.triu_indices_from(C, k=1)
        ρ = float(np.mean(C[iu]))
        共 = 真.reindex(M.index).dropna()
        ρ真 = float(np.mean([共.corr(M[c].reindex(共.index)) for c in M.columns]))
        b = 比值[f"{窗}·{族}"]
        ρ推 = 1.0 - b * b
        报["结果"][f"{窗}·{族}"] = {
            "★随机臂条数": int(M.shape[1]), "★天数": int(M.shape[0]),
            "★★★随机臂之间平均两两相关ρ": round(ρ, 3),
            "★★相关的范围": [round(float(C[iu].min()), 3), round(float(C[iu].max()), 3)],
            "★★★真臂与随机臂平均相关": round(ρ真, 3),
            "★跨臂SD÷单臂聚类SE（上一份实测）": b,
            "★★★由它推出的ρ（1−比值²）": round(ρ推, 3),
            "★★★★★推的和量的对得上吗": ("✅ 差 < 0.15" if abs(ρ推 - ρ) < 0.15 else
                              f"⚠ 差 {ρ推 - ρ:+.3f} —— ★ 如实报，不去圆它")}
        print(f"{窗}·{族}: 随机臂之间 ρ={ρ:.3f}（范围 {C[iu].min():.2f}~{C[iu].max():.2f}）· "
              f"真臂vs随机 {ρ真:.3f} · 比值 {b} → 推 ρ={ρ推:+.3f} · "
              f"{报['结果'][f'{窗}·{族}']['★★★★★推的和量的对得上吗']}", flush=True)

json.dump(报, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print("★ 写出:", OUT, flush=True)
