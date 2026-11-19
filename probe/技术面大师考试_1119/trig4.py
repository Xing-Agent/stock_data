import pandas as pd, numpy as np, warnings, itertools;warnings.filterwarnings('ignore')
exec(open('trig.py').read().split('def run(')[0])
def h4info(d):
    h=d.resample('4h').agg({'high':'max','low':'min','close':'last'}).dropna()
    a=pd.concat([h.high-h.low,(h.high-h.close.shift()).abs(),(h.low-h.close.shift()).abs()],axis=1).max(axis=1).rolling(14).mean()
    e20=h.close.ewm(span=20).mean();e60=h.close.ewm(span=60).mean()
    H120=h.high.rolling(120).max();L120=h.low.rolling(120).min()
    f=pd.DataFrame({'a4':a,'e20':e20,'e60':e60,'H120':H120,'L120':L120}).shift(1)
    return f.reindex(d.index,method='ffill')
def run2(d,name,trig='C',rrmode='gem',f_box=False,f_n=False,f_ema=False,tk_rules=False,f_ma=0,ref=None,la=None,sa=None,short_part=None,N=60,hold=72):
    tr,ma=trend_series(d,'4h');I=h4info(d);A=atr(d).values;O,H,Lo,C,V=[d[c].values for c in ['open','high','low','close','volume']]
    if f_ma:
        src=ref if ref is not None else d
        dc=src.close.resample('1D').last().dropna();m=dc.rolling(f_ma).mean();up=(dc>m).shift(1);dn=(dc<m).shift(1)
        UP=up.reindex(d.index,method='ffill').fillna(False).values;DN=dn.reindex(d.index,method='ffill').fillna(False).values
    trades=[];used=set();cnt={};last_tr=None;run_id=0;i=150
    early=('BTC' in name or 'ETH' in name or 'KORU' in name)
    part=0.4 if ('SOXL' in name or 'TQQQ' in name) else (0.65 if ('BTC' in name or 'KORU' in name) else 0.5)
    if not tk_rules: part=0.5
    part0=part
    while i<len(d)-2:
        t=tr.iloc[i]
        if t!=last_tr: run_id+=1;last_tr=t
        if t not in('up','down'): i+=1;continue
        Lg=t=='up';w0=i-N
        if Lg: ie=w0+H[w0:i+1].argmax();ext=H[ie];ib=w0+Lo[w0:ie+1].argmin();base=Lo[ib]
        else: ie=w0+Lo[w0:i+1].argmin();ext=Lo[ie];ib=w0+H[w0:ie+1].argmax();base=H[ib]
        leg=abs(ext-base)
        if (ie,Lg) in used or ie==i or leg<3*A[ie] or i-ie>30: i+=1;continue
        pin_i=ie+1+(Lo[ie+1:i+1].argmin() if Lg else H[ie+1:i+1].argmax());pin=Lo[pin_i] if Lg else H[pin_i]
        depth=(ext-pin)/leg if Lg else (pin-ext)/leg
        if depth>0.786: used.add((ie,Lg));i+=1;continue
        score=int((pin_i-ie)/max(ie-ib,1)<=1)+int(V[ie+1:pin_i+1].mean()<V[ib+1:ie+1].mean())+int((pin>ma.iloc[pin_i]) if Lg else (pin<ma.iloc[pin_i]))
        need={3:0.382,2:0.5}.get(score,0.618)
        if tk_rules and early: need=max(need,0.5)
        if depth<need: i+=1;continue
        if trig=='A': go=(C[i]>O[i] and C[i]>H[i-1]) if Lg else (C[i]<O[i] and C[i]<Lo[i-1])
        else:  # C 早鸟：长下影收回 或 吞没
            body=abs(C[i]-O[i]);rng=H[i]-Lo[i]+1e-12
            if Lg:
                wick=min(O[i],C[i])-Lo[i];hammer=wick>=2*body and C[i]>=Lo[i]+0.5*rng
                eng=C[i]>O[i] and O[i-1]>C[i-1] and C[i]>=O[i-1] and O[i]<=C[i-1]
            else:
                wick=H[i]-max(O[i],C[i]);hammer=wick>=2*body and C[i]<=H[i]-0.5*rng
                eng=C[i]<O[i] and O[i-1]<C[i-1] and C[i]<=O[i-1] and O[i]>=C[i-1]
            go=hammer or eng
        if not go: i+=1;continue
        e=C[i];st=pin-0.5*A[i] if Lg else pin+0.5*A[i];tp1=ext;tp2=ext+0.618*leg if Lg else ext-0.618*leg
        risk=abs(e-st);rr1=((tp1-e) if Lg else (e-tp1))/risk;rr2=abs(tp2-e)/risk
        # 过滤
        why=None
        if rrmode=='gem' and (rr1<1.3 or part*rr1+(1-part)*rr2<2): why='rr'
        if rrmode=='tp1_2' and rr1<2: why='rr'
        if f_box and why is None:
            pos=(e-I.L120.iloc[i])/(I.H120.iloc[i]-I.L120.iloc[i]+1e-12)
            if 0.33<=pos<=0.67: why='box'
        if f_ema and why is None:
            g=(I.e20.iloc[i]-I.e60.iloc[i])*(1 if Lg else -1)
            if g<1.5*I.a4.iloc[i]: why='ema'
        if f_ma and why is None and not (UP[i] if Lg else DN[i]): why='ma'
        if why is None and la is not None and Lg and not la[i]: why='la'
        if why is None and sa is not None and (not Lg) and not sa[i]: why='sa'
        key=(run_id,Lg);n=cnt.get(key,0)
        if f_n and why is None and n>=2: why='n'
        used.add((ie,Lg));cnt[key]=n+1
        if why: i+=1;continue
        part=part0 if (Lg or short_part is None) else short_part
        half=False;res=None;Rm=0
        for j in range(i+1,min(i+1+hold,len(d))):
            if not half:
                if (Lo[j]<=st) if Lg else (H[j]>=st): res=-1;break
                if (H[j]>=tp1) if Lg else (Lo[j]<=tp1): half=True;Rm=part*rr1;st=e
            else:
                if (Lo[j]<=st) if Lg else (H[j]>=st): res=Rm;break
                if (H[j]>=tp2) if Lg else (Lo[j]<=tp2): res=Rm+(1-part)*rr2;break
        if res is None:
            last=C[min(i+hold,len(d)-1)];res=(Rm if half else 0)+((1-part) if half else 1)*(((last-e) if Lg else (e-last))/risk)
        trades.append({'票':name,'t':str(d.index[i])[:16],'dir':'多' if Lg else '空','R':round(res,2),'tp1':half})
        i+=1
    return pd.DataFrame(trades)
def stats(t):
    if len(t)==0: return '0 笔'
    w=t.R[t.R>0].sum();l=-t.R[t.R<0].sum();cum=t.R.cumsum();dd=(cum-cum.cummax()).min()
    return f"{len(t):3d}笔 到TP1 {t.tp1.mean()*100:3.0f}% 赚钱 {(t.R>0).mean()*100:3.0f}% 合计{t.R.sum():+6.1f}R 每笔{t.R.mean():+.2f}R 利润因子{(w/l if l else np.inf):.2f} 最大回撤{dd:.1f}R"
S={k:v for k,v in SETS.items() if '1H' in k}
def tot(**kw):
    x=pd.concat([run2(d,n,**kw) for n,d in S.items()])
    return x
cfgs=[('原来 A扳机+不设闸',dict(trig='A',rrmode='none')),
('只换 C早鸟扳机',dict(trig='C',rrmode='none')),
('C+盈亏比双门槛',dict(trig='C',rrmode='gem')),
('C+双门槛+箱体中轴否决',dict(trig='C',rrmode='gem',f_box=True)),
('C+双门槛+前2次回踩',dict(trig='C',rrmode='gem',f_n=True)),
('C+双门槛+均线发散',dict(trig='C',rrmode='gem',f_ema=True)),
('C+双门槛+分票规则',dict(trig='C',rrmode='gem',tk_rules=True)),
('Gemini全套',dict(trig='C',rrmode='gem',f_box=True,f_n=True,f_ema=True,tk_rules=True)),
('Gemini全套去掉箱体',dict(trig='C',rrmode='gem',f_n=True,f_ema=True,tk_rules=True)),
('A扳机+Gemini全套',dict(trig='A',rrmode='gem',f_box=True,f_n=True,f_ema=True,tk_rules=True)),
]
out=[]
for nm,kw in cfgs:
    x=tot(**kw);print(f'{nm:16s} {stats(x)}')
    if nm=='Gemini全套':
        for n in S: print('     ',n,stats(x[x.票==n]))
        for s in ['多','空']: print('     ',s,stats(x[x.dir==s]))
        x.to_csv('gem_full_trades.csv',index=False)
