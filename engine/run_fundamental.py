"""
基本面两条链的真实结果(2026-10-29)。

  ★ A  cashflow_discipline.yaml  流派三 自由现金流与资本配置纪律派
  ★ B  deep_value.yaml           流派一 资产负债表与深度价值派

跑法:python -m engine.run_fundamental            # 两条链 × slots 三档
      python -m engine.run_fundamental A         # 只跑 A
      python -m engine.run_fundamental --loo     # 只做留一法瓶颈诊断

================== ★★ 跑之前对配置做的改动,一条不漏 ==================
★ 规矩:**一个数值都不改**。改动只有三类 —— (a) 把「配置写了、引擎没法执行」
  的规则显式关掉(不许悄悄忽略);(b) 填一个明确标成「占位、不是策略」的排序;
  (c) slots 三档敏感度。每一条都会原样打进报告。

A(流派三)
  A-1 ★ 关掉 ① no_large_equity_issuance —— 「大规模增发」的阈值专家原文没给
      (配置自己标了 undefined_param)。★ 不许借用 ⑥ 那条 2.0% 稀释线顶上。
  A-2 ★ 去掉 ③ 突破扳机的 volume_confirm: moderate —— 「温和放量」的量比区间
      专家原文没给。★ 流派二那边专家给过 [1.00,1.80],但那是另一条链的参数,
      ★ 不许跨链搬。
  → ★★ 所以 A 跑出来的也**不是完整的这一派**:① 少一道闸、③ 少放量确认。
       (审计报告说 A 是「三派里唯一能完整跑的」,指的是**数据**能不能算;
        ★ 实跑下来发现还有两处**参数未定**,这是本轮新发现的,必须写进报告。)

B(流派一)
  B-1 配置自己已关掉:① EV/EBITDA、① Altman Z''、② HYG/LQD 信用闸门、
      ★★ ⑥ EV/EBITDA 修复离场 —— ★ 止盈那一步被拆了。
  → ★★ 所以 B 跑出来的不是完整的这一派(报告顶部必须写这句)。

两条链共同
  C-1 ★ ranking 是 null(专家三轮没给)→ 用「ADV20 降序」当**占位排序**。
      ★ 这不是策略的一部分。槽位不够时买哪几只由它决定,结论对它敏感。
  C-2 slots 三档并列:★ 配置里那一档为主,另两档作敏感度(不是挑最优)。
=========================================================================
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import yaml

from . import (analyze, cache, chain, data, fundamentals, matrices,
               stats_gate, window_pool)
from .run_batch import _num, signal_funnel, window_pool_gate

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(HERE, "configs")
OUT_JSON = os.path.join(HERE, "results_1029_基本面流派一三.json")
LEDGER_DIR = os.path.join(HERE, "ledgers_1029_基本面")

#: ★ 占位排序 —— 明确标成「不是策略的一部分」
PLACEHOLDER_RANKING = {
    "primary": {"formula": "ADV20", "order": "desc"},
    "tiebreak": "symbol",
    "source": "★ 占位排序(不是策略的一部分)—— 专家三轮未给这两派的排序规则。"
              "选 ADV20 的理由:PIT 干净、两条链口径统一、覆盖率 100%,"
              "不会让「有基本面数据的票」系统性排在前面。见审计报告拍板第 2 条。",
}


def _load(name: str) -> dict:
    with open(os.path.join(CONFIG_DIR, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ================================================================ 配置变体

def cashflow_variants(slots_list=(5, 10, 20)) -> list:
    out = []
    for s in slots_list:
        raw = _load("cashflow_discipline.yaml")
        notes = []

        # A-1 ★ 关掉「无大规模增发」闸门
        for r in raw["universe"]["rules"]:
            if r.get("type") == "no_large_equity_issuance":
                r["enabled"] = False
                r["data_missing"] = False
                r["audit_blocked"] = "阈值未定(「大规模增发」专家原文没给)"
        notes.append(
            "★ A-1 关掉了 ①「过去 4 季度无大规模增发融资」—— 「大规模」的阈值"
            "专家原文没给(配置自己标了 undefined_param)。★ 不许借用 ⑥ 那条"
            "2.0% 稀释线顶上:那是另一步的参数,跨步搬过来等于我们自己定了"
            "一个闸门还假托有出处。★ 所以这一版 ① 少一道闸。")

        # A-2 ★ 去掉突破扳机的「温和放量」
        for r in raw["entry"]["rules"]:
            if r.get("type") == "donchian_close_breakout":
                r["params"].pop("volume_confirm", None)
        notes.append(
            "★ A-2 去掉了 ③ 突破扳机的 volume_confirm: moderate —— 「温和放量」"
            "的量比区间专家原文没给。★ 流派二那边专家给过 [1.00,1.80],"
            "★ 但那是另一条链的参数,不许跨链搬。★ 所以这一版的突破没有放量确认。")

        notes.append(
            "★★ 结论口径:A 跑出来的**不是完整的这一派** —— "
            "① 的「净股东回报率」闸门数据上根本算不出(腿三没有偿债现金流科目)、"
            "① 的「无大规模增发」闸门阈值未定、③ 没有放量确认。"
            "★ 资本配置纪律(Thorndike 那一半)在 ① 里整个没了,"
            "只在 ⑥ 的清仓规则里还留着。")

        raw["ranking"] = copy.deepcopy(PLACEHOLDER_RANKING)
        notes.append("★ C-1 " + PLACEHOLDER_RANKING["source"])

        raw["slots"] = s
        tag = "★主档(配置原值)" if s == 10 else "敏感度档"
        notes.append(f"★ C-2 slots={s}({tag})。配置原值 10 是专家明给的"
                     f"「最多 10 只」;另两档只做敏感度,★ 不是挑最优。")
        out.append((f"流派三_现金流纪律_slots{s}", raw, notes, s == 10))
    return out


def deep_value_variants(slots_list=(12, 15, 24)) -> list:
    out = []
    for s in slots_list:
        raw = _load("deep_value.yaml")
        notes = [
            "★★ B-1 这一版**不是完整的这一派**:缺了第⑥步的估值修复离场 "
            "(EV/EBITDA 修复至前 40% 就卖)—— EV/EBITDA 算不出(EBIT+D&A 覆盖率"
            "只有 13.6%),★ 所以止盈那一步被拆了,主动离场只剩 F-Score < 4 "
            "和那条来源存疑的 180 日时间止损。",
            "★ B-1 配置自己还关掉了:① EV/EBITDA 排名、① Altman Z''"
            "(科目齐备率不够 + 系数版本未定)、② HYG/LQD 信用闸门(仓库没有这两条线)。"
            "★ ① 三道基本面闸门只剩 Piotroski F-Score 一条。",
            "★ ③「跌破后强力收复」的强度口径专家原文没给。引擎用的是**唯一不含"
            "自由参数的机械读法**:当日最低跌破前 20 日最低、当日收盘又收回其上。"
            "★ 这是我们的读法,不是专家给的口径 —— 待确认。",
        ]
        raw["ranking"] = copy.deepcopy(PLACEHOLDER_RANKING)
        notes.append("★ C-1 " + PLACEHOLDER_RANKING["source"])
        raw["slots"] = s
        tag = "★主档(配置原值)" if s == 12 else "敏感度档"
        notes.append(
            f"★ C-2 slots={s}({tag})。配置原值 12 是专家给的区间「12–15 只」的"
            f"**紧端**(我们主动取紧端,为的是验出松端是不是在放水);"
            f"15 是区间另一端;24 是更松的一档。★ 三档并列,不是挑最优。")
        out.append((f"流派一_深度价值_slots{s}", raw, notes, s == 12))
    return out


# ================================================================ 留一法瓶颈诊断

def _strip_rule(raw: dict, step: str, rtype: str) -> dict:
    c = copy.deepcopy(raw)
    c[step]["rules"] = [r for r in c[step]["rules"] if r.get("type") != rtype]
    if not c[step]["rules"]:
        c[step]["rules"] = []
    return c


def leave_one_out(name: str, raw: dict, syms: list[str]) -> list[dict]:
    """
    ★ 留一法:逐条去掉条件看笔数怎么变 —— 笔数不够时,「少在哪一步」
      比「成绩多少」重要得多。

    ★ 注意这里报的是「去掉这一条之后笔数变成多少」,
      ★ 不是在搜一个更好的配置 —— 去掉条件的版本一律**不报成绩**,只报笔数。
    """
    rows = []
    base = chain.ChainConfig.from_dict(copy.deepcopy(raw))
    n0 = len(chain.run_chain(base, syms).ledger)
    rows.append({"去掉的条件": "(完整链,基准)", "笔数": n0, "笔数变化": 0})

    cand = []
    for r in (raw.get("universe", {}).get("rules") or []):
        if r.get("enabled", True) is not False:
            cand.append(("universe", r["type"]))
    for r in (raw.get("regime", {}).get("rules") or []):
        if r.get("enabled", True) is not False:
            cand.append(("regime", r["type"]))
    for r in (raw.get("entry", {}).get("rules") or []):
        if r.get("enabled", True) is not False:
            cand.append(("entry", r["type"]))

    for step, rtype in cand:
        c = _strip_rule(raw, step, rtype)
        if step == "entry" and not c["entry"]["rules"]:
            c["entry"] = {"type": "always", "source": "留一法:去掉全部进场条件"}
        try:
            cfg = chain.ChainConfig.from_dict(c)
            n = len(chain.run_chain(cfg, syms).ledger)
            rows.append({"去掉的条件": f"{step}.{rtype}", "笔数": n,
                         "笔数变化": n - n0})
        except Exception as e:
            rows.append({"去掉的条件": f"{step}.{rtype}", "笔数": None,
                         "笔数变化": None, "报错": f"{type(e).__name__}: {e}"})
    # ★ 额外一档:同时去掉基本面闸门(看基本面到底卡掉多少)
    fund_types = {"fcf_yield_rank_top", "sloan_accrual_below",
                  "piotroski_f_score_above"}
    c = copy.deepcopy(raw)
    kept = [r for r in c["universe"]["rules"] if r.get("type") not in fund_types]
    if len(kept) != len(c["universe"]["rules"]):
        c["universe"]["rules"] = kept
        try:
            cfg = chain.ChainConfig.from_dict(c)
            n = len(chain.run_chain(cfg, syms).ledger)
            rows.append({"去掉的条件": "★ 一次去掉全部基本面闸门", "笔数": n,
                         "笔数变化": n - n0})
        except Exception as e:
            rows.append({"去掉的条件": "★ 一次去掉全部基本面闸门",
                         "报错": f"{type(e).__name__}: {e}"})
    return rows


# ================================================================ 持仓周期 / 批次

def batch_stats(res, perf_days: int) -> dict:
    """
    ★ 任务书第②问:基本面链持仓周期长得多,「笔数」可能不是合适的度量。

    报三件事:
      · 平均 / 中位 持仓交易日
      · ★ 八年总共能开几批 = 绩效窗口交易日数 / 平均持仓天数
        (一个槽位八年能轮几次 —— 这才是「独立机会」的个数)
      · ★ 有效独立样本数 ≈ 槽位数 × 批数(并行槽位之间不独立,所以是上限)
    """
    led = res.ledger
    if led.empty:
        return {"说明": "没有成交"}
    hd = led["holding_days"].astype(float)
    avg = float(hd.mean())
    rounds = perf_days / avg if avg > 0 else float("nan")
    # 每个日历年有多少笔出场 —— 看机会是不是集中在某几年
    by_year = led.groupby(pd.to_datetime(led["exit_date"]).dt.year).size()
    return {
        "平均持仓(交易日)": avg,
        "中位持仓(交易日)": float(hd.median()),
        "最长持仓(交易日)": int(hd.max()),
        "最短持仓(交易日)": int(hd.min()),
        "★ 一个槽位八年能轮几批": rounds,
        "★ 槽位数 × 批数(独立机会上限)": None,     # 由调用方填 slots
        "逐年出场笔数": {str(k): int(v) for k, v in by_year.items()},
        "绩效窗口交易日数": perf_days,
    }


# ================================================================ 跑一条链

def run_one(name: str, raw: dict, notes: list[str], is_main: bool,
            syms: list[str], with_loo: bool = False) -> dict:
    t0 = time.time()
    print("=" * 78)
    print(f"跑链:{name}" + ("   ★ 主档" if is_main else ""))
    for nt in notes:
        print("  ⚠ " + nt)

    cfg = chain.ChainConfig.from_dict(copy.deepcopy(raw))
    rep = cfg.adapt_report
    print("  " + rep.text().replace("\n", "\n  "))
    if not rep.ok:
        raise RuntimeError(f"{name} 还有没实现的规则,★ 不许带着它跑:\n" + rep.text())

    funnel = signal_funnel(raw, [s for s in syms if s in cache.symbols()],
                           data.PERF_START)
    print("  [信号漏斗]")
    for r in funnel["逐关"]:
        print(f"    {r['关']:46s} 单条={r['单条']:9d} 累计={r['累计']:9d}")

    res = chain.run_chain(cfg, syms)
    res.save_ledger(os.path.join(LEDGER_DIR, f"{name}.csv"))
    n = len(res.ledger)
    print(f"  笔数 {n}")

    out = analyze.evaluate(cfg, res, syms, with_attribution=is_main,
                           with_sensitivity=is_main, with_gate=True)
    gate4 = window_pool_gate(cfg, syms) if is_main else None
    if gate4 is not None:
        print("  " + gate4.report().replace("\n", "\n  "))

    alarm = []
    if n:
        wr = float((res.ledger["net_pnl"] > 0).mean())
        rbar = float(res.ledger["r_multiple"].mean())
        if wr > 0.60 or rbar > 0.5:
            alarm.append(f"★★ 征兆警报:胜率 {wr:.1%} / 每笔R {rbar:+.3f} —— "
                         f"吊灯止损那个坑必须复查")
        print("  出场原因分布:" + ", ".join(
            f"{k}={v}" for k, v in res.ledger["reason"].value_counts().items()))

    bs = batch_stats(res, len(res.equity))
    slots = int((cfg.get("sizing") or {}).get("params", {}).get("max_positions", 0))
    if "★ 一个槽位八年能轮几批" in bs:
        bs["★ 槽位数 × 批数(独立机会上限)"] = slots * bs["★ 一个槽位八年能轮几批"]

    rec = {
        "链名": name,
        "★是否主档": is_main,
        "slots": slots,
        "★必须讲清楚的前提": notes,
        "适配层报告": rep.text(),
        "笔数": n,
        "样本量够不够": ("够" if n >= stats_gate.SYSTEM_MIN_TRADES
                        else f"★★ 不够(n={n} < {stats_gate.SYSTEM_MIN_TRADES})"),
        "★样本不足警示": analyze.sample_size_banner(n),
        "信号漏斗": funnel,
        "★持仓周期与批次": _num(bs),
        "出场原因分布": ({str(k): int(v) for k, v in
                          res.ledger["reason"].value_counts().items()} if n else {}),
        "绝对表现": _num(out["绝对表现"]),
        "坑一_现金拖累": _num(out["坑一_现金拖累"]),
        "坑二_跳空穿透止损": _num(out["坑二_跳空穿透止损"]),
        "代价": _num(out["代价"]),
        "执行负荷": _num(out["执行负荷"]),
        "摩擦成本": _num(out["摩擦成本"]),
        "基准一_同环境随机进场": _num(out["基准一_同环境随机进场"]),
        "基准二_同等仓位大盘": _num(out["基准二_同等仓位大盘"]),
        "判据_三套对照组": _num(out["判据"]),
        "★两窗口两池子硬关": _num(gate4) if gate4 is not None else "只对主档跑",
        "分步归因": _num(out.get("分步归因")),
        "坑四_摩擦敏感度": _num(out.get("坑四_摩擦敏感度")),
        "征兆警报": alarm,
        "引擎显式关掉的东西": matrices.disabled_log(),
        "耗时秒": round(time.time() - t0, 1),
    }
    if with_loo:
        print("  [留一法瓶颈诊断]")
        loo = leave_one_out(name, raw, syms)
        for r in loo:
            print(f"    {str(r['去掉的条件']):46s} 笔数={r.get('笔数')}"
                  f"  变化={r.get('笔数变化')}  {r.get('报错','')}")
        rec["★留一法瓶颈诊断"] = loo
    print(analyze.format_report(out))
    print(f"  (用了 {rec['耗时秒']} 秒)")
    return rec


# ================================================================ main

def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    only = next((a for a in argv if a in ("A", "B")), None)
    loo_only = "--loo" in argv

    print(data.cohort_report())
    print()
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    have_f = [s for s in syms if data.load_manifest()[s].fundamentals_path]
    print(f"全池 {len(syms)} 只,其中有 fundamentals.json 的 {len(have_f)} 只 —— "
          f"★ 另外 {len(syms)-len(have_f)} 只(pilot_50 那一批)"
          f"任何基本面闸门都按「看不到数据 = 不合格」永久判出局。"
          f"★ 两条基本面链的真实池子是 {len(have_f)} 只,不是 {len(syms)} 只。")
    print(f"绩效窗口 {data.PERF_START} .. {data.PERF_END}(2016 起热机)")
    print()
    print(fundamentals.verify_ytd(k=3))

    variants = []
    if only in (None, "A"):
        variants += cashflow_variants()
    if only in (None, "B"):
        variants += deep_value_variants()

    out = {
        "跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "全池只数": len(syms),
        "★有基本面数据的只数": len(have_f),
        "绩效窗口": f"{data.PERF_START} .. {data.PERF_END}(2016 起热机)",
        "★坑③_YTD口径自验": fundamentals.verify_ytd(k=3),
        "★基本面PIT口径": {
            "生效时点": "filing_date + 1 个交易日(严禁用报告期截止日)",
            "未公布期间": "沿用上一期(ffill);第一次公布之前 = NaN",
            "NaN 当闸门": "判不合格(不猜不补)",
            "NaN 当清仓条件": "★ 不触发清仓(拿不到数据不该凭空卖掉持仓)",
            "同一期取哪版": "首发版本,不用重述数据",
            "现金流口径": "★ YTD 差分还原单季再滚 TTM(要求最近 4 季时间连续)",
            "股数口径": "★ 走 share_gate 三道闸(单位 / 区间 / 拆股)",
        },
        "链": [],
    }
    for name, raw, notes, is_main in variants:
        try:
            out["链"].append(run_one(name, raw, notes, is_main, syms,
                                     with_loo=is_main))
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"★ {name} 跑挂了:{type(e).__name__}: {e}")
            out["链"].append({"链名": name, "★跑挂了": f"{type(e).__name__}: {e}",
                              "★必须讲清楚的前提": notes})
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
    print()
    print(f"原始数字已写:{OUT_JSON}")
    print(f"交易流水已写:{LEDGER_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
