#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ buy_and_hold 的 sanity check 四项 —— 摩擦改前 / 改后各跑一次(2026-11-04)

★★★ 三秒版:buy_and_hold 不只是锚点,它是「能认出自己坏了」那个检查点
    (`engine/bench_run_1029.py:160-205`,硬纪律第 11 条)。
    ★ 原话:「它不通过,这一轮的所有择时/选股拆分数字全部作废」。
    → 这个脚本就干一件事:把那四项**逐项实测**,摩擦改前改后各一次。

★★★ 登记(《手册 23》第四节)写死的判断,本脚本要去验的就是这两件:
    ① 四项检查**都不受摩擦影响**(关闸天数 = 0 · 择时贡献 ≡ 0 ·
       加法恒等式残差 ≡ 0 · 静态与动态基准(同敞口)逐日相同)
    ② 但「**原文口径下的敞口差额会变大**」(Ē 变小 → 差额变大)

★★ 两处口径留痕(★ 和 engine/bench_run_1029.main 不同,逐条写明):
    ① **池子**:bench_run_1029.main 用的是 `data.full_universe().pool("ALL")` 全池;
       ★★★ 本轮铁律是「只在研发池跑」,所以这里用**研发池 198 只 + 大+中口径**,
       和本轮 45 条链完全同池。★ 四项检查是结构性的(闸门/恒等式),
       换池不改变它们该不该成立。
    ② **改前**:buy_and_hold 的 sanity check 在研发池上**从来没跑过**
       (1102 那一轮只出基准一,没出基准线套件),所以「改前」这一次是现跑的 ——
       ★ 配置从 git `55088733^` 取(那时 `one_way_bps: 0.0`),★★ engine 一个字没动。

★ sanity_check 的判据**直接 import engine 自己的函数**,不自己抄一份。

跑法:python3 probe/friction_rerun_1104/sanity_bah_1104.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import traceback

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
V2 = os.path.join(ROOT, "probe", "v2_rerun_1030")
B1031 = os.path.join(ROOT, "probe", "bench1_rerun_1031")
for p in (ROOT, V2, B1031, HERE):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import bench_lines, bench_run_1029, chain, data, matrices  # noqa: E402
import rerun_core_1030 as RC                                          # noqa: E402

BAH = "buy_and_hold.yaml"
BEFORE_COMMIT = "55088733^"
SCOPE = "large_mid"
HOLDOUT_JSON = os.path.join(B1031, "holdout_1031.json")
OUT = os.path.join(HERE, "sanity_bah_1104.json")
LEDGERS = os.path.join(HERE, "ledgers_1104")


def dev_pool() -> tuple[list[str], set[str]]:
    d = json.load(open(HOLDOUT_JSON, encoding="utf-8"))
    return list(d["研发池名单"]), set(d["留出池名单"])


def raw_after() -> dict:
    with open(os.path.join(ROOT, "engine", "configs", BAH), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def raw_before() -> dict:
    r = subprocess.run(["git", "-C", ROOT, "show",
                        f"{BEFORE_COMMIT}:engine/configs/{BAH}"],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"★ 取不到改前的 {BAH}:{r.stderr[:200]!r}")
    return yaml.safe_load(r.stdout.decode("utf-8"))


def one(tag: str, raw: dict, dev: list[str], hold: set[str]) -> dict:
    t0 = time.time()
    cfg = chain.ChainConfig.from_dict(raw)
    m = matrices.build(cfg.raw, dev)
    scope_diag = RC.apply_scope(m, SCOPE)
    res = chain.run_chain(cfg, dev, data.PERF_START, data.PERF_END, m=m)
    led = res.ledger
    if len(led):
        leaked = sorted(set(led["symbol"].astype(str)) & hold)
        if leaked:
            raise RuntimeError(f"★★★ 留出池漏进来了:{leaked[:10]}")
        os.makedirs(LEDGERS, exist_ok=True)
        led.to_csv(os.path.join(LEDGERS, f"SANITY_{tag}__buy_and_hold.csv"),
                   index=False)

    suite = bench_lines.bench_suite(cfg, res, dev, m=m)
    rec = bench_run_1029._num({k: v for k, v in suite.items()
                               if not k.startswith("_")})
    sc = bench_run_1029.sanity_check(rec)

    costs = raw.get("costs") or {}
    import numpy as np
    import pandas as pd
    return {
        "标签": tag,
        "★摩擦口径": ("三档 " + json.dumps(costs.get("friction_tiers"),
                                           ensure_ascii=False)
                      if "friction_tiers" in costs
                      else (f"一刀切 one_way_bps={costs.get('one_way_bps')}"
                            if "one_way_bps" in costs else "★两个字段都没写")),
        "池子": f"研发池 {len(dev)} 只 × {SCOPE}",
        "universe收窄": scope_diag,
        "笔数": int(len(led)),
        "摩擦总额": (float(pd.to_numeric(led["friction_cost"],
                                         errors="coerce").sum())
                     if len(led) and "friction_cost" in led.columns else None),
        "净盈亏": (float(pd.to_numeric(led["net_pnl"], errors="coerce").sum())
                   if len(led) and "net_pnl" in led.columns else None),
        "单边bps取值": (sorted(set(pd.to_numeric(
            led["friction_bps"], errors="coerce").dropna().tolist()))
            if len(led) and "friction_bps" in led.columns else None),
        "三档笔数": (led["liquidity_tier"].value_counts().to_dict()
                     if len(led) and "liquidity_tier" in led.columns else {}),
        # ---- ★★★ 四项逐项
        "★★★sanity_check四项": sc,
        # ---- ★ 登记里说会变的那个数
        "★Ē_全周期固定净敞口": rec["基准二_静态基准"]["★Ē_全周期固定净敞口"],
        "★选股贡献_同敞口口径": rec["★选股贡献"],
        "★选股贡献_原文口径": rec["★选股贡献_原文口径"],
        "★★★原文口径下的敞口差额(原文 − 同敞口)":
            rec["★选股贡献_原文口径"] - rec["★选股贡献"],
        "★择时贡献": rec["★择时贡献"],
        "★加法恒等式残差": rec["★加法恒等式自检"]["残差"],
        "闸门统计": rec["闸门统计"],
        "链总收益": rec.get("链总收益"),
        "基准二_静态基准总收益": rec["基准二_静态基准"]["基准总收益"],
        "基准三_同敞口_基准总收益":
            rec["基准三_动态开关基准_同敞口口径"]["基准总收益"],
        "耗时秒": round(time.time() - t0, 1),
    }


def main() -> int:
    dev, hold = dev_pool()
    print(f"★ 研发池 {len(dev)} 只 · 留出池 {len(hold)} 只(一笔不跑)", flush=True)
    out: dict = {
        "这是什么": "★★★ buy_and_hold 的 sanity check 四项 —— 摩擦改前/改后各一次",
        "★口径留痕": [
            "① 池子:研发池 198 只 × large_mid(★ engine/bench_run_1029.main 用的是"
            "全池 —— 本轮铁律「只在研发池跑」,所以换成研发池,逐条留痕)",
            "② 改前这一次是**现跑**的:buy_and_hold 的基准线套件在研发池上从没跑过,"
            "1102 那一轮只出基准一。配置取自 git 55088733^(one_way_bps: 0.0)。",
            "③ 判据直接 import engine.bench_run_1029.sanity_check,没自己抄一份。",
        ],
        "容差": bench_run_1029.SANITY_TOL,
    }
    for tag, raw in (("改前_一刀切0bp", raw_before()),
                     ("改后_三档", raw_after())):
        try:
            r = one(tag, raw, dev, hold)
        except Exception:
            r = {"标签": tag, "★跑不了": traceback.format_exc(limit=8)}
        out[tag] = r
        try:
            print(f"\n==== {tag} ====", flush=True)
            if r.get("★跑不了"):
                print(r["★跑不了"], flush=True)
            else:
                print(f"笔数 {r['笔数']} · 摩擦 ${r['摩擦总额']:,.0f} · "
                      f"净盈亏 ${r['净盈亏']:,.0f} · bps {r['单边bps取值']}", flush=True)
                for c in r["★★★sanity_check四项"]["逐项"]:
                    print(f"  {'✅' if c['过'] else '★★★没过'} {c['检查项']}"
                          f" 实测={c['实测']} 期望={c['期望']}", flush=True)
                print(f"  ★结论 {r['★★★sanity_check四项']['★结论']}", flush=True)
                print(f"  Ē={r['★Ē_全周期固定净敞口']:.6f} · "
                      f"原文口径敞口差额={r['★★★原文口径下的敞口差额(原文 − 同敞口)']:+.6%}",
                      flush=True)
        except Exception:
            pass

    a, b = out.get("改前_一刀切0bp") or {}, out.get("改后_三档") or {}
    if not a.get("★跑不了") and not b.get("★跑不了"):
        key = "★★★原文口径下的敞口差额(原文 − 同敞口)"
        out["★★★登记那两件的实测判定"] = {
            "① 四项都不受摩擦影响": {
                "改前四项全过": a["★★★sanity_check四项"]["过"],
                "改后四项全过": b["★★★sanity_check四项"]["过"],
                "逐项改前改后是否同样通过": [
                    {"检查项": ca["检查项"], "改前过": ca["过"], "改后过": cb["过"],
                     "改前实测": ca["实测"], "改后实测": cb["实测"]}
                    for ca, cb in zip(a["★★★sanity_check四项"]["逐项"],
                                      b["★★★sanity_check四项"]["逐项"])],
                "★判定": ("✅ 和登记一致(四项都过,摩擦没影响它们)"
                           if a["★★★sanity_check四项"]["过"]
                           and b["★★★sanity_check四项"]["过"]
                           else "★★★ 有项没过 —— 整轮作废"),
            },
            "② Ē 变小 → 原文口径敞口差额变大": {
                "Ē_改前": a["★Ē_全周期固定净敞口"],
                "Ē_改后": b["★Ē_全周期固定净敞口"],
                "Ē是否变小": b["★Ē_全周期固定净敞口"] < a["★Ē_全周期固定净敞口"],
                "敞口差额_改前": a[key],
                "敞口差额_改后": b[key],
                "差额绝对值是否变大": abs(b[key]) > abs(a[key]),
                "★判定": ("✅ 和登记一致(Ē 变小、差额绝对值变大)"
                           if b["★Ē_全周期固定净敞口"] < a["★Ē_全周期固定净敞口"]
                           and abs(b[key]) > abs(a[key])
                           else "★★ 和登记不一致 —— 见逐项数"),
            },
        }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n★ 写到 {OUT}", flush=True)
    try:
        v = out.get("★★★登记那两件的实测判定") or {}
        for k, d in v.items():
            print(f"{k}: {d.get('★判定')}", flush=True)
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    sys.exit(main())
