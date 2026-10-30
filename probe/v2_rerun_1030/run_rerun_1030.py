#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 大+中池上的**真重跑** —— 2026-10-30

三秒版:上一轮(pool_scope_1030)是**拿现成流水按池子重切**。
        这一版是**从信号层重新跑回测**,目的只有一个:
        ★★ 把 `max_positions` 的名额在「只有大+中票」的世界里**重新分配一次**,
           看每条链的笔数和每笔 R 和「重切」差多少。

★★ 名额是怎么分配的(先搞清楚再跑,chain.py 实测读码):
   ⑤ 今天收盘:cands = [今天 entry 触发 且 universe 允许 且 没在持仓 且 票还活着]
      slots = max_positions − len(持仓)
      ★ 候选多于名额 → 按 rank_score 降序(并列按 ADV20 降序,再按代码字母序)
        取前 slots 只 → pending_entry
   ② 明天开盘:按 pending_entry 顺序买,★ 每买一只就查一次 len(pos) >= max_positions,
      满了就 break(剩下的**不排队、直接丢**)
   ★★★ 所以:全池里被小盘票占掉的名额,大中盘的信号就排不进来 ——
        重切流水看不到这件事。这就是本轮唯一要测的东西。

★ 本轮实测:槽位到底绑不绑(183 份流水的并发持仓)
     观测到的最大并发 = 10(= 默认 max_positions)的有 103 份;
     ★★ 但「满仓天数占比」从 0.0% 到 89.7% —— 所以影响**逐链差别极大**,
        不能一句话概括。本轮逐链报差。

★★ 硬纪律:
  1. ★ `engine/` 一个字符都没改。口径通过 `run_chain(cfg, syms, m=...)`
     这个**现成入参**注入(先例:engine/pool_scope.py 一行没改既有代码)。
  2. ★ 串行单进程。跑前打印 free / nproc。
  3. ★ 每份产出盖池子口径戳。
  4. ★ 报笔数必须同时报信号数;「天」一律写明交易日。
  5. ★★★ 不碰 probe/stage_path_1030/ · probe/snapshot_features_1030/ 等别人的目录。

★★ 已知局限(必须写在报告里,不许藏):
  ① **广度风险预算标尺(`size_mult`)没有在新口径上重算** —— 它在
     `matrices.build()` 里按全池 universe 算好,本脚本是在 build 之后
     才把池子口径与进 `m.universe` 的。★ 本脚本逐链记录 `size_mult` 是否恒为 1;
     恒为 1 的链完全不受这条局限影响。
  ② **只重跑得出配置的链**。182 条流水链分散在 15 个跑批脚本里,
     其中 5 个脚本把变体列成了可导入的 `VARIANTS`,本轮覆盖这些;
     其余(新基准线 / 第二轮 / 闸门 / 基本面 等)没有可导入的变体表,
     ★ 本轮不假装跑过它们。覆盖率在报告里写明。

跑法:python3 probe/v2_rerun_1030/run_rerun_1030.py
"""
from __future__ import annotations

import copy
import csv
import glob
import json
import os
import resource
import subprocess
import sys
import time

import numpy as np
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)
if HERE not in sys.path:
    sys.path.insert(0, HERE)

from engine import (analyze, cache, chain, data, matrices, ops_exits_1029,  # noqa: E402
                    pat6_ops, pool_scope)
import rerun_core_1030 as RC                                               # noqa: E402

CONFIG_DIR = os.path.join(ROOT, "engine", "configs")
OUT_JSON = os.path.join(HERE, "rerun_results_1030.json")
OUT_CSV = os.path.join(HERE, "按链-真重跑-1030.csv")

#: ★ run_declean 的双侧阈值,照抄不改(纪律:同一样东西一个口径)
RATIO_HI, RATIO_LO = 0.9, 0.01

#: ★ 可用判据的样本门槛(上一轮口径,照抄)
MIN_TRADES = 30

#: 口径内 variant 来源 —— 5 个有可导入 VARIANTS 的跑批脚本
VARIANT_MODULES = [
    ("A0十二条", "engine.run_a0_12"),
    ("技术派六条三版", "engine.pat6_run"),
    ("批五修正", "engine.run_p5_1029"),
    ("原著离场", "engine.run_orig_exits_1029"),
    ("剔污染", "engine.run_declean_1030"),
]


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


# ══════════════════════════════════════════════════════════════════════════
# 一 · 核对数(纪律 5:对不上就停)
# ══════════════════════════════════════════════════════════════════════════

KNOWN = {
    "流水文件数": 183, "成交笔数": 146_991, "策略链数": 182,
    "不同策略名": 160, "ledger一把捞": 237, "带BOM文件": 3,
    "池子行数": 74_268,
}


def _ledger_dirs() -> list[str]:
    return sorted(glob.glob(os.path.join(ROOT, "engine", "ledgers_*")))


def reconcile() -> dict:
    files, rows, names, empty = [], 0, set(), 0
    for d in _ledger_dirs():
        for p in sorted(glob.glob(os.path.join(d, "*.csv"))):
            files.append(p)
            with open(p, newline="", encoding="utf-8-sig") as fh:
                n = sum(1 for _ in csv.DictReader(fh))
            rows += n
            if n == 0:
                empty += 1
            names.add(os.path.basename(p)[:-4])
    # ★ 「ledger 一把捞」:ledger 也可能在**目录名**上(four_slot_complete 那张表)
    wide = {p for p in glob.glob(os.path.join(ROOT, "**", "*ledger*"), recursive=True)
            if os.path.isfile(p)}
    wide |= {p for d in glob.glob(os.path.join(ROOT, "**", "*ledger*"), recursive=True)
             if os.path.isdir(d)
             for p in glob.glob(os.path.join(d, "**", "*"), recursive=True)
             if os.path.isfile(p)}
    # ★★★ 2026-10-30 本轮第一件事就撞上了:一把捞读到 **239**,已知是 237。
    #   ★ 查明原因(不是流水多了):probe/declean_1030/ 里有两个**名字里带 ledger
    #     但根本不是流水**的文件 —— `naive_ledger_attrib_1030.py` 和它的 `.json`
    #     产出(朴素基准的逐笔归因脚本,提交 3fe1926,时间戳 2026-10-30 11:13,
    #     ★ 晚于「237」这个数被定下来的时刻)。
    #   ★★ 这正是「一把捞」这个办法自己的坑:`*ledger*` 会捞到**不是流水**的东西。
    #     所以这里把它们按名单显式排掉,并把 237 写成「截至 1fbd43f 的已知数」。
    NOT_LEDGERS = {
        os.path.join(ROOT, "probe", "declean_1030", "naive_ledger_attrib_1030.py"),
        os.path.join(ROOT, "probe", "declean_1030", "naive_ledger_attrib_1030.json"),
    }
    wide_raw = len(wide)
    wide = {p for p in wide if os.path.abspath(p) not in
            {os.path.abspath(x) for x in NOT_LEDGERS}}
    # ★★ BOM 必须在**字节层**查 —— utf-8-sig 打开后 BOM 已被吃掉,
    #    在 fieldnames 里永远查不到(今天第 9 次同类坑)
    bom = []
    for p in files:
        with open(p, "rb") as fh:
            if fh.read(3) == b"\xef\xbb\xbf":
                bom.append(p)
    idx = RC.pool_index()
    got = {
        "流水文件数": len(files), "成交笔数": rows,
        "策略链数": len(files) - empty, "不同策略名": len(names),
        "ledger一把捞": len(wide), "带BOM文件": len(bom),
        "池子行数": idx.rows,
    }
    bad = {k: (got[k], KNOWN[k]) for k in KNOWN if got[k] != KNOWN[k]}
    return {"读到": got, "已知": KNOWN, "对不上的": bad,
            "ledger一把捞_未排除前": wide_raw,
            "ledger一把捞_显式排掉的非流水": sorted(
                os.path.relpath(p, ROOT) for p in NOT_LEDGERS),
            "带BOM的文件": [os.path.relpath(p, ROOT) for p in bom]}


# ══════════════════════════════════════════════════════════════════════════
# 二 · 链名归一化(★ 三种写法,今天第 8 次同类坑)
# ══════════════════════════════════════════════════════════════════════════

def norm_chain(s: str) -> str:
    """流水文件名 / results JSON / 报告 三种写法归一到同一个键。

    已知差异:全部空白、分隔符 ·_/、全角括号、以及报告里会**掉 `Test`**。
    """
    s = str(s)
    for a, b in (("(", "("), (")", ")"), ("（", "("), ("）", ")"),
                 ("≥", ">="), ("×", "x")):
        s = s.replace(a, b)
    for ch in " \t　·_/★【】":
        s = s.replace(ch, "")
    s = s.replace("Test", "")
    return s


# ══════════════════════════════════════════════════════════════════════════
# 三 · 逐链:R 这把尺子在这条链上成不成立 + 无止损识别
# ══════════════════════════════════════════════════════════════════════════

def r_validity(led) -> dict:
    """★★ 实测 risk_per_share / entry_price,判这条链的每笔 R 能不能和别人并排。

    大白话:R = 「赚了几倍的风险金额」。风险 = 进场价 − 止损价。
      ★ 如果一条链**没有止损**,风险就等于进场价本身 → R 退化成「涨了百分之几」,
        ★★★ 和有止损的链的 R 写在同一列里排序,排序本身就是错的。
    """
    if led is None or len(led) == 0:
        return {"可比": False, "原因": "无成交"}
    e = led["entry_price"].astype(float).to_numpy()
    r = led["risk_per_share"].astype(float).to_numpy()
    ok = np.isfinite(e) & np.isfinite(r) & (e > 0)
    if not ok.any():
        return {"可比": False, "原因": "无有效风险距离"}
    ratio = r[ok] / e[ok]
    hi = float((ratio > RATIO_HI).mean())
    lo = float((ratio < RATIO_LO).mean())
    nostop = hi >= 0.5
    return {
        "风险距离占进场价_中位": float(np.median(ratio)),
        "比例>0.9的笔数占比": hi,
        "比例<0.01的笔数占比": lo,
        "★无止损(退化成收益率)": nostop,
        "可比": (not nostop) and lo < 0.5,
        "口径": f"risk/entry > {RATIO_HI} 过半 → 判为无止损,R 不可与有止损链并列",
    }


def concentration(led) -> dict:
    import importlib.util
    p = os.path.join(ROOT, "engine", "checks", "concentration_degenerate.py")
    spec = importlib.util.spec_from_file_location("cd_mod", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    pnl = led["net_pnl"].astype(float).tolist() if len(led) else []
    return mod.concentration(pnl)


def four_slot(raw: dict, name: str) -> dict:
    import importlib.util
    p = os.path.join(ROOT, "engine", "checks", "four_slot_complete.py")
    spec = importlib.util.spec_from_file_location("fs_mod", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    a = mod.audit_one(raw, name)
    return {"三槽位齐全_不含加仓": a["三槽位齐全_不含加仓"],
            "止损两级都齐": a["止损两级都齐"],
            "空着的": a["空着的"]}


# ══════════════════════════════════════════════════════════════════════════
# 四 · 净值口径的指标(SPY 对比要用)
# ══════════════════════════════════════════════════════════════════════════

def equity_stats(res) -> dict:
    eq = res.equity
    mdd, under, trough = analyze.drawdown(eq)
    return {
        "账户CAGR(净)": analyze.cagr(eq),
        "账户总收益": float(eq.iloc[-1] / eq.iloc[0] - 1.0),
        "最大回撤": mdd,
        "最长水下(交易日)": int(under),
        "最大回撤谷底": str(trough.date()) if trough is not None else None,
        "平均净敞口Ebar": float(res.exposure.mean()),
        "交易日数": int(len(eq)),
    }


# ══════════════════════════════════════════════════════════════════════════
# 五 · 跑一条链 × 两个口径
# ══════════════════════════════════════════════════════════════════════════

def load_raw(yaml_name: str) -> dict:
    with open(os.path.join(CONFIG_DIR, yaml_name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def run_pair(label, yaml_name, override, group, syms) -> dict:
    t0 = time.time()
    raw = load_raw(yaml_name)
    if override is not None:
        raw = override(copy.deepcopy(raw))
    cfg = chain.ChainConfig.from_dict(raw)
    if not cfg.adapt_report.ok:
        return {"链": label, "★跑不了": cfg.adapt_report.text()[:400]}

    m = matrices.build(cfg.raw, syms)
    sig_full = RC.signal_counts(m)
    size_mult_const = bool(np.allclose(m.size_mult, 1.0))
    res_f = chain.run_chain(cfg, syms, m=m)
    led_f = res_f.ledger

    # ★★ 同一个 m 复用:run_chain 只读 m,不改它。这里再把池子口径与进 universe。
    scope_diag = RC.apply_scope(m, "large_mid")
    sig_lm = RC.signal_counts(m)
    res_l = chain.run_chain(cfg, syms, m=m)
    led_l = res_l.ledger

    rec = {
        "链": label, "配置": yaml_name, "族": group,
        "有override": override is not None,
        "max_positions": int(((cfg.get("sizing") or {}).get("params") or {})
                             .get("max_positions", 10)),
        "sizing_type": (cfg.get("sizing") or {}).get("type", "risk_fraction"),
        "★广度标尺恒为1(不受局限①影响)": size_mult_const,
        "四槽位": four_slot(cfg.raw, label),
        "全池": {**RC.chain_metrics(led_f), **sig_full,
                 **equity_stats(res_f),
                 "R可比性": r_validity(led_f), "集中度": concentration(led_f)},
        "大中_重跑": {**RC.chain_metrics(led_l), **sig_lm,
                      **equity_stats(res_l),
                      "R可比性": r_validity(led_l), "集中度": concentration(led_l)},
        "池子收窄诊断": scope_diag,
        "耗时秒": round(time.time() - t0, 1),
        "峰值RSS_MB": round(_rss_mb(), 1),
    }
    # ★★ 重切:把**同一次全池重跑**的流水按池子口径切一刀 ——
    #   这样「重跑 vs 重切」的差**只剩名额重分配**这一个来源,没有别的混淆。
    idx = RC.pool_index()
    keep = []
    for r in led_f.itertuples():
        y = str(r.entry_date.year)
        rk, _t, _how = idx.resolve(str(r.symbol), y)
        keep.append(pool_scope.in_scope(rk, "large_mid"))
    led_c = led_f[np.array(keep, dtype=bool)] if len(led_f) else led_f
    rec["大中_重切"] = {**RC.chain_metrics(led_c),
                        "R可比性": r_validity(led_c),
                        "集中度": concentration(led_c)}
    a, b = rec["大中_重跑"], rec["大中_重切"]
    rec["重跑减重切"] = {
        "笔数差": a["笔数"] - b["笔数"],
        "笔数差比例": ((a["笔数"] - b["笔数"]) / b["笔数"]) if b["笔数"] else None,
        "每笔净R差": ((a["每笔净R"] - b["每笔净R"])
                      if (a["每笔净R"] is not None and b["每笔净R"] is not None) else None),
        "胜率差": ((a["胜率"] - b["胜率"])
                   if (a["胜率"] is not None and b["胜率"] is not None) else None),
        "符号翻转": ((a["每笔净R"] is not None and b["每笔净R"] is not None)
                     and (a["每笔净R"] > 0) != (b["每笔净R"] > 0)),
    }
    print(f"    全池 {rec['全池']['笔数']:6d} 笔 R {rec['全池']['每笔净R']} | "
          f"大中重跑 {a['笔数']:6d} R {a['每笔净R']} | "
          f"大中重切 {b['笔数']:6d} R {b['每笔净R']} | "
          f"Δ笔 {rec['重跑减重切']['笔数差']:+d} "
          f"{'★符号翻转' if rec['重跑减重切']['符号翻转'] else ''} "
          f"| {rec['耗时秒']}s RSS {rec['峰值RSS_MB']}MB")
    return rec


# ══════════════════════════════════════════════════════════════════════════
# 六 · SPY「买了躺着」基准
# ══════════════════════════════════════════════════════════════════════════

def spy_baseline(index) -> dict:
    b = data.load_benchmark("SPY")["close"].reindex(index).ffill()
    if b.isna().any():
        raise RuntimeError("★ SPY 在绩效窗口里有缺值 —— 停下来查,不许用别的代理")
    eq = b / float(b.iloc[0])
    mdd, under, trough = analyze.drawdown(eq)
    return {
        "标的": "SPY(pilot_300/benchmarks/SPY/daily.json,和个股走同一条拆股修正路径)",
        "交易日数": int(len(eq)),
        "起": str(index[0].date()), "止": str(index[-1].date()),
        "总收益": float(eq.iloc[-1] - 1.0),
        "CAGR": analyze.cagr(eq),
        "最大回撤": mdd,
        "最长水下(交易日)": int(under),
        "最大回撤谷底": str(trough.date()),
        "占用资金年化": analyze.cagr(eq),
        "★占用资金年化=CAGR的理由": (
            "SPY 买了不动 → 资金 100% 的交易日都在场,"
            "「占用资金」= 全部资金 × 全部交易日,所以这两个口径在它身上重合。"),
    }


# ══════════════════════════════════════════════════════════════════════════
# 七 · 全部 183 份流水上的「无止损」盘点(★ 协调方加问的那一条)
# ══════════════════════════════════════════════════════════════════════════

def nostop_census() -> dict:
    out, nostop, degen = [], [], []
    for d in _ledger_dirs():
        for p in sorted(glob.glob(os.path.join(d, "*.csv"))):
            with open(p, newline="", encoding="utf-8-sig") as fh:
                rows = list(csv.DictReader(fh))
            if not rows:
                continue
            e = np.array([float(r["entry_price"]) for r in rows])
            rr = np.array([float(r["risk_per_share"]) for r in rows])
            ok = np.isfinite(e) & np.isfinite(rr) & (e > 0)
            if not ok.any():
                continue
            ratio = rr[ok] / e[ok]
            hi = float((ratio > RATIO_HI).mean())
            lo = float((ratio < RATIO_LO).mean())
            rn = np.array([float(r["r_multiple_net"]) for r in rows
                           if r["r_multiple_net"] not in ("", None)])
            name = f"{os.path.basename(d).replace('ledgers_', '')}/{os.path.basename(p)[:-4]}"
            rec = {"链": name, "笔数": len(rows),
                   "风险距离占进场价_中位": float(np.median(ratio)),
                   "比例>0.9占比": hi, "比例<0.01占比": lo,
                   "每笔净R": float(rn.mean()) if rn.size else None}
            out.append(rec)
            if hi >= 0.5:
                nostop.append(rec)
            elif lo >= 0.5:
                degen.append(rec)
    return {"全部": out, "★无止损(R退化成收益率)": nostop,
            "★止损贴价(R被放大)": degen,
            "判据": f"risk/entry 中位及过半笔数 > {RATIO_HI} → 无止损;"
                    f"< {RATIO_LO} 过半 → 止损贴价"}


# ══════════════════════════════════════════════════════════════════════════
def main() -> int:
    print(subprocess.run(["free", "-m"], capture_output=True, text=True).stdout)
    print(subprocess.run(["uptime"], capture_output=True, text=True).stdout)
    print(f"CPU 核数 {os.cpu_count()} —— ★ 本脚本串行单进程,不开任何并行池\n")

    print("=" * 78)
    print("★ 核对数(纪律 5)")
    rec0 = reconcile()
    for k, v in rec0["读到"].items():
        ok = "✓" if v == KNOWN[k] else "✗"
        print(f"   {k:14s} 读到 {v:>8,d}  已知 {KNOWN[k]:>8,d}  {ok}")
    if rec0["对不上的"]:
        print(f"★★ 对不上:{rec0['对不上的']} —— 停下来查")
        return 2
    print("   ✓ 全部对上\n")

    pat6_ops.install()
    ops_exits_1029.install()

    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    print(f"回测池 {len(syms)} 只(★ 这是**回测**的票池,不是 74,268 行的"
          f"排名参照池;池子口径按年加在 universe 上)")

    _mask, mdiag = RC.scope_mask(syms, data.load_benchmark("SPY").loc[
        data.PERF_START:data.PERF_END].index, "large_mid")
    print(f"   每年在大+中档的只数:{mdiag['每年在池只数']}")
    print(f"   解析方式计数:{mdiag['票×年 解析方式计数']}\n")

    # 收变体
    seen, variants = set(), []
    for batch, modname in VARIANT_MODULES:
        mod = __import__(modname, fromlist=["VARIANTS"])
        for v in getattr(mod, "VARIANTS"):
            label, yml, ov, _why, group = v[0], v[1], v[2], v[3], v[4]
            key = (yml, id(ov) if ov else None, norm_chain(label))
            if key in seen:
                continue
            seen.add(key)
            variants.append((f"{batch}/{label}", yml, ov, group))
    print(f"★ 收到 {len(variants)} 个可重跑的变体(来自 "
          f"{len(VARIANT_MODULES)} 个有可导入 VARIANTS 的跑批脚本)\n")

    rows, fails = [], []
    t_all = time.time()
    for i, (label, yml, ov, group) in enumerate(variants, 1):
        print("=" * 78)
        print(f"[{i}/{len(variants)}] {label}   ({yml})")
        try:
            r = run_pair(label, yml, ov, group, syms)
            if "★跑不了" in r:
                fails.append((label, r["★跑不了"][:200]))
                print(f"    ★ 跑不了:{r['★跑不了'][:160]}")
            rows.append(r)
        except Exception as exc:                                  # noqa: BLE001
            import traceback
            traceback.print_exc()
            fails.append((label, repr(exc)[:300]))
    print(f"\n★ 全部跑完,共 {round(time.time() - t_all, 1)}s,"
          f"峰值 RSS {round(_rss_mb(), 1)} MB")

    # SPY
    spy_idx = data.perf_window(data.load_benchmark("SPY").index,
                               data.PERF_START, data.PERF_END)
    spy = spy_baseline(spy_idx)
    print(f"\n★ SPY 买了躺着:总收益 {spy['总收益']:+.2%} / CAGR {spy['CAGR']:+.2%} / "
          f"最大回撤 {spy['最大回撤']:.2%} / 最长水下 {spy['最长水下(交易日)']} 交易日")

    cen = nostop_census()
    print(f"★ 全部 {len(cen['全部'])} 条流水链里:无止损 "
          f"{len(cen['★无止损(R退化成收益率)'])} 条、止损贴价 "
          f"{len(cen['★止损贴价(R被放大)'])} 条")

    out = {
        "口径戳": pool_scope.stamp("large_mid", {
            "本轮做法": "★ 真重跑(从信号层)——池子口径按年与进 m.universe,"
                        "名额在只有大+中票的世界里重新分配",
            "注入点": "chain.run_chain(cfg, syms, m=...) 现成入参;engine/ 一行未改",
            "回测票池": f"{len(syms)} 只(pilot 全池)",
            "绩效窗口": f"{data.PERF_START} .. {data.PERF_END}(交易日 {len(spy_idx)} 天)",
            "已知局限①": "广度风险预算标尺 size_mult 未在新口径上重算(逐链标注)",
            "已知局限②": f"只重跑得出配置的 {len(variants)} 个变体,"
                          f"其余流水链本轮没有重跑,不假装跑过",
        }),
        "核对台账": rec0,
        "池子掩膜诊断": mdiag,
        "SPY基准": spy,
        "无止损盘点": cen,
        "逐链": rows,
        "跑不了的": fails,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n→ {os.path.relpath(OUT_JSON, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
