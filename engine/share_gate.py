"""
股数闸(2026-10-28 新增)—— 给 WeightedAverageDilutedShares 这条序列用。

================================ 三秒版 ================================
股数这条序列**不能直接拿来算稀释率**,它有三个坑叠在一起。这个文件
把三个坑按顺序过一遍,★ 每一步都只做「能判准的」,判不准的一律不改、
原样报出来让人看见。

  坑一 ★★ 单位不一致(本轮新发现,比拆股严重得多)
       同一只票、同一个字段、unit 都写着 "shares",实际值却混着
       「股 / 千股 / 百万股」三种口径。
       例:CHD 最小值 246(百万股)、最大值 2.676 亿(股)—— 差 100 万倍。
           CAL 34,407(千股) vs 4,266 万(股)—— 差 1000 倍。
       ★ 不修这一条,稀释率会出现 +98,000,000% 这种数,后面什么都不用谈。

  坑二 ★ 同一次申报里混着多个区间
       一份 10-Q 里同时有「本季 3 个月」和「年初至今 9 个月」两个
       加权平均股数。按 accepted_at 排序会把这两个值前后相邻地排在一起,
       算出来的「环比变化」其实是在比两个不同长度的区间。
       ★ 做法:只取**季度区间**(period_start→period_end 约 3 个月)的记录,
         同一个 period_end 只留一条。

  坑三 ★ 拆股(原来说的那个)
       摊薄股数是如实申报的、不跨期调整,一次 1:5 拆股会在
       「股本变化率」上表现成 +400% 的"稀释",直接触发流派三⑥的清仓。
       engine/split_gate.py 已经在最底层对**价格**做了这件事,
       ★ 股数序列一直没走同一道闸 —— 这个文件补上。

★ 为什么拆股不能一刀切地修:
  跳变的原因有三种 —— ① 拆股/反向拆股(记账口径变了,★ 必须修)
                    ② 真实的大额增发(★ 绝对不能修,修了就把真事件抹掉)
                    ③ 并购换股(判不准)
  所以只修「实测倍数贴近常见拆股比例」的那一类,★ 判不准的一律不修,
  并单独报出来。★ 和价格那道闸的态度一致:宁可让它留在数据里被看见,
  也不要悄悄改掉一个真实的增发。

★ PIT 没有被破坏:每条记录仍然带着自己的 accepted_at,
  「算今天只许用今天及以前的数据」这一条照旧成立。

跑法:python -m engine.share_gate          # 全池扫一遍,打印清单
=========================================================================
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd

from . import data

METRIC = "WeightedAverageDilutedShares"

# ---- 坑二:季度区间的判定(自然日)。10-Q 的季度一般 85~98 天。
QUARTER_MIN_DAYS = 60
QUARTER_MAX_DAYS = 110

# ---- 坑三:相邻两期跳变超出这个范围才算「可疑」(和审计报告口径一致)
JUMP_HI = 1.40
JUMP_LO = 0.72

# 常见拆股 / 合股比例
COMMON_RATIOS: tuple[float, ...] = (
    1.5, 2.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0, 10.0, 20.0, 30.0, 50.0, 100.0,
)
# 实测倍数和理论拆股比例的相对容差。
# ★ 定成 0.03 的理由(★ 这是数据清洗口径,不是策略参数,不受「不许网格搜索」管,
#   但照样把判断依据写出来):真拆股在加权平均股数上会落得**非常准**
#   (实测 TSLA 3.003x · WMT 2.991x · FAST 2.005x · CSGP 10.010x,
#    基本都在 ±1% 以内);而「倍数贴得松」的那一批点名核过,
#   全是**并购换股 / 大额增发**(KDP 7.585x = Keurig 并购 Dr Pepper、
#   FIS 1.602x = 收购 Worldpay)—— 那是真实的股本扩张,★ 不能修。
#   容差从 0.08 收到 0.03,正好把这两类分开。
#
# ★★ 残留的已知局限(必须讲清楚,不许装作解决了):
#   并购换股如果**恰好**换出一个接近整数的倍数,这里仍然会误判成拆股。
#   ★ 已点名核出一例:KHC 2015-09-27 的 3.005x 是 2015 年 7 月
#     Kraft 与 Heinz 合并,★ 不是拆股。
#   ★ 要彻底分开,需要一份真正的公司行动(corporate action)流水 ——
#     仓库里没有。★ 所以:流派三⑥的清仓规则要上生产,必须先补这份数据;
#     ★ 在那之前这道闸只能算「把最脏的那一层擦掉」,不能算干净。
TOLERANCE = 0.03


# =========================================================== 坑一 单位闸

def _scale_exponent(v: float, ref: float) -> int:
    """v 相对基准 ref 差了几个数量级(只认 0 / ±3 / ±6,其余返回 0)。"""
    if v <= 0 or ref <= 0:
        return 0
    d = math.log10(v / ref)
    for e in (6, 3, -3, -6):
        if abs(d - e) < 0.7:          # 0.7 个数量级的容差:千倍和百万倍分得开
            return e
    return 0


def _unit_normalize(pts: list[tuple[pd.Timestamp, float, pd.Timestamp, pd.Timestamp]]):
    """
    把混着「股 / 千股 / 百万股」的值统一到**出现次数最多的那个量级**上。

    基准取「所有值的对数中位数」所在的量级 —— 用中位数而不是众数,
    是因为中位数对少数极端值不敏感,而这里极端值正是我们要修的东西。
    返回 (统一后的点, 改了几条)。
    """
    if len(pts) < 3:
        return pts, 0
    logs = sorted(math.log10(p[1]) for p in pts if p[1] > 0)
    if not logs:
        return pts, 0
    ref = 10 ** logs[len(logs) // 2]
    out, n_fixed = [], 0
    for ts, v, ps, pe in pts:
        e = _scale_exponent(v, ref)
        if e:
            v = v / (10 ** e)
            n_fixed += 1
        out.append((ts, v, ps, pe))
    return out, n_fixed


# =========================================================== 取数 + 坑二

@dataclass(frozen=True)
class SharePoint:
    accepted_at: pd.Timestamp     # 什么时候能看到(PIT 用这个)
    period_end: pd.Timestamp      # 这笔数说的是哪一期
    shares: float


def _raw_points(symbol: str) -> list[tuple[pd.Timestamp, float, pd.Timestamp, pd.Timestamp]]:
    """从原始 json 取 (accepted_at, 值, period_start, period_end)。"""
    out = []
    for r in (data.load_fundamentals(symbol).get(METRIC) or []):
        ts = r.get("accepted_at") or r.get("filed_at")
        ps, pe, val = r.get("period_start"), r.get("period_end"), r.get("value")
        if not ts or not ps or not pe or val in (None, ""):
            continue
        try:
            out.append((pd.Timestamp(ts).tz_localize(None), float(val),
                        pd.Timestamp(ps), pd.Timestamp(pe)))
        except (ValueError, TypeError):
            continue
    return out


def quarterly_points(symbol: str) -> list[SharePoint]:
    """
    过完坑一(单位)+ 坑二(区间)之后的季度股数序列,按 period_end 排好。

    同一个 period_end 有多条时,★ 取 accepted_at 最早的那一条 ——
    就是「首发版本」,不用后来的重述数据(和 analyze 那边的 PIT 口径一致)。
    """
    pts, _ = _unit_normalize(_raw_points(symbol))
    best: dict[pd.Timestamp, tuple[pd.Timestamp, float]] = {}
    for ts, v, ps, pe in pts:
        days = (pe - ps).days
        if not (QUARTER_MIN_DAYS <= days <= QUARTER_MAX_DAYS):
            continue                       # ★ 只要季度区间,YTD 的不要
        cur = best.get(pe)
        if cur is None or ts < cur[0]:
            best[pe] = (ts, v)
    return [SharePoint(ts, pe, v) for pe, (ts, v) in sorted(best.items())]


# =========================================================== 坑三 拆股闸

@dataclass(frozen=True)
class ShareJump:
    symbol: str
    period_end: pd.Timestamp
    ratio: float                  # 实测倍数 = 本期 / 上期
    matched: float | None         # 贴近的拆股比例(None = 判不准)
    action: str                   # "ratio_fix" / "leave_as_is"
    note: str = ""

    @property
    def is_fixed(self) -> bool:
        return self.action == "ratio_fix"


def _match_ratio(r: float) -> float | None:
    for c in COMMON_RATIOS:
        for cand in (c, 1.0 / c):          # 拆股(变大)/ 合股(变小)
            if abs(r - cand) <= TOLERANCE * cand:
                return cand
    return None


def scan(symbol: str) -> list[ShareJump]:
    """扫一只票的季度股数序列,找出可疑跳变并判定修/不修。"""
    pts = quarterly_points(symbol)
    out: list[ShareJump] = []
    for i in range(1, len(pts)):
        prev, cur = pts[i - 1].shares, pts[i].shares
        if prev <= 0 or cur <= 0:
            continue
        r = cur / prev
        if JUMP_LO <= r <= JUMP_HI:
            continue
        m = _match_ratio(r)
        if m is None:
            out.append(ShareJump(
                symbol, pts[i].period_end, r, None, "leave_as_is",
                "贴不近任何常见拆股比例 —— ★ 判不准,★ 不修"
                "(更可能是真实的大额增发或并购换股,修了会把真事件抹掉)"))
        else:
            out.append(ShareJump(
                symbol, pts[i].period_end, r, m, "ratio_fix",
                f"实测 {r:.3f}x 贴近 {m:g}x,按拆股处理:"
                f"把这一期之前的历史股数整体乘 {m:g} 接回去"))
    return out


def adjusted_points(symbol: str) -> list[SharePoint]:
    """
    过完三道闸之后的股数序列。

    拆股的做法和价格那道闸一致:把**老数据折算到新口径**上,
    而不是去改新数据。
    """
    pts = quarterly_points(symbol)
    fixes = {j.period_end: j.matched for j in scan(symbol) if j.is_fixed and j.matched}
    if not fixes or len(pts) < 2:
        return pts
    factor, out = 1.0, []
    for p in reversed(pts):
        if p.period_end in fixes:
            out.append(p)                           # 跳变当期本身不动
            factor *= float(fixes[p.period_end])    # 它之前的全部往上折算
            continue
        out.append(SharePoint(p.accepted_at, p.period_end, p.shares * factor))
    out.reverse()
    return out


def dilution_pct(symbol: str, asof: pd.Timestamp, lookback_periods: int = 4
                 ) -> float | None:
    """
    ★ 过完三道闸之后的净稀释率(%),给流派三⑥的清仓规则用。

    = (当期股数 / 4 期之前的股数 − 1) × 100
    ★ PIT:只用 accepted_at ≤ asof 的记录。看不到足够历史就返回 None,不猜不补。
    """
    pts = [p for p in adjusted_points(symbol) if p.accepted_at <= asof]
    if len(pts) <= lookback_periods:
        return None
    cur, base = pts[-1].shares, pts[-1 - lookback_periods].shares
    if base <= 0:
        return None
    return (cur / base - 1.0) * 100.0


# =========================================================== 全池

def scan_all(symbols: list[str] | None = None) -> dict:
    syms = symbols or sorted(data.load_manifest())
    rows, unit_fixed = [], []
    for s in syms:
        raw = _raw_points(s)
        _, nfix = _unit_normalize(raw)
        if nfix:
            unit_fixed.append((s, nfix, len(raw)))
        rows.extend(scan(s))
    fixed = [j for j in rows if j.is_fixed]
    left = [j for j in rows if not j.is_fixed]
    return {
        "扫过的票数": len(syms),
        "坑一_单位不一致的票数": len(unit_fixed),
        "坑一_单位不一致明细": unit_fixed,
        "坑三_有可疑跳变的票数": len({j.symbol for j in rows}),
        "坑三_跳变总数": len(rows),
        "坑三_判为拆股已修": len(fixed),
        "坑三_判不准未修": len(left),
        "坑三_已修的票": sorted({j.symbol for j in fixed}),
        "坑三_未修的票": sorted({j.symbol for j in left}),
        "逐条": rows,
    }


def summary(symbols: list[str] | None = None) -> str:
    r = scan_all(symbols)
    n = max(1, r["扫过的票数"])
    out = [
        f"股数闸({METRIC})—— 扫过 {r['扫过的票数']} 只",
        "",
        f"★★ 坑一 单位不一致:{r['坑一_单位不一致的票数']} 只"
        f"({r['坑一_单位不一致的票数'] / n:.1%})的记录混着股/千股/百万股,已统一量级",
        f"★  坑二 区间混用:已只取季度区间(约 3 个月)、同期只留首发版本",
        f"★  坑三 拆股跳变:{r['坑三_有可疑跳变的票数']} 只"
        f"({r['坑三_有可疑跳变的票数'] / n:.1%})共 {r['坑三_跳变总数']} 处 —— "
        f"判为拆股已修 {r['坑三_判为拆股已修']} 处,"
        f"★ 判不准未修 {r['坑三_判不准未修']} 处",
        "",
        "已按拆股修正的:",
    ]
    for j in r["逐条"]:
        if j.is_fixed:
            out.append(f"    {j.symbol:6s} {j.period_end.date()}  "
                       f"{j.ratio:9.3f}x -> {j.matched:g}x")
    out.append("")
    out.append("★ 判不准、原样留着的(可能是真实增发 / 并购换股):")
    for j in r["逐条"]:
        if not j.is_fixed:
            out.append(f"    {j.symbol:6s} {j.period_end.date()}  {j.ratio:9.3f}x")
    return "\n".join(out)


if __name__ == "__main__":
    print(summary())
