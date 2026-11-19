from ev import *
Q=pd.read_csv('/home/claude/xing-agent-stock_data/market_tech_exam_1119/QQQ_日线_拆股折算.csv');Q['time']=pd.to_datetime(Q.time,utc=True).dt.tz_localize(None);Q=Q.set_index('time')
qe=np.minimum(Q.close.ewm(span=144).mean(),Q.close.ewm(span=169).mean());QDN=(Q.close<qe)
def analyze3(t,x,spans=(144,169),sma=False):
    x=x[x.index>='2009-01-01'].copy()
    if len(x)<600: return []
    C,H,L=x.close.values,x.high.values,x.low.values
    e144=(x.close.rolling(spans[0]).mean() if sma else x.close.ewm(span=spans[0]).mean()).values;e169=(x.close.rolling(spans[1]).mean() if sma else x.close.ewm(span=spans[1]).mean()).values;rb_lo=np.minimum(e144,e169);rb_hi=np.maximum(e144,e169)
    R=rsi(x.close).values;A=atr(x).values;n=len(x);ev=[];last=-999
    qdn=QDN.reindex(x.index,method='ffill').fillna(False).values
    swh=[i for i in range(5,n-5) if H[i]==H[i-5:i+6].max()]
    for i in range(300,n-151):
        if not (C[i]<rb_lo[i] and C[i-1]>=rb_lo[i-1]) or i-last<60: continue
        last=i
        mx=H[i-250:i].max();tt=[]
        for j in [j for j in swh if i-250<=j<=i-5 and H[j]>=mx*0.90]:
            if not tt or j-tt[-1]>=20: tt.append(j)
            elif H[j]>H[tt[-1]]: tt[-1]=j
        k=len(tt);div=k>=2 and R[tt[-1]]<R[tt[0]]-3
        # 反弹空：破位后 30 天内反抽到均线带下沿附近（最高价 ≥ 下沿 -0.5ATR）且没站回上沿，之后收盘跌破反抽前的低点
        lowb=L[i];j0=None
        for j in range(i+1,min(i+31,n-121)):
            lowb=min(lowb,L[j]) if j0 is None else lowb
            if j0 is None and H[j]>=rb_lo[j]-0.5*A[j] and C[j]<rb_hi[j]: j0=j;peak=H[j]
            elif j0 is not None:
                peak=max(peak,H[j])
                if C[j]>rb_hi[j]: j0=None;break
                if C[j]<min(L[j0:j]) : 
                    e=C[j];st=peak+0.5*A[j];risk=st-e;tp1=lowb;tp2=e-2*risk
                    res=None;half=False;Rm=0;s=st
                    for m in range(j+1,j+61):
                        if not half:
                            if H[m]>=s: res=-1;break
                            if L[m]<=tp1 and tp1<e: half=True;Rm=0.5*(e-tp1)/risk;s=e
                        else:
                            if H[m]>=s: res=Rm;break
                            if L[m]<=tp2: res=Rm+0.5*(e-tp2)/risk;break
                    if res is None: res=(Rm if half else 0)+(0.5 if half else 1)*(e-C[j+60])/risk
                    ev.append({'tk':t,'date':str(x.index[j].date()),'顶数':k,'背离':div,'大盘在均线下':bool(qdn[j]),'R':res,'r60':C[j+60]/e-1})
                    break
    return ev
