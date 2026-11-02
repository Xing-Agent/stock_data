#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 出「修复前 vs 修复后」逐条对照表 —— 2026-11-02

三秒版:左边是 1031 那一轮(退化 R **修复前**)的数,右边是本轮(**修复后**)的数,
        一条链一行,★ 差多少写多少。

数据来源(三份,都是实测文件,不是转述):
  ① probe/bench1_rerun_1031/bench1_rerun_1031.json   —— 修复前的 45 条
  ② probe/bench1_rerun_1102/bench1_rerun_1102.json   —— 本轮(修复后)
  ③ probe/bench1_rerun_1031/degenerate_r_1031.json   —— ★ 修复前流水上**重算**的
     退化 R 笔数(判据 risk/entry < 1e-4,和 engine 里现在那条**同一个判据**)。
     ★★ 为什么要用这一份:修复前的流水里**没有** `r_degenerate` 这一列
        (那一列是修复时才加的),★★★ 所以「修复前有几笔退化」只能这样重算,
        不能从 1031 的流水里直接读。

跑法:python3 probe/bench1_rerun_1102/make_tables_1102.py
"""
from __future__ import annotations

import hashlib
import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
B1031 = os.path.join(ROOT, "probe", "bench1_rerun_1031")

NEW = os.path.join(HERE, "bench1_rerun_1102.json")
#: ★★★ 本轮流水上**实测**的退化 R(★ 不能读 r_degenerate 列 —— 那一列
#   被 engine 的 LEDGER_COLUMNS 静默丢掉了,详见 degen_check_1102.py 的说明)
DEGEN_NEW = os.path.join(HERE, "退化R实测-1102.json")
OLD = os.path.join(B1031, "bench1_rerun_1031.json")
DEGEN = os.path.join(B1031, "degenerate_r_1031.json")
LEDGERS = os.path.join(HERE, "ledgers_1102")

OUT_MD = os.path.join(HERE, "表-逐链-修复前后-1102.md")
OUT_JSON = os.path.join(HERE, "对照-修复前后-1102.json")
MANIFEST = os.path.join(HERE, "ledgers_manifest_1102.json")


def f(v, n=4):
    """★ 有值就印值,没值印破折号 —— ★★ 1031 踩过「有值印成破折号」的 bug。"""
    if v is None:
        return "—"
    if isinstance(v, bool):
        return "是" if v else "否"
    if isinstance(v, (int,)):
        return str(v)
    try:
        x = float(v)
    except (TypeError, ValueError):
        return str(v)
    if x != x:
        return "NaN"
    if abs(x) >= 1e6:
        return f"{x:.4g}"
    return f"{x:.{n}f}"


def main() -> int:
    new = json.load(open(NEW, encoding="utf-8"))
    old = json.load(open(OLD, encoding="utf-8"))
    dg = json.load(open(DEGEN, encoding="utf-8"))
    dn = json.load(open(DEGEN_NEW, encoding="utf-8"))

    def safe_name(label: str) -> str:
        """★ 和 run_bench1_1102.safe_name 一字不差 —— 流水文件名就是这么拼的。"""
        return label.replace("/", "_").replace(" ", "")

    dn_real = dn["逐份_真链"]
    dn_ctrl = dn["逐份_对照组"]

    nmap = {r["链"]: r for r in new["逐链"]}
    omap = {r["链"]: r for r in old["逐链"]}
    dmap = {r["链"]: r for r in dg["逐链"]}
    bad_before = set(dg["★基准一不可用的链"])

    rows = []
    for label in sorted(nmap, key=lambda s: (s.split("/")[0], s)):
        n = nmap[label]
        o = omap.get(label, {})
        d = dmap.get(label, {})
        nb, ob = n.get("★新基准一值"), o.get("★新基准一值")
        # ★★★ 修复后的退化 R 笔数 = 在**本轮流水**上按同一个判据实测出来的
        #   (★ 不是读 r_degenerate 列 —— 那一列落盘时被 engine 丢掉了)
        sn = safe_name(label)
        real_new = (dn_real.get(sn) or {}).get("退化笔数_判据")
        ctrl_new = (dn_ctrl.get(sn) or {}).get("退化笔数_判据")
        real_old = (d.get("真链流水") or {}).get("退化笔数")
        ctrl_old = (d.get("对照流水") or {}).get("退化笔数")
        rows.append({
            "链": label,
            "族": n.get("族"),
            "修复前_笔数": o.get("笔数"),
            "修复后_笔数": n.get("笔数"),
            "笔数差": (None if o.get("笔数") is None
                       else n["笔数"] - o["笔数"]),
            "修复前_每笔净R": o.get("每笔净R"),
            "修复后_每笔净R": n.get("每笔净R"),
            "每笔净R差": (None if (o.get("每笔净R") is None
                                   or n.get("每笔净R") is None)
                          else n["每笔净R"] - o["每笔净R"]),
            "修复前_基准一": ob,
            "修复后_基准一": nb,
            "基准一差": (None if (nb is None or ob is None) else nb - ob),
            "★修复前基准一是不是坏数": label in bad_before,
            "★修复后基准一还坏不坏": None,     # 下面填
            "修复前_对照笔数偏差": o.get("★对照笔数偏差"),
            "修复后_对照笔数偏差": n.get("★对照笔数偏差"),
            "★修复前退化R_真链笔数(旧流水重算)": real_old,
            "★修复后退化R_真链笔数(r_degenerate)": real_new,
            "★修复前退化R_对照笔数(旧流水重算)": ctrl_old,
            "★修复后退化R_对照笔数(r_degenerate)": ctrl_new,
            "★符号是否翻转": (None if (nb is None or ob is None)
                              else bool((nb > 0) != (ob > 0))),
            "无止损(R退化成收益率)": n.get(
                "★无止损_R退化成收益率_不可和有止损同列排序"),
        })

    # ★★★ 「修复后还坏不坏」的判据(★ XING 自己定的,写明白):
    #   ① 真链或对照组仍有 r_degenerate 笔  → 还是有退化笔(但已被剔出 R 均值)
    #   ② |基准一| > 10                      → 数值仍然爆掉,不能用
    #   ★ 判据 ② 照抄 1031 那一份 degenerate_r_1031.json 的「爆掉」门槛。
    for r in rows:
        nb = r["修复后_基准一"]
        blew = (nb is not None and abs(nb) > 10)
        still = (bool(r["★修复后退化R_对照笔数(r_degenerate)"] or 0)
                 or bool(r["★修复后退化R_真链笔数(r_degenerate)"] or 0))
        r["★修复后基准一还坏不坏"] = {
            "数值是否仍爆掉(|值|>10)": blew,
            "仍有退化笔(已被剔出均值)": still,
            "★结论": ("★★★ 还是不能用(数值爆掉)" if blew
                       else ("★ 可用 —— 仍有退化笔,但已被剔出 R 均值" if still
                             else "★ 可用 —— 一笔退化都没有"))
        }

    bad_after = [r["链"] for r in rows
                 if r["★修复后基准一还坏不坏"]["数值是否仍爆掉(|值|>10)"]]
    flips = [r["链"] for r in rows if r["★符号是否翻转"]]
    real_hit = {r["链"]: r["★修复后退化R_真链笔数(r_degenerate)"] for r in rows
                if r["★修复后退化R_真链笔数(r_degenerate)"]}
    ctrl_hit = {r["链"]: r["★修复后退化R_对照笔数(r_degenerate)"] for r in rows
                if r["★修复后退化R_对照笔数(r_degenerate)"]}
    real_hit_old = {r["链"]: r["★修复前退化R_真链笔数(旧流水重算)"] for r in rows
                    if r["★修复前退化R_真链笔数(旧流水重算)"]}
    unchanged = [r["链"] for r in rows
                 if r["基准一差"] is not None and r["基准一差"] == 0.0]

    summary = {
        "链数": len(rows),
        "★修复前基准一是坏数的": sum(1 for r in rows
                                     if r["★修复前基准一是不是坏数"]),
        "★修复后数值仍爆掉(|值|>10)的": len(bad_after),
        "★修复后仍爆掉的名单": bad_after,
        "★符号翻转的条数": len(flips),
        "★符号翻转名单": flips,
        "★基准一一字未动(差 == 0)的条数": len(unchanged),
        "★★★真链退化R_修复后实测_有几条链": len(real_hit),
        "★★★真链退化R_修复后实测_总笔数": sum(real_hit.values()),
        "★★★真链退化R_修复后实测_名单": real_hit,
        "★真链退化R_修复前(旧流水重算)_有几条链": len(real_hit_old),
        "★真链退化R_修复前(旧流水重算)_总笔数": sum(real_hit_old.values()),
        "★真链退化R_修复前(旧流水重算)_名单": real_hit_old,
        "★对照组退化R_修复后实测_有几条链": len(ctrl_hit),
        "★对照组退化R_修复后实测_总笔数": sum(ctrl_hit.values()),
        "★对照笔数偏差_最大绝对值": max(
            abs(r["修复后_对照笔数偏差"]) for r in rows
            if r["修复后_对照笔数偏差"] is not None),
    }

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump({"汇总": summary, "逐链": rows}, fh,
                  ensure_ascii=False, indent=1, default=str)

    # ------------------------------------------------------------------ md
    L = ["# 表 · 老池 45 条链「退化 R 修复前 vs 修复后」逐条对照（2026-11-02）",
         "",
         "**三秒版**：同一套 45 条链、同一个研发池（198 只）、同一组 50 个写死种子，",
         "只换了一件事 —— engine 里的退化 R 修复（commit `95e293b`）。",
         "左边是修复前（1031 11:22 跑的），右边是修复后（本轮）。",
         "",
         f"- 修复前基准一是坏数的：**{summary['★修复前基准一是坏数的']} 条**",
         f"- 修复后数值仍爆掉（|值|>10）的：**{summary['★修复后数值仍爆掉(|值|>10)的']} 条**",
         f"- 符号翻转的：**{summary['★符号翻转的条数']} 条**",
         f"- 基准一一个字都没变（差 == 0）的：**{summary['★基准一一字未动(差 == 0)的条数']} 条**",
         f"- ★★★ 真链那边的退化 R（本轮实测）：**{summary['★★★真链退化R_修复后实测_有几条链']} 条链 / "
         f"{summary['★★★真链退化R_修复后实测_总笔数']} 笔**",
         "",
         "## 表一 · 逐条对照",
         "",
         "| 链 | 坏? | 笔数 前→后 | 每笔净R 前→后 | 基准一 前 | 基准一 后 | 基准一差 | 翻转 | 对照偏差 后 | 退化R 真链 前→后 | 退化R 对照 前→后 |",
         "|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in rows:
        L.append("| {链} | {坏} | {b1}→{b2} | {r1}→{r2} | {o} | {n} | {d} | {fl} "
                 "| {dev} | {dr1}→{dr2} | {dc1}→{dc2} |".format(
                     链=r["链"],
                     坏=("★坏" if r["★修复前基准一是不是坏数"] else ""),
                     b1=f(r["修复前_笔数"]), b2=f(r["修复后_笔数"]),
                     r1=f(r["修复前_每笔净R"]), r2=f(r["修复后_每笔净R"]),
                     o=f(r["修复前_基准一"]), n=f(r["修复后_基准一"]),
                     d=f(r["基准一差"], 6),
                     fl=f(r["★符号是否翻转"]),
                     dev=f(r["修复后_对照笔数偏差"], 4),
                     dr1=f(r["★修复前退化R_真链笔数(旧流水重算)"]),
                     dr2=f(r["★修复后退化R_真链笔数(r_degenerate)"]),
                     dc1=f(r["★修复前退化R_对照笔数(旧流水重算)"]),
                     dc2=f(r["★修复后退化R_对照笔数(r_degenerate)"])))

    L += ["", "## 表二 · 那 35 条「修复前是坏数」的,修复后变成了什么", "",
          "| 链 | 基准一 前 | 基准一 后 | 修复后结论 |", "|---|---|---|---|"]
    for r in rows:
        if r["★修复前基准一是不是坏数"]:
            L.append(f"| {r['链']} | {f(r['修复前_基准一'])} | "
                     f"{f(r['修复后_基准一'])} | "
                     f"{r['★修复后基准一还坏不坏']['★结论']} |")

    L += ["", "## 表三 · 符号翻转的链（修复前赢随机 / 修复后输随机，或反过来）", ""]
    if flips:
        L += ["| 链 | 基准一 前 | 基准一 后 | 方向 |", "|---|---|---|---|"]
        for r in rows:
            if r["★符号是否翻转"]:
                direc = ("修复前赢随机 → 修复后输随机"
                         if r["修复前_基准一"] > 0 else
                         "修复前输随机 → 修复后赢随机")
                L.append(f"| {r['链']} | {f(r['修复前_基准一'])} | "
                         f"{f(r['修复后_基准一'])} | {direc} |")
    else:
        L.append("★ 一条都没有。")

    L += ["", "## 表四 · 退化 R 到底出在哪一侧（★ 本轮实测）", "",
          f"- 真链（策略自己的流水）：**{summary['★★★真链退化R_修复后实测_有几条链']} 条链 / "
          f"{summary['★★★真链退化R_修复后实测_总笔数']} 笔**",
          f"- 对照组（50 个种子并池）：**{summary['★对照组退化R_修复后实测_有几条链']} 条链 / "
          f"{summary['★对照组退化R_修复后实测_总笔数']} 笔**", ""]
    if real_hit:
        L += ["| 链 | 真链退化R笔数（本轮实测） | 真链总笔数 |", "|---|---|---|"]
        for r in rows:
            v = r["★修复后退化R_真链笔数(r_degenerate)"]
            if v:
                L.append(f"| {r['链']} | {v} | {f(r['修复后_笔数'])} |")
    L.append("")

    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")

    # --------------------------------------------- 流水指纹清单(不存流水本身)
    man = []
    if os.path.isdir(LEDGERS):
        for fn in sorted(os.listdir(LEDGERS)):
            p = os.path.join(LEDGERS, fn)
            if not os.path.isfile(p):
                continue
            h = hashlib.sha256()
            with open(p, "rb") as fh:
                for blk in iter(lambda: fh.read(1 << 20), b""):
                    h.update(blk)
            man.append({"file": fn, "bytes": os.path.getsize(p),
                        "sha256": h.hexdigest()})
    with open(MANIFEST, "w", encoding="utf-8") as fh:
        json.dump({"这是什么": "★ 本轮流水的 SHA-256 清单 —— ★★ 流水本身不入库",
                   "目录": "probe/bench1_rerun_1102/ledgers_1102/",
                   "份数": len(man), "逐份": man},
                  fh, ensure_ascii=False, indent=1)

    print(json.dumps(summary, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
