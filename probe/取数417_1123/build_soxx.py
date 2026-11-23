#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 417 第 1 样:SOXX(iShares 半导体 ETF)日线 + 1 小时线,口径和《ETF和币_1120》一样(直接调用 build_343.py 的同一套函数)。
大白话:
  · 这只基金 2010-10-14 以前的代码是 IGW(同一只基金改名),Polygon 里分两段,这里接成一条;source_ticker 列写着每天来自哪段。
  · Polygon 从 2003-09-10 才有;2001-07-13 上市到 2003-09-09 那两年只有日线,取自 Yahoo(Yahoo 价格已折两次 3 拆 1,这里乘回 9 换成原始价)。
  · 拆股:2024-03-07 和 2026-11-05 各一次 3 拆 1,都已折进 *_adj 和 adjusted_close;分红 Polygon 为主,缺的用 Yahoo 补。
  · 小时线:Polygon 原生 30 分钟线拼,每根不跨时段(盘前 / 常规 9:30 起 / 盘后),2003-09 起。
  · 取到 2026-11-20(上周五)收盘。
  · 坏点:小时线扫出 3 根影线离谱的(2008-09-19、2010-05-06 闪崩、2025-04-07),这 3 天拿 1 分钟线按《356》同一套办法清洗
    (都是全市场剧烈波动的日子,常规时段只剔离中位数 35% 以上的孤立成交)。
  · 2026-11-20 Polygon 没有盘中数据(30 分钟、1 分钟都空),小时线只到 11-19;日线有 11-20。
用法:python3 build_soxx.py POLYGON.json.gz YAHOO.json.gz OUT_DIR [1分钟线.json.gz]"""
import csv, gzip, json, os, sys
from collections import defaultdict
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'ETF和币_1120'))
import build_343 as B
import polars as pl

POLY, YAH, OUT = sys.argv[1:4]
if len(sys.argv) > 4:
    M = json.load(gzip.open(sys.argv[4])); B.EVENT_DAYS.update(k.split('|')[1] for k in M)
    for k, bars in M.items():
        B.CLEAN[k], nf = B.clean_minutes([[int(b[0])] + [float(x) for x in b[1:6]] + [int(b[6])] for b in bars], False, True)
        print('清洗', k, nf)
B.LAST = '2026-11-20'
B.parts_of = lambda t: [('YSOXX', None, '2003-09-09'), ('IGW', '2003-09-10', '2010-10-14'), ('SOXX', '2010-10-15', None)]
D = json.load(gzip.open(POLY))
Y = json.loads(gzip.decompress(open(YAH, 'rb').read()))
errs = [k for k, v in D.items() if v and v[-1] == 'ERR']; assert not errs, errs
# Yahoo 早期日线:价格 ×9、量 ÷9 换回原始股数(两次 3 拆 1 都在 2003 年之后)
D['d|YSOXX'] = [[ts * 1000, round(o * 9, 3), round(h * 9, 3), round(l * 9, 3), round(c * 9, 3), round(v / 9), 0] for ts, o, h, l, c, v in Y['early'] if c is not None]
D['div|YSOXX'], D['spl|YSOXX'] = [], []
json.dump(Y['Y'], open('/tmp/_ydiv_soxx.json', 'w')); B.load_ydiv('/tmp/_ydiv_soxx.json')
# 接缝核对:Yahoo×9 和 Polygon IGW 重叠的几天
ych = {B.et_day(r[0]): r[4] for r in D['d|YSOXX']}
seam = [(B.et_day(r[0]), ych.get(B.et_day(r[0])), r[4]) for r in D['d|IGW'][:8]]
print('接缝 Yahoo×9 vs IGW', seam)
rows, ds, spl = B.daily(D, 'SOXX')
od, oh = f'{OUT}/日线', f'{OUT}/小时线'
for p in (od, oh): os.makedirs(p, exist_ok=True)
cols = ['date', 'open', 'high', 'low', 'close', 'volume', 'dividend_amount', 'split_coefficient', 'open_adj', 'high_adj', 'low_adj',
        'close_adj', 'volume_adj', 'adj_factor', 'adjusted_close', 'source_ticker']
for d in ds:
    if rows[d]['source_ticker'] == 'YSOXX': rows[d]['source_ticker'] = 'Yahoo:SOXX'
with open(f'{od}/SOXX_日线.csv', 'w', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=cols); w.writeheader(); w.writerows(rows[d] for d in ds)
jumps = [(ds[i], round(rows[ds[i]]['close_adj'] / rows[ds[i - 1]]['close_adj'] - 1, 4)) for i in range(1, len(ds))
         if abs(rows[ds[i]]['close_adj'] / rows[ds[i - 1]]['close_adj'] - 1) > 0.15]
seam_ret = {d: round(rows[d]['close_adj'] / rows[ds[ds.index(d) - 1]]['close_adj'] - 1, 4) for d in ('2003-09-10', '2010-10-15', '2024-03-07', '2026-11-05')}
h = B.hourly(D, 'SOXX', range(2003, 2027), spl)
miss, diff = B.check(h, rows, '2003-09-10', B.LAST)
ok = sum(abs(x[3]) <= 0.01 for x in diff)
bad = [(d, dh, mh, round(r * 100, 2)) for d, dh, mh, r in diff if abs(r) > 0.01]
for (y,), g in h.with_columns(pl.col('d').str.slice(0, 4).alias('y')).group_by(['y'], maintain_order=True):
    g.drop('d', 'y').write_parquet(f'{oh}/SOXX_{y}.parquet', compression='zstd', compression_level=9, statistics=True)
yrs = defaultdict(lambda: [0, 0]); [yrs.__setitem__(d[:4], [yrs[d[:4]][0] + 1, yrs[d[:4]][1] + (abs(r) <= 0.01)]) for d, _, _, r in diff]
summ = dict(代码='SOXX', 日线起=ds[0], 日线止=ds[-1], 日线行数=len(ds), 分红次数=sum(1 for d in ds if rows[d]['dividend_amount']),
            Yahoo补分红=len(B.YADD), 拆股=';'.join(f'{d}×{k:g}' for d, k in spl[1].items()),
            接缝当天涨跌=';'.join(f'{d}:{x * 100:+.2f}%' for d, x in seam_ret.items()),
            折算后单日涨跌超15pct=';'.join(f'{d}({x * 100:+.1f}%)' for d, x in jumps),
            小时线起=h['d'].min(), 小时线止=h['d'].max(), 小时线行数=h.height, 小时线常规时段缺的天数=len(miss), 缺的天=';'.join(miss[:40]),
            比对天数=len(diff), 最高价差1pct以内=ok, 占比=f'{ok / len(diff) * 100:.2f}%')
with open(f'{OUT}/说明.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(summ)); w.writeheader(); w.writerow(summ)
with open(f'{OUT}/分红补自Yahoo.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.writer(fh); w.writerow(['代码', '除息日', '每股分红(原始股数)']); w.writerows(sorted(set(B.YADD)))
with open(f'{oh}/日线对不上的日子.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.writer(fh); w.writerow(['日期', '日线最高价', '小时线常规时段最高价', '差(%)']); w.writerows(bad)
with open(f'{OUT}/坏点修正_日线.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=['层', '代码', '时间', '原开', '原高', '原低', '原收', '新高', '新低']); w.writeheader(); w.writerows(B.LOG)
print('日线坏点', B.LOG)
for k, v in summ.items(): print(k, v)
print('按年比对', dict(sorted((y, f'{b}/{a}') for y, (a, b) in yrs.items())))
print('对不上', bad[:30])
