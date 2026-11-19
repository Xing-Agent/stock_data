exec(open('gem2.py').read().split("go('基准(v0.2)',None)")[0])
def m_ema_both(n,d):
    u,dn=ema_ok(DD[PAR[n]]);return onto(u,d.index).astype(bool),onto(dn,d.index).astype(bool)
def m_ema_own(n,d):
    u,dn=ema_ok(DD[n]);return onto(u,d.index).astype(bool),None
def m_ema_struct(n,d):
    u,_=ema_ok(DD[PAR[n]]);s=onto(dstruct(DD[PAR[n]]),d.index);return onto(u,d.index).astype(bool)&(s=='up'),None
go('③看自己日线',m_ema_own)
go('③多空两边都管',m_ema_both)
x=go('③+①结构锁',m_ema_struct)
x=go('③(母体,只管多)',lambda n,d:(onto(ema_ok(DD[PAR[n]])[0],d.index).astype(bool),None))
for n in T: print('   ',n,stats(x[(x.票==n+' 1H')&(x.t<'2026-06')]))
for s in ['多','空']: print('   ',s,stats(x[(x.dir==s)&(x.t<'2026-06')]))
x.to_csv('ema_best.csv',index=False)
