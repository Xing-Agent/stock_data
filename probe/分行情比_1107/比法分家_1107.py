# -*- coding: utf-8 -*-
"""
★★★ 比法分家 —— ★ 来历：Lin 1107 09:05。

★★ 他指出的事：**不同策略类，该跟谁比是不一样的**。原话：
  「震荡单来讲，你只买大盘说白了收益几乎是零。然后在震荡单里就是来回做，
    那这一类来讲，其实就是有很大的机会。」
  「基本面那几个策略……说白了都是市场不好的时候买便宜的，市场好的时候卖掉，
    所以这种每个比的方法都不太一样……它的时间要求更长，而且得跨周期了。」

★★★ 我原来**只有一套比法**（对同敞口指数回归），这对震荡类和价值类都不对口：
  · ★ 趋势/突破类 → 跟**同期大盘**比（对：我们卖的就是「挑得更快」）
  · ★★★ 震荡类 → 大盘那一段**本来就是零** → ★★ 拿大盘当标尺等于**白送一条及格线**
      → 该跟 **零 / 无风险利率** 比，看**绝对收益**
  · ★★★ 价值类 → 跨周期 → ★ 日 alpha 测不出它，要按**完整一轮**算

★ 这一份先做前两件（第三件要等基本面流水跑完）：
  ① 每条臂，在**锯齿段**里同时报三个标尺：对大盘 alpha / **绝对年化** / **超无风险**
  ② 顺带报那一段**大盘自己**的年化（★★ 用来证实「震荡时买大盘确实接近零」）
"""
import glob, json, os, sys
import numpy as np, pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "组合日收益_1106"))
sys.path.insert(0, os.path.join(ROOT, "probe", "分行情比_1107"))
import 组合日收益_1107 as 核                      # noqa: E402
import 分行情比_1107 as 分                        # noqa: E402


def 年化(r: pd.Series) -> float:
    if len(r) < 20:
        return float("nan")
    return float((1 + r).prod() ** (252 / len(r)) - 1) * 100


def 一条(p: str, th: float = 0.6) -> dict:
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
    spy_r = s.pct_change()
    同敞口 = spy_r * 敞口.shift(1)
    g = 分.行情(eq.index)
    out = {"★平均敞口pct": round(float(敞口.mean()) * 100, 1)}

    for 名, m in (("走直线", (g["ER"] >= th)), ("锯齿", (g["ER"] < th))):
        m = m & g["ER"].notna()
        y = r[m].dropna()
        if len(y) < 60:
            out[名] = {"★算不出": f"只有 {len(y)} 天"}; continue
        a = 核.回归(y, 同敞口.reindex(y.index))
        out[名] = {
            "交易日": int(len(y)),
            "★标尺1_对大盘alpha年化pct": (None if "★算不出" in a else
                                   round(a["★★★alpha_年化pct"], 2)),
            "★标尺1_t": (None if "★算不出" in a else round(a["★★alpha的t值_NeweyWest"], 2)),
            "★★★标尺2_我们自己的绝对年化pct": round(年化(y), 2),
            "★★标尺3_同期大盘自己的年化pct": round(年化(spy_r.reindex(y.index).dropna()), 2),
            "★★★标尺3_我们减大盘_绝对口径pct": round(年化(y) - 年化(spy_r.reindex(y.index).dropna()), 2),
        }
    return out


def main() -> int:
    报 = {"★这一份做什么":
          "★★★ 按策略类换标尺（Lin 1107 09:05）。★ 震荡类不该拿大盘当标尺 —— "
          "那一段大盘本来就接近零，拿它比等于白送一条及格线。"
          "★★ 这里把同一段同时用三个标尺报出来，让 Lin 自己选。",
          "★标尺1": "对同敞口指数回归的 alpha + Newey-West t（★ 我原来唯一用的）",
          "★★★标尺2": "我们自己的**绝对年化**（★★ 震荡类该看这个）",
          "★★标尺3": "同期大盘自己的年化（★★★ 用来证实「震荡时买大盘接近零」）",
          "★门槛": "ER≥0.6（★ 三点里的中间那点；相邻三点已在分行情比里报过）"}
    fs = sorted(glob.glob("probe/挂闸_1106/ledgers_1106/REAL__*.csv")) + \
         sorted(glob.glob("probe/新策略_1106/**/REAL__融-*.csv", recursive=True))
    失败 = 0
    for f in fs:
        名 = os.path.basename(f)[6:-4]
        try:
            报[名] = 一条(f)
        except Exception as e:
            报[名] = {"★跑失败": repr(e)[:200]}; 失败 += 1
            print("⚠ 失败", 名, flush=True); continue
        z = 报[名].get("锯齿", {})
        print(f"✓ {名:<26} 锯齿段: 我们 {z.get('★★★标尺2_我们自己的绝对年化pct')}% "
              f"vs 大盘 {z.get('★★标尺3_同期大盘自己的年化pct')}%", flush=True)
    报["★★★失败条数"] = 失败
    with open("probe/分行情比_1107/比法分家_报告_1107.json", "w", encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print(f"★ 写完;★★★ 失败 {失败} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
