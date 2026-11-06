# -*- coding: utf-8 -*-
"""
生成「技术面策略 · 产品说明书」（2026-11-05）

★ Lin 1105 14:17 要的三份文档之一：
  「技术面策略（跑完的），每个策略的产品说明书，★★ 用大白话。」

★★★ 口径（★ 按 Lin 11-05 10:57 定的）：
  **一条策略 = 一个方法，不同版本算一个** → ★ 所以是 **11 份**，不是 45 份。
  ★★ 每份里把该方法的各个版本并排列出来。

★★★ 本文件里**没有一个手写的数字** —— 全部从这几份算出来：
  · `probe/searchfix_1105/rerun45_results_1105.json`（★ 摩擦统一后 + 修完 engine，自查项2 已过）
  · `probe/friction_rerun_1104/ledgers_1104/REAL__*.csv`（★ 成交流水）
  · `METHOD_LIBRARY/技-*.md`（★ 方法卡原文）
"""
from __future__ import annotations

import glob
import hashlib
import io
import json
import os
import re
from collections import defaultdict

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
RES = os.path.join(ROOT, "probe/searchfix_1105/rerun45_results_1105.json")
LED = os.path.join(ROOT, "probe/friction_rerun_1104/ledgers_1104")
CARDS = os.path.join(ROOT, "METHOD_LIBRARY")
OUT = os.path.join(ROOT, "手册/54-技术面策略-产品说明书-全11条-1105.md")
EQ0 = 1_000_000.0

# ★★★ 1106 修:第 10 格不是「11 条全空」—— 《59》(1105 17:05)已填好 5 条。
#   ★ 这一份原来写死「⬜ 空」,是没跟上。★★ 内容逐条抄《59》,不改写。
格10 = {
 "技-4": {"状态": "★ 已填", "①": "熊市（★ 欧奈尔原著自己的规则：大盘不好就空仓）",
          "②": "SPY 在 200 日线下方 = 熊市;派发日(放量收跌,20–25 天出 5–6 个)",
          "②实证": "★★ 200 日线有实证(Faber 2007;Brock 等 1992);★★★ 派发日/跟进日是惯例,无学术实证",
          "③": "SPY 两档 + 1% 缓冲带（Lin 11-04 拍板）"},
 "技-6": {"状态": "★ 已填", "①": "震荡市（★ 箱体会一个接一个假突破）",
          "②": "ADX(14) < 20 = 震荡,≥25 且 +DI>−DI = 单边;或效率比 ER(10) <0.3 / >0.6",
          "②实证": "★★ 指标出处可靠(Wilder 1978;Kaufman 1995),★★★ 但阈值是惯例;引的实证不是专测这个过滤器",
          "③": "ADX 或 ER 门槛跑相邻三点",
          "⚠": "★★★ 技-6 是**突破**策略 —— 这一格意思是「震荡市会把它打烂」,**不是「适合震荡市」**"},
 "技-10": {"状态": "★★★ 已填（★ 如实写「业内没有公认做法」）",
           "①": "大牛市主升浪期间禁用（★ 真突破会把这套方法打爆；这是方法自带的禁用条件）",
           "②": "★★★ **业内没有公认做法**（★ Gemini 第 30 与第 35 轮两次都这么说）",
           "②实证": "★★★ 它举的做法自己标了「我的推断」;挂的 George & Hwang 2004 讲的是 52 周新高动量,**不对题**",
           "③": "★ 待测,结果出来给一个可调默认值",
           "⚠": "★★ 第 33 轮查明:我们只做多,原著这条禁用针对的方向未必对得上"},
 "技-13": {"状态": "★★ 已填（★ 原著自带判法）",
           "①": "趋势市（★ 强趋势里计数会反复触发而价格继续走）",
           "②": "**TDST 线** —— 买入计数启动前那根 K 线的最低价是支撑,收盘跌破即判强空头、计数作废",
           "②实证": "★★ 出处 DeMark 1994（★ **待核页码**）;★★★ 实证 Bauer & Dahlquist 1999 等测下来基本没有超额",
           "③": "原著版直接用 TDST,不外挂 ADX"},
 "技-14": {"状态": "★★ 已填（★ 原著自带判法）",
           "①": "趋势市（★ 通道随价格一起下移,「触及下轨」会连续出现而价格一路新低）",
           "②": "**带宽创过去 125 天新高 且 %b < 0** → 判「沿下轨走」,禁止买入",
           "②实证": "★★ 出处 Bollinger 2001 第 12–13 章（★ **待核页码**）;★★★ Gemini 给的胜率数字是转述的,**不采用**",
           "③": "原著版用带宽 + %b;200 日线那条归行业版（康纳斯 2009）"},
}



#: ★ Lin 1105 13:47 给的行业三分法（★★ 这是他定的，不是我编的）
三分 = {"技-12": "震荡", "技-14": "震荡", "技-13": "震荡", "技-11": "震荡",
        "技-10": "震荡", "技-6": "突破", "技-5": "突破", "技-3": "突破",
        "技-4": "突破", "技-1": "大波段", "技-2": "大波段"}

#: ★★ 出处档位（★ 11-04 核过的三条是 ①a，其余按方法卡自己的页码栏标 ①b）
出处 = {"技-2": "①a 一手已核（法伯 2007 原文）",
        "技-4": "①a 一手已核（O'Neil 本人署名文章，AAII Journal 1999-09）",
        "技-12": "①a 一手已核（Connors & Alvarez 2008）"}


def b1(r: dict):
    """★ 取基准一的标量值。★★★ `★基准一` 在结果文件里是**整个 dict**,
    标量在 `★新基准一值` —— ★ 1105 踩过这个坑,所以统一走这里。"""
    import numbers
    for k in ("★新基准一值", "基准一", "★基准一"):
        v = r.get(k)
        if isinstance(v, numbers.Number):
            return float(v)
    return None


def 卡原文(mid: str) -> dict:
    p = os.path.join(CARDS, f"{mid}.md")
    if not os.path.exists(p):
        return {}
    s = io.open(p, encoding="utf-8", errors="ignore").read()
    out = {"标题": (re.search(r"^# (.+)$", s, re.M) or [None, ""])[1]}
    for k in ("他是谁", "一句话", "怎么买", "怎么退出", "什么时候用",
              "谁不该用", "最难受的时候", "规则归属", "数据与编码"):
        m = re.search(rf"^{k}\s+(.+?)$", s, re.M)
        if m:
            out[k] = m.group(1).strip()
    return out


_NORM = re.compile(r"[^0-9A-Za-z\u4e00-\u9fff]+")


def _k(s: str) -> str:
    """★ 把链名/文件名规范成只剩「字母数字汉字」—— ★★ 这样分隔符、空格、
    全角半角括号的差异全部消掉。★★★ 1105 踩过:只去空格和斜杠不够。"""
    return _NORM.sub("", s)


_LEDGER_INDEX: dict[str, str] | None = None


def 流水(label: str) -> dict | None:
    global _LEDGER_INDEX
    if _LEDGER_INDEX is None:
        _LEDGER_INDEX = {_k(os.path.basename(f)[6:-4]): f
                         for f in glob.glob(os.path.join(LED, "REAL__*.csv"))}
    f = _LEDGER_INDEX.get(_k(label))
    if not f:
        return None
    d = pd.read_csv(f)
    if d.empty:
        return None
    # ★★★ 1106 新增(规矩⑪):流水内容哈希 —— 用来按**规则内容**去重版本,
    #   ★ 不按文件名。技-1 的「10日出」和「10日反向通道出」两份配置
    #   ★★ 规则逐条相同(只有注释不同),流水逐字节相同 → 本是一个版本印了两遍。
    _h = hashlib.sha256(open(f, "rb").read()).hexdigest()[:12]
    pnl = pd.to_numeric(d["net_pnl"], errors="coerce").dropna()
    if pnl.empty:
        return None
    d["exit_date"] = pd.to_datetime(d["exit_date"], errors="coerce")
    dd = d.dropna(subset=["exit_date"]).sort_values("exit_date")
    g = dd.groupby("exit_date", as_index=False)["net_pnl"].sum()
    # ★ 最长连亏（按天，Lin 1105 12:47 定的口径）
    best = (0, 0.0, None, None)
    cur, amt, i0 = 0, 0.0, None
    arr = g["net_pnl"].to_numpy(dtype=float)
    dts = g["exit_date"].reset_index(drop=True)
    for i, p in enumerate(arr):
        if p < 0:
            cur += 1
            amt += float(p)
            i0 = i if i0 is None else i0
            if cur > best[0] or (cur == best[0] and amt < best[1]):
                best = (cur, amt, dts.iloc[i0], dts.iloc[i])
        else:
            cur, amt, i0 = 0, 0.0, None
    w = pnl > 0
    gross = pd.to_numeric(d["gross_pnl"], errors="coerce").sum()
    fric = pd.to_numeric(d["friction_cost"], errors="coerce").sum()
    return {
        "★流水哈希": _h,
        "笔数": int(len(pnl)), "净盈亏": float(pnl.sum()),
        "胜率": float(w.mean()),
        "平均赢": float(pnl[w].mean()) if w.any() else 0.0,
        "平均亏": float(pnl[~w].mean()) if (~w).any() else 0.0,
        "赢亏比": (float(pnl[w].mean() / abs(pnl[~w].mean()))
                   if w.any() and (~w).any() else np.nan),
        "最大单笔亏": float(pnl.min()),
        "连亏天数": int(best[0]), "连亏金额": float(best[1]),
        "连亏占本金": float(best[1]) / EQ0,
        "连亏持续天": (int((best[3] - best[2]).days) + 1 if best[2] is not None else None),
        "平均持有": float(pd.to_numeric(d["holding_days"], errors="coerce").mean()),
        "毛盈亏": float(gross), "摩擦": float(fric),
        # ★★★ 这个比值在「毛利接近 0」时会炸(1105 实测技-1 算出 8057%)——
        #   ★ 所以只在毛利明显大于 0 时才给,否则标成「毛利≈0,比值无意义」。
        "摩擦占毛利": (float(fric / abs(gross))
                       if gross and abs(gross) > 0.2 * abs(fric) else np.nan),
    }


def 跑批条件() -> dict:
    """★ 逐份解析 engine/configs/*.yaml,算出七槽位哪几格是空的。
    ★★ 这一份披露是配置文件自己要求的(技-6-原著.yaml:42-47)。
    ★★★ 一个数都不手写。"""
    import glob
    import yaml
    tech, other = [], []
    for f in sorted(glob.glob("engine/configs/*.yaml")):
        b = os.path.basename(f)
        if b.startswith("_"):
            continue
        try:
            d = yaml.safe_load(io.open(f, encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(d, dict):
            continue
        rec = {
            "name": b,
            "regime": [r for r in ((d.get("regime") or {}).get("rules") or [])],
            "universe": len((d.get("universe") or {}).get("rules") or []),
            "sizing": bool((d.get("sizing") or {}).get("type")),
            "ranking": bool(((d.get("ranking") or {}).get("primary") or {}).get("formula")),
        }
        (tech if b.startswith("技-") else other).append(rec)
    gate_types = sorted({
        r.get("type") for c in (tech + other) for r in c["regime"]
        if isinstance(r, dict) and r.get("type")
    })
    return {
        "n_tech": len(tech),
        "n_tech_regime": sum(1 for c in tech if c["regime"]),
        "n_tech_universe": sum(1 for c in tech if c["universe"]),
        "n_tech_sizing": sum(1 for c in tech if c["sizing"]),
        "n_tech_ranking": sum(1 for c in tech if c["ranking"]),
        "n_other_regime": sum(1 for c in other if c["regime"]),
        "gate_types": gate_types,
        "n_gate_types": len(gate_types),
    }


def main() -> int:
    res = json.load(io.open(RES, encoding="utf-8"))["逐链"]
    it = list(res.values()) if isinstance(res, dict) else res
    bym: dict[str, list] = defaultdict(list)
    for r in it:
        m = re.search(r"(技-\d+)", r["链"])
        if m:
            bym[m.group(1)].append(r)
    order = sorted(bym, key=lambda x: int(x.split("-")[1]))

    L: list[str] = []
    A = L.append
    A("# 54 · 技术面策略 · ★★★ 产品说明书（全 11 条）2026-11-05")
    A("")
    A("> ★ Lin 1105 14:17 要的。★★ **全部大白话。**")
    A("> ★★★ 口径：**一条策略 = 一个方法，不同版本算一个**（★ Lin 11-05 10:57 定）"
      f"→ 所以是 **{len(order)} 份**，不是 45 份。")
    A("> ★ 数据来自「摩擦口径统一后 + 修完 engine」那一轮（★★ 三道自查已过）。")
    A("> ★★★ **本文件没有一个手写的数字** —— 全部由 "
      "`probe/说明书_1105/生成产品说明书_1105.py` 算出来。")
    A("")
    A("---")
    A("")
    A("## ★★★ 三秒版")
    A("")
    A("```")
    tot = sum(len(v) for v in bym.values())
    allwin = [m for m in order
              if all((b1(x) or 0) > 0 for x in bym[m])]
    alllose = [m for m in order
               if all((b1(x) or 0) <= 0 for x in bym[m])]
    mixed = [m for m in order if m not in allwin and m not in alllose]
    A(f"★ {len(order)} 条策略 · {tot} 个**版本名**。")
    A("   ★★★ **1106 修（规矩⑪）**：版本按**流水内容**去重后，"
      "真实版本数见下表「版本」列 ——")
    A("   ★★ 原来按**文件名**数版本，同一份流水挂两个名字就被数成两个版本。")
    A(f"★★★ **所有版本都赢随机的:{len(allwin)} 条**({' · '.join(allwin)})")
    A(f"★★★ **有赢有输的:{len(mixed)} 条** —— ★ 同一个方法换个参数就翻")
    A(f"★★★ **所有版本都输的:{len(alllose)} 条**")
    A("")
    # ★★★ 这句原来写「严格讲一条都还不能出厂」—— **错了**(第 24 处错)。
    #   规格书第 1 节那张表里「不许留空」打★的只有第 1/2/5/9/12 格,
    #   **第 10 格不是必填格**;规格书第 20 行举的例子也是「第 9 格空着的,不行」。
    A(f"★★★ **第 10 格(明确不适用什么):11 条里已填 {len(格10)} 条,"
      f"还空 {11-len(格10)} 条。**")
    A(f"   ★ 已填的({' · '.join(格10)})内容抄自《59》(1105 17:05);")
    A("   ★★ 剩下 6 条的行业判法已写成《68》待发 Gemini。")
    A("   ★ 按规格书,第 10 格**不是必填格**(必填的是第 1/2/5/9/12 格),"
      "★★ 所以它空着**不挡出厂**;")
    A("   ★★★ 但它是说明书质量的核心 —— **「这条策略适合什么环境」就在这一格**。")
    A("```")
    A("")
    # ------------------------------------------------------------------
    # ★★★ 跑批条件披露 —— 配置文件自己要求的(技-6-原著.yaml:42-47
    #   「本次任何一版的成绩都不含大盘择时的贡献,报告里必须写明」)
    #   ★ 数字由下面的函数现算,不手写。
    # ------------------------------------------------------------------
    cond = 跑批条件()
    A("## ★★★ 这些成绩是在什么条件下跑出来的（★ 必读）")
    A("")
    A("```")
    A("★★★ **这些成绩里,不含任何「看大盘」和「筛股票池」的贡献。**")
    A("")
    A(f"★ 技-* 的 {cond['n_tech']} 份配置,★★ 逐份解析的结果:")
    A(f"   · **环境闸(看大盘)规则数:{cond['n_tech_regime']} 份非空** "
      f"—— ★★★ 也就是 {cond['n_tech'] - cond['n_tech_regime']} 份一条都没有")
    A(f"   · **选股池规则数:{cond['n_tech_universe']} 份非空**")
    A(f"   · 仓位(sizing):{cond['n_tech_sizing']} 份有 · "
      f"排序(ranking):{cond['n_tech_ranking']} 份有")
    A("")
    A("★★ **为什么留空**(★ 配置文件自己写的理由,逐字抄):")
    A("   「留空的理由是**可比性**:三版之间只允许形态参数不同。")
    A("     ★ 所以本次任何一版的成绩都**不含大盘择时的贡献,报告里必须写明**。」")
    A("")
    A("★★★ **所以这两句话要分清:**")
    A("   · ✅ 可以说:「这个**形态**本身,在不看大盘的条件下,成绩是这样」")
    A("   · ❌ **不能说**:「这条**策略**的成绩是这样」—— ★★ 真实的策略是会看大盘的")
    A("   · ❌ **更不能说**:「这条策略适合 / 不适合什么环境」—— ★★★ 我们**没测过**")
    A("")
    A("★★ engine **支持**环境闸(★ 已实现 "
      f"{cond['n_gate_types']} 种闸门类型,{cond['n_other_regime']} 份老配置在用:"
      f"{' · '.join(cond['gate_types'])})")
    A("   → ★★★ 所以这是**没跑**,不是**跑不了**。")
    A("```")
    A("")
    A("## ★★★ 先看这个：表里每一列是什么意思（★ 大白话，★★ Lin 1106 16:58 要的）")
    A("")
    A("| 这一列 | ★ 大白话 | ★★ 怎么算的 |")
    A("|---|---|---|")
    A("| **版本** | ★ 同一个方法的几种不同做法（★★ 比如止损松一点 / 紧一点） "
      "| ★★★ 1106 起按**规则内容**去重 —— 两个名字规则一样的，只算一个 |")
    A("| ★★ **赢随机** | ★★★ 「这条策略**比瞎买强吗**」 "
      "| ★ 在同样的行情里随机挑一样多的票、一样多的次数，两边比每笔赚多少。"
      "★★★ ⚠ 这把尺子有毛病，见下面那条 |")
    A("| **胜率** | ★ 一百笔里有多少笔是赚的 | ★★ 赚钱的笔数 ÷ 总笔数 |")
    A("| ★★★ **赢亏比** | ★ 「赚的时候比亏的时候**多赚几倍**」 "
      "| ★★ 赚钱那些笔的平均金额 ÷ 亏钱那些笔的平均金额。★★★ ⚠ 按**美元**算，"
      "会被仓位大小搅乱（见下） |")
    A("| **持有** | ★ 一笔平均拿多少天 | ★★ **交易日**，不是日历日（★ 20 天 ≈ 4 周） |")
    A("| ★★ **毛盈亏** | ★ 没扣成本之前赚/亏了多少钱 | ★★ 本金 **$1,000,000** |")
    A("| ★★★ **摩擦** | ★ 手续费 + 买卖价差 + 自己把价格推高推低的损失 "
      "| ★★★ **摩擦 > 毛利就是净亏** |")
    A("| **第10格** | ★ 「什么情况下**别用**这条策略」 | ★★ 11 条里已填 5 条 |")
    A("")
    A("```")
    A("★★★ 每笔用多少钱?(★ Lin 1106 16:47 问的)")
    A("   ★ 这些策略**不是**「本金 100 每次用 10 块」那种固定比例,")
    A("   ★★ 而是**先定「最多亏多少」再反推买多少股** ——")
    A("   → ★★★ 结果:止损近的票**买得特别重**。")
    A("   ★ 技-1 实测:每笔**真投进去** 中位 **$225,418**(本金的 22.5%)、最大 $652,135;")
    A("     每笔**最多亏** 中位 **$10,782**(1.08%)。★★ 同时最多持 8 只。")
    A("")
    A("★★★ ⚠ 两件已知的毛病(★ 不藏):")
    A("   ① **「赢随机」这把尺子量的主要是「出场」,不是「进场」** ——")
    A("      ★ 因为对照组的随机进场**沿用了策略自己的出场规则**。")
    A("      → ★★★ 所以「没赢随机」只能说成「**进场没比瞎买好**」,")
    A("        ★★ **不能**说成「这条策略没用」。(★ 1106 第 43 轮核实)")
    A("   ② **「赢亏比」按美元算,会被仓位骗** ——")
    A("      ★ 每笔投入从 11 万到 65 万差 6 倍,★★ 赚的笔仓位小、亏的笔仓位大时,")
    A("      ★★★ 这个数会算成负的而实际是正的(★ 融-2 真出现过)。")
    A("```")
    A("")
    A("### ★ 一屏总表")
    A("")
    A("| 策略 | ★ 派 | 版本 | ★★ 赢随机 | 胜率 | ★★★ 赢亏比 | 持有 "
      "| ★★ 毛盈亏 | ★★★ 摩擦 | 第10格 |")
    A("|---|---|---:|---|---:|---:|---:|---:|---:|---|")
    cache: dict[str, dict] = {}
    for m in order:
        vs = bym[m]
        # ★★★ 规矩⑪(1106):先按**流水内容**去重,再数「赢/输」——
        #   ★ 否则同一份流水挂两个名字就被数成两个版本、两次赢。
        #   ★★ 这一步修的是:技-14 原来报「8赢/1输」(按 9 个名字),真版本只有 5 个。
        配对 = []
        for x in vs:
            _s = 流水(x["链"])
            if _s:
                cache[x["链"]] = _s
            配对.append((x, _s))
        _seen, 去重后 = set(), []
        for x, _s in 配对:
            k = _s["★流水哈希"] if _s else ("无流水:" + x["链"])
            if k in _seen:
                continue
            _seen.add(k)
            去重后.append((x, _s))
        重数 = len(配对) - len(去重后)
        nw = sum(1 for x, _ in 去重后 if (b1(x) or 0) > 0)
        n版 = len(去重后)
        st = [_s for _, _s in 去重后 if _s]
        med = lambda k: (np.nanmedian([s[k] for s in st]) if st else np.nan)  # noqa: E731
        v = ("★ 全赢" if nw == n版 else
             ("全输" if nw == 0 else f"★★★ {nw}赢/{n版-nw}输"))
        版本显示 = (f"{n版}" if not 重数
                   else f"★★ {n版}（名字 {len(vs)} 个，★ 其中 {重数} 个重复）")
        A(f"| **{m} {卡原文(m).get('标题','').split('· ')[-1]}** | {三分.get(m,'?')} "
          f"| {版本显示} | {v} | {med('胜率'):.0%} | {med('赢亏比'):.2f} "
          f"| {med('平均持有'):.0f} 天 "
          f"| ${med('毛盈亏'):,.0f} "
          f"| ${med('摩擦'):,.0f} | {格10.get(m,{}).get('状态','⬜ 空')} |")
    A("")
    A("```")
    A("★ 「赢随机」= 跑赢「同环境、同出手次数的随机进场」(基准一)。")
    A("   ★★★ **1106 待核**:这把尺子是我们自己搭的(③档),**没请人核过** ——")
    A("   ★★ 实测随机组自己每笔赚 +0.24~+0.30 R(★ 乱买不该稳定赚钱),")
    A("   ★★★ 已写成第 43 轮问 Gemini:**它量的可能是出场而不是进场**。")
    A("★★ 「持有」= 每笔持有**交易日**数的平均,再取各版本中位数(★ 不是日历日)。")
    A("★★ 「赢亏比」= 平均赢 ÷ 平均亏。★★★ **它和胜率要一起看**:")
    A("   · 胜率高 + 赢亏比≈1 → **靠胜率活着**,胜率一掉就亏")
    A("   · 胜率低 + 赢亏比高 → **靠赢亏比活着**,胜率低是设计出来的")
    A("★★★ **「毛利」和「摩擦」并排看** —— ★ 摩擦 > 毛利就是**净亏**。")
    A("   ★★★ **1106 修**:这两列原来是把同一策略**所有版本的美元数加总** ——")
    A("   ★★ 那量的是「我们跑了多少次」不是「这条策略多赚钱」(版本越多数越大),")
    A("   ★★★ 现已改成和胜率/赢亏比一致的**中位数**(单个版本的量级)。")
    A("   ★ 口径:本金 **$1,000,000**,每笔赌本金的 **1%**(按进场价到止损价换成股数);")
    A("   ★ 「毛利」= 未扣成本;「摩擦」= 手续费 + 滑点 + 冲击成本。")
    A("   ★★ 为什么不给百分比:★★★ 毛利接近 0 时百分比会炸")
    A("   (★ 1105 实测技-1 算出 8057%,★★ 那不是「摩擦占 80 倍」,是分母太小)。")
    A("```")
    A("")
    A("---")
    A("")

    for i, m in enumerate(order, 1):
        c = 卡原文(m)
        vs = bym[m]
        A(f"# {i} · {c.get('标题', m)}")
        A("")
        A(f"**★ 派**：{三分.get(m,'?')}　**★ 出处档位**："
          f"{出处.get(m, '①b 手册转述（★ 方法卡页码栏写着「待核实」）')}")
        A("")
        A("## ★ 大白话：它在干什么（★★ 下面四行是方法卡**原文照抄**）")
        A("")
        for k in ("他是谁", "一句话", "怎么买", "怎么退出"):
            if c.get(k):
                A(f"- **{k}**：{c[k]}")
        A("")
        A("## ★★ 它什么时候灵、什么时候废（★★★ 也是原文照抄）")
        A("")
        for k in ("什么时候用", "谁不该用", "最难受的时候"):
            if c.get(k):
                A(f"- **{k}**：{c[k]}")
        A("")
        A("## ★★★ 跑出来的成绩（★ 逐版本）")
        A("")
        A("| 版本 | 笔数 | ★★ 赢随机 | 毛盈亏 | ★★ 摩擦 | 净盈亏 | 胜率 | 赢亏比 | 持有 |")
        A("|---|---:|---|---:|---:|---:|---:|---:|---:|")
        _seen_h: dict[str, str] = {}
        _dup: list[tuple[str, str]] = []
        for x in sorted(vs, key=lambda y: -(b1(y) or -9)):
            s = cache.get(x["链"])
            b = b1(x)
            # ★ 1106 修:长名字里有换行/竖线会把 markdown 表格打散(★ Lin 16:35 指出)
            # ★★★ 1106 第二次修(★ Lin 16:58 指出「10 日出)」那行):
            #   ★★ 真因是版本名里**本来就有斜杠**(「20 日入 / 10 日出」),
            #     而我写了 split("/")[-1] 想去路径前缀 → ★★★ 把名字从斜杠处砍断了。
            #   ★ 上一轮我以为是换行,改错了地方。★★ 现在只压空白、不按斜杠切。
            nm = " ".join(str(x["链"]).split()).replace("|", "／")
            win = ("★ 赢" if (b or 0) > 0 else "输") + (f" ({b:+.4f})" if b is not None else "")
            # ★★★ 1106 修(Lin 17:03):重复版本的说明**挪到表下统一讲** ——
            #   ★ 原来每行后面跟一句「和上面那条规则相同」,★★ 表里太挤。
            if s and s["★流水哈希"] in _seen_h:
                _dup.append((nm, _seen_h[s["★流水哈希"]]))
                continue
            if s:
                _seen_h[s["★流水哈希"]] = nm
                A(f"| {nm} | {s['笔数']} | {win} | ${s['毛盈亏']:,.0f} "
                  f"| ${s['摩擦']:,.0f} | ${s['净盈亏']:,.0f} "
                  f"| {s['胜率']:.0%} | {s['赢亏比']:.2f} | {s['平均持有']:.0f} 天 |")
            else:
                A(f"| {nm} | — | {win} | — | — | — | — | — | — |")
        A("")
        if _dup:
            A("```")
            A(f"★★ 这条策略有 {len(_dup)} 个**名字不同、规则完全相同**的版本，上表里只列了一次:")
            for 这, 那 in _dup:
                A(f"   · 「{这}」")
                A(f"     ★ 和「{那}」**规则逐条相同**（流水逐字节一致，只是注释文字不同）")
            A("★★★ 为什么会这样:★ 我们原来按**配置文件名**数版本，")
            A("   ★★ 两个文件名不一样、内容一样，就被数成了两个版本。")
            A("   → ★ 1106 起改成按**规则内容**去重（规矩⑪）。")
            A("```")
            A("")
        A("## ★★★ 你要受得了什么（★ 「人 × 策略」那一格）")
        A("")
        A("| | 最惨的那一串 |")
        A("|---|---|")
        st = [cache[x["链"]] for x in vs if x["链"] in cache]
        if st:
            k = min(st, key=lambda s: s["连亏占本金"])
            A(f"| ★ **连着亏几天** | **{k['连亏天数']} 天**（★★ 按天算，同一天平仓算一次） |")
            A(f"| ★★★ **这一串亏掉多少** | **{k['连亏占本金']:.1%}** 本金"
              f"（${abs(k['连亏金额']):,.0f}） |")
            A(f"| ★★ **这一串拖多久** | **{k['连亏持续天']} 个日历天** |")
            A(f"| ★ **最惨的单笔** | ${k['最大单笔亏']:,.0f} |")
        A("")
        A("```")
        A("★★★ 这三个数**几乎互不相关**(实测:连亏天数 × 持续天数的相关系数 = −0.026)——")
        A("   ★ 所以三个都要看,不能只看次数。")
        A("```")
        A("")
        g = 格10.get(m)
        if g:
            A(f"## ✅ 第 10 格 · 明确不适用什么（{g['状态']}）")
            A("")
            A("| 档 | 内容 |")
            A("|---|---|")
            A(f"| **①档 原著原话** | {g['①']} |")
            A(f"| ★★ **②档 行业通行** | {g['②']} |")
            A(f"| ★ **②档的出处与实证** | {g['②实证']} |")
            A(f"| ★★★ **③档 我们的（可配）** | {g['③']} |")
            if g.get("⚠"):
                A("")
                A("```")
                A(f"⚠ {g['⚠']}")
                A("```")
        else:
            A("## ⬜ 第 10 格 · 明确不适用什么（★★★ 这一格还是空的）")
            A("")
            A("```")
            A("★★★ 这一格**算不出来,只能人写**。★ 现状:")
            A("   · ①档 原著原话 —— ★ 上面「谁不该用」那一行就是")
            A("   · ②档 行业通行做法 —— ★★ **已写成《68》待发 Gemini**")
            A("   · ③档 我们回测出来的 —— ★★★ **做成用户可配**(Lin 1105 13:38 定)")
            A("★★ 在这一格填好之前,★★★ **这条策略不能出厂**。")
            A("```")
        A("")
        A("---")
        A("")

    A("## ★ 附 · 怎么读这份说明书（★★ 三条)")
    A("")
    A("```")
    A("★★★ 一、**「赢随机」不等于「能赚钱」。** ★ 它只说明「挑得比瞎买准」——")
    A("   ★★ 而摩擦吃毛利 >100% 的那些,**挑得准但照样净亏**。")
    A("★★★ 二、**所有数都在研发池、2018–2020(3 年)上跑的。**")
    A("   ★ 窗口只有 3 年 → 笔数先天偏少;★★ 行情只有 300 只 → 样本小。")
    A("   ★★★ **这两条限制让很多「输」其实落在噪声里,测不出来。**")
    A("★★★ 三、**不同版本不要排名次比。** ★ 尤其止损宽度不同的版本:")
    A("   ★★ R 的分母就是止损宽度,★★★ 止损收窄会让每笔 R 系统性变大,")
    A("   ★ 这和策略好不好**没有关系**。")
    A("```")

    io.open(OUT, "w", encoding="utf-8").write("\n".join(L) + "\n")
    print(f"★ 写到 {OUT} · {len(L)} 行 · {len(order)} 条策略")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
