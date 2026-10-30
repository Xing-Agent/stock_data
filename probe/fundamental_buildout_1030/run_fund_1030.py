#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 把基本面甲类(+ 确认可补的乙类)真跑起来 —— 2026-10-30

三秒版:五条链 × 先验网格,在**研发池**上跑;★★ 留出池物理封存,
        条件锁死后**只跑一次**。

══════════════════════════════════════════════════════════════════════════
★★★ 红线逐条落地
══════════════════════════════════════════════════════════════════════════
  ① 正交宏观锚点 —— ★ 只有基-2 的方法卡给了市场级条件,★★ 而那句话
     (「大量股票跌破净资产」)**用的正是它自己的因子** → ★ 本轮两条臂并列:
       臂甲 不装条件 · 臂乙 装「非牛市」(只用 SPY,正交)
     ★ 其余四条的方法卡声明的是「长期机械执行 / 任何时候」= 原著无条件。
  ② 禁止单点估计 —— ★ 每条链的自由参数跑 **3 个邻近点**;
     ★★★ 考核写法是「3 点是否全部同向」,★ 不报「最好的那一点」。
     ★★ 为了算得完:网格只在**主参数**上展开(分位 / 槽位各 3 点,
        十字形 5 个格子,不是 3×3=9 个),★ 并且**只有主格**跑完整的
        基准 + 四道门。★ 这一处简化是算力约束,已登记。
  ③ 预先登记 —— ★ configs_1030/ 五份 YAML 已在 commit e4c8668 提交,
     ★★★ 那个 commit 在本脚本第一次运行**之前**。登记后公式不改。
  ④ 纯样本外封存 —— 研发池 **2018-01-01 .. 2020-12-31**;
     留出池 **2021-01-01 .. 2025-12-31**,★ 默认**不跑**(要 --holdout 才跑)。
     ★★★ 一处不得已的偏离必须登记:红线④ 说研发池是 2014–2020,
        ★ 但 engine 的绩效窗口 `data.PERF_START` 是 **2018-01-01**
        (2016 起热机),★★ 所以实际研发池只有 **3 年**,不是 7 年。
        ★ 这会让研发池的笔数先天偏少,★★ 报告里必须跟着每一个数讲。
  ⑤ 原著未给环境过滤 → 不许隐式默认 —— ★ 只有基-12 是真空,
     它的配置里显式写了 `environment_declaration: Unspecified`,
     ★★ 本脚本会把这个声明原样搬进结果,★★★ 没有悄悄当成「常开」。

★★ 跑批纪律(今天为这两件各丢过一次跑批):
   ★ 不用 nohup;★★ 每跑完一格就 dump,重跑跳过已有;★★★ 先写结果再打印。
★ 「天」一律是交易日。
跑法:python3 probe/fundamental_buildout_1030/run_fund_1030.py            # 研发池
      python3 probe/fundamental_buildout_1030/run_fund_1030.py --timeonly # 先量耗时
      python3 probe/fundamental_buildout_1030/run_fund_1030.py --holdout  # ★ 封存池,只跑一次
"""
from __future__ import annotations

import copy
import json
import os
import sys
import time
import traceback

import numpy as np
import pandas as pd
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE, os.path.join(ROOT, "probe", "v2_rerun_1030"),
          os.path.join(ROOT, "probe", "regime_install_1030")):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import (analyze, cache, chain, data, matrices,  # noqa: E402
                    stats_gate)
import ops_fund_1030 as OF                                   # noqa: E402
import rerun_core_1030 as RC                                 # noqa: E402
import regime_vectors_1030 as RV                             # noqa: E402

CONFIG_DIR = os.path.join(HERE, "configs_1030")
LEDGER_DIR = os.path.join(HERE, "ledgers_1030")
PART_DIR = os.path.join(HERE, "parts")
OUT_JSON = os.path.join(HERE, "run_fund_results_1030.json")

DEV = ("2018-01-01", "2020-12-31")          # ★ 研发池
HOLDOUT = ("2021-01-01", "2025-12-31")      # ★★★ 留出池,封存
SCOPE = "large_mid"                          # ★ 大+中池(排名 1–2000)

#: ★★★ 2026-10-30 换数据源:EBIT / 长期负债改用数据组那份 SEC PIT 主表。
#   ★★ 实测在**可比的非金融 195 只**上:
#        EBIT       我补标签 164(84.1%) → ★★★ 数据组 192(**98.5%**)
#        长期负债   我补标签 168(86.2%) → ★★★ 数据组 190(**97.4%**)
#   ★ 所以换它的。我那份保留做交叉校验(见 sec_table_reconcile_1030.json)。
#
# ★★★ 哪几条链会被这次换源影响 —— ★ 逐条查过,不是猜的:
#     基-6(EV/EBIT + 净债)   ★★ 受影响 → **重跑**
#     基-4(ROC + EV/EBIT)     ★★ 受影响 → **重跑**
#     基-2(P/B = 净资产/股数)  ★ 不碰 EBIT / 长期负债 → ★★ 结果不变,不重跑
#     基-5(P/E = EPS)         ★ 同上 → 不重跑
#     基-12(股数 + FCF)        ★ 同上 → 不重跑
#   ★★ 覆盖层**只替换** EBIT 和 LongTermDebt 两列(白名单 `_SEC_METRICS`),
#      ★ 其余字段一个没动 —— 所以「不受影响」这句话是**代码上可查的**,不是推断。
DATA_SOURCE = "sec_table"
AFFECTED_BY_SOURCE = ("基-6", "基-4")

CHAINS = {
    "基-2": "基-2-施洛斯极度分散.yaml",
    "基-5": "基-5-低市盈率逆向.yaml",
    "基-6": "基-6-收购者倍数.yaml",
    "基-4": "基-4-神奇公式.yaml",
    "基-12": "基-12-无自由参数子集.yaml",
}
#: ★ 主参数的 3 点先验网格 —— ★★ 逐字来自各配置的 rank_prior_grid / slots_prior_grid
GRID_RANK = {"基-5": [10, 20, 30], "基-6": [10, 20, 30], "基-4": [10, 20, 30]}
GRID_SLOTS = {"基-2": [20, 40, 60], "基-5": [15, 30, 45], "基-6": [15, 30, 45],
              "基-4": [15, 30, 45], "基-12": [15, 30, 45]}
MAIN_SLOTS = {"基-2": 40, "基-5": 30, "基-6": 30, "基-4": 30, "基-12": 30}
MAIN_RANK = {"基-5": 20, "基-6": 20, "基-4": 20}
RANK_KEY = {"基-5": "pe_rank_bottom", "基-6": "ev_ebit_rank_bottom",
            "基-4": "magic_formula_rank_top"}


def _load(name: str) -> dict:
    with open(os.path.join(CONFIG_DIR, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _num(x):
    if isinstance(x, dict):
        return {str(k): _num(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_num(v) for v in x]
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        return None if not np.isfinite(float(x)) else float(x)
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, float):
        return None if not np.isfinite(x) else x
    if hasattr(x, "report"):
        try:
            return x.report()
        except Exception:
            return str(x)
    return x


def apply_grid(raw: dict, cid: str, slots: int, rank: int | None) -> dict:
    c = copy.deepcopy(raw)
    c["slots"] = int(slots)
    c.setdefault("sizing", {}).setdefault("params", {})["max_positions"] = int(slots)
    c["sizing"]["params"]["max_weight"] = round(1.0 / max(1, slots), 6)
    if rank is not None and cid in RANK_KEY:
        key = "rank_top_pct" if cid == "基-4" else "rank_bottom_pct"
        for r in c["universe"]["rules"]:
            if r.get("type") == RANK_KEY[cid]:
                r["params"][key] = int(rank)
    return c


# ══════════════════════════════════════════════════════════════════════════
# 跑一个格子
# ══════════════════════════════════════════════════════════════════════════

def run_cell(cid: str, raw: dict, slots: int, rank: int | None,
             window: tuple[str, str], arm: str, is_main: bool,
             syms: list[str]) -> dict:
    t0 = time.time()
    c = apply_grid(raw, cid, slots, rank)
    cfg = chain.ChainConfig.from_dict(copy.deepcopy(c))
    rep = cfg.adapt_report
    if not rep.ok:
        raise RuntimeError(f"{cid} 还有没实现的规则,★ 不许带着它跑:\n{rep.text()}")

    start, end = window
    # ★★★ 顺序很要紧(第一版就踩了):`matrices.build()` 内部**就会**调
    #   ⑥ exit_signal_matrix,所以 screen_dropout 要的掩膜必须在 build **之前**登记。
    #   ★ 第一版放在 build 之后 → KeyError(★ 好在那个 raise 写对了,
    #     没有悄悄当成「从不离场」)。
    # ★★ 登记的是**只过 ① 选股规则**的掩膜,★★★ 故意**不含**大+中池口径 ——
    #   理由:离场该由**策略条件**触发,不该由「我们选了哪个池子」触发。
    #   ★ 一只票掉出大+中池不等于它不再便宜。
    uni = matrices.universe_mask(cfg.raw.get("universe") or {}, syms)
    OF.set_screen(cid, uni)

    m = matrices.build(cfg.raw, syms)
    scope_diag = RC.apply_scope(m, SCOPE)
    sig = RC.signal_counts(m)

    arm_note = ""
    if arm == "乙_装非牛市":
        bull, meta = RV.market_vectors(m.index)["乙·牛市"]
        inv = ~bull.reindex(m.index).fillna(False).to_numpy()
        before = float(np.mean(m.regime))
        m.regime = m.regime & inv
        arm_note = (f"★ 装了「非牛市」(= ~牛市,只用 SPY,★ 正交于本策略的 P/B 因子)。"
                    f"★★ 条件成立的时间占比 {float(np.mean(inv)):.1%};"
                    f"★ regime 真值占比 {before:.1%} → {float(np.mean(m.regime)):.1%}。"
                    f"★ 参数出处:{meta['参数出处']}")

    res = chain.run_chain(cfg, syms, start, end, 1_000_000.0, m=m)
    led = res.ledger
    os.makedirs(LEDGER_DIR, exist_ok=True)
    tagname = f"{cid}_{arm}_slots{slots}" + (f"_rank{rank}" if rank else "")
    res.save_ledger(os.path.join(LEDGER_DIR, f"{tagname}.csv"))

    # ---- 条件成立的时间占比
    reg_frac = float(np.mean(m.regime))
    uni_sub = uni.loc[(uni.index >= pd.Timestamp(start)) & (uni.index <= pd.Timestamp(end))]
    days_with_cand = float((uni_sub.sum(axis=1) > 0).mean())
    avg_cand = float(uni_sub.sum(axis=1).mean())

    rec = {
        "链": cid, "臂": arm, "slots": slots, "分位": rank,
        "窗口": f"{start} .. {end}",
        "★是否主格": is_main,
        "臂说明": arm_note,
        "适配层报告": rep.text(),
        "信号数": sig,
        "笔数": len(led),
        "★条件成立的时间占比": {
            "② regime 真值占比": reg_frac,
            "★ 当天有候选票的交易日占比": days_with_cand,
            "★ 平均每天的候选只数": avg_cand,
        },
        "池子口径诊断": {k: v for k, v in scope_diag.items()
                         if k != "票×年 解析方式计数"},
        "★R口径": "★★★ 本链**无止损** → 1R = 进场价 → **R 退化成收益率**。"
                   "★ 不能和有止损的链放在同一列比。",
        "耗时秒": None,
    }
    if len(led):
        rn = led["r_multiple_net"].astype(float).to_numpy()
        rn = rn[np.isfinite(rn)]
        rec.update({
            "每笔净R(=净收益率)": float(rn.mean()) if rn.size else None,
            "每笔净R_中位": float(np.median(rn)) if rn.size else None,
            "胜率": float((led["net_pnl"] > 0).mean()),
            "净盈亏": float(np.nansum(led["net_pnl"].astype(float))),
            "平均持有交易日": float(led["holding_days"].astype(float).mean()),
            "出场原因分布": {str(k): int(v)
                             for k, v in led["reason"].value_counts().items()},
        })

    if is_main:
        try:
            out = analyze.evaluate(cfg, res, syms, start, end,
                                   with_attribution=False, with_sensitivity=False,
                                   with_gate=True)
            rec["绝对表现"] = _num(out["绝对表现"])
            rec["基准一_同环境随机进场"] = _num(out["基准一_同环境随机进场"])
            rec["基准二_同等仓位大盘"] = _num(out["基准二_同等仓位大盘"])
            rec["判据_三套对照组"] = _num(out["判据"])
            rec["摩擦成本"] = _num(out.get("摩擦成本"))
        except Exception as e:
            # ★★★ 基准一现在是硬闸(engine/analyze.BenchmarkPremiseBroken,
            #   另一条线 2026-10-30 刚把容差从 ±8% 收到 ±5% 并改成 raise)——
            #   ★ 破了就如实记下来,★★ 不许绕过去当成「基准不适用」。
            rec["★基准/判据跑挂了"] = f"{type(e).__name__}: {e}"
    rec["耗时秒"] = round(time.time() - t0, 1)
    return rec


# ══════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════

def cells(window_tag: str) -> list[tuple]:   # noqa: C901
    """(cell_id, cid, slots, rank, arm, is_main) —— ★ 十字形网格,不是 3×3。"""
    out = []
    only = os.environ.get("ONLY_CHAINS")
    pick = [c.strip() for c in only.split(",")] if only else list(CHAINS)
    for cid in CHAINS:
        if cid not in pick:
            continue
        ms, mr = MAIN_SLOTS[cid], MAIN_RANK.get(cid)
        src = DATA_SOURCE if cid in AFFECTED_BY_SOURCE else "不受换源影响"
        out.append((f"{window_tag}|{cid}|甲|s{ms}|r{mr}|{src}", cid, ms, mr,
                    "甲_不装条件", True))
        for s in GRID_SLOTS[cid]:
            if s != ms:
                out.append((f"{window_tag}|{cid}|甲|s{s}|r{mr}|{src}", cid, s, mr,
                            "甲_不装条件", False))
        for r in GRID_RANK.get(cid, []):
            if r != mr:
                out.append((f"{window_tag}|{cid}|甲|s{ms}|r{r}|{src}", cid, ms, r,
                            "甲_不装条件", False))
        if cid == "基-2":
            out.append((f"{window_tag}|{cid}|乙|s{ms}|r{mr}|{src}", cid, ms, mr,
                        "乙_装非牛市", True))
    return out


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    holdout = "--holdout" in argv
    timeonly = "--timeonly" in argv
    window = HOLDOUT if holdout else DEV
    wtag = "留出池" if holdout else "研发池"
    if holdout:
        print("★★★ 你在跑**留出池**(2021–2025)—— 这是封存样本,只跑一次。")

    OF.install(source=DATA_SOURCE)
    os.makedirs(PART_DIR, exist_ok=True)
    man = data.load_manifest()
    have_px = set(cache.symbols())
    syms = [s for s in sorted(man) if man[s].fundamentals_path and s in have_px]

    todo = cells(wtag)
    if timeonly:
        todo = todo[:2]
    results, errs = {}, {}
    for i, (cell, cid, slots, rank, arm, is_main) in enumerate(todo):
        part = os.path.join(PART_DIR, cell.replace("|", "__") + ".json")
        if os.path.exists(part):                 # ★ 可续跑
            results[cell] = json.load(open(part, encoding="utf-8"))
            continue
        raw = _load(CHAINS[cid])
        try:
            rec = run_cell(cid, raw, slots, rank, window, arm, is_main, syms)
        except Exception as e:
            rec = {"链": cid, "臂": arm, "slots": slots, "分位": rank,
                   "★跑挂了": f"{type(e).__name__}: {e}",
                   "traceback": traceback.format_exc()[-2500:]}
            errs[cell] = rec["★跑挂了"]
        # ★ 先写,再打印
        with open(part, "w", encoding="utf-8") as fh:
            json.dump(_num(rec), fh, ensure_ascii=False, indent=2, default=str)
        results[cell] = rec
        try:
            print(f"[{i+1}/{len(todo)}] {cell}  笔数={rec.get('笔数')} "
                  f"信号={(rec.get('信号数') or {}).get('合格进场信号(entry&universe)')} "
                  f"用时={rec.get('耗时秒')}s {rec.get('★跑挂了','')}")
        except Exception as e:
            print(f"(打印出错:{type(e).__name__}: {e})")

    out = {
        "跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "窗口": f"{window[0]} .. {window[1]}({wtag})",
        "★红线④偏离登记": "★★★ 红线④ 要求研发池 2014–2020,★ 但 engine 的"
                           "绩效窗口从 2018-01-01 起(2016 起热机)—— "
                           "★★ 实际研发池只有 3 年,笔数先天偏少。",
        "池子口径": f"{SCOPE}(大+中,成交额排名 1–2000);"
                     "★ 该池上 $5 万/日流动性门槛实测挡 0 笔,不需要流动性门槛",
        "回测票池只数": len(syms),
        "★算子备注": OF.notes(),
        "★数据源": DATA_SOURCE,
        "★受换源影响的链": list(AFFECTED_BY_SOURCE),
        "格子数": len(todo),
        "跑挂的格子": errs,
        "格子": {k: _num(v) for k, v in results.items()},
    }
    with open(OUT_JSON if not holdout else OUT_JSON.replace(".json", "_留出池.json"),
              "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
    try:
        print(f"\n★ 写了:{OUT_JSON}")
        tot = sum((r.get("耗时秒") or 0) for r in results.values())
        print(f"★ 总耗时 {tot:.0f}s / {len(todo)} 格")
    except Exception as e:
        print(f"(打印出错,结果已写出:{type(e).__name__}: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
