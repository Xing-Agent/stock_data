# 引擎外脚本：从成绩单流水和日线净值里，算每条已测技术策略两段成绩（第二段只到 2021-12-31，之后封存不读）
import pandas as pd,glob,os
d='probe/成绩单_1122/out_手册/'
rows=[]
for f in sorted(glob.glob(d+'流水_*.csv')):
    b=os.path.basename(f)[3:-4]; seg,name=b.split('_',1)
    t=pd.read_csv(f)
    e=pd.read_parquet(d+f'日线_{seg}_{name}.parquet')['eq']
    if seg=='一':
        t=t[t.entry_date<='2021-12-31']; e=e[:'2021-12-31']
    yrs=(e.index[-1]-e.index[0]).days/365.25
    cagr=(e.iloc[-1]/e.iloc[0])**(1/yrs)-1
    dd=(e/e.cummax()-1).min()
    r=t.r_multiple_net
    rows.append(dict(策略=name,段='2005-2014' if seg=='二' else '2015-2021',笔数=len(t),每笔平均R=round(r.mean(),2),赚钱笔占比=round((r>0).mean()*100),每年赚=round(cagr*100,1),最深亏损=round(dd*100,1)))
o=pd.DataFrame(rows).sort_values(['策略','段'])
o.to_csv('probe/大师接策略库_1126/成绩_两段_到2021.csv',index=False)
print(o.to_string(index=False))
