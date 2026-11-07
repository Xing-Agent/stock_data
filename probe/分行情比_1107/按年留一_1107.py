# -*- coding: utf-8 -*-
"""
★★★ 口径⑥ 自查：「走直线段 alpha 为正」会不会只是**少数几个单边年**撑起来的？

★★ 做三件：
 ① **按年份留一法**：每次剔掉一整年，重算走直线段 alpha → 看最坏的那一次还剩多少
 ② **走直线段按年份分布**：那 458 个交易日分散在几年里，各年占多少
 ③ **按年份的分年 alpha**：哪一年贡献最大

★ 任何一臂，只要「剔掉某一年后 alpha 翻负」→ ★★★ 就是被那一年主导,不许当证据。
"""
import glob, json, os, sys
import numpy as np, pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "组合日收益_1106"))
sys.path.insert(0, os.path.join(ROOT, "probe", "分行情比_1107"))
import 组合日收益_1107 as 核                      # noqa: E402
import 分行情比_1107 as 分                        # noqa: E402

# ★ 只查「走直线段 alpha 为正且三点同向」那几条（★★ 其余本来就不是证据）
查 = ["大波段·技-1·挂闸100日", "大波段·技-1·挂闸200日", "大波段·技-1·挂闸300日",
     "融-2_突破·lookback=20", "融-2_突破·lookback=40", "融-2_突破·lookback=55",
     "突破·技-6-原著·挂闸200日", "突破·技-6-原著·挂闸300日", "融-3_大波段·lookback=60"]


def 找(名: str) -> str | None:
    for p in (glob.glob(f"probe/挂闸_1106/ledgers_1106/REAL__{名}.csv")
              + glob.glob(f"probe/新策略_1106/**/REAL__{名}.csv", recursive=True)):
        return p
    return None


def 一条(名: str, th: float = 0.6) -> dict:
    p = 找(名)
    if not p:
        return {"★跑失败": "找不到流水"}
    d = pd.read_csv(p)
    for c in ("entry_date", "exit_date"):
        d[c] = pd.to_datetime(d[c], errors="coerce")
    for c in ("shares", "entry_price", "net_pnl"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["symbol", "entry_date", "shares", "entry_price", "net_pnl"])
    eq, 敞口, _ = 核.逐日(d)
    if eq is None:
        return {"★跑失败": "面板里没有这条臂的任何票"}
    r = eq.pct_change()
    s = 核.spy().reindex(eq.index).ffill()
    同敞口 = s.pct_change() * 敞口.shift(1)
    g = 分.行情(eq.index)
    m = (g["ER"] >= th) & g["ER"].notna()

    y = r[m].dropna(); x = 同敞口.reindex(y.index)
    全 = 核.回归(y, x)
    out = {"★全段": {"alpha年化pct": round(全["★★★alpha_年化pct"], 2),
                   "t": round(全["★★alpha的t值_NeweyWest"], 2),
                   "交易日": int(len(y))}}

    # ② 走直线段按年份分布
    年 = y.index.year
    分布 = pd.Series(年).value_counts().sort_index()
    out["②走直线段各年交易日数"] = {int(k): int(v) for k, v in 分布.items()}

    # ③ 分年 alpha（★ 少于 40 天判算不出）
    分年 = {}
    for yr in sorted(set(年)):
        mm = (年 == yr)
        if mm.sum() < 40:
            分年[int(yr)] = f"算不出(只有{int(mm.sum())}天)"; continue
        a = 核.回归(y[mm], x[mm])
        分年[int(yr)] = (None if "★算不出" in a else
                       {"alpha年化pct": round(a["★★★alpha_年化pct"], 1),
                        "t": round(a["★★alpha的t值_NeweyWest"], 2), "天": int(mm.sum())})
    out["③分年alpha"] = 分年

    # ① 按年份留一法
    留一 = {}
    for yr in sorted(set(年)):
        mm = (年 != yr)
        if mm.sum() < 60:
            留一[f"剔掉{yr}"] = "算不出"; continue
        a = 核.回归(y[mm], x[mm])
        留一[f"剔掉{yr}"] = (None if "★算不出" in a else
                          {"alpha年化pct": round(a["★★★alpha_年化pct"], 2),
                           "t": round(a["★★alpha的t值_NeweyWest"], 2)})
    out["①按年留一"] = 留一
    好 = [v["alpha年化pct"] for v in 留一.values() if isinstance(v, dict)]
    ts = [v["t"] for v in 留一.values() if isinstance(v, dict)]
    if 好:
        最坏 = min(好); 最坏t = min(ts)
        out["★★★留一最坏"] = {"alpha年化pct": 最坏, "t": 最坏t,
                           "★判定": ("★★★被单一年份主导·不许当证据" if 最坏 <= 0 else
                                   "★ 留一后仍为正" + ("且t仍过2" if 最坏t >= 2 else "但t掉到2以下"))}
    return out


def main() -> int:
    报 = {"★这一份做什么":
          "★★★ 口径⑥ 自查：走直线段的正 alpha 会不会只是少数单边年撑起来的。"
          "★ 做按年留一法 + 走直线段的年份分布 + 分年 alpha。"
          "★★ 门槛固定取 ER≥0.6（三点里的中间那点）。",
          "★判据": "剔掉任何一年后 alpha 翻负 → ★★★ 被那一年主导,不许当证据"}
    for 名 in 查:
        try:
            报[名] = 一条(名)
        except Exception as e:
            报[名] = {"★跑失败": repr(e)[:200]}
            print("⚠ 失败", 名, flush=True); continue
        r = 报[名].get("★★★留一最坏", {})
        print(f"✓ {名:<26} 留一最坏 alpha={r.get('alpha年化pct')} t={r.get('t')} "
              f"{r.get('★判定','')}", flush=True)
    with open("probe/分行情比_1107/按年留一_报告_1107.json", "w", encoding="utf-8") as f:
        json.dump(报, f, ensure_ascii=False, indent=1)
    print("★ 写完")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
