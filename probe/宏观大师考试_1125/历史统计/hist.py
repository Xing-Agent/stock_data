# 宏观考试 46/47/48/50 题的历史统计。用法: python3 -I hist.py <fred目录> <yahoo_idx.json.gz>
import sys,csv,gzip,json,datetime as dt,bisect
F,Y=sys.argv[1:3]
def rd(s):
    o={}
    for r in csv.DictReader(open(f"{F}/{s}.csv")):
        v=r[s]
        if v not in('','.'): o[r['observation_date']]=float(v)
    return o
g=json.load(gzip.open(Y))['^GSPC']['chart']['result'][0]
px={}
for t,c in zip(g['timestamp'],g['indicators']['quote'][0]['close']):
    if c: px[dt.datetime.utcfromtimestamp(t).strftime('%Y-%m-%d')]=c
D=sorted(px)
def at(d):
    i=bisect.bisect_left(D,d); return D[min(i,len(D)-1)]
def ret(d,months):
    d0=at(d); y,m,dd=map(int,d0.split('-')); m+=months; y+=(m-1)//12; m=(m-1)%12+1
    d1=f"{y:04d}-{m:02d}-{min(dd,28):02d}"
    if d1>D[-1]: return None
    return round((px[at(d1)]/px[d0]-1)*100,1)
def mdd(d,months):
    d0=at(d); y,m,dd=map(int,d0.split('-')); m+=months; y+=(m-1)//12; m=(m-1)%12+1
    d1=f"{y:04d}-{m:02d}-28"; seg=[px[x] for x in D if d0<=x<=d1]
    if not seg: return None
    return round((min(seg)/seg[0]-1)*100,1)
REC=rd('USREC'); rk=sorted(REC)
def rec_within(d,months):
    y,m,_=map(int,d.split('-')); out=[]
    for k in range(0,months+1):
        mm=m+k; yy=y+(mm-1)//12; mm=(mm-1)%12+1
        key=f"{yy:04d}-{mm:02d}-01"
        if REC.get(key)==1: return True
    return False
def rec_start_after(d):
    prev=0
    for k in rk:
        if k>=d[:7]+'-01' and REC[k]==1 and prev==0: return k
        prev=REC[k]
    return None
out={}
# 46 首次降息：公认日期（FOMC 宣布日），每个降息周期的第一刀
cuts=['1989-06-06','1995-07-06','1998-09-29','2001-01-03','2007-09-18','2019-07-31','2024-09-18']
rows=[]
for c in cuts:
    r12=ret(c,12); rows.append(dict(日期=c,之后12个月=r12,之后6个月=ret(c,6),期间最深=mdd(c,12),一年内衰退=rec_within(c,12)))
out['46首次降息']=rows
# 47 2s10s 倒挂：开始日=连续5天<0，且前180个交易日没有倒挂过
T=rd('T10Y2Y'); tk=sorted(T); inv=[]; last_inv=None
for i,k in enumerate(tk):
    if i>=4 and all(T[tk[j]]<0 for j in range(i-4,i+1)):
        if last_inv is None or (dt.date.fromisoformat(k)-dt.date.fromisoformat(last_inv)).days>365:
            inv.append(tk[i-4])
        last_inv=k
rows=[]
for s in inv:
    rs=rec_start_after(s)
    lag=None
    if rs: lag=round((dt.date.fromisoformat(rs)-dt.date.fromisoformat(s)).days/30.4)
    rows.append(dict(倒挂开始=s,下一次衰退开始=rs,间隔月=lag,倒挂后12个月标普=ret(s,12),倒挂后24个月标普=ret(s,24)))
out['47倒挂']=rows
# 48 油价暴涨：WTI 6个月涨 ≥50%，事件之间至少隔 12 个月
W=rd('DCOILWTICO'); wk=sorted(W); ev=[]; lastev=None
for i,k in enumerate(wk):
    j=bisect.bisect_left(wk,(dt.date.fromisoformat(k)-dt.timedelta(days=182)).isoformat())
    if j<i and W[wk[j]]>0 and W[k]/W[wk[j]]-1>=0.5:
        if not ev or (dt.date.fromisoformat(k)-dt.date.fromisoformat(ev[-1])).days>365:
            ev.append(k)
out['48油价暴涨']=[dict(触发日=e,WTI=W[e],之后6个月标普=ret(e,6),之后12个月标普=ret(e,12),期间最深=mdd(e,12),一年内衰退=rec_within(e,12)) for e in ev]
# 50 美元见顶：广义美元指数（2006 起）52周新高后一年内跌 ≥8% 的高点
U=rd('DTWEXBGS'); uk=sorted(U); peaks=[]
for i,k in enumerate(uk):
    j0=bisect.bisect_left(uk,(dt.date.fromisoformat(k)-dt.timedelta(days=365)).isoformat())
    j1=bisect.bisect_right(uk,(dt.date.fromisoformat(k)+dt.timedelta(days=365)).isoformat())
    win=[U[x] for x in uk[j0:j1]]
    if U[k]==max(win) and min(U[x] for x in uk[i:j1])<=U[k]*0.92:
        if not peaks or (dt.date.fromisoformat(k)-dt.date.fromisoformat(peaks[-1])).days>365: peaks.append(k)
out['50美元见顶']=[dict(高点=p,美元指数=U[p],之后12个月标普=ret(p,12),之后12个月黄金=None) for p in peaks]
print(json.dumps(out,ensure_ascii=False,indent=1))
json.dump(out,open('hist_result.json','w'),ensure_ascii=False,indent=1)
