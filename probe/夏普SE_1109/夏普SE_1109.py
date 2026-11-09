# -*- coding: utf-8 -*-
"""
★★★★★ Gemini 清单第 ③ 条收尾 —— 夏普的显著性，★ 把 11-07 那一步「我凑的标准误」换成算得出来的。

★★★ 11-07 第 6 次唤醒留的坑（《111》原话）：
    「★★★ ⚠ 标准误那一步**是我凑的**，原文没读到 → 只当参考」
    ★ 具体凑法（`probe/尺子v2_1107/尺子v2_1107.py:199~200`）：
        se_iid = sqrt((1 + SR_日²/2)/T)          ← ★ 这一步是对的（Lo 2002 的 iid 式）
        se_Lo  = se_iid × (η(q)/√q)              ← ★★★★★ 这一步是凑的

★★★★★ 为什么那一步一定错（★ 两条，都不用读原文就能判）：
  ① **年化因子在 t 值里会自己约掉。** SR_年 = η(q)·SR_日，SE(SR_年) = η(q)·SE(SR_日)
     → t = SR/SE 跟 η 无关。★★ 所以拿 η/√q 去乘标准误，等于把一个**约掉的量**塞进 t 里。
  ② **方向是危险的那一头。** 正自相关 → η < √q → 乘数 < 1 → 标准误变小 → **|t| 变大**。
     ★★★ 即：凑法会**系统性地把显著性往上抬**（规矩㊾ 那一类：改法本身造假信号）。

★★★★★ 算得出来的做法（Lo 2002 非 iid 情形，用 GMM + Newey-West，★ 不需要原文细节）：
    θ = (μ, σ²)，g(θ) = μ/√σ²
    ∇g = ( 1/σ , −μ/(2σ³) )
    h_t = ( r_t − μ , (r_t − μ)² − σ² )          ← ★ 两个矩条件
    Ω̂  = Γ̂₀ + Σ_{j=1..m} (1 − j/(m+1))(Γ̂_j + Γ̂_jᵀ)   ← ★ Bartlett 核，Γ̂_j = (1/T)Σ h_t h_{t−j}ᵀ
    Var(SR̂) = ∇gᵀ Ω̂ ∇g / T  →  SE_HAC = sqrt(...)
    ★★ m=0 时退回 iid 的样本版本（★ 不是 Lo 的解析式，但同阶）。
★ 出处档：**② 行业通行**（GMM + Newey-West 是教科书做法）；
  ★★★ Lo (2002) 原文**仍然没读到** —— 但上面两条都不依赖它，η(q) 那一式仍按原档 ⑤ 标注。

★★★ 这一份不跑回测：① 蒙特卡洛验大小（AR(1) 真夏普=0） ② 仓库现成 126 份日净值上新旧对照。
"""
from __future__ import annotations

import glob
import json
import os
import sys

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
TRADING_DAYS = 252


# ══════════════════════════════════════════════════ 规矩㊼ · 口径头
def 口径头(**kw) -> dict:
    必 = ("全收益或价格", "摩擦档", "窗口", "池子", "标签滞后天")
    头 = {k: kw.get(k, "★未声明") for k in 必}
    头["★★★规矩㊼"] = "★ 开关类默认值当成结论字段来报"
    缺 = [k for k in 必 if 头[k] == "★未声明"]
    if 缺:
        头["★★★口径没声明的项"] = 缺
    return 头


# ══════════════════════════════════════════════════ 自相关 / η(q)
def _rho(x: np.ndarray, kmax: int) -> np.ndarray:
    """★ 样本自相关（分母用全样本离差平方和，和 11-07 那版一致，便于逐数对照）。"""
    T = len(x)
    denom = float((x * x).sum())
    out = np.zeros(kmax, dtype=float)
    if denom <= 0 or kmax < 1:
        return out
    k = int(min(kmax, T - 1))
    ac = np.correlate(x, x, mode="full")[T - 1: T - 1 + k + 1]   # ★ 一次拿全部滞后
    out[:k] = ac[1:k + 1] / denom
    return out


def eta_q(r: np.ndarray, q: int) -> float:
    """★★ Lo (2002) 的**年化**因子 η(q) = q / sqrt(q + 2Σ_{k=1}^{q−1}(q−k)ρ_k)。
    ★ 出处档 ⑤（外部模型说的·待核）—— ★★★ 只用于点估计的年化，**不许进 t 值**。"""
    q = int(min(q, len(r) - 1))
    if q < 2:
        return float("nan")
    x = r - r.mean()
    rho = _rho(x, q - 1)
    s = q + 2.0 * float(sum((q - (k + 1)) * rho[k] for k in range(len(rho))))
    return q / np.sqrt(s) if s > 0 else float("nan")


# ══════════════════════════════════════════════════ ★★★★★ HAC 标准误（本份的正主）
def _nw_lag(T: int) -> int:
    """★ Newey–West (1994) 自动带宽：m = floor(4·(T/100)^(2/9))。★★ 报告里同时给几个固定 m。"""
    return int(np.floor(4.0 * (T / 100.0) ** (2.0 / 9.0)))


def se_夏普_HAC(r: np.ndarray, m: int) -> float:
    """★★★★★ SE(SR_日)，GMM + Bartlett 核，滞后 m（m=0 → 样本 iid 版）。"""
    r = np.asarray(r, dtype=float)
    T = len(r)
    mu = float(r.mean())
    var = float(r.var(ddof=0))
    if not np.isfinite(var) or var <= 0:
        return float("nan")
    sd = np.sqrt(var)
    e = r - mu
    h = np.column_stack([e, e * e - var])                       # ★ 两个矩条件
    G0 = h.T @ h / T
    Om = G0.copy()
    for j in range(1, int(m) + 1):
        if T - j <= 1:
            break
        Gj = h[j:].T @ h[:-j] / T
        w = 1.0 - j / (m + 1.0)
        Om = Om + w * (Gj + Gj.T)
    grad = np.array([1.0 / sd, -mu / (2.0 * sd ** 3)])
    v = float(grad @ Om @ grad)
    if not np.isfinite(v) or v <= 0:
        return float("nan")
    return float(np.sqrt(v / T))


def 夏普三法(r: pd.Series | np.ndarray, q: int = TRADING_DAYS,
           ms: tuple[int, ...] = (0, 21, 63, 252)) -> dict:
    """★★★ 同一条日收益上，三把标准误并排：iid解析式 / 11-07凑法 / HAC(本份)。"""
    r = pd.Series(r).dropna().to_numpy(dtype=float)
    T = len(r)
    if T < 60:
        return {"★算不出": f"只有 {T} 天(<60)"}
    mu, sd = float(r.mean()), float(r.std(ddof=1))
    if not np.isfinite(sd) or sd <= 0:
        return {"★算不出": "日收益标准差为 0"}
    sr_d = mu / sd
    eta = eta_q(r, q)
    qq = int(min(q, T - 1))
    比 = (eta / np.sqrt(qq)) if np.isfinite(eta) else float("nan")

    se_iid = np.sqrt((1.0 + 0.5 * sr_d ** 2) / T)               # ★ Lo iid 解析式
    se_凑 = se_iid * 比 if np.isfinite(比) else float("nan")      # ★★★ 11-07 那一步
    hac = {f"m={m}": se_夏普_HAC(r, m) for m in ms}
    m_auto = _nw_lag(T)
    se_hac_auto = se_夏普_HAC(r, m_auto)

    def _t(se):
        return float(sr_d / se) if (np.isfinite(se) and se > 0) else float("nan")

    return {
        "T天": T,
        "①日夏普": round(sr_d, 6),
        "②朴素年化_乘根252": round(sr_d * np.sqrt(qq), 3),
        "③Lo年化_乘eta": (round(sr_d * eta, 3) if np.isfinite(eta) else None),
        "④eta除根q": (round(float(比), 4) if np.isfinite(比) else None),
        "⑤一阶自相关": round(float(_rho(r - mu, 1)[0]), 4),
        "⑥SE_iid解析": round(float(se_iid), 6),
        "⑦SE_11-07凑法": (round(float(se_凑), 6) if np.isfinite(se_凑) else None),
        "★★★⑧SE_HAC自动m": (round(float(se_hac_auto), 6) if np.isfinite(se_hac_auto) else None),
        "⑨自动m": m_auto,
        "⑩SE_HAC各m": {k: (round(float(v), 6) if np.isfinite(v) else None) for k, v in hac.items()},
        "t_iid": round(_t(se_iid), 3),
        "t_11-07凑法": (round(_t(se_凑), 3) if np.isfinite(se_凑) else None),
        "★★★t_HAC": (round(_t(se_hac_auto), 3) if np.isfinite(se_hac_auto) else None),
        "t_HAC各m": {k: (round(_t(v), 3) if np.isfinite(v) else None) for k, v in hac.items()},
        "★读法": ("★ 凑法比 HAC 的 |t| 大 → 凑法在**抬显著性**；"
                "★★★ 年化因子 η 在 t 里本该约掉，凑法把它塞进了标准误"),
        "★出处档": "② 行业通行（GMM+Newey-West）；★ η(q) 仍是 ⑤ 待核",
    }


# ══════════════════════════════════════════════════ ① 蒙特卡洛 · 验「大小」
def 蒙特卡洛(n: int = 4000, T: int = 2500, rhos=(0.0, 0.05, 0.1, 0.2, 0.3, -0.2),
          seed: int = 20261109) -> dict:
    """★★★★★ AR(1)、**真夏普 = 0**（μ=0）→ 名义 5% 的检验实际拒绝多少次。
    ★ 正确的标准误 → 拒绝率应 ≈ 5%；★★ 偏高 = 造假显著；★★ 偏低 = 过于保守。
    ★★ 生成按「一次 n 条、按时间推进」做（★ 不在 Python 里逐条逐日循环）。"""
    rng = np.random.default_rng(seed)
    out = {}
    for rho in rhos:
        e = rng.standard_normal((n, T)) * 0.01
        X = np.empty((n, T))
        X[:, 0] = e[:, 0] / np.sqrt(max(1e-12, 1 - rho ** 2))
        for i in range(1, T):
            X[:, i] = rho * X[:, i - 1] + e[:, i]
        c = {"iid": 0, "凑法": 0, "HAC自动": 0, "HAC_m21": 0, "HAC_m63": 0}
        bad = 0
        m_auto = _nw_lag(T)
        for j in range(n):
            x = X[j]
            mu, sd = float(x.mean()), float(x.std(ddof=1))
            if sd <= 0:
                bad += 1
                continue
            sr = mu / sd
            se_iid = np.sqrt((1.0 + 0.5 * sr ** 2) / T)
            eta = eta_q(x, TRADING_DAYS)
            比 = eta / np.sqrt(min(TRADING_DAYS, T - 1))
            pairs = (("iid", se_iid), ("凑法", se_iid * 比),
                     ("HAC自动", se_夏普_HAC(x, m_auto)),
                     ("HAC_m21", se_夏普_HAC(x, 21)),
                     ("HAC_m63", se_夏普_HAC(x, 63)))
            for k, se in pairs:
                if np.isfinite(se) and se > 0 and abs(sr / se) > 1.96:
                    c[k] += 1
        mm = max(1, n - bad)
        out[f"rho={rho}"] = {"★名义": "5.0%", "★跑了": mm,
                            **{k: f"{100.0 * v / mm:.1f}%" for k, v in c.items()}}
    out["★读法"] = ("★ 三条读法：① iid 在 rho>0 时就已经偏高（这是清单第③条本来要修的）；"
                  "★★ ② 凑法比 iid **更高** → 它把问题弄反了；"
                  "★★★ ③ HAC 应最接近 5%。")
    return out


# ══════════════════════════════════════════════════ ② 真数据 · 126 份日净值
NAV = os.path.join(ROOT, "probe", "随机同档_1107", "日净值_1107")


def 真数据() -> dict:
    fs = sorted(glob.glob(os.path.join(NAV, "*.csv")))
    行 = []
    for p in fs:
        try:
            d = pd.read_csv(p)
        except Exception as ex:                                  # noqa: BLE001
            行.append({"文件": os.path.basename(p), "★读不了": str(ex)[:80]})
            continue
        if "equity" not in d.columns:
            行.append({"文件": os.path.basename(p), "★读不了": "没有 equity 列"})
            continue
        eq = pd.to_numeric(d["equity"], errors="coerce").dropna()
        r = eq.pct_change().dropna()
        r = r[np.isfinite(r)]
        res = 夏普三法(r)
        res["文件"] = os.path.basename(p)[:-4]
        行.append(res)
    好 = [x for x in 行 if "t_HAC" in str(x.keys()) and x.get("★★★t_HAC") is not None
         and x.get("t_11-07凑法") is not None]
    def _c(key, thr):
        return sum(1 for x in 好 if abs(x[key]) > thr)
    倍 = [abs(x["t_11-07凑法"]) / abs(x["★★★t_HAC"]) for x in 好
         if abs(x["★★★t_HAC"]) > 1e-9]
    return {
        "★口径头": 口径头(
            全收益或价格="★ 这 126 份日净值是 1107 随机同档那一批（价格口径流水）",
            摩擦档="★ 流水自带",
            窗口="★ 见各文件名（A_2004到2014 / B_2015到2025）",
            池子="并池2004",
            标签滞后天="★ 沿用原跑批口径"),
        "★★★这一份是什么": (
            "★★★ **尺子的体检表，不是成绩表** —— ★ 量的是「标准误换成算得出来的那一版之后，"
            "夏普的 t 会挪多少、翻不翻结论」；★★ 这 126 份净值本身不是本周口径的成绩。"),
        "★统计": {
            "读到文件": len(fs), "算得出": len(好), "算不出": len(行) - len(好),
            "★★★|t|>1.96 · 凑法": _c("t_11-07凑法", 1.96),
            "★★★|t|>1.96 · HAC": _c("★★★t_HAC", 1.96),
            "★★★|t|>3 · 凑法": _c("t_11-07凑法", 3.0),
            "★★★|t|>3 · HAC": _c("★★★t_HAC", 3.0),
            "|t|>1.96 · iid": _c("t_iid", 1.96),
            "★★★凑法比HAC的|t|大几倍_中位": (round(float(np.median(倍)), 3) if 倍 else None),
            "凑法比HAC的|t|大几倍_范围": ([round(float(np.min(倍)), 3), round(float(np.max(倍)), 3)]
                                 if 倍 else None),
            "★★★凑法把|t|抬过1.96而HAC过不了的条数": sum(
                1 for x in 好 if abs(x["t_11-07凑法"]) > 1.96 and abs(x["★★★t_HAC"]) <= 1.96),
            "HAC过1.96而凑法过不了的条数": sum(
                1 for x in 好 if abs(x["★★★t_HAC"]) > 1.96 and abs(x["t_11-07凑法"]) <= 1.96),
        },
        "逐条": 行,
    }


def main() -> int:
    报 = {
        "★★★这一份在修什么": (
            "★★★★★ 11-07《111》第③条留的「标准误是我凑的」——"
            " ★ 凑法 = se_iid × η(q)/√q；★★★ η 是**年化**因子，在 t 值里本该约掉。"),
        "① 蒙特卡洛_AR1_真夏普为0": 蒙特卡洛(),
        "② 真数据_126份日净值": 真数据(),
    }
    p = os.path.join(HERE, "夏普SE_报告_1109.json")
    with open(p, "w", encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print("✅ 写出", p)
    print(json.dumps(报["① 蒙特卡洛_AR1_真夏普为0"], ensure_ascii=False, indent=1))
    print(json.dumps(报["② 真数据_126份日净值"]["★统计"], ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
