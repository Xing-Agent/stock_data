"""
退市结算闸 —— ★ 2026-10-29 接入技术方核实的 delisting_settlement_price + 并购细分。

════════════════════════════════════════════════════════════════════════
★ 大白话(三秒版)
════════════════════════════════════════════════════════════════════════
一只票退市了,我们手上的仓位按多少钱平掉?以前是「破产类一律记 0,
其余按最后一天收盘价」。★ 现在改成以技术方逐只查到的证据为准。

★ 技术方写了一句最要紧的话,这个文件就是为了照办它:
    「null 表示证据无法确定,★★ 不等于 0」

所以结算价分成★ 三类,★ 三类都单独统计,让影响看得见:
  VERIFIED_CASH  9 只  有固定全现金并购价 → ★ 按那个价平仓
  VERIFIED_ZERO  7 只  已确认的重整计划下普通股无分配 → ★ 记 0(真 −100%)
  NULL          14 只  ★ 证据拿不到 → 用最后收盘价,★ 并单独记账
                       ★ 绝对不许当成 0

★ 和我们原来做法的差别(这是本次最实质的一处改动):
  原来:retirement_category ∈ {bankruptcy + 4 个「实质破产」类} → 一律 −100%,
        一共 12 只。
  现在:只有技术方确认归零的 7 只记 0。
  ★ 差 5 只:AMRS / CLVS / WPG / GTT / FRC —— 我们原来按 −100% 记,
    但技术方查完说「每股最终回收金额尚无可靠证据」(null)。
  ★ 方向上这会让成绩★ 变好看一点(原来凭空多记了 5 笔归零)。
  ★★ 这一改和 1028 Lin 拍板的「实质破产也按 −100%(Shumway 1997)」
     是冲突的 —— Lin 1029 的指示「null 不许当成 0」更新,所以按 1029 执行,
     ★ 但这是个需要明确拍板确认的反转,报告里单列。
     想切回去只要把 TREAT_NULL_AS_ZERO 改成 True。

════════════════════════════════════════════════════════════════════════
★ 并购细分:全现金 vs 换股
════════════════════════════════════════════════════════════════════════
  ACQUISITION_CASH  10 只 → 按结算价平仓,交易结束。★ 做得到。
  ACQUISITION_STOCK  7 只 → 仓位应该变成收购方的股票,交易★ 没结束。
     ★★ 我们做不到:仓库里没有收购方(AMD / AZN / COF / CVX / CP / COP / OCSL)
        的日线,一根都没有。★ 拿不到就是拿不到。
     ★ 所以按「退市日最后收盘价结算 + 单独标记」处理,并在报告里报清楚
        这偏向哪一边、涉及多少笔。
     ★ 方向:换股并购的收购方股票在成交后还会继续涨跌。我们在退市日就
        落袋,相当于★ 砍掉了后面那段(不管是赚还是亏)。
        由于这 7 只都是被大公司收购的大中盘股、成交后多数是上涨市,
        ★ 大概率是★ 低估了真实收益,但★ 也去掉了后续的回撤 ——
        ★ 严格说方向不定,只能报「少了多少笔的后续段」,不许说成单边偏差。
"""

from __future__ import annotations

import functools
import json
import os
from dataclasses import dataclass
from typing import Literal

REVIEW_JSON = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "pilot_300", "reviews", "corporate_actions_2026-10",
    "delisted_equity_outcome_review_20261028.json")

Basis = Literal["verified_cash", "verified_zero", "null_evidence"]

# ★ 开关:True = 切回「实质破产一律 −100%」的老做法(1028 口径)。
#   ★ 默认 False —— 按 Lin 1029 的指示「null 不等于 0」。
TREAT_NULL_AS_ZERO = False

# 换股并购的收购方 —— ★ 列在这里只为说明「我们缺的是什么」,仓库里一根日线都没有
STOCK_DEAL_ACQUIRERS = {
    "XLNX": "AMD (1.7234 AMD / XLNX)",
    "ALXN": "AZN",
    "DFS": "COF",
    "HES": "CVX",
    "KSU": "CP",
    "MRO": "COP",
    "OCSI": "OCSL",
}


@dataclass(frozen=True)
class Settlement:
    symbol: str
    retirement_category: str
    basis: Basis
    price: float | None          # None = 证据拿不到,用最后收盘价
    consideration_type: str | None
    status: str
    note: str

    @property
    def is_stock_deal(self) -> bool:
        return self.retirement_category == "ACQUISITION_STOCK"

    @property
    def is_cash_deal(self) -> bool:
        return self.retirement_category == "ACQUISITION_CASH"


@functools.lru_cache(maxsize=1)
def load() -> dict[str, Settlement]:
    """读技术方的 30 只结果表。★ 这是唯一的事实来源,我们不自己判断。"""
    if not os.path.exists(REVIEW_JSON):
        raise FileNotFoundError(
            f"拿不到技术方的退市结算价核实表:{REVIEW_JSON} —— "
            "拿不到就是拿不到,不用别的顶上(硬纪律第 7 条)")
    with open(REVIEW_JSON, encoding="utf-8") as fh:
        recs = json.load(fh)["records"]
    out: dict[str, Settlement] = {}
    for r in recs:
        px = r.get("delisting_settlement_price")
        if px is None:
            basis: Basis = "null_evidence"
        elif float(px) == 0.0:
            basis = "verified_zero"
        else:
            basis = "verified_cash"
        out[r["symbol"]] = Settlement(
            symbol=r["symbol"],
            retirement_category=(r.get("retirement_category") or "").strip(),
            basis=basis,
            price=None if px is None else float(px),
            consideration_type=r.get("transaction_consideration_type"),
            status=r.get("status") or "",
            note=r.get("settlement_price_basis") or "",
        )
    return out


def settlement_for(symbol: str) -> Settlement | None:
    return load().get(symbol)


def by_basis(basis: Basis) -> list[str]:
    return sorted(s.symbol for s in load().values() if s.basis == basis)


def forced_price(symbol: str) -> float | None:
    """
    ★ 引擎要用的那个数。
      返回 float  → 必须按这个价结算(含 0.0)
      返回 None   → 证据拿不到,用最后收盘价(★ 调用方必须把它单独记账)
    """
    s = settlement_for(symbol)
    if s is None:
        return None
    if s.basis in ("verified_cash", "verified_zero"):
        return s.price
    if TREAT_NULL_AS_ZERO:
        return 0.0
    return None


# ───────────────────────── 和我们原来 −100% 名单的逐只对照 ─────────────────────────

def diff_vs_old_bankruptcy_rule() -> dict:
    """
    ★ Lin 要的「逐只对一遍并报出差异」。
    老口径 = data.BANKRUPTCY_CATEGORIES(bankruptcy + 4 个实质破产类)一律 −100%。
    """
    from . import data
    old_zero = {s for s, m in data.load_manifest().items()
                if m.delisted and m.is_bankruptcy}
    # ★ 注意:AMRS / PRTY 原来被拆股闸整只剔掉,manifest 里读不到,
    #   这里按 retirement_category 直接补齐,免得对账漏人
    import csv
    with open(data.MANIFEST_CSV, newline="", encoding="utf-8") as fh:
        for row in csv.DictReader(fh):
            if (row["delisted"].strip().lower() == "true"
                    and row["retirement_category"].strip()
                    in data.BANKRUPTCY_CATEGORIES):
                old_zero.add(row["symbol"].strip())

    new_zero = set(by_basis("verified_zero"))
    nulls = set(by_basis("null_evidence"))
    return {
        "老口径按−100%的": sorted(old_zero),
        "技术确认归零的": sorted(new_zero),
        "两边都有(不变)": sorted(old_zero & new_zero),
        "★老口径记0但技术说证据拿不到(改为最后收盘价)": sorted(old_zero & nulls),
        "★技术说归零但老口径没记0(改为记0)": sorted(new_zero - old_zero),
    }


def report() -> str:
    s = load()
    cash = by_basis("verified_cash")
    zero = by_basis("verified_zero")
    nul = by_basis("null_evidence")
    d = diff_vs_old_bankruptcy_rule()
    lines = [
        "退市结算闸(技术方 2026-10-28 核实表,30 只):",
        f"  ① 固定全现金并购价 {len(cash)} 只 → 按结算价平仓:",
        "       " + ", ".join(f"{k} {s[k].price:g}" for k in cash),
        f"  ② 已确认普通股归零 {len(zero)} 只 → 记 0(真 −100%):",
        f"       {', '.join(zero)}",
        f"  ③ ★ 证据拿不到 {len(nul)} 只 → 用最后收盘价,★ 单独记账,★ 不许当 0:",
        f"       {', '.join(nul)}",
        "",
        "  ★★ 和我们原来「破产类一律 −100%」的逐只差异:",
        f"     老口径记 0 的 {len(d['老口径按−100%的'])} 只:{d['老口径按−100%的']}",
        f"     技术确认归零的 {len(d['技术确认归零的'])} 只:{d['技术确认归零的']}",
        f"     ✅ 两边一致 {len(d['两边都有(不变)'])} 只:{d['两边都有(不变)']}",
        f"     ★ 我们多记了 0 的 {len(d['★老口径记0但技术说证据拿不到(改为最后收盘价)'])} 只:"
        f"{d['★老口径记0但技术说证据拿不到(改为最后收盘价)']}"
        f"  ← ★ 这几只改为最后收盘价,成绩会变好看一点",
        f"     ★ 我们漏记 0 的 {len(d['★技术说归零但老口径没记0(改为记0)'])} 只:"
        f"{d['★技术说归零但老口径没记0(改为记0)']}",
        "",
        "  ★ 并购细分:",
        f"     ACQUISITION_CASH  {len([x for x in s.values() if x.is_cash_deal])} 只 → 按结算价平仓,交易结束",
        f"     ACQUISITION_STOCK {len([x for x in s.values() if x.is_stock_deal])} 只 → "
        "★ 应该变成收购方股票、交易没结束,但★ 仓库里没有收购方日线 → ",
        "       ★ 拿不到。按退市日最后收盘价结算 + 单独标记:",
    ]
    for k, v in sorted(STOCK_DEAL_ACQUIRERS.items()):
        lines.append(f"         {k:5s} → 收购方 {v}(日线:★ 没有)")
    return "\n".join(lines)


if __name__ == "__main__":
    print(report())
