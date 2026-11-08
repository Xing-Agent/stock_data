# -*- coding: utf-8 -*-
"""★★★ 给 19 张大师方法卡补「能力标签」，并把触发条件从「点名才用」改成「按需求触发」。

★★ 三秒版：现在 19 张卡**全部**写着「当用户明确点名该大师/方法时使用」——
   ★★★ 一个不知道威科夫是谁的用户，**永远触发不到这张卡**。

★★★ 依据（Lin 2026-10 定的架构，2026-11-08 19:31 重申）：
   **流派 → 人 → 能力 → 方法 → 三档（原著/行业/我们）**
   · 「以**能力**为基本，**方法是能力的体现**」
   · 「用户问不同问题时，系统给出最合适的观点，★ 背后**可标注来源于哪几位大师**」
→ ★★ 所以两条路都要通：★ 点名进来（人→能力→方法）· ★★ 描述需求进来（能力→方法）。

★★★★★ 关键约束：**正文一个字不动**，只改 frontmatter 的 description，并加 capabilities。
   ★ 触发用的那几句话**取自卡自己的「什么时候用」**，★★★ 不是我编的。
"""
from __future__ import annotations
import io
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CARDS = os.path.join(ROOT, "手册/V1原始skill归档")

# ★★★ 能力标签：组 / 面 / 具体能力（★ 组和面用 Lin 定的分法：研究组=基本面/技术面/宏观；行动组=策略/风控）
能力表 = {
    "akre-capital-allocation":        ("研究组", "基本面", "资本配置质量"),
    "buffett-munger-business-quality": ("研究组", "基本面", "企业质量与护城河"),
    "chanos-short-forensics":         ("研究组", "基本面", "反方取证与会计质量"),
    "dalio-macro-machine":            ("研究组", "宏观", "宏观传导"),
    "earnings-quick-read":            ("研究组", "基本面", "财报解读"),
    "feynman-plain-language":         ("通用件", "表达", "通俗化表达"),
    "financial-translation":          ("通用件", "表达", "金融翻译"),
    "fisher-scuttlebutt":             ("研究组", "基本面", "一手交叉验证"),
    "greenblatt-special-situations":  ("研究组", "基本面", "特殊事件"),
    "growth-quality":                 ("研究组", "基本面", "增长质量"),
    "lynch-cognitive-gap-flywheel":   ("研究组", "基本面", "成长与认知差"),
    "mauboussin-implied-expectations": ("研究组", "基本面", "隐含预期估值"),
    "piotroski-f-score":              ("研究组", "基本面", "财务健康度"),
    "schilit-financial-red-flags":    ("研究组", "基本面", "财务红旗"),
    "soros-reflexivity":              ("研究组", "宏观", "反身性与反馈循环"),
    "supply-chain-transmission":      ("研究组", "基本面", "供应链传导"),
    "weinstein-stage-analysis":       ("研究组", "技术面", "阶段分析"),
    "wyckoff-price-volume":           ("研究组", "技术面", "量价结构"),
    "zweig-market-breadth":           ("研究组", "技术面", "市场宽度"),
}

# ★ 人名：没有具名大师的，标 ——（★★★ Lin 1108：没人标注的按它干啥命名）
无具名大师 = {"earnings-quick-read", "financial-translation", "growth-quality",
            "supply-chain-transmission"}

点名句 = re.compile(r"[。；;]?\s*当用户明确点名该大师[^。]*。?")


def 取什么时候用(body: str, n: int = 3) -> list[str]:
    m = re.search(r"^##\s*什么时候用\s*$(.*?)^##", body, re.S | re.M)
    if not m:
        return []
    return [re.sub(r"^[-*]\s*", "", x).strip()
            for x in m.group(1).strip().splitlines() if x.strip().startswith(("-", "*"))][:n]


def main() -> int:
    干跑 = "--apply" not in sys.argv
    改了, 跳过 = [], []
    for 目录 in sorted(os.listdir(CARDS)):
        p = os.path.join(CARDS, 目录, "SKILL.md")
        if not os.path.exists(p):
            continue
        键 = 目录.replace("xing-master-", "")
        if 键 not in 能力表:
            跳过.append(目录)
            continue
        s = io.open(p, encoding="utf-8").read()
        fm = re.match(r"^---\n(.*?)\n---\n(.*)$", s, re.S)
        if not fm:
            跳过.append(目录 + "（没有 frontmatter）")
            continue
        头, 正文 = fm.group(1), fm.group(2)
        组, 面, 能力 = 能力表[键]
        场景 = 取什么时候用(正文)
        if not 场景:
            跳过.append(目录 + "（找不到「什么时候用」）")
            continue

        大师 = "" if 键 in 无具名大师 else 键.split("-")[0]
        触发 = ("当用户问到这类问题时使用：" + "；".join(x.rstrip("？?") for x in 场景) + "。"
                + (f" 用户点名「{大师}」或该方法时也用。" if 大师 else ""))
        新头 = 点名句.sub("", 头).rstrip()
        if not 新头.endswith("。"):
            新头 += "。"
        新头 += " " + 触发
        # ★★ 把 capabilities 作为独立字段加进去（★ 放在 description 之后）
        新头 = 新头.rstrip() + f"\ncapability_group: {组}\ncapability_face: {面}\ncapability: {能力}"
        if 大师:
            新头 += f"\nmaster: {大师}"
        新文 = f"---\n{新头}\n---\n{正文}"
        改了.append((目录, 组, 面, 能力, 大师 or "（无具名大师）", len(场景)))
        if not 干跑:
            io.open(p, "w", encoding="utf-8").write(新文)

    print(f"{'★ 干跑（没写盘）' if 干跑 else '★★★ 已写盘'} —— 改 {len(改了)} 张 · 跳过 {len(跳过)} 个")
    for r in 改了:
        print("  %-34s %s/%s · %s · 大师=%s · 场景 %d 条" % r)
    if 跳过:
        print("★ 跳过：", 跳过)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
