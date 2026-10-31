"""
pat6_make_configs —— 生成 技-3 / 技-4 / 技-5 / 技-6 / 技-11 / 技-14 的
「原著版 / 行业版 / XING版」三版配置文件。

大白话:一条形态三份配置,文件名就是 技-3-原著.yaml / 技-3-行业.yaml /
技-3-XING.yaml。这个脚本把它们写出来,★ 这样「哪个数来自哪一版」是
看文件就知道的,不是藏在某个 python 变量里。

★ 三版之间**只允许形态参数不同**。
  ① 选股范围 / ② 环境过滤 / ④⑤ 止损 / ⑥ 离场 / ⑦ 仓位 槽位 排序 成本
  —— 同一条形态的三版**完全一致**。
  ★ 为什么:纪律 11 要求「两版比较不许只看总收益」。如果三版的止损和离场
    也不一样,跑出来的差别就说不清是形态的功劳还是离场的功劳。
  ★ 代价必须写明:技-5 / 技-11 的 XING 版真实配置里是**带环境过滤**的
    (vcp_momentum 有 SPY>200MA 等三条,liquidity_sweep 有两条),
    ★ 这里为了可比把它们拿掉了 —— 所以本次的「XING版」成绩**不等于**
    那两条链的历史成绩,报告里必须这样写。

跑法:python3 -m engine.pat6_make_configs
"""

from __future__ import annotations

import os

HERE = os.path.dirname(os.path.abspath(__file__))
CFG = os.path.join(HERE, "configs")


def _tail(family: str, extra: str = "") -> str:
    return f"""
# ---------------------------------------------------------------------------
# ⑦ 仓位 / 槽位 / 排序 / 成本 / 基准 —— ★ 同一条形态的三版完全一致
# ---------------------------------------------------------------------------
sizing:
  type: risk_fraction
  params:
    risk_per_trade: 0.01
    max_positions: 10
    max_weight: 0.10
  source: 行业惯例(三版统一口径,★ 不是哪一版原著给的数)

slots: 10
source_slots: 行业惯例(三版统一,为了让三版之间只差形态参数)

ranking:
  primary:
    formula: ADV20
    order: desc
    source: 执行细节(槽位满时要有决胜规则,选了最不含观点的那个)

costs:
  one_way_bps: 5.0
  source: 行业惯例(SEC Rule 206(4)-1(d);GIPS 2020 Section 2.A)

benchmark:
  family: {family}
  component_match: large
  risk_free_annual: null
{extra}"""


_REGIME = """
# ---------------------------------------------------------------------------
# ② 环境过滤 —— ★ 三版一律留空。
#   ★ 这**不是**「原著没有」:Weinstein 和 O'Neil 都看大盘。
#   留空的理由是**可比性**:三版之间只允许形态参数不同。
#   ★ 所以本次任何一版的成绩都**不含大盘择时的贡献**,报告里必须写明。
# ---------------------------------------------------------------------------
regime:
  rules: []
  flatten_when_off: false
  source: 执行细节(三版可比性要求;★ 不是原著无此条)
"""

_UNIVERSE = """
# ---------------------------------------------------------------------------
# ① 选股范围 —— ★ 三版一律全池,不加任何闸门。
#   ★ 加一条就是我们自己发明的选股条件,会把「形态有没有用」和
#     「选股闸门有没有用」混在一起。
# ---------------------------------------------------------------------------
universe:
  rules: []
  source: 执行细节(全池照跑,★ 不加任何我们发明的闸门)
"""


# ===========================================================================
# 技-3 温斯坦阶段分析(作为交易策略)
# ===========================================================================

_J3_HEAD = """# ============================================================================
# 技-3 · 温斯坦阶段分析(作为交易策略){ver}
#
# 三秒版:一只票横了很久、30 周线不再往下、然后**放量**突破横盘区上沿 → 买。
#         跌破 30 周线(实测 ≈145 日线)就走。
#
# ★★ 本条最要紧的一件事:原著的「放量 ≥2 倍均量」是**周线口径**。
#   引文(Weinstein 1988《Secrets for Profiting in Bull and Bear Markets》
#   Ch.4 "The Buying Process", §"Volume Is a Must", p.74)【待核实】:
#     "Never trust a breakout that isn't accompanied by a significant increase
#      in volume. Either: a. a one-week volume spike that is at least twice the
#      average volume of the past few weeks, or b. a volume build-up over the
#      past 3-4 weeks that is at least twice the average volume of the past
#      several weeks, coupled with at least some increase in the breakout week."
#   ★ Weinstein 整套方法看**周线图**,所以「2 倍」是「一周累计量 vs 前几周周均量」。
#   ★ 把它机械地套成「单日量 ≥ 2×SMA50」是**换了口径**,
#     ★ 今天已经在 状-3 上撞过同一个坑(原著阈值是单根 K 线口径,
#       套到 20 根均值上导致 99.6% 输出「混合」)。
#
# ★★ 原著跑不了的一项:「长期横盘」要多久。
#   原文只有(Ch.2, p.12)【待核实】:"This base-building process can take
#   anywhere from a few months to several years." → **没有可执行阈值**。
#   ★ 本文件用的底盘长度是**我们的读法**(区间下沿「≥2~3 个月」),
#     ★ 不许当成原著写死的数。
#
# ★★ 另一项原著未写死:「上翘」。
#   原文只有 "The 30-week MA loses its downward slope and starts to flatten
#   out... and usually starts moving up shortly after breakout."【待核实】
#   → 原著版**不加这一条**(不许我们填一个斜率阈值);行业版才加。
# ============================================================================

meta:
  name: 技-3_{name}
  master: Stan Weinstein
  book: Secrets for Profiting in Bull and Bear Markets (1988)
  三版归属: {ver_tag}
  原著未给出可执行阈值的项: {blocked}
  caveat: >-
    原著是在**周线图**上做的,标的也不限于美股个股。本次跑的是 300 只美股、
    只做多。★ 原著证据不能搬过来。
"""

_J3_STOPEXIT = """
# ---------------------------------------------------------------------------
# ④ 初始止损 / ⑤ 移动止损 / ⑥ 离场 —— ★ 三版完全一致
#   止损:突破前 20 日的最低价(原著「止损放在支撑位下方」的最机械读法)
#   离场:收盘跌破 145 日线(= 30 周线,实测 144.61)—— ★ 这条是原著自己的(阶段四)
# ---------------------------------------------------------------------------
initial_stop:
  type: lowest_low
  params: { lookback: 20 }
  source: 执行细节(原著说「止损放在支撑位下方」,没给几日;20 日是三版统一口径)

trailing_stop:
  type: none
  source: 执行细节(三版统一不设移动止损,免得把形态的功劳和跟踪止损的功劳混在一起)

exit:
  rules:
    - type: close_below_ma
      params: { ma: 145 }
      source: 原著(跌破 30 周线 = 进入阶段四;★ 30 根周线实测覆盖 144.61 个交易日(中位 145)—— 旧值 150 是我们换算错了,2026-10-31 修正)
  params:
    profit_target_r: null
    time_stop_days: null
  fill: next_open
  source: 原著(温斯坦不设固定止盈)
"""


def j3(ver: str, name: str, ver_tag: str, blocked: str, entry: str) -> str:
    return (_J3_HEAD.format(ver=ver, name=name, ver_tag=ver_tag, blocked=blocked)
            + _UNIVERSE + _REGIME + entry + _J3_STOPEXIT + _tail("trend"))


J3_ORIG_WEEKLY = j3(
    " · 原著版(★ 忠实周线版)", "原著版_忠实周线",
    "原著版(放量口径忠实于原著 = 周线)",
    "「长期横盘」时长(原文只有 a few months to several years);「上翘」斜率",
    """
# ---------------------------------------------------------------------------
# ③ 进场扳机 —— ★★ 忠实周线版
#   周线收盘 > 前 13 根周线的最高价(底盘上沿,周线口径)
#   且 本周累计成交量 ≥ 2.0 × 前 4 周的周成交量均值
# ★ 信号只挂在该周**最后一个交易日**(那一刻周线那根才完整),次日开盘成交。
# ---------------------------------------------------------------------------
entry:
  rules:
    - type: pat6_weinstein_weekly_breakout
      params:
        base_weeks: 13
        volume_multiple: 2.0
        volume_avg_weeks: 4
        require_volume: true
      source: >-
        放量 2.0 倍 + 「前几周」取 4 周 = 原著(Ch.4 p.74)【待核实】;
        ★ base_weeks: 13(≈3 个月)是**我们的读法** —— 原著只说
        "a few months to several years",没有可执行阈值。
  signal_freeze: close
  fill: next_open
  source: 执行细节(原著在周线图上盘中突破即买;引擎只能周末收盘确认、次日开盘)
""")

J3_ORIG_WEEKLY_9W = j3(
    " · 原著版(忠实周线 · 底盘下沿 2 个月)", "原著版_忠实周线_底盘9周",
    "原著版(底盘取区间下沿 2 个月)",
    "同上;本档把底盘取到「2 个月」这一端",
    """
entry:
  rules:
    - type: pat6_weinstein_weekly_breakout
      params:
        base_weeks: 9
        volume_multiple: 2.0
        volume_avg_weeks: 4
        require_volume: true
      source: >-
        放量 2.0 倍 = 原著【待核实】;★ base_weeks: 9(≈2 个月)是**我们的读法**
        的区间下沿 —— 跑它是为了看「底盘长度」这个我们自己填的数
        对结论有多大影响。
  signal_freeze: close
  fill: next_open
  source: 执行细节
""")

J3_ORIG_DAILY = j3(
    " · 原著版(★ 机械日线版 —— 直接套用会怎样)", "原著版_机械日线",
    "原著版·机械日线对照(★ 口径被换掉了)",
    "同上",
    """
# ---------------------------------------------------------------------------
# ③ 进场扳机 —— ★★ 机械日线版(对照组,不是忠实复现)
#   把原著的「一周累计量 ≥ 2 倍前几周周均量」机械地换成
#   「单日量 ≥ 2.0 × SMA50(量)」,底盘换成 63 个交易日(≈13 周,和周线版同长)。
#   ★ 这一版存在的唯一目的:量出「直接套用原著数字、但换了口径」会差多少。
#   ★ 不许把这一版的成绩当成温斯坦原著的成绩。
# ---------------------------------------------------------------------------
entry:
  rules:
    - type: pat6_daily_base_breakout
      params: { base_bars: 63 }
      source: 执行细节(63 个交易日 ≈ 13 周,和忠实周线版同长,★ 为了可比)
    - type: pat6_volume_x_sma
      params:
        period: 50
        multiple: 2.0
        baseline_offset_days: 1
      source: >-
        ★★ 口径已被换掉:倍数 2.0 来自原著,但原著问的是「一周累计量 vs
        前几周周均量」,这里问的是「单日量 vs 50 日均量」。
        ★ 这不是原著,是「直接套用」的对照。
  signal_freeze: close
  fill: next_open
  source: 执行细节
""")

J3_IND = j3(
    " · 行业版", "行业版", "行业版",
    "不适用(行业版本来就是后人补的阈值)",
    """
# ---------------------------------------------------------------------------
# ③ 进场扳机 —— 行业版
#   横盘 ≥30 个交易日(专家给 30~60,取 30)
#   放量 1.30 × SMA50(专家给 1.30~1.80,★ 三端都跑,本文件是严格端的那一端)
#   上翘 = 150 日 SMA 的 20 日变化率 ≥ 0
# ---------------------------------------------------------------------------
entry:
  rules:
    - type: pat6_daily_base_breakout
      params: { base_bars: 30 }
      source: 行业惯例(横盘 ≥30~60 个交易日,取 30)
    - type: pat6_volume_x_sma
      params:
        period: 50
        multiple: 1.30
        baseline_offset_days: 1
      source: 行业惯例(1.30~1.80 × SMA50;本文件 = 区间严格端。★ 三端都跑)
    - type: pat6_ma_slope_up
      params:
        ma_period: 150
        slope_lookback: 20
        min_slope_pct: 0.0
      source: 行业惯例(150 日 SMA 的 20 日变化率 ≥0 = 「不再往下」的量化读法)
  signal_freeze: close
  fill: next_open
  source: 行业惯例
""")

J3_XING = j3(
    " · XING版", "XING版", "XING版",
    "不适用",
    """
# ---------------------------------------------------------------------------
# ③ 进场扳机 —— XING版
# ★★ 必须如实交代:**我们从来没有为 技-3 单独建过配置**。
#   这一版是用仓库里现有的写法拼出来的:
#     · 箱体 =「近 25 根 (max(High) − min(Low)) / mean(Close) ≤ 0.20」
#       —— 出自 engine/state_axis_tri_1029.py 里 状-2 行业版的箱体实现
#     · 上翘 = SMA150 的 20 日变化率 ≥0 —— 同一处
#     · 放量 = ★ **没有**。我们现有的突破类配置里没有放量确认。
#       ★ 这本身就是一个发现:XING 版把原著写得最死的那一条(放量 ≥2 倍)丢了。
# ---------------------------------------------------------------------------
entry:
  rules:
    - type: pat6_narrow_box_breakout
      params:
        bars: 25
        max_range_pct: 0.20
      source: >-
        XING 现有写法(state_axis_tri_1029.py 状-2 行业版箱体实现:
        近 25 根收盘/高低点区间收窄到 20%)
    - type: pat6_ma_slope_up
      params:
        ma_period: 150
        slope_lookback: 20
        min_slope_pct: 0.0
      source: XING 现有写法(同上)
  signal_freeze: close
  fill: next_open
  source: XING版
""")


# ===========================================================================
# 技-4 欧奈尔 CANSLIM 杯柄
# ===========================================================================

_J4_HEAD = """# ============================================================================
# 技-4 · 欧奈尔 CANSLIM 杯柄{ver}
#
# 三秒版:股价先走出一个「杯子」(深跌 12~33% 再爬回来),右边再缩出一个
#         小「柄」(回落不超过 12%),然后放量突破柄部最高点 → 买。
#
# ★ 这一条原著写得最死,专家给了全部引文(O'Neil《How to Make Money in
#   Stocks》4th ed. 2009, Ch.2 "The Cup with Handle", p.59-66)【全部待核实】:
#   · 杯深:"The usual percentage correction from the absolute peak to the low
#     point of the price pattern varies from 12% or 15% to 33%... A few can
#     correct up to 40% to 50% in severe bear markets."
#   · 柄深:"The handle's downward price drift should generally be contained
#     within 8% to 12%... Handles that correct more than 12% to 15% have a
#     higher rate of failure."
#   · 杯长:"Cup patterns can last from 7 weeks to as long as 65 weeks, but
#     most of them last for three to six months."
#   · 枢纽:"The pivot point is the highest price point in the handle... The
#     proper buy point is 10 cents above the peak of the handle."
#   · 放量:"The daily volume on the day a stock breaks out should expand at
#     least 40% to 50% above its average daily volume."
#
# ★★ 枢纽点 +$0.10 这个数**单列一类:「原著对但过时了」**。
#   1988/2009 年的美股票价结构下 10 美分是有意义的缓冲;今天对 300 美元的票
#   是 0.033%,对 5 美元的票是 2% —— 同一个「原著写死的数」在池子里的
#   实际含义相差 60 倍。★ 这不是「我们填错了」,报告里不许和填错混为一谈。
#
# ★ 形态扫描用到一条原文的**结构**约束(不是数值):
#   "the handle area should form in the upper half of the overall base"
#   → 柄部最高点 ≥ (杯左唇 + 杯底) / 2。
# ★ 原著还有一条「柄部要在 50 日线上方」—— 专家这次没给引文,本次**不加**。
# ============================================================================

meta:
  name: 技-4_{name}
  master: William J. O'Neil
  book: How to Make Money in Stocks (4th ed. 2009) Ch.2
  三版归属: {ver_tag}
  区间端: {band}
  caveat: >-
    原著的证据来自「每年几只领头羊」的选股体系(CANSLIM 的 A/N/S/L/I/M 六项
    基本面与大盘条件),本次**只跑形态那一项**,★ 不加任何基本面闸门。
    所以本次结论只对「光看杯柄形态」成立。
"""

_J4_STOPEXIT = """
# ---------------------------------------------------------------------------
# ④⑤⑥ —— ★ 三版完全一致
#   止损 7~8%:O'Neil 自己的铁律(取 8%)。★ 专家这次没给这一条的引文 → 【待核实】
#   离场:收盘跌破 50 日线
# ---------------------------------------------------------------------------
initial_stop:
  type: pct
  params: { pct: 0.08 }
  source: 原著(O'Neil「一律在亏 7~8% 时砍掉」,取 8%)【待核实 —— 专家本次未给引文】

trailing_stop:
  type: none
  source: 执行细节(三版统一)

exit:
  rules:
    - type: close_below_ma
      params: { ma: 50 }
      source: 原著(O'Neil 以 50 日线为持股防线)【待核实】
  params:
    profit_target_r: null
    time_stop_days: null
  fill: next_open
  source: 执行细节(原著的 20~25% 止盈本次不设,★ 否则会和止损口径打架)
"""


#: ★★ 技-4 的时间尺度声明 —— ★ 必须跟着 j4 一起生成,否则重跑一次本文件
#   就把 2026-10-30 的换算修正**静默冲掉**(`*_bars` 这个后缀只说「根」,
#   不说哪种根,更不说原著当年是在什么周期上给的数 —— 本轮的错就长在这个缝里)。
_J4_TIME_SCALE = """
# ---------------------------------------------------------------------------
# ★★ 时间尺度声明(engine/checks/time_scale_unit.py 的 C 式)
# ---------------------------------------------------------------------------
time_scale:
  entry.rules[0].params.handle_min_bars:
    unit: trading_days          # 我们实际作用在**日线**格子上
    book_unit: weeks            # ★ 原著给的是**周**
    book_value: 1               # ★ 原著数值:至少 1 周(区间 1–2 周,取下界)
    note: >-
      手册v13 六附 6.1 ① 引 O'Neil 4th ed. Ch.2「柄部持续时间:至少 1–2 周
      (日线至少 5 个交易日)」→ 1 周 × 5 = **5 个交易日**。
      ★ 原值 3 是把「3 周」当成「3 根日线」,2026-10-30 改正。
  entry.rules[0].params.handle_max_bars:
    unit: trading_days
    book_unit: weeks
    book_value: 5
    note: 5 周 × 5 = 25 个交易日;★ 上界本身是我们的读法(原著只给了下界)。
  entry.rules[0].params.cup_min_bars:
    unit: trading_days
    book_unit: weeks
    book_value: 7
    note: 原著「杯体持续 7 周至 65 周」→ 7 × 5 = 35 个交易日。
  entry.rules[0].params.cup_max_bars:
    unit: trading_days
    book_unit: weeks
    book_value: 65
    note: 原著「杯体持续 7 周至 65 周」→ 65 × 5 = 325 个交易日。
"""


def j4(ver: str, name: str, ver_tag: str, band: str, entry: str) -> str:
    return (_J4_HEAD.format(ver=ver, name=name, ver_tag=ver_tag, band=band)
            + _UNIVERSE + _REGIME + entry + _J4_STOPEXIT + _tail("trend")
            + _J4_TIME_SCALE)


def _j4_entry(dmin, hmax, vmult, pivot_line, pivot_src, extra="", extra_rules=""):
    return f"""
entry:
  rules:
    - type: pat6_cup_with_handle
      params:
        cup_depth_min: {dmin}
        cup_depth_max: 0.33
        handle_max_depth: {hmax}
        cup_min_bars: 35
        cup_max_bars: 325
        handle_min_bars: 5
        handle_max_bars: 25
        {pivot_line}
      source: >-
        杯深上限 0.33 / 杯长 ≥35 个交易日(= 7 周) / 杯长 ≤325 个交易日
        (= 65 周)= 原著【待核实】;杯深下限 {dmin} 与柄深上限 {hmax} 取自原著给的
        区间;★ 柄长下界 5 个交易日 = **原著**(手册v13 六附 6.1 ①,引 O'Neil
        4th ed. Ch.2:柄部持续时间「至少 1–2 周(日线至少 5 个交易日)」)——
        1 周 × 5 = 5;★ 2026-10-30 之前这里写的是 3,是把「3 周」当成了
        「3 根日线」,同一个算子里另外三个 bar 参数都 ×5 换算对了,只有这个
        下界没换。柄长**上界** 25 个交易日(= 5 周 × 5)仍是我们的读法。
        枢纽点:{pivot_src}
    - type: pat6_volume_x_sma
      params:
        period: 50
        multiple: {vmult}
        baseline_offset_days: 1
      source: 原著区间(突破日量 ≥ 均量 +40~50%)【待核实】;本档 = {vmult}×{extra}
{extra_rules}  signal_freeze: close
  fill: next_open
  source: 执行细节(原著盘中过枢纽点即买;引擎只能收盘确认、次日开盘)
"""


J4_ORIG_STRICT = j4(" · 原著版(严格端)", "原著版_严格端", "原著版·严格端",
                    "杯深下限 15% / 柄深 ≤12% / 放量 1.50×",
                    _j4_entry(0.15, 0.12, 1.50,
                              "pivot_offset_abs: 0.10",
                              "柄部最高点 **+$0.10** = 原著写死【待核实】"))
J4_ORIG_MID = j4(" · 原著版(中值)", "原著版_中值", "原著版·中值",
                 "杯深下限 13.5% / 柄深 ≤13.5% / 放量 1.45×",
                 _j4_entry(0.135, 0.135, 1.45,
                           "pivot_offset_abs: 0.10",
                           "柄部最高点 **+$0.10** = 原著写死【待核实】"))
J4_ORIG_LOOSE = j4(" · 原著版(宽松端)", "原著版_宽松端", "原著版·宽松端",
                   "杯深下限 12% / 柄深 ≤15%(原著的硬上限) / 放量 1.40×",
                   _j4_entry(0.12, 0.15, 1.40,
                             "pivot_offset_abs: 0.10",
                             "柄部最高点 **+$0.10** = 原著写死【待核实】"))
J4_IND = j4(" · 行业版", "行业版", "行业版",
            "杯深 12~33% / 柄深 ≤12% / 放量 1.20×",
            _j4_entry(0.12, 0.12, 1.20,
                      "pivot_offset_pct: 0.001",
                      "★ 行业版把 +$0.10 改成 **+0.1% 缓冲**(或柄部最高点本身)"
                      "—— 理由是 $0.10 这个绝对数已经和今天的票价结构脱节",
                      extra="(★ 行业版把突破日放量放宽到 1.20 倍,"
                            "重心转移到「柄部形成期间的极端缩量」,见下一条)",
                      extra_rules="""    - type: vcp_volume_duo
      params:
        slow_period: 50
        min_day_lookback: 20
        dryup_day_ratio: 0.60
        breakout_vs_slow: null
      source: >-
        行业惯例 —— ★ 行业版的重心:「柄部形成期间的极端缩量」。
        实现 = 突破前 20 个交易日(≈ 柄部窗口)里至少有 1 天
        成交量 ≤ 0.60 × SMA50(量)。
        ★ 0.60 这个数和 技-5 行业版用的是同一个行业数,★ 不是原著给的。
"""))


# ===========================================================================
# 技-5 米奈尔维尼 VCP
# ===========================================================================

_J5_HEAD = """# ============================================================================
# 技-5 · 米奈尔维尼 VCP(波动率收缩形态){ver}
#
# 三秒版:一只强势股的回调一次比一次浅(20% → 10% → 5%),成交量越来越小,
#         最后一次缩量到地量,然后突破 → 买。
#
# ★ 专家给的引文(Minervini 2013 Ch.10 / 2017 Ch.5)【全部待核实】:
#   · 次数:"Typically, most VCP setups will be formed by two to four
#     contractions, although sometimes there can be as many as five or six."
#   · 衰减:"...usually the first correction might be 20%, 25%, 33%—and then it
#     contracts usually to about half of the previous correction."
#   · 缩量:"You look for volume to dry up significantly, often with one or two
#     days where volume is 40% to 50% below the 50-day average, showing that
#     selling has stopped."
#
# ★★ 本条最重要的一个核对:「低于 50 日均量 40%~50%」= 量比在 **0.50 ~ 0.60**
#   之间。我们现在用的 0.60 **正好是这个区间最宽松的那一端**。
#   ★ 所以要把 0.50 / 0.55 / 0.60 三端都跑,并报出三端各自的笔数 ——
#     取严格端样本会更少,必须说清样本还够不够下结论。
# ============================================================================

meta:
  name: 技-5_{name}
  master: Mark Minervini
  book: Trade Like a Stock Market Wizard (2013) Ch.10;
        Think & Trade Like a Champion (2017) Ch.5
  三版归属: {ver_tag}
  区间端: {band}
  caveat: >-
    ★ 本文件的 ①②④⑤⑥⑦ 和 技-5 真实在跑的 vcp_momentum.yaml **不一样**:
    那条链带着 3 条环境过滤(SPY>200MA 等)和分级移动止损。
    为了让三版之间只差形态参数,本次把它们拿掉了。
    ★ 所以本次「XING版」的成绩**不等于** vcp_momentum.yaml 的历史成绩。
"""

_J5_STOPEXIT = """
# ---------------------------------------------------------------------------
# ④⑤⑥ —— ★ 三版完全一致(取自 vcp_momentum.yaml 的 ④⑥,但去掉分级跟踪)
# ---------------------------------------------------------------------------
initial_stop:
  type: structure_low_minus_atr
  params:
    structure_lookback: 5
    atr_period: 14
    atr_multiple: 0.2
  hard_gate:
    type: max_stop_distance_pct
    params: { max_pct: 8.0 }
    on_violation: reject_signal
    source: 原著(Minervini「止损距离超过 8% 这单就不做」)【待核实】
  source: 行业惯例(沿用 vcp_momentum.yaml 的 ④)

trailing_stop:
  type: none
  source: 执行细节(三版统一;★ vcp_momentum.yaml 真实配置里是分级跟踪,此处拿掉)

exit:
  rules:
    - type: close_below_ema
      params: { ema: 10 }
      source: 原著(Minervini 以 EMA10 为短线防线)【待核实】
  params:
    profit_target_r: null
    time_stop_days: null
  fill: next_open
  source: 行业惯例(沿用 vcp_momentum.yaml 的 ⑥)
"""


def j5(ver, name, ver_tag, band, entry):
    return (_J5_HEAD.format(ver=ver, name=name, ver_tag=ver_tag, band=band)
            + _UNIVERSE + _REGIME + entry + _J5_STOPEXIT + _tail("trend"))


def _j5_entry(decay, kmin, kmax, d1, dry, src):
    return f"""
entry:
  rules:
    - type: vcp_contraction
      stage: selection_gate
      params:
        swing_method: fractal_2_1_2
        fractal_half_width: 2
        base_min_days: 15
        base_max_days: 65
        range_metric: "(High_k - Low_k) / High_k"
        forbid_atr_ratio: true
        first_contraction_max_depth: {d1}
        decay_coefficient: {decay}
        min_contractions: {kmin}
        max_contractions: {kmax}
      source: {src}
    - type: vcp_volume_duo
      params:
        slow_period: 50
        min_day_lookback: 5
        dryup_day_ratio: {dry}
        breakout_vs_slow: null
      source: >-
        缩量阈值 {dry} —— 原著说「低于 50 日均量 40%~50%」= 0.50~0.60 区间。
        ★ 本档取 {dry}。★ 门禁2(突破日放量)按 1029 第二轮裁决已废除。
    - type: donchian_close_breakout
      params: {{ lookback: 5 }}
      source: 行业惯例(沿用 vcp_momentum.yaml:突破前 5 日高点。★ 原著的枢纽点
              定义在 技-4 里,这里用的是我们三版统一的突破口径)
  signal_freeze: close
  fill: next_open
  source: 执行细节
"""


J5_ORIG_050 = j5(" · 原著版(缩量严格端 0.50)", "原著版_缩量0.50", "原著版·严格端",
                 "缩量 0.50 ×SMA50(= 低于均量 50%,区间严格端)",
                 _j5_entry(0.50, 2, 4, 0.33, 0.50,
                           ">-\n        衰减 ≈0.50(原著「about half of the previous "
                           "correction」)/ 次数 2~4(原著 typically two to four)/\n"
                           "        第一段上限 0.33(原著「20%, 25%, 33%」的上限)"
                           "—— 全部原著【待核实】;\n        基底 15~65 个交易日沿用"
                           " vcp_momentum.yaml,★ 原著未给。"))
J5_ORIG_055 = j5(" · 原著版(缩量中值 0.55)", "原著版_缩量0.55", "原著版·中值",
                 "缩量 0.55 ×SMA50(区间中值)",
                 _j5_entry(0.50, 2, 4, 0.33, 0.55, "同严格端,只改缩量阈值"))
J5_ORIG_060 = j5(" · 原著版(缩量宽松端 0.60)", "原著版_缩量0.60", "原著版·宽松端",
                 "缩量 0.60 ×SMA50(= 低于均量 40%,区间宽松端。★ 我们现在用的就是这一端)",
                 _j5_entry(0.50, 2, 4, 0.33, 0.60, "同严格端,只改缩量阈值"))
J5_IND = j5(" · 行业版", "行业版", "行业版",
            "次数 ≥3(标准档) / 衰减 0.65 / 缩量窗口极值法 0.60",
            _j5_entry(0.65, 3, 6, 0.33, 0.60,
                      ">-\n        行业惯例:衰减放宽到 Dk ≤ 0.65 × D(k−1);"
                      "次数 ≥3 = 「标准档」(≥2 只算及格);\n"
                      "        缩量用窗口极值法「最后一次收缩区间内至少 1 天 "
                      "≤0.60×SMA50」。"))
J5_XING = j5(" · XING版", "XING版", "XING版",
             "次数 2~4 / 第一段 ≤30% / 衰减 0.65 / 缩量 0.60 —— 我们现在用的值",
             _j5_entry(0.65, 2, 4, 0.30, 0.60,
                       ">-\n        XING 现有值(engine/configs/vcp_momentum.yaml):"
                       "第一段 ≤30%、衰减 0.65、次数 2~4、缩量 0.60。\n"
                       "        ★ 其中 0.30 这个第一段上限**低于**原著给的 0.33,"
                       "衰减 0.65 **宽于**原著的 0.50。"))


# ===========================================================================
# 技-6 达瓦斯箱体
# ===========================================================================

_J6_HEAD = """# ============================================================================
# 技-6 · 达瓦斯箱体{ver}
#
# 三秒版:股价创一个新高,之后连续 3 天都没再超过它 → 这个高点就是箱顶;
#         再创一个新低,连续 3 天都没再跌破它 → 这是箱底。收盘站上箱顶就买。
#
# ★★ 本条我们整个形状都做错了。
#   **原著根本没有「N 天内区间收窄到 X%」这回事。**
#   达瓦斯用的是**离散事件规则(3 日规则)**。
#   引文(Darvas 1960《How I Made $2,000,000 in the Stock Market》
#   Ch.4 "Developing the Box Theory", p.23-27)【待核实】:
#     "I defined the top of the box as the highest price a stock reached as long
#      as it did not penetrate that high for three consecutive days... The
#      bottom of the box was defined as the lowest price reached after the top
#      had been established, provided that price was not touched or broken for
#      three consecutive days."
#
#   ★ 原著写死的**只有「连续 3 天」**。
#     **振幅百分比没有任何区间** —— 书中记录的箱体振幅 8%~30% 都有。
# ============================================================================

meta:
  name: 技-6_{name}
  master: Nicolas Darvas
  book: How I Made $2,000,000 in the Stock Market (1960) Ch.4
  三版归属: {ver_tag}
  caveat: >-
    原著是 1950 年代的美股、靠电报下单、只做少数几只票。本次跑的是
    300 只美股的全池扫描,★ 原著证据不能搬过来。
"""

_J6_STOPEXIT = """
# ---------------------------------------------------------------------------
# ④⑤⑥ —— ★ 三版完全一致
#   离场:★ 达瓦斯自己的离场就是「跌破箱底」—— 三版都用它(箱体由 3 日规则算出,
#         和进场用哪一版无关),★ 这样三版的离场才是同一把尺子。
# ---------------------------------------------------------------------------
initial_stop:
  type: lowest_low
  params: { lookback: 20 }
  source: 执行细节(原著「止损挂在箱底下面一点」;引擎的止损价是进场时一次定死的,
          取前 20 日最低价当箱底近似。★ 这是近似,不是原著的数)

trailing_stop:
  type: none
  source: 执行细节(三版统一)

exit:
  rules:
    - type: pat6_close_below_darvas_bottom
      params: { confirm_days: 3 }
      source: 原著(跌破箱底就走;箱底由 3 日规则认定)【待核实】
  params:
    profit_target_r: null
    time_stop_days: null
  fill: next_open
  source: 原著(达瓦斯不设固定止盈,靠一个箱体接一个箱体往上抬)
"""


def j6(ver, name, ver_tag, entry):
    return (_J6_HEAD.format(ver=ver, name=name, ver_tag=ver_tag)
            + _UNIVERSE + _REGIME + entry + _J6_STOPEXIT + _tail("trend"))


J6_ORIG = j6(" · 原著版(3 日规则)", "原著版_3日规则", "原著版", """
# ---------------------------------------------------------------------------
# ③ 进场扳机 —— 原著 3 日规则,★ 不加任何振幅条件
# ---------------------------------------------------------------------------
entry:
  rules:
    - type: pat6_darvas_breakout
      params:
        confirm_days: 3
        max_amplitude: null
        min_box_bars: 0
      source: >-
        原著(连续 3 天 —— 唯一写死的数)【待核实】。
        ★ max_amplitude / min_box_bars 显式写 null / 0:
          **原著没有振幅上限、没有存活天数下限**,★ 这里不是忘了填。
  signal_freeze: close
  fill: next_open
  source: 执行细节(原著用止损单盘中成交;引擎只能收盘确认、次日开盘)
""")

J6_IND = j6(" · 行业版(3 日规则 + 风控安全阀)", "行业版_3日规则加安全阀", "行业版", """
# ---------------------------------------------------------------------------
# ③ 进场扳机 —— 行业版:严格沿用原著的 3 日规则,**额外加一道安全阀**
#
# ★★ 这道振幅上限是**止损距离风控的安全阀,不是箱体的定义**。
#   箱体太宽 → 止损挂到箱底就太远 → 单笔风险超预算,所以行业做法是直接不做。
#   ★ 报告里不许写成「原著要求振幅小于 18%」。★ 原著对振幅一个字都没写。
# ---------------------------------------------------------------------------
entry:
  rules:
    - type: pat6_darvas_breakout
      params:
        confirm_days: 3
        max_amplitude: 0.18
        min_box_bars: 10
      source: >-
        3 日规则 = 原著【待核实】;
        ★ max_amplitude 0.18(专家给 15%~20%,取 18%)与 min_box_bars 10
        (专家给 10~30 个交易日,取 10)= **行业惯例的风控安全阀**,
        ★ 不是箱体定义,★ 不是原著。
  signal_freeze: close
  fill: next_open
  source: 行业惯例
""")

J6_XING = j6(" · XING版(百分比收窄写法)", "XING版_百分比收窄", "XING版", """
# ---------------------------------------------------------------------------
# ③ 进场扳机 —— XING 现有写法:「N 天内高低点区间收窄到 X%」
#
# ★★ 这个写法**不是达瓦斯**。它是一个「窄幅整理」筛子:
#   近 25 根 (max(High) − min(Low)) / mean(Close) ≤ 0.20,然后收盘突破那个上沿。
#   ★ 它和 3 日规则认出来的箱体重叠多少,是本次任务要实测的第一件事。
# ---------------------------------------------------------------------------
entry:
  rules:
    - type: pat6_narrow_box_breakout
      params:
        bars: 25
        max_range_pct: 0.20
      source: >-
        XING 现有写法(engine/state_axis_tri_1029.py 状-2 行业版箱体实现的同一口径:
        近 25 根区间收窄到 20%)。★ 原著里没有这个东西。
  signal_freeze: close
  fill: next_open
  source: XING版
""")


# ===========================================================================
# 技-11 威科夫量价洗盘
# ===========================================================================

J11_ORIG = """# ============================================================================
# 技-11 · 威科夫量价洗盘 —— 原著版 ★★ 跑不了
#
# 三秒版:原著(威科夫 1931 年函授课程)把洗盘讲成一套量价哲学,
#         **三项全都没有写死任何数字** —— 没有刺破幅度百分比、没有硬性收回
#         天数、没有量化成交量比例。所以按纪律:原著版跑不了,不许我们填。
#
# ★★ 这份文件**故意不给 entry 规则**。它存在的目的是把「跑不了」这件事
#   变成仓库里一个看得见的文件,而不是报告里一句话。
#   ★ 谁以后想跑它,必须先回答「阈值从哪来」。
#
# ★ 后人量化版(= 行业版的真正来源,见 技-11-行业.yaml)的传承链:
#     Bob Evans(1950s,提炼 Spring 1/2/3 号与 Upthrust)
#   → Hank Pruden《The Three Skills of Top Trading》(2007) Ch.4
#   → Tom Williams《Master the Markets》(1993) Ch.3(VSA)
#
# ★★ Spring 分三号,**只有 #3 可直接建仓**:
#   #1 终极洗盘:深度跌破 + 天量抛压 → 不可直接买,必须等漫长二次确认
#   #2 常规洗盘:中度跌破 + 量中等偏大 → 必须等次级测试(Secondary Test)
#   #3 微观弹簧:极轻微下刺(仅跌破数美分或 1%~2% 以内)+ 成交量极度萎缩
#                → 可直接建仓
#   ★ 我们现在的实现(liquidity_sweep.yaml)**没有区分三号** ——
#     见报告「技-11 Spring 1/2/3 号分流实测」一节。
# ============================================================================

meta:
  name: 技-11_原著版_跑不了
  master: Richard D. Wyckoff
  book: 威科夫 1931 年函授课程(Springs / Shakeouts)
  三版归属: 原著版
  cannot_run: true
  cannot_run_reason: >-
    原著三项全未写死:① 刺破幅度没有百分比 ② 没有硬性收回天数
    ③ 没有量化成交量比例。全是量价哲学描述。
    ★ 按纪律:原著没写死的地方不许我们填 → 只输出「原著未给出可执行阈值」+ 引文。
  原著未给出可执行阈值的项: 刺破幅度 · 收回天数 · 成交量比例(三项全部)
"""

_J11_HEAD = """# ============================================================================
# 技-11 · 威科夫量价洗盘{ver}
#
# 三秒版:价格往下扫一针、跌破前面的关键低点,但当天就收回来了,而且那一针
#         是缩量的(没人真的在抛)→ 买。
#
# ★★ 原著(1931 函授课程)三项全未写死 → 原著版跑不了(见 技-11-原著.yaml)。
#   本文件的阈值全部来自**后人量化版**:
#     Bob Evans(1950s)→ Pruden (2007) Ch.4 → Tom Williams (1993) Ch.3(VSA)
#   ★ 所以 source 一律标「后人量化版 / 行业惯例」,★ 一处都不许标原著。
# ============================================================================

meta:
  name: 技-11_{name}
  master: Richard D. Wyckoff(原著);Bob Evans / Hank Pruden / Tom Williams(量化版)
  book: Pruden (2007) Ch.4;Williams (1993) Ch.3
  三版归属: {ver_tag}
  caveat: >-
    ★ 本文件的 ②④⑤⑥⑦ 和真实在跑的 liquidity_sweep.yaml **不完全一样**:
    那条链带着 2 条环境过滤(其中 1 条因数据拿不到已显式关掉)和分级移动止损。
    为了让三版之间只差形态参数,本次把它们拿掉了。
    ★ 所以本次「XING版」的成绩**不等于** liquidity_sweep.yaml 的历史成绩。
"""

_J11_STOPEXIT = """
# ---------------------------------------------------------------------------
# ④⑤⑥ —— ★ 两版完全一致(取自 liquidity_sweep.yaml)
# ---------------------------------------------------------------------------
initial_stop:
  type: day_low_minus_atr
  params:
    atr_period: 14
    atr_multiple: 0.3
  source: 行业惯例(沿用 liquidity_sweep.yaml:下刺那根的最低价下方 0.3×ATR14)

trailing_stop:
  type: none
  source: 执行细节(两版统一;★ liquidity_sweep.yaml 真实配置里是分级跟踪,此处拿掉)

exit:
  rules:
    - type: close_below_ma
      params: { ma: 20 }
      source: 行业惯例(沿用 liquidity_sweep.yaml)
  params:
    profit_target_r: 2.0
    time_stop_days: null
  fill: next_open
  source: 行业惯例(沿用 liquidity_sweep.yaml 的 2R 止盈)
"""

J11_IND = (_J11_HEAD.format(ver=" · 行业版(后人量化版)", name="行业版_后人量化版",
                            ver_tag="行业版(= 后人量化版)")
           + _UNIVERSE + _REGIME + """
# ---------------------------------------------------------------------------
# ③ 进场扳机 —— 行业版(后人量化版)
#   下刺深度 0.15~0.80 ×ATR14(★ 硬帽 1.5×ATR,超过视为真实破位)
#   当日收盘必须收复:Close ≥ 前低 + 0.10×ATR;没收回则最宽 ≤2 个交易日
#   缩量测试:Volume ≤ 0.65×SMA50,且 Volume_t < min(Vol_{t−1}, Vol_{t−2})
#            (Tom Williams 原规则)
# ---------------------------------------------------------------------------
entry:
  rules:
    - type: pat6_spring
      params:
        lookback: 20
        min_bars_before: 4
        atr_period: 14
        depth_min_atr: 0.15
        depth_max_atr: 0.80
        depth_hard_cap_atr: 1.5
        reclaim_atr_multiple: 0.10
        reclaim_max_bars: 2
        vol_test_max_ratio: 0.65
        vol_slow_period: 50
        vol_below_prior_two: true
      source: >-
        后人量化版 / 行业惯例。★ 一处都不是原著。
        前低 = Connors 滚动 20 日绝对低点 + 4 天存活门禁
        (Connors & Raschke《Street Smarts》1995 Ch.4 Turtle Soup Rule 2 —— 已核实)。
        Volume_t < min(Vol_{t−1}, Vol_{t−2}) = Tom Williams (1993) Ch.3【待核实】。
  signal_freeze: close
  fill: next_open
  source: 行业惯例
""" + _J11_STOPEXIT + _tail("meanrev"))

J11_XING = (_J11_HEAD.format(ver=" · XING版", name="XING版", ver_tag="XING版")
            + _UNIVERSE + _REGIME + """
# ---------------------------------------------------------------------------
# ③ 进场扳机 —— XING 现有写法(逐字取自 engine/configs/liquidity_sweep.yaml)
# ★★ 它**没有区分 Spring 1/2/3 号**:只要跌破 20 日低点再收回就算,
#   下刺多深、量多大都不看。★ 所以 #1 终极洗盘(深跌 + 天量)也会被买进来 ——
#   那部分就是「接飞刀」。见报告的分流实测。
# ---------------------------------------------------------------------------
entry:
  rules:
    - type: swing_low_exists
      params:
        lookback: 20
        swing_definition: rolling_absolute_low_20
        min_bars_before: 4
      source: 原著(Connors & Raschke 1995 Ch.4 Rule 2 —— 已核实)
    - type: intraday_break_below_swing_low
      params: { min_new_low_days: 20 }
      source: XING 现有写法(liquidity_sweep.yaml)
    - type: close_reclaim_above_swing_low
      logic: AND
      components:
        - name: 绝对收复缓冲垫
          formula: Close_t >= SwingLow_20 + 0.15 * ATR14(t)
          params: { atr_period: 14, atr_multiple: 0.15 }
          source: 行业惯例
        - name: BCL_K线内收盘相对位置
          formula: (Close - Low) / (High - Low) >= 0.65
          params: { min_bcl: 0.65 }
          source: 行业惯例
      source: XING 现有写法(liquidity_sweep.yaml)
    - type: bullish_candle
      params: { require: close_gt_open }
      source: XING 现有写法(liquidity_sweep.yaml)
  signal_freeze: close
  fill: next_open
  source: XING版
""" + _J11_STOPEXIT + _tail("meanrev"))


# ===========================================================================
# 技-14 布林带均值回归
# ===========================================================================

_J14_HEAD = """# ============================================================================
# 技-14 · 布林带均值回归{ver}
#
# 三秒版:价格跌到布林带下轨附近 → 买,涨回中轨 → 走。
#
# ★★★ 本条的性质和别的五条都不一样:**不是「原著没写」,是「原著反对」**。
#   引文(John Bollinger《Bollinger on Bollinger Bands》2001,
#   Ch.12 "Fifteen Basic Rules", p.119)【待核实】:
#     "Rule 4: Tags of the bands are just that, tags not signals. A tag of the
#      upper Bollinger Band is NOT in-and-of-itself a sell signal. A tag of the
#      lower Bollinger Band is NOT in-and-of-itself a buy signal."
#   ★ 他反复警告「走带(Walking the Bands)」:强单边趋势里价格会连续数天、
#     甚至数周贴着下轨继续下行。
#   ★ 他认可的反转用法(Method III: Reversals)**必须由 W 底形态 +
#     一个无相关性的指标(MFI / 成交量积累派发线)发生底背离**才成立。
#
# ★ 布林带基础参数的原著标准:中轨 20 日 SMA、带宽 ±2.0σ
#   (周期缩到 10 日则 1.9σ,拉到 50 日则 2.1σ)。本条三版都用 20 / 2.0。
# ============================================================================

meta:
  name: 技-14_{name}
  master: John Bollinger
  book: Bollinger on Bollinger Bands (2001) Ch.12
  三版归属: {ver_tag}
  原著性质: {nature}
"""

_J14_STOPEXIT = """
# ---------------------------------------------------------------------------
# ④⑤⑥ —— ★ 三版完全一致
#
# ★★ 引擎做不到的一处,显式交代:行业版原文写的是「触中轨平 50%、触上轨清仓」
#   —— **引擎不支持分批离场**。本次三版一律按「触中轨全平」跑
#   (= 保守端:更早离场、吃不到上轨那一段)。
#   ★ 这会系统性低估行业版的总收益,报告里必须写明方向。
# ---------------------------------------------------------------------------
initial_stop:
  type: day_low_minus_atr
  params:
    atr_period: 14
    atr_multiple: 0.3
  source: 行业惯例(止损挂下刺波谷最低价下方 0.3×ATR14 —— 专家给的行业版写法)

trailing_stop:
  type: none
  source: 执行细节(三版统一)

exit:
  rules:
    - type: pat6_close_above_bb_mid
      params: { period: 20, k: 2.0 }
      source: >-
        行业惯例(触中轨离场)。★ 原文是「触中轨平 50%、触上轨清仓」,
        引擎不支持分批 → 本次按触中轨**全平**跑,★ 这是保守端。
  params:
    profit_target_r: null
    time_stop_days: null
  fill: next_open
  source: 行业惯例
"""


def j14(ver, name, ver_tag, nature, entry):
    return (_J14_HEAD.format(ver=ver, name=name, ver_tag=ver_tag, nature=nature)
            + _UNIVERSE + _REGIME + entry + _J14_STOPEXIT + _tail("meanrev"))


J14_ORIG = j14(" · 原著版(Method III 近似)", "原著版_MethodIII近似", "原著版",
               "★★ 原著**反对**「碰轨就买」。本版跑的是作者自己认可的 "
               "Method III(Reversals)的近似。", """
# ---------------------------------------------------------------------------
# ③ 进场扳机 —— 原著认可的 Method III(Reversals)近似
#   · 波谷用分型(半宽 2)认定
#   · 对确认的波谷 L2,在 5~60 根之前找上一个波谷 L1
#   · W 底(Bollinger 的 W4):Low(L2) < Low(L1) 但 %b(L2) > %b(L1);
#     并且 L1 刺破下轨(%b<0)、L2 守在下轨之上(%b>0)
#   · 无相关指标底背离:MFI(14) 在 L2 高于 L1
# ★ 这是**近似**,不是原著原文的算法。原著 Method III 还要人工判断形态质量。
# ---------------------------------------------------------------------------
entry:
  rules:
    - type: pat6_w_bottom_divergence
      params:
        fractal_half_width: 2
        min_gap_bars: 5
        max_gap_bars: 60
        period: 20
        k: 2.0
        mfi_period: 14
      source: >-
        原著 Method III 的结构要求(W 底 + 一个无相关性指标底背离、
        MFI 是作者自己点名的指标)= 原著【待核实】;
        ★ 分型半宽 2、上一个波谷回看 5~60 根 = **我们的读法**
        (原著靠人眼认 W 底,没给回看窗口)。
  signal_freeze: close
  fill: next_open
  source: 执行细节
""")

J14_IND = j14(" · 行业版", "行业版", "行业版",
              "原著反对裸碰轨;行业版的做法是「等它自己收回来再买」+ 三道趋势过滤", """
# ---------------------------------------------------------------------------
# ③ 进场扳机 —— 行业版:★ 不许盘中碰轨限价抄底。进场要三步 + 三道过滤器
#   三步:① 盘中跌破下轨,或前一日收盘已 %b<0
#         ② 当日收盘强力收复到下轨上方,且收阳线实体(Close>Lower 且 Close>Open)
#         ③ 2 日 RSI 从 <10 向上回升到 >15
#   三道必配的趋势过滤器:
#         ① 价格在 200 日均线上方,且 200 日线 20 日斜率 ≥0
#         ② ADX(14) ≤25 —— ★ ADX>25 是强趋势,此时碰下轨是**顺势做空点**,
#            严禁逆势抄底。这一条正是 Bollinger「走带」警告的工程化落地。
#         ③ 带宽突变熔断:(BW_t − BW_{t−3}) / BW_{t−3} ≤ 20%
# ---------------------------------------------------------------------------
entry:
  rules:
    - type: pat6_bb_reclaim
      params:
        period: 20
        k: 2.0
        rsi_period: 2
        rsi_low: 10.0
        rsi_back: 15.0
      source: 行业惯例(三步进场;2 日 RSI 的 10/15 两个数来自专家给的行业版)
    - type: pat6_bb_trend_filters
      params:
        ma_period: 200
        slope_lookback: 20
        adx_period: 14
        adx_max: 25.0
        period: 20
        k: 2.0
        bw_jump_lookback: 3
        bw_jump_max: 0.20
      source: 行业惯例(三道必配过滤器;ADX 定义 Wilder 1978)
  signal_freeze: close
  fill: next_open
  source: 行业惯例
""")

J14_XING = j14(" · XING版(触下轨就买)", "XING版_触下轨就买", "XING版",
               "★★ 这一版是**作者点名反对的做法**(Rule 4)。"
               "10-22 的记录里它已标「默认关闭」。", """
# ---------------------------------------------------------------------------
# ③ 进场扳机 —— XING 现有写法:收盘跌破下轨就买
# ★★ 这**就是** Bollinger Rule 4 点名反对的那个做法:
#   "A tag of the lower Bollinger Band is NOT in-and-of-itself a buy signal."
# ★ 跑它的目的不是指望它能成立,是把「作者反对的做法在我们池子里到底什么样」
#   量出来,以及给「走带」现象提供母集。
# ---------------------------------------------------------------------------
entry:
  rules:
    - type: pat6_bb_tag_lower
      params: { period: 20, k: 2.0 }
      source: >-
        XING 现有写法。★★ 性质:**作者点名反对**(Bollinger 2001 Ch.12 Rule 4)。
        ★ 不是「原著没写」,是「原著写了不要这么干」。
  signal_freeze: close
  fill: next_open
  source: XING版
""")


FILES = {
    "技-3-原著.yaml": J3_ORIG_WEEKLY,
    "技-3-原著-底盘9周.yaml": J3_ORIG_WEEKLY_9W,
    "技-3-原著-机械日线.yaml": J3_ORIG_DAILY,
    "技-3-行业.yaml": J3_IND,
    "技-3-XING.yaml": J3_XING,
    "技-4-原著.yaml": J4_ORIG_STRICT,
    "技-4-原著-中值.yaml": J4_ORIG_MID,
    "技-4-原著-宽松端.yaml": J4_ORIG_LOOSE,
    "技-4-行业.yaml": J4_IND,
    "技-5-原著.yaml": J5_ORIG_050,
    "技-5-原著-中值.yaml": J5_ORIG_055,
    "技-5-原著-宽松端.yaml": J5_ORIG_060,
    "技-5-行业.yaml": J5_IND,
    "技-5-XING.yaml": J5_XING,
    "技-6-原著.yaml": J6_ORIG,
    "技-6-行业.yaml": J6_IND,
    "技-6-XING.yaml": J6_XING,
    "技-11-原著.yaml": J11_ORIG,
    "技-11-行业.yaml": J11_IND,
    "技-11-XING.yaml": J11_XING,
    "技-14-原著.yaml": J14_ORIG,
    "技-14-行业.yaml": J14_IND,
    "技-14-XING.yaml": J14_XING,
}


def main() -> int:
    from . import ops_1029
    os.makedirs(CFG, exist_ok=True)
    for name, text in FILES.items():
        path = os.path.join(CFG, name)
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(text)
        # ★ 写完立刻用严格加载器读一遍 —— 重复 key 会静默取最后一个,
        #   今天查出来过一次(让一条链的笔数从 210 变成 313)。
        ops_1029.load_yaml_strict(path)
        print(f"  写好并通过严格加载:{name}")
    print(f"共 {len(FILES)} 份配置")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
