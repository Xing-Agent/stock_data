import sys
src=open('trig2.py').read().split('cfgs=')[0]
exec(src)
D3='/home/claude/xing-agent-stock_data/market_tech_exam_1119/'
def L3(f):
    d=pd.read_csv(D3+f);d['time']=pd.to_datetime(d['time'],utc=True);d=d.set_index('time').sort_index();return d[~d.index.duplicated()]
S={n+' 1H':L3(f'{n}_1h_含盘前盘后_拆股折算.csv') for n in ['SOXL','TQQQ','KORU','QQQ','SOXX']}
cfg={'原来 A扳机不设闸':dict(trig='A',rrmode='none'),'推荐版(223)':dict(trig='C',rrmode='gem',f_box=True,tk_rules=True,f_n=True),'推荐版去箱体':dict(trig='C',rrmode='gem',tk_rules=True,f_n=True),'只换早鸟扳机':dict(trig='C',rrmode='none')}
import pandas as pd
for nm,kw in cfg.items():
    x=pd.concat([run2(d,n,**kw) for n,d in S.items()]);x.to_csv(f'oos_{nm}.csv',index=False)
    x['y']=x.t.str[:4];oos=x[x.t<'2026-06'];ins=x[x.t>='2026-06']
    print(f'\n### {nm}\n  2020-01~2026-05(没用过): {stats(oos)}\n  2026-06~11(调规则用的): {stats(ins)}')
    for n in S: print('   ',n,stats(oos[oos.票==n]))
    for s in ['多','空']: print('   ',s,stats(oos[oos.dir==s]))
    print('   按年:',' | '.join(f"{y}:{len(g)}笔 {g.R.mean():+.2f}R" for y,g in oos.groupby('y')))
