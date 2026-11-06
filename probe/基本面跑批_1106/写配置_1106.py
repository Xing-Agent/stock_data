# -*- coding: utf-8 -*-
"""
★ 生成 A 路的基本面配置(基-4 是手写范本,不在这里生成)。
★★ 每份都带:meta.known_gap · meta.param_gap · 每条规则的 source(①原著 / ②行业通行 / ③我们的 / ④用户的 / ⑤外部模型说的·待核)
   · 扫参(相邻三点)。★★★ 卡原文逐句抄自 METHOD_LIBRARY/基-N.md 的「正文资料」。
★ 用法:python3 probe/基本面跑批_1106/写配置_1106.py  → 写到 configs/
"""
import io, os
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "configs")

PIT = {"effective": "filing_date_plus_1_trading_day", "update_frequency": "quarterly_discrete",
       "source": "★ 原著没写时点口径;★★ 引擎铁律(生效日 = 公布日 + 1 个交易日)"}
COSTS = {"friction_tiers": {"high_liquidity_bps": 5.0, "mid_liquidity_bps": 15.0,
                            "low_liquidity_bps": 30.0},
         "source": "行业惯例(★ 与其他链一致,便于横向比)"}
ENTRY = {"type": "always", "signal_freeze": "close", "fill": "next_open",
         "source": ("★★★ ③档 我们的(执行细节)。★ 原著是「符合条件就买」,没有进场扳机 → "
                    "`type: always` =「在池子里、有空槽就买」。★★ 不能写 rules: [] —— "
                    "那会落到默认 never,一笔都不买(matrices.py:986)。")}
NOSTOP = {"type": "none", "source": "★★ ①档 原著没有价格止损(★ 基本面派靠基本面离场;装止损会改变策略性质)"}
NOTRAIL = {"type": "none", "source": "★ 同上"}
NOREGIME = {"rules": [], "flatten_when_off": False,
            "source": "★ 原著没有环境闸 → 不挂(★ 挂了就不是这条策略)"}
EXIT_NOTE_HOLD = "★ 不再满足条件就卖 —— 用本路覆盖层 fund_rule_fails 在检查日判"


def sizing(n, rank, src_rank, src_n):
    return {"type": "fixed_fraction",
            "rank_by": {"primary": {"formula": rank, "order": "desc"}, "source": src_rank},
            "params": {"max_weight": round(1.0 / n, 4), "max_positions": n},
            "source": src_n}


def 写(name, d):
    d.setdefault("pit", PIT); d.setdefault("costs", COSTS); d.setdefault("benchmark", "SPY")
    d.setdefault("regime", NOREGIME); d.setdefault("entry", ENTRY)
    d.setdefault("initial_stop", NOSTOP); d.setdefault("trailing_stop", NOTRAIL)
    order = ["provenance", "实现缺口", "meta", "pit", "universe", "regime", "entry",
             "initial_stop", "trailing_stop", "exit", "sizing", "costs", "benchmark", "扫参"]
    out = {k: d[k] for k in order if k in d}
    p = os.path.join(OUT, f"{name}.yaml")
    hdr = (f"# {'=' * 74}\n# {name} · ★ 由 写配置_1106.py 生成(改这里请改生成器)\n"
           f"# ★ 三秒版:{d['meta']['三秒版']}\n# {'=' * 74}\n")
    io.open(p, "w", encoding="utf-8").write(
        hdr + yaml.safe_dump(out, allow_unicode=True, sort_keys=False, width=100))
    return p


def 扫(名, 档, **覆盖):
    return {"名": 名, "档": 档, "覆盖": 覆盖}


# ════════════════════════════════════════════════════════════════════ 基-1
G1 = {"years": 7, "min_revenue": 6.0e8, "min_current_ratio": 2.0, "max_ltd_over_nwc": 1.0,
      "min_growth": 0.3333, "max_pe": 15.0, "max_pb": 1.5, "max_product": 22.5}
写("基-1_格雷厄姆防御七条", {
    "provenance": {"composite": False, "method_cards": ["基-1"], "per_rule_cards_filled": True},
    "实现缺口": {
        "这一版缺哪几道闸": [
            {"闸": "★★★ 「10 年连续盈利」「20 年连续分红」「10 年盈利增长」这三条的**回看长度**",
             "为什么装不全": "★ 新财报库最早约 2009 年起(SEC 结构化财报起点);回测窗口 2015 起 →"
                         " ★★ 10 年回看要到 2019 年以后才有第一只票算得出,20 年分红**物理上不存在**。",
             "这一版怎么做": "★ 三条共用一个「回看年数」旋钮,跑 5 / 7 / 10 年三点(10 = 原著盈利口径);"
                          "★★ 分红那条原著 20 年,我们**只能**跟着同一个旋钮(≤10 年)—— 比原著松。",
             "成绩会偏哪边": "★★★ 方向不明,不写偏高偏低(★ 回看短 = 放进更多票,好坏都有可能)"},
            {"闸": "★ 「规模足够大」的门槛",
             "这一版怎么做": "★ 营收 TTM ≥ 6 亿美元 —— ★★ ③档我们的:原著 1972 年写的是年销售 ≥ 1 亿美元,"
                          "按 CPI 粗折到 2015~2020 约 6 亿;★ 池子本身已是大+中口径",
             "成绩会偏哪边": "★ 方向不明"},
            {"闸": "★ 「长期负债不超过营运资本」—— 没报长期债科目的公司",
             "这一版怎么做": "★★★ 没报 LongTermDebt 的票(★ 很多是真没有长期债)算不出 → 判不合格(引擎铁律:NaN 不合格)",
             "成绩会偏哪边": "★★ 方向不明;★ 但会系统性**漏掉无债公司**,报结论时必须带这一句"},
            {"闸": "★ 原著「一年重检一次」",
             "这一版怎么做": "★ 每年第一个交易日检查,不再满足七条就卖(fund_rule_fails · annual)"},
        ],
        "结论怎么写": {"不许这么写": ["格雷厄姆七条无效", "防御型投资法不成立"],
                    "只许这么写": "「**这一版**(回看长度被数据截短、无债公司被误剔)没有/有通过检验」"}},
    "meta": {
        "name": "基-1_格雷厄姆防御七条", "master": "本杰明·格雷厄姆", "card": "基-1",
        "book": "《The Intelligent Investor》第 14 章(★ 页码待核)", "family_label": "基本面",
        "三秒版": "七条硬性筛选全部通过才买,不需要判断,照着数就行;不再满足就换,一年重检一次。",
        "known_gap": "★★★ 见 实现缺口:回看长度被数据截短(10/20 年 → 5/7/10 年)· 规模门槛是我们折算的"
                     " · 没报长期债的公司被判不合格(★ 方向不明,只记事实)。",
        "param_gap": "★★ 原著给了全部数值(流动比率 2、市盈率 15、市净率 1.5、乘积 22.5、增长三分之一)→ 照原著;"
                     "★★★ 唯一跑三点的是「回看年数」5 / 7 / 10(★ 不是原著没给,是数据不够长)。",
        "教学用途": "★ 方法卡第④栏:教学与展示;不进交易契约的风险计算。"},
    "universe": {"rules": [{"type": "graham_defensive", "params": dict(G1), "source": (
        "★ ①档 原著七条(卡原文:「公司规模足够大;财务稳健(流动比率达标、长期负债不超过营运资本);"
        "过去若干年连续盈利,无亏损年;股息记录连续;盈利有长期增长;市盈率低于上限;市净率低于上限,"
        "且两者乘积不超过固定阈值」)。★★ 数值:流动比率 ≥ 2 · 长债 ≤ 净流动资产 · 市盈率(三年平均每股收益)≤ 15"
        " · 市净率 ≤ 1.5 或 市盈率×市净率 ≤ 22.5 · 三年平均每股收益比 N−3 年前高 ≥ 1/3 —— ①档(页码待核)。"
        "★★★ 规模门槛 6 亿 = ③档我们的(CPI 折算);回看年数 = 数据所限,见 实现缺口。")}]},
    "exit": {"rules": [{"type": "fund_rule_fails", "params": {
        "rule": {"type": "graham_defensive", "params": dict(G1)}, "check": "annual"},
        "source": "★ ①档 卡原文:「不再满足条件就换掉,通常一年重检一次」"}],
        "params": {"profit_target_r": None, "time_stop_days": None}, "fill": "next_open",
        "source": EXIT_NOTE_HOLD},
    "sizing": sizing(30, "FUND:pe3", "★★ ③档 我们的:原著没说名额不够时先买谁 → 按三年平均市盈率从低到高"
                     "(★ 不写的话引擎默认按 126 日涨幅挑,那不是原著)",
                     "★ ②档 卡原文「分散持有……有效性建立在数量上」;★ 原著提到 10~30 只(页码待核)→ 取 30,等权"),
    "扫参": [扫("回看5年", "③数据所限", **{"universe.rules.0.params.years": 5,
                                       "exit.rules.0.params.rule.params.years": 5}),
           扫("回看7年", "③数据所限", **{"universe.rules.0.params.years": 7,
                                       "exit.rules.0.params.rule.params.years": 7}),
           扫("回看10年", "①原著盈利口径", **{"universe.rules.0.params.years": 10,
                                        "exit.rules.0.params.rule.params.years": 10})],
})

# ════════════════════════════════════════════════════════════════════ 基-2
写("基-2_施洛斯极度分散", {
    "provenance": {"composite": False, "method_cards": ["基-2"], "per_rule_cards_filled": True},
    "实现缺口": {"这一版缺哪几道闸": [
        {"闸": "★ 「最好有长期经营历史」", "这一版怎么做": "★ 没装(卡原文是「最好」,不是硬条件;★ 也没给年数)",
         "成绩会偏哪边": "★ 方向不明"},
        {"闸": "★★ 买卖价差", "这一版怎么做": "★ 摩擦按全库统一三档;★★ 卡原文提醒「这类标的买卖价差很宽,"
                                          "低换手不等于成本低」→ ★★★ 我们的摩擦**可能偏低**(★ 有依据:卡原文)",
         "成绩会偏哪边": "★★ 偏高(★ 依据:卡原文明说价差宽,而我们按统一三档扣)"}],
        "结论怎么写": {"只许这么写": "「**这一版**(没装经营历史、摩擦按统一三档)……」"}},
    "meta": {"name": "基-2_施洛斯极度分散", "master": "沃尔特·施洛斯", "card": "基-2",
             "book": "访谈与公开记录(★ 卡原文)", "family_label": "基本面",
             "三秒版": "买一堆股价低于每股净资产、负债不高的公司,买 60 只以上;价格回到账面价值就卖。",
             "known_gap": "★ 没装「长期经营历史」;★★ 摩擦可能偏低(★ 依据:卡原文说这类票价差很宽)",
             "param_gap": "★★ 「没有高负债」原著没给数 → 总负债/股东权益 ≤ 0.5 / 1.0 / 1.5 三点;"
                          "★ 「低于每股净资产」= 市净率 < 1(★ 这就是那几个字本身,不是我们拍的数)"},
    "universe": {"rules": [
        {"type": "pb_below", "params": {"max_pb": 1.0},
         "source": "★ ①档 卡原文「股价低于每股净资产」→ 市净率 < 1.0(★ 无自由参数读法)"},
        {"type": "fund_metric_threshold", "params": {"metric": "liab_to_eq", "op": "le", "value": 1.0},
         "source": "★ ①档 卡原文「公司没有高负债」;★★★ 阈值是 ③档我们的(原著没给)→ 跑三点"}]},
    "exit": {"rules": [{"type": "fund_rule_fails", "params": {
        "rule": {"type": "pb_below", "params": {"max_pb": 1.0}}, "check": "daily"},
        "source": "★ ①档 卡原文「价格回到账面价值附近就卖,不等它涨成明星股」→ 市净率回到 ≥ 1 的收盘就卖"}],
        "params": {"profit_target_r": None, "time_stop_days": None}, "fill": "next_open",
        "source": EXIT_NOTE_HOLD},
    "sizing": sizing(60, "FUND:pb", "★ ③档 我们的:名额不够时按市净率从低到高(★ 原著没说先买谁)",
                     "★ ①档 卡原文「同时持有 60–100 只,单只占比很小」→ 取下沿 60,等权"),
    "扫参": [扫("负债0.5", "③", **{"universe.rules.1.params.value": 0.5}),
           扫("负债1.0", "③", **{"universe.rules.1.params.value": 1.0}),
           扫("负债1.5", "③", **{"universe.rules.1.params.value": 1.5})],
})

# ════════════════════════════════════════════════════════════════════ 基-3
写("基-3_F分数原著版", {
    "provenance": {"composite": False, "method_cards": ["基-3"], "per_rule_cards_filled": True},
    "实现缺口": {"这一版缺哪几道闸": [
        {"闸": "★★ 原著是**年度**数据算 F 分数", "这一版怎么做": "★ 引擎用季度 TTM 滚动算(fundamentals.py f_score)",
         "成绩会偏哪边": "★ 方向不明"},
        {"闸": "★ 原著是「高分的全部买、等权」", "这一版怎么做": "★ 30 个槽位,名额不够时按市净率从低到高",
         "成绩会偏哪边": "★ 方向不明"},
        {"闸": "★★ 九项任一算不出 → 整个 F 分数算不出 → 不进池", "这一版怎么做": "★ 照引擎铁律",
         "成绩会偏哪边": "★ 方向不明;★★ 金融股多数不报流动资产/流动负债 → 基本进不来"}],
        "结论怎么写": {"只许这么写": "「**这一版**(季度滚动算分、30 槽)……」"}},
    "meta": {"name": "基-3_F分数原著版", "master": "约瑟夫·皮奥特罗斯基", "card": "基-3",
             "book": "Piotroski (2000) JAR Vol.38 Supplement(★ 年份 2000,非 2001 —— 已核,见 deep_value.yaml)",
             "family_label": "基本面",
             "三秒版": "先挑市净率最低的 20%(便宜股),再在里面只买九项财务检查得 8~9 分的;一年重算一次。",
             "known_gap": "★ 季度滚动算分(原著年度)· 30 槽(原著全买)",
             "param_gap": "★★ 原著主组合 = F 8~9 → 照原著取 ≥ 8;★ 另跑 ≥ 7 / ≥ 9 两个相邻点看是否同向"
                          "(★ 不是原著没给,是敏感度)",
             "★★★原著版的两步": "① 先选账面市值比最高的 20%(= 市净率最低的 20%,原著第 3.1 节)"
                              " ② 再在里面按 F 分数挑。★ 这一份**两步都做了**,所以可以标「原著版」。"},
    "universe": {"rules": [
        {"type": "pb_rank_bottom", "params": {"rank_bottom_pct": 20},
         "source": "★ ①档 原著第 3.1 节:「按上一财年 BM 分五组取最高那组」→ 市净率最低的 20%"
                   "(★★ 池内横截面,不是全市场 —— 全市场分位拿不到)"},
        {"type": "piotroski_f_score_above", "params": {"min_score": 8, "max_score": 9},
         "source": "★ ①档 原著第 3.3 节主组合 F = 8~9(★ 已核,见 deep_value.yaml 注释)"}]},
    "exit": {"rules": [], "params": {"profit_target_r": None, "time_stop_days": 252},
             "fill": "next_open",
             "source": "★ ①档 卡原文「一年重算一次」→ 持满 252 个交易日平仓;★ 空槽按排序补(仍合格的会再买回)"},
    "sizing": sizing(30, "FUND:pb", "★ ③档 我们的:名额不够时按市净率从低到高",
                     "★ ③档 我们的:原著是高分全买等权 → 我们 30 槽等权"),
    "扫参": [扫("F≥7", "③相邻点", **{"universe.rules.1.params.min_score": 7}),
           扫("F≥8", "①原著主组合", **{"universe.rules.1.params.min_score": 8}),
           扫("F≥9", "③相邻点", **{"universe.rules.1.params.min_score": 9})],
})

# ════════════════════════════════════════════════════════════════════ 基-5
写("基-5_德雷曼低市盈率", {
    "provenance": {"composite": False, "method_cards": ["基-5"], "per_rule_cards_filled": True},
    "实现缺口": {"这一版缺哪几道闸": [
        {"闸": "★ 「可承受的负债」", "这一版怎么做": "★ 没装 —— 卡没给数;德雷曼原书是「比行业平均低」,"
                                              "★★ 我们没有历史时点行业分类", "成绩会偏哪边": "★ 方向不明"},
        {"闸": "★ 「正向盈利」", "这一版怎么做": "★ 每股收益 ≤ 0 时市盈率算不出 → 不进池(等价于要求正盈利)"}],
        "结论怎么写": {"只许这么写": "「**这一版**(没装负债闸)……」"}},
    "meta": {"name": "基-5_德雷曼低市盈率", "master": "大卫·德雷曼", "card": "基-5",
             "book": "《Contrarian Investment Strategies》(★ 页码待核)", "family_label": "基本面",
             "三秒版": "买市盈率最低的那一档;估值排名回到中位数附近就卖,换进新的最便宜的;每季度重排。",
             "known_gap": "★ 没装负债闸(要行业平均,没有历史行业分类)",
             "param_gap": "★★ 「回到中位数附近」= 第 50 百分位是卡原文;★ 「附近」没给宽度 → 跑 40 / 50 / 60 三点。"
                          "★ 进池用最便宜 20%(★ 五分组最低一组,②档 德雷曼研究用五分组)"},
    "universe": {"rules": [{"type": "pe_rank_bottom", "params": {"rank_bottom_pct": 20},
                            "source": "★ ②档 卡原文「按市盈率把全市场排序,只买最便宜的那一档」;"
                                      "★ 一档 = 五分组的最低一组(德雷曼研究的分组口径,页码待核)"}]},
    "exit": {"rules": [{"type": "fund_rule_fails", "params": {
        "rule": {"type": "pe_rank_bottom", "params": {"rank_bottom_pct": 50}}, "check": "quarterly"},
        "source": "★ ①档 卡原文「估值排名上升到市场中位数附近时卖出……通常按季度或年度重排」→ 每季第一个交易日,"
                  "市盈率分位 > 50% 就卖(★★ 50 = 中位数本身;「附近」的宽度跑三点)"}],
        "params": {"profit_target_r": None, "time_stop_days": None}, "fill": "next_open",
        "source": EXIT_NOTE_HOLD},
    "sizing": sizing(30, "FUND:pe", "★ ①档 卡原文「只买最便宜的那一档」→ 名额不够时按市盈率从低到高",
                     "★ ③档 我们的:30 槽等权(★ 卡原文提醒「分散度不够就会被拖垮」)"),
    "扫参": [扫("中位40", "③相邻点", **{"exit.rules.0.params.rule.params.rank_bottom_pct": 40}),
           扫("中位50", "①卡原文", **{"exit.rules.0.params.rule.params.rank_bottom_pct": 50}),
           扫("中位60", "③相邻点", **{"exit.rules.0.params.rule.params.rank_bottom_pct": 60})],
})

# ════════════════════════════════════════════════════════════════════ 基-6
写("基-6_收购者倍数", {
    "provenance": {"composite": False, "method_cards": ["基-6"], "per_rule_cards_filled": True},
    "实现缺口": {"这一版缺哪几道闸": [
        {"闸": "★ 排除金融股", "这一版怎么做": "★ 没装 —— 没有历史时点行业分类(同 基-4)",
         "成绩会偏哪边": "★ 方向不明"},
        {"闸": "★ 「持有一年后重排」", "这一版怎么做": "★ 满 252 个交易日平仓、空槽按 EV/EBIT 从低到高补(仍便宜的会再买回)"},
        {"闸": "★ 可挂载的 12 个月动量过滤", "这一版怎么做": "★ 不挂(卡原文:它是可挂载过滤器,不是这条的一部分)"}],
        "结论怎么写": {"只许这么写": "「**这一版**(没排除金融股)……」"}},
    "meta": {"name": "基-6_收购者倍数", "master": "托拜厄斯·卡莱尔", "card": "基-6",
             "book": "《The Acquirer's Multiple》(★ 页码待核)", "family_label": "基本面",
             "三秒版": "只看一个数:企业价值 ÷ 息税前利润,最便宜的那批买进,持有一年后重排。",
             "known_gap": "★ 没排除金融股(没有历史行业分类)",
             "param_gap": "★★ 原著没给持有只数(★ 作者网站的筛选器常列 30 只,页码待核)→ 跑 20 / 30 / 40 三点"},
    "universe": {"rules": [{"type": "ev_ebit_rank_bottom", "params": {"rank_bottom_pct": 100},
                            "source": "★ ①档 卡原文「按企业价值 / 息税前利润(EV/EBIT)给全市场排名」;"
                                      "★★ 这里 100 = 只要算得出就进池,★ 谁先买由排序决定(EV/EBIT 从低到高)"}]},
    "exit": {"rules": [], "params": {"profit_target_r": None, "time_stop_days": 252}, "fill": "next_open",
             "source": "★ ①档 卡原文「持有一年后重排,不再便宜就换掉」→ 满 252 日平仓,空槽按排序补"},
    "sizing": sizing(30, "FUND:ev_ebit", "★ ①档 卡原文「买最便宜的一批」→ EV/EBIT 从低到高",
                     "★ ③档 只数原著没给 → 三点"),
    "扫参": [扫(f"{n}只", "③", **{"sizing.params.max_positions": n,
                                  "sizing.params.max_weight": round(1 / n, 4)}) for n in (20, 30, 40)],
})

# ════════════════════════════════════════════════════════════════════ 基-7
写("基-7_早期巴菲特烟蒂", {
    "provenance": {"composite": False, "method_cards": ["基-7"], "per_rule_cards_filled": True},
    "实现缺口": {"这一版缺哪几道闸": [
        {"闸": "★★★ 三类机会里只做了第一类(极度低估的普通股)",
         "为什么": "★ 卡原文:套利(见第五章)要并购条款、控制型投资「个人做不了」;"
                 "「这家公司的资产到底值多少钱」需要人工判断",
         "这一版怎么做": "★ 「用五毛钱买一块钱」→ 用**净流动资产**(流动资产 − 总负债)当那「一块钱」——"
                      "★★ ③档我们的读法(★ 这其实是格雷厄姆的 Net-Net 口径,和 基-2 是近亲)",
         "成绩会偏哪边": "★ 方向不明"}],
        "结论怎么写": {"只许这么写": "「**这一版**(只做烟蒂那一类,价值用净流动资产代)……」"}},
    "meta": {"name": "基-7_早期巴菲特烟蒂", "master": "沃伦·巴菲特(1957–1969 合伙企业时期)", "card": "基-7",
             "book": "合伙企业时期致合伙人信(★ 卡原文)", "family_label": "基本面",
             "三秒版": "用五毛钱买一块钱的东西 —— 股价低于每股净流动资产的一半就买,涨到净流动资产就卖。",
             "known_gap": "★★★ 只做三类机会里的一类;「价值」用净流动资产代(③档我们的读法)",
             "param_gap": "★★ 卡原文「五毛钱买一块钱」→ 0.5 是原文数;★ 另跑 0.667(格雷厄姆的三分之二)/ 0.8 两个相邻点",
             "★★预警": "★ 大+中口径池子里,股价低于净流动资产一半的票**可能极少** —— 笔数少就如实报「样本不够」"},
    "universe": {"rules": [{"type": "net_net_below", "params": {"factor": 0.5},
                            "source": "★ ①档 卡原文「核心是用五毛钱买一块钱的东西」→ 价格 < 0.5 × 每股净流动资产;"
                                      "★★ 「一块钱」用净流动资产 = ③档我们的读法"}]},
    "exit": {"rules": [{"type": "fund_rule_fails", "params": {
        "rule": {"type": "net_net_below", "params": {"factor": 1.0}}, "check": "daily"},
        "source": "★ ①档 卡原文「涨到内在价值就卖,换下一个」→ 价格回到 ≥ 每股净流动资产就卖(★ 内在价值用同一读法)"}],
        "params": {"profit_target_r": None, "time_stop_days": None}, "fill": "next_open",
        "source": EXIT_NOTE_HOLD},
    "sizing": sizing(30, "FUND:p_ncav", "★ ③档 我们的:名额不够时按「价格 ÷ 净流动资产」从低到高",
                     "★ ③档 我们的:30 槽等权"),
    "扫参": [扫("五毛", "①卡原文", **{"universe.rules.0.params.factor": 0.5}),
           扫("三分之二", "②格雷厄姆口径", **{"universe.rules.0.params.factor": 0.6667}),
           扫("八毛", "③相邻点", **{"universe.rules.0.params.factor": 0.8})],
})

# ════════════════════════════════════════════════════════════════════ 基-8
ZG = {"growth_quarters": 3, "pe_lo_mult": 0.5, "pe_hi_mult": 2.0}
写("基-8_茨威格GARP红绿灯", {
    "provenance": {"composite": False, "method_cards": ["基-8"], "per_rule_cards_filled": True},
    "实现缺口": {"这一版缺哪几道闸": [
        {"闸": "★★★ 红绿灯的「利率方向」", "这一版怎么做": "★ 用 3 个月期美债(DTB3)比半年前低 = 利率在降"
                                               "(★ ③档我们的读法;原著用贴现率/优惠利率等货币指标,页码待核)",
         "成绩会偏哪边": "★ 方向不明"},
        {"闸": "★★ 红绿灯三态 → 引擎只有开/关", "这一版怎么做": "★ 绿=两条都成立 · 黄=一条 · 红=都不成立;"
                                                  "★★ 「非红就允许开仓,转红就清仓」= ③档我们的映射",
         "成绩会偏哪边": "★ 方向不明"},
        {"闸": "★ 「营收增长跟得上利润增长」", "这一版怎么做": "★ 单季营收同比 > 0 且 ≥ 利润增速的一半(③档我们的读法)"},
        {"闸": "★ 原著看的是**每股收益**增速", "这一版怎么做": "★ 单季净利润 ÷ 摊薄股数,同比(★ 不是公司公布的 EPS 科目)"}],
        "结论怎么写": {"只许这么写": "「**这一版**(红绿灯用 3 个月美债 + SPY 200 日线代)……」"}},
    "meta": {"name": "基-8_茨威格GARP红绿灯", "master": "马丁·茨威格", "card": "基-8",
             "book": "《Winning on Wall Street》(★ 页码待核)", "family_label": "基本面",
             "三秒版": "要有成长但别太贵:盈利连续几季正增长且在加快、市盈率在市场均值一半到两倍之间;大盘红灯就不买、转红就卖。",
             "known_gap": "★★★ 红绿灯用 3 个月美债 + SPY 200 日线代(③档读法)· 三态映射成开关(③)",
             "param_gap": "★★ 「连续多个季度」原著没给几季 → 2 / 3 / 4 季三点;"
                          "★ 「市盈率在市场均值的一半到两倍」是卡原文数 → 照用(★ 用池内中位数当「均值」,③)"},
    "universe": {"rules": [{"type": "zweig_garp", "params": dict(ZG),
                            "source": "★ ①档 卡原文「盈利连续多个季度正增长且增速在加快,市盈率在市场均值的一半到两倍之间,"
                                      "营收增长跟得上利润增长」;★★ 季数跑三点;「营收跟得上」的可算读法 ③"}]},
    "regime": {"rules": [{"type": "zweig_light", "params": {
        "symbol": "SPY", "ma": 200, "rate_lookback": 126, "allow": "not_red"},
        "source": "★ ①档 卡原文「输入是利率方向和大盘长均线,输出红/黄/绿三态」;"
                  "★★★ 利率用 DTB3、长均线取 200 日、半年回看、非红即开 —— 全部 ③档我们的读法"}],
        "flatten_when_off": True,
        "source": "★ ①档 卡原文「大盘不好的时候,再好的股票也不买」「大盘红绿灯转红」就退出 → 转红清仓"},
    "exit": {"rules": [{"type": "fund_rule_fails", "params": {
        "rule": {"type": "fund_metric_threshold",
                 "params": {"metric": "zweig_growth_ok_3", "op": "ge", "value": 1.0}},
        "check": "daily"},
        "source": "★ ①档 卡原文「盈利增速拐头向下」就卖 → 增长条件不再成立的那天收盘判离场"
                  "(★ 只看增长那半条,不看市盈率带 —— 卡原文离场只说增速)"}],
        "params": {"profit_target_r": None, "time_stop_days": None}, "fill": "next_open",
        "source": EXIT_NOTE_HOLD},
    "sizing": sizing(30, "FUND:eps_q_yoy", "★ ③档 我们的:名额不够时按单季每股收益同比增速从高到低",
                     "★ ③档 我们的:30 槽等权"),
    "扫参": [扫(f"{n}季", "③", **{"universe.rules.0.params.growth_quarters": n,
                                  "exit.rules.0.params.rule.params.metric": f"zweig_growth_ok_{n}"})
           for n in (2, 3, 4)],
})

# ════════════════════════════════════════════════════════════════════ 基-12
写("基-12_回购筛选", {
    "provenance": {"composite": False, "method_cards": ["基-12"], "per_rule_cards_filled": True},
    "实现缺口": {"这一版缺哪几道闸": [
        {"闸": "★★ 「持续多年而不是一次性」", "这一版怎么做": "★ 只看近 4 季股数同比(net_dilution_pct)"
                                                 "—— ★ 没装「多年持续」(③档,原著没给年数)", "成绩会偏哪边": "★ 方向不明"},
        {"闸": "★ 股数用加权平均摊薄股数", "这一版怎么做": "★ 引擎口径(★ 回购凶的公司期间加权偏高 → 回购幅度被低估)",
         "成绩会偏哪边": "★ 方向不明"}],
        "结论怎么写": {"只许这么写": "「**这一版**(只看一年、XING 读法)……」"}},
    "meta": {"name": "基-12_回购筛选", "master": "XING(源自威廉·索恩代克的资本配置框架)", "card": "基-12",
             "book": "《The Outsiders》(★ 卡原文:这是一个筛选器,只覆盖框架的一小部分)", "family_label": "基本面",
             "三秒版": "找自由现金流为正、而且股数在实打实减少(回购注销)的公司;回购停了就卖。",
             "known_gap": "★ 没装「多年持续」;股数口径是加权平均",
             "param_gap": "★★ 「大量」原著没给 → 股数同比减少 > 0% / 2% / 4% 三点",
             "★★卡原文自己的提醒": "「回购金额 ≤ 当期自由现金流」这个条件是 XING 补的 —— ★ 本版**没装**它"},
    "universe": {"rules": [
        {"type": "fund_metric_threshold", "params": {"metric": "net_dilution_pct", "op": "lt", "value": 0.0},
         "source": "★ ④档 XING 筛选器(卡标题自注「XING」)· 卡原文「持续在二级市场回购注销流通股」→ 股数同比下降;"
                   "★★ 「大量」阈值 ③ → 三点"},
        {"type": "fund_metric_threshold", "params": {"metric": "fcf_ttm", "op": "gt", "value": 0.0},
         "source": "★ ④档 卡原文「自由现金流充沛」→ FCF TTM > 0(★ 符号条件,无阈值)"}]},
    "exit": {"rules": [{"type": "fund_rule_fails", "params": {
        "rule": {"type": "fund_metric_threshold",
                 "params": {"metric": "net_dilution_pct", "op": "lt", "value": 0.0}},
        "check": "quarterly"},
        "source": "★ ④档 卡原文「回购停止」就退出 → 每季检查,股数同比不再下降就卖"}],
        "params": {"profit_target_r": None, "time_stop_days": None}, "fill": "next_open",
        "source": EXIT_NOTE_HOLD},
    "sizing": sizing(30, "FUND:dilution", "★ ③档 我们的:名额不够时按股数减少幅度从大到小",
                     "★ ③档 我们的:30 槽等权"),
    "扫参": [扫(f"减{k}%", "③", **{"universe.rules.0.params.value": -float(k)}) for k in (0, 2, 4)],
})

# ════════════════════════════════════════════════════════════════════ 基-16
写("基-16_特里史密斯", {
    "provenance": {"composite": False, "method_cards": ["基-16"], "per_rule_cards_filled": True},
    "实现缺口": {"这一版缺哪几道闸": [
        {"闸": "★ 「增长靠内生而非并购」「产品不易被技术替代」", "这一版怎么做": "★ 没装(卡原文:后者需要人工判断)",
         "成绩会偏哪边": "★ 方向不明"},
        {"闸": "★ 「估值高到说不过去」才卖", "这一版怎么做": "★ 没装(没有给数);只装「质量恶化」那一条"}],
        "结论怎么写": {"只许这么写": "「**这一版**(只装三道可算筛选)……」"}},
    "meta": {"name": "基-16_特里史密斯", "master": "特里·史密斯", "card": "基-16",
             "book": "Fundsmith 公开投资者信件(★ 卡原文)", "family_label": "基本面",
             "三秒版": "只买长期资本回报高、现金转化好、不靠高负债的好公司,按自由现金流收益率挑不贵的;买完尽量不动。",
             "known_gap": "★ 没装内生增长、技术替代、估值离场",
             "param_gap": "★★ 「长期高资本回报率」没给数 → ROCE 池内前 10% / 20% / 30% 三点;"
                          "★ 现金转化 ≥ 0.8、总负债/权益 ≤ 1.0 也是 ③档我们的(只跑中心点)"},
    "universe": {"rules": [
        {"type": "roce_rank_top_x", "params": {"rank_top_pct": 20},
         "source": "★ ①档 卡原文「长期高资本回报率(不靠杠杆做出来的)」→ ROCE = EBIT ÷(总资产 − 流动负债);"
                   "★★ 「高」= 池内前 N%,③ 跑三点"},
        {"type": "fund_metric_threshold", "params": {"metric": "fcf_conv", "op": "ge", "value": 0.8},
         "source": "★ ①档 卡原文「现金转化率高」;★★ 0.8 = ③档我们的"},
        {"type": "fund_metric_threshold", "params": {"metric": "liab_to_eq", "op": "le", "value": 1.0},
         "source": "★ ①档 卡原文「不依赖高负债」;★★ 1.0 = ③档我们的"}]},
    "exit": {"rules": [{"type": "fund_rule_fails", "params": {
        "rule": {"type": "roce_rank_top_x", "params": {"rank_top_pct": 50}}, "check": "annual"},
        "source": "★ ①档 卡原文「只有两个理由卖:公司质量本身恶化……」→ 每年检查,ROCE 跌出池内前一半就卖(★ 50 = ③)"}],
        "params": {"profit_target_r": None, "time_stop_days": None}, "fill": "next_open",
        "source": EXIT_NOTE_HOLD},
    "sizing": sizing(25, "FUND:fcf_yield", "★ ①档 卡原文「用自由现金流收益率判断价格是否合理」→ 从高到低",
                     "★ ①档 卡原文「组合通常只有二三十只」→ 25 只等权"),
    "扫参": [扫(f"ROCE前{k}%", "③", **{"universe.rules.0.params.rank_top_pct": k}) for k in (10, 20, 30)],
})

# ════════════════════════════════════════════════════════════════════ 基-20
写("基-20_价值动量双因子", {
    "provenance": {"composite": False, "method_cards": ["基-20"], "per_rule_cards_filled": True},
    "实现缺口": {"这一版缺哪几道闸": [
        {"闸": "★ 原研究是多资产、多空", "这一版怎么做": "★ 只做美股、只做多(★ 标「行业改进版」,不标原著)",
         "成绩会偏哪边": "★ 方向不明"}],
        "结论怎么写": {"只许这么写": "「**这一版**(只做多、权重和再平衡是 XING 的)……」"}},
    "meta": {"name": "基-20_价值动量双因子", "master": "克利夫·阿斯内斯 / AQR", "card": "基-20",
             "book": "Asness, Moskowitz & Pedersen (2013) JF《Value and Momentum Everywhere》(★ 页码待核)",
             "family_label": "基本面",
             "三秒版": "给每只票打两个分 —— 便宜分(市净率)和动量分(过去 12 个月剔除最近 1 个月),加权合成,买总分最高的一批,每季重排。",
             "known_gap": "★ 只做多、只美股",
             "param_gap": "★★ 卡原文「具体的权重与再平衡频率是 XING 的实现」→ 价值权重 0.3 / 0.5 / 0.7 三点;"
                          "★ 每季重排(卡原文「通常季度」);★ 掉出前 30% 就换(③)"},
    "universe": {"rules": [{"type": "value_momentum_top", "params": {"value_weight": 0.5, "top_pct": 100},
                            "source": "★ ①档 卡原文「给全市场同时打两个分……按权重合成总分」;"
                                      "★★ 价值腿 = 账面市值比(1/市净率,原研究口径);动量腿 = 12-1 月;"
                                      "★ 两腿都算得出才进池,谁先买由总分排序决定"}]},
    "exit": {"rules": [{"type": "fund_rule_fails", "params": {
        "rule": {"type": "value_momentum_top", "params": {"value_weight": 0.5, "top_pct": 30}},
        "check": "quarterly"},
        "source": "★ ①档 卡原文「定期重排(通常季度),总分掉出前列就换掉」;★★ 「前列」= 前 30% = ③"}],
        "params": {"profit_target_r": None, "time_stop_days": None}, "fill": "next_open",
        "source": EXIT_NOTE_HOLD},
    "sizing": sizing(50, "FUND:value_momentum_w0.5",
                     "★ ①档 卡原文「买总分最高的一批」→ 总分从高到低;★★ 加权不是交集(卡原文明说)",
                     "★ ③档 我们的:50 只等权(★ 卡原文「靠分散和再平衡,持仓数量少了就不成立」)"),
    "扫参": [扫(f"价值权重{w}", "③", **{"universe.rules.0.params.value_weight": w,
                                    "exit.rules.0.params.rule.params.value_weight": w,
                                    "sizing.rank_by.primary.formula": f"FUND:value_momentum_w{w}"})
           for w in (0.3, 0.5, 0.7)],
})

if __name__ == "__main__":
    print("★ 写完")
