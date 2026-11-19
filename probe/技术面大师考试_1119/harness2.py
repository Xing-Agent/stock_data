import re, pandas as pd, numpy as np, sys
exec(open('harness.py').read().split('def skill')[0])  # reuse loaders, swings
def atr_of(h):
    tr=pd.concat([h.high-h.low,(h.high-h.close.shift()).abs(),(h.low-h.close.shift()).abs()],axis=1).max(axis=1);return tr.rolling(14).mean().iloc[-1]
def trend4h(h):
    h4=h.resample('4h').agg({'high':'max','low':'min','close':'last'}).dropna().tail(40);a,b=swings(h4)
    if len(a)>=2 and len(b)>=2:
        if a[-1]<a[-2] and b[-1]<b[-2]: return 'down',a,b
        if a[-1]>a[-2] and b[-1]>b[-2]: return 'up',a,b
    return 'range',a,b
def tp_long(c,atr,cands,lo,hi):
    ups=sorted(v for v in cands if v>c+atr)
    if ups: return ups[0],'最近摆动点'
    mid=(lo+hi)/2
    if c<mid-atr: return mid,'箱体中线(补丁2)'
    if c<hi-atr: return hi,'箱体上沿(补丁2)'
    return max(c,hi)+(hi-lo),'箱体等距(补丁2)'
def tp_short(c,atr,cands,lo,hi):
    dn=sorted((v for v in cands if v<c-atr),reverse=True)
    if dn: return dn[0],'最近摆动点'
    mid=(lo+hi)/2
    if c>mid+atr: return mid,'箱体中线(补丁2)'
    if c>lo+atr: return lo,'箱体下沿(补丁2)'
    return min(c,lo)-(hi-lo),'箱体等距(补丁2)'
def sim(fut,side,entry,stop,tp):
    for _,b in fut.iterrows():
        if side=='L':
            if b.low<=stop: return 'STOP',(stop/entry-1)*100
            if b.high>=tp: return 'TP1',(tp/entry-1)*100
        else:
            if b.high>=stop: return 'STOP',(entry/stop-1)*100
            if b.low<=tp: return 'TP1',(entry/tp-1)*100
    return 'NONE',((fut.close.iloc[-1]/entry-1) if side=='L' else (entry/fut.close.iloc[-1]-1))*100
def pullback(d,t,side,zone_hi,zone_lo,leg_ext,atr,tp,n=72):
    """补丁1：等回踩(反抽)进等待区 → 1H收盘重新站回等待区上沿(跌回下沿)=扳机；止损=回踩极值-0.5ATR；入场时再查盈亏比>=2"""
    fut=d.loc[t:].iloc[1:n+1];touched=False;ext=None
    for i,(ts,b) in enumerate(fut.iterrows()):
        if side=='L':
            if b.low<leg_ext: return {'pb':'失效(跌破起涨点)'}
            if b.low<=zone_hi: touched=True;ext=b.low if ext is None else min(ext,b.low)
            if touched and b.close>zone_hi and b.close>b.open:
                e=b.close;st=ext-0.5*atr
                if (tp-e)/(e-st)<2: return {'pb':'触发但盈亏比<2','pb_t':str(ts)[:16]}
                h,r=sim(fut.iloc[i+1:],'L',e,st,tp);return {'pb':'进场','pb_t':str(ts)[:16],'pb_e':round(e,2),'pb_stop':round(st,2),'pb_tp':round(tp,2),'pb_hit':h,'pb_r%':round(r,2)}
        else:
            if b.high>leg_ext: return {'pb':'失效(突破起跌点)'}
            if b.high>=zone_lo: touched=True;ext=b.high if ext is None else max(ext,b.high)
            if touched and b.close<zone_lo and b.close<b.open:
                e=b.close;st=ext+0.5*atr
                if (e-tp)/(st-e)<2: return {'pb':'触发但盈亏比<2','pb_t':str(ts)[:16]}
                h,r=sim(fut.iloc[i+1:],'S',e,st,tp);return {'pb':'进场','pb_t':str(ts)[:16],'pb_e':round(e,2),'pb_stop':round(st,2),'pb_tp':round(tp,2),'pb_hit':h,'pb_r%':round(r,2)}
    return {'pb':'没回踩到' if not touched else '回踩了没扳机'}
def edge(d,t,side,lv,atr,tp,n=72):
    fut=d.loc[t:].iloc[1:n+1];pin=None;pin_i=None;cnt=0
    for i,(ts,b) in enumerate(fut.iterrows()):
        L=side=='L'
        cnt=cnt+1 if ((b.close<lv-0.25*atr) if L else (b.close>lv+0.25*atr)) else 0
        if cnt>=3: return {'pb':'真跌破→失效' if L else '真突破→失效'}
        if (b.low<=lv-0.1*atr) if L else (b.high>=lv+0.1*atr):
            pin=(b.low if L else b.high) if pin is None else (min(pin,b.low) if L else max(pin,b.high));pin_i=i
        if pin is not None and i-pin_i<=3 and ((b.close>lv) if L else (b.close<lv)):
            e=b.close;st=pin-0.5*atr if L else pin+0.5*atr
            rr=((tp-e)/(e-st)) if L else ((e-tp)/(st-e))
            if rr<2: return {'pb':'扳机触发但盈亏比<2','pb_t':str(ts)[:16]}
            hh,r=sim(fut.iloc[i+1:],side,e,st,tp);return {'pb':'进场','pb_t':str(ts)[:16],'pb_e':round(e,2),'pb_stop':round(st,2),'pb_tp':round(tp,2),'pb_hit':hh,'pb_r%':round(r,2)}
    return {'pb':'没等到扳机'}
def skill(d,t):
    h=d.loc[:t]
    if len(h)<150: return None
    atr=atr_of(h);x=h.tail(60);sh,sl=swings(x)
    if not sh or not sl: return None
    hi=max(sh+[x.high.tail(3).max()]);lo=min(sl+[x.low.tail(3).min()]);c=h.close.iloc[-1];p=(c-lo)/(hi-lo) if hi>lo else .5
    trend,s4h,s4l=trend4h(h)
    r={'close':c,'atr':atr,'p':round(p,2),'trend':trend,'hi':hi,'lo':lo}
    # 补丁1：顺势回踩 —— 上升趋势且不在低位 → 等回踩做多；下降趋势且不在高位 → 等反抽做空（镜像，试算）
    if trend=='up' and p>0.33:
        legLo=x.low.min();legHi=max(x.high.max(),c)
        f5,f618=legHi-0.5*(legHi-legLo),legHi-0.618*(legHi-legLo)
        broken=[v for v in sh if v<c-0.5*atr]   # 已被突破的摆动高点=平台
        zh=max(max(broken) if broken else f5,f5);zl=min(f618,zh-0.5*atr)
        tp=legHi if legHi>c+atr else legHi+(legHi-legLo)*0.5
        r.update(act='等回踩做多',why='补丁1',zone='%.2f~%.2f'%(zl,zh),**pullback(d,t,'L',zh,zl,legLo,atr,tp));return r
    if trend=='down' and p<0.67:
        legHi=x.high.max();legLo=min(x.low.min(),c)
        f5,f618=legLo+0.5*(legHi-legLo),legLo+0.618*(legHi-legLo)
        broken=[v for v in sl if v>c+0.5*atr]
        zl=min(min(broken) if broken else f5,f5);zh=max(f618,zl+0.5*atr)
        tp=legLo if legLo<c-atr else legLo-(legHi-legLo)*0.5
        r.update(act='等反抽做空(镜像试算)',why='补丁1镜像',zone='%.2f~%.2f'%(zl,zh),**pullback(d,t,'S',zh,zl,legHi,atr,tp));return r
    if 0.33<p<0.67: r['act']='WAIT';r['why']='中段禁区';return r
    if p<=0.33:
        tp,src=tp_long(lo,atr,sh+s4h,lo,hi);r.update(act='等箱底扳机做多',why='边缘',tp1=tp,tp_src=src,**edge(d,t,'L',lo,atr,tp))
    else:
        tp,src=tp_short(hi,atr,sl+s4l,lo,hi);r.update(act='等箱顶扳机做空',why='边缘',tp1=tp,tp_src=src,**edge(d,t,'S',hi,atr,tp))
    return r
def outcome(d,t,r,n=72):
    fut=d.loc[t:].iloc[1:n+1];c=r['close']
    res={'max_up%':round((fut.high.max()/c-1)*100,2),'max_dn%':round((fut.low.min()/c-1)*100,2),'ret%':round((fut.close.iloc[-1]/c-1)*100,2)}
    act=r['act'].replace('WAIT(','').replace(')','')
    if 'stop' in r:
        for _,b in fut.iterrows():
            if act=='LONG':
                if b.low<=r['stop']: res['hit']='STOP';break
                if b.high>=r['tp1']: res['hit']='TP1';break
            else:
                if b.high>=r['stop']: res['hit']='STOP';break
                if b.low<=r['tp1']: res['hit']='TP1';break
        else: res['hit']='NONE'
    return res
rows=[]
for tag,f,start in [('v2','/home/claude/gem/v2_full.md','2026-09-01'),('v3','/home/claude/gem/v3_full.md','2026-11-08')]:
    prevs={}
    for n,im,q,a in turns(f):
        if im=='0':continue
        m=re.search(r'(SOXL|KORU|TQQQ|ETH|BTC|以太坊|比特币)',a[:600]);p=re.search(r'(现价|当前价格?|最新价|现在价格)[^0-9$]{0,8}\$?\s?([0-9][0-9,]*\.?[0-9]*)',a[:1500])
        if not(m and p):continue
        tk=m.group(1);price=float(p.group(2).replace(',',''));d=DATA[tk]
        prev=prevs.get(F[tk],pd.Timestamp(start,tz='UTC'))
        w=d.loc[prev:];hit=w[(w.low<=price)&(w.high>=price)]
        if len(hit)==0: continue
        t=hit.index[0];prevs[F[tk]]=t
        r=skill(d,t)
        if r is None: continue
        o=outcome(d,t,r) if 'stop' in r else outcome(d,t,{**r,'act':'WAIT'})
        rows.append({'src':tag,'turn':n,'tk':tk,'price':price,'time':str(t)[:16],**{k:(round(v,2) if isinstance(v,float) else v) for k,v in r.items()},**o})
df=pd.DataFrame(rows).drop_duplicates(['tk','time'])
df.to_csv('results2.csv',index=False);print(len(df))
pd.set_option('display.width',250)
print(df[[c for c in ['src','turn','tk','time','act','why','p','trend','zone','pb','pb_t','pb_e','pb_stop','pb_tp','pb_hit','pb_r%','rr','tp_src','hit','max_up%','max_dn%','ret%'] if c in df]].to_string())
