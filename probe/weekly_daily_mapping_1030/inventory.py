"""
★★ 盘点:全库每一个数值阈值,原著在什么尺度上说的 / 代码在什么尺度上算的 / 对不对得上。

三秒版:730 个数值阈值,一个一个登记成甲(确认对不上)/ 乙(可疑)/ 丙(没问题)。
        ★★★ 没登记的会 raise —— 「没查」和「查了没问题」长得一样,是今天踩过的坑。

★★ 为什么必须 raise(照上一轮的做法,engine/checks/pending_registry.py 的同一条纪律):
   报告里写「我扫了全库」,如果扫漏了 50 个,报告长得和「扫完了」一模一样。
   ★ 所以这里不允许「默认丙」:每一个 (leaf 名) 都必须在下面的登记簿里有一条,
     漏一个就 raise,报告跑不出来。

★★ 已知的「同一样东西两种写法」(先读 engine/checks/four_slot_complete.py 顶部那张表):
   本轮新撞到的两处写进报告:
     ① 均线周期有四种写法:`ma` / `ma_period` / `mas`(列表) / `near_ma`
        —— 只认 `ma` 的话会漏掉 技-5 的 ma_period: 150/200 和 mas: [50,150,200]
     ② 回看期有七种写法:`lookback` / `*_lookback` / `period` / `*_period` /
        `*_bars` / `*_days` / `window`
   ★ 本文件的 LEAF_ALIASES 把这两组都列齐。

★ 本文件只读配置,不改任何东西。
跑法:python3 probe/weekly_daily_mapping_1030/inventory.py
"""

from __future__ import annotations

import glob
import json
import os
import sys
from collections import Counter, defaultdict

import yaml

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))
CONFIG_DIR = os.path.join(_REPO, "engine", "configs")
OUT = os.path.join(_HERE, "inventory_1030.json")

# 三态 —— ★ 刻意不设第四态「默认」
甲 = "甲·确认对不上"
乙 = "乙·可疑(原著没明说尺度,但方法出身是周线/月线体系)"
丙 = "丙·没问题"

# ══════════════════════════════════════════════════════════════════════════
# ★ 登记簿:leaf 名 → (判定, 原著尺度, 代码尺度, 理由)
#   ★★ 每一条都必须填。没填的在 main() 里 raise。
# ══════════════════════════════════════════════════════════════════════════

# ── 丙-1 · 尺度无关(仓位 / 成本 / 流动性 / 排序 / 比例 / R 倍数 / 价格)──────
_SCALE_FREE = """
max_weight risk_per_trade risk_per_trade_when_gate_enabled one_way_bps
high_liquidity_bps mid_liquidity_bps low_liquidity_bps slots
slots_range_other_end max_positions profit_target_r from_r to_r
unrealized_r_gt unrealized_r_between max_stop_distance_pct tight_end_other_side
min_price tick pivot_offset_abs pivot_offset_pct exclude_bottom_pct
rank_top_pct rank_bottom_pct min_percentile max_weight factor constant
min_valid_items min_count max_score min_score value X1 X2 X3 X4
gate_off_threshold z2_fallback_threshold max_drawdown_tolerance_multiplier
decay_coefficient atr_multiple stop_atr_multiple reclaim_atr_multiple
depth_min_atr depth_max_atr depth_hard_cap_atr max_distance_atr
cup_depth_min cup_depth_max handle_max_depth first_contraction_max_depth
max_pullback max_amplitude max_range_pct max_ratio dryup_day_ratio
test_vol_max_ratio vol_test_max_ratio spring_vol_min_ratio min_bcl
runup_min max_pct min_pct pct min_slope min_slope_pct max_hv_annualized_pct
min_roic_pct adx_max max_rsi rsi_low rsi_back threshold k multiple
min_contractions max_contractions count setup_count countdown
single_day_drop_pct bw_jump_max max_gap_bars min_gap_bars
""".split()

# ── 丙-2 · 原著就是日线 ────────────────────────────────────────────────────
_BOOK_IS_DAILY = {
    "lookback": ("技-1 海龟/唐奇安 20·55·60 日、技-10 的 20 日新低、"
                 "技-14 的 20 日、状-1 的 22 日 —— ★ 原著全部在日线上给",
                 "交易日", "交易日"),
    "period": ("技-12 康纳斯 RSI(2)、成交量 SMA20/50 —— 原著日线", "交易日", "交易日"),
    "fast_period": ("成交量快线 5 日 —— XING 的实现细节,日线", "交易日", "交易日"),
    "slow_period": ("成交量慢线 20/50 日 —— 日线", "交易日", "交易日"),
    "vol_slow_period": ("成交量慢线 50 日 —— 日线", "交易日", "交易日"),
    "atr_period": ("ATR(14) / ATR(20) —— Wilder 1978 原著就是日线;"
                   "★ 全库 atr_period 只有 14 和 20 两个值,★ 没有任何周线 ATR",
                   "交易日", "交易日"),
    "atr_fast": ("ATR 快线 10 日 —— 日线", "交易日", "交易日"),
    "atr_slow_ma": ("ATR 慢均 50 日 —— 日线", "交易日", "交易日"),
    "rsi_period": ("技-12 康纳斯 RSI(2) —— 原著明写 2 日 RSI;"
                   "★ 全库 rsi_period 只有 2,★ 没有周线 RSI(14)→日线 RSI(70) 这种映射",
                   "交易日", "交易日"),
    "adx_period": ("ADX(14) —— Wilder 原著日线", "交易日", "交易日"),
    "mfi_period": ("MFI(14) —— 日线", "交易日", "交易日"),
    "ema_period": ("布林中轨 EMA20 —— 原著日线", "交易日", "交易日"),
    "ema": ("技-5 米奈尔维尼 EMA10 —— ★ 原著(Minervini)用的就是**日线** 10/21 日 EMA,"
            "不是 10 周。★ 查过,不是周线被套到日线",
            "交易日", "交易日"),
    "ma": ("技-12 的 5 日线、技-14 的 20 日线、技-5 的 50/200 日线 —— 原著日线。"
           "★ 例外:ma=150 是 状-2/技-3 的 30 周线折算 → 另见甲类 ma150",
           "交易日", "交易日"),
    "ref_lag": ("技-13 TD 序列 C[t] < C[t−4] —— 狄马克原著 100% 写死,日线",
                "交易日", "交易日"),
    "cd_lag": ("技-13 TD Countdown C[t] <= L[t−2] —— 原著写死,日线", "交易日", "交易日"),
    "consecutive_days": ("技-6 达瓦斯 3 天定顶/定底 —— 原著写死,日线", "交易日", "交易日"),
    "confirm_days": ("技-6 达瓦斯箱体确认 —— 原著 3 天,日线", "交易日", "交易日"),
    "fractal_half_width": ("状-1 分形半宽 2 根 —— XING 实现,日线", "交易日", "交易日"),
    "baseline_offset_days": ("成交量基线取 t−1 —— 实现细节,日线", "交易日", "交易日"),
    "offset_days": ("同上", "交易日", "交易日"),
    "reclaim_max_bars": ("技-11 弹簧「N 根内收回」—— ★ 手册六附 6.3 明说威科夫原著"
                         "从未写过这个数,标 XING·待校准;尺度上是日线,不是周线折算",
                         "原著未给(XING 待校准)", "交易日"),
    "test_max_bars": ("同上 —— XING·待校准,日线", "原著未给(XING 待校准)", "交易日"),
    "min_box_bars": ("技-6 箱体「震荡满 N 天」—— 手册六附 6.3 明说原著完全没给,"
                     "标 XING·待校准;日线", "原著未给(XING 待校准)", "交易日"),
    "bw_jump_lookback": ("技-14 带宽跳变回看 3 日 —— XING 变体,日线", "交易日", "交易日"),
    "window": ("成交量/价格窗口 3·5·20 日 —— 日线", "交易日", "交易日"),
    "adv_period": ("ADV20 排序用 —— 执行细节,日线", "交易日", "交易日"),
    "dollar_volume_period": ("成交额中位数 63 日 —— 执行细节,日线", "交易日", "交易日"),
    "min_new_low_days": ("技-10 的 20 日新低 —— 原著日线", "交易日", "交易日"),
    "min_bars_before": ("技-10「前低至少 4 个交易日之前」—— 原著 Rule 2,日线",
                        "交易日", "交易日"),
    "days_held_lte": ("技-12 持仓 2–5 天 / 技-10 的持有上限 —— 原著日线", "交易日", "交易日"),
    "days_held_gte": ("同上", "交易日", "交易日"),
    "max_holding_days": ("技-12 的 2 日、技-10 的 20 日、长线的 180 日 —— 日线",
                         "交易日", "交易日"),
    "max_wait_days": ("进场挂单等待 10 日 —— 执行细节,日线", "交易日", "交易日"),
    "min_day_lookback": ("技-5 VCP 单日地量回看 —— Minervini 原著看**日线**极小值"
                         "(Ch.5「one or two days of extreme volume contraction」)",
                         "交易日", "交易日"),
    "from_high_lookback": ("距高点回看 20 日 —— 实现细节,日线", "交易日", "交易日"),
    "slope_lookback": ("斜率回看 20 日 —— XING 实现,日线", "交易日", "交易日"),
    "lookback_quarters": ("基本面按季 —— 财报本来就是季度口径,不涉及日/周折算",
                          "季度", "季度"),
    "quarters": ("同上", "季度", "季度"),
    "years": ("基本面按年 —— 不涉及日/周折算", "年", "年"),
    "near_ma": ("技-5 趋势模板「靠近 50 日线」—— 原著日线", "交易日", "交易日"),
    "close_above_ma": ("liquidity_sweep 的「站上 SMA20 后止损移保本」—— "
                       "20 个交易日,source 标的是行业惯例(不是原著),日线原生",
                       "行业惯例(非原著)", "交易日"),
    "setup_lookback": ("技-13 TD Risk Level 的 Setup 长度 9 —— ★ 狄马克原著写死的"
                       "「连续 9 根」,日线;手册六附 6.4 ② 明令禁止调这个参数",
                       "交易日(原著写死)", "交易日"),
    "mas": ("技-5 趋势模板 50/150/200 日线 —— ★ 原著(Minervini)明写**日线**"
            "(50-day / 150-day / 200-day MA),不是周线",
            "交易日", "交易日"),
    "bars": ("技-8 整理段 25 根 —— 见甲类 flag_min_bars 条;上界本身换算对了",
             "周(上界已按 ×5 换算)", "交易日"),
    "structure_lookback": ("技-8 的 25(跟 flag_max_bars 一致)、技-13 的 9、"
                           "技-10 的 3/5 —— ★ 技-8 那个 25 是 5 周 ×5,换算对了;"
                           "其余是日线原生", "混合(见备注)", "交易日"),
}

# ── 丙-3 · 周/月口径,★ 但代码已经真的按周/月在算(查了,没问题)────────────
_CONVERTED_OK = {
    "months": ("技-2 法伯 10 个**月**均线 —— ★★ 代码是真的按月重采样"
               "(engine/ops_a0.py:monthly_sma_state,docstring 明写"
               "「SMA 用月线收盘价 10 期,不是 200 个交易日 —— 两者不等价」)。"
               "★ 这是全库唯一一条把「原著的大周期」老老实实实现成大周期的 —— 模范案例",
               "月线", "月线(真重采样)"),
    "base_weeks": ("技-3 原著版底盘 13 周 / 9 周 —— ★ 代码走 pat6_ops."
                   "weinstein_weekly_breakout,真的在 W-FRI 周线 bar 上算",
                   "周线", "周线(真重采样)"),
    "volume_avg_weeks": ("技-3 原著版「前 4 周周均量」—— ★ 真周线", "周线", "周线(真重采样)"),
    "volume_multiple": ("技-3 原著版「≥2 倍」—— ★ 在周线口径上用,忠实",
                        "周线", "周线(真重采样)"),
    "cup_min_bars": ("技-4 杯体 ≥35 根 = 原著「7 周」× 5 ✓ 换算对了"
                     "(手册六附 6.1 ① 给的原著值是 7 周)", "周线", "交易日(×5 已换算)"),
    "cup_max_bars": ("技-4 杯体 ≤325 根 = 原著「65 周」× 5 ✓ 换算对了", "周线",
                     "交易日(×5 已换算)"),
    "handle_max_bars": ("技-4 柄长上界 25 根 —— ★ 原著没给柄长上界(只给下界 1–2 周),"
                        "25 是我们定的;尺度上和 ×5 口径一致", "原著未给上界",
                        "交易日(与 ×5 口径一致)"),
    "flag_max_bars": ("技-8 整理段上界 25 根 = 原著「5 周」× 5 ✓ 换算对了", "周线",
                      "交易日(×5 已换算)"),
    "base_min_days": ("技-4/技-5 底盘下界 15 个交易日 = 3 周 —— 和 ×5 口径一致",
                      "周线", "交易日(×5 已换算)"),
    "base_max_days": ("技-4/技-5 底盘上界 65 个交易日 = 13 周 —— 和 ×5 口径一致",
                      "周线", "交易日(×5 已换算)"),
    "base_bars": ("技-3 机械日线版底盘 63 根 = 13 周 × 5 ✓ 长度换算对了"
                  "(★ 但同一条链的**放量口径**没换算 —— 见甲类 multiple_vol_daily)",
                  "周线", "交易日(×5 已换算)"),
}

# ── 甲 · 确认对不上 ───────────────────────────────────────────────────────
_MISMATCH = {
    "handle_min_bars": {
        "判定": 甲,
        "原著尺度": "周线(至少 1–2 周)",
        "代码尺度": "交易日,值 = 3",
        "原著原文": ("手册六附 6.1 ①(引欧奈尔《How to Make Money in Stocks》4th ed. Ch.2):"
                     "「柄部持续时间:至少 1–2 周(★ 日线至少 5 个交易日)」"),
        "★问题": ("★★ 手册**自己把日线换算写出来了**(「日线至少 5 个交易日」),代码却用 3。"
                   "★ 同一个算子里 cup_min_bars 35(=7 周×5)、cup_max_bars 325(=65 周×5)、"
                   "flag/handle 上界 25 都换算对了 —— ★ 只有这一个下界没换算。"
                   "★ 这是「半边做了、半边没做」,不是整体口径选择。"),
        "影响的配置": ["技-4-原著.yaml", "技-4-原著-中值.yaml",
                       "技-4-原著-宽松端.yaml", "技-4-行业.yaml"],
        "量化": "见 quantify_results_1030.json 甲5 / impact_1030.json",
    },
    "flag_min_bars": {
        "判定": 甲,
        "原著尺度": "周线(横向整理 3 至 5 周)",
        "代码尺度": "交易日,值 = 3",
        "原著原文": ("手册六附 6.1 ②(引欧奈尔 4th ed. Ch.2 High, Tight Flag):"
                     "「4 至 8 周内上涨 100%–120%,随后横向整理 3 至 5 周」"),
        "★问题": ("★★ 上界 flag_max_bars = 25 = 5 周 × 5 ✓,下界 flag_min_bars = 3 ✗ "
                   "—— 「3 周」被直接当成「3 根」。应为 15。"
                   "★★ 另一处:技-8.yaml 的注释写「整理段长度手册也没给」,"
                   "★ 但手册六附 6.1 ② 明明给了(3 至 5 周)—— "
                   "这是「说原著没给、其实原著给了」,和阈值错是两件事,要分开记。"),
        "影响的配置": ["技-8.yaml"],
        "量化": "见 quantify_results_1030.json 甲5 / impact_1030.json",
    },
    "ma150_为30周线的折算": {
        "判定": 甲,
        "原著尺度": "周线(30 周均线)",
        "代码尺度": "交易日,值 = 150",
        "原著原文": ("手册第 400 行 / 状-2 方法卡:「长期均线 30 周(日线图用 150 日)」;"
                     "手册第 2325 行:「150 日均线(状-2 温斯坦 30 周线)」"),
        "★问题": ("★★★ 「30 周 ≈ 150 个交易日」这个折算**在真实美股日历上是错的**:"
                   "实测 627 个自然周里有 112 个 4 天周(假期),每周平均 4.81 个交易日,"
                   "★ 30 根 W-FRI 周线 bar 实际只覆盖 **144.6 个交易日**(中位 145),"
                   "不是 150 —— 差 5.4 个交易日(3.6%)。"
                   "★★ 本轮实测证明:这一个 5.4 天的折算误差**就是**"
                   "「周线领先日线 96.2%」那个现象的全部来源(见 mechanism_1030.json)。"),
        "影响的配置": ["状-2(engine/state_axis_tri_1029.py 的 STAGE_VERSIONS)",
                       "技-3-原著.yaml(exit close_below_ma ma:150)",
                       "技-3-原著-机械日线.yaml", "技-3-原著-底盘9周.yaml",
                       "技-3-XING.yaml", "技-3-行业.yaml"],
        "量化": "见 mechanism_1030.json ③④",
    },
    "multiple_vol_daily_技3机械日线": {
        "判定": 甲,
        "原著尺度": "周线(本周累计量 vs 前几周周均量)",
        "代码尺度": "交易日(单日量 vs SMA50 日均量)",
        "原著原文": ("Weinstein 1988 Ch.4 p.74【待核实】:「a one-week volume spike that is "
                     "at least twice the average volume of the past few weeks」"),
        "★问题": ("技-3-原著-机械日线.yaml 把「一周累计量 ≥ 2× 前几周周均量」换成"
                   "「单日量 ≥ 2.0 × SMA50(量)」。★ 配置自己已经把这件事写在注释里了"
                   "(第 64-81 行),所以这一条是**已知**的、不是本轮新发现 ——"
                   "本轮新增的只有发生率的实测数。"
                   "★★ 而且方向和任务单里记的相反,见 quantify 甲4。"),
        "影响的配置": ["技-3-原著-机械日线.yaml"],
        "量化": "见 quantify_results_1030.json 甲4",
    },
}

# ── 乙 · 可疑 ─────────────────────────────────────────────────────────────
_SUSPECT = {
    "ma_period": {
        "判定": 乙,
        "原著尺度": "没明说(技-5 趋势模板原著是日线;但 150 这个值的来历是 30 周线)",
        "代码尺度": "交易日,值 = 150 / 200",
        "★为什么可疑": ("ma_period: 150 出现在 状-2 的日线版和 技-5 的趋势模板里。"
                         "★ 技-5 的 150 日线是 Minervini 原著自己写的日线数(丙);"
                         "★ 但 状-2 的 150 是 30 周线折算来的(甲)。"
                         "★★ 同一个键名、同一个值 150,一个是丙一个是甲 —— "
                         "必须按出现的配置逐份判,不能按键名判。"
                         "★ 这正是「同一样东西两种写法」的镜像:**两样东西一种写法**。"),
    },
    "lookback_250_mansfield": {
        "判定": 乙,
        "原著尺度": "周线(状-5 相对强度 / 曼斯菲尔德 RS 原生是周线图上的指标)",
        "代码尺度": "交易日,值 = 250(cashflow_discipline.yaml 走 timeframe: weekly 分支)",
        "★为什么可疑": ("★★ engine/matrices.py:731-733 有一条 `timeframe: weekly` 分支,"
                         "它**不重采样**,只把回看期换算成 `lookback_weeks × 5`。"
                         "★ 而 cashflow_discipline.yaml:233 那条规则只写了 "
                         "`{against: SPY, timeframe: weekly}`,**没给 lookback_weeks** → "
                         "吃默认 50 × 5 = 250,和日线默认 lookback=250 **完全相同** → "
                         "★ 这个 weekly 分支目前是个**空操作**。"
                         "★★ 所以它今天没造成偏差,但它是个地雷:"
                         "任何人将来给它填一个 lookback_weeks,就会得到一个"
                         "「名义周线、实际日线 ×5」的指标,而不是真周线。"
                         "★ 全库只有这一处 ×5 折算(grep `* 5` 确认)。"),
    },
    "min_percentile_IBD_RS": {
        "判定": 乙,
        "原著尺度": "没明说周/日;但 IBD RS Rating 是**全市场分位排名**,不是相对基准收益",
        "代码尺度": "交易日 lookback 上的 rs_vs_bench",
        "★为什么可疑": ("★ 手册六附 6.2 已经把这一条登记为「口径不同,不是松紧不同」"
                         "(我们算相对基准超额,原著要全市场分位排名)。"
                         "★★ 这是**口径错**但**不是日/周尺度错** —— "
                         "本轮按任务定义不算甲类,但不能因为「不是本轮的类」就不记。"
                         "★ 已在手册六附登记,本轮只复核它还在(确认:技-4 配置仍用 "
                         "rs_vs_bench + min_percentile 80/85)。"),
    },
    "技-4_10周均线条件_整条没实现": {
        "判定": 乙,
        "原著尺度": "周线(柄必须运行在 10 周均线 ≈ 50 日均线之上)",
        "代码尺度": "★ 没有实现 —— 不是尺度错,是**条件缺失**",
        "★为什么可疑": ("手册六附 6.1 ① 列的原著五要素里有一条:"
                         "「柄必须整体落在杯体的上半部,★ 且运行在 10 周均线"
                         "(≈50 日均线)之上」。"
                         "★ engine/pat6_ops.py:_cup_one 实现了前半句"
                         "(柄高 ≥ (左唇+杯底)/2),★ 后半句「10 周均线之上」"
                         "**一行都没有**(grep 确认 _cup_one 里没有任何均线)。"
                         "★★ 这是漏装一个原著条件,方向上**放松**了形态门槛。"
                         "★ 手册已经给了换算(≈50 日),所以将来装的时候是 50,不是 10。"),
    },
}


def _flatten(o, path=""):
    if isinstance(o, dict):
        for k, v in o.items():
            here = f"{path}.{k}" if path else str(k)
            yield here, v
            yield from _flatten(v, here)
    elif isinstance(o, list):
        for i, v in enumerate(o):
            here = f"{path}[{i}]"
            yield here, v
            yield from _flatten(v, here)


def main() -> None:
    rows = []
    for p in sorted(glob.glob(os.path.join(CONFIG_DIR, "*.yaml"))):
        cfg = yaml.safe_load(open(p, encoding="utf-8")) or {}
        for path, val in _flatten(cfg):
            if isinstance(val, bool) or not isinstance(val, (int, float)):
                continue
            rows.append({"配置": os.path.basename(p), "路径": path, "值": val,
                         "leaf": path.split(".")[-1].split("[")[0]})

    leaves = sorted({r["leaf"] for r in rows})

    # ★★★ 强制登记闸 —— 漏一个就 raise
    # ★ 甲/乙 两类的登记键是「位置名」而不是裸 leaf 名(因为同一个 leaf 名可能
    #   一处是甲、一处是丙 —— 见 _SUSPECT 里 ma_period 那条)。所以这里把它们
    #   涉及的 leaf 名显式列出来参与登记闸,★ 不让它们因为改了键名而变成「漏登记」。
    _AB_LEAVES = {"handle_min_bars", "flag_min_bars", "ma_period",
                  "ma", "multiple", "lookback", "min_percentile"}
    registered = (set(_SCALE_FREE) | set(_BOOK_IS_DAILY) | set(_CONVERTED_OK)
                  | _AB_LEAVES)
    missing = [l for l in leaves if l not in registered]
    if missing:
        raise RuntimeError(
            "★★★ 强制登记闸 FAIL —— 下面这些数值阈值的 leaf 名**一条都没登记**,"
            "既没判成甲/乙,也没判成丙:\n  "
            + "\n  ".join(missing)
            + "\n★ 不许默认丙。「没查」和「查了没问题」必须分开 —— "
              "这是 2026-10-30 已经踩过的坑(上一轮因此加了 raise 强制登记)。"
              "\n★ 修法:在本文件的 _SCALE_FREE / _BOOK_IS_DAILY / _CONVERTED_OK / "
              "_MISMATCH / _SUSPECT 里给它一条。")

    # 分类统计
    verdict_of = {}
    for l in leaves:
        if l in _SCALE_FREE:
            verdict_of[l] = (丙, "尺度无关(仓位/成本/比例/R/价格)")
        elif l in _BOOK_IS_DAILY:
            verdict_of[l] = (丙, "原著就是日线:" + _BOOK_IS_DAILY[l][0])
        elif l in _CONVERTED_OK:
            verdict_of[l] = (丙, "原著是周/月线,★ 代码已正确换算或真重采样:"
                             + _CONVERTED_OK[l][0])
    # ══════════════════════════════════════════════════════════════════════
    # ★★ 位置级判定 —— 同一个 leaf 名在不同配置里可能是不同的态。
    #   ★ 这是本轮新撞到的「**两样东西一种写法**」(是「一样东西两种写法」的镜像):
    #     `ma_period: 150` 在 技-5 是原著日线(丙),在 技-3/状-2 是 30 周线折算(甲)。
    #   ★ 所以这几个 leaf 必须按「配置文件 + 值」判,不许按键名判。
    # ══════════════════════════════════════════════════════════════════════
    def position_verdict(r: dict) -> tuple[str, str]:
        f, leaf, v = r["配置"], r["leaf"], r["值"]
        if leaf == "handle_min_bars":
            return 甲, "技-4 柄长下界:原著 1–2 周(手册给了「日线至少 5 个交易日」),代码 3"
        if leaf == "flag_min_bars":
            return 甲, "技-8 整理段下界:原著 3 周(= 15 个交易日),代码 3"
        if leaf in ("ma", "ma_period", "mas"):
            if f.startswith("技-3") and (v == 150 or v == 150.0):
                return 甲, "技-3 的 150 日线 = 温斯坦 30 周线折算;★ 实测 30 周 = 144.6 个交易日,不是 150"
            return 丙, "原著就是日线(技-5 趋势模板 50/150/200 日、技-14 的 200 日、技-12 的 5 日)"
        if leaf == "multiple":
            if f == "技-3-原著-机械日线.yaml":
                return 甲, "技-3 机械日线版:原著「一周累计量 ≥2× 前几周周均量」被换成「单日量 ≥2× SMA50」"
            return 丙, "技-1 / 模板的 2.0 × ATR 跟踪止损 —— 海龟原著就是日线 ATR"
        if leaf == "lookback":
            if f == "cashflow_discipline.yaml":
                return 乙, "走 matrices.py:731 的 timeframe: weekly 分支 —— 不重采样、只 ×5;目前是空操作但是地雷"
            return 丙, "原著日线(唐奇安 20/55/60、技-10 的 20、状-1 的 22)"
        if leaf == "min_percentile":
            return 乙, "IBD RS Rating 口径问题(手册六附 6.2 已登记)—— 是口径错,不是日/周尺度错"
        return verdict_of[leaf]

    for r in rows:
        r["判定"], r["理由"] = position_verdict(r)

    cnt = Counter(v[0] for v in verdict_of.values())
    per_entry = Counter(r["判定"] for r in rows)
    # 甲/乙 的逐个位置清单(报告要逐个点名)
    甲乙清单 = [{k: r[k] for k in ("配置", "路径", "值", "判定", "理由")}
                for r in rows if r["判定"] in (甲, 乙)]

    # ★ 甲/乙 是按「具体位置」判的,不是按 leaf 名 —— 单列
    res = {
        "样本": {
            "扫到的配置份数": len({r["配置"] for r in rows}),
            "数值阈值条目数": len(rows),
            "不同的 leaf 名数": len(leaves),
            "★强制登记闸": f"通过 —— {len(leaves)} 个 leaf 名全部有登记,0 个漏登记",
        },
        "★三态统计_按leaf名": dict(cnt),
        "★三态统计_按条目数": dict(per_entry),
        "甲·确认对不上": _MISMATCH,
        "乙·可疑": _SUSPECT,
        "★甲乙的逐个位置清单(逐个点名)": 甲乙清单,
        "丙·尺度无关": {l: "仓位/成本/比例/R/价格 —— 和时间尺度无关"
                        for l in sorted(set(_SCALE_FREE) & set(leaves))},
        "丙·原著就是日线": {l: _BOOK_IS_DAILY[l][0]
                            for l in sorted(set(_BOOK_IS_DAILY) & set(leaves))},
        "丙·原著是周月线但代码已正确换算": {
            l: _CONVERTED_OK[l][0]
            for l in sorted(set(_CONVERTED_OK) & set(leaves))},
        "★不在本轮三态里但必须记的": {
            "既有闸门为什么没拦住这一类": (
                "engine/checks/time_scale_unit.py 已经有 book_unit 机制,"
                "★ 但它的 _EXEMPT 正则把 `multiple|ratio|倍|threshold|thr|pct|"
                "percent|fraction` 全部豁免了 —— "
                "★★ 而本轮的甲类全部长在这几个词上"
                "(volume_multiple / handle_min_bars 的「倍」类邻居 / atr_multiple)。"
                "★ 所以那道闸**在设计上就看不见本轮这一类错**。"
                "★ 另:全库 0 份配置写了 time_scale 块、0 份写了 book_unit —— "
                "那道闸现在在真实配置上拦下 197 处「缺声明」,全部未处理。"),
            "pending_registry 里有没有这一类": (
                "★ grep 过:engine/checks/pending_registry.yaml 的 13 条登记项里"
                "**没有任何一条**是「周线阈值套到日线」这一类。"
                "★ 最接近的是「达瓦斯箱体:离散事件规则被我们做成了百分比阈值」—— "
                "那是口径类型错,不是时间尺度错。★ 这一类目前没有登记对应物。"),
        },
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(res, fh, ensure_ascii=False, indent=1)
    print(f"★ 扫了 {res['样本']['扫到的配置份数']} 份配置、"
          f"{len(rows)} 个数值阈值、{len(leaves)} 个不同 leaf 名")
    print(f"★ 强制登记闸:{res['样本']['★强制登记闸']}")
    print(f"★ 甲类 {len(_MISMATCH)} 条、乙类 {len(_SUSPECT)} 条")
    print(f"★ 按条目数:{dict(per_entry)}")
    print(f"→ {OUT}")


if __name__ == "__main__":
    main()
