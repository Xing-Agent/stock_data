#!/usr/bin/env python3
# 手册 327:把分钟线库拼成「不跨时段」的 15 分钟线(只处理最活跃 200 只)。只读分钟线,结果写到 Downloads/xing_15m/out/。
# 用法:python3 agg_day.py SEG_JSON OUT_DIR day_file1 day_file2 ...   (已经做过的日子自动跳过,可以反复跑)
import json, os, sys, time
import numpy as np, pandas as pd

EARLY = {'2015-11-27', '2015-12-24', '2016-11-25', '2017-07-03', '2017-11-24', '2018-07-03', '2018-11-23', '2018-12-24', '2019-07-03',
         '2019-11-29', '2019-12-24', '2020-11-27', '2020-12-24', '2021-11-26', '2022-11-25', '2023-07-03', '2023-11-24', '2024-07-03',
         '2024-11-29', '2024-12-24', '2025-07-03', '2025-11-28', '2025-12-24'}
seg = json.load(open(sys.argv[1])); out = sys.argv[2]
by_t = {}
for folder, ss in seg.items():
    for t, a, b in ss: by_t.setdefault(t, []).append((folder, a, b))
t0 = time.time()
for fp in sys.argv[3:]:
    d = os.path.basename(fp)[:10]
    of = os.path.join(out, d[:4], d + '.csv.gz')
    if os.path.exists(of): continue
    want = {t: f for t, L in by_t.items() for (f, a, b) in L if a <= d <= b}
    if not want:
        continue
    df = pd.read_csv(fp)
    if 'window_start' in df.columns:
        df = df.rename(columns={'volume': 'v', 'open': 'o', 'close': 'c', 'high': 'h', 'low': 'l', 'transactions': 'n'})
        df['ts'] = df['window_start'] // 1_000_000
    else:
        df = df.rename(columns={'t': 'ts'})
    df = df[df['ticker'].isin(want.keys())]
    if df.empty:
        os.makedirs(os.path.dirname(of), exist_ok=True); pd.DataFrame().to_csv(of, index=False); continue
    et = pd.to_datetime(df['ts'], unit='ms', utc=True).dt.tz_convert('America/New_York')
    mins = (et.dt.hour * 60 + et.dt.minute).to_numpy()
    close = 13 * 60 if d in EARLY else 16 * 60
    keep = (mins >= 240) & (mins < 1200)
    df = df[keep]; et = et[keep]; mins = mins[keep]
    sess = np.where(mins < 570, 'pre', np.where(mins < close, 'regular', 'post'))
    startmin = (mins // 15) * 15  # 9:30、收盘、4:00、20:00 都是 15 的整数倍,直接按 15 分钟取整
    midnight = et.dt.normalize()
    start = (midnight + pd.to_timedelta(startmin, unit='m')).dt.tz_convert('UTC')
    df = df.assign(session=sess, start=(start.astype('int64') // 1_000_000).to_numpy(), folder=df['ticker'].map(want))
    df = df.sort_values(['ticker', 'ts'])
    g = df.groupby(['folder', 'ticker', 'start', 'session'], sort=True)
    a = g.agg(o=('o', 'first'), h=('h', 'max'), l=('l', 'min'), c=('c', 'last'), v=('v', 'sum'), n=('n', 'sum'), m=('o', 'size')).reset_index()
    os.makedirs(os.path.dirname(of), exist_ok=True)
    a.to_csv(of + '.tmp', index=False, compression='gzip'); os.replace(of + '.tmp', of)
    if time.time() - t0 > 150: break
print('done', round(time.time() - t0, 1))
