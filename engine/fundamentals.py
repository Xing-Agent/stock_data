"""
基本面 PIT 层(2026-10-29 新增)—— 三条基本面链的全部指标都从这里出。

================================ 三秒版 ================================
这个文件只干一件事:**把 SEC 原始申报整理成「某一天能看到的、口径正确的」
基本面数字**。它处理掉三个会静默出错的坑:

  坑① ★ PIT 生效时点 —— 一律按 **filing_date + 1 个交易日** 生效,
       ★ 严禁用报告期截止日(period_end)。未公布期间沿用上一期(ffill),
       ★ 第一次公布之前一律 NaN(= 那天算不合格,不猜不补)。

  坑② ★★ 股数单位混乱 —— 同一字段混着「股 / 千股 / 百万股」。
       直接复用 share_gate 的三道闸(单位 / 区间 / 拆股),不另写一套。

  坑③ ★★ 现金流科目是「年初至今累计(YTD)」口径,不是单季。
       ★ 按季度直接相加算 TTM,会把 FCF / Sloan / ROIC 系统性放大约 2.5 倍,
         ★ 而且不报错。
       做法:按 period_start 分组、按 period_end 排序,**YTD 做差还原单季**,
       再滚 4 季。实测 ABT 2025:
         原始 YTD  Q1 1417 / H1 3464 / 9M 6251 / FY 9566(百万美元)
         直接相加  = 20698   ← ★ 错的,放大 2.16 倍
         差分还原  = 9566    ← ★ 对的(就是 FY 那个数)

★ 口径里所有「取哪一版」的选择一律是:**同一期只留首发版本**,
  不用后来的重述数据 —— 和 share_gate / analyze 一致。

跑法:python -m engine.fundamentals            # 自验三坑 + 覆盖率
=========================================================================
"""

from __future__ import annotations

import functools
import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from . import data, share_gate

# ---------------------------------------------------------------- 字段分类
# ★ 流量科目(利润表 / 现金流量表):YTD 累计口径,★ 必须差分还原单季再滚 TTM
FLOW_METRICS = {
    "Revenue", "CostOfRevenue", "EBIT", "NetIncome", "IncomeBeforeTax",
    "InterestExpense", "OperatingCashFlow", "DilutedEPS",
    "PaymentsToAcquirePropertyPlantAndEquipment",
    "PaymentsToAcquireProductiveAssets",
    "ProceedsFromIssuanceOfCommonStock",
    "PaymentsForRepurchaseOfCommonStock",
    "PaymentsOfDividends", "PaymentsOfDividendsCommonStock",
    "DepreciationDepletionAndAmortization",
    "DepreciationAmortizationAndAccretionNet",
    "ResearchAndDevelopmentExpense",
}
# ★ 存量科目(资产负债表):某一时点的余额,★ 不做差分、不滚 TTM
STOCK_METRICS = {
    "TotalAssets", "StockholdersEquity", "CurrentAssets", "CurrentLiabilities",
    "LongTermDebt", "LongTermDebtCurrent", "Liabilities", "ShortTermBorrowings",
    "DebtCurrent", "CashAndCashEquivalentsAtCarryingValue", "InventoryNet",
    "AccountsReceivableNetCurrent", "Goodwill", "IntangiblesAndGoodwill",
    "IntangibleAssetsNetExcludingGoodwill",
    "RetainedEarningsAccumulatedDeficit",
}

# 季度区间判定(自然日)。10-Q 的季度一般 85~98 天,留一点余量。
Q_MIN_DAYS, Q_MAX_DAYS = 75, 110
# 相邻两季 period_end 的间隔(自然日):连续性检查用
GAP_MIN_DAYS, GAP_MAX_DAYS = 70, 120


# ---------------------------------------------------------------- 生效时点

@functools.lru_cache(maxsize=1)
def _cal() -> pd.DatetimeIndex:
    return data.trading_calendar()


def effective_date(filing_ts: pd.Timestamp) -> pd.Timestamp | None:
    """
    ★ 坑①:filing_date + 1 个交易日 生效。

    大白话:SEC 受理常在收盘后(实测 ABT 是 20:05 UTC ≈ 美东 16:05,收盘后),
    所以「受理当天就能用」等于偷看。这里一律推到**受理日之后的下一个交易日**。
    """
    cal = _cal()
    d = pd.Timestamp(filing_ts).tz_localize(None).normalize()
    pos = int(np.searchsorted(cal.to_numpy(), np.datetime64(d), side="right"))
    return cal[pos] if pos < len(cal) else None


# ---------------------------------------------------------------- 原始取数

@dataclass(frozen=True)
class Obs:
    """一个季度观测:eff = 哪天能看到,period_end = 这笔数说的是哪一期。"""
    eff: pd.Timestamp
    period_end: pd.Timestamp
    value: float


def _raw(symbol: str, metric: str) -> list[dict]:
    out = []
    for r in (data.load_fundamentals(symbol).get(metric) or []):
        ts = r.get("filing_date") or r.get("accepted_at") or r.get("filed_at")
        val = r.get("value")
        pe = r.get("period_end")
        if ts is None or val in (None, "") or pe is None:
            continue
        try:
            out.append({
                "eff": effective_date(ts),
                "filing": pd.Timestamp(ts).tz_localize(None),
                "period_start": pd.Timestamp(r["period_start"]) if r.get("period_start") else None,
                "period_end": pd.Timestamp(pe),
                "value": float(val),
            })
        except (ValueError, TypeError):
            continue
    return [r for r in out if r["eff"] is not None]


# ---------------------------------------------------------------- 坑③ YTD 差分

@functools.lru_cache(maxsize=16384)
def quarterly(symbol: str, metric: str) -> tuple[Obs, ...]:
    """
    单季序列。

    ★ 流量科目走坑③的 YTD 差分还原:
      按 period_start 分组 → 按 period_end 排序 → 本期 = YTD(t) − YTD(t−1)。
      只保留还原出来的区间长度在 75~110 天之间的(= 真的是一个季度)。
    ★ 存量科目不做差分,直接取 period_end 上的余额。
    ★ 同一期只留**首发版本**(filing 最早的那条),不用重述数据。
    """
    recs = _raw(symbol, metric)
    if not recs:
        return ()

    if metric in STOCK_METRICS:
        best: dict[pd.Timestamp, dict] = {}
        for r in recs:
            cur = best.get(r["period_end"])
            if cur is None or r["filing"] < cur["filing"]:
                best[r["period_end"]] = r
        return tuple(Obs(r["eff"], pe, r["value"])
                     for pe, r in sorted(best.items()))

    if metric not in FLOW_METRICS:
        raise KeyError(f"字段 {metric} 没有分类(流量 / 存量)—— "
                       f"★ 不许猜它是哪种口径,请先在 FLOW_METRICS / "
                       f"STOCK_METRICS 里登记。")

    # 流量:先按 (period_start, period_end) 去重留首发
    uniq: dict[tuple, dict] = {}
    for r in recs:
        if r["period_start"] is None:
            continue
        k = (r["period_start"], r["period_end"])
        cur = uniq.get(k)
        if cur is None or r["filing"] < cur["filing"]:
            uniq[k] = r

    groups: dict[pd.Timestamp, list[dict]] = {}
    for (ps, _pe), r in uniq.items():
        groups.setdefault(ps, []).append(r)

    out: dict[pd.Timestamp, Obs] = {}
    for ps, rs in groups.items():
        rs.sort(key=lambda x: x["period_end"])
        prev_end, prev_val = None, 0.0
        for r in rs:
            span_start = ps if prev_end is None else prev_end + pd.Timedelta(days=1)
            span_days = (r["period_end"] - span_start).days + 1
            q_val = r["value"] - prev_val
            prev_end, prev_val = r["period_end"], r["value"]
            if not (Q_MIN_DAYS <= span_days <= Q_MAX_DAYS):
                continue          # 不是一个干净的季度 → 丢掉,不猜
            cur = out.get(r["period_end"])
            # 同一个 period_end 可能从不同 period_start 组还原出来 → 留 eff 最早的
            if cur is None or r["eff"] < cur.eff:
                out[r["period_end"]] = Obs(r["eff"], r["period_end"], q_val)
    return tuple(v for _, v in sorted(out.items()))


@functools.lru_cache(maxsize=16384)
def ttm(symbol: str, metric: str) -> tuple[Obs, ...]:
    """
    TTM(滚动 4 季)序列。★ 要求最近 4 季**时间连续**(相邻 period_end 相隔
    70~120 天),缺一季就不给数 —— 不拿 3 季凑、不年化。
    eff 取 4 季里最晚的那个(= 最后一季公布之后才看得到完整 TTM)。
    """
    qs = quarterly(symbol, metric)
    if metric in STOCK_METRICS:
        return qs                       # 存量科目没有 TTM 的概念
    out = []
    for i in range(3, len(qs)):
        win = qs[i - 3:i + 1]
        gaps = [(win[k + 1].period_end - win[k].period_end).days for k in range(3)]
        if any(not (GAP_MIN_DAYS <= g <= GAP_MAX_DAYS) for g in gaps):
            continue
        out.append(Obs(max(w.eff for w in win), win[-1].period_end,
                       float(sum(w.value for w in win))))
    return tuple(out)


# ---------------------------------------------------------------- 股数(走 share_gate)

@functools.lru_cache(maxsize=4096)
def shares_quarterly(symbol: str) -> tuple[Obs, ...]:
    """
    ★ 坑②:摊薄股数直接用 share_gate 过完三道闸(单位 / 区间 / 拆股)的序列。
    ★ 这里只把它的 accepted_at 换成「+1 个交易日」的生效口径,和别的科目统一。
    """
    out = []
    for p in share_gate.adjusted_points(symbol):
        e = effective_date(p.accepted_at)
        if e is not None:
            out.append(Obs(e, p.period_end, float(p.shares)))
    return tuple(out)


# ---------------------------------------------------------------- 季度对齐表

#: 每只票一张「按 period_end 对齐」的表:列是口径已经修正好的原始科目
_QCOLS = {
    "rev": ("Revenue", "ttm"),
    "cor": ("CostOfRevenue", "ttm"),
    "ni": ("NetIncome", "ttm"),
    "ocf": ("OperatingCashFlow", "ttm"),
    "capex_ppe": ("PaymentsToAcquirePropertyPlantAndEquipment", "ttm"),
    "capex_alt": ("PaymentsToAcquireProductiveAssets", "ttm"),
    "issue": ("ProceedsFromIssuanceOfCommonStock", "ttm"),
    "ta": ("TotalAssets", "pt"),
    "ca": ("CurrentAssets", "pt"),
    "cl": ("CurrentLiabilities", "pt"),
    "ltd": ("LongTermDebt", "pt"),
}


@functools.lru_cache(maxsize=4096)
def quarter_frame(symbol: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    返回 (值表, 生效日表),两张表都以 period_end 为索引、列名见 _QCOLS 再加 shares。

    ★ 两张表分开的原因:同一期不同科目的公布时间不一样(10-Q 里有的科目要到
      10-K 才补)。做派生指标时 eff 取**用到的那几列里最晚的那个** —— 保守一边。
    """
    cols: dict[str, dict] = {}
    effs: dict[str, dict] = {}
    for name, (metric, kind) in _QCOLS.items():
        series = ttm(symbol, metric) if kind == "ttm" else quarterly(symbol, metric)
        cols[name] = {o.period_end: o.value for o in series}
        effs[name] = {o.period_end: o.eff for o in series}
    sq = shares_quarterly(symbol)
    cols["shares"] = {o.period_end: o.value for o in sq}
    effs["shares"] = {o.period_end: o.eff for o in sq}

    idx = sorted({pe for d in cols.values() for pe in d})
    if not idx:
        return pd.DataFrame(), pd.DataFrame()
    vals = pd.DataFrame({k: pd.Series(v) for k, v in cols.items()}).reindex(idx)
    ef = pd.DataFrame({k: pd.Series(v) for k, v in effs.items()}).reindex(idx)
    vals.index = pd.DatetimeIndex(idx)
    ef.index = pd.DatetimeIndex(idx)
    return vals, ef


def _need(vals: pd.DataFrame, ef: pd.DataFrame, cols: list[str]
          ) -> tuple[pd.Series, pd.Series]:
    """要用到 cols 这几列:全都有值才算得出;eff 取最晚的那个。"""
    ok = vals[cols].notna().all(axis=1)
    eff = ef[cols].max(axis=1)
    return ok, eff


# ---------------------------------------------------------------- 派生指标(季度级)

def _capex(vals: pd.DataFrame, ef: pd.DataFrame) -> tuple[pd.Series, pd.Series]:
    """CapEx:主用 PPE,缺的回落到 ProductiveAssets。两个都没有 → NaN。"""
    c = vals["capex_ppe"].copy()
    e = ef["capex_ppe"].copy()
    m = c.isna() & vals["capex_alt"].notna()
    c[m] = vals["capex_alt"][m]
    e[m] = ef["capex_alt"][m]
    return c, e


def metric_quarterly(symbol: str, name: str) -> tuple[pd.Series, pd.Series]:
    """
    算一个派生指标的季度序列,返回 (值, 生效日)。看不到就是 NaN —— 不猜不补。

    支持:
      fcf_ttm              自由现金流 TTM = OCF_ttm − CapEx_ttm
      sloan_accrual        (NetIncome_ttm − OCF_ttm) / TotalAssets
                           ★ 出处 Hribar & Collins (2002, JAR),不是 Sloan 1996 原版
      fcf_per_share        FCF_ttm / 摊薄股数(FCF Yield 的分子,分母要日频收盘价)
      shares               过完三道闸的摊薄股数
      net_dilution_pct     (本期股数 / 4 期前股数 − 1) × 100
      equity_issuance_ttm  ProceedsFromIssuanceOfCommonStock 的 TTM
      f_score              Piotroski 9 项合计(★ 9 项必须全算得出,否则 NaN)
      f_score_available    9 项是否全齐(1/0)—— 用来把「低分剔除」和「算不出剔除」分开
    """
    vals, ef = quarter_frame(symbol)
    if vals.empty:
        return pd.Series(dtype=float), pd.Series(dtype="datetime64[ns]")

    if name == "fcf_ttm":
        cap, cap_e = _capex(vals, ef)
        ok = vals["ocf"].notna() & cap.notna()
        v = (vals["ocf"] - cap).where(ok)
        return v, pd.concat([ef["ocf"], cap_e], axis=1).max(axis=1)

    if name == "sloan_accrual":
        ok, eff = _need(vals, ef, ["ni", "ocf", "ta"])
        ta = vals["ta"].where(vals["ta"] > 0)
        return ((vals["ni"] - vals["ocf"]) / ta).where(ok), eff

    if name == "shares":
        return vals["shares"], ef["shares"]

    if name == "fcf_per_share":
        fcf, fe = metric_quarterly(symbol, "fcf_ttm")
        sh = vals["shares"].where(vals["shares"] > 0)
        ok = fcf.notna() & sh.notna()
        return (fcf / sh).where(ok), pd.concat([fe, ef["shares"]], axis=1).max(axis=1)

    if name == "equity_issuance_ttm":
        return vals["issue"], ef["issue"]

    if name == "net_dilution_pct":
        sh = vals["shares"]
        base = sh.shift(4)
        ok = sh.notna() & base.notna() & (base > 0)
        return ((sh / base - 1.0) * 100.0).where(ok), ef["shares"]

    if name in ("f_score", "f_score_available"):
        need = ["ni", "ocf", "ta", "ca", "cl", "ltd", "rev", "cor", "shares"]
        v = vals[need]
        ta0 = v["ta"].shift(4)              # ★ Piotroski:用「期初」总资产做分母
        roa = v["ni"] / ta0.where(ta0 > 0)
        cfo = v["ocf"] / ta0.where(ta0 > 0)
        lever = v["ltd"] / v["ta"].where(v["ta"] > 0)
        liquid = v["ca"] / v["cl"].where(v["cl"] > 0)
        margin = (v["rev"] - v["cor"]) / v["rev"].where(v["rev"] > 0)
        turn = v["rev"] / ta0.where(ta0 > 0)

        parts = {
            "1_ROA": roa > 0,
            "2_CFO": cfo > 0,
            "3_dROA": roa > roa.shift(4),
            "4_ACCRUAL": cfo > roa,
            "5_dLEVER": lever < lever.shift(4),
            "6_dLIQUID": liquid > liquid.shift(4),
            "7_EQ_OFFER": v["shares"] <= v["shares"].shift(4),
            "8_dMARGIN": margin > margin.shift(4),
            "9_dTURN": turn > turn.shift(4),
        }
        # ★ 每一项都要「算得出」才算;任一项算不出 → 整个 F-Score 是 NaN(不猜不补)
        avail = (roa.notna() & cfo.notna() & roa.shift(4).notna()
                 & lever.notna() & lever.shift(4).notna()
                 & liquid.notna() & liquid.shift(4).notna()
                 & v["shares"].notna() & v["shares"].shift(4).notna()
                 & margin.notna() & margin.shift(4).notna()
                 & turn.notna() & turn.shift(4).notna())
        if name == "f_score_available":
            return avail.astype(float), ef[need].max(axis=1)
        score = sum(p.astype(float) for p in parts.values())
        return score.where(avail), ef[need].max(axis=1)

    raise KeyError(f"派生指标 {name} 还没实现 —— ★ 没有悄悄返回 NaN。")


# ---------------------------------------------------------------- 日频面板

def _to_daily(v: pd.Series, eff: pd.Series, index: pd.DatetimeIndex) -> pd.Series:
    """
    季度序列 → 日频序列。
    ★ 生效日那天起才看得见(filing_date + 1 个交易日),
    ★ 未公布期间沿用上一期(ffill),★ 第一次公布之前是 NaN。
    """
    out = pd.Series(np.nan, index=index, dtype=float)
    if v.empty:
        return out
    df = pd.DataFrame({"v": v.astype(float), "e": pd.to_datetime(eff)}).dropna(subset=["e"])
    df = df[df["v"].notna()].sort_values("e")
    if df.empty:
        return out
    arr = index.to_numpy()
    for e, val in zip(df["e"].to_numpy(), df["v"].to_numpy()):
        pos = int(np.searchsorted(arr, e, side="left"))
        if pos < len(index):
            out.iloc[pos] = val
    return out.ffill()


@functools.lru_cache(maxsize=64)
def panel(name: str, symbols: tuple[str, ...], index_key: int = 0) -> pd.DataFrame:
    """[日期 × 票] 的派生指标面板。★ 看不到的格子是 NaN,调用方必须当「不合格」。"""
    cal = _cal()
    cols = {}
    for s in symbols:
        try:
            v, e = metric_quarterly(s, name)
        except Exception:
            v, e = pd.Series(dtype=float), pd.Series(dtype="datetime64[ns]")
        cols[s] = _to_daily(v, e, cal)
    return pd.DataFrame(cols, index=cal)


def get(name: str, symbols: list[str]) -> pd.DataFrame:
    return panel(name, tuple(symbols))


# ---------------------------------------------------------------- 自验

def verify_ytd(symbols: list[str] | None = None, metric: str = "OperatingCashFlow",
               k: int = 3) -> str:
    """
    ★★ 坑③ 的自验(任务书要求:挑 3 只票手算一个季度,和 TTM 对量级)。

    做法:对每只票,拿**原始 YTD 记录**自己重算一遍 FY 全年值,
    和引擎差分还原后滚出来的 TTM 对一下;同时给出「如果按季度直接相加」
    会得到什么 —— 看放大几倍。
    """
    syms = symbols or [s for s in sorted(data.load_manifest())
                       if data.load_manifest()[s].fundamentals_path]
    lines = [f"★★ 坑③ YTD 口径自验({metric})—— 挑 {k} 只票手算对账", ""]
    done = 0
    for s in syms:
        recs = _raw(s, metric)
        if not recs:
            continue
        # 找一组完整的 YTD 阶梯(同一个 period_start,4 个 period_end)
        groups: dict[pd.Timestamp, list[dict]] = {}
        for r in recs:
            if r["period_start"] is not None:
                groups.setdefault(r["period_start"], []).append(r)
        pick = None
        for ps, rs in sorted(groups.items()):
            seen: dict[pd.Timestamp, dict] = {}
            for r in rs:
                cur = seen.get(r["period_end"])
                if cur is None or r["filing"] < cur["filing"]:
                    seen[r["period_end"]] = r
            rs2 = [seen[pe] for pe in sorted(seen)]
            if len(rs2) >= 4:
                pick = (ps, rs2[:4])
                break
        if pick is None:
            continue
        ps, rs2 = pick
        ytd = [r["value"] for r in rs2]
        naive = float(sum(ytd))                      # ★ 错法:4 条记录直接相加
        truth = float(ytd[-1])                       # ★ 对法:FY 的 YTD 就是全年
        qs = {o.period_end: o.value for o in quarterly(s, metric)}
        mine = sum(qs.get(r["period_end"], np.nan) for r in rs2)
        lines += [
            f"{s}  财年起 {ps.date()}",
            f"    原始 YTD 四级:" + " / ".join(f"{x/1e6:,.0f}M" for x in ytd),
            f"    ★ 手算全年(= FY 的 YTD)          {truth/1e6:,.0f}M",
            f"    引擎差分还原后四个单季相加         "
            f"{mine/1e6:,.0f}M   {'✅ 一致' if np.isfinite(mine) and abs(mine-truth) <= abs(truth)*1e-6 else '⚠ 不一致'}",
            f"    ★ 如果按季度直接相加(错法)       {naive/1e6:,.0f}M   "
            f"→ ★ 放大 {naive/truth:.2f} 倍" if truth else "",
            "",
        ]
        done += 1
        if done >= k:
            break
    return "\n".join([l for l in lines if l != ""] + [""])


def coverage(symbols: list[str], names: list[str], dates: list[str]) -> pd.DataFrame:
    """几个断面上,各派生指标在池内有多少比例的票算得出来。"""
    rows = []
    for nm in names:
        p = get(nm, symbols)
        row = {"指标": nm}
        for d in dates:
            ts = pd.Timestamp(d)
            sub = p.loc[:ts]
            row[d] = float(sub.iloc[-1].notna().mean()) if len(sub) else float("nan")
        rows.append(row)
    return pd.DataFrame(rows).set_index("指标")


def main() -> int:
    syms = [s for s, m in sorted(data.load_manifest().items()) if m.fundamentals_path]
    print(f"有 fundamentals.json 的票:{len(syms)} 只"
          f"(全池 {len(data.load_manifest())} 只 —— "
          f"★ 其余的票任何基本面闸门都永久判不合格)")
    print()
    print(verify_ytd(k=3))
    print(coverage(syms, ["fcf_ttm", "sloan_accrual", "fcf_per_share",
                          "net_dilution_pct", "f_score", "f_score_available"],
                   ["2018-06-30", "2022-06-30", "2025-06-30"]).to_string(
        float_format=lambda x: f"{x:.1%}"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
