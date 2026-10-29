"""
三流派 —— 应用专家 2026-10-29 **第二轮**裁决之后的重跑。

================================ 三秒版 ================================
三条链各改了一件事,三件都是专家第二轮裁决:

  ★ 流派二 VCP        成交量门禁只留门禁1(突破日不再有任何成交量条件)
  ★ 流派三 流动性猎杀  摆动波谷 = Connors 滚动 20 日绝对低点 + ★ 4 天存活门禁
                      —— ★ 这是它**第一次能跑**
  ★ 流派一 深度价值    进场拆成双阶段状态机 + F-Score 三层修补
                      —— ★ Altman Z'' 兜底阈值 1.80 / 1.10 **两版并列跑**

每条:slots 三档并列 · 全套输出(两条基准线 / Bootstrap 判据 /
两窗口两池子硬关 / 代价 / 执行负荷 / 摩擦三档 / 分步归因 / 跳空穿透)

跑法:python -m engine.run_second_round_1029            # 三条全跑
      python -m engine.run_second_round_1029 two       # 只跑流派二
      python -m engine.run_second_round_1029 three
      python -m engine.run_second_round_1029 one
=========================================================================

★ 硬纪律落点(九条,逐条对应):
  1 预热 2016 / 2018-01-01 起计绩效     → data.PERF_START,引擎写死
  2 Bootstrap + 经验 p + 效应量          → stats_gate,★ 全程不取随机分布最大值
  3 随机对照同环境取样                   → window_pool 每格内取样
  4 吊灯不高于当根收盘;胜率>60% 或每笔>+0.5R 停下来查 → 本脚本打征兆警报
  5 全池含退市股;退市结算按证据(null≠0) → cache/delisting_gate
  6 ★ 不许网格搜索                       → slots/摩擦三档是并列敏感度,
                                          留一法只定位瓶颈、不上报成绩;
                                          ★ Z'' 1.80 vs 1.10 是「来源存疑所以两版并列」,
                                          ★ 不是在挑好看的那个
  7 拿不到就说拿不到                     → 显式关掉的东西全列进报告
  8 总笔数 < 150 → 顶部强制警示          → analyze.sample_size_banner
  9 ★ 两版比较不许只看总收益              → compare_two_versions() 同时报
                                          每笔 R / 笔数 / 胜率
"""

from __future__ import annotations

import copy
import json
import os
import sys
import time

import numpy as np
import pandas as pd
import yaml

from . import (analyze, cache, chain, data, fundamentals, matrices,
               ops_1029, stats_gate)
from .run_batch import _num, signal_funnel, window_pool_gate

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(HERE, "configs")
OUT_JSON = os.path.join(HERE, "results_1029_三流派第二轮.json")
LEDGER_DIR = os.path.join(HERE, "ledgers_1029_第二轮")

# ★ 专家给的预期量级 —— 跑完必须对照,写进每一档结果
VCP_EXPECT_SIGNALS = 246          # ★ 第二轮他给的信号数
VCP_EXPECT_TRADES = (150, 185)    # ★ 10 槽位约束下八年成交笔数

#: ★ 占位排序(不是策略的一部分)—— 专家三轮没给流派一的排序规则
PLACEHOLDER_RANKING = {
    "primary": {"formula": "ADV20", "order": "desc"},
    "tiebreak": "symbol",
    "source": "★ 占位排序(不是策略的一部分)—— 专家三轮未给流派一的排序规则。"
              "选 ADV20 的理由:PIT 干净、覆盖率 100%,不会让「有基本面数据的票」"
              "系统性排在前面。★ 槽位不够时买哪几只由它决定,结论对它敏感。",
}


def _load(name: str) -> dict:
    # ★★ 用严格加载器:YAML 重复 key 直接报错,不许静默取最后一个。
    #   ★ 本轮踩过一次 —— deep_value.yaml 里旧 F-Score 闸门的 enabled 写了两次
    #     (false 在前、true 在后),于是旧闸门一直在和三层修补版 AND 在一起跑,
    #     把修补的效果整个抵消掉了。详见 ops_1029 里那一段注释。
    return ops_1029.load_yaml_strict(os.path.join(CONFIG_DIR, name))


# ================================================================ 流派二

def _vcp_base_1029() -> tuple[dict, list[str]]:
    """
    流派二第二轮版。★ 只改一件事(门禁2 已在配置里改成 null),
    另外沿用前两批就有的两处「显式关掉」—— ★ 不是本轮新关的。
    """
    raw = _load("vcp_momentum.yaml")
    notes: list[str] = []

    for r in raw["universe"]["rules"]:
        for c in (r.get("components") or []):
            if (c.get("type") == "mansfield_rs_positive"
                    and str((c.get("params") or {}).get("against")) == "SECTOR"):
                c["enabled"] = False
    notes.append(
        "★ 关掉了「宏观基底_行业 RS」(★ 前两批就关着,不是本轮新关的):"
        "仓库只有 sector_classification_current_non_pit.csv(元数据自承非 PIT),"
        "用今天的行业标签跑 2016 年整段都在用未来信息;且 XLC/XLRE "
        "在 2016–2018 根本没数据。审计 §3-C。")

    before = len(raw["stop_trail"]["stages"])
    raw["stop_trail"]["stages"] = [s for s in raw["stop_trail"]["stages"]
                                   if s.get("action") != "rotate_out"]
    assert len(raw["stop_trail"]["stages"]) == before - 1
    notes.append(
        "★★ 关掉了 ⑤「15 日滞涨换血」(★ 前两批就关着):触发条件"
        "「备选池有新高动量信号」没有定义(审计 §2-C),不能猜。"
        "★ 换血是专家宣称的三大改进之一 —— ★ 所以这一版不是完整的这一派。")

    notes.append(
        "★★★ 本轮唯一的实质改动:★ 成交量门禁**只剩门禁1**。"
        "门禁1 = 突破前 5 天内至少有 1 天 Volume ≤ 0.60 × SMA50_Volume[t−1];"
        "★ 门禁2(突破日放量 ≥ 1.0×SMA50)★ 彻底废除 —— 突破日不再有任何成交量条件。"
        "★ 专家机制:门禁1 考核供给端枯竭(浮动筹码已离场、盘子锁死),"
        "门禁2 考核需求端暴动(当天就得放量);两者冲突 —— 筹码深度沉淀之后"
        "卖盘极度匮乏,主力只要很弱的买盘就能拉穿阻力位,"
        "★ 很多高质量爆发不在突破第一天放量,是第二三天追风资金才进来。"
        "★ 出处 Minervini (2013, Ch.10)「Contraction precedes expansion」;"
        "★ 标注:行业惯例(专家 2026-10-29 第二轮裁决)。")
    return raw, notes


def vcp_variants() -> list:
    out = []
    for s in (3, 5, 10):
        raw, notes = _vcp_base_1029()
        raw["slots"] = s
        notes = list(notes)
        if s == 10:
            notes.append("★★ 这一档是结论档(专家结论 slots=10,单票上限 10% NAV)。")
        else:
            notes.append(
                f"★ slots={s} 不是结论档(结论档是 10)。三档并列报是因为"
                f"上一批证明 slots 会翻结论的符号(流派一 3/5/10 "
                f"= −5.9% / −13.8% / +9.3%)。")
        out.append((f"流派二_VCP_只留门禁1_slots{s}", raw, notes, s == 10))
    return out


# ================================================================ 流派三

def sweep_variants() -> list:
    out = []
    for s in (5, 10, 20):
        raw = _load("liquidity_sweep.yaml")
        raw["slots"] = s
        notes = [
            "★★★ 本轮改动:★ 摆动波谷定义定版 + ★ 4 天存活门禁加回 —— "
            "★ 这条链**第一次能跑**(前两轮因为「摆动波谷」没定义,"
            "一个进场信号都出不来)。",
            "★ 波谷定义 = Connors 滚动 20 日绝对低点 "
            "SwingLow[t−1] = min(Low[t−20]…Low[t−1]);"
            "★ 明确**不复用**流派二那个 5 根 Bar 的 2-1-2 分型 —— "
            "专家理由:2-1-2 每隔 3~5 天就产生一个微观波谷,"
            "那里根本没有大规模止损盘;猎杀的必须是全市场公认的关键结构防线。",
            "★★ Age_Gate:t − t_low ≥ 4 个交易日。"
            "★ 出处已亲自核实原文 —— Connors & Raschke《Street Smarts》(1995) "
            "**Ch.4 \"Turtle Soup\", Rule 2**:\"The previous 20-day low must "
            "have occurred at least four trading sessions earlier. This is very "
            "important.\" ★ 章号/规则号/英文原文三项全对。"
            "★ 顺带纠正:配置 meta 原来写 Ch.3 是错的(Ch.3 是 Money Management)。",
            "★★ 这一版**不是完整的这一派**:② 的 HYG/LQD 信用利差闸门仍然关着"
            "(仓库没有这两只 ETF),而专家自承裸测 p ≈ 0.12、"
            "这道闸门正是「大盘环境排雷」的一半。"
            "★ 关闭期间按专家给的代偿方案:单笔风险 1.0% → 0.5%。",
            "★★ ⑤「三根K线不启动退出」显式关掉 —— 「成本区」没定义(审计 §2-N),"
            "不能猜。★ ⑤ 的另两级(站上 SMA20 保本 → 前 10 日低点跟踪)本轮补了"
            "引擎实现,现在在干活。",
            "★ 结构性偏离(不是参数问题):Connors 原版是**当日盘中**在前低上方"
            "5~10 跳挂 buy stop 成交(Rule 3),我们是**收盘确认 + 次日开盘市价进**。"
            "★ 没改成原版的理由和专家第二轮删掉「当日收盘入场」是同一条:"
            "判定含 BCL 和收盘价,必须等收盘才算得出来。★ 这个偏离会系统性让进场价更差。",
        ]
        notes.append(
            f"★★★ slots={s} —— ★ 专家到第二轮**仍然没给**流派三的持仓上限"
            f"(审计 §2-E)。★ 三档 5/10/20 **全部是我们自己填的敏感度档**,"
            f"★ 这条链**没有结论档** —— 因为定这个数的人还没定。"
            f"★ 引用任何一档的绝对收益都必须带上这句。")
        out.append((f"流派三_流动性猎杀_slots{s}", raw, notes, s == 10))
    return out


# ================================================================ 流派一

def deep_value_variants(z2_thr: float) -> list:
    out = []
    for s in (12, 15, 24):
        raw = _load("deep_value.yaml")
        for r in raw["universe"]["rules"]:
            if r.get("type") == "piotroski_f_score_three_layer":
                r["params"]["z2_fallback_threshold"] = float(z2_thr)
        raw["ranking"] = copy.deepcopy(PLACEHOLDER_RANKING)
        raw["slots"] = s
        notes = [
            "★★★ 本轮改动一:进场拆成**双阶段状态机**。"
            "原来要求**同一根 K 线**既跌破 20 日低点、又收盘站上 EMA20 —— "
            "★ 专家本轮承认这在深度价值股上几乎不可能(需要一根覆盖整个 20 日"
            "区间的巨阳线),★ 我们实测它砍掉了 98.3% 的样本。"
            "现在:第一阶段 T0 破底 + 4 天存活规则 + 当日收盘收复 → "
            "第二阶段 T0+1..T0+10 内收盘站上 EMA20 → 次日开盘进;"
            "★ 止损锚定在 Low[T0] − 0.5×ATR14[T0](不是进场那根)。",
            "★★★ 本轮改动二:F-Score **三层修补**。"
            "我们测出这道闸剔掉的票里 94.7% 是「算不出分」、只有 5.3% 是「分低」;"
            "专家确认是严重缺陷,原话「这道闸在代码里执行的不是『剔除劣质公司』,"
            "而是系统性剔除数据结构非标准的特定行业,产生极恶劣的选择性偏差」。"
            "三层 = 行业豁免(SIC 6000–6999,Altman Z'' 兜底)/ "
            "容差缩放(有效项≥7 按比例放大到 9 分制再判 ≥5)/ "
            "严重缺失降级(回退 Z''，不许直接判死刑)。",
            f"★★★ Altman Z'' 兜底阈值 = {z2_thr} —— "
            f"★ {'【来源存疑(专家自定)】专家没给出处,而 Altman 自己的分区是 '
                 '困境<1.10 / 灰区 1.10~2.60 / 安全>2.60,1.80 落在灰区正中间、来路不明'
                 if abs(z2_thr - 1.80) < 1e-9 else
                 '这一版用 Altman 自己的困境线 1.10(灰区下沿)'
                 '—— 和 1.80 那版并列报,不许只报一版'}。"
            f"★ 「有效项 ≥ 7」同样标【来源存疑(专家自定)】。",
            "★★★ 必须对专家提的反对意见(实测数据支持,不是推测):"
            "★ 第一层**是循环的、基本上跑不起来**。专家说金融/房地产不适用 "
            "F-Score、由 Altman Z'' 兜底,★ 但 Z'' 的 X1 = (流动资产−流动负债)/总资产,"
            "★★ 它需要的正是银行和 REIT **根本不报**的那两个字段 —— "
            "根因和 F-Score 算不出来完全相同。"
            "★ 实测:53 只 SIC 6000–6999 的票里只有 11 只报 CA/CL(20.8%),"
            "非金融 197 只里有 189 只报(95.9%);"
            "★ 绩效窗口内被豁免的 101,775 个格子里 Z'' 只在 11.0% 算得出来,"
            "★★ 89% 的金融格子穿过第一层之后照样被判不通过。"
            "★ 所以专家点名要修的那个偏差,★ 第一层没有修掉。",
            "★★ 出处核查:★ 「Piotroski (2001, JAR) 论文第一节明确写死样本严格剔除"
            "金融行业(SIC 6000–6999)」—— ★★ **核不实**。本轮核了原文"
            "(2000 年 4 月,JAR Vol.38 Supplement):第 1 节是引言、不含任何样本筛选;"
            "样本选择在**第 3.1 节**,口径是「COMPUSTAT 上股价与账面价值数据齐备的票,"
            "按上一财年 BM 分五组取最高那组」,14,043 个公司-年;"
            "★ 全文没有任何 SIC 码或行业剔除的句子。"
            "★★ 所以「剔除金融业」不是 Piotroski 原著 —— 严格说原著是"
            "**把金融股留在样本里的**。★ 标注一律降级为行业惯例。"
            "★ 机制本身讲得通、和我们实测对得上,但出处要改。",
            "★★ 这一版仍**不是完整的这一派**:① EV/EBITDA 排名算不出(EBITDA 覆盖率"
            "只有 13.6%)、② HYG/LQD 信用闸门仓库没有这两只 ETF、"
            "★★ ⑥ 的 EV/EBITDA 估值修复离场也算不出 —— ★ 止盈那一步被拆了,"
            "主动离场只剩 F-Score 恶化和那条**来源存疑**的 180 日时间止损。",
            "★ ①「① Altman Z'' > 1.10」那条独立闸门仍然 enabled: false(数据齐备率不够);"
            "★ 注意它和三层修补里的 Z'' 兜底不是一回事:前者是「够不够安全才买」,"
            "后者只在 F-Score 算不出时当替补。",
            "★ ③「强力收复」的强度口径专家原文仍没给。第一阶段用的是"
            "**唯一不含自由参数的机械读法**:当日最低跌破 SwingLow20、当日收盘又收回其上。"
            "★ 这是我们的读法,不是专家给的口径。",
            "★ C-1 " + PLACEHOLDER_RANKING["source"],
        ]
        tag = "★主档(配置原值 12,专家区间 12–15 的紧端)" if s == 12 else "敏感度档"
        notes.append(f"★ slots={s}({tag})。15 是区间另一端,24 是更松的一档。"
                     f"★ 三档并列,不是挑最优。")
        out.append((f"流派一_深度价值_Z{z2_thr:g}_slots{s}", raw, notes, s == 12))
    return out


# ================================================================ 跑一条链

def run_one(name: str, raw: dict, notes: list[str], is_main: bool,
            syms: list[str]) -> dict:
    t0 = time.time()
    print("=" * 78)
    print(f"跑链:{name}" + ("   ★ 主档" if is_main else ""))
    for nt in notes:
        print("  ⚠ " + nt)

    chain.reset_t0_fallback_count()
    cfg = chain.ChainConfig.from_dict(copy.deepcopy(raw))
    rep = cfg.adapt_report
    print("  " + rep.text().replace("\n", "\n  "))
    if not rep.ok:
        raise RuntimeError(
            f"{name} 还有没实现的规则,★ 不许带着它跑(悄悄忽略最危险):\n"
            + rep.text())

    funnel = signal_funnel(raw, [s for s in syms if s in cache.symbols()],
                           data.PERF_START)
    print("  [信号漏斗]")
    for r in funnel["逐关"]:
        print(f"    {r['关']:48s} 单条={r['单条']:9d} 累计={r['累计']:9d}")

    res = chain.run_chain(cfg, syms)
    os.makedirs(LEDGER_DIR, exist_ok=True)
    res.save_ledger(os.path.join(LEDGER_DIR, f"{name}.csv"))
    # ★★ 关键自检:正式链跑完,T0 止损锚点的回退次数必须是 0 ——
    #   回退路径只允许在「基准一 随机进场」和归因中间行里走。
    t0_fb_mainchain = chain.t0_fallback_count()

    n = len(res.ledger)
    banner = analyze.sample_size_banner(n)
    if banner:
        print("  " + "=" * 74)
        print("  " + banner)
        print("  " + "=" * 74)
    print(f"  笔数 {n}")

    # ★ 全套输出:两条基准线 / 判据 / 代价 / 执行负荷 / 摩擦三档 / 归因 / 跳空
    out = analyze.evaluate(cfg, res, syms, with_attribution=True,
                           with_sensitivity=True, with_gate=True)
    gate4 = window_pool_gate(cfg, syms)
    print("  " + gate4.report().replace("\n", "\n  "))

    # ★ 纪律 4:胜率 >60% 或每笔 >+0.5R → 停下来查吊灯止损那个坑
    alarm = []
    if n:
        wr = float((res.ledger["net_pnl"] > 0).mean())
        rbar = float(res.ledger["r_multiple"].mean())
        if wr > 0.60 or rbar > 0.5:
            alarm.append(f"★★ 征兆警报:胜率 {wr:.1%} / 每笔R {rbar:+.3f} —— "
                         f"吊灯止损那个坑必须复查")
        print("  出场原因分布:" + ", ".join(
            f"{k}={v}" for k, v in res.ledger["reason"].value_counts().items()))
    for a in alarm:
        print("  " + a)

    rec = {
        "链名": name,
        "★是否主档": is_main,
        "slots": int((cfg.get("sizing") or {}).get("params", {})
                     .get("max_positions", 0)),
        "★必须讲清楚的前提": notes,
        "适配层报告": rep.text(),
        "笔数": n,
        "★过没过纪律8的150底线": ("过了" if n >= stats_gate.SYSTEM_MIN_TRADES
                                  else f"★★ 没过(n={n} < "
                                       f"{stats_gate.SYSTEM_MIN_TRADES})"),
        "★样本不足警示": banner,
        "信号漏斗": funnel,
        "出场原因分布": ({str(k): int(v) for k, v in
                          res.ledger["reason"].value_counts().items()} if n else {}),
        "绝对表现": _num(out["绝对表现"]),
        "坑一_现金拖累": _num(out["坑一_现金拖累"]),
        "坑二_跳空穿透止损": _num(out["坑二_跳空穿透止损"]),
        "代价": _num(out["代价"]),
        "执行负荷": _num(out["执行负荷"]),
        "摩擦成本": _num(out["摩擦成本"]),
        "基准一_同环境随机进场": _num(out["基准一_同环境随机进场"]),
        "基准二_同等仓位大盘": _num(out["基准二_同等仓位大盘"]),
        "判据_三套对照组": _num(out["判据"]),
        "★两窗口两池子硬关": _num(gate4),
        "分步归因": _num(out.get("分步归因")),
        "坑四_摩擦敏感度": _num(out.get("坑四_摩擦敏感度")),
        "征兆警报": alarm,
        "引擎显式关掉的东西": matrices.disabled_log(),
        "★实现口径里我们自己做的选择": ops_1029.notes(),
        "★T0止损锚点回退次数_正式链": t0_fb_mainchain,
        "★T0止损锚点回退次数_含基准与归因": chain.t0_fallback_count(),
        "★T0回退怎么读": (
            "★ 正式链那个数**必须是 0** —— 状态机吐信号的同时就写了 T0 锚点,"
            "所以正式链每个进场日都有锚点。"
            "★ 第二个数 > 0 是预期的:「基准一 随机进场」和分步归因中间行"
            "把 ③ 换掉了,没有第一阶段、也就没有 T0 锚点,"
            "它们回退到「同一个 0.5×ATR14 公式、锚在自己的信号根上」。"
            "★★ 所以基准一和正式链的止损锚点**不是同一根 K 线**:"
            "方向上正式链的锚点(T0 的低点)通常更低 → 止损更宽、每笔 R 的分母更大。"
            "★ 这个差别对基准一的比较是**不利于正式链**的方向吗?不一定 —— "
            "止损更宽同时意味着更不容易被打掉,所以方向不单一,★ 只能如实标明、"
            "不许声称基准一是完全同口径的。"),
        "耗时秒": round(time.time() - t0, 1),
    }
    # ★★ 纪律 9 要的三个数,单独拎出来,不许只看总收益
    if n:
        led = res.ledger
        rec["★纪律9_三个必看的数"] = {
            "笔数": n,
            "每笔R(毛)": round(float(led["r_multiple"].mean()), 4),
            "胜率": round(float((led["net_pnl"] > 0).mean()), 4),
        }
    print(analyze.format_report(out))
    print(f"  (用了 {rec['耗时秒']} 秒)")
    return rec


def compare_two_versions(chains: list[dict], tag_a: str, tag_b: str) -> dict:
    """
    ★★ 纪律 9:两版比较**不许只看总收益**,要看每笔 R / 笔数 / 胜率。
    这里把同 slots 的两版摆在一起。
    """
    rows = []
    for c in chains:
        nm = c.get("链名", "")
        if tag_a not in nm and tag_b not in nm:
            continue
        rows.append({
            "链名": nm,
            "版本": tag_a if tag_a in nm else tag_b,
            "slots": c.get("slots"),
            "笔数": c.get("笔数"),
            "每笔R(毛)": (c.get("★纪律9_三个必看的数") or {}).get("每笔R(毛)"),
            "胜率": (c.get("★纪律9_三个必看的数") or {}).get("胜率"),
            "净收益": ((c.get("绝对表现") or {}) or {}).get("总收益_净")
                      or ((c.get("绝对表现") or {}) or {}).get("总收益(净)"),
        })
    return {
        "★口径": "★★ 纪律 9:两版比较不许只看总收益 —— 笔数 / 每笔 R / 胜率 "
                  "三个数必须同时摆出来。总收益受 slots 和单票上限的影响很大,"
                  "单看它会把「门槛松了多买了几笔」误读成「挑得更准」。",
        "逐行": rows,
    }


# ================================================================ main

def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    want = {a for a in argv if a in ("two", "three", "one")} or {"two", "three", "one"}

    print(data.cohort_report())
    print()
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    have_f = [s for s in syms if data.load_manifest()[s].fundamentals_path]
    print(f"全池 {len(syms)} 只,其中有 fundamentals.json 的 {len(have_f)} 只 —— "
          f"★ 另外 {len(syms) - len(have_f)} 只(pilot_50 那一批)"
          f"任何基本面闸门都按「看不到数据 = 不合格」永久判出局。")
    print(f"绩效窗口 {data.PERF_START} .. {data.PERF_END}(2016 起热机)")
    print()

    out = {
        "跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "全池只数": len(syms),
        "★有基本面数据的只数": len(have_f),
        "绩效窗口": f"{data.PERF_START} .. {data.PERF_END}(2016 起热机)",
        "★本轮应用的第二轮裁决": {
            "流派二": "★ 彻底废除门禁2(突破日放量 ≥1.0×SMA50),只保留门禁1"
                      "(突破前 5 天内至少 1 天 Volume ≤ 0.60×SMA50[t−1])。"
                      "★ 突破日不再有任何成交量条件。"
                      "机制:门禁1 考核供给端枯竭、门禁2 考核需求端暴动,两者冲突 —— "
                      "筹码深度沉淀后卖盘极度匮乏,很多高质量爆发不在突破第一天放量。"
                      "出处 Minervini (2013, Ch.10);标注 行业惯例(专家 1029 第二轮)。",
            "流派三": "★ 摆动波谷 = Connors 滚动 20 日绝对低点(★ 不复用流派二的"
                      "2-1-2 分型)+ ★ 4 天存活门禁 Age_Gate t−t_low ≥ 4。"
                      "★ 这条链第一次能跑。",
            "流派一": "★ 进场拆双阶段状态机(T0 触底排毒 → 10 日内 EMA20 收复),"
                      "止损锚定 Low[T0] − 0.5×ATR14[T0];"
                      "★ F-Score 三层修补(行业豁免 / 容差缩放 / 严重缺失降级),"
                      "★ Z'' 兜底阈值 1.80 与 1.10 两版并列跑。",
        },
        "★出处核查_本轮两处": {
            "Connors 4 天规则": {
                "专家标的": "Connors & Raschke《Street Smarts》(1995) Ch.4 "
                            "Turtle Soup, Rule 2;英文原文 \"The previous 20-day low "
                            "must have occurred at least four trading sessions earlier.\"",
                "核查结果": "★★ 核实了,一字不差。章号 Ch.4 对(Turtle Soup 确在 Ch.4,"
                            "Ch.3 是 Money Management)、规则号 Rule 2 对、"
                            "英文原文对(原书还多一句 \"This is very important.\")。"
                            "★ 这是专家本轮**标对**的一处。"
                            "★ 顺带纠正:liquidity_sweep.yaml 的 meta 原来写 Ch.3,已改。",
                "结论": "★ 可以标「原著写死」。",
            },
            "Piotroski 剔除金融行业": {
                "专家标的": "Piotroski (2001, JAR) 论文**第一节**明确写死:"
                            "样本严格剔除金融行业(SIC 6000–6999)。",
                "核查结果": "★★ **核不实**,三项全错:"
                            "① 年份是 **2000 年 4 月**(JAR Vol.38 Supplement),不是 2001;"
                            "② 第 1 节是**引言**,不含任何样本筛选条件 —— "
                            "样本选择在**第 3.1 节**;"
                            "③ ★★ 全文**没有任何** SIC 码或行业剔除的句子。"
                            "第 3.1 节的口径是「COMPUSTAT 上股价与账面价值数据齐备的票,"
                            "按上一财年 BM 分五组取最高那组」,14,043 个公司-年(1976–1996)。"
                            "★ 严格说原著是**把金融股留在样本里的**。",
                "结论": "★ 标注降级为「行业惯例」。★ 机制本身讲得通"
                        "(金融企业的流动资产/应收/经营现金流和工商业不是一个概念)、"
                        "而且和我们实测的 94.7% 完全对得上 —— ★ 但不许说这是原著写死的。",
            },
        },
        "硬纪律落点": {
            "预热": "2016 起热机,2018-01-01 才计入绩效(Fama 1998)",
            "退市破产按−100%": sorted(
                s for s in syms if data.load_manifest()[s].is_bankruptcy),
            "拆股8根": "6 根已按比例修正,2 根(AMRS/PRTY)判不准、整只剔除",
            "网格搜索": "★ 没有。slots 三档 / 摩擦三档都是并列报的敏感度;"
                        "★ Z'' 1.80 vs 1.10 两版并列是因为 1.80 来源存疑,"
                        "★ 不是在挑好看的那一个。",
        },
        "链": [],
    }

    # ★ F-Score 三层修补的分流统计 —— 两个阈值都记下来
    print("=" * 78)
    print("★ 先把 F-Score 三层修补的分流统计跑出来(两个 Z'' 阈值都要)")
    fstat = {}
    for thr in (1.80, 1.10):
        _, _, st = ops_1029.f_score_three_layer(have_f, z2_threshold=thr)
        fstat[f"Z''阈值{thr:g}"] = st
        print(f"  --- Z'' 阈值 {thr} ---")
        for k, v in st.items():
            print(f"    {k}: {v}")
    out["★F-Score三层修补_分流统计"] = fstat
    print()

    variants = []
    if "two" in want:
        variants += vcp_variants()
    if "three" in want:
        variants += sweep_variants()
    if "one" in want:
        variants += deep_value_variants(1.80)
        variants += deep_value_variants(1.10)

    for name, raw, notes, is_main in variants:
        try:
            out["链"].append(run_one(name, raw, notes, is_main, syms))
        except Exception as e:
            import traceback
            traceback.print_exc()
            print(f"★ {name} 跑挂了:{type(e).__name__}: {e}")
            out["链"].append({"链名": name, "★跑挂了": f"{type(e).__name__}: {e}",
                              "★必须讲清楚的前提": notes})
        # ★ 边跑边落盘 —— 容器重启过一次,不许把半天的结果攒在内存里
        with open(OUT_JSON, "w", encoding="utf-8") as fh:
            json.dump(out, fh, ensure_ascii=False, indent=2, default=str)

    # ★ 流派二对专家预期的对照
    vcp10 = next((c for c in out["链"]
                  if c.get("链名", "").startswith("流派二")
                  and c.get("链名", "").endswith("slots10")), None)
    if vcp10:
        n = vcp10.get("笔数", 0)
        lo, hi = VCP_EXPECT_TRADES
        out["★流派二_对专家预期"] = {
            "专家预期": f"{VCP_EXPECT_SIGNALS} 个信号 → 10 槽位约束下八年成交 {lo}~{hi} 笔",
            "实际成交笔数(slots=10)": n,
            "年均": round(n / 8.0, 1) if n else 0,
            "对照": ("★ 落在专家预期区间内" if lo <= n <= hi
                     else f"★ 不在预期区间内(差 {n - lo:+d} / {n - hi:+d} 笔)"),
        }

    # ★★ 纪律 9:Z'' 两版并列比较
    if "one" in want:
        out["★流派一_Z1.80_vs_Z1.10"] = compare_two_versions(
            out["链"], "Z1.8", "Z1.1")

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2, default=str)
    print()
    print(f"原始数字已写:{OUT_JSON}")
    print(f"交易流水已写:{LEDGER_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
