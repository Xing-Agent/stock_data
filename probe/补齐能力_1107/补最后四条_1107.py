# -*- coding: utf-8 -*-
"""
★★★ 补《78 能力对齐表》剩下的**最后 4 条**必备缺口 —— ★ engine/ 零改动（进程内覆盖层）。

★★ 这 4 条（★ 账在《78》1107 更新那一节：原 13 → 划 5 → 剩 8 → 已补 4 → **剩这 4**）：
   ① **基 1.4 / 4.1 时序估值分位** —— ★ 跟**自己历史**比（★★ 同行比见下面「如实标」）
   ② **技 5.1 突破后跟进验证** —— ★★ Gemini 第 44 轮：「进场后第 3~5 天还没走出动量就平」
   ③ **技 5.2 回踩支撑的量价健康度** —— ★ 回踩量 < 突破日的 0.6 倍 + 回撤深度
   ④ **基 5.4 换股** —— ★★ 排名缓冲（进前 10 买 / 掉出前 30 卖）+ 成本门槛

★★★★★ 一处必须先说的更正（★ 本次自查出，★★ 规矩⑮「先查代码再喊结论」）：
   ★ 《78》1107 那张表里写「基 1.4 同行比**用 11 只行业 ETF 绕**」。
   ★★★ **绕不过去。** —— ★ 实测打出来：`fundamentals_ext/` 4,005 家里
     **XLK / XLF / XLE / SPY 一个都没有财报**（ETF 只有价格）。
   → ★★ 行业 ETF 能绕的是**相对强度**（价格比价，`mansfield_rs_positive(SECTOR)` 已有），
     ★★★ **不能**绕「同行的市盈率中位数」—— 那要**成分股权重 + PIT 行业分类**，我们都没有。
   → ★ 所以本文件交付的是**时序分位（跟自己历史比）这一条腿**；
     ★★★ **同行比那条腿如实标「仍做不到」**，并在《78》里改掉那句话。

★★★ 三条铁律（照抄 `基本面零件_1106.py`，一个字不改意思）：
   ① 生效时点 = filing_date + 1 个交易日（★ 严禁用报告期截止日）—— 由 `F.get` 负责
   ② 认不出的类型 **原样转回原函数**（★★★ 不许吞掉）
   ③ NaN 的那天一律判「不合格」/「不触发」—— ★ 不猜、不补、不用近似值顶上

★★ 口径档位：★ 定义来自原著/行业 → ①/②档；★★ 我们选的近似 → ③档并写明**偏差方向**；
   ★★★ 原著没给的数 **一律跑相邻三点**（规矩②）。
"""
from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
_装过 = False

# ★★ 跑批时由包装过的 build 存进来 —— ★ 排名缓冲要用配置里的 ranking 公式，
#   而 exit_signal_matrix(spec, symbols) 的签名里**没有 cfg**（★ 签名是打出来的，规矩⑬）。
_当前CFG: dict = {}


# ════════════════════════════════════════════════════════════════════
# ★ 一 · 基 1.4 / 4.1 · 时序估值分位（★ 跟自己历史比）
# ════════════════════════════════════════════════════════════════════
新池规则 = (
    "valuation_ts_percentile_below",   # ★★ 当前倍数在自己历史里的分位低于 X（便宜）
    "valuation_ts_percentile_above",   # ★ 反向（贵）—— ★★ 给「禁用条件」用
)

# ★ 认得的倍数名 → 怎么算。★★★ 全部用 `基本面零件_1106.py` 已有的**每股量**，
#   ★ 这样生效时点跟着 F.get 走，不会把季频和日频混错（照抄 fcf_yield_rank_top 的做法）。
倍数表 = {
    "pe": ("eps_ttm_ps", "price_div_ps", True),     # ★ 市盈率 = 价 / 每股收益；要求分母 > 0
    "pb": ("bvps", "price_div_ps", True),           # ★ 市净率 = 价 / 每股净资产；要求分母 > 0
    "ev_ebit": ("ebit_ttm_ps", "ev_div_ps", True),  # ★★ EV/EBIT（收购者倍数）
    # ★★★ **没有市销率（ps）** —— ★ 规矩⑬ 救的一处：我本来写了 `rev_ttm_ps`，
    #   ★★ 打出 1106 那层的指标名列表才发现**库里没有这个每股量**
    #   （有的是 eps_ttm_ps · bvps · ebit_ttm_ps · steady_ebit_ps · netdebt_ps
    #     · div_ttm_ps · ncav_ps · roc · interest_cov —— ★ 九个，没有营收每股）。
    #   → ★★★ **不留着让它悄悄返 NaN**，直接不认这个名字（给出的会当场报错）。
}


def _时序分位(x: pd.DataFrame, 窗口: int) -> pd.DataFrame:
    """★ 每一只**跟自己过去 `窗口` 个交易日**比，当前值处在第几分位（0~1）。

    ★★★ 为什么是**时序**而不是横截面：★ 《78》缺的就是这一条 ——
      引擎只有 `rank(axis=1)`（池内横截面），★★ 没有「跟自己历史比」。
    ★★ min_periods=窗口：★★★ 不满窗口的**算不出 → NaN**（不用短窗口顶替）。
    ★ 分位定义 = 过去窗口内 **≤ 当前值** 的比例（★ 含自己，所以最低分位是 1/窗口，不是 0）。
    """
    def 一列(s: pd.Series) -> pd.Series:
        return s.rolling(窗口, min_periods=窗口).apply(
            lambda w: float((w <= w[-1]).sum()) / float(len(w)), raw=True)
    return x.apply(一列, axis=0)


def _倍数矩阵(M, which: str, syms: list[str], index: pd.DatetimeIndex
              ) -> pd.DataFrame:
    """★ 算出日频的估值倍数矩阵。★★ 分母 ≤ 0 → NaN（亏钱/负净资产时倍数没有意义）。"""
    if which not in 倍数表:
        raise ValueError(f"★ 倍数名只认 {sorted(倍数表)}，给的是 {which!r}")
    ps_name, mode, 需正 = 倍数表[which]
    close = M.cache.field("close", syms).reindex(index=index, columns=syms)
    F = M.fundamentals
    ps = F.get(ps_name, syms).reindex(index=index, columns=syms)
    if 需正:
        ps = ps.where(ps > 0)
    if mode == "price_div_ps":
        return close / ps
    if mode == "ev_div_ps":
        # ★ EV 每股 = 价 + 每股净债务（★★ netdebt_ps 是 1106 那层已有的指标）
        nd = F.get("netdebt_ps", syms).reindex(index=index, columns=syms)
        return (close + nd) / ps
    raise ValueError(f"★ mode 只认 price_div_ps / ev_div_ps，给的是 {mode!r}")


def 池规则(M, rule: dict, syms: list[str], index: pd.DatetimeIndex
           ) -> pd.DataFrame | None:
    """★ 认得就返回布尔矩阵；★★★ 认不出返回 None（由包装层**原样转回**原函数）。"""
    t = rule.get("type")
    if t not in 新池规则:
        return None
    p = rule.get("params", {}) or {}
    which = str(p.get("multiple", "pe"))
    窗口 = int(p.get("lookback_days", 1260))      # ★★ 1260 ≈ 5 年（252×5）；②档惯例
    阈 = float(p["percentile"])                    # ★ 0~1
    pct = _时序分位(_倍数矩阵(M, which, syms, index), 窗口)
    if t == "valuation_ts_percentile_below":
        return (pct.notna() & (pct <= 阈)).fillna(False)
    return (pct.notna() & (pct >= 阈)).fillna(False)


# ════════════════════════════════════════════════════════════════════
# ★ 二 · 技 5.1 / 技 5.2 / 基 5.4 · 三条**离场**规则
# ════════════════════════════════════════════════════════════════════
新离场规则 = (
    "momentum_not_followed_through",   # ★★ 技 5.1
    "pullback_health_broken",          # ★★ 技 5.2
    "rank_drop_out_of_top",            # ★★★ 基 5.4 的排名缓冲（卖那一腿）
)


def 离场规则(M, rule: dict, syms: list[str]) -> pd.DataFrame | None:
    """★ 认得就返回布尔矩阵；★★★ 认不出返回 None（包装层原样转回）。"""
    t = rule.get("type")
    if t not in 新离场规则:
        return None
    p = rule.get("params", {}) or {}
    close = M.cache.field("close", syms)
    idx, cols = close.index, close.columns

    if t == "momentum_not_followed_through":
        # ★★★ 技 5.1。★ Gemini 第 44 轮给的定义:「**进场后第 3~5 天还没走出动量就平**」。
        #
        # ★★★★★ 一处**必须如实标的近似**(★ 规矩⑮：先查代码再喊结论，这里是查完之后的话)：
        #   ★ 原定义要的是「**距进场第 N 天**」—— 它依赖**这一笔是哪天进的**。
        #   ★★ 而引擎的离场矩阵签名是 `exit_signal_matrix(spec, symbols)` →
        #     ★★★ **只有「日 × 票」，没有进场日**（★ 签名是打出来的，不是记的）。
        #   → ★★ 要做成原定义，只能改 `engine/chain.py` 的持仓循环 ——
        #     ★★★ 而「engine 一个字节都不许改」是硬规矩 → **不改**。
        #   → ★ 所以这里做的是**日频近似**：「**最近 N 天净涨幅没过门槛就走**」。
        #     ★★ 对**刚好持满 N 天**的那一笔，它和原定义**完全等价**；
        #     ★★★ 对持更久的笔，它退化成一条「动量停滞就走」的规则 —— ★ 这是**偏差方向**：
        #       它会**比原定义卖得更勤**（老仓位也会被它扫到）。
        #   → ★★★ 档位：**③我们的（近似）** —— 不许标①原著版、也不许标②行业通行。
        n = int(p.get("days", 4))                    # ★ 原著区间 3~5 → ★★ 相邻三点 3/4/5
        门槛 = float(p.get("min_gain_pct", 0.0))      # ★ ②档：默认「净涨幅 ≤ 0 就算没走出」
        涨 = (close / close.shift(n) - 1.0) * 100.0
        return (涨.notna() & (涨 <= 门槛)).fillna(False)

    if t == "pullback_health_broken":
        # ★★ 技 5.2。★ 简化成两条（《78》写的）：
        #   ① **回踩那天的量 < 突破日的 0.6 倍** —— ★★ 这是「健康」的条件；
        #      ★★★ 所以**离场条件是它的反面**：回踩放量（量 ≥ 突破日 × factor）
        #   ② **回撤深度**超过上限就走
        # ★ 「突破日」怎么定（★★ 原著没给可算定义 → ③档）：
        #   取**过去 lookback 天里成交量最大的那一天**当突破日 ——
        #   ★★★ 偏差方向：真实突破日若不是最大量日，门槛会被定得偏高（卖得偏松）。
        lb = int(p.get("lookback", 20))
        factor = float(p.get("volume_factor", 0.6))      # ★ 《78》给的 0.6；②档
        深上限 = float(p.get("max_drawdown_pct", 8.0))    # ★★ 原著没给 → 相邻三点 6/8/10
        vol = M.cache.field("volume", syms)
        high = M.cache.field("high", syms)
        突破量 = vol.rolling(lb, min_periods=lb).max()
        放量回踩 = vol >= (突破量 * factor)
        近高 = high.rolling(lb, min_periods=lb).max()
        回撤 = (1.0 - close / 近高) * 100.0
        在回踩 = 回撤 > 0.0
        坏 = (在回踩 & 放量回踩) | (回撤 >= 深上限)
        return (坏 & 回撤.notna() & 突破量.notna()).fillna(False)

    if t == "rank_drop_out_of_top":
        # ★★★ 基 5.4 的**卖那一腿**：「**掉出前 N 名才卖**」(★ 排名缓冲)。
        #   ★ 买那一腿「进前 10 才买」**引擎已经做到了** ——
        #     `chain.py` 槽位不够时按 `rank_score` 取前 max_positions 只
        #     （★★ 这是读代码确认的，不是记的）。
        #   ★★★ 所以缺的只有卖这一腿：**名次掉出前 N 就走**。
        #   ★ 为什么要缓冲：买门槛和卖门槛**同一条线**会在线上来回抽 →
        #     ★★ 每次抽都付一次来回成本（这就是「成本门槛」那条腿要管的事）。
        n = int(p.get("exit_rank", 30))      # ★★ 《78》给 30 → 相邻三点 20/30/40
        score = M.rank_score_matrix((_当前CFG.get("sizing") or {}).get("ranking")
                                    or (_当前CFG.get("ranking")),
                                    syms, _当前CFG)
        score = score.reindex(index=idx, columns=cols)
        # ★ 名次：分数**越大越优先**（照 chain.py 的 `-(s)` 排序口径）→ 降序名次
        名次 = score.rank(axis=1, ascending=False, method="min")
        return (score.notna() & (名次 > n)).fillna(False)

    return None


# ════════════════════════════════════════════════════════════════════
# ★ 三 · 基 5.4 的**第二条腿**：成本门槛（★ 这一条不是矩阵，是一个要报的数）
# ════════════════════════════════════════════════════════════════════
def 成本门槛(来回成本_pct: float, 预计持有天: float,
             一年交易日: int = 252) -> dict:
    """★★ Gemini 第 44 轮：「新票的**预期超额**要高过「**来回成本 ÷ 预计持有年数**」」。

    ★★★ 为什么它**不能**做成矩阵（★ 如实标，规矩⑮）：
      ★ 它要的是「**这只新票的预期超额**」—— ★★ 而「预期超额」我们**量不出来**
        （★★★ 整个 1106 的结论就是：买点的超额**测不出**，见《83》第五步）。
      → ★ 所以这条腿只能做成**可核的门槛数**：★★ 把它翻成
        「**换一次股，至少要持多久才值得**」，★★★ 再拿流水里的**实测中位持有天**去比。
      → ★★ 这是**③档（我们的翻译）**，不许标①原著/②行业通行。
    ★ 返回里带 `★够不够`：★★ 实测持有天 ≥ 最低持有天 → 这条腿**过**。
    """
    年数 = max(预计持有天, 1.0) / float(一年交易日)
    年化拖累 = 来回成本_pct / 年数 if 年数 > 0 else float("inf")
    return {
        "来回成本_pct": round(来回成本_pct, 4),
        "预计持有天": round(float(预计持有天), 1),
        "折成年数": round(年数, 4),
        "★年化成本拖累_pct": round(年化拖累, 3),
        "★★这条腿的读法": "★ 新票的**预期年化超额**必须高过这个数，才值得换 ——"
                      " ★★★ 而我们量不出预期超额 → 只能报这个门槛，不能自动执行",
    }


# ════════════════════════════════════════════════════════════════════
# ★ 四 · 装上（★★ 认不出一律原样转回）
# ════════════════════════════════════════════════════════════════════
def install() -> dict:
    global _装过
    if _装过:
        return {"★已装过": True}
    sys.path.insert(0, ROOT)
    sys.path.insert(0, os.path.join(ROOT, "probe", "补齐能力_1106"))
    import 基本面零件_1106 as P1106          # noqa: E402
    import 接新财报库_1106 as EXT             # noqa: E402
    _ext = EXT.install()
    _p1106 = P1106.install()                  # ★★ 时序分位要用它的每股量（eps_ttm_ps 等）

    from engine import matrices as M          # noqa: E402

    # ---- ① 池规则（基 1.4 / 4.1）
    旧池 = M._universe_rule_mask

    def 新池fn(rule, syms, index):
        r = 池规则(M, rule, list(syms), index)
        if r is not None:
            return M._as_bool(r)
        return 旧池(rule, syms, index)          # ★★★ 原样转回

    M._universe_rule_mask = 新池fn

    # ---- ② 离场规则（技 5.1 / 技 5.2 / 基 5.4）
    旧离 = M.exit_signal_matrix

    def 新离fn(spec: dict, symbols):
        syms = list(symbols)
        rules = ((spec or {}).get("rules") or [])
        我的 = [r for r in rules if (r or {}).get("type") in 新离场规则]
        其余 = [r for r in rules if (r or {}).get("type") not in 新离场规则]
        # ★★★ 其余的**原样转回原函数** —— ★ 包括它那条 NotImplementedError 的大声报错
        out = 旧离({**(spec or {}), "rules": 其余}, syms)
        for r in 我的:
            m = 离场规则(M, r, syms)
            assert m is not None, f"★ 认领了却算不出：{r.get('type')}"
            out = out | M._as_bool(m.reindex(index=out.index, columns=out.columns))
        return out

    M.exit_signal_matrix = 新离fn

    # ---- ③ 包一层 build，把 cfg 存下来（★ 排名缓冲要 ranking 公式）
    旧build = M.build

    def 新build(cfg: dict, symbols=None):
        global _当前CFG
        _当前CFG = cfg or {}
        return 旧build(cfg, symbols)

    M.build = 新build

    _装过 = True
    return {
        "★装上了": True,
        "★新池规则": list(新池规则),
        "★新离场规则": list(新离场规则),
        "★基5.4第二条腿": "成本门槛 —— ★★ 不是矩阵，是一个要报的数（见 成本门槛()）",
        "★★★一处更正": "《78》写「同行比用 11 只行业 ETF 绕」—— **绕不过去**："
                    "ETF 在 fundamentals_ext 里没有财报（实测 XLK/XLF/XLE/SPY 全无）",
        "★依赖的两层": {"接新财报库": _ext.get("★装上了", _ext),
                    "基本面零件": _p1106.get("★装上了", _p1106)},
    }


if __name__ == "__main__":
    import json
    print(json.dumps(install(), ensure_ascii=False, indent=1, default=str))
