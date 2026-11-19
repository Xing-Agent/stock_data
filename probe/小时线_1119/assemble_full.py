#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 318 · 研发池 1 小时线全量:2015 来自 Polygon 30 分钟线(浏览器取),2016–2025 来自 Lin 电脑上的分钟线库(在那台电脑上用 agg_day.py 先拼成小时)。
大白话:
  · 分钟线库 2016-01 ~ 2021-03-25 那段是「已按拆股折算到下载那天」的价(REST 拉的),要先还原成原始价:
    每天拿研究库日线的原始最高价 ÷ 这天常规时段小时线的最高价 = 还原倍数;倍数只在拆股那天才变,
    所以取前后 11 天的中位数、再按「跳超过 2% 才算换档」做成台阶,价格 × 倍数、成交量 ÷ 倍数。2021-03-26 以后本来就是原始价。
  · 原始价有了以后,用我们自己的拆股表(研究库系数 + 全池版并股表修正)算折算价,和试水批一样。
  · 每根标 session(pre / regular / post),切法见 README。
用法:python3 assemble_full.py WORK_DIR OUT_DIR
"""
import csv, gzip, io, json, math, os, sys
from collections import defaultdict
from datetime import date
import numpy as np, polars as pl

R = '/home/claude/stock_data'
sys.path.insert(0, os.path.dirname(__file__))
import build_1h as B   # split_events(), EARLY, TABLE

EARLY = B.EARLY


def read_year(fp):
    raw = gzip.open(fp).read()
    raw = b'\n'.join(l for l in raw.split(b'\n') if l.count(b',') == 10 and not l.startswith(b'folder,'))
    df = pl.read_csv(io.BytesIO(raw), has_header=False, infer_schema=False,
                     new_columns=['folder', 'ticker', 'start', 'session', 'o', 'h', 'l', 'c', 'v', 'n', 'm'], truncate_ragged_lines=True)
    df = df.filter(pl.col('folder').is_not_null() & (pl.col('folder') != 'folder') & (pl.col('folder') != '') & pl.col('m').is_not_null())
    return df.with_columns(pl.col('start').cast(pl.Int64), *[pl.col(x).cast(pl.Float64) for x in 'ohlc'],
                           pl.col('v').cast(pl.Float64), pl.col('n').cast(pl.Int64), pl.col('m').cast(pl.Int32))


def read_2015(fp):
    J = json.load(gzip.open(fp))['data']
    rows = []
    for k, bars in J.items():
        f, t, a, b = k.split('|')
        for ts, o, h, l, c, v, n in bars: rows.append((f, t, a, b, ts, o, h, l, c, v, n))
    df = pl.DataFrame(rows, schema=['folder', 'ticker', 'a', 'b', 'ts', 'o', 'h', 'l', 'c', 'v', 'n'], orient='row')
    et = pl.from_epoch('ts', time_unit='ms').dt.replace_time_zone('UTC').dt.convert_time_zone('America/New_York')
    df = df.with_columns(et.alias('et')).with_columns(pl.col('et').dt.strftime('%Y-%m-%d').alias('d'),
                                                       (pl.col('et').dt.hour().cast(pl.Int32) * 60 + pl.col('et').dt.minute().cast(pl.Int32)).alias('mins'))
    df = df.filter((pl.col('d') >= pl.col('a')) & (pl.col('d') <= pl.col('b')) & (pl.col('mins') >= 240) & (pl.col('mins') < 1200))
    close = pl.when(pl.col('d').is_in(list(EARLY))).then(780).otherwise(960)
    df = df.with_columns(pl.when(pl.col('mins') < 570).then(pl.lit('pre')).when(pl.col('mins') < close).then(pl.lit('regular')).otherwise(pl.lit('post')).alias('session'))
    df = df.with_columns(pl.when(pl.col('session') == 'regular').then(570 + ((pl.col('mins') - 570) // 60) * 60).otherwise((pl.col('mins') // 60) * 60).alias('smin'))
    df = df.with_columns((pl.col('ts') - (pl.col('mins') - pl.col('smin')) * 60_000).alias('start'))
    df = df.sort(['folder', 'ts'])
    g = df.group_by(['folder', 'ticker', 'start', 'session'], maintain_order=True).agg(
        pl.col('o').first(), pl.col('h').max(), pl.col('l').min(), pl.col('c').last(), pl.col('v').sum().cast(pl.Float64), pl.col('n').sum(),
        (pl.len() * 30).cast(pl.Int32).alias('m'))
    return g.with_columns(*[pl.col(x).cast(pl.Float64) for x in 'ohlc'])


DAILY = {}


def daily(folder):
    if folder not in DAILY:
        fp = f'{R}/market_ext_1105/{folder}/daily.json.gz'
        if not os.path.exists(fp): fp = f'{R}/market_etf_1106/{folder}/daily.json.gz'
        DAILY[folder] = {x['date']: {'high': x.get('high')} for x in json.load(gzip.open(fp))['data'] if '2015-01-01' <= x['date'] <= '2025-12-31'}
    return DAILY[folder]


def unadjust(df):
    """2016-01-01 ~ 2021-03-25 的 REST 段:按日线原始最高价还原。返回加了 rest_mult 的 df 和每只票的还原记录"""
    df = df.with_columns(pl.from_epoch('start', time_unit='ms').dt.replace_time_zone('UTC').dt.convert_time_zone('America/New_York').dt.strftime('%Y-%m-%d').alias('d'))
    rest = df.filter(pl.col('d') < '2021-03-26')
    if rest.height == 0: return df.with_columns(pl.lit(1.0).alias('rest_mult')), {}
    hi = rest.filter(pl.col('session') == 'regular').group_by(['folder', 'd']).agg(pl.col('h').max().alias('mh'))
    mult_rows, notes = [], {}
    for (f,), g in hi.sort('d').group_by(['folder'], maintain_order=True):
        D = daily(f)
        ds = g['d'].to_list(); mh = g['mh'].to_list()
        r = [(D[d]['high'] / x) if d in D and D[d].get('high') and x else None for d, x in zip(ds, mh)]
        arr = np.array([np.nan if v is None else v for v in r])
        med = np.array([np.nanmedian(arr[max(0, i - 5): i + 6]) if np.isfinite(arr[max(0, i - 5): i + 6]).any() else np.nan for i in range(len(arr))])
        # 台阶:和上一档差 > 2% 才换档
        step, cur = [], None
        for m in med:
            if np.isfinite(m) and (cur is None or abs(m / cur - 1) > 0.04): cur = m
            step.append(cur if cur is not None else np.nan)
        step = np.array(step, dtype=float)
        if np.isnan(step).any():
            s = pl.Series(step).fill_nan(None).fill_null(strategy='backward').fill_null(strategy='forward').to_numpy(); step = s
        # 常见值规整:离 1 很近就当 1
        def snap(x):
            # 还原倍数只能是「拆股比例的乘积」:要么离 1 很近(就是 1),要么能凑成干净的分数;凑不成的当噪音
            if not np.isfinite(x) or x <= 0 or abs(x - 1) < 0.04: return 1.0
            if x < 1:
                inv = snap(1 / x)
                return None if inv is None else 1 / inv
            for den in range(1, 13):
                num = round(x * den)
                if num > 0 and abs(num / den / x - 1) < 0.006: return num / den
            return float(x)   # 凑不成干净分数的(送股、分拆调整这类)就用实测值
        st2, prev = [], 1.0
        for x in step:
            v = snap(x)
            if v is None: v = prev
            st2.append(v); prev = v
        step = np.array(st2)
        # 拆股那天前后中位数会「抹平」台阶:当天自己的比值和中位数差 >2%、且和前一天或后一天的比值一致(差 <1%),就用当天自己的
        for i in range(len(arr)):
            v = arr[i]
            if not np.isfinite(v) or not np.isfinite(step[i]) or abs(v / step[i] - 1) <= 0.04: continue
            nb = [arr[j] for j in (i - 1, i + 1) if 0 <= j < len(arr) and np.isfinite(arr[j])]
            if any(abs(v / x - 1) < 0.01 for x in nb):
                sv = snap(v)
                if sv is not None: step[i] = sv
        mult_rows += list(zip([f] * len(ds), ds, step.tolist()))
        lv = sorted({round(x, 4) for x in step.tolist()})
        if lv != [1.0]: notes[f] = lv
    M = pl.DataFrame(mult_rows, schema=['folder', 'd', 'rest_mult'], orient='row')
    df = df.join(M, on=['folder', 'd'], how='left')
    # 只有盘前盘后、没有常规时段的日子:按同一只票最近的倍数补
    df = df.sort(['folder', 'start']).with_columns(
        pl.when(pl.col('d') < '2021-03-26').then(pl.col('rest_mult').forward_fill().backward_fill().over('folder')).otherwise(1.0).alias('rest_mult'))
    df = df.with_columns(pl.col('rest_mult').fill_null(1.0))
    return df, notes


def main(work, out):
    os.makedirs(out, exist_ok=True)
    EV = {}
    report = defaultdict(dict)
    for y in range(2015, 2026):
        if os.path.exists(f'{out}/{y}.parquet'):   # 已经做过的年份:只读回来做统计
            df = pl.read_parquet(f'{out}/{y}.parquet', columns=['symbol', 'time_utc', 'session'])
            df = df.with_columns(pl.col('time_utc').dt.convert_time_zone('America/New_York').dt.strftime('%Y-%m-%d').alias('d'))
            for f, a, b, n in df.group_by('symbol').agg(pl.col('d').min(), pl.col('d').max().alias('b'), pl.len()).iter_rows():
                r = report[f]; r['起'] = min(r.get('起', a), a); r['止'] = max(r.get('止', b), b); r['行数'] = r.get('行数', 0) + n
            for f, d in df.filter(pl.col('session') == 'regular').select('symbol', 'd').unique().iter_rows():
                report[f].setdefault('有常规K线的天', set()).add(d)
            print(y, 'skip(已做)', flush=True)
            continue
        df = read_2015(f'{work}/h1_2015_raw30m_1119.json.gz') if y == 2015 else read_year(f'{work}/{y}.csv.gz')
        if y <= 2021:
            df, notes = unadjust(df) if y >= 2016 else (df.with_columns(pl.lit(1.0).alias('rest_mult')), {})
            for f, lv in notes.items(): report[f].setdefault('还原倍数', set()).update(lv)
        else:
            df = df.with_columns(pl.lit(1.0).alias('rest_mult'))
        df = df.with_columns((pl.col('o') * pl.col('rest_mult')).alias('open'), (pl.col('h') * pl.col('rest_mult')).alias('high'),
                             (pl.col('l') * pl.col('rest_mult')).alias('low'), (pl.col('c') * pl.col('rest_mult')).alias('close'),
                             (pl.col('v') / pl.col('rest_mult')).round(0).alias('volume'))
        et = pl.from_epoch('start', time_unit='ms').dt.replace_time_zone('UTC').dt.convert_time_zone('America/New_York')
        df = df.with_columns(et.dt.strftime('%Y-%m-%d').alias('d'))
        # 我们自己的拆股折算
        fac_rows = []
        for f, d in df.select('folder', 'd').unique().iter_rows():
            if f not in EV: EV[f] = B.split_events(f)[0]
            c = 1.0
            for e, k in EV[f]:
                if d < e: c *= k
            fac_rows.append((f, d, c))
        F = pl.DataFrame(fac_rows, schema=['folder', 'd', 'adj_factor'], orient='row')
        df = df.join(F, on=['folder', 'd'], how='left')
        df = df.with_columns(*[(pl.col(x) / pl.col('adj_factor')).alias(x + '_adj') for x in ('open', 'high', 'low', 'close')],
                             (pl.col('volume') * pl.col('adj_factor')).alias('volume_adj'))
        df = df.with_columns(pl.from_epoch('start', time_unit='ms').dt.replace_time_zone('UTC').alias('time_utc'))
        df = df.select(pl.col('folder').alias('symbol'), 'time_utc', 'session', 'open', 'high', 'low', 'close', 'volume',
                       'open_adj', 'high_adj', 'low_adj', 'close_adj', 'volume_adj', 'adj_factor', pl.col('n').alias('trades'),
                       pl.col('m').alias('minutes'), pl.col('ticker').alias('source_ticker'), 'd').sort(['symbol', 'time_utc'])
        # 每只票的统计
        st = df.group_by('symbol').agg(pl.col('d').min().alias('a'), pl.col('d').max().alias('b'), pl.len().alias('n'),
                                       pl.col('d').filter(pl.col('session') == 'regular').n_unique().alias('days'))
        for f, a, b, n, days in st.iter_rows():
            r = report[f]; r['起'] = min(r.get('起', a), a); r['止'] = max(r.get('止', b), b); r['行数'] = r.get('行数', 0) + n
        for f, d in df.filter(pl.col('session') == 'regular').select('symbol', 'd').unique().iter_rows():
            report[f].setdefault('有常规K线的天', set()).add(d)
        df.drop('d').write_parquet(f'{out}/{y}.parquet', compression='zstd', compression_level=9, statistics=True)
        print(y, df.height, os.path.getsize(f'{out}/{y}.parquet') // 1_000_000, 'MB', flush=True)
    return report, EV


if __name__ == '__main__':
    work, out = sys.argv[1], sys.argv[2]
    rep, EV = main(work, out)
    spy = [x['date'] for x in json.load(gzip.open(f'{R}/market_etf_1106/SPY/daily.json.gz'))['data']]
    seg = json.load(open('/mnt/user-data/outputs/xing_1h/segments.json'))
    names = [x.strip() for x in open(f'{R}/probe/挂件_1119/小时线取数名单_研发池中档_1119.txt') if x.strip()] + ['SPY', 'QQQ']
    rows = []
    for f in names:
        r = rep.get(f)
        D = daily(f)
        dd = sorted(d for d in D if '2015-01-01' <= d <= '2025-12-31')
        if not r:
            rows.append(dict(代码=f, 日线起=dd[0] if dd else '', 日线止=dd[-1] if dd else '', 小时线起='', 小时线止='', 行数=0, 常规时段缺的天数=len(dd), 缺的例子='',
                             拆股折算='', 还原倍数='', 说明='取不到:这只票这段时间分钟线库和 Polygon 都没有小时数据' if dd else '这只票 2015–2025 没有行情(研究库日线也没有)'))
            continue
        have = r['有常规K线的天']
        miss = [d for d in dd if d not in have]
        ev = [f'{e}×{k:g}' for e, k in EV.get(f, []) if '2015-01-01' <= e <= '2026-12-31']
        rows.append(dict(代码=f, 日线起=dd[0] if dd else '', 日线止=dd[-1] if dd else '', 小时线起=r['起'], 小时线止=r['止'], 行数=r['行数'],
                         常规时段缺的天数=len(miss), 缺的例子=';'.join(miss[:12]), 拆股折算=';'.join(ev),
                         还原倍数=';'.join(f'{x:g}' for x in sorted(r.get('还原倍数', []))), 说明=''))
    with open(f'{out}/说明_每只票.csv', 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    print('done', len(rows))
