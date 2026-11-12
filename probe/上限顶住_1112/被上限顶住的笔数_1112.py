#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数一遍「被 10% 上限顶住」的笔数（2026-11-12）

★ 来源：《172》Gemini 那一轮，Lin 11-12 16:04 拍板「先诊断，暂不改」。
★★ 要回答的那句：「**每条策略有多少笔因为 10% 上限，实际风险不到 1%**」。

★★★★★ **这件事不用重跑、不用 NAV —— 纯算术**，推导如下：
   ★ 引擎的算法（`chain.py:605~615` + `458`）：
       按风险算的名义 = (净值 × 1%) ÷ 止损幅度
       实际名义       = min(按风险算的名义, 净值 × 10%)
   ★★ 所以：**止损幅度 < 10% → 按风险算的名义 > 净值 × 10% → 被上限截住**，
       ★★★ 而截住之后 **实际风险 = 10% × 止损幅度 < 1%**。
   ★★★★★ 净值在不等式两边都被约掉了 → ★ **只需要「止损幅度」这一列**。

★ 止损幅度 = (entry_price − initial_stop) ÷ entry_price —— ★★ 两列流水里都有。

🔴 ★★ 本脚本**只给数，不下结论**（★ 共用边界：不写「建议改/不改」）。
★ 不碰 engine/ 一个字节。
"""
import glob
import io
import os
import re
import sys

import numpy as np
import pandas as pd

ROOT = "/home/claude/xing-agent-stock_data"
风险 = 0.01      # ★ risk_per_trade，★★ 32 个配置写的都是 0.01
上限 = 0.10      # ★ max_weight


def 一条(p: str):
    d = pd.read_csv(p)
    need = {"entry_price", "initial_stop"}
    if not need <= set(d.columns):
        return None
    d = d[(d["entry_price"] > 0) & (d["initial_stop"] > 0)].copy()
    if not len(d):
        return None
    d["止损幅度"] = (d["entry_price"] - d["initial_stop"]) / d["entry_price"]
    d = d[d["止损幅度"] > 0]
    if not len(d):
        return None
    顶住 = d["止损幅度"] < 上限
    # ★★★★★ 实际风险 = min(1%, 10% × 止损幅度)
    d["实际风险"] = np.minimum(风险, 上限 * d["止损幅度"])
    return {
        "笔数": len(d),
        "被上限顶住的笔数": int(顶住.sum()),
        "占比%": round(float(顶住.mean()) * 100, 1),
        "止损幅度中位数%": round(float(d["止损幅度"].median()) * 100, 2),
        "实际风险中位数%": round(float(d["实际风险"].median()) * 100, 3),
        "★实际风险只有名义的几成": round(float(d["实际风险"].median()) / 风险, 2),
        "最窄止损幅度%": round(float(d["止损幅度"].min()) * 100, 2),
    }


def main():
    fs = [f for f in sorted(glob.glob(os.path.join(ROOT, "probe/*/ledgers*/*.csv")))
          if os.path.basename(f).startswith("REAL__")]
    print(f"★ 扫 {len(fs)} 份 REAL 流水\n")
    行 = []
    for p in fs:
        名 = re.sub(r"^REAL__", "", os.path.basename(p)[:-4])
        r = 一条(p)
        if r is None:
            continue
        r["臂"] = 名
        行.append(r)
    if not 行:
        print("🔴 一份都算不出来 —— ★★ 流水里没有 entry_price / initial_stop")
        return 1
    df = pd.DataFrame(行).drop_duplicates(subset=["臂"]).sort_values("占比%", ascending=False)
    out = os.path.join(ROOT, "probe/上限顶住_1112/被上限顶住_1112.csv")
    os.makedirs(os.path.dirname(out), exist_ok=True)
    df.to_csv(out, index=False)

    print(f"{'臂':46s}{'笔数':>7s}{'顶住':>7s}{'占比%':>8s}{'止损幅度中位%':>12s}{'实际风险中位%':>12s}")
    for _, r in df.head(18).iterrows():
        print(f"{r['臂'][:44]:46s}{r['笔数']:7d}{r['被上限顶住的笔数']:7d}"
              f"{r['占比%']:8.1f}{r['止损幅度中位数%']:12.2f}{r['实际风险中位数%']:12.3f}")
    print(f"\n★ 共 {len(df)} 条臂 → {out}")
    print(f"\n★★★★★ **全体**：")
    print(f"   被上限顶住的笔数占比 —— 中位数 **{df['占比%'].median():.1f}%** · "
          f"最高 {df['占比%'].max():.1f}% · 最低 {df['占比%'].min():.1f}%")
    print(f"   止损幅度中位数 —— **{df['止损幅度中位数%'].median():.2f}%**")
    print(f"   实际风险中位数 —— **{df['实际风险中位数%'].median():.3f}%**"
          f"（★★ 名义是 1.000%）")
    全顶住 = int((df['占比%'] >= 99.9).sum())
    print(f"   ★★★ **几乎每一笔都被顶住**（占比 ≥ 99.9%）的臂：**{全顶住} / {len(df)}** 条")
    print("\n🔴 ★★★★★ **本脚本不下结论** —— ★ 要不要把 1% / 10% 改成 0.5% / 5%，")
    print("   ★★ Lin 11-12 16:04 已定「**先诊断，暂不改**」。★★★ 这就是那个诊断的第一半。")
    print("   ★ 另一半（微仓全接：信号成交率 / 排序提升度 / 被丢信号成绩 / 起始日敏感度）")
    print("   ★★★★★ **要重跑回测**，★★ 而 `matrices.build(2224只)` 在这台 8GB 机器上会被 OOM 杀掉。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
