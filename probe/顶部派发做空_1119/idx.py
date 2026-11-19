from ev3 import *
import json,gzip
def ld(f):
    d=json.load(gzip.open(f))['data'];x=pd.DataFrame(d);x['date']=pd.to_datetime(x.date);x=x.set_index('date')
    x=x[['open','high','low','close','volume','split_coefficient']].astype(float);sc=x.split_coefficient.fillna(1).replace(0,1);fct=sc[::-1].cumprod()[::-1].shift(-1).fillna(1)
    for c in ['open','high','low','close']: x[c]=x[c]/fct
    return x.drop(columns='split_coefficient')
B='/home/claude/xing-agent-stock_data/market_etf_1106/'
for t in ['QQQ','SPY']:
    x=ld(B+t+'/daily.json.gz')
    for lab,y in [('日线',x),('周线',x.resample('W-FRI').agg({'open':'first','high':'max','low':'min','close':'last','volume':'sum'}).dropna())]:
        # 周线：均线带用 144/169 太长（3年），改用 30/40 周（约等于日线 150/200）
        if lab=='周线':
            y=y.copy()
        e=analyze3(t,y) if lab=='日线' else None
        if lab=='周线':
            C,H,L=y.close.values,y.high.values,y.low.values
            e1=y.close.ewm(span=30).mean().values;e2=y.close.ewm(span=40).mean().values;lo=np.minimum(e1,e2)
            ev=[]
            for i in range(60,len(y)-27):
                if C[i]<lo[i] and C[i-1]>=lo[i-1] and (C[i-26:i]>lo[i-26:i]).mean()>0.7:
                    ev.append((str(y.index[i].date()),round(C[i+13]/C[i]-1,3),round(C[i+26]/C[i]-1,3),round(L[i+1:i+27].min()/C[i]-1,3)))
            print(t,lab,'跌破30/40周均线带 → 13周后/26周后/26周内最多跌');[print('   ',r) for r in ev]
        else:
            print(t,lab,'反弹空');print(pd.DataFrame(e)[['date','顶数','背离','R','r60']].round(2).to_string())
