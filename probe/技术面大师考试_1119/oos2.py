exec(open('oos.py').read().split('cfg={')[0])
cfg={'早鸟+双门槛':dict(trig='C',rrmode='gem'),'早鸟+双门槛+前两次':dict(trig='C',rrmode='gem',f_n=True),'早鸟+双门槛+分票':dict(trig='C',rrmode='gem',tk_rules=True),'早鸟+到TP1≥2(原卡)':dict(trig='C',rrmode='tp1_2'),'推荐去箱体+均线拉开':dict(trig='C',rrmode='gem',tk_rules=True,f_n=True,f_ema=True)}
for nm,kw in cfg.items():
    x=pd.concat([run2(d,n,**kw) for n,d in S.items()]);oos=x[x.t<'2026-06'];x['y']=x.t.str[:4]
    print(f'{nm:14s} 没用过的段: {stats(oos)} | 2022: {x[x.y=="2022"].R.mean():+.2f}R')
