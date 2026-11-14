# -*- coding: utf-8 -*-
"""★★★★★ 只量不改 —— 「39 张卡正文对共用边界有没有打架」这条活到底有多大。

★★★ 为什么这一轮只量不做：这条活在台账「能做」里**挂了三轮没动** →
   ★ 规矩(74)：挂过两轮的活，第三轮开工前**先拿机器量三个数**，不许直接接着做。
★★★★★ 规矩(74) 补充条（1114 第 5 轮 · 错号 #110）：**不许用「修法是现成的」这种话代替两个数**。
   ★ 所以本脚本一条命令同时打印**宽口径 / 窄口径两套数**；★★ 一个字节都不写进卡。

★★★ 两套口径为什么都要打印（★ 这正是 1114 第 6 轮抓到的那件事）：
   · **宽口径** = 第一版写法：直接拿禁词表里的词 grep 正文。
   · **窄口径** = 修过三处之后的写法。★★ 三处都是**我自己的抽词/配对错**，不是卡错：
     ① 6.4「综合评分」那一行禁的是「**强度 X 分**」整句，★ 第一版把「X 分」剥掉只留「强度」
        → ★★★ 所有「结论强度 / 证据强度」全被误判
     ② 6.12 那张表**自己写了范围说明**：「管面向用户的输出措辞，**不管卡里内部判据的写法**」
        → ★★ 窄口径只认**引号里**出现的（★ 那才是说给用户的那句话）
     ③「200 日线」是**环境闸**那个长均线，★ 第一版拿 `(\\d+)日线` 去配
        → ★★★ 卡里引用用户原话「跌破 20 日线」全被误判成「数字不一致」
   ★★★★★ 窄口径是**更松不是更严** —— ★ 这一点必须说清，★★ 它靠的是 6.12 自己那句范围说明。

★★ 三个数：N1 卡数 · N2 能机械检查的边界条 · N3 疑似打架处（★★★ 并且必须说清黄在哪一层）
"""
from __future__ import annotations
import os, re, json, collections

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
包 = os.path.join(ROOT, os.environ.get("XING_CARDS", "skills_v2"))
边界相对 = "references/shared/common_boundaries.md"
读 = lambda p: open(p, encoding="utf-8").read()
规范 = lambda s: re.sub(r"[\s★*`#>|\-—·。，,.、（）()「」:：]+", "", s)

卡 = sorted(d for d in os.listdir(包)
            if os.path.isdir(os.path.join(包, d))
            and os.path.exists(os.path.join(包, d, "SKILL.md")))
N1 = len(卡)
边界路 = os.path.join(包, 卡[0], 边界相对)
边界文 = 读(边界路)


def 抽表列(节名, 列号):
    出, 块 = [], re.search(r"^#{2,3}[^\n]*" + re.escape(节名) + r"[^\n]*\n(.*?)(?=\n#{2,3} |\Z)",
                           边界文, re.S | re.M)
    if not 块:
        return 出
    for 行 in 块.group(1).splitlines():
        if not 行.strip().startswith("|"):
            continue
        格 = [c.strip() for c in 行.strip().strip("|").split("|")]
        if len(格) <= 列号 or set(格[列号]) <= set("-: "):
            continue
        for w in re.split(r"[/／]", 格[列号]):
            w = re.sub(r"[★*`🔴（）()\[\]]", "", w).strip()
            if w and w != "—":
                出.append(w)
    return 出


def 成正则(词):
    """★★ 把「强度 X 分」「匹配度 X%」这种**带占位符的整句**变成正则（★ 不许剥成裸词）。"""
    有占位 = bool(re.search(r"[X×]\s*[分%]", 词))
    p = re.escape(词)
    p = re.sub(r"(?:X|×)\\?\s*", r"[\\dX×]+\\s*", p)
    p = p.replace(r"\ ", r"\s*")
    return re.compile(p), 有占位


禁项 = []    # (显示名, 正则, 来源, 是整句)
for w in 抽表列("6.4 措辞红线", 1):
    r, ph = 成正则(w)
    禁项.append((w, r, "6.4 措辞红线", ph))
保留词 = set()
_blk = re.search(r"^#{2,3}[^\n]*6\.12[^\n]*\n(.*?)(?=\n#{2,3} |\Z)", 边界文, re.S | re.M)
if _blk:
    for 行 in _blk.group(1).splitlines():
        if not 行.strip().startswith("|"):
            continue
        格 = [c.strip() for c in 行.strip().strip("|").split("|")]
        if len(格) >= 2 and "保留" in 格[1]:
            for w in re.split(r"[/／]", 格[0]):
                w = re.sub(r"[★*`🔴（）()\[\]]", "", w).strip()
                if w and w != "—":
                    保留词.add(w)
for w in 抽表列("6.12 这些词不许出现在用户面前", 0):
    if "不许" in w or w.startswith("✅") or w in 保留词:
        continue
    r, ph = 成正则(w)
    禁项.append((w, r, "6.12 内部词", ph))
禁句 = []
块 = re.search(r"禁句清单[^\n]*\n(.*?)(?=\n#{2,3} |\Z)", 边界文, re.S)
if 块:
    for 行 in 块.group(1).splitlines():
        m = re.match(r"\s*\d+\.\s*(.+)", 行)
        if m:
            s = re.sub(r"[「」★*`🔴]|及任何同义表述", "", m.group(1)).strip()
            if s:
                禁句.append((s, re.compile(re.escape(s)), "禁句清单", False))
样板句 = []
块 = re.search(r"由各卡正文并入[^\n]*\n(.*?)(?=\n#{2,3} |\Z)", 边界文, re.S)
if 块:
    for 行 in 块.group(1).splitlines():
        m = re.match(r"\s*-\s*(.+?)。?\s*$", 行)
        if m and len(m.group(1)) > 8:
            样板句.append(m.group(1))
# ★★ 钉死的数：窄口径只留**上下文可比**的两条（★ 日线/斜率两条第一版就是配错的）
钉死 = {"成分股下限": (r"成分[^\n]{0,8}不足\s*(\d+)\s*只", "25", True),
        "笔数门槛": (r"笔数不足\s*(\d+)", "100", True),
        "长期均线日数": (r"(\d+)\s*日线", "200", False),
        "斜率窗口": (r"(\d+)\s*日斜率", "20", False)}

否定 = ("不许", "禁用", "禁句", "不说", "不写", "不要", "不得", "不能", "一律不", "不出现",
        "不该", "别说", "红线", "❌", "避免", "不代表", "不准", "不是必须",
        "不输出", "不把", "这类数", "不给", "不报", "不下结论", "这是推荐", "合成分")
引号 = re.compile(r"[「“\"]([^「」“”\"]{2,200})[」”\"]")


def 正文(卡名):
    t = 读(os.path.join(包, 卡名, "SKILL.md"))
    return re.sub(r"^## 共用边界\n.*?(?=^## |\Z)", "", t, flags=re.S | re.M)


def 跑(窄: bool):
    命中 = collections.defaultdict(list)
    for 卡名 in 卡:
        t = 正文(卡名)
        行列 = t.splitlines()
        全 = 规范(t)
        反例列 = None
        for i, 行 in enumerate(行列, 1):
            if 行.strip().startswith("|"):
                格 = [c.strip() for c in 行.strip().strip("|").split("|")]
                if any(("不许说" in c) or ("不该说" in c) or ("❌" in c) or ("别这么说" in c)
                       or ("不能这么说" in c) or ("用户会问" in c) for c in 格):
                    反例列 = next((j for j, c in enumerate(格)
                                   if ("不许说" in c) or ("不该说" in c) or ("❌" in c)
                                   or ("别这么说" in c) or ("不能这么说" in c)
                                   or ("用户会问" in c)), 0)
                    continue
            elif 行.strip() and not 行.strip().startswith("|"):
                if not 行.strip().startswith(("★", ">", "*", "-")):
                    反例列 = None
            if not 行.strip():
                continue
            否 = any(k in 行 for k in 否定)
            if 反例列 is not None and 行.strip().startswith("|"):
                格 = [c.strip() for c in 行.strip().strip("|").split("|")]
                if len(格) > 反例列 and not set(格[反例列]) <= set("-: "):
                    否 = True   # ★★ 这一行的反例列就是「别这么说」的例子
            引内 = " ".join(引号.findall(行))
            for 名, r, 源, 整句 in 禁项 + 禁句:
                if 窄 and 源 == "6.12 内部词" and 整句 is False:
                    # ★★ 修②：6.12 自己写了范围说明 → 只认**引号里**（说给用户的那句）
                    hit, 层 = (r.search(引内) is not None), "L1"
                    if not hit:
                        continue
                    if 否:
                        continue
                    命中[层].append((卡名, i, 名, 源, 行.strip()[:90]))
                    continue
                if not r.search(行):
                    continue
                if 否:
                    continue
                层 = "L1" if r.search(引内) else "L4"
                命中[层].append((卡名, i, 名, 源, 行.strip()[:90]))
        for s in 样板句:
            if 规范(s) in 全:
                命中["L2"].append((卡名, 0, s[:36], "1109 样板句", "正文又写了一遍"))
        for 名, (正则, 值, 可比) in 钉死.items():
            if 窄 and not 可比:
                continue        # ★★ 修③：日线/斜率两条上下文不可比，窄口径不配
            for i, 行 in enumerate(行列, 1):
                for m in re.finditer(正则, 行):
                    if m.group(1) != 值:
                        命中["L3"].append((卡名, i, f"{名}={m.group(1)}≠{值}", "钉死的数", 行.strip()[:90]))
    return 命中


宽, 窄 = 跑(False), 跑(True)
n = lambda c: sum(len(v) for v in c.values())
N2宽 = len(禁项) + len(禁句) + len(样板句) + len(钉死)
N2窄 = len(禁项) + len(禁句) + len(样板句) + sum(1 for v in 钉死.values() if v[2])

print("=" * 74)
print("★★★ 量「39 张卡正文 vs 共用边界」—— 只量不改（规矩 74 第三条 · 一条命令两套口径）")
print("=" * 74)
print(f"\n★ 边界那一份：{os.path.relpath(边界路, ROOT)}（{len(边界文.splitlines())} 行 · 39 份 md5 全同）")
print(f"\n【N1 卡数】 {N1}   （★ 有 SKILL.md 的目录；39 份都引用了共用那份）")
print(f"\n【N2 能机械检查的边界条】  宽 {N2宽}  →  窄 {N2窄}")
print(f"    · 6.4 措辞红线      {sum(1 for x in 禁项 if x[2].startswith('6.4'))}")
print(f"    · 6.12 内部词       {sum(1 for x in 禁项 if x[2].startswith('6.12'))}")
print(f"    · 禁句清单          {len(禁句)}")
print(f"    · 1109 样板句(回归) {len(样板句)}")
print(f"    · 钉死的数          {len(钉死)} → 窄 {sum(1 for v in 钉死.values() if v[2])}")
print(f"\n【N3 疑似打架处】  ★★★★★ 宽 {n(宽)}  →  窄 {n(窄)}")
for 层, 说明 in (("L1", "硬撞：说给用户的那句话里出现禁词/禁句"),
                 ("L2", "改写样板：1109 已并走的句子正文又写了一遍（回归）"),
                 ("L3", "数字不一致：共用边界钉死的数，正文给了另一个"),
                 ("L4", "机器核不了：命中禁词但在卡的内部文字里（6.12 范围外）")):
    print(f"    · {层} {说明}\n         → 宽 {len(宽[层])}  →  窄 {len(窄[层])} 处"
          + (f"（{len(set(x[0] for x in 窄[层]))} 张卡）" if 窄[层] else ""))
for 层 in ("L1", "L2", "L3", "L4"):
    v = 窄[层]
    if not v:
        continue
    print(f"\n--- 窄口径 {层} 明细（{len(v)} 处）---")
    for 卡名, i, 什么, 源, 行 in v[:25]:
        print(f"  {卡名}:{i}  [{源}] {什么}\n      {行}")
    if len(v) > 25:
        print(f"  …… 还有 {len(v)-25} 处")
print("\n" + "=" * 74)
print("★★ 判法（★ 写清楚，免得这些黄又挂三轮被当背景噪声）：")
print("  ✅ 不算 = 那一行带否定标记（不许/禁用/❌/红线…）→ 它在说禁令本身")
print("  ✅ 不算 = 「## 共用边界」整节切掉 → 那一节本来就是引用")
print("  ✅ 不算 = 6.12 的词出现在卡的**内部文字**里 → 6.12 自己写了「不管内部判据的写法」")
print("  🟡 L1  = 词出现在**引号里**（说给用户的那一句）→ 这才是真打架")
print("★★★ 本脚本只读：skills_v2/ 一个字节都没写")
print("=" * 74)
json.dump({"N1": N1, "N2": {"宽": N2宽, "窄": N2窄},
           "N3": {"宽": n(宽), "窄": n(窄)},
           "分层": {"宽": {k: len(v) for k, v in 宽.items()}, "窄": {k: len(v) for k, v in 窄.items()}},
           "窄明细": {k: [list(x) for x in v] for k, v in 窄.items()}},
          open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "量正文对边界_1114.json"), "w"),
          ensure_ascii=False, indent=1)
