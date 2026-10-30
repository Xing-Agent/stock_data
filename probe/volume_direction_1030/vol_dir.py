"""
★★★ 成交量方向(进 vs 出)能不能独立判顶底 —— 指标构件库

本文件只放**构件**(指标怎么算、准确率怎么算),不跑批。跑批在 run_probe.py。

════════════════════════════════════════════════════════════════════════════
★★★ 归属声明 —— 每个指标是谁的主张,逐个写明
════════════════════════════════════════════════════════════════════════════
  指标 1(放量日方向性)   ★★ 策略组的主张 + 【XING 填的】实现
  指标 2(收盘位置 × 量)  ★ 行业做法(Money Flow Multiplier / Chaikin)
  指标 3(A/D 线斜率)     ★ 行业做法
  指标 4(OBV 斜率)       ★ 行业做法
  指标 5(effort vs result)★★ 威科夫一脉的说法 + 【XING 填的】可执行版
  指标 6(缩量沉底/高位巨量滞涨)★★【Gemini 的推断】—— 原著没有这条可执行约束

★★★ 没有任何一个指标的阈值出自原著。凡是数字,要么是策略组定的方向,
     要么是【XING 填的】,要么是【Gemini 的推断】。**一个都不许标成原著。**

════════════════════════════════════════════════════════════════════════════
★★ 方向约定(★ 这是**事先定好的**,不是事后挑的)
════════════════════════════════════════════════════════════════════════════
  策略组原话:「顶和底部的很大的区别就是这个量的进出,一个是进,一个是出。」
  → 所以:**score > 0 = 量在进 = 判「底部(阶段一)」**
          **score < 0 = 量在出 = 判「顶部(阶段三)」**
  ★★★ 这个符号是**假设给定的**,不是从数据上拟合的 ——
       所以准确率低于 50% 不等于「反过来用就行」,那是另一个假设,要单独说。
  ★ score == 0 → 算作「算不出」(没有方向),不许往任一边倒。

════════════════════════════════════════════════════════════════════════════
★ 时间尺度:本文件**所有**窗口、回看长度一律是**交易日**。没有自然日。
════════════════════════════════════════════════════════════════════════════
"""
from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# 常量 —— ★ 全是【XING 填的】,逐个标注理由
# ---------------------------------------------------------------------------

#: 量的基准均线长度(**交易日**)。★【XING 填的】:取 50 个交易日 ≈ 10 周,
#  和 状-2 走平斜率的回看长度(10*WEEK=50)对齐,免得两把尺子不一样长。
VOL_BASE = 50

#: 三个邻近窗口(**交易日**)—— ★ 判据是**三点同向**,不是挑最好的那一点
WINDOWS = (10, 20, 30)

#: 三个邻近放量倍数 —— 同上
VOL_MULTS = (1.5, 2.0, 2.5)

#: 「说不清」的占位
NA = np.nan


def _ols_slope(a: np.ndarray, W: int) -> np.ndarray:
    """
    滚动 W 根的最小二乘斜率(每根 bar 的平均增量)。
    ★【XING 填的】用 OLS 而不是「首尾相减 / W」—— 理由写在报告里:
      首尾相减版的 A/D 斜率和指标 2(CMF)在代数上**完全相同**,
      那样指标 3 就是指标 2 的复制件,三点同向会变成假独立。
    """
    n = len(a)
    out = np.full(n, np.nan)
    if n < W:
        return out
    x = np.arange(W, dtype=float)
    x -= x.mean()
    denom = float((x * x).sum())
    s = pd.Series(a)
    # 滚动点积 = sum(x_i * y_i);x 固定,直接用 strided 窗口
    y = np.lib.stride_tricks.sliding_window_view(a, W)
    num = (y * x).sum(axis=1)
    out[W - 1:] = num / denom
    # 窗口里有 NaN → NaN(sliding_window_view 会自然传播)
    _ = s
    return out


def bar_prims(o: np.ndarray, h: np.ndarray, l: np.ndarray,
              c: np.ndarray, v: np.ndarray) -> dict:
    """
    逐 bar 的原料。★ 全部只用当天及更早的数据,**没有未来**。

    ★ 一个必须声明的口径:`h == l`(全天一个价,实测 7,086 根)时
      收盘位置算不出来 → 记 NaN,**不记 0**。
      理由:记 0 等于说「收在中间」,那是一个我们没有依据的判断。
    """
    n = len(c)
    pc = np.full(n, np.nan)
    pc[1:] = c[:-1]
    rng = h - l
    with np.errstate(invalid="ignore", divide="ignore"):
        # Money Flow Multiplier:收在最高 = +1(全进),收在最低 = −1(全出)
        mfm = np.where(rng > 0, ((c - l) - (h - c)) / rng, np.nan)
        cpos = np.where(rng > 0, (c - l) / rng, np.nan)        # 0..1
        ret = np.where(np.isfinite(pc) & (pc > 0), c / pc - 1.0, np.nan)
    vs = pd.Series(v)
    vsma = vs.rolling(VOL_BASE, min_periods=VOL_BASE).mean().to_numpy()
    absret = np.abs(ret)
    med_absret = (pd.Series(absret).rolling(VOL_BASE, min_periods=VOL_BASE)
                  .median().to_numpy())
    return {"pc": pc, "mfm": mfm, "cpos": cpos, "ret": ret, "v": v,
            "vsma": vsma, "absret": absret, "med_absret": med_absret,
            "c": c, "h": h, "l": l}


def _roll_sum(a: np.ndarray, W: int) -> np.ndarray:
    return pd.Series(a).rolling(W, min_periods=W).sum().to_numpy()


def _roll_mean(a: np.ndarray, W: int) -> np.ndarray:
    return pd.Series(a).rolling(W, min_periods=W).mean().to_numpy()


# ===========================================================================
# 六个指标 —— 每个返回一个**有符号分数**数组(>0 判底 / <0 判顶 / NaN 算不出)
# ===========================================================================

def ind1_volume_day_direction(P: dict, W: int, k: float) -> np.ndarray:
    """
    ★★★ 指标 1:放量日的方向性(策略组的主张)

    放量日 = 当日量 > k × 近 50 个交易日均量。
    方向   = 收盘比前收高 → 「进」;低 → 「出」。★ 平收不计入任一边。
    score  = (放量上涨日数 − 放量下跌日数) / (两者之和)   ∈ [−1, +1]
    ★ 窗口内一个放量日都没有 → **算不出**(NaN),不记 0。
    """
    big = P["v"] > k * P["vsma"]
    up = big & (P["c"] > P["pc"])
    dn = big & (P["c"] < P["pc"])
    nu = _roll_sum(up.astype(float), W)
    nd = _roll_sum(dn.astype(float), W)
    tot = nu + nd
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.where(tot > 0, (nu - nd) / tot, np.nan)
    # ★ 均量未成形(前 50 个交易日)→ 算不出
    s = np.where(np.isfinite(P["vsma"]), s, np.nan)
    return s


def ind2_close_position_x_volume(P: dict, W: int) -> np.ndarray:
    """
    ★ 指标 2:收盘在当日区间的位置 × 成交量,窗口累加(行业做法 = Chaikin Money Flow)

    score = Σ(MFM × 量) / Σ(量)   ∈ [−1, +1]
    ★ h==l 的 bar:MFM 算不出 → 该 bar **整根剔掉**(分子分母都不计),
      不是当 0 算。
    """
    mfm, v = P["mfm"], P["v"]
    ok = np.isfinite(mfm) & np.isfinite(v)
    num = _roll_sum(np.where(ok, mfm * v, 0.0), W)
    den = _roll_sum(np.where(ok, v, 0.0), W)
    nok = _roll_sum(ok.astype(float), W)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.where((den > 0) & (nok >= W * 0.8), num / den, np.nan)
    return s


def ind3_ad_line_slope(P: dict, W: int) -> np.ndarray:
    """
    ★ 指标 3:累积派发线(A/D line)的斜率(行业做法)

    A/D = cumsum(MFM × 量);score = OLS 斜率(每交易日) / 近 W 日均量。
    ★ 用 OLS 斜率、不用首尾相减 —— 首尾相减在代数上等于指标 2,会变成复制件。
    """
    mfm, v = P["mfm"], P["v"]
    step = np.where(np.isfinite(mfm) & np.isfinite(v), mfm * v, 0.0)
    ad = np.cumsum(step)
    sl = _ols_slope(ad, W)
    mv = _roll_mean(np.where(np.isfinite(v), v, np.nan), W)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.where(mv > 0, sl / mv, np.nan)
    return s


def ind4_obv_slope(P: dict, W: int) -> np.ndarray:
    """
    ★ 指标 4:OBV 的斜率(行业做法)

    OBV = cumsum(sign(收盘变化) × 量);score = OLS 斜率 / 近 W 日均量。
    ★ 平收日记 0(这是 OBV 的标准定义,不是我们填的)。
    """
    v, c, pc = P["v"], P["c"], P["pc"]
    sgn = np.where(np.isfinite(pc) & np.isfinite(v),
                   np.sign(c - pc) * v, 0.0)
    obv = np.cumsum(sgn)
    sl = _ols_slope(obv, W)
    mv = _roll_mean(np.where(np.isfinite(v), v, np.nan), W)
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.where(mv > 0, sl / mv, np.nan)
    return s


def ind5_effort_vs_result(P: dict, W: int, k: float) -> np.ndarray:
    """
    ★★ 指标 5:effort vs result —— 量大、价格却没走动的日子,按方向分开(威科夫一脉)

    ★ 原著(威科夫)讲的是「有人在接货 / 派货的痕迹」,★★★ **没给数**
      (这一条和 engine/configs/技-11-原著.yaml 的登记一致:原著未给出可执行阈值)。
    ★★ 所以下面这个可执行版是【XING 填的】:
        吸收日 = 当日量 > k × 50 日均量      ← effort 大
                 且 |当日涨跌幅| ≤ 近 50 个交易日的涨跌幅中位数   ← result 小
        方向   = 收盘落在当日区间**上半** → 接货(进);**下半** → 派货(出)
                 ★ 正好 0.5 不计入任一边;h==l 算不出,不计入。
        score  = (接货日数 − 派货日数) / (两者之和)
    ★ 窗口内一个吸收日都没有 → **算不出**。
    """
    big = P["v"] > k * P["vsma"]
    small = P["absret"] <= P["med_absret"]
    absorb = big & small & np.isfinite(P["cpos"])
    upper = absorb & (P["cpos"] > 0.5)
    lower = absorb & (P["cpos"] < 0.5)
    nu = _roll_sum(upper.astype(float), W)
    nd = _roll_sum(lower.astype(float), W)
    tot = nu + nd
    with np.errstate(invalid="ignore", divide="ignore"):
        s = np.where(tot > 0, (nu - nd) / tot, np.nan)
    s = np.where(np.isfinite(P["vsma"]) & np.isfinite(P["med_absret"]), s, np.nan)
    return s


def ind6_gemini_rule(P: dict, W: int, k: float) -> np.ndarray:
    """
    ★★【Gemini 的推断】指标 6:阶段一「缩量沉底 + 异动放量吸筹」/
                                阶段三「高位巨量换手滞涨」

    ★★★ 这不是一个分数,是一条**规则**,所以它只出三种值:
         +1 = 像底部 / −1 = 像顶部 / NaN = 算不出(两边都不像,或两边都像)
    ★ 可执行版是【XING 填的】(Gemini 只给了措辞,没给数):
        缩量沉底    = 窗口内「量 < 均量 / k」的日子 ≥ 一半
        异动放量吸筹 = 窗口内至少有一天「量 > k × 均量」且收涨
        → 两条都满足 = 像底部
        高位巨量换手滞涨 = 窗口内至少有一天「量 > k × 均量」
                          且 |涨跌幅| ≤ 50 日中位数(滞涨)
                          且 收盘在窗口价格区间的上四分之一(高位)
        → 满足 = 像顶部
    """
    v, vsma, c = P["v"], P["vsma"], P["c"]
    quiet = (v < vsma / k).astype(float)
    quiet_frac = _roll_mean(quiet, W)
    big = v > k * vsma
    big_up = (big & (c > P["pc"])).astype(float)
    has_big_up = _roll_sum(big_up, W) >= 1
    hi = pd.Series(c).rolling(W, min_periods=W).max().to_numpy()
    lo = pd.Series(c).rolling(W, min_periods=W).min().to_numpy()
    with np.errstate(invalid="ignore", divide="ignore"):
        pos = np.where(hi > lo, (c - lo) / (hi - lo), np.nan)
    stall = big & (P["absret"] <= P["med_absret"]) & (pos >= 0.75)
    has_stall = _roll_sum(stall.astype(float), W) >= 1
    like_bottom = (quiet_frac >= 0.5) & has_big_up
    like_top = has_stall
    out = np.full(len(c), np.nan)
    out[like_bottom & ~like_top] = 1.0
    out[like_top & ~like_bottom] = -1.0
    out = np.where(np.isfinite(vsma) & np.isfinite(quiet_frac), out, np.nan)
    return out


#: 指标注册表:名字 -> (函数, 参数三点, 参数名, 归属)
#  ★★ 每个指标**三个邻近参数点**,判据是三点同向。
INDICATORS: dict[str, dict] = {
    "1-放量日方向性": {
        "fn": ind1_volume_day_direction, "needs_k": True,
        "variants": [(W, k) for W in WINDOWS for k in VOL_MULTS],
        "attr": "★★ 策略组的主张 + 【XING 填的】实现",
        "plain": "最近这些天,放量的日子里涨的多还是跌的多",
    },
    "2-收盘位置×量": {
        "fn": ind2_close_position_x_volume, "needs_k": False,
        "variants": [(W, None) for W in WINDOWS],
        "attr": "★ 行业做法(Chaikin Money Flow)",
        "plain": "成交量是砸在当天的高位还是低位",
    },
    "3-A/D线斜率": {
        "fn": ind3_ad_line_slope, "needs_k": False,
        "variants": [(W, None) for W in WINDOWS],
        "attr": "★ 行业做法",
        "plain": "资金累计曲线是往上爬还是往下掉",
    },
    "4-OBV斜率": {
        "fn": ind4_obv_slope, "needs_k": False,
        "variants": [(W, None) for W in WINDOWS],
        "attr": "★ 行业做法",
        "plain": "同上,换一种算法",
    },
    "5-effort_vs_result": {
        "fn": ind5_effort_vs_result, "needs_k": True,
        "variants": [(W, k) for W in WINDOWS for k in VOL_MULTS],
        "attr": "★★ 威科夫一脉的说法 + 【XING 填的】可执行版",
        "plain": "量很大但价格没动的日子,收在上半截还是下半截",
    },
    "6-Gemini规则": {
        "fn": ind6_gemini_rule, "needs_k": True,
        "variants": [(W, k) for W in WINDOWS for k in VOL_MULTS],
        "attr": "★★【Gemini 的推断】—— 原著没有这条可执行约束",
        "plain": "缩量沉底+放量吸筹算底;高位放量不涨算顶",
    },
}


def score_panel(P: dict, name: str, W: int, k: float | None) -> np.ndarray:
    spec = INDICATORS[name]
    return spec["fn"](P, W, k) if spec["needs_k"] else spec["fn"](P, W)


# ===========================================================================
# 评分 —— ★★ 混淆矩阵 / 覆盖率 / kappa 分开报,不许混成一个准确率
# ===========================================================================

def evaluate(score: np.ndarray, truth: np.ndarray) -> dict:
    """
    score: 有符号分数(NaN = 算不出);truth: 1 或 3(字符串/数字都接受)
    ★ 判据(事先定好):score > 0 → 判 1(底);score < 0 → 判 3(顶);
      score == 0 或 NaN → **算不出**。
    """
    t = np.asarray([str(x) for x in truth])
    n_all = len(t)
    have = np.isfinite(score) & (score != 0.0)
    pred = np.where(score > 0, "1", "3")

    n_have = int(have.sum())
    out = {
        "格子总数": n_all,
        "★ 算得出的格子": n_have,
        "★★ 覆盖率": round(n_have / max(1, n_all), 4),
        "算不出的格子": n_all - n_have,
    }
    if n_have == 0:
        out["★ 结论"] = "全部算不出,无法评分"
        return out

    th, ph = t[have], pred[have]
    correct = th == ph
    acc = float(correct.mean())
    # 类别先验(= 多数类基线,★ 这才是真正的「瞎猜」上限,不是 50%)
    n1 = int((th == "1").sum())
    n3 = int((th == "3").sum())
    maj = max(n1, n3) / max(1, n1 + n3)
    # 分类召回 → 平衡准确率(抵掉类别不平衡)
    r1 = float((ph[th == "1"] == "1").mean()) if n1 else NA
    r3 = float((ph[th == "3"] == "3").mean()) if n3 else NA
    bal = (r1 + r3) / 2 if n1 and n3 else NA
    # 混淆矩阵
    tp1 = int(((th == "1") & (ph == "1")).sum())
    f13 = int(((th == "1") & (ph == "3")).sum())   # ★★★ 底部判成顶部 → 会在底部卖出
    f31 = int(((th == "3") & (ph == "1")).sum())   # ★★★ 顶部判成底部 → 会在顶部买入
    tp3 = int(((th == "3") & (ph == "3")).sum())
    # Cohen's kappa(判断 vs 真值)
    po = acc
    p1p = (ph == "1").mean()
    p3p = (ph == "3").mean()
    pe = (n1 / len(th)) * p1p + (n3 / len(th)) * p3p
    kappa = (po - pe) / (1 - pe) if (1 - pe) > 1e-12 else NA
    # AUC(与阈值无关 —— 排除「只是阈值选得不好」这个辩解)
    auc = _auc(score[have], th == "1")

    out.update({
        "★★★ 准确率": round(acc, 4),
        "★ 瞎猜(50%)": 0.5,
        "★★ 多数类基线(真正的「瞎猜上限」)": round(maj, 4),
        "★★ 平衡准确率(抵掉类别不平衡)": (round(bal, 4) if bal is not NA else None),
        "底部召回(真底里判对的)": (round(r1, 4) if r1 is not NA else None),
        "顶部召回(真顶里判对的)": (round(r3, 4) if r3 is not NA else None),
        "★★ AUC(与阈值无关)": (round(auc, 4) if auc is not None else None),
        "★★ kappa(判断 vs 真值)": (round(kappa, 4) if kappa is not NA else None),
        "★★★ 混淆矩阵": {
            "真底判底(对)": tp1,
            "★★★ 真底判成顶(会在底部卖出)": f13,
            "★★★ 真顶判成底(会在顶部买入)": f31,
            "真顶判顶(对)": tp3,
            "真底占比": round(n1 / len(th), 4),
            "真顶占比": round(n3 / len(th), 4),
        },
    })
    return out


def _auc(score: np.ndarray, pos: np.ndarray) -> float | None:
    """Mann-Whitney AUC:score 越大越该是「底部」。★ 平手记 0.5。"""
    p = score[pos]
    q = score[~pos]
    if len(p) == 0 or len(q) == 0:
        return None
    allv = np.concatenate([p, q])
    r = pd.Series(allv).rank().to_numpy()
    rp = r[:len(p)].sum()
    return float((rp - len(p) * (len(p) + 1) / 2) / (len(p) * len(q)))


def same_direction(evals: list[dict]) -> dict:
    """
    ★★★ 三点同向判据(已采纳的防作弊规矩):
    一个指标算过关,**三个邻近参数点必须同向** ——
    这里把「同向」定义成:三点的 AUC 全在 0.5 同一侧,且三点准确率都 > 多数类基线。
    ★ 任一点越界 → 判「不同向」→ 这个指标**不算过关**,不许只报最好的那一点。
    """
    aucs = [e.get("★★ AUC(与阈值无关)") for e in evals]
    accs = [e.get("★★★ 准确率") for e in evals]
    majs = [e.get("★★ 多数类基线(真正的「瞎猜上限」)") for e in evals]
    if any(a is None for a in aucs) or any(a is None for a in accs):
        return {"三点同向": False, "原因": "有参数点算不出来"}
    side = [a > 0.5 for a in aucs]
    beat = [a > m for a, m in zip(accs, majs)]
    return {
        "三点 AUC": aucs, "三点准确率": accs, "三点多数类基线": majs,
        "AUC 是否同侧": len(set(side)) == 1,
        "是否三点都打赢多数类基线": all(beat),
        "三点同向": bool(len(set(side)) == 1 and all(beat)),
    }


def two_segment(score: np.ndarray, truth: np.ndarray, when: np.ndarray) -> dict:
    """
    ★★★ 两段一致性检验(必做)。
    ★★ 为什么必做:今天刚踩过 T4 的坑 —— 覆盖 100%、分布最漂亮,
       但两段一致率 0.436 < 偶然的 0.500、kappa −0.13 → 纯噪音。
       ★ 所以「在一段上准」不算证据,必须两段都准、而且方向一致。

    测法(★【XING 填的】):按时间中位数把样本切成前后两段,
      ① 两段各自算 kappa(判断 vs 真值)
      ② 两段的 AUC 必须在 0.5 同一侧
      ③ 判据:**两段 kappa 都 ≥ 0.2** 且 AUC 同侧 → 过;否则判噪音
    """
    have = np.isfinite(score) & (score != 0.0)
    if have.sum() < 100:
        return {"★ 跑不了": "算得出的格子不足 100"}
    w0 = np.asarray(when)
    is_dt = np.issubdtype(w0.dtype, np.datetime64)
    w = w0.astype("datetime64[ns]").astype("int64") if is_dt else w0.astype(float)
    cut = float(np.median(w[have]))
    seg_a = have & (w <= cut)
    seg_b = have & (w > cut)
    out = {"切点": (str(pd.Timestamp(int(cut)).date()) if is_dt else cut)}
    res = {}
    for nm, m in (("前段", seg_a), ("后段", seg_b)):
        if m.sum() < 30:
            res[nm] = {"★ 跑不了": f"样本只有 {int(m.sum())} 个"}
            continue
        res[nm] = evaluate(np.where(m, score, np.nan), truth)
    out["两段"] = res
    ka = res.get("前段", {}).get("★★ kappa(判断 vs 真值)")
    kb = res.get("后段", {}).get("★★ kappa(判断 vs 真值)")
    aa = res.get("前段", {}).get("★★ AUC(与阈值无关)")
    ab = res.get("后段", {}).get("★★ AUC(与阈值无关)")
    ok = (ka is not None and kb is not None and ka >= 0.2 and kb >= 0.2
          and aa is not None and ab is not None
          and ((aa > 0.5) == (ab > 0.5)))
    out["★★★ 前段 kappa"] = ka
    out["★★★ 后段 kappa"] = kb
    out["AUC 同侧"] = (None if (aa is None or ab is None) else (aa > 0.5) == (ab > 0.5))
    out["★★★ 两段一致性判据(两段 kappa 都 ≥0.2 且 AUC 同侧)"] = bool(ok)
    out["★ 判据不过 = 判为噪音,不许往下用"] = (not ok)
    return out
