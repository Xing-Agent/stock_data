import pandas as pd, numpy as np, sys, warnings;warnings.filterwarnings('ignore')
D1='/home/claude/xing-agent-stock_data/market_tech_exam_1117/';D2='/home/claude/xing-agent-stock_data/market_tech_exam_1118/'
def L(p):
    d=pd.read_csv(p);d['time']=pd.to_datetime(d['time'],utc=True);d=d.set_index('time').sort_index();return d[~d.index.duplicated()]
def cat(a,b):
    x=L(a)
    try: y=L(b);x=pd.concat([x,y[y.index>x.index[-1]]])
    except Exception: pass
    return x
SETS={
 'SOXL 1H':cat(D1+'SOXL_1h_含盘前盘后.csv',D2+'SOXL_1h_含盘前盘后_补1117起.csv'),
 'TQQQ 1H':cat(D1+'TQQQ_1h_含盘前盘后.csv',D2+'TQQQ_1h_含盘前盘后_补1117起.csv'),
 'KORU 1H':cat(D1+'KORU_1h_含盘前盘后_拆股折算.csv',D2+'KORU_1h_含盘前盘后_补1117起.csv'),
 'BTC 1H':cat(D1+'BTC_1h.csv',D2+'BTC_1h_补1117起.csv'),
 'ETH 1H':cat(D1+'ETH_1h.csv',D2+'ETH_1h_补1117起.csv'),
 'BTC 日线(2017-)':L(D2+'BTC_日线_Coinbase.csv'),
 'ETH 日线(2017-)':L(D2+'ETH_日线_Coinbase.csv'),
}
def atr(d,n=14):
    tr=pd.concat([d.high-d.low,(d.high-d.close.shift()).abs(),(d.low-d.close.shift()).abs()],axis=1).max(axis=1);return tr.rolling(n).mean()
def zigzag(d,k):
    a=atr(d).bfill().values;H=d.high.values;Lo=d.low.values;piv=[];dirn=0;ei=0;ev=H[0]
    for i in range(1,len(d)):
        if dirn>=0:
            if H[i]>ev or dirn==0 and H[i]>ev: ev=H[i];ei=i;dirn=1 if dirn==0 else dirn
            if dirn==1 and Lo[i]<ev-k*a[ei]: piv.append((ei,ev,'H'));dirn=-1;ev=Lo[i];ei=i;continue
        if dirn<=0:
            if Lo[i]<ev or dirn==0: 
                if dirn==0 and Lo[i]>=ev: pass
                else: ev=Lo[i];ei=i
            if dirn==-1 and H[i]>ev+k*a[ei]: piv.append((ei,ev,'L'));dirn=1;ev=H[i];ei=i
    return piv
def legs(d,k):
    p=zigzag(d,k);V=d.volume.values;out=[]
    for j in range(2,len(p)-3):
        (i0,v0,t0),(i1,v1,t1),(i2,v2,t2),(i3,v3,t3)=p[j:j+4];vp=p[j-1][1]
        up=t1=='H'
        if up and not v1>vp: continue   # 只算顺势腿：做多=这段创了新高
        if (not up) and not v1<vp: continue
        imp=abs(v1-v0);ret=abs(v1-v2)/imp
        cont=(v3>v1) if up else (v3<v1)
        out.append({'方向':'多' if up else '空','回踩深度':ret,'延续':cont,'用时比':(i2-i1)/max(i1-i0,1),'量比':V[i1+1:i2+1].mean()/max(V[i0+1:i1+1].mean(),1e-9),'腿长ATR':imp/atr(d).iloc[i1]})
    return pd.DataFrame(out)
bins=[0,0.382,0.5,0.618,0.786,1.0,9];lab=['<0.382','0.382~0.5','0.5~0.618','0.618~0.786','0.786~1','>1(破起点)']
rows=[]
for name,d in SETS.items():
    a=atr(d);atrp=(a/d.close*100).median()
    lg=legs(d,3)
    if len(lg)==0: continue
    lg['档']=pd.cut(lg['回踩深度'],bins,labels=lab)
    lg['其他三项好']=(lg['用时比']<=1).astype(int)+(lg['量比']<1).astype(int)
    print(f'\n##### {name}  K线{len(d)}根  {str(d.index[0])[:10]}~{str(d.index[-1])[:10]}  ATR中位={atrp:.2f}%  波段{len(lg)}个')
    t=lg.groupby('档',observed=False).agg(次数=('延续','size'),之后创新高低=('延续','mean')).round(2);print(t.T.to_string())
    print('回踩深度中位 %.2f；用时比≤1且量比<1(强)的波段：回踩中位 %.2f，延续 %.0f%% (n=%d)；其余：回踩中位 %.2f，延续 %.0f%% (n=%d)'%(lg['回踩深度'].median(),lg[lg['其他三项好']==2]['回踩深度'].median(),lg[lg['其他三项好']==2]['延续'].mean()*100,(lg['其他三项好']==2).sum(),lg[lg['其他三项好']<2]['回踩深度'].median(),lg[lg['其他三项好']<2]['延续'].mean()*100,(lg['其他三项好']<2).sum()))
    lg['票']=name;rows.append(lg)
pd.concat(rows).to_csv('legs.csv',index=False)
