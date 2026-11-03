#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 三道基本面闸的分解 —— 老库(250 只)vs 新库(3,654 家)  2026-11-03

══════════════════════════════════════════════════════════════════════════
★★★ 三秒版:只数个数。不看收益、不跑策略、不算 R。
     把 10-30 那一轮 run_masters_57_1030.py:gate_decomposition() 的同一套口径
     搬到扩池后的新库上重算一遍,并补上两两交集和三道全达标。
══════════════════════════════════════════════════════════════════════════

★ 口径:一条都没另发明。
  · 闸门定义/阈值  = engine/configs/quality_compounder.yaml ① 段,逐字
  · 指标算法        = probe/masters_57_1030/ops_q57_1030.py:metric_q()(原封不动调用)
  · PIT             = engine/fundamentals.py(申报日 + 1 交易日生效;YTD 差分;
                      TTM 四季连续;同一期只留首发版本)—— 原封不动复用
  · 池子            = engine/pool_scope.py in_scope(),DEFAULT_SCOPE="large_mid"
  · 窗口            = engine/data.py PERF_START .. PERF_END
                      ★ 和 gate_decomposition 当轮一致(见报告「窗口」一节)

★★ engine/ 一个字符都没改。新库的 .json.gz 是**运行时把 data.load_fundamentals
   换掉**读的(engine/data.py 文件本身没动)。

跑法:python3 probe/gate_decomp_1103/run_gate_decomp_1103.py
"""
from __future__ import annotations

import csv
import functools
import gzip
import json
import os
import sys
import time

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, os.path.join(ROOT, "probe", "masters_57_1030"),
          os.path.join(ROOT, "probe", "v2_rerun_1030")):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import data, fundamentals as F, pool_scope          # noqa: E402
import ops_q57_1030 as Q                                        # noqa: E402
import rerun_core_1030 as RC                                    # noqa: E402

SCOPE = "large_mid"
EXT_DIR = os.path.join(ROOT, "fundamentals_ext")
POOL_CIK = os.path.join(ROOT, "probe", "fund_expand_1103",
                        "pool_cik_by_year_1103.csv")
POOL_FULL = pool_scope.pool_path()
OUT_JSON = os.path.join(HERE, "gate_decomp_1103.json")

# ★ 闸门阈值 —— 逐字来自 quality_compounder.yaml ① 段,一个都没新拍
GATE1_YEARS, GATE1_MIN_ROIC = 3, 15.0      # roic_consecutive_above
GATE2_THRESHOLD = 2.5                      # net_debt_to_ebitda_below
GATE3_MIN_PCTL = 80.0                      # gross_profit_to_assets_rank_above

#: Q.frame() 要用到的 13 个科目(★ 只为了给新库的 loader 做裁剪,不改口径)
NEED = {m for m, _k in Q._COLS.values()}


# ══════════════════════════════════════════════════════════════════════════
# 一 · 新库 loader(运行时替换 data.load_fundamentals,engine/ 未改)
# ══════════════════════════════════════════════════════════════════════════

_ORIG_LOADER = data.load_fundamentals
_EXT_STATS = {"命中": 0, "文件不存在": 0}


@functools.lru_cache(maxsize=4)
def _load_ext(symbol: str) -> dict:
    p = os.path.join(EXT_DIR, symbol, "fundamentals.json.gz")
    if not os.path.exists(p):
        _EXT_STATS["文件不存在"] += 1
        return {}
    with gzip.open(p, "rt", encoding="utf-8") as fh:
        raw = json.load(fh)
    _EXT_STATS["命中"] += 1
    fv = raw.get("financial_versions") or {}
    return {k: v for k, v in fv.items() if k in NEED}


def _clear_caches() -> None:
    for fn in (F.quarterly, F.ttm, F.quarter_frame, F.panel, F.shares_quarterly,
               Q.frame, Q.panel, Q.roic_consecutive):
        fn.cache_clear()


def use_ext_library() -> None:
    """★ 切到新库:只换 data.load_fundamentals 这一个函数引用。"""
    data.load_fundamentals = _load_ext
    _clear_caches()


def use_old_library() -> None:
    data.load_fundamentals = _ORIG_LOADER
    _clear_caches()


# ══════════════════════════════════════════════════════════════════════════
# 二 · 闸门分解 —— ★ 逐行照搬 gate_decomposition(),只多留下布尔掩膜做交集
# ══════════════════════════════════════════════════════════════════════════

def _decomp(syms: list[str], scope_mask: np.ndarray, cal: pd.DatetimeIndex,
            n_days: int, pool_cells_override: int | None = None) -> tuple[dict, dict]:
    """返回 (逐闸统计, 掩膜字典)。统计口径和 1030 那一轮逐字一致。"""
    out: dict = {}
    masks: dict = {}
    pool_cells = int(pool_cells_override if pool_cells_override is not None
                     else scope_mask.sum())

    def _row(ev_m, ps_m, extra=None) -> dict:
        d = {
            "池内票·日": pool_cells,
            "★可评估票·日": int(ev_m.sum()),
            "可评估占池内": round(float(ev_m.sum()) / pool_cells, 6) if pool_cells else None,
            "★达标票·日": int(ps_m.sum()),
            "★★可评估里的达标率": (round(float(ps_m.sum()) / float(ev_m.sum()), 6)
                                   if ev_m.sum() else None),
            "★每天平均有几只通过": (round(float(ps_m.sum()) / n_days, 4)
                                    if n_days else None),
            "★每天平均有几只可评估": (round(float(ev_m.sum()) / n_days, 4)
                                      if n_days else None),
        }
        if extra:
            d.update(extra)
        return d

    # ---------------- ① ROIC 连续 3 年 ≥ 15%
    for mode in ("years", "quarters"):
        lags = [0, 4, 8] if mode == "years" else list(range(12))
        evalable = {}
        for s in syms:
            vq, e = Q.metric_q(s, "roic_ttm")
            if vq.empty:
                continue
            ok = None
            for L in lags:
                c = vq.shift(L).notna()
                ok = c if ok is None else (ok & c)
            evalable[s] = F._to_daily(ok.astype(float), e, cal).fillna(0.0) > 0.5
        ev = pd.DataFrame(evalable).reindex(index=cal, columns=syms).fillna(False)
        ps = Q.roic_consecutive(tuple(syms), GATE1_YEARS, GATE1_MIN_ROIC, mode
                                ).reindex(index=ev.index, columns=syms).fillna(False)
        ev_m = ev.to_numpy(bool) & scope_mask
        ps_m = ps.to_numpy(bool) & scope_mask
        key = f"① ROIC 连续3年≥15%({mode})"
        out[key] = _row(ev_m, ps_m, {
            "★★★ 读法": "「可评估占池内」低 = 我们看不到;"
                         "「可评估里的达标率」低 = 这个门槛本身严。两件事不许混。"})
        masks[key] = (ev_m, ps_m)
        del ev, ps, evalable

    # ---------------- ② 净负债 / EBITDA < 2.5
    nd = Q.get("net_debt_to_ebitda", syms).reindex(index=cal, columns=syms)
    ev_m = nd.notna().to_numpy(bool) & scope_mask
    ps_m = (nd < GATE2_THRESHOLD).fillna(False).to_numpy(bool) & scope_mask
    key2 = "② 净负债÷EBITDA < 2.5"
    out[key2] = _row(ev_m, ps_m)
    masks[key2] = (ev_m, ps_m)
    del nd

    # ---------------- ③ GP/A 池内横截面分位 ≥ 80
    gp = Q.get("gpa_ttm", syms).reindex(index=cal, columns=syms)
    pct = gp.rank(axis=1, pct=True)
    ev_m = gp.notna().to_numpy(bool) & scope_mask
    ps_m = (gp.notna() & (pct >= GATE3_MIN_PCTL / 100.0)).to_numpy(bool) & scope_mask
    key3 = "③ GP/A 池内横截面分位 ≥ 80"
    out[key3] = _row(ev_m, ps_m, {
        "★ 注意": "分位闸是**池内横截面**的 —— 算不出的票不参与排名,"
                   "★★ 所以「前 20%」实际是「**算得出的那批里**的前 20%」,"
                   "覆盖率低的时候这道闸比纸面上松得多。"})
    masks[key3] = (ev_m, ps_m)
    del gp, pct

    return out, masks


def _intersections(masks: dict, pool_cells: int, n_days: int) -> dict:
    """★★★ 两两交集 + 三道全达标。① 取 years 口径(主档),quarters 另列一份。"""
    res = {}
    for mode in ("years", "quarters"):
        k1 = f"① ROIC 连续3年≥15%({mode})"
        trio = [(("①", k1)), (("②", "② 净负债÷EBITDA < 2.5")),
                (("③", "③ GP/A 池内横截面分位 ≥ 80"))]
        blk = {}
        for i in range(3):
            for j in range(i + 1, 3):
                (na, ka), (nb, kb) = trio[i], trio[j]
                ev = masks[ka][0] & masks[kb][0]
                ps = masks[ka][1] & masks[kb][1]
                blk[f"{na}∩{nb}"] = {
                    "★两道都可评估票·日": int(ev.sum()),
                    "两道都可评估占池内": round(float(ev.sum()) / pool_cells, 6) if pool_cells else None,
                    "★★两道都达标票·日": int(ps.sum()),
                    "两道都达标占池内": round(float(ps.sum()) / pool_cells, 6) if pool_cells else None,
                    "★每天平均有几只两道都达标": round(float(ps.sum()) / n_days, 4) if n_days else None,
                }
        ev3 = masks[k1][0] & masks[trio[1][1]][0] & masks[trio[2][1]][0]
        ps3 = masks[k1][1] & masks[trio[1][1]][1] & masks[trio[2][1]][1]
        blk["①∩②∩③ 三道全"] = {
            "★★★三道都可评估票·日": int(ev3.sum()),
            "三道都可评估占池内": round(float(ev3.sum()) / pool_cells, 6) if pool_cells else None,
            "★★★三道全达标票·日": int(ps3.sum()),
            "三道全达标占池内": round(float(ps3.sum()) / pool_cells, 6) if pool_cells else None,
            "★★★每天平均有几只三道全达标": round(float(ps3.sum()) / n_days, 4) if n_days else None,
        }
        res[f"①用{mode}口径"] = blk
    return res


# ══════════════════════════════════════════════════════════════════════════
# 三 · 新库的池子掩膜 —— 实体轴用 fundamentals_ext 的文件夹名
# ══════════════════════════════════════════════════════════════════════════

def ext_pool_mask(cal: pd.DatetimeIndex, perf: np.ndarray
                  ) -> tuple[list[str], np.ndarray, dict]:
    rows = list(csv.DictReader(open(POOL_CIK, encoding="utf-8-sig")))
    by_year: dict[str, set[str]] = {}
    miss_file = set()
    for r in rows:
        try:
            rk = int(float(r["rank"]))
        except (TypeError, ValueError):
            continue
        if not pool_scope.in_scope(rk, SCOPE):
            continue
        fo = (r["folder"] or "").strip()
        if not fo:
            continue
        if not os.path.exists(os.path.join(EXT_DIR, fo, "fundamentals.json.gz")):
            miss_file.add(fo)
            continue
        by_year.setdefault(r["year"], set()).add(fo)
    syms = sorted({s for y, ss in by_year.items() for s in ss
                   if "2018" <= y <= "2025"})
    years = np.array([str(d.year) for d in cal])
    col = {s: j for j, s in enumerate(syms)}
    mask = np.zeros((len(cal), len(syms)), dtype=bool)
    for y, ss in by_year.items():
        sel = (years == y)
        if not sel.any():
            continue
        for s in ss:
            if s in col:
                mask[sel, col[s]] = True
    mask &= perf[:, None]
    diag = {"实体轴(fundamentals_ext 文件夹)只数": len(syms),
            "索引里 rank≤2000 但 ext 里没文件": sorted(miss_file),
            "每年映射上的只数": {y: len(ss) for y, ss in sorted(by_year.items())},
            "掩膜为真的票日": int(mask.sum())}
    return syms, mask, diag


def true_pool_cells(cal: pd.DatetimeIndex, perf: np.ndarray) -> dict:
    """★ 真实大+中池的票·日(= 每年 2000 只 × 当年交易日数)—— 诚实的分母。"""
    cnt: dict[str, set] = {}
    with open(POOL_FULL, newline="", encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            try:
                rk = int(float(r["rank"]))
            except (TypeError, ValueError):
                continue
            if pool_scope.in_scope(rk, SCOPE):
                cnt.setdefault(r["year"], set()).add(r["company_id"])
    years = np.array([str(d.year) for d in cal])
    total, per_year = 0, {}
    for y in sorted(cnt):
        if not ("2018" <= y <= "2025"):
            continue
        nd = int((perf & (years == y)).sum())
        per_year[y] = {"在池公司数": len(cnt[y]), "交易日数": nd,
                       "票·日": len(cnt[y]) * nd}
        total += len(cnt[y]) * nd
    return {"真实大+中池票·日合计": total, "逐年": per_year}


# ══════════════════════════════════════════════════════════════════════════
def main() -> int:
    t0 = time.time()
    Q.install()
    cal = data.trading_calendar()
    perf = np.asarray((cal >= pd.Timestamp(data.PERF_START)) &
                      (cal <= pd.Timestamp(data.PERF_END)), dtype=bool)
    n_days = int(perf.sum())
    print(f"窗口 {data.PERF_START} .. {data.PERF_END},交易日 {n_days} 个")
    print(f"池子口径 {SCOPE} = {pool_scope.SCOPE_LABELS[SCOPE]}")

    tp = true_pool_cells(cal, perf)
    print(f"★ 真实大+中池票·日 = {tp['真实大+中池票·日合计']:,d}")

    res: dict = {"口径戳": pool_scope.stamp(SCOPE, {
        "本轮做法": "★★★ 只数个数:三道基本面闸的「算不出 vs 分低」分解 + 两两交集,"
                    "老库(pilot_300 的 250 只)vs 新库(fundamentals_ext 3,654 家)。"
                    "★ 没跑任何策略、没算任何收益、没算任何 R。",
        "窗口": f"{data.PERF_START} .. {data.PERF_END}(交易日 {n_days} 个)"
                "★ 照 gate_decomposition 当轮用的 data.PERF_START/PERF_END,"
                "不是任务单提到的 2018-2020",
        "闸门定义出处": "engine/configs/quality_compounder.yaml ① 段逐字:"
                        f"roic_consecutive_above(years={GATE1_YEARS}, "
                        f"min_roic_pct={GATE1_MIN_ROIC}, basis=TTM) / "
                        f"net_debt_to_ebitda_below(threshold={GATE2_THRESHOLD}, basis=TTM) / "
                        f"gross_profit_to_assets_rank_above(min_percentile={GATE3_MIN_PCTL}, basis=TTM)",
        "指标实现": "probe/masters_57_1030/ops_q57_1030.py:metric_q()(原封不动调用)",
        "PIT": "engine/fundamentals.py:申报日+1 交易日生效 / YTD 差分还原单季 / "
               "TTM 要求四季连续 / 同一期只留首发版本 —— 原封不动复用",
        "engine 改动": "★ 零。新库的 .json.gz 用运行时替换 data.load_fundamentals 读,"
                       "engine/data.py 文件本身一个字符都没改。",
    }), "真实池分母": tp, "交易日数": n_days}

    # ---------------------------------------------------------------- 老库
    print("\n" + "=" * 70 + "\n★ 老库(pilot_300 的 250 只 fundamentals.json)")
    use_old_library()
    man = data.load_manifest()
    syms_old = [s for s in sorted(man) if man[s].fundamentals_path]
    smask_old, sdiag_old = RC.scope_mask(syms_old, cal, SCOPE)
    smask_old = smask_old & perf[:, None]
    print(f"  有 fundamentals.json 的 {len(syms_old)} 只,"
          f"在大+中池的票·日 {int(smask_old.sum()):,d}")
    d_old, m_old = _decomp(syms_old, smask_old, cal, n_days)
    i_old = _intersections(m_old, int(smask_old.sum()), n_days)
    i_old_truepool = _intersections(m_old, tp["真实大+中池票·日合计"], n_days)
    res["老库_250只"] = {
        "实体数": len(syms_old),
        "池内票·日(1030 原分母:250 只里在大+中池的)": int(smask_old.sum()),
        "逐闸": d_old, "两两交集_分母=1030原分母": i_old,
        "两两交集_分母=真实大中池": i_old_truepool,
        "池子掩膜诊断": {k: v for k, v in sdiag_old.items() if k != "票×年 解析方式计数"},
    }
    for k, v in d_old.items():
        print(f"  {k}\n     可评估 {v['★可评估票·日']:>9,d} / 池内 {v['池内票·日']:>9,d}"
              f" = {v['可评估占池内']:.2%}  达标 {v['★达标票·日']:>9,d}"
              f"  达标率 {v['★★可评估里的达标率']}  每天平均过 {v['★每天平均有几只通过']}")
    del m_old

    # ---------------------------------------------------------------- 新库
    print("\n" + "=" * 70 + "\n★ 新库(fundamentals_ext 3,654 家 .json.gz)")
    use_ext_library()
    syms_new, smask_new, ndiag = ext_pool_mask(cal, perf)
    print(f"  实体轴 {len(syms_new)} 只,掩膜票·日 {int(smask_new.sum()):,d}")
    d_new, m_new = _decomp(syms_new, smask_new, cal, n_days,
                           pool_cells_override=tp["真实大+中池票·日合计"])
    d_new_own, _ = None, None
    i_new = _intersections(m_new, tp["真实大+中池票·日合计"], n_days)
    res["新库_3654家"] = {
        "实体数": len(syms_new),
        "★池内票·日(分母=真实大+中池 2000只×交易日)": tp["真实大+中池票·日合计"],
        "掩膜票·日(索引映射上、且 ext 里有文件的部分)": int(smask_new.sum()),
        "映射缺口占真实池": round(1 - int(smask_new.sum()) / tp["真实大+中池票·日合计"], 6),
        "逐闸": d_new, "两两交集": i_new, "池子映射诊断": ndiag,
        "新库 loader 统计": dict(_EXT_STATS),
    }
    for k, v in d_new.items():
        print(f"  {k}\n     可评估 {v['★可评估票·日']:>9,d} / 池内 {v['池内票·日']:>9,d}"
              f" = {v['可评估占池内']:.2%}  达标 {v['★达标票·日']:>9,d}"
              f"  达标率 {v['★★可评估里的达标率']}  每天平均过 {v['★每天平均有几只通过']}")
    print("\n  ★★★ 交集(① years 口径)")
    for k, v in i_new["①用years口径"].items():
        print(f"    {k:14s} 都可评估 {v.get('★两道都可评估票·日', v.get('★★★三道都可评估票·日')):>9,d}"
              f"   都达标 {v.get('★★两道都达标票·日', v.get('★★★三道全达标票·日')):>9,d}")
    del m_new

    res["算子备注"] = Q.notes()
    res["耗时秒"] = round(time.time() - t0, 1)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n→ {os.path.relpath(OUT_JSON, ROOT)}  ({res['耗时秒']}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
