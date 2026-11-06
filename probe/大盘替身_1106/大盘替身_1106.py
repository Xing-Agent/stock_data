# -*- coding: utf-8 -*-
"""
★★★ 大盘替身 —— ★ 基准必须和策略「**同进同出**」。

★★ 来历：Lin 1106 18:42 指出：
  「如果买大盘，也是分时间买，和卖的，**你测的时间不一样，真的不一样**。」
★★★ 他说的是对的，而且这是整个比较的核心：
  ★ 「全程买入持有」从头拿到尾，★★ 而策略只在**特定那些日子**在场 ——
  ★★★ **两边在场的时间不一样，比的就不是同一件事。**

★★★ 这一份的做法（★ 唯一的差别只剩「买了什么」）：
  每一笔 → 用**同样的钱 · 同样的进场日 · 同样的离场日**去买 SPY，
  ★★ 然后和真实那一笔**逐笔配对**比。
  → ★★★ 时间、金额、持有长度**全部对齐**。

★ 它直接回答那个真问题：
  **「我在同样那些时刻、拿同样久，不如直接买大盘吗？」**

★★ 纪律：算不出单独报数，不猜不补；标准误按**进场日聚类**；失败大声报（规矩⑯）。
★ engine 零改动。
"""
import glob, json, os, sys
import numpy as np, pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from engine import data as D                                   # noqa: E402

OUT = "probe/大盘替身_1106"

# ★★★ 1106 21:45 修（★★ B 路查出来的，我独立复核过）——
#   ★ 原来这份自己写了一套替身算法，有**两个错叠在一起**：
#     ① ★★★ `if ... j <= i: 算不出 += 1; continue`
#        把「离场日 = 进场日」的笔**整条扔掉**（连策略那一侧一起扔）。
#        ★★ 实测（震荡·技-14-原著·不挂闸，10,405 笔）：被扔掉 **2,442 笔（23.5%）**，
#          其中 **99.96% 是亏的**、平均 **−2.10%**，离场原因 2,438 笔是**止损** ——
#          ★★★ 也就是**当天就被打掉的单子**。
#        → ★ 策略真实平均 **−0.14%** 被抬成 **+0.46%**（抬高 0.60 个百分点）。
#        ★★★ 这是教科书式的**存活者偏差**，而我把它建进了自己的基准里。
#     ② **时点没对齐**：策略是次日**开盘**成交，而我拿 SPY 的**收盘**比。
#   → ★★ 修法：**直接复用 B 路那一份实现**（`probe/挂件_1106/台_公共_1106.py`
#     的 `替身收益()`）—— ★★★ 不许有两份实现，否则下次还会分叉。
sys.path.insert(0, os.path.join(ROOT, "probe", "挂件_1106"))
import 台_公共_1106 as 台                                      # noqa: E402


def 一条(p: str) -> dict | None:
    d = pd.read_csv(p)
    need = {"entry_date", "exit_date", "notional_in", "net_pnl", "reason"}
    if d.empty or not need <= set(d.columns):
        return {"★跑失败": f"缺列:{sorted(need - set(d.columns))}"}
    for c in ("entry_date", "exit_date"):
        d[c] = pd.to_datetime(d[c], errors="coerce")
    for c in ("notional_in", "net_pnl"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["entry_date", "exit_date", "notional_in", "net_pnl"])
    d = d[d["notional_in"] > 0]
    if d.empty:
        return None

    真 = d["net_pnl"] / d["notional_in"]          # ★ 已扣摩擦的净收益率
    替 = 台.替身收益(d)                            # ★★★ 修正口径（当天单不扔、时点对齐）
    ok = 真.notna() & 替.notna()
    算不出 = int((~ok).sum())
    if int(ok.sum()) < 20:
        return {"★算不出": f"可配对只有 {int(ok.sum())} 笔，★ 少于 20 笔不比",
                "★算不出笔数": 算不出}
    差 = (真[ok] - 替[ok])
    st = 台.聚类t(差, d.loc[ok, "entry_date"])
    t = st["t"]
    return {
        "①可配对笔数": int(ok.sum()),
        "★算不出笔数": 算不出,
        "②真策略_每笔收益率均值pct": round(float(真[ok].mean()) * 100, 4),
        "③大盘替身_每笔收益率均值pct": round(float(替[ok].mean()) * 100, 4),
        "★★★④差(真 减 替身)pct": round(st["均值"] * 100, 4),
        "★按进场日聚类的标准误pct": (round(st["聚类标准误"] * 100, 4)
                              if np.isfinite(st["聚类标准误"]) else None),
        "★★聚类数(不同进场日)": st["聚类数"],
        "t值": (round(float(t), 2) if np.isfinite(t) else None),
        "★★★判定": ("★ 正且过 2 倍标准误（★★ 比同期大盘好）" if (np.isfinite(t) and t > 2)
                  else ("负且过 2 倍标准误（★★★ 不如同期买大盘）"
                        if (np.isfinite(t) and t < -2)
                        else "★★★ 测不出（在噪声里）")),
        "⑤赢过替身的笔数占比": round(float((差 > 0).mean()) * 100, 1),
        "⑥平均持有天(日历)": round(float((d.loc[ok, "exit_date"]
                                   - d.loc[ok, "entry_date"]).dt.days.mean()), 1),
        "★★★当天进当天出的笔数": int((d.loc[ok, "exit_date"]
                              == d.loc[ok, "entry_date"]).sum()),
    }


def main() -> int:
    报 = {"★这一份比什么": {
        "做法": "★★★ 每笔用**同样的钱 · 同样的进场日 · 同样的离场日**买 SPY，逐笔配对比",
        "为什么": "★★ Lin 1106 18:42：「如果买大盘，也是分时间买，和卖的，"
               "**你测的时间不一样，真的不一样**」—— ★ 他说得对",
        "★★★唯一的差别": "只剩「**买了什么**」—— 时间、金额、持有长度全部对齐",
        "口径": "★ 真策略那一笔用**净收益率** = net_pnl ÷ notional_in（★★ 已扣摩擦）；"
              "★★★ 大盘替身**不扣摩擦**（★ 所以这个对比对我们**不利**，是保守的）",
        "标准误": "★★ 按**进场日聚类**",
        "算不出": "★ 窗口落在 SPY 序列之外 → 单独报数，**不外推、不用最近值顶替**",
        "engine改动": "零",
        "★★★1106_21_45_修": ["① 当天进当天出的笔**不再扔**（原来整条扔掉 → 存活者偏差，实测把技-14 抬高 0.60 个百分点）", "② **时点对齐**：进场用 SPY 开盘；规则/时间离场用离场日开盘；止损/退市/期末用离场日收盘；当天进当天出用当天开→收"],
    }}
    fs = sorted(glob.glob("probe/挂闸_1106/ledgers_1106/REAL__*.csv")) + \
         sorted(glob.glob("probe/新策略_1106/**/REAL__融-*.csv", recursive=True)) + \
         sorted(glob.glob("probe/friction_rerun_1104/ledgers_1104/REAL__*.csv"))
    失败 = 0
    for f in fs:
        名 = os.path.basename(f)[6:-4]
        if 名 in 报:
            continue
        try:
            r = 一条(f)
        except Exception as e:
            r = {"★跑失败": repr(e)[:200]}
            失败 += 1
        if r:
            报[名] = r
            if "★跑失败" in r:
                print("⚠ 失败", 名, flush=True)
    报["★★★失败条数"] = 失败
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "大盘替身_报告_1106.json"), "w",
              encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print(f"★ 写完;★★★ 失败 {失败} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
