# -*- coding: utf-8 -*-
"""A 组（第二天收不住）做空：换几种止损 / 目标，看是不是「到目标就走」能赚。引擎外。2022 以后不看。"""
import os, sys, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("m", os.path.join(HERE, "消息大阳线_1125.py")); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m)
E = pd.read_csv(os.path.join(HERE, "out/逐笔.csv"), parse_dates=["date"]); A = E[(E.组 == "A收不住") & (E.类 == "ETF")]
rows, det = [], []
for 止损名 in ["大阳线最高+0.5ATR", "第二天最高+0.5ATR"]:
    for 目标名 in ["前20天最低", "大阳线最低", "大阳线前一天收盘", "1R", "2R"]:
        for 进名 in ["第2天开盘", "第1天收盘"]:
            T = []
            for s, g in A.groupby("sym"):
                D = m.读etf(s); c, o, h, l = [D[k].values for k in ["close", "open", "high", "low"]]; n = len(c)
                tr = np.maximum(h - l, np.maximum(np.abs(h - np.r_[np.nan, c[:-1]]), np.abs(l - np.r_[np.nan, c[:-1]]))); atr = pd.Series(tr).rolling(20).mean().values
                ll20 = pd.Series(l).rolling(20).min().values
                for d in g.date:
                    i = D.index.get_loc(d); j = i + 1; k = j + 1
                    if k >= n: continue
                    ent = o[k] if 进名 == "第2天开盘" else c[j]; k0 = k
                    stp = (h[i] if 止损名.startswith("大阳线") else h[j]) + 0.5 * atr[i]
                    if stp <= ent: continue
                    tgt = {"前20天最低": ll20[i - 1], "大阳线最低": l[i], "大阳线前一天收盘": c[i - 1], "1R": ent - (stp - ent), "2R": ent - 2 * (stp - ent)}[目标名]
                    if tgt >= ent: continue
                    ex = None
                    for kk in range(k0, min(k0 + 10, n)):
                        if kk > k0 or 进名 == "第1天收盘":
                            if o[kk] >= stp: ex, why = o[kk], "止损"; break
                            if o[kk] <= tgt: ex, why = o[kk], "目标"; break
                        if h[kk] >= stp: ex, why = stp, "止损"; break
                        if l[kk] <= tgt: ex, why = tgt, "目标"; break
                    if ex is None: ex, why = c[kk], "到期"
                    risk = (stp - ent) / ent
                    T.append(dict(sym=s, date=d, R=(ent - ex) / (stp - ent) - 0.001 / risk, why=why, 目标距离R=(ent - tgt) / (stp - ent)))
            T = pd.DataFrame(T).sort_values("date"); R = T.R; cum = R.cumsum()
            def f(x): return round(x.R.mean(), 3) if len(x) else None
            熊 = T.date.between("2007-10-01", "2009-03-31")
            rows.append(dict(进=进名, 止损=止损名, 目标=目标名, 笔=len(T), 胜率=round((R > 0).mean(), 3), 每笔R=round(R.mean(), 3),
                             利润因子=round(R[R > 0].sum() / max(1e-9, -R[R <= 0].sum()), 2), 最深连亏R=round((cum - cum.cummax()).min(), 1),
                             到目标=round((T.why == "目标").mean(), 2), 止损比=round((T.why == "止损").mean(), 2), 目标平均离几R=round(T.目标距离R.mean(), 2),
                             段05_14=f(T[T.date < "2015-01-01"]), 段15_21=f(T[T.date >= "2015-01-01"]), 熊2008=f(T[熊]), 非2008=f(T[~熊]),
                             去掉2020三月=f(T[~T.date.between("2020-03-01", "2020-03-31")])))
X = pd.DataFrame(rows); X.to_csv(os.path.join(HERE, "out/换止损目标.csv"), index=False)
pd.set_option("display.width", 300); print(X.to_string())
