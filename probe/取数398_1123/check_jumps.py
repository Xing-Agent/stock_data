#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 398 补 3:2005–2014 面板「单日跳 30% 以上又没记拆股」逐条拿 Yahoo 核。
用法:python3 check_jumps.py YAHOO.json.gz 待核.csv"""
import json, gzip, csv, sys, collections
from datetime import datetime, date
from zoneinfo import ZoneInfo
ET = ZoneInfo('America/New_York')
Y = json.load(gzip.open(sys.argv[1])); fn = sys.argv[2]
R = list(csv.DictReader(open(fn, encoding='utf-8-sig')))
out = []
for r in R:
    r = {k: v for k, v in r.items() if k in ('代码', '日期', '前收', '当天开', '当天收', '收盘比', '开盘比前收', '最接近的整比例', '判断')}
    t = r['代码']; y = Y.get(t.replace('.', '-'))
    spl = [(datetime.fromtimestamp(s[0], ET).date().isoformat(), s[1] / s[2]) for s in (y.get('spl', []) if isinstance(y, dict) else [])]
    near = [s for s in spl if abs((date.fromisoformat(s[0]) - date.fromisoformat(r['日期'])).days) <= 3]
    yr = None
    if isinstance(y, dict) and 't' in y:
        days = [datetime.fromtimestamp(x, ET).date().isoformat() for x in y['t']]
        idx = {d: i for i, d in enumerate(days)}; d = r['日期']
        if d in idx and idx[d] > 0 and y['c'][idx[d]] and y['c'][idx[d] - 1]: yr = y['c'][idx[d]] / y['c'][idx[d] - 1]
    pr = float(r['收盘比']); r['应补系数'] = ''
    if not isinstance(y, dict):
        r['Yahoo核对'] = 'Yahoo 查不到这只(已退市或改名)'; r['结论'] = '待核(Yahoo 没有)'
    elif near:
        k = near[0][1]
        r['Yahoo核对'] = f"Yahoo 记了 {near[0][0]} 拆股,新股数÷旧股数 = {k:g}" + (f";Yahoo 折算后当天 {(yr - 1) * 100:+.1f}%" if yr else '')
        r['结论'] = '漏记拆股(Yahoo 有记录)'; r['应补系数'] = round(1 / k, 6)
    elif yr is not None and abs(yr / pr - 1) < 0.05:
        r['Yahoo核对'] = f"Yahoo 当天也是 {(yr - 1) * 100:+.1f}%,没有拆股记录"; r['结论'] = '真行情或分拆(Yahoo 同样跳)'
    elif yr is not None:
        r['Yahoo核对'] = f"Yahoo 当天 {(yr - 1) * 100:+.1f}%,我们 {(pr - 1) * 100:+.1f}%"; r['结论'] = '我们这边价格对不上 Yahoo'
    else:
        r['Yahoo核对'] = 'Yahoo 那天没数据'; r['结论'] = '待核(Yahoo 没那天)'
    out.append(r)
c = collections.Counter(o['结论'] for o in out); print(c, len({o['代码'] for o in out if o['结论'].startswith('漏记')}))
for o in out:
    if o['结论'].startswith('我们'): print(o['代码'], o['日期'], o['收盘比'], o['Yahoo核对'])
out.sort(key=lambda o: (o['结论'], o['代码'], o['日期']))
with open(fn, 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
