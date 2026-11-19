exec(open('gem2.py').read().split("go('基准(v0.2)',None)")[0])
def reg(dd):
    e20=dd.close.ewm(span=20).mean();e50=dd.close.ewm(span=50).mean()
    up=(dd.close>e20)&(e20>e50)&(e20>e20.shift(3));dn=(dd.close<e20)&(e20<e50)&(e20<e20.shift(3))
    r=pd.Series('震荡',index=dd.index);r[up]='上涨';r[dn]='下跌';return r.shift(1)
def mk(lr):
    def f(n,d):
        r=onto(reg(DD[PAR[n]]),d.index);I=h4info(d);pos=((d.close-I.L120)/(I.H120-I.L120)).values
        la=(r=='上涨')|((r=='震荡')&(pos<=0.33)) if lr['range_long'] else (r=='上涨')
        sa=np.ones(len(d),bool)
        if lr['range_short_top']: sa=sa&~((r=='震荡')&(pos<0.67))
        if lr['up_short']=='none': sa=sa&(r!='上涨')
        return la,sa
    return f
def score(lab,lr):
    xs=[]
    for n in T:
        d=S[n+' 1H'];la,sa=mk(lr)(n,d);t=run2(d,n+' 1H',**base,la=la,sa=sa)
        if len(t):
            rr=onto(reg(DD[PAR[n]]),pd.DatetimeIndex(pd.to_datetime(t.t,utc=True)));t['regime']=rr
        xs.append(t)
    x=pd.concat(xs);
    if lr['up_short']=='half': x.loc[(x.dir=='空')&(x.regime=='上涨'),'R']*=0.5
    x['y']=x.t.str[:4];o=x[x.t<'2026-06']
    print(f'{lab:28s} {stats(o)}\n{"":28s} 按年: '+' | '.join(f"{y}:{len(g)}笔{g.R.mean():+.2f}" for y,g in x.groupby('y')))
    print(f'{"":28s} 分行情: '+' | '.join(f"{a}{b}:{len(g)}笔{g.R.mean():+.2f}" for (a,b),g in o.groupby(['dir','regime'])))
    return x
score('③现状(上涨才做多,空不限)',dict(range_long=False,range_short_top=False,up_short='full'))
score('+上涨里做空半仓',dict(range_long=False,range_short_top=False,up_short='half'))
score('+上涨里不做空',dict(range_long=False,range_short_top=False,up_short='none'))
score('+震荡底部(下1/3)做多',dict(range_long=True,range_short_top=False,up_short='full'))
score('+震荡只在顶部(上1/3)做空',dict(range_long=False,range_short_top=True,up_short='full'))
x=score('Lin框架:上涨多/半仓空,震荡底多顶空',dict(range_long=True,range_short_top=True,up_short='half'))
x.to_csv('lin_frame.csv',index=False)
score('Lin框架但震荡空不限顶部',dict(range_long=True,range_short_top=False,up_short='half'))
