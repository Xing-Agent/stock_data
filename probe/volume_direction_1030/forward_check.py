"""
★★★ 第五节:绕开「我们自己的编号」—— 直接看后面涨还是跌

════════════════════════════════════════════════════════════════════════════
★★★ 为什么必须有这一节(★ 这是前四节的**致命局限**)
════════════════════════════════════════════════════════════════════════════
前四节量的全部是「量指标能不能**判出我们自己的阶段号**」。
★★★ 那个阶段号**不是市场真相**,它是我们自己那条规则在全历史上的输出。
     → 所以「量指标判不出它」有两种读法,前四节分不开:
         读法甲:量真的没有「进 vs 出」的信息(策略组的主张在我们数据上不成立)
         读法乙:量有信息,★★ 但**我们的阶段号本身没有信息** ——
                 于是「判不中它」反而说明不了量的问题。

★ 本节用一个不依赖我们编号的靶子把这两种读法分开:**后面 60 个交易日的涨跌**。
  ① 我们的阶段号自己分不分得开后面的涨跌?(★ 如果分不开,前四节的靶子就是歪的)
  ② 量指标的方向分不分得开后面的涨跌?(★ 这才是「量最重要」最直接的检验)

★★ 判据:事先定好 —— 「分得开」= 两组的 60 个交易日前瞻收益中位数之差
   ≥ 1 个百分点,且**两段都同向**。★ 低于这个一律判「分不开」。

★★★ 这一节**不是**回测,没有成本、没有仓位、没有止损。
     它只回答「这个标签/这个指标和后面的涨跌有没有关系」。

跑法:python3 probe/volume_direction_1030/forward_check.py
"""
from __future__ import annotations

import importlib.util
import json
import os
import sys

import numpy as np
import pandas as pd

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
sys.path.insert(0, _REPO)

from engine import cache, pool_scope                              # noqa: E402
from engine import state_axis_tri_1029 as tri                     # noqa: E402

_spec = importlib.util.spec_from_file_location(
    "_sp_1030", os.path.join(_REPO, "probe", "stage_path_1030", "run_probe.py"))
SP = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(SP)

sys.path.insert(0, _HERE)
import vol_dir as VD                                              # noqa: E402

OUT = os.path.join(_HERE, "results_5前瞻收益.json")

#: 前瞻窗口(**交易日**)—— ★【XING 填的】三个邻近点,判据同样是三点同向
FWD = (20, 60, 120)
HSTAR = 250          # ★ 和第一节订正出来的 H* 一致
MIN_SPREAD = 0.01    # ★ 事先定好:中位数之差 ≥1 个百分点才算「分得开」


def _stats(r: np.ndarray) -> dict:
    r = r[np.isfinite(r)]
    if len(r) == 0:
        return {"n": 0}
    return {"n": int(len(r)), "中位数": round(float(np.median(r)), 4),
            "平均": round(float(np.mean(r)), 4),
            "胜率(>0)": round(float((r > 0).mean()), 4)}


def main() -> int:
    p = cache.load()
    cl = p["close"]
    syms = list(cl.columns)
    idx = cl.index
    keep = np.asarray(idx >= pd.Timestamp(tri.START))
    pos = np.arange(len(idx))

    picks = [("1-放量日方向性", 20, 2.0), ("3-A/D线斜率", 20, None),
             ("6-Gemini规则", 20, 2.0)]
    pi = pool_scope.PoolIndex()
    acc = {"truth": [], "date": [], "inscope": []}
    for f in FWD:
        acc[f"fwd{f}"] = []
    for pk in picks:
        acc[str(pk)] = []

    for s in syms:
        c = cl[s].to_numpy()
        a = cl[s].notna().to_numpy()
        fv = int(a.argmax()) if a.any() else len(a)
        lab, _r, _e = SP.daily_labels(c, 0)
        ls = np.asarray([str(x) for x in lab])
        hist = pos - fv
        m = keep & (hist >= HSTAR) & np.isin(ls, ["1", "3"])
        if not m.any():
            continue
        cols = [p[f][s].to_numpy() for f in ("open", "high", "low", "close", "volume")]
        P = VD.bar_prims(*cols)
        scs = {pk: VD.score_panel(P, pk[0], pk[1], pk[2]) for pk in picks}
        t = np.flatnonzero(m)
        acc["truth"].append(ls[t])
        acc["date"].append(idx.to_numpy()[t])
        # ★ 池子口径(大+中池):按 (symbol, 当年) 查排名 —— 用 PoolIndex(它管改名)
        yrs = np.asarray([str(y) for y in idx.year])[t]
        rk = {}
        for y in set(yrs.tolist()):
            r, _tier, _how = pi.resolve(s, y)
            rk[y] = bool(r is not None and r <= 2000)
        acc["inscope"].append(np.asarray([rk[y] for y in yrs]))
        for f in FWD:
            fwd = np.full(len(c), np.nan)
            if len(c) > f:
                with np.errstate(invalid="ignore", divide="ignore"):
                    fwd[:-f] = c[f:] / c[:-f] - 1.0
            acc[f"fwd{f}"].append(fwd[t])
        for pk in picks:
            acc[str(pk)].append(scs[pk][t])

    truth = np.concatenate(acc["truth"])
    dates = np.concatenate(acc["date"]).astype("datetime64[ns]").astype("int64")
    isc = np.concatenate(acc["inscope"])
    cut = float(np.median(dates))
    res = {
        "★ 这一节的靶子": "后面 20 / 60 / 120 个**交易日**的收盘涨跌幅(不含成本)",
        "★ 判据(事先定好)": f"两组中位数之差 ≥ {MIN_SPREAD:.0%} 且两段同向 → 「分得开」",
        "样本": {"格子数": int(len(truth)),
                "阶段一(底部)": int((truth == "1").sum()),
                "阶段三(顶部)": int((truth == "3").sum()),
                "H*": HSTAR},
        "★★★ 一 · 我们自己的阶段号分不分得开后面的涨跌": {},
        "★★★ 二 · 量指标的方向分不分得开后面的涨跌": {},
    }

    # ① 我们的阶段号
    for f in FWD:
        r = np.concatenate(acc[f"fwd{f}"])
        s1 = _stats(r[truth == "1"])
        s3 = _stats(r[truth == "3"])
        sp = (s1.get("中位数", 0) - s3.get("中位数", 0))
        seg = {}
        for nm, mm in (("前段", dates <= cut), ("后段", dates > cut)):
            a1 = _stats(r[mm & (truth == "1")])
            a3 = _stats(r[mm & (truth == "3")])
            seg[nm] = {"阶段一": a1, "阶段三": a3,
                       "差(一 − 三)": round(a1.get("中位数", 0) - a3.get("中位数", 0), 4)}
        same = (seg["前段"]["差(一 − 三)"] > 0) == (seg["后段"]["差(一 − 三)"] > 0)
        res["★★★ 一 · 我们自己的阶段号分不分得开后面的涨跌"][f"前瞻 {f} 个交易日"] = {
            "阶段一(底部,该买)": s1, "阶段三(顶部,该卖)": s3,
            "★★★ 中位数之差(一 − 三)": round(sp, 4),
            "两段": seg, "两段同向": bool(same),
            "★★★ 分得开吗": bool(abs(sp) >= MIN_SPREAD and same),
            "★ 方向对不对": ("对(阶段一后面涨得多)" if sp > 0
                          else "★★★ **反的**(阶段三后面反而涨得多)"),
        }

    # ② 量指标
    for pk in picks:
        sc = np.concatenate(acc[str(pk)])
        have = np.isfinite(sc) & (sc != 0.0)
        ent = {"覆盖率": round(float(have.mean()), 4),
               "归属": VD.INDICATORS[pk[0]]["attr"]}
        for f in FWD:
            r = np.concatenate(acc[f"fwd{f}"])
            inn = _stats(r[have & (sc > 0)])      # 量在进 → 假设该涨
            outt = _stats(r[have & (sc < 0)])     # 量在出 → 假设该跌
            sp = inn.get("中位数", 0) - outt.get("中位数", 0)
            seg = {}
            for nm, mm in (("前段", dates <= cut), ("后段", dates > cut)):
                a1 = _stats(r[mm & have & (sc > 0)])
                a3 = _stats(r[mm & have & (sc < 0)])
                seg[nm] = {"量在进": a1, "量在出": a3,
                           "差(进 − 出)": round(a1.get("中位数", 0)
                                              - a3.get("中位数", 0), 4)}
            same = (seg["前段"]["差(进 − 出)"] > 0) == (seg["后段"]["差(进 − 出)"] > 0)
            # ★★ 池子口径复核:这一节是本轮**唯一一个有信号的结果**,
            #    所以必须在大+中池上再量一遍,确认不是小票在带节奏。
            p1 = _stats(r[isc & have & (sc > 0)])
            p3 = _stats(r[isc & have & (sc < 0)])
            sp_isc = p1.get("中位数", 0) - p3.get("中位数", 0)
            ent[f"前瞻 {f} 个交易日"] = {
                "量在进(score>0)": inn, "量在出(score<0)": outt,
                "★★★ 中位数之差(进 − 出)": round(sp, 4),
                "两段": seg, "两段同向": bool(same),
                "★★★ 分得开吗": bool(abs(sp) >= MIN_SPREAD and same),
                "★★ 只要大+中池(rank ≤ 2000)": {
                    "量在进": p1, "量在出": p3,
                    "中位数之差(进 − 出)": round(sp_isc, 4),
                    "和全 300 只同向吗": bool((sp > 0) == (sp_isc > 0)),
                },
            }
        res["★★★ 二 · 量指标的方向分不分得开后面的涨跌"][
            f"{pk[0]}|窗口{pk[1]}" + (f"×{pk[2]}倍" if pk[2] else "")] = ent

    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False, indent=1)[:4000])
    return 0


if __name__ == "__main__":
    sys.exit(main())
