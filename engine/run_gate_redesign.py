"""
闸门新方案对照 G0..G4(2026-10-28)。

大白话:系统每天要决定「今天准不准开新仓」。这是个总开关。
旧方案用「全市场广度」当这个开关 —— 2018Q4 和 2022 救了命,2021 年多亏了一大截,
净值为零。新方案是三条改动:

  改动一 开关只由大盘长期方向决定(SPY ≥ SMA200×0.99 且 SMA200 的 20 日斜率 ≥ 0)
  改动二 广度降级成「风险预算标尺」—— 只管仓位,不管开关
  改动三 广度看★ 这条链自己的选股范围,不看全市场

五组对照(全部用流派一当载体 —— 它目前唯一能跑出样本):

  G0  只看 SPY 200 日线 + 20 日斜率                    ← 基准
  G1  G0 + 全市场广度当★ 开关(旧方案)
  G2  G0 + 全市场广度当★ 仓位标尺
  G3  G0 + ★ 本链自己范围的广度当★ 仓位标尺            ← 新方案
  G4  G0 + 本链自己范围的广度当★ 开关                  ← 拆解用

★★ 一件必须先讲清楚的事(不然下面的数会被读错):
  仓位标尺★ 不会改变每笔的 R 倍数 —— R 是价格口径(出场价−进场价)/(进场价−止损价),
  跟这一笔下多大无关。G0 和 G3 的成交明细是★ 一模一样的 225 笔,
  只有「每笔冒多少钱」不同。所以:
    · 比 G3 vs G0 不能用「每笔 R 的 Bootstrap」—— 那个尺子对仓位标尺是瞎的
    · 必须用 ① 组合净值层面的配对块重排检验 ② 风险加权 R = r_multiple × size_mult
  G1 / G4 是开关,会改变成交哪几笔,那两组可以照常用每笔 R 的判据。

★ 不许网格搜索:slots 三档 / 广度阈值三档(40/50/60)/ 减不减仓两版,
  全部是★ 并列报的敏感度,不许挑一个最好的当结论。

跑法:python -m engine.run_gate_redesign
"""

from __future__ import annotations

import copy
import json
import os
import time

import numpy as np
import pandas as pd
import yaml

from . import analyze, cache, chain, data, matrices, stats_gate, window_pool

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(HERE, "configs")
OUT_JSON = os.path.join(HERE, "results_1028_闸门新方案.json")
LEDGER_DIR = os.path.join(HERE, "ledgers_1028_闸门")

SLOTS = (3, 5, 10)
THRESHOLDS = (40.0, 50.0, 60.0)       # ★ 我们定的(敏感度展示),不是搜出来的
THR_MAIN = 50.0                       # 主报的那一档,★ 同样是我们定的
LOW_MULTS = (1.0, 0.5)                # ★「不减仓」和「减半」两版都要报
MIN_NAMES = 30                        # ★ 我们定的:范围不足 30 只时标尺不生效

OUR_CHOICE = "我们定的(敏感度展示)"


# ================================================================ 配置变体

def _base() -> dict:
    with open(os.path.join(CONFIG_DIR, "trend_following.yaml"), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def build_variant(group: str, slots: int, thr: float, low_mult: float) -> dict:
    """
    照 G0 的 regime 为底(改动一:开关只由大盘长期方向决定),按组加东西。
    ★ 不改 engine/configs/ 下的任何文件 —— 变体全部在内存里拼,
      免得和正在改配置的另一条线撞车。
    """
    raw = _base()
    raw["slots"] = slots
    raw["source_slots"] = f"{OUR_CHOICE} —— 专家两轮都没给流派一的持仓上限(审计 §2-E)"

    # G0 的 regime 就是 trend_following 原文那两条,这里确认一下没多余的
    kinds = [r.get("type") for r in raw["regime"]["rules"]]
    assert kinds == ["index_above_ma_scaled", "index_ma_slope"], kinds

    if group == "G0":
        pass

    elif group == "G1":       # 全市场广度当开关(旧方案)
        raw["regime"]["rules"].append({
            "type": "breadth_above",
            "field": "pct_above_ma50",
            "value": thr,
            "source": f"{OUR_CHOICE}:阈值 {thr:.0f}% 三档并列(40/50/60)",
        })

    elif group == "G4":       # 本链自己范围的广度当开关
        raw["regime"]["rules"].append({
            "type": "breadth_above_chain",
            "params": {"ma": 50, "value": thr, "min_names": MIN_NAMES},
            "source": f"{OUR_CHOICE}:阈值 {thr:.0f}% 三档并列;"
                      f"范围不足 {MIN_NAMES} 只时这道闸门不生效",
        })

    elif group in ("G2", "G3"):   # 广度当仓位标尺(G2 全市场 / G3 本链自己范围)
        raw["sizing"]["breadth_risk_scaler"] = {
            "source": "market" if group == "G2" else "chain",
            "field": "pct_above_ma50",
            "ma": 50,
            "threshold": thr,
            "low_risk_mult": low_mult,
            "min_names": MIN_NAMES,
            "source_note": f"{OUR_CHOICE}:★ 0.5 这个数外部专家没给出处,"
                           f"所以「不减仓 1.0」和「减半 0.5」两版都报",
        }
    else:
        raise ValueError(group)
    return raw


def variant_label(group: str, slots: int, thr: float, low_mult: float) -> str:
    if group == "G0":
        return f"G0_基准_slots{slots}"
    if group in ("G1", "G4"):
        return f"{group}_开关_thr{thr:.0f}_slots{slots}"
    return f"{group}_仓位标尺_thr{thr:.0f}_x{low_mult}_slots{slots}"


# ================================================================ 指标

def r_sums(led: pd.DataFrame) -> dict:
    """
    ★ 按「出场日」把 R 归到期间(盈亏在出场那天兑现)。
    ★ 风险加权 R = r_multiple × size_mult —— 仓位标尺只有在这个口径下才看得见。
    """
    if led.empty:
        return {}
    d = led.copy()
    d["exit_date"] = pd.to_datetime(d["exit_date"])
    d["w"] = d["r_multiple"] * d.get("size_mult", 1.0)
    out = {}
    for y, g in d.groupby(d["exit_date"].dt.year):
        out[str(int(y))] = {"R": float(g["r_multiple"].sum()),
                            "风险加权R": float(g["w"].sum()),
                            "笔数": int(len(g))}
    q4 = d[(d["exit_date"] >= "2018-10-01") & (d["exit_date"] <= "2018-12-31")]
    out["2018Q4"] = {"R": float(q4["r_multiple"].sum()),
                     "风险加权R": float(q4["w"].sum()), "笔数": int(len(q4))}
    out["全期"] = {"R": float(d["r_multiple"].sum()),
                   "风险加权R": float(d["w"].sum()), "笔数": int(len(d))}
    return out


def period_return(eq: pd.Series, start: str, end: str) -> float:
    s = eq[(eq.index >= pd.Timestamp(start)) & (eq.index <= pd.Timestamp(end))]
    if len(s) < 2:
        return float("nan")
    return float(s.iloc[-1] / s.iloc[0] - 1.0)


def paired_block_test(eq_a: pd.Series, eq_b: pd.Series,
                      B: int = stats_gate.B_DEFAULT,
                      seed: int = 20181028) -> dict:
    """
    ★ 组合净值层面的配对检验(A − B)。
    为什么需要它:仓位标尺不改每笔的 R,只改每笔下多大 ——
    「每笔 R 的 Bootstrap」对它是瞎的,必须在净值层面比。

    做法:取两条净值的日对数收益之差 d_t,用 Circular Block Bootstrap
    (Politis & Romano 1994,块长 n^(1/3))重抽 B 次,看 mean(d) 落在哪。
    ★ 全程不取随机分布的最大值。
    """
    a = np.log(eq_a / eq_a.shift(1)).dropna()
    b = np.log(eq_b / eq_b.shift(1)).dropna()
    idx = a.index.intersection(b.index)
    d = (a.reindex(idx) - b.reindex(idx)).to_numpy(float)
    d = d[np.isfinite(d)]
    if d.size < 30:
        return {"n日": int(d.size), "判定": "日数太少,算不了"}
    obs = float(d.mean())
    # 零假设:两条链没差别 → 把 d 去心化后块重排,看 |mean| 能有多大
    d0 = d - obs
    sampler = stats_gate.circular_block_sampler(d0, n_draw=d.size)
    rng = np.random.default_rng(seed)
    null = np.array([float(np.mean(sampler(rng))) for _ in range(B)])
    sd = float(null.std(ddof=1))
    z = obs / sd if sd > 0 else float("nan")
    p = (1 + int((null >= obs).sum())) / (B + 1)
    return {
        "n日": int(d.size),
        "日均对数收益差": round(obs, 8),
        "年化差(个百分点)": round(obs * 252 * 100, 3),
        "全期累计差(个百分点)": round(
            (float(eq_a.iloc[-1] / eq_a.iloc[0]) -
             float(eq_b.iloc[-1] / eq_b.iloc[0])) * 100, 3),
        "Z": round(z, 3) if np.isfinite(z) else None,
        "经验p": round(p, 4),
        "判定": ("基础显著(Z≥1.65)" if np.isfinite(z) and z >= stats_gate.Z_BASIC
                 else "不显著"),
        "B": B,
    }


def drop_year_test(led_sig: pd.DataFrame, led_ctrl: pd.DataFrame | None,
                   drop_year: int | None, B: int = stats_gate.B_DEFAULT) -> dict:
    """拿掉某一年之后,每笔 R 对「同环境随机进场」还显不显著(块重排口径)。"""
    def _f(led):
        if led is None or led.empty:
            return np.array([])
        d = led.copy()
        d["exit_date"] = pd.to_datetime(d["exit_date"])
        if drop_year is not None:
            d = d[d["exit_date"].dt.year != drop_year]
        return d["r_multiple"].dropna().to_numpy(float)

    sig, ctrl = _f(led_sig), _f(led_ctrl)
    if sig.size == 0:
        return {"n": 0, "判定": "没有样本"}
    if ctrl.size == 0:
        ctrl = sig
    r = stats_gate.bootstrap_test(
        f"块重排(拿掉{drop_year or '无'})", sig,
        stats_gate.circular_block_sampler(ctrl, n_draw=sig.size), B=B)
    return {"n": int(r.n_signal), "信号均值": round(float(r.signal_mean), 4),
            "随机均值": round(float(r.random_mean), 4),
            "Z": round(float(r.z_effect), 3) if np.isfinite(r.z_effect) else None,
            "p": round(float(r.p_empirical), 4),
            "判定": ("基础显著" if np.isfinite(r.z_effect)
                     and r.z_effect >= stats_gate.Z_BASIC else "不显著")}


# ================================================================ 跑一条

def run_variant(group: str, slots: int, thr: float, low_mult: float,
                syms: list[str], keep_ledger: bool = False) -> dict:
    label = variant_label(group, slots, thr, low_mult)
    raw = build_variant(group, slots, thr, low_mult)
    cfg = chain.ChainConfig.from_dict(raw)
    if not cfg.adapt_report.ok:
        raise RuntimeError(f"{label} 有没实现的规则,不许带着它跑:\n"
                           + cfg.adapt_report.text())
    m = matrices.build(cfg.raw, syms)
    res = chain.run_chain(cfg, syms, m=m)
    led = res.ledger
    eq = res.equity

    # ★ 开闸天数(绩效窗口内)
    perf = data.perf_window(m.index)
    pm = pd.Series(m.regime, index=m.index).reindex(perf)
    sm = pd.Series(m.size_mult, index=m.index).reindex(perf)

    mdd, under, trough = analyze.drawdown(eq)
    rec = {
        "标签": label, "组": group, "slots": slots,
        "广度阈值": thr if group != "G0" else None,
        "减仓乘数": low_mult if group in ("G2", "G3") else None,
        "笔数": int(len(led)),
        "净收益": round(float(eq.iloc[-1] / eq.iloc[0] - 1.0), 6),
        "毛收益": round(float(res.equity_gross.iloc[-1]
                             / res.equity_gross.iloc[0] - 1.0), 6),
        "CAGR净": round(analyze.cagr(eq), 6),
        "最大回撤": round(mdd, 6),
        "最长水下天数": int(under),
        "胜率": round(float((led["net_pnl"] > 0).mean()), 4) if len(led) else None,
        "每笔R毛": round(float(led["r_multiple"].mean()), 4) if len(led) else None,
        "每笔R扣摩擦": round(float(led["r_multiple_net"].mean()), 4) if len(led) else None,
        "每笔R毛_95CI": analyze._fmt_ci(analyze.ci95(led["r_multiple"]))
        if len(led) else None,
        "平均敞口": round(float(res.exposure.mean()), 4),
        "开闸天数": int(pm.sum()), "总交易日": int(len(pm)),
        "开闸比例": round(float(pm.mean()), 4),
        "★减半的天数(绩效窗口内)": int((sm < 1.0).sum()),
        "逐年净收益": {k: round(v, 6) for k, v in analyze.yearly_returns(eq).items()},
        "R归集": r_sums(led),
        "广度标尺诊断": m.breadth_diag,
        "执行器备注": res.notes,
    }
    if keep_ledger:
        os.makedirs(LEDGER_DIR, exist_ok=True)
        res.save_ledger(os.path.join(LEDGER_DIR, f"{label}.csv"))
    rec["_eq"] = eq
    rec["_led"] = led
    rec["_cfg"] = cfg
    return rec


def random_control_ledger(cfg: chain.ChainConfig, led: pd.DataFrame,
                          eq: pd.Series, syms: list[str]) -> pd.DataFrame | None:
    """同环境随机进场的对照流水(进场频率对齐真信号)。"""
    rate = max(1e-7, len(led) / max(1, len(eq)) / 100)
    c2 = cfg.copy_with(entry={"type": "random",
                              "params": {"rate": rate, "seed": 424242},
                              "source": "判据对照组:同环境随机进场"})
    try:
        return chain.run_chain(c2, syms).ledger
    except Exception:
        return None


# ================================================================ main

def main(argv=None) -> int:
    t_all = time.time()
    print(data.cohort_report())
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    print(f"\n全池 {len(syms)} 只,绩效窗口 {data.PERF_START} .. {data.PERF_END}"
          f"(2016 起热机)\n")

    out: dict = {
        "跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "全池只数": len(syms),
        "载体": "流派一_系统化中长周期趋势跟随(目前唯一能跑出样本的那条链)",
        "★我们定的参数": {
            "slots": f"3/5/10 三档并列 —— {OUR_CHOICE}",
            "广度阈值": f"40/50/60 三档并列,主报 {THR_MAIN:.0f}% —— {OUR_CHOICE}",
            "减仓乘数": f"1.0(不减仓)/ 0.5(减半)两版都报 —— "
                        f"0.5 这个数外部专家没给出处",
            "最少只数": f"{MIN_NAMES} 只 —— {OUR_CHOICE};范围不足时标尺/闸门不生效,"
                        f"而不是给一个不可信的广度数",
        },
        "★不是网格搜索": "三组敏感度全部并列报出,没有挑最好的那一档当结论",
        "主对照": [], "敏感度": [], "专项": {},
    }

    # ---------------- 主对照:thr=50,减半版,slots 三档 ----------------
    main_runs: dict[tuple, dict] = {}
    print("=" * 78)
    print(f"主对照(广度阈值 {THR_MAIN:.0f}%,减仓乘数 0.5,slots 三档并列)")
    for group in ("G0", "G1", "G2", "G3", "G4"):
        for s in SLOTS:
            rec = run_variant(group, s, THR_MAIN, 0.5, syms, keep_ledger=True)
            main_runs[(group, s)] = rec
            print(f"  {rec['标签']:34s} 笔数={rec['笔数']:4d} "
                  f"净收益={rec['净收益']:+8.2%} MDD={rec['最大回撤']:+7.2%} "
                  f"开闸={rec['开闸比例']:5.1%} 全期R={rec['R归集'].get('全期',{}).get('风险加权R',0):+7.1f}")

    # ---------------- 验证:减仓乘数 1.0 必须复现 G0 ----------------
    print("\n[验证] 仓位标尺「不减仓(×1.0)」必须和 G0 一模一样:")
    ident = []
    for group in ("G2", "G3"):
        for s in SLOTS:
            r1 = run_variant(group, s, THR_MAIN, 1.0, syms)
            g0 = main_runs[("G0", s)]
            same = (abs(r1["净收益"] - g0["净收益"]) < 1e-9
                    and r1["笔数"] == g0["笔数"])
            ident.append({"组": group, "slots": s, "净收益": r1["净收益"],
                          "G0净收益": g0["净收益"], "与G0完全一致": bool(same)})
            print(f"  {group} ×1.0 slots{s}: {r1['净收益']:+.6%} vs "
                  f"G0 {g0['净收益']:+.6%} → {'一致 ✅' if same else '★ 不一致!'}")
    out["专项"]["不减仓版等同于G0"] = {
        "说明": "★ 仓位标尺的「不减仓(×1.0)」在定义上就等于 G0 —— "
                "这两版不是两条不同的链。下面所有「减不减仓」的对比,"
                "等价于「G2/G3 减半版 vs G0」。这一点必须讲清楚,"
                "不然会被读成跑了两条新链。",
        "逐档验证": ident}

    # ---------------- 敏感度:阈值 40/60 ----------------
    print("\n" + "=" * 78)
    print("敏感度:广度阈值 40 / 50 / 60 三档并列(★ 不挑最好的)")
    for group in ("G1", "G2", "G3", "G4"):
        for thr in THRESHOLDS:
            for s in SLOTS:
                if thr == THR_MAIN and group in main_runs_groups():
                    rec = main_runs.get((group, s))
                    if rec is not None:
                        out["敏感度"].append(_strip(rec))
                        continue
                rec = run_variant(group, s, thr, 0.5, syms)
                out["敏感度"].append(_strip(rec))
                print(f"  {rec['标签']:34s} 笔数={rec['笔数']:4d} "
                      f"净收益={rec['净收益']:+8.2%} MDD={rec['最大回撤']:+7.2%} "
                      f"开闸={rec['开闸比例']:5.1%}")

    # ---------------- ① G3 vs G0:净值层面的配对检验 ----------------
    print("\n" + "=" * 78)
    print("① G3 vs G0(净值层面配对块重排;★ 每笔 R 的判据对仓位标尺是瞎的)")
    pair: dict = {}
    for group in ("G1", "G2", "G3", "G4"):
        for s in SLOTS:
            a, b = main_runs[(group, s)], main_runs[("G0", s)]
            full = paired_block_test(a["_eq"], b["_eq"])
            w1 = paired_block_test(
                a["_eq"][a["_eq"].index < "2022-01-01"],
                b["_eq"][b["_eq"].index < "2022-01-01"])
            w2 = paired_block_test(
                a["_eq"][a["_eq"].index >= "2022-01-01"],
                b["_eq"][b["_eq"].index >= "2022-01-01"])
            pair[f"{group}_slots{s}"] = {"全期": full, "2018-2021": w1,
                                         "2022-2025": w2}
            if group == "G3":
                print(f"  G3−G0 slots{s}: 全期 {full['全期累计差(个百分点)']:+6.2f}pp "
                      f"Z={full['Z']} p={full['经验p']} | "
                      f"18-21 Z={w1['Z']} | 22-25 Z={w2['Z']}")
    out["专项"]["①_各组减G0_净值配对检验"] = pair

    # ---------------- ② 拆解:换范围 vs 降级 ----------------
    print("\n" + "=" * 78)
    print("② 拆解:换范围(G4−G1)值多少 / 降级成仓位标尺(G2−G1)值多少")
    decomp = {}
    for s in SLOTS:
        g = {k: main_runs[(k, s)]["净收益"] for k in ("G0", "G1", "G2", "G3", "G4")}
        rg = {k: main_runs[(k, s)]["R归集"].get("全期", {}).get("风险加权R", float("nan"))
              for k in ("G0", "G1", "G2", "G3", "G4")}
        decomp[f"slots{s}"] = {
            "净收益": {k: round(v, 6) for k, v in g.items()},
            "全期风险加权R": {k: round(v, 2) for k, v in rg.items()},
            "换范围 G4−G1(pp)": round((g["G4"] - g["G1"]) * 100, 2),
            "降级成仓位标尺 G2−G1(pp)": round((g["G2"] - g["G1"]) * 100, 2),
            "两个都做 G3−G1(pp)": round((g["G3"] - g["G1"]) * 100, 2),
            "G3−G0(pp)": round((g["G3"] - g["G0"]) * 100, 2),
        }
        d = decomp[f"slots{s}"]
        print(f"  slots{s}: 换范围 {d['换范围 G4−G1(pp)']:+7.2f}pp | "
              f"降级 {d['降级成仓位标尺 G2−G1(pp)']:+7.2f}pp | "
              f"两个都做 {d['两个都做 G3−G1(pp)']:+7.2f}pp | "
              f"G3−G0 {d['G3−G0(pp)']:+7.2f}pp")
    out["专项"]["②_换范围与降级各值多少"] = decomp

    # ---------------- ③ 三段关键期:2018Q4 / 2021 / 2022 ----------------
    print("\n" + "=" * 78)
    print("③ 三段关键期(★ 用风险加权R,仓位标尺只有这个口径下才看得见)")
    key = {}
    for s in SLOTS:
        row = {}
        for k in ("G0", "G1", "G2", "G3", "G4"):
            rs = main_runs[(k, s)]["R归集"]
            eq = main_runs[(k, s)]["_eq"]
            row[k] = {
                "2018Q4_风险加权R": round(rs.get("2018Q4", {}).get("风险加权R", 0.0), 2),
                "2021_风险加权R": round(rs.get("2021", {}).get("风险加权R", 0.0), 2),
                "2022_风险加权R": round(rs.get("2022", {}).get("风险加权R", 0.0), 2),
                "2018Q4_收益": round(period_return(eq, "2018-10-01", "2018-12-31"), 6),
                "2021_收益": round(period_return(eq, "2021-01-01", "2021-12-31"), 6),
                "2022_收益": round(period_return(eq, "2022-01-01", "2022-12-31"), 6),
            }
        for k in ("G1", "G2", "G3", "G4"):
            for per in ("2018Q4", "2021", "2022"):
                row[k][f"{per}_相对G0的风险加权R"] = round(
                    row[k][f"{per}_风险加权R"] - row["G0"][f"{per}_风险加权R"], 2)
        key[f"slots{s}"] = row
        print(f"  slots{s} 相对 G0 的风险加权R: " + " | ".join(
            f"{k} 18Q4 {row[k]['2018Q4_相对G0的风险加权R']:+6.1f} "
            f"21 {row[k]['2021_相对G0的风险加权R']:+6.1f} "
            f"22 {row[k]['2022_相对G0的风险加权R']:+6.1f}"
            for k in ("G1", "G3")))
    out["专项"]["③_2018Q4_2021_2022"] = key

    # ---------------- ④ 两窗口两池子硬关:G3 与 G0 ----------------
    print("\n" + "=" * 78)
    print("④ 两窗口两池子硬关(G0 与 G3 各三档)")
    hard = {}
    from .run_batch import window_pool_gate
    for group in ("G0", "G3"):
        for s in SLOTS:
            cfg = main_runs[(group, s)]["_cfg"]
            v = window_pool_gate(cfg, syms)
            hard[f"{group}_slots{s}"] = {
                "通过": bool(v.passed), "理由": list(v.reasons),
                "降级结论": v.downgraded_conclusion,
                "四格": [{"格": c.key, "n": int(c.result.n_signal),
                          "差值": round(float(c.result.diff), 4),
                          "Z": round(float(c.result.z_effect), 3)
                          if np.isfinite(c.result.z_effect) else None}
                         for c in v.cells]}
            print(f"  {group} slots{s}: {'过' if v.passed else '★ 没过'} — "
                  + ", ".join(f"{c.key} Z={c.result.z_effect:+.2f}" for c in v.cells))
    out["专项"]["④_两窗口两池子硬关"] = hard

    # ---------------- ⑤ 拿掉 2021 年 ----------------
    print("\n" + "=" * 78)
    print("⑤ 拿掉 2021 年之后,G3 还剩多少")
    drop = {}
    for s in SLOTS:
        g3, g0 = main_runs[("G3", s)], main_runs[("G0", s)]
        # 净值层面:把 2021 整年挖掉,把 2018-2020 和 2022-2025 两段的日收益接起来
        def _ex2021(eq):
            lr = np.log(eq / eq.shift(1)).dropna()
            return lr[lr.index.year != 2021]
        a, b = _ex2021(g3["_eq"]), _ex2021(g0["_eq"])
        idx = a.index.intersection(b.index)
        ea = pd.Series(np.exp(np.cumsum(a.reindex(idx).to_numpy())), index=idx)
        eb = pd.Series(np.exp(np.cumsum(b.reindex(idx).to_numpy())), index=idx)
        t_no21 = paired_block_test(ea, eb)
        ctrl = random_control_ledger(g3["_cfg"], g3["_led"], g3["_eq"], syms)
        drop[f"slots{s}"] = {
            "★G3−G0_拿掉2021": t_no21,
            "G3每笔R_含2021": drop_year_test(g3["_led"], ctrl, None),
            "G3每笔R_拿掉2021": drop_year_test(g3["_led"], ctrl, 2021),
            "G3_2021那一年的风险加权R": round(
                g3["R归集"].get("2021", {}).get("风险加权R", 0.0), 2),
            "G0_2021那一年的风险加权R": round(
                g0["R归集"].get("2021", {}).get("风险加权R", 0.0), 2),
        }
        print(f"  slots{s}: 拿掉2021后 G3−G0 累计差 "
              f"{t_no21.get('全期累计差(个百分点)')}pp Z={t_no21.get('Z')} "
              f"p={t_no21.get('经验p')}")
    out["专项"]["⑤_拿掉2021年"] = drop

    # ---------------- 收尾 ----------------
    out["主对照"] = [_strip(main_runs[(g, s)])
                     for g in ("G0", "G1", "G2", "G3", "G4") for s in SLOTS]
    out["引擎显式关掉的东西"] = matrices.disabled_log()
    out["★仍然拿不到的东西"] = [
        "无风险利率序列(基准二的现金腿按 0% 记,仓库只有 TLT 长债 ETF)",
        "MDY 中盘指数(本轮没用到,component_match: large → SPY)",
        "分红复权(所有收益都是价格口径,全池系统性低估)",
    ]
    out["耗时秒"] = round(time.time() - t_all, 1)

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
    print(f"\n原始数字已写:{OUT_JSON}")
    print(f"交易流水已写:{LEDGER_DIR}/")
    print(f"总耗时 {out['耗时秒']} 秒")
    return 0


def main_runs_groups():
    return ("G1", "G2", "G3", "G4")


def _strip(rec: dict) -> dict:
    return {k: v for k, v in rec.items() if not k.startswith("_")}


if __name__ == "__main__":
    raise SystemExit(main())
