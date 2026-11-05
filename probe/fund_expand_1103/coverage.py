#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基本面库字段可算率(只数覆盖,不算任何收益)。
口径:选股池 2016–2025 年每个「公司 × 年份」(已对上 CIK 的),看**上一财年**(截止日落在上一自然年、年报口径):
  · 资产负债表项:有截止日在上一年的时点值
  · 现金流 / 损益项:有截止日在上一年、期间 330–400 天的值
  · 股东回报三项齐全 = 增发、分红、回购三项都有
  · Sloan 应计原著版 = 上一年和再上一年都有:流动资产、流动负债、现金、短期有息负债、应交所得税、折旧
用法:python3 coverage.py fundamentals_dir pool_cik_by_year.csv [--no-suspect]   (--no-suspect:把「可疑的 0」当作缺)"""
import csv, gzip, json, os, sys
from collections import defaultdict
from datetime import date

BS = ['CurrentAssets', 'CurrentLiabilities', 'CashAndCashEquivalentsAtCarryingValue', 'ShortTermDebt', 'IncomeTaxesPayable']
FL = ['StockIssuance', 'DividendsPaid', 'ShareRepurchase', 'DepreciationDepletionAndAmortization']


def years_with(recs, flow, no_suspect):
    ys = set()
    for r in recs:
        if no_suspect and r.get('zero_suspect'): continue
        pe = r.get('period_end')
        if not pe: continue
        if flow:
            if not r.get('period_start'): continue
            n = (date.fromisoformat(pe) - date.fromisoformat(r['period_start'])).days
            if not 330 <= n <= 400: continue
        elif r.get('period_start'): continue
        ys.add(int(pe[:4]))
    return ys


def main(fdir, pool_path, *flags):
    ns = '--no-suspect' in flags
    rows = [r for r in csv.DictReader(open(pool_path)) if 2016 <= int(r['year']) <= 2025]
    folder_of = {}
    for r in rows: folder_of[r['cik']] = r['folder']
    have = {}
    for cik, f in folder_of.items():
        p = os.path.join(fdir, f, 'fundamentals.json.gz')
        if not os.path.exists(p): continue
        fv = json.load(gzip.open(p))['financial_versions']
        have[cik] = {m: years_with(fv.get(m, []), m in FL, ns) for m in BS + FL}
    cnt = defaultdict(int); n = 0
    for r in rows:
        h = have.get(r['cik']); n += 1
        if not h: continue
        y = int(r['year']) - 1
        for m in BS + FL: cnt[m] += y in h[m]
        cnt['三项齐全'] += all(y in h[m] for m in ('StockIssuance', 'DividendsPaid', 'ShareRepurchase'))
        sl = ['CurrentAssets', 'CurrentLiabilities', 'CashAndCashEquivalentsAtCarryingValue', 'ShortTermDebt', 'IncomeTaxesPayable', 'DepreciationDepletionAndAmortization']
        cnt['Sloan 原著版'] += all(y in h[m] and (y - 1) in h[m] for m in sl)
    print('公司×年', n, '(--no-suspect)' if ns else '')
    for k in ['IncomeTaxesPayable', 'ShortTermDebt', 'StockIssuance', 'DividendsPaid', 'ShareRepurchase', '三项齐全', 'Sloan 原著版',
              'CurrentAssets', 'CurrentLiabilities', 'DepreciationDepletionAndAmortization']:
        print(f'{k}\t{cnt[k] / n:.1%}')


if __name__ == '__main__':
    main(*sys.argv[1:])
