# -*- coding: utf-8 -*-
"""
★★★★★ 新旧尺子对照 —— ★ 在**仓库里现成的 33 份剔脏日流水**上跑，★★★ 不跑回测。

★★ 这一份要回答的**只有一个问题**：
   ★★★ 「把那四条尺子错修好之后，**哪些结论会翻，翻多少**？」

★★★★★ ⚠ 两件必须跟着这份数一起说（★ 不写就是误导）：
   ① ★★★ 这 33 条臂跑在**老池（2,224 只）× 2015~2025**上。
      ★★ 今天上午 Lin 已拍板**考卷并回研究池**（并池 3,834 / 窗口 2016~2025，
         B 路又拉到 2004~2025）→ ★★★ **这些数本身已经不作数了**。
      → ★ 所以本份**不是成绩表**，是**尺子的体检表**：量的是「尺子改了之后数会挪多少」。
   ② ★★ 流水本身是**价格口径**（TOTAL_RETURN_DEFAULT 今天上午才打开）→
      ★★★ 策略那一侧也缺分红。★ 本份只能修**基准那一侧**，所以
        「全收益替身」那一列是**对我们不利的那一半修正**，★★ 另一半（策略侧）要重跑才有。
      → ★★★ 诚实读法：下面那个「差值变化」是**修正的上界**，不是最终值。
"""
from __future__ import annotations

import glob
import importlib.util
import io
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "挂件_1106"))

import 台_公共_1106 as 台                                        # noqa: E402  ★ 现用口径
_s = importlib.util.spec_from_file_location("V2", os.path.join(HERE, "尺子v2_1107.py"))
V = importlib.util.module_from_spec(_s); _s.loader.exec_module(V)  # noqa: E402
_s2 = importlib.util.spec_from_file_location("M91", "probe/买入持有新尺子_1106/新尺子_1106.py")
M = importlib.util.module_from_spec(_s2); _s2.loader.exec_module(M)  # noqa: E402

LEDG = "probe/剔脏日重出_1107/ledgers_clean"
PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
OUT = os.path.join(HERE, "尺子v2对照_报告_1107.json")


def main() -> int:
    基 = V.基准两口径("SPY")
    w = pd.read_parquet(PANEL)
    cl = w["close"]
    del w
    spy价 = 基["_收盘"]

    报 = {"★口径头": V.口径头(
        全收益或价格="★★★ 基准侧**两个都算**（价格 / 全收益）；★ 策略侧流水是**价格口径**（无法补）",
        摩擦档="★ 流水自带（基本面那批 30bp 单边）",
        窗口=f"{M.PERF0.date()} → {M.PERF1.date()}（★ 组合层那一列）",
        池子="★★★ 老池 2,224 只 —— ★ 已被今天上午的「并池 3,834」取代，**本份不是成绩表**",
        标签滞后天="★ 流水沿用原跑批口径（财报滞后见《98》）"),
        "★★★这一份是什么": {
            "是": "★★★ **尺子的体检表** —— 量「四条尺子错修好之后，数会挪多少、结论翻不翻」",
            "不是": "★★★ **不是成绩表** —— 这 33 条臂的池子和窗口今天上午已经作废",
            "跑没跑回测": "★★ 没有 —— 只用仓库里现成的 33 份剔脏日流水重新量",
        },
        "★★★基准两口径自证": {k: v for k, v in 基.items() if not k.startswith("_")},
        "逐条": {}, "★★★汇总": {}}

    # ★ SPY 两口径在绩效窗口内的年化（★★ 给下面所有差值一个尺度感）
    win = (spy价.index >= M.PERF0) & (spy价.index <= M.PERF1)
    报["★★★基准两口径自证"]["★绩效窗口内年化"] = {
        "价格pct": round(V.年化(基["_价格日收益"].loc[win]) * 100, 3),
        "全收益pct": round(V.年化(基["_全收益日收益"].loc[win]) * 100, 3),
    }
    报["★★★基准两口径自证"]["★★★差pct_年"] = round(
        报["★★★基准两口径自证"]["★绩效窗口内年化"]["全收益pct"]
        - 报["★★★基准两口径自证"]["★绩效窗口内年化"]["价格pct"], 3)

    失败 = []
    for f in sorted(glob.glob(os.path.join(LEDG, "REAL__*.csv"))):
        名 = os.path.basename(f)[6:-4]
        rec: dict = {}
        try:
            d = pd.read_csv(f)
            for c in ("entry_date", "exit_date"):
                d[c] = pd.to_datetime(d[c], errors="coerce")
            for c in ("notional_in", "net_pnl", "shares", "entry_price"):
                if c in d.columns:
                    d[c] = pd.to_numeric(d[c], errors="coerce")
            d = d.dropna(subset=["entry_date", "exit_date", "notional_in", "net_pnl"])
            d = d[d["notional_in"] > 0].reset_index(drop=True)
            if len(d) < 20:
                rec = {"★跑失败": f"只剩 {len(d)} 笔(<20) —— ★ 不出数（规矩⑯ 不打空表）"}
                失败.append(名); 报["逐条"][名] = rec
                print(f"✗ {名[:34]:34s} {rec['★跑失败']}", flush=True)
                continue

            真 = d["net_pnl"] / d["notional_in"]
            替 = V.替身收益_两口径(d, 基)
            ok = 真.notna() & 替["_价格"].notna() & 替["_全收益"].notna()
            nok = int(ok.sum())
            if nok < 20:
                rec = {"★跑失败": f"可配对只有 {nok} 笔(<20)"}
                失败.append(名); 报["逐条"][名] = rec
                print(f"✗ {名[:34]:34s} {rec['★跑失败']}", flush=True)
                continue

            差_价 = (真[ok] - 替["_价格"][ok])
            差_全 = (真[ok] - 替["_全收益"][ok])
            st价 = 台.聚类t(差_价, d.loc[ok, "entry_date"])
            st全 = 台.聚类t(差_全, d.loc[ok, "entry_date"])

            # ★★★ 自证：我这份的「价格替身」必须和现用口径 `台.替身收益` 一字不差
            替旧 = 台.替身收益(d)
            共 = (替旧.notna() & 替["_价格"].notna())
            最大差 = float((替旧[共] - 替["_价格"][共]).abs().max()) if 共.any() else float("nan")

            rec["①可配对笔数"] = nok
            rec["★★★②复刻自证_与现用替身口径最大差"] = (
                f"{最大差:.2e}" if np.isfinite(最大差) else "★算不出")
            rec["★★★②自证过没过"] = ("✅ 过（< 1e-12，★ 同一套时点口径）"
                                 if np.isfinite(最大差) and 最大差 < 1e-12
                                 else f"★★★ 没过！差 {最大差:.2e} —— 停下来查")
            rec["★★★③#76基准侧全收益"] = {
                "替身_价格口径_每笔pct": round(float(替["_价格"][ok].mean()) * 100, 4),
                "替身_全收益口径_每笔pct": round(float(替["_全收益"][ok].mean()) * 100, 4),
                "★每笔平均分红率pct": round(float(替["_每笔分红率"][ok].mean()) * 100, 4),
                "①差_对价格替身pct": round(st价["均值"] * 100, 4),
                "①t_对价格替身": (round(float(st价["t"]), 2) if np.isfinite(st价["t"]) else None),
                "★★★②差_对全收益替身pct": round(st全["均值"] * 100, 4),
                "★★★②t_对全收益替身": (round(float(st全["t"]), 2) if np.isfinite(st全["t"]) else None),
                "★★★③差值被修掉多少pct": round((st全["均值"] - st价["均值"]) * 100, 4),
            }
            # ★★★ ⑧ 重叠交易：四种标准误并排（★ 用修正后的全收益差值）
            rec["★★★④第⑧条_重叠交易"] = V.重叠聚类t(
                差_全, d.loc[ok, "entry_date"], d.loc[ok, "exit_date"])

            # ★ 组合层：日净值 → ③ 夏普 Lo + ⑥ 对数
            syms = tuple(sorted(set(d["symbol"].astype(str))))
            有 = [s for s in syms if s in cl.columns]
            sub = cl[有]
            eq, 在场, 缺 = M.逐日净值(d, sub)
            wmask = (eq.index >= M.PERF0) & (eq.index <= M.PERF1)
            eqw = eq.loc[wmask].dropna()
            if len(eqw) >= 60:
                r = eqw.pct_change().dropna()
                rb价 = 基["_价格日收益"].reindex(eqw.index).dropna()
                rb全 = 基["_全收益日收益"].reindex(eqw.index).dropna()
                rex = (r - rb全).dropna()
                rec["★★★⑤第③条_夏普Lo2002"] = {
                    "策略超额(对全收益SPY)": V.夏普_Lo(rex),
                }
                rec["★★★⑥第⑥条_对数收益"] = {
                    "对价格SPY": V.对数检验(r, rb价),
                    "★★★对全收益SPY": V.对数检验(r, rb全),
                }
            else:
                rec["★★★⑤第③条_夏普Lo2002"] = {"★算不出": f"窗口内只有 {len(eqw)} 天"}
                rec["★★★⑥第⑥条_对数收益"] = {"★算不出": f"窗口内只有 {len(eqw)} 天"}
            if 缺:
                rec["★⑰面板里没有的票"] = [len(缺), sorted(缺)[:5]]
        except Exception as e:
            import traceback
            rec = {"★跑失败": f"{type(e).__name__}: {str(e)[:200]}",
                   "回溯": traceback.format_exc(limit=3)[-500:]}
            失败.append(名)
        报["逐条"][名] = rec
        b = rec.get("★★★③#76基准侧全收益") or {}
        o8 = rec.get("★★★④第⑧条_重叠交易") or {}
        print(f"{'✗' if '★跑失败' in rec else '✓'} {名[:34]:34s} "
              f"替身价 t={b.get('①t_对价格替身')} → 全收益 t={b.get('★★★②t_对全收益替身')} "
              f"| 重叠块t={(o8.get('★★★③④按持有期重叠连通块') or {}).get('t')}", flush=True)

    # ══════════════ 汇总
    L = 报["逐条"]
    def 数(f):
        return sorted(k for k, v in L.items() if "★跑失败" not in v and f(v))
    def g(v, *ks):
        cur = v
        for k in ks:
            cur = (cur or {}).get(k)
        return cur
    正价 = 数(lambda v: isinstance(g(v, "★★★③#76基准侧全收益", "①t_对价格替身"), (int, float))
             and g(v, "★★★③#76基准侧全收益", "①t_对价格替身") >= 1.96)
    正全 = 数(lambda v: isinstance(g(v, "★★★③#76基准侧全收益", "★★★②t_对全收益替身"), (int, float))
             and g(v, "★★★③#76基准侧全收益", "★★★②t_对全收益替身") >= 1.96)
    负价 = 数(lambda v: isinstance(g(v, "★★★③#76基准侧全收益", "①t_对价格替身"), (int, float))
             and g(v, "★★★③#76基准侧全收益", "①t_对价格替身") <= -1.96)
    负全 = 数(lambda v: isinstance(g(v, "★★★③#76基准侧全收益", "★★★②t_对全收益替身"), (int, float))
             and g(v, "★★★③#76基准侧全收益", "★★★②t_对全收益替身") <= -1.96)
    挪 = [g(v, "★★★③#76基准侧全收益", "★★★③差值被修掉多少pct")
         for v in L.values() if "★跑失败" not in v]
    挪 = [x for x in 挪 if isinstance(x, (int, float))]
    # ★★★ ⑧ 条：现用口径 t 过线、但重叠块 t 不过线的
    翻8 = 数(lambda v: isinstance(g(v, "★★★④第⑧条_重叠交易", "③②按进场日聚类_现用", "t"), (int, float))
            and abs(g(v, "★★★④第⑧条_重叠交易", "③②按进场日聚类_现用", "t")) >= 1.96
            and isinstance(g(v, "★★★④第⑧条_重叠交易", "★★★③④按持有期重叠连通块", "t"), (int, float))
            and abs(g(v, "★★★④第⑧条_重叠交易", "★★★③④按持有期重叠连通块", "t")) < 1.96)
    同时 = [g(v, "★★★④第⑧条_重叠交易", "★★★④平均同时在场笔数")
           for v in L.values() if "★跑失败" not in v]
    同时 = [x for x in 同时 if isinstance(x, (int, float))]
    比 = [g(v, "★★★⑤第③条_夏普Lo2002", "策略超额(对全收益SPY)", "★★★④修正比_eta除根q")
         for v in L.values() if "★跑失败" not in v]
    比 = [x for x in 比 if isinstance(x, (int, float))]
    拖 = [g(v, "★★★⑥第⑥条_对数收益", "★★★对全收益SPY", "★★★④波动拖累pct_年")
         for v in L.values() if "★跑失败" not in v]
    拖 = [x for x in 拖 if isinstance(x, (int, float))]

    报["★★★汇总"] = {
        "臂数": len(L), "★★★跑失败的": {"条数": len(失败), "名单": 失败},
        "★★★①#76基准侧全收益的后果": {
            "每笔差值平均被修掉pct": (round(float(np.mean(挪)), 4) if 挪 else None),
            "最多被修掉pct": (round(float(np.min(挪)), 4) if 挪 else None),
            "正显著_对价格替身": {"条数": len(正价), "名单": 正价},
            "★★★正显著_对全收益替身": {"条数": len(正全), "名单": 正全},
            "负显著_对价格替身": {"条数": len(负价)},
            "★★★负显著_对全收益替身": {"条数": len(负全)},
            "★读法": "★★★ 修正方向必然对我们不利（替身拿到分红了）—— ★ 所以正显著只会变少、负显著只会变多",
        },
        "★★★②第⑧条_重叠交易的后果": {
            "平均同时在场笔数_中位": (round(float(np.median(同时)), 1) if 同时 else None),
            "★★★现用t过线但重叠块t不过线的": {"条数": len(翻8), "名单": 翻8},
            "★读法": "★★ 这些条的「显著」是**持有期重叠**造出来的，★★★ 换最保守的聚类就没了",
        },
        "★★★③第③条_夏普Lo修正的后果": {
            "修正比_中位": (round(float(np.median(比)), 4) if 比 else None),
            "修正比_范围": ([round(float(np.min(比)), 4), round(float(np.max(比)), 4)] if 比 else None),
            "★读法": "★ <1 → 朴素年化夏普和朴素 t 都**偏高**（正自相关）",
        },
        "★★★④第⑥条_对数收益的后果": {
            "波动拖累_中位pct_年": (round(float(np.median(拖)), 3) if 拖 else None),
            "波动拖累_范围pct_年": ([round(float(np.min(拖)), 3), round(float(np.max(拖)), 3)] if 拖 else None),
            "★读法": "★★ 算术年化**系统性高于**对数年化这么多 —— ★★★ 报成绩要用对数那一行",
        },
    }
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print("\n★★★ 汇总:", json.dumps(报["★★★汇总"], ensure_ascii=False, indent=1))
    print("★ 写到", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
