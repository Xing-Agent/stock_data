#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
建池 · C 口径(按规模档分层)· 2026-10-30

★ 为什么要这一版(策略组 2026-10-30 拍板选 C):

  上一版 `建池-逐年-1029-v2.py` 产出的是「每年按成交额排前 1000 名」。
  ★★ 但实测发现:★ 那个池子和我们现在在跑的池子★ 不是超集关系 ——
     ★ 现有池子 300 只里,★★ 只有 116 只在 2018 年的前 1000 名里,
     ★★★ 另外 137 只不在。
  ★ 原因:★ 现有池子是 large / mid / small ★ 各挑 100 只均分来的,
     ★★ 而「成交额前 1000」天然偏大盘、偏流动。

  ★★★ 所以直接换成前 1000 不是"扩池子",是★「换池子」——
     ★ 老池子里偏小偏冷的那 137 只会掉出去,
     ★★ 而技-8(高紧旗形)、技-9(次新股首发底)正是靠那批票。

  ★★ C 口径的目的:★ 让新旧结论可比 —— ★★★ 同一套挑法,只是只数变多。

────────────────────────────────────────────────────────────────────────
口径(每一条都写明是谁定的)
  · 规模代理 = volume × volume_weighted_average   ★ 这批数据没有市值字段
    ★ 2021-03-26 起的日线没有均价列 → 用 (最高+最低+收盘)/3 代替,逐行标注
  · 先取【成交额前 TOP_FLOOR 名】当合格池   ★★ 这是地板,防止"小盘档"装进一堆
    几乎不可成交的微型票。TOP_FLOOR = 2000 是 XING 拍的,★ 不是原著数字。
  · 再把合格池按成交额★ 三等分(大 / 中 / 小),★ 每档取 PER_TIER 只
    ★ PER_TIER = 330 → 每年约 990 只,★★ 和现有池子同一套挑法(各档均分)
  · 按「段」选池,不按代码选池        ★★★ 改名接续只当标签,不许拼价格(15% 是错的)
  · 剔权证 / 单位 / 权利 / 优先股 / 已知 ETF / 已知清盘产品
────────────────────────────────────────────────────────────────────────

用法(★ 那台机器每条命令 45 秒上限,所以用后台跑):
  nohup python3 建池-规模档-C口径-1030.py <日线目录> ALL > 建池C.log 2>&1 &
  tail -5 建池C.log          # 看进度

  ★ 或者一次只跑一年(断了可以续,已存在的年份自动跳过):
  python3 建池-规模档-C口径-1030.py <日线目录> 2018

产出:
  pool_C_<年>.csv      逐只:年份/档位/档内排名/全局排名/60日日均成交额/段起止
  pool_C_ALL.csv       合表
  pool_C_对照.csv      ★ 现有 300 只池子里,每一只落在 C 池的哪一档(或掉出去了)
★ 推到 GitHub 仓库 probe/survivorship_1029/ 下。
"""
import csv
import glob
import gzip
import json
import os
import re
import sys
from collections import defaultdict

#: ★ 地板:只在成交额前这么多名里分档。XING 拍的,不是原著数字。
TOP_FLOOR = 2000
#: ★ 每档取多少只。330 × 3 ≈ 990,和现有池子「各档均分」同一套挑法。
PER_TIER = 330
LOOKBACK = 60          # 回看 60 个交易日算日均成交额
MIN_DAYS = 30          # 回看窗内至少出现 30 天

KNOWN_ETF_SEED = set(
    "SPY QQQ IWM MDY IVE IVW TLT HYG LQD RSP VIX XLK XLF XLE XLV XLI "
    "XLY XLP XLU XLB XLRE XLC VOO VTI AGG BND IEF SHY EEM EFA GLD SLV "
    "DIA EWJ FXI VWO IJH IJR SDY DVY".split())
#: ★ 已清盘 / 杠杆产品 —— 它们不在任何现存 ETF 名单里,会被当成公司。
#: ★★ 而它们恰恰是死得最惨的那批(XIV 2018-02 一夜清零)。★ 这份名单不完整。
KNOWN_DEAD_PRODUCTS = set(
    "XIV TVIX UGAZ DGAZ UWT DWT SOXL SOXS LABU LABD FAS FAZ TNA TZA "
    "SPXU UPRO UVXY VXX SVXY JNUG JDST NUGT DUST GUSH DRIP".split())


def is_noncompany(sym: str, etf_all: set) -> bool:
    base, _, suf = sym.partition(".")
    sh = suf.split(".")[0] if suf else ""
    if sh.startswith("W") or sh in ("U", "R", "CL"):
        return True
    if len(base) == 5 and base.isalpha() and base[4] in "WUR":
        return True
    if re.fullmatch(r"[A-Z]{2,5}P[A-Z]", base):
        return True
    return sym in etf_all or sym in KNOWN_DEAD_PRODUCTS


def read(path):
    with gzip.open(path, "rt", newline="") as f:
        yield from csv.DictReader(f)


def dollar_vol(r) -> tuple[float, str]:
    """成交额 + 用的是哪种价。★ 2021-03-26 起没有均价列。"""
    try:
        v = float(r.get("volume") or 0)
    except ValueError:
        return 0.0, "bad"
    w = r.get("volume_weighted_average") or r.get("volume_weighted_average_price")
    try:
        w = float(w) if w not in (None, "") else 0.0
    except ValueError:
        w = 0.0
    if w > 0:
        return v * w, "vwap"
    try:
        h, l, c = float(r["high"]), float(r["low"]), float(r["close"])
    except (KeyError, ValueError, TypeError):
        return 0.0, "bad"
    if h <= 0:
        return 0.0, "bad"
    return v * (h + l + c) / 3.0, "typical"


def load_etf_list() -> set:
    for p in ("/home/claude/etf_tickers.txt", "etf_tickers.txt",
              os.path.expanduser("~/etf_tickers.txt")):
        if os.path.exists(p):
            s = set(open(p).read().split())
            print(f"  ETF 名单:{p},{len(s)} 个")
            return s | KNOWN_ETF_SEED
    print("  ★ 没找到 etf_tickers.txt —— 只用内置的 "
          f"{len(KNOWN_ETF_SEED)} 个种子 ETF 名单。★★ 池子里会漏进 ETF,"
          "要在结论里标明")
    return set(KNOWN_ETF_SEED)


def load_segments() -> dict:
    segs = defaultdict(list)
    for p in ("pit_company_segments.csv",
              "../xing-pit-universe-20261029-025954/pit_company_segments.csv"):
        if not os.path.exists(p):
            continue
        with open(p, newline="") as f:
            for r in csv.DictReader(f):
                k = r.get("symbol") or r.get("ticker")
                segs[k].append((r.get("first_seen") or r.get("start"),
                                r.get("last_seen") or r.get("end")))
        print(f"  段表:{p},{sum(len(v) for v in segs.values())} 段")
        return segs
    print("  ★ 没找到 pit_company_segments.csv —— 段列会是空的,"
          "★★ 池子仍可用,但要在结论里标明")
    return segs


def build_year(dates, by_date, year, segs, etf_all) -> str | None:
    out = f"pool_C_{year}.csv"
    if os.path.exists(out):
        print(f"{year}: 已存在 {out},跳过")
        return out
    later = [d for d in dates if d >= f"{year}-01-01"]
    if not later:
        print(f"{year}: 日线不覆盖,跳过")
        return None
    d0 = later[0]
    idx = dates.index(d0)
    window = dates[max(0, idx - LOOKBACK):idx]
    if len(window) < MIN_DAYS:
        print(f"{year}: 回看窗只有 {len(window)} 天 < {MIN_DAYS},跳过")
        return None

    on_d0 = {r["ticker"] for r in read(by_date[d0])}
    dv, nd, price_kind = defaultdict(float), defaultdict(int), defaultdict(set)
    for d in window:
        for r in read(by_date[d]):
            t = r["ticker"]
            if t not in on_d0:
                continue
            val, kind = dollar_vol(r)
            if val <= 0:
                continue
            dv[t] += val
            nd[t] += 1
            price_kind[t].add(kind)

    cand = [(t, dv[t] / nd[t], nd[t],
             "typical" if "typical" in price_kind[t] else "vwap")
            for t in dv
            if not is_noncompany(t, etf_all) and nd[t] >= MIN_DAYS]
    cand.sort(key=lambda x: -x[1])
    floor = cand[:TOP_FLOOR]
    if len(floor) < PER_TIER * 3:
        print(f"{year}: ★ 合格池只有 {len(floor)} 只 < {PER_TIER*3},"
              f"★★ 每档按比例缩减")

    n = len(floor)
    third = n // 3
    tiers = [("大盘档", floor[:third]),
             ("中盘档", floor[third:2 * third]),
             ("小盘档", floor[2 * third:])]

    rows = []
    for tier_name, members in tiers:
        take = members[:PER_TIER]
        for j, (t, adv, days, kind) in enumerate(take):
            seg_s, seg_e = "", ""
            for s, e in segs.get(t, []):
                if s and e and s <= d0 <= e:
                    seg_s, seg_e = s, e
                    break
            rows.append({
                "year": year, "tier": tier_name, "rank_in_tier": j + 1,
                "rank_global": floor.index((t, adv, days, kind)) + 1,
                "symbol": t, "avg_dollar_volume_60d": round(adv, 2),
                "days_in_window": days, "dollar_vol_price": kind,
                "seg_start": seg_s, "seg_end": seg_e,
                "seg_found": int(bool(seg_s)),
            })
    if not rows:
        print(f"{year}: ★★ 一只都没选出来 —— 脚本坏了,不是数据没有")
        return None
    with open(out, "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    nf = sum(1 for r in rows if not r["seg_found"])
    typ = sum(1 for r in rows if r["dollar_vol_price"] == "typical")
    print(f"{year}: 基准日 {d0} · 在册 {len(on_d0)} · 合格池 {len(cand)} "
          f"· 地板取 {len(floor)} · 入池 {len(rows)} "
          f"(没匹配到段 {nf} · 用典型价 {typ})→ {out}")
    return out


def main() -> None:
    daydir = sys.argv[1] if len(sys.argv) > 1 else "/home/claude/pituni/day"
    which = sys.argv[2] if len(sys.argv) > 2 else "ALL"

    files = sorted(glob.glob(os.path.join(daydir, "*.csv.gz")))
    if not files:
        print(f"★★ {daydir} 里没找到 *.csv.gz —— 脚本坏了,不是数据没有。退出。")
        sys.exit(2)
    dates = [os.path.basename(f).split(".")[0] for f in files]
    by_date = dict(zip(dates, files))
    print(f"日线覆盖 {dates[0]} .. {dates[-1]},共 {len(dates)} 个交易日")

    # ★ 硬闸:对照组不过就退出(上次踩过坑才加的)
    probe = {r["ticker"] for r in read(by_date[dates[len(dates) // 2]])}
    missing = [s for s in ("AAPL", "MSFT", "KO") if s not in probe]
    if missing:
        print(f"★★ 对照组没过:{missing} 不在册 → 脚本坏了,不是数据没有。退出。")
        sys.exit(3)
    print("对照组 AAPL/MSFT/KO 通过")

    etf_all = load_etf_list()
    segs = load_segments()

    years = range(2015, 2027) if which == "ALL" else [int(which)]
    made = [p for p in (build_year(dates, by_date, y, segs, etf_all)
                        for y in years) if p]

    if which != "ALL" or not made:
        return

    allrows = []
    for p in made:
        with open(p, newline="") as f:
            allrows += list(csv.DictReader(f))
    with open("pool_C_ALL.csv", "w", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(allrows[0].keys()))
        w.writeheader()
        w.writerows(allrows)
    print(f"★ 合表 pool_C_ALL.csv:{len(allrows)} 行,{len(made)} 个年份")

    # ★★ 对照:现有 300 只池子里,每一只落在 C 池哪一档
    old = None
    for p in ("../../pilot_300", "pilot_300", "/home/claude/pilot_300"):
        if os.path.isdir(p):
            old = sorted(d for d in os.listdir(p)
                         if os.path.isdir(os.path.join(p, d))
                         and d != "benchmarks")
            break
    if not old:
        print("★ 找不到现有池子目录,跳过对照表")
        return
    by_sym = defaultdict(list)
    for r in allrows:
        by_sym[r["symbol"]].append((r["year"], r["tier"]))
    with open("pool_C_对照.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["symbol", "在C池出现年数", "最常落在哪档", "各年明细"])
        for s in old:
            hits = by_sym.get(s, [])
            if hits:
                from collections import Counter
                c = Counter(t for _, t in hits)
                w.writerow([s, len(hits), c.most_common(1)[0][0],
                            ";".join(f"{y}:{t}" for y, t in hits)])
            else:
                w.writerow([s, 0, "★ 掉出 C 池", ""])
    kept = sum(1 for s in old if by_sym.get(s))
    print(f"★★ 对照:现有池子 {len(old)} 只里,{kept} 只进了 C 池,"
          f"★ {len(old)-kept} 只掉出去了 → pool_C_对照.csv")


if __name__ == "__main__":
    main()
