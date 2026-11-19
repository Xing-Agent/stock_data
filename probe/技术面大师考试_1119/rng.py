exec(open('lin.py').read().split("def mk(lr):")[0])
def run_range(d,name,regs,box_n=120,trig='sfp',tp='mid',zone=0.33,hold=72,rr_min=1.0,allow=('震荡',)):
    I=h4info(d) if box_n==120 else None
    h=d.resample('4h').agg({'high':'max','low':'min'}).dropna()
    Hn=h.high.rolling(box_n).max().shift(1).reindex(d.index,method='ffill').values
    Ln=h.low.rolling(box_n).min().shift(1).reindex(d.index,method='ffill').values
    A=atr(d).values;O,H,Lo,C=[d[c].values for c in ['open','high','low','close']]
    out=[];armedL=armedS=True;i=150;n=len(d)
    while i<n-2:
        hi,lo=Hn[i],Ln[i];rg=regs[i]
        if np.isnan(hi) or hi<=lo or rg not in allow: i+=1;continue
        w=hi-lo;pos=(C[i]-lo)/w;a=A[i]
        if pos>0.45 and pos<0.55: armedL=armedS=True   # 回到中轴附近才重新上膛（一个结构一枪）
        sig=None
        for side in ('L','S'):
            if side=='L' and not armedL: continue
            if side=='S' and not armedS: continue
            L=side=='L'
            inzone=(min(Lo[i-3:i+1])<=lo+zone*w) if L else (max(H[i-3:i+1])>=hi-zone*w)
            if not inzone: continue
            if trig=='sfp':  # 假跌破：最近3根里有一根刺穿箱底≥0.1ATR，本根收盘回到箱底之上
                pin=min(Lo[i-3:i+1]) if L else max(H[i-3:i+1])
                ok=(pin<=lo-0.1*a and C[i]>lo) if L else (pin>=hi+0.1*a and C[i]<hi)
            else:            # 早鸟：长下影收回 / 吞没，在下1/3里
                body=abs(C[i]-O[i]);rng_=H[i]-Lo[i]+1e-12
                if L: ok=((min(O[i],C[i])-Lo[i]>=2*body and C[i]>=Lo[i]+0.5*rng_) or (C[i]>O[i] and O[i-1]>C[i-1] and C[i]>=O[i-1] and O[i]<=C[i-1]))
                else: ok=((H[i]-max(O[i],C[i])>=2*body and C[i]<=H[i]-0.5*rng_) or (C[i]<O[i] and O[i-1]<C[i-1] and C[i]<=O[i-1] and O[i]>=C[i-1]))
                pin=min(Lo[i-3:i+1]) if L else max(H[i-3:i+1])
            if ok: sig=(side,pin);break
        if not sig: i+=1;continue
        side,pin=sig;L=side=='L';e=C[i];st=pin-0.5*a if L else pin+0.5*a;risk=abs(e-st)
        mid=(hi+lo)/2;tp1=mid;tp2=(hi-0.1*w) if L else (lo+0.1*w)
        if tp=='edge': tp1=tp2
        rr1=((tp1-e) if L else (e-tp1))/risk;rr2=((tp2-e) if L else (e-tp2))/risk
        if L: armedL=False
        else: armedS=False
        if rr1<rr_min: i+=1;continue
        half=False;res=None;Rm=0;stp=st
        for j in range(i+1,min(i+1+hold,n)):
            if not half:
                if (Lo[j]<=stp) if L else (H[j]>=stp): res=-1;break
                if (H[j]>=tp1) if L else (Lo[j]<=tp1):
                    if tp=='edge': res=rr1;break
                    half=True;Rm=0.5*rr1;stp=e
            else:
                if (Lo[j]<=stp) if L else (H[j]>=stp): res=Rm;break
                if (H[j]>=tp2) if L else (Lo[j]<=tp2): res=Rm+0.5*rr2;break
        if res is None:
            last=C[min(i+hold,n-1)];res=(Rm if half else 0)+(0.5 if half else 1)*(((last-e) if L else (e-last))/risk)
        out.append({'票':name,'t':str(d.index[i])[:16],'dir':'多' if L else '空','R':round(res,2),'tp1':half or (tp=='edge' and res>0),'rr1':round(rr1,2),'regime':rg})
        i+=1
    return pd.DataFrame(out)
REG={n:onto(reg(DD[PAR[n]]),S[n+' 1H'].index) for n in T}
def go(lab,**kw):
    x=pd.concat([run_range(S[n+' 1H'],n,REG[n],**kw) for n in T]);x['y']=x.t.str[:4];o=x[x.t<'2026-06']
    print(f'{lab:26s} {stats(o)}\n{"":26s} 多:{stats(o[o.dir=="多"])}\n{"":26s} 空:{stats(o[o.dir=="空"])}\n{"":26s} 按年: '+' | '.join(f"{y}:{len(g)}笔{g.R.mean():+.2f}" for y,g in x.groupby('y')))
    return x
go('震荡·假跌破·目标中轴+对边')
go('震荡·早鸟·目标中轴+对边',trig='early')
go('震荡·假跌破·目标只到中轴',tp='edge'.replace('edge','edge')) if False else None
go('震荡·假跌破·盈亏比≥2',rr_min=2)
go('震荡·假跌破·箱体60根4H',box_n=60)
go('震荡·假跌破·下1/4才做',zone=0.25)
go('对照:三种行情都做',allow=('震荡','上涨','下跌'))
