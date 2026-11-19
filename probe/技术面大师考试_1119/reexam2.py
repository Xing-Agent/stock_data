exec(open('trig2.py').read().split('cfgs=')[0])
r=pd.read_csv('/home/claude/work/ta_exam/results2.csv')
nm={'SOXL':'SOXL 1H','TQQQ':'TQQQ 1H','KORU':'KORU 1H','BTC':'BTC 1H','ETH':'ETH 1H'}
for lab,kw in [('卡v0.3(含箱体闸)',dict(trig='C',rrmode='gem',f_box=True,tk_rules=True,f_n=True)),('卡v0.3去箱体闸',dict(trig='C',rrmode='gem',tk_rules=True,f_n=True)),('原卡v0',dict(trig='A',rrmode='tp1_2'))]:
    T={n:run2(S[n],n,**kw) for n in set(nm.values())}
    rows=[]
    for _,x in r.iterrows():
        n=nm[x.tk];t=pd.Timestamp(x.time+':00',tz='UTC');end=str(t+pd.Timedelta(hours=72))[:16]
        tr=T[n];tr=tr[(tr.t>x.time)&(tr.t<=end)] if len(tr) else tr
        if len(tr): rows.append({'turn':x.turn,'tk':x.tk,'time':x.time,'at':tr.t.iloc[0],'dir':tr.dir.iloc[0],'R':tr.R.iloc[0],'tp1':tr.tp1.iloc[0]})
    o=pd.DataFrame(rows);u=o.drop_duplicates(['tk','at'])
    print(f'\n{lab}: 45个时点里 {len(o)} 个在之后3天出了进场，去重后：{stats(u)}')
    print(u[['turn','tk','time','at','dir','R']].to_string())
