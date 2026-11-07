# -*- coding: utf-8 -*-
"""★★★ 把 66 条臂汇总成一份报告 —— ★ 配对检验 · 条件 alpha · 随机离散度 · 连亏 · 持仓画像。

★★★ 纪律（每一条都写在产出里，不靠我记得）：
  · 规矩㊸v2：**配对检验没做完，一律写「待配对检验」** —— 不许写「更好」，也不许写「分不出」。
  · 规矩㊹：比单次用**标准差**，比均值用**标准误**，并写明用的是哪一把。
  · 规矩㊾：bootstrap/随机区间三种算法会打架，**偏度必须跟着一起报**；N 不够就说 N 不够。
  · 规矩㊼：头部五字段（全收益/价格 · 摩擦档 · 窗口 · 池子 · 标签滞后）—— 少一个，报告作废。
  · ★★★ 《98》2.2：基本面那几条的结论行跑前就写死（本批没跑基本面，不涉及）。
  · ★★★ 跑批没跑完的段，**它的任何计数都不许进结论句，连对比句也不行** → 本脚本会把
    不满 11 条臂的族整段标成「未跑完·不许进结论」。
"""
from __future__ import annotations
import glob, io, json, os, sys

import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, HERE); sys.path.insert(0, ROOT)
os.chdir(ROOT)
import 配对与条件alpha_1107 as A                                      # noqa: E402
import 持仓画像_1107 as PZ                                            # noqa: E402

ARMS = os.path.join(HERE, "arms_1107")
LED = os.path.join(HERE, "ledgers_1107")
代表 = {"大波段": "技-1", "突破": "技-6-原著", "震荡": "技-14-原著"}
种子 = [424242, 20181001, 20220101, 777013, 31337, 90210, 10007, 31415926, 27182818, 65537]
窗口 = {"B_2015到2025": ("2015-01-01", "2025-12-31"),
       "A_2004到2014": ("2004-01-02", "2014-12-31")}
OUT = os.path.join(HERE, "总报告_1107.json")


def 读臂(label):
    p = os.path.join(ARMS, f"a_{A.臂hash(label)}.json")
    return json.load(io.open(p, encoding="utf-8")) if os.path.exists(p) else None


def main() -> int:
    报 = {
        "【本次口径】": ("**全收益**（分红再投，策略侧和基准侧同口径，《104》拍板）· "
                   "摩擦档 = 配置自带三档 friction_tiers（11 条臂完全一样）· "
                   "窗口 见各段 · 池 = 并池2004 全量 3,858 只（一档，无留出池）· "
                   "标签滞后 1 天（regime_mask 末行 shift(1)）"),
        "★★★本批没算的": ["基准一（同环境随机进场）—— 见 跳过基准一_1107.py，"
                     "★ 任何结论句不许引用它"],
        "★NW滞后阶": A.NW_LAG,
        "各段": {},
    }
    for 窗名, (起, 止) in 窗口.items():
        ie = None
        段 = {"窗口": f"{起} ~ {止}", "各族": {}}
        for 族, fn in 代表.items():
            真 = f"{窗名}·并池2004·{族}·{fn}·A原样"
            随机 = [f"{窗名}·并池2004·{族}·{fn}·R随机{s}" for s in 种子]
            r真 = 读臂(真)
            r随 = [读臂(x) for x in 随机]
            有几条 = int((r真 is not None) + sum(x is not None for x in r随))
            d = {"★臂数": f"{有几条}/11"}
            if 有几条 < 11:
                d["★★★这一族"] = ("**未跑完 —— 不许进任何结论句，连对比句也不行**"
                              f"（只有 {有几条}/11 条）")
                段["各族"][族] = d
                continue
            # ① ★★★ 配对检验（规矩㊸v2 第①道）：A原样 vs 每条随机，逐日相减
            配 = [A.配对检验(真, x) for x in 随机]
            ts = [c.get("★★★配对差(A−B)的检验", {}).get("★★★NW_t") for c in 配]
            ts = [t for t in ts if t is not None]
            d["①配对检验_A原样vs随机排序"] = {
                "★做了几对": len(ts),
                "★★★配对NW_t的十条": [round(t, 3) for t in ts],
                "★t>0的条数": int(sum(t > 0 for t in ts)),
                "★|t|>2的条数": int(sum(abs(t) > 2 for t in ts)),
                "★★★怎么读": ("★ 每一条的意思是「真信号的日收益 − 这一条随机排序的日收益」"
                         "逐日相减后均值是否为 0。★★ 十条方向不一致 = 真信号和随机排序"
                         "**分不出高下**；★★★ 十条同向且 |t| 都大 = 真的有差别。"),
                "明细": 配,
            }
            # ② ★★★ 条件 alpha 交互项（本批跑前登记的主判据）
            if ie is None:
                ie = A.取指数与环境(起, 止)
            d["②条件alpha_交互项"] = {
                "A原样": A.条件alpha(真, 起, 止, ie),
                "★★★这一道回答什么": ("策略对大盘的敏感度，在「SPY 在 200 日线上方」和"
                              "「下方」是不是不一样 —— ★ 看交互项。"
                              "★★ 这**不是**「挂上开关会不会变好」（那是《102》第四档）。"),
            }
            # ③ ★★★ 随机排序的离散度（规矩㊾ + ㊹）
            d["③随机排序的离散度"] = A.随机离散度(
                r真["每笔净R"], [x["每笔净R"] for x in r随])
            d["③随机排序的离散度"]["★真值是"] = f"A原样 每笔净R = {r真['每笔净R']:+.4f}"
            # ④ ★★ 最长连亏 / 没新高（用户真正会放弃的地方）
            lp = os.path.join(LED, f"REAL__{真}.csv")
            d["④用户会放弃的地方_A原样"] = {
                **(A.最长连亏(lp) if os.path.exists(lp) else {"★缺流水": lp}),
                **A.没新高多少天(真),
            }
            # ⑤ ★★★ 持仓画像（Lin 的核心一问，成交的那一栏）
            if os.path.exists(lp):
                d["⑤持仓画像_成交的那一栏"] = PZ.画像(lp, 真)
                d["⑤持仓画像_成交的那一栏"]["★★★只看这一栏回答不了 Lin 那一问"] = (
                    "★ 成交 = 信号 + ADV20 降序排序**共同**作用；"
                    "★★★ 「信号自己走到哪」要看 信号自己走到哪_报告_1107.json")
            # ⑥ ★★★ 《102》第四档：挂环境开关 vs 不挂 —— ★ 配对检验，门槛 |t| > 3
            if 窗名 == "B_2015到2025":
                第四档 = {}
                for n in (100, 200, 300):
                    挂 = f"{窗名}·并池2004·{族}·{fn}·B挂闸{n}日"
                    if 读臂(挂) is None:
                        第四档[f"ma{n}"] = {"★没跑": 挂}; continue
                    c = A.配对检验(挂, 真)       # ★★★ 挂闸 − 不挂，正数 = 挂闸更好
                    t = c.get("★★★配对差(A−B)的检验", {}).get("★★★NW_t")
                    第四档[f"ma{n}"] = {
                        "★★★配对NW_t(挂闸−不挂)": (round(t, 3) if t is not None else None),
                        "★★★过没过门槛|t|>3": (("过" if abs(t) > 3 else "没过")
                                        if t is not None else None),
                        "明细": c}
                同向 = [v.get("★★★配对NW_t(挂闸−不挂)") for v in 第四档.values()]
                同向 = [x for x in 同向 if x is not None]
                d["⑥第四档_挂环境开关"] = {
                    "★开关定义": "index_above_ma SPY N 日 · flatten_when_off=false（《102》3.1 写死）",
                    "★★★门槛": "|t| > 3（3 族 × 3 档 = 9 次检验，HLZ 2016）—— 跑前写死",
                    "★★★相邻三点是否同向(红线②)": (
                        ("同向" if len(set(np.sign(同向))) == 1 else
                         "★★★ 不同向 → 那是尖峰，算挑出来的，不算站得住")
                        if len(同向) == 3 else "★ 三点没齐"),
                    "★三点的t": [round(x, 3) for x in 同向],
                    "各档": 第四档}
            段["各族"][族] = d
        报["各段"][窗名] = 段
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"★ 写完 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
