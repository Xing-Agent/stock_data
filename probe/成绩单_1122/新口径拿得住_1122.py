# -*- coding: utf-8 -*-
"""《249》新口径「拿不拿得住」重算（只读《384》存下的日净值，不跑回测、不起跑批）
旧口径(《384》那一列)：峰值回撤15%  或 150个交易日不创新高
新口径(《249》)      ：上面两条  +  月末净值连着3个月比上月低  +  标普同期涨>12%而账户<=0
对称：标普买入不动 / 同样仓位的标普 / 等权标普RSP 都按同一套规则算
"""
import os, glob, gzip, json
import numpy as np, pandas as pd
ROOT = "/home/claude/stock_data"
OUT  = os.path.join(ROOT, "probe/成绩单_1122/out")

def 指数净值(tick, idx):
    f = os.path.join(ROOT, f"market_ext_1105/指数ETF长历史_1120/{tick}_日线.csv")
    s = pd.read_csv(f, parse_dates=["date"]).set_index("date")["adjusted_close"].reindex(idx).ffill().bfill()
    return s / s.iloc[0]

def 现金日收益(idx):
    d = json.load(gzip.open(os.path.join(ROOT, "market_macro_1105/DTB3/daily.json.gz")))["data"]
    s = pd.Series({pd.Timestamp(x["date"]): x["close"] for x in d if x["close"] is not None}).sort_index()
    return (s.reindex(idx, method="ffill").fillna(0) / 100 / 252)

def 等仓位标普(idx, 仓位):
    spy = 指数净值("SPY", idx).pct_change().fillna(0); cash = 现金日收益(idx)
    w = 仓位.reindex(idx).fillna(0).clip(0, None).shift(1).fillna(0)
    return (1 + (w * spy + (1 - w).clip(0, None) * cash)).cumprod()

def 生存(eq, spy, 步=5, 窗=252, 回撤线=0.15, 不新高=150, 连亏月=3, 大盘涨=0.12, 新口径=True):
    v = np.asarray(eq, float); idx = eq.index; sv = np.asarray(spy, float); n = len(v)
    活 = 0; 总 = 0; 因 = {"回撤": 0, "不新高": 0, "连亏3个月": 0, "跑输大盘": 0}
    for s in range(0, n - 窗, 步):
        seg = v[s:s+窗+1] / v[s]; pk = np.maximum.accumulate(seg); dd = seg / pk - 1
        a = int(np.argmax(dd < -回撤线)) if (dd < -回撤线).any() else 10**9
        prev = np.concatenate([[seg[0]], pk[:-1]]); last = 0; b = 10**9
        for k in range(1, len(seg)):
            if seg[k] > prev[k] + 1e-12: last = k
            elif k - last >= 不新高: b = k; break
        c = d_ = 10**9
        if 新口径:
            sub = pd.Series(seg, index=idx[s:s+窗+1])
            me = sub.groupby([sub.index.year, sub.index.month]).last()
            mp = sub.groupby([sub.index.year, sub.index.month]).apply(lambda x: x.index[-1])
            base = np.concatenate([[1.0], me.values[:-1]])
            down = me.values < base - 1e-12; run = 0
            for j in range(len(down)):
                run = run + 1 if down[j] else 0
                if run >= 连亏月: c = int(sub.index.searchsorted(mp.values[j])); break
            sgm = sv[s:s+窗+1] / sv[s]
            hit = np.where((sgm > 1 + 大盘涨) & (seg <= 1.0))[0]
            if len(hit): d_ = int(hit[0])
        总 += 1; x = min(a, b, c, d_)
        if x >= 10**9: 活 += 1
        else:
            因["回撤" if x == a else ("不新高" if x == b else ("连亏3个月" if x == c else "跑输大盘"))] += 1
    return (round(活/总*100, 1) if 总 else None), {k: round(val/总*100, 1) for k, val in 因.items()}, 总

名 = {"buy_and_hold": "拿着不动", "trend_following": "趋势跟随", "技-1": "技-1",
      "技-3-XING": "技-3(XING)", "技-4-行业": "技-4(行业)", "技-6-XING": "技-6(XING)"}
池 = {"A_原样": "整个池", "D_动量20加增长30": "挑过票"}
序 = ["buy_and_hold", "trend_following", "技-1", "技-3-XING", "技-4-行业", "技-6-XING"]

rows = []
idx0 = None; expo_ref = None
for k in 序:
    for p, pz in 池.items():
        f = os.path.join(OUT, f"日线_{k}_{p}.parquet")
        if not os.path.exists(f): print("缺", f); continue
        d = pd.read_parquet(f); eq = d["eq"].dropna(); eq = eq / eq.iloc[0]
        if idx0 is None: idx0 = eq.index; expo_ref = d["expo"]
        spy = 指数净值("SPY", eq.index)
        o, _, tot = 生存(eq, spy, 新口径=False)
        nw, why, _ = 生存(eq, spy, 新口径=True)
        rows.append((f"{名[k]} · {pz}", o, nw, why, tot, round(float(d['expo'].mean())*100,1)))

for nm, getter in [("标普买入不动", lambda i: 指数净值("SPY", i)),
                   ("等权标普 RSP 买入不动", lambda i: 指数净值("RSP", i)),
                   ("同样仓位的标普(用技-3整个池的仓位)", lambda i: 等仓位标普(i, expo_ref))]:
    eq = getter(idx0); eq = eq / eq.iloc[0]; spy = 指数净值("SPY", idx0)
    o, _, tot = 生存(eq, spy, 新口径=False); nw, why, _ = 生存(eq, spy, 新口径=True)
    rows.append((nm, o, nw, why, tot, None))

print(f"窗口 {idx0[0].date()} → {idx0[-1].date()} · 每条 {rows[0][4]} 个开始日\n")
print("| | 旧口径(《384》) | 新口径(《249》) | 差 | 放弃原因占比（新口径） |")
print("|---|---|---|---|---|")
for nm, o, nw, why, tot, ex in rows:
    w = " · ".join(f"{k} {v}%" for k, v in why.items() if v > 0)
    print(f"| {nm} | {o}% | {nw}% | {round(nw-o,1)} | {w} |")
