# -*- coding: utf-8 -*-
"""每一段(公司)的「价格历史从哪天开始」—— 把 2013 年以前那截从 2004 年起的日线补回来。
大白话:段表只从 2013 年算起,2013-01-02 就出现的票其实可能已经交易了十年。
这里沿用段表同样的切法(缺席 ≥30 个交易日切;缺席 ≥5 天且价格变 3 倍、不是拆股比也切),往前倒着找。"""
import glob, os, numpy as np, polars as pl
DAY = "/home/claude/pituni/day"
files = sorted(f for f in glob.glob(f"{DAY}/*.csv.gz") if os.path.basename(f) < "2013-01-02")
dates = [os.path.basename(f)[:10] for f in files]
parts = []
for i, f in enumerate(files):
    d = pl.read_csv(f, columns=["ticker", "close"], schema_overrides={"ticker": pl.String, "close": pl.Float64})
    parts.append(d.with_columns(pl.lit(i, pl.Int32).alias("i")))
pre = pl.concat(parts)
N = len(dates)                       # 2013-01-02 的下标 = N
S = pl.read_csv("/home/claude/seg/pit_company_segments.csv", infer_schema_length=0)
SPL = [2, 3, 4, 5, 6, 8, 10, 15, 20, 25, 30, 40, 50, 100, 1.5]
def near_split(r):
    return any(abs(np.log(r / t)) < 0.05 for k in SPL for t in (k, 1 / k))
need = S.filter(pl.col("first_seen") == "2013-01-02").select("seg_id", "ticker", "c_first")
pre_g = {t: g.sort("i") for (t,), g in pre.filter(pl.col("ticker").is_in(need["ticker"].to_list())).group_by(["ticker"])}
start = {}
for sid, t, c0 in need.iter_rows():
    g = pre_g.get(t)
    if g is None:
        start[sid] = ("2013-01-02", False, "2013 年以前没出现过"); continue
    ii = g["i"].to_numpy(); cc = g["close"].to_numpy()
    ii = np.append(ii, N); cc = np.append(cc, float(c0))
    k = len(ii) - 1; why = "一直连到 2004 年"
    while k > 0:
        gap = ii[k] - ii[k - 1] - 1
        if gap >= 30:
            why = f"往前缺席 {gap} 个交易日,切"; break
        if gap >= 5 and cc[k - 1] > 0 and cc[k] > 0:
            r = cc[k] / cc[k - 1]
            if (r > 3 or r < 1 / 3) and not near_split(r):
                why = f"缺席 {gap} 天后价格变 {r:.2f} 倍,切"; break
        k -= 1
    first = dates[ii[k]] if ii[k] < N else "2013-01-02"
    start[sid] = (first, first == dates[0], why)
S = S.with_columns(
    pl.col("seg_id").map_elements(lambda s: start.get(s, (None,))[0], return_dtype=pl.String).alias("_bf"),
    pl.col("seg_id").map_elements(lambda s: start.get(s, (None, False))[1], return_dtype=pl.Boolean).alias("_cens"),
    pl.col("seg_id").map_elements(lambda s: start.get(s, (None, None, ""))[2], return_dtype=pl.String).alias("backfill_note"),
).with_columns(
    pl.coalesce("_bf", "first_seen").alias("history_start"),
    pl.col("_cens").fill_null(False).alias("history_start_censored"),
)
# 公司级:沿改名链,取最早那段的 history_start(改名前后价格是连续的)
cst = S.group_by("company_id").agg(pl.col("history_start").min().alias("company_history_start"),
                                    pl.col("history_start_censored").any().alias("company_start_censored"))
S = S.join(cst, on="company_id", how="left")
# 疑似新上市:历史起点不是数据开头(2004-01-02)、也不是改名接上来的
S = S.with_columns(
    ((~pl.col("company_start_censored")) & (pl.col("renamed_from") == "") & (pl.col("company_history_start") > "2004-01-02")
     ).alias("new_listing_candidate"),
    pl.col("c_first").cast(pl.Float64).is_between(9.5, 10.5).alias("spac_like_price"),
)
out = S.select("seg_id", "company_id", "ticker", "seg_no", "first_seen", "last_seen", "history_start",
               "history_start_censored", "company_history_start", "company_start_censored",
               "new_listing_candidate", "spac_like_price", "renamed_from", "cut_reason", "backfill_note", "end_type")
out.write_csv("pit_history_start_1030.csv")
print(out.height, "段;从 2013-01-02 开始、往前补的段", need.height)
print(out.group_by("backfill_note").len().sort("len", descending=True).head(8))
for t in ["AAPL", "META", "FB", "TSLA", "SNOW", "ABNB", "SIVB", "ELV", "HHH"]:
    print(out.filter(pl.col("ticker") == t).select("ticker", "seg_no", "first_seen", "history_start", "company_history_start", "new_listing_candidate", "spac_like_price").rows())

# ── 新股判定再收紧:同一个代码在历史起点之前出现过、而且离得不到 250 个交易日 → 不算新股(SIVB 2005 年数据缺口这种)──
alld = sorted(os.path.basename(f)[:10] for f in glob.glob(f"{DAY}/*.csv.gz"))
idx = {d: i for i, d in enumerate(alld)}
pre_last = {t: g.select(pl.col("i").max()).item() for (t,), g in pre.group_by(["ticker"])}   # 2013 前最后一次出现
segs = out.sort("ticker", pl.col("seg_no").cast(pl.Int32))
prev_gap = {}
last_by_t = {}
for sid, t, hs, ls in segs.select("seg_id", "ticker", "history_start", "last_seen").iter_rows():
    h = idx.get(hs)
    prev = last_by_t.get(t)
    if prev is None and t in pre_last and hs >= "2013-01-02":
        prev = pre_last[t]
    if prev is None and hs < "2013-01-02":            # 往前补的段:看补到的起点之前还有没有这个代码
        g = pre_g.get(t)
        if g is not None:
            before = g.filter(pl.col("i") < h)["i"]
            prev = before.max() if before.len() else None
    prev_gap[sid] = None if prev is None else h - prev - 1
    last_by_t[t] = idx.get(ls)
out = out.with_columns(pl.col("seg_id").replace_strict(prev_gap, default=None, return_dtype=pl.Int64).alias("gap_since_same_ticker_before"))
out = out.with_columns((pl.col("new_listing_candidate") &
                        (pl.col("gap_since_same_ticker_before").is_null() | (pl.col("gap_since_same_ticker_before") >= 250))
                        ).alias("new_listing_candidate"))
out.write_csv("pit_history_start_1030.csv")
print("新股候选", out["new_listing_candidate"].sum(), "· 其中价格像 SPAC", out.filter(pl.col("new_listing_candidate") & pl.col("spac_like_price")).height)
for t in ["SIVB", "TSLA", "FB", "SNOW", "ABNB", "AAPL", "RIVN", "ARM"]:
    print(out.filter(pl.col("ticker") == t).select("ticker", "seg_no", "history_start", "new_listing_candidate", "gap_since_same_ticker_before").rows())
