#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""幸存者偏差实测 1029 —— 串行、低内存。"""
import csv, json, os, re, sys, datetime as dt
from collections import Counter, defaultdict

PIT = "/home/claude/xing-agent-stock_data/probe/xing-pit-universe-20261029-025954"
REPO = "/home/claude/xing-agent-stock_data"
OUT = {}

def load(name):
    with open(os.path.join(PIT, name)) as f:
        return list(csv.DictReader(f))

syms = load("pit_universe_symbols.csv")
counts = load("pit_universe_daily_counts.csv")
disapp = load("pit_universe_disappeared.csv")
gaps = load("pit_universe_gap_suspects.csv")
for r in syms:
    r["trading_days"] = int(r["trading_days"])
print(f"[读入] symbols={len(syms)} daily_counts={len(counts)} disappeared={len(disapp)} gap_suspects={len(gaps)}")

# ---------------- 一 · 证券分类 ----------------
# 已知 ETF(仓库里有的)
known_etf = set()
for d, names in (
    (os.path.join(REPO, "pilot_300", "benchmarks"), None),
    (os.path.join(REPO, "reference_etfs_20261025"), None),
):
    if os.path.isdir(d):
        for e in os.listdir(d):
            if os.path.isdir(os.path.join(d, e)) and re.fullmatch(r"[A-Z]{1,5}", e):
                known_etf.add(e)
known_etf |= {"SPY", "QQQ", "IWM", "MDY", "IVE", "IVW", "TLT", "HYG", "LQD", "RSP"}
known_etf |= {"XL" + c for c in "KFEVIYPUB"} | {"XLRE", "XLC"}
print(f"[ETF 清单] 仓库里可交叉的 ETF 代码数 = {len(known_etf)} -> {sorted(known_etf)}")

def classify(sym):
    """返回 (大类, 依据)。保守:只有高置信度才判非公司。"""
    base, _, suf = sym.partition(".")
    suf_head = suf.split(".")[0] if suf else ""
    if suf_head.startswith("W"):
        return "warrant", "dot-suffix .%s" % suf
    if suf_head == "U":
        return "unit", "dot-suffix .U"
    if suf_head == "R":
        return "right", "dot-suffix .R"
    # .CL = Polygon 的优先股/类别股后缀,样本全是 XXXPy 形态
    if suf_head == "CL":
        return "preferred_or_class", "dot-suffix .CL"
    if len(base) == 5 and base.isalpha():
        c = base[4]
        if c == "W":
            return "warrant", "5字母第5位W"
        if c == "U":
            return "unit", "5字母第5位U"
        if c == "R":
            return "right", "5字母第5位R"
    # 优先股形态:根 + P + 类别字母(AAICPB / ALLYPB / AESPC)
    if re.fullmatch(r"[A-Z]{2,5}P[A-Z]", base):
        return "preferred_or_class", "形态 ROOT+P+类别字母"
    if sym in known_etf:
        return "etf_known", "仓库已知 ETF 清单"
    return "unclassified", ""

cls = {}
why = Counter()
for r in syms:
    k, w = classify(r["symbol"])
    cls[r["symbol"]] = k
    why[(k, w)] += 1
cat = Counter(cls.values())
print("\n=== 一 · 分类结果(按代码,25,689 个)===")
for k, v in cat.most_common():
    print(f"  {k:22s} {v:6d}  {v/len(syms)*100:5.2f}%")

# 行为特征:只有「在册天数」可算
short = [r["symbol"] for r in syms if r["trading_days"] < 60]
short_unc = [s for s in short if cls[s] == "unclassified"]
print(f"\n  行为筛(唯一可算的一条):在册 <60 天 = {len(short)} 个,"
      f"其中原本未分类的 {len(short_unc)} 个")
OUT["cls"] = cat
OUT["short"] = (len(short), len(short_unc))
OUT["why"] = why

# 认定为「非公司」的集合
NONCO = {"warrant", "unit", "right", "preferred_or_class", "etf_known"}
nonco = {s for s, k in cls.items() if k in NONCO} | set(short)
print(f"  → 判定为非公司证券(含在册<60天):{len(nonco)} 个 "
      f"({len(nonco)/len(syms)*100:.2f}%)")
print(f"  → 剩下「疑似真公司 + 认不出的 ETF」:{len(syms)-len(nonco)} 个 "
      f"({(len(syms)-len(nonco))/len(syms)*100:.2f}%)")
OUT["nonco_n"] = len(nonco)

# ---------------- 二 · PIT 重建池 ----------------
dates = [c["date"] for c in counts]
target = "2018-01-02"
d0 = min((d for d in dates if d >= target), key=lambda x: x)
END = "2025-12-31"
print(f"\n=== 二 · 核心测量:基准日 {d0}(目标 {target});存活判定日 {END} ===")
print(f"  当日名单代码数(daily_counts)= {dict((c['date'],c['n_symbols']) for c in counts)[d0]}")

alive0 = [r for r in syms if r["first_seen"] <= d0 <= r["last_seen"]]
print(f"  区间覆盖 {d0} 的代码数(first_seen<=d<=last_seen)= {len(alive0)}")
alive0_co = [r for r in alive0 if r["symbol"] not in nonco]
print(f"  剔掉非公司后 = {len(alive0_co)}")

def surv(rows):
    s = sum(1 for r in rows if r["last_seen"] >= END)
    return s, len(rows), (s / len(rows) * 100 if rows else float("nan"))

for label, rows in (("全部代码", alive0), ("剔非公司后", alive0_co)):
    s, n, p = surv(rows)
    print(f"  {label:12s} n={n:6d}  到{END}还在={s:6d}  存活率={p:5.2f}%  消失率={100-p:5.2f}%")
OUT["coh"] = {"d0": d0, "all": surv(alive0), "co": surv(alive0_co)}

# 替代分层:上市年龄档(非规模!)
print("\n  ★ 规模分档【做不到】—— 没有市值,也没有成交额(原始日线文件已不在机器上)")
print("  ★ 退而求其次:按「基准日之前已在册多久」分三档(这是上市年龄,不是规模)")
start = "2015-12-01"
buckets = defaultdict(list)
for r in alive0_co:
    fs = r["first_seen"]
    if fs <= start:
        buckets["A·样本起点就在(>=2年)"].append(r)
    elif fs <= "2017-01-02":
        buckets["B·2016年内上市"].append(r)
    else:
        buckets["C·2017年后上市(<1年)"].append(r)
for k in sorted(buckets):
    s, n, p = surv(buckets[k])
    print(f"    {k:26s} n={n:5d}  存活={s:5d}  存活率={p:5.2f}%  消失率={100-p:5.2f}%")
OUT["age"] = {k: surv(v) for k, v in buckets.items()}

# 我们池子的消失率(口径对齐:到 2025-12-31)
man = list(csv.DictReader(open(os.path.join(REPO, "pilot_300", "manifest.csv"))))
dl = sum(1 for r in man if r["delisted"] == "True")
print(f"\n  我们的池子:{len(man)} 只,delisted=True {dl} 只 = {dl/len(man)*100:.2f}% 消失率")
OUT["ours"] = (dl, len(man))

# ---------------- 三 · 反向检查 ----------------
print("\n=== 三 · 反向检查:我们 300 只 vs PIT 名单 ===")
pit = {r["symbol"]: r for r in syms}
missing_in_pit, not_alive_d0, late_listed = [], [], []
mismatch = []
for r in man:
    sym = r["symbol"]
    p = pit.get(sym)
    if p is None:
        missing_in_pit.append(sym)
        continue
    if not (p["first_seen"] <= d0 <= p["last_seen"]):
        not_alive_d0.append((sym, p["first_seen"], p["last_seen"], r["size_group"]))
    if p["first_seen"] > d0:
        late_listed.append((sym, p["first_seen"], r["size_group"]))
    # last_seen vs 我们的 download_end_date / delisted
    de = r["download_end_date"]
    if r["delisted"] == "True":
        # PIT 的 last_seen 应与退市日接近
        try:
            d_pit = dt.date.fromisoformat(p["last_seen"])
            d_man = dt.date.fromisoformat(de)
            diff = abs((d_pit - d_man).days)
        except Exception:
            diff = None
        if diff is None or diff > 30:
            mismatch.append((sym, p["last_seen"], de, diff, "已退市但PIT last_seen差>30天"))
    else:
        if p["last_seen"] < "2026-07-01":
            mismatch.append((sym, p["last_seen"], de, None, "我们标未退市但PIT里已消失"))
print(f"  PIT 名单里【完全找不到】的:{len(missing_in_pit)} -> {missing_in_pit}")
print(f"  {d0} 当天【不在册】的:{len(not_alive_d0)}")
for x in not_alive_d0:
    print("     ", x)
print(f"  对不上的(last_seen vs manifest):{len(mismatch)}")
for x in mismatch:
    print("     ", x)
OUT["rev"] = {"missing": missing_in_pit, "not_alive": not_alive_d0, "mismatch": mismatch}

# 拼接嫌疑:★ 正确算法 = 最长连续缺失(用我们自己的日线,按工作日数)
print("\n  ★ 拼接嫌疑:最长连续缺失(用我们自己的 daily.json;工作日计数)+ 跨缺口价格量级突变")
def bdays(a, b):
    n, d = 0, a
    one = dt.timedelta(days=1)
    while d < b:
        d += one
        if d.weekday() < 5:
            n += 1
    return n

splice = []
nofile = []
for r in man:
    sym = r["symbol"]
    pth = os.path.normpath(os.path.join(REPO, "pilot_300", r["data_path"]))
    if not os.path.exists(pth):
        nofile.append(sym); continue
    try:
        with open(pth) as f:
            bars = json.load(f).get("data") or []
    except Exception as e:
        nofile.append(sym); continue
    bars = [b for b in bars if b.get("date") and b.get("close")]
    best = (0, None, None, None, None)
    for i in range(1, len(bars)):
        a = dt.date.fromisoformat(bars[i-1]["date"]); b = dt.date.fromisoformat(bars[i]["date"])
        g = bdays(a, b) - 1
        if g > best[0]:
            best = (g, bars[i-1]["date"], bars[i]["date"], bars[i-1]["close"], bars[i]["close"])
    g, da, db, ca, cb = best
    if g >= 20:
        ratio = (cb / ca) if (ca and cb) else None
        splice.append((sym, r["size_group"], g, da, db, ca, cb, ratio))
    del bars
splice.sort(key=lambda x: -x[2])
print(f"  最长连续缺失 >=20 个工作日的:{len(splice)} 只;读不到日线文件的:{len(nofile)} -> {nofile[:10]}")
for x in splice[:40]:
    print(f"     {x[0]:6s} {x[1]:5s} 缺{x[2]:4d}工作日 {x[3]}->{x[4]} close {x[5]}->{x[6]} 倍数={x[7]:.2f}" if x[7] else f"     {x}")
OUT["splice"] = splice
OUT["nofile"] = nofile

# ---------------- 四 · ETF 清单确认 ----------------
want = ("HYG LQD SPY QQQ IWM XLK XLF XLE XLV XLI XLY XLP XLU XLB XLRE XLC "
        "MDY IVE IVW TLT").split()
print("\n=== 四 · 这些在不在 PIT 名单里 ===")
etf_rows = []
for s in want:
    p = pit.get(s)
    if p:
        print(f"  ✅ {s:5s} {p['first_seen']} -> {p['last_seen']}  在册 {p['trading_days']} 天")
        etf_rows.append((s, True, p["first_seen"], p["last_seen"], p["trading_days"]))
    else:
        print(f"  ❌ {s:5s} 不在名单里")
        etf_rows.append((s, False, "", "", ""))
OUT["etf"] = etf_rows

# gap_suspects 里我们 300 只命中几只
ours = {r["symbol"] for r in man}
hit = [g for g in gaps if g["symbol"] in ours]
print(f"\n  （参考）gap_suspects(累计口径,已知有缺陷)里命中我们 300 只的:{len(hit)} -> {[h['symbol'] for h in hit]}")
OUT["gap_hit"] = [h["symbol"] for h in hit]

with open("/tmp/claude-0/-home-claude/e6b5eede-2545-5921-9bbc-5820cecf2c9c/scratchpad/sb_out.json", "w") as f:
    json.dump({k: (v if not isinstance(v, Counter) else {str(a): b for a, b in v.items()}) for k, v in OUT.items()}, f, ensure_ascii=False, default=str, indent=1)
print("\n[done]")
