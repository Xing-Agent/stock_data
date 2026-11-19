exec(open('trig4.py').read().split('cfgs=')[0])
D3='/home/claude/xing-agent-stock_data/market_tech_exam_1119/'
def L3(f):
    d=pd.read_csv(D3+f);d['time']=pd.to_datetime(d['time'],utc=True);d=d.set_index('time').sort_index();return d[~d.index.duplicated()]
T=['SOXL','TQQQ','KORU','QQQ','SOXX']
S={n+' 1H':L3(f'{n}_1h_含盘前盘后_拆股折算.csv') for n in T}
DD={n:L3(f'{n}_日线_拆股折算.csv') for n in T}
PAR={'SOXL':'SOXX','TQQQ':'QQQ','KORU':'KORU','QQQ':'QQQ','SOXX':'SOXX'}
def dstruct(dd,k=3):
    H,L,C=dd.high.values,dd.low.values,dd.close.values;st=[];lastH=None;lastL=None;state='none'
    for i in range(len(dd)):
        j=i-k
        if j>=k:
            if H[j]==H[j-k:j+k+1].max(): lastH=H[j]
            if L[j]==L[j-k:j+k+1].min(): lastL=L[j]
        if lastH is not None and C[i]>lastH: state='up'
        elif lastL is not None and C[i]<lastL: state='down'
        st.append(state)
    return pd.Series(st,index=dd.index).shift(1)   # 用前一天收盘的状态
def natr(dd):
    tr=pd.concat([dd.high-dd.low,(dd.high-dd.close.shift()).abs(),(dd.low-dd.close.shift()).abs()],axis=1).max(axis=1)
    return (tr.rolling(14).mean()/dd.close).shift(1)
def ema_ok(dd):
    e20=dd.close.ewm(span=20).mean();e50=dd.close.ewm(span=50).mean()
    up=(dd.close>e20)&(e20>e50)&(e20>e20.shift(3));dn=(dd.close<e20)&(e20<e50)&(e20<e20.shift(3))
    return up.shift(1),dn.shift(1)
def onto(sr,idx):
    s=sr.copy();s.index=s.index.normalize()
    return s.reindex(idx.normalize(),method='ffill').values
base=dict(trig='C',rrmode='gem',tk_rules=True,f_n=True)
def go(lab,mk,**extra):
    xs=[]
    for n in T:
        d=S[n+' 1H'];la,sa=mk(n,d) if mk else (None,None)
        xs.append(run2(d,n+' 1H',**base,la=la,sa=sa,**extra))
    x=pd.concat(xs);x['y']=x.t.str[:4];o=x[x.t<'2026-06']
    print(f'{lab:22s} 2020-26.5: {stats(o)}\n{"":22s} 按年: '+' | '.join(f"{y}:{len(g)}笔{g.R.mean():+.2f}" for y,g in x.groupby('y'))+f' | 2022多:{x[(x.y=="2022")&(x.dir=="多")].R.mean():+.2f}')
    return x
go('基准(v0.2)',None)
def m_struct_own(n,d):
    s=onto(dstruct(DD[n]),d.index);return (s=='up'),None
def m_struct_par(n,d):
    s=onto(dstruct(DD[PAR[n]]),d.index);return (s=='up'),None
def m_struct_both(n,d):
    s=onto(dstruct(DD[PAR[n]]),d.index);return (s=='up'),(s=='down')
def m_natr(n,d):
    v=onto(natr(DD[PAR[n]]),d.index);v=np.nan_to_num(v.astype(float),nan=0);return v<=0.022,None
def m_ema(n,d):
    u,dn=ema_ok(DD[PAR[n]]);return onto(u,d.index).astype(bool),None
def m_struct_natr(n,d):
    a,_=m_struct_par(n,d);b,_=m_natr(n,d);return a&b,None
go('①日线结构锁(看自己)',m_struct_own)
go('①日线结构锁(看母体)',m_struct_par)
go('①结构锁多空两边都管',m_struct_both)
go('②母体波动熔断禁多',m_natr)
go('③日线EMA20/50多头才多',m_ema)
go('①+②',m_struct_natr)
go('空单TP1平67%',None,short_part=0.67)
x=go('①母体+空单平67%',m_struct_par,short_part=0.67)
x.to_csv('gem2_best.csv',index=False)
