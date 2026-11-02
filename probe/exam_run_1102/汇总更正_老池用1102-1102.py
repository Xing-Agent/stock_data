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
"""
from __future__ import annotations

import json
import os
import sys

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


def main() -> int:
    rows = exam_rows()
    old_d = json.load(open(OLD, encoding="utf-8"))
    old = {r["链"]: r for r in old_d["逐链"]}

    ok = [r for r in rows if r.get("★新基准一值") is not None]
    broke = [r for r in rows if r.get("★前提破了_禁止下游")]
    crash = [r for r in rows if r.get("★跑不了")]
    thin = [r for r in rows if r.get("笔数") is not None and r["笔数"] < 30]
    degen = [r for r in rows if r.get("★退化R_本轮是否出现")]
    tol_over = [r for r in ok if r.get("★对照笔数偏差") is not None
                and abs(r["★对照笔数偏差"]) > 0.05]

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
            "考卷_退化R再出现的": len(degen),
            "考卷_对照偏差超±5%的": len(tol_over),
            "考卷_赢随机": len(exam_pos),
            "考卷_输随机": len(ok) - len(exam_pos),
            "老池_赢随机": len(old_pos),
            "老池_输随机": len(old) - len(old_pos),
            "★能并列对比的链数": len(pairs),
            "★★★符号翻转的": len(flips),
            "符号翻转名单": [f["链"] for f in flips],
            "老池那边没有可比数的": missing_old,
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
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
