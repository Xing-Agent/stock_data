exec(open('rng.py').read().split("go('震荡·假跌破·目标中轴+对边')")[0])
def rsi(c,n=14):
    d=np.diff(c,prepend=c[0]);u=pd.Series(np.where(d>0,d,0)).ewm(alpha=1/n).mean();v=pd.Series(np.where(d<0,-d,0)).ewm(alpha=1/n).mean()
    return (100-100/(1+u/(v+1e-12))).values
def run_top(d,name,regs,box_n=60,need=('sfp',),allow=('震荡',),side='S',hold=72,look=40):
    h=d.resample('4h').agg({'high':'max','low':'min'}).dropna()
    Hn=h.high.rolling(box_n).max().shift(1).reindex(d.index,method='ffill').values
    Ln=h.low.rolling(box_n).min().shift(1).reindex(d.index,method='ffill').values
    A=atr(d).values;O,H,Lo,C,V=[d[c].values for c in ['open','high','low','close','volume']];R_=rsi(C);n=len(d)
    out=[];armed=True;i=150
    while i<n-2:
        hi,lo=Hn[i],Ln[i];rg=regs[i]
        if np.isnan(hi) or hi<=lo or rg not in allow: i+=1;continue
        w=hi-lo;a=A[i];pos=(C[i]-lo)/w
        if 0.45<pos<0.55: armed=True
        if not armed: i+=1;continue
        S=side=='S'
        # 候选：价格在上 1/3（做多镜像下 1/3）
        if (S and max(H[i-3:i+1])<hi-0.33*w) or ((not S) and min(Lo[i-3:i+1])>lo+0.33*w): i+=1;continue
        k=i-3+(np.argmax(H[i-3:i+1]) if S else np.argmin(Lo[i-3:i+1]));pin=H[k] if S else Lo[k]
        conds={}
        conds['sfp']=(pin>=hi+0.1*a and C[i]<hi) if S else (pin<=lo-0.1*a and C[i]>lo)
        # 背离：针尖创 look 根内新高（新低），但 RSI 低于（高于）之前那个高点（低点）时的 RSI
        j0=max(0,k-look);seg=slice(j0,k-3)
        if k-3>j0:
            pj=j0+(np.argmax(H[seg]) if S else np.argmin(Lo[seg]))
            conds['div']=(H[k]>H[pj] and R_[k]<R_[pj]-2) if S else (Lo[k]<Lo[pj] and R_[k]>R_[pj]+2)
        else: conds['div']=False
        # 派发（吸筹）：上 1/3 里最近 20 根，下跌K线的量 > 上涨K线的量 ×1.2；并且本根是阴线收在下半截（阳线收在上半截）
        sl_=slice(i-20,i+1);dn=V[sl_][C[sl_]<O[sl_]].sum();up=V[sl_][C[sl_]>O[sl_]].sum()
        rng_=H[i]-Lo[i]+1e-12
        conds['dist']=((dn>1.2*up) and C[i]<O[i] and C[i]<=Lo[i]+0.5*rng_) if S else ((up>1.2*dn) and C[i]>O[i] and C[i]>=Lo[i]+0.5*rng_)
        if need=='any2': ok=sum(conds.values())>=2
        elif need=='anyone': ok=any(conds.values())
        else: ok=all(conds[c] for c in need)
        if not ok: i+=1;continue
        armed=False;e=C[i];st=(max(H[i-3:i+1])+0.5*a) if S else (min(Lo[i-3:i+1])-0.5*a);risk=abs(e-st)
        mid=(hi+lo)/2;tp1=mid;tp2=(lo+0.1*w) if S else (hi-0.1*w)
        rr1=((e-tp1) if S else (tp1-e))/risk;rr2=((e-tp2) if S else (tp2-e))/risk
        if rr1<1.0: i+=1;continue
        half=False;res=None;Rm=0;stp=st
        for j in range(i+1,min(i+1+hold,n)):
            if not half:
                if (H[j]>=stp) if S else (Lo[j]<=stp): res=-1;break
                if (Lo[j]<=tp1) if S else (H[j]>=tp1): half=True;Rm=0.5*rr1;stp=e
            else:
                if (H[j]>=stp) if S else (Lo[j]<=stp): res=Rm;break
                if (Lo[j]<=tp2) if S else (H[j]>=tp2): res=Rm+0.5*rr2;break
        if res is None:
            last=C[min(i+hold,n-1)];res=(Rm if half else 0)+(0.5 if half else 1)*(((e-last) if S else (last-e))/risk)
        out.append({'票':name,'t':str(d.index[i])[:16],'dir':'空' if S else '多','R':round(res,2),'tp1':half,'regime':rg,**{k_:bool(v) for k_,v in conds.items()}})
        i+=1
    return pd.DataFrame(out)
def go2(lab,**kw):
    x=pd.concat([run_top(S[n+' 1H'],n,REG[n],**kw) for n in T])
    if len(x)==0: print(lab,'0 笔');return x
    x['y']=x.t.str[:4];o=x[x.t<'2026-06']
    print(f'{lab:30s} {stats(o)}  按年: '+' | '.join(f"{y}:{len(g)}笔{g.R.mean():+.2f}" for y,g in x.groupby('y')))
    return x
print('== 震荡里顶部做空 ==')
go2('只要假突破',need=('sfp',))
go2('只要背离',need=('div',))
go2('只要派发',need=('dist',))
go2('假突破+背离',need=('sfp','div'))
go2('假突破+派发',need=('sfp','dist'))
go2('背离+派发',need=('div','dist'))
go2('三选二',need='any2')
go2('三样都有',need=('sfp','div','dist'))
print('== 上涨行情里顶部做空（逆势、特别好的形态）==')
go2('上涨·假突破+背离',need=('sfp','div'),allow=('上涨',))
go2('上涨·三选二',need='any2',allow=('上涨',))
go2('上涨·三样都有',need=('sfp','div','dist'),allow=('上涨',))
print('== 震荡里底部做多（镜像，对照）==')
go2('底·只要假跌破',need=('sfp',),side='L')
go2('底·假跌破+背离',need=('sfp','div'),side='L')
go2('底·三选二',need='any2',side='L')
