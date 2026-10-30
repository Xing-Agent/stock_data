#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 把原著声明的「使用条件」装进代码,然后重跑 —— 2026-10-30

三秒版:上一轮实测 79 个变体里 **75 个的 ② regime 在代码里是空的**
        (真 100% 的交易日)。★ 也就是说我们一直在评判一批**没装自己使用条件**
        的策略,然后把它们记成「不成立」。★★ 这一轮把条件装上,再跑一遍。

══════════════════════════════════════════════════════════════════════════
★★★ 跑法:每个变体跑**两条**,只差一件事
══════════════════════════════════════════════════════════════════════════
    甲臂「不装条件」= 大+中池真重跑            ← ★ 和上一轮 `大中_重跑` 同口径
    乙臂「装了条件」= 大+中池真重跑 + 条件向量   ← ★ 本轮新增
  ★ 两臂共用同一个 `matrices.build()` 的产物,所以差异**只剩条件这一个来源**。
  ★★ 注入点:`m.regime &= 向量`(市场级)或 `raw['entry']['rules'] += [...]`
     (个股级)—— ★★★ `engine/` 一个字符都没改(先例:engine/pool_scope.py)。

══════════════════════════════════════════════════════════════════════════
★★ 反向偏差的防线(任务单最后一条:本轮方向是「可能让策略活下来」)
══════════════════════════════════════════════════════════════════════════
  ① 甲类(原著可执行)和乙类(我们翻译)**分两套统计**,不许合并成一个「活了几条」。
  ② 条件向量在 `regime_vectors_1030.py` 里**跑之前定稿**,一个新数都没拍。
  ③ 条件成立的**时间占比**必须和成绩一起报 —— ★ 一条一年只成立两三次的条件,
     和一条常年可用的,是两种完全不同的商品。
  ④ ★★★ 不做「从几个候选条件里挑成绩最好的那个」这件事。每条方法**只装一个**
     条件,由它的方法卡原文决定装哪个,★ 不看结果。

★ 「天」一律是**交易日**。★ 报笔数一定同时报信号数。
跑法:python3 probe/regime_install_1030/run_regime_install_1030.py
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import re
import resource
import subprocess
import sys
import time

import numpy as np
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE, os.path.join(ROOT, "probe", "v2_rerun_1030")):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import (cache, chain, data, matrices, ops_exits_1029,     # noqa: E402
                    pat6_ops, pool_scope)
import rerun_core_1030 as RC                                         # noqa: E402
import regime_vectors_1030 as RV                                     # noqa: E402

CONFIG_DIR = os.path.join(ROOT, "engine", "configs")
OUT_JSON = os.path.join(HERE, "regime_install_results_1030.json")

MIN_TRADES = 30                      # ★ 上一轮口径,照抄不改
RATIO_HI, RATIO_LO = 0.9, 0.01       # ★ 同上

VARIANT_MODULES = [
    ("A0十二条", "engine.run_a0_12"),
    ("技术派六条三版", "engine.pat6_run"),
    ("批五修正", "engine.run_p5_1029"),
    ("原著离场", "engine.run_orig_exits_1029"),
    ("剔污染", "engine.run_declean_1030"),
]


# ══════════════════════════════════════════════════════════════════════════
# 一 · 每条方法装什么条件 —— ★★★ 由方法卡原文决定,不看结果
# ══════════════════════════════════════════════════════════════════════════
#
# 三态分类(任务单第一步):
#   甲 = 原著给的条件**可执行**(说了判什么 + 用谁判 + 怎么处置)
#   乙 = 原著的条件是**定性的**,要我们翻译成判据才能装 → ★ 翻译规则必须写出来
#   丙 = 原著**根本没给**可执行条件 → 直接写「原著未给出」,★ 这是有用的答案
#
# ★★ 装在哪一层也必须对:
#   市场级 → ② regime(一维,全池共用)
#   个股级 → ① universe / ③ entry   ★★★ 装错层 = 把选股条件当成大盘总开关
#
PLAN: dict[str, dict] = {
    "技-1": {
        "等级": "乙",
        "原著原文": "流动性好、方向明确的市场。强产业趋势期表现最好。",
        "层": "市场级",
        "装": "乙·牛市",
        "翻译规则": "「方向明确的市场」→ SPY>200日线 且 200日线20日斜率>0。"
                    "★「流动性好」不装:上一轮实测大+中池上 $500 万/日 的门槛"
                    "只挡 0.08%,这一条已有定论(probe/liquidity_gate_1030/)。"
                    "★「强产业趋势期表现最好」是成绩描述,不是闸门。",
    },
    "技-2": {
        "等级": "丙", "层": "—", "装": None,
        "原著原文": "完全没时间看盘的人,或作为其他策略的大盘总开关。",
        "为什么不装": "★★★ 这句话说的是「技-2 可以当别人的总开关」—— "
                      "它**自己就是**那个开关(月线收在 10 月均线之上才持有)。"
                      "原著没有给技-2 自己再套一个环境条件。→ 原著未给出。",
    },
    "技-3": {
        "等级": "丙", "层": "—", "装": None,
        "原著原文": "周线级别的中长线,适合每周看一次盘的人。",
        "为什么不装": "★★ 这是**时间尺度 + 用户画像**,不是市场环境条件。"
                      "→ 原著未给出可执行的环境条件。"
                      "★ 另:技-3 的阶段闸本身在我们数据上**未被证明有用**"
                      "(probe/stage_path_1030/),不许借本轮偷偷把它装上。",
    },
    "技-4": {
        "等级": "乙",
        "原著原文": "牛市中段,成长股领涨的阶段。",
        "层": "市场级", "装": "乙·牛市",
        "翻译规则": "「牛市」→ SPY>200日线 且 200日线20日斜率>0。"
                    "★★★「中段」和「成长股领涨」**没有翻译** —— "
                    "我们没有「牛市走到第几段」的判据,也没有风格因子。"
                    "所以这条翻译只覆盖了原文的一部分,是**宽口径代理**。",
    },
    "技-5": {
        "等级": "乙",
        "原著原文": "牛市里的强势股。适合每天收盘后花二十分钟看图的人。",
        "层": "市场级", "装": "乙·牛市",
        "翻译规则": "「牛市」同上。★「强势股」是选股条件,技-5 的 VCP + "
                    "趋势模板已经在 ③ entry 里做了,不重复装。",
        "已装部分": "★ vcp_momentum 真实链已有 regime(占 61.9% 交易日);"
                    "★★ 但 技-5-原著/行业/XING 这几份配置的 ② regime 是空的。",
    },
    "技-6": {
        "等级": "乙",
        "原著原文": "单边上涨行情。它的设计前提就是只买最强的。",
        "层": "市场级", "装": "乙·牛市",
        "翻译规则": "「单边上涨行情」→ SPY>200日线 且 200日线20日斜率>0。"
                    "★ 这是本轮翻译里**最贴**的一条(原文就是说大盘在单边涨)。",
    },
    "技-8": {
        "等级": "乙",
        "原著原文": "牛市里最强的那一小批股票。一年可能只有几次机会。",
        "层": "市场级", "装": "乙·牛市",
        "翻译规则": "「牛市」同上。★★「一年只有几次机会」**不是闸门**,"
                    "是对信号稀少的预期 —— 它恰好和实测对得上(笔数 34~37)。",
    },
    "技-9": {
        "等级": "丙", "层": "—", "装": None,
        "原著原文": "新股活跃、市场情绪好的阶段。",
        "为什么不装": "★「市场情绪好」没有任何可执行定义;「新股活跃」要 IPO "
                      "数量/首日表现序列,★★ 仓库里没有这份数据。→ 原著未给出。"
                      "★ 另:技-9 本轮也不在可重跑的变体表里。",
    },
    "技-10": {
        "等级": "甲",
        "原著原文": "【application】震荡市、宽幅箱体市。"
                    "【data_requirement】规则完全机械。但必须和市场状态判断绑定"
                    "(见 状-1、状-3),不允许在趋势市里自动触发。",
        "层": "市场级", "装": "甲·非趋势市",
        "为什么是甲": "★★★ 这句话三样都给了:判什么(趋势市/震荡市)· "
                      "用谁判(状-1)· 怎么处置(不许自动触发)。→ 可执行。",
        "今天才装得上": "状-1 的摆动点压在 zigzag_pivots 上,而那个函数的"
                        "静默返回空 2026-10-30 `023fbbf` 才修好。"
                        "★ 配置里原来写的「接不上,所以本次没装」理由已消失。",
    },
    "技-11": {
        "等级": "乙", "层": "★ 个股级(不是市场级)", "装": None,
        "原著原文": "长期横盘、成交量持续萎缩的标的。",
        "为什么不装进 regime": "★★★ 原文说的是「标的」,这是**选股**条件 "
                               "(① universe / ③ entry),不是大盘总开关。"
                               "★ 装进 ② regime 会把整条链在某些日子全关掉 —— "
                               "那是装错层。★★ 而它的个股实现(spring 的量能条件)"
                               "已经在 ③ entry 里。本轮不动。",
    },
    "技-12": {
        "等级": "甲", "层": "★ 个股级", "装": None,
        "原著原文": "【application】温和上涨但每天上下波动的市场。持仓周期通常 2–5 天。"
                    "【data_requirement】「200 日均线之上」这个前提不允许用户关掉。",
        "已装": "★★ **已经装了**:① universe 的 price_above_ma(ma: 200)。"
                "★ 实测 universe 真 37.60% 的票·交易日(上一轮 §5.2)。",
        "为什么不再装": "★ 甲类里可执行的那一句(200 日线)已经在代码里。"
                        "「温和上涨但每天上下波动」是定性的(乙),"
                        "★★★ 而它和「200 日线之上」部分重叠 —— "
                        "再叠一道牛市闸等于把同一件事装两遍,本轮不做。",
    },
    "技-13": {
        "等级": "乙",
        "原著原文": "震荡市中的拐点判断。也常被用作其他策略的辅助确认。",
        "层": "市场级", "装": "甲·非趋势市",
        "翻译规则": "「震荡市」→ 复用技-10 那条状-1 非趋势市向量(同一把尺子)。"
                    "★★★ 但**记为乙类**:技-13 的方法卡只说了「震荡市中的拐点判断」,"
                    "**没有**像技-10 那样给「不允许在趋势市自动触发」这种处置指令。"
                    "★ 条件向量和技-10 一样,出处等级不一样 —— 这两件事不许混。",
    },
    "技-14": {
        "等级": "甲", "层": "★ 个股级",
        "原著原文": "【application】震荡市,或上升趋势中的回调。和康纳斯互补。"
                    "【data_requirement】「长期趋势向上」这个前提不允许关掉。",
        "装": "甲·个股长期趋势向上",
        "为什么是甲": "★ 「长期趋势向上」+「不允许关掉」= 明确的处置指令;"
                      "★★ 现成实现就在仓库里(pat6_bb_trend_gate,"
                      "ma_period 200 + slope_lookback 20),"
                      "技-14-行业 / 技-14-行业-RSI2 已经在用。",
        "★★★ 上一轮说错的地方": "上一轮 §5.1 把技-14 整条记成「✅ 装了」。"
                                 "★ 实测:**4 份技-14 配置里只有 2 份装了**"
                                 "(行业 / 行业-RSI2,装在 ③ entry),"
                                 "★★ 技-14-XING 和 技-14-原著 **没装**。"
                                 "→ 本轮给这两份补装。",
    },
}

#: ★ 技-14 补装用的那条规则 —— 逐字照抄 技-14-行业-RSI2.yaml 的 pat6_bb_trend_gate
T14_GATE = {
    "type": "pat6_bb_trend_gate",
    "params": {"ma_period": 200, "slope_lookback": 20},
    "source": "★ 本轮补装:逐字照抄 engine/configs/技-14-行业-RSI2.yaml 的 "
              "pat6_bb_trend_gate(行业惯例)—— 一个新数都没拍。"
              "出处等级 = 甲(方法卡写「长期趋势向上这个前提不允许关掉」)",
}

#: ★★★ 「同一样东西两种写法」—— 本轮新撞的一个,差点就多装一遍。
#:   「长期趋势向上」这道闸在仓库里有**两种写法**:
#:       pat6_bb_trend_gate     = 单独一道(ma_period 200 + slope_lookback 20)
#:                                 ← 技-14-行业-RSI2 用这个
#:       pat6_bb_trend_filters  = 三道必配过滤器**打包**,里面第一道就是
#:                                 ma_period 200 + slope_lookback 20
#:                                 ← 技-14-行业 用这个
#:   ★ 只认前者的话,会在 技-14-行业 上**把同一道闸装第二遍**。
#:     实测后果:笔数 Δ=0(因为是同一个条件,叠上去等于没变)—— ★★ 结果没错,
#:     但「已装 / 本轮补装」这个标注会错,而说明书第①栏要的正是这个标注。
T14_GATE_ALIASES = ("pat6_bb_trend_gate", "pat6_bb_trend_filters")


#: ★★ 五个变体的配置名不是 `技-N-*.yaml`(是七个大师配置 / 锚点),
#:   ★ 第一版它们落进了「未分类」—— 而「未分类」和「原著没给」长得一样,
#:     ★★★ 正是今天反复踩的那一类坑。所以按配置名显式登记,一条不许留空。
YAML_PLAN: dict[str, dict] = {
    "vcp_momentum.yaml": {
        "等级": "乙", "层": "市场级", "装": None, "对应方法": "技-5",
        "原著原文": "技-5:牛市里的强势股。",
        "已装": "★★ **已经装了**:② regime 三条(index_above_ma 200 · "
                "index_ma_slope 200/20 · no_distribution_day)—— "
                "★ 实测真 61.9% 的交易日(上一轮 §5.2)。",
        "为什么不再装": "★ 本轮的乙类牛市向量**就是照抄它前两条**。"
                        "再装一遍等于把同一件事装两遍。"
                        "★★ 它反过来是本轮向量的**交叉验证**:我们的向量"
                        "(少 no_distribution_day)占比必须 ≥ 61.9% —— 实测 65.4%,对上。",
    },
    "trend_following.yaml": {
        "等级": "乙", "层": "市场级", "装": None, "对应方法": "技-1",
        "原著原文": "技-1:流动性好、方向明确的市场。",
        "已装": "★★ **已经装了**:② regime 两条(index_above_ma_scaled "
                "200×0.99 · index_ma_slope 200/20)—— 实测真 76.9% 的交易日。",
        "为什么不再装": "同上:本轮向量和它是同一把尺子的两个写法"
                        "(它第一条带 factor 0.99,容忍小幅跌破)。"
                        "★★★ 这是「同一样东西两种写法」的又一例 —— "
                        "index_above_ma 和 index_above_ma_scaled。",
    },
    "buy_and_hold.yaml": {
        "等级": "丙", "层": "—", "装": None, "对应方法": "无(锚点)",
        "原著原文": "★ 无方法卡 —— 它署名 XING,不是原著(提交 c096442 已补出处)。",
        "为什么不装": "★★ 它是流水里的一条**对照链**,不是产品选项,"
                      "更没有原著给它声明使用条件。→ 原著未给出(不适用)。",
    },
}


def method_of(yaml_name: str) -> str | None:
    m = re.match(r"^(技-\d+)", yaml_name)
    return m.group(1) if m else None


def plan_of(yaml_name: str) -> dict:
    """★ 先按配置名查(七个大师配置 / 锚点),再按 技-N 查。"""
    if yaml_name in YAML_PLAN:
        return YAML_PLAN[yaml_name]
    return PLAN.get(method_of(yaml_name) or "", {})


# ══════════════════════════════════════════════════════════════════════════
# 二 · 复用上一轮的判据件(★ 纪律 3:先搜仓库,搜到就用)
# ══════════════════════════════════════════════════════════════════════════

def _load_check(fn: str):
    p = os.path.join(ROOT, "engine", "checks", fn)
    spec = importlib.util.spec_from_file_location(fn[:-3] + "_mod", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_CONC = _load_check("concentration_degenerate.py")
_FOUR = _load_check("four_slot_complete.py")


def concentration(led) -> dict:
    return _CONC.concentration(led["net_pnl"].astype(float).tolist()
                               if len(led) else [])


def four_slot(raw: dict, name: str) -> dict:
    a = _FOUR.audit_one(raw, name)
    return {"三槽位齐全_不含加仓": a["三槽位齐全_不含加仓"],
            "止损两级都齐": a["止损两级都齐"], "空着的": a["空着的"]}


def r_validity(led) -> dict:
    if led is None or len(led) == 0:
        return {"可比": False, "原因": "无成交", "★无止损(退化成收益率)": False}
    e = led["entry_price"].astype(float).to_numpy()
    r = led["risk_per_share"].astype(float).to_numpy()
    ok = np.isfinite(e) & np.isfinite(r) & (e > 0)
    if not ok.any():
        return {"可比": False, "原因": "无有效风险距离",
                "★无止损(退化成收益率)": False}
    ratio = r[ok] / e[ok]
    hi, lo = float((ratio > RATIO_HI).mean()), float((ratio < RATIO_LO).mean())
    return {"风险距离占进场价_中位": float(np.median(ratio)),
            "比例>0.9的笔数占比": hi, "比例<0.01的笔数占比": lo,
            "★无止损(退化成收益率)": hi >= 0.5,
            "可比": (hi < 0.5) and lo < 0.5}


#: ★★ 「同一样东西两种写法」的第 N 次:集中度这个数的键名是
#:   `集中度_前10笔占总盈利`(带 TOP_N),**不是** `集中度`。
#:   ★ 上一轮的报告正文里写「集中度」,JSON 里是带后缀的键 —— 这里取一次,
#:     后面全走 `conc_value()`,不许各处再自己猜键名。
CONC_KEY = f"集中度_前{_CONC.TOP_N}笔占总盈利"


def conc_value(conc: dict):
    return conc.get(CONC_KEY)


def gates(met: dict, conc: dict, fs: dict) -> dict:
    """★ 三道硬闸,口径和上一轮 §3.1 / 附录 E **完全一致**,一个字没改。

    ★★ 集中度那道闸:退化 / 半退化 / 集中度 > 50% —— 三种都**不算过**。
      理由是闸自己写的那句:退化和半退化两档**根本读不出东西**,
      而「读不出东西」不能当成「通过」。
    """
    g1 = met["笔数"] >= MIN_TRADES
    g2 = bool(fs["三槽位齐全_不含加仓"])
    degen = bool(conc.get("★退化"))
    semi = bool(conc.get("★半退化"))
    c = conc_value(conc)
    g3 = bool((not degen) and (not semi) and c is not None and c <= 0.50)
    return {"笔数够": bool(g1), "三槽位齐": g2, "集中度闸": g3,
            "集中度档": ("退化" if degen else ("半退化" if semi else "可读")),
            "集中度值": c, "结构下限": conc.get("结构下限"),
            "★过三道硬闸": bool(g1 and g2 and g3)}


# ══════════════════════════════════════════════════════════════════════════
# 三 · 跑一个变体 × 两条臂
# ══════════════════════════════════════════════════════════════════════════

#: ★★★ 2026-10-30 本轮踩到的一个**口径坑**,记在这里:
#:   条件向量第一版是在**绩效窗口**(2018-01-02 ~ 2025-12-31,2,011 个交易日)
#:   上算的,而 `matrices.build()` 的 `m.index` 是 **2014-01-02 ~ 2025-12-31
#:   (3,018 个交易日)**。★ 把短向量 reindex 到长索引,2014–2017 全被填成 False
#:   → 乙臂等于**把前四年整个关掉**,而那不是原著的条件,是我们的对齐事故。
#:   ★★ 后果是双向的:既少算了笔数,又把「条件成立占比」报低
#:      (技-10 报成 19.75%,真值 29.64%)。
#:   ★ 修法:向量一律在 **m.index 本身**上算(下面这个带缓存的工厂),
#:     ★★ 并且报占比时也用同一条索引 —— 两处必须是同一把尺子。
_VEC_CACHE: dict = {}


def vec_for(name: str, index) -> tuple:
    key = (name, len(index), str(index[0]), str(index[-1]))
    if key not in _VEC_CACHE:
        _VEC_CACHE[key] = RV.market_vectors(index)
    return _VEC_CACHE[key][name]


def load_raw(name: str) -> dict:
    with open(os.path.join(CONFIG_DIR, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _measure(cfg, syms, m, label_arm: str) -> dict:
    res = chain.run_chain(cfg, syms, m=m)
    led = res.ledger
    met = RC.chain_metrics(led)
    return {**met,
            **RC.signal_counts(m),
            "★regime为真的交易日占比": round(float(np.asarray(m.regime).mean()), 6),
            "R可比性": r_validity(led),
            "集中度": concentration(led),
            "平均净敞口Ebar": float(res.exposure.mean()),
            "_arm": label_arm}


def run_one(label, yaml_name, override, group, syms, vecs) -> dict:
    t0 = time.time()
    mid = method_of(yaml_name)
    plan = plan_of(yaml_name)
    if not plan:
        raise RuntimeError(
            f"★★★ {yaml_name} 没有登记三态分类 —— 停下来补。"
            "「未分类」和「原著没给」长得一样,不许让它们混在一起。")
    vec_name = plan.get("装")
    # ★ 技-14 那条是个股级 —— 走 entry,不走 regime
    stock_level = (vec_name == "甲·个股长期趋势向上")

    raw0 = load_raw(yaml_name)
    if override is not None:
        raw0 = override(copy.deepcopy(raw0))

    rec: dict = {"链": label, "配置": yaml_name, "族": group, "方法": mid,
                 "条件出处等级": plan.get("等级"), "装的条件": vec_name,
                 "装在哪一层": plan.get("层"), "条件计划": plan}

    # ── 甲臂:不装条件(= 上一轮 `大中_重跑` 同口径)
    cfg_a = chain.ChainConfig.from_dict(copy.deepcopy(raw0))
    if not cfg_a.adapt_report.ok:
        rec["★跑不了"] = cfg_a.adapt_report.text()[:400]
        return rec
    m_a = matrices.build(cfg_a.raw, syms)
    RC.apply_scope(m_a, "large_mid")
    rec["四槽位"] = four_slot(cfg_a.raw, label)
    arm_a = _measure(cfg_a, syms, m_a, "不装条件")
    rec["甲臂_不装条件"] = arm_a
    rec["甲臂_闸"] = gates(arm_a, arm_a["集中度"], rec["四槽位"])

    if not vec_name:
        rec["乙臂_装了条件"] = None
        rec["★本轮没装的理由"] = plan.get("为什么不装") or plan.get(
            "为什么不再装") or plan.get("为什么不装进 regime") or "见条件计划"
        rec["耗时秒"] = round(time.time() - t0, 1)
        return rec

    # ── 乙臂:装上条件
    if stock_level:
        raw_b = copy.deepcopy(raw0)
        ent = raw_b.setdefault("entry", {}).setdefault("rules", [])
        hit = [r.get("type") for r in ent if r.get("type") in T14_GATE_ALIASES]
        if hit:
            rec["乙臂_装了条件"] = None
            rec["★本轮没装的理由"] = (
                f"★ 这份配置的 ③ entry 里**已经有**这道闸了,写法 = {hit}"
                f"(★★ 两种写法都认:{list(T14_GATE_ALIASES)})")
            rec["★甲类条件状态"] = "已装(本轮不动)"
            rec["耗时秒"] = round(time.time() - t0, 1)
            return rec
        ent.append(copy.deepcopy(T14_GATE))
        cfg_b = chain.ChainConfig.from_dict(raw_b)
        if not cfg_b.adapt_report.ok:
            rec["★乙臂跑不了"] = cfg_b.adapt_report.text()[:400]
            rec["耗时秒"] = round(time.time() - t0, 1)
            return rec
        m_b = matrices.build(cfg_b.raw, syms)
        RC.apply_scope(m_b, "large_mid")
        arm_b = _measure(cfg_b, syms, m_b, "装了条件(个股级·③entry)")
        # ★ 个股级条件的「成立占比」= 条件成立的票·交易日占比(不是交易日占比)
        u_a, u_b = int(m_a.universe.sum()), int(m_b.universe.sum())
        e_a = int((m_a.entry & m_a.universe).sum())
        e_b = int((m_b.entry & m_b.universe).sum())
        rec["条件成立占比"] = {
            "口径": "★ 个股级条件 —— 报的是「合格进场信号」被这道闸留下的比例,"
                    "不是交易日占比(两者不可混)",
            "合格进场信号_装前": e_a, "合格进场信号_装后": e_b,
            "留下比例": round(e_b / e_a, 6) if e_a else None,
            "universe票日_装前": u_a, "universe票日_装后": u_b,
        }
    else:
        # ★★ 市场级:**复用同一个 m**(run_chain 只读 m,不改它),只改 m.regime。
        #   ★ 这样两臂的 ① universe / ③ entry / 排序打分**逐元素相同**,
        #     差异只剩 ② regime 这一个来源 —— 而且省掉一次 matrices.build。
        cfg_b, m_b = cfg_a, m_a
        # ★★★ 向量在 m.index 本身上算(见上面 _VEC_CACHE 那段口径坑)
        vec, meta = vec_for(vec_name, m_b.index)
        v = vec.to_numpy(dtype=bool)
        before = float(np.asarray(m_b.regime).mean())
        m_b.regime = np.asarray(m_b.regime, dtype=bool) & v
        arm_b = _measure(cfg_b, syms, m_b, "装了条件(市场级·②regime)")
        st = RV.share_of_days(vec)
        rec["条件成立占比"] = {**st, "口径": "★ 交易日占比(不是自然日)",
                               "装前 regime 真占比": round(before, 6),
                               "装后 regime 真占比":
                                   round(float(np.asarray(m_b.regime).mean()), 6),
                               "条件元信息": meta}

    rec["乙臂_装了条件"] = arm_b
    rec["乙臂_闸"] = gates(arm_b, arm_b["集中度"], rec["四槽位"])
    a, b = arm_a, arm_b
    rec["装上之后的变化"] = {
        "笔数": (a["笔数"], b["笔数"], b["笔数"] - a["笔数"]),
        "合格进场信号": (a["合格进场信号(entry&universe)"],
                         b["合格进场信号(entry&universe)"]),
        "每笔净R": (a["每笔净R"], b["每笔净R"],
                    (b["每笔净R"] - a["每笔净R"])
                    if (a["每笔净R"] is not None and b["每笔净R"] is not None)
                    else None),
        "胜率": (a["胜率"], b["胜率"]),
        "集中度": (conc_value(a["集中度"]), conc_value(b["集中度"])),
        "★R变好了吗": ((b["每笔净R"] > a["每笔净R"])
                       if (a["每笔净R"] is not None and b["每笔净R"] is not None)
                       else None),
        "★过闸": (rec["甲臂_闸"]["★过三道硬闸"], rec["乙臂_闸"]["★过三道硬闸"]),
        "★★★活了": (not rec["甲臂_闸"]["★过三道硬闸"]
                     and rec["乙臂_闸"]["★过三道硬闸"]),
        "★★R口径活了(原过闸但R≤0 → 过闸且R>0)": bool(
            rec["甲臂_闸"]["★过三道硬闸"] and rec["乙臂_闸"]["★过三道硬闸"]
            and a["每笔净R"] is not None and b["每笔净R"] is not None
            and a["每笔净R"] <= 0 < b["每笔净R"]),
    }
    rec["耗时秒"] = round(time.time() - t0, 1)
    rec["峰值RSS_MB"] = round(_rss_mb(), 1)
    ch = rec["装上之后的变化"]
    print(f"    [{plan.get('等级')}] 不装 {a['笔数']:5d}笔 R {a['每笔净R']} | "
          f"装了 {b['笔数']:5d}笔 R {b['每笔净R']} | Δ笔 {ch['笔数'][2]:+d} "
          f"{'★★★活了' if ch['★★★活了'] else ''} | {rec['耗时秒']}s")
    return rec


# ══════════════════════════════════════════════════════════════════════════
def main() -> int:
    print(subprocess.run(["free", "-m"], capture_output=True, text=True).stdout)
    print(f"CPU 核数 {os.cpu_count()} —— ★ 串行单进程\n")

    # ★ 核对数(纪律 4)—— 直接复用上一轮的 reconcile(),不自己再写一遍
    import run_rerun_1030 as RR
    rec0 = RR.reconcile()
    for k, v in rec0["读到"].items():
        print(f"   {k:14s} 读到 {v:>8,d}  已知 {RR.KNOWN[k]:>8,d} "
              f"{'✓' if v == RR.KNOWN[k] else '✗'}")
    if rec0["对不上的"]:
        print(f"★★ 对不上:{rec0['对不上的']} —— 停下来查")
        return 2
    print("   ✓ 全部对上\n")

    pat6_ops.install()
    ops_exits_1029.install()
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    idx = data.perf_window(data.load_benchmark("SPY").index,
                           data.PERF_START, data.PERF_END)
    vecs = RV.market_vectors(idx)
    print(f"回测池 {len(syms)} 只 / 绩效窗口 {len(idx)} 个交易日\n")
    for n, (v, meta) in vecs.items():
        st = RV.share_of_days(v)
        print(f"★ 条件向量「{n}」[{meta['出处等级']}] 成立 "
              f"{st['条件成立的交易日数']}/{st['交易日总数']} 交易日 "
              f"= {st['条件成立时间占比']:.2%}")
    print()

    seen, variants = set(), []
    for batch, modname in VARIANT_MODULES:
        mod = __import__(modname, fromlist=["VARIANTS"])
        for v in getattr(mod, "VARIANTS"):
            label, yml, ov, group = v[0], v[1], v[2], v[4]
            key = (yml, id(ov) if ov else None, RR.norm_chain(label))
            if key in seen:
                continue
            seen.add(key)
            variants.append((f"{batch}/{label}", yml, ov, group))
    print(f"★ 收到 {len(variants)} 个可重跑的变体\n")

    rows, fails = [], []
    t_all = time.time()
    for i, (label, yml, ov, group) in enumerate(variants, 1):
        print("=" * 78)
        print(f"[{i}/{len(variants)}] {label}   ({yml})")
        try:
            rows.append(run_one(label, yml, ov, group, syms, vecs))
        except Exception as exc:                                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            fails.append((label, repr(exc)[:300]))
    print(f"\n★ 跑完 {round(time.time() - t_all, 1)}s,峰值 RSS "
          f"{round(_rss_mb(), 1)} MB")

    out = {
        "口径戳": pool_scope.stamp("large_mid", {
            "本轮做法": "★★★ 把原著声明的「使用条件」装进代码后重跑;"
                        "每个变体两条臂(不装条件 / 装了条件),"
                        "两臂只差条件这一个来源",
            "注入点": "市场级 → m.regime &= 向量;个股级 → raw.entry.rules 追加;"
                      "★ engine/ 一行未改",
            "绩效窗口": f"{data.PERF_START} .. {data.PERF_END}"
                        f"(交易日 {len(idx)} 天)",
            "条件向量出处": "probe/regime_install_1030/regime_vectors_1030.py"
                            "(跑前定稿,一个新数都没拍)",
            "★★★ 甲乙必须分开统计": "乙类是我们翻译的 —— 不许和甲类合并成"
                                     "「装上条件之后活了几条」这一个数",
        }),
        "核对台账": rec0,
        # ★★ 两条索引上各报一遍 —— 口径必须写明是哪一条:
        #   绩效窗口 = 2018-01-02 ~ 2025-12-31(2,011 个交易日)← 说明书口径
        #   回测索引 = m.index(2014-01-02 ~ 2025-12-31,3,018 个交易日)← 实跑口径
        "条件向量_绩效窗口口径": {
            n: {**RV.share_of_days(v), "元信息": meta}
            for n, (v, meta) in vecs.items()},
        "条件向量_实跑回测索引口径": {
            f"{n} @ {k[2][:10]}..{k[3][:10]} ({k[1]}交易日)":
                RV.share_of_days(v)
            for k, vv in _VEC_CACHE.items() for n, (v, _m) in vv.items()
            if n == k[0]},
        "三态分类表_按方法": PLAN,
        "三态分类表_按配置名(七个大师配置/锚点)": YAML_PLAN,
        "个股级条件备注": RV.STOCK_LEVEL_NOTES,
        "逐链": rows,
        "跑不了的": fails,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n→ {os.path.relpath(OUT_JSON, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
