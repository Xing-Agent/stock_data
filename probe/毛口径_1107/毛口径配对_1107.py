# -*- coding: utf-8 -*-
"""★★★《114》毛口径配对 —— ★ ADV20 排序对随机排序的优势里，有多少是成本档位给的。

★★ 为什么必须有这一份（全文见《114》第一节）：
  `engine/chain.py:150 _liquidity_tiers()` 按**当日横截面 ADV20 的 1/3、2/3** 分三档，
  `costs.friction_tiers` = 高 5 / 中 15 / 低 30 bps；
  ★★★ 而三条代表链的 `ranking` 就是 **ADV20 desc** ——
  → **排序变量和成本档位是同一个变量**，ADV20 排序自带约 3.3 倍的单边成本优势，
    ★★ 不含任何选股本事。→ 所以「真信号 vs 随机排序」这把尺子在净口径上是**不公平的**。

★ 做法（《114》第四节，跑前写死）：同一族同一窗口，A原样 对每条 R随机，
  ★★ **毛净值**（不扣摩擦）和**净值**各自逐日相减 → Newey-West(8) t，两版并排报。
  ★★★ 两版之差 = 摩擦档位贡献了多少。门槛 |t| > 3（《114》4.1，跑前写死）。

★★ 口径（规矩㊼）：全收益（分红再投，两侧同口径）· 摩擦档 5/15/30 bps（★ 本档就是要剥它）
  · 窗口 A 标签 2004 实际 2005~2014 / B 2015~2025 · 池 并池2004 全量 3,858 只 · 标签滞后 1 天。
★★★ 本份不引用基准一（本批没算）。
"""
from __future__ import annotations
import glob, json, os, sys

import numpy as np
import pandas as pd
import statsmodels.api as sm

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
ARMS_毛 = os.path.join(ROOT, "probe", "重测_1107", "arms_毛_1107")
ARMS_原 = os.path.join(ROOT, "probe", "重测_1107", "arms_1107")
DS   = os.path.join(ROOT, "probe", "重测_1107", "日序列毛_1107")
OUT  = os.path.join(HERE, "毛口径配对_报告_1107.json")
NW_LAG = 8                 # ★《93》第六节第 7 条：滞后阶数按公式取 8
门槛 = 3.0                  # ★★★《114》4.1 跑前写死，不许报的时候放宽


def 安全名(label: str) -> str:
    """★★★ 不许凭记忆写 —— ★ 照 `日序列覆盖层_1107.安全名` 的做法（sha256 前 16 位）。
    ★★ 核过：`日序列覆盖层_1107.py:48`。"""
    import hashlib
    return hashlib.sha256(label.encode()).hexdigest()[:16]


def 读(label: str):
    p = os.path.join(DS, f"d_{安全名(label)}.csv")
    if not os.path.exists(p):
        return None
    return pd.read_csv(p, parse_dates=["日期"]).set_index("日期")


def nw_t(x) -> dict:
    """★ 「均值是否为 0」的 Newey-West(HAC) t。★★ 用 statsmodels，不手写核权重。"""
    x = pd.Series(x).astype(float).dropna()
    n = len(x)
    if n < 30:
        return {"★样本不够": n}
    m = sm.OLS(x.to_numpy(), np.ones((n, 1))).fit(
        cov_type="HAC", cov_kwds={"maxlags": NW_LAG})
    return {"n": int(n), "均值": float(m.params[0]),
            "★标准差(单次离散度)": float(x.std(ddof=1)),
            "★NW标准误(均值精度)": float(m.bse[0]),
            "★★★NW_t": float(m.tvalues[0]), "p": float(m.pvalues[0]),
            "★NW滞后阶": NW_LAG}


def 配对(a: str, b: str, 列: str) -> dict:
    da, db = 读(a), 读(b)
    if da is None or db is None or 列 not in da.columns or 列 not in db.columns:
        return {"★算不了": f"缺 {列}（a={da is not None} b={db is not None}）"}
    ra = da[列].astype(float).pct_change().dropna()
    rb = db[列].astype(float).pct_change().dropna()
    共 = ra.index.intersection(rb.index)
    if len(共) < 30:
        return {"★算不了": f"共同交易日 {len(共)}"}
    return nw_t(ra.reindex(共) - rb.reindex(共))


def 曲线指标(label: str, 列: str) -> dict | None:
    d = 读(label)
    if d is None or 列 not in d.columns:
        return None
    nv = d[列].astype(float)
    r = nv.pct_change().dropna()
    年 = (len(nv) - 1) / 252.0
    峰 = nv.cummax()
    return {"年化": float((nv.iloc[-1] / nv.iloc[0]) ** (1 / 年) - 1),
            "最大回撤": float((nv / 峰 - 1).min()),
            "期末倍数": float(nv.iloc[-1] / nv.iloc[0]),
            "夏普_无风险按0": float(r.mean() / r.std(ddof=1) * np.sqrt(252))}


def main() -> int:
    arms = {}
    for f in glob.glob(os.path.join(ARMS_毛, "*.json")):
        j = json.load(open(f, encoding="utf-8"))
        arms[j["链"]] = j
    if not arms:
        print("★★★ 一个臂文件都没读到 —— 大声报（规矩⑯）", file=sys.stderr)
        return 2

    # ★★★ 先过可复现性闸（《114》第六节写死：不相等就停，结论一个字不许发）
    原 = {}
    for f in glob.glob(os.path.join(ARMS_原, "*.json")):
        j = json.load(open(f, encoding="utf-8"))
        原[j["链"]] = j
    共臂 = sorted(set(arms) & set(原))
    不一致 = [k for k in 共臂
              if 原[k]["笔数"] != arms[k]["笔数"]
              or abs(原[k]["每笔净R"] - arms[k]["每笔净R"]) > 1e-12]
    复现 = {"★对账臂数": len(共臂), "★不一致": 不一致,
            "★★★判": ("✅ 逐条相等（跨会话第三次独立对账）" if not 不一致
                        else "★★★ 不相等 —— 本档结论作废")}
    if 不一致:
        json.dump({"★★★停": 复现}, open(OUT, "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        print("★★★ 可复现性闸没过，停", 不一致, file=sys.stderr)
        return 3

    报告 = {
        "★本次口径": ("全收益（分红再投，两侧同口径，《104》）· 摩擦档 5/15/30 bps"
                      "· 窗口 A 标签2004 实际2005~2014 / B 2015~2025"
                      "· 池 并池2004 全量 3,858 只 · 标签滞后 1 天"),
        "★门槛": f"|NW_t| > {门槛}（《114》4.1 跑前写死）",
        "★不许引用": "基准一（同环境随机进场）本批没算",
        "★★★可复现性闸": 复现,
        "★★★这一档在问什么": ("ADV20 排序比随机排序好的那部分，有多少是 "
                               "`_liquidity_tiers()` 按 ADV20 分的成本档位给的。"
                               "★ 毛口径把摩擦整个剥掉 → 剩下的才是选股那部分。"),
        "★毛口径的边界（诚实写）": ("毛口径下两边都不付成本 —— ★★ 这不是「更真实」，"
                                   "是**把一个变量关掉**。★★★ 对外成绩一律仍用净口径（《104》）。"),
        "分段": {},
    }

    by = {}
    for k, v in arms.items():
        by.setdefault((k.split("·")[0], v["族"]), {})[v["臂"]] = k

    for (段, 族) in sorted(by):
        d = by[(段, 族)]
        if "A原样" not in d:
            continue
        随机 = sorted(x for x in d if x.startswith("R随机"))
        块 = {"段": 段, "族": 族, "随机臂数": len(随机), "逐对": {}}
        for 列 in ("净值", "毛净值"):
            ts, 过 = [], 0
            for r in 随机:
                res = 配对(d["A原样"], d[r], 列)
                t = res.get("★★★NW_t")
                块["逐对"].setdefault(列, {})[r] = res
                if t is not None:
                    ts.append(t)
                    过 += 1 if abs(t) > 门槛 else 0
            if ts:
                块[f"{列}_汇总"] = {
                    "t范围": [round(min(ts), 3), round(max(ts), 3)],
                    "t中位": round(float(np.median(ts)), 3),
                    "t>0的": f"{sum(1 for x in ts if x > 0)}/{len(ts)}",
                    f"|t|>{门槛}的": f"{过}/{len(ts)}",
                    "★★★判": ("★★★ 过门槛" if 过 == len(ts) else
                                ("★★ 部分过（不算站住）" if 过 else
                                 f"★ 一条都没过 |t|>{门槛}")),
                }
        # ★★★ 摩擦贡献 = 净口径 t 中位 − 毛口径 t 中位（★ 只报方向，t 不可相减成「量」）
        if "净值_汇总" in 块 and "毛净值_汇总" in 块:
            块["★★★摩擦档位的方向"] = {
                "净口径t中位": 块["净值_汇总"]["t中位"],
                "毛口径t中位": 块["毛净值_汇总"]["t中位"],
                "★差": round(块["净值_汇总"]["t中位"] - 块["毛净值_汇总"]["t中位"], 3),
                "★怎么读": ("差为正 = 摩擦档位在帮 ADV20。"
                             "★★★ t 值不是可加的量，这个差只读**方向**，不许当幅度引用。"),
            }
        # ★ 曲线层两口径并排（★★ 净口径那一版和《113》对得上才算没写错）
        块["曲线"] = {}
        for 列 in ("净值", "毛净值"):
            真 = 曲线指标(d["A原样"], 列)
            rs = [曲线指标(d[r], 列) for r in 随机]
            rs = [x for x in rs if x]
            if 真 and rs:
                块["曲线"][列] = {
                    "真_年化": round(真["年化"], 5),
                    "随机_年化中位": round(float(np.median([x["年化"] for x in rs])), 5),
                    "真_最大回撤": round(真["最大回撤"], 4),
                    "随机_回撤中位": round(float(np.median([x["最大回撤"] for x in rs])), 4),
                    "真_夏普": round(真["夏普_无风险按0"], 4),
                    "随机_夏普中位": round(float(np.median(
                        [x["夏普_无风险按0"] for x in rs])), 4),
                    "真的秩_年化_1最好": int(sum(
                        1 for x in rs if x["年化"] >= 真["年化"]) + 1),
                    "共几个": len(rs) + 1,
                }
        报告["分段"][f"{段}·{族}"] = 块

    json.dump(报告, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("写出", OUT)
    for k, v in 报告["分段"].items():
        print("\n===", k, "随机臂", v["随机臂数"])
        for 列 in ("净值", "毛净值"):
            s = v.get(f"{列}_汇总")
            if s:
                print(f"  {列:5s} t范围 {s['t范围']} 中位 {s['t中位']:+.3f} "
                      f"t>0 {s['t>0的']}  |t|>3 {s[f'|t|>{门槛}的']}  {s['★★★判']}")
        if "★★★摩擦档位的方向" in v:
            print("  摩擦方向:", v["★★★摩擦档位的方向"]["★差"])
        for 列, c in v["曲线"].items():
            print(f"  曲线·{列:5s} 真年化 {c['真_年化']:+.4f} vs 随机中位 "
                  f"{c['随机_年化中位']:+.4f} | 秩 {c['真的秩_年化_1最好']}/{c['共几个']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
