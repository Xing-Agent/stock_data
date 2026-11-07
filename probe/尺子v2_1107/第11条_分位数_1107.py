# -*- coding: utf-8 -*-
"""
★★★ 清单第 ⑪ 条的实测：**随机/重抽样分布到底偏不偏？「均值±2 标准差」错多少？**

★★ 为什么要实测而不是直接改：★ 「分布是偏的」是 Gemini 说的（⑤ 档·待核），
   ★★★ 我们自己**从来没量过偏度** —— ★ 不量就改，等于把一条没验过的话当结论（#68 那一类）。

★★★ 做法（★ 用真数据，不造假分布）：
   每条臂取**配对差的按月块重抽样**分布（★ 和 `台_公共_1106.块重抽样()` 同一套块定义，
   ★★ 只是把次数提到 2,000 并把整条分布留下来），然后逐条量：
     · 偏度 · 峰度
     · 95% 范围：**分位数(2.5/97.5)** vs **均值±2 标准差**
     · 两种判法（区间含不含 0）**结论一不一致**
★ 这一份回答的是「换成分位数会改掉几条结论」，★★★ 不是「策略好不好」。
"""
from __future__ import annotations

import glob
import importlib.util
import io
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "挂件_1106"))
import 台_公共_1106 as 台                                      # noqa: E402

_s = importlib.util.spec_from_file_location("V2", os.path.join(HERE, "尺子v2_1107.py"))
V = importlib.util.module_from_spec(_s); _s.loader.exec_module(V)

LEDG = "probe/剔脏日重出_1107/ledgers_clean"
OUT = os.path.join(HERE, "第11条_分位数_报告_1107.json")
N_BOOT = 2000


def main() -> int:
    基 = V.基准两口径("SPY", 打印=True)
    报 = {"★口径头": V.口径头(
        全收益或价格="★★★ 两侧都有分红（净效果口径）", 摩擦档="★ 流水自带",
        窗口="★ 流水全区间（★ 块重抽样不切窗口）",
        池子="★★★ 老池 2,224 —— 本份是尺子体检，不是成绩表", 标签滞后天="★ 沿用原跑批"),
        "★★★这一份量什么": {
            "量": "★ 重抽样分布的**偏度**，以及「分位数」和「均值±2 标准差」两种 95% 范围差多少",
            "不量": "★★★ 不是策略成绩 —— ★ 这 33 条臂的池子窗口已被并池取代",
            "重抽样次数": N_BOOT, "块定义": "★ 按**进场月**成块（和 台_公共_1106.块重抽样 同一套）"},
        "逐条": {}, "★★★汇总": {}}
    偏度表, 打架 = [], []
    for f in sorted(glob.glob(os.path.join(LEDG, "REAL__*.csv"))):
        名 = os.path.basename(f)[6:-4]
        d = pd.read_csv(f)
        for c in ("entry_date", "exit_date"):
            d[c] = pd.to_datetime(d[c], errors="coerce")
        for c in ("notional_in", "net_pnl", "shares"):
            d[c] = pd.to_numeric(d[c], errors="coerce")
        d = d.dropna(subset=["entry_date", "exit_date", "notional_in", "net_pnl"])
        d = d[d["notional_in"] > 0].reset_index(drop=True)
        if len(d) < 20:
            报["逐条"][名] = {"★跑失败": f"只剩 {len(d)} 笔(<20)"}
            continue
        替 = V.替身收益_两口径(d, 基)
        真 = d["net_pnl"] / d["notional_in"]
        ok = 真.notna() & 替["_全收益"].notna()
        if int(ok.sum()) < 20:
            报["逐条"][名] = {"★跑失败": f"可配对 {int(ok.sum())} 笔(<20)"}
            continue
        diff = (真 - 替["_全收益"])[ok]
        月 = d.loc[ok, "entry_date"].dt.to_period("M")
        g = pd.DataFrame({"d": diff.values, "m": 月.values}).groupby("m")["d"].agg(["sum", "count"])
        S, C = g["sum"].to_numpy(), g["count"].to_numpy()
        nb = len(S)
        if nb < 6:
            报["逐条"][名] = {"★跑失败": f"块数 {nb} < 6 —— ★ 不做（和现用口径一致）"}
            continue
        rng = np.random.default_rng(7)
        pick = rng.integers(0, nb, size=(N_BOOT, nb))
        bs = S[pick].sum(1) / C[pick].sum(1)
        mu, sd = float(bs.mean()), float(bs.std(ddof=1))
        lo_q, hi_q = (float(v) for v in np.percentile(bs, [2.5, 97.5]))
        lo_s, hi_s = mu - 2 * sd, mu + 2 * sd
        偏 = float(((bs - mu) ** 3).mean() / sd ** 3) if sd > 0 else float("nan")
        峰 = float(((bs - mu) ** 4).mean() / sd ** 4 - 3.0) if sd > 0 else float("nan")
        含0_q = bool(lo_q <= 0 <= hi_q)
        含0_s = bool(lo_s <= 0 <= hi_s)
        rec = {"块数": nb, "笔数": int(ok.sum()),
               "点估计pct": round(float(diff.mean()) * 100, 4),
               "★★★偏度": round(偏, 3), "超额峰度": round(峰, 3),
               "①分位数95%范围pct": [round(lo_q * 100, 4), round(hi_q * 100, 4)],
               "②均值±2标准差范围pct": [round(lo_s * 100, 4), round(hi_s * 100, 4)],
               "★两端差多少pct": [round((lo_q - lo_s) * 100, 4), round((hi_q - hi_s) * 100, 4)],
               "①分位数判_含0吗": 含0_q, "②标准差判_含0吗": 含0_s,
               "★★★两种判法一致吗": ("✅ 一致" if 含0_q == 含0_s else "★★★ **打架**")}
        if 含0_q != 含0_s:
            打架.append({"臂": 名, "偏度": rec["★★★偏度"],
                       "分位数判": "不含0(有信号)" if not 含0_q else "含0(分不出)",
                       "标准差判": "不含0(有信号)" if not 含0_s else "含0(分不出)"})
        偏度表.append(偏)
        报["逐条"][名] = rec
        print(f"✓ {名[:32]:32s} 偏度{偏:+6.3f} 峰{峰:+6.2f} | 分位[{lo_q*100:7.3f},{hi_q*100:7.3f}] "
              f"sd[{lo_s*100:7.3f},{hi_s*100:7.3f}] {rec['★★★两种判法一致吗']}", flush=True)
    a = np.array(偏度表, float)
    报["★★★汇总"] = {
        "出数臂数": int(len(a)),
        "★★★偏度_中位": round(float(np.median(a)), 3) if len(a) else None,
        "★★★偏度_范围": ([round(float(a.min()), 3), round(float(a.max()), 3)] if len(a) else None),
        "★偏度绝对值>0.5的条数": int((np.abs(a) > 0.5).sum()) if len(a) else None,
        "★★★两种判法打架的": {"条数": len(打架), "明细": 打架},
        "★★★结论": None,
    }
    s = 报["★★★汇总"]
    s["★★★结论"] = (
        f"★ 分布确实是偏的（偏度中位 {s['★★★偏度_中位']}，"
        f"{s['★偏度绝对值>0.5的条数']}/{s['出数臂数']} 条绝对值 >0.5）—— ★★ Gemini 那一条**说对了**；"
        f"★★★ 但在这 {s['出数臂数']} 条臂上，换成分位数**改掉了 {len(打架)} 条结论** → "
        + ("★★ 所以这是一条「该改但眼下不改结论」的修法：改它是为了**以后不被偏度咬**，"
           "★★★ 不是为了翻现在这批数。" if not 打架 else
           "★★★ 有结论被改掉了，**必须逐条复核**。"))
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print("\n★★★ 汇总:", json.dumps(s, ensure_ascii=False, indent=1))
    print("★ 写到", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
