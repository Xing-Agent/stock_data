import json,gzip,os,numpy as np,pandas as pd,warnings;warnings.filterwarnings('ignore')
B='/home/claude/xing-agent-stock_data/market_ext_1105/'
def load(t):
    d=json.load(gzip.open(B+t+'/daily.json.gz'))['data']
    x=pd.DataFrame(d);x['date']=pd.to_datetime(x.date);x=x.set_index('date')[['open','high','low','close','volume','split_coefficient']].astype(float)
    sc=x.split_coefficient.fillna(1).replace(0,1)
    f=sc[::-1].cumprod()[::-1].shift(-1).fillna(1)   # 拆股当天之前的价格都除以之后累计拆股比例
    for c in ['open','high','low','close']: x[c]=x[c]/f
    x['volume']=x.volume*f
    return x.drop(columns='split_coefficient')
if __name__=='__main__':
    ts=sorted(os.listdir(B));rows=[]
    for t in ts:
        try:
            x=load(t);x=x[x.index>='2010-01-01']
            if len(x)<1500: continue
            dv=(x.close*x.volume).median();r=x.close.pct_change().abs()
            if (r>0.6).any(): continue  # 疑似没折对
            rows.append((t,dv,len(x)))
        except Exception as e: pass
    u=pd.DataFrame(rows,columns=['t','dv','n']).sort_values('dv',ascending=False);u.to_csv('univ.csv',index=False);print(len(u));print(u.head(10))
