# 每年全市场成交额排名(修正版过滤),给口径对比用
import importlib.util, csv, os, sys, json
from collections import defaultdict
os.chdir("/home/claude/sd4/probe/survivorship_1029")
spec=importlib.util.spec_from_file_location("C","建池-规模档-C口径-1030.py"); C=importlib.util.module_from_spec(spec); spec.loader.exec_module(C)
import glob
files=sorted(glob.glob("/home/claude/pituni/day/*.csv.gz")); dates=[os.path.basename(f)[:10] for f in files]; by=dict(zip(dates,files))
ETF=set(open("/home/claude/etf_tickers.txt").read().split())|C.KNOWN_ETF_SEED
SEG=defaultdict(list)
for r in csv.DictReader(open("../xing-pit-universe-20261029-025954/pit_company_segments.csv")): SEG[r["ticker"]].append((r["first_seen"],r["last_seen"]))
import re
def noncomp_fixed(sym):
    base,_,suf=sym.partition("."); sh=suf.split(".")[0] if suf else ""
    if sh.startswith("W") or sh in ("U","R","CL"): return True
    if len(base)==5 and base.isalpha() and base[4] in "WUR": return True
    if re.search(r"[a-z]", sym): return True            # 优先股在这批数据里写作 ABCpA(小写 p)
    return sym in C.KNOWN_DEAD_PRODUCTS
def etf_now(t,d0):
    if t not in ETF: return False
    ss=sorted(SEG.get(t,[]))
    if not ss: return True
    cur=[x for x in ss if x[0]<=d0<=x[1]]
    return bool(cur) and cur[0]==ss[-1]
out=[]
for y in range(2015,2027):
    d0=[d for d in dates if d>=f"{y}-01-01"][0]; i=dates.index(d0); win=dates[i-60:i]
    on={r["ticker"] for r in C.read(by[d0])}
    dv=defaultdict(float); nd=defaultdict(int)
    for d in win:
        for r in C.read(by[d]):
            t=r["ticker"]
            if t not in on: continue
            v,_=C.dollar_vol(r)
            if v>0: dv[t]+=v; nd[t]+=1
    cand=sorted([(t,dv[t]/nd[t]) for t in dv if nd[t]>=30 and not noncomp_fixed(t) and not etf_now(t,d0)], key=lambda x:-x[1])
    for k,(t,a) in enumerate(cand): out.append((y,k+1,t,a))
    print(y,len(cand),flush=True)
import polars as pl
pl.DataFrame(out,schema=["year","rank","symbol","adv"],orient="row").write_parquet("/home/claude/seg/ranks_fixed.parquet")
