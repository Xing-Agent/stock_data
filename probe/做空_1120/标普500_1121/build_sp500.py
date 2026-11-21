#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 338 第二样:标普 500 历史成分。来源 github.com/fja05680/sp500(MIT 许可,2026-09-07 那版),
它是「每次成分变动后的完整名单」;这里把相邻两版做差,得到 2005-01 ~ 2025-12 每次调入、调出的日期和代码。
用法:python3 build_sp500.py 原始.csv OUT_DIR"""
import csv, sys, os
src, out = sys.argv[1], sys.argv[2]; os.makedirs(out, exist_ok=True)
rows = sorted((r['date'], set(r['tickers'].split(','))) for r in csv.DictReader(open(src)))
ch, snap, prev = [], [], None
for d, s in rows:
    if prev is not None and '2005-01-01' <= d <= '2025-12-31':
        add, rem = sorted(s - prev[1]), sorted(prev[1] - s)
        for t in add: ch.append(dict(日期=d, 动作='调入', 代码=t, 当天调入几只=len(add), 当天调出几只=len(rem)))
        for t in rem: ch.append(dict(日期=d, 动作='调出', 代码=t, 当天调入几只=len(add), 当天调出几只=len(rem)))
    if '2004-12-01' <= d <= '2025-12-31': snap.append(dict(日期=d, 成分数=len(s), 成分=','.join(sorted(s))))
    prev = (d, s)
with open(f'{out}/调入调出_2005_2025.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(ch[0])); w.writeheader(); w.writerows(ch)
with open(f'{out}/每次变动后的成分_2004_2025.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(snap[0])); w.writeheader(); w.writerows(snap)
# 每只票在标普里的时间段(进出多次的分开写)
span, cur = [], {}
for d, s in rows:
    for t in s:
        if t not in cur: cur[t] = d
    for t in list(cur):
        if t not in s: span.append(dict(代码=t, 进=cur[t], 出=d)); cur.pop(t)
for t, a in cur.items(): span.append(dict(代码=t, 进=a, 出=''))
span = [x for x in span if not x['出'] or x['出'] >= '2005-01-01']
span.sort(key=lambda x: (x['代码'], x['进']))
with open(f'{out}/每只票在标普里的时间段.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=['代码', '进', '出']); w.writeheader(); w.writerows(span)
n = [x['成分数'] for x in snap if x['日期'] >= '2005-01-01']
print('changes', len(ch), 'snapshots', len(snap), 'members min/max', min(n), max(n), 'spans', len(span))
