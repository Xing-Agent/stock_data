#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""笔数不足 100 的那 6 条 —— 找「丙」：按年分段看一致性（2026-11-12）

★ Lin 1112 15:43 拍板：「这样吧，1）先找丙，2）没有合适的话，
  就给用户标注清楚就好了，可以推给用户。」

★★★ 「丙」= 用别的办法补证据。★★★★★ 这里做的是**不用重跑**的那一种：
   **拿已有流水按年切开，看每一年的方向是不是一致。**
   ★★ 逻辑：笔数少是这条策略的性质（筛得严），★★★ 但如果**十一年里年年都是同一个方向**，
   ★ 那它比「一共只有 20 笔」这句话给出的信息多。

🔴 ★★★★★ **这不是在放宽门槛**（★ 那是乙，Lin 没选）——
   ★★ 笔数不足的事实照记，★★★ 这里只是**另加一条证据**。
🔴 ★★ 而且**不下「能不能给用户」的结论** —— ★ 那是 Lin 的事（★★★ 共用边界：只给数字）。

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
六条 = ["基-1", "基-16", "基-8", "技-8", "基-7", "基-3"]


def 找流水(sid: str) -> list:
    """★★★★★ 必须**精确前缀**匹配 —— ★ 第一版用 `*基-1*` 把 **基-12 / 基-16** 也捞进来了。
    ★★ 流水文件名的格式是 `<前缀>__<条目>_<名字>…csv` 或 `<条目>_<名字>…csv`，
    ★★★ 所以条目后面必须紧跟 `_` 或 `·`，不能再是数字。"""
    out = []
    for p in glob.glob(os.path.join(ROOT, "probe/*/ledgers*/*.csv")):
        b = os.path.basename(p)
        核 = re.sub(r"^(REAL|CTRL)__", "", b)
        if re.match(re.escape(sid) + r"(?![0-9])[_·]", 核):
            out.append(p)
    return out


def 按年(p: str):
    d = pd.read_csv(p)
    if "exit_date" not in d.columns or "net_pnl" not in d.columns:
        return None
    d["exit_date"] = pd.to_datetime(d["exit_date"], errors="coerce")
    d = d.dropna(subset=["exit_date"])
    if not len(d):
        return None
    d["年"] = d["exit_date"].dt.year
    g = d.groupby("年").agg(笔数=("net_pnl", "size"), 合计=("net_pnl", "sum"))
    return g


def main():
    print("★★★ 笔数不足 100 的 6 条 —— 按年分段看一致性\n")
    print("★ 判法（★★ 机械的，没有我的主观）：")
    print("  · **正年数 / 负年数** —— ★★ 每一年该策略的总盈亏是正还是负")
    print("  · ★★★ 「年年同向」= 所有有交易的年份方向一致")
    print("  🔴 ★★★★★ 不换算、不年化、不下「能不能给用户」的结论\n")
    汇 = []
    for sid in 六条:
        fs = sorted(找流水(sid))
        if not fs:
            print(f"🔴 {sid}：**一个流水文件都没有** —— ★★ 这一条做不了「丙」，照实记\n")
            汇.append({"条目": sid, "臂数": 0, "★": "没有流水，做不了"})
            continue
        print(f"=== {sid} · {len(fs)} 条臂 ===")
        for p in fs:
            名 = re.sub(r"^(REAL|CTRL)__", "", os.path.basename(p)[:-4])
            g = 按年(p)
            if g is None or not len(g):
                print(f"  🔴 {名[:54]:56s} 流水里没有 exit_date / net_pnl")
                continue
            正 = int((g["合计"] > 0).sum())
            负 = int((g["合计"] < 0).sum())
            年数 = len(g)
            同向 = "✅ 年年同向·正" if 负 == 0 and 正 > 0 else (
                "❌ 年年同向·负" if 正 == 0 and 负 > 0 else "🟡 有正有负")
            print(f"  {名[:54]:56s} 笔数 {int(g['笔数'].sum()):5d} · "
                  f"有交易的年份 {年数:2d} · 正 {正:2d} / 负 {负:2d}  {同向}")
            汇.append({"条目": sid, "臂": 名, "笔数": int(g["笔数"].sum()),
                       "有交易年份": 年数, "正年": 正, "负年": 负, "★按年": 同向,
                       "最少的一年笔数": int(g["笔数"].min()),
                       "最多的一年笔数": int(g["笔数"].max())})
        print()
    out = os.path.join(ROOT, "probe/笔数不足_按年一致性_1112/按年一致性_1112.csv")
    pd.DataFrame(汇).to_csv(out, index=False)
    print(f"★ 明细 → {out}")
    print("\n★★★★★ **自证待做（★ 本脚本不自己下结论）**：")
    print("   ★ 这里的「正年/负年」只用了 `net_pnl` 的**年度合计** ——")
    print("   ★★★ 它**没有扣**同期大盘，也**没有**按敞口缩放。")
    print("   ★★★★★ 所以它只能回答「**这条策略每一年自己是赚还是赔**」，")
    print("   🔴 **不能**回答「它每一年有没有跑赢大盘」。★★ 要那个，得另做。")


if __name__ == "__main__":
    sys.exit(main() or 0)
