import pandas as pd, numpy as np
r=pd.read_csv('/home/claude/work/ta_exam/results2.csv')
x=pd.read_csv('combo.csv'); x['tk']=x['票'].astype(str).str.replace(' 1H','')
rows=[]
for _,m in r.iterrows():
    t=pd.Timestamp(m.time+':00',tz='UTC'); end=str(t+pd.Timedelta(hours=72))[:16]
    tr=x[(x.tk==m.tk)&(x.t>m.time)&(x.t<=end)]
    d=dict(turn=m.turn,tk=m.tk,time=m.time,old=m.act,up=m['max_up%'],dn=m['max_dn%'],ret=m['ret%'])
    if len(tr): f=tr.iloc[0]; d.update(entry=f.t,dir=f.dir,R=f.R,src=f.src,regime=f.regime)
    rows.append(d)
o=pd.DataFrame(rows)
print('45个时点:',len(o),' 之后3天出了进场:',o.entry.notna().sum())
u=o.dropna(subset=['entry']).drop_duplicates(['tk','entry'])
print('去重后笔数',len(u),'合计R %.2f 每笔 %.2f 胜(>0) %d'%(u.R.sum(),u.R.mean(),(u.R>0).sum()))
print(u.groupby(['src','dir']).R.agg(['count','sum','mean']).round(2))
print(o.groupby(o.entry.notna()).agg(n=('turn','size'),up=('up','median'),dn=('dn','median'),ret=('ret','median')).round(1))
print(u[['turn','tk','time','entry','dir','src','regime','R']].to_string())
o.to_csv('reexam3_45.csv',index=False)
