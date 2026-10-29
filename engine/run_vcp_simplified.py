"""
流派二 VCP —— 按专家 2026-10-29 最终裁决简化成交量门禁之后的重跑。

================================ 三秒版 ================================
1028 那版把三个成交量条件全部 AND 在一起,八年只成交 15 笔,没法评估。
★ 专家最终裁决(Lin 已拍板):条件1 和条件2 高度共线、冗余,强行叠加是
  样本从 289 雪崩到 15 的唯一真凶。★ 条件2 彻底删除;条件3 的 1.20×SMA5
  连乘项删除;★ 原 breakout_volume_band 的 1.80 倍上限物理删除。
  成交量门禁只剩两条:① 突破前 5 天内有一天地量 ② 突破当天量上 50 日均量。
这个脚本把裁决版跑出来,★ slots 三档 × 摩擦三档,全部并列报。

跑法:python -m engine.run_vcp_simplified
=========================================================================

★ 专家给的预期量级(跑完必须对照,写在每一档的结果里):
    无槽位限制的纯信号:八年 180 ~ 280 笔(年均 25~35)
    10 槽位约束下成交:    140 ~ 220 笔(年均 18~28)
    三档诊断:15 笔 = 系统性维度休克 · 1254 笔 = 过度泛滥 ·
             160 ~ 210 笔 = 黄金区间
  ★ 若仍远低于 140 → 说明还有别的条件在误杀,★ 本脚本自动跑留一法定位。

★ 仍然关掉的两样(和前两批一致,不是本轮新关的):
  · ① 行业 RS —— 仓库的行业标签是当前快照、非 PIT(审计 §3-C)
  · ⑤「15 日滞涨换血」—— 触发条件没定义,不能猜(审计 §2-C)
  ★ 所以这一版**仍然不是完整的这一派**,报告里必须写明。
"""

from __future__ import annotations

import copy
import json
import os
import time

import numpy as np
import pandas as pd

from . import analyze, cache, chain, data, matrices, stats_gate
from .run_batch import _load, _num, _vcp_base, signal_funnel, window_pool_gate

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "results_1029_流派二成交量简化后.json")
LEDGER_DIR = os.path.join(HERE, "ledgers_1029_vcp简化后")

SLOTS = (3, 5, 10)

# ★ 专家给的预期量级与三档诊断 —— 写死在这里,跑完自动对照
EXPECT_SIGNALS = (180, 280)      # 无槽位限制的纯信号笔数
EXPECT_TRADES = (140, 220)       # 10 槽位约束下的成交笔数
GOLDEN_BAND = (160, 210)         # 黄金区间
SHOCK_LEVEL = 15                 # 系统性维度休克(上一轮)
FLOOD_LEVEL = 1254               # 过度泛滥


def _tier(n: int) -> str:
    """专家三档诊断:我们落在哪一档。★ 这是跑完必须明确报的第一件事。"""
    if n <= 40:
        return (f"★★【系统性维度休克】n={n} —— 和上一轮的 {SHOCK_LEVEL} 笔同一档。"
                f"★ 说明还有别的条件在误杀,必须用留一法定位")
    if n >= 800:
        return (f"★★【过度泛滥】n={n} —— 往 {FLOOD_LEVEL} 笔那一档走了,"
                f"★ 这一派已退化成普通的高位均线追高系统,不再是 VCP")
    if GOLDEN_BAND[0] <= n <= GOLDEN_BAND[1]:
        return f"★★【黄金区间】n={n},落在专家给的 {GOLDEN_BAND[0]}~{GOLDEN_BAND[1]} 之内"
    if EXPECT_TRADES[0] <= n <= EXPECT_TRADES[1]:
        return (f"★【预期区间内、黄金区间外】n={n} 落在 "
                f"{EXPECT_TRADES[0]}~{EXPECT_TRADES[1]} 之内,"
                f"但不在黄金区间 {GOLDEN_BAND[0]}~{GOLDEN_BAND[1]} 内")
    if n < EXPECT_TRADES[0]:
        return (f"★【低于预期区间】n={n} < {EXPECT_TRADES[0]} —— "
                f"差 {EXPECT_TRADES[0] - n} 笔。"
                + ("★ 但已过纪律 8 的 150 底线,结论可以下"
                   if n >= stats_gate.SYSTEM_MIN_TRADES
                   else f"★ 且未过纪律 8 的 {stats_gate.SYSTEM_MIN_TRADES} 底线"))
    return (f"★【高于预期区间】n={n} > {EXPECT_TRADES[1]},"
            f"比专家预计多 {n - EXPECT_TRADES[1]} 笔 —— 门禁可能放得偏松,"
            f"但离 {FLOOD_LEVEL} 笔那一档还远")


def vcp_variants() -> list[tuple[str, dict, list[str]]]:
    """裁决版 × slots 三档。★ 三档是并列报的敏感度,不是三选一。"""
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
            f"★★ 本版 = 专家 2026-10-29 最终裁决版(成交量门禁只剩两条),"
            f"slots={s}。"
            f"★ 门禁1 min(Vol[t−5..t−1]) ≤ 0.60 × SMA50(t−1)"
            f"(Minervini 2017 Ch.5「one or two days of extreme volume "
            f"contraction」);"
            f"★ 门禁2 Vol[t] ≥ 1.00 × SMA50(t−1),★ 无上限。"
            f"★ 已删除:条件2(SMA5 ≤ 0.85×SMA50,与门禁1 共线冗余)· "
            f"1.20×SMA5 连乘项 · breakout_volume_band 的 1.80 倍上限"
            f"(★ 物理删除,专家自判为【IS-只让样本内好看】)。")
        if s != 10:
            notes.append(
                f"★ slots={s} 不是结论档(结论档是 10)。三档并列报是因为"
                f"上一批证明 slots 会翻结论的符号(流派一 3/5/10 "
                f"= −5.9% / −13.8% / +9.3%)。")
        else:
            notes.append("★★ 这一档是结论档(专家结论:slots=10,单票上限 10% NAV)。")
        out.append((f"流派二_VCP_裁决版_slots{s}", raw, notes))
    return out


# ------------------------------------------------------------------ 纯信号笔数
def pure_signal_trades(syms: list[str]) -> dict:
    """
    ★ 无槽位限制时的纯信号笔数 —— 专家预期区间 180~280 对的就是这个数。
    做法:把 slots 开到远大于全池只数(999),其余七步一字不动。
    ★ 这不是一个「结果档」,只用来和专家的信号量预期对照。
    """
    raw, _ = _vcp_base()
    raw["slots"] = 999
    cfg = chain.ChainConfig.from_dict(raw)
    res = chain.run_chain(cfg, syms)
    n = len(res.ledger)
    yrs = 8.0
    return {
        "无槽位限制的纯信号笔数": n,
        "年均": round(n / yrs, 1),
        "专家预期": f"{EXPECT_SIGNALS[0]}~{EXPECT_SIGNALS[1]} 笔(年均 25~35)",
        "对照": ("★ 落在预期区间内"
                 if EXPECT_SIGNALS[0] <= n <= EXPECT_SIGNALS[1]
                 else f"★ 不在预期区间内(差 {n - EXPECT_SIGNALS[0]:+d} / "
                      f"{n - EXPECT_SIGNALS[1]:+d} 笔)"),
    }


# ------------------------------------------------------------------ 留一法定位
def leave_one_out(syms: list[str]) -> dict:
    """
    ★ 留一法 —— ★ 只为定位「还有哪一关在误杀」,去掉任何一关的版本
      ★ 一律不作为结果上报。任务书:若笔数仍远低于 140,用留一法定位。
    """
    idx = cache.field("close", syms).index
    perf = np.asarray(idx >= pd.Timestamp(data.PERF_START))

    def cnt(df):
        return int(np.asarray(df.to_numpy(bool))[perf, :].sum())

    base, _ = _vcp_base()

    def entry_events(skip_type=None):
        cum = None
        for r in base["entry"]["rules"]:
            if skip_type is not None and r.get("type") == skip_type:
                continue
            m = matrices._entry_rule_raw(r, syms)
            cum = m if cum is None else cum & m
        return matrices._event_only(cum)

    def universe(skip_idx=None):
        cum = None
        for k, r in enumerate(base["universe"]["rules"]):
            if skip_idx is not None and k == skip_idx:
                continue
            m = matrices._universe_rule_mask(r, syms, idx)
            cum = m if cum is None else cum & m
        return cum

    def trades(raw):
        return len(chain.run_chain(chain.ChainConfig.from_dict(raw), syms).ledger)

    def drop_entry(raw: dict, ty: str) -> dict:
        raw = copy.deepcopy(raw)
        raw["slots"] = 10
        raw["entry"]["rules"] = [r for r in raw["entry"]["rules"]
                                 if r.get("type") != ty]
        return raw

    def drop_universe(raw: dict, k: int) -> dict:
        raw = copy.deepcopy(raw)
        raw["slots"] = 10
        raw["universe"]["rules"] = [r for i, r in enumerate(raw["universe"]["rules"])
                                    if i != k]
        return raw

    full_ev, full_uni = entry_events(), universe()
    raw10 = copy.deepcopy(base)
    raw10["slots"] = 10
    rows = [{"一次只去掉一关": "(不去掉,裁决版完整链)",
             "③进场事件": cnt(full_ev),
             "③×①过选股范围": cnt(full_ev & full_uni),
             "★成交笔数(slots=10)": trades(raw10)}]

    for ty, label in [("vcp_volume_duo", "③ 成交量两门禁"),
                      ("sigma_squeeze", "③ σ5 点火门禁"),
                      ("vcp_contraction", "③ VCP 几何收缩"),
                      ("donchian_close_breakout", "③ 5 日收盘突破")]:
        ev = entry_events(skip_type=ty)
        rows.append({"一次只去掉一关": f"去掉 {label}",
                     "③进场事件": cnt(ev),
                     "③×①过选股范围": cnt(ev & full_uni),
                     "★成交笔数(slots=10)": trades(drop_entry(base, ty))})

    for k, r in enumerate(base["universe"]["rules"]):
        uni = universe(skip_idx=k)
        rows.append({"一次只去掉一关": f"去掉 ① {r.get('type')}(第 {k + 1} 条)",
                     "③进场事件": cnt(full_ev),
                     "③×①过选股范围": cnt(full_ev & uni),
                     "★成交笔数(slots=10)": trades(drop_universe(base, k))})

    # ★ 另外单独看一个:④ 止损距离 8% 硬闸 —— 它是在成交层面否决信号的
    raw_nogate = copy.deepcopy(base)
    raw_nogate["slots"] = 10
    raw_nogate["stop_init"]["hard_gate"]["params"]["max_pct"] = 100.0
    raw_keep = copy.deepcopy(base)
    raw_keep["slots"] = 10
    extra = {
        "④ 止损距离硬闸 8%(slots=10 下成交笔数)": trades(raw_keep),
        "④ 把硬闸放到 100%(★ 只为定位,不作为结果)": trades(raw_nogate),
    }
    return {"★口径": "★ 只为定位瓶颈,去掉任何一关的版本一律不作为结果上报",
            "逐关": rows, "④止损硬闸单独看": extra}


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
    tier = _tier(n)
    print(f"  笔数 {n}   {tier}")

    out = analyze.evaluate(cfg, res, syms, with_attribution=True,
                           with_sensitivity=True, with_gate=True)
    gate4 = window_pool_gate(cfg, syms)
    print("  " + gate4.report().replace("\n", "\n  "))

    # ★ 纪律 4:胜率 >60% 或每笔 >+0.5R → 停下来查吊灯止损那个坑
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
        "★专家三档诊断_落在哪一档": tier,
        "★样本容量底线警示": banner,
        "★对专家预期140–220笔": (
            f"专家预计 10 槽位约束下 {EXPECT_TRADES[0]}~{EXPECT_TRADES[1]} 笔"
            f"(年均 18~28),实际 {n} 笔(年均 {n / 8.0:.1f})"),
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
        "★本轮应用的专家最终裁决": [
            "① ★ 条件2(SMA5(t−1) ≤ 0.85 × SMA50(t−1))彻底删除 —— "
            "与条件1 高度共线冗余,专家承认是研究员自己加的过度约束,"
            "强行叠加是样本从 289 雪崩到 15 的唯一真凶",
            "② ★ 条件3 的「≥1.20 × SMA5(t−1)」连乘项删除 —— "
            "突破日既上 50 日均量、前 5 天又有 0.6x 地量日,"
            "对前 5 日均量的放大倍数天然已超 1.2 倍,写死连乘只会引入偶发边际失败",
            "③ ★★ breakout_volume_band 的 1.80 倍上限 **物理删除** —— "
            "原著对突破日放量从来是「越大越好」,推崇 2/3/5 倍的爆发日;"
            "焊死上限会精准击杀最强的前 5% 领头羊。专家自判【IS-只让样本内好看】。"
            "★ 它是项目里唯一一条我们自己数据定的参数,删掉等于删掉一个旋钮",
            "④ 成交量门禁最终 = 门禁1 AND 门禁2,只剩两条",
        ],
        "硬纪律落点": {
            "退市破产按−100%": sorted(
                s for s in syms if data.load_manifest()[s].is_bankruptcy),
            "拆股8根": "6 根已按比例修正,2 根(AMRS/PRTY)判不准、整只剔除",
            "★股数序列拆股闸": "engine/share_gate.py —— 单位闸 + 季度区间去重 + 拆股闸",
            "预热": "2016 起热机,2018-01-01 才计入绩效(Fama 1998)",
            "网格搜索": "没有。slots 三档 / 摩擦三档都是并列报的敏感度;"
                        "留一法只为定位瓶颈,不上报成绩",
        },
        "链": [],
    }

    print("=" * 78)
    print("★ 先算无槽位限制的纯信号笔数(对专家的 180~280 预期)")
    ps = pure_signal_trades(syms)
    for k, v in ps.items():
        print(f"    {k}:{v}")
    out["★无槽位限制的纯信号笔数"] = ps
    print()

    for name, raw, notes in vcp_variants():
        try:
            out["链"].append(run_one(name, raw, notes, syms))
        except Exception as e:
            print(f"★ {name} 跑挂了:{type(e).__name__}: {e}")
            out["链"].append({"链名": name, "★跑挂了": f"{type(e).__name__}: {e}",
                              "★必须讲清楚的前提": notes})

    # ★ 结论档笔数仍远低于 140 → 按任务书跑留一法定位
    main_n = next((c.get("笔数", 0) for c in out["链"]
                   if c.get("链名", "").endswith("slots10")), 0)
    if main_n < EXPECT_TRADES[0]:
        print("=" * 78)
        print(f"★ 结论档 {main_n} 笔 < {EXPECT_TRADES[0]} —— "
              f"按任务书跑留一法定位还有什么在误杀")
        loo = leave_one_out(syms)
        for r in loo["逐关"]:
            print(f"    {r['一次只去掉一关']:46s} 事件={r['③进场事件']:8d} "
                  f"过选股={r['③×①过选股范围']:7d}")
        for k, v in loo["④止损硬闸单独看"].items():
            print(f"    {k}:{v}")
        out["★留一法定位"] = loo
    else:
        out["★留一法定位"] = f"★ 没跑 —— 结论档 {main_n} 笔已达 {EXPECT_TRADES[0]} 以上"

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print()
    print(f"原始数字已写:{OUT_JSON}")
    print(f"交易流水已写:{LEDGER_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
