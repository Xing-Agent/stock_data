import polars as pl, glob
# 孤立尖刺:最高比开收盘都高 50% 以上,且比前一根、后一根的最高都高 50% 以上(最低同理,低 33% 以上)。个股财报跳空不会被算进来
res=[]; tot=0
for f in sorted(glob.glob('*.parquet')):
    df=pl.read_parquet(f,columns=['symbol','time_utc','session','open','high','low','close']).sort(['symbol','time_utc'])
    tot+=df.height
    df=df.with_columns(pl.col('high').shift(1).over('symbol').alias('hp'),pl.col('high').shift(-1).over('symbol').alias('hn'),
                       pl.col('low').shift(1).over('symbol').alias('lp'),pl.col('low').shift(-1).over('symbol').alias('ln'),
                       pl.max_horizontal('open','close').alias('mx'),pl.min_horizontal('open','close').alias('mn'))
    x=df.filter(((pl.col('high')>pl.col('mx')*1.5)&(pl.col('high')>pl.col('hp')*1.5)&(pl.col('high')>pl.col('hn')*1.5))|
                ((pl.col('low')<pl.col('mn')*0.67)&(pl.col('low')<pl.col('lp')*0.67)&(pl.col('low')<pl.col('ln')*0.67)))
    res.append(x.select('symbol','time_utc','session','open','high','low','close'))
R=pl.concat(res); print('hourly bars',tot,'spikes',R.height,'tickers',R['symbol'].n_unique()); print(R.group_by('session').len())
with pl.Config(tbl_rows=15,tbl_width_chars=200): print(R.sample(15,seed=1).sort('time_utc'))
R.write_csv('/tmp/claude-0/-home-claude/cf24d0a9-5547-518c-8690-478e8aedafe0/scratchpad/stock_hourly_spikes.csv')
