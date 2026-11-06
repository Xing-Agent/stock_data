# -*- coding: utf-8 -*-
"""
★★★ 大盘替身 —— ★ 基准必须和策略「**同进同出**」。

★★ 来历：Lin 1106 18:42 指出：
  「如果买大盘，也是分时间买，和卖的，**你测的时间不一样，真的不一样**。」
★★★ 他说的是对的，而且这是整个比较的核心：
  ★ 「全程买入持有」从头拿到尾，★★ 而策略只在**特定那些日子**在场 ——
  ★★★ **两边在场的时间不一样，比的就不是同一件事。**

★★★ 这一份的做法（★ 唯一的差别只剩「买了什么」）：
  每一笔 → 用**同样的钱 · 同样的进场日 · 同样的离场日**去买 SPY，
  ★★ 然后和真实那一笔**逐笔配对**比。
  → ★★★ 时间、金额、持有长度**全部对齐**。

★ 它直接回答那个真问题：
  **「我在同样那些时刻、拿同样久，不如直接买大盘吗？」**

★★ 纪律：算不出单独报数，不猜不补；标准误按**进场日聚类**；失败大声报（规矩⑯）。
★ engine 零改动。
"""
import glob, json, os, sys
import numpy as np, pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from engine import data as D                                   # noqa: E402

OUT = "probe/大盘替身_1106"
_SPY = None


def spy():
    global _SPY
    if _SPY is None:
        b = D.load_benchmark("SPY")
        _SPY = b["close"].dropna()
    return _SPY


def 一条(p: str) -> dict | None:
    d = pd.read_csv(p)
    need = {"entry_date", "exit_date", "notional_in", "net_pnl", "gross_pnl",
            "friction_cost"}
    if d.empty or not need <= set(d.columns):
        return None
    for c in ("entry_date", "exit_date"):
        d[c] = pd.to_datetime(d[c], errors="coerce")
    for c in ("notional_in", "net_pnl", "gross_pnl", "friction_cost"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["entry_date", "exit_date", "notional_in", "net_pnl"])
    if d.empty:
        return None
    s = spy()
    idx = s.index

    真收益率, 替身收益率, 算不出 = [], [], 0
    for a, b, 本, 净 in zip(d["entry_date"], d["exit_date"],
                          d["notional_in"], d["net_pnl"]):
        if 本 is None or not np.isfinite(本) or 本 <= 0:
            算不出 += 1
            continue
        i = idx.searchsorted(a)
        j = idx.searchsorted(b)
        # ★★★ 窗口落在 SPY 序列之外 → 算不出（★ 不外推、不用最近值顶替）
        if i >= len(idx) or j >= len(idx) or j <= i:
            算不出 += 1
            continue
        p0, p1 = float(s.iloc[i]), float(s.iloc[j])
        if not (np.isfinite(p0) and np.isfinite(p1) and p0 > 0):
            算不出 += 1
            continue
        真收益率.append(float(净) / float(本))
        替身收益率.append(p1 / p0 - 1.0)

    if len(真收益率) < 20:
        return {"★算不出": f"可配对只有 {len(真收益率)} 笔,★ 少于 20 笔不比",
                "★算不出笔数": 算不出}

    真 = pd.Series(真收益率)
    替 = pd.Series(替身收益率)
    差 = 真 - 替
    # ★★★ 按进场日聚类（同一天进场的几笔不独立）
    日 = d["entry_date"].iloc[:len(差)].reset_index(drop=True)
    g = 差.groupby(日.dt.strftime("%Y-%m-%d").values).mean().dropna()
    nd = len(g)
    se = float(g.std(ddof=1) / np.sqrt(nd)) if nd >= 3 else np.nan
    m = float(差.mean())
    t = m / se if (np.isfinite(se) and se > 0) else np.nan
    return {
        "①可配对笔数": int(len(真)),
        "★算不出笔数": 算不出,
        "②真策略_每笔收益率均值pct": round(float(真.mean()) * 100, 4),
        "③大盘替身_每笔收益率均值pct": round(float(替.mean()) * 100, 4),
        "★★★④差(真 减 替身)pct": round(m * 100, 4),
        "★按进场日聚类的标准误pct": (round(se * 100, 4) if np.isfinite(se) else None),
        "★★聚类数(不同进场日)": nd,
        "t值": (round(float(t), 2) if np.isfinite(t) else None),
        "★★★判定": ("★ 正且过 2 倍标准误（★★ 比同期大盘好）" if (np.isfinite(t) and t > 2)
                  else ("负且过 2 倍标准误（★★★ 不如同期买大盘）"
                        if (np.isfinite(t) and t < -2)
                        else "★★★ 测不出（在噪声里）")),
        "⑤赢过替身的笔数占比": round(float((差 > 0).mean()) * 100, 1),
        "⑥平均持有天(日历)": round(float((d["exit_date"] - d["entry_date"])
                                 .dt.days.mean()), 1),
    }


def main() -> int:
    报 = {"★这一份比什么": {
        "做法": "★★★ 每笔用**同样的钱 · 同样的进场日 · 同样的离场日**买 SPY，逐笔配对比",
        "为什么": "★★ Lin 1106 18:42：「如果买大盘，也是分时间买，和卖的，"
               "**你测的时间不一样，真的不一样**」—— ★ 他说得对",
        "★★★唯一的差别": "只剩「**买了什么**」—— 时间、金额、持有长度全部对齐",
        "口径": "★ 真策略那一笔用**净收益率** = net_pnl ÷ notional_in（★★ 已扣摩擦）；"
              "★★★ 大盘替身**不扣摩擦**（★ 所以这个对比对我们**不利**，是保守的）",
        "标准误": "★★ 按**进场日聚类**",
        "算不出": "★ 窗口落在 SPY 序列之外 → 单独报数，**不外推、不用最近值顶替**",
        "engine改动": "零",
    }}
    fs = sorted(glob.glob("probe/挂闸_1106/ledgers_1106/REAL__*.csv")) + \
         sorted(glob.glob("probe/新策略_1106/**/REAL__融-*.csv", recursive=True)) + \
         sorted(glob.glob("probe/friction_rerun_1104/ledgers_1104/REAL__*.csv"))
    失败 = 0
    for f in fs:
        名 = os.path.basename(f)[6:-4]
        if 名 in 报:
            continue
        try:
            r = 一条(f)
        except Exception as e:
            r = {"★跑失败": repr(e)[:200]}
            失败 += 1
        if r:
            报[名] = r
            if "★跑失败" in r:
                print("⚠ 失败", 名, flush=True)
    报["★★★失败条数"] = 失败
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "大盘替身_报告_1106.json"), "w",
              encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print(f"★ 写完;★★★ 失败 {失败} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
