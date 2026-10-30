#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★ 把 gates_1030.json 变成报告里的 markdown 表 —— 2026-10-30

★ 只做排版,不算任何新数;所有数来自 gates_1030.json。
★★ 有止损 / 无止损**分两张表**(无止损的 1R = 进场价,R 退化成收益率,
   不能和有止损的放一列排序 —— 纪律项)。

跑法:python3 probe/gates_rebuild_1030/make_tables_1030.py > tables.md
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "gates_1030.json")


def f(x, nd=4, sign=True):
    if x is None:
        return "—"
    if isinstance(x, bool):
        return "是" if x else "否"
    try:
        v = float(x)
    except (TypeError, ValueError):
        return str(x)
    return f"{v:+.{nd}f}" if sign else f"{v:.{nd}f}"


def pct(x, nd=2):
    return "—" if x is None else f"{float(x)*100:+.{nd}f}%"


def short(label: str, n: int = 46) -> str:
    s = label.replace("|", "/")
    return s if len(s) <= n else s[:n - 1] + "…"


def main() -> int:
    d = json.load(open(SRC, encoding="utf-8"))
    rows = d["逐链"]
    s = d["汇总"]

    has_stop = [r for r in rows
                if not r["★R是收益率(无止损,不许和有止损同列排序)"]]
    no_stop = [r for r in rows
               if r["★R是收益率(无止损,不许和有止损同列排序)"]]

    print("### 表 A1 · 基准一:新值 vs 旧值(★ 有止损的链,可同列排序)\n")
    print("| 链 | 笔数 | 基准一·旧(5 种子/±8%) | 基准一·新(50 种子/±5%) | "
          "差(新−旧) | 符号翻了 | 对照笔数偏差·旧 | 对照笔数偏差·新 |")
    print("|---|---:|---:|---:|---:|:--:|---:|---:|")
    for r in sorted(has_stop, key=lambda x: -(abs(x.get("基准一_差(新−旧)") or 0))):
        print(f"| {short(r['链'])} | {r['笔数']} | {f(r['基准一_旧'])} | "
              f"{f(r['基准一_新'])} | {f(r.get('基准一_差(新−旧)'))} | "
              f"{'★是' if r.get('★基准一符号翻了') else '否'} | "
              f"{pct(r['对照笔数偏差_旧'])} | {pct(r['对照笔数偏差_新'])} |")

    if no_stop:
        print("\n### 表 A2 · 基准一:★ 无止损的链 —— 1R = 进场价,"
              "R 退化成收益率,**单列报,不与上表排序**\n")
        print("| 链 | 笔数 | 基准一·旧 | 基准一·新 | 差(新−旧) | 符号翻了 |")
        print("|---|---:|---:|---:|---:|:--:|")
        for r in no_stop:
            print(f"| {short(r['链'])} | {r['笔数']} | {f(r['基准一_旧'])} | "
                  f"{f(r['基准一_新'])} | {f(r.get('基准一_差(新−旧)'))} | "
                  f"{'★是' if r.get('★基准一符号翻了') else '否'} |")

    print("\n### 表 B · 第二件:三档 Z 门并列(★ Z 取「条件分层随机」与"
          "「块重排」里更小的那个)\n")
    print("| 链 | 笔数 | Z·条件分层随机 | Z·块重排 | ★Z(取小) | "
          "对照偏差≤±5% | ≥1.65 | ≥1.96 | ≥2.5 | ≥3.0 |")
    print("|---|---:|---:|---:|---:|:--:|:--:|:--:|:--:|:--:|")
    for r in sorted(rows, key=lambda x: -(x.get("★Z_取两关里小的那个") or -99)):
        m = lambda k: "★过" if r.get(k) else "—"      # noqa: E731
        print(f"| {short(r['链'])} | {r['笔数']} | {f(r.get('Z_条件分层随机'),3)} | "
              f"{f(r.get('Z_块重排'),3)} | {f(r.get('★Z_取两关里小的那个'),3)} | "
              f"{'是' if r.get('对照组偏差≤±5%') else '★否'} | "
              f"{m('过Z≥1.65门')} | {m('过Z≥1.96门')} | {m('过Z≥2.5门')} | "
              f"{m('过Z≥3.0门')} |")

    print("\n### 表 C · 第三件:新门(双向聚类面板回归 t)vs 旧门(四格符号一致)\n")
    print("| 链 | 笔数 | 旧门·四格符号 | 旧门·过没过 | ★新门·cluster-robust t | "
          "新门 t>2.0 | 不聚类 t(只为看虚高) | t·只用真链常数项(无FE) | 面板行数 |")
    print("|---|---:|:--:|:--:|---:|:--:|---:|---:|---:|")
    for r in sorted(rows, key=lambda x: -(x.get("★面板t") or -99)):
        od = r.get("旧门_四格符号") or ("★没跑过" if r["旧门状态"] != "跑过" else "—")
        op = ("★过" if r.get("旧门_通过") else
              ("没过" if r["旧门状态"] == "跑过" else "★没跑过"))
        print(f"| {short(r['链'])} | {r['笔数']} | {od} | {op} | "
              f"{f(r.get('★面板t'),3)} | "
              f"{'★过' if r.get('★过新门 t>2.0') else '—'} | "
              f"{f(r.get('面板t_不聚类t(只为看虚高多少)'),3)} | "
              f"{f(r.get('t_只用真链_常数项_双向聚类(无固定效应)'),3)} | "
              f"{r.get('面板t_行数') or '—'} |")

    print("\n### 表 D · 汇总\n```")
    print(json.dumps(s, ensure_ascii=False, indent=1))
    print("```")
    return 0


if __name__ == "__main__":
    sys.exit(main())
