# -*- coding: utf-8 -*-
"""《249》最后一条：「拿住的人收益中位数也不能低于标普」
★ 只读《401》《384》已存下的日净值 parquet，不跑回测、不起跑批。
口径（和《249》《397》《401》那套「拿得住」逐字同一套，窗 252 个交易日、步 5）：
  放弃判据 = 回撤>15% | 150 日不新高 | 月末连 3 个月比上月低 | 标普同期涨>12% 而账户<=0
对称（规矩《104》：两侧同口径）：
  标普买入不动 / 等权 RSP / **每条自己仓位的标普**（不是统一拿技-3 的仓位）都按同一窗同一批开始日算。
输出：① 活下来比例 ② 活下来那批开始日的期末收益中位数 ③ 同一批开始日标普的中位数 ④ 差
"""
import os, gzip, json, sys
import numpy as np, pandas as pd

ROOT = "/home/claude/stock_data"
SRC  = os.path.join(ROOT, "probe/成绩单_1122/out_手册")
OUT  = os.path.join(ROOT, "probe/成绩单_1123/out")
os.makedirs(OUT, exist_ok=True)
窗, 步 = 252, 5

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

def 逐开始日(eq, spy):
    """返回 (活掩码, 期末收益数组) —— 期末收益 = 窗口末 / 窗口初 - 1（不管中途放弃，先全算出来）"""
    v = np.asarray(eq, float); idx = eq.index; sv = np.asarray(spy, float); n = len(v)
    活, 末 = [], []
    for s in range(0, n - 窗, 步):
        seg = v[s:s+窗+1] / v[s]
        末.append(seg[-1] - 1)
        pk = np.maximum.accumulate(seg); dd = seg / pk - 1
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
        活.append(min(a, b, c, d_) >= 10**9)
    return np.array(活), np.array(末)

序 = ["buy_and_hold", "trend_following", "技-1", "技-3-XING", "技-4-行业", "技-6-XING"]
名 = {"buy_and_hold": "拿着不动", "trend_following": "趋势跟随", "技-1": "技-1",
      "技-3-XING": "技-3(XING)", "技-4-行业": "技-4(行业)", "技-6-XING": "技-6(XING)"}
段 = {"一": "2015–2025", "二": "2005–2014"}

汇总 = []
for seg_k, seg_nm in 段.items():
    print(f"\n{'='*78}\n★★★ {seg_nm}（段{seg_k}）· 窗 {窗} 个交易日 · 步 {步}\n{'='*78}")
    print("| 版本 | 活下来 | 拿住的人期末收益中位数 | 同一批开始日·标普买入不动 | 同一批开始日·同仓标普 | 差(对买入不动) | 差(对同仓) |")
    print("|---|---|---|---|---|---|---|")
    for k in 序:
        f = os.path.join(SRC, f"日线_{seg_k}_{k}.parquet")
        if not os.path.exists(f):
            print(f"| {名[k]} | 缺文件 | | | | | |"); continue
        d = pd.read_parquet(f); eq = d["eq"].dropna(); eq = eq / eq.iloc[0]
        spy_nav = 指数净值("SPY", eq.index)
        同仓 = 等仓位标普(eq.index, d["expo"]); 同仓 = 同仓 / 同仓.iloc[0]
        活, 末 = 逐开始日(eq, spy_nav)
        _, 末spy = 逐开始日(spy_nav, spy_nav)
        _, 末同仓 = 逐开始日(同仓, spy_nav)
        if 活.sum() == 0:
            print(f"| {名[k]} | 0% (0/{len(活)}) | 一个都没活 | | | | |"); continue
        m  = float(np.median(末[活])); ms = float(np.median(末spy[活])); mt = float(np.median(末同仓[活]))
        row = dict(段=seg_nm, 版本=名[k], 活比例=round(活.sum()/len(活)*100,1), 活数=int(活.sum()), 总开始日=len(活),
                   拿住中位数=round(m*100,2), 标普中位数=round(ms*100,2), 同仓中位数=round(mt*100,2),
                   差_买入不动=round((m-ms)*100,2), 差_同仓=round((m-mt)*100,2),
                   全样本中位数=round(float(np.median(末))*100,2))
        汇总.append(row)
        print(f"| {名[k]} | {row['活比例']}% ({row['活数']}/{row['总开始日']}) | {row['拿住中位数']}% | "
              f"{row['标普中位数']}% | {row['同仓中位数']}% | {row['差_买入不动']:+} | {row['差_同仓']:+} |")

json.dump(汇总, open(os.path.join(OUT, "拿住的人收益中位数_1123.json"), "w"), ensure_ascii=False, indent=1)
print(f"\n★ 写到 {OUT}/拿住的人收益中位数_1123.json")
print("★★ 本尺子只读日净值，★★★ 没跑回测、没起跑批、没碰 skills_v2/")
