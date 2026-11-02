#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 汇总更正:「老池」那一列改用 bench1_rerun_1102 · 2026-11-02

三秒版:跑批脚本里「老池」读的是 `bench1_rerun_1031.json`。★★ 那一份不能用 ——
        它跑在退化 R 修复**之前**,35 条的基准一是坏数。
        ★★★ 所以 `exam_run_1102.json` 里的「老池_*」和「★符号是否翻转」
        **全部作废**,本脚本用 `bench1_rerun_1102.json` 重算一份权威汇总。

★ 为什么不改跑批脚本重跑:跑批已经跑过半,老池那几列只是**并列展示用**,
  不参与考卷这一侧的任何计算(考卷的笔数、每笔 R、基准一、对照偏差、退化 R
  全都和老池无关)。★★ 为了换一个对照源重跑 5 小时不成比例。
★★★ 所以处置是:**不动已落盘的逐链 JSON**(它是原始产物),
  另出一份更正汇总,★ 报告一律引用这一份。

★ 本脚本只读不写原件,输出 `汇总更正_老池用1102-1102.json`。

★★★ 2026-11-02 策略组要求的第二处更正 —— **退化 R 必须拆成两个数**:
   ★ 原来写成一个 `考卷_退化R再出现的 = 6`,★★ 它的定义是「真链**或**对照组
     任一有退化笔的链数」—— 而日志里打印的 `退化R=0` 是**真链**的笔数。
   ★★★ 一个合起来的「6」会让读的人以为**考卷的真链出了退化 R**,
     ★ 而实测恰好相反:真链一笔都没有。
   ★ 策略组原话:「我今天就因为同一类错,对着老池说了四次『真链 0 笔、
     全在对照组』才说对」(手册 v3.1 坑表第 36 处)。
   → 所以本脚本一律给四个数:真链链数 / 真链笔数 / 对照组链数 / 对照组笔数,
     ★★ 名字里写明是哪一边,**不许合并**。
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))

SRC = os.path.join(HERE, "exam_run_1102.json")
PER_CHAIN = os.path.join(HERE, "per_chain")
OLD = os.path.join(ROOT, "probe", "bench1_rerun_1102", "bench1_rerun_1102.json")
OUT = os.path.join(HERE, "汇总更正_老池用1102-1102.json")

STALE = os.path.join(ROOT, "probe", "bench1_rerun_1031", "bench1_rerun_1031.json")


def exam_rows() -> list[dict]:
    """★ 优先读全量汇总;没有就从 per_chain 重建(可续跑中途也能出表)。"""
    if os.path.exists(SRC):
        return json.load(open(SRC, encoding="utf-8"))["逐链"]
    rows = []
    for f in sorted(os.listdir(PER_CHAIN)):
        if f.endswith(".json"):
            rows.append(json.load(open(os.path.join(PER_CHAIN, f),
                                      encoding="utf-8")))
    return rows


def b1_of(r: dict):
    return (r.get("★基准一") or {}).get("★真信号每笔R − 随机进场每笔R")


# ══════════════════════════════════════════════════════════════════════════
# ★★★ 退化 R —— 四个数,真链和对照组**分开**
#
# ★ 为什么要自己从流水反算,不读结果 JSON 里的字段:
#   `bench1_rerun_1102.json` 的 `★真链退化R` 是去读流水的 `r_degenerate` 列,
#   ★★ 而那一列被 `LEDGER_COLUMNS` 静默丢掉了(手册 v3.1 坑表第 37 处)——
#   所以那个字段实测是 `{"退化R笔数": null, "有r_degenerate列": false}`,**没有数**。
#   ★★★ 唯一能数的办法:按 engine 里那同一行判据从 risk_per_share/entry_price 反算。
# ══════════════════════════════════════════════════════════════════════════

#: ★ 和 engine/chain.py:51 DEGENERATE_R_MIN 同一个数
DEGEN_REL = 1e-4


def _scan_one(path: str) -> tuple[int, int]:
    """-> (总笔数, 退化笔数)。"""
    try:
        df = pd.read_csv(path, usecols=lambda c: c in (
            "entry_price", "risk_per_share"))
    except Exception:                                            # noqa: BLE001
        return 0, 0
    if df.empty or "risk_per_share" not in df.columns:
        return int(len(df)), 0
    rps = pd.to_numeric(df["risk_per_share"], errors="coerce").abs()
    ep = pd.to_numeric(df.get("entry_price"), errors="coerce").abs()
    rel = rps / ep.replace(0, np.nan)
    bad = (rel < DEGEN_REL) | rps.isna() | (rps == 0)
    return int(len(df)), int(bad.sum())


def pnl_from_ledgers(ledger_dir: str) -> dict:
    """★★★ 逐链全期净盈亏(从真链流水 net_pnl 加总)。

    ★ 为什么要另算:跑批脚本的逐链记录里**没有**净盈亏这一格
      (只有笔数 / 每笔净R / 每笔毛R / 胜率)。★★ 而「锚点 buy_and_hold
      赢不赢」是比任何单条策略成绩都重要的一条,必须有这个数。
    ★★★ 口径:**在 100 万美元账户上**(engine 的 initial_equity 默认值)——
      ★ 换账户规模不是线性的,引用这个数必须把口径一起说。
    ★ 净盈亏和 R 是两套尺子:无止损的链 R 退化成收益率、不可和有止损同列排序,
      ★★ 但净盈亏不受这个影响(它是钱,不是风险倍数)→ 可以同列排。
    """
    rows = []
    for p in sorted(glob.glob(os.path.join(ledger_dir, "REAL__*.csv"))):
        name = os.path.basename(p)[6:-4]
        try:
            df = pd.read_csv(p, usecols=lambda c: c in ("net_pnl", "gross_pnl"))
        except Exception:                                        # noqa: BLE001
            continue
        if df.empty or "net_pnl" not in df.columns:
            rows.append({"链文件名": name, "净盈亏": 0.0, "笔数": int(len(df))})
            continue
        v = pd.to_numeric(df["net_pnl"], errors="coerce")
        rows.append({"链文件名": name,
                     "净盈亏": float(np.nansum(v.to_numpy())),
                     "笔数": int(len(df))})
    rows.sort(key=lambda x: x["净盈亏"], reverse=True)
    for i, r in enumerate(rows, 1):
        r["净盈亏排名"] = i
    anchor = [r for r in rows if "buy_and_hold" in r["链文件名"]]
    return {
        "口径": "★★★ 在 100 万美元账户上(engine initial_equity 默认值)—— "
                "★ 换规模不是线性的,引用必须带口径",
        "怎么算的": "真链流水 net_pnl 逐笔加总(已扣摩擦)",
        "链数": len(rows),
        "为正的链数": sum(1 for r in rows if r["净盈亏"] > 0),
        "★最高的那条": rows[0] if rows else None,
        "★第二高": rows[1] if len(rows) > 1 else None,
        "★★★锚点 buy_and_hold": anchor[0] if anchor else None,
        "★★★锚点是不是第一": (bool(anchor and anchor[0]["净盈亏排名"] == 1)
                              if anchor else None),
        "逐链": rows,
    }


def degen_from_ledgers(ledger_dir: str) -> dict:
    """扫一个流水目录,真链和对照组分别统计。★ 四个数,名字写明哪一边。"""
    real_chains, real_trades, ctrl_chains, ctrl_trades = [], 0, [], 0
    n_real = n_ctrl = 0
    for p in sorted(glob.glob(os.path.join(ledger_dir, "REAL__*.csv"))):
        n_real += 1
        n, b = _scan_one(p)
        if b:
            real_chains.append({"链文件名": os.path.basename(p)[6:-4],
                                "退化笔数": b, "总笔数": n})
            real_trades += b
    for p in sorted(glob.glob(os.path.join(ledger_dir, "CTRL__*.csv"))):
        n_ctrl += 1
        n, b = _scan_one(p)
        if b:
            ctrl_chains.append({"链文件名": os.path.basename(p)[6:-4],
                                "退化笔数": b, "总笔数": n})
            ctrl_trades += b
    return {
        "判据": f"risk_per_share / entry_price < {DEGEN_REL}"
                " —— ★ 和 engine/chain.py:51 DEGENERATE_R_MIN 同一个数",
        "★扫了多少条真链流水": n_real,
        "★扫了多少条对照组流水": n_ctrl,
        "★★★真链_有退化笔的链数": len(real_chains),
        "★★★真链_退化笔总数": real_trades,
        "★★★对照组_有退化笔的链数": len(ctrl_chains),
        "★★★对照组_退化笔总数": ctrl_trades,
        "真链_逐条": real_chains,
        "对照组_逐条": ctrl_chains,
    }


def main() -> int:
    rows = exam_rows()
    old_d = json.load(open(OLD, encoding="utf-8"))
    old = {r["链"]: r for r in old_d["逐链"]}

    ok = [r for r in rows if r.get("★新基准一值") is not None]
    broke = [r for r in rows if r.get("★前提破了_禁止下游")]
    crash = [r for r in rows if r.get("★跑不了")]
    thin = [r for r in rows if r.get("笔数") is not None and r["笔数"] < 30]
    tol_over = [r for r in ok if r.get("★对照笔数偏差") is not None
                and abs(r["★对照笔数偏差"]) > 0.05]
    # ★★★ 无止损:R 是收益率不是风险倍数 → 不可和有止损的链同列排序
    nostop = [r for r in rows
              if r.get("★无止损_R退化成收益率_不可和有止损同列排序")]
    nostop_old = [old[l] for l in old
                  if old[l].get("★无止损_R退化成收益率_不可和有止损同列排序")]
    # ★★★ 退化 R:四个数,两边分开
    degen_exam = degen_from_ledgers(os.path.join(HERE, "ledgers_1102"))
    degen_old = degen_from_ledgers(
        os.path.join(ROOT, "probe", "bench1_rerun_1102", "ledgers_1102"))
    # ★★★ 净盈亏 —— 「锚点 buy_and_hold 在考卷上还赢不赢」
    pnl_exam = pnl_from_ledgers(os.path.join(HERE, "ledgers_1102"))
    pnl_old = pnl_from_ledgers(
        os.path.join(ROOT, "probe", "bench1_rerun_1102", "ledgers_1102"))

    pairs, flips, missing_old = [], [], []
    for r in ok:
        lab = r["链"]
        o = old.get(lab)
        if o is None:
            missing_old.append(lab)
            continue
        ob = b1_of(o)
        nb = r["★新基准一值"]
        if ob is None:
            missing_old.append(lab)
            continue
        rec = {
            "链": lab,
            "考卷_笔数": r.get("笔数"), "老池_笔数": o.get("笔数"),
            "考卷_每笔净R": r.get("每笔净R"), "老池_每笔净R": o.get("每笔净R"),
            "考卷_基准一": nb, "老池_基准一": ob,
            "差(考卷−老池)": nb - ob,
            "★符号翻转": bool((nb > 0) != (ob > 0)),
            "方向": ("老池赢随机 → 考卷输随机" if ob > 0 and nb <= 0 else
                     "老池输随机 → 考卷赢随机" if ob <= 0 and nb > 0 else
                     "同向"),
            "★考卷笔数<30_不给统计结论": bool((r.get("笔数") or 0) < 30),
        }
        pairs.append(rec)
        if rec["★符号翻转"]:
            flips.append(rec)

    exam_pos = [r for r in ok if r["★新基准一值"] > 0]
    old_pos = [l for l in old if b1_of(old[l]) is not None and b1_of(old[l]) > 0]

    out = {
        "这是什么": "★★★ 汇总更正 —— 「老池」那一列改用 bench1_rerun_1102(2026-11-02)",
        "★★★为什么要这一份": {
            "跑批脚本里老池读的是": os.path.relpath(STALE, ROOT),
            "为什么不能用": "它跑在退化 R 修复(95e293b,10-31 14:25)之前,"
                            "口径戳提交号 fbf760f(10-31 11:30),"
                            "★ 其中 35 条的基准一是坏数(技-10 三档 −31 亿/−53 亿/−60 亿)",
            "本份用的是": os.path.relpath(OLD, ROOT),
            "★作废的字段": ["exam_run_1102.json 的 逐链[*].老池_笔数",
                            "逐链[*].老池_每笔净R", "逐链[*].老池_基准一",
                            "逐链[*].★和老池的差", "逐链[*].★符号是否翻转",
                            "汇总.★符号翻转的", "汇总.符号翻转名单"],
            "★已落盘的逐链 JSON 没有改动": True,
        },
        "★★两边池子不一样大(报告必须写)": {
            "考卷": "1,026 只(名单 1,042,engine 既有规则剔 16 只有效 bar<60 根)",
            "老池": sorted({str(old[l].get("★跑在哪个池")) for l in old
                            if old[l].get("★跑在哪个池")}),
            "★所以": "「考卷 vs 老池」这一列里同时混着**样本外**和**池子变大**两件事,"
                      "★★★ 分不开 —— 不许把差额全算到「样本外」头上。",
        },
        "汇总": {
            "考卷_链数": len(rows),
            "考卷_算出基准一的": len(ok),
            "考卷_前提破裂的": len(broke),
            "考卷_跑不了的": len(crash),
            "考卷_笔数<30的": len(thin),
            "考卷_对照偏差超±5%的": len(tol_over),
            # ★★★ 退化 R —— 四个数,真链和对照组分开(策略组 2026-11-02 要求)
            "★★★考卷_真链有退化笔的链数": degen_exam["★★★真链_有退化笔的链数"],
            "★★★考卷_真链退化笔总数": degen_exam["★★★真链_退化笔总数"],
            "★★★考卷_对照组有退化笔的链数": degen_exam["★★★对照组_有退化笔的链数"],
            "★★★考卷_对照组退化笔总数": degen_exam["★★★对照组_退化笔总数"],
            "★★★老池_真链有退化笔的链数": degen_old["★★★真链_有退化笔的链数"],
            "★★★老池_真链退化笔总数": degen_old["★★★真链_退化笔总数"],
            "★★★老池_对照组有退化笔的链数": degen_old["★★★对照组_有退化笔的链数"],
            "★★★老池_对照组退化笔总数": degen_old["★★★对照组_退化笔总数"],
            # ★★★ 无止损
            "★★★考卷_无止损的链数": len(nostop),
            "★★★老池_无止损的链数": len(nostop_old),
            "考卷_赢随机": len(exam_pos),
            "考卷_输随机": len(ok) - len(exam_pos),
            "老池_赢随机": len(old_pos),
            "老池_输随机": len(old) - len(old_pos),
            "★能并列对比的链数": len(pairs),
            "★★★符号翻转的": len(flips),
            "符号翻转名单": [f["链"] for f in flips],
            "老池那边没有可比数的": missing_old,
        },
        "★★★退化R_考卷(真链和对照组分开)": degen_exam,
        "★★★退化R_老池(真链和对照组分开)": degen_old,
        "★★★退化R_两边并列一句话": (
            "★ 退化 R 在**考卷的真链**上"
            f"{'没有再出现' if degen_exam['★★★真链_有退化笔的链数'] == 0 else '又出现了'}"
            f"({degen_exam['★★★真链_有退化笔的链数']} 条链 / "
            f"{degen_exam['★★★真链_退化笔总数']} 笔,"
            f"扫了 {degen_exam['★扫了多少条真链流水']} 条真链流水);"
            f"★★ 在**老池的真链**上有 {degen_old['★★★真链_有退化笔的链数']} 条链 / "
            f"{degen_old['★★★真链_退化笔总数']} 笔。"
            "★★★ 两边都是实测,**不要合成一句话** —— 这两个池子在这件事上行为不同。"),
        "★★★无止损的链(R 是收益率不是风险倍数)": {
            "为什么要单列": "★ 无止损 → 1R = 进场价 → R 退化成收益率。"
                            "★★★ 任何「考卷上哪条最好」的排名里,"
                            "这几条**必须单独一组**,不可和有止损的链同列排序。",
            "考卷_条数": len(nostop),
            "考卷_名单": [{"链": r["链"], "怎么判的": r.get("★无止损_怎么判的")}
                          for r in nostop],
            "老池_条数": len(nostop_old),
            "老池_名单": [{"链": r["链"], "怎么判的": r.get("★无止损_怎么判的")}
                          for r in nostop_old],
        },
        "★★两条口径(手册 v3.1 坑表 41/42,报告里不许写错)": {
            "绩效窗口": "★★★ **2018-01-01 ~ 2025-12-31 = 8 年**(engine/data.py:42-44)。"
                        "★ 日历起点 2014(12 年)、热机起点 2016 是另外两个数。"
                        "★★★ 报告里**不许用「十年」描述成绩** —— 成绩只有 8 年。",
            "regime开关": "★ 45 条链只有 4 套 (universe, regime) 规格,其中 3 套"
                          "等于没有开关:技-1 那套 **40 条链**、技-12 套 3 条、"
                          "buy_and_hold 1 条,regime 全期 **100% 开着**。"
                          "★★ 唯一有真开关的是 trend_following(76.9%,2022 年只有 19%)。"
                          "★★★ 所以「这些策略熊市会不会被挡住」的答案是"
                          "**不会 —— 40 条里一条开关都没装**。"
                          "★ 这一条是策略组实测,不是我测的。",
        },
        "逐链并列": sorted(pairs, key=lambda x: x["链"]),
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    try:
        s = out["汇总"]
        print("写到", OUT)
        print(f"可并列 {s['★能并列对比的链数']} 条 · 翻转 {s['★★★符号翻转的']} 条 · "
              f"考卷赢随机 {s['考卷_赢随机']}/{s['考卷_算出基准一的']} · "
              f"老池赢随机 {s['老池_赢随机']}/45")
        print(f"★ 退化R 考卷:真链 {s['★★★考卷_真链有退化笔的链数']} 条/"
              f"{s['★★★考卷_真链退化笔总数']} 笔 · "
              f"对照组 {s['★★★考卷_对照组有退化笔的链数']} 条/"
              f"{s['★★★考卷_对照组退化笔总数']} 笔")
        print(f"★ 退化R 老池:真链 {s['★★★老池_真链有退化笔的链数']} 条/"
              f"{s['★★★老池_真链退化笔总数']} 笔 · "
              f"对照组 {s['★★★老池_对照组有退化笔的链数']} 条/"
              f"{s['★★★老池_对照组退化笔总数']} 笔")
        print(f"★ 无止损 考卷 {s['★★★考卷_无止损的链数']} 条 · "
              f"老池 {s['★★★老池_无止损的链数']} 条")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
