#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 直接在本轮流水上实测「退化 R 到底出在哪一侧」—— 2026-11-02

★★★ 为什么还要这一步(★ 这是本轮实测查出来的一件事):
   `95e293b` 的提交信息写着「每笔留痕 `r_degenerate`,不许静默丢弃」,
   ★★ 但 `engine/chain.py` 的 `LEDGER_COLUMNS`(第 117 行)**没有**这一列,
      而流水是 `pd.DataFrame(rows, columns=LEDGER_COLUMNS)` 建的
      → ★★★ `r_degenerate` 这一列**被静默丢掉了**,落盘的流水里根本没有。
   ★ 所以「真链有没有退化 R」不能靠读那一列,只能自己按**同一个判据**重算。
   ★★★ 本脚本**不改 engine**(考卷在跑、题目冻结),只读流水。

判据(照抄 engine/chain.py · DEGENERATE_R_MIN = 1e-4):
   risk_per_share > 0 且 entry_price > 0 且 risk_per_share / entry_price < 1e-4
   → 这一笔是退化 R。

交叉验证(★ 两条路对不上就报出来,不许只报好看的那一条):
   路一 · 按上面的判据算
   路二 · 数 `r_multiple` 是 NaN 而 `risk_per_share > 0` 的笔数
          —— 修复后这两者应该**完全相等**(修复做的就是把这些笔的 R 置 NaN)。

跑法:python3 probe/bench1_rerun_1102/degen_check_1102.py
"""
from __future__ import annotations

import json
import os
import traceback

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGERS = os.path.join(HERE, "ledgers_1102")
OUT = os.path.join(HERE, "退化R实测-1102.json")

DEGENERATE_R_MIN = 1e-4          # ★ 照抄 engine/chain.py,不自己定


def scan(path: str) -> dict:
    df = pd.read_csv(path)
    n = len(df)
    if n == 0:
        return {"笔数": 0, "退化笔数_判据": 0, "退化笔数_NaN路": 0,
                "两条路是否一致": True}
    risk = pd.to_numeric(df["risk_per_share"], errors="coerce")
    entry = pd.to_numeric(df["entry_price"], errors="coerce")
    rm = pd.to_numeric(df["r_multiple"], errors="coerce")
    ratio = risk / entry.replace(0, np.nan)
    by_rule = (risk > 0) & (entry > 0) & (ratio < DEGENERATE_R_MIN)
    by_nan = rm.isna() & (risk > 0)
    out = {
        "笔数": int(n),
        "退化笔数_判据": int(by_rule.sum()),
        "退化笔数_NaN路": int(by_nan.sum()),
        "两条路是否一致": bool(int(by_rule.sum()) == int(by_nan.sum())),
        "最小 risk/entry 比": (float(np.nanmin(ratio)) if n else None),
        "最小 risk_per_share": (float(np.nanmin(risk)) if n else None),
        "r_multiple 为 NaN 的总笔数": int(rm.isna().sum()),
        "★有没有 r_degenerate 这一列": bool("r_degenerate" in df.columns),
    }
    if out["退化笔数_判据"]:
        s = df[by_rule].head(5)
        out["头几笔退化样本"] = s[["symbol", "entry_date", "entry_price",
                                   "initial_stop", "risk_per_share",
                                   "r_multiple", "r_multiple_net"]].to_dict("records")
    return out


def main() -> int:
    real, ctrl, errs = {}, {}, {}
    for fn in sorted(os.listdir(LEDGERS)):
        if not fn.endswith(".csv"):
            continue
        p = os.path.join(LEDGERS, fn)
        try:
            d = scan(p)
        except Exception:
            errs[fn] = traceback.format_exc(limit=3)
            continue
        if fn.startswith("REAL__"):
            real[fn[len("REAL__"):-4]] = d
        elif fn.startswith("CTRL__"):
            ctrl[fn[len("CTRL__"):-4]] = d

    def agg(m):
        hit = {k: v["退化笔数_判据"] for k, v in m.items() if v["退化笔数_判据"]}
        return {
            "扫了多少份流水": len(m),
            "总笔数": sum(v["笔数"] for v in m.values()),
            "有退化笔的份数": len(hit),
            "退化笔总数": sum(hit.values()),
            "名单": dict(sorted(hit.items(), key=lambda kv: -kv[1])),
            "★两条路不一致的份数": sum(1 for v in m.values()
                                       if not v["两条路是否一致"]),
            "★两条路不一致的名单": [k for k, v in m.items()
                                     if not v["两条路是否一致"]],
            "★有 r_degenerate 列的份数": sum(
                1 for v in m.values() if v["★有没有 r_degenerate 这一列"]),
        }

    out = {
        "这是什么": "★★★ 本轮(退化 R 修复后)流水上**实测**的退化 R 分布 —— "
                    "★ 不引用上一轮的说法",
        "判据": f"risk_per_share / entry_price < {DEGENERATE_R_MIN}(照抄 engine)",
        "★★★落盘流水里有没有 r_degenerate 这一列":
            "★★★ 没有 —— engine/chain.py 的 LEDGER_COLUMNS 里没登记这一列,"
            "pd.DataFrame(rows, columns=LEDGER_COLUMNS) 把它静默丢了。"
            "★ 提交信息里承诺的「每笔留痕」在落盘流水上没有兑现。"
            "★★ 本轮不改 engine(题目冻结),只如实报告。",
        "真链(REAL__)": agg(real),
        "对照组(CTRL__)": agg(ctrl),
        "逐份_真链": real,
        "逐份_对照组": ctrl,
        "读不了的": errs,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    try:
        print(json.dumps({"真链": out["真链(REAL__)"],
                          "对照组": {k: v for k, v in out["对照组(CTRL__)"].items()
                                     if k != "名单"}},
                         ensure_ascii=False, indent=1))
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
