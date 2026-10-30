"""用修好 bootstrap 的 ZigZag 重跑 T1/T2/T3 —— 回答「顶底特点到底能不能上界面」。

为什么要这一轮:engine 的 zigzag 在 k≥6 静默返回空,所以 k=3 是**唯一能跑的档**,
而 k=3 给每只票 8 年 54 个「重要顶部」(每年 6.8 个)—— 那不叫重要顶部。
文档里写的「历史上 7 次重要顶部」对应的量级是 k≈8。本文件把 k=3/6/8 都跑一遍。
★ 「天」一律交易日。
"""
from __future__ import annotations
import os, sys
import numpy as np, pandas as pd
from scipy import stats
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE)
import engine.data as D
from engine.signals import atr as _atr
import features_1030 as F, pool_map_1030 as PM
from zigzag_bug_1030 import zz_fixed

KS = (3.0, 6.0, 8.0)
PER = {"全期": list(range(2018, 2026)), "2018-2022": list(range(2018, 2023)),
       "2023-2025": list(range(2023, 2026))}

man = D.load_manifest(); syms = sorted(man)
pool = PM.load_pool(); scope = PM.scope_sets(PM.membership(pool, PM.resolve_company_ids(pool, syms)))
S = set(scope["全期2018-2025"])
print(f"[核对] 票 {len(syms)}(已知 300)· 池 {len(pool)} 行(已知 74,268)· 大中盘口径内 {len(S)} 只")

rows = []
for s in syms:
    df = D.load_daily(s)
    if df is None or len(df) < 300: continue
    df = df[df.index >= F.WARM_START]
    a = _atr(df, 14).to_numpy(float)
    hi, lo, cl = (df[c].to_numpy(float) for c in ("high", "low", "close"))
    yr = df.index.year.to_numpy()
    for k in KS:
        piv = zz_fixed(hi, lo, cl, a, k=k)
        b = dict(piv=piv, low=lo, close=cl)
        for pn, ys in PER.items():
            m = np.isin(yr, ys)
            t1 = F.f_T1_top_shape(b, m); t2 = F.f_T2_bottom_shape(b, m); t3 = F.f_T3_swing_size(b, m)
            rows.append(dict(symbol=s, k=k, period=pn, **{kk: vv for kk, vv in
                        list(t1.items()) + list(t2.items()) + list(t3.items()) if kk != "_n"}))
R = pd.DataFrame(rows); R.to_csv(os.path.join(HERE, "topbottom_fixed_1030.csv"), index=False)
R = R[R.symbol.isin(S)]

print(f"\n=== 分布(大中盘口径内 {R.symbol.nunique()} 只,全期 2018-2025 = 8 年)===")
f = R[R.period == "全期"]
for k in KS:
    g = f[f.k == k]
    print(f"\nk={k:.0f}×ATR(14)  顶部次数中位 {g.n_tops.median():.0f}(每年 {g.n_tops.median()/8:.1f} 次)· 底部次数中位 {g.n_bottoms.median():.0f}")
    for col, lab in (("share_double_top", "二次触顶占比"), ("share_grind", "磨底占比")):
        v = g[col].astype(float).dropna()
        if len(v) < 20: print(f"   {lab}: 有效样本只有 {len(v)} 只 → 不足"); continue
        print(f"   {lab}: 中位 {v.median():.3f} · Q25 {v.quantile(.25):.3f} · Q75 {v.quantile(.75):.3f}"
              f" · ≥0.5 的票 {100*(v>=.5).mean():.1f}% · 取 0 的票 {100*(v==0).mean():.1f}%")
    for col, lab in (("median_top_to_bottom", "顶→底跌幅中位"), ("median_bottom_to_top", "底→顶涨幅中位")):
        v = g[col].astype(float).dropna()
        if len(v) >= 20:
            print(f"   {lab}: 中位 {v.median():+.1%} · Q25 {v.quantile(.25):+.1%} · Q75 {v.quantile(.75):+.1%}")

print("\n=== 两段一致性(2018-2022 vs 2023-2025)===")
print(f"{'k':>4} {'特征':<16} {'最低事件数':>10} {'可判票数':>8} {'一致率':>8} {'偶然':>8} {'kappa':>7} {'Spearman':>9}")
for k in KS:
    A = R[(R.k == k) & (R.period == "2018-2022")].set_index("symbol")
    B = R[(R.k == k) & (R.period == "2023-2025")].set_index("symbol")
    c = sorted(set(A.index) & set(B.index)); A, B = A.loc[c], B.loc[c]
    for col, ncol, minn, lab in (("share_double_top", "n_tops", 4, "T1 二次触顶型"),
                                 ("share_grind", "n_bottoms", 4, "T2 磨底型"),
                                 ("median_top_to_bottom", "n_swings", 6, "T3 顶→底跌幅")):
        va = A[col].astype(float).where(A[ncol].astype(float) >= minn)
        vb = B[col].astype(float).where(B[ncol].astype(float) >= minn)
        ok = va.notna() & vb.notna()
        if ok.sum() < 20:
            print(f"{k:4.0f} {lab:<16} {minn:>10} {ok.sum():>8}   ← 可判的票不到 20 只,★ 这一档根本做不出逐票判定")
            continue
        x, y = va[ok], vb[ok]
        if col == "median_top_to_bottom":
            t1_, t2_ = x.quantile(1/3), x.quantile(2/3)
            lx = pd.cut(x, [-9, t1_, t2_, 9], labels=["低", "中", "高"])
            ly = pd.cut(y, [-9, t1_, t2_, 9], labels=["低", "中", "高"])
        else:
            lx, ly = (x >= .5).map({True: "高", False: "低"}), (y >= .5).map({True: "高", False: "低"})
        obs = float((lx.astype(str) == ly.astype(str)).mean())
        px = lx.astype(str).value_counts(normalize=True); py = ly.astype(str).value_counts(normalize=True)
        exp = float(sum(px.get(z, 0)*py.get(z, 0) for z in set(px.index) | set(py.index)))
        rr = stats.spearmanr(x, y)
        kp = (obs-exp)/(1-exp) if exp < 1 else float("nan")
        print(f"{k:4.0f} {lab:<16} {minn:>10} {ok.sum():>8} {obs:>8.3f} {exp:>8.3f} {kp:>7.3f} {rr.statistic:>+9.3f}")
