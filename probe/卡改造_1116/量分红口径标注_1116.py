# -*- coding: utf-8 -*-
"""量「成绩节有没有标分红口径」—— 只读，不改任何文件。
背景：Lin 2026-11-16 拍板「分红口径统一成两侧都含分红，旧跑批全部重出」。
问题：卡里的成绩数全是老口径（不含分红），卡里有没有任何地方说这件事？
规矩(80)① 先报分母。规矩(74) 先量再改。
"""
import os, re, json, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
PKG = os.path.join(ROOT, "skills_v2")

# 口径标注词：卡里只要出现其中之一，就算「说了分红这件事」
DIV_WORDS = ["含分红", "不含分红", "含股息", "除息", "分红口径", "再投"]
# 成绩数字的特征词（给用户看的四样 + 内部三把尺子）
NUM_WORDS = ["笔数", "利润因子", "胜率", "平均持有", "年化", "卡玛", "最大回撤", "往下亏掉"]
# 对标侧「全收益」的说法 —— 它暗示两侧同口径，而实际策略侧不含分红
TR_WORDS = ["全收益"]

all_md, cards = [], set()
for dp, dn, fn in os.walk(PKG):
    for f in fn:
        if f.endswith(".md"):
            p = os.path.join(dp, f)
            all_md.append(p)
            rel = os.path.relpath(p, PKG)
            top = rel.split(os.sep)[0]
            if top.endswith(".md"):
                continue
            cards.add(top)

entries = [p for p in all_md if os.sep + "entries" + os.sep in p]

def read(p):
    with open(p, encoding="utf-8") as fh:
        return fh.read()

has_section, with_nums, with_div, with_tr, tr_no_div = [], [], [], [], []
for p in entries:
    t = read(p)
    if "XING 实测成绩" not in t:
        continue
    has_section.append(p)
    sec = t[t.index("XING 实测成绩"):]
    n = any(w in sec for w in NUM_WORDS)
    d = any(w in t for w in DIV_WORDS)
    r = any(w in t for w in TR_WORDS)
    if n: with_nums.append(p)
    if d: with_div.append(p)
    if r: with_tr.append(p)
    if r and not d and n: tr_no_div.append(p)

# 全仓（490 个 .md，含共用边界/SKILL.md/手册类）有没有一处提分红
pkg_div = [p for p in all_md if any(w in read(p) for w in DIV_WORDS)]

out = {
    "分母": {
        "skills_v2 下 .md 总数": len(all_md),
        "卡（顶层目录）": len(cards),
        "entries 文件": len(entries),
    },
    "有成绩节的 entries": len(has_section),
    "成绩节里有数字的": len(with_nums),
    "🔴 成绩数有、分红口径一个字没说的": len(with_nums) - len([p for p in with_nums if p in with_div]),
    "整份文件提到分红口径的 entries": len(with_div),
    "说了对标是「全收益」的 entries": len(with_tr),
    "🔴 说了对标全收益 + 自己有数 + 不说分红（暗示同口径）": len(tr_no_div),
    "全包 490 个 .md 里提分红口径的文件数": len(pkg_div),
    "全包提分红的文件清单": [os.path.relpath(p, ROOT) for p in pkg_div][:20],
}
print(json.dumps(out, ensure_ascii=False, indent=2))
