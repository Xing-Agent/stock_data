"""
第一批真实结果:流派一(slots 三档敏感度)+ 流派二(松端 / 紧端两版)。

大白话:这个脚本把「要跑的三组」一次跑完,每条链都吐出同一套东西
(绝对表现 / 两条基准线 / 判据 / 两窗口两池子硬关 / 代价 / 执行负荷 /
摩擦三档 / 分步归因 / 跳空统计 / 信号漏斗),原始数字写成 json。

★★ 三件要讲清楚的事(都不是网格搜索):
  一、流派一的 slots 跑 3 / 5 / 10 三档,是★ 敏感度展示 ——
      专家两轮都没给持仓上限,我们不许自己挑一个「最好的」。
  二、流派二跑松端 / 紧端两版,两端★ 都来自原著给的区间
      (O'Neil 7~8% / Minervini 一半~三分之二 / 低 40%~50%),
      报的是★ 区间两端的差异,不是在挑一个好看的。
  三、摩擦三档(5/15/30bp)是强制同时报的,不是在选成本。

跑法:python -m engine.run_batch
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
OUT_JSON = os.path.join(HERE, "results_1028_流派一二.json")
LEDGER_DIR = os.path.join(HERE, "ledgers_1028")


# ================================================================ 配置变体

def _load(name: str) -> dict:
    with open(os.path.join(CONFIG_DIR, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def trend_variants() -> list[tuple[str, dict, list[str]]]:
    """流派一:slots 三档。★ 敏感度展示,不是挑最优。"""
    out = []
    for s in (3, 5, 10):
        raw = _load("trend_following.yaml")
        raw["slots"] = s
        # ★ 纪律 6:填了数就得标出处。这里明确标成「我们定的(敏感度展示)」
        raw["source_slots"] = "我们定的(敏感度展示)—— 专家两轮都没给流派一的持仓上限"
        notes = [
            f"slots={s} ★ 是我们定的,source: 我们定的(敏感度展示)。"
            f"专家两轮都没给流派一的持仓上限(审计 §2-E),"
            f"所以三档一起报,★ 这不是我们挑的最优值。",
        ]
        out.append((f"流派一_趋势跟随_slots{s}", raw, notes))
    return out


# 松端 / 紧端的三个数(★ 两端都来自原著给的区间)
LOOSE_TIGHT = {
    "松端(专家给的)": {"max_stop_pct": 8.0, "decay": 0.65, "dryup": 0.60},
    "紧端(原著另一端)": {"max_stop_pct": 7.0, "decay": 0.50, "dryup": 0.50},
}


def _vcp_base() -> tuple[dict, list[str]]:
    """流派二的公共改动:关掉非 PIT 的行业 RS、去掉定义未定的「滞涨换血」。"""
    raw = _load("vcp_momentum.yaml")
    notes: list[str] = []

    # ① 行业 RS(非 PIT)—— 显式关掉,★ 不是悄悄忽略
    for r in raw["universe"]["rules"]:
        for c in (r.get("components") or []):
            if (c.get("type") == "mansfield_rs_positive"
                    and str((c.get("params") or {}).get("against")) == "SECTOR"):
                c["enabled"] = False
    notes.append(
        "★ 关掉了「宏观基底_行业 RS」:仓库只有 "
        "sector_classification_current_non_pit.csv(元数据自承非 PIT),"
        "用今天的行业标签跑 2016 年整段都在用未来信息;且 XLC/XLRE "
        "在 2016–2018 根本没数据。配置里本来就留了 "
        "variant_without_rs_sector 开关(审计 §3-C)。")

    # ② ⑤ 的「滞涨换血」—— 换血条件没定义,这一阶段关掉
    before = len(raw["stop_trail"]["stages"])
    raw["stop_trail"]["stages"] = [s for s in raw["stop_trail"]["stages"]
                                   if s.get("action") != "rotate_out"]
    assert len(raw["stop_trail"]["stages"]) == before - 1
    notes.append(
        "★★ 关掉了 ⑤「15 日滞涨换血」:触发条件"
        "「备选池有新高动量信号」没有定义(新高是几日新高?动量怎么比?"
        "审计 §2-C),不能猜。★ 而换血是专家宣称的三大改进之一 —— "
        "★ 所以这一版不是完整的这一派。")
    return raw, notes


def vcp_variants() -> list[tuple[str, dict, list[str]]]:
    """流派二:松端版 + 紧端版。slots 照用专家给的 5。"""
    out = []
    for label, v in LOOSE_TIGHT.items():
        raw, notes = _vcp_base()
        # ④ 初始止损硬闸:O'Neil「7~8%」的哪一端
        raw["stop_init"]["hard_gate"]["params"]["max_pct"] = v["max_stop_pct"]
        for r in raw["entry"]["rules"]:
            if r.get("type") == "vcp_contraction":
                # Minervini 收缩「约为前一半 ~ 三分之二」的哪一端
                r["params"]["decay_coefficient"] = v["decay"]
            if r.get("type") == "volume_dryup":
                # Minervini 缩量「低于 50 日均量 40% ~ 50%」的哪一端
                r["params"]["max_ratio"] = v["dryup"]
        notes.insert(0,
                     f"★ 本版 = {label}:止损硬闸 {v['max_stop_pct']}% · "
                     f"收缩递减 {v['decay']} · 缩量 {v['dryup']}。"
                     f"★ 两端都取自原著给的区间(O'Neil 7~8% / "
                     f"Minervini 一半~三分之二 / 低 40%~50%),"
                     f"★ 报的是区间两端的差异,不是在挑一个好看的。")
        notes.append("slots=5 ★ 照用专家给的值(审计里标的是行业惯例)。")
        out.append((f"流派二_VCP_{label}", raw, notes))
    return out


# ================================================================ 信号漏斗
# ★ 链跑出来笔数很少时,「少在哪一步」比「成绩多少」重要得多。

def signal_funnel(raw: dict, syms: list[str], start: str) -> dict:
    """逐条数每一关之后还剩多少个 [日 × 票] 单元,以及事件化之后剩多少。"""
    idx = cache.field("close", syms).index
    perf = np.asarray(idx >= pd.Timestamp(start))
    tot = int(perf.sum()) * len(syms)

    def n(df):
        a = np.asarray(df.to_numpy(bool))
        return int(a[perf, :].sum())

    rows, cum = [], None
    for r in (raw.get("universe", {}).get("rules") or []):
        m = matrices._universe_rule_mask(r, syms, idx)
        cum = m if cum is None else cum & m
        rows.append({"关": "① " + str(r.get("type")), "单条": n(m), "累计": n(cum)})
    uni = cum
    reg = matrices.regime_mask(raw.get("regime") or {}, idx)
    rows.append({"关": "② regime(开闸天数/总天数)",
                 "单条": int(np.asarray(reg.to_numpy(bool))[perf].sum()),
                 "累计": int(perf.sum())})
    cum2 = None
    for r in (raw.get("entry", {}).get("rules") or []):
        m = matrices._entry_rule_raw(r, syms)
        cum2 = m if cum2 is None else cum2 & m
        rows.append({"关": "③ " + str(r.get("type")), "单条": n(m), "累计": n(cum2)})
    ev = matrices._event_only(cum2)
    rows.append({"关": "③ 事件化(只在转折那天触发)", "单条": n(ev), "累计": n(ev)})
    rows.append({"关": "③ × ① 选股范围", "单条": n(ev & uni), "累计": n(ev & uni)})
    return {"全池单元数": tot, "逐关": rows}


# ================================================================ 两窗口两池子硬关

def window_pool_gate(cfg: chain.ChainConfig, syms: list[str],
                     B: int = stats_gate.B_DEFAULT) -> window_pool.WindowPoolVerdict:
    """
    四格各跑一遍真链 + 同格内的随机进场对照。
    ★ 对照必须在同格内取样 —— 用别格的票当对照等于偷看。
    """
    def signal_fn(start, end, cell_syms):
        cell_syms = [s for s in cell_syms if s in cache.symbols()]
        try:
            r = chain.run_chain(cfg, cell_syms, start, end)
            vals = r.ledger["r_multiple"].dropna().to_numpy(float)
        except Exception:
            vals = np.array([])
        if vals.size == 0:
            return [], (lambda rng: np.array([np.nan]))
        rate = max(1e-7, min(1.0, vals.size / max(1, len(r.equity) * len(cell_syms))))
        c2 = cfg.copy_with(entry={"type": "random",
                                  "params": {"rate": rate, "seed": 20181001},
                                  "source": "同格内随机进场对照"})
        try:
            ctrl = chain.run_chain(c2, cell_syms, start, end
                                   ).ledger["r_multiple"].dropna().to_numpy(float)
        except Exception:
            ctrl = np.array([])
        if ctrl.size == 0:
            ctrl = vals
        return list(vals), stats_gate.circular_block_sampler(ctrl, n_draw=vals.size)

    return window_pool.run_grid(signal_fn, syms, B=B)


# ================================================================ 跑一条链

def _num(x):
    """把 numpy / pandas 的东西转成能写进 json 的东西。"""
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating, float)):
        f = float(x)
        return None if not np.isfinite(f) else round(f, 6)
    if isinstance(x, (np.bool_, bool)):
        return bool(x)
    if isinstance(x, pd.DataFrame):
        return json.loads(x.reset_index().to_json(orient="records", force_ascii=False))
    if isinstance(x, pd.Series):
        return {str(k): _num(v) for k, v in x.items()}
    if isinstance(x, dict):
        return {str(k): _num(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_num(v) for v in x]
    if isinstance(x, stats_gate.GateVerdict):
        return {"通过": bool(x.passed), "级别": x.level,
                "理由": list(x.reasons),
                "三套对照组": {k: {"n": int(r.n_signal), "信号均值": _num(r.signal_mean),
                                   "随机均值": _num(r.random_mean),
                                   "σ随机": _num(r.random_std),
                                   "p": _num(r.p_empirical), "Z": _num(r.z_effect),
                                   "级别": r.level}
                               for k, r in x.results.items()}}
    if isinstance(x, window_pool.WindowPoolVerdict):
        return {"通过": bool(x.passed), "理由": list(x.reasons),
                "降级结论": x.downgraded_conclusion,
                "四格": [{"格": c.key, "n": int(c.result.n_signal),
                          "差值": _num(c.result.diff), "Z": _num(c.result.z_effect),
                          "p": _num(c.result.p_empirical)} for c in x.cells]}
    return x


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
    print(f"  笔数 {n}")
    out = analyze.evaluate(cfg, res, syms,
                           with_attribution=True, with_sensitivity=True,
                           with_gate=True)
    gate4 = window_pool_gate(cfg, syms)
    print("  " + gate4.report().replace("\n", "\n  "))

    # ★ 坑:胜率 >60% 或每笔 >+0.5R → 先停下来查吊灯止损那个坑
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
        "样本量够不够": ("够" if n >= stats_gate.MIN_N
                        else f"★ 不够(n={n} < {stats_gate.MIN_N})—— 任何结论都要打问号"),
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


# ================================================================ main

def main(argv=None) -> int:
    print(data.cohort_report())
    print()
    syms = data.full_universe().pool("ALL")
    syms = [s for s in syms if s in cache.symbols()]
    print(f"全池 {len(syms)} 只,绩效窗口 {data.PERF_START} .. {data.PERF_END}")
    print()

    all_variants = trend_variants() + vcp_variants()
    out = {"跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
           "全池只数": len(syms),
           "绩效窗口": f"{data.PERF_START} .. {data.PERF_END}(2016 起热机)",
           "硬纪律落点": {
               "退市破产按−100%": sorted(
                   s for s in syms
                   if data.load_manifest()[s].is_bankruptcy),
               "拆股8根": "6 根已按比例修正(修正后跳变 0.97~1.02x),"
                           "2 根(AMRS/PRTY)判不准、整只剔除",
               "预热": "2016 起热机,2018-01-01 才计入绩效(Fama 1998)",
               "网格搜索": "没有。slots 三档=敏感度展示;松紧两端都来自原著区间;"
                            "摩擦三档=强制报的",
           },
           "链": []}
    for name, raw, notes in all_variants:
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
