import pandas as pd, numpy as np
exec(open('harness2.py').read().split('rows=[]')[0])
def manage(fut,L,e,st,tp1,tp2):
    """Sniper 管理：到 TP1 平一半、止损推保本；剩下一半到 TP2 或保本或到期"""
    half=False;got=0
    for _,b in fut.iterrows():
        hi,lo=(b.high,b.low)
        if not half:
            if (lo<=st) if L else (hi>=st): return 'STOP',((st/e-1) if L else (e/st-1))*100
            if (hi>=tp1) if L else (lo<=tp1): half=True;got=0.5*((tp1/e-1) if L else (e/tp1-1))*100;st=e
        else:
            if (lo<=st) if L else (hi>=st): return 'TP1+保本',got
            if (hi>=tp2) if L else (lo<=tp2): return 'TP1+TP2',got+0.5*((tp2/e-1) if L else (e/tp2-1))*100
    last=fut.close.iloc[-1] if len(fut) else e
    return ('TP1+到期' if half else '到期'),got+(0.5 if half else 1)*((last/e-1) if L else (e/last-1))*100
def pb3(d,t,L,weak_ok,rr_min=2,n=72):
    h=d.loc[:t];x=h.tail(60);atr=atr_of(h)
    if L: ih=x.high.values.argmax();ext=x.high.iloc[ih];pre=x.iloc[:ih+1];il=pre.low.values.argmin();base=pre.low.iloc[il]
    else: ih=x.low.values.argmin();ext=x.low.iloc[ih];pre=x.iloc[:ih+1];il=pre.high.values.argmax();base=pre.high.iloc[il]
    imp_bars=max(ih-il,1);imp_vol=x.volume.iloc[il:ih+1].mean();ext_t=x.index[ih]
    fut=d.loc[t:].iloc[1:n+1];allb=d.loc[ext_t:]
    for ts,b in fut.iterrows():
        # 创新高（新低）=趋势延续，腿重置
        if (b.high>ext) if L else (b.low<ext):
            ext=b.high if L else b.low;ext_t=ts;continue
        seg=d.loc[ext_t:ts].iloc[1:]
        if len(seg)==0: continue
        leg=abs(ext-base);pbx=seg.low.min() if L else seg.high.max()
        depth=(ext-pbx)/leg if L else (pbx-ext)/leg
        if depth>0.786: return {'r':'回踩超过0.786→趋势可能坏了，放弃'}
        conf=(b.close>b.open and b.close>seg.high.iloc[-2]) if (L and len(seg)>1) else ((b.close<b.open and b.close<seg.low.iloc[-2]) if len(seg)>1 else False)
        if depth<0.382 or not conf: continue
        h4=d.loc[:ts].close.resample('4h').last().dropna();ma=h4.rolling(20).mean().iloc[-1]
        s_time=len(seg)/imp_bars<=1; s_vol=seg.volume.mean()<imp_vol; s_ma=(pbx>ma) if L else (pbx<ma)
        score=int(s_time)+int(s_vol)+int(s_ma)
        need=0.382 if score==3 else (0.5 if score==2 else 0.618)
        if depth<need: continue
        if score<=1 and not weak_ok: return {'r':'弱(其他三项≤1项好)→不做','depth':round(depth,2),'score':score}
        e=b.close;st=pbx-0.5*atr if L else pbx+0.5*atr;tp1=ext;tp2=ext+0.618*leg if L else ext-0.618*leg
        rr=(tp1-e)/(e-st) if L else (e-tp1)/(st-e)
        info={'t':str(ts)[:16],'depth':round(depth,2),'score':score,'rr':round(rr,2),'e':round(e,2),'stop':round(st,2),'tp1':round(tp1,2)}
        if rr<rr_min: return {'r':'盈亏比<%g'%rr_min,**info}
        res,pct=manage(d.loc[ts:].iloc[1:n+1],L,e,st,tp1,tp2)
        return {'r':'进场',**info,'hit':res,'pct':round(pct,2),'risk%':round(abs(e-st)/e*100,2)}
    return {'r':'没回踩到位/没确认'}
df=pd.read_csv('results2.csv')
for weak_ok in [False,True]:
  for rr_min in [2,1.5,1]:
    out=[]
    for _,r in df[df.act.str.startswith('等')&df.act.str.contains('回踩|反抽')].iterrows():
        d=DATA[r.tk];t=pd.Timestamp(r.time+':00',tz='UTC');L='做多' in r.act
        out.append({'turn':r.turn,'tk':r.tk,'方向':'多' if L else '空(镜像)',**pb3(d,t,L,weak_ok,rr_min)})
    o=pd.DataFrame(out);e=o[o.r=='进场'].drop_duplicates(['tk','t'])
    print(f'\n=== 弱也做={weak_ok} 盈亏比门槛={rr_min}  时点{len(o)}  进场{len(e)}  合计{e.pct.sum():.2f}%  ' + str(e.hit.value_counts().to_dict()))
    if rr_min==2 and not weak_ok: print(o.r.value_counts().to_string())
    if len(e): print(e[['turn','tk','方向','t','depth','score','rr','risk%','hit','pct']].to_string())
