"""
只数个数:道氏摆动点(状-1)判震荡 vs ADX(Wilder 1978)判震荡 —— SPY 大盘。

三秒版:这个脚本只回答「哪些交易日被判成震荡」,然后数个数。
★ 不碰收益、不跑策略、不算 R。★ engine/ 一个字节没改,只 import。

跑法:python3 probe/chop_compare_1104/chop_compare_1104.py
"""

from __future__ import annotations

import json
import os
import sys

import numpy as np
import pandas as pd

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if REPO not in sys.path:
    sys.path.insert(0, REPO)

from engine import data                               # noqa: E402
from engine.run_a0_states import zigzag_pivots        # noqa: E402

OUT_JSON = os.path.join(os.path.dirname(os.path.abspath(__file__)), "原始数字-1104.json")

SYMBOL = "SPY"
K_GRID = (2.5, 3.0, 3.5)
WICK_GRID = (True, False)

# ★ 窗口一:engine/data.py 的 PERF_START / PERF_END
W_PERF = (data.PERF_START, data.PERF_END)
# ★ 窗口二:④ 要复算 28.53% 的那条索引
W_28 = ("2014-01-02", "2025-12-31")


# ---------------------------------------------------------------------------
# ATR(14) —— ★ 逐字照抄 probe/regime_install_1030/regime_vectors_1030.py 的算法
#   (rolling(14).mean() 的简单均值,不是 Wilder 平滑)
#   ★ 留痕:engine/run_a0_states.base_of() 用的是 matrices._wilder,口径不同。
#     本轮 SPY 上的 状-1 沿用 regime_vectors 那一版,因为 28.53% 是它出的。
# ---------------------------------------------------------------------------
def atr14_regime_style(hi, lo, cl):
    tr = np.maximum.reduce([
        hi[1:] - lo[1:],
        np.abs(hi[1:] - cl[:-1]),
        np.abs(lo[1:] - cl[:-1]),
    ])
    atr = np.full(len(cl), np.nan)
    atr[1:] = pd.Series(tr).rolling(14, min_periods=14).mean().to_numpy()
    return atr


# ---------------------------------------------------------------------------
# 道氏三态 —— ★ 逐字照抄 regime_vectors_1030.dow_arrangement 的判据
#   上涨 = H1>H2 且 L1>L2 · 下跌 = H1<H2 且 L1<L2 · 震荡 = 其余
#   摆动点不足 4 个 = 预热 · 最后 shift(1)
# ---------------------------------------------------------------------------
def dow_states(px: pd.DataFrame, k: float, use_wick: bool):
    hi = px["high"].to_numpy(float)
    lo = px["low"].to_numpy(float)
    cl = px["close"].to_numpy(float)
    atr = atr14_regime_style(hi, lo, cl)
    piv = zigzag_pivots(hi, lo, cl, atr, k=k, use_wick=use_wick)

    # ★★ 自检:摆动点数不许是 0(这就是 023fbbf 修掉的静默空的形状)
    if not piv:
        raise RuntimeError(
            f"★★★ 自检失败:SPY / k={k} / use_wick={use_wick} 一个摆动点都没有 —— "
            f"停下来查,不许当成「震荡」往下跑。")

    out = np.full(len(cl), "预热", dtype=object)
    highs: list[float] = []
    lows: list[float] = []
    p = 0
    for i in range(len(cl)):
        while p < len(piv) and piv[p][0] <= i:
            _idx, kind, val = piv[p]
            (highs if kind == "H" else lows).append(float(val))
            p += 1
        if len(highs) >= 2 and len(lows) >= 2:
            up = highs[-1] > highs[-2] and lows[-1] > lows[-2]
            dn = highs[-1] < highs[-2] and lows[-1] < lows[-2]
            out[i] = "上涨" if up else ("下跌" if dn else "震荡")
    s = pd.Series(out, index=px.index).shift(1).fillna("预热")
    return s, len(piv)


# ---------------------------------------------------------------------------
# ADX —— Wilder 1978《New Concepts in Technical Trading Systems》标准递推
#   ★ 一行代码都不是从别处抄的,本轮新写。
#   步骤:+DM/−DM → Wilder 平滑(首值取 n 项和,之后 prev - prev/n + new)
#         → +DI = 100*sm(+DM)/sm(TR) · −DI 同理
#         → DX = 100*|+DI − −DI|/(+DI + −DI)
#         → ADX = DX 的 Wilder 平滑(首值取前 n 个 DX 的算术平均)
# ---------------------------------------------------------------------------
def adx_wilder(px: pd.DataFrame, n: int = 14):
    hi = px["high"].to_numpy(float)
    lo = px["low"].to_numpy(float)
    cl = px["close"].to_numpy(float)
    m = len(cl)
    tr = np.full(m, np.nan)
    pdm = np.full(m, np.nan)
    ndm = np.full(m, np.nan)
    for i in range(1, m):
        up_move = hi[i] - hi[i - 1]
        dn_move = lo[i - 1] - lo[i]
        pdm[i] = up_move if (up_move > dn_move and up_move > 0) else 0.0
        ndm[i] = dn_move if (dn_move > up_move and dn_move > 0) else 0.0
        tr[i] = max(hi[i] - lo[i], abs(hi[i] - cl[i - 1]), abs(lo[i] - cl[i - 1]))

    def wilder_sum(x):
        s = np.full(m, np.nan)
        # 首值 = 第 1..n 根的和(索引 1..n → 落在 i=n)
        if m <= n:
            return s
        s[n] = np.nansum(x[1:n + 1])
        for i in range(n + 1, m):
            s[i] = s[i - 1] - s[i - 1] / n + x[i]
        return s

    str_ = wilder_sum(tr)
    spdm = wilder_sum(pdm)
    sndm = wilder_sum(ndm)
    with np.errstate(invalid="ignore", divide="ignore"):
        pdi = 100.0 * spdm / str_
        ndi = 100.0 * sndm / str_
        dx = 100.0 * np.abs(pdi - ndi) / (pdi + ndi)
    adx = np.full(m, np.nan)
    # ADX 首值 = 前 n 个有效 DX 的算术平均(落在 i = n + n - 1 = 2n-1)
    first = n + n - 1
    if m > first:
        adx[first] = np.nanmean(dx[n:first + 1])
        for i in range(first + 1, m):
            adx[i] = (adx[i - 1] * (n - 1) + dx[i]) / n
    return pd.Series(adx, index=px.index), pd.Series(pdi, index=px.index), pd.Series(ndi, index=px.index)


def adx_bucket(v):
    if not np.isfinite(v):
        return "无数据"
    if v < 20:
        return "无趋势(<20)"
    if v > 25:
        return "有趋势(>25)"
    return "灰区(20-25)"


# ---------------------------------------------------------------------------
def longest_run(mask: np.ndarray) -> int:
    best = cur = 0
    for v in mask:
        cur = cur + 1 if v else 0
        best = max(best, cur)
    return best


def pct(a, b):
    return round(100.0 * a / b, 2) if b else None


def main():
    px = data.load_benchmark(SYMBOL)
    print(f"SPY 全序列 {px.index[0].date()} .. {px.index[-1].date()},共 {len(px)} 根 bar")

    adx, pdi, ndi = adx_wilder(px, 14)
    adx_shift = adx.shift(1)

    result = {"symbol": SYMBOL,
              "全序列": [str(px.index[0].date()), str(px.index[-1].date()), len(px)],
              "窗口": {}}

    for wname, (w0, w1) in (("PERF", W_PERF), ("W2014", W_28)):
        idx = px.index[(px.index >= pd.Timestamp(w0)) & (px.index <= pd.Timestamp(w1))]
        blk = {"窗口实际": [str(idx[0].date()), str(idx[-1].date())], "交易日数": len(idx),
               "道氏": {}, "ADX": {}, "交叉表": {}}
        print(f"\n===== 窗口 {wname}: {idx[0].date()} .. {idx[-1].date()} | {len(idx)} 交易日 =====")

        # --- ① 道氏 6 种组合 ---
        dow_series = {}
        for k in K_GRID:
            for w in WICK_GRID:
                s_full, npiv = dow_states(px, k, w)
                s = s_full.reindex(idx)
                vc = s.value_counts().to_dict()
                chop = (s == "震荡").to_numpy()
                # ★ 自检二:窗口内摆动点数(落在窗口里的)也不许是 0
                key = f"k={k} / {'影线' if w else '收盘'}"
                dow_series[key] = s
                blk["道氏"][key] = {
                    "摆动点总数(全序列)": npiv,
                    "震荡天数": int(chop.sum()),
                    "震荡占比%": pct(int(chop.sum()), len(idx)),
                    "最长震荡段(交易日)": longest_run(chop),
                    "三态+预热分布": {kk: int(vv) for kk, vv in vc.items()},
                    "上涨占比%": pct(int((s == "上涨").sum()), len(idx)),
                    "下跌占比%": pct(int((s == "下跌").sum()), len(idx)),
                    "预热占比%": pct(int((s == "预热").sum()), len(idx)),
                }
                print(f"  道氏 {key:22s} 摆动点={npiv:4d} 震荡={int(chop.sum()):4d} "
                      f"({pct(int(chop.sum()), len(idx))}%) 最长段={longest_run(chop)}")

        # --- ② ADX 三档 ---
        for tag, ser in (("不挪", adx), ("挪一天(和道氏同口径)", adx_shift)):
            b = ser.reindex(idx).map(adx_bucket)
            vc = b.value_counts().to_dict()
            blk["ADX"][tag] = {kk: {"天数": int(vv), "占比%": pct(int(vv), len(idx))}
                               for kk, vv in vc.items()}
            chopa = (b == "无趋势(<20)").to_numpy()
            blk["ADX"][tag]["最长无趋势段(交易日)"] = longest_run(chopa)
            print(f"  ADX[{tag}] " + " | ".join(
                f"{kk}={int(vv)}({pct(int(vv), len(idx))}%)" for kk, vv in sorted(vc.items())))

        # --- ③ 交叉表(ADX 用挪一天那版,和道氏同口径) ---
        badx = adx_shift.reindex(idx).map(adx_bucket)
        for key, s in dow_series.items():
            dow2 = np.where((s == "震荡").to_numpy(), "道氏震荡", "道氏非震荡")
            ct = pd.crosstab(pd.Series(dow2, index=idx), badx)
            d_chop = (s == "震荡").to_numpy()
            a_chop = (badx == "无趋势(<20)").to_numpy()
            blk["交叉表"][key] = {
                "表": {r: {c: int(ct.loc[r, c]) for c in ct.columns} for r in ct.index},
                "两套都判震荡": int((d_chop & a_chop).sum()),
                "只有道氏判震荡": int((d_chop & ~a_chop).sum()),
                "只有ADX判震荡": int((~d_chop & a_chop).sum()),
                "两套都不判震荡": int((~d_chop & ~a_chop).sum()),
            }
        result["窗口"][wname] = blk

    # 交叉表打印(只打默认参数那一组,PERF 窗口)
    for wname in ("PERF", "W2014"):
        d = result["窗口"][wname]["交叉表"]["k=3.0 / 影线"]
        print(f"\n--- 交叉表 {wname} / k=3.0 影线 ---")
        print(json.dumps(d, ensure_ascii=False, indent=2))

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(result, fh, ensure_ascii=False, indent=2)
    print(f"\n写出 {OUT_JSON}")


if __name__ == "__main__":
    main()
