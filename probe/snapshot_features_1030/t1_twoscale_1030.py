"""T1「它怎么做顶」还能不能救:两尺度定义。

为什么要换定义:★★★ 一个双顶的两个峰之间的那个坑,按定义**小于** ZigZag 的阈值 ——
否则中间就会多出一个摆动点。所以用同一把 k×ATR 的尺子既找「重要顶部」又认
「二次触顶」,是自相矛盾的:尺子大到能叫「重要」,两个峰就被并成一个点。

两尺度做法:
  大尺度(k×ATR 的 ZigZag)只负责**找到重要顶部在哪**;
  小尺度(围绕那个顶部的 ±W 交易日窗口)负责数**那个价位被摸过几次**。
  摸过 ≥2 次(两次之间要先跌破 v×(1−dip))= 二次触顶型。
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

TOL = 0.03      # 「摸到同一个价位」容差 3%  ★ XING·待校准
DIP = 0.06      # 两次之间必须先跌破 顶部×(1−6%)  ★ XING·待校准
W = 60          # 顶部前后各 60 个交易日
KS = (6.0, 8.0)
PER = {"全期": list(range(2018, 2026)), "2018-2022": list(range(2018, 2023)),
       "2023-2025": list(range(2023, 2026))}


def touches(hi, cl, i, v):
    a, b = max(0, i - W), min(len(hi), i + W + 1)
    lvl, dipl = v * (1 - TOL), v * (1 - DIP)
    n, armed = 0, True
    for j in range(a, b):
        if armed and hi[j] >= lvl:
            n += 1; armed = False
        elif not armed and cl[j] < dipl:
            armed = True
    return n


man = D.load_manifest(); syms = sorted(man)
pool = PM.load_pool(); scope = PM.scope_sets(PM.membership(pool, PM.resolve_company_ids(pool, syms)))
S = set(scope["全期2018-2025"])
print(f"[核对] 票 {len(syms)}(已知 300)· 池 {len(pool)} 行(已知 74,268)· 口径内 {len(S)} 只")
rows = []
for s in syms:
    df = D.load_daily(s)
    if df is None or len(df) < 300: continue
    df = df[df.index >= F.WARM_START]
    a = _atr(df, 14).to_numpy(float)
    hi, lo, cl = (df[c].to_numpy(float) for c in ("high", "low", "close"))
    yr = df.index.year.to_numpy()
    for k in KS:
        piv = [(i, t, v) for i, t, v in zz_fixed(hi, lo, cl, a, k=k) if t == "H"]
        for pn, ys in PER.items():
            m = np.isin(yr, ys)
            ev = [touches(hi, cl, i, v) for i, t, v in piv if m[i]]
            n = len(ev)
            rows.append(dict(symbol=s, k=k, period=pn, n_tops=n,
                             share_double=(np.mean([e >= 2 for e in ev]) if n else None),
                             median_touches=(float(np.median(ev)) if n else None)))
R = pd.DataFrame(rows); R.to_csv(os.path.join(HERE, "t1_twoscale_1030.csv"), index=False)
R = R[R.symbol.isin(S)]
print(f"\n=== 两尺度 T1 分布(口径内 {R.symbol.nunique()} 只,全期 8 年,容差 {TOL:.0%} / 坑 {DIP:.0%} / 窗口 ±{W} 交易日)===")
for k in KS:
    g = R[(R.k == k) & (R.period == "全期")]
    v = g.share_double.astype(float).dropna()
    print(f"k={k:.0f}: 顶部次数中位 {g.n_tops.median():.0f}(每年 {g.n_tops.median()/8:.1f})· 被摸次数中位 {g.median_touches.astype(float).median():.1f}")
    print(f"      二次触顶占比 中位 {v.median():.3f} · Q25 {v.quantile(.25):.3f} · Q75 {v.quantile(.75):.3f}"
          f" · ≥0.5 的票 {100*(v>=.5).mean():.1f}% · 取 0 的票 {100*(v==0).mean():.1f}% · 取 1 的票 {100*(v==1).mean():.1f}%")
print("\n=== 两段一致性 ===")
for k in KS:
    A = R[(R.k == k) & (R.period == "2018-2022")].set_index("symbol")
    B = R[(R.k == k) & (R.period == "2023-2025")].set_index("symbol")
    c = sorted(set(A.index) & set(B.index)); A, B = A.loc[c], B.loc[c]
    for minn in (3, 4):
        va = A.share_double.astype(float).where(A.n_tops >= minn)
        vb = B.share_double.astype(float).where(B.n_tops >= minn)
        ok = va.notna() & vb.notna()
        if ok.sum() < 20:
            print(f"k={k:.0f} 最低{minn}个顶: 可判票 {ok.sum()} 只 → ★ 不到 20,做不出逐票判定"); continue
        x, y = va[ok], vb[ok]
        lx, ly = (x >= .5), (y >= .5)
        obs = float((lx == ly).mean()); pa_, pb_ = float(lx.mean()), float(ly.mean())
        exp = pa_*pb_ + (1-pa_)*(1-pb_)
        rr = stats.spearmanr(x, y)
        print(f"k={k:.0f} 最低{minn}个顶: n={ok.sum():3d} · 「二次触顶型」占比 {pa_:.2f}→{pb_:.2f}"
              f" · 一致 {obs:.3f} / 偶然 {exp:.3f} / kappa {(obs-exp)/(1-exp) if exp<1 else float('nan'):+.3f}"
              f" · Spearman {rr.statistic:+.3f} (p={rr.pvalue:.3g})")
