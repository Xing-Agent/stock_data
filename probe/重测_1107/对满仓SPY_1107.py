# -*- coding: utf-8 -*-
"""★★★ 主基准：**满仓标准指数买入持有**（《93》3.1，对外唯一能用的那个）。

★★ 口径（规矩㊽：修一把尺子必须两侧一起修）：
  · 两侧都**全收益**（分红再投）—— 策略侧引擎里 `cash += gain` 事实上在再投（《104》第二节）。
  · ★★★ **两侧用同一段日期**。A 段有个坑：池表 2004 年诚实跳过（前面没有 60 个交易日）
    → 策略在 2004 **一笔都买不到**（实测最早一笔 2005-01-04），
    ★★ 而 SPY 在 2004 照样涨 → 从 2004 起算就是**让策略空跑一年再跟 SPY 比**。
    → ★★★ 所以 A 段**另报一行 2005 起**的同期对照，两行并列，不许只报一行。
  · 不扣税（《104》：税率因人而异，给一个数就是替用户假设）。
"""
from __future__ import annotations
import hashlib, io, json, os, sys

import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, ROOT)
os.chdir(ROOT)
import 配对与条件alpha_1107 as A                                   # noqa: E402

代表 = {"大波段": "技-1", "突破": "技-6-原著", "震荡": "技-14-原著"}
段 = {"B_2015到2025": [("2015-01-01", "2025-12-31")],
     "A_2004到2014": [("2004-01-02", "2014-12-31"), ("2005-01-01", "2014-12-31")]}
OUT = os.path.join(HERE, "对满仓SPY_报告_1107.json")


def 年化(s: pd.Series) -> float:
    s = s.dropna()
    n = len(s)
    return float((s.iloc[-1] / s.iloc[0]) ** (252.0 / n) - 1.0) if n > 10 else float("nan")


def main() -> int:
    报 = {"★★★这一份是什么": __doc__.strip()[:1200],
         "【本次口径】": ("全收益（分红再投，两侧同口径）· 摩擦档 配置自带三档 · "
                    "池 并池2004 全量 3,858 只 · 标签滞后 1 天 · 不扣税"),
         "各段": {}}
    for 窗名, 区间们 in 段.items():
        报["各段"][窗名] = {}
        for 起, 止 in 区间们:
            ie = A.取指数与环境(起, 止)
            spy = (1 + ie["指数日收益"]).cumprod()
            spy年化 = 年化(spy)
            行 = {"★★★满仓SPY全收益_年化": round(spy年化 * 100, 3), "各族": {}}
            打得过 = 0
            for 族, fn in 代表.items():
                lab = f"{窗名}·并池2004·{族}·{fn}·A原样"
                d = A.读日序列(lab)
                if d is None:
                    行["各族"][族] = {"★缺日序列": True}; continue
                eq = d["净值"].astype(float)
                eq = eq.loc[(eq.index >= pd.Timestamp(起)) & (eq.index <= pd.Timestamp(止))]
                a = 年化(eq)
                峰 = eq.cummax()
                赢 = bool(a > spy年化)
                打得过 += int(赢)
                行["各族"][族] = {
                    "年化": round(a * 100, 3),
                    "★★★对满仓SPY差额(个百分点)": round((a - spy年化) * 100, 3),
                    "最大回撤": round(float((eq / 峰 - 1).min()) * 100, 2),
                    "期末净值倍数": round(float(eq.iloc[-1] / eq.iloc[0]), 3),
                    "★打得过满仓SPY吗": ("打得过" if 赢 else "打不过"),
                }
            行["★★★打得过满仓SPY的条数"] = f"{打得过}/{len(代表)}"
            报["各段"][窗名][f"{起}~{止}"] = 行
            print(f"★ {窗名} {起}~{止}: SPY全收益 {spy年化*100:.3f}%/年 · "
                  f"打得过 {打得过}/{len(代表)}", flush=True)
            for 族, v in 行["各族"].items():
                if "年化" in v:
                    print(f"    {族}: {v['年化']:+.3f}%/年 "
                          f"(差 {v['★★★对满仓SPY差额(个百分点)']:+.2f}pp) "
                          f"回撤 {v['最大回撤']:.1f}% · {v['期末净值倍数']}x", flush=True)
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"★ 写完 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
