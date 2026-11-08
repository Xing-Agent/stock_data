# -*- coding: utf-8 -*-
"""★★★ R1 的 A/B —— 甲（分红未折算，已在盘上那批）vs 乙（折算好，1108 重跑）。
★ 口径与门槛见《129》第四、五节，★★★ 本脚本一个字都不改那份登记。
★ 只读落盘的臂 / 日净值，不跑回测。
"""
from __future__ import annotations
import importlib.util as IU
import json, os, sys
import numpy as np, pandas as pd

ROOT = os.path.abspath(".")
sys.path.insert(0, ROOT)
RT = os.path.join(ROOT, "probe", "重测_1107")
spec = IU.spec_from_file_location("Q", os.path.join(RT, "出数_1107.py"))
Q = IU.module_from_spec(spec); spec.loader.exec_module(Q)

窗口起, 窗口止 = "2015-01-01", "2025-12-31"
前缀 = "B_2015到2025·并池2004·大波段·技-1"
两边 = {
    "甲_分红未折算": (os.path.join(RT, "arms_1107"), os.path.join(RT, "日净值_分红未折算_1108")),
    "乙_折算好_1108": (os.path.join(RT, "arms_修分红_1108"), os.path.join(RT, "日净值_修分红_1108")),
}


def 年化(x: pd.Series) -> float:
    return float((1.0 + x).prod() ** (252.0 / len(x)) - 1.0)


def 画像(r: pd.Series) -> dict:
    eq = (1.0 + r).cumprod()
    峰 = eq.cummax()
    回 = eq / 峰 - 1.0
    # ★ 最长多少天没创新高
    新高 = eq >= 峰 * (1 - 1e-12)
    最长, 当前 = 0, 0
    for v in 新高.to_numpy():
        当前 = 0 if v else 当前 + 1
        最长 = max(最长, 当前)
    return {"年化": 年化(r), "最大回撤": float(回.min()),
            "最长不创新高天数": int(最长), "天数": int(len(r))}


出 = {"★这是什么": "R1（分红拆股折算）修好前后的 A/B",
      "★登记": "手册/129-跑前预先登记-R1分红折算-1108.md（跑之前已提交）",
      "★★★本次口径": ("全收益（分红再投，两侧同口径）· 摩擦档 三档 friction_tiers · "
                 f"窗口 B 段 {窗口起}~{窗口止} · 池 并池2004(3858,一档) · 标签滞后 1 天"),
      "两边": {}, "逐日配对": {}, "判决翻没翻": {}}

曲线 = {}
for 名, (arms, curv) in 两边.items():
    Q.ARMS, Q.CURV = arms, curv
    df = Q.读臂("B_2015到2025")
    r = Q.读日净值(f"{前缀}·A原样")
    assert r is not None, f"{名} 没有 A原样 日净值"
    曲线[名] = r
    出["两边"][名] = {
        "臂数": int(len(df)),
        "A原样画像": {k: (f"{v*100:+.2f}%" if k in ("年化", "最大回撤") else v)
                  for k, v in 画像(r).items()},
        "尺子②_比标普全收益": Q.尺子二(f"{前缀}·A原样", 窗口起, 窗口止),
        "尺子③_比同池随机": Q.尺子三(df, "大波段"),
        "第四档_挂开关": Q.第四档(前缀, 窗口起, 窗口止),
        "条件alpha交互项": Q.条件alpha(f"{前缀}·A原样", 窗口起, 窗口止),
        "臂明细": df[["臂", "笔数", "每笔净R", "净盈亏"]].to_dict("records"),
    }

甲, 乙 = 曲线["甲_分红未折算"], 曲线["乙_折算好_1108"]
共 = 甲.index.intersection(乙.index)
d = (乙.reindex(共) - 甲.reindex(共)).dropna()
出["逐日配对"] = {
    "★口径": "乙 − 甲，逐日相减 + Newey-West 滞后 8（《129》第四节）",
    "重叠交易日": int(len(共)),
    "★★★配对t": Q.配对t(d),
    "年化差(乙−甲)": f"{(年化(乙.reindex(共)) - 年化(甲.reindex(共)))*100:+.3f}pp/年",
    "★甲的交易日": int(len(甲)), "★乙的交易日": int(len(乙)),
}

# ★★★ 《129》第五节：方向预期 + 门槛 0.30pp
Δ = (年化(乙.reindex(共)) - 年化(甲.reindex(共))) * 100
出["判决翻没翻"] = {
    "★★★Δ年化(乙−甲)": f"{Δ:+.3f}pp/年",
    "★门槛": "0.30pp/年（《129》第五节，跑前写死）",
    "★★★落在哪种情形": ("情形一（|Δ|<0.30pp，还要看三个判决）" if abs(Δ) < 0.30
                  else "情形二（|Δ|≥0.30pp → 《126》带分红的数作废，84 条臂全重跑）"),
    "★方向预期": "修好之后策略侧年化应当**下降**（之前虚增）",
    "★★★方向对不对": ("★ 对（下降）" if Δ < 0 else
                 "★★★ 反了（上升）—— 按《129》第五节必须停下来先怀疑方向，不许直接往外报"),
}
os.makedirs("probe/审计复核_1108", exist_ok=True)
json.dump(出, open("probe/审计复核_1108/AB_修分红_1108.json", "w", encoding="utf-8"),
          ensure_ascii=False, indent=1, default=str)
print(json.dumps({k: v for k, v in 出.items() if k != "两边"}, ensure_ascii=False, indent=1, default=str))
for 名, v in 出["两边"].items():
    print("="*20, 名)
    print(json.dumps({k: vv for k, vv in v.items() if k != "臂明细"}, ensure_ascii=False, indent=1, default=str))
