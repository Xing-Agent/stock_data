# -*- coding: utf-8 -*-
"""★★★★★ 把「共用边界只有一份」这条设计修回去 —— ★ Lin 1109 17:50 拍「修吧」。

★★ 三秒版：38 张卡目录里都有 `common_boundaries.md`（★ md5 全同），
   ★★★ 但只有 **8 张**正文引用它 —— 另外 30 张不受它管，
   ★★★★★ 我们每次改的就是那份**没人指的文件**。

★★ 量过的事实（★ 这些数决定了改法）：
   · 21 张自己写了一节「共用边界」，★ 独家句 127 条 → **去重只剩 25 条**
   · 其中 **6 条是纯样板**（每条出现在 16~19 张卡里）—— ★★ 和共用那份说同一件事、换了说法
   · 其中 **19 条是真·各卡独家**（每条只在 1~2 张里）—— ★★★★★ **一个字都不许丢**
     （★ 例：菲利普费雪 vs 肯尼斯费雪的人物歧义;阶段判断必须允许第五态「无法判定」）
   · 另有 9 张**两样都没有**
→ ★★★ 共用边界 6.10：「精简永远不许减掉**代价 / 坏消息 / 归属**」—— 那 19 条正是归属。

★★ 本脚本做三件：
   ① 6 条样板句并进共用那份（★ 38 份同文件一起改，★★ 改完 md5 必须仍然全同）
   ② 21 张：边界节换成「引用共用那份」+ **原样保留各自的独家句**
   ③ 9 张：补一行引用
★★★★★ 写盘前先在内存里跑完自证;★ 任何一条独家句对不上 —— **一个字节都不写**。
"""
from __future__ import annotations
import glob
import hashlib
import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
包 = os.path.join(ROOT, os.environ.get("XING_CARDS", "skills_v2"))
试跑 = os.environ.get("XING_DRYRUN", "") == "1"

# ★★★ 那 6 条样板句 —— ★ 出现在 16~19 张卡里，不是任何一张的独家内容
样板句 = [
    "重要结论必须有证据，不用大师名气替代证据",
    "不输出个性化买卖、仓位、止损、杠杆、收益承诺或无依据目标价",
    "缺少数据时明确写「数据不足/待验证」，不要补造事实",
    "「大师 Skill」表示使用该方法论视角，不代表相关人物本人参与或背书",
    "只有用户要求完整方法推导时才按需查看 references/method.md",
    "共用研究规则与导师表达边界以 references/shared/common_boundaries.md 为唯一来源",
]
并入节 = (
    "\n## 由各卡正文并入（2026-11-09 · Lin 拍板「修吧」）\n\n"
    "★★★ 下面几条原先重复写在 16~19 张卡的正文里。★ 它们说的和本文件其余部分是同一件事，\n"
    "只是换了说法 —— ★★ 并到这里之后，各卡正文改为引用本文件，不再各写一遍。\n\n"
    + "".join(f"- {s}。\n" for s in 样板句)
)

引用行 = (
    "## 共用边界\n\n"
    "本卡的研究规则与表达边界，以 `references/shared/common_boundaries.md` 为**唯一来源**。\n"
    "该文件 38 张卡共用一份；**不要改写、不要复制到本卡正文里**。\n"
)
本卡独有 = "\n### 本卡独有的边界（★ 共用那份没有，不许省）\n\n"


def 规范(s: str) -> str:
    return re.sub(r"[\s★*`#>|\-—·]+", "", s)


def 切句(t: str) -> list:
    return [x for x in (规范(y) for y in re.split(r"[。\n；;]", t)) if len(x) >= 10]


def main() -> int:
    共用路径 = sorted(glob.glob(os.path.join(包, "*", "references", "shared", "common_boundaries.md")))
    if not 共用路径:
        print(f"★★★ 找不到 common_boundaries.md：{包}")
        return 1
    原共用 = io.open(共用路径[0], encoding="utf-8").read()
    指纹集 = {hashlib.md5(io.open(p, "rb").read()).hexdigest() for p in 共用路径}
    if len(指纹集) != 1:
        print(f"★★★★★ 那 {len(共用路径)} 份共用文件**本来就不一致**（{len(指纹集)} 种指纹）—— "
              "★★ 这是另一个问题，先查清，本次什么都不改。")
        return 1
    print(f"★ 共用那份：{len(共用路径)} 处副本、指纹全同、{len(原共用)} 字")

    共用句 = set(切句(原共用))
    新共用 = 原共用.rstrip("\n") + "\n" + 并入节

    # ---- 分类 + 算出每张卡要保留的独家句
    计划 = {}   # 卡 -> (新正文, 独家句原文列表)
    分类 = {"已引用": [], "换引用": [], "补引用": []}
    for p in sorted(glob.glob(os.path.join(包, "*", "SKILL.md"))):
        卡 = os.path.basename(os.path.dirname(p))
        t = io.open(p, encoding="utf-8").read()
        if "common_boundaries" in t:
            分类["已引用"].append(卡)
            continue
        m = re.search(r"(#+[^\n]*共用边界[^\n]*\n)(.*?)(?=\n#+ |\Z)", t, re.S)
        if not m:
            分类["补引用"].append(卡)
            计划[卡] = (t.rstrip("\n") + "\n\n" + 引用行, [])
            continue
        节原文 = m.group(2)
        # ★★★ 独家 = 这一节里、共用那份没有、且不属于那 6 条样板的句子
        样板规范 = {规范(s) for s in 样板句}
        独家原句 = []
        for 行 in 节原文.splitlines():
            if len(规范(行)) < 10:
                continue
            if any(规范(x) in 共用句 or 规范(x) in 样板规范 for x in re.split(r"[。；;]", 行) if 规范(x)):
                # ★ 整行里每一小句都已被共用那份或样板覆盖 → 不是独家
                if all((规范(x) in 共用句 or 规范(x) in 样板规范)
                       for x in re.split(r"[。；;]", 行) if len(规范(x)) >= 10):
                    continue
            独家原句.append(行.strip())
        新节 = 引用行 + (本卡独有 + "".join(f"{x}\n" for x in 独家原句) if 独家原句 else "")
        新正文 = t[:m.start()] + 新节 + t[m.end():]
        计划[卡] = (新正文, 独家原句)
        分类["换引用"].append(卡)

    print(f"★★ 分类：已引用 {len(分类['已引用'])} 张 · 换引用 {len(分类['换引用'])} 张 · "
          f"补引用 {len(分类['补引用'])} 张")

    # ---- ★★★★★ 自证（写盘**之前**跑完）
    print("\n★★★ 自证（★ 写盘前）")
    失败 = []

    # a) 每一条独家句必须逐字出现在新正文里
    丢 = 0
    for 卡, (新, 独家) in 计划.items():
        for s in 独家:
            if s not in 新:
                失败.append(f"{卡}: 独家句丢了 → {s[:40]}")
                丢 += 1
    总独家 = sum(len(v[1]) for v in 计划.values())
    print(f"   {'✓' if 丢 == 0 else '✗'} 独家句共 {总独家} 条，逐字保留 {总独家 - 丢} 条，丢 {丢} 条")

    # b) 改完之后每张卡都必须引用共用那份
    没引用 = [c for c, (新, _) in 计划.items() if "common_boundaries" not in 新]
    print(f"   {'✓' if not 没引用 else '✗'} 改完后 38 张全部引用共用那份"
          f"（★ 本次动 {len(计划)} 张，仍未引用 {len(没引用)} 张）")
    if 没引用:
        失败.append(f"仍未引用：{没引用}")

    # c) ★★★ 那 19 条真独家里，抽三条点名验证（★ 这几条是最不能丢的）
    点名 = ["菲利普费雪", "第五态", "并购套利"]
    全新文 = "".join(v[0] for v in 计划.values()) + "".join(
        io.open(os.path.join(包, c, "SKILL.md"), encoding="utf-8").read() for c in 分类["已引用"])
    for k in 点名:
        旧 = sum(io.open(p, encoding="utf-8").read().count(k)
                for p in glob.glob(os.path.join(包, "*", "SKILL.md")))
        新 = 全新文.count(k)
        ok = 新 >= 旧 and 旧 > 0
        print(f"   {'✓' if ok else '✗'} 点名验「{k}」：改前 {旧} 次 → 改后 {新} 次")
        if not ok:
            失败.append(f"点名句「{k}」改前 {旧} 改后 {新}")

    # d) 样板句并进共用那份之后，共用那份必须真的含有它们
    for s in 样板句:
        if 规范(s) not in 规范(新共用):
            失败.append(f"样板句没并进共用那份：{s[:30]}")
    print(f"   {'✓' if all(规范(s) in 规范(新共用) for s in 样板句) else '✗'} "
          f"6 条样板句已并进共用那份（★ {len(原共用)} 字 → {len(新共用)} 字）")

    if 失败:
        print("\n★★★★★ 自证不通过，**一个字节都没写**：")
        for x in 失败[:12]:
            print("   ", x)
        return 1
    if 试跑:
        print("\n★★ XING_DRYRUN=1 —— 自证通过，但按要求**没有写盘**。")
        return 0

    # ---- 写盘
    for p in 共用路径:
        io.open(p, "w", encoding="utf-8").write(新共用)
    for 卡, (新, _) in 计划.items():
        io.open(os.path.join(包, 卡, "SKILL.md"), "w", encoding="utf-8").write(新)

    写后指纹 = {hashlib.md5(io.open(p, "rb").read()).hexdigest() for p in 共用路径}
    print(f"\n   {'✓' if len(写后指纹) == 1 else '✗'} 写盘后 {len(共用路径)} 份共用文件仍然指纹全同")
    print(f"\n★★ 写完。★★★ 动了 {len(计划)} 张卡 + {len(共用路径)} 份共用文件。")
    print("★★★★★ 没查到的：**边界挂上了不等于模型会照着做** —— "
          "要靠「刁钻输入」那一类测试,机器查不出来。")
    print("★★ 另外：B 组那 6 张用的是 `common_contract`，**本次没动** —— 那是另一个包。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
