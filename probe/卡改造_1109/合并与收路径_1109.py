# -*- coding: utf-8 -*-
"""★★★★★ 两件事一次做完 —— ★ Lin 1109 18:18「合」· 18:19「乙」。

★★ 【一·合】把 B 组 V2.6.1 那一层并进主包（★★★ 两边都是加法，没有冲突项）：
   · B 组 `common_contract.md` 的 25 条规则 → 并进主包 `common_boundaries.md`
     （★★ 点名验过 9/10 条主包确实没有;★★★ 重复一条无害,**丢一条有害** —— 所以宁可重）
   · B 组新写的 `xing-condition-engine` 卡 → 补进主包（★★★★★ 主卡路由一直指着它、卡却不存在）
   · 今天补的「四样底线」→ 同步进主包的 skill-builder / agent-builder
   ★ 主包那 5 张的正文**一个字不删** —— 界面每屏内容、查证、实测数字（含止损宽度 10.9%）全留。

★★ 【二·乙】3 张卡正文里的 `probe/...` 内部路径 → 移到各卡 `references/数据清单.md`，
   ★★★ 正文只留「（有，依据见 references/数据清单.md）」。
   ★★★★★ **结论和数字一个字不动** —— 只搬路径。
   ★ 理由:直接删会丢掉「这个结论的依据在哪」,违反共用边界 6.10
     「精简永远不许减掉代价 / 坏消息 / 归属」。

★★★★★ 写盘前跑完自证;任何一条对不上 —— 一个字节都不写。
★ 退出码 0 = 改完且自证通过。XING_DRYRUN=1 只自证不写盘。
"""
from __future__ import annotations
import glob
import hashlib
import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
主包 = os.path.join(ROOT, "skills_v2")
B包 = os.path.join(ROOT, "skills_v2_6_1")
试跑 = os.environ.get("XING_DRYRUN", "") == "1"

五张 = ["xing-quote", "xing-screener", "xing-review", "xing-skill-builder", "xing-agent-builder"]

# ★★ 【二】要搬的路径：卡 → [(原文片段, 替换成)]
#   ★★★ 只动反引号里的路径本身，★★★★★ 句子其余部分（结论、行数、日期）逐字不变
路径活 = {
    "xing-main": ["probe/survivorship_1029/pool_FULL_ALL.csv"],
    "xing-screener": ["probe/fundamental_buildout_1030/", "probe/survivorship_1029/pool_FULL_ALL.csv"],
    "xing-technical-analyst": [
        "probe/xing-pit-universe-20261029-025954/pit_universe_symbols.csv:6273",
        "probe/fundamentals_sec_1030/sec_earnings_dates_1030.csv",
    ],
}
清单模板 = """# 数据清单（内部查证用）

> ★★ 这张卡正文里的「我们有 / 我们没有」每一条，依据都在这里。
> ★★★ 按共用边界 6.13：说「我们有 X」必须附查证;★★★★★ 说「我们没有 X」也必须附查证。
> ★ 路径是我们仓库内部路径，所以不写在正文里 —— ★★ 但**不能没有**。

| 编号 | 正文里对应的说法 | 依据（仓库内部路径） |
|---|---|---|
{行}

★★ 改动规矩：正文里加一条「我们有 / 我们没有」，**这张表必须同时加一行**。
★★★ 只改一边 = 共用边界 6.13 没落地。
"""


def md5(p: str) -> str:
    return hashlib.md5(io.open(p, "rb").read()).hexdigest()


def main() -> int:
    读 = lambda p: io.open(p, encoding="utf-8").read()
    计划文件 = {}   # 路径 -> 新内容
    原文 = {}

    # ========== 【一·合】① B 组 25 条并进主包共用边界 ==========
    B契约 = 读(os.path.join(B包, "xing-skill-builder", "references", "common_contract.md"))
    B行 = [l.rstrip() for l in B契约.splitlines()
           if l.strip().startswith("-") and len(re.sub(r"[\s★*`>|\-—·]+", "", l)) >= 12]
    共用路径 = sorted(glob.glob(os.path.join(主包, "*", "references", "shared", "common_boundaries.md")))
    原共用 = 读(共用路径[0])
    if len({md5(p) for p in 共用路径}) != 1:
        print("★★★★★ 38 份共用文件本来就不一致 —— 先查清，本次什么都不改。")
        return 1
    并入 = (
        "\n## 并自 B 组 common_contract（2026-11-09 · Lin 拍板「合」）\n\n"
        "★★★ 下面是 B 组 V2.6.1 写出来、而这份文件原先**没有**的规矩。★★ 它们管的是同一件事：\n"
        "**不许用文字制造「已经干完了」的假象。**\n\n"
        "★★★★★ 有少数几条和本文件其它小节说的是同一个意思（★ 点名验过 10 条里重 1 条）——\n"
        "★★ 保留重复是有意的：**同一条边界说两遍无害，漏掉一条有害。**\n\n"
        + "\n".join(B行) + "\n"
    )
    新共用 = 原共用.rstrip("\n") + "\n" + 并入
    for p in 共用路径:
        计划文件[p] = 新共用

    # ========== 【一·合】② condition-engine 整卡搬进主包 ==========
    搬卡 = []
    src = os.path.join(B包, "xing-condition-engine")
    dst = os.path.join(主包, "xing-condition-engine")
    if os.path.isdir(src) and not os.path.isdir(dst):
        for p in sorted(glob.glob(os.path.join(src, "**", "*"), recursive=True)):
            if os.path.isfile(p):
                搬卡.append((p, p.replace(src, dst, 1)))

    # ========== 【一·合】③ 四样底线同步进主包 ==========
    四样源 = 读(os.path.join(B包, "xing-skill-builder", "SKILL.md"))
    m = re.search(r"\n## 验证的四样底线.*?(?=\n## (?!#)|\Z)", 四样源, re.S)
    if not m:
        print("★★★ 在 B 包里找不到「验证的四样底线」那一节 —— 本次什么都不改。")
        return 1
    四样节 = m.group(0)
    前置源 = 读(os.path.join(B包, "xing-agent-builder", "SKILL.md"))
    m2 = re.search(r"\n## 绑定规则前的前置条件.*?(?=\n## (?!#)|\Z)", 前置源, re.S)
    前置节 = m2.group(0) if m2 else ""

    for 卡, 追加 in (("xing-skill-builder", 四样节), ("xing-agent-builder", 前置节)):
        p = os.path.join(主包, 卡, "SKILL.md")
        原文[p] = 读(p)
        if 追加 and "验证的四样底线" not in 原文[p] and "绑定规则前的前置条件" not in 原文[p]:
            计划文件[p] = 原文[p].rstrip("\n") + "\n" + 追加

    # ========== 【二·乙】路径搬到 references/数据清单.md ==========
    清单计划 = {}
    for 卡, 路径们 in 路径活.items():
        p = os.path.join(主包, 卡, "SKILL.md")
        t = 计划文件.get(p, 原文.get(p) or 读(p))
        原文.setdefault(p, 读(p))
        行 = []
        for i, 路 in enumerate(路径们, 1):
            编号 = f"D-{i:02d}"
            # ★ 找出这条路径所在那一行，取前 46 字当「正文里对应的说法」
            说法 = next((re.sub(r"[|★*`]", "", l).strip()[:46]
                         for l in t.splitlines() if 路 in l), "（见正文）")
            行.append(f"| {编号} | {说法} | `{路}` |")
            # ★★★★★ 只替换路径本身，句子其余部分不动
            t = t.replace(f"`{路}`", f"（依据见 `references/数据清单.md` {编号}）")
            t = t.replace(路, f"（依据见 references/数据清单.md {编号}）")
        计划文件[p] = t
        清单计划[os.path.join(主包, 卡, "references", "数据清单.md")] = 清单模板.format(行="\n".join(行))

    # ========== 自证（★ 写盘前） ==========
    print("★★★ 自证（★ 写盘前）")
    失败 = []

    # a) 主包 5 张的正文一个字不许删
    # ★★★★★ 1109 改判法：原来一律用「纯追加」判 —— ★ 但 xing-screener 既在五张里、
    #   又要搬路径，★★ 路径换成短引用后净 −15 字，★★★ 判据当场报错。
    #   ★★★★★ 不是改动错，是**判据前提错**：搬过路径的卡本来就不该是纯追加。
    # ★★ 改成更强的判法：**把路径和替换标记都抹掉之后，两边必须逐字相同** ——
    #   ★★★ 这证明「除了搬路径，别的一个字没动」，比「纯追加」更严。
    def 抹(s: str) -> str:
        s = re.sub(r"（依据见 `?references/数据清单\.md`? D-\d+）", "", s)
        for 路们 in 路径活.values():
            for 路 in 路们:
                s = s.replace(f"`{路}`", "").replace(路, "")
        return s
    for 卡 in 五张:
        p = os.path.join(主包, 卡, "SKILL.md")
        新 = 计划文件.get(p, 原文.get(p) or 读(p))
        旧 = 原文.setdefault(p, 读(p))
        if 卡 in 路径活:
            ok = 抹(新).startswith(抹(旧).rstrip("\n")) or 抹(新) == 抹(旧)
            说 = f"除搬路径外逐字未动（抹掉路径后 {len(抹(旧))} vs {len(抹(新))} 字）"
        else:
            ok = 新.startswith(旧.rstrip("\n")) or 新 == 旧
            说 = f"原文 {len(旧)} 字原样保留（新 {len(新)} 字，净增 {len(新)-len(旧)}）"
        print(f"   {'✓' if ok else '✗'} {卡} {说}")
        if not ok:
            失败.append(f"{卡} 正文被动过（不只是搬路径）")

    # b) ★★★★★ 那个回测挣来的数必须还在
    主全文 = "".join((计划文件.get(os.path.join(主包, c, "SKILL.md"))
                    or 读(os.path.join(主包, c, "SKILL.md"))) for c in 五张)
    for k in ["10.9", "止损宽度"]:
        旧 = sum(读(os.path.join(主包, c, "SKILL.md")).count(k) for c in 五张)
        新 = 主全文.count(k)
        ok = 新 >= 旧 and 旧 > 0
        print(f"   {'✓' if ok else '✗'} 「{k}」改前 {旧} 次 → 改后 {新} 次（★★★ 回测挣来的数）")
        if not ok:
            失败.append(f"「{k}」{旧}→{新}")

    # c) B 组那一层真的并进来了
    for k in ["回执", "不得自动升级", "百分点", "四舍五入", "INVALID"]:
        旧, 新 = 原共用.count(k), 新共用.count(k)
        ok = 新 > 旧
        print(f"   {'✓' if ok else '✗'} 共用边界里「{k}」{旧} → {新} 次")
        if not ok:
            失败.append(f"共用边界「{k}」没并进来（{旧}→{新}）")

    # d) ★★ 路径搬走之后，正文里不许还剩 probe/，且清单里必须有那条路径
    for 卡, 路径们 in 路径活.items():
        新 = 计划文件[os.path.join(主包, 卡, "SKILL.md")]
        剩 = 新.count("probe/")
        清单 = 清单计划[os.path.join(主包, 卡, "references", "数据清单.md")]
        齐 = all(路 in 清单 for 路 in 路径们)
        print(f"   {'✓' if 剩 == 0 and 齐 else '✗'} {卡}: 正文剩 probe/ {剩} 处 · "
              f"清单收录 {sum(路 in 清单 for 路 in 路径们)}/{len(路径们)} 条")
        if 剩 or not 齐:
            失败.append(f"{卡} 路径搬运不干净（正文剩 {剩}，清单齐 {齐}）")

    # e) ★★★ 结论句里的关键数字不许被我顺手改掉
    for 卡, 数 in (("xing-main", ["74,268"]), ("xing-screener", ["74,268"]),
                  ("xing-technical-analyst", ["15,192", "6,583", "292"])):
        p = os.path.join(主包, 卡, "SKILL.md")
        旧t, 新t = 原文.setdefault(p, 读(p)), 计划文件[p]
        for d in 数:
            ok = 旧t.count(d) == 新t.count(d) and 旧t.count(d) > 0
            print(f"   {'✓' if ok else '✗'} {卡} 里「{d}」改前 {旧t.count(d)} → 改后 {新t.count(d)}")
            if not ok:
                失败.append(f"{卡} 数字 {d} 被动了")

    # f) condition-engine 补上了
    print(f"   {'✓' if 搬卡 else '—'} condition-engine 整卡搬进主包（{len(搬卡)} 个文件）")

    if 失败:
        print("\n★★★★★ 自证不通过，**一个字节都没写**：")
        for x in 失败[:12]:
            print("   ", x)
        return 1
    if 试跑:
        print("\n★★ XING_DRYRUN=1 —— 自证通过，按要求没有写盘。")
        return 0

    # ========== 写盘 ==========
    for p, c in {**计划文件, **清单计划}.items():
        os.makedirs(os.path.dirname(p), exist_ok=True)
        io.open(p, "w", encoding="utf-8").write(c)
    for s, d in 搬卡:
        os.makedirs(os.path.dirname(d), exist_ok=True)
        io.open(d, "wb").write(io.open(s, "rb").read())

    写后 = {md5(p) for p in 共用路径}
    print(f"\n   {'✓' if len(写后) == 1 else '✗'} 写盘后 {len(共用路径)} 份共用文件仍然指纹全同")
    print(f"\n★★ 写完。★ 共用边界 {len(原共用)} → {len(新共用)} 字 · "
          f"卡 {len([p for p in 计划文件 if p.endswith('SKILL.md')])} 张 · "
          f"新建数据清单 {len(清单计划)} 份 · condition-engine {len(搬卡)} 个文件。")
    print("★★★★★ 没查到的：**并进来了不等于模型会照着做** —— 要靠「刁钻输入」那一类测试。")
    print("★★ 另外：主包那 5 张的**界面每屏内容、查证、实测数字全部原样保留**，一个字没删。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
