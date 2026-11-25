# v2：下行门槛改成「相对」口径（固定水平门槛跨年代不可比）。A=BAA10Y 高于过去5年的第p分位；B=BAA10Y 近63个交易日走阔≥x
import sys,runpy,bisect,json
sys.argv=[sys.argv[0]]+sys.argv[1:4]
src=open('cash_bt.py').read().split("tb_last=3.0\nP=")[0]
g={'__name__':'x'}; exec(src.replace("json.dump(res","pass #"),g)
BAA,baad,SAHMa,CPIa,FFa,asof,asof_hist,baa_series_upto=[g[k] for k in ['BAA','baad','SAHMa','CPIa','FFa','asof','asof_hist','baa_series_upto']]
cache={}
def pct_ok(d,p):
    i=bisect.bisect_right(baad,d); win=[BAA[x] for x in baad[max(0,i-1260):i]]
    if len(win)<500: return False
    s=sorted(win); q=s[int(p*(len(s)-1))]
    last10=win[-10:]; return min(last10)>q
def wid_ok(d,x):
    i=bisect.bisect_right(baad,d)
    if i<64: return False
    return BAA[baad[i-1]]-BAA[baad[i-64]]>=x
def mk(kind,par):
    def regime(d,thr=None):
        s=asof(SAHMa,d)
        stress = pct_ok(d,par) if kind=='分位' else wid_ok(d,par)
        if (s is not None and s>=0.5) or stress: return '下行'
        c=asof(CPIa,d); f0=asof(FFa,d); f3=asof_hist(FFa,d,3); w26=baa_series_upto(d,130)
        nar=len(w26)>=60 and w26[-1]<sum(w26)/len(w26)
        if c and f0 is not None and f3 is not None and c[0]<c[1] and f0<=f3+0.05 and nar: return '上行'
        return '基准'
    return regime
g['tb_last']=3.0
P=[('1993–2007','1993-01-01','2007-12-31'),('2008–2021','2008-01-01','2021-12-31'),('2022–（封存）','2022-01-01','2026-12-31')]
base={'上行':0.10,'基准':0.25,'下行':0.40}
out={}
for name,s,e in P:
    R={'一直满仓':g['run'](None,0.0,s,e),'一直留25%现金':g['run'](None,0.25,s,e)}
    for kind,pars in [('分位',[0.80,0.85,0.90]),('走阔',[0.4,0.5,0.6])]:
        for p in pars:
            g['regime']=mk(kind,p); R[f'三档10/25/40 {kind}{p}']=g['run'](0,base,s,e)
    g['regime']=mk('分位',0.85)
    for k,lst in [('上行',[0.0,0.2]),('基准',[0.15,0.35]),('下行',[0.30,0.50])]:
        for v in lst:
            a=dict(base);a[k]=v;R[f'分位0.85 {k}改{int(v*100)}%']=g['run'](0,a,s,e)
    out[name]=R
json.dump(out,open('result_v2_1125.json','w'),ensure_ascii=False,indent=1)
for p,R in out.items():
  print('==',p)
  for k,v in R.items(): print(f'  {k:24s} 年化{v["cagr"]:6.2f} 最深{v["mdd"]:6.1f} 比{v["ratio"]} {v["months"]}')
