"""
配置适配层 —— 把「流派配置」那套字段名翻成执行器的七步接口。

大白话:三流派配置(trend_following / vcp_momentum / liquidity_sweep)是另一条线
写的,字段名和模板不一样:它用 stop_init / stop_trail / slots / ranking,
模板用 initial_stop / trailing_stop / sizing.params.max_positions。
两套名字不一致,所以那三份配置原来根本加载不了。

这个文件干两件事:
  一、名字对齐 —— 两套名字都认,不用去改那三份配置
  二、★ 把「还没实现的规则」明确报出来 —— 列出每一条的名字和原因,
      而不是悄悄忽略。悄悄忽略最危险:配置里写了基本面闸门、
      引擎没执行,跑出来的成绩会凭空变好,而且没人知道。
      (硬纪律第 7 条:拿不到就说拿不到,不要用近似值顶上。)

★ 有两类「还没实现」要分清楚:
  A. 引擎没写 —— 规则讲得清楚,是工作量问题,补代码就行
  B. ★ 配置本身没定 —— params 里是 null,或那条线自己标了 audit_blocked,
     说明连定义都还没定下来。这类不能猜,必须等那条线给定义。
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field

# 字段别名:流派配置的名字 → 执行器的名字
STEP_ALIASES = {
    "stop_init": "initial_stop",
    "stop_trail": "trailing_stop",
}

# 已实现的规则类型(按步分),其余一律报出来
IMPLEMENTED = {
    "universe": {
        "price_above_ma",
        "adv_rank_exclude_bottom",
        "dollar_volume_rank_exclude_bottom",
        "return_rank_top",
        "ma_stack_bullish",
        "hv_below",
        "return_rank_percentile",
        "momentum_dual_gate",
        "mansfield_rs_positive",      # ★ 只有 against: SPY 能跑;SECTOR 非 PIT,见下
        # ★ 1029 新实现:基本面 PIT 闸门(engine/fundamentals.py)
        "fcf_yield_rank_top",         # FCF Yield 池内横截面前 N%
        "sloan_accrual_below",        # Hribar & Collins (2002) 现金流量表法应计项
        "piotroski_f_score_above",    # Piotroski 9 项(★ 9 项全齐才算,否则判不合格)
        # ★★ 1029 第二轮裁决新实现(engine/ops_1029.py):
        #   F-Score 三层修补(行业豁免 / 容差缩放 / 严重缺失降级)
        "piotroski_f_score_three_layer",
        #   Altman Z'' 池内分位闸门。★ 注意:分位闸门对 Altman 的系数版本
        #   **不敏感** —— 加常数是所有票同时平移,横截面排序一字不变,
        #   所以「系数版本三轮未答」在这一条上不卡。
        "altman_z_double_prime_exclude_bottom",
    },
    "regime": {
        "none", "index_above_ma", "index_above_ma_scaled", "index_ma_slope",
        "breadth_above", "vix_below", "no_distribution_day", "no_large_down_day",
        # ★ 1028 闸门新方案:本链自己选股范围的广度当开关(G4 对照用)
        "breadth_above_chain",
        # ★ 1029 新实现:11 只板块 ETF 的扩散指数
        "sector_diffusion_above",
    },
    "entry": {
        "donchian_close_breakout", "donchian_breakout", "atr_squeeze",
        "volume_dryup", "ma_cross", "rsi_oversold", "roc_momentum",
        "pullback_to_ma", "always", "random", "never",
        # ★ 1028 新实现(专家第二轮把死数给齐了之后)
        "vcp_contraction", "sigma_squeeze",
        # ★★ 成交量门禁两条(专家 2026-10-29 最终裁决版)——
        #   取代 1028 的 vcp_volume_tripod(三条件全 AND)。
        #   ★ breakout_volume_band(含 1.80 上限)与 vcp_volume_tripod
        #     都已物理删除,并登记进 BLOCKED_REASONS,写了就报错。
        "vcp_volume_duo",
        # ★ 1029 新实现:深度价值派的「跌破后强力收复」+ 收盘站上 EMA
        "undercut_and_rally", "close_above_ema",
        # ★ 进场里的曼斯菲尔德 RS:★ 只有 against: SPY 能跑(SECTOR 非 PIT)
        "mansfield_rs_positive",
        # ★★ 1029 第二轮裁决新实现(engine/ops_1029.py):
        #   流派三:摆动波谷 = Connors 滚动 20 日绝对低点 + ★ 4 天存活门禁
        #   (出处已核实:Street Smarts 1995 Ch.4 Turtle Soup, Rule 2)
        "swing_low_exists", "intraday_break_below_swing_low",
        "close_reclaim_above_swing_low", "bullish_candle",
        #   流派一:双阶段状态机(触底排毒 T0 → 10 日内均线收复)
        "deep_value_two_stage",
        # ★★ 1029 A0 十二条新增（engine/ops_a0.py）
        "monthly_sma_above",      # 技-2 法伯 10 月线
        "turtle_soup",            # 技-10 海龟汤（两版；收盘确认必须显式写）
        "htf_flag_breakout",      # 技-8 高紧旗形（runup_min / max_pullback 必须显式写）
        "td_buy_setup",           # 技-13 TD Buy Setup 9
        "td_buy_countdown",       # 技-13 TD Buy Countdown 13
    },
    "exit": {
        "close_below_ma", "close_below_ema", "close_below_trailing_stop",
        # ★★ 1029 A0 新增
        "close_below_lowest_low",  # 技-1 海龟反向通道退出
        "close_above_ma",         # 技-12 康纳斯：回到 5 日均线之上就走
        "monthly_sma_below",      # 技-2 法伯：月末跌破 10 月线清仓
        "rules", "signal_only",     # 适配层自己塞的标记,不是规则
        # ★ 1029 新实现:基本面季度否决 / 季度再平衡(PIT 生效日触发)
        "fundamental_quarterly_reject", "fundamental_quarterly_rebalance",
        "time_stop",
    },
    "initial_stop": {
        "atr_multiple", "pct", "chandelier", "lowest_low", "tightest_of",
        "structure_low_minus_atr", "day_low_minus_atr",
        # ★★ 1029:流派一双阶段状态机的 T0 绝对初始止损锚点
        #   Stop = Low[T0] − 0.5 × ATR14[T0](T0 = 第一阶段那根,不是进场那根)
        "t0_anchor_stop",
        # ★★ 1029 A0：「原著不设止损」的显式写法（技-2 法伯 / 技-12 康纳斯）
        #   止损价 = 0.0，只有破产退市那根 0 价 bar 才触发
        "none",
    },
    "trailing_stop": {"chandelier", "none", "staged", "ema_trail",
                      # ★ 1029 新实现:Stop_t = max(Stop_{t−1}, LowestLow_N)
                      "lowest_low_trail"},
}

# ⑤ 移动止损各级认得的 action
IMPLEMENTED_STAGE_ACTIONS = {
    "hold_initial_stop", "move_to_breakeven", "breakeven",
    "move_stop_to_breakeven", "exit_unconditional",
    # ★ 1029 新实现:分级里直接写 action 的两种跟踪止损
    "chandelier", "lowest_low_trail",
}

# 明确「配置本身没定」的规则:为什么不能猜
BLOCKED_REASONS = {
    # ★ vcp_contraction 已解封:专家第二轮把全部死数给齐了(分型半宽 2 /
    #   D1≤30% / 递减 0.65 / 2~4 次 / 15~65 天 / 振幅分母用段高点),
    #   1028 已在 matrices.vcp_matrices 实现。★ 仍有一处口径待专家确认:
    #   「形态成立后门禁开多久」——专家没说,引擎用的机械读法写在
    #   matrices.py VCP 那一段的注释里,报告里也列为待确认项。
    "rotate_out": "⑤「滞涨换血」的触发条件 candidate_pool_has_new_high_signal 没定义"
                  "(新高是几日新高?动量怎么比?)—— 不能猜,见审计 §2-C",
    # ★★ 2026-10-29 第二轮裁决:下面这三条**已解封**,定义到位、4 天规则到位:
    #   摆动波谷 = Connors 滚动 20 日绝对低点 min(Low[t−20..t−1]);
    #   Age_Gate = t − t_low ≥ 4 个交易日
    #   ★ 出处已亲自核实原文:Connors & Raschke《Street Smarts》(1995)
    #     Ch.4 "Turtle Soup", Rule 2 —— "The previous 20-day low must have
    #     occurred at least four trading sessions earlier. This is very important."
    #   ★ 明确不复用流派二那个 5 根 Bar 的 2-1-2 分型(专家理由:2-1-2 每 3~5 天
    #     就造一个微观波谷,那里根本没有大规模止损盘)。实现在 engine/ops_1029.py。
    "credit_spread_weekly_change_below": "series 是 null,且仓库里没有信用利差数据 —— 拿不到",
    # ★★ 2026-10-29:altman_z_double_prime_exclude_bottom **已解封**。
    #   科目齐备率确实不高(实测绩效窗口内 25.6% 的格子算得出 Z''),
    #   ★ 但「算不出就不合格」本来就是这道闸的既定口径,不是不能跑的理由;
    #   ★ 而且它是**分位**闸门,对 Altman 的系数版本不敏感(加常数不改排序)。
    #   ★★ 必须跟着结果一起讲的局限:算不出的那 74.4% 格子会被判出局,
    #     而算不出最集中的恰恰是银行 / REIT(它们不报流动资产/流动负债,
    #     而 X1 = 营运资金/总资产 正需要这两项)—— ★ 所以这道闸同样带
    #     系统性的行业选择偏差,方向和 F-Score 那道闸完全一样。
    "mktcap_rank_exclude_bottom":
        "仓库没有严格 PIT 的市值(README 明确说 WeightedAverageDilutedShares × 收盘价 "
        "只是规模代理,不是 PIT 市值)—— 改用 dollar_volume_rank_exclude_bottom 或等定义",
    # ★ 2026-10-28:GP/A 与净股东回报率从「绝对值阈值」改成「截面分位」
    #   (专家逐条承认原阈值标错)。★ 引擎还没写这两个截面分位算子 ——
    #   ★ 属于 A 类「引擎没写」,不是 B 类「定义没定」:口径已经明确,
    #     就是每个评估日在池内做横截面排序取前 20%,补代码即可。
    "gross_profit_to_assets_rank_above":
        "GP/A 的截面分位算子引擎还没写(A 类:口径已明确 = 池内横截面前 20%,"
        "补代码即可)—— 2026-10-28 从绝对值 0.35 改过来的",
    "net_shareholder_yield_rank_above":
        "净股东回报率的截面分位算子引擎还没写;★ 而且这一条底层数据本来就缺"
        "(35 个字段里没有任何偿债/举债的现金流科目,腿三算不出)",
    "mansfield_rs_positive":
        "against: SECTOR 这一条要个股→板块 ETF 的 PIT 映射,仓库的行业标签是"
        "当前快照、非 PIT —— 需先定映射口径",
    # ★ 2026-10-29 新增两条 B 类(配置本身没定,不能猜):
    "no_large_equity_issuance":
        "★ B 类:「大规模增发」的阈值专家原文没给(配置里 undefined_param 写着)。"
        "★ 不许借用流派三⑥那条 2.0% 稀释线顶上 —— 那是另一步的参数,跨步搬过来"
        "就等于我们自己定了一个闸门还假托有出处。要跑必须显式关掉并在报告里写明",
    "volume_confirm_moderate":
        "★ B 类:③ 突破扳机里的「温和放量」量比区间专家原文没给。"
        "★ 不许跨链搬流派二那边的数 —— ★ 而且流派二那个 [1.00, 1.80] 的"
        "**上限 1.80 已在 2026-10-29 被专家裁决物理删除**,更不存在可搬的东西",
    # ★★ 2026-10-29 按专家最终裁决物理删除的两个算子 ——
    #   登记在这里,所以任何配置再写它们会在预检就报错,不会悄悄跑过去。
    "breakout_volume_band":
        "★ 已物理删除(2026-10-29 专家最终裁决,Lin 已拍板)。它带的"
        "**1.80 倍上限**会在算法层面精准击杀爆发力最凶猛的前 5% 领头羊,"
        "专家自判为【IS-只让样本内好看】,原话「坚决不要保留,彻底物理删除」。"
        "★ 突破日放量请改用 vcp_volume_duo 的门禁2(只有下界、没有上界)",
    "vcp_volume_tripod":
        "★ 已物理删除(2026-10-29 专家最终裁决,Lin 已拍板)。三条件全部 AND 是"
        "样本从 289 雪崩到 15 的唯一真凶 —— 其中条件2(SMA5 ≤ 0.85×SMA50)与"
        "条件1 高度共线、冗余,专家承认是研究员自己加的过度约束。"
        "★ 请改用 vcp_volume_duo(门禁1 单日地量 + 门禁2 突破日上 50 日均量)。"
        "★ 要复现 1028 那次 15 笔的结果,请 git checkout 022a3de",
}


@dataclass
class AdaptReport:
    renamed: list[str] = field(default_factory=list)
    unimplemented: list[tuple[str, str, str]] = field(default_factory=list)  # (步, 规则, 原因)
    # ★ 配置里 enabled: false 的规则 —— ★ 不是悄悄忽略,是配置自己显式关掉的,
    #   但照样要逐条列出来,并写进报告(缺了它这一派完不完整,由报告负责说明)
    disabled: list[tuple[str, str, str]] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.unimplemented

    def text(self) -> str:
        lines = []
        if self.renamed:
            lines.append(f"字段名已对齐:{', '.join(self.renamed)}")
        if self.disabled:
            lines.append("★ 配置里显式关掉的规则(enabled: false)—— "
                         "引擎没执行它们,报告里必须写明:")
            for step, rule, why in self.disabled:
                lines.append(f"    [{step}] {rule} —— {why}")
        if self.unimplemented:
            lines.append("★ 这些规则还没法跑(没有悄悄忽略,全列在这里):")
            for step, rule, why in self.unimplemented:
                lines.append(f"    [{step}] {rule}")
                lines.append(f"        原因:{why}")
        else:
            lines.append("全部规则都已实现,可以直接跑。")
        return "\n".join(lines)


def _off(node) -> bool:
    """这条规则是不是被配置显式关掉了(enabled: false)。"""
    return isinstance(node, dict) and node.get("enabled", True) is False


def _rule_types(block) -> list[str]:
    if not isinstance(block, dict):
        return []
    out = []
    for r in (block.get("rules") or []):
        if isinstance(r, dict) and r.get("type") and not _off(r):
            out.append(r["type"])
    if block.get("type"):
        out.append(block["type"])
    for c in (block.get("components") or []):
        if isinstance(c, dict) and c.get("type") and not _off(c):
            out.append(c["type"])
    for s in (block.get("stages") or []):
        if isinstance(s, dict) and s.get("type") and not _off(s):
            out.append(s["type"])
    return out


def adapt(raw: dict) -> tuple[dict, AdaptReport]:
    """
    把一份配置规范化成执行器能吃的形状,并报告哪些规则还没法跑。
    ★ 不改任何数值,只改字段名和结构。
    """
    cfg = copy.deepcopy(raw)
    rep = AdaptReport()

    # 一、字段名对齐
    for old, new in STEP_ALIASES.items():
        if old in cfg and new not in cfg:
            cfg[new] = cfg.pop(old)
            rep.renamed.append(f"{old} → {new}")

    # slots / ranking 并进 sizing
    sizing = cfg.setdefault("sizing", {})
    if not isinstance(sizing, dict):
        sizing = cfg["sizing"] = {}
    params = sizing.setdefault("params", {})
    if cfg.get("slots") is not None:
        params.setdefault("max_positions", int(cfg["slots"]))
        rep.renamed.append(f"slots({cfg['slots']}) → sizing.params.max_positions")
    else:
        # ★ 槽位没写就必须有个值,否则引擎不知道能同时持几只。
        #   这里不替配置猜,给一个明确的默认并记下来。
        params.setdefault("max_positions", 10)
        rep.renamed.append("slots 没写 → sizing.params.max_positions 默认 10(★ 需确认)")
    if cfg.get("ranking") is not None:
        sizing.setdefault("rank_by", cfg["ranking"])
        rep.renamed.append(f"ranking → sizing.rank_by")
    cfg.pop("slots", None)
    cfg.pop("ranking", None)
    cfg.pop("source_slots", None)

    # 多级移动止损:stages 形式 → type: staged
    ts = cfg.get("trailing_stop")
    if isinstance(ts, dict) and ts.get("stages") and not ts.get("type"):
        ts["type"] = "staged"
        rep.renamed.append("trailing_stop.stages → type: staged")

    # ★ 1029:分级写的是 from_r / to_r,执行器认的是 when.unrealized_r_*。
    #   ★ 这是纯粹的字段名翻译,★ 一个数值都没改。
    #   ★ 为什么必须翻:没有 when 的话 _stage_hits 对每一级都返回 True,
    #     执行器会永远取最后一级 —— 等于「未达 +2R 前锁死初始止损」这条
    #     根本没被执行,而且不报错。这正是「配置写了、引擎没干」那类 bug。
    for st in ((ts or {}).get("stages") or []):
        if not isinstance(st, dict) or st.get("when"):
            continue
        if "from_r" not in st and "to_r" not in st:
            continue
        lo, hi = st.get("from_r"), st.get("to_r")
        when: dict = {}
        if lo is not None and hi is not None:
            when["unrealized_r_between"] = [float(lo), float(hi)]
        elif lo is not None:
            when["unrealized_r_gt"] = float(lo) - 1e-12
        elif hi is not None:
            when["unrealized_r_lt"] = float(hi)
        st["when"] = when
        rep.renamed.append(
            f"trailing_stop 分级 from_r={lo}/to_r={hi} → when={list(when)[0]}")
        # 分级里只写了 action: chandelier / lowest_low_trail 时,把 type 也补上,
        # 这样执行器的两条铁律分支能认出来
        if st.get("action") in ("chandelier", "lowest_low_trail") and not st.get("type"):
            st["type"] = st["action"]

    # ★ 1029:初始止损 params 写成「候选列表」(tightest_of)→ components
    ist = cfg.get("initial_stop")
    if isinstance(ist, dict) and isinstance(ist.get("params"), list) \
            and not ist.get("components"):
        ist["components"] = ist.pop("params")
        rep.renamed.append("initial_stop.params(列表)→ initial_stop.components")
    # ★ 1029:止损距离上限写在顶层(max_stop_distance_pct + on_exceed)→ hard_gate
    if isinstance(ist, dict) and ist.get("max_stop_distance_pct") is not None \
            and not ist.get("hard_gate"):
        if str(ist.get("on_exceed", "reject_entry")) != "reject_entry":
            raise ValueError(
                f"initial_stop.on_exceed 只认 reject_entry,给的是 {ist.get('on_exceed')} "
                f"—— ★ 别的处理方式(比如把止损放大)引擎没实现,不许悄悄按默认处理。")
        ist["hard_gate"] = {
            "type": "max_stop_distance_pct",
            "params": {"max_pct": float(ist["max_stop_distance_pct"])},
        }
        rep.renamed.append(
            f"initial_stop.max_stop_distance_pct({ist['max_stop_distance_pct']}%) "
            f"→ hard_gate(超过就拒掉信号,不放大止损)")

    # exit 的 rules 形式 → 执行器的 signal_only + 规则列表
    ex = cfg.get("exit")
    if isinstance(ex, dict) and ex.get("rules") and not ex.get("type"):
        ex["type"] = "rules"
    # ★ 1029:时间止损写成 exit.rules 里的一条(max_holding_days)→ exit.params.time_stop_days
    for r in ((ex or {}).get("rules") or []):
        if isinstance(r, dict) and r.get("type") == "time_stop" and not _off(r):
            d = (r.get("params") or {}).get("max_holding_days")
            if d is None:
                raise ValueError("exit 的 time_stop 没给 max_holding_days —— 不许猜")
            ex.setdefault("params", {}).setdefault("time_stop_days", int(d))
            # ★ 纪律 6:参数搬到哪里,出处就跟到哪里。
            #   时间止损那条规则自己标的是「来源存疑」—— 原样带过来,不许洗白。
            ex.setdefault("source", r.get("source") or "来源存疑")
            rep.renamed.append(
                f"exit.rules.time_stop.max_holding_days({int(d)}) "
                f"→ exit.params.time_stop_days")

    # 七步齐不齐
    need = ["universe", "regime", "entry", "initial_stop",
            "trailing_stop", "exit", "sizing"]
    for k in need:
        cfg.setdefault(k, {})

    # 二、查哪些规则还没实现
    for step in ("universe", "regime", "entry", "initial_stop",
                 "trailing_stop", "exit"):
        for rt in _rule_types(cfg.get(step)):
            if rt in IMPLEMENTED.get(step, set()):
                continue
            why = BLOCKED_REASONS.get(
                rt, "引擎还没实现这条规则 —— 规则本身讲得清楚,是工作量问题")
            rep.unimplemented.append((step, rt, why))

    # ★ 配置里 enabled: false 的规则:逐条记下来(不进 unimplemented,但必须被看见)
    def _scan_disabled(node, path):
        if isinstance(node, dict):
            if _off(node):
                why = []
                if node.get("data_missing"):
                    why.append("配置标了 data_missing(数据拿不到)")
                if node.get("audit_blocked"):
                    why.append(f"audit_blocked={node['audit_blocked']}")
                rep.disabled.append((
                    path, node.get("name") or node.get("type") or "?",
                    ";".join(why) or "配置里 enabled: false"))
                return
            for v in node.values():
                _scan_disabled(v, path)
        elif isinstance(node, list):
            for v in node:
                _scan_disabled(v, path)

    for step in need:
        _scan_disabled(cfg.get(step), step)

    # ⑤ 各级的 action 也要查 —— 只查 type 会漏掉 rotate_out 这种「只有 action」的级
    for st in ((cfg.get("trailing_stop") or {}).get("stages") or []):
        if not isinstance(st, dict) or _off(st):
            continue
        act = st.get("action")
        if act and act not in IMPLEMENTED_STAGE_ACTIONS:
            rep.unimplemented.append((
                "trailing_stop",
                f"{st.get('name') or '?'}(action={act})",
                BLOCKED_REASONS.get(act, "引擎还没实现这一级的 action")))
        for cond in (st.get("when") or {}):
            if cond not in ("unrealized_r_gt", "unrealized_r_lt",
                            "unrealized_r_between", "days_held_gte",
                            "days_held_lte",
                            # ★★ 1029 第二轮新实现(A 类,口径本来就清楚):
                            #   close_above_ma 收盘站上 N 日均线(流派三 ⑤ 保本级)
                            #   after_stage    前一级已经触发过(分级有先后)
                            "close_above_ma", "after_stage"):
                rep.unimplemented.append((
                    "trailing_stop",
                    f"{st.get('name') or '?'}(when.{cond})",
                    "这个触发条件引擎认不出来 —— 认不出来的条件会让这一级永远不生效,"
                    "★ 所以在这里报出来,不留给它悄悄失效"))

    # ★ 非 PIT 数据的单独一关:against: SECTOR 的行业 RS
    for rule in ((cfg.get("universe") or {}).get("rules") or []):
        for comp in ([rule] + list(rule.get("components") or [])):
            if (comp.get("type") == "mansfield_rs_positive"
                    and str((comp.get("params") or {}).get("against", "")).upper() == "SECTOR"
                    and comp.get("enabled", True) is not False):
                rep.unimplemented.append((
                    "universe", "mansfield_rs_positive(against: SECTOR)",
                    BLOCKED_REASONS["mansfield_rs_positive"]))

    # audit_blocked 标记一并带出来(★ 已经被 enabled: false 显式关掉的不再重复报)
    def _scan_blocked(node, path):
        if isinstance(node, dict):
            if _off(node):
                return
            if node.get("audit_blocked"):
                rep.unimplemented.append(
                    (path, node.get("name") or node.get("type") or "?",
                     f"那条线自己标了 audit_blocked={node['audit_blocked']} —— 定义未定,不能猜"))
            for k, v in node.items():
                _scan_blocked(v, path)
        elif isinstance(node, list):
            for v in node:
                _scan_blocked(v, path)

    for step in need:
        _scan_blocked(cfg.get(step), step)

    return cfg, rep


def check_file(path: str) -> AdaptReport:
    """只做检查、不跑链:看一份配置离「能跑」还差什么。"""
    import json
    with open(path, encoding="utf-8") as fh:
        raw = (__import__("yaml").safe_load(fh)
               if path.endswith((".yaml", ".yml")) else json.load(fh))
    _, rep = adapt(raw)
    return rep


def main(argv: list[str] | None = None) -> int:
    import argparse
    import glob
    import os
    ap = argparse.ArgumentParser(
        description="检查配置能不能跑:对齐字段名,并列出还没实现的规则")
    ap.add_argument("configs", nargs="*",
                    help="配置文件;不给就检查 engine/configs/ 下全部")
    a = ap.parse_args(argv)
    paths = a.configs or sorted(
        glob.glob(os.path.join(os.path.dirname(__file__), "configs", "*.yaml")))
    bad = 0
    for p in paths:
        rep = check_file(p)
        print("=" * 72)
        print(os.path.basename(p), "—", "✅ 可以跑" if rep.ok else "⚠ 还差东西")
        print(rep.text())
        bad += 0 if rep.ok else 1
    print("=" * 72)
    print(f"共 {len(paths)} 份配置,{len(paths)-bad} 份可以跑,{bad} 份还差东西")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
