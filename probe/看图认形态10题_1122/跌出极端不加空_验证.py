exec(open('gem2.py').read().split("go('基准(v0.2)',None)")[0])
import numpy as np
x=pd.read_csv('combo.csv'); x['tk']=x['票'].str.split().str[0]
rows=[]
for k,g in x.groupby('tk'):
    dd=DD[k] if k in DD else DD[PAR.get(k,k)]
    tr=pd.concat([dd.high-dd.low,(dd.high-dd.close.shift()).abs(),(dd.low-dd.close.shift()).abs()],axis=1).max(axis=1)
    atr=tr.rolling(14).mean(); e20=dd.close.ewm(span=20).mean()
    dist=((dd.close-e20)/atr).shift(1)          # 前一天收盘离 20 日线几倍 ATR（不偷看）
    drop=((dd.close-dd.close.shift())/atr).shift(1)  # 前一天单日涨跌几倍 ATR
    for _,r in g.iterrows():
        ts=pd.Timestamp(r.t[:10],tz='UTC')
        rows.append(dict(r, dist=dist.asof(ts), dj=drop.asof(ts)))
o=pd.DataFrame(rows); s=o[o.dir=='空'].copy()
s['极端']=(s.dist<-2.5)|(s.dj<-3)
s['离线']=pd.cut(s.dist,[-99,-2.5,-1.5,-0.5,99],labels=['<-2.5','-2.5~-1.5','-1.5~-0.5','>-0.5'])
print('空单',len(s)); print(s.groupby('极端').R.agg(['count','mean','sum']).round(2))
print(s.groupby('离线').R.agg(['count','mean','sum']).round(2))
print(s.groupby([s.t.str[:4]>='2015','极端']).R.agg(['count','mean']).round(2))
m=o[o.dir=='多'].copy(); m['极端']=(m.dist>2.5)|(m.dj>3)
print('多单 离20日线很远(上方)'); print(m.groupby('极端').R.agg(['count','mean','sum']).round(2))
o.to_csv('ext_out.csv',index=False)
