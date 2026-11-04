#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 扩库全跑(1104)—— 把 8 条新策略的 16 条臂真跑起来

三秒版(大白话):
  16 条臂,每条在**研发池**(2018–2020)上跑;★ 原著没给的数跑三个点;
  ★★ 主格再跑一遍「赢不赢随机进场」;★★★ 考卷那 1,042 只一个都不碰。

══════════════════════════════════════════════════════════════════════════
★★ 跑批纪律(逐条照《35》)
══════════════════════════════════════════════════════════════════════════
  ① **只用研发池**,`exam_1042/` 一个文件都不读 —— ★ 自证:本轮 250 只票的
     基本面文件路径全部落在 `pilot_300/` 下(实测 `exam_1042` 命中 0)。
     ★★ 下面注释里出现的 `exam_1042` 只是说明文字,没有任何代码路径打开它。
  ② **engine/ 一个字节不改** —— 算子全在 ops_expand_1104.py。
  ③ **库冻结窗口**:跑前跑后各记一次 `fundamentals_ext/_MANIFEST.sha256`。
  ④ **流水不入库**:ledgers_1104/ 跑完压 .tar.gz。
  ⑤ **一个数不许编**:算不出来 = NaN = 判不合格,★ 不用近似值/默认值顶替。
  ⑥ ★★★ **「算不出来」和「分数差」分成两列记** —— 本脚本的
     `可算率` 和 `入选票数` 是两个独立字段,不混。
  ⑦ 不用 nohup;★ 每跑完一格就 dump,重跑跳过已有;★★ 先写文件再打印。

跑法:python3 probe/expand_run_1104/run_expand_1104.py
      ONLY=扩4-orig,扩4-ours python3 probe/expand_run_1104/run_expand_1104.py
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
for p in (ROOT, HERE, os.path.join(ROOT, "probe", "v2_rerun_1030")):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import analyze, cache, chain, data, matrices   # noqa: E402
import ops_expand_1104 as OX                               # noqa: E402
import rerun_core_1030 as RC                               # noqa: E402

CONFIG_DIR = os.path.join(HERE, "configs_1104")
LEDGER_DIR = os.path.join(HERE, "ledgers_1104")
PART_DIR = os.path.join(HERE, "parts")
OUT_JSON = os.path.join(HERE, "run_expand_results_1104.json")

DEV = ("2018-01-01", "2020-12-31")      # ★ 研发池
SCOPE = "large_mid"                      # ★ 大+中池(成交额排名 1–2000)

#: ★ 每条臂的「分数面板」名字 —— 用来算**可算率**(★★ 和「入选票数」分开记)
SCORE_OF = {
    "扩1-ours": "accrual_cf",
    "扩2-orig": "asset_growth",
    "扩2-ours": "operating_asset_growth",
    "扩3-orig-bm": "lsv_bm",
    "扩3-orig-cp": "lsv_cp",
    "扩3-orig-ep": "lsv_ep",
    "扩3-ours": "lsv_median",
    "扩4-orig": "netnav_inputs",
    "扩4-ours": "netnav_inputs",
    "扩5-orig": "inventory_abnormal",
    "扩5-ours": "inventory_abnormal",
    "扩6-orig": "gp_ta",
    "扩6-ours": "gp_avg_ta",
    "扩7-orig": "shareholder_yield",
    "扩7-ours": "shareholder_yield",
    "扩8-ours": "earnings_acceleration",
}

#: ★ 自由参数的网格 —— ★★ 逐字来自各配置的 rank_prior_grid / slots_prior_grid
SLOTS_GRID = [15, 30, 45]
SLOTS_MAIN = 30
RANK_RULE = {           # cid -> (规则 type, 参数名, 主值, 三点)
    "扩7-orig": ("shareholder_yield_rank_top", "rank_top_pct", 20, [10, 20, 30]),
    "扩7-ours": ("shareholder_yield_minus_asset_growth_rank_top",
                 "rank_top_pct", 20, [10, 20, 30]),
    "扩8-ours": ("return_rank_percentile", "min_percentile", 80, [70, 80, 90]),
}

#: ★★★ 《35》列的「原著版不跑 / 算不出来」的格子 —— ★ 照实登记,不试图跑
NOT_RUN = {
    "扩1-orig": {
        "策略": "① Sloan 应计 · 原著版(资产负债表法)",
        "判定": "★★★ 算不出来",
        "缺的是哪一样": "**应交所得税(IncomeTaxesPayable / "
                        "AccruedIncomeTaxesCurrent)—— 老库覆盖率 0.0%(0/250)**。"
                        "★ Sloan (1996) 的资产负债表法应计 = "
                        "(Δ流动资产 − Δ现金) − (Δ流动负债 − Δ一年内到期债务 − Δ应交所得税) "
                        "− 折旧摊销,★★ 其中「Δ应交所得税」这一项**库里一个格子都没有**。",
        "★为什么不拿别的顶上": "★★★ 《35》口径⑦:算不出来就记算不出来,"
                               "**不许用近似值顶上**。★ 去掉应交所得税那一项"
                               "≠ 原著口径,那是**另一个指标**,"
                               "★★ 标成「原著版」就违反红线①。",
        "★★一处要更正的事": "★★★ 我这一轮拿到的字段现状说「折旧摊销**没有**」—— "
                            "**那句话是错的**。实测 "
                            "DepreciationDepletionAndAmortization = 174/250(69.6%),"
                            "并上 DepreciationAmortizationAndAccretionNet 后 "
                            "183/250(**73.2%**)。★ 所以这一条卡住的**不是折旧摊销**,"
                            "是应交所得税。",
    },
    "扩8-orig": {
        "策略": "⑧ 趋势模板 AND 盈利加速 · 原著版",
        "判定": "⬜ 不跑(★ 预先登记就是这么写的)",
        "缺的是哪一样": "★★★ **没有单一原著** —— 这是融合条目。"
                        "★ 《35》跑的清单第 8 行已登记「原著版不跑」。",
        "★为什么不拿别的顶上": "★ 拿 Minervini 一个人的书当「整条的原著」"
                               "会把我们自己组合的那一半标成原著 —— 红线①。",
    },
}


def _load(cid: str) -> dict:
    with open(os.path.join(CONFIG_DIR, f"{cid}.yaml"), encoding="utf-8") as fh:
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


# ══════════════════════════════════════════════════════════════════════════
# ★★★ 可算率 —— ★ 和「入选票数」是两件事,分两列记(《35》口径⑧)
# ══════════════════════════════════════════════════════════════════════════

def computability(cid: str, syms: list[str], scope_mask: pd.DataFrame) -> dict:
    """算得出来的格子有多少。

    ★★★ 口径写死,两个数都报:
      · **符号级**:250 只里有多少只**有这个科目** —— ★ 《35》预言一就是
        按这个口径写死的,所以必须按同一个口径判定预言。
      · **窗口内日频**:研发池窗口里,(交易日 × 票)格子中算得出的比例 ——
        ★★ 这才是**真正用来选股**的那个数。
      ★ 两个数系统性不同(TTM 流量科目要凑满 4 个季度才出第一个值),
        ★★★ 不许混成一个数。
    """
    name = SCORE_OF[cid]
    start, end = DEV
    if name == "netnav_inputs":
        # ★★★ Net-Net 的可算率看的是**投入项**(流动资产 / 全部负债 / 股数),
        #   ★ **不是**最终那个比值 —— 净流动资产 ≤ 0 是「不合格」,
        #   ★★ 不是「算不出来」。两者混起来会把 Net-Net 的可算率报低一大截。
        nc = OX.get("ncav", syms)
        mc = OX.mktcap(syms)
        ok = nc.notna() & mc.notna().reindex_like(nc).fillna(False)
        sc_pos = OX.score("netnav_ratio", syms)
        extra = {"★其中净流动资产≤0(= 不合格,不是算不出来)":
                 None}
        sub_ok = ok.loc[start:end]
        sub_pos = sc_pos.loc[start:end]
        m = scope_mask.loc[start:end].reindex_like(sub_ok).fillna(False)
        n_ok = int((sub_ok & m).sum().sum())
        n_pos = int((sub_pos.notna() & m).sum().sum())
        extra["★其中净流动资产≤0(= 不合格,不是算不出来)"] = n_ok - n_pos
        base = sub_ok
    elif name == "lsv_median":
        parts = [OX.score(k, syms) for k in ("lsv_bm", "lsv_cp", "lsv_ep")]
        base = (parts[0].notna() & parts[1].notna() & parts[2].notna()).loc[start:end]
        extra = {}
    elif name == "earnings_acceleration":
        base = OX.get("earnings_acceleration", syms).notna().loc[start:end]
        extra = {}
    else:
        base = OX.score(name, syms).notna().loc[start:end]
        extra = {}

    m = scope_mask.loc[start:end].reindex(index=base.index,
                                          columns=base.columns).fillna(False)
    tot = int(m.sum().sum())
    good = int((base.astype(bool) & m).sum().sum())
    per_day = (base.astype(bool) & m).sum(axis=1)
    out = {
        "★窗口内日频可算率(口径内格子)": round(good / tot, 4) if tot else None,
        "★日均算得出的只数": round(float(per_day.mean()), 1),
        "口径内总格子": tot,
        "算得出的格子": good,
        "★算不出来的格子": tot - good,
    }
    out.update({k: v for k, v in extra.items() if v is not None})
    return out


# ══════════════════════════════════════════════════════════════════════════
# 跑一个格子
# ══════════════════════════════════════════════════════════════════════════

def apply_grid(raw: dict, cid: str, slots: int, rank) -> dict:
    c = copy.deepcopy(raw)
    c["slots"] = int(slots)
    c.setdefault("sizing", {}).setdefault("params", {})["max_positions"] = int(slots)
    c["sizing"]["params"]["max_weight"] = round(1.0 / max(1, slots), 6)
    if rank is not None and cid in RANK_RULE:
        rtype, pname, _, _ = RANK_RULE[cid]
        for r in c["universe"]["rules"]:
            if r.get("type") == rtype:
                r["params"][pname] = int(rank)
    return c


def run_cell(cid: str, raw: dict, slots: int, rank, is_main: bool,
             syms: list[str], scope_mask: pd.DataFrame) -> dict:
    t0 = time.time()
    c = apply_grid(raw, cid, slots, rank)
    cfg = chain.ChainConfig.from_dict(copy.deepcopy(c))
    rep = cfg.adapt_report
    if not rep.ok:
        raise RuntimeError(f"{cid} 还有没实现的规则,★ 不许带着它跑:\n{rep.text()}")

    start, end = DEV
    # ★★★ 顺序要紧:matrices.build() 内部就会调 ⑥ exit_signal_matrix,
    #   所以 screen_dropout 要的掩膜必须在 build **之前**登记(1030 踩过)。
    uni = matrices.universe_mask(cfg.raw.get("universe") or {}, syms)
    OX.set_screen(cid, uni)

    m = matrices.build(cfg.raw, syms)
    scope_diag = RC.apply_scope(m, SCOPE)
    sig = RC.signal_counts(m)

    res = chain.run_chain(cfg, syms, start, end, 1_000_000.0, m=m)
    led = res.ledger
    os.makedirs(LEDGER_DIR, exist_ok=True)
    tag = f"{cid}_slots{slots}" + (f"_rank{rank}" if rank is not None else "")
    res.save_ledger(os.path.join(LEDGER_DIR, f"{tag}.csv"))

    uni_sub = uni.loc[(uni.index >= pd.Timestamp(start))
                      & (uni.index <= pd.Timestamp(end))]
    sm = scope_mask.reindex(index=uni_sub.index,
                            columns=uni_sub.columns).fillna(False)
    sel = uni_sub.astype(bool) & sm
    per_day = sel.sum(axis=1)

    rec = {
        "臂": cid,
        "slots": slots,
        "★自由参数档位": rank,
        "窗口": f"{start} .. {end}(研发池)",
        "★是否主格": is_main,
        "归属": (raw.get("meta") or {}).get("★★★归属"),
        "适配层报告": rep.text(),
        "信号数": sig,
        "笔数": len(led),
        # ★★★ 「入选票数」—— ★ 和可算率是两件事
        "★入选票数": {
            "日均入选只数": round(float(per_day.mean()), 2),
            "入选只数_中位": float(per_day.median()),
            "入选只数_最多": int(per_day.max()) if len(per_day) else 0,
            "★有票可买的交易日占比": round(float((per_day > 0).mean()), 4),
            "★一只都没有的交易日占比": round(float((per_day == 0).mean()), 4),
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
            "★每笔净R(=净收益率)": float(rn.mean()) if rn.size else None,
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
                                   with_attribution=False,
                                   with_sensitivity=False, with_gate=True)
            rec["绝对表现"] = _num(out["绝对表现"])
            rec["★基准一_同环境随机进场"] = _num(out["基准一_同环境随机进场"])
            rec["基准二_同等仓位大盘"] = _num(out["基准二_同等仓位大盘"])
            rec["判据_三套对照组"] = _num(out["判据"])
        except Exception as e:
            # ★★★ 基准一是硬闸(analyze.BenchmarkPremiseBroken)——
            #   ★ 破了就如实记下来,★★ 不许绕过去当成「基准不适用」。
            rec["★基准/判据跑挂了"] = f"{type(e).__name__}: {e}"
    rec["耗时秒"] = round(time.time() - t0, 1)
    return rec


# ══════════════════════════════════════════════════════════════════════════
# main
# ══════════════════════════════════════════════════════════════════════════

def cells() -> list[tuple]:
    """(cell_id, cid, slots, rank, is_main) —— ★ 十字形网格,不是全交叉。"""
    out = []
    only = os.environ.get("ONLY")
    pick = [x.strip() for x in only.split(",")] if only else list(SCORE_OF)
    for cid in SCORE_OF:
        if cid not in pick:
            continue
        mr = RANK_RULE[cid][2] if cid in RANK_RULE else None
        out.append((f"{cid}|s{SLOTS_MAIN}|r{mr}", cid, SLOTS_MAIN, mr, True))
        for s in SLOTS_GRID:
            if s != SLOTS_MAIN:
                out.append((f"{cid}|s{s}|r{mr}", cid, s, mr, False))
        if cid in RANK_RULE:
            for r in RANK_RULE[cid][3]:
                if r != mr:
                    out.append((f"{cid}|s{SLOTS_MAIN}|r{r}", cid,
                                SLOTS_MAIN, r, False))
    return out


def main(argv=None) -> int:
    OX.install()
    os.makedirs(PART_DIR, exist_ok=True)
    man = data.load_manifest()
    have_px = set(cache.symbols())
    # ★★★ 只用研发池那 250 只(有基本面 + 有行情)。
    #   ★ 实测:这 250 只的 fundamentals_path 全部在 pilot_300/ 下,exam_1042 命中 0。
    syms = [s for s in sorted(man) if man[s].fundamentals_path and s in have_px]

    # ★ RC.scope_mask 返回的是 numpy 数组,★★ 这里包成 DataFrame 便于对齐
    cal = data.trading_calendar()
    _sm, _ = RC.scope_mask(syms, cal, SCOPE)
    scope_mask = pd.DataFrame(_sm, index=cal, columns=syms)

    todo = cells()
    results, errs = {}, {}
    cov_cache: dict[str, dict] = {}
    for i, (cell, cid, slots, rank, is_main) in enumerate(todo):
        part = os.path.join(PART_DIR, cell.replace("|", "__") + ".json")
        if os.path.exists(part):
            results[cell] = json.load(open(part, encoding="utf-8"))
            continue
        raw = _load(cid)
        try:
            rec = run_cell(cid, raw, slots, rank, is_main, syms, scope_mask)
            if is_main:
                if cid not in cov_cache:
                    cov_cache[cid] = computability(cid, syms, scope_mask)
                rec["★可算率"] = cov_cache[cid]
        except Exception as e:
            rec = {"臂": cid, "slots": slots, "★自由参数档位": rank,
                   "★跑挂了": f"{type(e).__name__}: {e}",
                   "traceback": traceback.format_exc()[-2500:]}
            errs[cell] = rec["★跑挂了"]
        with open(part, "w", encoding="utf-8") as fh:        # ★ 先写
            json.dump(_num(rec), fh, ensure_ascii=False, indent=2, default=str)
        results[cell] = rec
        try:                                                  # ★ 再打印
            print(f"[{i+1}/{len(todo)}] {cell}  笔数={rec.get('笔数')} "
                  f"日均入选={(rec.get('★入选票数') or {}).get('日均入选只数')} "
                  f"用时={rec.get('耗时秒')}s {rec.get('★跑挂了','')}")
        except Exception as e:
            print(f"(打印出错:{type(e).__name__}: {e})")

    out = {
        "跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "窗口": f"{DEV[0]} .. {DEV[1]}(研发池)",
        "★只用研发池": "★★★ 考卷 exam_1042/ 一个文件都没读 —— "
                        "本脚本里没有这个路径。",
        "★红线④偏离登记": "★★★ 研发池本该是 2014–2020,★ 但 engine 的绩效窗口"
                           "`data.PERF_START` 是 2018-01-01(2016 起热机)—— "
                           "★★ 实际研发池只有 **3 年**,笔数先天偏少,"
                           "★★★ 报告里每一个数都要跟着这句话读。",
        "池子口径": f"{SCOPE}(大+中,成交额排名 1–2000)",
        "回测票池只数": len(syms),
        "★数据覆盖层": "★★★ **本轮一个都没挂** —— data.load_fundamentals 原封不动,"
                        "★ 所以结果里没有任何「换源」造成的差异(代码上可查)。",
        "★算子备注": OX.notes(),
        "★★★不跑/算不出来的格子": NOT_RUN,
        "格子数": len(todo),
        "跑挂的格子": errs,
        "格子": {k: _num(v) for k, v in results.items()},
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
    try:
        print(f"\n★ 写了:{OUT_JSON}")
        tot = sum((r.get("耗时秒") or 0) for r in results.values())
        print(f"★ 总耗时 {tot:.0f}s / {len(todo)} 格;跑挂 {len(errs)} 格")
    except Exception as e:
        print(f"(打印出错,结果已写出:{type(e).__name__}: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
