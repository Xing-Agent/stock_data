"""
★ 四 · 阈值 vs 分布体检 —— 任何写进配置的阈值,跑批时必须打印它在**实际数据分布**
   里的分位。落在 p1 以下或 p99 以上 → 报警「这个阈值几乎不筛掉 / 几乎筛掉全部」。

三秒版:一个阈值到底严不严,不看这个数本身,看它在我们数据里切在哪个位置。
        切在 p99 外面 = 它几乎从不触发,装了等于没装;
        切在 p1 里面 = 它几乎什么都不挡,装了也等于没装。
★ 还有第三种更隐蔽的:阈值那一侧**样本太少**,于是「该不该设」★ 说不出来。

为什么要有这个文件(2026-10-29 真实踩的坑):
  ① 技-11 的「下刺 > 1.5 ATR 该不该禁」——★ 那一档只有 **51 个**样本(占 1.3%),
     60 日均值 +2.42% 比 0.8~1.5 那档**还高**。
     ★★ 当时的结论原样留下:「★ 我们的答案是『说不出来』」。
     ★ 说不出来本身必须是一个**会 FAIL 的状态**,不是一句报告里的脚注。
  ② 状-3 XING 版:实体占比阈值 body_trend = 0.60,
     ★ 而 20 根均值的实测 p90 只有 0.532 → 这个阈值**永远达不到**,
     于是 trend 态只占 0.37% —— 这条判据等于不存在。

★ 四种口径都支持(手上有什么就用什么):
   · 原始样本    check_against_sample()     → 精确分位,p1/p99 规则
   · 分档计数    check_against_buckets()    → 累计分位 + 尾部样本量
   · 分位摘要    check_against_quantiles()  → 只能给上下界,★ 会明说分辨不出 p99
   · 触发率      check_trigger_rate()       → 直接看这个阈值实际触发了百分之几

★ 本文件只读,不改配置、不改跑批逻辑。
"""

from __future__ import annotations

import bisect
import csv
import json
import os
from typing import Sequence

# ────────────────────────────────────────────────────────────────────────
# 阈值的阈值 —— 出处写明
# ────────────────────────────────────────────────────────────────────────

#: FAIL 带。出处:策略组 2026-10-29 原话「阈值落在 p1 以下或 p99 以上 → 报警」。
FAIL_LO, FAIL_HI = 1.0, 99.0

#: WARN 带。出处:自检盘点-1029 §三·乙「若阈值落在实际分布的 p95 之外 → 报警
#  『这个阈值几乎不会被触发』;若落在 p5 之内 → 报警『几乎总会被触发』」。
WARN_LO, WARN_HI = 5.0, 95.0

#: 尾部样本量下限。低于它 → 「该不该设说不出来」,★ 判 FAIL。
#  出处:stats_gate.MIN_N = 100(本仓库自己的样本量下限,九关第六关)。
#  技-11 的 >1.5ATR 档只有 51 个样本,正好落在这条线下面。
MIN_TAIL_N = 100

#: 触发率的 FAIL 带(p1/p99 规则在触发率口径上的等价写法)。
TRIGGER_LO, TRIGGER_HI = 0.01, 0.99


def _verdict(pct: float) -> tuple[str, str]:
    """返回 (级别, 话)。级别 ∈ {FAIL, WARN, OK}。"""
    if pct > FAIL_HI:
        return "FAIL", (f"落在 p{pct:.2f} > p{FAIL_HI:.0f} —— "
                        f"★ 这个阈值几乎不会被触发(只有 {100 - pct:.2f}% 的"
                        f"样本在它那一侧),装了等于没装。")
    if pct < FAIL_LO:
        return "FAIL", (f"落在 p{pct:.2f} < p{FAIL_LO:.0f} —— "
                        f"★ 这个阈值几乎什么都不挡({pct:.2f}% 的样本在它下面),"
                        f"装了也等于没装。")
    if pct > WARN_HI:
        return "WARN", (f"落在 p{pct:.2f}(> p{WARN_HI:.0f})—— "
                        f"只有 {100 - pct:.2f}% 的样本在它那一侧,偏严,"
                        f"★ 要确认这是有意的。")
    if pct < WARN_LO:
        return "WARN", (f"落在 p{pct:.2f}(< p{WARN_LO:.0f})—— "
                        f"几乎总会被触发,★ 要确认这是有意的。")
    return "OK", f"落在 p{pct:.2f},在正常区间内。"


# ────────────────────────────────────────────────────────────────────────
# ① 原始样本
# ────────────────────────────────────────────────────────────────────────

def check_against_sample(name: str, threshold: float,
                         samples: Sequence[float], *,
                         side: str = "above") -> dict:
    """
    side="above":阈值的作用是「取 > threshold 的那一侧」(尾部在上面)。
    side="below":反之。
    """
    xs = sorted(float(x) for x in samples
                if x is not None and x == x)          # x==x 过滤 NaN
    n = len(xs)
    if n == 0:
        return {"项": name, "级别": "FAIL",
                "话": f"[{name}] ★★ FAIL 一个样本都没有 —— 无法体检这个阈值"}
    pct = bisect.bisect_left(xs, threshold) / n * 100
    n_tail = (n - bisect.bisect_left(xs, threshold)) if side == "above" \
        else bisect.bisect_left(xs, threshold)
    level, words = _verdict(pct)

    out = {"项": name, "阈值": threshold, "样本量": n,
           "分位": round(pct, 4), "尾部样本量": n_tail,
           "p1": xs[max(0, int(n * 0.01) - 1)],
           "p50": xs[n // 2], "p99": xs[min(n - 1, int(n * 0.99))],
           "级别": level}

    if n_tail < MIN_TAIL_N:
        out["级别"] = "FAIL"
        out["话"] = (
            f"[{name}] ★★ FAIL 这个阈值**该不该设说不出来**:"
            f"阈值 {threshold} {words} "
            f"★ 更要紧的是它那一侧只有 **{n_tail} 个**样本"
            f"(< {MIN_TAIL_N} = 本仓库自己的样本量下限 stats_gate.MIN_N)—— "
            f"★ 样本不足到无法判断「该不该设」,"
            f"★ 不许用它那一侧的均值去支持任何结论。"
            f"(这正是技-11 >1.5ATR 那 51 个样本的处境:"
            f"均值比上一档还高,而我们的答案只能是「说不出来」。)")
        return out

    out["话"] = (f"[{name}] {'★★ FAIL' if level == 'FAIL' else '★ WARN' if level == 'WARN' else 'OK'} "
                 f"阈值 {threshold} {words} "
                 f"(n={n},p1={out['p1']:.4g} / p50={out['p50']:.4g} / "
                 f"p99={out['p99']:.4g},尾部 {n_tail} 个样本)")
    return out


# ────────────────────────────────────────────────────────────────────────
# ② 分档计数
# ────────────────────────────────────────────────────────────────────────

def check_against_buckets(name: str, threshold_label: str,
                          buckets: Sequence[tuple[str, int]]) -> dict:
    """
    buckets:[(档名, 个数), ...],★ 按从小到大的顺序给。
    threshold_label:阈值切在哪一档的**下沿** —— 即这一档及以后都在阈值那一侧。
    """
    labels = [b[0] for b in buckets]
    counts = [int(b[1]) for b in buckets]
    total = sum(counts)
    if threshold_label not in labels:
        return {"项": name, "级别": "FAIL",
                "话": f"[{name}] ★★ FAIL 分档里找不到 `{threshold_label}`,"
                      f"现有档:{labels}"}
    i = labels.index(threshold_label)
    below = sum(counts[:i])
    n_tail = sum(counts[i:])
    pct = below / total * 100 if total else 0.0
    level, words = _verdict(pct)
    out = {"项": name, "阈值档": threshold_label, "母集": total,
           "分位": round(pct, 4), "尾部样本量": n_tail, "级别": level}
    if n_tail < MIN_TAIL_N:
        out["级别"] = "FAIL"
        out["话"] = (
            f"[{name}] ★★ FAIL 这个阈值**该不该设说不出来**:"
            f"`{threshold_label}` 这一档及以上只有 **{n_tail} 个**样本"
            f"(占母集 {n_tail / total:.2%},母集 {total})"
            f"—— < {MIN_TAIL_N}(stats_gate.MIN_N)。"
            f"★ 阈值切在 p{pct:.2f}。{words} "
            f"★ 这一档的均值无论多好看都不能用来支持「该禁 / 不该禁」。")
        return out
    out["话"] = f"[{name}] 阈值档 `{threshold_label}` {words}(尾部 {n_tail} 个)"
    return out


# ────────────────────────────────────────────────────────────────────────
# ③ 只有分位摘要(p10 / median / p90)
# ────────────────────────────────────────────────────────────────────────

def check_against_quantiles(name: str, threshold: float,
                            quantiles: dict) -> dict:
    """
    手上只有 p10 / median / p90 这种摘要时的降级口径。
    ★ 它**不能**分辨 p99,所以这里会明说分辨不出来 —— 不许假装精确。
    """
    pairs = []
    for k, v in quantiles.items():
        kk = str(k).lower()
        if not isinstance(v, (int, float)):
            continue
        if kk in ("median", "p50", "中位"):
            pairs.append((50.0, float(v)))
        elif kk.startswith("p") and kk[1:].isdigit():
            pairs.append((float(kk[1:]), float(v)))
    pairs.sort()
    if not pairs:
        return {"项": name, "级别": "FAIL",
                "话": f"[{name}] ★★ FAIL 摘要里一个分位都没有"}
    lo = [p for p, v in pairs if v <= threshold]
    hi = [p for p, v in pairs if v > threshold]
    top_p = max(pairs)[0]
    if not hi:                                       # 阈值在最高那个分位之上
        level = "FAIL" if top_p >= WARN_HI else "WARN"
        words = (f"★ 阈值 {threshold} 高于手上最高的分位 p{top_p:.0f}"
                 f"(= {max(pairs)[1]:.4g})→ 它至少落在 p{top_p:.0f} 以上,"
                 f"★ 说明它几乎永远达不到。"
                 f"★ 但只有 p10/中位/p{top_p:.0f} 的摘要**分辨不出是否超 p{FAIL_HI:.0f}** "
                 f"—— 要判死必须拿原始样本重算。")
        return {"项": name, "阈值": threshold, "级别": level,
                "分位下界": top_p, "话": f"[{name}] {'★★ FAIL' if level == 'FAIL' else '★ WARN'} {words}"}
    lo_p = max(lo) if lo else 0.0
    hi_p = min(hi)
    return {"项": name, "阈值": threshold, "级别": "OK",
            "分位区间": (lo_p, hi_p),
            "话": f"[{name}] 阈值 {threshold} 落在 p{lo_p:.0f} ~ p{hi_p:.0f} 之间,"
                  f"★ 摘要口径,精度到此为止。"}


# ────────────────────────────────────────────────────────────────────────
# ④ 触发率
# ────────────────────────────────────────────────────────────────────────

def check_trigger_rate(name: str, rate: float, *, n: int | None = None) -> dict:
    """阈值实际触发了百分之几。这是 p1/p99 规则在触发率口径上的等价写法。"""
    if rate < TRIGGER_LO:
        return {"项": name, "触发率": rate, "级别": "FAIL",
                "话": f"[{name}] ★★ FAIL 这个阈值实际只触发了 {rate:.2%}"
                      f"(< {TRIGGER_LO:.0%})—— ★ 它几乎永远达不到,"
                      f"这条判据等于不存在。"
                      + (f"(n={n})" if n else "")}
    if rate > TRIGGER_HI:
        return {"项": name, "触发率": rate, "级别": "FAIL",
                "话": f"[{name}] ★★ FAIL 这个阈值触发了 {rate:.2%}"
                      f"(> {TRIGGER_HI:.0%})—— ★ 它几乎什么都不挡。"}
    return {"项": name, "触发率": rate, "级别": "OK",
            "话": f"[{name}] 触发率 {rate:.2%},在正常区间内。"}


def problems(results: Sequence[dict]) -> list[str]:
    """把一批体检结果里 FAIL 的挑出来。"""
    return [r["话"] for r in results if r.get("级别") == "FAIL"]


# ────────────────────────────────────────────────────────────────────────
# 五 · 自测 —— ★ 跑在仓库里现成的真实配置 / 流水 / 产物上
# ────────────────────────────────────────────────────────────────────────

_ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _ledger_col(rel: str, col: str) -> list[float]:
    with open(os.path.join(_ENGINE, rel), encoding="utf-8") as fh:
        return [float(r[col]) for r in csv.DictReader(fh)
                if r.get(col) not in (None, "")]


def _selftest() -> None:
    # ── 真实案例 ①:技-11 的「>1.5 ATR 该不该禁」= 51 个样本 ──────────────
    #   真实产物:results_1029_批五实测.json → 第一件③_下刺深度分档 → 母集A
    with open(os.path.join(_ENGINE, "results_1029_批五实测.json"),
              encoding="utf-8") as fh:
        d5 = json.load(fh)
    blk = d5["第一件③_下刺深度分档"]
    mu = next(v for k, v in blk.items() if str(k).startswith("母集A"))
    buckets = [(b["深度档"], b["个数"]) for b in mu["逐档"]]
    r1 = check_against_buckets("技-11 下刺深度阈值 1.5ATR",
                               buckets[-1][0], buckets)
    assert r1["级别"] == "FAIL", r1
    assert r1["尾部样本量"] == 51, r1
    print(f"  ① {r1['话'][:150]} …")

    # ── 真实案例 ②:技-11-XING.yaml 的 profit_target_r = 2.0 ─────────────
    #   对照真实流水 ledgers_1029_技术派六条三版/技-11_XING版…csv 的 r_multiple_net
    rs = _ledger_col("ledgers_1029_技术派六条三版/"
                     "技-11_XING版(跌破20日低点再收回).csv", "r_multiple_net")
    r2 = check_against_sample("技-11-XING.yaml exit.params.profit_target_r",
                              2.0, rs)
    assert r2["级别"] == "FAIL", r2
    assert r2["尾部样本量"] < MIN_TAIL_N, r2
    print(f"  ② {r2['话'][:150]} …")

    # ── 真实案例 ③:liquidity_sweep.yaml 的 profit_target_r = 2.0 ────────
    rs3 = _ledger_col("ledgers_1029_新基准线/"
                      "流派三_微观结构流动性猎杀与均值回归.csv", "r_multiple_net")
    r3 = check_against_sample("liquidity_sweep.yaml exit.params.profit_target_r",
                              2.0, rs3)
    assert r3["级别"] == "FAIL", r3
    print(f"  ③ {r3['话'][:150]} …")

    # ── 真实案例 ④:状-3 XING 版 body_trend = 0.60 vs 实测 raw_body ──────
    with open(os.path.join(_ENGINE, "results_1029_状态轴三版.json"),
              encoding="utf-8") as fh:
        dz = json.load(fh)
    x3 = dz["状-3"]["XING版"]
    r4 = check_against_quantiles("状-3.XING版 spec.body_trend",
                                 x3["spec"]["body_trend"], x3["raw_body"])
    assert r4["级别"] in ("FAIL", "WARN"), r4
    print(f"  ④ {r4['话'][:170]} …")
    #   ★ 同一条用触发率口径一查就判死:trend 态只占 0.37%
    r5 = check_trigger_rate("状-3.XING版 trend 态触发率",
                            x3["state_share"]["trend"])
    assert r5["级别"] == "FAIL", r5
    print(f"  ⑤ {r5['话'][:140]} …")

    # ── 不该误伤:行业版 body_trend = 0.50 的触发率 10.78% ───────────────
    ok = check_trigger_rate("状-3.行业版 trend 态触发率",
                            dz["状-3"]["行业版"]["state_share"]["trend"])
    assert ok["级别"] == "OK", ok
    #   不该误伤:样本充足、分位居中
    ok2 = check_against_sample("技-12 r_multiple_net @ 0",
                               0.0, _ledger_col(
                                   "ledgers_1029_新基准线/技-12_康纳斯均值回归.csv",
                                   "r_multiple_net"))
    assert ok2["级别"] == "OK", ok2
    print(f"  ⑥ 不误伤:行业版触发率 10.78% → OK;技-12 的 0 线 "
          f"p{ok2['分位']:.1f}、尾部 {ok2['尾部样本量']} 个 → OK")

    bad = problems([r1, r2, r3, r5, ok, ok2])
    assert len(bad) == 4, bad
    print("checks/threshold_vs_distribution 自测通过 —— "
          "★ 三条真实阈值(技-11 1.5ATR / 技-11-XING 2.0R / 流派三 2.0R)"
          "在真实数据上直接 FAIL;"
          "★ 状-3 的 0.60 因为手上只有 p10/中位/p90 的摘要,摘要口径只能判 WARN "
          "并明说「分辨不出是否超 p99」—— 换触发率口径(0.37%)立刻 FAIL。")


if __name__ == "__main__":
    _selftest()
