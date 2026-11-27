# 引擎外：每条已测技术策略两段成绩。2005–2014 用修过坏点的那一套（out_手册_修；缺的回退到原版并标出来），2015–2021 用原版截到 2021-12-31（之后封存不读）
import pandas as pd, glob, os, numpy as np
A = 'probe/成绩单_1122/out_手册/'; B = 'probe/成绩单_1122/out_手册_修/'; rows = []
for f in sorted(glob.glob(A + '流水_*.csv')):
    b = os.path.basename(f)[3:-4]; seg, name = b.split('_', 1); d = A; 源 = '原'
    if seg == '二' and os.path.exists(B + f'流水_二_{name}.csv') and os.path.exists(B + f'日线_二_{name}.parquet'): d = B; 源 = '修坏点'
    t = pd.read_csv(d + f'流水_{seg}_{name}.csv'); e = pd.read_parquet(d + f'日线_{seg}_{name}.parquet')['eq']
    if seg == '一': t = t[t.entry_date <= '2021-12-31']; e = e[:'2021-12-31']
    yrs = (e.index[-1] - e.index[0]).days / 365.25; r = t.r_multiple_net; pnl = t.net_pnl
    y08 = e['2008'] if seg == '二' else None
    rows.append(dict(策略=name, 段='2005-2014' if seg == '二' else '2015-2021', 数据=源, 笔数=len(t), 每笔平均R=round(r.mean(), 2), 赚钱笔占比=round((r > 0).mean() * 100, 1),
                     利润因子=round(pnl[pnl > 0].sum() / -pnl[pnl < 0].sum(), 2) if (pnl < 0).any() else np.nan, 每年赚=round(((e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1) * 100, 1), 最深亏损=round((e / e.cummax() - 1).min() * 100, 1),
                     年2008=round((y08.iloc[-1] / e[:'2007-12-31'].iloc[-1] - 1) * 100, 1) if y08 is not None and len(y08) else np.nan))
O = pd.DataFrame(rows).sort_values(['策略', '段']); O.to_csv('probe/大师接策略库_1126/成绩_两段_到2021_修坏点.csv', index=False)
g = {'趋势跟随': ['trend_following', '技-1', '技-2', '技-3'], '突破': ['技-6', '技-4', '技-5', '技-8'], '均值回归': ['技-12', '技-14'], '假突破反手': ['技-10', '技-11', '技-13']}
O['类'] = O.策略.map(lambda n: next((k for k, v in g.items() for p in v if n == p or n.startswith(p + '-')), None))
print(O[O.类.notna()].groupby(['类', '段']).agg(版本=('策略', 'nunique'), 年lo=('每年赚', 'min'), 年hi=('每年赚', 'max'), 亏浅=('最深亏损', 'max'), 亏深=('最深亏损', 'min')).to_string())
print(O[O.策略 == 'buy_and_hold'].to_string(index=False)); print(O[(O.段 == '2005-2014') & (O.数据 == '原')].策略.tolist())
print(O[O.策略.isin(['技-10','技-13','技-12'])][['策略','段','每年赚','赚钱笔占比','最深亏损']].to_string(index=False))
