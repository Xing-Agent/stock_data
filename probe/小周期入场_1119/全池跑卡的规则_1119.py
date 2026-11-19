#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""把技术面大师卡的规则原样搬到研发池小时线上跑（2026-11-19）

大白话：考试那边在 5 只票、5 个月上把规则调到「每笔 +0.35R」。那个数是照着同一份数据调出来的，偏好看。
这里把他们的规则程序（probe/技术面大师考试_1119/trig2.py 的 run2）**一个字不改**地拿来，
换到研发池的票、2015–2025 的 1 小时线上跑，看原样的结果。
  · 规则代码：直接读 trig2.py 的源码执行，不是我重写的。只在输出里多记三样（进场价、每笔冒的风险占比、止损价），不影响任何判断。
  · 数据：market_ext_1105/小时线_1119/全量_2015_2025，用折算价，含盘前盘后（和考试那边一样）。
  · 票：研发池小时线名单里按固定种子随机抽（默认 300 只），因为全量 2,125 只逐根循环要跑十几个小时。抽样名单存盘。
  · 几版并排：卡现在这版（早鸟扳机 + 盈亏比双门槛 + 中段禁区 + 只做前两次 + 分票规则）、去掉中段禁区、只换早鸟扳机、最早那版（收盘确认、不设闸）。
  · 成本：考试那边没扣。这里另算一列「扣成本后」：每边 5 个基点，折成 R = 0.001 ÷ 每笔风险占比。
没做的：没有账户层面（同时拿几只、钱够不够），只是每个信号一笔；分票规则里的 SOXL / BTC 那些名字在研发池里碰不上，等于都按「其余」。
"""
import io, json, os, re, sys, time, random
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
import numpy as np, pandas as pd, warnings; warnings.filterwarnings("ignore")
import pyarrow.parquet as pq, pyarrow.dataset as ds
EX = os.path.join(ROOT, "probe/技术面大师考试_1119")
t1 = io.open(os.path.join(EX, "trig.py"), encoding="utf-8").read()
def atr(d, n=14):
    tr = pd.concat([d.high - d.low, (d.high - d.close.shift()).abs(), (d.low - d.close.shift()).abs()], axis=1).max(axis=1); return tr.rolling(n).mean()
exec("def trend_series" + t1.split("def trend_series")[1].split("def run(")[0])          # 原样
t2 = io.open(os.path.join(EX, "trig2.py"), encoding="utf-8").read()
src = "def h4info" + t2.split("def h4info")[1].split("S={k:v")[0]
a = "trades.append({'票':name,'t':str(d.index[i])[:16],'dir':'多' if Lg else '空','R':round(res,2),'tp1':half})"
assert a in src
src = src.replace("e=C[i];st=pin-0.5*A[i] if Lg else pin+0.5*A[i];", "e=C[i];st=pin-0.5*A[i] if Lg else pin+0.5*A[i];_st0=st;")
src = src.replace(a, "trades.append({'票':name,'t':str(d.index[i])[:16],'dir':'多' if Lg else '空','R':round(res,4),'tp1':half,'e':e,'风险占比':risk/e,'止损':_st0})")
assert "_st0=st" in src
exec(src)

D = os.path.join(ROOT, "market_ext_1105/小时线_1119/全量_2015_2025")
N = int(os.environ.get("XING_N", "300")); TAG = os.environ.get("XING_TAG", f"抽{N}")
OUT = os.path.join(HERE, "out_" + TAG); os.makedirs(OUT, exist_ok=True)
allsym = [l.strip() for l in io.open(os.path.join(ROOT, "probe/挂件_1119/小时线取数名单_研发池中档_1119.txt"), encoding="utf-8") if l.strip()]
random.seed(20261119); 抽 = sorted(random.sample(allsym, N)) if N < len(allsym) else allsym
io.open(os.path.join(OUT, "抽样名单.txt"), "w", encoding="utf-8").write("\n".join(抽) + "\n")
CFG = {"卡现在这版": dict(trig="C", rrmode="gem", f_box=True, tk_rules=True, f_n=True),
       "去掉中段禁区": dict(trig="C", rrmode="gem", tk_rules=True, f_n=True),
       "只换早鸟扳机_不设闸": dict(trig="C", rrmode="none"),
       "最早那版_收盘确认_不设闸": dict(trig="A", rrmode="none")}
files = sorted(f for f in os.listdir(D) if f.endswith(".parquet"))
cols = ["symbol", "time_utc", "open_adj", "high_adj", "low_adj", "close_adj", "volume_adj"]
B = 25
for b in range(0, len(抽), B):
    fp = os.path.join(OUT, f"批{b // B:03d}.csv")
    if os.path.exists(fp): continue
    grp = 抽[b:b + B]; t0 = time.time()
    df = pd.concat([ds.dataset(os.path.join(D, f)).to_table(columns=cols, filter=ds.field("symbol").isin(grp)).to_pandas() for f in files])
    df.columns = ["symbol", "time", "open", "high", "low", "close", "volume"]
    rows = []
    for s, d in df.groupby("symbol"):
        d = d.set_index("time").sort_index(); d = d[~d.index.duplicated()].drop(columns="symbol").dropna(subset=["close"])
        d = d[(d.close > 0)]
        if len(d) < 2000: continue
        for nm, kw in CFG.items():
            try:
                x = run2(d, s, **kw)
            except Exception as e:
                x = pd.DataFrame(); print("ERR", s, nm, repr(e)[:120], flush=True)
            if len(x): x["版"] = nm; rows.append(x)
    (pd.concat(rows) if rows else pd.DataFrame(columns=["票"])).to_csv(fp, index=False)
    print(f"批 {b // B} 完成 {len(grp)} 只 {time.time() - t0:.0f}s", flush=True)
print("ALL_DONE", flush=True)
