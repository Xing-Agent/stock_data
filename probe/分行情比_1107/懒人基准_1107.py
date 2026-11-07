# -*- coding: utf-8 -*-
"""
★★★ 懒人基准 —— ★ 用户面的那条线，而不是判断选股本事的那条线。

★★ 来历：Lin 1107 09:36：
  「他买大盘的一个好处就是说白了就是懒，懒得动，这批人。那你现在懒得动，
    那没办法。那只要你愿意动，用我们的我们就帮你 —— 通过主动挑选策略、
    策略各个方面优化好，能够比同期大盘或者比较的对象要好。」

★★★ 我之前所有结论用的是两个「对我们放水」的口径：
  · **等权同池**（+7.7%）—— ★ 对判断选股本事是公平的
  · **同敞口**（把指数按我们的实际敞口缩放）—— ★★ 剥掉了「我们只有半仓」这件事
→ ★★★ 但用户真会做的事是：**满仓买 SPY，拿着不动**（+11.6%/年）。
  ★ 他不会去买一个 2,770 只的等权篮子，也不会跟着我们的敞口上下。
→ ★★ 所以**向用户承诺跑赢**，必须过**满仓 SPY 买入持有**这条线。

★ 这一份只报一件事：**每条臂（含挂 ER 闸版）打不打得过满仓 SPY 买入持有。**
★★★ 口径⑥：这个换法会让我们数字**变难看** —— ★ 所以它是自我审查，不是自我表扬。
"""
import glob, json, os, sys
import numpy as np, pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
for d in ("probe/组合日收益_1106", "probe/分行情比_1107"):
    sys.path.insert(0, os.path.join(ROOT, d))
import 组合日收益_1107 as 核                      # noqa: E402
import 分行情比_1107 as 分                        # noqa: E402


def 年化(r): 
    r = r.dropna()
    return float("nan") if len(r) < 20 else float((1 + r).prod() ** (252 / len(r)) - 1) * 100


def 回撤(r):
    nav = (1 + r.fillna(0)).cumprod()
    return round(float((nav / nav.cummax() - 1).min()) * 100, 2)


def 夏普(r, rf=0.0):
    r = r.dropna()
    s = r.std()
    return None if (len(r) < 20 or s == 0) else round(float((r.mean() - rf) / s * np.sqrt(252)), 2)


def 一条(p):
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
    spy_r = 核.spy().reindex(eq.index).ffill().pct_change()
    g = 分.行情(eq.index)
    out = {"★平均敞口pct": round(float(敞口.mean()) * 100, 1)}

    def 报(y, 名):
        # ★★★ 懒人基准 = **满仓** SPY 买入持有（★ 不按敞口缩放、不剥任何东西）
        x = spy_r.reindex(y.dropna().index)
        a = 核.回归(y.dropna(), x)
        我年化, 他年化 = 年化(y), 年化(x)
        return {名: {
            "★★★我们年化pct": round(我年化, 2),
            "★★★满仓SPY同期年化pct": round(他年化, 2),
            "★★★差_个百分点": round(我年化 - 他年化, 2),
            "★对满仓SPY的alpha年化pct": (None if "★算不出" in a else
                                   round(a["★★★alpha_年化pct"], 2)),
            "★t": (None if "★算不出" in a else round(a["★★alpha的t值_NeweyWest"], 2)),
            "beta": (None if "★算不出" in a else round(a["beta"], 2)),
            "★我们最大回撤pct": 回撤(y),
            "★满仓SPY最大回撤pct": 回撤(x),
            "★我们夏普": 夏普(y), "★满仓SPY夏普": 夏普(x),
        }}

    out.update(报(r, "①一直做_不挂ER闸"))
    开 = (g["ER"] >= 0.6) & g["ER"].notna()
    out.update(报(r.where(开, 0.0), "②环境不对就空仓_挂ER≥0.6"))
    return out


def main():
    报 = {"★这一份做什么":
          "★★★ 换成**用户面**的那条线（Lin 1107 09:36）：懒人真会做的事 = "
          "**满仓买 SPY 拿着不动**。★ 我之前用的「等权同池 + 同敞口」对判断选股本事公平，"
          "★★ 但对向用户承诺跑赢是**放水**的 —— 那个懒人一直满仓，我们平均只有 15~75% 在场。",
          "★★★口径⑥声明": "这个换法会让我们数字**变难看** → ★ 这是自我审查，不是自我表扬。",
          "★基准": "★★★ 满仓 SPY 买入持有，**不按敞口缩放**"}
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
        A = 报[名]["①一直做_不挂ER闸"]; B = 报[名]["②环境不对就空仓_挂ER≥0.6"]
        print(f"✓ {名:<26} 一直做 {A['★★★差_个百分点']:+.1f}pp   "
              f"空仓版 {B['★★★差_个百分点']:+.1f}pp", flush=True)
    报["★★★失败条数"] = 失败
    with open("probe/分行情比_1107/懒人基准_报告_1107.json", "w", encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print(f"★ 写完;★★★ 失败 {失败} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
