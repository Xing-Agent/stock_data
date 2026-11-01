# -*- coding: utf-8 -*-
"""Polygon 拆股 → 对齐到价格真正跳的那一天;再扫「价格跳了、没有拆股记录」的。
大白话:Polygon 的拆股日期偶尔早一天(BMI、USNA),所以在记录日前后 3 个交易日里,
找「前收 ÷ 今开」最接近拆股比例的那天当真正的拆股日。"""
import gzip, json, numpy as np, polars as pl
px = pl.read_parquet("px_2015.parquet").sort("ticker", "d")
px = px.with_columns(pl.col("close").shift(1).over("ticker").alias("pc"), pl.col("d").shift(1).over("ticker").alias("pd"))
cal = sorted(px["d"].unique().to_list()); ci = {d: i for i, d in enumerate(cal)}
px = px.with_columns(pl.col("d").replace_strict(ci, return_dtype=pl.Int32).alias("i"),
                     pl.col("pd").replace_strict(ci, default=None, return_dtype=pl.Int32).alias("pi"))
px = px.with_columns((pl.col("pc") / pl.col("open")).alias("jump"))   # >1 = 价格往下跳(拆股)
S = json.load(gzip.open("/home/claude/stock_data/probe/splits_1101/polygon_splits_1101.json.gz"))["rows"]
S = pl.DataFrame(S, schema=["ticker", "execution_date", "split_from", "split_to", "id"], orient="row")
S = S.filter((pl.col("execution_date") >= "2015-01-05") & (pl.col("execution_date") <= "2026-08-03")).with_columns(
    (pl.col("split_to") / pl.col("split_from")).alias("ratio"))
import bisect
def nearest_i(d):
    k = bisect.bisect_left(cal, d); return min(k, len(cal) - 1)
S = S.with_columns(pl.col("execution_date").map_elements(nearest_i, return_dtype=pl.Int32).alias("ei"))
J = px.filter(pl.col("jump").is_not_null()).select("ticker", "d", "i", "pi", "pc", "open", "jump")
cand = S.join(J, on="ticker", how="inner").filter((pl.col("i") - pl.col("ei")).abs() <= 3)
cand = cand.with_columns((pl.col("jump").log() - pl.col("ratio").log()).abs().alias("err"))
best = cand.sort("err").group_by("id").first()
S = S.join(best.select("id", pl.col("d").alias("aligned_date"), "jump", "err"), on="id", how="left")
S = S.with_columns(
    pl.when(pl.col("err").is_null()).then(pl.lit("无行情"))
      # 容差:小比例(送股)0.15;大比例拆股/合股常伴随当天大涨大跌,放宽到 0.4,但方向必须一致
      .when((pl.col("err") < 0.15) | ((pl.col("ratio").log().abs() >= 0.5) & (pl.col("err") < 0.4)
            & ((pl.col("jump").log() * pl.col("ratio").log()) > 0))).then(pl.when(pl.col("aligned_date") == pl.col("execution_date")).then(pl.lit("确认·同日")).otherwise(pl.lit("确认·日期改")))
      .otherwise(pl.lit("价格没跳")).alias("check"))
S.drop("ei").write_csv("polygon_splits_aligned_1101.csv")
print(S.group_by("check").len().sort("len", descending=True))
print(S.filter(pl.col("check") == "确认·日期改").with_columns((pl.col("aligned_date").str.to_date() - pl.col("execution_date").str.to_date()).dt.total_days().alias("lag")).group_by("lag").len().sort("lag"))
# ── 第三道核对:隔夜跳 ≥1.8 倍(或跌到 0.55 以下),前后 3 天没有确认的拆股 ──
ok = S.filter(pl.col("check").str.starts_with("确认")).select("ticker", pl.col("aligned_date").replace_strict(ci, default=None, return_dtype=pl.Int32).alias("si"))
big = J.filter(((pl.col("jump") > 1.8) | (pl.col("jump") < 0.55)) & ((pl.col("i") - pl.col("pi")) == 1) & (pl.col("pc") >= 1))
big = big.join(ok, on="ticker", how="left").with_columns(((pl.col("i") - pl.col("si")).abs() <= 3).fill_null(False).alias("_m"))
unexpl = big.group_by("ticker", "d").agg(pl.col("_m").any(), pl.col("jump").first(), pl.col("pc").first(), pl.col("open").first()).filter(~pl.col("_m")).drop("_m").sort("ticker", "d")
unexpl.write_csv("unexplained_jumps_1101.csv")
print("隔夜跳 ≥1.8 倍或 ≤0.55、没有拆股记录:", unexpl.height, "次 /", unexpl["ticker"].n_unique(), "个代码")
