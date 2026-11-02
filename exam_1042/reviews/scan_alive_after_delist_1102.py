import json, polars as pl, os
cal = sorted(f[:10] for f in os.listdir('/home/claude/pituni/day')); idx = {d: i for i, d in enumerate(cal)}
S = pl.read_csv('/home/claude/seg/pit_company_segments.csv', infer_schema_length=0).with_columns(pl.col('c_first').cast(pl.Float64), pl.col('c_last').cast(pl.Float64), pl.col('vol_med_last20').cast(pl.Float64))
m = pl.read_csv('/home/claude/stock_data/exam_1042/manifest.csv', infer_schema_length=0).filter(pl.col('delisted') == 'true')
scan = json.load(open('/home/claude/stock_data/exam_1042/reviews/sec_delist_scan_1102.json'))['d']
from datetime import date, timedelta
def near(a, b, n): return abs((date.fromisoformat(a) - date.fromisoformat(b)).days) <= n
res = []
for r in m.iter_rows(named=True):
    s, dd = r['symbol'], r['delisting_date']; o = scan[s]; rows = o['rows']
    k10 = [x[1] for x in rows if x[0].startswith('10-K') and x[1] > (date.fromisoformat(dd) + timedelta(45)).isoformat()]
    bk = any(x[0].startswith('8-K') and '1.03' in x[2] for x in rows)
    a201 = any(x[0].startswith('8-K') and '2.01' in x[2] and near(x[1], dd, 45) for x in rows)
    f25 = any(x[0].startswith(('25', '15')) and near(x[1], dd, 45) for x in rows)
    me = S.filter((pl.col('company_id') == r['company_id']) & (pl.col('last_seen') == dd))
    lc = me['c_last'][0] if me.height else None; lv = me['vol_med_last20'][0] if me.height else None
    nxt = cal[idx[dd] + 1] if dd in idx else None
    c = S.filter(pl.col('first_seen') == nxt).with_columns((pl.col('c_first') / lc - 1).abs().alias('dp')).filter(pl.col('dp') < 0.6).sort('dp') if (nxt and lc) else pl.DataFrame()
    cands = ' '.join(f"{t}({dp:.2f})" for t, dp in c.select('ticker', 'dp').head(4).iter_rows()) if c.height else ''
    res.append(dict(symbol=s, delist=dd, name=o['name'], former=';'.join(o['former'][:3]), tenk_after=len(k10), bk=bk, item201=a201, form25_15=f25, next_day_new=cands))
df = pl.DataFrame(res); df.write_csv('/home/claude/delist/alive_check.csv')
sus = df.filter((pl.col('tenk_after') > 0) & ~pl.col('bk') & ~pl.col('item201'))
print(sus.height)
for x in sus.iter_rows(): print(x)
