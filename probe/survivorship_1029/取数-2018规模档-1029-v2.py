#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★ 在存着全量日线的那台机器上跑。补上今天唯一补不了的一块:
  2018-01-02 当天、按【前 60 个交易日日均成交额(volume × volume_weighted_average)】
  排名的前 300 名,以及它们到 2025-12-31 的存活情况,分前100/中100/后100 三档。

用法:
  python3 取数-2018规模档-1029.py /path/to/day      # day 目录里是 YYYY-MM-DD.csv.gz
产出:
  pit_top300_2018_survival.csv   (逐只:代码/档位/日均成交额/到2025-12-31是否还在)
  pit_top300_2018_survival.json  (三档汇总)
把这两个文件推到 GitHub 仓库 probe/survivorship_1029/ 下即可。

口径(和 1029 的测量保持一致):
  · 成交额是【市值的代理】,不是市值 —— 这批数据没有市值字段
  · 非公司证券剔除规则 = 权证(.WS/.W*/5字母第5位W)· 单位(.U/第5位U)·
    权利(第5位R)· 优先股或类别股(.CL / 根+P+类别字母)· 在册<60天
  · ETF 认不出来 —— 只能剔掉仓库里已知的那 22 个,其余留在池子里(要在结论里标明)
"""
import csv, glob, gzip, json, os, re, sys
from collections import defaultdict
ETF_ALL = set(open("/home/claude/etf_tickers.txt").read().split())
SEG = defaultdict(list)
for r in csv.DictReader(open("../xing-pit-universe-20261029-025954/pit_company_segments.csv")):
    SEG[r["ticker"]].append(r)

DAYDIR = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/pituni/day"
D0 = "2018-01-02"
END = "2025-12-31"
LOOKBACK = 60
KNOWN_ETF = set("XIV TVIX VXX UGAZ DGAZ UWT DWT USLV DSLV UGLD DGLD JNUG NUGT SVXY ZIV VIIX TVIZ VMIN VMAX XIVH SPXL SPXS SQQQ TQQQ OILU OILD GUSH DRIP LABU LABD BOIL KOLD UCO SCO AGQ ZSL UVXY VIXY SPY QQQ IWM MDY IVE IVW TLT HYG LQD RSP VIX XLK XLF XLE XLV XLI "
                "XLY XLP XLU XLB XLRE XLC".split())

def is_noncompany(sym):
    base, _, suf = sym.partition(".")
    sh = suf.split(".")[0] if suf else ""
    if sh.startswith("W") or sh in ("U", "R", "CL"):
        return True
    if len(base) == 5 and base.isalpha() and base[4] in "WUR":
        return True
    if re.fullmatch(r"[A-Z]{2,5}P[A-Z]", base):
        return True
    return sym in KNOWN_ETF

files = sorted(glob.glob(os.path.join(DAYDIR, "*.csv.gz")))
dates = [os.path.basename(f).split(".")[0] for f in files]
by_date = dict(zip(dates, files))
# 基准日 = 第一个 >= D0 的交易日;回看窗 = 它之前的 60 个交易日
idx = next(i for i, d in enumerate(dates) if d >= D0)
d0 = dates[idx]
window = dates[max(0, idx - LOOKBACK):idx]
print(f"基准日 {d0};回看 {len(window)} 个交易日 {window[0]}..{window[-1]}")

def read(path):
    with gzip.open(path, "rt", newline="") as f:
        for row in csv.DictReader(f):
            yield row

# 1) 基准日当天在册的代码
on_d0 = {r["ticker"] for r in read(by_date[d0])}
print(f"基准日在册代码 {len(on_d0)}")

# 2) 回看窗内累计成交额 + 出现天数(★ 串行,一天一个文件,内存只留 dict)
dv = defaultdict(float)
nd = defaultdict(int)
for d in window:
    for r in read(by_date[d]):
        t = r["ticker"]
        if t not in on_d0:
            continue
        try:
            v = float(r.get("volume") or 0)
            w = float(r.get("volume_weighted_average")
                      or r.get("volume_weighted_average_price") or 0)
        except ValueError:
            continue
        if w <= 0:
            continue
        dv[t] += v * w
        nd[t] += 1

cand = []
for t, tot in dv.items():
    if is_noncompany(t):
        continue
    ss = sorted(SEG.get(t, []), key=lambda r: r["first_seen"])
    cur = [r for r in ss if r["first_seen"] <= d0 <= r["last_seen"]]
    if t in ETF_ALL and (not ss or (cur and cur[0] is ss[-1])):   # ★ v2:ETF 按段剔
        continue
    if nd[t] < LOOKBACK * 0.5:      # 回看窗内出现不足一半 → 当成不够连续,剔掉
        continue
    cand.append((t, tot / nd[t], nd[t]))
cand.sort(key=lambda x: -x[1])
top = cand[:300]
print(f"候选(剔非公司、回看窗出现≥30天)= {len(cand)};取前 300")

# 3) 这 300 只到 END 还在不在 —— 用 END 当天(或之后最近一天)的名单
end_dates = [d for d in dates if d >= END]
if not end_dates:
    print("★ 日线不覆盖 2025-12-31,停"); sys.exit(1)
dE = end_dates[0]
on_end = {r["ticker"] for r in read(by_date[dE])}
print(f"存活判定日 {dE},当天在册 {len(on_end)}")

rows, summary = [], {}
for i, (t, adv, n) in enumerate(top):
    tier = "前100" if i < 100 else ("中100" if i < 200 else "后100")
    alive_ticker = t in on_end
    cur = [r for r in SEG.get(t, []) if r["first_seen"] <= d0 <= r["last_seen"]]
    sg = cur[0] if cur else None
    # ★ v2:按段判。同名还在 / 改名还在(沿接续链走到底仍在交易)/ 消失
    status, chain = "无段信息", ""
    if sg:
        if sg["last_seen"] >= dE:
            status = "同名还在"
        else:
            k, seen, nm = sg, set(), []
            while k and k["renamed_to"] and k["seg_id"] not in seen:
                seen.add(k["seg_id"]); nm.append(k["renamed_to"])
                nxt = [r for r in SEG.get(k["renamed_to"], []) if r["renamed_from"] == k["ticker"]]
                k = nxt[0] if nxt else None
            chain = "→".join(nm)
            status = "改名还在" if (k and k is not sg and k["last_seen"] >= dE) else ("改名后又消失" if nm else "消失")
    alive = status in ("同名还在", "改名还在")
    rows.append({"rank": i + 1, "symbol": t, "tier": tier,
                 "avg_dollar_volume_60d": round(adv, 2),
                 "days_in_window": n, "alive_on_end": int(alive), "status": status,
                 "rename_chain": chain, "seg_last_seen": sg["last_seen"] if sg else "",
                 "ticker_on_end_原口径": int(alive_ticker)})
for tier in ("前100", "中100", "后100"):
    sub = [r for r in rows if r["tier"] == tier]
    a = sum(r["alive_on_end"] for r in sub)
    summary[tier] = {"n": len(sub), "alive": a,
                     "survival_pct": round(a / len(sub) * 100, 2),
                     "disappear_pct": round((len(sub) - a) / len(sub) * 100, 2)}
a = sum(r["alive_on_end"] for r in rows)
summary["合计"] = {"n": len(rows), "alive": a,
                   "survival_pct": round(a / len(rows) * 100, 2),
                   "disappear_pct": round((len(rows) - a) / len(rows) * 100, 2)}
for st in ("同名还在", "改名还在", "改名后又消失", "消失", "无段信息"):
    summary.setdefault("按状态", {})[st] = sum(1 for r in rows if r["status"] == st)
summary["原口径_按代码判存活"] = sum(r["ticker_on_end_原口径"] for r in rows)
summary["口径"] = {"基准日": d0, "回看": [window[0], window[-1]],
                   "存活判定日": dE, "规模代理": "volume × volume_weighted_average(不是市值)",
                   "v2改动": "ETF 按段剔(CMES 名单只用于当前那一段);存活按段判,改名沿接续链走到底"}

with open("pit_top300_2018_survival.csv", "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
with open("pit_top300_2018_survival.json", "w") as f:
    json.dump(summary, f, ensure_ascii=False, indent=1)
print(json.dumps(summary, ensure_ascii=False, indent=1))
