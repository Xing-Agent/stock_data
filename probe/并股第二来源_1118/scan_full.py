#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 312 · 全池扫描:① 跳变候选(三档) ② 同一代码中间断档
大白话:
  · 跳变候选(只用来找候选,定性要靠 SEC 公告):
      A 单日收盘比 > 3 或 < 1/3
      B 后 5 日中位 ÷ 前 5 日中位 ≥3(或 ≤1/3)且股数成交量反向 ≥1.5 倍
      C(新加的低一档)单日 ≥1.8 倍且股数量缩到 1/1.5 以下;或单日 ≤1/1.8 且股数量放大 1.5 倍以上(没折的正向拆股)
    当天已有拆股系数、方向对得上的 → 已折算,不进待查。
  · 11-07 对齐时被丢掉的 Polygon 拆股(「价格没跳」「无行情」)也逐条放进待查:按当时代码在全池找到对应文件和日子。
  · 断档:同一文件里相邻两根 K 线之间隔了 ≥20 个交易日(交易日历用 SPY)。
"""
import csv, glob, gzip, json, math, os, statistics as st, bisect
from collections import defaultdict
R = '/home/claude/stock_data'
OUT = f'{R}/probe/并股第二来源_1118'
spy = json.load(gzip.open(f'{R}/market_etf_1106/SPY/daily.json.gz'))['data']
CAL = [x['date'] for x in spy]; CI = {d: i for i, d in enumerate(CAL)}


def tdays(a, b):
    return bisect.bisect_left(CAL, b) - bisect.bisect_left(CAL, a)


done = set()  # 第一轮已核过的(代码, 日期)
for r in csv.DictReader(open(f'{R}/market_ext_1105/并股事件表_第二来源_1118.csv', encoding='utf-8-sig')):
    done.add((r['代码'], r['生效日']))

cand, gaps, by_src = [], [], defaultdict(list)
files = sorted(glob.glob(f'{R}/market_ext_1105/*/daily.json.gz'))
for fp in files:
    s = fp.split('/')[-2]
    J = json.load(gzip.open(fp)); D = J['data']
    segs = J.get('company_segments') or []
    for i, x in enumerate(D):
        by_src[x.get('source_ticker') or s].append((s, x['date'], i))
    # 断档
    for i in range(1, len(D)):
        g = tdays(D[i-1]['date'], D[i]['date'])
        if g >= 20:
            cid = lambda d: next((sg.get('company_id') for sg in segs if sg['from'] <= d <= sg['to']), None)
            gaps.append({'代码': s, '断档前最后一天': D[i-1]['date'], '接上的第一天': D[i]['date'], '断了多少个交易日': g,
                         '断前代码': D[i-1].get('source_ticker') or s, '接上后代码': D[i].get('source_ticker') or s,
                         '断前收盘': D[i-1]['close'], '接上后收盘': D[i]['close'], 'cik_文件': J['cik'],
                         '断前company_id': cid(D[i-1]['date']), '接上后company_id': cid(D[i]['date'])})
    # 跳变
    ev = {}
    for i in range(1, len(D)):
        p, c = D[i-1]['close'], D[i]['close']
        if not p or not c: continue
        r1 = c / p
        pr = vr = None
        if 5 <= i <= len(D) - 5:
            a = [x['close'] for x in D[i-5:i] if x['close']]; b = [x['close'] for x in D[i:i+5] if x['close']]
            va = [x['volume'] or 0 for x in D[i-5:i]]; vb = [x['volume'] or 0 for x in D[i:i+5]]
            if a and b and st.median(a) > 0 and st.median(va) > 0:
                pr = st.median(b) / st.median(a); vr = st.median(vb) / st.median(va)
        A = r1 > 3 or r1 < 1/3
        B = pr is not None and ((pr >= 3 and vr <= 1/1.5) or (pr <= 1/3 and vr >= 1.5))
        C = vr is not None and ((r1 >= 1.8 and vr <= 1/1.5) or (r1 <= 1/1.8 and vr >= 1.5))
        if A or B or C:
            ev[i] = (r1, pr, vr, ('A' if A else '') + ('B' if B else '') + ('C' if C else ''))
    # 15 个交易日内并成一件,取单日变动最大那天
    ks = sorted(ev); groups = []
    for k in ks:
        if groups and k - groups[-1][-1] <= 10: groups[-1].append(k)
        else: groups.append([k])
    for g in groups:
        lo, hi = max(1, g[0] - 3), min(len(D) - 1, g[-1] + 3)
        k = max(range(lo, hi + 1), key=lambda j: abs(math.log(D[j]['close'] / D[j-1]['close'])) if D[j]['close'] and D[j-1]['close'] else 0)
        r1 = D[k]['close'] / D[k-1]['close']
        coef = D[k].get('split_coefficient')
        if coef not in (None, 1, 1.0) and ((coef < 1) == (r1 > 1)):
            continue  # 已折算
        flags = ''.join(sorted(set(''.join(ev[j][3] for j in g))))
        e = ev.get(k) or ev[g[0]]
        cik = J['cik']
        cand.append({'代码': s, '日期': D[k]['date'], '前一根K线日': D[k-1]['date'], '源头代码': D[k].get('source_ticker') or s,
                     'cik': str(cik).lstrip('0'), '单日收盘比': round(r1, 4), '窗口价比': round(e[1], 3) if e[1] else '',
                     '股数量比': round(e[2], 3) if e[2] else '', '判据': flags, '来源': '扫描',
                     '附近系数': ';'.join(f"{D[j]['date']}:{D[j]['split_coefficient']}" for j in range(max(0, k-10), min(len(D), k+10)) if D[j].get('split_coefficient') not in (1, 1.0, None))})

# 11-07 对齐时丢掉的 Polygon 拆股
dropped = [r for r in csv.DictReader(open(f'{R}/probe/market_1105/polygon_splits_aligned_1107.csv')) if r['check'] in ('价格没跳', '无行情')]
have = {(c['代码'], c['日期']) for c in cand}
add = 0; nofile = 0
for r in dropped:
    hits = by_src.get(r['ticker'], [])
    near = [(s, d, i) for (s, d, i) in hits if abs(tdays(min(d, r['execution_date']), max(d, r['execution_date']))) <= 5 and d >= r['execution_date']]
    if not near:
        nofile += 1; continue
    s, d, i = min(near, key=lambda t: t[1])
    if any(c['代码'] == s and abs(tdays(min(c['日期'], d), max(c['日期'], d))) <= 5 for c in cand):
        for c in cand:
            if c['代码'] == s and abs(tdays(min(c['日期'], d), max(c['日期'], d))) <= 5: c['来源'] += '+对齐丢弃'
        continue
    J = json.load(gzip.open(f'{R}/market_ext_1105/{s}/daily.json.gz')); D = J['data']
    if D[i].get('split_coefficient') not in (None, 1, 1.0): continue
    r1 = D[i]['close'] / D[i-1]['close'] if i and D[i-1]['close'] else 1
    cand.append({'代码': s, '日期': d, '前一根K线日': D[i-1]['date'] if i else '', '源头代码': r['ticker'], 'cik': str(J['cik']).lstrip('0'),
                 '单日收盘比': round(r1, 4), '窗口价比': '', '股数量比': '', '判据': 'P', '来源': f"对齐丢弃({r['check']})",
                 '附近系数': f"Polygon {r['execution_date']} {r['split_from']}→{r['split_to']}"}); add += 1

new = [c for c in cand if (c['代码'], c['日期']) not in done]
for c in cand: c['第一轮已核'] = 'Y' if (c['代码'], c['日期']) in done else ''
with open(f'{OUT}/全池候选_1118.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(cand[0])); w.writeheader(); w.writerows(cand)
with open(f'{OUT}/全池断档_1118.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(gaps[0])); w.writeheader(); w.writerows(gaps)
from collections import Counter
print('文件', len(files), '候选', len(cand), '新的', len(new), Counter(c['判据'] for c in new).most_common(12))
print('对齐丢弃', len(dropped), '新增', add, '找不到文件', nofile)
print('断档', len(gaps), '只数', len({g['代码'] for g in gaps}))
