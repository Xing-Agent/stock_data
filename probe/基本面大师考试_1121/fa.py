import json,gzip,sys,datetime as dt
R='/home/claude/xing-agent-stock_data/'
def load(t):
    f=json.load(gzip.open(R+f'fundamentals_ext/{t}/fundamentals.json.gz'))['financial_versions']
    import os
    fp=R+f'market_ext_1105/{t}/daily.json.gz'
    if not os.path.exists(fp): return f,[{'close':float('nan'),'high':float('nan'),'date':'缺'}]
    p=json.load(gzip.open(fp))
    bars=p.get('bars') or p.get('data') or [v for k,v in p.items() if isinstance(v,list)][0]
    return f,bars
def D(s): return dt.date.fromisoformat(s[:10])
def series(f,m):
    out={}
    for e in f.get(m,[]):
        if e.get('value') is None: continue
        ps=e.get('period_start'); pe=e['period_end']
        dur=(D(pe)-D(ps)).days if ps else 0
        k=(ps,pe)
        if k not in out or e.get('filed_at','')>out[k]['filed_at']: out[k]=dict(v=float(e['value']),dur=dur,pe=pe,ps=ps,filed_at=e.get('filed_at',''))
    return list(out.values())
def ttm(f,m):
    s=series(f,m)
    if not s: return None,None
    fy=sorted([x for x in s if 350<=x['dur']<=380],key=lambda x:x['pe'])
    last=max(s,key=lambda x:(x['pe'],x['dur']))
    if 350<=last['dur']<=380: return last['v'],last['pe']
    if not fy: return None,None
    F=fy[-1]
    if last['pe']<=F['pe']: return F['v'],F['pe']
    E=D(last['pe']); d=last['dur']
    pr=[x for x in s if abs((E-D(x['pe'])).days-365)<=10 and abs(x['dur']-d)<=10]
    if not pr: return None,None
    return F['v']+last['v']-pr[0]['v'],last['pe']
def inst(f,m):
    s=series(f,m)
    if not s: return None,None
    x=max(s,key=lambda x:x['pe']); return x['v'],x['pe']
def fyvals(f,m):
    s=sorted([x for x in series(f,m) if 350<=x['dur']<=380],key=lambda x:x['pe'])
    return [(x['pe'][:4],x['v']) for x in s]
REF={}
def g(f,*ms,kind=inst):
    best=(None,None)
    for m in ms:
        v,pe=kind(f,m)
        if v is None: continue
        if best[0] is None or pe>best[1]: best=(v,pe)   # 取最新的那个标签，不取过时的
    return best
def report(t):
    f,b=load(t); px=b[-1]['close']; pdate=b[-1]['date']
    hi52=max(x['high'] for x in b[-252:])
    rev,rpe=g(f,'Revenue',kind=ttm); gp,_=g(f,'GrossProfit',kind=ttm); cor,_=g(f,'CostOfRevenue',kind=ttm)
    if gp is None and rev and cor: gp=rev-cor
    ni,_=g(f,'NetIncome',kind=ttm); ocf,_=g(f,'OperatingCashFlow',kind=ttm)
    capex,_=g(f,'PaymentsToAcquirePropertyPlantAndEquipment','PaymentsToAcquireProductiveAssets',kind=ttm)
    ebit,_=g(f,'OperatingIncomeLoss','EBIT',kind=ttm); da,_=g(f,'DepreciationDepletionAndAmortization','DepreciationAmortizationAndAccretionNet',kind=ttm)
    eq,epe=g(f,'StockholdersEquity'); ca,_=g(f,'CurrentAssets'); cl,_=g(f,'CurrentLiabilities')
    ltd,_=g(f,'LongTermDebt'); std,spe=g(f,'ShortTermBorrowings','DebtCurrent','LongTermDebtCurrent','ShortTermDebt')
    if spe and epe and spe<epe: std=0
    cash,cpe=g(f,'CashCashEquivalentsAndShortTermInvestments')
    if cash is None or cpe<epe:
        c0,cpe0=g(f,'CashAndCashEquivalentsAtCarryingValue'); sti=0
        for m in ('ShortTermInvestments','MarketableSecuritiesCurrent','AvailableForSaleSecuritiesDebtSecuritiesCurrent'):
            v,p=inst(f,m)
            if v and p==cpe0: sti=max(sti,v)
        cash=(c0 or 0)+sti
    gw,_=g(f,'Goodwill'); ia,_=g(f,'IntangibleAssetsNetExcludingGoodwill')
    sh,_=g(f,'WeightedAverageDilutedShares',kind=inst)
    debt=(ltd or 0)+(std or 0); mc=px*sh if sh else None
    ebitda=(ebit or 0)+(da or 0) if ebit is not None else None
    fcf=ocf-capex if ocf is not None and capex is not None else None
    ev=mc+debt-(cash or 0) if mc else None
    out=dict(t=t,price=px,price_date=pdate,fin_period_end=rpe,bal_period_end=epe,mktcap_bn=mc and mc/1e9,
      ev_ebitda=ev/ebitda if ev and ebitda else None,fcf_yield=fcf/mc if fcf and mc else None,
      pb=mc/eq if mc and eq else None,netdebt_ebitda=(debt-(cash or 0))/ebitda if ebitda else None,
      current_ratio=ca/cl if ca and cl else None,roe=ni/eq if ni and eq else None,
      pe=mc/ni if mc and ni else None,gross_margin=gp/rev if gp and rev else None,
      ocf_over_ni=ocf/ni if ocf and ni else None,de=debt/eq if eq else None,p_fcf=mc/fcf if fcf and mc else None,
      gw_over_eq=gw/eq if gw and eq else None,from_52w_high=px/hi52-1,ocf_ttm_bn=ocf and ocf/1e9,fcf_ttm_bn=fcf and fcf/1e9)
    rv=fyvals(f,'Revenue'); sv=fyvals(f,'WeightedAverageDilutedShares')
    out['rev_fy']=rv[-6:]; out['shares_fy']=[(y,round(v/1e6,1)) for y,v in sv[-4:]]
    return out
if __name__=='__main__':
    for t in sys.argv[1:]:
        o=report(t)
        print('=====',t)
        for k,v in o.items(): print(f'  {k}: {round(v,3) if isinstance(v,float) else v}')
