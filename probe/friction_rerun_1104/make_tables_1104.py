#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 摩擦改前 / 改后 逐链对照表 + 两条预言的实测判定(2026-11-04)

★★★ 三秒版:这个脚本不跑链,只把两轮的数摆到一起,然后回答两个是非题:
    ① 有没有任何一条链**变好**?(登记:只会变差或不变)
    ② 赢随机的条数是**增加/不变**还是**减少**?(登记:增加或不变)

★★ 数从哪来(逐条写明,★ 不许有第三个来源):
    · 改后:probe/friction_rerun_1104/friction_rerun_1104.json(本轮实跑)
    · 改前「每笔净R / 笔数 / 基准一」:probe/bench1_rerun_1102/bench1_rerun_1102.json
      ★★★ 按铁律**只读,不重跑**
    · 改前「净盈亏 / 摩擦总额」:★★ 1102 的汇总 JSON 里**没有**这两个美元数,
      所以从 1102 的流水 `ledgers_1102/REAL__*.csv` 现算(sum(net_pnl) /
      sum(friction_cost))—— ★★★ 这是读流水,不是重跑。

★★★ 中途的数不许进结论:全量不齐(45 条)或有「跑不了」→ 直接退出,不出表。

跑法:python3 probe/friction_rerun_1104/make_tables_1104.py
"""
from __future__ import annotations

import json
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
B1102 = os.path.join(ROOT, "probe", "bench1_rerun_1102")

NEW_JSON = os.path.join(HERE, "friction_rerun_1104.json")
OLD_JSON = os.path.join(B1102, "bench1_rerun_1102.json")
OLD_LEDGERS = os.path.join(B1102, "ledgers_1102")
OUT_JSON = os.path.join(HERE, "对照-摩擦改前后-1104.json")
OUT_MD = os.path.join(HERE, "表-逐链-摩擦改前后-1104.md")

#: ★★★ 登记(《手册 23》2.3)单列的那三条 —— 全部用 技-11-行业.yaml,
#   策略倍数 3.97× > 对照 3.17×(持仓流动性比随机进场还差)
JI11_REGISTERED = "技-11-行业.yaml"

#: ★ 浮点噪声容差:小于这个的变化算「不变」,不算「变好」
EPS_USD = 0.01          # 美元
EPS_R = 1e-9            # 每笔净 R


def safe_name(label: str) -> str:
    return label.replace("/", "_").replace(" ", "")


def old_money(label: str) -> dict:
    """★ 改前的美元数:从 1102 的流水现算。★★ 找不到就写「算不出」+ 原因。"""
    p = os.path.join(OLD_LEDGERS, f"REAL__{safe_name(label)}.csv")
    if not os.path.exists(p):
        return {"净盈亏": None, "摩擦总额": None, "笔数": None,
                "★算不出": f"找不到 1102 的流水 {os.path.basename(p)}"}
    df = pd.read_csv(p)
    out = {"笔数": int(len(df))}
    for k, col in (("净盈亏", "net_pnl"), ("摩擦总额", "friction_cost")):
        if col in df.columns:
            out[k] = float(pd.to_numeric(df[col], errors="coerce").sum())
        else:
            out[k] = None
            out["★算不出"] = f"1102 流水里没有 {col} 列"
    out["名义金额"] = (float(pd.to_numeric(df["notional_in"], errors="coerce").sum()
                            + pd.to_numeric(df["notional_out"],
                                            errors="coerce").sum())
                       if {"notional_in", "notional_out"} <= set(df.columns)
                       else None)
    out["每笔净R_从流水重算"] = (
        float(pd.to_numeric(df["r_multiple_net"], errors="coerce").mean())
        if "r_multiple_net" in df.columns else None)
    return out


def main() -> int:
    new = json.load(open(NEW_JSON, encoding="utf-8"))
    old = {r["链"]: r for r in json.load(open(OLD_JSON, encoding="utf-8"))["逐链"]}
    rows_new = new["逐链"]

    # ---- ★★★ 中途的数不许进结论
    crash = [r["链"] for r in rows_new if r.get("★跑不了")]
    if len(rows_new) != 45 or crash:
        print(f"★★★ 不出表:本轮 {len(rows_new)} 条(要 45 条)· "
              f"跑不了 {len(crash)} 条 {crash[:5]} —— 中途的数不许进结论。")
        return 2

    rows: list[dict] = []
    for r in rows_new:
        label = r["链"]
        o = old.get(label) or {}
        om = old_money(label)
        nm = r.get("★真链美元") or {}
        d: dict = {
            "链": label,
            "族": r.get("族"),
            "配置": r.get("配置"),
            "★是登记单列的技-11三条之一": r.get("配置") == JI11_REGISTERED,
            "改前摩擦口径": "一刀切 one_way_bps(buy_and_hold 为 0.0,其余 5.0)",
            "改后摩擦口径": r.get("★本轮摩擦口径"),
            # ---- 笔数
            "笔数_改前": o.get("笔数"),
            "笔数_改后": r.get("笔数"),
            # ---- 净盈亏(美元)
            "净盈亏_改前": om.get("净盈亏"),
            "净盈亏_改后": nm.get("净盈亏"),
            # ---- 摩擦总额(美元)
            "摩擦总额_改前": om.get("摩擦总额"),
            "摩擦总额_改后": nm.get("摩擦总额"),
            # ---- 每笔净 R
            "每笔净R_改前": o.get("每笔净R"),
            "每笔净R_改后": r.get("每笔净R"),
            # ---- 基准一
            "基准一_改前": o.get("★新基准一值"),
            "基准一_改后": r.get("★新基准一值"),
            "★改前流水找不到或缺列": om.get("★算不出"),
            "改前笔数_从流水数": om.get("笔数"),
            "三档笔数_改后": nm.get("三档笔数"),
            "单边bps_改后": nm.get("单边bps取值"),
        }
        # ---- 差值
        def diff(a, b):
            return (None if a is None or b is None else b - a)
        d["净盈亏差"] = diff(d["净盈亏_改前"], d["净盈亏_改后"])
        d["摩擦总额差"] = diff(d["摩擦总额_改前"], d["摩擦总额_改后"])
        d["摩擦倍数(改后/改前)"] = (
            None if not d["摩擦总额_改前"] else
            d["摩擦总额_改后"] / d["摩擦总额_改前"])
        d["每笔净R差"] = diff(d["每笔净R_改前"], d["每笔净R_改后"])
        d["基准一差"] = diff(d["基准一_改前"], d["基准一_改后"])
        d["笔数差"] = diff(d["笔数_改前"], d["笔数_改后"])
        # ---- ★★★ 预言一:变好 / 变差 / 不变
        d["净盈亏_判"] = ("算不出" if d["净盈亏差"] is None else
                          "变好" if d["净盈亏差"] > EPS_USD else
                          "变差" if d["净盈亏差"] < -EPS_USD else "不变")
        d["每笔净R_判"] = ("算不出" if d["每笔净R差"] is None else
                           "变好" if d["每笔净R差"] > EPS_R else
                           "变差" if d["每笔净R差"] < -EPS_R else "不变")
        # ---- ★★★ 预言二:赢不赢随机(判据和 1102/考卷同一套:基准一 > 0)
        d["赢随机_改前"] = (None if d["基准一_改前"] is None
                            else bool(d["基准一_改前"] > 0))
        d["赢随机_改后"] = (None if d["基准一_改后"] is None
                            else bool(d["基准一_改后"] > 0))
        d["赢随机_是否翻转"] = (None if d["赢随机_改前"] is None
                                or d["赢随机_改后"] is None
                                else d["赢随机_改前"] != d["赢随机_改后"])
        rows.append(d)

    # ══════════════════════════════════════════════════════════════════
    # ★★★ 预言一
    # ══════════════════════════════════════════════════════════════════
    better_pnl = [r for r in rows if r["净盈亏_判"] == "变好"]
    better_r = [r for r in rows if r["每笔净R_判"] == "变好"]
    uncomputable = [r for r in rows
                    if "算不出" in (r["净盈亏_判"], r["每笔净R_判"])]
    p1 = {
        "登记原文": "所有链只会变差或不变,没有一条会变好",
        "判据": f"净盈亏差 > {EPS_USD} 美元 或 每笔净R差 > {EPS_R} 即算「变好」",
        "净盈亏": {
            "变好": len(better_pnl), "变差":
                len([r for r in rows if r["净盈亏_判"] == "变差"]),
            "不变": len([r for r in rows if r["净盈亏_判"] == "不变"]),
            "算不出": len([r for r in rows if r["净盈亏_判"] == "算不出"]),
            "变好名单": [r["链"] for r in better_pnl],
        },
        "每笔净R": {
            "变好": len(better_r), "变差":
                len([r for r in rows if r["每笔净R_判"] == "变差"]),
            "不变": len([r for r in rows if r["每笔净R_判"] == "不变"]),
            "算不出": len([r for r in rows if r["每笔净R_判"] == "算不出"]),
            "变好名单": [r["链"] for r in better_r],
        },
        "算不出的链": [{"链": r["链"], "原因": r.get("★改前流水找不到或缺列")}
                       for r in uncomputable],
        "★★★判定": ("✅ 预言一成立 —— 没有任何一条变好"
                     if not better_pnl and not better_r else
                     "★★★ 预言一被伪证 —— 有链变好,立刻停"),
        "★★★是否要立刻停": bool(better_pnl or better_r),
    }

    # ══════════════════════════════════════════════════════════════════
    # ★★★ 预言二
    # ══════════════════════════════════════════════════════════════════
    main_rows = [r for r in rows if not r["★是登记单列的技-11三条之一"]]
    ji11 = [r for r in rows if r["★是登记单列的技-11三条之一"]]

    def wins(rs, key):
        return [r["链"] for r in rs if r[key] is True]

    p2 = {
        "登记原文": "赢随机的条数应该增加或不变",
        "判据": "基准一(真信号每笔R − 同环境随机进场每笔R)> 0 即「赢随机」"
                " —— ★ 和 1102/考卷同一套判据",
        "★★★登记里写的改前基线「21 赢 / 22 输」是考卷(1,042 只)的数,不是研发池的":
            "★★ 研发池(老池 198 只)1102 实测是 22 赢 / 23 输"
            "(出处:probe/exam_run_1102/考卷结果-1102.md 那张两列表)。"
            "★★★ 本轮铁律只许跑研发池,所以可比的改前基线用 22,不是 21。",
        "全部45条": {
            "赢随机_改前": len(wins(rows, "赢随机_改前")),
            "赢随机_改后": len(wins(rows, "赢随机_改后")),
            "输随机_改前": len([r for r in rows if r["赢随机_改前"] is False]),
            "输随机_改后": len([r for r in rows if r["赢随机_改后"] is False]),
        },
        "★剔掉登记单列的技-11三条之后(42条)": {
            "赢随机_改前": len(wins(main_rows, "赢随机_改前")),
            "赢随机_改后": len(wins(main_rows, "赢随机_改后")),
            "★方向": None,
        },
        "★单列·技-11三条": [
            {"链": r["链"], "配置": r["配置"],
             "基准一_改前": r["基准一_改前"], "基准一_改后": r["基准一_改后"],
             "赢随机_改前": r["赢随机_改前"], "赢随机_改后": r["赢随机_改后"],
             "摩擦倍数": r["摩擦倍数(改后/改前)"]}
            for r in ji11],
        "翻转明细": [
            {"链": r["链"], "方向": ("赢→输" if r["赢随机_改前"] else "输→赢"),
             "基准一_改前": r["基准一_改前"], "基准一_改后": r["基准一_改后"],
             "★是登记单列的技-11三条之一": r["★是登记单列的技-11三条之一"]}
            for r in rows if r["赢随机_是否翻转"]],
    }
    w_b = p2["★剔掉登记单列的技-11三条之后(42条)"]["赢随机_改前"]
    w_a = p2["★剔掉登记单列的技-11三条之后(42条)"]["赢随机_改后"]
    p2["★剔掉登记单列的技-11三条之后(42条)"]["★方向"] = (
        "增加" if w_a > w_b else "不变" if w_a == w_b else "减少")
    p2["★★★判定(按登记:技-11三条单列,看其余 42 条)"] = (
        f"✅ 预言二成立 —— 42 条里赢随机 {w_b} → {w_a}"
        f"({p2['★剔掉登记单列的技-11三条之后(42条)']['★方向']})"
        if w_a >= w_b else
        f"★★★ 预言二被伪证 —— 42 条里赢随机 {w_b} → {w_a}(减少),停")
    p2["★★★是否要立刻停"] = bool(w_a < w_b)
    # ★ 同时报全 45 条的方向(只作参考,不改判定)
    tw_b = p2["全部45条"]["赢随机_改前"]
    tw_a = p2["全部45条"]["赢随机_改后"]
    p2["★全45条的方向(参考,不作判定)"] = (
        "增加" if tw_a > tw_b else "不变" if tw_a == tw_b else "减少")

    # ══════════════════════════════════════════════════════════════════
    # 摩擦倍数实测(登记 §2.1 预测:策略中位 2.55×)
    # ══════════════════════════════════════════════════════════════════
    mult = sorted(r["摩擦倍数(改后/改前)"] for r in rows
                  if r["摩擦倍数(改后/改前)"] is not None)
    fr = {
        "有倍数的链数": len(mult),
        "中位": (mult[len(mult) // 2] if mult else None),
        "最小": (mult[0] if mult else None),
        "最大": (mult[-1] if mult else None),
        "★登记预测的策略中位": 2.55,
        "★注": "★★ 登记那个 2.55× 是在**考卷流水**上、按名义金额加权算的;"
               "这里是研发池、按摩擦总额直接相除 —— ★★★ 两者口径不同,只看量级。",
    }

    out = {
        "这是什么": "★★★ 摩擦口径统一(三档)· 研发池 45 条链 · 改前/改后对照"
                    " + 两条预言的实测判定",
        "数据来源": {
            "改后": "probe/friction_rerun_1104/friction_rerun_1104.json(本轮实跑)",
            "改前_每笔净R/笔数/基准一": "probe/bench1_rerun_1102/bench1_rerun_1102.json"
                                        "(★ 只读,没重跑)",
            "改前_净盈亏/摩擦总额": "probe/bench1_rerun_1102/ledgers_1102/REAL__*.csv"
                                    "(★★ 1102 汇总 JSON 里没有美元数,只能从流水现算)",
        },
        "★★★预言一_绝对": p1,
        "★★★预言二_相对": p2,
        "摩擦倍数实测": fr,
        "逐链": rows,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)

    # ---------------------------------------------------------------- md 表
    def f_usd(v):
        return "算不出" if v is None else f"{v:,.0f}"

    def f_r(v, n=4):
        return "算不出" if v is None else f"{v:+.{n}f}"

    L: list[str] = []
    L.append("# 逐链 · 摩擦改前 / 改后 对照表(2026-11-04)\n")
    L.append("> ★ 改前 = 一刀切单边 5bp(`buy_and_hold` 是 0.0)· "
             "改后 = 三档 5 / 15 / 30bp(单边,进出各扣一次,档位按进场日锁定)\n")
    L.append("> ★★ 改前的每笔净R / 笔数 / 基准一 直接读 1102 的汇总 JSON;"
             "美元数从 1102 的流水现算(汇总 JSON 里没有)。\n")
    L.append("\n## 表一 · 净盈亏(美元)· 每笔净R · 笔数 · 摩擦总额\n")
    L.append("| # | 链 | 笔数 | 净盈亏 改前 | 净盈亏 改后 | 差 | 每笔净R 改前 | "
             "每笔净R 改后 | 差 | 摩擦 改前 | 摩擦 改后 | 倍数 | 判 |")
    L.append("|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|")
    for i, r in enumerate(sorted(rows, key=lambda x: (x["族"] or "", x["链"])), 1):
        star = " ★技-11" if r["★是登记单列的技-11三条之一"] else ""
        n = (f"{r['笔数_改后']}" if r["笔数_改前"] == r["笔数_改后"]
             else f"{r['笔数_改前']}→{r['笔数_改后']}")
        L.append(
            f"| {i} | {r['链']}{star} | {n} | {f_usd(r['净盈亏_改前'])} | "
            f"{f_usd(r['净盈亏_改后'])} | {f_usd(r['净盈亏差'])} | "
            f"{f_r(r['每笔净R_改前'])} | {f_r(r['每笔净R_改后'])} | "
            f"{f_r(r['每笔净R差'])} | {f_usd(r['摩擦总额_改前'])} | "
            f"{f_usd(r['摩擦总额_改后'])} | "
            f"{'算不出' if r['摩擦倍数(改后/改前)'] is None else format(r['摩擦倍数(改后/改前)'], '.2f')}× | "
            f"{r['净盈亏_判']} / {r['每笔净R_判']} |")

    L.append("\n## 表二 · 赢不赢随机(基准一)\n")
    L.append("| # | 链 | 基准一 改前 | 基准一 改后 | 差 | 改前 | 改后 | 翻转 |")
    L.append("|--:|---|--:|--:|--:|---|---|---|")
    for i, r in enumerate(sorted(rows, key=lambda x: -(x["基准一_改后"] or -9)), 1):
        star = " ★技-11" if r["★是登记单列的技-11三条之一"] else ""
        wb = "赢" if r["赢随机_改前"] else "输" if r["赢随机_改前"] is False else "—"
        wa = "赢" if r["赢随机_改后"] else "输" if r["赢随机_改后"] is False else "—"
        L.append(f"| {i} | {r['链']}{star} | {f_r(r['基准一_改前'])} | "
                 f"{f_r(r['基准一_改后'])} | {f_r(r['基准一差'])} | {wb} | {wa} | "
                 f"{'★是' if r['赢随机_是否翻转'] else ''} |")

    L.append("\n## 表三 · 两条预言的判定\n")
    L.append(f"- **预言一**(绝对):{p1['★★★判定']}")
    L.append(f"  - 净盈亏:变好 **{p1['净盈亏']['变好']}** · "
             f"变差 {p1['净盈亏']['变差']} · 不变 {p1['净盈亏']['不变']} · "
             f"算不出 {p1['净盈亏']['算不出']}")
    L.append(f"  - 每笔净R:变好 **{p1['每笔净R']['变好']}** · "
             f"变差 {p1['每笔净R']['变差']} · 不变 {p1['每笔净R']['不变']} · "
             f"算不出 {p1['每笔净R']['算不出']}")
    L.append(f"- **预言二**(相对):{p2['★★★判定(按登记:技-11三条单列,看其余 42 条)']}")
    L.append(f"  - 全 45 条:赢随机 {tw_b} → {tw_a}"
             f"({p2['★全45条的方向(参考,不作判定)']})")
    L.append(f"  - 剔掉技-11 三条(42 条):{w_b} → {w_a}")
    L.append(f"  - ★★★ 登记写的「改前 21 赢」是**考卷**的数;研发池改前是 **22 赢 / 23 输**")
    L.append("\n### 单列 · 技-11 三条(登记 §2.3)\n")
    L.append("| 链 | 基准一 改前 | 基准一 改后 | 改前 | 改后 | 摩擦倍数 |")
    L.append("|---|--:|--:|---|---|--:|")
    for r in p2["★单列·技-11三条"]:
        L.append(f"| {r['链']} | {f_r(r['基准一_改前'])} | {f_r(r['基准一_改后'])} | "
                 f"{'赢' if r['赢随机_改前'] else '输'} | "
                 f"{'赢' if r['赢随机_改后'] else '输'} | "
                 f"{'算不出' if r['摩擦倍数'] is None else format(r['摩擦倍数'], '.2f')}× |")
    L.append(f"\n### 摩擦倍数(研发池实测,摩擦总额直接相除)\n")
    L.append(f"- 中位 **{fr['中位']:.2f}×** · 最小 {fr['最小']:.2f}× · "
             f"最大 {fr['最大']:.2f}×({fr['有倍数的链数']} 条)")
    L.append(f"- {fr['★注']}")
    with open(OUT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")

    print(f"★ 写到 {OUT_JSON}")
    print(f"★ 写到 {OUT_MD}")
    print(f"\n★★★ 预言一:{p1['★★★判定']}")
    print(f"   净盈亏 变好 {p1['净盈亏']['变好']} / 每笔净R 变好 {p1['每笔净R']['变好']}")
    print(f"★★★ 预言二:{p2['★★★判定(按登记:技-11三条单列,看其余 42 条)']}")
    print(f"   全45条 {tw_b} → {tw_a} · 剔技-11三条(42条){w_b} → {w_a}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
