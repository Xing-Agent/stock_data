exec(open('top.py').read().split("print('== 震荡里顶部做空 ==')")[0])
S4={k:v.resample('4h').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna() for k,v in S.items()}
REG4={n:onto(reg(DD[PAR[n]]),S4[n+' 1H'].index) for n in T}
def go4(lab,**kw):
    x=pd.concat([run_top(S4[n+' 1H'],n,REG4[n],hold=30,**kw) for n in T]);x['y']=x.t.str[:4];o=x[x.t<'2026-06']
    print(f'{lab:26s} {stats(o)}');return x
for allow in [('震荡',),('上涨',),('震荡','上涨','下跌')]:
    print('==',allow)
    for need in [('sfp',),('sfp','div'),'any2',('div',)]:
        go4(f'4小时·空·{need}',need=need,allow=allow,box_n=120)
    go4('4小时·底多·假跌破',need=('sfp',),allow=allow,side='L',box_n=120)
