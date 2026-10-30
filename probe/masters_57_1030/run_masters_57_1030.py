#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ ⑤ 质量复利 · ⑦ 融合大师 —— 装上原著使用条件后真跑(2026-10-30)

══════════════════════════════════════════════════════════════════════════
★★★ 三秒版
  ① ⑤ 一直被记成「卡在缺 EBIT 和长期负债」—— ★ 这个记法错了两层:
     数据 2026-10-27 就在仓库里;★★ 真正缺的是**引擎没写那三个算子**。
     算子已补在 probe/masters_57_1030/ops_q57_1030.py(运行时挂钩,engine/ 未改)。
  ② ⑦ 融合大师**在 78 条方法卡里根本没有卡** —— ★ 所以它的「原著使用条件」
     是丙类(原著未给出)。★★ 本轮的 ⑦ 是我们按 Gemini 批七 §一 的「范式一
     权限非对称分工制」搭的,★★★ 搭法是我们定的,不是原著给的,明确记乙类。
  ③ 覆盖率三分类另出一份:probe/masters_57_1030/coverage_triage_1030.py
══════════════════════════════════════════════════════════════════════════

★ 口径一律照抄上一轮 probe/regime_install_1030/,一条都没另发明:
    池子   = 大+中(rank ≤ 2000),走 rerun_core_1030.apply_scope
    条件   = regime_vectors_1030 的现成向量(★ 一个新数都没拍)
    三个数 = engine/analyze.py 的 基准一 / 基准二 / 判据(★ grep 到的现成实现)
    四道门 = 笔数≥30 · 四格符号一致(engine/window_pool.py)· Z≥1.65
             (engine/stats_gate.py)· 集中度(engine/checks/concentration_degenerate.py)
  ★★★ 四道门**只摆数,不写「不成立」** —— 策略组已定调:
     「基准不是裁判,基准是货架上另一个商品」。

★★ run_chain 被包了一层:凡是没传 m 的调用(基准一的随机链 / 四格硬关的
   每一格),★ 一律在 m 上补上「大+中池掩膜」和「条件向量」—— 否则真链在
   大+中池上跑、对照组在全池上跑,那个差值读出来是池子差异不是信号差异。

跑法:python3 probe/masters_57_1030/run_masters_57_1030.py
      python3 probe/masters_57_1030/run_masters_57_1030.py --quick   # 跳过四格硬关
"""
from __future__ import annotations

import copy
import importlib.util
import json
import os
import resource
import sys
import time

import numpy as np
import pandas as pd
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
for p in (ROOT, HERE, os.path.join(ROOT, "probe", "v2_rerun_1030"),
          os.path.join(ROOT, "probe", "regime_install_1030")):
    if p not in sys.path:
        sys.path.insert(0, p)

from engine import (analyze, cache, chain, data, matrices, pat6_ops,   # noqa: E402
                    pool_scope, stats_gate)
from engine.run_batch import _num, signal_funnel, window_pool_gate    # noqa: E402
# ★★ 排序占位:★ 直接用 engine/run_fundamental.py 里**已有**的那一份,
#   ★★★ 不重新写一个 —— 三条基本面链用的就是它,口径必须统一。
from engine.run_fundamental import PLACEHOLDER_RANKING               # noqa: E402
import rerun_core_1030 as RC                                          # noqa: E402
import regime_vectors_1030 as RV                                      # noqa: E402
import ops_q57_1030 as Q                                              # noqa: E402

CONFIG_DIR = os.path.join(ROOT, "engine", "configs")
OUT_JSON = os.path.join(HERE, "masters_57_results_1030.json")
LEDGER_DIR = os.path.join(HERE, "ledgers_1030")

MIN_TRADES = 30                 # ★ 上一轮口径,照抄不改
RATIO_HI, RATIO_LO = 0.9, 0.01  # ★ 同上
Z_MAIN = stats_gate.Z_BASIC     # ★ 主判据 Z 的线,从 engine 读,不在这里写死


def _load_check(fn: str):
    p = os.path.join(ROOT, "engine", "checks", fn)
    spec = importlib.util.spec_from_file_location(fn[:-3] + "_m57", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_CONC = _load_check("concentration_degenerate.py")
_FOUR = _load_check("four_slot_complete.py")
CONC_KEY = f"集中度_前{_CONC.TOP_N}笔占总盈利"


def conc_value(c: dict):
    return c.get(CONC_KEY)


def concentration(led) -> dict:
    return _CONC.concentration(led["net_pnl"].astype(float).tolist() if len(led) else [])


def four_slot(raw: dict, name: str) -> dict:
    a = _FOUR.audit_one(raw, name)
    return {"三槽位齐全_不含加仓": a["三槽位齐全_不含加仓"],
            "止损两级都齐": a["止损两级都齐"], "空着的": a["空着的"]}


def r_validity(led) -> dict:
    """★★ 纪律:无止损 → 1R = 进场价 → R 退化成收益率,不能和有止损的并列排序。"""
    if led is None or len(led) == 0:
        return {"可比": False, "原因": "无成交", "★无止损(退化成收益率)": False}
    e = led["entry_price"].astype(float).to_numpy()
    r = led["risk_per_share"].astype(float).to_numpy()
    ok = np.isfinite(e) & np.isfinite(r) & (e > 0)
    if not ok.any():
        return {"可比": False, "原因": "无有效风险距离", "★无止损(退化成收益率)": False}
    ratio = r[ok] / e[ok]
    hi, lo = float((ratio > RATIO_HI).mean()), float((ratio < RATIO_LO).mean())
    return {"风险距离占进场价_中位": float(np.median(ratio)),
            "比例>0.9的笔数占比": hi, "比例<0.01的笔数占比": lo,
            "★无止损(退化成收益率)": hi >= 0.5, "可比": (hi < 0.5) and lo < 0.5}


# ══════════════════════════════════════════════════════════════════════════
# 一 · run_chain 的那一层包装 —— ★ 让对照组和真链在同一个池子、同一个条件下
# ══════════════════════════════════════════════════════════════════════════

_SCOPE = "large_mid"
_VEC_NAME: str | None = None
_VEC_CACHE: dict = {}
_orig_run_chain = None
_SCOPE_DIAG: dict = {}


def _vec(name: str, index):
    key = (name, len(index), str(index[0]), str(index[-1]))
    if key not in _VEC_CACHE:
        _VEC_CACHE[key] = RV.market_vectors(index)
    return _VEC_CACHE[key][name]


def _wrapped_run_chain(cfg, symbols=None, start=data.PERF_START,
                       end=data.PERF_END, initial_equity=1_000_000.0,
                       m=None, **kw):
    if m is None:
        syms = symbols if symbols is not None else list(cache.symbols())
        m = matrices.build(cfg.raw, syms)
        d = RC.apply_scope(m, _SCOPE)
        _SCOPE_DIAG.setdefault("最近一次", d)
        if _VEC_NAME:
            v, _meta = _vec(_VEC_NAME, m.index)
            m.regime = np.asarray(m.regime, dtype=bool) & v.to_numpy(dtype=bool)
    return _orig_run_chain(cfg, symbols, start, end, initial_equity, m=m, **kw)


def install_wrapper() -> None:
    global _orig_run_chain
    if _orig_run_chain is None:
        _orig_run_chain = chain.run_chain
        chain.run_chain = _wrapped_run_chain
        analyze.chain.run_chain = _wrapped_run_chain


# ══════════════════════════════════════════════════════════════════════════
# 二 · ★★★ 原著使用条件的三态分类 —— 跑之前定稿,★ 不看结果
# ══════════════════════════════════════════════════════════════════════════
#
# ★ 口径和 probe/regime_install_1030/ 完全一致:
#     甲 = 原著给的条件**可执行**(说了判什么 + 用谁判 + 怎么处置)
#     乙 = 原著的条件是**定性的**,要我们翻译 → 翻译规则必须写出来
#     丙 = 原著**根本没给**可执行条件 → 直接写「原著未给出」
#
# ★★ 本轮新撞到的一件事,必须写在最前面:
#   任务单说方法卡有 `does_not_do` 字段(「看不了什么」)。
#   ★★★ 实测 method_capability_index.json 的 78 条卡里**没有这个字段** ——
#     35 个键里最接近的是 `data_requirement` 和 `permitted_use_from_v13`。
#     ★ 所以「看不了什么」这件事本轮只能从 data_requirement 里读。
PLAN: dict[str, dict] = {
    "⑤质量复利": {
        "对应方法卡": ["LENS-BUFFETT-MUNGER-QUALITY", "LENS-AKRE-CAPITAL",
                       "基-16 特里·史密斯", "基-20 价值与动量双因子(AQR)"],
        "等级": "丙(市场级)+ 甲(个股级 ① 三道闸)",
        "原著原文_市场级": {
            "LENS-BUFFETT-MUNGER-QUALITY": "按原 Skill 的方法要求;"
                                           "★★★ 需要策略组补结构化时限,**不擅自补阈值**",
            "LENS-AKRE-CAPITAL": "同上(逐字相同)",
            "基-16": "长期资金。检验周期以五年十年计。",
            "基-20": "作为长期底仓方法。",
        },
        "为什么市场级是丙": "★★★ 两张 LENS 卡自己写着「需要策略组补结构化时限,"
                            "不擅自补阈值」—— ★ 这是原著层**明确授权我们不要填**,"
                            "不是我们偷懒。基-16 / 基-20 给的是**时间尺度**"
                            "(五年十年 / 长期底仓),和 技-3 那条「周线级别中长线」"
                            "同类,★ 不是市场环境条件。→ 原著未给出可执行的环境条件。",
        "★ 但市场级条件其实已经装了": "★★ 和 技-N 那 75 个变体不同:"
                                       "quality_compounder.yaml 的 ② regime **不是空的** —— "
                                       "index_above_ma(SPY,200)+ index_ma_slope(200/20)+ "
                                       "vix_below(30)三条都 enabled,source 标的是「行业惯例」。"
                                       "★★★ 所以 ⑤ 从来不是「裸版」。本轮**不再叠一道牛市闸**:"
                                       "那和上一轮技-12 的处置一致(同一件事不装两遍)。",
        "甲·个股级": "★★★ ① 的三道基本面闸门(ROIC 连续 3 年 ≥15% / GP/A 池内分位 ≥80 / "
                      "净负债÷EBITDA < 2.5)+ ⑥ 的基本面否决 —— ★ 这是「盈利质量与超额"
                      "资本回报派」的**定价信仰本身**,配置自己写着「这一派就是它」。"
                      "★ 它们一直 enabled: false,理由记的是「数据算不出」——"
                      "★★ 本轮实测:数据有,是**引擎没写算子**。已补,本轮第一次装得上。",
        "本轮装什么": "装 ① 三道闸 + ⑥ 基本面否决(数值逐字照抄配置,一个新数没拍)",
    },
    "⑦融合大师": {
        "对应方法卡": ["★★★ 无 —— 78 条方法卡里没有「跨面融合」这一条"],
        "等级": "丙(方法本身)→ 乙(本轮的搭法是我们翻译的)",
        "原著原文": "★★★ 原著未给出 —— 连方法卡都没有。"
                    "★ 它在 /home/claude/贴Gemini-04 里的定义只有一行:"
                    "「基本面定方向 + 技术面定时机」。",
        "为什么还能跑": "★ 它的零件全部有出处:① 基本面选池照抄 ⑤;"
                        "②③④⑥ 技术面择时与离场**逐字照抄 engine/configs/技-4-原著.yaml**"
                        "(欧奈尔 CANSLIM)。★★ 选 技-4 的理由写在跑之前:"
                        "Gemini 批七 §一(b) 第 1 条点名 CANSLIM 是「基本面定选拔 + "
                        "技术面定时机与出场」的典范,且它的离场规则是【原著原文】"
                        "(O'Neil《How to Make Money in Stocks》4th Ed Ch.10/11)。"
                        "★★★ **不是因为它成绩好** —— 定稿在跑之前,跑完一个字没改。",
        "离场听谁的": "★★ 两条臂,出处都写明:"
                      "臂一「范式① 权限非对称分工制」= 基本面只管选池,离场 100% 技术面"
                      "(= 去掉 ⑥ 的基本面否决);"
                      "臂二「范式② 双重一票否决」= 基本面否决与技术面离场取 OR。"
                      "★ 两种范式的出处见 probe/gemini_raw/批七-大师层与跨面-原文-1029.txt,"
                      "★★★ **都是【行业普遍做法】/【原著原文】的旁证,不是原著给融合派的规定**。",
        "本轮装什么": "② 装乙·牛市(技-4 方法卡「牛市中段,成长股领涨」,"
                      "★ 翻译规则逐字照抄上一轮 regime_vectors_1030,没重新翻)",
    },
}

#: ★ 跨方法借来的那条参照 —— 基-4 格林布拉特方法卡 data_requirement 原文
JI4_EXCLUDE = {
    "type": "exclude_sic_groups",
    "params": {"exclude_financial": True, "exclude_sic2": ["49"]},
    "source": "★★★ 跨方法借来的:基-4(神奇公式)方法卡 data_requirement 原文"
              "「两个公式加一次排序。**金融股和公用事业通常要排除**。」"
              "★ 这**不是** ⑤ 自己的原著条件 —— 只作第三条参照臂,"
              "★★ 不进主结论。放进来的唯一理由:它和 1030 覆盖率三分类里的"
              "丙类(金融业方法不适用)指向同一件事,值得量一下。",
}


def load_raw(name: str) -> dict:
    with open(os.path.join(CONFIG_DIR, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _set_universe(raw: dict, types: dict) -> list[str]:
    """按 type 开/关 ① 的规则,返回动过的清单(★ 逐条打进报告)。"""
    log = []
    for r in (raw.get("universe", {}).get("rules") or []):
        t = r.get("type")
        if t in types:
            before = r.get("enabled", True)
            r["enabled"] = types[t]
            r.pop("data_missing", None)
            r.pop("audit_blocked", None)
            log.append(f"① {t}: enabled {before} → {types[t]}")
    return log


def _fix_blockers(raw: dict) -> list[str]:
    """
    ★★★ 两处「引擎没写 / 配置没定」的显式处置 —— 照 engine/run_fundamental.py
    立的规矩办:**不许悄悄忽略**,每一条原样打进报告。

      C-1 ranking 是 null(专家三轮没给)→ 用 run_fundamental 里**已有**的
          「ADV20 降序」占位排序。★ 这不是策略的一部分。
      C-2 ★★ ⑤ 移动止损第二级 `close_below_ma_trail`(>+2R 后 SMA50 收盘破位
          跟踪)**引擎没实现**(A 类:口径明确,补代码即可)。
          ★★★ 本版把这一级显式关掉 → 所以这一版**没有移动止损**,
          只有初始结构止损(局部波谷下方 0.5×ATR14)。
          ★ 不许拿 ema_trail(EMA50)顶上:EMA ≠ SMA,那是换口径,
            而且会在仓库里又造一个「同一样东西两种写法」。
    """
    log = []
    if (raw.get("ranking") or {}).get("primary") is None:
        raw["ranking"] = copy.deepcopy(PLACEHOLDER_RANKING)
        log.append("★ C-1 ranking 为 null → 用 run_fundamental.PLACEHOLDER_RANKING"
                   "(ADV20 降序,★ 明确标成「占位排序,不是策略的一部分」)")
    # ★★★ C-3 本轮撞到的一个**真的、一直在那里的 bug**(不是这一轮造的):
    #   engine/matrices.py:regime_mask() 读 ② regime 参数的方式**不统一** ——
    #       index_above_ma        读 rule["symbol"] / rule["ma"]   ← ★ 顶层,不读 params
    #       vix_below             读 rule["value"]                 ← ★ 顶层,不读 params
    #       index_ma_slope        读 rule.get("params", rule)      ← ★ params 优先
    #       index_above_ma_scaled 读 rule.get("params", rule)      ← 同上
    #   ★★ 而 quality_compounder.yaml 这三条全写在 params 里。后果两件:
    #     ① `vix_below` → KeyError: 'value' 直接炸(★ 本轮才第一次炸出来,
    #        因为 ⑤ 以前连适配层都过不了,从来没跑到 ② 这一步);
    #     ② ★★★ 更坏的那个:`index_above_ma` **不报错**,它悄悄退回默认值
    #        (SPY / 200)。★ 这份配置写的正好也是 SPY/200,所以结果对 ——
    #        ★★ 但如果配置写 ma: 150,引擎会用 200,而**没有任何人会发现**。
    #   ★ 本轮处置:把这两条的 params 抬到顶层(两种写法都写上),engine 不改。
    for r in ((raw.get("regime") or {}).get("rules") or []):
        if r.get("type") in ("index_above_ma", "vix_below") and r.get("params"):
            for k, val in r["params"].items():
                if k not in r:
                    r[k] = val
            log.append(f"★★★ C-3 ② {r['type']} 的 params 已抬到顶层 —— "
                       f"engine/matrices.py:regime_mask() 这两条**只读顶层、不读 "
                       f"params**(vix_below 会 KeyError 炸;index_above_ma 会"
                       f"**静默退回默认值 SPY/200**)。★ 这是 engine 的 bug,"
                       f"本轮绕过,已登记待办。")
    stages = ((raw.get("stop_trail") or raw.get("trailing_stop") or {})
              .get("stages") or [])
    keep, dropped = [], []
    for st in stages:
        if st.get("action") == "close_below_ma_trail":
            dropped.append(st)
        else:
            keep.append(st)
    if dropped:
        key = "stop_trail" if "stop_trail" in raw else "trailing_stop"
        raw[key]["stages"] = keep
        # ★ 键名不能叫 audit_blocked —— 适配层读那个键,会把整条链判成
        #   「定义未定,不能猜」而拒跑(★ 本轮踩过一次)。用一个它不读的键名留痕。
        raw[key]["★本轮处置"] = (
            "★★ close_below_ma_trail(>+2R 后 SMA50 收盘破位跟踪)引擎没实现 —— "
            "A 类(口径明确、补代码即可)。本版显式关掉。")
        log.append("★★ C-2 ⑤ 移动止损第二级 close_below_ma_trail 引擎没实现 → "
                   "**显式关掉**。★★★ 所以这一版没有移动止损,只有初始结构止损 —— "
                   "报告必须写明「这一版把跟踪止损拆了」。")
    return log


def _set_veto(raw: dict, on: bool) -> list[str]:
    log = []
    for r in (raw.get("exit", {}).get("rules") or []):
        if r.get("type") != "fundamental_veto":
            continue
        for c in (r.get("conditions_any") or []):
            m = c.get("metric")
            before = c.get("enabled", True)
            if m == "roic_ttm":
                c["enabled"] = on
                c.pop("data_missing", None)
                c.pop("audit_blocked", None)
                log.append(f"⑥ fundamental_veto.{m}: {before} → {on}")
            elif m == "gross_margin_yoy_bps":
                c["enabled"] = on
                log.append(f"⑥ fundamental_veto.{m}: {before} → {on}")
        if not on:
            raw["exit"]["rules"] = [x for x in raw["exit"]["rules"]
                                    if x.get("type") != "fundamental_veto"]
            log.append("⑥ ★ 整条 fundamental_veto 已移除(范式① 权限非对称:"
                       "离场 100% 技术面)")
            break
    return log


# ══════════════════════════════════════════════════════════════════════════
# 三 · 变体表 —— ★★★ 跑之前定稿
# ══════════════════════════════════════════════════════════════════════════

def variants() -> list[dict]:
    out = []

    # ───────── ⑤ 质量复利 ─────────
    # A:只开「一直都开得起来」的那道(GP/A)—— ★ 这是**对照臂**,不是产品
    a = load_raw("quality_compounder.yaml")
    log = _set_universe(a, {"roic_consecutive_above": False,
                            "net_debt_to_ebitda_below": False,
                            "gross_profit_to_assets_rank_above": True})
    log += _set_veto(a, False)
    log += _fix_blockers(a)
    out.append({"链": "⑤质量复利_A_只开GPA(对照臂)", "配置": "quality_compounder.yaml",
                "大师": "⑤", "raw": a, "装的条件": None, "改动": log,
                "说明": "★ 对照臂:① 只剩 GP/A 一道基本面闸(+ADV20),⑥ 没有基本面否决。"
                        "★★ 它**不是**这一派 —— 这一派的定价信仰是 ROIC。"})

    # B:★ 主档 —— 装齐原著三道闸 + 基本面否决
    b = load_raw("quality_compounder.yaml")
    log = _set_universe(b, {"roic_consecutive_above": True,
                            "net_debt_to_ebitda_below": True,
                            "gross_profit_to_assets_rank_above": True})
    log += _set_veto(b, True)
    log += _fix_blockers(b)
    out.append({"链": "★⑤质量复利_B_装齐原著三道闸(主档)",
                "配置": "quality_compounder.yaml", "大师": "⑤", "raw": b,
                "装的条件": None, "改动": log, "主档": True,
                "说明": "★★★ 本轮主档:ROIC 连续3年≥15% + GP/A 池内分位≥80 + "
                        "净负债÷EBITDA<2.5 + ⑥ 基本面否决(ROIC 连续两季<12% 或 "
                        "毛利率同比<−200bps)。★ 数值全部逐字照抄配置。"})

    # B-q:ROIC「12 个季度点」的严端(★ 敏感度,不是挑最优)
    bq = copy.deepcopy(b)
    for r in bq["universe"]["rules"]:
        if r.get("type") == "roic_consecutive_above":
            r.setdefault("params", {})["mode"] = "quarters"
    out.append({"链": "⑤质量复利_Bq_ROIC按12个季度点(严端敏感度)",
                "配置": "quality_compounder.yaml", "大师": "⑤", "raw": bq,
                "装的条件": None, "改动": log + ["① roic_consecutive_above.mode = quarters"],
                "说明": "★ 「过去3年连续」原文没说是 3 个年度点还是 12 个季度点 —— "
                        "两端都跑,★★ 不是挑最优。"})

    # C:★ 参照臂 —— B + 跨方法借来的「排除金融与公用事业」
    c = copy.deepcopy(b)
    c["universe"]["rules"].append(copy.deepcopy(JI4_EXCLUDE))
    out.append({"链": "⑤质量复利_C_再排除金融与公用事业(★跨方法参照臂)",
                "配置": "quality_compounder.yaml", "大师": "⑤", "raw": c,
                "装的条件": None, "改动": log + ["① 追加 exclude_sic_groups(基-4 方法卡)"],
                "说明": "★★ 参照臂,★★★ 不进主结论 —— 条件来自**另一条方法**的卡。"})

    # ───────── ⑦ 融合大师 ─────────
    # ① 基本面选池照抄 ⑤-B 的三道闸;②③④⑤⑥ 逐字照抄 技-4-原著.yaml
    t4 = load_raw("技-4-原著.yaml")
    qc = load_raw("quality_compounder.yaml")
    fund_rules = []
    for r in qc["universe"]["rules"]:
        if r.get("type") in ("adv_rank_exclude_bottom", "roic_consecutive_above",
                             "gross_profit_to_assets_rank_above",
                             "net_debt_to_ebitda_below"):
            rr = copy.deepcopy(r)
            rr["enabled"] = True
            rr.pop("data_missing", None)
            rr.pop("audit_blocked", None)
            fund_rules.append(rr)

    f1 = copy.deepcopy(t4)
    f1["universe"] = {"rules": fund_rules,
                      "source": "★ 逐字照抄 quality_compounder.yaml ① 的四条"
                                "(ADV20 + ROIC + GP/A + 净负债/EBITDA)"}
    f1["costs"] = copy.deepcopy(qc["costs"])
    f1["benchmark"] = copy.deepcopy(qc["benchmark"])
    f1["meta"] = {"name": "⑦跨面融合_范式①权限非对称",
                  "source": "★★★ 无方法卡;①=⑤ 的基本面闸,②③④⑤⑥=技-4-原著 逐字"}
    out.append({"链": "★⑦融合大师_范式①权限非对称(离场100%技术面)",
                "配置": "技-4-原著.yaml + quality_compounder.yaml①", "大师": "⑦",
                "raw": f1, "装的条件": "乙·牛市", "主档": True,
                "改动": ["① 换成 ⑤ 的四条基本面闸",
                         "costs / benchmark 用 ⑤ 的 friction_tiers"
                         "(★ 技-4 原本是一刀切 5bp —— 两套摩擦口径不可横向比,"
                         "统一到分档,见 1028 拍板第 5 条)"],
                "说明": "★ 离场只有技术面:O'Neil 8% 硬止损 + 收盘跌破 50 日线。"})

    # 臂二:再叠基本面否决(范式②双重一票否决)
    f2 = copy.deepcopy(f1)
    veto = [r for r in qc["exit"]["rules"] if r.get("type") == "fundamental_veto"]
    v2 = copy.deepcopy(veto[0])
    for cc in (v2.get("conditions_any") or []):
        cc["enabled"] = True
        cc.pop("data_missing", None)
        cc.pop("audit_blocked", None)
    f2["exit"]["rules"] = f2["exit"]["rules"] + [v2]
    f2["meta"] = {"name": "⑦跨面融合_范式②双重一票否决",
                  "source": "★ 同上,再叠 ⑤ 的 ⑥ fundamental_veto"}
    out.append({"链": "⑦融合大师_范式②双重一票否决(基本面也能卖)",
                "配置": "技-4-原著.yaml + quality_compounder.yaml①⑥", "大师": "⑦",
                "raw": f2, "装的条件": "乙·牛市",
                "改动": ["同范式①,再把 ⑤ 的 ⑥ fundamental_veto 整条加回来"],
                "说明": "★ 离场 = 技术面 OR 基本面否决。"})

    # 臂三:★ 不装 ② 牛市条件的那一版 —— 用来隔离「条件」这一个来源
    f0 = copy.deepcopy(f1)
    out.append({"链": "⑦融合大师_范式①_★不装②牛市条件(隔离臂)",
                "配置": "同范式①", "大师": "⑦", "raw": f0, "装的条件": None,
                "改动": ["★ 和范式① 只差 ② 条件这一个来源"],
                "说明": "★★ 两臂只差条件 → 差值可以直接读成「条件的效果」。"})
    return out


# ══════════════════════════════════════════════════════════════════════════
# 四 · 四道门 —— ★★★ 只摆数,不判生死
# ══════════════════════════════════════════════════════════════════════════

def four_doors(met: dict, conc: dict, fs: dict, verdict, z_main) -> dict:
    g1 = met["笔数"] >= MIN_TRADES
    degen, semi = bool(conc.get("★退化")), bool(conc.get("★半退化"))
    c = conc_value(conc)
    g4 = bool((not degen) and (not semi) and c is not None and c <= 0.50)
    cells = []
    g2 = None
    if verdict is not None:
        for cc in verdict.cells:
            cells.append({"格": cc.key, "n": cc.result.n_signal,
                          "差值": _num(cc.result.diff),
                          "Z": _num(cc.result.z_effect),
                          "p": _num(cc.result.p_empirical)})
        g2 = bool(verdict.passed)
    g3 = (None if z_main is None or not np.isfinite(z_main)
          else bool(z_main >= Z_MAIN))
    return {
        "门一_笔数≥30": {"值": met["笔数"], "过": bool(g1)},
        "门二_四格符号一致": {"过": g2, "四格": cells,
                              "说明": (verdict.reasons if verdict else
                                       "★ --quick 模式没跑")},
        "门三_主判据Z≥%.2f" % Z_MAIN: {"Z": _num(z_main), "过": g3},
        "门四_集中度": {"值": _num(c),
                        "档": ("退化" if degen else ("半退化" if semi else "可读")),
                        "过": g4, "结构下限": _num(conc.get("结构下限"))},
        "★★★ 不写结论": "四道门的阈值**全是我们自己拍的,没有一道来自原著**"
                         "(正在和 Gemini 对齐)。策略组已定调:"
                         "「基准不是裁判,基准是货架上另一个商品」——"
                         "★ 这四个数是**使用说明书**,不是及格线。",
    }


# ══════════════════════════════════════════════════════════════════════════
# 五 · ★★★ 「算不出被剔除」和「分低被剔除」必须分开统计
# ══════════════════════════════════════════════════════════════════════════
#
# ★ 1028 审计里已经点过这件事:按「看不到数据那天算不合格」,一道闸会把
#   七成的票判出局 —— ★★ **不是因为它们分低,是因为算不出分**。
#   ★★★ 混在一起会让这道闸看起来比实际有效。本轮必须把两者量开。

def gate_decomposition(syms: list[str], scope_mask) -> dict:
    """三道基本面闸,各报:可评估票日 / 达标票日 / 可评估里的达标率。"""
    out = {}
    pool_cells = int(scope_mask.sum())

    # ① ROIC 连续 3 年 ≥ 15%
    for mode in ("years", "quarters"):
        lags = [0, 4, 8] if mode == "years" else list(range(12))
        evalable = {}
        for s in syms:
            vq, e = Q.metric_q(s, "roic_ttm")
            if vq.empty:
                continue
            ok = None
            for L in lags:
                c = vq.shift(L).notna()
                ok = c if ok is None else (ok & c)
            from engine import fundamentals as F
            evalable[s] = F._to_daily(ok.astype(float), e,
                                      data.trading_calendar()).fillna(0.0) > 0.5
        ev = pd.DataFrame(evalable).reindex(
            index=data.trading_calendar(), columns=syms).fillna(False)
        ps = Q.roic_consecutive(tuple(syms), 3, 15.0, mode).reindex(
            index=ev.index, columns=syms).fillna(False)
        ev_m = (ev.to_numpy(bool) & scope_mask)
        ps_m = (ps.to_numpy(bool) & scope_mask)
        out[f"① ROIC 连续3年≥15%({mode})"] = {
            "池内票·日": pool_cells,
            "★可评估票·日(三点都算得出)": int(ev_m.sum()),
            "可评估占池内": round(float(ev_m.sum()) / pool_cells, 6),
            "★达标票·日": int(ps_m.sum()),
            "★★可评估里的达标率": (round(float(ps_m.sum()) / float(ev_m.sum()), 6)
                                   if ev_m.sum() else None),
            "★★★ 读法": "「可评估占池内」低 = 我们看不到;"
                         "「可评估里的达标率」低 = 这个门槛本身严。两件事不许混。",
        }

    # ② 净负债/EBITDA < 2.5
    nd = Q.get("net_debt_to_ebitda", syms).reindex(
        index=data.trading_calendar(), columns=syms)
    ev_m = (nd.notna().to_numpy(bool) & scope_mask)
    ps_m = ((nd < 2.5).fillna(False).to_numpy(bool) & scope_mask)
    out["② 净负债÷EBITDA < 2.5"] = {
        "池内票·日": pool_cells, "★可评估票·日": int(ev_m.sum()),
        "可评估占池内": round(float(ev_m.sum()) / pool_cells, 6),
        "★达标票·日": int(ps_m.sum()),
        "★★可评估里的达标率": (round(float(ps_m.sum()) / float(ev_m.sum()), 6)
                               if ev_m.sum() else None)}

    # ③ GP/A 池内分位 ≥ 80
    gp = Q.get("gpa_ttm", syms).reindex(index=data.trading_calendar(), columns=syms)
    pct = gp.rank(axis=1, pct=True)
    ev_m = (gp.notna().to_numpy(bool) & scope_mask)
    ps_m = ((gp.notna() & (pct >= 0.80)).to_numpy(bool) & scope_mask)
    out["③ GP/A 池内横截面分位 ≥ 80"] = {
        "池内票·日": pool_cells, "★可评估票·日": int(ev_m.sum()),
        "可评估占池内": round(float(ev_m.sum()) / pool_cells, 6),
        "★达标票·日": int(ps_m.sum()),
        "★★可评估里的达标率": (round(float(ps_m.sum()) / float(ev_m.sum()), 6)
                               if ev_m.sum() else None),
        "★ 注意": "分位闸是**池内横截面**的 —— 算不出的票不参与排名,"
                   "★★ 所以「前 20%」实际是「**算得出的那批里**的前 20%」,"
                   "覆盖率低的时候这道闸比纸面上松得多。"}
    return out


# ══════════════════════════════════════════════════════════════════════════
def run_one(v: dict, syms: list[str], quick: bool) -> dict:
    global _VEC_NAME
    t0 = time.time()
    name = v["链"]
    print("=" * 78)
    print(f"跑链:{name}")
    for x in v["改动"]:
        print("  ⚠ 改动:" + x)
    _VEC_NAME = v.get("装的条件")
    rec = {"链": name, "大师": v["大师"], "配置": v["配置"],
           "★是否主档": bool(v.get("主档")), "装的条件": _VEC_NAME,
           "★必须讲清楚的前提": [v["说明"]] + v["改动"]}

    cfg = chain.ChainConfig.from_dict(copy.deepcopy(v["raw"]))
    rep = cfg.adapt_report
    rec["适配层报告"] = rep.text()
    print("  " + (rep.text() or "(无)").replace("\n", "\n  "))
    if not rep.ok:
        rec["★跑不了"] = rep.text()
        print("  ★ 跑不了 —— 不带着没实现的规则跑")
        return rec
    rec["四槽位"] = four_slot(cfg.raw, name)

    # 条件成立占比(★ 交易日占比,和上一轮同口径)
    idx = data.perf_window(data.load_benchmark("SPY").index,
                           data.PERF_START, data.PERF_END)
    if _VEC_NAME:
        vec, meta = _vec(_VEC_NAME, idx)
        rec["条件成立占比"] = {**RV.share_of_days(vec),
                               "口径": "★ 交易日占比(不是自然日)", "条件元信息": meta}
    else:
        rec["条件成立占比"] = {"口径": "★ 本链没装市场级条件向量(见三态分类)"}

    funnel = signal_funnel(v["raw"], [s for s in syms if s in cache.symbols()],
                           data.PERF_START)
    rec["信号漏斗"] = funnel
    print("  [信号漏斗]")
    for r in funnel["逐关"]:
        print(f"    {str(r['关'])[:52]:52s} 单条={r['单条']:9d} 累计={r['累计']:9d}")

    # ★ 主链自己建一次 m,★ 这样「合格进场信号」有数可报(纪律:报笔数必须报信号数)
    m_main = matrices.build(cfg.raw, syms)
    rec["池子掩膜"] = _num(RC.apply_scope(m_main, _SCOPE))
    if _VEC_NAME:
        vv, _mt = _vec(_VEC_NAME, m_main.index)
        before = float(np.asarray(m_main.regime).mean())
        m_main.regime = np.asarray(m_main.regime, dtype=bool) & vv.to_numpy(dtype=bool)
        rec["条件成立占比"]["装前 regime 真占比"] = round(before, 6)
        rec["条件成立占比"]["装后 regime 真占比"] = round(
            float(np.asarray(m_main.regime).mean()), 6)
    res = chain.run_chain(cfg, syms, m=m_main)
    led = res.ledger
    os.makedirs(LEDGER_DIR, exist_ok=True)
    res.save_ledger(os.path.join(LEDGER_DIR, f"{name.replace('/', '_')}.csv"))
    met = RC.chain_metrics(led)
    rec.update({k: _num(x) for k, x in met.items()})
    rec.update(RC.signal_counts(m_main))
    rec["R可比性"] = _num(r_validity(led))
    conc = concentration(led)
    rec["集中度"] = _num(conc)
    rec["平均净敞口Ebar"] = _num(float(res.exposure.mean()))
    print(f"  笔数 {met['笔数']}  每笔净R {met['每笔净R']}  胜率 {met['胜率']}")
    if met["笔数"]:
        print("  出场原因:" + ", ".join(f"{k}={x}" for k, x in
                                        led["reason"].value_counts().items()))
        rec["出场原因分布"] = {str(k): int(x) for k, x in
                               led["reason"].value_counts().items()}

    out = analyze.evaluate(cfg, res, syms, with_attribution=False,
                           with_sensitivity=False, with_gate=True)
    rec["绝对表现"] = _num(out["绝对表现"])
    rec["代价"] = _num(out["代价"])
    rec["摩擦成本"] = _num(out["摩擦成本"])
    rec["基准一_同环境随机进场"] = _num(out["基准一_同环境随机进场"])
    rec["基准二_同等仓位大盘"] = _num(out["基准二_同等仓位大盘"])
    rec["判据_三套对照组"] = _num(out.get("判据"))
    z_main = None
    vd = out.get("判据")
    if vd is not None and getattr(vd, "results", None):
        r0 = vd.results.get("条件分层随机")
        if r0 is not None and np.isfinite(r0.z_effect):
            z_main = float(r0.z_effect)
    rec["★主判据Z(条件分层随机)"] = _num(z_main)

    verdict = None
    if not quick and met["笔数"] > 0:
        try:
            verdict = window_pool_gate(cfg, syms)
            print("  " + verdict.report().replace("\n", "\n  "))
        except Exception as exc:                            # noqa: BLE001
            rec["★四格跑挂了"] = repr(exc)[:300]
    rec["★四道门"] = four_doors(met, conc, rec["四槽位"], verdict, z_main)
    rec["耗时秒"] = round(time.time() - t0, 1)
    rec["峰值RSS_MB"] = round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)
    print(f"  (用了 {rec['耗时秒']}s)")
    return rec


def main(argv=None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    quick = "--quick" in argv
    only = next((a for a in argv if a in ("5", "7")), None)

    pat6_ops.install()
    Q.install()
    install_wrapper()

    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    have_f = [s for s in syms if data.load_manifest()[s].fundamentals_path]
    print(f"全池 {len(syms)} 只,其中有 fundamentals.json 的 {len(have_f)} 只")
    print(f"绩效窗口 {data.PERF_START} .. {data.PERF_END}")
    print(f"池子口径 {_SCOPE}  ★ 条件向量来自 regime_vectors_1030(现成的)")
    print()

    vs = [x for x in variants() if only is None or x["大师"].strip("⑤⑦") == "" and
          (("⑤" in x["大师"]) if only == "5" else ("⑦" in x["大师"]))] \
        if only else variants()

    # ★★★ 断点续跑(本轮逼出来的):2 核 / 8GB 上,一条链连着跑完
    #   「真链 + 基准一的 5 条随机链 + 判据重抽」之后 RSS 到 2GB+,
    #   ★ 进程被 OOM 杀掉**不留 traceback** —— 看起来像「卡住了」。
    #   ★★ 处置:**每跑完一条链就落一次盘**,并且重跑时自动跳过已经有结果的链。
    #     ★ 这样一次被杀掉只丢一条链,再跑一遍就能接上。
    done: dict = {}
    if os.path.exists(OUT_JSON):
        try:
            with open(OUT_JSON, encoding="utf-8") as fh:
                prev = json.load(fh)
            for r in (prev.get("逐链") or prev.get("★未完成_只有逐链") or []):
                if isinstance(r, dict) and r.get("链") and "★跑不了" not in r:
                    done[r["链"]] = r
        except Exception:                                   # noqa: BLE001
            done = {}
    if done:
        print(f"★ 断点续跑:已有 {len(done)} 条链的结果,本轮跳过 —— "
              f"{sorted(done)}\n")

    rows, fails = [], []
    t_all = time.time()
    for v in vs:
        if v["链"] in done:
            rows.append(done[v["链"]])
            print(f"★ 跳过(已有结果):{v['链']}")
            continue
        try:
            rows.append(run_one(v, syms, quick))
        except Exception as exc:                            # noqa: BLE001
            import traceback
            traceback.print_exc()
            fails.append((v["链"], repr(exc)[:400]))
        # ★ 每条链落一次盘
        with open(OUT_JSON, "w", encoding="utf-8") as fh:
            json.dump({"逐链": rows, "跑不了的": fails}, fh,
                      ensure_ascii=False, indent=1, default=str)
    print(f"\n★ 跑完 {round(time.time()-t_all,1)}s")

    # ★ 先把逐链结果落一次盘 —— ★★ 这样后面的闸门分解万一挂了也不丢成果
    #   (★ 本轮已经因为一个 print 的键名拼错丢过一次 437 秒的跑批)
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump({"逐链": rows, "跑不了的": fails}, fh,
                  ensure_ascii=False, indent=1, default=str)
    print(f"★ 逐链结果已先落盘:{os.path.relpath(OUT_JSON, ROOT)}")

    # ★★★ 闸门分解(算不出 vs 分低)—— 在大+中池掩膜上量
    print("\n★★★ 三道基本面闸的分解(算不出被剔除 / 分低被剔除)")
    cal = data.trading_calendar()
    perf = (cal >= pd.Timestamp(data.PERF_START)) & (cal <= pd.Timestamp(data.PERF_END))
    smask, sdiag = RC.scope_mask(have_f, cal, _SCOPE)
    smask = smask & perf[:, None]
    try:
        decomp = gate_decomposition(have_f, smask)
    except Exception as exc:                                # noqa: BLE001
        import traceback
        traceback.print_exc()
        decomp = {"★跑挂了": repr(exc)[:400]}
    for k, x in decomp.items():
        if not isinstance(x, dict):
            print(f"  {k}: {x}")
            continue
        ev = next((v for kk, v in x.items() if kk.startswith("★可评估票·日")), None)
        print(f"  {k}")
        print(f"     可评估 {ev:>9,d} / 池内 {x['池内票·日']:>9,d}"
              f" = {x['可评估占池内']:.2%}   达标 {x['★达标票·日']:>9,d}"
              f"   ★ 可评估里的达标率 {x['★★可评估里的达标率']}")

    out = {
        "★★★闸门分解_算不出vs分低": decomp,
        "口径戳": pool_scope.stamp(_SCOPE, {
            "本轮做法": "★★★ ⑤ 质量复利 / ⑦ 融合大师 —— 装上原著使用条件后真跑;"
                        "缺的五个算子补在 probe/masters_57_1030/ops_q57_1030.py"
                        "(运行时挂钩,engine/ 一字未改)",
            "绩效窗口": f"{data.PERF_START} .. {data.PERF_END}",
            "三个数的实现": "engine/analyze.py:random_entry_benchmark(基准一)/ "
                            "exposure_matched_benchmark(基准二)/ "
                            "bootstrap_on_ledger(判据)—— ★ 全是现成的,没重写",
            "四道门的实现": "笔数=本文件 MIN_TRADES=30 · 四格=engine/window_pool.py · "
                            "Z=engine/stats_gate.py Z_BASIC · "
                            "集中度=engine/checks/concentration_degenerate.py",
            "★★★ 四道门不判生死": "阈值全是我们自己拍的,没有一道来自原著",
            "run_chain包装": "★ 没传 m 的调用(基准一随机链 / 四格每一格)"
                             "一律补上大+中池掩膜和条件向量 —— "
                             "否则真链和对照组不在同一个池子里",
        }),
        "三态分类表": PLAN,
        "跨方法参照条件": JI4_EXCLUDE,
        "算子备注": Q.notes(),
        "池子掩膜诊断": _num(_SCOPE_DIAG.get("最近一次", {})),
        "逐链": rows,
        "跑不了的": fails,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n→ {os.path.relpath(OUT_JSON, ROOT)}")
    print(f"→ 流水 {os.path.relpath(LEDGER_DIR, ROOT)}/")
    return 0


if __name__ == "__main__":
    sys.exit(main())
