#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 第二件 + 第三件 —— 两道新门,逐链算 + 和旧门对照(2026-10-30)

第二件:新门 `Z ≥ 1.96` + 对照组偏差 ≤ ±5%(替掉旧的 `Z ≥ 1.65`)
        ★★★ 并把 1.96 / 2.5 / 3.0 三档一起算出来并列报 ——
          外部意见正文说「必须 t ≥ 3.0」(Harvey/Liu/Zhu 2016),
          它最后给的矩阵里却写的是 Z ≥ 1.96。★ 这两个数差很远,
          本轮按 1.96 实现,但把换门槛的代价摆出来,不替它圆。

第三件:新门 双向聚类面板回归 `t > 2.0`(替掉「四格符号一致」)
        ★ 实现和反向自测在 `panel_t_1030.py`(四项自测全过才许出数)。

输入(全部现成,★ 不重跑回测):
   probe/gates_rebuild_1030/bench1_fixed_1030.json   ← 第一件的产出(新基准一 + 判据 Z)
   probe/gates_rebuild_1030/ledgers_1030/*.csv       ← 真链流水 + 50 种子对照并池流水
   probe/v2_rerun_1030/bench_two_1030.json           ← 旧基准一(对差)
   engine/results_1029_*.json / results_1030_剔污染.json ← 旧门「四格符号一致」
   pilot_300|pilot_50/*/fundamentals.json            ← SIC 行业

跑法:python3 probe/gates_rebuild_1030/run_gates_1030.py
"""
from __future__ import annotations

import json
import os
import sys
import time
import traceback

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

import panel_t_1030 as PT                                    # noqa: E402

NEW_BENCH = os.path.join(HERE, "bench1_fixed_1030.json")
OLD_BENCH = os.path.join(ROOT, "probe", "v2_rerun_1030", "bench_two_1030.json")
LEDGERS = os.path.join(HERE, "ledgers_1030")
OUT = os.path.join(HERE, "gates_1030.json")

Z_LEVELS = (1.65, 1.96, 2.5, 3.0)

OLD_GATE_FILES = {
    "A0十二条": ("engine/results_1029_A0十二条.json", "链"),
    "技术派六条三版": ("engine/results_1029_技术派六条三版.json", "各版结果"),
    "批五修正": ("engine/results_1029_批五修正.json", "各版结果"),
    "原著离场": ("engine/results_1029_原著离场.json", "各版结果"),
    "剔污染": ("engine/results_1030_剔污染.json", "各链两版"),
}

#: ★★ 纪律:无止损 → 1R = 进场价 → R 退化成收益率,**不能和有止损的放一列排序**。
#   全库只有 4 条无止损:buy_and_hold / 技-2 / 技-12×2。
#   ★ 出处:probe/v2_rerun_1030/按链-真重跑-★无止损-R是收益率-1030.csv
NO_STOP_KEYS = ("buy_and_hold", "技-2 ", "技-12 ")


def _say(*a):
    try:
        print(*a, flush=True)
    except Exception:
        pass


def is_no_stop(label: str) -> bool:
    name = label.split("/", 1)[-1]
    return any(k in name or name.startswith(k.strip()) for k in NO_STOP_KEYS)


# ══════════════════════════════════════════════════════════════════════════
# 一 · 旧门:四格符号一致
# ══════════════════════════════════════════════════════════════════════════

def old_four_cell() -> dict[str, dict]:
    out: dict[str, dict] = {}
    for batch, (f, key) in OLD_GATE_FILES.items():
        d = json.load(open(os.path.join(ROOT, f), encoding="utf-8"))
        for r in d[key]:
            label = f"{batch}/{r['报表名']}"
            g = r.get("★两窗口两池子硬关")
            if not isinstance(g, dict) or not g.get("四格"):
                # ★★ 「没跑过」和「跑了没过」必须分开 —— 这里显式登记前者
                out[label] = {"★旧门状态": "没跑过(这一批没算四格)"}
                continue
            cells = g["四格"]
            zs = [c.get("Z") for c in cells]
            dif = [c.get("差值") for c in cells]
            pos = sum(1 for z in zs if z is not None and z > 0)
            out[label] = {
                "★旧门状态": "跑过",
                "四格Z": zs, "四格差值": dif,
                "四格符号": "".join("+" if (z or 0) > 0 else "−" for z in zs),
                "正号格数": pos,
                "四格全正": bool(pos == 4),
                "旧门通过(引擎记的)": bool(g.get("通过")),
                "最弱格差值": (min(x for x in dif if x is not None)
                               if any(x is not None for x in dif) else None),
                "理由": g.get("理由"),
            }
    return out


# ══════════════════════════════════════════════════════════════════════════
# 二 · 第三件:逐链跑面板回归
# ══════════════════════════════════════════════════════════════════════════

def _prep(df: pd.DataFrame, sic: dict[str, str]) -> pd.DataFrame:
    df["date"] = pd.to_datetime(df["entry_date"])
    df["ym"] = df["date"].dt.strftime("%Y-%m")
    df["sym"] = df["symbol"].astype(str)
    # ★ 池子存当年年初代码(ANTM)、流水存最终代码(ELV);本地 SIC 目录用的
    #   也是最终代码(实测 pilot_300/ELV 存在、pilot_300/ANTM 不存在)→ 直接对。
    df["ind"] = df["sym"].map(sic).fillna("SIC未知")
    df["y"] = pd.to_numeric(df["r_multiple_net"], errors="coerce")
    return df


def load_one(label: str, which: str, sic: dict[str, str],
             d: float) -> pd.DataFrame | None:
    safe = label.replace("/", "_").replace(" ", "")
    f = os.path.join(LEDGERS, f"{which}__{safe}.csv")
    if not os.path.exists(f):
        return None
    t = pd.read_csv(f, encoding="utf-8-sig")
    if t.empty:
        return None
    t = t[["symbol", "entry_date", "r_multiple_net"]].copy()
    t["d"] = d
    return _prep(t, sic)


def load_pair(label: str, sic: dict[str, str]) -> pd.DataFrame | None:
    """
    ★★ 真链 + 50 种子对照并池 摞在一起。
    ★ 对照流水不在(= 基准一的笔数前提破了,那条链被禁止出下游数)→ 返回 None,
      主表不出数。★ 但「只用真链」那一栏照样出 —— 它不需要对照组。
    """
    a = load_one(label, "REAL", sic, 1.0)
    b = load_one(label, "CTRL", sic, 0.0)
    if a is None or b is None:
        return None
    return pd.concat([a, b], ignore_index=True)


# ══════════════════════════════════════════════════════════════════════════
# 三 · main
# ══════════════════════════════════════════════════════════════════════════

def main() -> int:
    t0 = time.time()
    _say("★★★ 先跑面板回归的反向自测 —— 不过就停,不出任何数")
    st = PT.selftest(verbose=False)
    _say(json.dumps(st, ensure_ascii=False, indent=1))

    new = {r["链"]: r for r in
           json.load(open(NEW_BENCH, encoding="utf-8"))["逐链"]}
    old = {r["链"]: r for r in
           json.load(open(OLD_BENCH, encoding="utf-8"))["逐链"]}
    old4 = old_four_cell()
    sic = PT.sic_map()
    _say(f"★ SIC 覆盖 {len(sic)} 只票\n")

    rows = []
    for i, (label, r) in enumerate(new.items(), 1):
        rec: dict = {"链": label, "族": r.get("族"), "配置": r.get("配置"),
                     "笔数": r.get("笔数"), "每笔净R": r.get("每笔净R"),
                     "★R是收益率(无止损,不许和有止损同列排序)": is_no_stop(label)}
        b = r.get("★基准一") or {}
        ob = (old.get(label) or {}).get("★基准一_同环境随机进场") or {}

        # ---- 第一件:新旧基准一对差
        rec["基准一_新"] = b.get("★真信号每笔R − 随机进场每笔R")
        rec["基准一_旧"] = ob.get("★真信号每笔R − 随机进场每笔R")
        if rec["基准一_新"] is not None and rec["基准一_旧"] is not None:
            rec["基准一_差(新−旧)"] = rec["基准一_新"] - rec["基准一_旧"]
            rec["★基准一符号翻了"] = bool(
                np.sign(rec["基准一_新"]) != np.sign(rec["基准一_旧"]))
        rec["对照笔数偏差_新"] = b.get("★对照笔数偏差")
        rec["对照笔数偏差_旧"] = (
            None if ob.get("随机进场_校准后对照笔数") is None
            else (ob["随机进场_校准后对照笔数"] - ob["随机进场_真链笔数"])
                 / max(1, ob["随机进场_真链笔数"]))
        rec["★旧值当年就破了±5%"] = (
            None if rec["对照笔数偏差_旧"] is None
            else bool(abs(rec["对照笔数偏差_旧"]) > 0.05))
        rec["对照每笔R均值的标准误_新"] = b.get("★对照每笔R均值的标准误")
        rec["种子数_新"] = b.get("随机进场_种子数")
        rec["种子数_旧"] = ob.get("随机进场_种子数")
        rec["前提破了_禁止下游"] = bool(r.get("★前提破了_禁止下游"))
        if r.get("★前提破了_禁止下游"):
            rec["前提破了_说明"] = r["★前提破了_禁止下游"]["说明"].split("\n")[1].strip()

        # ---- 第二件:Z 门。★ 取两关里更小的那个(纪律:不许取 max)
        zs = r.get("★判据Z_用50种子并池对照") or {}
        z1 = zs.get("条件分层随机")
        z2 = zs.get("块重排(Politis&Romano)")
        zmin = (min(x for x in (z1, z2) if x is not None)
                if any(x is not None for x in (z1, z2)) else None)
        rec["Z_条件分层随机"] = z1
        rec["Z_块重排"] = z2
        rec["★Z_取两关里小的那个"] = zmin
        rec["Z_波动率选择(附报,不判生死)"] = zs.get("波动率选择(|R|)")
        ok_dev = (rec["对照笔数偏差_新"] is not None
                  and abs(rec["对照笔数偏差_新"]) <= 0.05)
        rec["对照组偏差≤±5%"] = bool(ok_dev)
        for lv in Z_LEVELS:
            rec[f"过Z≥{lv}门"] = bool(zmin is not None and zmin >= lv and ok_dev)

        # ---- 第三件:面板回归 t
        try:
            # ★ 「只用真链、常数项、双向聚类」那一栏 —— 不需要对照组,先单独算
            real = load_one(label, "REAL", sic, 1.0)
            if real is not None:
                g0 = PT.cluster_t_mean_only(real)
                rec["t_只用真链_常数项_双向聚类(无固定效应)"] = g0.get("t")
                rec["t_只用真链_每笔R均值"] = g0.get("每笔R均值")
            df = load_pair(label, sic)
            if df is None:
                rec["★面板t"] = None
                rec["面板t_不出数"] = (
                    "★ 基准一的笔数前提破了 → 对照流水按纪律不落盘,主表不出数"
                    if rec["前提破了_禁止下游"] else "缺流水(真链或对照并池)")
            else:
                g = PT.cluster_t(df)
                rec["★面板t"] = g.get("t")
                rec["面板t_beta"] = g.get("beta")
                rec["面板t_不聚类t(只为看虚高多少)"] = g.get(
                    "t_不做聚类(只为对照看虚高多少)")
                rec["面板t_行数"] = g.get("n")
                rec["面板t_真信号笔数"] = g.get("真信号笔数")
                rec["面板t_对照笔数"] = g.get("对照笔数")
                rec["面板t_时间聚类组数"] = g.get("聚类_时间组数")
                rec["面板t_股票聚类组数"] = g.get("聚类_股票组数")
                rec["面板t_固定效应列数"] = g.get("固定效应_列数")
                rec["面板t_不出数"] = g.get("★不出数")
        except Exception:
            rec["★面板t"] = None
            rec["面板t_出错"] = traceback.format_exc(limit=3)
        t_ = rec.get("★面板t")
        rec["★过新门 t>2.0"] = bool(t_ is not None and t_ > PT.T_GATE)

        # ---- 旧门 vs 新门
        o = old4.get(label) or {"★旧门状态": "没跑过(名字对不上)"}
        rec["旧门状态"] = o["★旧门状态"]
        rec["旧门_四格符号"] = o.get("四格符号")
        rec["旧门_四格Z"] = o.get("四格Z")
        rec["旧门_四格全正"] = o.get("四格全正")
        rec["旧门_通过"] = o.get("旧门通过(引擎记的)")
        if o["★旧门状态"] == "跑过":
            rec["★旧门挡住·新门放过"] = bool(
                (not o.get("旧门通过(引擎记的)")) and rec["★过新门 t>2.0"])
            rec["★旧门放过·新门挡住"] = bool(
                o.get("旧门通过(引擎记的)") and not rec["★过新门 t>2.0"])
        rows.append(rec)
        try:
            _say(f"[{i}/{len(new)}] {label[:48]:48s} "
                 f"基准一 {rec['基准一_旧']}→{rec['基准一_新']} "
                 f"Zmin={zmin} 面板t={rec['★面板t']} "
                 f"旧门={rec['旧门_四格符号']}")
        except Exception:
            pass

    # ---- 汇总
    runnable = [r for r in rows if not r["前提破了_禁止下游"]]
    tt = [r for r in rows if r.get("★面板t") is not None]
    out = {
        "生成时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "面板回归反向自测": st,
        "口径": {
            "第二件_新门": "Z ≥ 1.96 且 对照组笔数偏差 ≤ ±5%(替掉 Z ≥ 1.65)",
            "第二件_Z取哪个": "条件分层随机 与 块重排 两关里**更小**的那个"
                              "(★ 不许取 max —— stats_gate 顶部的硬纪律)",
            "第三件_新门": "带行业(SIC 两位)+ 年月固定效应的面板回归,"
                           "按 entry_date 与 symbol 双向聚类的稳健 t > 2.0",
            "第三件_回归式": "R_i = β·真信号_i + 行业FE + 年月FE + ε_i;"
                             "报的是 β 的双向聚类 t",
            "第三件_数据来源": "★ 只用现有流水(真链 + 50 种子对照并池),没重跑回测",
            "★结论口径": "★★★ Z 不显著时一律写「在现有样本容量下未显现统计显著性」,"
                          "严禁写「不成立」—— 未能拒绝零假设 ≠ 零假设成立。"
                          "★★ 审核结果不判生死:基准不是裁判,是货架上另一个商品。",
        },
        "汇总": {
            "链数": len(rows),
            "前提破了·基准一不出数的条数": len(rows) - len(runnable),
            "基准一符号翻了的条数": sum(1 for r in rows
                                        if r.get("★基准一符号翻了")),
            "旧值当年就破了±5%的条数": sum(1 for r in rows
                                           if r.get("★旧值当年就破了±5%")),
            "各档Z过关条数": {f"Z≥{lv}": sum(1 for r in rows if r.get(f"过Z≥{lv}门"))
                              for lv in Z_LEVELS},
            "★纯噪音期望过关数(测试次数 × 单侧 p)": {
                f"Z≥{lv}": round(len(rows) * float(
                    __import__("scipy.stats", fromlist=["norm"]).norm.sf(lv)), 2)
                for lv in Z_LEVELS},
            "面板t出数的条数": len(tt),
            "★过新门 t>2.0 的条数": sum(1 for r in rows if r["★过新门 t>2.0"]),
            "旧门跑过的条数": sum(1 for r in rows if r["旧门状态"] == "跑过"),
            "旧门通过的条数": sum(1 for r in rows if r.get("旧门_通过")),
            "★旧门挡住·新门放过": [r["链"] for r in rows
                                   if r.get("★旧门挡住·新门放过")],
            "★旧门放过·新门挡住": [r["链"] for r in rows
                                   if r.get("★旧门放过·新门挡住")],
        },
        "逐链": rows,
        "总耗时秒": round(time.time() - t0, 1),
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    pd.DataFrame(rows).to_csv(os.path.join(HERE, "按链-两道新门-1030.csv"),
                              index=False, encoding="utf-8-sig")
    try:
        _say("\n" + json.dumps(out["汇总"], ensure_ascii=False, indent=1))
        _say(f"\n共 {out['总耗时秒']}s")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
