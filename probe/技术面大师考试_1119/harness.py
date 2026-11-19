import re, pandas as pd, numpy as np, json, sys
D='/home/claude/xing-agent-stock_data/market_tech_exam_1117/'
F={'SOXL':'SOXL_1h_含盘前盘后.csv','KORU':'KORU_1h_含盘前盘后_拆股折算.csv','TQQQ':'TQQQ_1h_含盘前盘后.csv','BTC':'BTC_1h.csv','ETH':'ETH_1h.csv','以太坊':'ETH_1h.csv','比特币':'BTC_1h.csv'}
def L(f):
    d=pd.read_csv(D+f);d['time']=pd.to_datetime(d['time'],utc=True);return d.set_index('time').sort_index()
DATA={k:L(v) for k,v in F.items()}
def turns(f):
    s=open(f).read()
    return [(int(n),im,q,a) for n,im,q,a in re.findall(r'######## 第(\d+)轮 · Lin（图(\d+)张）\n(.*?)\n\n######## 第\d+轮 · Gemini\n(.*?)(?=\n######## 第|\Z)',s,re.S)]
def swings(x):
    sh=[];sl=[]
    for i in range(2,len(x)-2):
        if x.high.iloc[i]>x.high.iloc[i-2:i].max() and x.high.iloc[i]>x.high.iloc[i+1:i+3].max(): sh.append(x.high.iloc[i])
        if x.low.iloc[i]<x.low.iloc[i-2:i].min() and x.low.iloc[i]<x.low.iloc[i+1:i+3].min(): sl.append(x.low.iloc[i])
    return sh,sl
def skill(d,t):
    h=d.loc[:t]
    if len(h)<150: return None
    tr=pd.concat([h.high-h.low,(h.high-h.close.shift()).abs(),(h.low-h.close.shift()).abs()],axis=1).max(axis=1);atr=tr.rolling(14).mean().iloc[-1]
    x=h.tail(60);sh,sl=swings(x)
    if not sh or not sl: return None
    hi,lo=max(sh),min(sl);c=h.close.iloc[-1];p=(c-lo)/(hi-lo) if hi>lo else .5
    h4=h.resample('4h').agg({'high':'max','low':'min','close':'last'}).dropna().tail(40);s4h,s4l=swings(h4)
    trend='range'
    if len(s4h)>=2 and len(s4l)>=2:
        if s4h[-1]<s4h[-2] and s4l[-1]<s4l[-2]: trend='down'
        elif s4h[-1]>s4h[-2] and s4l[-1]>s4l[-2]: trend='up'
    r={'close':c,'atr':atr,'p':round(p,2),'trend':trend,'hi':hi,'lo':lo}
    if 0.33<p<0.67: r['act']='WAIT';r['why']='中段禁区';return r
    if p<=0.33:
        if trend=='down': r['act']='WAIT';r['why']='不接飞刀';return r
        stop=lo-0.5*atr;ups=sorted([v for v in sh+s4h if v>c+atr]);tp=ups[0] if ups else hi
        rr=(tp-c)/(c-stop) if c>stop else 0
        r.update(act='LONG',stop=stop,tp1=tp,rr=round(rr,2))
    else:
        if trend=='up': r['act']='WAIT';r['why']='不追杀跌(强势上升不空)';return r
        stop=hi+0.5*atr;dns=sorted([v for v in sl+s4l if v<c-atr],reverse=True);tp=dns[0] if dns else lo
        rr=(c-tp)/(stop-c) if stop>c else 0
        r.update(act='SHORT',stop=stop,tp1=tp,rr=round(rr,2))
    if r['rr']<2: r['why']='盈亏比<2 (%.2f)'%r['rr'];r['act']='WAIT('+r['act']+')'
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
def gem_dir(a):
    a=a[:400]
    s=sum(a.count(k) for k in ['做空','空单','看空','反弹空','逢高空'])
    l=sum(a.count(k) for k in ['做多','多单','看多','接多','逢低'])
    w=sum(a.count(k) for k in ['观望','等待','不要','绝对不','别急','不追','空仓'])
    if w>=max(s,l) and w>0: return 'WAIT'
    return 'SHORT' if s>l else ('LONG' if l>s else '?')
rows=[]
for tag,f,start in [('v2','/home/claude/gem/v2_full.md','2026-09-01'),('v3','/home/claude/gem/v3_full.md','2026-11-08')]:
    prevs={}
    for n,im,q,a in turns(f):
        if im=='0':continue
        m=re.search(r'(SOXL|KORU|TQQQ|ETH|BTC|以太坊|比特币)',a[:600]);p=re.search(r'(现价|当前价格?|最新价|现在价格)[^0-9$]{0,8}\$?\s?([0-9][0-9,]*\.?[0-9]*)',a[:1500])
        if not(m and p):continue
        tk=m.group(1);price=float(p.group(2).replace(',',''))
        d=DATA[tk];
        # sanity: price within data range
        prev=prevs.get(F[tk],pd.Timestamp(start,tz='UTC'))
        w=d.loc[prev:];hit=w[(w.low<=price)&(w.high>=price)]
        if len(hit)==0: rows.append({'src':tag,'turn':n,'tk':tk,'price':price,'map':'未匹配'});continue
        t=hit.index[0];prevs[F[tk]]=t
        r=skill(d,t)
        if r is None: continue
        o=outcome(d,t,r)
        rows.append({'src':tag,'turn':n,'tk':tk,'price':price,'time':str(t)[:16],'q':q.replace('\n',' ')[:30],'gemini':gem_dir(a),**{k:(round(v,2) if isinstance(v,float) else v) for k,v in r.items()},**o})
df=pd.DataFrame(rows);df.to_csv('/home/claude/work/ta_exam/results.csv',index=False)
print(len(df),'matched',df['time'].notna().sum())
cols=[c for c in ['src','turn','tk','price','time','gemini','act','why','p','trend','rr','hit','max_up%','max_dn%','ret%'] if c in df.columns];print(df[df.time.notna()][cols].to_string())
