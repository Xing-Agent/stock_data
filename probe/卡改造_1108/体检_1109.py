# -*- coding: utf-8 -*-
"""★★★ 38 张卡的机器体检 —— ★ V2 测试「第二类 · 边界」的主力，每轮冻结后跑一次。

★★ 三秒版：四件事人查会漏、机器查不会 ——
   ① **有没有人改了判据**（★★★ 最要紧，《130》A 格）
   ② 有没有违反共用边界
   ③ 术语是不是统一（同一个东西有没有三种叫法）
   ④ 有没有把内部标记 / 测试记录 / 开发讨论**漏给用户看**

★★★★★ 它只产清单，**不改任何东西**（★ 《131》定的：机器找错，人来修）。
★ 退出码：0 = 没查到；1 = 查到问题（★★ 可以当发布闸用）。
"""
from __future__ import annotations
import io
import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
CARDS = os.path.join(ROOT, os.environ.get("XING_CARDS", "skills_v2"))
基线 = os.environ.get("XING_BASELINE", "")          # ★ 给上一版的目录就能比「判据有没有被动」

# ★★★ 判据长什么样：数字门槛 / 条数 / 比较符 —— ★ 这些一动，选出来的股票就会变
判据模式 = [
    (re.compile(r"(≥|≤|>|<|>=|<=)\s*\d+(\.\d+)?\s*%?"), "比较门槛"),
    (re.compile(r"前\s*\d+\s*(只|名|%)"), "取前N"),
    (re.compile(r"\d+\s*日(均线|线|新高|新低)"), "周期参数"),
    (re.compile(r"(止损|止盈)[^。\n]{0,12}?\d+(\.\d+)?\s*(%|R|ATR|倍)"), "止损止盈刻度"),
]
# ★★ 不许漏给用户看的东西
泄漏模式 = [
    (re.compile(r"（?★+\s*(我|Claude|主路|B 路|账本|规矩\s*[㊀-㊿\d])"), "内部标记/账本"),
    (re.compile(r"(待配对检验|跑前登记|作废|OOM|git |commit|probe/)"), "开发痕迹"),
    (re.compile(r"\b(TODO|FIXME|XXX|待补|占位)\b"), "占位未填"),
]
# ★ 同一个概念的多种叫法 —— ★★ 每组里出现 ≥2 种就记一条
术语组 = [
    ("止损", ["止损", "停损", "割肉"]),
    ("回撤", ["回撤", "最大亏损幅度", "drawdown"]),
    ("标普500", ["标普500", "标普 500", "S&P500", "S&P 500", "SPX"]),
    ("均线", ["均线", "移动平均", "MA线"]),
]


def 读卡(基: str) -> dict:
    出 = {}
    if not os.path.isdir(基):
        return 出
    for d in sorted(os.listdir(基)):
        p = os.path.join(基, d, "SKILL.md")
        if os.path.exists(p):
            出[d] = io.open(p, encoding="utf-8").read()
    return 出


def 抽判据(txt: str) -> set:
    """★ 把卡里所有「会改变选股/买卖/通过与否」的数字抽出来当指纹。"""
    s = set()
    for 正则, 名 in 判据模式:
        for m in 正则.finditer(txt):
            s.add(f"{名}::{m.group(0).strip()}")
    return s


def main() -> int:
    卡 = 读卡(CARDS)
    if not 卡:
        print(f"★★★ 读不到卡：{CARDS}")
        return 1
    报 = {"★卡数": len(卡), "🔴判据被动": [], "🔴泄漏": [], "🟡术语不统一": [],
         "🔴违反共用边界": [], "★★本次没查到的": []}

    # ---- ① 判据有没有被动（★★★ 要有基线才能查）
    if 基线:
        旧 = 读卡(os.path.join(ROOT, 基线))
        for d, txt in 卡.items():
            if d not in 旧:
                报["🔴判据被动"].append({"卡": d, "情况": "★ 新增的卡（基线里没有）"})
                continue
            新集, 旧集 = 抽判据(txt), 抽判据(旧[d])
            加, 删 = sorted(新集 - 旧集), sorted(旧集 - 新集)
            if 加 or 删:
                报["🔴判据被动"].append({"卡": d, "新增": 加[:6], "删掉": 删[:6],
                                   "★★★要走谁": "Lin（《130》A 格：逐条问）"})
    else:
        报["★★本次没查到的"].append(
            "★★★ **判据有没有被动** —— ★ 没给基线目录（XING_BASELINE=上一版目录），这一项没查。"
            "★★ 这是四项里最要紧的一项。")

    # ---- ② 泄漏
    for d, txt in 卡.items():
        体 = txt.split("---", 2)[-1]
        for 正则, 名 in 泄漏模式:
            for m in 正则.finditer(体):
                报["🔴泄漏"].append({"卡": d, "类": 名, "原文": m.group(0)[:40]})
                break

    # ---- ③ 术语
    for 概念, 叫法 in 术语组:
        命中 = {}
        for d, txt in 卡.items():
            用到 = [x for x in 叫法 if x in txt]
            if len(用到) >= 2:
                命中[d] = 用到
        if 命中:
            报["🟡术语不统一"].append({"概念": 概念, "卡数": len(命中),
                                 "例": dict(list(命中.items())[:3])})

    # ---- ④ 共用边界
    # ★★★★★ 1109 第二次改判据 —— ★★★ 这是「关键词写太死」**第四次**
    #   （#99 用 ★ 数行 · #104 清理正则漏变体 · 本日第一版 30 张假红 · B 组 6 张假红）。
    #   ★★ 按规矩㊺/㊻：第三次就该改结构，★★★ 拖到第四次了，这次改成**认结构不认字**。
    #
    # ★ 第一版：正文必须出现 `common_boundaries` → 30 张假红（klarman 等自己写全了边界）。
    # ★★ 第二版：正文必须出现「共用边界」四个字 → ★★★ B 组 6 张全红，一验也全是假的：
    #   B 组把同一层边界落到了 `references/common_contract.md`，★★ 内容齐全甚至更严。
    # ★★★★★ 教训：**边界有没有落地，不能靠它叫什么名字来判。**
    #
    # ★★ 现在的判法：① 认一组同义名（含文件名）；② 再看**边界本体的内容指纹**在不在；
    #   ★★★ 两样都没有才算红。★ 另外把「名字分叉」单列成一条真问题 —— ★★ 它会漏同步。
    边界别名 = ["共用边界", "common_boundaries", "common_contract",
             "通用边界", "共同约束", "共用约束", "shared_boundaries"]
    # ★★★ 边界本体一定会说的事（★ 从 38 张卡 + B 组 24 个文件里共同抽出来的）
    边界指纹 = [re.compile(r"不(得|许|能)(编造|捏造|补出|虚构)"),
            re.compile(r"(未知|UNKNOWN|缺失).{0,16}(不得|不许|不能)"),
            re.compile(r"(不承诺|不保证|不给目标价|不预测)"),
            re.compile(r"(数据|行情).{0,10}时点")]
    for d, txt in 卡.items():
        命中名 = [a for a in 边界别名 if a in txt]
        命中纹 = [p.pattern for p in 边界指纹 if p.search(txt)]
        if not 命中名 and len(命中纹) < 2:
            报["🔴违反共用边界"].append(
                {"卡": d, "★": "★★★ 既没有任何「共用边界」同义节名，正文也查不到边界本体的内容指纹"
                              " —— ★★ 边界确实没落地", "命中指纹数": len(命中纹)})
        elif not 命中名:
            报["🟡术语不统一"].append(
                {"概念": "边界落地方式", "卡": d, "命中指纹": 命中纹[:3],
                 "★": "★★ 查到了边界**内容**但没有成节的名字 —— ★★★ 改共用边界时它不会跟着变"})
        elif "common_boundaries" not in txt:
            报["🟡术语不统一"].append(
                {"概念": "★★★ 共用边界文件名分叉", "卡": d, "它用的名": 命中名,
                 "★": "★★★★★ 它引用的**不是 28 张卡共用的那一份 `common_boundaries.md`** —— "
                      "★★ 不算违规，★★★★★ 但我们改共用边界时**这张卡不会跟着变**，必须单独同步"})

    报["★★本次没查到的"] += [
        "★ **答得对不对** —— ★★ 机器只查结构和边界，★★★ 内容对错要靠三类测试里的「刁钻输入」。",
        "★ **流程顺不顺** —— ★★★ 那是体验的事，不是体检的事（《131》：体验属于「改」的阶段）。",
        "★ **references 里的内容** —— ★★ 本次只读 SKILL.md 正文。",
    ]
    红 = len(报["🔴判据被动"]) + len(报["🔴泄漏"]) + len(报["🔴违反共用边界"])
    黄 = len(报["🟡术语不统一"])
    报["★★★三秒版"] = f"🔴 红牌 {红} 张 · 🟡 黄牌 {黄} 张 · ★ 卡数 {len(卡)}"
    out = os.path.join(ROOT, "手册", f"体检_{os.environ.get('XING_TAG','1109')}.json")
    io.open(out, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1))
    print(报["★★★三秒版"])
    for k in ("🔴判据被动", "🔴泄漏", "🔴违反共用边界", "🟡术语不统一"):
        if 报[k]:
            print(f"\n{k}（{len(报[k])}）")
            for x in 报[k][:6]:
                print("  ", json.dumps(x, ensure_ascii=False)[:150])
    print("\n★★ 本次没查到的：")
    for x in 报["★★本次没查到的"]:
        print("  ", x[:110])
    print(f"\n★ 写到 {out}")
    return 1 if 红 else 0


if __name__ == "__main__":
    raise SystemExit(main())
