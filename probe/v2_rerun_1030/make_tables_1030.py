#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把三份 json 合成说明书用的两张表 —— 2026-10-30。

★★ 两张表**分开**,不许合成一张:
   ① 有止损的链 —— 每笔 R 是「赚了几倍的风险金额」,可以互相排序
   ② ★★★ 无止损的链 —— 1R = 进场价,R 退化成**普通收益率**。
      ★ 把它和有止损的链写在同一列里排序,**排序本身就是错的**。
      ★★ 今天第二次因为「两个单位混在一列」出错,所以这里结构化地防住。
"""
from __future__ import annotations

import csv
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
from engine import pool_scope  # noqa: E402

RR = json.load(open(os.path.join(HERE, "rerun_results_1030.json"), encoding="utf-8"))
BB = {x["链"]: x for x in json.load(
    open(os.path.join(HERE, "bench_two_1030.json"), encoding="utf-8"))["逐链"]}
CC = {x["链"]: x for x in json.load(
    open(os.path.join(HERE, "condition_window_1030.json"), encoding="utf-8"))["逐链"]}

ORDER = {"A0十二条": 1, "技术派六条三版": 2, "批五修正": 3, "原著离场": 4, "剔污染": 5}


def norm(s: str) -> str:
    s = str(s)
    for a, b in (("（", "("), ("）", ")"), ("≥", ">="), ("×", "x")):
        s = s.replace(a, b)
    for ch in " \t　·_/★【】":
        s = s.replace(ch, "")
    return s.replace("Test", "")


def gates(r):
    a = r["大中_重跑"]
    c = a["集中度"]
    sh = c.get("集中度_前10笔占总盈利")
    return {
        "笔数>=30": a["笔数"] >= 30,
        "三槽位齐(进场/离场/止损)": r["四槽位"]["三槽位齐全_不含加仓"],
        "止损两级都齐": r["四槽位"]["止损两级都齐"],
        "集中度": ((not c.get("★退化")) and (not c.get("★半退化"))
                   and sh is not None and sh <= 0.50),
        "R可比(有止损)": a["R可比性"].get("可比", False),
    }


def main() -> int:
    rows = [r for r in RR["逐链"] if "★跑不了" not in r]
    # ★ 按策略去重:同一个归一化变体名在多个批次各有一份 → 保留批次最晚的那个
    #   (批次越晚 = 修过的坑越多;实测 5 组重复的数字完全一致,所以保留哪个不影响数)
    grp: dict[str, list] = {}
    for r in rows:
        batch, label = r["链"].split("/", 1)
        grp.setdefault(norm(label), []).append((ORDER[batch], r))
    ded = [sorted(v, key=lambda x: -x[0])[0][1] for v in grp.values()]

    stamp = pool_scope.stamp("large_mid", {
        "本表做法": "★ 真重跑(从信号层,名额在只有大+中票的世界里重新分配)",
        "去重": f"{len(rows)} 个变体 → {len(ded)} 个不同策略(同名多版本保留批次最晚的)",
        "R 的单位警告": "★★★ 无止损的链另表 —— 1R=进场价,R 退化成收益率,不可并列排序",
    })

    for tag, want_nostop in (("有止损", False), ("★无止损-R是收益率", True)):
        out = os.path.join(HERE, f"按链-真重跑-{tag}-1030.csv")
        with open(out, "w", newline="", encoding="utf-8") as fh:
            w = csv.writer(fh)
            for k, v in stamp.items():
                w.writerow([f"# {k}", v])
            w.writerow([f"# 本表口径", f"{tag}的链"])
            w.writerow([])
            w.writerow([
                "链", "族", "配置",
                "②环境条件成立的交易日占比", "②股票条件成立的票交易日占比",
                "②两个条件都成立的票交易日占比", "②平均每交易日可买只数",
                "③信号数(entry&universe,大中)", "③笔数(大中重跑)",
                "③每笔净R" + ("(★实为收益率)" if want_nostop else ""),
                "③胜率", "③盈利笔数", "③集中度前10笔占总盈利", "③集中度读法",
                "③净盈亏", "③占用资金年化", "③最大回撤", "③最长水下(交易日)",
                "③平均净敞口Ebar",
                "⑤基准一差值(真信号每笔R−随机进场每笔R)",
                "⑤基准二超额(链−同等仓位大盘)", "⑤基准二成分指数",
                "闸_笔数>=30", "闸_三槽位齐", "闸_止损两级齐", "闸_集中度",
                "过三道硬闸", "重跑减重切_笔数差", "重跑减重切_每笔R差", "符号翻转",
                "池子口径",
            ])
            for r in sorted(ded, key=lambda x: -(x["大中_重跑"]["每笔净R"] or -9)):
                a = r["大中_重跑"]
                rv = a["R可比性"]
                nostop = bool(rv.get("★无止损(退化成收益率)"))
                if nostop != want_nostop:
                    continue
                g = gates(r)
                c = a["集中度"]
                b = BB.get(r["链"], {})
                b1 = (b.get("★基准一_同环境随机进场") or {})
                b2 = (b.get("★基准二_同等仓位大盘") or {})
                cw = CC.get(r["链"], {})
                w.writerow([
                    r["链"], r["族"], r["配置"],
                    cw.get("②市场环境条件成立的交易日占比"),
                    cw.get("②股票条件成立的票·交易日占比"),
                    cw.get("②两个条件都成立的票·交易日占比"),
                    cw.get("②平均每个交易日有多少只票可买"),
                    a["合格进场信号(entry&universe)"], a["笔数"],
                    a["每笔净R"], a["胜率"], c.get("盈利笔数"),
                    c.get("集中度_前10笔占总盈利"),
                    ("退化" if c.get("★退化") else
                     "半退化" if c.get("★半退化") else "可读"),
                    a["净盈亏"], a["占用资金年化"], a["最大回撤"],
                    a["最长水下(交易日)"], a["平均净敞口Ebar"],
                    b1.get("★真信号每笔R − 随机进场每笔R"),
                    b2.get("★超额收益(链 − 同等仓位大盘)"),
                    b2.get("成分匹配指数"),
                    g["笔数>=30"], g["三槽位齐(进场/离场/止损)"],
                    g["止损两级都齐"], g["集中度"],
                    g["笔数>=30"] and g["三槽位齐(进场/离场/止损)"] and g["集中度"],
                    r["重跑减重切"]["笔数差"], r["重跑减重切"]["每笔净R差"],
                    r["重跑减重切"]["符号翻转"],
                    "large_mid = 大盘+中盘(成交额排名 1–2000)",
                ])
        n = sum(1 for r in ded
                if bool(r["大中_重跑"]["R可比性"].get("★无止损(退化成收益率)")) == want_nostop)
        print(f"→ {os.path.relpath(out, ROOT)}  ({n} 条)")
    print(f"\n★ 去重:{len(rows)} 变体 → {len(ded)} 个不同策略")
    return 0


if __name__ == "__main__":
    sys.exit(main())
