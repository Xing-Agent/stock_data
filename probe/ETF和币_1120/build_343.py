#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 343:23 只指数 / 行业 / 杠杆 ETF 的日线(2003 起)和 1 小时线(2015 起;2004–2014 先拿 SPY 试、过关后其余也取了)。
大白话:
  · 全部来自 Polygon(Lin 浏览器取,adjusted=false 原始价 + 分红 + 拆股记录)。
  · 日线格式和《指数ETF长历史_1120》一样:原始价、只折拆股的 *_adj、拆股加分红都折的 adjusted_close。
  · 小时线格式和《小时线_1119》全量一样:用 Polygon 原生 30 分钟线拼,每根不跨时段(盘前整点、常规从 9:30 起、盘后整点),
    半日交易日 13:00 以后算盘后,夜盘不要。折算按 Polygon 拆股记录,折到今天。
  · 今天(11-20)美股还在交易,只取到 11-19 收盘,不放半天的数据。
  · QQQ 2004-12-01 ~ 2011-03-22 那段代码是 QQQQ(同一只基金),日线、小时线都接成一条。
用法:python3 build_343.py RAW.json.gz OUT_DIR RAW_2004_2014.json.gz
"""
import csv, gzip, json, os, sys
from collections import defaultdict
from datetime import datetime
from zoneinfo import ZoneInfo
import polars as pl

ET = ZoneInfo('America/New_York')
LAST = '2026-11-19'
TICKERS = ['SPY', 'QQQ', 'IWM', 'DIA', 'XLK', 'XLF', 'XLE', 'XLV', 'XLI', 'XLY', 'XLP', 'XLU', 'XLB', 'XLRE', 'XLC', 'SMH', 'KRE',
           'TQQQ', 'SQQQ', 'SOXL', 'SOXS', 'SH', 'PSQ']
# 半日交易日(13:00 收盘)。2015–2025 同《小时线_1119》;2004–2014 按 NYSE 公告;2026 到 11-19 为止没有
EARLY = {'2004-11-26', '2005-11-25', '2006-07-03', '2006-11-24', '2007-07-03', '2007-11-23', '2007-12-24', '2008-07-03', '2008-11-28',
         '2008-12-24', '2009-11-27', '2009-12-24', '2010-11-26', '2011-11-25', '2012-07-03', '2012-11-23', '2012-12-24', '2013-07-03',
         '2013-11-29', '2013-12-24', '2014-07-03', '2014-11-28', '2014-12-24',
         '2015-11-27', '2015-12-24', '2016-11-25', '2017-07-03', '2017-11-24', '2018-07-03', '2018-11-23', '2018-12-24', '2019-07-03',
         '2019-11-29', '2019-12-24', '2020-11-27', '2020-12-24', '2021-11-26', '2022-11-25', '2023-07-03', '2023-11-24', '2024-07-03',
         '2024-11-29', '2024-12-24', '2025-07-03', '2025-11-28', '2025-12-24'}


def et_day(ts): return datetime.fromtimestamp(ts / 1000, ET).date().isoformat()


# ---- 《356》修坏点:可疑的那些天,拿 1 分钟线重拼,剔掉孤立的离群成交 ----
LEV = {'TQQQ', 'SQQQ', 'SOXL', 'SOXS'}
CLEAN, LOG = {}, []      # CLEAN['SPY|2004-08-18'] = 清洗后的 1 分钟线;LOG 记下改了什么


# 全市场一起剧烈波动的日子(23 只里有 3 只以上同一天被扫出来):闪崩、2008 年 9–11 月、2015-08-24、2020 年 3 月、2025-04-07 等。
# 这些天常规时段的大振幅多半是真的,只剔掉离得离谱的(1 倍 35%、3 倍 70%);盘前盘后照常严,比如 SOXL 2010-05-06 的 0.15、SPY 2008-09-29 的 11.85
EVENT_DAYS = set()


def clean_minutes(bars, lev, event=False):
    """一根 1 分钟线跟前后各 5 根的收盘价中位数比:最高 / 最低离得太远(平常日子 1 倍 6%、3 倍杠杆 15%)就是孤立的坏成交,
    把最高压回开收盘、最低抬回开收盘;开盘收盘都离得太远的整根丢掉。连续的真行情(闪崩、熔断)前后几根一起动,不会被删。"""
    import statistics
    k0, k1 = (0.15 if lev else 0.06), (0.70 if lev else 0.35)
    bars = sorted(bars); cs = [b[4] for b in bars]; out, n_fix = [], 0
    for i, (ts, o, h, l, c, v, n) in enumerate(bars):
        et = datetime.fromtimestamp(ts / 1000, ET); m = et.hour * 60 + et.minute
        k = k1 if event and 570 <= m < (780 if et.date().isoformat() in EARLY else 960) else k0   # 放宽只放常规时段;盘前盘后照常严
        nb = cs[max(0, i - 5): i] + cs[i + 1: i + 6]
        if not nb: out.append([ts, o, h, l, c, v, n]); continue
        ref = statistics.median(nb)
        bo, bc = abs(o / ref - 1) > k, abs(c / ref - 1) > k
        if bo and bc: n_fix += 1; continue
        if bo: o = c
        if bc: c = o
        h2 = h if h <= ref * (1 + k) else max(o, c)
        l2 = l if l >= ref * (1 - k) else min(o, c)
        n_fix += (h2 != h) + (l2 != l) + bo + bc
        out.append([ts, o, h2, l2, c, v, n])
    return out, n_fix


# ---- 《356》XLF 2016-09-19 分出 XLRE:Polygon 把它同时记成「拆股 ×1.139」和「现金分红 4.44」,重复算了两遍 ----
# 改成:只按分出去的价值折价(前收 ÷ (前收 − 4.44356)),不折量,不再当分红,也不当拆股
SPINOFF = {('XLF', '2016-09-19'): 4.44356}


def parts_of(t):
    return [('QQQ', None, '2004-11-30'), ('QQQQ', '2004-12-01', '2011-03-22'), ('QQQ', '2011-03-23', None)] if t == 'QQQ' else [(t, None, None)]


def daily(D, t):
    rows, divs, spl = {}, {}, {}
    for src, a, b in parts_of(t):
        for ts, o, h, l, c, v, n in D['d|' + src]:
            d = et_day(ts)
            if (a and d < a) or (b and d > b) or d > LAST: continue
            rows[d] = dict(date=d, open=o, high=h, low=l, close=c, volume=v, source_ticker=src)
        for ex, amt, pay, typ, fr in D['div|' + src]:
            if (a and ex < a) or (b and ex > b) or ex > LAST: continue
            divs[ex] = divs.get(ex, 0) + float(amt)
        for ex, f, to in D['spl|' + src]:
            if ex <= LAST: spl[ex] = to / f
    spin = {d: amt for (tt, d), amt in SPINOFF.items() if tt == t}
    for d, amt in spin.items():
        spl.pop(d, None); divs[d] = round(divs.get(d, 0) - amt, 6)
        if abs(divs[d]) < 1e-9: divs.pop(d)
    ds = sorted(rows)
    for d in ds:   # 坏点:可疑的日子用清洗后的 1 分钟线核最高最低
        m = CLEAN.get(f'{t}|{d}')
        if not m: continue
        r = rows[d]; cm, cl = max(b[2] for b in m), min(b[3] for b in m)
        nh = r['high'] if r['high'] <= cm * 1.005 else max(cm, r['open'], r['close'])
        nl = r['low'] if r['low'] >= cl * 0.995 else min(cl, r['open'], r['close'])
        if nh != r['high'] or nl != r['low']:
            LOG.append(dict(层='日线', 代码=t, 时间=d, 原开=r['open'], 原高=r['high'], 原低=r['low'], 原收=r['close'], 新高=nh, 新低=nl))
            r['high'], r['low'] = nh, nl
    for d in ds:
        rows[d]['dividend_amount'] = round(divs.get(d, 0.0), 6); rows[d]['split_coefficient'] = spl.get(d, 1.0)
    for ex, amt in divs.items():   # 除息日不是交易日的(极少):挪到之后第一个交易日
        if ex not in rows and ds[0] <= ex <= ds[-1]:
            nxt = next(x for x in ds if x > ex); rows[nxt]['dividend_amount'] = round(rows[nxt]['dividend_amount'] + amt, 6)
    lost = [ex for ex in spl if ex not in rows and ds[0] <= ex <= ds[-1]]
    for ex in lost:                # 拆股生效日不是交易日的:挪到之后第一个交易日
        nxt = next(x for x in ds if x > ex); rows[nxt]['split_coefficient'] *= spl[ex]
    pspin = {}
    for d, amt in spin.items():
        pc = rows[ds[ds.index(d) - 1]]['close']; pspin[d] = pc / (pc - amt)
    f_split, f_spin, f_tr = 1.0, 1.0, 1.0
    for i in range(len(ds) - 1, -1, -1):
        r = rows[ds[i]]
        r['adj_factor'] = f_split * f_spin                       # 价格折算系数(含分拆折价)
        for k in ('open', 'high', 'low', 'close'): r[k + '_adj'] = round(r[k] / r['adj_factor'], 6)
        r['volume_adj'] = round(r['volume'] * f_split, 2)        # 成交量只按拆股折
        r['adjusted_close'] = round(r['close'] / r['adj_factor'] * f_tr, 6)
        f_split *= r['split_coefficient']; f_spin *= pspin.get(ds[i], 1.0)
        if r['dividend_amount'] and i > 0:
            f_tr *= (1 - r['dividend_amount'] / rows[ds[i - 1]]['close'])
    psp = {d: rows[d]['split_coefficient'] for d in ds if rows[d]['split_coefficient'] != 1.0}
    allp = dict(psp)
    for d, x in pspin.items(): allp[d] = allp.get(d, 1.0) * x
    return rows, ds, (allp, psp)


def hourly(D, t, years, splits):
    """30 分钟线 → 不跨时段的 1 小时线;splits = (价格系数 {生效日: 系数}, 成交量系数 {生效日: 系数}),折到今天。
    可疑的日子(CLEAN 里有的)不用 30 分钟线,改用清洗后的 1 分钟线拼"""
    splits, vsplits = splits
    rec = []
    cdays = {k.split('|')[1] for k in CLEAN if k.startswith(t + '|')}
    for src, a, b in parts_of(t):
        for y in years:
            if (b and f'{y}-01-01' > b) or (a and f'{y}-12-31' < a): continue   # 这一年不在这段代码的时间里
            for ts, o, h, l, c, v, n in D.get(f'm30|{src}|{y}', []):
                if et_day(ts) in cdays: continue
                rec.append((src, a or "0000", b or "9999", int(ts), float(o), float(h), float(l), float(c), float(v), int(n), 30))
    for d in cdays:
        src = next(s for s, a, b in parts_of(t) if (not a or d >= a) and (not b or d <= b))
        for ts, o, h, l, c, v, n in CLEAN[f'{t}|{d}']:
            rec.append((src, '0000', '9999', int(ts), float(o), float(h), float(l), float(c), float(v), int(n), 1))
    if not rec: return None
    df = pl.DataFrame(rec, schema=['ticker', 'a', 'b', 'ts', 'o', 'h', 'l', 'c', 'v', 'n', 'w'], orient='row').unique(['ticker', 'ts'])
    et = pl.from_epoch('ts', time_unit='ms').dt.replace_time_zone('UTC').dt.convert_time_zone('America/New_York')
    df = df.with_columns(et.dt.strftime('%Y-%m-%d').alias('d'), (et.dt.hour().cast(pl.Int32) * 60 + et.dt.minute().cast(pl.Int32)).alias('mins'))
    df = df.filter((pl.col('d') >= pl.col('a')) & (pl.col('d') <= pl.col('b')) & (pl.col('d') <= LAST) & (pl.col('mins') >= 240) & (pl.col('mins') < 1200))
    close = pl.when(pl.col('d').is_in(list(EARLY))).then(780).otherwise(960)
    df = df.with_columns(pl.when(pl.col('mins') < 570).then(pl.lit('pre')).when(pl.col('mins') < close).then(pl.lit('regular')).otherwise(pl.lit('post')).alias('session'))
    df = df.with_columns(pl.when(pl.col('session') == 'regular').then(570 + ((pl.col('mins') - 570) // 60) * 60).otherwise((pl.col('mins') // 60) * 60).alias('smin'))
    df = df.with_columns((pl.col('ts') - (pl.col('mins') - pl.col('smin')) * 60_000).alias('start')).sort('ts')
    g = df.group_by(['ticker', 'start', 'session', 'd'], maintain_order=True).agg(
        pl.col('o').first().alias('open'), pl.col('h').max().alias('high'), pl.col('l').min().alias('low'), pl.col('c').last().alias('close'),
        pl.col('v').sum().alias('volume'), pl.col('n').sum().alias('trades'), pl.col('w').sum().cast(pl.Int32).alias('minutes'))
    fac = {d: 1.0 for d in g['d'].unique().to_list()}; vfac = dict(fac)
    for d in fac:
        for e, k in splits.items():
            if d < e: fac[d] *= k
        for e, k in vsplits.items():
            if d < e: vfac[d] *= k
    g = g.with_columns(pl.col('d').replace_strict(fac, return_dtype=pl.Float64).alias('adj_factor'),
                       pl.col('d').replace_strict(vfac, return_dtype=pl.Float64).alias('vf'))
    g = g.with_columns(*[(pl.col(x) / pl.col('adj_factor')).alias(x + '_adj') for x in ('open', 'high', 'low', 'close')],
                       (pl.col('volume') * pl.col('vf')).alias('volume_adj'),
                       pl.from_epoch('start', time_unit='ms').dt.replace_time_zone('UTC').alias('time_utc'), pl.lit(t).alias('symbol'))
    return g.select('symbol', 'time_utc', 'session', 'open', 'high', 'low', 'close', 'volume', 'open_adj', 'high_adj', 'low_adj', 'close_adj',
                    'volume_adj', 'adj_factor', 'trades', 'minutes', pl.col('ticker').alias('source_ticker'), 'd').sort('time_utc')


def check(h, rows, a0, b0):
    """每天常规时段最高价 vs 日线最高价;常规时段缺的天"""
    hi = dict(h.filter(pl.col('session') == 'regular').group_by('d').agg(pl.col('high').max()).iter_rows())
    dd = [d for d in rows if a0 <= d <= b0]
    miss = [d for d in dd if d not in hi]
    diff = [(d, rows[d]['high'], hi[d], hi[d] / rows[d]['high'] - 1) for d in dd if d in hi and rows[d]['high']]
    return miss, diff


def main(raw, out):
    D = json.load(gzip.open(raw))
    if len(sys.argv) > 3: D.update(json.load(gzip.open(sys.argv[3])))   # 2004–2014 那批 30 分钟线
    if len(sys.argv) > 4:   # 《356》可疑日子的 1 分钟线
        M = json.load(gzip.open(sys.argv[4])); nfix = 0
        from collections import Counter
        cnt = Counter(k.split('|')[1] for k in M); EVENT_DAYS.update(d for d, n in cnt.items() if n >= 3)
        for k, bars in M.items():
            t, d = k.split('|')
            CLEAN[k], nf = clean_minutes([[int(b[0])] + [float(x) for x in b[1:6]] + [int(b[6])] for b in bars], t in LEV, d in EVENT_DAYS); nfix += nf
        print('event days', sorted(EVENT_DAYS))
        print('clean days', len(CLEAN), 'minute fixes', nfix)
    errs = [k for k, v in D.items() if v and v[-1] == 'ERR']
    assert not errs, errs
    od, oh, ot = f'{out}/日线', f'{out}/小时线_2015起', f'{out}/小时线_2004_2014'
    for p in (od, oh, ot): os.makedirs(p, exist_ok=True)
    cols = ['date', 'open', 'high', 'low', 'close', 'volume', 'dividend_amount', 'split_coefficient', 'open_adj', 'high_adj', 'low_adj',
            'close_adj', 'volume_adj', 'adj_factor', 'adjusted_close', 'source_ticker']
    summ, Hs, bad = [], [], []
    for t in TICKERS:
        rows, ds, spl = daily(D, t)
        with open(f'{od}/{t}_日线.csv', 'w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows[d] for d in ds)
        # 日线自己:折算后单日涨跌超过 40% 的(拆股没折对会冒出来)
        jumps = []
        for i in range(1, len(ds)):
            r0, r1 = rows[ds[i - 1]], rows[ds[i]]
            x = r1['close_adj'] / r0['close_adj'] - 1
            if abs(x) > 0.4: jumps.append(f'{ds[i]}({x * 100:+.0f}%)')
        h = hourly(D, t, range(2015, 2027), spl)
        h = h.filter(pl.col('d') >= '2015-01-01')
        miss, diff = check(h, rows, max('2015-01-01', ds[0]), LAST)
        ok = sum(abs(x[3]) <= 0.01 for x in diff)
        bad += [(t, d, dh, mh, round(r * 100, 2)) for d, dh, mh, r in diff if abs(r) > 0.01]
        Hs.append(h)
        divd = [d for d in ds if rows[d]['dividend_amount']]
        summ.append(dict(代码=t, 日线起=ds[0], 日线止=ds[-1], 日线行数=len(ds), 分红次数=len(divd), 拆股=';'.join(f'{d}×{k:g}' for d, k in spl[1].items()) + (';2016-09-19 分出XLRE(只折价)' if t == 'XLF' else ''),
                         折算后单日涨跌超40pct=';'.join(jumps), 小时线起=h['d'].min(), 小时线止=h['d'].max(), 小时线行数=h.height,
                         小时线常规时段缺的天数=len(miss), 缺的天=';'.join(miss[:30]), 比对天数=len(diff), 最高价差1pct以内=ok,
                         占比=f'{ok / len(diff) * 100:.2f}%' if diff else ''))
        print(summ[-1], flush=True)
    H = pl.concat(Hs)
    sizes = []
    for (y,), g in H.with_columns(pl.col('d').str.slice(0, 4).alias('y')).group_by(['y'], maintain_order=True):
        fp = f'{oh}/{y}.parquet'; g.drop('d', 'y').sort(['symbol', 'time_utc']).write_parquet(fp, compression='zstd', compression_level=9, statistics=True)
        sizes.append((y, g.height, os.path.getsize(fp) // 1000))
    print(sorted(sizes))
    with open(f'{out}/坏点修正_日线.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=['层', '代码', '时间', '原开', '原高', '原低', '原收', '新高', '新低']); w.writeheader(); w.writerows(LOG)
    with open(f'{out}/说明_每只.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=list(summ[0])); w.writeheader(); w.writerows(summ)
    with open(f'{oh}/日线对不上的日子.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.writer(fh); w.writerow(['代码', '日期', '日线最高价', '小时线常规时段最高价', '差(%)']); w.writerows(bad)
    # 2004–2014:先拿 SPY 试(逐年核对),过关后其余也取了
    trial_rows, Hs2, bad2 = [], [], []
    for t in TICKERS:
        rows, ds, spl = daily(D, t)
        if ds[0] > '2014-12-31': continue
        h = hourly(D, t, range(2004, 2015), spl)
        if h is None: continue
        h = h.filter((pl.col('d') >= '2004-01-01') & (pl.col('d') <= '2014-12-31'))
        miss, diff = check(h, rows, max('2004-01-01', ds[0]), '2014-12-31')
        ok = sum(abs(x[3]) <= 0.01 for x in diff)
        bad2 += [(t, d, dh, mh, round(r * 100, 2)) for d, dh, mh, r in diff if abs(r) > 0.01]
        Hs2.append(h)
        trial_rows.append(dict(代码=t, 小时线起=h['d'].min(), 小时线止=h['d'].max(), 小时线行数=h.height, 常规时段缺的天数=len(miss),
                               缺的天=';'.join(miss[:30]) + (' …' if len(miss) > 30 else ''), 比对天数=len(diff), 最高价差1pct以内=ok,
                               占比=f'{ok / len(diff) * 100:.2f}%' if diff else ''))
        print(trial_rows[-1], flush=True)
        if t == 'SPY':
            byy = defaultdict(lambda: [0, 0, 0, 0])
            for d, dh, mh, r in diff:
                b = byy[d[:4]]; b[0] += 1; b[1] += abs(r) <= 0.01
            pre = h.filter(pl.col('session') != 'regular').group_by(pl.col('d').str.slice(0, 4).alias('y')).agg(
                pl.col('d').n_unique().alias('n1'), pl.len().alias('n2'))
            for y, nd, nb in pre.iter_rows(): byy[y][2] = nd; byy[y][3] = nb
            spy = [dict(年=y, 比对天数=v[0], 最高价差1pct以内=v[1], 占比=f'{v[1] / v[0] * 100:.2f}%', 有盘前盘后的天=v[2], 盘前盘后根数=v[3])
                   for y, v in sorted(byy.items())]
            with open(f'{ot}/SPY试取_逐年核对.csv', 'w', newline='', encoding='utf-8-sig') as fh:
                w = csv.DictWriter(fh, fieldnames=list(spy[0])); w.writeheader(); w.writerows(spy)
    H2 = pl.concat(Hs2)
    for (y,), g in H2.with_columns(pl.col('d').str.slice(0, 4).alias('y')).group_by(['y'], maintain_order=True):
        g.drop('d', 'y').sort(['symbol', 'time_utc']).write_parquet(f'{ot}/{y}.parquet', compression='zstd', compression_level=9, statistics=True)
    with open(f'{ot}/说明_每只.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=list(trial_rows[0])); w.writeheader(); w.writerows(trial_rows)
    with open(f'{ot}/日线对不上的日子.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.writer(fh); w.writerow(['代码', '日期', '日线最高价', '小时线常规时段最高价', '差(%)']); w.writerows(bad2)
    print('2004-2014', H2.height, 'bad', len(bad2), sum(r['常规时段缺的天数'] for r in trial_rows))


if __name__ == '__main__':
    main(sys.argv[1], sys.argv[2])
