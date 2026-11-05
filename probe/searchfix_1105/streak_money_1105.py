# -*- coding: utf-8 -*-
"""
第 38 条 · 给「最长连亏」补上金额那一列（2026-11-05）

★★★ 为什么要补 —— ★ 一句大白话：
  「这套做法历史上**最长连亏 61 次**」—— ★★ 听着吓人，
  ★★★ 但它**没告诉人亏了多少钱**。
  ★ 「连亏 61 次，每次亏一点」和「连亏 4 次，每次亏很多」
    ★★ 对一个人来说是**完全不同**的两件事 —— 而我们只给了次数。

★ 这一版加三列（★★ 全部从流水里算，不估不猜）：
  · **这一串总共亏了多少钱**（★ 按净盈亏加总）
  · **占起始本金的百分之几**（★★ 起始本金 = 1,000,000，★ 和回测一致）
  · **这一串持续了多少天**（★★★ 「连亏 61 次」如果只花 3 周，和拖了 2 年，感受完全不同）

⚠ 口径：
  · ★ 「连亏」按**平仓日期排序**后的连续净亏损笔数（★★ 平仓才算结果）
  · ★★★ 同一天平仓多笔时，**同一天的算一组**（★ 一个人看对账单是按天看的，不是按笔）
    → ★★ 两种都算，**并排给**，不混成一个数
  · ★ 只用研发池那一轮的流水（`probe/bench1_rerun_1102/ledgers_1102/REAL__*.csv`）
"""
from __future__ import annotations

import glob
import json
import os
import re

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
LED = os.path.join(ROOT, "probe", "bench1_rerun_1102", "ledgers_1102")
OUT = os.path.join(HERE, "streak_money_1105.json")
EQ0 = 1_000_000.0


def _streaks(pnl: np.ndarray, dates: pd.Series):
    """★ 返回最长那一串连亏的 (笔数/组数, 亏的钱, 开始日, 结束日)。"""
    best = (0, 0.0, None, None)
    n = cur = 0
    amt = 0.0
    i0 = None
    for i, p in enumerate(pnl):
        if p < 0:
            cur += 1
            amt += float(p)
            if i0 is None:
                i0 = i
            if cur > best[0] or (cur == best[0] and amt < best[1]):
                best = (cur, amt, dates.iloc[i0], dates.iloc[i])
        else:
            cur = 0
            amt = 0.0
            i0 = None
    return best


def main() -> int:
    files = sorted(glob.glob(os.path.join(LED, "REAL__*.csv")))
    assert files, f"★★★ 找不到流水:{LED}"
    rows = []
    for f in files:
        name = re.sub(r"^REAL__", "", os.path.basename(f))[:-4]
        d = pd.read_csv(f)
        d["exit_date"] = pd.to_datetime(d["exit_date"], errors="coerce")
        d = d.dropna(subset=["exit_date", "net_pnl"]).sort_values("exit_date")
        if d.empty:
            rows.append({"链": name, "★跑挂了": "流水为空"})
            continue

        # ★ 口径一:逐笔
        n1, a1, s1, e1 = _streaks(d["net_pnl"].to_numpy(dtype=float),
                                  d["exit_date"].reset_index(drop=True))
        # ★★★ 口径二:同一天算一组(★ 一个人看对账单是按天看的)
        g = d.groupby("exit_date", as_index=False)["net_pnl"].sum()
        n2, a2, s2, e2 = _streaks(g["net_pnl"].to_numpy(dtype=float),
                                  g["exit_date"].reset_index(drop=True))

        rows.append({
            "链": name,
            "总笔数": int(len(d)),
            "★口径一_逐笔": {
                "最长连亏笔数": int(n1),
                "★这一串亏了多少钱": round(float(a1), 2),
                "★占起始本金": round(float(a1) / EQ0, 4),
                "起": str(s1.date()) if s1 is not None else None,
                "止": str(e1.date()) if e1 is not None else None,
                "★这一串持续多少天": (int((e1 - s1).days) + 1
                                      if s1 is not None else None),
            },
            "★★★口径二_同一天算一组": {
                "最长连亏天数": int(n2),
                "★这一串亏了多少钱": round(float(a2), 2),
                "★占起始本金": round(float(a2) / EQ0, 4),
                "起": str(s2.date()) if s2 is not None else None,
                "止": str(e2.date()) if e2 is not None else None,
                "★这一串持续多少天": (int((e2 - s2).days) + 1
                                      if s2 is not None else None),
            },
        })

    ok = [r for r in rows if "★跑挂了" not in r]
    def col(path):
        out = []
        for r in ok:
            v = r
            for p in path:
                v = v[p]
            out.append(v)
        return [x for x in out if x is not None]

    n1s = col(["★口径一_逐笔", "最长连亏笔数"])
    a1s = col(["★口径一_逐笔", "★占起始本金"])
    n2s = col(["★★★口径二_同一天算一组", "最长连亏天数"])
    a2s = col(["★★★口径二_同一天算一组", "★占起始本金"])
    doc = {
        "这是什么": "★ 第 38 条:给《36 人乘策略匹配》的「最长连亏」补上**金额**那一列",
        "★为什么要补": ("★★「连亏 61 次」没告诉人亏了多少钱 —— "
                        "★★★「连亏 61 次每次亏一点」和「连亏 4 次每次亏很多」"
                        "对一个人是完全不同的两件事"),
        "★流水来自": "probe/bench1_rerun_1102/ledgers_1102/REAL__*.csv(研发池那一轮)",
        "★起始本金": EQ0,
        "链数": len(ok),
        "★★★两个口径并排_不混成一个数": {
            "口径一_逐笔": {
                "最长连亏笔数_最少": int(min(n1s)), "中位": int(np.median(n1s)),
                "最多": int(max(n1s)),
                "★这一串亏掉本金的比例_最小": f"{min(a1s):.2%}",
                "中位": f"{np.median(a1s):.2%}", "★最大": f"{min(a1s) if False else max(a1s):.2%}",
                "★★最惨的那一条": f"{min(a1s):.2%}",
            },
            "口径二_同一天算一组": {
                "最长连亏天数_最少": int(min(n2s)), "中位": int(np.median(n2s)),
                "最多": int(max(n2s)),
                "★★最惨的那一条亏掉本金": f"{min(a2s):.2%}",
            },
        },
        "逐链": rows,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(doc, fh, ensure_ascii=False, indent=2, default=str)

    print(f"★ {len(ok)} 条链算完 → {OUT}\n")
    print("★★★ 口径一(逐笔):最长连亏 %d~%d 笔(中位 %d)" %
          (min(n1s), max(n1s), np.median(n1s)))
    print("★★★ 口径二(同一天算一组):最长连亏 %d~%d 天(中位 %d)" %
          (min(n2s), max(n2s), np.median(n2s)))
    print()
    # ★ 按「这一串亏掉本金多少」排序,给最惨的 8 条
    ok.sort(key=lambda r: r["★口径一_逐笔"]["★占起始本金"])
    print(f"{'链':<52}{'连亏笔':>6}{'亏掉本金':>10}{'持续天':>7}")
    print("-" * 78)
    for r in ok[:8]:
        a = r["★口径一_逐笔"]
        print(f"{r['链'][:50]:<52}{a['最长连亏笔数']:>6}"
              f"{a['★占起始本金']:>9.1%}{str(a['★这一串持续多少天']):>7}")
    print("\n★ 对比:连亏次数最多的 5 条(★★ 看它们亏的钱是多还是少)")
    ok.sort(key=lambda r: -r["★口径一_逐笔"]["最长连亏笔数"])
    for r in ok[:5]:
        a = r["★口径一_逐笔"]
        print(f"{r['链'][:50]:<52}{a['最长连亏笔数']:>6}"
              f"{a['★占起始本金']:>9.1%}{str(a['★这一串持续多少天']):>7}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
