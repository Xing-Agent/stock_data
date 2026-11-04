#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 把跑批结果整理成《35》第五节要的固定格式 —— ★ 只读 parts/,不重跑

三秒版:把 54 个格子的结果,整理成「每条两版并排」的表 + 五条预言的判定。

★★ 两个纪律落在这个文件里:
  ① **「算不出来」和「分数差」分成两列** —— 可算率 / 入选票数 是两列,不混。
  ② **原著没给的数不报「最好的那一点」** —— 只报「三点是否同向」。
"""
from __future__ import annotations

import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

PART_DIR = os.path.join(HERE, "parts")
OUT = os.path.join(HERE, "table_expand_1104.json")

#: ★ 8 条 × 两版的编排(★★ 原著版 / 我们的版本 分列)
LAYOUT = [
    ("1", "Sloan 应计", "扩1-orig", "扩1-ours"),
    ("2", "资产扩张", "扩2-orig", "扩2-ours"),
    ("3", "LSV 逆向价值", ["扩3-orig-bm", "扩3-orig-cp", "扩3-orig-ep"], "扩3-ours"),
    ("4", "Net-Net", "扩4-orig", "扩4-ours"),
    ("5", "存货异常", "扩5-orig", "扩5-ours"),
    ("6", "毛利质量", "扩6-orig", "扩6-ours"),
    ("7", "股东回报", "扩7-orig", "扩7-ours"),
    ("8", "趋势模板 AND 盈利加速", "扩8-orig", "扩8-ours"),
]

#: ★★★ 「符号翻转」的判定口径 —— ★ 跑之前就写死这一句,免得事后挑定义:
SIGN_RULE = (
    "★★★ **符号翻转的判定口径(写死)**:文献对这 8 条的方向主张都是"
    "「照这个条件选股,能跑赢同环境下的瞎买」。"
    "★ 所以**翻转 = (本链每笔净R − 基准一随机进场每笔净R) < 0**,"
    "即**方向和文献相反**。"
    "★★ 只在**主格**上判(主格才跑基准一);"
    "★★★ 没跑成或笔数为 0 的格子判「测不到」,不判翻转。"
)


def load() -> dict:
    out = {}
    if not os.path.isdir(PART_DIR):
        return out
    for fn in sorted(os.listdir(PART_DIR)):
        if not fn.endswith(".json"):
            continue
        cell = fn[:-5].replace("__", "|")
        with open(os.path.join(PART_DIR, fn), encoding="utf-8") as fh:
            out[cell] = json.load(fh)
    return out


def main_cell(parts: dict, cid: str) -> dict | None:
    for cell, rec in parts.items():
        if rec.get("臂") == cid and rec.get("★是否主格"):
            return rec
    return None


def grid_cells(parts: dict, cid: str) -> list[dict]:
    return [r for r in parts.values() if r.get("臂") == cid]


def _bench(rec: dict) -> dict:
    b = rec.get("★基准一_同环境随机进场") or {}
    d = b.get("★真信号每笔R − 随机进场每笔R")
    return {
        "基准一_随机进场每笔R": b.get("随机进场_平均每笔R"),
        "★每笔R减随机进场": d,
        "★赢不赢随机": (None if d is None else ("赢" if d > 0 else "没赢")),
        "★对照笔数偏差": b.get("★对照笔数偏差"),
        "★对照笔数容差": b.get("★对照笔数容差"),
        "★单种子每笔R的极差": b.get("★单种子每笔R的极差"),
        "★★读法警示": "★ 如果「每笔R减随机进场」的绝对值 **小于** 单种子极差,"
                       "★★★ 那这个符号本身就是噪声,不许当成结论。",
    }


def summarise(parts: dict, cid: str) -> dict:
    rec = main_cell(parts, cid)
    if rec is None:
        return {"★状态": "没有这个格子"}
    if rec.get("★跑挂了"):
        return {"★状态": "★★★ 跑挂了", "错误": rec["★跑挂了"]}
    cov = rec.get("★可算率") or {}
    sel = rec.get("★入选票数") or {}
    g = grid_cells(parts, cid)
    # ★★★ 三点同向:只报同不同向,★ 不报最好的那一点
    slots_pts = sorted([(x["slots"], x.get("★每笔净R(=净收益率)"))
                        for x in g
                        if x.get("★自由参数档位") == rec.get("★自由参数档位")
                        and not x.get("★跑挂了")])
    vals = [v for _, v in slots_pts if v is not None]
    same = (None if len(vals) < 2 else
            ("三点同向(全正)" if all(v > 0 for v in vals) else
             "三点同向(全负)" if all(v < 0 for v in vals) else "★ 不同向"))
    rank_pts = sorted([(x["★自由参数档位"], x.get("★每笔净R(=净收益率)"))
                       for x in g
                       if x["slots"] == rec["slots"] and not x.get("★跑挂了")
                       and x.get("★自由参数档位") is not None])
    rvals = [v for _, v in rank_pts if v is not None]
    rsame = (None if len(rvals) < 2 else
             ("三点同向(全正)" if all(v > 0 for v in rvals) else
              "三点同向(全负)" if all(v < 0 for v in rvals) else "★ 不同向"))
    return {
        "★状态": "跑成了",
        "归属": rec.get("归属"),
        "★可算率_窗口内日频": cov.get("★窗口内日频可算率(口径内格子)"),
        "★日均算得出的只数": cov.get("★日均算得出的只数"),
        "★算不出来的格子": cov.get("★算不出来的格子"),
        "★其中净流动资产≤0(不合格,不是算不出来)":
            cov.get("★其中净流动资产≤0(= 不合格,不是算不出来)"),
        "★入选票数_日均": sel.get("日均入选只数"),
        "★一只都没有的交易日占比": sel.get("★一只都没有的交易日占比"),
        "笔数": rec.get("笔数"),
        "★每笔净R": rec.get("★每笔净R(=净收益率)"),
        "胜率": rec.get("胜率"),
        "平均持有交易日": rec.get("平均持有交易日"),
        "基准一": _bench(rec),
        "★槽位三点(15/30/45)是否同向": {"逐点": slots_pts, "判定": same},
        "★档位三点是否同向": ({"逐点": rank_pts, "判定": rsame}
                              if rank_pts else "★ 这一条没有档位自由参数"),
    }


def main() -> int:
    parts = load()
    res_path = os.path.join(HERE, "run_expand_results_1104.json")
    not_run = {}
    if os.path.exists(res_path):
        with open(res_path, encoding="utf-8") as fh:
            not_run = (json.load(fh)).get("★★★不跑/算不出来的格子") or {}

    rows = []
    for num, name, orig, ours in LAYOUT:
        origs = orig if isinstance(orig, list) else [orig]
        row = {"#": num, "策略": name, "原著版": {}, "我们的版本": {}}
        for o in origs:
            row["原著版"][o] = (not_run.get(o) if o in not_run
                                else summarise(parts, o))
        row["我们的版本"][ours] = (not_run.get(ours) if ours in not_run
                                   else summarise(parts, ours))
        rows.append(row)

    # ---------------- ④ 符号翻转逐条点名
    flips, nonflips, untestable = [], [], []
    for cell, rec in parts.items():
        if not rec.get("★是否主格") or rec.get("★跑挂了"):
            continue
        d = ((rec.get("★基准一_同环境随机进场") or {})
             .get("★真信号每笔R − 随机进场每笔R"))
        rng = ((rec.get("★基准一_同环境随机进场") or {})
               .get("★单种子每笔R的极差"))
        if d is None or not rec.get("笔数"):
            untestable.append({"臂": rec["臂"], "笔数": rec.get("笔数"),
                               "原因": "没跑出基准一 / 笔数为 0"})
            continue
        item = {"臂": rec["臂"], "每笔R减随机进场": d,
                "单种子极差": rng,
                "★这个符号是否小于噪声":
                    (None if rng is None else bool(abs(d) < abs(rng)))}
        (flips if d < 0 else nonflips).append(item)

    # ---------------- ★ 「我们的版本」赢了几条(预言四)
    ours_win = []
    for num, name, orig, ours in LAYOUT:
        origs = orig if isinstance(orig, list) else [orig]
        o_recs = [main_cell(parts, o) for o in origs]
        o_recs = [r for r in o_recs if r and not r.get("★跑挓了")
                  and not r.get("★跑挂了")]
        u = main_cell(parts, ours)
        if not o_recs or u is None or u.get("★跑挂了"):
            ours_win.append({"#": num, "策略": name, "判定": "测不到",
                             "原因": "原著版没跑(或跑挂)→ 没有可比的对照"})
            continue
        ov = [r.get("★每笔净R(=净收益率)") for r in o_recs]
        ov = [x for x in ov if x is not None]
        uv = u.get("★每笔净R(=净收益率)")
        if not ov or uv is None:
            ours_win.append({"#": num, "策略": name, "判定": "测不到",
                             "原因": "某一版笔数为 0,每笔R 没有定义"})
            continue
        best_o = max(ov)
        ours_win.append({
            "#": num, "策略": name,
            "原著版每笔R": ov, "我们的版本每笔R": uv,
            "判定": ("我们的赢" if uv > best_o else "原著赢或打平"),
            "★★读法": "★ 两版票数差很大时,这个比较主要在比「票多票少」,"
                       "★★ 不是在比「谁的方法好」—— 见各行入选票数那一列。",
        })

    out = {
        "★口径": {
            "窗口": "2018-01-01 .. 2020-12-31(研发池)",
            "★R口径": "★★★ 这 8 条**全部无止损** → 1R = 进场价 → "
                       "**R 退化成收益率**,★ 不能和有止损的链放同一列比。",
            "★★可算率 vs 入选票数": "★★★ 两件事,分两列:"
                                     "**可算率** = 这个分数算不算得出来;"
                                     "**入选票数** = 算得出来的里面有几只入选。"
                                     "★ 「算不出来」绝不记成「分数差」。",
            "★符号翻转口径": SIGN_RULE,
            "★分位的分母": "★★ 十分位/五分位是在**有基本面数据的 250 只**上排的,"
                            "★ 大+中池口径在排名**之后**才与上去(和 1030 那一轮一致)"
                            "—— ★★★ 所以「十分位」不等于「大中池里的十分位」。",
        },
        "①每条两版并排": rows,
        "④符号翻转逐条点名": {
            "★翻转的(方向和文献相反)": flips,
            "没翻转的": nonflips,
            "测不到的": untestable,
            "★翻转条数": len(flips),
        },
        "★预言四用的对照": ours_win,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
    print(f"★ 写了 {OUT}")
    print(f"★ 翻转 {len(flips)} 条;没翻转 {len(nonflips)} 条;"
          f"测不到 {len(untestable)} 条")
    for r in rows:
        for side in ("原著版", "我们的版本"):
            for cid, v in r[side].items():
                if isinstance(v, dict) and v.get("★状态") == "跑成了":
                    print(f"  {cid:14s} 可算率={v['★可算率_窗口内日频']} "
                          f"日均入选={v['★入选票数_日均']} 笔数={v['笔数']} "
                          f"每笔R={v['★每笔净R']} "
                          f"{v['基准一']['★赢不赢随机']}")
                elif isinstance(v, dict):
                    print(f"  {cid:14s} {v.get('★状态') or v.get('判定')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
