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
    # ── 技术方核实有证据的拆股 → 修
    SplitEvent(
        "ACOR", "2021-01-04", "ratio_fix", ratio=6.0, coefficient=1 / 6,
        label="1合6(2020-12-31 生效,2021-01-04 首个调整交易日)",
        verdict="SEC 确认 1 合 6 反向拆股;我们原来记的「2021-11-30 10合1」日期和比例都不对",
        source="sec.gov/Archives/edgar/data/1008848/000156459020058970/acor-ex991_25.htm",
    ),
    SplitEvent(
        "ACOR", "2023-06-05", "ratio_fix", ratio=20.0, coefficient=0.05,
        label="1合20",
        verdict="SEC 确认 1 合 20。★ 技术方同时警告:这只票的 daily.json 自称 raw,"
                "但观测价格和独立来源差 60 倍,口径不一致,用的时候要知道",
        source="sec.gov/Archives/edgar/data/1008848/000095017023026094/acor-ex99_1.htm",
    ),
    SplitEvent(
        "WPG", "2020-12-22", "ratio_fix", ratio=9.0, coefficient=1 / 9,
        label="1合9",
        verdict="SEC 确认 1 合 9。我们原来记的 8 合 1 是错的",
        source="sec.gov/Archives/edgar/data/1610911/000159468621000014/wpg-20210331.htm",
    ),

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
    "★ 源头 daily.json 里新增的 split_coefficient 字段,★ 引擎目前完全不读。"
    "本次是故意不读的(读了才会双重修正)。以后若要改成读源头系数,"
    "必须同时把这里的 ratio_fix 关掉,★ 两边只能有一边动手。",
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


def events_for(symbol: str) -> list[SplitEvent]:
    """要做比例修正的事件(data.py 用)。"""
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
        "  ★ 源头 daily.json 只加了 split_coefficient 标记字段,价格未改;"
        "引擎不读该字段 → 不存在双重修正",
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
    by_date = {(e.symbol, e.date): e for e in EVENTS}
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

    # ★ 残余扫描:全池还剩多少根 3 倍以上的单日跳变 —— ★ 不许藏起来
    res = residual_jumps(min_jump=3.0)
    lines.append(f"  ★ 全池残余 3 倍以上单日跳变 {len(res)} 根"
                 f"{'(✅ 一根不剩)' if not res else ':'}")
    for sym, d, jj in res:
        lines.append(f"      {sym:5s} {d}  {jj:.2f}x  ★ 遗留,未修(没有核实证据)")

    text = "\n".join(lines)
    if verbose:
        print(text)
    return ok, text


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
