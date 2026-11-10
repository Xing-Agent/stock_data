#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
把「满仓标普不是一个真实可选的对照组」这条口径做成格子（2026-11-10 · Lin 19:57 定）

★★★★★ 为什么要有这个脚本：
   这条口径 Lin 今天说了三次，我犯了三次。grep 过了 ——
   共用边界 0 处、《93》抬头 0 处、比法规格书只写了「必须用它」没写「它不可达」。
   也就是说：**它从来没有被写下来过**，我每次都靠「当时记得」。
   今天已经学到三次：写规则管不住，格子才管得住。所以这次做成：
     ① 共用边界里的一段正文（39 份同步）
     ② 《93》抬头的一段
     ③ 体检里的一条机器检查（在 体检_1109.py 里，另一个 commit）

★ 不动 engine/ 一个字节。
"""
import hashlib
import os
import re
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(os.path.dirname(__file__))))
ROOT = "/home/claude/xing-agent-stock_data"
DRY = os.environ.get("XING_DRYRUN") == "1"

# ────────────────────────────────────────────────────────────────
# 要插进共用边界的正文（★ 措辞全部来自 Lin 11-10 19:57 的原话）
# ────────────────────────────────────────────────────────────────
ANCHOR = "**那句硬话（不许省）**"

INSERT = """**③-附 · 这个副参考不是一个「可选项」（★★★★★ 不许省，★ 省掉就是骗人）**

把 ③ 单独报出来、或者拿它当「本来可以有的选择」，是**错的**。原因有三层：

- **基金结构上做不到。** 回撤到一定规模，基金**必须直接止损 / 降敞口** ——
  这是合同和风控写死的，不是意愿问题。所以「满仓不动十一年」对**专业机构也不可执行**。
- **个人几乎做不到。** 这十一年里有过 **-34.1%** 的回撤、**2.0 年**不创新高。
  能原封不动坐过去的人极少。
- **能做到的只剩两种钱**：① 把各种衍生品策略叠在一起的超复杂结构；
  ② **自己的钱，并且有绝对的信仰**。

所以 ③ 的正确读法是：
> 「**这是一个上帝视角的参照线，不是一个你本来可以选的方案。**
>   它用来回答『我们这套有没有白折腾』，**不用来回答『你应该去买指数』**。」

**并且 ③ 永远不许单独出现** —— 报 ③ 的同一段里必须同时有 ① 的利润因子和回撤。
我们测过的 28 条里 **23 条利润因子 > 1**；21 条里 **14 条回撤比满仓标普浅**。
**「没跑赢大盘」不等于「不赚钱」，不许写成后者。**

"""

# ────────────────────────────────────────────────────────────────
# 要插进《93》抬头的正文
# ────────────────────────────────────────────────────────────────
LEDGER = "手册/93-策略说明书-全40条-按新尺子-1107.md"
LEDGER_BLOCK = """
> ★★★★★ **读这张台账之前必须先读这一段（2026-11-10 · Lin 定）**
>
> 台账里的「判定」几乎全是**跟满仓标普全收益比**出来的。
> ★★★ **满仓标普全收益、十一年一动不动，不是一个真实可选的对照组：**
> 基金回撤到一定规模**必须直接止损**，结构上做不到；个人要坐过 **-34.1%** 回撤、
> **2.0 年**不创新高，也极少有人做到。能做到的只剩两种钱 ——
> **超复杂衍生品叠加**，或者**自己的钱 + 绝对的信仰**。
>
> ★★★★★ 所以：**「❌ 没跑赢大盘」≠「不赚钱」。**
> 实测 28 条里 **23 条利润因子 > 1**，21 条里 **14 条回撤比满仓标普浅**。
> **任何一句引用本台账判定的话，都必须带上这一层**，否则就是在歪曲它。
>
> ★★ 另：全表只测过 **2015-01-01 ~ 2025-12-31 一个窗口**。换一个十一年，不是这个样子。

"""


def sha(p):
    with open(p, "rb") as f:
        return hashlib.md5(f.read()).hexdigest()


def main():
    cards = sorted(
        os.path.join(dp, "common_boundaries.md")
        for dp, _, fn in os.walk(os.path.join(ROOT, "skills_v2"))
        if "common_boundaries.md" in fn
    )
    print(f"【前置】找到 {len(cards)} 份共用边界")
    before = {p: sha(p) for p in cards}
    uniq = set(before.values())
    print(f"【前置】改之前 md5 种类数 = {len(uniq)}  " + ("✅ 全同" if len(uniq) == 1 else "🔴 不一致，停"))
    if len(uniq) != 1:
        sys.exit(1)

    src = open(cards[0], encoding="utf-8").read()
    if "这个副参考不是一个「可选项」" in src:
        print("【跳过】已经写过了")
        return
    if src.count(ANCHOR) != 1:
        print(f"🔴 锚点出现 {src.count(ANCHOR)} 次，应为 1，停")
        sys.exit(1)

    new = src.replace(ANCHOR, INSERT + ANCHOR)

    # ── 自证 ①：纯插入，原文一个字不动 ──────────────────────
    assert new.replace(INSERT, "", 1) == src, "🔴 不是纯插入"
    print(f"【自证①】纯插入 ✅  原文 {len(src)} 字 → {len(new)} 字（+{len(new)-len(src)}）")

    # ── 自证 ②：关键词进去了 ────────────────────────────────
    for kw, want in [("必须直接止损", 1), ("绝对的信仰", 1), ("上帝视角", 1),
                     ("不等于「不赚钱」", 1), ("永远不许单独出现", 1)]:
        got = new.count(kw)
        print(f"【自证②】「{kw}」{src.count(kw)} → {got}  " + ("✅" if got >= want else "🔴"))
        assert got >= want

    # ── 自证 ③：没引入「建议 / 倾向」这类红线词 ──────────────
    for bad in ["建议挂", "建议不挂", "我倾向"]:
        assert new.count(bad) == src.count(bad), f"🔴 引入了禁词 {bad}"
    print("【自证③】未引入禁词 ✅")

    if DRY:
        print("【DRYRUN】不写盘")
        return

    for p in cards:
        with open(p, "w", encoding="utf-8") as f:
            f.write(new)
    after = {p: sha(p) for p in cards}
    uq = set(after.values())
    print(f"【写后】{len(cards)} 份已写，md5 种类数 = {len(uq)}  " + ("✅ 仍全同" if len(uq) == 1 else "🔴"))
    assert len(uq) == 1

    # ── 《93》抬头 ─────────────────────────────────────────
    lp = os.path.join(ROOT, LEDGER)
    if os.path.exists(lp):
        txt = open(lp, encoding="utf-8").read()
        if "不是一个真实可选的对照组" in txt:
            print("【《93》】已经写过了")
        else:
            lines = txt.split("\n")
            # 插在第一个 H1 之后
            idx = next((i for i, l in enumerate(lines) if l.startswith("# ")), -1)
            assert idx >= 0, "🔴 《93》没找到 H1"
            out = "\n".join(lines[: idx + 1]) + "\n" + LEDGER_BLOCK + "\n".join(lines[idx + 1 :])
            assert out.replace(LEDGER_BLOCK, "", 1) == txt, "🔴 《93》不是纯插入"
            with open(lp, "w", encoding="utf-8") as f:
                f.write(out)
            print(f"【《93》】已插入抬头（+{len(out)-len(txt)} 字）· 纯插入自证 ✅")
    else:
        print(f"🟡 找不到 {LEDGER}，《93》这一半没做")


if __name__ == "__main__":
    main()
