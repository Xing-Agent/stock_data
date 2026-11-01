# -*- coding: utf-8 -*-
"""给 9 指标时点表补「没有」的两种情况:从来没报过(never)/ 报过但这一期没有(gap)。

大白话:
  主表只有「报了的数」,没报的那一期根本没有行。所以这里另做一张「每家公司 × 每个指标 × 每份财报」的格子表:
  每份 10-K/10-Q 都有一行,有数写 has,没数再分 never / gap。
  年报和季报分开判断:广告这类只在年报里披露的,季报里没有是正常的 → 季报那边标 never_in_10q,不算 gap。
  发新股收入是 gap、而且这一期股本比上一期多了 0.5% 以上 → gap_shares_up(发了新股、只是报在别的科目,绝不能当 0)。
"""
import gzip, json
import polars as pl

FACTS = pl.read_csv("sec_fin10_pit_1101.csv", infer_schema_length=0)
SUB = json.load(gzip.open("sec_submissions_300_1030.json.gz"))
METRICS = FACTS["metric"].unique().sort().to_list()

# 每家公司的定期财报(2014 起),一份一行
fil = []
for key, rows in SUB["rows"].items():
    sym = key.split("@")[0]
    for accn, filed, acc, rd, form, items in rows:
        if form in ("10-K", "10-Q", "10-KT") and filed >= "2014-01-01" and rd:
            fil.append((sym, accn, filed, rd, "10-K" if form.startswith("10-K") else "10-Q"))
F = pl.DataFrame(fil, schema=["symbol", "accession", "filed", "period_end", "form_family"], orient="row").unique(["symbol", "accession"])

# 主表里「这份财报、这一期」有没有数(期间数取期间最长的那条:季报里的现金流项是年初至今累计)
fx = FACTS.filter(pl.col("form").str.starts_with("10-")).with_columns(
    pl.when(pl.col("form").str.starts_with("10-K")).then(pl.lit("10-K")).otherwise(pl.lit("10-Q")).alias("form_family"))
# 股本的封面数(dei)日期是封面日、不是期末 → 股本只按同一份财报对,不要求日期相同
fx = fx.with_columns(pl.when(pl.col("metric") == "SharesOutstanding").then(pl.lit(None, pl.String)).otherwise(pl.col("period_end")).alias("_pe"))
Fk = F.select("symbol", "accession", pl.col("period_end").alias("_pe_f"))
hit = (fx.join(Fk, on=["symbol", "accession"], how="inner").filter(pl.col("_pe").is_null() | (pl.col("_pe") == pl.col("_pe_f")))
         .sort("period_start").group_by("symbol", "accession", "metric").agg(pl.col("value").first(), pl.col("source_tag").first(),
                                                                              pl.col("period_start").first()))
grid = F.join(pl.DataFrame({"metric": METRICS}), how="cross").join(hit, on=["symbol", "accession", "metric"], how="left")

# 这家公司(分年报 / 季报)有没有报过这个指标、第一次是哪份
ever = grid.filter(pl.col("value").is_not_null()).group_by("symbol", "metric", "form_family").agg(
    pl.col("filed").min().alias("first_reported"), pl.col("filed").max().alias("last_reported"))
grid = grid.join(ever, on=["symbol", "metric", "form_family"], how="left")
any_ever = ever.group_by("symbol", "metric").agg(pl.len().alias("_any"))
grid = grid.join(any_ever, on=["symbol", "metric"], how="left")

# 股本:同一份财报的期末股本(资产负债表那个;没有就用封面股本)
sh = (FACTS.filter(pl.col("metric") == "SharesOutstanding")
      .with_columns((pl.col("source_tag") == "CommonStockSharesOutstanding").alias("bs"))
      .sort("bs", descending=True).group_by("symbol", "accession").agg(pl.col("value").first().cast(pl.Float64).alias("shares")))
grid = grid.join(sh, on=["symbol", "accession"], how="left").sort("symbol", "metric", "form_family", "period_end", "filed")
grid = grid.with_columns(pl.col("shares").shift(1).over("symbol", "metric", "form_family").alias("shares_prev"))
grid = grid.with_columns(
    pl.when(pl.col("value").is_not_null()).then(pl.lit("has"))
      .when(pl.col("first_reported").is_null() & (pl.col("form_family") == "10-Q") & pl.col("_any").is_not_null()).then(pl.lit("never_in_10q"))
      .when(pl.col("first_reported").is_null()).then(pl.lit("never"))
      .when((pl.col("metric") == "ShareIssuanceProceeds") & (pl.col("shares") > pl.col("shares_prev") * 1.005)).then(pl.lit("gap_shares_up"))
      .otherwise(pl.lit("gap")).alias("status"),
    (pl.col("filed") < pl.col("first_reported")).fill_null(False).alias("before_first_report"),
)
# 季报:如果年报里报过、季报里从来没报过 → never_in_10q 已经标了;年报从来没报过 → 季报也算 never
out = grid.select("symbol", "metric", "form_family", "accession", "period_end", "filed", "status", "value", "period_start",
                  "source_tag", "first_reported", "last_reported", "before_first_report", "shares", "shares_prev")
out.write_csv("sec_fin10_status_1101.csv")

c = (out.group_by("metric", "form_family", "status").len()
       .pivot(on="status", index=["metric", "form_family"], values="len").fill_null(0).sort("form_family", "metric"))
cols = [x for x in ["has", "never", "never_in_10q", "gap", "gap_shares_up"] if x in c.columns]
c = c.select("metric", "form_family", *cols)
c.write_csv("sec_fin10_status_counts_1101.csv")
pl.Config.set_tbl_rows(30); pl.Config.set_tbl_cols(10)
print(c)
g = out.filter(pl.col("status").str.starts_with("gap"))
print("gap 里属于「第一次报之前」的:", g.filter(pl.col("before_first_report")).height, "/", g.height)
