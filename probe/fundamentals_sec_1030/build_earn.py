# -*- coding: utf-8 -*-
"""业绩公布日(8-K 第 2.02 项)+ 4 位行业代码(SIC),300 只。

大白话:
  公司公布业绩当天会向 SEC 交一份 8-K,里面勾上「2.02 经营业绩」。这份的提交时间就是业绩公布时间,
  通常比 10-Q/10-K 的递交日(我们之前用的 filed)早几天到几周。
  每条公布事件再对上「它公布的是哪一期」:之后最近的那份 10-Q/10-K 的报告期。
"""
import gzip, json, sys
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
import polars as pl

SRC = sys.argv[1] if len(sys.argv) > 1 else "sec_submissions_300_1030.json.gz"
raw = json.load(gzip.open(SRC))
F = ["accn", "filed", "accepted", "report_date", "form", "items"]

# 交易日历(用日线文件名)
import glob, os
cal = sorted(os.path.basename(f)[:10] for f in glob.glob("/home/claude/pituni/day/*.csv.gz"))
def next_td(d, strict):
    import bisect
    i = bisect.bisect_right(cal, d) if strict else bisect.bisect_left(cal, d)
    return cal[i] if i < len(cal) else None

ev, meta = [], []
for key, m in raw["meta"].items():
    sym = key.split("@")[0]
    meta.append((sym, m["cik"], m["name"], m.get("sic") or "", m.get("sicDescription") or "",
                 ",".join(m.get("tickers") or []), ",".join(x or "" for x in (m.get("exchanges") or []))))
    rows = [dict(zip(F, r)) for r in raw["rows"].get(key, [])]
    rows = list({r["accn"]: r for r in rows}.values())
    periodic = sorted([r for r in rows if r["form"].split("/")[0] in ("10-Q", "10-K", "10-KT", "20-F", "40-F")
                       and not r["form"].endswith("/A")], key=lambda r: r["filed"])
    for r in rows:
        if not r["form"].startswith("8-K") or "2.02" not in (r["items"] or ""):
            continue
        acc = r["accepted"] or ""
        # SEC 的 acceptanceDateTime 是 UTC(CHRW 盘后 4 点多发稿,记录为 20:28Z / 冬天 21:34Z),换成美东时间
        hhmm, aday = "", r["filed"]
        if len(acc) >= 19:
            et = datetime.fromisoformat(acc[:19]).replace(tzinfo=timezone.utc).astimezone(ZoneInfo("America/New_York"))
            hhmm, aday = et.strftime("%H:%M"), et.date().isoformat()
        sess = "" if not hhmm else ("盘前" if hhmm < "09:30" else "盘后" if hhmm >= "16:00" else "盘中")
        react = next_td(aday, strict=(sess == "盘后"))
        # 对上报告期:公布后 120 天内、最早递交的那份 10-Q/10-K
        nxt = next((p for p in periodic if p["filed"] >= r["filed"]
                    and p["filed"] <= (datetime.fromisoformat(r["filed"]) + timedelta(days=120)).date().isoformat()), None)
        ev.append((sym, m["cik"], aday, hhmm, sess, react, r["form"], r["items"], r["accn"],
                   nxt["report_date"] if nxt else None, nxt["form"] if nxt else None, nxt["filed"] if nxt else None))
cols = ["symbol", "cik", "announce_date", "announce_time_et", "session", "first_tradable_date", "form", "items",
        "accession", "period_end", "periodic_form", "periodic_filed"]
E = pl.DataFrame(ev, schema=cols, orient="row").filter(pl.col("announce_date") >= "2014-01-01")
E = E.with_columns((pl.col("periodic_filed").str.to_date() - pl.col("announce_date").str.to_date()).dt.total_days().alias("days_before_filed"))
# 同一报告期可能有好几份 2.02:正式业绩之外,还有交付量/初步数/预告(TSLA 每季初的交付量也勾 2.02)。
# 「正式业绩」= 报告期结束之后、10-Q/10-K 递交之前,最晚的那一份;其余保留、标 main_release = false
E = E.sort("symbol", "announce_date", "announce_time_et")
ok = (pl.col("announce_date") > pl.col("period_end")) & (pl.col("announce_date") <= pl.col("periodic_filed"))
E = E.with_columns(ok.fill_null(False).alias("_ok"))
E = E.with_columns((pl.col("_ok") & (pl.col("announce_date") == pl.col("announce_date").filter(pl.col("_ok")).max().over("symbol", "period_end"))
                    & (pl.int_range(pl.len()).over("symbol", "period_end", "announce_date").reverse() == 0)).alias("main_release")).drop("_ok")
E = E.with_columns(pl.len().over("symbol", "period_end").alias("releases_this_period"))
E.write_csv("sec_earnings_dates_1030.csv")
M = pl.DataFrame(meta, schema=["symbol", "cik", "sec_name", "sic4", "sic_description", "sec_tickers", "sec_exchanges"], orient="row")
M = M.unique("symbol", keep="first").sort("symbol")
M.write_csv("sec_sic4_1030.csv")
print("事件", E.height, "· 公司", E["symbol"].n_unique(), "· 报告期对上", E["period_end"].is_not_null().sum())
print(E.group_by("session").len())
print("公布日早于递交日的天数(中位/90%):", E["days_before_filed"].median(), E["days_before_filed"].quantile(0.9))
print("公布晚于递交(不该有):", E.filter(pl.col("days_before_filed") < 0).height)
M2 = E.filter(pl.col("main_release"))
print("正式业绩", M2.height, "· 每只票中位", M2.group_by("symbol").len()["len"].median(), "· 有报告期但没选出正式业绩的期数",
      E.filter(pl.col("period_end").is_not_null()).group_by("symbol", "period_end").agg(pl.col("main_release").any()).filter(~pl.col("main_release")).height)
print("正式业绩早于递交(天) 中位/90%:", M2["days_before_filed"].median(), M2["days_before_filed"].quantile(0.9), "· 同一天:", M2.filter(pl.col("days_before_filed") == 0).height)
