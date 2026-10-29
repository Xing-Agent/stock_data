#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★ 在存着全量日线的那台机器上跑。目的:生产一个没有幸存者偏差的池子。

和 取数-2018规模档-1029.py 的区别:
  那个只回答「幸存者偏差有多大」(存活率),★ 不生产池子。
  ★★ 这个生产池子本身 —— 逐年给出「那一年年初真实可买的前 N 名」。

★ 关键口径(来自那台机器自己的提醒,必须遵守):
  ★★ 按「段」选池,不按代码选池。改名接续只当标签用,不许把前后两段价格拼成一条。
     (有 15% 是错的,拼错了等于把仓位转进一只毫不相干的新股。)
  ★ 段一消失,就按最后价出场。

用法(★ 一次只跑一年,因为那台机器每条命令有 45 秒上限):
  python3 建池-逐年-1029.py /path/to/day 2018
  python3 建池-逐年-1029.py /path/to/day 2019
  ...
★ 或者后台一次跑完(推荐):
  nohup python3 建池-逐年-1029.py /path/to/day ALL > 建池.log 2>&1 &
  然后 tail -5 建池.log 看进度

产出(每年一个文件,断了可以续跑,已存在的年份自动跳过):
  pool_pit_<年>.csv     逐只:排名/代码/档位/60日日均成交额/段起止
产出(全部跑完后):
  pool_pit_ALL.csv      合起来的一张表
把这些文件推到 GitHub 仓库 probe/survivorship_1029/ 下即可。
"""
import csv, glob, gzip, json, os, re, sys
from collections import defaultdict

TOPN = 1000          # ★ 每年取前 1000 —— 比现在的 298 只大 3.3 倍
LOOKBACK = 60        # 回看 60 个交易日算日均成交额
MIN_DAYS = 30        # 回看窗内至少出现 30 天,否则当成不够连续
KNOWN_ETF = set("SPY QQQ IWM MDY IVE IVW TLT HYG LQD RSP VIX XLK XLF XLE XLV XLI "
                "XLY XLP XLU XLB XLRE XLC".split())

def is_noncompany(sym):
    """剔掉权证/单位/权利/优先股/已知 ETF。口径和 1029 的测量保持一致。"""
    base, _, suf = sym.partition(".")
    sh = suf.split(".")[0] if suf else ""
    if sh.startswith("W") or sh in ("U", "R", "CL"):
        return True
    if len(base) == 5 and base.isalpha() and base[4] in "WUR":
        return True
    if re.fullmatch(r"[A-Z]{2,5}P[A-Z]", base):
        return True
    return sym in KNOWN_ETF

def read(path):
    with gzip.open(path, "rt", newline="") as f:
        for row in csv.DictReader(f):
            yield row

def build_one_year(dates, by_date, year, segs):
    out = f"pool_pit_{year}.csv"
    if os.path.exists(out):
        print(f"{year}: 已存在 {out},跳过"); return out
    d0_target = f"{year}-01-01"
    later = [d for d in dates if d >= d0_target]
    if not later:
        print(f"{year}: 日线不覆盖,跳过"); return None
    d0 = later[0]
    idx = dates.index(d0)
    window = dates[max(0, idx - LOOKBACK):idx]
    if len(window) < MIN_DAYS:
        print(f"{year}: 回看窗只有 {len(window)} 天,不足 {MIN_DAYS},跳过"); return None

    on_d0 = {r["ticker"] for r in read(by_date[d0])}
    dv, nd = defaultdict(float), defaultdict(int)
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

    cand = [(t, dv[t] / nd[t], nd[t]) for t in dv
            if not is_noncompany(t) and nd[t] >= MIN_DAYS]
    cand.sort(key=lambda x: -x[1])
    top = cand[:TOPN]

    rows = []
    for i, (t, adv, n) in enumerate(top):
        # ★ 段归属:找包含 d0 的那一段,池子记的是段,不是代码
        seg_s, seg_e = "", ""
        for s, e in segs.get(t, []):
            if s <= d0 <= e:
                seg_s, seg_e = s, e
                break
        rows.append({"year": year, "rank": i + 1, "symbol": t,
                     "tier": "前300" if i < 300 else ("中300" if i < 600 else "后400"),
                     "avg_dollar_volume_60d": round(adv, 2),
                     "days_in_window": n,
                     "seg_start": seg_s, "seg_end": seg_e,
                     "seg_found": int(bool(seg_s))})
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)
    nf = sum(1 for r in rows if not r["seg_found"])
    print(f"{year}: 基准日 {d0} · 在册 {len(on_d0)} · 候选 {len(cand)} · 取 {len(rows)} "
          f"· ★ 没匹配到段的 {nf} 只 → {out}")
    return out

def main():
    daydir = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/pituni/day"
    which  = sys.argv[2] if len(sys.argv) > 2 else "ALL"

    files = sorted(glob.glob(os.path.join(daydir, "*.csv.gz")))
    if not files:
        print(f"★ {daydir} 里没找到 *.csv.gz —— 脚本坏了,不是数据没有。退出。"); sys.exit(2)
    dates = [os.path.basename(f).split(".")[0] for f in files]
    by_date = dict(zip(dates, files))
    print(f"日线覆盖 {dates[0]} .. {dates[-1]},共 {len(dates)} 个交易日")

    # ★ 硬闸:对照组不过就退出(这条是上次踩过坑才加的)
    probe = {r["ticker"] for r in read(by_date[dates[len(dates)//2]])}
    missing = [s for s in ("AAPL", "MSFT", "KO") if s not in probe]
    if missing:
        print(f"★★ 对照组没过:{missing} 不在册 → 脚本坏了,不是数据没有。退出。"); sys.exit(3)
    print("对照组 AAPL/MSFT/KO 通过")

    # 段表(按公司切分的那份,上次已经做好推上去了)
    segs = defaultdict(list)
    segfile = next((p for p in ("pit_company_segments.csv",
                                "../xing-pit-universe-20261029-025954/pit_company_segments.csv")
                    if os.path.exists(p)), None)
    if segfile:
        with open(segfile, newline="") as f:
            for r in csv.DictReader(f):
                segs[r.get("symbol") or r.get("ticker")].append(
                    (r.get("first_seen") or r.get("start"), r.get("last_seen") or r.get("end")))
        print(f"段表已加载:{segfile},{sum(len(v) for v in segs.values())} 段")
    else:
        print("★ 没找到 pit_company_segments.csv —— 段列会是空的,池子仍可用,但要在结论里标明")

    years = range(2015, 2027) if which == "ALL" else [int(which)]
    made = [p for p in (build_one_year(dates, by_date, y, segs) for y in years) if p]

    if which == "ALL" and made:
        allrows = []
        for p in made:
            with open(p, newline="") as f:
                allrows += list(csv.DictReader(f))
        with open("pool_pit_ALL.csv", "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(allrows[0].keys()))
            w.writeheader(); w.writerows(allrows)
        print(f"★ 合表 pool_pit_ALL.csv:{len(allrows)} 行,{len(made)} 个年份")

if __name__ == "__main__":
    main()
