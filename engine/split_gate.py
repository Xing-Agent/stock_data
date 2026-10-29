"""
拆股闸 —— ★ 2026-10-29 按技术方 SEC 核实结果重写。

════════════════════════════════════════════════════════════════════════
★ 大白话(三秒版)
════════════════════════════════════════════════════════════════════════
我们原来那份 8 条拆股清单,技术方逐条对着 SEC 文件查完,★ 错了 5 条。
这个文件现在只认技术方核实过的结果,★ 自己不再判断「这是不是拆股」。

★ 最要紧的一件事先说清楚:★ 没有双重修正的风险。
  技术方在源头 daily.json 里加的是 `split_coefficient` 这个**标记字段**,
  ★ 价格和成交量一个数都没改(他们在交付说明里写明了:
  「日线的价格、成交量和原始供应商快照未改」)。
  而我们的引擎(engine/data.py)★ 从来不读 split_coefficient,
  只读 open/high/low/close/volume。
  ★ 所以:源头没动价格 + 我们不读那个字段 = 修正只发生一次,就在这里。
  ★ 反过来说:价格该修的还得我们修,不修就是 bug。
  (这一条有自检守着:engine.split_gate 的 self_check(),
   以及 engine.selftest 的第 ⑥ 项。)

════════════════════════════════════════════════════════════════════════
★ 三种处理方式(★ 不再有 exclude_symbol)
════════════════════════════════════════════════════════════════════════
  ratio_fix   —— 技术方拿到了发行人 / 交易所证据的拆股。
                 把事件日之前的价格乘上 ratio,成交量除以 ratio,接成连续序列。
  no_action   —— 技术方明确说「这不是拆股」。我们什么都不做,原样留着。
                 ★ 原来我们把 AMRS / PRTY 整只剔了 —— 那是错的,现在收回。
                 ★ AMRS 是破产股,是样本里最该留的那一类,无故剔掉等于偷偷
                   把最难看的一段成绩删了。
  cut_series  —— ★ 数据里有一个价格断裂,★ 但技术方核实后说它不是拆股
                 (或者说证据对不上)。这种情况下:
                   · 我们★ 不许自己编一个系数去修(硬纪律:不许自己判断);
                   · 也★ 不能原样留着 —— 原样留着就等于凭空造出一天
                     +867% 或 −90%;
                   · 所以只有一条路:★ 在断裂处把序列切开,只用其中
                     内部自洽的那一段,另一段当「拿不到」丢掉。
                 ★ keep="after" 表示只留断裂日及之后;"before" 表示只留之前。
                 ★ 这是「拿不到就说拿不到」,不是修正。

════════════════════════════════════════════════════════════════════════
★★ 需要 Lin 拍板的三条(都在 NEEDS_RULING 里,报告里会单独列)
════════════════════════════════════════════════════════════════════════
  SQBG 2020-07-27:技术核实是 1 合 40(系数 0.025),但数据里实际跳了
      1201 倍。按 40 修完还剩 30 倍的假跳变 —— 说明 SQBG 拆股前那段价格
      本身就被供应商额外调整过(技术方对 ACOR 也写了同样的毛病:
      「provider_label_inconsistent_with_observed_prices」)。
      ★ 默认:cut_series keep="after",丢掉 2020-07-27 之前那段。
  ACOR 2021-11-30:数据里有 9.67 倍跳变,★ 技术方说这一天没有任何公司行为。
      ★ 默认:cut_series keep="after"。
  UHAL 2022-11-10:每股派发 9 股新类别股票(股票股利),技术方明确说
      「不是同一证券的 1 拆 10」。不修的话引擎会吃到一天 −90% 的假亏。
      ★ 默认:cut_series keep="before",只用 2022-11-10 之前那段
      (那段更长,6.9 年 vs 3.1 年),之后那段当另一只证券,丢掉。

★ PROP 另有一个和拆股无关的问题,见 DATA_INTEGRITY_FLAGS。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Action = Literal["ratio_fix", "no_action", "cut_series"]

# 证据目录(技术方交付)
REVIEW_DIR = "pilot_300/reviews/corporate_actions_2026-10"


@dataclass(frozen=True)
class SplitEvent:
    symbol: str
    date: str                      # 引擎实际动手的那一天(首个调整交易日)
    action: Action
    # ratio = 事件当天价格 / 前一天价格 的理论值 = 1 / split_coefficient。
    # 1 合 6 → 系数 1/6 → 价格 ×6 → ratio = 6
    ratio: float | None = None
    coefficient: float | None = None   # 技术方给的 split_coefficient(新股/旧股)
    keep: Literal["before", "after"] | None = None   # 只有 cut_series 用
    label: str = ""
    verdict: str = ""              # 技术方的核实结论(原文大意)
    source: str = ""


@dataclass(frozen=True)
class Candidate:
    """我们原来给技术方的那 8 条候选,★ 以及每一条的最终下场。"""
    symbol: str
    candidate_date: str
    our_old_claim: str             # 我们原来说的
    our_old_action: str            # 我们原来干的
    verified: str                  # 技术方核实结论
    now: str                       # 现在怎么处理


# ───────────────────────────────── ① 引擎实际执行的动作 ─────────────────────────────────
# ★ 来源:verified_split_events_20261029.json + corporate_action_review_20261028.json
#   每一条都能指到一份 SEC / 交易所文件。★ 我们没有自己判断任何一条。

EVENTS: tuple[SplitEvent, ...] = (
    # ══════════════════════════════════════════════════════════════════════
    # ★★ 2026-10-29 第二次重写:原来这里手写着 3 条 ratio_fix
    #    (ACOR 2021-01-04 ×6 / ACOR 2023-06-05 ×20 / WPG 2020-12-22 ×9)。
    # ★ 现在全部删掉 —— 比例修正一律从源头 daily.json 的 split_coefficient 读。
    #   见本文件 ⑤「源头系数」一节。手工清单上一轮被技术方核出错 5 条,
    #   根因就是 load_daily() 从来没读过这个字段,我们在手工猜一个文件里本来就有的数。
    # ★ 实证:源头系数和技术方 SEC 核实结果在 7 个争议点上**逐条一致**
    #   (ACOR 1合6@2021-01-04 + 1合20@2023-06-05 / WPG 1合9@2020-12-22 /
    #    SQBG 1合40@2020-07-27 / AMRS·PRTY·UHAL 无非1系数 = 确实不是拆股),
    #   并且正确地否掉了 KHC(Kraft×Heinz 合并,系数为 1)。
    #   这一致性由 self_check() 的 ⑥ 项逐条断言守着。
    # ══════════════════════════════════════════════════════════════════════

    # ── 技术方明确说「不是拆股」→ 什么都不做(★ 原来被我们剔掉的两只在这里收回)
    SplitEvent(
        "AMRS", "2023-08-10", "no_action",
        label="原记 1拆5 —— 不是拆股",
        verdict="没找到任何支持 1 拆 5 的公司行为证据;那几天是 2023-08-09 破产申请和指数处理。"
                "★ 这一天的 −80.7% 是真实亏损,必须留在样本里",
        source="assets.bbhub.io/professional/sites/10/Treatment-of-Bankruptcy-for-Amyris.pdf",
    ),
    SplitEvent(
        "PRTY", "2019-11-07", "no_action",
        label="原记 1拆3 —— 不是拆股",
        verdict="2019-11-07 的 8-K 不构成 1 拆 3;2020 年委托书里的 1合3~1合20 只是「拟议区间」,"
                "授权不等于实施。★ 这一天的 −67.2% 是真实的财报暴跌",
        source="sec.gov/Archives/edgar/data/1592058/000119312519286588/R1.htm",
    ),
    SplitEvent(
        "PROP", "2020-05-14", "no_action",
        label="原记 4合1 —— 不是拆股",
        verdict="旧 PROP ticker 的证券身份和当前样本发行人无法仅凭 ticker 对应。"
                "★ 技术方:不要把 2020 年及更早的 PROP 价格归给现在这个发行人。"
                "★ 另见 DATA_INTEGRITY_FLAGS —— 这只票有一个比拆股更大的问题",
        source="sec.gov/Archives/edgar/data/1162896/000149315223030135/ex99-3.htm",
    ),

    # ── ★ 有断裂但技术方说不是拆股 → 切开,只用自洽的那一段(★ 需 Lin 拍板)
    SplitEvent(
        "ACOR", "2021-11-30", "cut_series", keep="after",
        label="数据里 9.67x 跳变,★ 技术方说这一天没有公司行为",
        verdict="技术方核实:2021-11-30 既没有 10 合 1 也没有任何其他拆股。"
                "数据里的 9.67 倍跳变没有证据支持 → 不编系数,切开",
        source="corporate_action_review_20261028.json / status=candidate_date_ratio_contradicted",
    ),
    SplitEvent(
        "SQBG", "2020-07-27", "cut_series", keep="after",
        ratio=40.0, coefficient=0.025,
        label="1合40 已核实,★ 但数据实跳 1201x,按 40 修完还剩 30x",
        verdict="SEC 8-K + Nasdaq 公告确认 1 合 40(我们原来记的 1200 合 1 是错的)。"
                "★ 但按 40 修完残余 30.0 倍假跳变 —— 拆股前那段价格本身被额外调整过,"
                "口径拿不到 → 不编第二个系数,切开只用拆股后那段",
        source="sec.gov/Archives/edgar/data/1648428/000110465920086221/tm2025519d1_8k.htm"
               " + nasdaqtrader.com ECA2020-131",
    ),
    SplitEvent(
        "UHAL", "2022-11-10", "cut_series", keep="before",
        label="原记 1拆10 —— 实际是每股派发 9 股新类别股票(股票股利)",
        verdict="技术方:发行了一个新的无投票权系列,★ 不是同一证券的 1 拆 10。"
                "我们不许按拆股修(那是自己判断);但原样留着会吃到一天 −89.9% 的假亏 →"
                "按「断裂日之后是另一只证券」处理,只用之前那段",
        source="sec.gov/Archives/edgar/data/4457/000000445723000011/uhal-20221231_htm.xml",
    ),
)


# ───────────────────────────────── ② 8 条候选的下场对照表 ─────────────────────────────────
# ★ 这张表就是「我们错了什么」的账。报告直接引它。

CANDIDATES: tuple[Candidate, ...] = (
    Candidate("ACOR", "2021-11-30", "10合1 (ratio 10.0)", "ratio_fix ×10",
              "★ 错 —— 日期和比例都不对。真事件是 2020-12-31 生效的 1合6"
              "(首个调整交易日 2021-01-04)",
              "ratio_fix ×6 挪到 2021-01-04;2021-11-30 的 9.67x 断裂改为 cut_series"),
    Candidate("ACOR", "2023-06-05", "20合1 (ratio 20.0)", "ratio_fix ×20",
              "✅ 对(系数 0.05)", "不变:ratio_fix ×20"),
    Candidate("AMRS", "2023-08-10", "1拆5 (ratio 0.2)", "exclude_symbol(整只剔除)",
              "★★ 不是拆股 —— 是破产申请和指数处理",
              "★ 取消剔除、取消修正。★ 破产股归队"),
    Candidate("PROP", "2020-05-14", "4合1 (ratio 4.0)", "ratio_fix ×4",
              "★★ 不是拆股 —— 旧 ticker 和当前发行人对不上",
              "★ 取消修正。★ 但留下 4.0x 残余断裂,见 DATA_INTEGRITY_FLAGS"),
    Candidate("PRTY", "2019-11-07", "1拆3 (ratio 1/3)", "exclude_symbol(整只剔除)",
              "★★ 不是拆股 —— 文件里只是「授权」,没实施",
              "★ 取消剔除、取消修正。−67.2% 是真实财报暴跌"),
    Candidate("SQBG", "2020-07-27", "1200合1 (ratio 1200.0)", "ratio_fix ×1200",
              "★ 错 —— 实际 1合40(系数 0.025)",
              "★ cut_series keep=after(按 40 修完还剩 30x,口径拿不到)"),
    Candidate("UHAL", "2022-11-10", "1拆10 (ratio 0.1)", "ratio_fix ×0.1",
              "★★ 不是拆股 —— 每股派发 9 股新类别股票(股票股利)",
              "★ cut_series keep=before(不许自己按拆股修,也不能吃假 −90%)"),
    Candidate("WPG", "2020-12-22", "8合1 (ratio 8.0)", "ratio_fix ×8",
              "★ 错 —— 实际 1合9(系数 1/9)", "ratio_fix ×9"),
)

# ★ 8 条里我们原来判错的 5 条(报告里的「用错清单」就是这 5 条)
WRONG_IN_OLD_LIST: tuple[str, ...] = (
    "ACOR 2021-11-30", "AMRS 2023-08-10", "PROP 2020-05-14",
    "PRTY 2019-11-07", "SQBG 2020-07-27", "UHAL 2022-11-10", "WPG 2020-12-22",
)

# ★ 需要 Lin 拍板的三条(默认值已经生效,改 EVENTS 里的 action/keep 就能切换)
NEEDS_RULING: tuple[str, ...] = (
    "SQBG 2020-07-27 → cut_series keep=after(残余 30x,证据拿不到)",
    "ACOR 2021-11-30 → cut_series keep=after(9.67x 无任何公司行为证据)",
    "UHAL 2022-11-10 → cut_series keep=before(股票股利,不许按拆股修)",
)

# ★ 和拆股无关、但同一批核实里暴露出来的数据问题 —— 不在这个闸的职责内,但必须记着
DATA_INTEGRITY_FLAGS: tuple[str, ...] = (
    "PROP:技术方说 2020 年及更早的 PROP 价格不属于当前发行人(CIK 1162896 原名 "
    "Creek Road Miners,2023-05-03 合并后才改名 Prairie Operating 并启用 PROP)。"
    "★ 这是「整段历史张冠李戴」,比拆股严重。本次按 Lin 的指示不动它,★ 但要拍板。",
    "ACOR:daily.json 自称 adjustment=raw,实测价格和独立来源差 60 倍 —— "
    "技术方原话「Do not use as raw price; source needs revalidation」。",
    "SQBG:拆股前那段价格被额外调整过(按核实的 1合40 修完仍残余 30x)。",
    "★★ 2026-10-29 已修复(原文留档,因为它本身就是一个错误判断):"
    "原来这里写「split_coefficient 引擎完全不读,是故意不读的,读了会双重修正」。"
    "★ 这句话是错的。实测源头价格是 raw —— 66 个非 1 系数事件的"
    "「当天价格比值 ÷ (1/系数)」中位数 = 1.00,源头一个价格都没改。"
    "★ 不读才是 bug:接之前全池有 48 根未修的假跳变(GOOG −95.1% / CSGP −90.4% / "
    "TSLA −77.5% / BNED +7312%),其中 27 根落在绩效窗口内。"
    "★ 现在 split_coefficient 是比例修正的唯一来源,手工 ratio_fix 清单已删空。",
)


# ───────────────────────────────── ③ 对外接口 ─────────────────────────────────

# ★ 不再有任何票因为「判不准」被剔除 —— 这是本次最重要的一处收回
EXCLUDED_SYMBOLS: frozenset[str] = frozenset()

FIX_EVENTS: tuple[SplitEvent, ...] = tuple(
    e for e in EVENTS if e.action == "ratio_fix")

CUT_EVENTS: tuple[SplitEvent, ...] = tuple(
    e for e in EVENTS if e.action == "cut_series")

NO_ACTION_EVENTS: tuple[SplitEvent, ...] = tuple(
    e for e in EVENTS if e.action == "no_action")


# ───────────────────────────── ⑤ 源头系数(比例修正的唯一来源) ─────────────────────────────
#
# ★★ 大白话:拆股该乘几,不再由我们判断,一律读源头 daily.json 里每根 bar 自带的
#    `split_coefficient`。它的含义是「新股 / 旧股」,所以价格的理论比值 = 1 / 系数:
#    1 拆 3 → 系数 3 → 当天价格变成前一天的 1/3 → 我们把这一天之前的价格 ×(1/3) 接上去。
#
# ★ 为什么可以直接用、不存在双重修正:实测全池 66 个非 1 系数事件,
#   当天实际价格比值 ÷ (1/系数) ≈ 1.00(中位 1.00、绝大多数在 ±5% 内,
#   残差就是当天真实涨跌)。★ 说明源头价格是**未调整的 raw**,
#   该修的还得我们修 —— 这一条由 self_check() 的 ⑦ 项守着。
#
# ★★ 已知局限(必须讲清楚,不许装作解决了):
#   一、★ 13 只票的 split_coefficient 整列为空 / 缺字段:
#       AMRS CLVS COLM FRC GTT PRTY REV TFC TUP XPRO(全列空)
#       ACOR(2082 根里只有 2 根有值)· SQBG(1 根)· WPG(1 根)
#       → 恰好有值的那几根就是事件根,和技术方核实结果一致;但**不能假设这个字段齐全**。
#   二、★ 源头价格从 2016-01-01 起,所以 2016 年之前的拆股**没有系数根可读**。
#       实测受影响的是 KHC 2015 / PPG 2015 / SSP 2015 / LDOS 2016-09 / VIRT 2017-09
#       等股数跳变 —— 一律判「不可核实,不修」并报出来(都在绩效起点 2018-01-01 之前)。
#   三、★★ 换股并购在这个字段里是 1.0(= 明说不是拆股),所以**这个盲区还在**:
#       实测 7 只换股并购退市股(OCSI ALXN DFS HES KSU MRO XLNX)在价格上
#       零痕迹、系数也全是 1。★ 要补这个洞只能靠一份真正的公司行动流水表,仓库里没有。
#       → merger_blind_spot() 把它列出来,self_check() 每次打印,不许当问题没了。

#: 认为「系数有效」的下限 —— 系数必须是正数且不等于 1
_COEF_EPS = 1e-9

#: 常见拆股 / 合股比例(只用于**标注**是不是标准比例,★ 不用于判断修不修)
_STD_RATIOS: tuple[float, ...] = (1.25, 1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0,
                                  9.0, 10.0, 12.0, 20.0, 30.0, 40.0, 50.0, 100.0)

#: ★ 总开关:关掉就退回「只用 FIX_EVENTS 手工清单」。
#  只给 run_split_bias.py 的 A/B 对照用,★ 生产一律 True。
USE_SOURCE_COEFFICIENTS: bool = True


def classify_coefficient(coef: float) -> str:
    """
    给一个系数贴标签。★ 只是标注,不影响修不修 —— 修不修只看「系数是不是非 1」。

    标准拆股/合股 : 系数或其倒数贴近常见比例(容差 3%)
    非标准比例     : 其余 —— 实测这一类是**股票股利或分拆**
                    (如 CBSH 每年 1.05 = 5% 股票股利;EXC 1.402 = Constellation 分拆)
                    ★ 这一类的口径需要拍板,见 nonstandard_events()
    """
    if coef <= _COEF_EPS:
        return "系数无效"
    for c in _STD_RATIOS:
        for cand in (c, 1.0 / c):
            if abs(coef - cand) <= 0.03 * cand:
                return "标准拆股/合股"
    return "非标准比例(股票股利/分拆)"


def ratio_events_from_rows(symbol: str, rows: list[dict]) -> list[SplitEvent]:
    """
    ★ 从源头 daily.json 的原始 bar 列表里读出比例修正事件。

    纯函数(不读文件、不 import data)—— 这样 data.load_daily() 可以在它已经
    拿在手里的 rows 上直接调用,★ 不会和 data.py 形成循环依赖、也不会重复读盘。

    返回的每个事件:ratio = 1 / coefficient,action = "ratio_fix"。
    ★ 系数为空 / NaN / 1.0 的 bar 一律跳过(= 那天没有拆股)。
    """
    if not USE_SOURCE_COEFFICIENTS:
        return []
    out: list[SplitEvent] = []
    for r in rows:
        v = r.get("split_coefficient")
        if v is None:
            continue
        try:
            coef = float(v)
        except (TypeError, ValueError):
            continue
        if coef != coef:                      # NaN
            continue
        if coef <= _COEF_EPS or abs(coef - 1.0) <= _COEF_EPS:
            continue
        d = r.get("date")
        if not d:
            continue
        out.append(SplitEvent(
            symbol, str(d)[:10], "ratio_fix",
            ratio=1.0 / coef, coefficient=coef,
            label=f"源头系数 {coef:g}({classify_coefficient(coef)})",
            verdict="来自 daily.json 的 split_coefficient,★ 不是我们自己判断的",
            source=f"pilot_300/{symbol}/daily.json .data[].split_coefficient",
        ))
    return out


def events_for(symbol: str) -> list[SplitEvent]:
    """
    ★ 手工比例修正事件。现在恒为空 —— 比例修正一律走 ratio_events_from_rows()。
    ★ 保留这个函数是因为 run_split_bias.py 的 A/B 对照会 monkeypatch FIX_EVENTS,
      把旧的错清单塞回来跑对照组。
    """
    return [e for e in FIX_EVENTS if e.symbol == symbol]


def cuts_for(symbol: str) -> list[SplitEvent]:
    """要切断序列的断裂点(data.py 用)。"""
    return [e for e in CUT_EVENTS if e.symbol == symbol]


def candidate_dates() -> list[tuple[str, str]]:
    """原来那 8 条候选的 (symbol, date) —— 自检要逐个断言。"""
    return [(c.symbol, c.candidate_date) for c in CANDIDATES]


def summary() -> str:
    lines = [
        "拆股闸(2026-10-29 按技术方 SEC 核实结果重写):",
        f"  比例修正 {len(FIX_EVENTS)} 处 / 序列切断 {len(CUT_EVENTS)} 处 / "
        f"明确不动 {len(NO_ACTION_EVENTS)} 处",
        f"  ★ 因判不准被剔除的票:{sorted(EXCLUDED_SYMBOLS) or '无(原来是 AMRS / PRTY,已收回)'}",
        "  ★★ 比例修正的来源 = 源头 daily.json 的 split_coefficient"
        f"(USE_SOURCE_COEFFICIENTS={USE_SOURCE_COEFFICIENTS});"
        "手工 ratio_fix 清单已删空",
        "  ★ 源头价格是 raw(未调整),所以该修的我们修一次 → 不存在双重修正"
        "(self_check ⑦ 项守着)",
        "",
        "  8 条候选的下场:",
    ]
    for c in CANDIDATES:
        lines.append(f"    {c.symbol:5s} {c.candidate_date}  我们原来:{c.our_old_claim}"
                     f" / {c.our_old_action}")
        lines.append(f"            核实:{c.verified}")
        lines.append(f"            现在:{c.now}")
    lines.append("")
    lines.append("  ★★ 待 Lin 拍板:")
    for n in NEEDS_RULING:
        lines.append(f"    · {n}")
    lines.append("  ★ 数据完整性遗留问题:")
    for n in DATA_INTEGRITY_FLAGS:
        lines.append(f"    · {n}")
    return "\n".join(lines)


# ───────────────────────────────── ④ 自检 ─────────────────────────────────

JUMP_LO, JUMP_HI = 0.5, 2.0      # 修正后「不该再有假跳变」的合理区间


def self_check(verbose: bool = True) -> tuple[bool, str]:
    """
    ★ 对原来那 8 条候选的日期★ 逐个断言,一条都不许漏。

    每一条按它的处理方式断言不同的东西 —— ★ 这是故意的,不是放水:
      ratio_fix  → 修正后跳变必须落在 [0.5, 2.0](假跳变已经抹平)
      cut_series → 那一天必须「切不出跨断裂的收益」:
                   要么已经不在序列里,要么已经是序列的第一根
      no_action  → 跳变必须和原始数据★ 一模一样(证明我们真的没动它),
                   并且把实际跳变报出来 —— ★ 这几根本来就是真实的暴涨暴跌,
                   硬套 [0.5, 2.0] 才是错的
    """
    import pandas as pd
    from . import cache

    c = cache.load()["close"]
    # ★ 现在 ratio_fix 来自源头系数,不在 EVENTS 里 —— 所以查动作要两头都看
    by_date: dict[tuple[str, str], SplitEvent] = {
        (e.symbol, e.date): e for e in EVENTS}
    for sym, date, want, _why in TECH_VERIFIED_COEFFICIENTS:
        if (sym, date) in by_date:
            continue
        got = _coef_on(sym, date)
        if got is not None and USE_SOURCE_COEFFICIENTS:
            by_date[(sym, date)] = SplitEvent(
                sym, date, "ratio_fix", ratio=1.0 / got, coefficient=got,
                label=f"源头系数 {got:g}")
    lines, ok = [], True

    def jump(sym: str, date: str):
        """返回 (跳变倍数, 状态)。状态: ok / not_in_series / first_bar / not_trading_day"""
        if sym not in c.columns:
            return None, "not_in_series"
        s = c[sym].dropna()
        ts = pd.Timestamp(date)
        if ts not in s.index:
            return None, "not_in_series"
        i = s.index.get_loc(ts)
        if i == 0:
            return None, "first_bar"
        prev = s.iloc[i - 1]
        return (float(s.iloc[i] / prev) if prev else None), "ok"

    for cand in CANDIDATES:
        sym, date = cand.symbol, cand.candidate_date
        # 这条候选现在对应的动作:同日的 EVENTS 优先,否则看这只票有没有 cut
        ev = by_date.get((sym, date))
        j, st = jump(sym, date)

        if ev is not None and ev.action == "ratio_fix":
            good = j is not None and JUMP_LO <= j <= JUMP_HI
            lines.append(
                f"  {sym:5s} {date}  ratio_fix ×{ev.ratio:g}  修正后跳变 "
                f"{j:.3f}x  {'✅ 已在 [0.5,2.0]' if good else '★ 还有假跳变!'}")
        elif ev is not None and ev.action == "cut_series":
            good = st in ("not_in_series", "first_bar")
            lines.append(
                f"  {sym:5s} {date}  cut_series keep={ev.keep}  序列状态 "
                f"{st}  {'✅ 已切开,跨断裂的收益不存在' if good else f'★ 断裂还在,跳变 {j:.3f}x'}")
        else:
            # no_action:断言我们确实没动 —— 和源头原始跳变逐位对上
            raw = _raw_jump(sym, date)
            good = (j is not None and raw is not None
                    and abs(j - raw) < 1e-6)
            tail = ("(AMRS / PRTY:这是真实暴跌,该留)" if sym in ("AMRS", "PRTY")
                    else "(★ PROP:这 4.0x 没有拆股证据,★ 按 Lin 的指示原样留着,"
                         "★ 是遗留风险,见 DATA_INTEGRITY_FLAGS)")
            lines.append(
                f"  {sym:5s} {date}  no_action  跳变 {j if j is None else f'{j:.4f}'}x "
                f"(源头原始 {raw if raw is None else f'{raw:.4f}'}x)  "
                f"{'✅ 确实一个数都没动 ' + tail if good else '★ 被动过了!'}")
        ok &= bool(good)

    # ACOR 的真实事件日不在 8 条候选里,单独断言一次
    j, st = jump("ACOR", "2021-01-04")
    lines.append(f"  ACOR  2021-01-04  技术核实的真事件日,序列状态 {st}"
                 f"{'' if j is None else f',跳变 {j:.3f}x'}"
                 f"  (★ 已被 2021-11-30 的 cut 吞掉,属预期)")

    # 没有任何票被整只剔除
    ok &= (len(EXCLUDED_SYMBOLS) == 0)
    lines.append(f"  ★ 整只剔除的票:{sorted(EXCLUDED_SYMBOLS) or '无'} "
                 f"{'✅ AMRS / PRTY 已归队' if not EXCLUDED_SYMBOLS else '★ 还有票被剔'}")
    for s in ("AMRS", "PRTY"):
        inp = s in c.columns
        ok &= inp
        lines.append(f"  {s:5s} 在池子里:{'✅ 是' if inp else '★ 不在!'}")

    # ───────────── ⑥ 源头系数 vs 技术方核实结果:逐条断言 ─────────────
    lines.append("")
    lines.append("  ⑥ ★★ 源头 split_coefficient vs 技术方 SEC 核实结果(逐条):")
    a_ok, a_lines = coefficient_agreement()
    lines += a_lines
    ok &= a_ok

    # ───────────── ⑦ 源头价格是 raw(= 不存在双重修正) ─────────────
    lines.append("")
    lines.append("  ⑦ ★★ 源头价格是否未调整(raw)—— 双重修正的防线:")
    r_ok, r_lines = source_prices_are_raw()
    lines += r_lines
    ok &= r_ok

    # ───────────── ⑧ KHC 回归:并购不许被当成拆股 ─────────────
    lines.append("")
    lines.append("  ⑧ ★★ KHC 回归测试(并购不许被误判成拆股):")
    k_ok, k_lines = khc_regression()
    lines += k_lines
    ok &= k_ok

    # ★ 残余扫描:全池还剩多少根 3 倍以上的单日跳变 —— ★ 不许藏起来
    lines.append("")
    res = residual_jumps(min_jump=3.0)
    lines.append(f"  ★ 全池残余 3 倍以上单日跳变 {len(res)} 根"
                 f"{'(✅ 一根不剩)' if not res else ':'}")
    for sym, d, jj in res:
        lines.append(f"      {sym:5s} {d}  {jj:.2f}x  ★ 遗留,未修(没有核实证据)")

    # ★★ 盲区:接了源头系数也补不上的那一类 —— ★ 每次都打印,不许当问题没了
    lines.append("")
    lines += merger_blind_spot()
    lines.append("")
    lines += nonstandard_events()

    text = "\n".join(lines)
    if verbose:
        print(text)
    return ok, text


#: ★★ 技术方 SEC 核实过的 7 个争议点 —— 源头系数必须和它们逐条一致。
#  这是「源头系数能不能替掉手工清单」的全部依据,★ 任一条不一致就不许用源头系数。
#  格式:(ticker, 日期, 期望系数 或 None 表示"该日不该有非1系数")
TECH_VERIFIED_COEFFICIENTS: tuple[tuple[str, str, float | None, str], ...] = (
    ("ACOR", "2021-01-04", 1 / 6, "SEC 确认 1 合 6"),
    ("ACOR", "2023-06-05", 0.05, "SEC 确认 1 合 20"),
    ("WPG", "2020-12-22", 1 / 9, "SEC 确认 1 合 9(我们原来记 8 合 1 是错的)"),
    ("SQBG", "2020-07-27", 0.025, "SEC + Nasdaq 确认 1 合 40(我们原来记 1200 合 1)"),
    ("AMRS", "2023-08-10", None, "不是拆股 —— 是破产申请,★ −80.7% 是真实亏损"),
    ("PRTY", "2019-11-07", None, "不是拆股 —— 文件里只是授权,没实施"),
    ("UHAL", "2022-11-10", None, "不是拆股 —— 每股派 9 股新类别股(股票股利)"),
    # ★ KHC:股数闸原来把 3.0053x 误判成 1 拆 3,真相是 Kraft×Heinz 合并。
    #   源头系数在 KHC 上恒为 1 → 正确地否掉了它。这是回归测试的锚点。
    ("KHC", "2015-09-27", None, "不是拆股 —— 2015 Kraft×Heinz 合并(真实股本扩张)"),
)


def _coef_on(symbol: str, date: str) -> float | None:
    """读某只票某一天的源头系数(非 1 才返回)。★ 直接读文件,不走 load_daily。"""
    import json
    import os
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    p = os.path.join(base, "pilot_300", symbol, "daily.json")
    if not os.path.exists(p):
        return None
    try:
        with open(p, encoding="utf-8") as fh:
            rows = (json.load(fh).get("data") or [])
    except (OSError, ValueError):
        return None
    for r in rows:
        if str(r.get("date", ""))[:10] != date:
            continue
        v = r.get("split_coefficient")
        if v is None:
            return None
        try:
            c = float(v)
        except (TypeError, ValueError):
            return None
        if c != c or abs(c - 1.0) <= _COEF_EPS:
            return None
        return c
    return None


def coefficient_agreement() -> tuple[bool, list[str]]:
    """
    ★★ ⑥ 源头系数 vs 技术方 SEC 核实结果 —— 逐条断言。

    这是「可以拿源头系数替掉手工清单」的全部依据。★ 任一条不一致,
    就说明源头系数不可信,必须退回手工清单(把 USE_SOURCE_COEFFICIENTS 设成 False)。
    """
    ok, lines = True, []
    for sym, date, want, why in TECH_VERIFIED_COEFFICIENTS:
        got = _coef_on(sym, date)
        if want is None:
            good = got is None
            lines.append(f"  {sym:5s} {date}  期望「无非1系数」  实际 "
                         f"{'无' if got is None else f'{got:g}'}  "
                         f"{'✅ 一致' if good else '★ 不一致!'}  {why}")
        else:
            good = got is not None and abs(got - want) <= 0.02 * want
            lines.append(f"  {sym:5s} {date}  期望系数 {want:.6g}  实际 "
                         f"{'无' if got is None else f'{got:.6g}'}  "
                         f"{'✅ 一致' if good else '★ 不一致!'}  {why}")
        ok &= good
    return ok, lines


def source_prices_are_raw(tol: float = 0.35) -> tuple[bool, list[str]]:
    """
    ★★ ⑦ 断言源头价格是**未调整的 raw** —— 这是「我们还得自己修」的前提,
    也是「不会双重修正」的证明。

    做法:对每个非 1 系数事件,看当天**原始** close 比值 ÷ (1/系数)。
      ≈1 → 源头没动价格(raw),我们修是对的。
      ≈1/系数的倒数(即比值≈系数)→ 源头已经修过了,★ 我们再修就是双重修正。
    ★ 这里用中位数判断,单只票的残差是当天真实涨跌,不该要求为 0。
    """
    import json
    import os
    import numpy as np
    import pandas as pd
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    ratios, n_ev = [], 0
    for sym in sorted(os.listdir(os.path.join(base, "pilot_300"))):
        p = os.path.join(base, "pilot_300", sym, "daily.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                rows = (json.load(fh).get("data") or [])
        except (OSError, ValueError):
            continue
        evs = ratio_events_from_rows(sym, rows) if USE_SOURCE_COEFFICIENTS else []
        if not evs:
            continue
        df = pd.DataFrame(rows)
        df["date"] = pd.to_datetime(df["date"])
        c = pd.to_numeric(df.set_index("date").sort_index()["close"], errors="coerce").dropna()
        c = c[c > 0]
        for e in evs:
            ts = pd.Timestamp(e.date)
            if ts not in c.index:
                continue
            i = c.index.get_loc(ts)
            if i == 0:
                continue
            obs = float(c.iloc[i] / c.iloc[i - 1])
            ratios.append(obs / e.ratio)       # e.ratio = 1/系数
            n_ev += 1
    if not ratios:
        return False, ["  ★ 一个系数事件都没读到 —— 源头系数可能没接上"]
    med = float(np.median(ratios))
    good = abs(med - 1.0) <= tol
    lines = [
        f"  扫到 {n_ev} 个非 1 系数事件,(当天原始价格比值 ÷ 1/系数) 的中位数 = {med:.4f}",
        f"  {'✅ ≈1 → 源头价格是 raw,该修的得我们修,不存在双重修正' if good else '★ 偏离 1!源头可能已经调整过价格 —— 再修就是双重修正,立刻停用源头系数'}",
    ]
    return good, lines


#: ★★ 换股并购盲区 —— 价格上零痕迹、系数恒为 1,★ 这个洞接了源头系数也没补上。
#  判定依据:manifest.csv 的 retirement_category == 'ACQUISITION_STOCK'
MERGER_BLIND_SPOT_SYMBOLS: tuple[str, ...] = (
    "OCSI", "ALXN", "DFS", "HES", "KSU", "MRO", "XLNX",
)


def merger_blind_spot() -> list[str]:
    """
    ★★ 列出「接了源头系数之后仍然看不见」的那一类事件。

    ★ 为什么必须每次打印:接源头系数只解决了**拆股**。换股并购在价格上是连续的
      (换股比例接近 1:1),split_coefficient 在换股日也是 1.0 —— 两个信号都为零。
      ★ 不打印就会让人以为"接了官方字段,问题没了"。它没没了。
    """
    import os
    import json
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lines = [
        "  ★★ 换股并购盲区(接了源头系数也补不上)—— 需要一份公司行动流水表:",
    ]
    for sym in MERGER_BLIND_SPOT_SYMBOLS:
        p = os.path.join(base, "pilot_300", sym, "daily.json")
        n_coef = 0
        if os.path.exists(p):
            try:
                with open(p, encoding="utf-8") as fh:
                    rows = (json.load(fh).get("data") or [])
                n_coef = len(ratio_events_from_rows(sym, rows))
            except (OSError, ValueError):
                pass
        lines.append(f"      {sym:6s} retirement_category=ACQUISITION_STOCK  "
                     f"源头非1系数 {n_coef} 个  价格 ≥3x 跳变 0 根  "
                     f"→ ★ 两个信号都为零,看不见")
    lines += [
        "      ★ 结论:这 7 只的换股事件我们【仍然无法识别】。"
        "在世公司的并购同样不覆盖。",
        "      ★ 唯一的解法是补事件流水表(ticker + ex_date + event_type + "
        "exchange_ratio + 对手方),仓库里没有。",
    ]
    return lines


def nonstandard_events() -> list[str]:
    """
    ★★ 系数非标准比例的事件 —— 实测是**股票股利 / 分拆**,★ 口径需要拍板。

    ★ 为什么单独列出来:这些事件我们现在和拆股**一视同仁地修了**。
      对股票股利(如 CBSH 每年 1.05)这么做是对的 —— 股数真的变多了。
      ★ 但对**分拆**(如 EXC 1.402 = Constellation 分拆)这么做是一个近似:
        股东拿到的是**另一家公司**的股票,不是本公司更多的股票。
        按系数修 = 假设你在分拆当天按隐含价把分拆出来的那部分卖了。
      ★ 这是行业惯例(供应商给出这个系数就是这个用意),但它是近似,不是恒等。
      ★ 默认:照系数修(否则会在 EXC / MSGS / WDC 上吃一天 −29% 的假亏)。
        要改成不修,把这些票的系数在 ratio_events_from_rows 里跳过即可。
    """
    import os
    import json
    base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    rows_out = []
    for sym in sorted(os.listdir(os.path.join(base, "pilot_300"))):
        p = os.path.join(base, "pilot_300", sym, "daily.json")
        if not os.path.exists(p):
            continue
        try:
            with open(p, encoding="utf-8") as fh:
                rows = (json.load(fh).get("data") or [])
        except (OSError, ValueError):
            continue
        for e in ratio_events_from_rows(sym, rows):
            if e.coefficient and classify_coefficient(e.coefficient).startswith("非标准"):
                rows_out.append((sym, e.date, e.coefficient))
    lines = [f"  ★ 非标准比例(股票股利 / 分拆)事件 {len(rows_out)} 个 —— "
             f"★ 默认照系数修,口径待拍板:"]
    for sym, d, c in sorted(rows_out):
        lines.append(f"      {sym:6s} {d}  系数 {c:g}  "
                     f"(价格 ×{1 / c:.4f})")
    return lines


def khc_regression() -> tuple[bool, list[str]]:
    """
    ★★ ⑧ KHC 回归测试 —— 防止「并购换股被当成拆股修掉」这个 bug 回来。

    事故原文:股数闸原来的判据是「实测倍数贴近常见拆股比例 ±3% 就按拆股修」。
    KHC 2015-09-27 实测 3.0053x 贴近 3x,被判为 1 拆 3 并做了修正。
    ★ 真相是 2015 年 Kraft 与 Heinz 合并 —— 真实股本扩张,修了就把真事件抹掉。

    断言三件事:
      ① KHC 在源头系数里没有任何非 1 系数(= 源头正确地说"这不是拆股")
      ② 股数闸扫 KHC 2015-09-27 这一处,action 必须是 leave_as_is
      ③ 股数闸过完之后,KHC 2015-06-28 那一期的股数必须等于**原始申报值**
         (= 我们确实没有乘 3)
    """
    from . import share_gate
    import pandas as pd
    lines, ok = [], True

    # ① 源头系数
    n = len([1 for _ in TECH_VERIFIED_COEFFICIENTS])  # noqa: F841 (仅为可读)
    got = _coef_on("KHC", "2015-09-27")
    g1 = got is None
    lines.append(f"      ① KHC 源头非1系数:{'无' if got is None else got} "
                 f"{'✅ 源头说这不是拆股' if g1 else '★ 源头给了系数?'}")
    ok &= g1

    # ② 股数闸的判定
    target = pd.Timestamp("2015-09-27")
    js = [j for j in share_gate.scan("KHC") if j.period_end == target]
    g2 = bool(js) and all(j.action == "leave_as_is" for j in js)
    if js:
        for j in js:
            lines.append(f"      ② 股数闸 KHC {j.period_end.date()} 实测 "
                         f"{j.ratio:.4f}x → action={j.action}  "
                         f"{'✅ 没当成拆股' if j.action == 'leave_as_is' else '★ 又被当成拆股了!'}")
    else:
        lines.append("      ② ★ 没扫到 KHC 2015-09-27 这处跳变 —— 回归测试失去锚点")
    ok &= g2

    # ③ 过闸后的值必须是原始申报值
    raw = {p.period_end: p.shares for p in share_gate.quarterly_points("KHC")}
    adj = {p.period_end: p.shares for p in share_gate.adjusted_points("KHC")}
    probe = pd.Timestamp("2015-06-28")
    g3 = (probe in raw and probe in adj
          and abs(raw[probe] - adj[probe]) <= 1e-6 * max(1.0, abs(raw[probe])))
    lines.append(
        f"      ③ KHC {probe.date()} 原始申报 "
        f"{raw.get(probe, float('nan')):,.0f} / 过闸后 "
        f"{adj.get(probe, float('nan')):,.0f}  "
        f"{'✅ 一个数都没动' if g3 else '★ 被乘过了!'}")
    ok &= g3
    return ok, lines


def residual_jumps(min_jump: float = 3.0) -> list[tuple[str, str, float]]:
    """
    ★ 修完之后全池还剩哪些 3 倍以上的单日跳变。
    ★ 这是「我们还欠多少」的诚实清单 —— 自检会把它打出来,不许藏。
    """
    import numpy as np
    from . import cache
    c = cache.load()["close"]
    out: list[tuple[str, str, float]] = []
    for sym in c.columns:
        s = c[sym].dropna()
        s = s[s > 0]
        if len(s) < 2:
            continue
        r = (s / s.shift(1)).to_numpy(float)[1:]
        hit = np.flatnonzero((r >= min_jump) | (r <= 1.0 / min_jump))
        for k in hit:
            out.append((sym, str(s.index[k + 1].date()), float(r[k])))
    return sorted(out)


def _raw_jump(symbol: str, date: str) -> float | None:
    """直接从源头 daily.json 读原始跳变,用来证明 no_action 真的没动过。"""
    import json
    import os
    from . import data
    try:
        meta = data.load_manifest()[symbol]
    except KeyError:
        return None
    if not os.path.exists(meta.daily_path):
        return None
    with open(meta.daily_path, encoding="utf-8") as fh:
        rows = (json.load(fh).get("data") or [])
    rows = sorted(rows, key=lambda r: r["date"][:10])
    idx = {r["date"][:10]: i for i, r in enumerate(rows)}
    i = idx.get(date)
    if i is None or i == 0:
        return None
    prev = rows[i - 1].get("close")
    cur = rows[i].get("close")
    if not prev or cur is None:
        return None
    return float(cur) / float(prev)


if __name__ == "__main__":
    print(summary())
    print()
    print("=" * 78)
    print("★ 自检:对原来那 8 条候选的日期逐个断言")
    print("=" * 78)
    good, _ = self_check()
    print()
    print("★ 全绿" if good else "★ 有红的 —— 不要往下跑")
    raise SystemExit(0 if good else 1)
