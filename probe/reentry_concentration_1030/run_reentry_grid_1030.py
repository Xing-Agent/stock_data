#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 重新进场 冷却期/上限 网格 + 组合集中度闸 —— 真跑(2026-10-30)

★ 跑批纪律(今天为这几件各丢过一次跑批,逐条照做):
  ① 不用 `nohup … &`。
  ② 可续跑:每跑完一条链 dump 一次 JSON,重跑跳过已有结果。
  ③ 先用 1~2 条链量耗时(已量:m 建一次 1~31s,run_chain 只 0.4~0.7s
     → ★ m **只建一次**,网格各点共用,所以总时间 ≈ 建矩阵的时间)。
  ④ 先写结果再打印,print 一律包 try。

★★ 口径一条都没另发明:
   池子   = 大+中(large_mid),走 rerun_core_1030.apply_scope(先例)
   基准二 = engine/analyze.py 的 exposure_matched_benchmark(★ grep 到的现成实现,
            **不自己再写一份** —— 今天「同一样东西几种写法」已累计 26 处)
   R      = r_multiple_net(扣摩擦)
   ★★★ 基准一(同环境随机进场)**本轮一个都不跑、一个结论都不下** ——
      策略组已定:基准一正在修(对照组曾在错的池子里跑)。
"""
from __future__ import annotations

import copy
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE, os.path.join(ROOT, "probe", "v2_rerun_1030")):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import (analyze, chain, data, matrices, ops_exits_1029,   # noqa: E402
                    pat6_ops)
import rerun_core_1030 as RC                                          # noqa: E402
import reentry_gate_1030 as RG                                        # noqa: E402

OUT = os.path.join(HERE, "reentry_grid_1030.json")

#: ★ 3~5 条最有代表性的链(任务书要求:≥1 趋势跟随 · ≥1 温斯坦 · ≥1 突破)
CHAINS = [
    ("趋势跟随(大师)",          "engine/configs/trend_following.yaml",             "趋势跟随"),
    ("技-1 唐奇安System1",       "engine/configs/技-1-原著-唐奇安反向通道离场.yaml",  "趋势跟随"),
    ("技-3 温斯坦-行业",         "engine/configs/技-3-行业.yaml",                   "温斯坦"),
    ("技-4 杯柄-行业",           "engine/configs/技-4-行业.yaml",                   "突破"),
    ("技-8 时间止损20日-行业",   "engine/configs/技-8-行业-时间止损20日.yaml",       "突破"),
]


def _load() -> dict:
    if os.path.exists(OUT):
        try:
            with open(OUT, encoding="utf-8") as fh:
                return json.load(fh)
        except Exception:
            pass
    return {"口径": {
        "池子": "大+中(large_mid),rerun_core_1030.apply_scope",
        "基准二": "engine/analyze.py exposure_matched_benchmark(Ē 全周期固定)",
        "基准一": "★★★ 本轮不跑、不下任何结论(它正在被另一个 agent 修)",
        "R": "r_multiple_net(扣摩擦)",
        "★XING填的数": {
            "冷却期N(交易日)": list(RG.COOLDOWN_GRID),
            "重进上限M(次)": list(RG.CAP_GRID),
            "一轮的定义": "整个回测期(主口径)/ 一个日历年(敏感度)——★ 原著与任务书都没定义",
        },
        "★引擎本来就有重新进场": ("chain.py 第⑤步 `j not in pos and m.entry[i,j]` —— "
                                   "进场条件重新成立+仓位空着就会再进。"
                                   "本文件装的是**约束**,M=0 那一档 = 没有重新进场的反事实"),
    }, "逐链": {}}


def _save(st: dict) -> None:
    tmp = OUT + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(st, fh, ensure_ascii=False, indent=1, default=str)
    os.replace(tmp, OUT)


def _metrics(res, cfg) -> dict:
    led = res.ledger
    r = led["r_multiple_net"].astype(float).to_numpy() if len(led) else np.array([])
    r = r[np.isfinite(r)]
    d = led.copy()
    if len(d):
        d = d.sort_values(["symbol", "entry_date"], kind="mergesort")
        d["seq"] = d.groupby("symbol").cumcount()

    def _split(sel):
        if not len(d):
            return {"笔数": 0}
        s = d[sel]
        rr = s["r_multiple_net"].astype(float).to_numpy()
        rr = rr[np.isfinite(rr)]
        return {"笔数": int(len(s)),
                "胜率": float((rr > 0).mean()) if rr.size else None,
                "每笔净R": float(rr.mean()) if rr.size else None,
                "总净R": float(rr.sum()) if rr.size else None,
                "净盈亏": float(s["net_pnl"].sum())}

    bm = cfg.get("benchmark") or {}
    b2 = analyze.exposure_matched_benchmark(
        res, bm.get("component_match", "large"), bm.get("risk_free_annual"))
    return {
        "笔数": int(len(led)),
        "总净R": float(r.sum()) if r.size else None,
        "每笔净R": float(r.mean()) if r.size else None,
        "胜率": float((r > 0).mean()) if r.size else None,
        "净盈亏": float(led["net_pnl"].sum()) if len(led) else 0.0,
        "总收益": float(res.equity.iloc[-1] / res.equity.iloc[0] - 1.0),
        "Ē净敞口": float(res.exposure.mean()),
        "基准二_超额": float(b2["★超额收益(链 − 同等仓位大盘)"]),
        "基准二_基准总收益": float(b2["基准总收益"]),
        "基准二_为正": bool(b2["★超额收益(链 − 同等仓位大盘)"] > 0),
        "基准二_成分指数": b2["成分匹配指数"],
        "基准二_Ē是否退化为市场中性": bool(abs(float(b2["★Ē_全周期固定净敞口"])) <= 0.10),
        "首次进场": _split(d["seq"] == 0) if len(d) else {"笔数": 0},
        "重进": _split(d["seq"] > 0) if len(d) else {"笔数": 0},
    }


def variants() -> list[tuple[str, dict]]:
    v = [("现状(引擎默认:重进不受限)", {})]
    v.append(("★反事实:完全不许重进(M=0)", {"cap": 0}))
    for n in RG.COOLDOWN_GRID:
        v.append((f"冷却期 N={n} 交易日", {"cooldown": n}))
    for mm in RG.CAP_GRID:
        v.append((f"重进上限 M={mm} 次/全期", {"cap": mm}))
    for mm in RG.CAP_GRID:
        v.append((f"重进上限 M={mm} 次/年(敏感度)",
                  {"cap": mm, "round_mode": "year"}))
    return v


def main() -> int:
    pat6_ops.install()
    ops_exits_1029.install()
    st = _load()
    syms = data.full_universe().pool("ALL")
    for label, cf, school in CHAINS:
        done = st["逐链"].get(label, {}).get("变体", {})
        todo = [(nm, kw) for nm, kw in variants() if nm not in done]
        if not todo:
            try:
                print(f"跳过(已有结果){label}")
            except Exception:
                pass
            continue
        t0 = time.time()
        cfg = chain.ChainConfig.load(os.path.join(ROOT, cf))
        m0 = matrices.build(cfg.raw, syms)
        scope_diag = RC.apply_scope(m0, "large_mid")
        tb = time.time() - t0
        rec = st["逐链"].setdefault(label, {"配置": cf, "流派": school,
                                            "池子诊断_掩膜真值比例":
                                            scope_diag.get("掩膜为真的票日比例"),
                                            "建矩阵秒": round(tb, 1), "变体": {}})
        for nm, kw in todo:
            t1 = time.time()
            mm = copy.copy(m0)                 # ★ 浅拷贝够用:只换 universe 这一个字段
            try:
                res, diag = RG.run_constrained(cfg, syms, mm, chain.run_chain, **kw)
                met = _metrics(res, cfg)
                met["约束"] = {k: v for k, v in kw.items()}
                met["不动点迭代"] = diag
                met["秒"] = round(time.time() - t1, 1)
                rec["变体"][nm] = met
            except Exception as exc:
                rec["变体"][nm] = {"失败": f"{type(exc).__name__}: {exc}"}
            _save(st)                          # ★★ 每个点存一次 → 可续跑
            try:
                r = rec["变体"][nm]
                if "失败" in r:
                    print(f"  {label} | {nm}: {r['失败'][:110]}")
                else:
                    print(f"  {label} | {nm}: 笔={r['笔数']:5d} 总R={r['总净R'] or 0:8.1f} "
                          f"基准二超额={r['基准二_超额']*100:7.2f}% "
                          f"重进={r['重进']['笔数']:5d} ({r['秒']}s)")
            except Exception as exc:
                print("打印出错(结果已写出):", repr(exc))
        _save(st)
    try:
        print(f"\n已写 {OUT}")
    except Exception:
        pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
