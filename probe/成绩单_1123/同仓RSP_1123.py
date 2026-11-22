# -*- coding: utf-8 -*-
"""《249》对称基准补齐：**同样仓位的等权标普 RSP**（之前只有「RSP 买入不动」）
★ 只读日净值，不跑回测。仓位取技-3(XING) 整个池的每日仓位（和《397》《401》「同仓标普」同一条仓位序列）。
口径与窗口和《249》新口径逐字相同：窗 252 · 步 5 · 回撤15% / 150日不新高 / 月末连3个月低 / 标普涨>12%账户<=0
"""
import os, gzip, json
import numpy as np, pandas as pd
ROOT = "/home/claude/stock_data"
窗, 步 = 252, 5

def 指数净值(t, idx):
    f = os.path.join(ROOT, f"market_ext_1105/指数ETF长历史_1120/{t}_日线.csv")
    s = pd.read_csv(f, parse_dates=["date"]).set_index("date")["adjusted_close"].reindex(idx).ffill().bfill()
    return s / s.iloc[0]

def 现金日收益(idx):
    d = json.load(gzip.open(os.path.join(ROOT, "market_macro_1105/DTB3/daily.json.gz")))["data"]
    s = pd.Series({pd.Timestamp(x["date"]): x["close"] for x in d if x["close"] is not None}).sort_index()
    return (s.reindex(idx, method="ffill").fillna(0) / 100 / 252)

def 同仓(idx, 基, 仓位):
    r = 基.pct_change().fillna(0); cash = 现金日收益(idx)
    w = 仓位.reindex(idx).fillna(0).clip(0, None).shift(1).fillna(0)
    return (1 + (w * r + (1 - w).clip(0, None) * cash)).cumprod()

def 生存(eq, spy):
    v = np.asarray(eq, float); idx = eq.index; sv = np.asarray(spy, float); n = len(v)
    活 = 0; 总 = 0; 因 = {"回撤": 0, "不新高": 0, "连亏3个月": 0, "跑输大盘": 0}
    for s in range(0, n - 窗, 步):
        seg = v[s:s+窗+1] / v[s]; pk = np.maximum.accumulate(seg); dd = seg / pk - 1
        a = int(np.argmax(dd < -0.15)) if (dd < -0.15).any() else 10**9
        prev = np.concatenate([[seg[0]], pk[:-1]]); last = 0; b = 10**9
        for k in range(1, len(seg)):
            if seg[k] > prev[k] + 1e-12: last = k
            elif k - last >= 150: b = k; break
        sub = pd.Series(seg, index=idx[s:s+窗+1])
        me = sub.groupby([sub.index.year, sub.index.month]).last()
        base = np.concatenate([[1.0], me.values[:-1]])
        down = me.values < base - 1e-12; run = 0; c = 10**9
        for j in range(len(down)):
            run = run + 1 if down[j] else 0
            if run >= 3:
                mp = sub.groupby([sub.index.year, sub.index.month]).apply(lambda x: x.index[-1])
                c = int(sub.index.searchsorted(mp.values[j])); break
        sgm = sv[s:s+窗+1] / sv[s]
        hit = np.where((sgm > 1.12) & (seg <= 1.0))[0]
        d_ = int(hit[0]) if len(hit) else 10**9
        总 += 1; x = min(a, b, c, d_)
        if x >= 10**9: 活 += 1
        else: 因["回撤" if x == a else ("不新高" if x == b else ("连亏3个月" if x == c else "跑输大盘"))] += 1
    return round(活/总*100, 1), {k: round(v2/总*100, 1) for k, v2 in 因.items()}, 总

out = []
for seg, nm in [("一", "2015–2025"), ("二", "2005–2014")]:
    d = pd.read_parquet(os.path.join(ROOT, f"probe/成绩单_1122/out_手册/日线_{seg}_技-3-XING.parquet"))
    eq = d["eq"].dropna(); idx = eq.index
    spy = 指数净值("SPY", idx); rsp = 指数净值("RSP", idx)
    平均仓 = round(float(d["expo"].mean()) * 100, 1)
    print(f"\n★★★ {nm} · 技-3 平均仓位 {平均仓}% · 窗{窗}步{步}")
    print("| 基准 | 活下来(新口径) | 放弃原因占比 |")
    print("|---|---|---|")
    for lab, s_ in [("标普 SPY 买入不动", spy), ("等权标普 RSP 买入不动", rsp),
                    ("同样仓位的 SPY", 同仓(idx, spy, d["expo"])), ("同样仓位的 RSP", 同仓(idx, rsp, d["expo"]))]:
        s_ = s_ / s_.iloc[0]
        a, why, tot = 生存(s_, spy)
        print(f"| {lab} | {a}% | " + " · ".join(f"{k} {v}%" for k, v in why.items() if v > 0) + " |")
        out.append(dict(段=nm, 基准=lab, 活比例=a, 开始日=tot, 平均仓=平均仓, 原因=why))
    # 技-3 本体对照
    e = eq / eq.iloc[0]; a, why, tot = 生存(e, spy)
    print(f"| （对照）技-3(XING) 本体 | {a}% | " + " · ".join(f"{k} {v}%" for k, v in why.items() if v > 0) + " |")
    out.append(dict(段=nm, 基准="技-3(XING) 本体", 活比例=a, 开始日=tot, 平均仓=平均仓, 原因=why))

os.makedirs(os.path.join(ROOT, "probe/成绩单_1123/out"), exist_ok=True)
json.dump(out, open(os.path.join(ROOT, "probe/成绩单_1123/out/同仓RSP_1123.json"), "w"), ensure_ascii=False, indent=1)
print("\n★ 写到 probe/成绩单_1123/out/同仓RSP_1123.json ★★ 只读日净值，没起跑批")
