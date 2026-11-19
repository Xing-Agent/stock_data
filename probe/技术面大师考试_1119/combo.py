exec(open('rng.py').read().split("go('震荡·假跌破·目标中轴+对边')")[0])
exec("def mk(lr):"+open('lin.py').read().split("def mk(lr):")[1].split("score('③现状")[0])
xa=pd.concat([run_range(S[n+' 1H'],n,REG[n],box_n=60) for n in T]);xa=xa[xa.dir=='多'];xa['src']='震荡底部假跌破做多'
xs=[]
for n in T:
    d=S[n+' 1H'];la,sa=mk(dict(range_long=False,range_short_top=False,up_short='half'))(n,d);t=run2(d,n+' 1H',**base,la=la,sa=sa)
    t['regime']=onto(reg(DD[PAR[n]]),pd.DatetimeIndex(pd.to_datetime(t.t,utc=True)));xs.append(t)
xb=pd.concat(xs);xb.loc[(xb.dir=='空')&(xb.regime=='上涨'),'R']*=0.5;xb['src']='顺势回踩/反抽'
x=pd.concat([xa,xb]).sort_values('t');x['y']=x.t.str[:4];o=x[x.t<'2026-06']
print('合计',stats(o))
for s,g in o.groupby('src'): print('  ',s,stats(g))
print('  按年: '+' | '.join(f"{y}:{len(g)}笔 合计{g.R.sum():+.1f}R" for y,g in x.groupby('y')))
x.to_csv('combo.csv',index=False)
