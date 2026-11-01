# -*- coding: utf-8 -*-
"""第 17、18 轮策略要用的 9 个财务指标 → 带公布日的时点表(300 只,SEC)。

大白话:
  同一样东西,公司可能用不同字段名报。每个指标列了几个字段名,按顺序试,
  同一份财报、同一期先找到哪个用哪个,用的哪个写在 source_tag 里。
  每条都带「哪天公布」(filed),回测时只能用 filed 之后的。
  「这家公司从来没报过这一项」和「缺数据」是两回事 —— 见 README。
"""
import gzip, json, sys
import polars as pl

RAW = sys.argv[1] if len(sys.argv) > 1 else "sec_companyfacts_fin10_1101.json.gz"
MAN = "/home/claude/sd5/pilot_300/manifest.csv"
OUT = "sec_fin10_pit_1101.csv"

# 指标: (时点数? , [字段名按优先级])
METRICS = {
    "ShareIssuanceProceeds": (False, ["ProceedsFromIssuanceOfCommonStock", "ProceedsFromIssuanceOrSaleOfEquity"]),
    "OptionExerciseProceeds": (False, ["ProceedsFromStockOptionsExercised"]),
    "RnD": (False, ["ResearchAndDevelopmentExpense", "ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",
                    "ResearchAndDevelopmentExpenseSoftwareExcludingAcquiredInProcessCost"]),
    "Advertising": (False, ["AdvertisingExpense", "MarketingAndAdvertisingExpense"]),
    "InterestExpense": (False, ["InterestExpense", "InterestExpenseNonoperating", "InterestExpenseDebt", "InterestAndDebtExpense"]),
    "AccountsReceivable": (True, ["AccountsReceivableNetCurrent", "ReceivablesNetCurrent"]),
    "ShortTermDebt": (True, ["ShortTermBorrowings", "ShortTermBankLoansAndNotesPayable", "CommercialPaper", "DebtCurrent"]),
    "RetainedEarnings": (True, ["RetainedEarningsAccumulatedDeficit"]),
    "SharesOutstanding": (True, ["dei:EntityCommonStockSharesOutstanding", "CommonStockSharesOutstanding"]),
}
NOTE = {"MarketingAndAdvertisingExpense": "含市场营销,偏大", "DebtCurrent": "含一年内到期的长期债,偏大",
        "CommercialPaper": "只有商业票据", "ProceedsFromIssuanceOrSaleOfEquity": "含优先股等",
        "ReceivablesNetCurrent": "含其他应收", "dei:EntityCommonStockSharesOutstanding": "财报封面股本,日期是封面日"}

raw = json.load(gzip.open(RAW))
man = pl.read_csv(MAN, infer_schema_length=0)
sector = dict(zip(man["symbol"], man["sector"]))
FIN = {"Financial Services", "Real Estate"}

rows = []
for key, comp in raw["companies"].items():
    sym = key.split("@")[0]
    for metric, (instant, tags) in METRICS.items():
        done = set()
        for tag in tags:
            for v, s, e, fy, fp, form, filed, accn, unit in comp["tags"].get(tag, []):
                if instant != (not s):
                    continue
                k = (accn, e) if instant else (accn, s, e)
                if k in done:
                    continue
                done.add(k)
                rows.append((sym, comp["cik"], metric, v, unit, s, e, fy, fp, form, filed, accn, tag, NOTE.get(tag, "")))
cols = ["symbol", "cik", "metric", "value", "unit", "period_start", "period_end", "fiscal_year", "fiscal_period",
        "form", "filed", "accession", "source_tag", "note"]
df = pl.DataFrame(rows, schema=cols, orient="row", infer_schema_length=None)
df = df.with_columns(pl.col("symbol").replace_strict(sector, default="").alias("sector")).with_columns(
    pl.col("sector").is_in(list(FIN)).alias("financial_sector")
).filter(pl.col("filed") >= "2014-01-01").sort("symbol", "metric", "period_end", "filed", "accession", "period_start", maintain_order=True)
df.write_csv(OUT)
print("行数", df.height)

syms = man["symbol"].to_list()
nonfin = [s for s in syms if sector.get(s) not in FIN]
k = df.filter(pl.col("form").str.starts_with("10-K"))
print(f"{'指标':24s} 有数(300) 非金融有数({len(nonfin)}) 8年以上年报(非金融)")
cov = []
for m in METRICS:
    d = k.filter(pl.col("metric") == m)
    have = set(d["symbol"])
    yrs = d.group_by("symbol").agg(pl.col("period_end").str.slice(0, 4).n_unique().alias("n"))
    long = set(yrs.filter(pl.col("n") >= 8)["symbol"])
    r = (m, len([s for s in syms if s in have]), len([s for s in nonfin if s in have]), len([s for s in nonfin if s in long]))
    cov.append(r); print(f"{r[0]:24s} {r[1]:8d} {r[2]:10d} {r[3]:10d}")
print(df.group_by("metric", "source_tag").len().sort("metric", "len", descending=True))
pl.DataFrame(cov, schema=["metric", "have_300", "have_nonfin", "nonfin_8y_annual"], orient="row").write_csv("sec_fin10_coverage_1101.csv")
