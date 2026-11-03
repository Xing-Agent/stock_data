#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
全量库盘点(2026-11-03)—— 只读,不改任何文件。

用途:在存放 20 年全量数据的那台机器上跑一遍,回答三件事:
  ① 基本面有哪些字段、覆盖多少只票、多少年
  ② ★★★ 有没有「申报日」,以及重述能不能分开(决定能不能用于回测)
  ③ 票数能不能覆盖考卷池

用法(任选一种):
    python3 inventory_fulllib_1103.py <数据根目录>
    python3 inventory_fulllib_1103.py          # 不给参数则自动扫 HOME 和常见位置

产出:
    ./库盘点-1103.json      ← ★ 把这个推到 GitHub 就行
    屏幕上同时打印摘要

★ 不读大文件全文:每个文件只抽头部样本,所以跑得很快。
"""
import json, os, sys, gzip, io, glob, re

OUT = "库盘点-1103.json"
MAXDEPTH = 5
SAMPLE_BYTES = 300_000          # 每个文件只抽这么多字节做结构判断

# ★ 我们关心的字段(基本面)
WANT_TAGS = [
    "PropertyPlantAndEquipmentNet",      # ★★★ 基-4 神奇公式缺的那一个
    "Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
    "NetIncomeLoss", "EarningsPerShareDiluted", "GrossProfit",
    "OperatingIncomeLoss", "Assets", "AssetsCurrent", "LiabilitiesCurrent",
    "StockholdersEquity", "LongTermDebtNoncurrent",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "NetCashProvidedByUsedInOperatingActivities",
    "DepreciationDepletionAndAmortization",
]
# ★★★ 决定「能不能用于回测」的时点字段
PIT_KEYS = ["filed", "filing_date", "filingDate", "acceptedDate", "accepted",
            "period_of_report", "periodOfReport", "frame", "fy", "fp",
            "start", "end", "report_date", "date_filed", "version", "restated",
            "amendment", "amended", "original", "form"]

HINT = re.compile(r"(fundament|financ|companyfact|xbrl|sec|income|balance|cashflow|"
                  r"daily|price|ohlc|bar|minute|split|dividend|ticker)", re.I)
EXTS = (".json", ".json.gz", ".jsonl", ".jsonl.gz", ".csv", ".csv.gz",
        ".parquet", ".pq", ".db", ".sqlite", ".h5", ".feather")


def roots_from_args():
    if len(sys.argv) > 1:
        return [os.path.expanduser(p) for p in sys.argv[1:]]
    home = os.path.expanduser("~")
    cand = [home,
            os.path.join(home, "Desktop"), os.path.join(home, "Documents"),
            os.path.join(home, "Downloads"), os.path.join(home, "data"),
            "/data", "/mnt", "/Volumes", "D:\\", "E:\\", "F:\\"]
    return [p for p in cand if os.path.isdir(p)]


def walk(root):
    base = root.rstrip(os.sep).count(os.sep)
    for dirpath, dirnames, filenames in os.walk(root, topdown=True):
        if dirpath.count(os.sep) - base >= MAXDEPTH:
            dirnames[:] = []
        dirnames[:] = [d for d in dirnames
                       if not d.startswith(".") and d not in
                       ("node_modules", "__pycache__", "Library", "Applications",
                        "Windows", "Program Files", "AppData", "site-packages")]
        for fn in filenames:
            low = fn.lower()
            if low.endswith(EXTS):
                yield os.path.join(dirpath, fn)


def head(path, n=SAMPLE_BYTES):
    try:
        if path.lower().endswith(".gz"):
            with gzip.open(path, "rb") as f:
                return f.read(n).decode("utf-8", "ignore")
        with open(path, "rb") as f:
            return f.read(n).decode("utf-8", "ignore")
    except Exception as e:
        return "<<读不动: %s>>" % e


def probe(path):
    sz = os.path.getsize(path)
    rec = {"path": path, "mb": round(sz / 1e6, 1)}
    low = path.lower()
    if low.endswith((".parquet", ".pq", ".feather", ".db", ".sqlite", ".h5")):
        rec["note"] = "二进制格式,本脚本不解析 —— ★ 需要的话我再给一段针对它的命令"
        return rec
    txt = head(path)
    rec["tags_found"] = sorted({t for t in WANT_TAGS if t in txt})
    rec["pit_keys_found"] = sorted({k for k in PIT_KEYS
                                    if re.search(r'["\',]\s*%s\s*["\':,]' % re.escape(k), txt)
                                    or ("," + k + ",") in txt
                                    or txt.lstrip().startswith(k + ",")})
    yrs = re.findall(r"\b(19[89]\d|20[0-4]\d)-\d\d-\d\d\b", txt)
    if yrs:
        rec["years_in_sample"] = [min(yrs), max(yrs)]
    if low.endswith((".csv", ".csv.gz")):
        rec["header"] = txt.split("\n", 1)[0][:600]
    else:
        try:
            obj = json.loads(txt)
            rec["json_top_keys"] = list(obj)[:40] if isinstance(obj, dict) else "<list>"
        except Exception:
            rec["json_top_keys"] = "<截断,无法整体解析;见 tags_found/pit_keys_found>"
    return rec


def main():
    roots = roots_from_args()
    print("★ 扫描根目录:", roots)
    hits, seen = [], set()
    for r in roots:
        for p in walk(r):
            if p in seen:
                continue
            seen.add(p)
            fn = os.path.basename(p)
            try:
                big = os.path.getsize(p) > 2_000_000
            except OSError:
                continue
            if HINT.search(p) or big:
                hits.append(p)
            if len(hits) > 4000:
                break

    hits.sort(key=lambda p: -os.path.getsize(p))
    picked = hits[:60]
    print("★ 命中 %d 个候选文件,盘点最大的 %d 个" % (len(hits), len(picked)))

    out = {"generated": "2026-11-03", "roots": roots,
           "candidate_count": len(hits), "files": []}
    for i, p in enumerate(picked, 1):
        rec = probe(p)
        out["files"].append(rec)
        print("\n[%d/%d] %s  (%s MB)" % (i, len(picked), p, rec["mb"]))
        if rec.get("tags_found"):
            print("   ★ 命中字段:", ", ".join(rec["tags_found"]))
        if rec.get("pit_keys_found"):
            print("   ★★★ 时点字段:", ", ".join(rec["pit_keys_found"]))
        if rec.get("years_in_sample"):
            print("   ★ 样本里的日期范围:", rec["years_in_sample"])
        if rec.get("header"):
            print("   表头:", rec["header"][:300])
        if rec.get("note"):
            print("  ", rec["note"])

    # 三秒版结论
    anypp = any("PropertyPlantAndEquipmentNet" in f.get("tags_found", [])
                for f in out["files"])
    anypit = any(f.get("pit_keys_found") for f in out["files"])
    out["三秒版"] = {
        "有没有 PP&E(基-4 缺的那个)": bool(anypp),
        "有没有时点字段(决定能不能回测)": bool(anypit),
    }
    print("\n" + "=" * 60)
    print("★★★ 三秒版")
    print("  有 PropertyPlantAndEquipmentNet 吗 :", "有" if anypp else "样本里没看到")
    print("  有申报日/版本这类时点字段吗       :", "有" if anypit else "样本里没看到")
    print("=" * 60)

    with open(OUT, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print("\n★ 已写出:", os.path.abspath(OUT))
    print("★ 把这个文件推到 GitHub 就行(只有结构信息,没有行情数据本身)")


if __name__ == "__main__":
    main()
