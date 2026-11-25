# 现金三档回测（《467》口径）。用法: python3 -I cash_bt.py <fred目录> <yahoo_idx.json.gz> <输出json>
import sys, csv, gzip, json, datetime as dt, math
fred, idxp, outp = sys.argv[1:4]
def rd(s):
    out={}
    for r in csv.DictReader(open(f"{fred}/{s}.csv")):
        v=r[s]
        if v not in ('','.'): out[r['observation_date']]=float(v)
    return out
BAA=rd('BAA10Y'); HY=rd('BAMLH0A0HYM2') if __import__('os').path.exists(f"{fred}/BAMLH0A0HYM2.csv") else {}
SAHM=rd('SAHMREALTIME'); CORE=rd('CPILFESL'); FF=rd('FEDFUNDS'); TB=rd('DGS3MO')
# 标普（价格指数）
g=json.load(gzip.open(idxp))['^GSPC']['chart']['result'][0]
ts=g['timestamp']; cl=g['indicators']['quote'][0]['close']
px={}
for t,c in zip(ts,cl):
    if c: px[dt.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d')]=c
days=sorted(d for d in px if d>='1992-01-01')
DIV=0.02  # 分红近似：每年 2%（价格指数不含分红，标注为近似）

# 1) HY 4.5% 对应的 BAA10Y：重叠期线性回归
ov=[(HY[d],BAA[d]) for d in HY if d in BAA]
n=len(ov); mx=sum(a for a,_ in ov)/n; my=sum(b for _,b in ov)/n
b=sum((a-mx)*(c-my) for a,c in ov)/sum((a-mx)**2 for a,_ in ov); a0=my-b*mx
map45=a0+b*4.5
corr=sum((a-mx)*(c-my) for a,c in ov)/math.sqrt(sum((a-mx)**2 for a,_ in ov)*sum((c-my)**2 for _,c in ov))
hyr=(min(x for x,_ in ov),max(x for x,_ in ov)); baar=(min(y for _,y in ov),max(y for _,y in ov))

def lastv(series,d,lagdays=0):
    # 取 d 之前（含）已经能拿到的最新值；月度数据按「下个月 15 号发布」处理
    best=None
    for k in series:
        pass
    return best
# 月度：观测月 m 的数据，在 m+1 月 15 日后可用
def monthly_avail(series):
    av={}
    for k,v in series.items():
        y,m,_=map(int,k.split('-')); m+=1
        if m==13: y+=1; m=1
        av[f"{y:04d}-{m:02d}-15"]=v
    return sorted(av.items())
SAHMa=monthly_avail(SAHM); FFa=monthly_avail(FF)
# 核心 CPI：近 3 个月年化 vs 前 3 个月年化（回落=近 < 前）
ck=sorted(CORE); cpi3={}
for i in range(6,len(ck)):
    r3=(CORE[ck[i]]/CORE[ck[i-3]])**4-1; p3=(CORE[ck[i-3]]/CORE[ck[i-6]])**4-1
    cpi3[ck[i]]=(r3,p3)
CPIa=monthly_avail(cpi3)
ffl=monthly_avail({k:v for k,v in FF.items()})
def asof(arr,d):
    lo=None
    for k,v in arr:
        if k<=d: lo=v
        else: break
    return lo
def asof_hist(arr,d,back):
    ks=[v for k,v in arr if k<=d]
    return ks[-1-back] if len(ks)>back else None
baad=sorted(BAA)
def baa_series_upto(d,k):
    # 最近 k 个交易日的 BAA10Y
    import bisect
    i=bisect.bisect_right(baad,d)
    return [BAA[x] for x in baad[max(0,i-k):i]]

def regime(d,thr):
    s=asof(SAHMa,d); w=baa_series_upto(d,10)  # 两周 ≈ 10 个交易日
    if (s is not None and s>=0.5) or (len(w)==10 and min(w)>thr): return '下行'
    c=asof(CPIa,d); f0=asof(FFa,d); f3=asof_hist(FFa,d,3)
    w26=baa_series_upto(d,130)
    narrowing = len(w26)>=60 and w26[-1] < sum(w26)/len(w26)
    if c and f0 is not None and f3 is not None and c[0]<c[1] and f0<=f3+0.05 and narrowing: return '上行'
    return '基准'

# 每月第一个交易日调仓
def run(thr, alloc, start, end):
    eq=1.0; peak=1.0; mdd=0.0; cur=None; seq=[]
    prev=None; w=None; counts={'上行':0,'基准':0,'下行':0}
    ds=[d for d in days if start<=d<=end]
    for i,d in enumerate(ds):
        if prev is not None:
            r=px[d]/px[prev]-1 + DIV/252
            tb=TB.get(prev) or tb_last
            cash_r=tb/100/252
            eq*= 1+ (1-w)*r + w*cash_r
            peak=max(peak,eq); mdd=min(mdd,eq/peak-1)
        if prev is None or d[:7]!=prev[:7]:
            rg=regime(d,thr) if isinstance(alloc,dict) else None
            w=alloc[rg] if isinstance(alloc,dict) else alloc
            if rg: counts[rg]+=1
        globals()['tb_last']=TB.get(d) or globals().get('tb_last',3.0)
        prev=d
    yrs=(dt.date.fromisoformat(ds[-1])-dt.date.fromisoformat(ds[0])).days/365.25
    cagr=eq**(1/yrs)-1
    return dict(cagr=round(cagr*100,2), mdd=round(mdd*100,1), ratio=round(cagr/abs(mdd),2) if mdd else None, months=counts)
tb_last=3.0
P=[('1993–2007','1993-01-01','2007-12-31'),('2008–2021','2008-01-01','2021-12-31'),('2022–（封存，不进统计）','2022-01-01','2026-12-31')]
res={'HY4.5对应BAA10Y':round(map45,2),'回归':dict(n=n,slope=round(b,3),corr=round(corr,3),HY范围=hyr,BAA范围=baar),'结果':{}}
base={'上行':0.10,'基准':0.25,'下行':0.40}
thrs=[round(map45-0.25,2),round(map45,2),round(map45+0.25,2)]
for name,s,e in P:
    R={}
    R['一直满仓']=run(None,0.0,s,e)
    R['一直留25%现金']=run(None,0.25,s,e)
    for thr in thrs:
        R[f'三档 10/25/40 · BAA门槛{thr}']=run(thr,base,s,e)
    thr=thrs[1]
    for k,lst in [('上行',[0.0,0.2]),('基准',[0.15,0.35]),('下行',[0.30,0.50])]:
        for v in lst:
            a=dict(base); a[k]=v
            R[f'三档 {k}改{int(v*100)}% · 门槛{thr}']=run(thr,a,s,e)
    res['结果'][name]=R
json.dump(res,open(outp,'w'),ensure_ascii=False,indent=1)
print(json.dumps(res,ensure_ascii=False,indent=1))
