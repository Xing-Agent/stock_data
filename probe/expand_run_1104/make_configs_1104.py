#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 扩库全跑(1104)的 16 条臂配置生成器 —— ★ 在任何一次回测之前跑完并落盘

三秒版(大白话):
  这个脚本只负责**把 16 份配置写出来**。★ 写完才允许开跑;
  ★★ 开跑之后这些文件一个字不改 —— 这就是「预先登记」。

══════════════════════════════════════════════════════════════════════════
★★ 两版并排的规矩(逐字来自《35》预先登记第一节)
══════════════════════════════════════════════════════════════════════════
  **原著版** = 只用原著给的数,一个不添;★ 原话没说的那一格**空着不跑**,
               ★★★ 不许用「行业惯例」顶上冒充原著。
  **我们的版本** = 在原著版基础上**只改一处**,并标清「这是我们改的」。
  ★★★ 绝不把我们改的那一处标成原著 —— 红线①。

══════════════════════════════════════════════════════════════════════════
★★★ 原著没给的数 → 跑相邻三个点(《35》口径⑤)
══════════════════════════════════════════════════════════════════════════
  · **槽位数**(买几只):8 条**全部**原著没给 → 网格 15 / 30 / 45,主格 30
  · **股东回报的排名档数**:原著只说「占市值比例排名」,没说取前几 %
       → 网格 10 / 20 / 30,主格 20
  · **第 8 条的相对强度档位**:融合条目,没有原著 → 网格 70 / 80 / 90,主格 80
  ★ 考核写法一律是「三点是否同向」,★★★ **不报最好的那一点**。
"""
from __future__ import annotations

import os

import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "configs_1104")

# ---------------------------------------------------------------- 公共块

PIT = {
    "effective": "filing_date_plus_1_trading_day",
    "forbid": "严禁用报告期截止日",
    "missing_policy": "未公布期间沿用上一期(Forward-fill);第一次公布之前 = NaN = 不合格",
    "source": "原著",
}

COSTS = {
    "friction_tiers": {"high_liquidity_bps": 5.0, "mid_liquidity_bps": 15.0,
                       "low_liquidity_bps": 30.0},
    "source": "行业惯例",
    "note": "★ 按《23 摩擦口径统一-1104》拍板的三档(5/15/30 bp,进出各扣一次),"
            "★★ 不用一刀切 —— 一刀切会系统性补贴随机对照组。",
}

RANKING = {
    "primary": {"formula": "ADV20", "order": "desc"},
    "tiebreak": "symbol",
    "source": "★ 占位排序(**不是策略的一部分**),沿用 "
              "engine/run_fundamental.PLACEHOLDER_RANKING。"
              "★★ 槽位不够时买哪几只由它决定,结论对它敏感。",
}


def common(name: str, master: str, family: str, note_r: str) -> dict:
    return {
        "pit": dict(PIT),
        "regime": {
            "rules": [],
            "flatten_when_off": False,
            "environment_declaration": "Unspecified",
            "source": "★★★ 原著没给市场级使用条件 → 显式声明 Unspecified,"
                      "★ **没有悄悄当成「常开」**(《35》口径⑤ / 红线⑤)。",
        },
        "entry": {
            "type": "always",
            "fill": "next_open_market",
            "source": "原著(机械筛选,过了筛选就买,无进场扳机)",
        },
        "initial_stop": {
            "type": "none",
            "source": "★★★ 原著这一派不设价格止损 —— 靠分散和筛选条件承担单票风险。"
                      "★ 所以这一格是「明确为无 + 有出处」,不是「空着」。"
                      "★★ 代价:1R = 进场价 → **R 退化成收益率**,"
                      "★★★ 不能和有止损的链放在同一列比。",
        },
        "trailing_stop": {"type": "none", "source": "★ 同 ④,原著无移动止损。"},
        "add_on": {"type": "none",
                   "source": "★ 原著未提加仓;全库一条都没有加仓(1030 已登记)。"},
        "sizing": {"type": "fixed_fraction",
                   "params": {"max_positions": 30, "max_weight": round(1 / 30, 6)},
                   "source": "★ XING(原著只说分散持有,没给只数)"},
        "slots": 30,
        "slots_prior_grid": [15, 30, 45],
        "source_slots": "★★★ 《35》口径⑤ 禁止单点估计。槽位数原著没给 → "
                        "声明 3 个邻近点 15 / 30 / 45,★ 考核标准是「3 点同向」,"
                        "★★★ 不是挑最好的那一点。",
        "ranking": dict(RANKING),
        "costs": dict(COSTS),
        "benchmark": {"family": family, "component_match": "large",
                      "risk_free_annual": None,
                      "note": "★ 仓库没有短端利率序列,现金腿按 0% 记并在结果里标明。"},
        "_r_note": note_r,
    }


def chain(cid: str, name: str, master: str, family: str,
          rules: list[dict], attribution: str, three_sec: str,
          extra_meta: dict | None = None) -> dict:
    c = common(name, master, family, "")
    c["meta"] = {
        "name": name,
        "master": master,
        "chain_id": cid,
        "★三秒版": three_sec,
        "★★★归属": attribution,
        "pre_registered": "probe/expand_run_1104/configs_1104/ —— "
                          "★ 本文件在任何一次回测之前落盘",
    }
    if extra_meta:
        c["meta"].update(extra_meta)
    c["universe"] = {"rules": rules}
    c["exit"] = {
        "type": "rules",
        "rules": [{"type": "screen_dropout", "params": {"screen": cid},
                   "source": "原著(无自由参数读法)"}],
        "note": "★ 「筛选条件不再成立」那天收盘走。"
                "★★★ 原著的再平衡频率方法卡没给 —— 本轮**没有拍这个数**,"
                "★ 用的是唯一不含自由参数的读法。",
    }
    return c


ORIG = "★★★ **原著版** —— ★ 只用原著给的数,一个不添。"
OURS = "★★★ **我们的版本** —— ★ 在原著版基础上只改一处,★★ 下面写明改的是哪一处。"

CHAINS: dict[str, dict] = {}

# ══════════════════════════════════════════════════════════════════════════
# ① Sloan 应计
#   ★★★ 原著版(资产负债表法)**不跑** —— 见 README「算不出来」那一列:
#     Sloan (1996) 的资产负债表法要「Δ应交所得税」,
#     ★ 老库里 IncomeTaxesPayable / AccruedIncomeTaxesCurrent 覆盖率都是 **0.0%**。
#     ★★ 按《35》口径⑦:记「算不出来 + 缺的是哪一样」,**不许用近似值顶上**。
# ══════════════════════════════════════════════════════════════════════════
CHAINS["扩1-ours"] = chain(
    "扩1-ours", "扩1_Sloan应计_现金流量表法_我们的", "Richard Sloan", "meanrev",
    [{"type": "accrual_cf_decile_bottom", "params": {"decile_pct": 10},
      "source": "我们的(行业改进:Hribar & Collins 2002 的现金流量表法)"}],
    OURS + "★ 改的那一处 = **用现金流量表法代替资产负债表法**"
           "(★★ 这是后人的改法,标**行业改进**,不是 Sloan 原著)。"
           "★★★ 分母「平均总资产」是**原著口径**,这一处没改。",
    "买「账上利润比收到的现金多得最少」的那一成票 —— 利润水分最小的那一档。")

# ══════════════════════════════════════════════════════════════════════════
# ② 资产扩张
# ══════════════════════════════════════════════════════════════════════════
CHAINS["扩2-orig"] = chain(
    "扩2-orig", "扩2_资产扩张_原著", "Cooper / Gulen / Schill (2008)", "meanrev",
    [{"type": "asset_growth_decile_bottom", "params": {"decile_pct": 10},
      "source": "原著"}],
    ORIG + "★ 总资产同比增速,十分位,买最低那一档 —— 只用总资产一个科目。",
    "买「去年一年摊子铺得最慢」的那一成票。")

CHAINS["扩2-ours"] = chain(
    "扩2-ours", "扩2_资产扩张_经营资产口径_我们的", "Cooper / Gulen / Schill (2008)",
    "meanrev",
    [{"type": "operating_asset_growth_decile_bottom", "params": {"decile_pct": 10},
      "source": "我们的(口径降级版,见 meta)"}],
    OURS + "★ 改的那一处 = 把分子从「总资产」换成「经营资产」。"
           "★★★ **必须照实说**:《35》登记的是「净经营资产」,"
           "★ 但真净经营资产要剔经营负债,而有息负债科目在老库里残缺"
           "(56.0% / 59.2% / 35.2% / 19.2%,四个互补、谁盖谁说不清)"
           "→ ★★ 真口径记为**算不出来**,这里跑的是「总资产 − 现金」。"
           "★★★ 两者不混成一个数。",
    "买「去年一年真金白银的摊子铺得最慢」的那一成票(现金不算摊子)。")

# ══════════════════════════════════════════════════════════════════════════
# ③ LSV 逆向价值 —— ★★★ 原著是**单指标各跑一次,不合成**
# ══════════════════════════════════════════════════════════════════════════
for key, zh, desc in (("bm", "账面市值比", "净资产 ÷ 市值"),
                      ("cp", "现金流价格比", "经营现金流 ÷ 市值"),
                      ("ep", "盈利价格比", "净利润 ÷ 市值")):
    CHAINS[f"扩3-orig-{key}"] = chain(
        f"扩3-orig-{key}", f"扩3_LSV逆向价值_{zh}_原著",
        "Lakonishok / Shleifer / Vishny (1994)", "meanrev",
        [{"type": "lsv_single_decile_cheapest",
          "params": {"indicator": key, "decile_pct": 10}, "source": "原著"}],
        ORIG + f"★ **单指标**十分位({desc}),买最便宜那一档。"
               "★★★ 原著**明确不合成分数** → 三个指标是**三条独立的臂**,"
               "★ 这一条只跑其中一个。",
        f"只看一个数({desc}),买最便宜的那一成票。")

CHAINS["扩3-ours"] = chain(
    "扩3-ours", "扩3_LSV逆向价值_三指标名次中位数_我们的",
    "Lakonishok / Shleifer / Vishny (1994)", "meanrev",
    [{"type": "lsv_rank_median_decile_cheapest", "params": {"decile_pct": 10},
      "source": "我们的(原著明确没有合成分数)"}],
    OURS + "★ 改的那一处 = **把三个指标的名次取中位数合成一个分数**。"
           "★★★ 原著明确没有合成分数,所以这一处**百分之百是我们加的**。",
    "三个便宜指标各排一次名,取中间那个名次,买最便宜的那一成票。")

# ══════════════════════════════════════════════════════════════════════════
# ④ Net-Net
# ══════════════════════════════════════════════════════════════════════════
CHAINS["扩4-orig"] = chain(
    "扩4-orig", "扩4_NetNet_三分之二门槛_原著", "Benjamin Graham", "meanrev",
    [{"type": "netnav_discount_below", "params": {"max_ratio": 2.0 / 3.0},
      "source": "原著(《聪明的投资者》1949 版)"}],
    ORIG + "★ 净流动资产 = 流动资产 − **全部负债**;"
           "★★ 市值 ≤ 其 **2/3** 才买。"
           "★★★ 出处是《聪明的投资者》**1949 版**,不是 1934。",
    "买「整个公司的市价还不到它流动资产减掉所有欠款后的三分之二」的票。",
    {"★市值口径": "★★ 市值 = 收盘价 × 摊薄股数 = **规模代理,不是 PIT 市值**,"
                  "★ 和 ops_fund_1030 的 EV 股权腿同一个口径,照实标。"})

CHAINS["扩4-ours"] = chain(
    "扩4-ours", "扩4_NetNet_门槛放宽到1.0_我们的", "Benjamin Graham", "meanrev",
    [{"type": "netnav_discount_below", "params": {"max_ratio": 1.0},
      "source": "我们的(门槛 2/3 → 1.0)"}],
    OURS + "★ 改的那一处 = **门槛从 2/3 放宽到 1.0**"
           "(即「低于净流动资产就买」)。★★ 只改这一个数,其余一字不动。",
    "买「市价低于流动资产减掉所有欠款」的票 —— 比原著宽松一档。")

# ══════════════════════════════════════════════════════════════════════════
# ⑤ 存货异常
# ══════════════════════════════════════════════════════════════════════════
CHAINS["扩5-orig"] = chain(
    "扩5-orig", "扩5_存货异常_原著", "Thomas & Zhang (2002)", "meanrev",
    [{"type": "inventory_abnormal_decile_bottom", "params": {"decile_pct": 10},
      "source": "原著"}],
    ORIG + "★ 存货增速 − 收入增速,十分位,买最低那一档。",
    "买「货越积越少、生意却没变差」的那一成票。",
    {"★预言三": "★★★ 服务业没有存货 → 它们是**算不出来**,"
                "★ 不是「分数差」,两者必须分成两列记。"})

CHAINS["扩5-ours"] = chain(
    "扩5-ours", "扩5_存货异常_加制造零售行业闸_我们的", "Thomas & Zhang (2002)",
    "meanrev",
    [{"type": "inventory_abnormal_decile_bottom", "params": {"decile_pct": 10},
      "source": "原著"},
     {"type": "sic_industry_in",
      "params": {"sic_ranges": [[2000, 3999], [5200, 5999]]},
      "source": "我们的(行业闸)"}],
    OURS + "★ 改的那一处 = **加一道「只在制造/零售业用」的行业闸**。"
           "★★ 用 SIC 码,★★★ **按时点取**(每个版本 observed_from + 1 个交易日生效,"
           "第一版之前是 NaN)—— ★ 绝不用最新版本回填历史。"
           "★★ 区间:SIC 2000–3999 = 制造业,5200–5999 = 零售业。",
    "和原著一样,但只在「真的有货要管」的制造和零售公司里挑。")

# ══════════════════════════════════════════════════════════════════════════
# ⑥ 毛利质量
# ══════════════════════════════════════════════════════════════════════════
CHAINS["扩6-orig"] = chain(
    "扩6-orig", "扩6_毛利质量_原著", "Robert Novy-Marx (2013)", "trend",
    [{"type": "gross_profitability_quintile_top",
      "params": {"quintile_pct": 20, "denominator": "total_assets"},
      "source": "原著"}],
    ORIG + "★ 毛利 ÷ 总资产(毛利 = 收入 − 营业成本),**五分位**,买最高那一档。"
           "★★★ 原著是**五分位,不是十分位**。",
    "买「每一块钱的家当能赚出最多毛利」的那两成票。")

CHAINS["扩6-ours"] = chain(
    "扩6-ours", "扩6_毛利质量_换平均总资产_我们的", "Robert Novy-Marx (2013)", "trend",
    [{"type": "gross_profitability_quintile_top",
      "params": {"quintile_pct": 20, "denominator": "avg_total_assets"},
      "source": "我们的(分母换平均总资产)"}],
    OURS + "★ 改的那一处 = **分母从「总资产」换成「平均总资产」**。只改这一处。",
    "和原著一样,只是家当按一年的平均数算,不按期末那一天。")

# ══════════════════════════════════════════════════════════════════════════
# ⑦ 股东回报 —— ★ 排名档数原著没给 → 3 点网格
# ══════════════════════════════════════════════════════════════════════════
_SY_GRID = {"rank_prior_grid": [10, 20, 30],
            "source_rank": "★★★ 原著只说「占市值比例排名」,**没说取前几 %** → "
                           "按《35》口径⑤ 跑相邻三点 10 / 20 / 30,主格 20,"
                           "★ 报「三点是否同向」,★★★ 不报最好的那一点。"}

c = chain("扩7-orig", "扩7_股东回报_原著", "Shareholder Yield(Priest / O'Shaughnessy 系)",
          "meanrev",
          [{"type": "shareholder_yield_rank_top", "params": {"rank_top_pct": 20},
            "source": "原著(回购 + 分红 − 增发,占市值比例排名)"}],
          ORIG + "★ 回购 + 分红 − 增发,占市值比例排名,买最高那一档。"
                 "★★★ 三项**必须全有**才算得出 —— ★ 缺一项记「算不出来」,"
                 "**不按 0 补**(「没报这个科目」和「真的没有」在这份库里分不开)。",
          "买「真金白银还给股东最多」的那两成票。",
          {"★分红口径": "★★ PaymentsOfDividends 优先、缺的用 "
                         "PaymentsOfDividendsCommonStock 补,★★★ **不相加**"
                         "(后者是前者的子集,相加等于算两遍)。"
                         "★ 这正是《35》预言一里登记为「不确定」的那一项。"})
c.update(_SY_GRID)
CHAINS["扩7-orig"] = c

c = chain("扩7-ours", "扩7_股东回报_减资产扩张惩罚_我们的",
          "Shareholder Yield(Priest / O'Shaughnessy 系)", "meanrev",
          [{"type": "shareholder_yield_minus_asset_growth_rank_top",
            "params": {"rank_top_pct": 20}, "source": "我们的(减资产扩张惩罚)"}],
          OURS + "★ 改的那一处 = **再减一个「资产扩张惩罚」**"
                 "(股东回报率 − 总资产同比增速)。"
                 "★★★ 这是**我们合并出来的新形状**,原著没有这一项。",
          "买「还钱给股东最多、同时摊子铺得最慢」的那两成票。")
c.update(_SY_GRID)
CHAINS["扩7-ours"] = c

# ══════════════════════════════════════════════════════════════════════════
# ⑧ 趋势模板 AND 盈利加速 —— ★★★ 只有「我们组合的」一版
# ══════════════════════════════════════════════════════════════════════════
c = chain("扩8-ours", "扩8_趋势模板AND盈利加速_我们组合的",
          "Mark Minervini(价格那一半)+ 盈利加速(基本面那一半)", "trend",
          [{"type": "ma_stack_bullish",
            "params": {"mas": [50, 150, 200], "require_price_above_all": True},
            "source": "原著(Minervini 趋势模板的均线叠放)"},
           {"type": "return_rank_percentile",
            "params": {"lookback": 126, "min_percentile": 80},
            "source": "我们的(档位原著没给,3 点网格)"},
           {"type": "earnings_acceleration", "params": {"require": "rev_and_eps"},
            "source": "我们的(符号条件,无阈值)"}],
    "★★★ **只做「我们组合的」一版** —— ★ 这是融合条目,**没有单一原著**,"
    "★★ 归属如实标:价格那一半来自 Minervini 趋势模板,"
    "盈利加速那一半是我们按「增速在往上走」的符号读法做的,"
    "★★★ 原书那个「营收和 EPS 增长 20% 以上」的数**本轮没有拍**"
    "(出处还没回原文核,见《18》第 3 条)。",
    "买「价格已经在领先、而且营收和每股收益的增速还在往上走」的票。",
    {"★★★原著版": "⬜ **不跑** —— 没有单一原著(《35》跑的清单第 8 行)。"})
c["rank_prior_grid"] = [70, 80, 90]
c["source_rank"] = ("★★★ 「相对强度排前面」的具体档位没有原著 → "
                    "按《35》口径⑤ 跑相邻三点 70 / 80 / 90,主格 80,"
                    "★ 报「三点是否同向」,★★★ 不报最好的那一点。")
CHAINS["扩8-ours"] = c


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    for cid, cfg in CHAINS.items():
        p = os.path.join(OUT, f"{cid}.yaml")
        with open(p, "w", encoding="utf-8") as fh:
            fh.write("# ★★★ 预先登记配置 —— 本文件在任何一次回测之前落盘。\n"
                     "# ★ 登记之后无论结果多惨,公式一个字不改(《35》红线)。\n")
            yaml.safe_dump(cfg, fh, allow_unicode=True, sort_keys=False,
                           default_flow_style=False, width=100)
    print(f"★ 写了 {len(CHAINS)} 份配置到 {OUT}")
    for cid in CHAINS:
        print("   ", cid)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
