from ev import *
def analyze2(t,x):
    x=x[x.index>='2009-01-01'].copy()
    if len(x)<600: return []
    C,H,L=x.close.values,x.high.values,x.low.values
    e144=x.close.ewm(span=144).mean().values;e169=x.close.ewm(span=169).mean().values
    rb_lo=np.minimum(e144,e169);R=rsi(x.close).values;n=len(x);ev=[];last=-999
    swh=[i for i in range(5,n-5) if H[i]==H[i-5:i+6].max()]
    for i in range(300,n-121):
        if not (C[i]<rb_lo[i] and C[i-1]>=rb_lo[i-1]) or i-last<60: continue
        last=i
        slope=e144[i]/e144[i-60]-1
        mx=H[i-250:i].max()
        tt=[]
        for j in [j for j in swh if i-250<=j<=i-5 and H[j]>=mx*0.90]:
            if not tt or j-tt[-1]>=20: tt.append(j)
            elif H[j]>H[tt[-1]]: tt[-1]=j
        k=len(tt);div=k>=2 and R[tt[-1]]<R[tt[0]]-3
        # 一次比一次弱：后一个顶的RSI 依次降低
        weak=k>=3 and all(R[tt[m+1]]<R[tt[m]] for m in range(len(tt)-1))
        fr={f'r{h}':C[i+h]/C[i]-1 for h in (20,60,120)};fr['mdd60']=L[i+1:i+61].min()/C[i]-1
        ev.append({'tk':t,'date':str(x.index[i].date()),'顶数':k,'背离':div,'一次比一次弱':weak,'均线斜率60':slope,**fr})
    return ev
if __name__=='__main__':
    u=pd.read_csv('univ.csv').head(400);E=[]
    for t in u.t:
        try: E+=analyze2(t,load(t))
        except Exception as e: pass
    for t,f in [('BTC','/home/claude/xing-agent-stock_data/market_tech_exam_1118/BTC_日线_Coinbase.csv'),('ETH','/home/claude/xing-agent-stock_data/market_tech_exam_1118/ETH_日线_Coinbase.csv')]+[(n,f'/home/claude/xing-agent-stock_data/market_tech_exam_1119/{n}_日线_拆股折算.csv') for n in ['QQQ','SOXX','SOXL','TQQQ','KORU']]:
        x=pd.read_csv(f);x['time']=pd.to_datetime(x.time,utc=True).dt.tz_localize(None);x=x.set_index('time');E+=analyze2(t,x)
    E=pd.DataFrame(E);E.to_csv('events2.csv',index=False)
    flat=E.均线斜率60.abs()<0.05
    def show(lab,m):
        s=E[m];print(f'{lab:34s} 次数{len(s):5d}  20天{s.r20.median():+.3f} 60天{s.r60.median():+.3f} 120天{s.r120.median():+.3f}  60天内最多跌{s.mdd60.median():+.3f}  跌超15%{(s.mdd60<-0.15).mean():.0%}  60天后还在下面{(s.r60<0).mean():.0%}')
    show('所有「跌破均线带」',E.index==E.index)
    show('均线还在往上(斜率>5%)',E.均线斜率60>0.05)
    show('均线走平(|斜率|<5%)',flat)
    show('走平+≥3顶',flat&(E.顶数>=3))
    show('走平+≥3顶+背离',flat&(E.顶数>=3)&E.背离)
    show('走平+≥3顶+一次比一次弱',flat&E.一次比一次弱)
    show('任何斜率+≥3顶+一次比一次弱',E.一次比一次弱)
    show('走平+0~1顶(没有派发)',flat&(E.顶数<=1))
