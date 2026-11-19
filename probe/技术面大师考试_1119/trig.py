import pandas as pd, numpy as np, warnings;warnings.filterwarnings('ignore')
exec(open('/home/claude/work/profile/profile.py').read().split('def zigzag')[0].replace("def atr(d,n=14)","def _a(d,n=14)") + "\ndef atr(d,n=14):\n    tr=pd.concat([d.high-d.low,(d.high-d.close.shift()).abs(),(d.low-d.close.shift()).abs()],axis=1).max(axis=1);return tr.rolling(n).mean()\n")
def trend_series(d,rule):
    h=d.resample(rule).agg({'high':'max','low':'min','close':'last'}).dropna()
    H,L=h.high.values,h.low.values;sh=[];sl=[];tr=[]
    for i in range(len(h)):
        j=i-2  # 摆动点要右边 2 根确认
        if j>=2:
            if H[j]>H[j-2:j].max() and H[j]>H[j+1:j+3].max(): sh.append(H[j])
            if L[j]<L[j-2:j].min() and L[j]<L[j+1:j+3].min(): sl.append(L[j])
        t='range'
        if len(sh)>=2 and len(sl)>=2:
            if sh[-1]>sh[-2] and sl[-1]>sl[-2]: t='up'
            elif sh[-1]<sh[-2] and sl[-1]<sl[-2]: t='down'
        tr.append(t)
    s=pd.Series(tr,index=h.index).shift(1)  # 用上一根已收盘的大周期
    ma=h.close.rolling(20).mean().shift(1)
    return s.reindex(d.index,method='ffill'),ma.reindex(d.index,method='ffill')
def run(d,rule,mode,rr_min,N=60,hold=72):
    tr,ma=trend_series(d,rule);A=atr(d).values;O,H,Lo,C,V=[d[c].values for c in ['open','high','low','close','volume']]
    trades=[];i=150;used_ext=set()
    while i<len(d)-2:
        t=tr.iloc[i]
        if t not in('up','down'): i+=1;continue
        Lg=t=='up';w0=i-N
        if Lg: ie=w0+H[w0:i+1].argmax();ext=H[ie];ib=w0+Lo[w0:ie+1].argmin();base=Lo[ib]
        else: ie=w0+Lo[w0:i+1].argmin();ext=Lo[ie];ib=w0+H[w0:ie+1].argmax();base=H[ib]
        leg=abs(ext-base)
        if (ie,Lg) in used_ext or ie==i or leg<3*A[ie] or i-ie>30: i+=1;continue
        seg=slice(ie+1,i+1)
        pin_i=ie+1+(Lo[seg].argmin() if Lg else H[seg].argmax());pin=Lo[pin_i] if Lg else H[pin_i]
        depth=(ext-pin)/leg if Lg else (pin-ext)/leg
        if depth>0.786: used_ext.add((ie,Lg));i+=1;continue
        score=int((pin_i-ie)/max(ie-ib,1)<=1)+int(V[ie+1:pin_i+1].mean()<V[ib+1:ie+1].mean())+int((pin>ma.iloc[pin_i]) if Lg else (pin<ma.iloc[pin_i]))
        need={3:0.382,2:0.5}.get(score,0.618)
        if depth<need: i+=1;continue
        go=False
        if mode=='一根阳线':
            go=(C[i]>O[i] and C[i]>H[i-1]) if Lg else (C[i]<O[i] and C[i]<Lo[i-1])
        else: # 回踩不破前针尖：针尖后先反弹出一个高点R，再回落但不破针尖，然后收盘站上R
            if i-pin_i>=3:
                k=pin_i+1+(H[pin_i+1:i].argmax() if Lg else Lo[pin_i+1:i].argmin());R=H[k] if Lg else Lo[k]
                if k<i-1:
                    l2=Lo[k+1:i].min() if Lg else H[k+1:i].max()
                    held=(l2>pin) if Lg else (l2<pin)
                    go=held and ((C[i]>R) if Lg else (C[i]<R))
        if not go: i+=1;continue
        e=C[i];st=pin-0.5*A[i] if Lg else pin+0.5*A[i];tp1=ext;tp2=ext+0.618*leg if Lg else ext-0.618*leg
        risk=abs(e-st);rr=((tp1-e) if Lg else (e-tp1))/risk
        used_ext.add((ie,Lg))
        if rr<rr_min: i+=1;continue
        # 管理：TP1 平一半推保本，其余到 TP2/保本/到期；结果用 R（=1 倍风险）记
        half=False;res=None;Rm=0
        for j in range(i+1,min(i+1+hold,len(d))):
            if not half:
                if (Lo[j]<=st) if Lg else (H[j]>=st): res=-1;break
                if (H[j]>=tp1) if Lg else (Lo[j]<=tp1): half=True;Rm=0.5*rr;st=e
            else:
                if (Lo[j]<=st) if Lg else (H[j]>=st): res=Rm;break
                if (H[j]>=tp2) if Lg else (Lo[j]<=tp2): res=Rm+0.5*abs(tp2-e)/risk;break
        if res is None:
            last=C[min(i+hold,len(d)-1)];res=(Rm if half else 0)+(0.5 if half else 1)*(((last-e) if Lg else (e-last))/risk)
        trades.append({'t':str(d.index[i])[:16],'dir':'多' if Lg else '空','depth':round(depth,2),'score':score,'rr':round(rr,2),'risk%':round(risk/e*100,2),'R':round(res,2),'tp1':half})
        i+=1
    return pd.DataFrame(trades)
def stats(t):
    if len(t)==0: return '0 笔'
    t=t.sort_values('t') if 't' in t else t
    w=t.R[t.R>0].sum();l=-t.R[t.R<0].sum();cum=t.R.cumsum();dd=(cum-cum.cummax()).min()
    return f"{len(t):3d}笔 到TP1 {t.tp1.mean()*100:3.0f}% 赚钱 {(t.R>0).mean()*100:3.0f}% 合计{t.R.sum():+6.1f}R 每笔{t.R.mean():+.2f}R 利润因子{(w/l if l else np.inf):.2f} 最大回撤{dd:.1f}R"
SETS2={k:(v,'4h') for k,v in SETS.items() if '1H' in k}
SETS2.update({k:(v,'W') for k,v in SETS.items() if '日线' in k})
allt=[]
for name,(d,rule) in SETS2.items():
    print(f'\n## {name}  {str(d.index[0])[:10]}~{str(d.index[-1])[:10]}（大周期定方向={rule}）')
    for mode in ['一根阳线','回踩不破前针尖']:
        for rr_min in [0,2]:
            t=run(d,rule,mode,rr_min)
            print(f'  {mode:8s} 盈亏比门槛{rr_min}: {stats(t)}')
            if len(t): t['票']=name;t['扳机']=mode;t['门槛']=rr_min;allt.append(t)
A=pd.concat(allt);A.to_csv('trades.csv',index=False)
print('\n## 合计（5只票1H）')
for mode in ['一根阳线','回踩不破前针尖']:
    for rr_min in [0,2]:
        x=A[(A.扳机==mode)&(A.门槛==rr_min)&A.票.str.contains('1H')];print(f'  {mode} 门槛{rr_min}: {stats(x)}')
        for s in ['多','空']: print(f'      {s}: {stats(x[x.dir==s])}')
