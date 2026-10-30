#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★ 把 `regime_install_results_1030.json` 汇成报告要的几个数 + 两张 CSV。

三秒版:这个文件不算任何新东西,只做「汇总 + 分表」。
        ★★★ 唯一的硬规矩:**甲类和乙类分开统计**,
            不许合并成一个「装上条件之后活了几条」。

★ 两张 CSV 物理分开(纪律 6):有止损 / 无止损 —— R 的分母不同,混在一列排序本身就是错的。
"""
from __future__ import annotations

import csv
import json
import os
import statistics
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE, os.path.join(ROOT, "probe", "v2_rerun_1030")):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import pool_scope                                   # noqa: E402
import run_rerun_1030 as RR                                     # noqa: E402

IN_JSON = os.path.join(HERE, "regime_install_results_1030.json")
CSV_STOP = os.path.join(HERE, "按策略-装上条件-有止损-1030.csv")
CSV_NOSTOP = os.path.join(HERE, "按策略-装上条件-★无止损-R是收益率-1030.csv")
OUT_SUM = os.path.join(HERE, "汇总数-1030.json")

GRADE = {"甲": "甲", "乙": "乙", "丙": "丙"}


def grade_of(rec: dict) -> str:
    g = str(rec.get("条件出处等级") or "").strip()
    for k in GRADE:
        if g.startswith(k):
            return k
    return "未分类"


def main() -> int:
    d = json.load(open(IN_JSON, encoding="utf-8"))
    rows = d["逐链"]

    # ── 按策略去重(归一化变体名;★ 保留第一次出现,和上一轮同规则)
    seen, uniq = set(), []
    for r in rows:
        key = RR.norm_chain(r["链"].split("/", 1)[-1])
        if key in seen:
            continue
        seen.add(key)
        uniq.append(r)

    runnable = [r for r in uniq if "★跑不了" not in r]
    nostop = [r for r in runnable
              if (r["甲臂_不装条件"]["R可比性"].get("★无止损(退化成收益率)"))]
    withstop = [r for r in runnable if r not in nostop]

    # ── ① 三态分类
    by_grade: dict[str, list] = {"甲": [], "乙": [], "丙": [], "未分类": []}
    for r in runnable:
        by_grade[grade_of(r)].append(r)
    # ★ 按**方法**(技-N)也数一遍 —— 变体数会把同一条方法数好几遍
    meth: dict[str, str] = {}
    for r in runnable:
        if r.get("方法"):
            meth[r["方法"]] = grade_of(r)
    meth_grade: dict[str, list] = {"甲": [], "乙": [], "丙": [], "未分类": []}
    for m, g in sorted(meth.items()):
        meth_grade[g].append(m)

    installed = [r for r in runnable if r.get("乙臂_装了条件")]

    # ── ② 活了几条(★ 甲 / 乙 分开)
    def alive(r, key):
        ch = r.get("装上之后的变化") or {}
        return bool(ch.get(key))

    alive_strict = [r for r in installed
                    if alive(r, "★★★活了")]
    alive_r = [r for r in installed
               if alive(r, "★★R口径活了(原过闸但R≤0 → 过闸且R>0)")]
    better_r = [r for r in installed
                if (r.get("装上之后的变化") or {}).get("★R变好了吗") is True]
    worse_r = [r for r in installed
               if (r.get("装上之后的变化") or {}).get("★R变好了吗") is False]
    died = [r for r in installed
            if (r.get("甲臂_闸") or {}).get("★过三道硬闸")
            and not (r.get("乙臂_闸") or {}).get("★过三道硬闸")]

    def split(lst):
        return {g: [r["链"] for r in lst if grade_of(r) == g]
                for g in ("甲", "乙")}

    # ── ③ 条件成立时间占比的分布(★ 只统计市场级的,个股级口径不同不许混)
    shares = [(r["链"], r["条件成立占比"]["条件成立时间占比"])
              for r in installed
              if "条件成立时间占比" in (r.get("条件成立占比") or {})]
    sv = [s for _n, s in shares]
    share_stat = ({"条数": len(sv), "中位": round(statistics.median(sv), 4),
                   "最低": round(min(sv), 4), "最高": round(max(sv), 4)}
                  if sv else None)
    stock_shares = [(r["链"], r["条件成立占比"].get("留下比例"))
                    for r in installed
                    if "留下比例" in (r.get("条件成立占比") or {})]

    # ── ④ 技-10
    t10 = [r for r in runnable if r.get("方法") == "技-10"]

    summary = {
        "口径戳": d["口径戳"],
        "①三态分类": {
            "按方法(技-N)": {g: meth_grade[g] for g in ("甲", "乙", "丙")},
            "按变体条数": {g: len(by_grade[g]) for g in by_grade},
            "可重跑变体": len(rows), "按策略去重后": len(uniq),
            "其中有止损": len(withstop), "其中无止损": len(nostop),
            "★本轮实际装上条件的策略条数": len(installed),
        },
        "②活了几条": {
            "★口径一(严格:原来不过三道硬闸 → 装上后过了)": {
                "合计": len(alive_strict), **split(alive_strict)},
            "★口径二(R:原过闸且R≤0 → 过闸且R>0)": {
                "合计": len(alive_r), **split(alive_r)},
            "装上之后 R 变好的": {"合计": len(better_r), **split(better_r)},
            "装上之后 R 变差的": {"合计": len(worse_r), **split(worse_r)},
            "★装上之后反而掉出闸的": {"合计": len(died), **split(died)},
        },
        "③条件成立时间占比": {
            "市场级(交易日占比)": share_stat,
            "市场级逐条": shares,
            "★个股级口径不同,单独列(合格进场信号留下比例)": stock_shares,
        },
        "④技-10": [{
            "链": r["链"], "装的条件": r.get("装的条件"),
            "甲臂": {k: r["甲臂_不装条件"].get(k) for k in
                     ("笔数", "合格进场信号(entry&universe)", "每笔净R", "胜率")},
            "乙臂": ({k: r["乙臂_装了条件"].get(k) for k in
                      ("笔数", "合格进场信号(entry&universe)", "每笔净R", "胜率")}
                     if r.get("乙臂_装了条件") else None),
            "甲臂闸": r.get("甲臂_闸"), "乙臂闸": r.get("乙臂_闸"),
            "条件成立占比": (r.get("条件成立占比") or {}).get("条件成立时间占比"),
        } for r in t10],
        "条件向量_绩效窗口口径": d["条件向量_绩效窗口口径"],
        "条件向量_实跑回测索引口径": d["条件向量_实跑回测索引口径"],
    }
    json.dump(summary, open(OUT_SUM, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)

    # ── 两张 CSV
    stamp = pool_scope.stamp("large_mid", {"本表": "装上原著使用条件前后对照"})
    cols = ["链", "方法", "族", "条件出处等级", "装的条件", "装在哪一层",
            "条件成立时间占比",
            "不装_笔数", "不装_信号数", "不装_每笔净R", "不装_胜率", "不装_集中度",
            "不装_过三道硬闸",
            "装了_笔数", "装了_信号数", "装了_每笔净R", "装了_胜率", "装了_集中度",
            "装了_过三道硬闸",
            "Δ笔数", "Δ每笔净R", "★活了(严格)", "★R口径活了", "本轮没装的理由"]

    def write(path, lst, note):
        with open(path, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            for k, v in stamp.items():
                w.writerow([f"# {k}", v])
            w.writerow([f"# {note}"])
            w.writerow(cols)
            for r in lst:
                a = r["甲臂_不装条件"]
                b = r.get("乙臂_装了条件")
                ch = r.get("装上之后的变化") or {}
                cs = r.get("条件成立占比") or {}
                w.writerow([
                    r["链"], r.get("方法"), r.get("族"), r.get("条件出处等级"),
                    r.get("装的条件"), r.get("装在哪一层"),
                    cs.get("条件成立时间占比", cs.get("留下比例")),
                    a["笔数"], a["合格进场信号(entry&universe)"], a["每笔净R"],
                    a["胜率"], (r.get("甲臂_闸") or {}).get("集中度值"),
                    (r.get("甲臂_闸") or {}).get("★过三道硬闸"),
                    b["笔数"] if b else "",
                    b["合格进场信号(entry&universe)"] if b else "",
                    b["每笔净R"] if b else "", b["胜率"] if b else "",
                    (r.get("乙臂_闸") or {}).get("集中度值") if b else "",
                    (r.get("乙臂_闸") or {}).get("★过三道硬闸") if b else "",
                    ch.get("笔数", ("", "", ""))[2] if ch else "",
                    ch.get("每笔净R", ("", "", ""))[2] if ch else "",
                    ch.get("★★★活了") if ch else "",
                    ch.get("★★R口径活了(原过闸但R≤0 → 过闸且R>0)") if ch else "",
                    str(r.get("★本轮没装的理由") or "")[:300],
                ])

    write(CSV_STOP, withstop, f"有止损的策略 {len(withstop)} 条")
    write(CSV_NOSTOP, nostop,
          f"★★★ 无止损 {len(nostop)} 条 —— R 退化成收益率,"
          f"**不可和上一张并列排序**(R 的分母不同)")

    print(json.dumps(summary["①三态分类"], ensure_ascii=False, indent=1))
    print(json.dumps(summary["②活了几条"], ensure_ascii=False, indent=1))
    print(json.dumps(summary["③条件成立时间占比"]["市场级(交易日占比)"],
                     ensure_ascii=False, indent=1))
    print(json.dumps(summary["④技-10"], ensure_ascii=False, indent=1))
    print(f"\n→ {os.path.relpath(OUT_SUM, ROOT)}\n→ "
          f"{os.path.relpath(CSV_STOP, ROOT)}\n→ "
          f"{os.path.relpath(CSV_NOSTOP, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
