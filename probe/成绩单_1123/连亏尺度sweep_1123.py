# -*- coding: utf-8 -*-
"""《408》二节那条「推断」改成量出来的：把「连亏 N 个月」从 3 推到文献尺度(11~12个月 / 5~6个季度)。
★ 只读《384》存下的日净值，不跑回测、不起跑批。口径与《249》新口径逐字相同：窗252 步5 回撤15% 150日不新高 标普涨>12%账户<=0
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

def 生存(eq, spy, 连亏月):
    """连亏月=None → 去掉这一条"""
    v = np.asarray(eq, float); idx = eq.index; sv = np.asarray(spy, float); n = len(v)
    活 = 0; 总 = 0; 因 = {"回撤":0, "不新高":0, "连亏":0, "跑输大盘":0}
    for s in range(0, n - 窗, 步):
        seg = v[s:s+窗+1] / v[s]; pk = np.maximum.accumulate(seg); dd = seg / pk - 1
        a = int(np.argmax(dd < -0.15)) if (dd < -0.15).any() else 10**9
        prev = np.concatenate([[seg[0]], pk[:-1]]); last = 0; b = 10**9
        for k in range(1, len(seg)):
            if seg[k] > prev[k] + 1e-12: last = k
            elif k - last >= 150: b = k; break
        c = 10**9
        if 连亏月 is not None:
            sub = pd.Series(seg, index=idx[s:s+窗+1])
            me = sub.groupby([sub.index.year, sub.index.month]).last()
            base = np.concatenate([[1.0], me.values[:-1]])
            down = me.values < base - 1e-12; run = 0
            for j in range(len(down)):
                run = run + 1 if down[j] else 0
                if run >= 连亏月:
                    mp = sub.groupby([sub.index.year, sub.index.month]).apply(lambda x: x.index[-1])
                    c = int(sub.index.searchsorted(mp.values[j])); break
        sgm = sv[s:s+窗+1] / sv[s]
        hit = np.where((sgm > 1.12) & (seg <= 1.0))[0]
        d_ = int(hit[0]) if len(hit) else 10**9
        总 += 1; x = min(a, b, c, d_)
        if x >= 10**9: 活 += 1
        else: 因["回撤" if x==a else ("不新高" if x==b else ("连亏" if x==c else "跑输大盘"))] += 1
    return round(活/总*100,1), {k: round(v2/总*100,1) for k,v2 in 因.items()}, 总

def 窗内月末个数(idx):
    cnt = []
    for s in range(0, len(idx) - 窗, 步):
        sub = idx[s:s+窗+1]
        cnt.append(len(pd.Series(0, index=sub).groupby([sub.year, sub.month]).last()))
    return np.array(cnt)

档 = [3, 4, 6, 9, 11, 12, 13, 15, 18, None]
结果 = {}
for seg, nm in [("一", "2015-2025"), ("二", "2005-2014")]:
    d = pd.read_parquet(os.path.join(ROOT, f"probe/成绩单_1122/out_手册/日线_{seg}_技-3-XING.parquet"))
    eq = d["eq"].dropna(); eq = eq/eq.iloc[0]; idx = eq.index
    spy = 指数净值("SPY", idx); rsp = 指数净值("RSP", idx)
    同SPY = 同仓(idx, spy, d["expo"]); 同RSP = 同仓(idx, rsp, d["expo"])
    mc = 窗内月末个数(idx)
    print(f"\n★★★ 段{seg} {nm} · {idx[0].date()}→{idx[-1].date()} · 窗内月末个数 min {mc.min()} / 中位 {int(np.median(mc))} / max {mc.max()}")
    print("| 连亏阈值 | 策略 | 同仓SPY | 同仓RSP | 策略−同仓SPY | 策略−同仓RSP | 连亏这条打掉占比(策略) |")
    print("|---|---|---|---|---|---|---|")
    for m in 档:
        a_, wa, tot = 生存(eq, spy, m)
        b_, _, _  = 生存(同SPY, spy, m)
        c_, _, _  = 生存(同RSP, spy, m)
        lab = "去掉这一条" if m is None else f"连 {m} 个月"
        print(f"| {lab} | {a_} | {b_} | {c_} | {round(a_-b_,1):+} | {round(a_-c_,1):+} | {wa['连亏']}% |")
        结果[(seg, str(m))] = dict(策略=a_, 同仓SPY=b_, 同仓RSP=c_, 连亏占比=wa["连亏"], 开始日=tot)
    结果[(seg,"月末个数")] = dict(min=int(mc.min()), med=int(np.median(mc)), max=int(mc.max()))
json.dump({f"{k[0]}|{k[1]}": v for k, v in 结果.items()},
          open(os.path.join(ROOT,"probe/成绩单_1123/out/连亏尺度sweep_1123.json"),"w"), ensure_ascii=False, indent=1)
print("\n★ 只读日净值，没起跑批")
