#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 2026-10-31 本轮**新查出来的第三处缺陷**:基准一的对照组均值挡不住「退化 R」。

三秒版:止损价正好落在进场价上(浮点尘埃,risk_per_share = 3.55e-15)→
        1R ≈ 0 → 那一笔的 R = 1.75e14 → **一笔就把 50 个种子的均值毁掉**。
        实测:`原著离场/技-10 · 持仓 2 天` 的基准一算出 **−3,144,405,145**。
        ★ 这不是一个数,这是垃圾。

★★ 为什么不直接在 analyze.py 里改 R 的定义:
   「止损价 = 进场价 时 1R 等于多少」**本身没有定义**,
   怎么补(剔掉 / 置 NaN / 用进场价当分母)会改变全库每一个数,
   ★ 这是策略层面的口径决定,不是我能自己定的 → 登记成待拍板的问题。

★★★ 本脚本只做两件事,**不改任何既有数**:
   ① 逐链扫对照流水和真链流水,数出有多少笔「退化 R」
   ② 对受影响的链,把基准一**标成不出数**,并同时给出
      「剔掉退化笔之后会是多少」作为参考 —— ★ 两个数都摆出来,不替策略组选

判据(★ XING 填的,不是原著):
   退化 = risk_per_share / entry_price < DEGEN_REL(止损离进场价不到 0.01%)
   ★ 为什么用相对值而不是绝对值:$5 的票和 $500 的票,同样的绝对距离意义不同。
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGERS = os.path.join(HERE, "ledgers_1031")
PER_CHAIN = os.path.join(HERE, "per_chain")
OUT = os.path.join(HERE, "degenerate_r_1031.json")

#: ★ XING 填的阈值:止损离进场价不到 0.01% → 1R 没有意义
DEGEN_REL = 1e-4


def scan(path: str) -> dict:
    try:
        df = pd.read_csv(path)
    except Exception as e:                                       # noqa: BLE001
        return {"读不了": repr(e)}
    if df.empty or "risk_per_share" not in df.columns:
        return {"笔数": int(len(df)), "退化笔数": 0, "退化比例": 0.0}
    rps = pd.to_numeric(df["risk_per_share"], errors="coerce").abs()
    ep = pd.to_numeric(df.get("entry_price"), errors="coerce").abs()
    rel = rps / ep.replace(0, np.nan)
    bad = (rel < DEGEN_REL) | rps.isna() | (rps == 0)
    r = pd.to_numeric(df.get("r_multiple"), errors="coerce")
    out = {
        "笔数": int(len(df)),
        "退化笔数": int(bad.sum()),
        "退化比例": float(bad.mean()),
        "最小 risk_per_share": (None if rps.dropna().empty
                                else float(rps.min())),
        "最大 |R|": (None if r.dropna().empty else float(r.abs().max())),
        "每笔R_原样": (None if r.dropna().empty else float(r.mean())),
        "每笔R_剔掉退化笔": (None if r[~bad].dropna().empty
                            else float(r[~bad].mean())),
    }
    if int(bad.sum()):
        cols = [c for c in ("symbol", "entry_date", "entry_price",
                            "initial_stop", "risk_per_share", "r_multiple")
                if c in df.columns]
        out["退化笔样例"] = df.loc[bad, cols].head(3).to_dict("records")
    return out


def main() -> int:
    rows = []
    for ctrl in sorted(glob.glob(os.path.join(LEDGERS, "CTRL__*.csv"))):
        name = os.path.basename(ctrl)[len("CTRL__"):-len(".csv")]
        real = os.path.join(LEDGERS, f"REAL__{name}.csv")
        c = scan(ctrl)
        r = scan(real) if os.path.exists(real) else {"缺失": True}
        pc = os.path.join(PER_CHAIN, f"{name}.json")
        b1 = None
        label = name
        if os.path.exists(pc):
            d = json.load(open(pc, encoding="utf-8"))
            b1 = d.get("★新基准一值")
            label = d.get("链", name)
        # ★ 基准一能不能用:对照组或真链只要有一笔退化,这个均值就不可信
        usable = (c.get("退化笔数", 0) == 0 and r.get("退化笔数", 0) == 0)
        fixed = None
        if (not usable and r.get("每笔R_剔掉退化笔") is not None
                and c.get("每笔R_剔掉退化笔") is not None):
            fixed = r["每笔R_剔掉退化笔"] - c["每笔R_剔掉退化笔"]
        rows.append({
            "链": label,
            "基准一_原样": b1,
            "★基准一能不能用": usable,
            "★剔掉退化笔之后的基准一(参考,不是结论)": fixed,
            "对照流水": c,
            "真链流水": r,
        })

    bad = [x for x in rows if not x["★基准一能不能用"]]
    blown = [x for x in rows
             if x["基准一_原样"] is not None and abs(x["基准一_原样"]) > 10]
    payload = {
        "这是什么": "★★★ 2026-10-31 新查出的第三处缺陷:基准一对照组均值"
                    "挡不住退化 R(止损price == 进场price → 1R ≈ 0)",
        "判据(★ XING 填的,不是原著)":
            f"退化 = risk_per_share / entry_price < {DEGEN_REL}",
        "扫了多少条链": len(rows),
        "★基准一不可用的链数": len(bad),
        "★基准一不可用的链": [x["链"] for x in bad],
        "★基准一数值已经爆掉(|值| > 10)的链": [
            {"链": x["链"], "值": x["基准一_原样"]} for x in blown],
        "★待策略组拍板": "「止损价 == 进场价」时 1R 等于多少 —— 这个没有定义。"
                        "剔掉 / 置 NaN / 用进场价当分母,三种补法会改变全库每一个 R。"
                        "★ 我不自己定,登记成问题。",
        "逐链": rows,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, indent=1, default=str)
    try:
        print(f"扫了 {len(rows)} 条链")
        print(f"★ 基准一不可用(有退化 R)的链:{len(bad)} 条")
        for x in bad:
            print(f"   {x['链']}")
            print(f"      对照退化 {x['对照流水'].get('退化笔数')} / "
                  f"{x['对照流水'].get('笔数')} 笔 · "
                  f"真链退化 {x['真链流水'].get('退化笔数')} / "
                  f"{x['真链流水'].get('笔数')} 笔")
            print(f"      原样 {x['基准一_原样']} → "
                  f"剔掉退化笔 {x['★剔掉退化笔之后的基准一(参考,不是结论)']}")
        print(f"★ 数值已经爆掉的链:{len(blown)} 条")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
