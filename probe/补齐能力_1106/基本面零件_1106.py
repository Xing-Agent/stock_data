# -*- coding: utf-8 -*-
"""
★★★ 给引擎补**基本面选股零件** —— ★ engine 零改动（进程内覆盖层）。

★★ 为什么要这个（1106 实测打出来的，不是记的）：
  引擎的「选股池」规则**一共只有 12 种**，其中和基本面有关的**只有 5 种**：
    altman_z_double_prime_exclude_bottom · fcf_yield_rank_top
    · piotroski_f_score_above · piotroski_f_score_three_layer · sloan_accrual_below
  ★★★ 而方法库里有 **23 张基本面卡**，要的是市盈率、市净率、EV/EBIT、ROC、
    股息率、Net-Net…★ **引擎一个都没有** → 23 条里只能表达 4~6 条。

★★★ 做法照抄已有两套覆盖层（接新财报库_1106.py / pat6_ops.install）：
  ① 包一层 `fundamentals.metric_quarterly` —— 认得新指标名就自己算，认不出**原样转回**
  ② 包一层 `matrices._universe_rule_mask` —— 认得新规则就自己判，认不出**原样转回**
  ③ 清掉 engine.fundamentals 的 lru_cache
★★ 「原样转回」这一条是铁律：★★★ **不许吞掉不认识的类型**（照 pat6_ops.py:966 的做法）。

★★★ 三条共同铁律（照抄 engine/matrices.py:364 那段注释，一个字不改意思）：
  ① 生效时点 = filing_date + 1 个交易日（★ 严禁用报告期截止日）
  ② 未公布期间沿用上一期；第一次公布之前 = NaN
  ③ ★★★ NaN 的那天一律判「不合格」—— **不猜、不补、不用近似值顶上**

★★ 口径档位（★ 每个零件都标了，配置里要照抄）：
  · 定义本身来自原著/教科书的 → ①档
  · **阈值**几乎都是惯例 → ②档；★★★ 原著没给数的**一律跑相邻三点**
  · 我们自己选的近似 → ③档，并在 docstring 里写明**偏差方向**
"""
from __future__ import annotations

import functools
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_装过 = False

# ════════════════════════════════════════════════════════════════════
# ★ 一 · 新增的派生指标（季度序列）
#   ★★ 命名规矩：**带价格的一律做成「每股」量**，由规则层再除/乘当日收盘 ——
#     ★★★ 照抄 fcf_yield_rank_top 的做法（engine/matrices.py:370），
#       因为价格是日频、财报是季频，混在一起算会把生效时点搞错。
# ════════════════════════════════════════════════════════════════════
新指标 = (
    "eps_ttm_ps",          # ★ 每股收益 TTM
    "bvps",                # ★ 每股净资产
    "ebit_ttm_ps",         # ★ 每股 EBIT（TTM）
    "steady_ebit_ps",      # ★★ 每股「稳态 EBIT」= 近 20 季 EBIT 中位 × 4
    "netdebt_ps",          # ★ 每股净债务 = (总债 − 现金) / 股数
    "div_ttm_ps",          # ★ 每股分红 TTM
    "ncav_ps",             # ★★ 每股净流动资产 =（流动资产 − 总负债）/ 股数
    "roc",                 # ★★ 资本回报率 = EBIT_TTM /（净运营资本 + 净固定资产）
    "interest_cov",        # ★ 利息覆盖 = EBIT_TTM / 利息支出
)


def _ttm(s: pd.Series) -> pd.Series:
    """★ 四个季度滚动求和。★★ 不满 4 季 → NaN（不用 3 季顶替）。"""
    return s.rolling(4, min_periods=4).sum()


def _原始(F, symbol: str, metric: str) -> pd.Series | None:
    """★ 取 quarter_frame 那 16 个短代号之外的科目（按**库自己的** XBRL 名）。
       ★★★ 规矩⑬：科目名是**打出来核过的**，不是凭记忆写的 ——
         新库 50 个科目名见 probe/补齐能力_1106/补齐_1106.py 的注释。"""
    try:
        obs = F.quarterly(symbol, metric)
    except Exception:
        return None
    if not obs:
        return None
    s = pd.Series({o.period_end: o.value for o in obs}).dropna()
    return s.sort_index() if len(s) else None


def metric_quarterly(F, symbol: str, name: str,
                     vals: pd.DataFrame, ef: pd.DataFrame
                     ) -> tuple[pd.Series, pd.Series]:
    """★ 新派生指标的季度序列。★★★ 算不出一律 NaN —— 不猜、不补。"""
    空 = (pd.Series(dtype=float), pd.Series(dtype="datetime64[ns]"))
    if vals is None or vals.empty:
        return 空
    生效 = ef.iloc[:, 0] if (ef is not None and not ef.empty) else None

    def 收(v: pd.Series):
        v = v.replace([np.inf, -np.inf], np.nan)
        e = 生效.reindex(v.index) if 生效 is not None else pd.Series(
            v.index, index=v.index)
        return v, e

    有 = lambda *c: all(x in vals.columns for x in c)   # noqa: E731
    股 = vals["shares"].where(vals["shares"] > 0) if 有("shares") else None

    if name == "eps_ttm_ps":
        # ★ ①档 定义（每股收益）；★★ 用**摊薄**股数（库里 shares 就是摊薄的）
        if not 有("ni", "shares"):
            return 空
        return 收(_ttm(vals["ni"]) / 股)

    if name == "bvps":
        # ★ ①档 定义（每股净资产 = 股东权益 / 股数）—— ★★ 存量科目，不做 TTM
        if not 有("eq", "shares"):
            return 空
        return 收(vals["eq"] / 股)

    if name == "ebit_ttm_ps":
        if not 有("ebit", "shares"):
            return 空
        return 收(_ttm(vals["ebit"]) / 股)

    if name == "steady_ebit_ps":
        # ★★ ③档 我们的：近 **20 个季度（5 年）** EBIT 的**中位数** × 4 → 年化
        #   ★ 用中位数不用平均：避免一次性损益带偏。
        #   ★★★ 不满 20 季 → NaN（★ 不用短窗口顶替）
        if not 有("ebit", "shares"):
            return 空
        return 收(vals["ebit"].rolling(20, min_periods=20).median() * 4.0 / 股)

    if name == "netdebt_ps":
        # ★ ①档 定义（净债务 = 总债 − 现金）
        #   ★★ 总债 = 长期债 + 短期债（两个来源都试，★★★ 缺哪个都不补 0）
        if not 有("ltd", "shares"):
            return 空
        短 = _原始(F, symbol, "DebtCurrent")
        if 短 is None:
            短 = _原始(F, symbol, "ShortTermBorrowings")
        if 短 is None:
            短 = _原始(F, symbol, "ShortTermDebt")
        现 = _原始(F, symbol, "CashAndCashEquivalentsAtCarryingValue")
        if 短 is None or 现 is None:
            return 空
        idx = vals.index
        债 = vals["ltd"] + 短.reindex(idx)
        return 收((债 - 现.reindex(idx)) / 股)

    if name == "div_ttm_ps":
        # ★ ①档 定义（每股分红）。★★ 三个科目名都试（库里口径不统一）
        if not 有("shares"):
            return 空
        d = None
        for m in ("PaymentsOfDividendsCommonStock", "PaymentsOfDividends",
                  "DividendsPaid"):
            d = _原始(F, symbol, m)
            if d is not None:
                break
        if d is None:
            return 空
        # ★★★ 分红是**现金流出**，库里可能是正也可能是负 → 取绝对值
        return 收(_ttm(d.reindex(vals.index).abs()) / 股)

    if name == "ncav_ps":
        # ★★ ①档 格雷厄姆原著口径：净流动资产 = 流动资产 − **总负债**
        #   ★★★ 注意：是减**总**负债，不是减流动负债（★ 这是原著的保守之处）
        if not 有("ca", "liab", "shares"):
            return 空
        return 收((vals["ca"] - vals["liab"]) / 股)

    if name == "roc":
        # ★★ ①档 乔尔·格林布拉特《股市稳赚》口径：
        #   ROC = EBIT ÷（**净运营资本** + **净固定资产**）
        #   ★ 净运营资本 = 流动资产 − 流动负债
        #   ★★ 净固定资产 = PropertyPlantAndEquipmentNet
        #   ★★★ 分母 ≤ 0 → NaN（★ 不取绝对值、不设下限 —— 那会造出假的高 ROC）
        if not 有("ebit", "ca", "cl"):
            return 空
        ppe = _原始(F, symbol, "PropertyPlantAndEquipmentNet")
        if ppe is None:
            return 空
        分母 = (vals["ca"] - vals["cl"]) + ppe.reindex(vals.index)
        return 收(_ttm(vals["ebit"]) / 分母.where(分母 > 0))

    if name == "interest_cov":
        # ★ ①档 定义（利息覆盖 = EBIT / 利息支出）
        if not 有("ebit"):
            return 空
        ie = _原始(F, symbol, "InterestExpense")
        if ie is None:
            return 空
        分母 = ie.reindex(vals.index).abs()
        return 收(_ttm(vals["ebit"]) / 分母.where(分母 > 0))

    return 空


# ════════════════════════════════════════════════════════════════════
# ★ 二 · 新增的「选股池」规则
# ════════════════════════════════════════════════════════════════════
新规则 = (
    "pe_rank_bottom",            # ★★ 低市盈率（池内横截面分位，留最低的 N%）
    "pb_below",                  # ★★ 市净率低于阈值
    "ev_ebit_rank_bottom",       # ★★ 收购者倍数（EV/EBIT 最低的 N%）
    "roc_rank_top",              # ★★ 资本回报率最高的 N%
    "dividend_yield_rank_top",   # ★ 股息率最高的 N%
    "net_net_below",             # ★★ 价格低于每股净流动资产 × factor
    "steady_earnings_yield_top", # ★★★ 稳态 EBIT ÷ EV 最高的 N%（★ 不用折现率）
    "interest_coverage_above",   # ★ 利息覆盖高于阈值
)


def _分位留低(x: pd.DataFrame, bottom_pct: float) -> pd.DataFrame:
    """★ 池内横截面分位，留最低的 bottom_pct% —— ★★ NaN 一律判不合格。"""
    pct = x.rank(axis=1, pct=True)
    return (x.notna() & (pct <= bottom_pct / 100.0)).fillna(False)


def _分位留高(x: pd.DataFrame, top_pct: float) -> pd.DataFrame:
    pct = x.rank(axis=1, pct=True)
    return (x.notna() & (pct >= 1.0 - top_pct / 100.0)).fillna(False)


def universe_rule_mask(M, rule: dict, syms: list[str],
                       index: pd.DatetimeIndex) -> pd.DataFrame | None:
    """★ 认得就返回布尔矩阵；★★★ 认不出返回 None（由包装层原样转回原函数）。"""
    t = rule.get("type")
    if t not in 新规则:
        return None
    p = rule.get("params", {}) or {}
    close = M.cache.field("close", syms)
    F = M.fundamentals

    def 每股(name):
        return F.get(name, syms).reindex(index=close.index, columns=syms)

    if t == "pe_rank_bottom":
        # ★★ ②档 阈值是惯例（原著没给具体分位）→ ★★★ 配置里要跑相邻三点
        #   ★ 亏钱的公司（每股收益 ≤ 0）市盈率没有意义 → NaN，判不合格
        eps = 每股("eps_ttm_ps")
        pe = close / eps.where(eps > 0)
        return _分位留低(pe, float(p.get("rank_bottom_pct", 20)))

    if t == "pb_below":
        # ★★ ①档 定义 + ②档 阈值（★ 施洛斯/格雷厄姆用过 1.0 / 1.2 / 0.66 等不同数）
        bv = 每股("bvps")
        pb = close / bv.where(bv > 0)
        thr = float(p.get("max_pb", 1.0))
        return (pb.notna() & (pb < thr)).fillna(False)

    if t == "ev_ebit_rank_bottom":
        # ★★ ①档 定义（收购者倍数，Tobias Carlisle）：EV / EBIT
        #   ★ EV 的每股形式 = 收盘 + 每股净债务
        nd = 每股("netdebt_ps")
        eb = 每股("ebit_ttm_ps")
        ev_ps = close + nd
        x = ev_ps.where(ev_ps > 0) / eb.where(eb > 0)
        return _分位留低(x, float(p.get("rank_bottom_pct", 20)))

    if t == "roc_rank_top":
        return _分位留高(每股("roc"), float(p.get("rank_top_pct", 20)))

    if t == "dividend_yield_rank_top":
        dv = 每股("div_ttm_ps")
        y = dv.where(dv > 0) / close.replace(0.0, np.nan)
        return _分位留高(y, float(p.get("rank_top_pct", 20)))

    if t == "net_net_below":
        # ★★ ①档 格雷厄姆原著：市值 < 每股净流动资产 × **2/3**
        ncav = 每股("ncav_ps")
        f = float(p.get("factor", 2.0 / 3.0))
        x = ncav.where(ncav > 0) * f
        return (x.notna() & (close < x)).fillna(False)

    if t == "steady_earnings_yield_top":
        # ★★★ 基 1.3 / 4.5 的**替代口径** —— ★ 不需要折现率，
        #   所以不碰「自己定折现率 = 自己发明一个闸」那条红线。
        #   ★★ 界面上必须写清：**这不是教科书的「安全边际」**（那要先有 DCF 内在价值）。
        se = 每股("steady_ebit_ps")
        nd = 每股("netdebt_ps")
        ev_ps = close + nd
        y = se.where(se > 0) / ev_ps.where(ev_ps > 0)
        return _分位留高(y, float(p.get("rank_top_pct", 20)))

    if t == "interest_coverage_above":
        ic = 每股("interest_cov")
        thr = float(p.get("min_coverage", 3.0))
        return (ic.notna() & (ic > thr)).fillna(False)

    return None


# ════════════════════════════════════════════════════════════════════
# ★ 三 · 装上（★★★ engine 一个字节都没动）
# ════════════════════════════════════════════════════════════════════
def install() -> dict:
    global _装过
    if _装过:
        return {"★已装过": True}
    sys.path.insert(0, ROOT)
    from engine import fundamentals as F, matrices as M

    # ★★★ 先补登记口径 —— ★ 引擎**明确拒绝猜**科目是流量还是存量
    #   (`fundamentals.py:151` 直接报错:「不许猜它是哪种口径,请先登记」)。
    #   ★★ 这是引擎做得对的一处,所以我们**补登记**,不绕过。
    #   ★★★ 下面这些都是**资产负债表科目 = 存量**(某一时点的余额,不做差分、不滚 TTM):
    新存量 = {
        "ShortTermDebt",                 # ★ 短期债务(AAL/AAPL/MSFT 都只有这个,没有 DebtCurrent)
        "PropertyPlantAndEquipmentNet",  # ★★ 净固定资产(ROC 的分母要它)
        "ShortTermInvestments",          # ★ 短期投资(现金跑道要它)
        "MarketableSecuritiesCurrent",
        "AvailableForSaleSecuritiesDebtSecuritiesCurrent",
        "CashCashEquivalentsAndShortTermInvestments",
        "IncomeTaxesPayable",
    }
    新流量 = {
        "GrossProfit",                   # ★ 毛利
        "OperatingIncomeLoss",            # ★ 营业利润
        "SellingGeneralAndAdministrativeExpense",  # ★★★ SG&A(Beneish M 要它)
        "IncomeLossFromContinuingOperations",
        "DividendsPaid",
        "ShareRepurchase",
        "StockIssuance",
        "IncreaseDecreaseInIncomeTaxesPayable",
    }
    _加存 = sorted(新存量 - set(F.STOCK_METRICS))
    _加流 = sorted(新流量 - set(F.FLOW_METRICS))
    F.STOCK_METRICS |= 新存量
    F.FLOW_METRICS |= 新流量

    旧指标 = F.metric_quarterly

    def 新指标fn(symbol: str, name: str):
        if name in 新指标:
            try:
                vals, ef = F.quarter_frame(symbol)
            except Exception:
                return (pd.Series(dtype=float),
                        pd.Series(dtype="datetime64[ns]"))
            return metric_quarterly(F, symbol, name, vals, ef)
        # ★★★ 认不出 → **原样转回原函数**（铁律，不许吞掉）
        return 旧指标(symbol, name)

    if hasattr(旧指标, "cache_clear"):
        旧指标.cache_clear()
    F.metric_quarterly = 新指标fn

    旧规则 = M._universe_rule_mask

    def 新规则fn(rule: dict, syms, index):
        r = universe_rule_mask(M, rule, list(syms), index)
        if r is not None:
            return M._as_bool(r)
        # ★★★ 认不出 → **原样转回原函数**
        return 旧规则(rule, syms, index)

    M._universe_rule_mask = 新规则fn

    for fn in (getattr(F, "panel", None), getattr(F, "quarterly", None),
               getattr(F, "ttm", None), getattr(F, "quarter_frame", None),
               getattr(F, "shares_quarterly", None)):
        if fn is not None and hasattr(fn, "cache_clear"):
            fn.cache_clear()

    _装过 = True
    return {"★装上了": True,
            "★补登记的存量科目": _加存,
            "★补登记的流量科目": _加流,
            "★★为什么要补登记": "★ 引擎明确拒绝猜科目口径(fundamentals.py:151 报错)"
                            " —— ★★ 这是引擎做得对的一处,所以补登记,不绕过",
            "★新指标": list(新指标),
            "★★新规则": list(新规则),
            "★★★engine改动": "零 —— 只在进程内替换函数指针",
            "★认不出怎么办": "原样转回原函数（不许吞掉）"}


if __name__ == "__main__":
    import json
    sys.path.insert(0, ROOT)
    os.chdir(ROOT)
    sys.path.insert(0, os.path.dirname(__file__))
    import 接新财报库_1106 as EXT
    print(json.dumps(EXT.install(), ensure_ascii=False))
    print(json.dumps(install(), ensure_ascii=False, indent=1))
    from engine import fundamentals as F
    for n in 新指标:
        v, e = F.metric_quarterly("AAL", n)
        print(f"★ AAL {n:18s} 期数 {len(v.dropna()) if len(v) else 0}")
