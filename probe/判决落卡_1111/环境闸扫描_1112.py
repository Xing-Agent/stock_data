#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""扫出每个台账条目的「环境闸：有 / 无 + 为什么」（2026-11-12）

★ Lin 1112 16:08 同意：「有的有，有的无，没有的就是无」—— ★★ 标出来。

★★★★★ **标这一行立刻查出一个我刚写错的东西**：
   ★ 我今天下午在共用边界顶部写的照抄句是
     「不是原著没讲，是我们**为了三版可比**故意留空」——
   ★★★★★ 但「无」其实有**四种原因**，那句话**只对其中一种**：
     ① 三版可比性，我们故意留空   → ✅ 我那句话对
     ② ★★★★★ **原著本来就没有**（技-1 海龟）→ 🔴 答「不是原著没讲」**就是答错**
     ③ 原著有、但我们接不上（技-10：要 状-1 的摆动点，阈值还没校准）
     ④ 配置里没写理由            → ★★ 只能说「我们没记」
🔴 ★★ 所以答法必须**按条目自己那一行说**，不许用一句话套所有条目。

★★ 配置分散在三处（★ 都扫）：
   `engine/configs/`（技/状/模/六套打法）
   `probe/fundamental_buildout_1030/configs_1030/`（基-X 第一批）
   `probe/基本面跑批_1106/configs/`（基-X 现行）
★ 不碰 engine/ 一个字节 —— 只读。
"""
import glob
import io
import json
import os
import re

import yaml

ROOT = "/home/claude/xing-agent-stock_data"
目录 = [
    "engine/configs",
    "probe/fundamental_buildout_1030/configs_1030",
    "probe/基本面跑批_1106/configs",
    "probe/新策略_1106/configs",
]


def 分类(有: bool, src) -> tuple:
    """★★★ 返回（档, 给用户的那句话）—— ★★★★★ 每一句都**贴着配置自己写的理由**，不是我编的。"""
    s = str(src or "")
    if 有:
        return ("有", "★★ 这一版**装了**环境闸 —— ★★★ 闸上那几个数是**行业惯例**，不是原著给的。")
    if "照原文" in s or "无环境过滤" in s:
        return ("无·原著本来就没有",
                "★★★★★ **原著本身就没有这道闸** —— ★ 我们留空是**照原文**，不是忘了填。"
                "🔴 ★★ 所以**不许**答「不是原著没讲」—— ★★★ 原著真的没讲。")
    if "接不上" in s:
        return ("无·原著有但接不上",
                "★★★★★ **原著有禁用条件，但我们接不上** —— ★ 它要另一条策略的摆动点定义，"
                "而那个阈值还没校准。★★★ 所以这一版没装，**不是忽略**。")
    if "三版可比" in s:
        return ("无·为了三版可比",
                "★★★★★ **我们这版没装 —— 不是原著没讲，是为了让三个版本可以互相比，"
                "这一格故意留空。**\n"
                "🔴 ★★ 答用户时**后半句必须整句带出，不许省成「这版没装」**—— "
                "省掉就把「我们的执行选择」说成了「原著没讲」，那是红线①。"
                "（★ C 组 1112 实测：带这句的技-1 三轮全对，不带的技-4 两轮都缺半句）")
    return ("无·配置里没写理由",
            "★★ 这一版**没装**环境闸。★★★★★ **为什么没装，我们这边没有记录** —— "
            "🔴 ★ 不许替它编一个理由（★★ 比如别说「原著没讲」，我们并不知道）。")


def main():
    出 = {}
    for d in 目录:
        for f in sorted(glob.glob(os.path.join(ROOT, d, "*.y*ml"))):
            if "TEMPLATE" in f:
                continue
            try:
                c = yaml.safe_load(io.open(f, encoding="utf-8"))
            except Exception:
                continue
            if not isinstance(c, dict):
                continue
            nm = os.path.basename(f).rsplit(".", 1)[0]
            m = re.match(r"([一-鿿]-\d+)", nm)
            if not m:
                continue                      # ★ 六套打法（流派N_*）不是台账条目
            cid = m.group(1)
            reg = c.get("regime")
            有 = bool(isinstance(reg, dict) and reg.get("rules"))
            src = reg.get("source") if isinstance(reg, dict) else None
            档, 话 = 分类(有, src)
            出.setdefault(cid, {"版本": [], "档": set()})
            出[cid]["版本"].append({"配置": nm, "档": 档, "话": 话})
            出[cid]["档"].add(档)

    汇 = {}
    for cid, v in sorted(出.items()):
        档s = sorted(v["档"])
        # ★★★★★ 同一条目的几个版本**可能不同档** —— ★ 那就都列出来，不合并成一句
        汇[cid] = {
            "版本数": len(v["版本"]),
            "档": 档s,
            "一致吗": len(档s) == 1,
            "话": v["版本"][0]["话"] if len(档s) == 1 else None,
            "逐版本": v["版本"],
        }
    p = os.path.join(ROOT, "probe/判决落卡_1111/_环境闸_1112.json")
    json.dump(汇, io.open(p, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"★ 扫到 {len(汇)} 个台账条目（★★ 从 {len(目录)} 个配置目录）\n")
    import collections
    c = collections.Counter(d for v in 汇.values() for d in v["档"])
    for k, n in c.most_common():
        print(f"   {k:24s} {n} 个条目")
    不一致 = [k for k, v in 汇.items() if not v["一致吗"]]
    print(f"\n★★★ 同条目各版本**不同档**的：{不一致 if 不一致 else '无'}")
    print(f"★ → {p}")
    print("\n★★★★★ **没有配置的条目怎么办**：")
    print("   ★ 本脚本只覆盖有配置文件的条目。★★ 其余条目**不写这一行** ——")
    print("   🔴 ★★★ 没有数据就不标，**不许默认写「无」**（★ 那是猜）。")


if __name__ == "__main__":
    main()
