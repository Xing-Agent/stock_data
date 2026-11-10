# -*- coding: utf-8 -*-
"""★★★★★ 修「自述不符」26 条 —— ★ 这是**我 1109 改出来的错**，另一个 chat 的新检查项抓住的。

★★ 病因（★★★ 和 #99 / #104 同一个根因：**新句加了，旧句没删**）：
   ★ 1109 我把 30 张卡的边界节换成「以 `common_boundaries.md` 为**唯一来源**」，
   ★★★★★ 但没删掉各卡原有的那句「**常态不加载包外 `shared/` 文件**」。
   → ★★ 同一张卡里两条指令打架，★★★★★ **AI 可能据此根本不去读那份文件** ——
     ★ 比原来「没引用」更难查：现在是「引用了但被另一句挡住」。

★★ 另一条：共用边界文件**头部自己写着「引用它的卡共 8 张」**，
   ★★★ 我 1109 改成 39 张却没改这句 —— ★★★★★ 按它分工会漏掉其余 31 张。

★★ 本脚本只做两件，**不动任何判据**：
   ① 删掉与「唯一来源」打架的旧句（★ 只删那一句，句子其余内容原样保留）
   ② 把共用边界头部的「共 8 张」改成实际张数
★★★★★ 写盘前跑完自证;任一条对不上 —— 一个字节都不写。XING_DRYRUN=1 只自证。
"""
from __future__ import annotations
import glob
import hashlib
import io
import os
import re

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
包 = os.path.join(ROOT, "skills_v2")
试跑 = os.environ.get("XING_DRYRUN", "") == "1"

# ★★★ 要删的旧句（★ 逐字匹配，不用正则猜）
旧句们 = [
    "常态不加载包外 `shared/` 文件——旧路径在原包中不存在。",
    "常态不加载包外 `shared/` 文件——旧路径在原包中不存在。 ",
    "常态不加载包外 `shared/` 文件。",
    "边界已内联在下方，常态不加载包外 `shared/` 文件。",
    "（已内联在下方）",
    "已内联在下方。",
]
替 = ("共用边界以 `references/shared/common_boundaries.md` 为唯一来源（本卡已引用）。")


def md5(p):
    return hashlib.md5(io.open(p, "rb").read()).hexdigest()


def main() -> int:
    读 = lambda p: io.open(p, encoding="utf-8").read()
    卡们 = sorted(glob.glob(os.path.join(包, "*", "SKILL.md")))
    共用们 = sorted(glob.glob(os.path.join(包, "*", "references", "shared", "common_boundaries.md")))
    if len({md5(p) for p in 共用们}) != 1:
        print("★★★★★ 共用文件本来就不一致 —— 先查清，本次什么都不改。")
        return 1

    原文, 计划 = {}, {}
    命中统计 = {}
    for p in 卡们:
        t = 原文[p] = 读(p)
        新 = t
        命中 = []
        for s in 旧句们:
            if s in 新:
                命中.append(s)
                # ★★ 第一条打架句换成一句明确的;其余直接删掉（避免重复）
                新 = 新.replace(s, 替 if not 计划.get(p) and s == 命中[0] else "")
        if 命中:
            计划[p] = 新
            命中统计[os.path.basename(os.path.dirname(p))] = [x[:22] for x in 命中]

    # ---- 共用边界头部那个「共 8 张」
    原共用 = 读(共用们[0])
    m = re.search(r"共\s*\*{0,2}(\d+)\s*\*{0,2}\s*张", 原共用[:1500])
    新共用 = 原共用
    头部改 = None
    if m:
        头部改 = (m.group(1), str(len(卡们)))
        新共用 = 原共用[:m.start()] + m.group(0).replace(m.group(1), str(len(卡们))) \
            + 原共用[m.end():]

    # ---- 自证
    print("★★★ 自证（★ 写盘前）")
    失败 = []
    print(f"   ★ 要动的卡：{len(计划)} 张")

    # a) ★★★★★ 只许删那一句，★ 其余内容一个字不许少
    for p, 新 in 计划.items():
        卡 = os.path.basename(os.path.dirname(p))
        抹 = lambda s: re.sub(r"\s+", "", s)
        去旧 = 原文[p]
        for s in 旧句们:
            去旧 = 去旧.replace(s, "")
        ok = 抹(新.replace(替, "")) == 抹(去旧)
        if not ok:
            失败.append(f"{卡}: 除了删那几句，正文还被动了")
    print(f"   {'✓' if not 失败 else '✗'} {len(计划)} 张卡「除删除目标句外逐字未动」")

    # b) ★★★ 改完之后，不许再有卡同时出现「不加载包外」和「唯一来源」
    仍打架 = []
    for p in 卡们:
        t = 计划.get(p, 原文[p])
        if ("不加载包外" in t or "已内联在下方" in t) and "唯一来源" in t:
            仍打架.append(os.path.basename(os.path.dirname(p)))
    print(f"   {'✓' if not 仍打架 else '✗'} 改完后仍打架的卡：{len(仍打架)} 张 {仍打架[:4]}")
    if 仍打架:
        失败.append(f"仍打架 {len(仍打架)} 张")

    # c) ★★ 引用没被删掉（★★★ 修这个错不许顺手把昨天的成果弄丢）
    丢引用 = [os.path.basename(os.path.dirname(p)) for p in 卡们
            if "common_boundaries" not in 计划.get(p, 原文[p])]
    print(f"   {'✓' if not 丢引用 else '✗'} 39 张仍然全部引用共用那份（★ 丢了 {len(丢引用)} 张）")
    if 丢引用:
        失败.append(f"丢引用 {丢引用}")

    # d) ★ 头部数字
    print(f"   {'✓' if 头部改 else '—'} 共用边界头部「共 {头部改[0]} 张」→「共 {头部改[1]} 张」"
          if 头部改 else "   — 头部没找到「共 N 张」这句")

    # e) ★★★★★ 判据一个都不许动
    数 = ["74,268", "10.9", "15,192", "6,583"]
    for d in 数:
        旧n = sum(原文[p].count(d) for p in 卡们)
        新n = sum(计划.get(p, 原文[p]).count(d) for p in 卡们)
        ok = 旧n == 新n
        print(f"   {'✓' if ok else '✗'} 「{d}」{旧n} → {新n}")
        if not ok:
            失败.append(f"数字 {d} 被动了")

    if 失败:
        print("\n★★★★★ 自证不通过，**一个字节都没写**：")
        for x in 失败[:10]:
            print("   ", x)
        return 1
    if 试跑:
        print(f"\n★★ XING_DRYRUN=1 —— 自证通过，没写盘。★ 命中明细：{命中统计}")
        return 0

    for p, c in 计划.items():
        io.open(p, "w", encoding="utf-8").write(c)
    for p in 共用们:
        io.open(p, "w", encoding="utf-8").write(新共用)
    print(f"\n   {'✓' if len({md5(p) for p in 共用们}) == 1 else '✗'} 写盘后 {len(共用们)} 份共用文件指纹全同")
    print(f"\n★★ 写完。★ 动了 {len(计划)} 张卡 + {len(共用们)} 份共用文件。")
    print("★★★★★ 这个错是**另一个 chat 的新检查项抓住的，不是我自己发现的** —— "
          "★★★ 同一个根因（新句加了、旧句没删）今天是第 7 次。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
