#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""第三道卡口 · 出处 grep 对账

★ 这一道不检查「source 这一栏填了没有」,检查「这个数在方法卡原文里 grep 得到吗」。

为什么需要这一道
────────────────
旧的归属检查只验 source 字段非空。实测它自己的测试里:
  source 写「原著(编的)」/「x」/「随便写点什么」—— ★ 全部通过检查。
而我们已经人工抓到 5 处归属错(我们自己填的值标成了原著)。
机械检查抓不到归属错,因为归属错的字段是**填满的**,只是填的内容是假的。

怎么做
──────
对每一个声称 source=原著 的数值,去方法卡原文(handbook/v11.txt)里找。
★★★ 关键:**不全文 grep,只在这一条策略自己那一段里 grep。**
   原文 187KB,小整数(2/3/5/20/50)全文随便都能命中 —— 全文 grep 等于没查。

输出三桶
────────
  找得到            —— 出处站得住
  ★ 找不到          —— **强制改标「我们填的」**
  ★★ 判不了(小整数) —— 这一道对小整数本来就没有分辨力,如实标出来,不假装查过

★★★ 这一道卡口自己的局限(必须一起报出去,不许藏)
   1. 小整数(默认 |x| < 10 且为整数)在一段几百字的文本里命中率天然很高
      → 命中**不等于**出处为真。这类一律进第三桶「判不了」,不计入「找得到」。
   2. 原文里的数可能以别的写法出现(八 / 8% / 0.08 / 8倍)。
      本脚本做了常见几种折算,但**折算不全**;所以「找不到」是**疑似**,不是定罪。
   3. 本脚本只判数值,不判文字判据。文字判据的归属仍然只能靠人读。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

import yaml

# ── 方法卡原文 ──────────────────────────────────────────────────────────
DEFAULT_CORPUS = Path("/home/claude/handbook/v11.txt")

# 一条策略一段的分段标记,例:「技-1 · 系统化趋势跟随   理查德·丹尼斯」
SECTION_RE = re.compile(r"^((?:技|基|套|配|模|状)-\d+)\s*[·‧]", re.MULTILINE)

# source 里出现这些词 → 声称是原著
CLAIMS_ORIG = ("原著", "原文", "原版")
# 但出现这些词 → 其实是在声明「不是原著」,不该被当成原著声称
DISCLAIMS = ("非原著", "不是原著", "原著没有", "原著未", "我们", "行业", "惯例", "编的")

SMALL_INT_CUTOFF = 10  # |x| < 10 且为整数 → 进「判不了」桶


def split_sections(corpus_text: str) -> dict[str, str]:
    """把原文切成 {策略号: 那一段文字}。"""
    marks = list(SECTION_RE.finditer(corpus_text))
    out: dict[str, str] = {}
    for i, m in enumerate(marks):
        end = marks[i + 1].start() if i + 1 < len(marks) else len(corpus_text)
        sid = m.group(1)
        # 同一个号可能出现多次(正文 + 附录),全部拼起来
        out[sid] = out.get(sid, "") + corpus_text[m.start():end]
    return out


def claims_original(src: object) -> bool:
    if not isinstance(src, str):
        return False
    if any(d in src for d in DISCLAIMS):
        return False
    return any(c in src for c in CLAIMS_ORIG)


def number_variants(x: float) -> list[str]:
    """一个数在原文里可能的几种写法。★ 折算不全,这是本脚本已知的局限之一。"""
    v: list[str] = []
    if float(x).is_integer():
        v.append(str(int(x)))
    else:
        s = ("%f" % x).rstrip("0").rstrip(".")
        v.append(s)
        v.append(s.lstrip("0") if s.startswith("0.") else s)  # .08
    # 百分数互换:0.08 ↔ 8% / 8
    if 0 < abs(x) < 1:
        pct = x * 100
        if abs(pct - round(pct)) < 1e-9:
            v += [f"{int(round(pct))}%", str(int(round(pct)))]
    elif float(x).is_integer() and 1 <= abs(x) <= 100:
        v.append(f"{int(x)}%")
        frac = ("%f" % (x / 100)).rstrip("0").rstrip(".")
        v.append(frac)
    return sorted(set(v), key=len, reverse=True)


def walk(node: object, path: str, inherited_src: object, out: list[dict]) -> None:
    """走配置树。一个 dict 里的 source 管这个 dict 里的标量。"""
    if isinstance(node, dict):
        src = node.get("source", inherited_src)
        for k, val in node.items():
            if k == "source":
                continue
            p = f"{path}.{k}" if path else k
            if isinstance(val, bool):
                continue
            if isinstance(val, (int, float)):
                out.append({"path": p, "value": val, "source": src})
            else:
                walk(val, p, src, out)
    elif isinstance(node, list):
        for i, val in enumerate(node):
            walk(val, f"{path}[{i}]", inherited_src, out)


def infer_ids(cfg: dict, text: str) -> list[str]:
    """这份配置对应原文里哪几段。"""
    ids = set()
    for key in ("method_id", "id", "handbook_id", "method"):
        v = cfg.get(key)
        if isinstance(v, str):
            ids.update(re.findall(r"(?:技|基|套|配|模|状)-\d+", v))
    ids.update(re.findall(r"(?:技|基|套|配|模|状)-\d+", text[:4000]))
    return sorted(ids)


def audit_file(p: Path, sections: dict[str, str]) -> dict:
    raw = p.read_text(encoding="utf-8", errors="replace")
    try:
        cfg = yaml.safe_load(raw)
    except Exception as e:  # 配置坏了是另一道闸的事,这里只记下
        return {"file": str(p), "error": f"yaml 解析失败: {e}"}
    if not isinstance(cfg, dict):
        return {"file": str(p), "error": "顶层不是 dict"}

    prov = cfg.get("provenance") or {}
    if prov.get("composite") and not prov.get("per_rule_cards_filled"):
        # ★ 合成流派且未逐条登记来源卡 → 单独一桶,不混进「找不到」
        items_c: list[dict] = []
        walk(cfg, "", None, items_c)
        claimed_c = [it for it in items_c if claims_original(it["source"])]
        for it in claimed_c:
            it["why"] = "合成流派,未逐条登记来源方法卡 → 无法对账"
        return {"file": str(p), "ids": [], "section_found": False,
                "composite_unregistered": True,
                "claimed_original": len(claimed_c), "found": [], "missing": [],
                "undecidable": [], "unmappable": claimed_c}

    ids = infer_ids(cfg, raw)
    corpus = "\n".join(sections.get(i, "") for i in ids)

    items: list[dict] = []
    walk(cfg, "", None, items)
    claimed = [it for it in items if claims_original(it["source"])]

    found, missing, undecidable, unmappable = [], [], [], []
    for it in claimed:
        x = it["value"]
        # ★★★ 先分「查不了」:配置没标方法卡编号 → 根本无法对账,不是归属错
        if not corpus:
            it["why"] = (f"推出了号 {ids} 但原文里没有这几段"
                         if ids else "配置里没写它对应方法卡哪一条")
            unmappable.append(it)
            continue
        if float(x).is_integer() and abs(x) < SMALL_INT_CUTOFF:
            undecidable.append(it)
            continue
        hit = next((v for v in number_variants(x) if v in corpus), None)
        if hit:
            it["hit_as"] = hit
            found.append(it)
        else:
            it["why"] = "本段原文里 grep 不到这个数"
            missing.append(it)

    return {
        "file": str(p),
        "ids": ids,
        "section_found": bool(corpus),
        "claimed_original": len(claimed),
        "found": found,
        "missing": missing,
        "undecidable": undecidable,
        "unmappable": unmappable,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="出处 grep 对账(第三道卡口)")
    ap.add_argument("configs", nargs="*", help="配置文件或目录;默认 engine/configs")
    ap.add_argument("--corpus", default=str(DEFAULT_CORPUS), help="方法卡原文")
    ap.add_argument("--json-out", help="结果写到这个文件")
    args = ap.parse_args()

    corpus_path = Path(args.corpus)
    if not corpus_path.exists():
        print(f"✗ 找不到方法卡原文:{corpus_path}", file=sys.stderr)
        print("  ★ 这一道卡口没有原文就无法运行 —— 不要让它静默通过。", file=sys.stderr)
        return 2
    sections = split_sections(corpus_path.read_text(encoding="utf-8", errors="replace"))

    targets = [Path(a) for a in args.configs] or [Path("engine/configs")]
    files: list[Path] = []
    for t in targets:
        files.extend(sorted(t.rglob("*.yaml")) if t.is_dir() else [t])
    files = [f for f in files if not f.name.startswith("_TEMPLATE")]

    reports = [audit_file(f, sections) for f in files]
    ok = [r for r in reports if "error" not in r]

    n_claim = sum(r["claimed_original"] for r in ok)
    n_found = sum(len(r["found"]) for r in ok)
    n_miss = sum(len(r["missing"]) for r in ok)
    n_und = sum(len(r["undecidable"]) for r in ok)
    n_unmap = sum(len(r["unmappable"]) for r in ok)
    n_nomap_files = sum(1 for r in ok if not r["section_found"])
    n_comp = sum(1 for r in ok if r.get("composite_unregistered"))

    print("=" * 72)
    print("第三道卡口 · 出处 grep 对账")
    print("=" * 72)
    print(f"原文分段:{len(sections)} 段   配置:{len(files)} 份"
          f"({len(files) - len(ok)} 份解析失败)")
    print(f"声称 source=原著 的数值:{n_claim}")
    print(f"  找得到              {n_found}")
    print(f"  ★ 找不到            {n_miss}   ← 强制改标「我们填的」")
    print(f"  ★★ 判不了(小整数)   {n_und}   ← 这一道对小整数没有分辨力,不计入找得到")
    print(f"  ★★★ 查不了          {n_unmap}   ← **配置没标方法卡编号,根本无法对账**")
    print()
    if n_unmap:
        print("─" * 72)
        print("★★★ 「查不了」是这一轮最大的一桶 —— 而它本身就是一个结论")
        print("─" * 72)
        print(f"  其中 {n_comp} 份是**我们自己合成的「流派」** —— ★ 它们不对应单一方法卡,")
        print("  所以不是「漏填 method_id」,给它们补一个 method_id 本身就是错的修法。")
        print("  ★★★ 正确修法:在 provenance 里逐条登记 ——")
        print("     method_cards: 这一份借用了哪几张卡;")
        print("     per_rule_cards_filled: 每条 source:原著 是否已指明来自哪张卡。")
        print("  ★ 在填完之前,这些配置里的「原著」**一律不算已核实**。")
        print(f"  (另有 {n_nomap_files - n_comp} 份是真的推不出策略号。)")
        print()

    if n_miss:
        print("─" * 72)
        print("★ 找不到的(疑似归属错,逐条要人判)")
        print("─" * 72)
        for r in ok:
            if not r["missing"]:
                continue
            print(f"\n{r['file']}  段落:{r['ids'] or '推不出'}")
            for it in r["missing"]:
                print(f"    {it['path']} = {it['value']}")
                print(f"      source: {it['source']}")
                print(f"      ★ {it['why']}")

    print()
    print("─" * 72)
    print("★★★ 这一道卡口自己的局限(不许藏)")
    print("─" * 72)
    print("  1. 小整数在一段几百字里命中率天然很高 → 命中不等于出处为真,")
    print("     所以小整数一律进「判不了」桶,不计入「找得到」。")
    print("  2. 数在原文里可能是别的写法(八 / 8% / 0.08 / 8倍),本脚本折算不全,")
    print("     ★ 所以「找不到」是**疑似**,不是定罪 —— 每条仍要人看一眼。")
    print("  3. 只判数值,不判文字判据。文字判据的归属仍然只能靠人读。")
    print("  4. ★★★ 配置没有 method_id 的,这一道**完全无能为力** —— 进「查不了」桶。")

    if args.json_out:
        Path(args.json_out).write_text(
            json.dumps({"summary": {"claimed": n_claim, "found": n_found,
                                    "missing": n_miss, "undecidable": n_und,
                                    "unmappable": n_unmap,
                                    "files_without_method_id": n_nomap_files},
                        "reports": reports}, ensure_ascii=False, indent=2),
            encoding="utf-8")
        print(f"\n结果写到 {args.json_out}")

    # ★ 这一道不 fail 跑批 —— 它产出的是「要人判的清单」,不是自动判决
    return 0


if __name__ == "__main__":
    sys.exit(main())
