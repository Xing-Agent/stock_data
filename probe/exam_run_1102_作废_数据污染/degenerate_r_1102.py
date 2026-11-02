#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★ 退化 R 在考卷上有没有再出现 —— 事后扫流水,2026-11-02

三秒版:「止损价落在进场价上」那一类。冻结版的 engine **已经自己会剔**
        (`engine/chain.py:547` 的 `r_ok`,判据 risk/entry ≥ 1e-4,
         提交 95e293b,10-31 14:25 —— ★ 冻结在 11-01,所以修复在题目里)。
        ★ 本脚本只是**数一遍**,确认它真的没再出现,★ 一行 engine 都没改。

★★★ 本脚本附带查到的一件事(★ 不许改,只登记):
   95e293b 的提交信息写着「★★ 每笔留痕 `r_degenerate`,不许静默丢弃」,
   而 `engine/chain.py:117` 的 `LEDGER_COLUMNS` 是写死的 26 列、**不含**
   `r_degenerate`;第 793 行 `pd.DataFrame(rows, columns=LEDGER_COLUMNS)`
   ★★★ **把这一列静默丢掉了**。
   ★ 对数字没有影响(退化那一笔的 r_multiple 本来就已经是 NaN),
     ★★ 影响的是**事后对账**:流水里查不到「这一笔是被剔掉的」。
   ★ 这正是坑表上「参数位置不统一会静默吃掉设置」的同一个毛病。
   ★★★ engine 冻结期内**不改** —— 登记在这里,等解冻再处置。

★ 所以「有没有退化笔」只能从 `risk_per_share / entry_price` 反算,
  ★★ 判据和 engine 里那一行**同一个数**(1e-4),没有另立口径。
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGERS = os.path.join(HERE, "ledgers_1102")
OUT = os.path.join(HERE, "degenerate_r_1102.json")

#: ★ 和 engine/chain.py:51 DEGENERATE_R_MIN 同一个数
DEGEN_REL = 1e-4


def scan(path: str) -> dict:
    try:
        df = pd.read_csv(path)
    except Exception as e:                                       # noqa: BLE001
        return {"读不了": repr(e)}
    if df.empty:
        return {"笔数": 0, "退化笔数": 0, "NaN_R笔数": 0}
    rps = pd.to_numeric(df.get("risk_per_share"), errors="coerce").abs()
    ep = pd.to_numeric(df.get("entry_price"), errors="coerce").abs()
    rel = rps / ep.replace(0, np.nan)
    bad = (rel < DEGEN_REL) | rps.isna() | (rps == 0)
    r = pd.to_numeric(df.get("r_multiple"), errors="coerce")
    out = {
        "笔数": int(len(df)),
        "退化笔数": int(bad.sum()),
        "退化比例": float(bad.mean()),
        # ★ engine 把退化笔的 R 置成 NaN。两个数应该对得上 ——
        #   对不上说明还有**别的**原因让 R 变 NaN,要单独查。
        "NaN_R笔数": int(r.isna().sum()),
        "★退化笔数和NaN_R笔数是否一致": bool(int(bad.sum()) == int(r.isna().sum())),
        "最小 risk_per_share": (None if rps.dropna().empty else float(rps.min())),
        "最小 risk占进场价比例": (None if rel.dropna().empty else float(rel.min())),
        "最大 |R|": (None if r.dropna().empty else float(r.abs().max())),
        "每笔R(engine口径·退化笔已是NaN)": (None if r.dropna().empty
                                            else float(r.mean())),
    }
    if int(bad.sum()):
        cols = [c for c in ("symbol", "entry_date", "entry_price",
                            "initial_stop", "risk_per_share", "r_multiple")
                if c in df.columns]
        out["退化笔样例"] = df.loc[bad, cols].head(3).to_dict("records")
    return out


def main() -> int:
    rows = []
    for real in sorted(glob.glob(os.path.join(LEDGERS, "REAL__*.csv"))):
        name = os.path.basename(real)[len("REAL__"):-len(".csv")]
        ctrl = os.path.join(LEDGERS, f"CTRL__{name}.csv")
        rec = {"链文件名": name, "真链": scan(real),
               "对照": scan(ctrl) if os.path.exists(ctrl) else None}
        a = rec["真链"].get("退化笔数") or 0
        b = (rec["对照"] or {}).get("退化笔数") or 0
        rec["★这条链有没有退化R"] = bool(a or b)
        rows.append(rec)

    hit = [r for r in rows if r["★这条链有没有退化R"]]
    mismatch = [r for r in rows
                if r["真链"].get("★退化笔数和NaN_R笔数是否一致") is False
                or ((r["对照"] or {}).get("★退化笔数和NaN_R笔数是否一致") is False)]
    out = {
        "这是什么": "★★ 退化 R 在考卷上有没有再出现(2026-11-02)",
        "判据": f"risk_per_share / entry_price < {DEGEN_REL}"
                " —— ★ 和 engine/chain.py:51 DEGENERATE_R_MIN 同一个数",
        "★冻结版里退化R已经由engine自己剔": {
            "提交": "95e293b(2026-10-31 14:25)",
            "位置": "engine/chain.py:547 r_ok / 第 51 行 DEGENERATE_R_MIN",
            "在冻结清单里": True,
            "处置": "退化那一笔的 r_multiple / r_multiple_net 置 NaN,其余 R 一个不动",
        },
        "★★★附带查到_不许改_只登记": {
            "是什么": "95e293b 承诺的每笔留痕 `r_degenerate` 被静默丢掉了",
            "怎么丢的": "engine/chain.py:117 LEDGER_COLUMNS 写死 26 列、不含 "
                        "r_degenerate;第 793 行 pd.DataFrame(rows, "
                        "columns=LEDGER_COLUMNS) 直接按这 26 列建表",
            "对数字有影响吗": "没有 —— 退化笔的 R 本来就已经是 NaN",
            "影响的是什么": "事后对账:流水里查不到「这一笔是被剔掉的」,"
                            "只能从 risk_per_share/entry_price 反算",
            "为什么本轮不改": "engine 冻结期内一行都不许改",
        },
        "扫了多少条链": len(rows),
        "★有退化R的链数": len(hit),
        "★有退化R的链": [r["链文件名"] for r in hit],
        "★退化笔数和NaN_R笔数对不上的链数": len(mismatch),
        "★退化笔数和NaN_R笔数对不上的链": [r["链文件名"] for r in mismatch],
        "逐链": rows,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    try:
        print(f"写到 {OUT}")
        print(f"扫 {len(rows)} 条 · 有退化R {len(hit)} 条 · "
              f"退化笔数与NaN_R对不上 {len(mismatch)} 条")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
