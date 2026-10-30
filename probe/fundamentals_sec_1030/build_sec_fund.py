# -*- coding: utf-8 -*-
"""从 SEC companyfacts 原始数据,做出「长期负债」和「EBIT」的时点表(300 只)。

大白话:
  每家公司在 SEC 的财报里,同一样东西可能用不同的字段名报(YUM 的长期负债报在
  LongTermDebtAndCapitalLeaseObligations 下面)。这里按优先级一个一个试,
  同一份财报里先找到哪个用哪个,并把「用的是哪个字段」写在 source_tag 里。
  每条都带「哪天公布」(filed),回测时只能用公布日之前的。
"""
import gzip, json
import polars as pl

RAW = "/home/claude/secfund/sec_companyfacts_300_1030.json.gz"
MAN = "/home/claude/sd5/pilot_300/manifest.csv"
OUT = "/home/claude/secfund/sec_ltd_ebit_pit_1030.csv"

# 长期负债(资产负债表上「一年以后才到期」的那部分)—— 按优先级
LTD_TAGS = [
    ("LongTermDebtNoncurrent", "noncurrent"),
    ("LongTermDebtAndCapitalLeaseObligations", "noncurrent_incl_capital_lease"),
    ("LongTermNotesPayable", "notes_noncurrent"),
    ("SeniorLongTermNotes", "senior_notes"),
    ("OtherLongTermDebtNoncurrent", "other_noncurrent"),
]
# 兜底:只有「含一年内到期」的总数时,用 总数 − 一年内到期
LTD_TOTAL = [("LongTermDebt", "LongTermDebtCurrent"),
             ("LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities",
              "LongTermDebtAndCapitalLeaseObligationsCurrent")]
LTD_LAST = [("LongTermDebt", "total_incl_current_no_split"),
            ("LongTermDebtAndCapitalLeaseObligationsIncludingCurrentMaturities", "total_incl_current_no_split"),
            ("ConvertibleLongTermNotesPayable", "convertible_notes"),
            ("ConvertibleNotesPayable", "convertible_notes"),
            ("LongTermLineOfCredit", "credit_line")]
PRETAX = ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
          "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"]
INTEREST = ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestAndDebtExpense"]

raw = json.load(gzip.open(RAW))
man = pl.read_csv(MAN, infer_schema_length=0)
sector = dict(zip(man["symbol"], man["sector"]))
FIN = {"Financial Services", "Real Estate"}

def facts(comp, tag):
    """→ {(accn, start, end): (val, fy, fp, form, filed)}"""
    out = {}
    for v, s, e, fy, fp, form, filed, accn, frame in comp["tags"].get(tag, []):
        out[(accn, s, e)] = (v, fy, fp, form, filed)
    return out

rows = []
for key, comp in raw["companies"].items():
    sym = key.split("@")[0]
    cik = comp["cik"]
    # ── 长期负债:时点数(没有 start)──
    done = set()
    for tag, basis in LTD_TAGS:
        for (accn, s, e), (v, fy, fp, form, filed) in facts(comp, tag).items():
            if s or (accn, e) in done:
                continue
            done.add((accn, e))
            rows.append((sym, cik, "LongTermDebt", v, "", e, fy, fp, form, filed, accn, tag, basis))
    for tot, cur in LTD_TOTAL:
        T, C = facts(comp, tot), facts(comp, cur)
        for (accn, s, e), (v, fy, fp, form, filed) in T.items():
            if s or (accn, e) in done:
                continue
            c = C.get((accn, s, e))
            if c is None:
                continue
            done.add((accn, e))
            rows.append((sym, cik, "LongTermDebt", v - c[0], "", e, fy, fp, form, filed, accn,
                         f"{tot}-{cur}", "derived_total_minus_current"))
    # 再兜底:只有「含一年内到期的总数」、没拆分(房屋建筑商等不分流动/非流动的报表就是这样),
    # 或者只报可转债/长期授信 —— 照用,basis 标清楚
    for tag, basis in LTD_LAST:
        for (accn, s, e), (v, fy, fp, form, filed) in facts(comp, tag).items():
            if s or (accn, e) in done:
                continue
            done.add((accn, e))
            rows.append((sym, cik, "LongTermDebt", v, "", e, fy, fp, form, filed, accn, tag, basis))
    # ── EBIT:期间数(有 start)──
    done = set()
    for (accn, s, e), (v, fy, fp, form, filed) in facts(comp, "OperatingIncomeLoss").items():
        if not s:
            continue
        done.add((accn, s, e))
        rows.append((sym, cik, "EBIT", v, s, e, fy, fp, form, filed, accn,
                     "OperatingIncomeLoss", "reported_operating_income"))
    P = {}
    for t in PRETAX:
        for k, x in facts(comp, t).items():
            P.setdefault(k, (x, t))
    I = {}
    for t in INTEREST:
        for k, x in facts(comp, t).items():
            I.setdefault(k, (x, t))
    for k, ((v, fy, fp, form, filed), pt) in P.items():
        accn, s, e = k
        if not s or k in done or k not in I:
            continue
        (iv, *_), it = I[k]
        rows.append((sym, cik, "EBIT", v + iv, s, e, fy, fp, form, filed, accn,
                     f"{pt}+{it}", "derived_pretax_plus_interest"))

cols = ["symbol", "cik", "metric", "value", "period_start", "period_end", "fiscal_year", "fiscal_period",
        "form", "filed", "accession", "source_tag", "basis"]
df = pl.DataFrame(rows, schema=cols, orient="row", infer_schema_length=None)
df = df.with_columns(
    pl.col("symbol").replace_strict(sector, default="").alias("sector"),
    pl.col("symbol").replace_strict(sector, default="").is_in(list(FIN)).alias("financial_sector"),
).filter(pl.col("filed") >= "2014-01-01").sort("symbol", "metric", "period_end", "filed", "accession", "period_start", maintain_order=True)
df.write_csv(OUT)
print("rows", df.height)

# ── 覆盖 ──
syms = man["symbol"].to_list()
def cov(metric, nonfin_only=False):
    d = df.filter((pl.col("metric") == metric) & pl.col("form").str.starts_with("10-K"))
    yrs = d.group_by("symbol").agg(pl.col("period_end").str.slice(0, 4).cast(pl.Int32).unique().alias("y"))
    full = {r[0] for r in yrs.iter_rows() if all(y in r[1] for y in range(2016, 2025))}
    have = set(d["symbol"].unique().to_list())
    S = [s for s in syms if not (nonfin_only and sector.get(s) in FIN)]
    return len([s for s in S if s in have]), len([s for s in S if s in full]), len(S)
for m in ("LongTermDebt", "EBIT"):
    print(m, "全部 300 只: 有数据 / 2016-2024 年报全覆盖 / 总数 =", cov(m), "· 非金融:", cov(m, True))
print(df.group_by("metric", "basis").len().sort("metric", "len", descending=True))
json.dump({"syms": syms}, open("/home/claude/secfund/_syms.json", "w"))
