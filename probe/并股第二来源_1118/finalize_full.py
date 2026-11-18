#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 312 · 全池版并股事件表 = 第一轮(两份名单,已按收紧后的规则重判)+ 全池新增(来自名单 = 全池)"""
import csv, json
from collections import Counter
R1 = list(csv.DictReader(open('/home/claude/stock_data/market_ext_1105/并股事件表_第二来源_1118.csv', encoding='utf-8-sig')))
o = json.load(open('judged_全池.json'))
GAPCUT = {('BTE', '2023-02-23'), ('CRC', '2020-10-28'), ('DYN__1379895', '2012-10-03'), ('GTX', '2021-05-03'), ('HTZ', '2021-11-09'),
          ('SD', '2016-10-04'), ('TLN', '2024-07-10'), ('CHRD', '2020-11-20')}
# 同一份公告确认了两次不同跳变的,只认离公告最近的那次
use = Counter((x['来源'], x['比例']) for x in o if x['结论'] in ('是并股', '是拆股'))
rows, seen = [], {(r['代码'], r['生效日']) for r in R1}
for x in o:
    x = dict(x)
    if (x['代码'], x['日期']) in GAPCUT:
        x.update(结论='不是并股', 比例='', 来源='见 代码中间断档_全池_1118.csv',
                 备注='代码中间断档:断档前后是两段不同的证券(退市后重新上市或破产重组换新股),不能折算,按断档表切开')
    if x['结论'] in ('是并股', '是拆股') and use[(x['来源'], x['比例'])] > 1:
        same = [y for y in o if y['来源'] == x['来源'] and y['比例'] == x['比例'] and y['结论'] in ('是并股', '是拆股')]
        fd = x['备注'].split(' ')[2] if x['备注'].startswith('SEC') else x['日期']
        near = min(same, key=lambda y: abs((__import__('datetime').date.fromisoformat(y['日期']) - __import__('datetime').date.fromisoformat(fd)).days))
        if near is not x and (near['代码'], near['日期']) != (x['代码'], x['日期']):
            x.update(结论='查不到', 比例='', 备注='同一份公告已经确认了 %s 那次,这次跳变没有自己的公告;' % near['日期'] + x['备注'])
    key = (x['代码'], x['日期'])
    if key in seen: continue
    seen.add(key)
    rows.append({'代码': x['代码'], '结论': x['结论'], '生效日': x['日期'], '比例(新股数:旧股数)': x['比例'], '来源(链接或公告号)': x['来源'],
                 '备注': x['备注'], '当时代码': x['源头代码'], 'cik': x['cik'], '前一根K线日': x.get('前一根K线日', ''),
                 '单日收盘比': round(x['单日收盘比'], 4), '来自名单': '全池'})
allrows = R1 + rows
allrows.sort(key=lambda r: (r['代码'], r['生效日']))
with open('/home/claude/stock_data/market_ext_1105/并股事件表_第二来源_全池_1118.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(R1[0])); w.writeheader(); w.writerows(allrows)
print('第一轮', len(R1), Counter(r['结论'] for r in R1))
print('全池新增', len(rows), Counter(r['结论'] for r in rows))
print('合计', len(allrows), '只数', len({r['代码'] for r in allrows}))
print('要折算的(是并股/是拆股/错位)只数:', len({r['代码'] for r in allrows if r['结论'] in ('是并股', '是拆股', '有系数但日期错位')}))
