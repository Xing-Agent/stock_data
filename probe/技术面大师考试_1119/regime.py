exec(open('gem2.py').read().split("go('基准(v0.2)',None)")[0])
x=pd.read_csv('ema_best.csv')
def reg(dd):
    e20=dd.close.ewm(span=20).mean();e50=dd.close.ewm(span=50).mean()
    up=(dd.close>e20)&(e20>e50)&(e20>e20.shift(3));dn=(dd.close<e20)&(e20<e50)&(e20<e20.shift(3))
    r=pd.Series('震荡',index=dd.index);r[up]='上涨';r[dn]='下跌';return r.shift(1)
R={n:reg(DD[PAR[n]]) for n in T}
x['tk']=x.票.str.split().str[0]
x['regime']=[R[k].asof(pd.Timestamp(t[:10],tz='UTC')) for k,t in zip(x.tk,x.t)]
o=x[x.t<'2026-06']
print(o.groupby(['dir','regime']).R.agg(['count','mean','sum']).round(2))
print('\n2022:');print(o[o.t.str[:4]=='2022'].groupby(['dir','regime']).R.agg(['count','mean','sum']).round(2))
x.to_csv('ema_best_regime.csv',index=False)
