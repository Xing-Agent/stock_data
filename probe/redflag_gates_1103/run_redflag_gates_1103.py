#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 四道「财务排雷否决闸」各剔掉多少只票 —— 2026-11-03

══════════════════════════════════════════════════════════════════════════
★★★ 三秒版:只数个数。不看收益、不跑策略、不算 R。
     四道排雷闸(利息覆盖 / Sloan 应计 / Zmijewski / Beneish)各自剔掉多少
     票·日,两两交集多少,合起来(并集)多少,★ 再叠到「三道基本面闸全达标
     每天 6.74 只」上面看还剩几只。
══════════════════════════════════════════════════════════════════════════

★ 口径:一条都没另发明。
  · 闸门公式/阈值 = 任务单给的原文(见 ops_redflag_1103.py 顶部)
  · PIT           = engine/fundamentals.py 原封不动复用
  · 池子          = engine/pool_scope.py in_scope(),DEFAULT_SCOPE="large_mid"
  · 窗口          = engine/data.py PERF_START .. PERF_END
                    ★ 和 probe/gate_decomp_1103 那一轮一致,所以两份结果可比
  · 三道基本面闸  = probe/masters_57_1030/ops_q57_1030.py:metric_q()(原封不动调用)
                    阈值逐字来自 engine/configs/quality_compounder.yaml ① 段
  · 考卷那 1,042 只:★ 一只都没碰(只用 fundamentals_ext 研发池)

★★ engine/ 一个文件都没改。新库的 .json.gz 是**运行时把 data.load_fundamentals
   换掉**读的;SG&A 旁路科目是**运行时往 F.FLOW_METRICS 里加一个 key**。
   engine/ 下的文件内容一个字符都没动。

跑法:python3 probe/redflag_gates_1103/run_redflag_gates_1103.py
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
for p in (ROOT, HERE, os.path.join(ROOT, "probe", "masters_57_1030")):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import data, fundamentals as F, pool_scope          # noqa: E402
import ops_q57_1030 as Q                                        # noqa: E402
import ops_redflag_1103 as R                                    # noqa: E402

SCOPE = "large_mid"
EXT_DIR = os.path.join(ROOT, "fundamentals_ext")
POOL_CIK = os.path.join(ROOT, "probe", "fund_expand_1103",
                        "pool_cik_by_year_1103.csv")
POOL_FULL = pool_scope.pool_path()
OUT_JSON = os.path.join(HERE, "redflag_gates_1103.json")

# ★ 三道基本面闸的阈值 —— 逐字来自 quality_compounder.yaml ① 段
GATE1_YEARS, GATE1_MIN_ROIC = 3, 15.0
GATE2_THRESHOLD = 2.5
GATE3_MIN_PCTL = 80.0

#: 新库 loader 要留下的科目 = 三道基本面闸要的 + 四道排雷闸要的
NEED = ({m for m, _k in Q._COLS.values()} | R.NEEDED_METRICS) - {R.SGA_SYNTH}

#: raw_tags 里 SG&A 的 key 和字段顺序(= 文件里 raw_tags_fields)
SGA_RAW_KEY = "us-gaap:SellingGeneralAndAdministrativeExpense|USD"
RAW_FIELDS = ["val", "start", "end", "fy", "fp", "form", "filed", "accn", "frame"]

GATE_NAMES = {
    "①": "① 利息覆盖不足 EBIT÷利息费用 < 1",
    "②": "② 利润现金流背离 (NI−OCF)÷TA 截面最高10%",
    "③": "③ 破产概率 Zmijewski > 50%",
    "④": "④ Beneish M-Score > −1.78",
}


# ══════════════════════════════════════════════════════════════════════════
# 一 · 新库 loader(运行时替换 data.load_fundamentals,engine/ 未改)
# ══════════════════════════════════════════════════════════════════════════

_ORIG_LOADER = data.load_fundamentals
_EXT_STATS = {"命中": 0, "文件不存在": 0,
              "financial_versions 里有 SG&A 的文件": 0,
              "raw_tags 里有 SG&A 的文件": 0,
              "两处都没有 SG&A 的文件": 0}
#: 任务单第 4 道闸的「主档」口径:只认 financial_versions。
#: ★ 置 True 时额外把 raw_tags 里的 SG&A 接进来,作为**旁路**对照(报告里分开写)。
USE_RAWTAG_SGA = True

#: SG&A 在 financial_versions 里的科目名(SEC 标准标签名,★ 用来证明它真的没有)
SGA_FV_CANDIDATES = ("SellingGeneralAndAdministrativeExpense",
                     "SellingGeneralAndAdministrative", "SGA",
                     "GeneralAndAdministrativeExpense")


def _sga_from_rawtags(raw: dict) -> list[dict]:
    """把 raw_tags 里的 SG&A 位置数组翻译成 financial_versions 的记录形状。

    ★ 只做「换个形状」,没做任何口径加工:YTD 差分 / 首发版本 / TTM 四季连续
      全部交给 engine/fundamentals.py 的 quarterly()/ttm() 去做(所以口径和
      别的科目**完全同一套**)。
    ★ 唯一的口径差:raw_tags 的时间戳是 SEC **filed 日期**(没有受理时刻),
      financial_versions 用的是受理时刻(UTC)。两者 normalize 到日再 +1 交易日
      之后在绝大多数情况下同一天 —— ★ 但这是一处差异,报告里留痕。
    """
    rows = raw.get("raw_tags") or {}
    recs = rows.get(SGA_RAW_KEY) or []
    fields = raw.get("raw_tags_fields") or RAW_FIELDS
    ix = {f: i for i, f in enumerate(fields)}
    out = []
    for r in recs:
        try:
            start, end = r[ix["start"]], r[ix["end"]]
            filed, val = r[ix["filed"]], r[ix["val"]]
        except (IndexError, KeyError, TypeError):
            continue
        if not start or not end or not filed or val is None:
            continue
        out.append({"metric": R.SGA_SYNTH, "value": val, "unit": "USD",
                    "period_start": start, "period_end": end,
                    "filing_date": filed, "filed_at": filed,
                    "source_type": "sec_companyfacts_raw_tags",
                    "source_tag": SGA_RAW_KEY})
    return out


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
    out = {k: v for k, v in fv.items() if k in NEED}
    fv_has = any(fv.get(c) for c in SGA_FV_CANDIDATES)
    if fv_has:
        _EXT_STATS["financial_versions 里有 SG&A 的文件"] += 1
    sga = _sga_from_rawtags(raw) if USE_RAWTAG_SGA else []
    if sga:
        _EXT_STATS["raw_tags 里有 SG&A 的文件"] += 1
        out[R.SGA_SYNTH] = sga
    elif not fv_has:
        _EXT_STATS["两处都没有 SG&A 的文件"] += 1
    return out


def _clear_caches() -> None:
    for fn in (F.quarterly, F.ttm, F.quarter_frame, F.panel, F.shares_quarterly,
               Q.frame, Q.panel, Q.roic_consecutive):
        fn.cache_clear()
    R.clear_caches()


def use_ext_library() -> None:
    """★ 切到新库:只换 data.load_fundamentals 这一个函数引用。"""
    data.load_fundamentals = _load_ext
    # ★ SG&A 是利润表科目 = 流量,必须走 YTD 差分。这里把它登记进 FLOW_METRICS。
    #   ★ 这是**运行时改集合**,engine/fundamentals.py 文件本身没动。
    F.FLOW_METRICS.add(R.SGA_SYNTH)
    # ★ PropertyPlantAndEquipmentNet 是资产负债表余额 = 存量科目(不差分、不滚 TTM)。
    #   engine 的 STOCK_METRICS 里还没登记过它(老链没用到),这里运行时补登记。
    #   ★ engine/fundamentals.py 文件本身没动;★★ 它那条「不许猜口径」的护栏
    #   正是靠这个登记动作生效的 —— 我们是**显式声明**它是存量,不是绕过护栏。
    F.STOCK_METRICS.add("PropertyPlantAndEquipmentNet")
    _clear_caches()


# ══════════════════════════════════════════════════════════════════════════
# 二 · 池子掩膜 / 真实分母 —— ★ 和 probe/gate_decomp_1103 逐行一致
# ══════════════════════════════════════════════════════════════════════════

def ext_pool_mask(cal, perf):
    rows = list(csv.DictReader(open(POOL_CIK, encoding="utf-8-sig")))
    by_year, miss_file = {}, set()
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


def true_pool_cells(cal, perf) -> dict:
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
# 三 · 四道排雷闸的掩膜
# ══════════════════════════════════════════════════════════════════════════

def redflag_masks(syms, scope_mask, cal):
    """返回 {闸名: (可评估掩膜, 触发剔除掩膜)} + 一些诊断。"""
    masks, diag = {}, {}

    # ---------------- ① EBIT ÷ 利息费用 < 1
    df = R.get("int_cov", syms).reindex(index=cal, columns=syms)
    ev = df.notna().to_numpy(bool) & scope_mask
    tr = (df < R.INTCOV_THRESHOLD).fillna(False).to_numpy(bool) & scope_mask
    masks[GATE_NAMES["①"]] = (ev, tr)
    del df

    # ---------------- ② Sloan 应计:★ 池内横截面最高 10%
    df = R.get("sloan_accrual", syms).reindex(index=cal, columns=syms)
    ev = df.notna().to_numpy(bool) & scope_mask
    # ★ 排名在「脚本列集合」里做,和 gate_decomp_1103 的 ③ GP/A 分位一个做法
    #   (照抄,为了可比)。算不出的票不参与排名 —— 报告附录里留痕。
    pct = df.rank(axis=1, pct=True)
    tr = ((df.notna()) & (pct > 1.0 - R.SLOAN_TOP_PCT)).to_numpy(bool) & scope_mask
    masks[GATE_NAMES["②"]] = (ev, tr)
    del df, pct

    # ---------------- ③ Zmijewski 概率 > 50%
    df = R.get("zmij_prob", syms).reindex(index=cal, columns=syms)
    ev = df.notna().to_numpy(bool) & scope_mask
    tr = (df > R.ZMIJEWSKI_P_THRESHOLD).fillna(False).to_numpy(bool) & scope_mask
    masks[GATE_NAMES["③"]] = (ev, tr)
    del df

    # ---------------- ④ Beneish M-Score > −1.78
    df = R.get("m_score", syms).reindex(index=cal, columns=syms)
    ev = df.notna().to_numpy(bool) & scope_mask
    tr = (df > R.BENEISH_THRESHOLD).fillna(False).to_numpy(bool) & scope_mask
    masks[GATE_NAMES["④"]] = (ev, tr)
    del df

    # ★ 诊断:八项里去掉 SGAI 的那七项全齐的票·日(= SG&A 到位后的覆盖率上限)
    d7 = R.get("m_score_no_sgai", syms).reindex(index=cal, columns=syms)
    ev7 = ((d7.fillna(0.0) > 0.5).to_numpy(bool)) & scope_mask
    diag["④ 七项(除SGAI)全齐票·日"] = int(ev7.sum())
    del d7

    return masks, diag, ev7


# ══════════════════════════════════════════════════════════════════════════
# 四 · 三道基本面闸的掩膜 —— ★ 逐行照搬 probe/gate_decomp_1103
# ══════════════════════════════════════════════════════════════════════════

def fundamental_masks(syms, scope_mask, cal):
    masks = {}
    lags = [0, 4, 8]                      # ★ years 主档口径
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
    ps = Q.roic_consecutive(tuple(syms), GATE1_YEARS, GATE1_MIN_ROIC, "years"
                            ).reindex(index=ev.index, columns=syms).fillna(False)
    masks["基① ROIC 连续3年≥15%(years)"] = (ev.to_numpy(bool) & scope_mask,
                                             ps.to_numpy(bool) & scope_mask)
    del ev, ps, evalable

    nd = Q.get("net_debt_to_ebitda", syms).reindex(index=cal, columns=syms)
    masks["基② 净负债÷EBITDA < 2.5"] = (
        nd.notna().to_numpy(bool) & scope_mask,
        (nd < GATE2_THRESHOLD).fillna(False).to_numpy(bool) & scope_mask)
    del nd

    gp = Q.get("gpa_ttm", syms).reindex(index=cal, columns=syms)
    pct = gp.rank(axis=1, pct=True)
    masks["基③ GP/A 池内横截面分位 ≥ 80"] = (
        gp.notna().to_numpy(bool) & scope_mask,
        (gp.notna() & (pct >= GATE3_MIN_PCTL / 100.0)).to_numpy(bool) & scope_mask)
    del gp, pct
    return masks


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
    POOL = tp["真实大+中池票·日合计"]
    print(f"★ 真实大+中池票·日 = {POOL:,d}")

    use_ext_library()
    syms, smask, pdiag = ext_pool_mask(cal, perf)
    print(f"实体轴 {len(syms)} 只,掩膜票·日 {int(smask.sum()):,d}")

    res = {"口径戳": pool_scope.stamp(SCOPE, {
        "本轮做法": "★★★ 只数个数:四道财务排雷否决闸各剔掉多少票·日 + 两两交集 + "
                    "并集 + 叠到三道基本面闸全达标上面。"
                    "★ 没跑任何策略、没算任何收益、没算任何 R、没碰考卷那 1,042 只。",
        "窗口": f"{data.PERF_START} .. {data.PERF_END}(交易日 {n_days} 个)"
                " ★ 和 probe/gate_decomp_1103 同一窗口,两份结果可比",
        "数据库": "fundamentals_ext/<代码>/fundamentals.json.gz(3,653 家)",
        "①公式": "EBIT_ttm ÷ InterestExpense_ttm < 1.0;利息费用 ≤ 0 判「算不出」"
                  "(不按 0 算、不当无穷大)—— Asquith 等 1994",
        "②公式": f"(NetIncome_ttm − OperatingCashFlow_ttm) ÷ TotalAssets,"
                  f"池内横截面排名 > {1 - R.SLOAN_TOP_PCT:.0%} 分位(= 最高 "
                  f"{R.SLOAN_TOP_PCT:.0%})—— Sloan 1996",
        "③公式": "X = −4.3 − 4.5·(NetIncome_ttm÷TotalAssets) "
                  "+ 5.7·(★★★ Liabilities 总负债 ÷ TotalAssets) "
                  "− 0.004·(CurrentAssets÷CurrentLiabilities);"
                  "P = 1/(1+e^−X) > 0.50 —— Zmijewski 1984。"
                  "★★★ 第二项用的是**总负债**(us-gaap:Liabilities),不是有息负债。",
        "④公式": "M = −4.84 + 0.920·DSRI + 0.528·GMI + 0.404·AQI + 0.892·SGI "
                  "+ 0.115·DEPI − 0.172·SGAI + 4.679·TATA − 0.327·LVGI > −1.78"
                  " —— Beneish 1999。★ 同比一律取 shift(4) 个季度(机械读法)。"
                  " ★ TATA 的分子原著是「持续经营利润 − 经营现金流」,库里没有"
                  "「持续经营利润」科目,用 NetIncome 代 —— 留痕。",
        "PIT": "engine/fundamentals.py 原封不动复用:申报日+1 交易日生效 / "
               "YTD 差分还原单季 / TTM 四季连续 / 同一期只留首发版本 / "
               "_to_daily 日频铺开",
        "engine 改动": "★ 零。新库用运行时替换 data.load_fundamentals 读;"
                       "SG&A 旁路科目用运行时往 F.FLOW_METRICS 加 key。"
                       "engine/ 下文件内容一个字符都没动。",
        "SG&A 来源": ("★ financial_versions 里没有 SG&A 这个科目;本轮把 raw_tags 里的 "
                      f"{SGA_RAW_KEY} 接进同一套 PIT 作为**旁路**口径。"
                      "★★ 主档(只认 financial_versions)下 ④ 覆盖率 = 0%,算不出。"
                      if USE_RAWTAG_SGA else "只认 financial_versions"),
    }), "真实池分母": POOL, "交易日数": n_days, "实体数": len(syms),
        "池子映射诊断": pdiag,
        "掩膜票·日": int(smask.sum()),
        "映射缺口占真实池": round(1 - int(smask.sum()) / POOL, 6)}

    # ------------------------------------------------------------- 排雷闸
    print("\n" + "=" * 70 + "\n★ 四道排雷闸")
    rmask, rdiag, ev7 = redflag_masks(syms, smask, cal)

    def _row(ev, tr):
        return {
            "池内票·日(真实大+中池)": POOL,
            "★可评估票·日": int(ev.sum()),
            "可评估占池内": round(float(ev.sum()) / POOL, 6),
            "★算不出票·日": POOL - int(ev.sum()),
            "算不出占池内": round(1 - float(ev.sum()) / POOL, 6),
            "★★触发剔除票·日": int(tr.sum()),
            "★★★剔除率(占可评估)": (round(float(tr.sum()) / float(ev.sum()), 6)
                                     if ev.sum() else None),
            "剔除票·日占池内": round(float(tr.sum()) / POOL, 6),
            "★每天平均剔掉几只": round(float(tr.sum()) / n_days, 4),
            "★每天平均有几只可评估": round(float(ev.sum()) / n_days, 4),
        }

    res["逐闸"] = {}
    for k, (ev, tr) in rmask.items():
        res["逐闸"][k] = _row(ev, tr)
        v = res["逐闸"][k]
        print(f"  {k}\n     可评估 {v['★可评估票·日']:>9,d} ({v['可评估占池内']:.2%})"
              f"  剔除 {v['★★触发剔除票·日']:>9,d}"
              f"  剔除率 {v['★★★剔除率(占可评估)']}"
              f"  每天剔 {v['★每天平均剔掉几只']}")

    res["④ 诊断"] = dict(rdiag)
    res["④ 诊断"]["七项全齐占池内"] = round(rdiag["④ 七项(除SGAI)全齐票·日"] / POOL, 6)
    res["新库 loader 统计"] = dict(_EXT_STATS)

    # ------------------------------------------------------------- 两两交集 + 并集
    keys = [GATE_NAMES[k] for k in ("①", "②", "③", "④")]
    pair = {}
    for i in range(4):
        for j in range(i + 1, 4):
            a, b = keys[i], keys[j]
            ev = rmask[a][0] & rmask[b][0]
            tr = rmask[a][1] & rmask[b][1]
            pair[f"{a.split(' ')[0]}∩{b.split(' ')[0]}"] = {
                "两道都可评估票·日": int(ev.sum()),
                "★两道都触发剔除票·日": int(tr.sum()),
                "都剔除占池内": round(float(tr.sum()) / POOL, 6),
                "★每天平均几只被两道同时剔": round(float(tr.sum()) / n_days, 4)}
    res["两两交集"] = pair

    any_tr = np.zeros_like(smask)
    for k in keys:
        any_tr |= rmask[k][1]
    any_tr3 = np.zeros_like(smask)
    for k in keys[:3]:
        any_tr3 |= rmask[k][1]
    res["★★★并集(任一触发即剔)"] = {
        "四道并集剔除票·日": int(any_tr.sum()),
        "★★★占真实池": round(float(any_tr.sum()) / POOL, 6),
        "每天平均剔掉几只": round(float(any_tr.sum()) / n_days, 4),
        "前三道并集剔除票·日(★ 不含 Beneish)": int(any_tr3.sum()),
        "前三道占真实池": round(float(any_tr3.sum()) / POOL, 6),
        "前三道每天平均剔掉几只": round(float(any_tr3.sum()) / n_days, 4),
    }
    print(f"\n  ★★★ 四道并集剔除 {int(any_tr.sum()):,d} 票·日 = "
          f"{float(any_tr.sum()) / POOL:.2%} 的池子,每天平均剔 "
          f"{float(any_tr.sum()) / n_days:.2f} 只")

    # ------------------------------------------------------------- 叠到三道基本面闸
    print("\n" + "=" * 70 + "\n★★★ 叠到「三道基本面闸全达标」上面")
    fmask = fundamental_masks(syms, smask, cal)
    fk = list(fmask)
    pass3 = fmask[fk[0]][1] & fmask[fk[1]][1] & fmask[fk[2]][1]
    n3 = int(pass3.sum())
    print(f"  三道基本面闸全达标 {n3:,d} 票·日 = 每天 {n3 / n_days:.2f} 只"
          f"(★ gate_decomp_1103 记的是 13,563 / 6.74)")

    stack = {"三道基本面闸全达标票·日": n3,
             "三道全达标每天平均几只": round(n3 / n_days, 4),
             "★ 和 gate_decomp_1103 对账": "该轮记 13,563 票·日 / 6.74 只每天"}
    for k in keys:
        survive = pass3 & ~rmask[k][1]
        stack[f"再叠 {k.split(' ')[0]} 之后"] = {
            "剩下票·日": int(survive.sum()),
            "★每天平均剩几只": round(float(survive.sum()) / n_days, 4),
            "被这道闸剔掉票·日": n3 - int(survive.sum()),
            "被剔掉占三道全达标": (round(1 - float(survive.sum()) / n3, 6)
                                   if n3 else None)}
    sv_all = pass3 & ~any_tr
    sv_3 = pass3 & ~any_tr3
    stack["★★★ 四道排雷闸全叠完"] = {
        "剩下票·日": int(sv_all.sum()),
        "★★★每天平均剩几只": round(float(sv_all.sum()) / n_days, 4),
        "被排雷闸剔掉票·日": n3 - int(sv_all.sum()),
        "★★★被剔掉占三道全达标": (round(1 - float(sv_all.sum()) / n3, 6)
                                   if n3 else None)}
    stack["★ 只叠前三道(不含 Beneish)"] = {
        "剩下票·日": int(sv_3.sum()),
        "★每天平均剩几只": round(float(sv_3.sum()) / n_days, 4),
        "被剔掉占三道全达标": (round(1 - float(sv_3.sum()) / n3, 6) if n3 else None)}
    res["★★★ 排雷闸叠在基本面闸之上"] = stack
    print(f"  ★★★ 四道排雷闸全叠完,剩 {int(sv_all.sum()):,d} 票·日 = "
          f"每天 {float(sv_all.sum()) / n_days:.2f} 只"
          f"(剔掉 {1 - float(sv_all.sum()) / n3:.1%})")
    print(f"  ★ 只叠前三道,剩 每天 {float(sv_3.sum()) / n_days:.2f} 只")

    # ★ 严端敏感度:算不出也当「剔掉」(= 看不见就不许买)
    strict = np.zeros_like(smask)
    for k in keys:
        strict |= (rmask[k][1] | (~rmask[k][0] & smask))
    res["★ 敏感度:算不出也剔(严端)"] = {
        "四道严端并集剔除票·日": int(strict.sum()),
        "占真实池": round(float(strict.sum()) / POOL, 6),
        "叠在三道全达标之上剩下票·日": int((pass3 & ~strict).sum()),
        "★每天平均剩几只": round(float((pass3 & ~strict).sum()) / n_days, 4),
        "读法": "★ 否决闸的默认读法是「看不见 → 不否决」(宽端,上面主档用的就是它);"
                "这一行是反过来「看不见 → 也否决」的严端,给策略层拍板用。"}
    print(f"  ★ 严端(算不出也剔):剩 每天 "
          f"{float((pass3 & ~strict).sum()) / n_days:.2f} 只")

    res["耗时秒"] = round(time.time() - t0, 1)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n→ {os.path.relpath(OUT_JSON, ROOT)}  ({res['耗时秒']}s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
