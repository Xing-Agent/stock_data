# ★★★★★ 注意：这是**一次性对账脚本**，★ 不是说明书的输入。
#   ★★ 说明书走的是 `probe/说明书_1107b/生成说明书_1107b.py`（1107 第 4 次唤醒那版），
#     ★★★ 它**早就**用的是剔脏日之后的数 —— ★ 我 1108 没先核抬头就跑了旧生成器，
#     把好版本覆盖了（账本 #95）。
#   ★★ 本脚本留下来的唯一价值：它算出了「**剔脏日到底改变了多少**」——
#     ★★★ 剔 314 笔(3.1%) · t 中位变化 +0.000 · 最差 −0.90 · **没有一条臂改变显著性**。
#   → ★ 不要把它接进任何流水线。

# -*- coding: utf-8 -*-
"""★★★ 把基本面 33 条的说明书字段，在**剔脏日之后的干净流水**上重算一遍。

★★ 三秒版：说明书里基本面那 33 条现在用的是**没剔脏日**的数；
   ★★★ 这个脚本在干净流水上把说明书要的字段重算，输出成生成器认的那个格式。

★★★ 为什么不能「换个文件就完事」（★ 台账原来是这么写的，不对）：
  ★ 剔脏日那一轮（`剔脏日后_33条_1107.json`）只重算了**三把尺子**，
    ★★ 说明书还要 胜率 / 利润因子 / 持有天 / 每笔中位 / 去尾 / 十倍 /
      不同股票 / 期末持仓 / 哈希 —— ★★★ 干净那份里**一个都没有**。
  → ★★ 所以这里：能从干净流水算的**全部重算**；
    ★★★ 干净那轮**没量**的（尺子C：进场后 20 日超额）→ **标「算不出来」**，
      ★ 绝不把脏值混进干净行（规矩：「算不出来」和「分数差」分开记）。

★ 脏日口径完全沿用 `剔脏日重出_1107`：持有区间 ±15 个日历日内含任一脏日 → 整笔剔掉。
  ★★ 本脚本**不自己定任何门槛**，只读它产出的 `ledgers_clean/`。
"""
from __future__ import annotations
import glob
import hashlib
import io
import json
import os

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CLEAN = os.path.join(ROOT, "probe/剔脏日重出_1107/ledgers_clean")
净JSON = os.path.join(ROOT, "probe/剔脏日重出_1107/剔脏日后_33条_1107.json")
脏JSON = os.path.join(ROOT, "probe/基本面跑批_1106/成绩_1106.json")
OUT = os.path.join(ROOT, "probe/说明书_1107/干净成绩_1108.json")

尺子C缺 = "★算不出来：剔脏日那一轮没量这把尺子（不是分数差）"


def 读流水(臂: str) -> pd.DataFrame | None:
    p = os.path.join(CLEAN, f"REAL__{臂.replace('/', '／').replace(' ', '_')}.csv")
    if not os.path.exists(p):
        return None
    return pd.read_csv(p)


def 哈希(臂: str) -> str | None:
    p = os.path.join(CLEAN, f"REAL__{臂.replace('/', '／').replace(' ', '_')}.csv")
    if not os.path.exists(p):
        return None
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()[:16]


def 尾巴(led: pd.DataFrame) -> tuple:
    """★ 每笔中位收益率 · 去掉最高 1% 后的均值 · 涨 10 倍以上的笔数（口径同《出表_1106》）。"""
    if led is None or led.empty or "gross_return" not in led:
        return None, None, None
    r = pd.to_numeric(led["gross_return"], errors="coerce").dropna() * 100.0
    if not len(r):
        return None, None, None
    cut = r.quantile(0.99)
    return (round(float(r.median()), 4),
            round(float(r[r <= cut].mean()), 4),
            int((r >= 900.0).sum()))          # ★ 涨 10 倍 = +900%


def 期末持仓(led: pd.DataFrame) -> tuple:
    if led is None or led.empty or "reason" not in led:
        return None, None
    rs = led["reason"].astype(str)
    return int((rs == "退市结算").sum()), int((rs == "真退市").sum())


def main() -> int:
    净 = json.load(io.open(净JSON, encoding="utf-8"))
    脏 = json.load(io.open(脏JSON, encoding="utf-8"))
    # ★ 只从脏表借**标签**（档），★★★ 不借任何数字
    档表 = {f'{r["策略"]}·{r["点"]}': r.get("档") for r in 脏.get("表", [])}

    rows, 缺 = [], []
    for 臂, v in 净["逐条"].items():
        bm = v.get("★★★大盘替身") or {}
        acc = v.get("账户百分比") or {}
        led = 读流水(臂)
        if led is None:
            缺.append(臂)
        中位, 去尾, 十倍 = 尾巴(led)
        tail, real = 期末持仓(led)
        策略, 点 = (臂.split("·", 1) + [""])[:2]
        hd = (pd.to_numeric(led["holding_days"], errors="coerce").dropna()
              if led is not None and "holding_days" in led else pd.Series(dtype=float))
        rows.append({
            "策略": 策略, "点": 点, "档": 档表.get(臂),
            "笔数": (int(len(led)) if led is not None else None),
            "不同股票": (int(led["symbol"].nunique())
                     if led is not None and "symbol" in led else None),
            "比同期大盘_差pct(均值)": bm.get("★★★④差(真 减 替身)pct"),
            "t": bm.get("t值"),
            "判定": bm.get("★★★判定") or bm.get("★算不出"),
            # ★★★ 干净那轮没量尺子C → 标算不出来，★ 不许回填脏值
            "进场后20日超额pct(均值)": 尺子C缺, "20日t": 尺子C缺,
            "每笔中位pct": 中位, "去掉最高1%后均值pct": 去尾,
            "涨10倍以上笔数(要核拆股)": 十倍,
            "利润因子": acc.get("⑤利润因子_按净值pct"), "胜率": acc.get("②胜率"),
            "持有交易日(中位)": (round(float(hd.median()), 1) if len(hd) else None),
            "期末还拿着(被记成退市结算)": tail, "真退市": real,
            "流水哈希": 哈希(臂),
            # ★★ 剔脏日本身的代价，一起带着走（★★★ 不许只报干净数字不报剔了多少）
            "★剔掉笔数": v.get("★★★剔掉笔数"), "★剔掉占比pct": v.get("★剔掉占比pct"),
            "★原笔数": v.get("原笔数"),
        })

    df = pd.DataFrame(rows)
    同向 = {}
    for s, g in df.groupby("策略"):
        x = pd.to_numeric(g["比同期大盘_差pct(均值)"], errors="coerce").dropna()
        同向[s] = ("三点同向·正" if len(x) == 3 and (x > 0).all() else
                 "三点同向·负" if len(x) == 3 and (x < 0).all() else
                 f"不同向或不足三点({len(x)})")
    df["三点同向"] = df["策略"].map(同向)
    tt = pd.to_numeric(df["t"], errors="coerce").dropna()
    dup = df[df.duplicated("流水哈希", keep=False) & df["流水哈希"].notna()]

    out = {
        # ★★★ 规矩㊼：五字段「本次口径」行
        "【本次口径】": ("价格口径（基本面这批没开全收益）· 摩擦档见每行「档」· "
                   "窗口 2009~2025（财报限制）· 池 见原跑批 · 标签滞后 1 天"
                   " · ★★★ **已剔脏日**（±15 日历日内含脏日的整笔剔掉）"),
        "★★★这一份干什么": ("★ 把基本面 33 条的说明书字段在**干净流水**上重算。"
                      "★★★ 尺子C（进场后 20 日超额）剔脏日那轮没量 → 标算不出来，"
                      "**不是**分数差。"),
        "★★★脏日口径来自": "probe/剔脏日重出_1107/（本脚本不自己定门槛）",
        "失败": [],
        "表": rows,
        "★多重检验": {"检验个数": int(len(tt)),
                   "运气约给几个|t|>2": round(0.05 * len(tt), 1),
                   "实际正显著": int((tt > 2).sum()), "实际负显著": int((tt < -2).sum())},
        "三点同向": 同向,
        "★重复版本(流水一样)": dup[["策略", "点", "流水哈希"]].to_dict("records"),
        "★★★找不到干净流水的臂": 缺,
    }
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=False, indent=1, default=str))

    print(f"★ 臂数 {len(rows)} · 找不到干净流水 {len(缺)}")
    print(f"★★★ 多重检验: {json.dumps(out['★多重检验'], ensure_ascii=False)}")
    剔 = pd.to_numeric(df["★剔掉占比pct"], errors="coerce").dropna()
    if len(剔):
        print(f"★★ 剔掉占比: 中位 {剔.median():.2f}% · 最大 {剔.max():.2f}% "
              f"· 一笔没剔的臂 {(剔 == 0).sum()} 条")
    print(f"★ 写到 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
