# -*- coding: utf-8 -*-
"""★★★★★ 只量不改 —— 6.12 最后一行「失效位」那条**换查法**量一遍（台账 1115 第十一轮 五节②）。

★★★ 为什么要换查法：6.12 表里其余 11 行都是「不许出现」→ grep 禁词就够（规矩78 宽口径）。
   ★★ 「失效位」是**保留词**，它要求的是：**第一次出现必须跟一句**
      「跌破它，当初做这笔的理由就不在了」。
   ★★★ 所以规矩(78) 那把尺子**管不到它** —— 它查的不是「出现没出现」，
      是「第一次出现**后面 N 行**有没有那句解释」。

★★★ 规矩(74)：先量三个数，一个字节不写进卡。★★ 宽口径先捞，再按 6.12 自己的范围说明人核。
★★ 规矩(78)：位置要分类打印（裸正文 / 表格单元格 / 箱体 / 表头 / 引号 / frontmatter），
   ★★★ 不许只认引号——1115 两轮已经证实窄口径看不见表格和箱体。
"""
from __future__ import annotations
import os, re, json, sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
包 = os.path.join(ROOT, os.environ.get("XING_CARDS", "skills_v2"))
词 = "失效位"
窗 = int(os.environ.get("XING_WIN_LINES", "6"))          # ★ 往后看几行
窗前 = int(os.environ.get("XING_WIN_BACK", "3"))         # ★★★ 往**前**看几行
# ★★★★★ 为什么要往前看（1115 第十二轮当场抓到的尺子窟窿）：
#   ★ 第一版只看后面 N 行 → `xing-quote/SKILL.md:71` 那句
#     「证伪线 170.31 20 日低点 —— 跌破它这条逻辑整条作废」**就在 失效位 那行的上一行**，
#   ★★ 第一版一处都没报 → 和规矩(78) 是同一类错：**口径窄了，数就只是下限**。
读 = lambda p: open(p, encoding="utf-8").read()

# ★★★ 要求的那句解释：按**语义骨架**配，不是整句字面
#   骨架 = 「跌破/破了它」+「(当初做)这笔的理由/原因」+「不在了/不成立」
严 = re.compile(r"跌破[^\n]{0,12}(当初)?[^\n]{0,8}(做这笔|这笔|这单|买它|买入)[^\n]{0,8}(理由|原因)[^\n]{0,8}(就)?(不在|不成立|没了)")
# ★★ 宽一档：允许换词（走坏 / 不算数 / 看错了）—— ★★★ 宽口径只做候选，必须人核
宽 = re.compile(r"(跌破|破了|破掉|失效)[^\n]{0,20}(理由|原因|逻辑|判断|看法|想法)[^\n]{0,14}"
                r"(不在|不成立|没了|不对|错了|作废|取消)"
                r"|(理由|原因|逻辑)[^\n]{0,14}(不在了|不成立了|没了)")

def 位置(行: str, 上一行: str) -> str:
    s = 行.strip()
    if s.startswith("|"):
        return "表头" if set(上一行.strip().strip("|").replace("|", "")) <= set("-: ") or \
                        re.match(r"^\|[\s:\-|]+\|?$", 上一行.strip()) else "表格单元格"
    if s.startswith("│") or s.startswith("┌") or s.startswith("└"):
        return "箱体"
    if re.search(r"[「“\"][^「」“”\"]*" + 词, 行):
        return "引号"
    return "裸正文"

# ★★★★★ 人核表（1115 第十二轮 · 规矩74「先量再改」的「核」那一半）
# ★★ 为什么必须手钉：6.12 自己写了范围说明 —— 「管**面向用户的输出措辞**，不管卡里内部判据的写法」。
#   ★★★ 机器按文件顺序取的「第一次出现」**不等于**用户第一次看见它
#   （★ xing-main 第一处是路由表、xing-quote 第一处是 frontmatter、技术面第一处是内部能力表）。
# ★★ 归类口径照抄《197》四节那 8 类「刻意不改」。★ 键 = (文件, 原文片段)，★★★ 片段配不上就当没核过→报错。
内部 = [
    ("xing-main/SKILL.md", "持仓页", "路由/场景表（《197》路由块）"),
    ("xing-quote/SKILL.md", "description:", "frontmatter 路由元信息，不上界面"),
    ("xing-quote/SKILL.md", "单只票的状态、关键位", "「这个 Skill 管什么」内部小节"),
    ("xing-quote/SKILL.md", "① **失效位必须说清", "自检条/禁令本身（《197》禁令本身）"),
    ("xing-quote/SKILL.md", "**三、失效位必须说清", "禁令本身"),
    ("xing-review/SKILL.md", "技术面复检", "内部判据表（第 1 问→用哪一面）"),
    ("xing-review/SKILL.md", "（现价 - 失效位）÷", "内部口径格（怎么算）"),
    ("xing-review/SKILL.md", "为什么要用该股自身波动换算", "内部口径格（为什么）"),
    ("xing-review/SKILL.md", "| **v2** |", "版本历史表（《197》版本历史）"),
    ("xing-technical-analyst/SKILL.md", "**C 失效位**", "内部能力清单表（《197》内部能力清单）"),
    ("xing-technical-analyst/references/layers.md", "", "层规格 = 内部判据，6.12 明文不管"),
]
def 是内部(h):
    for f, frag, why in 内部:
        if h["文件"] == f and (frag == "" or frag in h["原文"]):
            return why
    return None

卡 = sorted(d for d in os.listdir(包)
            if os.path.isdir(os.path.join(包, d))
            and os.path.exists(os.path.join(包, d, "SKILL.md")))

全命中, 结果 = [], []
for c in 卡:
    根 = os.path.join(包, c)
    文件 = []
    for dp, _, fns in os.walk(根):
        for fn in sorted(fns):
            if fn.endswith(".md") and fn != "common_boundaries.md":   # ★ 边界本体是禁词表自己
                文件.append(os.path.join(dp, fn))
    # ★★ SKILL.md 排最前（用户先看到它），其余按路径
    文件.sort(key=lambda p: (0 if os.path.basename(p) == "SKILL.md" and os.path.dirname(p) == 根 else 1, p))
    命中 = []
    for p in 文件:
        行s = 读(p).splitlines()
        在frontmatter = False
        for i, 行 in enumerate(行s):
            if i == 0 and 行.strip() == "---":
                在frontmatter = True; continue
            if 在frontmatter and 行.strip() == "---":
                在frontmatter = False; continue
            if 词 not in 行:
                continue
            loc = "frontmatter" if 在frontmatter else 位置(行, 行s[i-1] if i else "")
            尾 = "\n".join(行s[i:i+1+窗])
            头文 = "\n".join(行s[max(0, i-窗前):i])
            命中.append(dict(文件=os.path.relpath(p, 包), 行号=i+1, 位置=loc,
                             原文=行.strip()[:120],
                             严=bool(严.search(尾)), 宽=bool(宽.search(尾)),
                             严前=bool(严.search(头文)), 宽前=bool(宽.search(头文))))
    for h in 命中:
        h["内部"] = 是内部(h)
    全命中 += [dict(卡=c, **h) for h in 命中]
    面向用户 = [h for h in 命中 if not h["内部"]]
    if 命中:
        头 = 面向用户[0] if 面向用户 else 命中[0]
        结果.append(dict(卡=c, 命中数=len(命中), 面向用户数=len(面向用户), 第一次=头,
                         判=("⚪ 本卡没有面向用户的出现（全是内部写法）" if not 面向用户 else
                            "✅ 严格句就在近旁" if (头["严"] or 头["严前"]) else
                            ("🟡 只匹到宽口径（" + ("前" if 头["宽前"] else "后") + "），要人核"
                             if (头["宽"] or 头["宽前"]) else "🔴 第一次出现前后都没有解释"))))

print(f"★ N1 卡数 = {len(卡)}")
print(f"★ N2 用到「{词}」的卡 = {len(结果)}  （命中总数 {len(全命中)} 处 · 窗口 {窗} 行）")
print(f"★ N2b 其中**面向用户**的出现 = {sum(r['面向用户数'] for r in 结果)} 处"
      f"（内部写法 {sum(1 for h in 全命中 if h['内部'])} 处，6.12 明文不管）")
print(f"★ N3 **面向用户第一次**出现没跟解释的卡 = {sum(1 for r in 结果 if r['判'].startswith('🔴'))}")
print("\n=== 位置分类（宽口径，规矩78 要求）===")
分 = {}
for h in 全命中:
    分[h["位置"]] = 分.get(h["位置"], 0) + 1
for k, v in sorted(分.items(), key=lambda kv: -kv[1]):
    print(f"  {k}: {v}")
print(f"\n=== 解释句命中（{窗前} 行前 / {窗} 行后两侧都看）===")
print(f"  严格句（后）{sum(1 for h in 全命中 if h['严'])} · 严格句（前）{sum(1 for h in 全命中 if h['严前'])}")
print(f"  宽口径（后）{sum(1 for h in 全命中 if h['宽'])} · 宽口径（前）{sum(1 for h in 全命中 if h['宽前'])}")
print("★★★ 全仓找一遍解释句本身（不限窗口）：")
import glob as _g
_n严 = _n宽 = 0
for _p in _g.glob(os.path.join(包, "*", "**", "*.md"), recursive=True):
    if os.path.basename(_p) == "common_boundaries.md":
        continue
    _t = 读(_p)
    _a, _b = len(严.findall(_t)), len(宽.findall(_t))
    _n严 += _a; _n宽 += _b
    if _b:
        print(f"    {os.path.relpath(_p, 包)}  严 {_a} · 宽 {_b}")
print(f"  合计 严 {_n严} · 宽 {_n宽}")
print("\n=== 逐卡 ===")
for r in 结果:
    h = r["第一次"]
    print(f"\n【{r['卡']}】{r['判']}  （本卡 {r['命中数']} 处）")
    print(f"   面向用户第一次 → {h['文件']}:{h['行号']}  [{h['位置']}]"
          + (f"  (内部 {r['命中数']-r['面向用户数']} 处已排除)" if r['命中数']>r['面向用户数'] else ""))
    print(f"   原文: {h['原文']}")
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "量失效位解释_1115.json")
json.dump(dict(卡数=len(卡), 窗口行=窗, 结果=结果, 全命中=全命中),
          open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"\n★ 落盘 {out}")
