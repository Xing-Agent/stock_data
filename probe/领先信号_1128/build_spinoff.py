#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 562 第二项：分拆 / 特别分派折算表。
来源：
  1. Yahoo 的拆股记录里「比例不整」的那些 —— Yahoo 把分拆、特别分派、送股都当成拆股记，比例就是它用的折算系数
     (例:DUK 2007-01-03 记 10000:5811,意思是之前的价格 × 0.5811)。扫了 1,514 只(考卷 1,042 家 + 历来标普成分)。
  2. 《417》优先核的 47 处里判成「分拆/特别分红」的(Yahoo 没记或没那只票的，用开盘 ÷ 前收或合并条款算的系数)。
然后逐条去我们的日线(exam_pre2016_1107 / exam_1042 / market_ext_1105)看那天：有没有已经记了拆股、价格是不是真的跳了。
系数的用法：除权日「之前」的价格乘系数(成交量不动 —— 分拆不改变股数)。
用法:python3 build_spinoff.py yahoo_splits.json.gz 47处.csv OUT.csv"""
import csv, gzip, json, os, sys
YS, F47, OUT = sys.argv[1:4]
Y = json.load(gzip.open(YS))


def load(t):
    for p in (f'exam_pre2016_1107/{t}/daily.json.gz', f'exam_1042/{t}/daily.json', f'market_ext_1105/{t}/daily.json.gz'):
        if os.path.exists(p):
            J = json.load(gzip.open(p)) if p.endswith('gz') else json.load(open(p))
            yield p.split('/')[0], J['data'] if isinstance(J, dict) else J


def look(t, d):
    """在我们的日线里找除权日:返回 (库, 当天日期, 前收, 当天开, 记的拆股系数)"""
    res = []
    for lib, D in load(t):
        for i, x in enumerate(D):
            if x['date'] >= d and i:
                if x['date'] > d and (int(x['date'][:4]) - int(d[:4])) * 400 + (int(x['date'][5:7]) - int(d[5:7])) * 31 + int(x['date'][8:]) - int(d[8:]) > 6: break
                p = D[i - 1]; res.append((lib, x['date'], p['close'], x['open'], x.get('split_coefficient', 1.0) or 1.0)); break
    return res


rows = []
for t, d, n, dd, k in Y['SPIN']:
    if n == dd: continue
    if dd == 100 and 100 < n <= 110 or dd == 1000 and 1000 < n <= 1100: typ = f'送股(每 100 股送 {n - dd if dd == 100 else (n - dd) / 10:g} 股)'
    elif k < 1: typ = '分拆或特别分派'
    else: typ = '其他(比例 >1,多为合并换股或反向，单独看)'
    rows.append(dict(代码=t, 除权日=d, 类型=typ, 系数=round(k, 4), 系数怎么来的=f'Yahoo 记 {n}:{dd}', 来源='Yahoo 拆股记录'))
have = {(r['代码'], r['除权日']) for r in rows}
NAME = {'VRX': '老 Valeant 并入 Biovail(1.7809 股新股 + 16.77 美元特别分红)', 'DISCA': '每股 A 送 1 股 C 股', 'CY': '分拆 SunPower',
        'FNF': 'FNF / FNT 重组派股', 'NCR': '分拆 Teradata', 'STR': '分拆 QEP', 'DUK': '分拆 Spectra Energy', 'TYC': '分拆'}
for r in csv.DictReader(open(F47, encoding='utf-8-sig')):
    if r['结论'] != '分拆/特别分红': continue
    if (r['代码'], r['日期']) in have: continue
    rows.append(dict(代码=r['代码'], 除权日=r['日期'], 类型='分拆或特别分派', 系数=float(r['系数']), 系数怎么来的=r['说明'][:80], 来源='《417》47 处'))
# 逐条到我们的日线里看
for r in rows:
    L = look(r['代码'], r['除权日'])
    if not L: r['我们日线里'] = '没有这只或没这段'; continue
    lib, dd, pc, op, sc = L[0]
    gap = op / pc if pc else None
    if sc != 1.0: st = f'已记拆股 {sc:g}(不用再折)'
    elif gap is not None and abs(gap - r['系数']) < 0.06 and r['系数'] < 0.97: st = f'没折:当天开盘 ÷ 前收 = {gap:.3f},和系数对得上 —— 要按表折'
    elif gap is not None and r['系数'] >= 0.97: st = f'系数接近 1,影响小(开盘 ÷ 前收 {gap:.3f})'
    else: st = f'开盘 ÷ 前收 = {gap:.3f},和系数对不上，单独看'
    r['我们日线里'] = f'{lib} {dd}:{st}'
rows.sort(key=lambda r: (r['除权日'], r['代码']))
with open(OUT, 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=['代码', '除权日', '类型', '系数', '系数怎么来的', '来源', '我们日线里']); w.writeheader(); w.writerows(rows)
from collections import Counter
print(len(rows), Counter(r['类型'][:4] for r in rows))
print(Counter(r['我们日线里'].split(':')[-1][:4] if ':' in r['我们日线里'] else r['我们日线里'] for r in rows))
for t in ('DUK', 'NI', 'COG'):
    for r in rows:
        if r['代码'] == t: print(r)
