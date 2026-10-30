"""三项敏感度 + 一项口径自检。

一、ZigZag 阈值 k:文档说「历史上 7 次重要顶部」。k=3(状-1 的值)到底给几次?
二、底部「磨底 / V 底」:3% 固定容差 vs 1×ATR 容差 —— 这个二分法到底存不存在。
三、PEAD 的 filed_at − period_end(修了聚合 bug 之后)。
★ 所有「天」= 交易日,除了明确写「自然日」的。
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
from scipy import stats

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
import engine.data as D
from engine.signals import atr as _atr
from engine.run_a0_states import zigzag_pivots
import features_1030 as F, pool_map_1030 as PM

KS = (3.0, 6.0, 10.0)
YEARS_FULL = list(range(2018, 2026))
PA, PB = list(range(2018, 2023)), list(range(2023, 2026))

man = D.load_manifest(); syms = sorted(man)
pool = PM.load_pool(); cids = PM.resolve_company_ids(pool, syms)
scope = PM.scope_sets(PM.membership(pool, cids))
S = set(scope["全期2018-2025"])
print(f"[核对] 票 {len(syms)}(已知 300)· 池 {len(pool)} 行(已知 74,268)· 口径内 {len(S)} 只")

rows, lag_rows = [], []
for s in syms:
    df = D.load_daily(s)
    if df is None or len(df) < 300:
        continue
    df = df[df.index >= F.WARM_START]
    a = _atr(df, F.ZZ_ATR_P).to_numpy(float)
    hi, lo, cl = (df[c].to_numpy(float) for c in ("high", "low", "close"))
    yr = df.index.year.to_numpy()
    atr_rel = a / cl
    for k in KS:
        piv = zigzag_pivots(hi, lo, cl, a, k=k, use_wick=True)
        for pname, ys in (("全期", YEARS_FULL), ("2018-2022", PA), ("2023-2025", PB)):
            m = np.isin(yr, ys)
            b = dict(piv=piv, low=lo, close=cl)
            t1 = F.f_T1_top_shape(b, m)
            t2 = F.f_T2_bottom_shape(b, m)
            # 底部容差换成 1×ATR
            runs = []
            for i, t, v in piv:
                if t != "L" or not m[i]:
                    continue
                tol = atr_rel[i] if np.isfinite(atr_rel[i]) else F.BOT_TOL
                j = i
                while j - 1 >= 0 and (cl[j-1]-v)/v <= tol:
                    j -= 1
                kk = i
                while kk + 1 < len(cl) and (cl[kk+1]-v)/v <= tol:
                    kk += 1
                runs.append(kk-j+1)
            rows.append(dict(symbol=s, k=k, period=pname,
                             n_tops=t1["n_tops"], share_double_top=t1["share_double_top"],
                             n_bottoms=t2["n_bottoms"], share_grind=t2["share_grind"],
                             median_bottom_days=t2["median_bottom_days"],
                             share_grind_atr=(np.mean([r >= F.GRIND_MIN for r in runs]) if runs else None),
                             median_bottom_days_atr=(float(np.median(runs)) if runs else None)))
    if man[s].fundamentals_path:
        for d, pe in F.earnings_dates(s):
            if pe is not None:
                lag_rows.append((d-pe).days)

R = pd.DataFrame(rows); R.to_csv(os.path.join(HERE, "sens_zigzag_1030.csv"), index=False)
R = R[R.symbol.isin(S)]
print("\n=== 一 · ZigZag 阈值 k 对「重要顶部次数」的影响(口径内 %d 只,全期 2018-2025 = 8 年)===" % R.symbol.nunique())
f = R[R.period == "全期"]
for k in KS:
    g = f[f.k == k]
    print(f"  k={k:4.1f}×ATR(14): 顶部次数 中位 {g.n_tops.median():5.1f} (Q25 {g.n_tops.quantile(.25):.0f} / Q75 {g.n_tops.quantile(.75):.0f})"
          f" → 折成每年 {g.n_tops.median()/8:.1f} 次 · 二次触顶占比中位 {g.share_double_top.median():.3f}"
          f" · 占比≥0.5 的票 {100*(g.share_double_top>=0.5).mean():.1f}%")

print("\n=== 二 · 底部「磨底 vs V 底」(≥%d 个交易日贴在底上 = 磨底)===" % F.GRIND_MIN)
for k in KS:
    g = f[f.k == k]
    print(f"  k={k:4.1f}: 容差3%%固定 → 磨底占比中位 {g.share_grind.median():.3f} · 底部持续中位 {g.median_bottom_days.median():.1f} 交易日"
          f" | 容差1×ATR → 磨底占比中位 {g.share_grind_atr.astype(float).median():.3f} · 持续中位 {g.median_bottom_days_atr.astype(float).median():.1f} 交易日")

print("\n=== 三 · 换 k 之后两段还是不一致吗(T1 二次触顶占比)===")
for k in KS:
    A = R[(R.k == k) & (R.period == "2018-2022")].set_index("symbol")["share_double_top"].astype(float)
    B = R[(R.k == k) & (R.period == "2023-2025")].set_index("symbol")["share_double_top"].astype(float)
    c = A.index.intersection(B.index); A, B = A[c].dropna(), B[c].dropna()
    c2 = A.index.intersection(B.index)
    rr = stats.spearmanr(A[c2], B[c2])
    hi_a, hi_b = (A[c2] >= .5), (B[c2] >= .5)
    obs = float((hi_a == hi_b).mean())
    pa_, pb_ = hi_a.mean(), hi_b.mean()
    exp = pa_*pb_ + (1-pa_)*(1-pb_)
    print(f"  k={k:4.1f}: n={len(c2)} · Spearman {rr.statistic:+.3f} (p={rr.pvalue:.3g})"
          f" · 「二次触顶型」两段一致 {obs:.3f} / 偶然 {exp:.3f}")

L = pd.Series(lag_rows)
print(f"\n=== 四 · PEAD 口径自检:filed_at − period_end(自然日,逐笔 n={len(L)})===")
print(f"  中位 {L.median():.0f} 自然日 · Q25 {L.quantile(.25):.0f} · Q75 {L.quantile(.75):.0f} · 5% {L.quantile(.05):.0f} · 95% {L.quantile(.95):.0f}")
print(f"  >90 自然日的占 {100*(L>90).mean():.1f}%  （★ 修聚合 bug 前这个中位数是 401 自然日 —— 那是我的 bug,不是数据)")
