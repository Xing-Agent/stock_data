#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 562 第一项的 2、3:VIX3M 和信用利差替代品。
  · VIX3M:2009-09-18 起用 CBOE 官方 CSV(cdn.cboe.com VIX3M_History.csv);更早(2006-07-17 起,当时叫 VXV)用 Yahoo ^VIX3M。重叠段逐日比对。
  · 信用:FRED 上 ICE 高收益利差 BAMLH0A0HYM2 现在只给最近 3 年(2023-11-27 起),替代品两样:
      ① HYG、IEF 复权日线(Yahoo adjclose,拆股分红都折),外加 HYG÷IEF 比值;
      ② 穆迪 Baa 公司债减 10 年国债 BAA10Y(FRED,1986 起,没有转载限制)。
用法:python3 build_vix3m_credit.py VIX3M_History.csv yahoo_562.json.gz fred目录 OUT"""
import csv, gzip, json, sys, os
from datetime import datetime
from zoneinfo import ZoneInfo
CB, YF, FR, OUT = sys.argv[1:5]; ET = ZoneInfo('America/New_York')
Y = json.load(gzip.open(YF))


def yahoo(s):
    R = Y[s]['chart']['result'][0]; q = R['indicators']['quote'][0]; a = R['indicators']['adjclose'][0]['adjclose']; out = {}
    for i, t in enumerate(R['timestamp']):
        if q['close'][i] is None: continue
        out[datetime.fromtimestamp(t, ET).date().isoformat()] = (q['open'][i], q['high'][i], q['low'][i], q['close'][i], a[i], q['volume'][i])
    return out


# VIX3M
d1 = os.path.join(OUT, 'VIX3M'); os.makedirs(d1, exist_ok=True)
cb = {}
for r in csv.DictReader(open(CB)):
    m, d, y = r['DATE'].split('/'); cb[f'{y}-{m}-{d}'] = tuple(float(r[k]) for k in ('OPEN', 'HIGH', 'LOW', 'CLOSE'))
yv = yahoo('^VIX3M')
ov = [(d, cb[d][3], round(yv[d][3], 2)) for d in sorted(cb) if d in yv]
bad = [x for x in ov if abs(x[1] - x[2]) > 0.02]
first_cb = min(cb)
rows = [(d, *[round(x, 2) for x in yv[d][:4]], 'Yahoo ^VIX3M(当年叫 VXV)') for d in sorted(yv) if d < first_cb] + \
       [(d, *[round(x, 2) for x in cb[d]], 'CBOE 官方') for d in sorted(cb)]
with open(f'{d1}/VIX3M_日线.csv', 'w', newline='') as fh:
    w = csv.writer(fh); w.writerow(['date', 'open', 'high', 'low', 'close', 'source']); w.writerows(rows)
print('VIX3M', len(rows), rows[0][0], rows[-1][0], 'CBOE 起', first_cb, '重叠', len(ov), '收盘差>0.02', len(bad), bad[:5])
# 信用
d2 = os.path.join(OUT, '信用利差'); os.makedirs(d2, exist_ok=True)
H, I = yahoo('HYG'), yahoo('IEF')
for nm, S in (('HYG', H), ('IEF', I)):
    with open(f'{d2}/{nm}_复权日线.csv', 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['date', 'open', 'high', 'low', 'close', 'adjusted_close', 'volume'])
        w.writerows((d, *[round(x, 4) for x in v[:5]], v[5]) for d, v in sorted(S.items()))
    print(nm, len(S), min(S), max(S))
with open(f'{d2}/HYG除以IEF_复权.csv', 'w', newline='') as fh:
    w = csv.writer(fh); w.writerow(['date', 'hyg_adj', 'ief_adj', 'hyg_div_ief'])
    for d in sorted(set(H) & set(I)): w.writerow([d, round(H[d][4], 4), round(I[d][4], 4), round(H[d][4] / I[d][4], 6)])
for s in ('BAA10Y', 'BAMLH0A0HYM2'):
    L = [r for r in csv.reader(open(f'{FR}/{s}.csv'))][1:]
    with open(f'{d2}/{s}_FRED.csv', 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['date', 'value_pct']); w.writerows((a, b) for a, b in L if b not in ('', '.'))
    print(s, len(L), L[0], L[-1])
