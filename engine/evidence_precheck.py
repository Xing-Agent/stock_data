"""
evidence_precheck —— ★★ 对技术方报「缺字段 / 数据有问题」之前的**强制检查**。

================================ 三秒版 ================================
这个脚本回答一句话:**「你说缺的那个字段,到底是真缺,还是我们没读?」**

★ 为什么要有它:这类错已经两次了 ——
  · 上周:我们报「缺 delisting_reason」,实际 manifest.csv 里的
    retirement_category 早就有,是我们没翻到。
  · 本轮:我们报「缺 LongTermDebt」,实际字段在、覆盖 46%、代码里一直在读;
    我们报「拆股跳变区分不出来」,实际 daily.json 自带 split_coefficient
    已经能解释 34/57 根,只是 load_daily() 从来没读它;
    我们报「现金流可能被重复计入」,实际引擎早就做了 YTD 差分。
  ★ 三条的共同根因都是同一个:**没有在原始文件里查过就下结论**。

★★ 纪律(硬性,写在这里就是为了被引用):
  ┌──────────────────────────────────────────────────────────────────┐
  │ 凡要对技术方报「缺字段 / 数据有问题」,必须先跑这个脚本,         │
  │ 并把脚本输出**原样附在提单里**。★ 跑不过不准发单。                │
  └──────────────────────────────────────────────────────────────────┘
  判定口径:
    · 字段在原始文件里**存在** → ★ 不许报「缺字段」,只能报「覆盖不足」,
      并且必须给出实测覆盖率。
    · 字段存在、但 engine 里**没有任何代码读它** → ★ 这是我方 bug,
      不许发单,先把代码改了。
    · 字段真的不在原始文件里 → 才可以报「缺」,并附本脚本的输出。

跑法:
  python -m engine.evidence_precheck LongTermDebt EBIT DebtCurrent
  python -m engine.evidence_precheck --daily split_coefficient
  python -m engine.evidence_precheck --audit-loaders      # ★ 查所有「有但没读」的字段
  python -m engine.evidence_precheck --all                # 三件一起
=========================================================================
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from collections import Counter

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ENGINE = os.path.join(REPO, "engine")
PILOT = os.path.join(REPO, "pilot_300")

SEP = "=" * 78


# ─────────────────────────────── 工具 ───────────────────────────────

def _symbols() -> list[str]:
    return sorted(d for d in os.listdir(PILOT)
                  if os.path.isdir(os.path.join(PILOT, d))
                  and os.path.exists(os.path.join(PILOT, d, "daily.json")))


def _load(sym: str, which: str) -> dict | None:
    p = os.path.join(PILOT, sym, f"{which}.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return None


def _grep(pattern: str) -> list[tuple[str, int, str]]:
    """在 engine/ 里找字段名出现的位置。用 grep -rn,拿不到就退回纯 Python。"""
    try:
        out = subprocess.run(
            ["grep", "-rn", "--include=*.py", "-F", pattern, ENGINE],
            capture_output=True, text=True, timeout=60).stdout
        hits = []
        for line in out.splitlines():
            parts = line.split(":", 2)
            if len(parts) < 3:
                continue
            hits.append((os.path.relpath(parts[0], REPO), int(parts[1]), parts[2].strip()))
        return hits
    except (OSError, subprocess.SubprocessError, ValueError):
        return []


def _is_self_reference(path: str) -> bool:
    """本脚本和证据包脚本里的提及不算「代码在读它」。"""
    base = os.path.basename(path)
    return base.startswith("evidence_")


# ────────────────────── 检查一:基本面字段 ──────────────────────

def check_fundamental_field(field: str) -> dict:
    syms = _symbols()
    has_key = has_val = 0
    n_recs = 0
    reasons: Counter = Counter()
    status: Counter = Counter()
    tags: Counter = Counter()
    derived = None
    no_file = 0
    examples_present: list[str] = []
    for s in syms:
        blob = _load(s, "fundamentals")
        if blob is None:
            no_file += 1
            continue
        fv = blob.get("financial_versions") or {}
        cov = blob.get("coverage") or {}
        af = (cov.get("additional_fields") or {}).get(field)
        dm = (cov.get("derived_metrics") or {}).get(field)
        if dm and derived is None:
            derived = dm.get("formula")
        if af:
            status[af.get("status") or "?"] += 1
            if af.get("missing_reason"):
                reasons[af["missing_reason"]] += 1
        if field in fv:
            has_key += 1
            recs = [r for r in (fv[field] or []) if r.get("value") not in (None, "")]
            n_recs += len(recs)
            if recs:
                has_val += 1
                if len(examples_present) < 5:
                    examples_present.append(
                        f"{s}:{len(recs)} 期 "
                        f"({recs[0].get('period_end')}..{recs[-1].get('period_end')})")
                for r in recs:
                    if r.get("source_tag"):
                        tags[r["source_tag"]] += 1
    hits = [h for h in _grep(field) if not _is_self_reference(h[0])]
    return {
        "field": field, "n_symbols": len(syms), "no_file": no_file,
        "has_key": has_key, "has_value": has_val, "n_records": n_recs,
        "source_tags": dict(tags.most_common(5)),
        "delivery_status": dict(status), "missing_reasons": dict(reasons),
        "derived_formula": derived,
        "examples": examples_present,
        "code_hits": hits,
    }


# ────────────────────── 检查二:日线字段 ──────────────────────

def check_daily_field(field: str) -> dict:
    syms = _symbols()
    has_key = 0
    nonnull_syms = 0
    n_bars = n_key = n_nonnull = 0
    nontrivial_syms: list[str] = []
    for s in syms:
        blob = _load(s, "daily")
        rows = (blob or {}).get("data") or []
        if not rows:
            continue
        n_bars += len(rows)
        k = sum(1 for r in rows if field in r)
        nn = 0
        nt = 0
        for r in rows:
            v = r.get(field)
            if v is None:
                continue
            if isinstance(v, float) and v != v:
                continue
            nn += 1
            if field == "split_coefficient" and float(v) != 1.0:
                nt += 1
        n_key += k
        n_nonnull += nn
        if k:
            has_key += 1
        if nn:
            nonnull_syms += 1
        if nt:
            nontrivial_syms.append(s)
    hits = [h for h in _grep(field) if not _is_self_reference(h[0])]
    return {
        "field": field, "n_symbols": len(syms), "has_key_symbols": has_key,
        "nonnull_symbols": nonnull_syms, "n_bars": n_bars,
        "n_bars_with_key": n_key, "n_bars_nonnull": n_nonnull,
        "nontrivial_symbols": nontrivial_syms, "code_hits": hits,
    }


# ────────────────────── 检查三:loader 字段审计 ──────────────────────
#
# ★ 这一节回答:engine 里还有没有别的 loader 像 load_daily 那样「只读了一部分」?
#   做法:把每个 loader **实际读取的字段**(人工登记 + 下面的 grep 核对)
#   和**原始文件里可用的字段**对一次差。

#: (loader 名, 代码位置, 原始文件, 层级, 实际读取的字段)
LOADERS: tuple[tuple[str, str, str, str, tuple[str, ...]], ...] = (
    ("data.load_daily", "engine/data.py::load_daily", "pilot_300/<T>/daily.json",
     "data[]", ("date", "open", "high", "low", "close", "volume",
                "split_coefficient")),
    ("data.load_fundamentals", "engine/data.py::load_fundamentals",
     "pilot_300/<T>/fundamentals.json", "<top>", ("financial_versions",)),
    ("ops_1029.sic_exempt", "engine/ops_1029.py::_sic_table",
     "pilot_300/<T>/fundamentals.json", "<top>", ("sic_versions",)),
    ("fundamentals._raw", "engine/fundamentals.py::_raw",
     "pilot_300/<T>/fundamentals.json", "financial_versions[*][]",
     ("value", "period_start", "period_end", "filing_date", "accepted_at",
      "filed_at")),
    ("share_gate._raw_points", "engine/share_gate.py::_raw_points",
     "pilot_300/<T>/fundamentals.json", "financial_versions[*][]",
     ("value", "period_start", "period_end", "accepted_at", "filed_at")),
    ("data.load_manifest", "engine/data.py::load_manifest",
     "pilot_300/manifest.csv", "<columns>",
     ("symbol", "name", "origin", "size_group", "sector", "delisted",
      "retirement_category", "data_path", "download_end_date")),
)


def _available_daily_fields(limit: int = 40) -> Counter:
    c: Counter = Counter()
    for s in _symbols()[:limit]:
        rows = (_load(s, "daily") or {}).get("data") or []
        for r in rows[:5]:
            c.update(r.keys())
    return c


def _available_fund_top(limit: int = 40) -> Counter:
    c: Counter = Counter()
    for s in _symbols()[:limit]:
        b = _load(s, "fundamentals")
        if b:
            c.update(b.keys())
    return c


def _available_fund_record(limit: int = 20) -> Counter:
    c: Counter = Counter()
    for s in _symbols()[:limit]:
        b = _load(s, "fundamentals") or {}
        for recs in (b.get("financial_versions") or {}).values():
            for r in (recs or [])[:3]:
                c.update(r.keys())
    return c


def _available_manifest_cols() -> list[str]:
    import csv
    p = os.path.join(PILOT, "manifest.csv")
    if not os.path.exists(p):
        return []
    with open(p, newline="", encoding="utf-8") as fh:
        return list(next(csv.reader(fh)))


def audit_loaders() -> dict:
    avail = {
        ("pilot_300/<T>/daily.json", "data[]"): sorted(_available_daily_fields()),
        ("pilot_300/<T>/fundamentals.json", "<top>"): sorted(_available_fund_top()),
        ("pilot_300/<T>/fundamentals.json", "financial_versions[*][]"):
            sorted(_available_fund_record()),
        ("pilot_300/manifest.csv", "<columns>"): _available_manifest_cols(),
    }
    rows = []
    for name, where, f, level, reads in LOADERS:
        a = avail.get((f, level), [])
        unread = [k for k in a if k not in reads]
        phantom = [k for k in reads if a and k not in a]
        rows.append({"loader": name, "code": where, "file": f, "level": level,
                     "reads": list(reads), "available": a,
                     "unread": unread, "declared_but_absent": phantom})
    return {"avail": avail, "rows": rows}


def _unread_field_usage(field: str) -> list[tuple[str, int, str]]:
    return [h for h in _grep(field) if not _is_self_reference(h[0])]


# ─────────────────────────────── 输出 ───────────────────────────────

def report_fundamental(field: str) -> list[str]:
    r = check_fundamental_field(field)
    n = r["n_symbols"]
    read_by = [h for h in r["code_hits"]]
    verdict = (
        "★★ 不许报「缺字段」—— 字段存在。只能报「覆盖不足」,并附上面的覆盖率。"
        if r["has_key"] else
        "✅ 字段确实不在原始文件里 —— 可以报「缺」,并把本段输出附在提单里。")
    if r["has_key"] and not read_by:
        verdict += "\n  ★★ 而且 engine 里没有任何代码读它 —— ★ 这是我方 bug,先改代码,不许发单。"
    lines = [
        SEP, f"【基本面字段】{field}", SEP,
        f"  原始文件        : pilot_300/<TICKER>/fundamentals.json"
        f" → financial_versions.{field}[]",
        f"  扫过的票        : {n} 只(其中 {r['no_file']} 只没有 fundamentals.json)",
        f"  ★ 键存在的票    : {r['has_key']}/{n} = {r['has_key']/max(1,n):.1%}",
        f"  ★ 有非空值的票  : {r['has_value']}/{n} = {r['has_value']/max(1,n):.1%}"
        f"(非空记录共 {r['n_records']} 条)",
        f"  SEC 原始 tag    : {r['source_tags'] or '(无)'}",
        f"  交付侧 status   : {r['delivery_status'] or '(该字段不在 coverage.additional_fields 里)'}",
        f"  交付侧缺失原因  : {r['missing_reasons'] or '(未给)'}",
        f"  派生公式        : {r['derived_formula'] or '(非派生字段)'}",
        f"  有值的样本      : {r['examples'] or '(无)'}",
        "",
        f"  ★ engine 里读它的位置({len(read_by)} 处):",
    ]
    for p, ln, txt in read_by[:12]:
        lines.append(f"      {p}:{ln}  {txt[:96]}")
    if len(read_by) > 12:
        lines.append(f"      … 另有 {len(read_by)-12} 处")
    if not read_by:
        lines.append("      ★★ 没有任何代码读它!")
    lines += ["", f"  判定:{verdict}", ""]
    return lines


def report_daily(field: str) -> list[str]:
    r = check_daily_field(field)
    n = r["n_symbols"]
    read_by = r["code_hits"]
    lines = [
        SEP, f"【日线字段】{field}", SEP,
        f"  原始文件          : pilot_300/<TICKER>/daily.json → data[].{field}",
        f"  扫过的票          : {n} 只 / 共 {r['n_bars']:,} 根 bar",
        f"  ★ 有该键的票      : {r['has_key_symbols']}/{n} = "
        f"{r['has_key_symbols']/max(1,n):.1%}"
        f"(bar 级 {r['n_bars_with_key']:,}/{r['n_bars']:,} = "
        f"{r['n_bars_with_key']/max(1,r['n_bars']):.1%})",
        f"  ★ 有非空值的票    : {r['nonnull_symbols']}/{n} = "
        f"{r['nonnull_symbols']/max(1,n):.1%}"
        f"(bar 级非空 {r['n_bars_nonnull']:,})",
    ]
    if field == "split_coefficient":
        lines.append(f"  ★ 出现过非 1 取值的票:{len(r['nontrivial_symbols'])} 只 "
                     f"{r['nontrivial_symbols']}")
    lines += ["", f"  ★ engine 里读它的位置({len(read_by)} 处):"]
    for p, ln, txt in read_by[:12]:
        lines.append(f"      {p}:{ln}  {txt[:96]}")
    if not read_by:
        lines.append("      ★★ 没有任何代码读它!")
    verdict = ("★★ 不许报「缺字段」—— 字段存在。" if r["has_key_symbols"]
               else "✅ 字段确实不在原始文件里 —— 可以报「缺」。")
    if r["has_key_symbols"] and not read_by:
        verdict += " ★★ 而且没有任何代码读它 —— ★ 这是我方 bug,先改代码,不许发单。"
    lines += ["", f"  判定:{verdict}", ""]
    return lines


def report_audit() -> list[str]:
    a = audit_loaders()
    lines = [SEP, "【loader 字段审计】原始文件里有、但我们没读的字段", SEP,
             "  ★ 这一节是为了找出「还有没有别的 load_daily」——",
             "    即 loader 只读了原始文件的一部分,而我们据此下了「数据里没有」的结论。",
             ""]
    total_unread = 0
    for row in a["rows"]:
        lines.append(f"  ◆ {row['loader']}   ({row['code']})")
        lines.append(f"      文件/层级 : {row['file']}  {row['level']}")
        lines.append(f"      实际读取  : {sorted(row['reads'])}")
        lines.append(f"      可用字段  : {len(row['available'])} 个")
        if row["declared_but_absent"]:
            lines.append(f"      ★ 声明读但文件里没有:{row['declared_but_absent']}")
        if row["unread"]:
            total_unread += len(row["unread"])
            lines.append(f"      ★★ 有但没读({len(row['unread'])} 个):")
            for k in row["unread"]:
                used = _unread_field_usage(k)
                where = (f"★ 别处有 {len(used)} 处提及,例:"
                         f"{used[0][0]}:{used[0][1]}" if used
                         else "★ 全仓库没有任何代码碰过")
                lines.append(f"          {k:46s} {where}")
        else:
            lines.append("      ✅ 可用字段全部读到了")
        lines.append("")
    lines += [f"  ★★ 合计「有但没读」的字段 {total_unread} 个 —— "
              f"★ 在对技术方报任何「缺数据」之前,先确认不在这张表里。", ""]
    return lines


DEFAULT_FUND = ("LongTermDebt", "EBIT", "DebtCurrent", "LongTermDebtCurrent",
                "Liabilities", "OperatingCashFlow")
DEFAULT_DAILY = ("split_coefficient",)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="对技术方报「缺字段」之前的强制检查")
    ap.add_argument("fields", nargs="*", help="要查的基本面字段名")
    ap.add_argument("--daily", nargs="*", default=[], help="要查的日线字段名")
    ap.add_argument("--audit-loaders", action="store_true",
                    help="审计所有 loader:原始文件里有但没读的字段")
    ap.add_argument("--all", action="store_true", help="默认字段 + loader 审计")
    a = ap.parse_args(argv)

    fund = list(a.fields)
    daily = list(a.daily)
    audit = a.audit_loaders
    if a.all or (not fund and not daily and not audit):
        fund = fund or list(DEFAULT_FUND)
        daily = daily or list(DEFAULT_DAILY)
        audit = True

    out: list[str] = [
        SEP,
        "★★ 提单强制检查(evidence_precheck)",
        SEP,
        "纪律:凡要对技术方报「缺字段 / 数据有问题」,必须先跑这个脚本,",
        "      并把输出原样附在提单里。★ 跑不过不准发单。",
        "判定:字段存在 → 不许报「缺」,只能报「覆盖不足」并给覆盖率;",
        "      字段存在但没代码读 → ★ 我方 bug,先改代码;",
        "      字段真不在文件里 → 才可以报「缺」。",
        "",
    ]
    for f in fund:
        out += report_fundamental(f)
    for f in daily:
        out += report_daily(f)
    if audit:
        out += report_audit()
    print("\n".join(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
