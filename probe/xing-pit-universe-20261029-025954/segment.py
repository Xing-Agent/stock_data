# -*- coding: utf-8 -*-
"""把「按代码」的名单改成「按公司」:切段 + 改名接续。

大白话:
  ① 切:同一个代码连续消失 ≥ 30 个交易日 → 后面那段当成另一家公司;
        消失 5–29 天、回来时价格差 3 倍以上(又不是整数拆股比)→ 也切。
  ② 接:代码 A 某天最后一次出现,第二天代码 B 第一次出现,
        B 的开盘价和 A 的收盘价差 < 3%、成交量也接得上 → 认为是同一家公司改名(FB→META 这种),
        A 那段不算「退市」。
  这都是没有公司编号(CIK)时的近似;每条判断都留了理由列,能人工复核。
"""
import numpy as np
import polars as pl

GAP_CUT = 30          # 连续缺席多少个交易日就切
GAP_PRICE = 5         # 缺席这么多天以上,回来价格差 3 倍也切
PX_BREAK = 3.0
SPLITS = [2, 3, 4, 5, 6, 8, 10, 15, 20, 25, 30, 40, 50, 100, 1.5]
STAT0 = "2014-12-01"

df = pl.read_parquet("raw_all.parquet").sort(["t", "d"])
dates = np.sort(df["d"].unique().to_numpy())
END = len(dates) - 1
dmap = pl.DataFrame({"d": dates, "i": np.arange(len(dates), dtype=np.int32)}).with_columns(pl.col("d").cast(pl.Date))
df = df.join(dmap, on="d").sort(["t", "d"])


def near_split(r):
    for k in SPLITS:
        for t in (k, 1 / k):
            if abs(np.log(r / t)) < 0.05:
                return True
    return False


segs = []
for (t,), g in df.group_by(["t"], maintain_order=True):
    i = g["i"].to_numpy(); c = g["c"].to_numpy(); o = g["o"].to_numpy(); v = g["v"].to_numpy()
    cut = [0]; why = ["start"]
    for k in range(1, len(i)):
        gap = i[k] - i[k - 1] - 1
        if gap >= GAP_CUT:
            cut.append(k); why.append(f"缺席{gap}个交易日")
        elif gap >= GAP_PRICE and c[k - 1] > 0 and c[k] > 0:
            r = c[k] / c[k - 1]
            if (r > PX_BREAK or r < 1 / PX_BREAK) and not near_split(r):
                cut.append(k); why.append(f"缺席{gap}天后价格变{r:.2f}倍")
    cut.append(len(i))
    for n, (a, b) in enumerate(zip(cut[:-1], cut[1:])):
        segs.append(dict(ticker=t, seg_no=n + 1, i0=int(i[a]), i1=int(i[b - 1]), days=int(b - a),
                         o_first=float(o[a]), c_first=float(c[a]), c_last=float(c[b - 1]),
                         v_head=float(np.median(v[a:min(b, a + 20)])), v_tail=float(np.median(v[max(a, b - 20):b])),
                         cut_reason=why[n]))
S = pl.DataFrame(segs).with_row_index("seg_id")
print("代码", df["t"].n_unique(), "→ 段", S.height, "· 被切开的代码", S.filter(pl.col("seg_no") > 1)["ticker"].n_unique())

# ── 改名接续:A 段在 e 日结束,B 段在 e+1..e+2 日开始,价格和量都接得上 ──
ends = S.filter(pl.col("i1") < END).select("seg_id", "ticker", "i1", "c_last", "v_tail")
starts = S.select(pl.col("seg_id").alias("nid"), pl.col("ticker").alias("nt"), "i0", "o_first", "c_first", "v_head")
cand = []
for k in (1, 2):
    m = ends.with_columns((pl.col("i1") + k).alias("i0")).join(starts, on="i0")
    m = m.filter((pl.col("ticker") != pl.col("nt"))
                 & ((pl.col("o_first") / pl.col("c_last") - 1).abs() < 0.03)
                 & ((pl.col("v_head") / pl.col("v_tail")).is_between(0.3, 3.3))
                 & (pl.col("c_last") > 0)
                 # 收紧:只接普通股样式的代码、量够大、价格不在 SPAC($10)和面值($25)扎堆区
                 & pl.col("ticker").str.contains(r"^[A-Z]{1,5}$") & pl.col("nt").str.contains(r"^[A-Z]{1,5}$")
                 & (pl.col("v_tail") >= 50000) & (pl.col("v_head") >= 50000)
                 & ~pl.col("c_last").is_between(9.4, 10.6) & ~pl.col("c_last").is_between(24.0, 26.0))
    cand.append(m.with_columns(pl.lit(k).alias("lag"),
                               (pl.col("o_first") / pl.col("c_last") - 1).abs().alias("pxdiff")))
C = pl.concat(cand)
# 一对一:同一个 A 只能接一个 B,同一个 B 只能被一个 A 接;有多个候选的标「不确定」,不接
na = C.group_by("seg_id").len().rename({"len": "na"})
nb = C.group_by("nid").len().rename({"len": "nb"})
C = C.join(na, on="seg_id").join(nb, on="nid")
link = C.filter((pl.col("na") == 1) & (pl.col("nb") == 1))
amb = C.filter((pl.col("na") > 1) | (pl.col("nb") > 1))
print("改名接续:确定", link.height, "· 有多个候选、没接", amb["seg_id"].n_unique())

nxt = dict(zip(link["seg_id"].to_list(), link["nid"].to_list()))
prv = {b: a for a, b in nxt.items()}
cid = {}
for s in S["seg_id"].to_list():
    if s in prv:
        continue
    c, k = s, s
    while True:
        cid[k] = c
        if k in nxt:
            k = nxt[k]
        else:
            break
tick = dict(zip(S["seg_id"].to_list(), S["ticker"].to_list()))
amb_ids = set(amb["seg_id"].to_list())
S = S.with_columns(
    pl.col("seg_id").replace_strict(cid, return_dtype=pl.UInt32).alias("company_id"),
    pl.col("seg_id").map_elements(lambda s: tick.get(prv.get(s), ""), return_dtype=pl.String).alias("renamed_from"),
    pl.col("seg_id").map_elements(lambda s: tick.get(nxt.get(s), ""), return_dtype=pl.String).alias("renamed_to"),
)
S = S.with_columns(
    pl.when(pl.col("i1") == END).then(pl.lit("样本末尾仍在交易"))
      .when(pl.col("renamed_to") != "").then(pl.lit("改名(公司还在)"))
      .when(pl.col("seg_id").is_in(list(amb_ids))).then(pl.lit("消失(可能改名,候选不唯一)"))
      .otherwise(pl.lit("消失(退市/被收购/到期)")).alias("end_type"),
    pl.col("i0").map_elements(lambda x: str(dates[x])[:10], return_dtype=pl.String).alias("first_seen"),
    pl.col("i1").map_elements(lambda x: str(dates[x])[:10], return_dtype=pl.String).alias("last_seen"),
)
out = S.filter(pl.col("last_seen") >= STAT0).select(
    "seg_id", "company_id", "ticker", "seg_no", "first_seen", "last_seen", "days",
    pl.col("c_first").round(4), pl.col("c_last").round(4), pl.col("v_tail").round(0).alias("vol_med_last20"),
    "cut_reason", "renamed_from", "renamed_to", "end_type").sort(["ticker", "seg_no"])
out.write_csv("pit_company_segments.csv")
print(out.group_by("end_type").len().sort("len", descending=True))
print("公司数(company_id)", out["company_id"].n_unique(), "· 段数", out.height)
