from ev3b import *
u=pd.read_csv('univ.csv').head(200)
cr=[]
for t,f in [('BTC','/home/claude/xing-agent-stock_data/market_tech_exam_1118/BTC_日线_Coinbase.csv'),('ETH','/home/claude/xing-agent-stock_data/market_tech_exam_1118/ETH_日线_Coinbase.csv')]:
    x=pd.read_csv(f);x['time']=pd.to_datetime(x.time,utc=True).dt.tz_localize(None);cr.append((t,x.set_index('time')))
stk=[(t,load(t)) for t in u.t]
for lab,kw in [('144/169日指数均线',dict(spans=(144,169))),('100/200日指数均线',dict(spans=(100,200))),('50/200日简单均线',dict(spans=(50,200),sma=True)),('200/250日指数均线',dict(spans=(200,250))),('60/120日指数均线',dict(spans=(60,120)))]:
    C=pd.DataFrame(sum([analyze3(t,x,**kw) for t,x in cr],[]));Sx=pd.DataFrame(sum([analyze3(t,x,**kw) for t,x in stk],[]))
    print(f'{lab:16s} 币: {len(C)}笔 每笔{C.R.mean():+.2f}R | 美股(前200只): {len(Sx)}笔 每笔{Sx.R.mean():+.2f}R  ≥3顶+背离: {Sx[(Sx.顶数>=3)&Sx.背离].R.mean():+.2f}R')
