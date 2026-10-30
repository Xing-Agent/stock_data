"""★★★ 顺手查出来的一个 engine bug —— 不是本轮任务,但它决定 T1/T2/T3 能不能校准。

三秒版:`engine/run_a0_states.zigzag_pivots` 在阈值 k ≥ 约 5 时**一个摆动点都不出**,
        而且是静默的(返回空列表,不报错)。所以「ZigZag 阈值 3×ATR 待校准」
        这件事**现在校准不了** —— 往上调一点就全空。

病根:方向未定(direction == 0)时,函数的两个分支**在同一根 bar 里都执行**:
      先把 ext_v 抬到当根 high,再把 ext_v 压到当根 low。
      于是「正在跟踪的极值」每根 bar 都被重置,跳出 direction==0 的条件退化成
      **单根 bar 的振幅 ≥ k×ATR**。k=3 偶尔能满足(于是看着正常),k=6 永不满足。

★ 本文件只做取证,不改 engine/。
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
import engine.data as D
from engine.signals import atr as _atr
from engine.run_a0_states import zigzag_pivots as ENGINE_ZZ


def zz_fixed(high, low, close, atr, k=3.0):
    """同一套判据,只把 bootstrap 改对:方向未定时同时记住跑到过的最高和最低,
    谁先满足 k×ATR 的反转就定方向。其余逻辑(严格交替、取更极端)不变。"""
    n = len(close); piv = []
    direction = 0
    hi_i = lo_i = 0
    hi_v = high[0]; lo_v = low[0]
    ext_i, ext_v = 0, close[0]
    for i in range(1, n):
        a = atr[i]
        if not np.isfinite(a) or a <= 0:
            continue
        thr = k * a
        h, lo = high[i], low[i]
        if not (np.isfinite(h) and np.isfinite(lo)):
            continue
        if direction == 0:
            if h > hi_v: hi_i, hi_v = i, h
            if lo < lo_v: lo_i, lo_v = i, lo
            if (hi_v - lo) >= thr and hi_i < i:
                piv.append((hi_i, "H", float(hi_v))); direction, ext_i, ext_v = -1, i, lo
            elif (h - lo_v) >= thr and lo_i < i:
                piv.append((lo_i, "L", float(lo_v))); direction, ext_i, ext_v = 1, i, h
            continue
        if direction > 0:
            if h > ext_v: ext_i, ext_v = i, h
            if (ext_v - lo) >= thr:
                piv.append((ext_i, "H", float(ext_v))); direction, ext_i, ext_v = -1, i, lo
        else:
            if lo < ext_v: ext_i, ext_v = i, lo
            if (h - ext_v) >= thr:
                piv.append((ext_i, "L", float(ext_v))); direction, ext_i, ext_v = 1, i, h
    out = []
    for p in piv:
        if out and out[-1][1] == p[1]:
            keep = p if ((p[1] == "H" and p[2] > out[-1][2]) or
                         (p[1] == "L" and p[2] < out[-1][2])) else out[-1]
            out[-1] = keep
        else:
            out.append(p)
    return out


if __name__ == "__main__":
    man = D.load_manifest(); syms = sorted(man)
    print(f"[核对] 票 {len(syms)}(已知 300)")
    KS = (2.0, 3.0, 4.0, 5.0, 6.0, 8.0, 12.0)
    rows = []
    single_bar_hits = []
    for s in syms:
        df = D.load_daily(s)
        if df is None or len(df) < 300: continue
        df = df[df.index >= "2016-01-04"]
        a = _atr(df, 14).to_numpy(float)
        hi, lo, cl = (df[c].to_numpy(float) for c in ("high", "low", "close"))
        rg = hi - lo
        with np.errstate(invalid="ignore"):
            single_bar_hits.append([float(np.nanmean(rg >= k*a)) for k in KS])
        r = {"symbol": s}
        for k in KS:
            r[f"engine_k{k}"] = len(ENGINE_ZZ(hi, lo, cl, a, k=k, use_wick=True))
            r[f"fixed_k{k}"] = len(zz_fixed(hi, lo, cl, a, k=k))
        rows.append(r)
    R = pd.DataFrame(rows); R.to_csv(os.path.join(HERE, "zigzag_bug_1030.csv"), index=False)
    sb = pd.DataFrame(single_bar_hits, columns=[f"k{k}" for k in KS])
    print(f"\n摆动点总数(2016-2025,{len(R)} 只票)· 中位 / 有 0 个摆动点的票占比")
    print(f"{'k':>6} | {'engine 现状':>12} {'0点的票':>8} | {'修好 bootstrap':>14} {'0点的票':>8} | {'单根bar振幅≥k×ATR 的天数占比(中位)':>12}")
    for k in KS:
        e, f = R[f"engine_k{k}"], R[f"fixed_k{k}"]
        print(f"{k:6.1f} | {e.median():12.0f} {100*(e==0).mean():7.1f}% | {f.median():14.0f} {100*(f==0).mean():7.1f}% | {100*sb[f'k{k}'].median():10.4f}%")
    print("\n★ 读法:engine 现状那一列在 k=6 之后整列 0,而「单根 bar 振幅 ≥ k×ATR」的概率"
          "\n  恰好在同一个 k 上掉到 0 —— 这就是病根的直接证据。修好 bootstrap 之后 k=12 仍有摆动点。")
