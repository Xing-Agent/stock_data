#!/usr/bin/env python3
"""把要核的「跳变」事件列出来:手册 305 的两份名单取并集,在 market_ext_1105 原始日线上重新定位日期。
判据(和策略组同口径,两条任一):
 A. 单日收盘 ÷ 前收 > 3 或 < 1/3(1118 清单的口径)
 B. 后 5 日收盘中位 ÷ 前 5 日中位 ≥3 或 ≤1/3,且股数成交量反向 ≥1.5 倍(1107 口径)
同一只 15 个日历日内的多条并成一件。已带 split_coefficient≠1 的日子标出来。"""
import csv, gzip, json, os, statistics as st
from datetime import date
R = '/home/claude/stock_data'
j = json.load(open(f'{R}/probe/假跳变_1107/假跳变_报告_1107.json'))
L1107 = set(j['全部只数名单'])
L1118 = {}
for r in csv.DictReader(open(f'{R}/probe/含分红重出_1116/一天跳三倍_清单_1118.csv', encoding='utf-8-sig')):
    L1118.setdefault(r['代码'], set()).add(r['日期'])
out = []
for s in sorted(L1107 | set(L1118)):
    J = json.load(gzip.open(f'{R}/market_ext_1105/{s}/daily.json.gz'))
    D = J['data']; segs = J.get('company_segments') or []
    ev = {}
    for i in range(1, len(D)):
        p, c = D[i-1]['close'], D[i]['close']
        if not p or not c: continue
        r1 = c / p
        hitA = r1 > 3 or r1 < 1/3
        hitB = False; pr = vr = None
        if 5 <= i <= len(D) - 5:
            a = [x['close'] for x in D[i-5:i] if x['close']]; b = [x['close'] for x in D[i:i+5] if x['close']]
            va = [x['volume'] or 0 for x in D[i-5:i]]; vb = [x['volume'] or 0 for x in D[i:i+5]]
            if a and b and st.median(a) > 0 and st.median(va) > 0:
                pr = st.median(b) / st.median(a); vr = st.median(vb) / st.median(va)
                hitB = (pr >= 3 and vr <= 1/1.5) or (pr <= 1/3 and vr >= 1.5)
        if hitA or hitB:
            ev[D[i]['date']] = dict(r1=r1, pr=pr, vr=vr, A=hitA, B=hitB, i=i)
    # 并成事件:15 天内的取 |log 单日比| 最大的那天
    import math
    days = sorted(ev); groups = []
    for d in days:
        if groups and (date.fromisoformat(d) - date.fromisoformat(groups[-1][-1])).days <= 15: groups[-1].append(d)
        else: groups.append([d])
    for g in groups:
        d = max(g, key=lambda x: abs(math.log(ev[x]['r1'])))
        e = ev[d]; i = e['i']; row = D[i]
        cik = J['cik']
        for sg in segs:
            if isinstance(sg, dict) and sg.get('start_date', '0') <= d <= sg.get('end_date', '9'): cik = sg.get('cik', cik) or cik
        win = D[max(0, i-10):i+10]
        out.append({'代码': s, '日期': d, '源头代码': row.get('source_ticker') or s, 'cik': str(cik).lstrip('0'),
                    '前收': D[i-1]['close'], '收盘': row['close'], '开盘': row['open'], '单日收盘比': round(e['r1'], 4),
                    '窗口价比': round(e['pr'], 3) if e['pr'] else '', '股数量比': round(e['vr'], 3) if e['vr'] else '',
                    '判据': ('A' if e['A'] else '') + ('B' if e['B'] else ''),
                    '附近已有拆股系数': ';'.join(f"{x['date']}:{x['split_coefficient']}" for x in win if x.get('split_coefficient') not in (1, 1.0, None)),
                    '来自名单': ('1107' if s in L1107 else '') + ('+1118' if s in L1118 else ''),
                    '1118同日': 'Y' if d in L1118.get(s, ()) or any(x in L1118.get(s, ()) for x in g) else ''})
with open(f'{R}/probe/并股第二来源_1118/待核事件_1118.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
from collections import Counter
print(len(out), 'events,', len({o['代码'] for o in out}), 'tickers', Counter(o['判据'] for o in out), 'has coef nearby', sum(1 for o in out if o['附近已有拆股系数']))
print('1118 rows covered', sum(1 for s, ds in L1118.items() for d in ds if any(o['代码']==s and abs((date.fromisoformat(o['日期'])-date.fromisoformat(d)).days)<=15 for o in out)), 'of', sum(len(v) for v in L1118.values()))
print('1107 tickers w/o event', [s for s in L1107 if not any(o['代码']==s for o in out)])
