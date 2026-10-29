"""
流派一 趋势跟随 —— 2026-10-29 最新口径重跑(slots 3 / 5 / 10 三档并列)。

大白话:10-28 跑过这条链,之后口径变了六处(拆股闸重写 / 池子 298→300 /
退市结算价 / slots=10 与单票上限 10% / 硬关种子 bug / 判据两个 bug),
所以那份结果不能再引用,必须按新口径从头跑一遍。

本脚本额外做两件 10-28 没做的事:
  ★ 一、随机对照触发率统一到 analyze.random_control_rate 一个口径,
       并同时报出「旧公式(笔数/天数/100)」算出来的触发率,量化差几倍。
  ★ 二、判据用新旧两种触发率各跑一遍,量化旧口径把 Z 推偏了多少
       —— 这是「哪些已出的 Z 要作废重算」的证据。

跑法:python3 -m engine.run_trend_1029
"""

from __future__ import annotations

import json
import os
import time

import numpy as np
import pandas as pd
import yaml

from . import (analyze, cache, chain, data, matrices, stats_gate,
               window_pool)
from .run_batch import _num, signal_funnel, window_pool_gate

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(HERE, "configs")
OUT_JSON = os.path.join(HERE, "results_1029_趋势跟随最终.json")
LEDGER_DIR = os.path.join(HERE, "ledgers_1029_趋势跟随")

SLOTS = (3, 5, 10)


def _load(name: str) -> dict:
    with open(os.path.join(CONFIG_DIR, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _judge_with_rate(cfg: chain.ChainConfig, res: chain.ChainResult,
                     syms: list[str], rate: float,
                     ctrl=None) -> dict:
    """用指定触发率跑一遍判据三套对照组,返回四个 Z / p。"""
    if ctrl is None:
        c2 = cfg.copy_with(entry={"type": "random",
                                  "params": {"rate": rate, "seed": 424242},
                                  "source": "判据对照组:同环境随机进场"})
        try:
            ctrl = chain.run_chain(c2, syms, data.PERF_START, data.PERF_END).ledger
        except Exception:
            ctrl = None
    v = analyze.bootstrap_on_ledger(res, ctrl)
    return {"触发率": rate,
            "对照组笔数": int(len(ctrl)) if ctrl is not None else None,
            **{k: {"Z": _num(r.z_effect), "p": _num(r.p_empirical),
                   "随机均值": _num(r.random_mean), "信号均值": _num(r.signal_mean)}
               for k, r in v.results.items()},
            "判定": {"通过": bool(v.passed), "级别": v.level,
                     "理由": list(v.reasons)}}


def run_one(slots: int, syms: list[str]) -> dict:
    t0 = time.time()
    name = f"流派一_趋势跟随_slots{slots}"
    print("=" * 78)
    print(f"跑链:{name}")

    raw = _load("trend_following.yaml")
    raw["slots"] = slots
    raw["source_slots"] = ("配置主值 10(专家 10-28 结论,行业惯例);"
                           "3 / 5 档为敏感度展示,★ 不是挑最优")

    cfg = chain.ChainConfig.from_dict(raw)
    rep = cfg.adapt_report
    if not rep.ok:
        raise RuntimeError(f"{name} 还有没实现的规则,不许带着它跑:\n{rep.text()}")

    funnel = signal_funnel(raw, [s for s in syms if s in cache.symbols()],
                           data.PERF_START)
    res = chain.run_chain(cfg, syms)
    os.makedirs(LEDGER_DIR, exist_ok=True)
    res.save_ledger(os.path.join(LEDGER_DIR, f"{name}.csv"))
    n = len(res.ledger)
    print(f"  笔数 {n}")

    out = analyze.evaluate(cfg, res, syms, with_attribution=True,
                           with_sensitivity=True, with_gate=True)

    # ★ 触发率三个口径的对照:旧错公式 / 闭式起点 / 校准后(最终口径)
    n_days = max(1, len(res.equity))
    n_syms = max(1, len(matrices.universe_mask(
        raw.get("universe") or {}, syms).columns))
    rate_closed = analyze.random_control_rate(n, n_days, n_syms)
    rate_old = max(1e-7, n / max(1, n_days) / 100)      # 10-28 判据用的旧公式
    rate_cal = out["判据_随机对照触发率"]
    print(f"  触发率 校准后={rate_cal:.6g}(对照成交 {out['判据_随机对照笔数']} 笔/真链 {n} 笔) "
          f"闭式起点={rate_closed:.6g} 旧错公式={rate_old:.6g}")

    judge_cal = _judge_with_rate(cfg, res, syms, rate_cal)
    judge_closed = _judge_with_rate(cfg, res, syms, rate_closed)
    judge_old = _judge_with_rate(cfg, res, syms, rate_old)

    gate4 = window_pool_gate(cfg, syms)
    print("  " + gate4.report().replace("\n", "\n  "))

    alarm = []
    if n:
        wr = float((res.ledger["net_pnl"] > 0).mean())
        rbar = float(res.ledger["r_multiple"].mean())
        if wr > 0.60 or rbar > 0.5:
            alarm.append(f"★★ 征兆警报:胜率 {wr:.1%} / 每笔R {rbar:+.3f} —— 复查吊灯止损")
    for a in alarm:
        print("  " + a)

    # 极性反转单列(第③套对照组)
    pol = out["判据"].results.get("极性反转")

    rec = {
        "链名": name,
        "slots": slots,
        "笔数": n,
        "样本量": ("够(≥150)" if n >= stats_gate.SYSTEM_MIN_TRADES
                   else f"★ 不够(n={n} < {stats_gate.SYSTEM_MIN_TRADES})"),
        "信号漏斗": funnel,
        "绝对表现": _num(out["绝对表现"]),
        "坑一_现金拖累": _num(out["坑一_现金拖累"]),
        "坑二_跳空穿透止损": _num(out["坑二_跳空穿透止损"]),
        "代价": _num(out["代价"]),
        "执行负荷": _num(out["执行负荷"]),
        "摩擦成本": _num(out["摩擦成本"]),
        "基准一_同环境随机进场": _num(out["基准一_同环境随机进场"]),
        "基准二_同等仓位大盘": _num(out["基准二_同等仓位大盘"]),
        "判据_三套对照组": _num(out["判据"]),
        "★极性反转": ({"Z": _num(pol.z_effect), "p": _num(pol.p_empirical),
                       "信号均值": _num(pol.signal_mean),
                       "随机均值": _num(pol.random_mean),
                       "级别": pol.level} if pol is not None else None),
        "★随机对照触发率": {"口径": analyze.RANDOM_RATE_DEF,
                            "最终_校准后": rate_cal,
                            "校准后对照成交笔数": out["判据_随机对照笔数"],
                            "校准轮次": out["判据_随机对照校准轮次"],
                            "闭式起点(笔数/天数/票数)": rate_closed,
                            "旧_判据用的错公式(笔数/天数/100)": rate_old,
                            "旧比闭式起点高几倍": round(rate_old / rate_closed, 3),
                            "池内票数": n_syms, "交易日数": n_days},
        "★判据_最终口径(校准后)": judge_cal,
        "★判据_闭式起点(仅作对照)": judge_closed,
        "★判据_旧错公式(作废,仅作对照)": judge_old,
        "★两窗口两池子硬关": _num(gate4),
        "分步归因": _num(out["分步归因"]),
        "坑四_摩擦敏感度": _num(out["坑四_摩擦敏感度"]),
        "征兆警报": alarm,
        "引擎显式关掉的东西": matrices.disabled_log(),
        "耗时秒": round(time.time() - t0, 1),
    }
    print(analyze.format_report(out))
    print(f"  (用了 {rec['耗时秒']} 秒)")
    return rec


def main(argv=None) -> int:
    print(data.cohort_report())
    syms = data.full_universe().pool("ALL")
    syms = [s for s in syms if s in cache.symbols()]
    print(f"\n全池 {len(syms)} 只,绩效窗口 {data.PERF_START} .. {data.PERF_END}\n")

    out = {"跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
           "全池只数": len(syms),
           "绩效窗口": f"{data.PERF_START} .. {data.PERF_END}(2016 起热机)",
           "口径": "2026-10-29(拆股闸重写 / 退市结算价 / 池子 300 / "
                   "slots=10 单票 10% / 硬关种子已修 / 随机对照触发率已统一)",
           "链": []}
    for s in SLOTS:
        try:
            out["链"].append(run_one(s, syms))
        except Exception as e:
            print(f"★ slots={s} 跑挂了:{type(e).__name__}: {e}")
            out["链"].append({"链名": f"slots{s}", "★跑挂了": f"{type(e).__name__}: {e}"})
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\n原始数字已写:{OUT_JSON}\n交易流水已写:{LEDGER_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
