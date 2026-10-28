"""
流派二 VCP —— 应用外部专家 2026-10-28 全部修正之后的重跑。

================================ 三秒版 ================================
上一批流派二八年只成交 1 笔,根本没法评估。原因是成交量那两条被掐在
同一天 AND 在一起(要求量在一天之内从「不到均量 6 成」跳到「均量以上」)。
★ 专家已书面承认那个写法是自毁的,并给了修正版的三条件写法。
这个脚本把修正版跑出来,★ slots 三档 × 摩擦三档,全部并列报。

跑法:python -m engine.run_vcp_fixed
=========================================================================

★ 本轮改了什么(全部来自专家 2026-10-28 的书面修正,我们一个数没自己挑):
  ① 成交量:volume_dryup + breakout_volume_band → vcp_volume_tripod 三条件
     标注一律「行业惯例(专家 2026-10-28 修正版)」,★ 不许标「原著写死」
  ② slots:锁 10(长尾遮蔽效应),单票名义上限 10% NAV
     ★ 但 3 / 5 / 10 三档照样并列报 —— 上一批证明 slots 会翻结论的符号

★ 仍然关掉的两样(和上一批一致,不是本轮新关的):
  · ① 行业 RS —— 仓库的行业标签是当前快照、非 PIT(审计 §3-C)
  · ⑤「15 日滞涨换血」—— 触发条件没定义,不能猜(审计 §2-C)
  ★ 所以这一版**仍然不是完整的这一派**,报告里必须写明。
"""

from __future__ import annotations

import json
import os
import time

import numpy as np
import pandas as pd

from . import analyze, cache, chain, data, matrices, stats_gate
from .run_batch import (CONFIG_DIR, _load, _num, _vcp_base, signal_funnel,
                        window_pool_gate)

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "results_1028_流派二修正后.json")
LEDGER_DIR = os.path.join(HERE, "ledgers_1028_vcp修正后")

SLOTS = (3, 5, 10)


def vcp_fixed_variants() -> list[tuple[str, dict, list[str]]]:
    """修正版 × slots 三档。★ 三档是并列报的敏感度,不是三选一。"""
    out = []
    for s in SLOTS:
        raw, notes = _vcp_base()
        raw["slots"] = s
        raw["source_slots"] = (
            "行业惯例 —— 专家 2026-10-28 结论 slots=10"
            "(Clenow《Stocks on the Move》2015 Ch.6 用 20 槽;"
            "Statman 1987 JFQA:12~15 只已吸收 90% 以上特质风险)。"
            "★ 3 / 5 两档是并列报的敏感度,不是我们挑的最优值。")
        notes.insert(0,
            f"★ 本版 = 专家 2026-10-28 修正版,slots={s}。"
            f"★★ 成交量改成三条件(条件1 突破前 5 天内至少 1 天地量 ≤0.60×SMA50;"
            f"条件2 SMA5(t−1) ≤0.85×SMA50(t−1) 收敛;"
            f"条件3 突破日 Vol ≥1.00×SMA50(t−1) 且 ≥1.20×SMA5(t−1))。"
            f"★ 标注:行业惯例(专家 2026-10-28 修正版),★ 不是「原著写死」。")
        if s != 10:
            notes.append(
                f"★ slots={s} 不是结论档。专家结论是 slots=10"
                f"(长尾遮蔽效应:55 日突破胜率只有 30~35%,正期望全靠前 5~8% 的"
                f"极端大牛股,槽位太少会被平庸试错单占满、真龙头来了没位置)。"
                f"★ 三档并列报是因为上一批证明 slots 会翻结论的符号。")
        else:
            notes.append(
                "★★ 这一档是结论档(专家 2026-10-28 结论:slots=10,"
                "单票名义上限 10% NAV)。")
        out.append((f"流派二_VCP_修正版_slots{s}", raw, notes))
    return out


def run_one(name: str, raw: dict, notes: list[str], syms: list[str]) -> dict:
    t0 = time.time()
    print("=" * 78)
    print(f"跑链:{name}")
    for nt in notes:
        print("  ⚠ " + nt)

    cfg = chain.ChainConfig.from_dict(raw)
    rep = cfg.adapt_report
    if not rep.ok:
        raise RuntimeError(
            f"{name} 还有没实现的规则,★ 不许带着它跑(悄悄忽略最危险):\n"
            + rep.text())
    print("  " + rep.text().replace("\n", "\n  "))

    funnel = signal_funnel(raw, [s for s in syms if s in cache.symbols()],
                           data.PERF_START)
    print("  [信号漏斗]")
    for r in funnel["逐关"]:
        print(f"    {r['关']:46s} 单条={r['单条']:9d} 累计={r['累计']:9d}")

    res = chain.run_chain(cfg, syms)
    os.makedirs(LEDGER_DIR, exist_ok=True)
    res.save_ledger(os.path.join(LEDGER_DIR, f"{name}.csv"))

    n = len(res.ledger)
    banner = analyze.sample_size_banner(n)
    if banner:
        print("  " + "=" * 74)
        print("  " + banner)
        print("  " + "=" * 74)
    print(f"  笔数 {n}")

    out = analyze.evaluate(cfg, res, syms, with_attribution=True,
                           with_sensitivity=True, with_gate=True)
    gate4 = window_pool_gate(cfg, syms)
    print("  " + gate4.report().replace("\n", "\n  "))

    # ★ 征兆:胜率 >60% 或每笔 >+0.5R → 停下来查吊灯止损那个坑
    alarm = []
    if n:
        wr = float((res.ledger["net_pnl"] > 0).mean())
        rbar = float(res.ledger["r_multiple"].mean())
        if wr > 0.60 or rbar > 0.5:
            alarm.append(f"★★ 征兆警报:胜率 {wr:.1%} / 每笔R {rbar:+.3f} —— "
                         f"吊灯止损那个坑必须复查")
    for a in alarm:
        print("  " + a)

    rec = {
        "链名": name,
        "★必须讲清楚的前提": notes,
        "笔数": n,
        "★样本容量底线警示": banner,
        "★对专家预计180–260笔": (
            f"专家预计八年能到 180–260 笔,实际 {n} 笔 —— "
            + ("★ 落在预计区间内" if 180 <= n <= 260 else
               f"★ 不在区间内(差 {n - 180:+d} / {n - 260:+d} 笔),"
               f"★ 按任务书要求:差很远就是我们实现得不对,要查")),
        "样本量够不够": ("够" if n >= stats_gate.MIN_N
                        else f"★ 不够(n={n} < {stats_gate.MIN_N})"),
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
    print()
    syms = data.full_universe().pool("ALL")
    syms = [s for s in syms if s in cache.symbols()]
    print(f"全池 {len(syms)} 只,绩效窗口 {data.PERF_START} .. {data.PERF_END}")
    print()

    out = {
        "跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "全池只数": len(syms),
        "绩效窗口": f"{data.PERF_START} .. {data.PERF_END}(2016 起热机)",
        "★本轮应用的专家修正": [
            "① 成交量三条件(取代上一版自毁的 缩量 AND 突破日放量 同日写法)"
            " —— 标注:行业惯例(专家 2026-10-28 修正版)",
            "② slots 锁 10 · 单票名义上限 10% NAV(长尾遮蔽效应);"
            "★ 3/5/10 三档仍然并列报",
            "③ 新纪律:全系统全周期有效交易笔数 ≥ 150 的统计底线,"
            "不足时报告顶部强制打警示",
        ],
        "硬纪律落点": {
            "退市破产按−100%": sorted(
                s for s in syms if data.load_manifest()[s].is_bankruptcy),
            "拆股8根": "6 根已按比例修正,2 根(AMRS/PRTY)判不准、整只剔除",
            "★股数序列拆股闸": "★ 本轮新增 engine/share_gate.py —— "
                                "单位闸 + 季度区间去重 + 拆股闸三道",
            "预热": "2016 起热机,2018-01-01 才计入绩效(Fama 1998)",
            "网格搜索": "没有。slots 三档 / 摩擦三档都是并列报的敏感度",
        },
        "链": [],
    }
    for name, raw, notes in vcp_fixed_variants():
        try:
            out["链"].append(run_one(name, raw, notes, syms))
        except Exception as e:
            print(f"★ {name} 跑挂了:{type(e).__name__}: {e}")
            out["链"].append({"链名": name, "★跑挂了": f"{type(e).__name__}: {e}",
                              "★必须讲清楚的前提": notes})
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print()
    print(f"原始数字已写:{OUT_JSON}")
    print(f"交易流水已写:{LEDGER_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
