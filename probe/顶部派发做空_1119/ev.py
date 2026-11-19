from load import *
def rsi(c,n=14):
    d=c.diff();u=d.clip(lower=0).ewm(alpha=1/n).mean();v=(-d.clip(upper=0)).ewm(alpha=1/n).mean();return 100-100/(1+u/(v+1e-12))
def atr(x,n=14):
    tr=pd.concat([x.high-x.low,(x.high-x.close.shift()).abs(),(x.low-x.close.shift()).abs()],axis=1).max(axis=1);return tr.rolling(n).mean()
def analyze(t,x):
    x=x[x.index>='2009-01-01'].copy()
    if len(x)<600: return [],[]
    C,H,L=x.close.values,x.high.values,x.low.values
    e144=x.close.ewm(span=144).mean().values;e169=x.close.ewm(span=169).mean().values
    rb_lo=np.minimum(e144,e169);rb_hi=np.maximum(e144,e169);R=rsi(x.close).values;A=atr(x).values
    n=len(x);ev=[];sh=[]
    # 摆动高点（左右5根）——只在确认后(5天后)才可用
    swh=[i for i in range(5,n-5) if H[i]==H[i-5:i+6].max()]
    for i in range(300,n-121):
        if not (C[i]<rb_lo[i] and C[i-1]>=rb_lo[i-1]): continue
        if (C[i-60:i]>rb_lo[i-60:i]).mean()<0.7: continue   # 之前是上升段
        mx=H[i-250:i].max()
        tops=[j for j in swh if i-250<=j<=i-5 and H[j]>=mx*0.93]
        # 两个顶至少隔 10 天
        tt=[];
        for j in tops:
            if not tt or j-tt[-1]>=10: tt.append(j)
            elif H[j]>H[tt[-1]]: tt[-1]=j
        k=len(tt);div=k>=2 and R[tt[-1]]<R[tt[0]]-3
        weak=k>=2 and (C[i]-0)>0  # 占位
        fr={f'r{h}':C[i+h]/C[i]-1 for h in (20,60,120)}
        fr['mdd60']=L[i+1:i+61].min()/C[i]-1;fr['mup60']=H[i+1:i+61].max()/C[i]-1
        ev.append({'tk':t,'date':str(x.index[i].date()),'顶数':k,'背离':div,**fr})
    return ev
if __name__=='__main__':
    u=pd.read_csv('univ.csv').head(400)
    E=[]
    for t in u.t:
        try: E+=analyze(t,load(t))
        except Exception as e: print(t,e)
    for t,f in [('BTC','/home/claude/xing-agent-stock_data/market_tech_exam_1118/BTC_日线_Coinbase.csv'),('ETH','/home/claude/xing-agent-stock_data/market_tech_exam_1118/ETH_日线_Coinbase.csv')]+[(n,f'/home/claude/xing-agent-stock_data/market_tech_exam_1119/{n}_日线_拆股折算.csv') for n in ['QQQ','SOXX','SOXL','TQQQ','KORU']]:
        x=pd.read_csv(f);x['time']=pd.to_datetime(x.time,utc=True).dt.tz_localize(None);x=x.set_index('time');E+=analyze(t,x)
    E=pd.DataFrame(E);E.to_csv('events.csv',index=False)
    E['类']=np.where(E.顶数>=3,np.where(E.背离,'3顶+背离','3顶无背离'),np.where(E.顶数==2,np.where(E.背离,'2顶+背离','2顶无背离'),'没有顶部派发(0-1顶)'))
    g=E.groupby('类').agg(次数=('r20','size'),之后20天=('r20','median'),之后60天=('r60','median'),之后120天=('r120','median'),六十天内最多跌=('mdd60','median'),六十天内跌超15比例=('mdd60',lambda s:(s<-0.15).mean()),之后60天还在跌比例=('r60',lambda s:(s<0).mean()))
    print(g.round(3).to_string())
