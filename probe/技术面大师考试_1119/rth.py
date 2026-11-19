exec(open('lin.py').read().split("def mk(lr):")[0])
def rth(d):
    et=d.index.tz_convert('America/New_York');return d[(et.hour>=9)&(et.hour<=15)&(et.dayofweek<5)]
def run_set(SS,lab,ema=False):
    xs=[]
    for n in T:
        d=SS[n+' 1H'];la=None
        if ema:
            r=onto(reg(DD[PAR[n]]),d.index);la=(r=='上涨')
        t=run2(d,n+' 1H',**base,la=la);xs.append(t)
    x=pd.concat(xs);x['y']=x.t.str[:4];o=x[x.t<'2026-06']
    # 成本：每边 5 个基点 → 需要风险占比；run2 没输出，用粗估：ETF 1小时风险约 1.5%（杠杆）/0.7%（QQQ、SOXX）
    print(f'{lab:28s} 2020-26.5: {stats(o)}  全段每笔{x.R.mean():+.3f}R')
    return x
S_all=S;S_rth={k:rth(v) for k,v in S.items()}
for k in S: print(k,len(S_all[k]),len(S_rth[k]))
run_set(S_all,'卡v0.4(去箱体) 含盘前盘后')
run_set(S_rth,'卡v0.4(去箱体) 只常规时段')
run_set(S_all,'+上涨才做多 含盘前盘后',ema=True)
run_set(S_rth,'+上涨才做多 只常规时段',ema=True)
print('--- 扣成本（每边 5 个基点 → 0.001÷风险占比）')
for lab,SS,ema in [('含盘前盘后·去箱体',S_all,False),('只常规·去箱体',S_rth,False),('含盘前盘后·上涨才做多',S_all,True),('只常规·上涨才做多',S_rth,True)]:
    xs=[]
    for n in T:
        d=SS[n+' 1H'];la=(onto(reg(DD[PAR[n]]),d.index)=='上涨') if ema else None
        xs.append(run2(d,n+' 1H',**base,la=la))
    x=pd.concat(xs);o=x[x.t<'2026-06'].copy();o['Rc']=o.R-0.001/o.riskp
    print(f'{lab:18s} 每笔{o.R.mean():+.3f}R 扣成本{o.Rc.mean():+.3f}R  风险占比中位{o.riskp.median():.2%}  做多扣后{o[o.dir=="多"].Rc.mean():+.3f} 做空扣后{o[o.dir=="空"].Rc.mean():+.3f}  按年(扣后):'+' '.join(f"{y}:{g.Rc.mean():+.2f}" for y,g in o.groupby(o.t.str[:4])))
