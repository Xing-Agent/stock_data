#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 补 us-gaap 标签 —— 把「我们只问了一个标签」这个 bug 修掉(2026-10-30)

三秒版:`LongTermDebt` 我们只认了**一个**标签 `LongTermDebtNoncurrent`,
        `EBIT` 的 177 只**全是推导的、一条原始标签记录都没有**。
        ★ 本文件按**事先声明的优先级梯子**把同义标签补回去,
        ★★ 逐只票记清「用了哪一级、哪个标签、覆盖率从多少变到多少」。

══════════════════════════════════════════════════════════════════════════
★★ 数据来源(★ 本地,★★ 不连 SEC —— 本机 data.sec.gov 被代理 403 挡住)
══════════════════════════════════════════════════════════════════════════
  ① 本地 `pilot_300/*/fundamentals.json` 的 `financial_versions`
     —— ★ 每条带 `source_tag`,所以「我们实际问了哪个标签」是可查的
  ② 本地 `probe/fundamentals_sec_1030/sec_companyfacts_300_1030.json.gz`
     —— ★★ 这是 **2026-10-30 08:03 抓下来的 SEC companyfacts 原始数据**
        (301 家 · 21 个负债/利润相关标签 · 字段
         val/start/end/fy/fp/form/filed/accn/frame)
     ★★★ 上一轮报「本地无法连 SEC 验证」时**没用到这份文件** ——
        它当天就已经提交进仓库了(commit ab1e6de)。
        ★ 所以「乙类 55 只是下限」这句话现在**可以变成实测**。

★★★ PIT 的一处口径让步,必须登记:
   ★ 本地记录有 `accepted_at`(带时分秒的 SEC 受理时间),★★ 而这份 dump 只有
     `filed`(日期,无时分)。★ 本文件对 dump 补进来的记录用
     `filed` 当生效基准(再 +1 个交易日,和 engine 一致)。
   ★★ 这是**用了 `filed_at` 口径**,和纪律「一律用 available_at / accepted_at」相悖。
   ★ 处置:在两边**都有**的记录上逐条对差(见 `PIT口径对差`),
     把偏差量出来而不是假设它为零;★★★ 偏差不为零的部分一律在报告里写明。

══════════════════════════════════════════════════════════════════════════
★★★ 优先级梯子(★ 跑之前定稿,★★ 看了结果不许改)
══════════════════════════════════════════════════════════════════════════
【目标一】`LTD_NC`:和我们现有 `LongTermDebt` 字段**同一个语义** = 非当期长期债务
   R1 本地 `LongTermDebtNoncurrent`(含 `us-gaap:` 带前缀写法)   ← 现状
   R2 dump  `LongTermDebtNoncurrent`
   R3 dump  `LongTermDebt`(**平标签 = 含当期的总额**)− 当期部分
            ★ 当期部分 = 本地/dump 的 `LongTermDebtCurrent`,★★ 同一 period_end
              两边都要有值才做这个减法 —— ★★★ 不许只拿平标签直接当非当期用,
              那会把当期到期部分**重复计一次**(这是本梯子最要紧的一道防线)
   R4 dump  `LongTermDebtAndCapitalLeaseObligations`
            ★★ 口径含**融资租赁**,比纯债务偏大 → 逐只标明,报告单列
   R5 dump  `LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities`
            − `LongTermDebtAndCapitalLeaseObligationsCurrent`(两边都要有)
   ★ **不用** `DebtInstrumentCarryingAmount` —— 它是**单笔债务工具**的账面额,
     同一期有多笔会重复,不是总额(实测 51 只有这个标签,★ 一律不采)
   ★ **不用** `FinanceLeaseLiabilityNoncurrent` 单独顶 —— 租赁不是债务

【目标二】`LTD_TOTAL`:**含当期**的长期债务总额(★ 新指标,现有字段里没有)
   T1 dump 平标签 `LongTermDebt`
   T2 `LTD_NC` + `LongTermDebtCurrent`(两边都有)
   T3 dump `LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities`

【目标三】`EBIT_F`
   E1 本地已有的 derived EBIT(`IncomeBeforeTax + InterestExpense`)   ← 现状
   E2 dump 税前利润 + dump 利息费用
      ★ 税前利润两种标签都认(…ExtraordinaryItemsNoncontrollingInterest /
        …MinorityInterestAndIncomeLossFromEquityMethodInvestments)
      ★ 利息费用按 InterestExpense → InterestExpenseNonoperating →
        InterestExpenseDebt → InterestAndDebtExpense 顺序回落
   E3 dump `OperatingIncomeLoss`
      ★★★ **这一级口径不同** —— 营业利润 ≠ EBIT(差的是非经营性损益)。
      ★ 所以 E3 **单独统计、单独开关**,并在两边都有值的期上**逐期量差**;
      ★★ 不许把 E3 混进 E1/E2 就说「EBIT 覆盖率提高了」。

★ 「天」一律是交易日。★ 先写结果再打印。
跑法:python3 probe/fundamental_buildout_1030/tag_backfill_1030.py
"""
from __future__ import annotations

import gzip
import json
import os
import sys
from collections import Counter, defaultdict

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import data  # noqa: E402

DUMP = os.path.join(ROOT, "probe", "fundamentals_sec_1030",
                    "sec_companyfacts_300_1030.json.gz")
OUT_OVERLAY = os.path.join(HERE, "tag_overlay_1030.json.gz")
OUT_JSON = os.path.join(HERE, "tag_backfill_1030.json")
OUT_CSV = os.path.join(HERE, "逐只票-补标签前后-1030.csv")

PRETAX = ("IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItems"
          "NoncontrollingInterest",
          "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterest"
          "AndIncomeLossFromEquityMethodInvestments")
INTEREST = ("InterestExpense", "InterestExpenseNonoperating",
            "InterestExpenseDebt", "InterestAndDebtExpense")

#: ★ 明确不采的标签 + 理由(★ 登记在册,免得以后有人以为我们漏了)
REJECTED_TAGS = {
    "DebtInstrumentCarryingAmount": "★ 单笔债务工具的账面额,同一期多笔会重复 —— "
                                    "不是总额(本地实测 51 只有这个标签)",
    "FinanceLeaseLiabilityNoncurrent": "★ 融资租赁负债,不是债务;"
                                       "只在 R4/R5 的合报标签里间接含着",
    "LongTermLineOfCredit": "★ 循环信贷额度的已提取部分 —— 是债务的一个分项,"
                            "单独顶会系统性偏小;★ 只在平标签都没有时才有意义,"
                            "本轮梯子不采(留给下一轮)",
    "LongTermNotesPayable": "★ 同上,分项",
    "SeniorLongTermNotes": "★ 同上,分项",
    "ConvertibleLongTermNotesPayable": "★ 同上,分项",
    "ConvertibleNotesPayable": "★ 同上,分项",
    "OtherLongTermDebtNoncurrent": "★ 「其他」类分项,★★ 按定义就不是总额",
}


# ══════════════════════════════════════════════════════════════════════════
# 一 · 读两个来源
# ══════════════════════════════════════════════════════════════════════════

def load_dump() -> tuple[dict, list[str]]:
    d = json.load(gzip.open(DUMP, "rt", encoding="utf-8"))
    return d["companies"], d["fields"]


def dump_series(co: dict, tag: str, fields: list[str]) -> dict:
    """{period_end: {"val":…, "start":…, "filed":…, "accn":…, "form":…}} —— ★ 留首发版。"""
    recs = (co.get("tags") or {}).get(tag) or []
    iv, istart, iend = fields.index("val"), fields.index("start"), fields.index("end")
    ifiled, iaccn, iform = (fields.index("filed"), fields.index("accn"),
                            fields.index("form"))
    out: dict[str, dict] = {}
    for r in recs:
        try:
            val = float(r[iv])
        except (TypeError, ValueError):
            continue
        end, filed = r[iend], r[ifiled]
        if not end or not filed:
            continue
        key = (r[istart] or "", end)
        cur = out.get(key)
        if cur is None or filed < cur["filed"]:
            out[key] = {"val": val, "start": r[istart] or None, "end": end,
                        "filed": filed, "accn": r[iaccn], "form": r[iform],
                        "tag": tag}
    return out


def local_series(sym: str, metric: str) -> dict:
    """本地记录 → {(period_start, period_end): rec} 留首发版(按 accepted_at)。"""
    out: dict = {}
    for r in (data.load_fundamentals(sym).get(metric) or []):
        pe = r.get("period_end")
        if pe is None or r.get("value") in (None, ""):
            continue
        acc = r.get("available_at") or r.get("accepted_at") or r.get("filed_at")
        key = (r.get("period_start") or "", str(pe)[:10])
        cur = out.get(key)
        if cur is None or str(acc) < str(cur.get("_acc")):
            out[key] = {"val": float(r["value"]), "start": r.get("period_start"),
                        "end": str(pe)[:10], "filed": str(r.get("filed_at"))[:10],
                        "accn": r.get("filing_accession"),
                        "form": r.get("source_form"),
                        "tag": r.get("source_tag") or "(derived)", "_acc": acc}
    return out


def _mk(rec: dict, rung: str, note: str = "") -> dict:
    """做成 engine 认得的记录格式。★ 生效基准写明是 accepted_at 还是 filed。"""
    acc = rec.get("_acc")
    return {
        "metric": None, "value": rec["val"], "unit": "USD",
        "period_start": rec.get("start"), "period_end": rec["end"],
        "filed_at": rec.get("filed"),
        "accepted_at": acc or rec.get("filed"),
        "available_at": acc or rec.get("filed"),
        "filing_date": acc or rec.get("filed"),
        "filing_accession": rec.get("accn"), "source_form": rec.get("form"),
        "source_tag": rec.get("tag"), "taxonomy": "us-gaap",
        "pit_status": "strict" if acc else "filed_date_only",
        "★补标签_级": rung,
        "★生效基准": "accepted_at(本地)" if acc else "filed(dump,无时分 —— 登记在册)",
        "★口径备注": note,
    }


# ══════════════════════════════════════════════════════════════════════════
# 二 · 三个目标的梯子
# ══════════════════════════════════════════════════════════════════════════

def build_ltd_nc(sym: str, co: dict, fields: list[str]) -> tuple[list, Counter]:
    """目标一:非当期长期债务。返回 (记录表, 每级命中的期数)。"""
    used = Counter()
    loc = local_series(sym, "LongTermDebt")                     # R1
    ltdc_loc = local_series(sym, "LongTermDebtCurrent")
    d_nc = dump_series(co, "LongTermDebtNoncurrent", fields)    # R2
    d_flat = dump_series(co, "LongTermDebt", fields)            # R3
    d_ltdc = dump_series(co, "LongTermDebtCurrent", fields)
    d_lcl = dump_series(co, "LongTermDebtAndCapitalLeaseObligations", fields)   # R4
    d_inc = dump_series(co, "LongTermDebtAndCapitalLeaseObligations"
                            "IncludingCurrentMaturities", fields)               # R5
    d_lclc = dump_series(co, "LongTermDebtAndCapitalLeaseObligationsCurrent",
                         fields)

    # 以 period_end 为准(存量科目,period_start 为空)
    def by_end(d: dict) -> dict:
        return {k[1]: v for k, v in d.items()}

    L, NC, FLAT, LTDC, LCL, INC, LCLC = (by_end(loc), by_end(d_nc), by_end(d_flat),
                                         by_end({**d_ltdc, **ltdc_loc}),
                                         by_end(d_lcl), by_end(d_inc),
                                         by_end(d_lclc))
    ends = sorted(set(L) | set(NC) | set(FLAT) | set(LCL) | set(INC))
    out = []
    for e in ends:
        if e in L:
            out.append(_mk(L[e], "R1_本地LongTermDebtNoncurrent")); used["R1"] += 1
        elif e in NC:
            out.append(_mk(NC[e], "R2_dump_LongTermDebtNoncurrent")); used["R2"] += 1
        elif e in FLAT and e in LTDC:
            r = dict(FLAT[e]); r["val"] = FLAT[e]["val"] - LTDC[e]["val"]
            out.append(_mk(r, "R3_平标签减当期",
                           "★ 平标签 LongTermDebt(含当期) − LongTermDebtCurrent"))
            used["R3"] += 1
        elif e in LCL:
            out.append(_mk(LCL[e], "R4_债务与融资租赁合报",
                           "★★ 口径含融资租赁,比纯债务偏大")); used["R4"] += 1
        elif e in INC and e in LCLC:
            r = dict(INC[e]); r["val"] = INC[e]["val"] - LCLC[e]["val"]
            out.append(_mk(r, "R5_合报含当期减当期",
                           "★★ 口径含融资租赁")); used["R5"] += 1
    return out, used


def build_ltd_total(sym: str, co: dict, fields: list[str], nc_recs: list
                    ) -> tuple[list, Counter]:
    used = Counter()
    d_flat = {k[1]: v for k, v in dump_series(co, "LongTermDebt", fields).items()}
    ltdc = {k[1]: v for k, v in {
        **dump_series(co, "LongTermDebtCurrent", fields),
        **local_series(sym, "LongTermDebtCurrent")}.items()}
    d_inc = {k[1]: v for k, v in dump_series(
        co, "LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
        fields).items()}
    nc = {str(r["period_end"]): r for r in nc_recs}
    out = []
    for e in sorted(set(d_flat) | set(nc) | set(d_inc)):
        if e in d_flat:
            out.append(_mk(d_flat[e], "T1_dump平标签")); used["T1"] += 1
        elif e in nc and e in ltdc:
            r = {"val": float(nc[e]["value"]) + ltdc[e]["val"], "start": None,
                 "end": e, "filed": nc[e].get("filed_at"),
                 "accn": nc[e].get("filing_accession"),
                 "form": nc[e].get("source_form"), "tag": "LTD_NC+LongTermDebtCurrent",
                 "_acc": nc[e].get("available_at")}
            out.append(_mk(r, "T2_非当期加当期")); used["T2"] += 1
        elif e in d_inc:
            out.append(_mk(d_inc[e], "T3_合报含当期",
                           "★★ 口径含融资租赁")); used["T3"] += 1
    return out, used


def build_ebit(sym: str, co: dict, fields: list[str]
               ) -> tuple[list, list, Counter, list]:
    """目标三:EBIT。返回 (E1E2记录, E3记录, 每级期数, 口径对差样本)。"""
    used = Counter()
    loc = local_series(sym, "EBIT")                                  # E1
    pre: dict = {}
    for t in PRETAX:
        for k, v in dump_series(co, t, fields).items():
            if k not in pre:
                pre[k] = v
    ie: dict = {}
    for t in INTEREST:
        for k, v in dump_series(co, t, fields).items():
            if k not in ie:
                ie[k] = v
    oil = dump_series(co, "OperatingIncomeLoss", fields)              # E3

    out12, out3, diffs = [], [], []
    keys = sorted(set(loc) | set(pre))
    for k in keys:
        if k in loc:
            out12.append(_mk(loc[k], "E1_本地derived")); used["E1"] += 1
        elif k in pre and k in ie:
            r = dict(pre[k]); r["val"] = pre[k]["val"] + ie[k]["val"]
            r["tag"] = f"{pre[k]['tag']}+{ie[k]['tag']}"
            out12.append(_mk(r, "E2_dump税前加利息")); used["E2"] += 1
    have12 = {r["period_end"] + "|" + str(r["period_start"]) for r in out12}
    for k, v in sorted(oil.items()):
        out3.append(_mk(v, "E3_OperatingIncomeLoss",
                        "★★★ 口径不同:营业利润 ≠ EBIT"))
        used["E3"] += 1
        kk = v["end"] + "|" + str(v["start"])
        if kk in have12:
            base = next(r for r in out12
                        if r["period_end"] + "|" + str(r["period_start"]) == kk)
            b = float(base["value"])
            if b != 0:
                diffs.append({"symbol": sym, "period_end": v["end"],
                              "EBIT": b, "OperatingIncomeLoss": v["val"],
                              "相对差": (v["val"] - b) / abs(b)})
    return out12, out3, used, diffs


# ══════════════════════════════════════════════════════════════════════════
# 三 · PIT 口径对差:dump 的 filed vs 本地的 accepted_at
# ══════════════════════════════════════════════════════════════════════════

def pit_gap(sym: str, co: dict, fields: list[str]) -> list[dict]:
    """两边都有的记录上,★ 量 filed(dump) 和 accepted_at(本地) 差几天。"""
    loc = local_series(sym, "LongTermDebt")
    dmp = dump_series(co, "LongTermDebtNoncurrent", fields)
    rows = []
    for k, lv in loc.items():
        dv = dmp.get(k)
        if dv is None or not lv.get("_acc"):
            continue
        a = pd.Timestamp(str(lv["_acc"])).tz_localize(None).normalize()
        f = pd.Timestamp(dv["filed"])
        rows.append({"symbol": sym, "period_end": k[1],
                     "本地accepted_at": str(a.date()), "dump_filed": dv["filed"],
                     "差几天": int((a - f).days),
                     "值是否一致": bool(abs(lv["val"] - dv["val"])
                                        <= max(1.0, abs(lv["val"]) * 1e-9))})
    return rows


# ══════════════════════════════════════════════════════════════════════════
# 四 · main
# ══════════════════════════════════════════════════════════════════════════

def sic2(sym: str) -> str:
    """★ SIC 两位 —— 取 PIT 版 sic_versions 的**最早**一条(整段窗口定一个,
    只用来做行业分布的前后对比,★ 不进任何闸门)。"""
    p = data.load_manifest()[sym].fundamentals_path
    if not p:
        return "??"
    try:
        with open(p, encoding="utf-8") as fh:
            sv = json.load(fh).get("sic_versions") or []
        if not sv:
            return "??"
        code = str(sorted(sv, key=lambda x: str(x.get("accepted_at")))[0]
                   .get("sic_code") or "")
        return code[:2] if len(code) >= 2 else "??"
    except Exception:
        return "??"


def main() -> int:
    companies, fields = load_dump()
    man = data.load_manifest()
    syms = [s for s in sorted(man) if man[s].fundamentals_path]

    overlay: dict[str, dict] = {}
    rows, all_diffs, all_pit = [], [], []
    rung_tot = {"LTD_NC": Counter(), "LTD_TOTAL": Counter(), "EBIT": Counter()}
    no_dump = []

    for s in syms:
        co = companies.get(s)
        if co is None:
            no_dump.append(s)
            co = {"tags": {}}
        nc, u1 = build_ltd_nc(s, co, fields)
        tot, u2 = build_ltd_total(s, co, fields, nc)
        e12, e3, u3, diffs = build_ebit(s, co, fields)
        all_diffs += diffs
        all_pit += pit_gap(s, co, fields)
        for k, u in (("LTD_NC", u1), ("LTD_TOTAL", u2), ("EBIT", u3)):
            rung_tot[k] += u
        overlay[s] = {"LongTermDebt": nc, "LongTermDebtTotal": tot,
                      "EBIT": e12, "EBIT_OperatingIncomeLoss": e3}
        before_ltd = len(local_series(s, "LongTermDebt"))
        before_ebit = len(local_series(s, "EBIT"))
        rows.append({
            "symbol": s, "SIC2": sic2(s), "在dump里": co.get("cik") is not None,
            "补前_LTD期数": before_ltd, "补后_LTD期数": len(nc),
            "补前_EBIT期数": before_ebit, "补后_EBIT期数": len(e12),
            "LTD_TOTAL期数": len(tot), "E3_营业利润期数": len(e3),
            "LTD用到的级": "+".join(sorted(u1)) or "(无)",
            "EBIT用到的级": "+".join(sorted(u3 - Counter({"E3": u3["E3"]}))) or "(无)",
            "LTD用到的标签": "/".join(sorted({str(r["source_tag"]) for r in nc})) or "(无)",
            "EBIT用到的标签": "/".join(sorted({str(r["source_tag"]) for r in e12})[:3]) or "(无)",
        })

    df = pd.DataFrame(rows)
    # ---- 四个数:补标签前后
    def cnt(col: str) -> int:
        return int((df[col] > 0).sum())
    gate_before = (df["补前_EBIT期数"] > 0) & (df["补前_LTD期数"] > 0)
    gate_after = (df["补后_EBIT期数"] > 0) & (df["补后_LTD期数"] > 0)

    ind = {}
    for s2 in sorted(set(df["SIC2"])):
        sub = df[df["SIC2"] == s2]
        ind[s2] = {"全池": int(len(sub)),
                   "补前_过EBIT+LTD闸": int(gate_before[sub.index].sum()),
                   "补后_过EBIT+LTD闸": int(gate_after[sub.index].sum())}

    dd = pd.DataFrame(all_diffs)
    pg = pd.DataFrame(all_pit)
    out = {
        "票数": len(df),
        "★ 不在 dump 里的票": no_dump,
        "★★★ 四个数(补标签前 → 后)": {
            "LongTermDebt 的票数": [cnt("补前_LTD期数"), cnt("补后_LTD期数")],
            "EBIT 的票数": [cnt("补前_EBIT期数"), cnt("补后_EBIT期数")],
            "过「EBIT+LongTermDebt 都要」闸的票数": [int(gate_before.sum()),
                                                     int(gate_after.sum())],
            "★ 新增指标 LongTermDebtTotal(含当期)的票数": cnt("LTD_TOTAL期数"),
            "★ E3 营业利润(口径不同,单列)的票数": cnt("E3_营业利润期数"),
        },
        "★ 每一级命中的期数": {k: dict(v) for k, v in rung_tot.items()},
        "★ 明确不采的标签及理由": REJECTED_TAGS,
        "★★ 行业分布前后对比(SIC 两位)": ind,
        "★★★ E3 口径对差(营业利润 vs EBIT,两边都有值的期)": (
            {"样本期数": int(len(dd)), "票数": int(dd["symbol"].nunique()),
             "相对差_中位": float(dd["相对差"].median()),
             "相对差_绝对值中位": float(dd["相对差"].abs().median()),
             "相对差_绝对值p90": float(dd["相对差"].abs().quantile(0.90)),
             "相对差_绝对值>10%的期数占比": float((dd["相对差"].abs() > 0.10).mean())}
            if len(dd) else {"样本期数": 0, "说明": "没有重叠期"}),
        "★★ PIT口径对差(本地 accepted_at − dump filed,单位:天)": (
            {"样本期数": int(len(pg)),
             "差0天的占比": float((pg["差几天"] == 0).mean()),
             "差几天_中位": float(pg["差几天"].median()),
             "差几天_最小": int(pg["差几天"].min()),
             "差几天_最大": int(pg["差几天"].max()),
             "值完全一致的占比": float(pg["值是否一致"].mean())}
            if len(pg) else {"样本期数": 0}),
    }

    # ★ 先写结果,再打印
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    df.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    with gzip.open(OUT_OVERLAY, "wt", encoding="utf-8") as fh:
        json.dump(overlay, fh, ensure_ascii=False)
    if len(dd):
        dd.to_csv(os.path.join(HERE, "E3口径对差-逐期-1030.csv"),
                  index=False, encoding="utf-8-sig")
    if len(pg):
        pg.to_csv(os.path.join(HERE, "PIT口径对差-逐期-1030.csv"),
                  index=False, encoding="utf-8-sig")
    try:
        print(json.dumps(out, ensure_ascii=False, indent=2)[:6000])
        print(f"\n{OUT_JSON}\n{OUT_CSV}\n{OUT_OVERLAY}")
    except Exception as e:
        print(f"(打印出错,结果已写出:{type(e).__name__}: {e})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
