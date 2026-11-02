import json, glob, os, polars as pl
cal = sorted(os.path.basename(f)[:10] for f in glob.glob('/home/claude/pituni/day/*.csv.gz') if '2016-01-01' <= os.path.basename(f)[:10] <= '2025-12-31')
ci = {d: i for i, d in enumerate(cal)}
res = []
for f in glob.glob('/home/claude/stock_data/exam_1042/*/daily.json'):
    d = json.load(open(f)); rows = d['data']; s = d['symbol']
    ds = [r['date'] for r in rows]
    idx = [ci.get(x) for x in ds]
    miss = sum(b - a - 1 for a, b in zip(idx, idx[1:]) if a is not None and b is not None)
    bad = sum(1 for r in rows if not r['close'] or r['close'] <= 0 or r['open'] is None or r['high'] < r['low'])
    # 复权后隔夜跳空 > 50%(检查有没有漏掉的拆股 / 代码换主体)
    fac = 1.0; adj = []
    for r in reversed(rows):
        adj.append((r['date'], r['open'] / fac, r['close'] / fac)); fac *= (r['split_coefficient'] or 1.0) if False else 1.0
    big = 0; f2 = 1.0; prev = None; jumps = []
    cum = 1.0; adjc = {}
    for r in reversed(rows):
        adjc[r['date']] = (r['open'] * cum, r['close'] * cum)
        cum *= 1.0 / (r['split_coefficient'] or 1.0)
    for a, b in zip(ds, ds[1:]):
        g = adjc[b][0] / adjc[a][1]
        if g > 1.5 or g < 0.5: jumps.append((b, round(g, 3)))
    res.append((s, len(rows), ds[0], ds[-1], miss, bad, len(jumps), str(jumps[:3])))
Q = pl.DataFrame(res, schema=['symbol', 'bars', 'first', 'last', 'missing_days', 'bad_bars', 'big_jumps', 'examples'], orient='row')
Q.write_csv('/home/claude/stock_data/exam_1042/qc_1102.csv')
print(Q.select(pl.len(), pl.col('missing_days').sum(), (pl.col('missing_days') > 0).sum().alias('有缺口的票'), pl.col('bad_bars').sum(), (pl.col('big_jumps') > 0).sum().alias('有大跳的票'), pl.col('big_jumps').sum()))
print('起点不在 2016-01-04 的:', Q.filter(pl.col('first') > '2016-01-04').height)
print(Q.filter(pl.col('big_jumps') > 0).sort('big_jumps', descending=True).head(25).select('symbol', 'big_jumps', 'examples').rows())
print(Q.sort('missing_days', descending=True).head(8).select('symbol', 'missing_days', 'first', 'last').rows())
