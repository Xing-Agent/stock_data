#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 53 · manifest.csv(表头照取数单原样)+ manifest_detail.csv(多给的列:CIK、代码、股本来源…)

大白话:
  · 市值 = 当天收盘价(原始价)× 当时最新的流通股数(SEC 封面 dei:EntityCommonStockSharesOutstanding,多类股相加;
    没有就用 us-gaap:CommonStockSharesOutstanding;再没有(多类股公司)用最近一期加权平均基本股数);股数报告日之后如果拆过股,按 split_coefficient 折算
  · 日子:还在交易的用 2026-11-04;退市的用它最后一个交易日
  · 大小:≥ 100 亿美元 large,20~100 亿 mid,< 20 亿 small(取数单的口径)
  · ADR(Polygon 类型 ADRC):SEC 报的是原股股数,不是 ADR 份数,乘出来不对 → 市值留空,size_group 写 unknown
  · 行业:SEC SIC 代码所在大类(sector_basis 写明代码)
  · 交易所:Polygon 年度代码表里这只票最后一次出现时的主交易所,没有就用 SEC 现在的

用法:python3 build_manifest.py market_dir fundamentals_dir
"""
import csv, glob, gzip, json, os, sys
from collections import defaultdict

ROOT = '/home/claude/stock_data'
EXC = {'XNYS': 'NYSE', 'XNAS': 'NASDAQ', 'XASE': 'NYSE American', 'ARCX': 'NYSE Arca', 'BATS': 'Cboe BZX', 'XCHI': 'NYSE Chicago'}
DIV = [(1, 9, 'Agriculture, Forestry & Fishing'), (10, 14, 'Mining'), (15, 17, 'Construction'), (20, 39, 'Manufacturing'),
       (40, 49, 'Transportation, Communications & Utilities'), (50, 51, 'Wholesale Trade'), (52, 59, 'Retail Trade'),
       (60, 67, 'Finance, Insurance & Real Estate'), (70, 89, 'Services'), (91, 99, 'Public Administration')]


def sector(sic):
    try: s2 = int(str(sic)[:2]) if len(str(sic)) == 4 else int(str(sic).zfill(4)[:2])
    except Exception: return ''
    for a, b, n in DIV:
        if a <= s2 <= b: return n
    return 'Nonclassifiable'


def shares_at(F, d):
    """d 当天能看到的最新股数(filed ≤ d);多类股同一份申报同一天相加。返回 (股数, 截止日, 来源)"""
    for key in ('dei:EntityCommonStockSharesOutstanding|shares', 'us-gaap:CommonStockSharesOutstanding|shares'):
        rows = [r for r in F['raw_tags'].get(key, []) if r[6] and r[6] <= d and r[0]]
        if not rows: continue
        last = max(rows, key=lambda r: (r[6], r[2]))
        tot = sum(float(r[0]) for r in rows if r[7] == last[7] and r[2] == last[2])
        return tot, last[2], key.split('|')[0]
    # 多类股公司(Meta、Airbnb……)封面股数按股类分开报,companyfacts 里没有 → 用最近一期的加权平均基本股数(期间平均,不是期末数;shares_source 里写明)
    rows = [r for r in F['raw_tags'].get('us-gaap:WeightedAverageNumberOfSharesOutstandingBasic|shares', []) if r[6] and r[6] <= d and r[0] and r[2]]
    if rows:
        last = max(rows, key=lambda r: (r[2], r[6], r[1] or ''))      # 截止日最新的;同截止日取最短的那期(开始日最晚)
        return float(last[0]), last[2], 'us-gaap:WeightedAverageNumberOfSharesOutstandingBasic(期间平均)'
    return None, None, None


def main(mdir, fdir):
    raw = list(csv.DictReader(open(os.path.join(mdir, '_manifest_raw.csv'))))
    SUB = json.load(gzip.open('/home/claude/fx/sub_all.json.gz'))
    poly = {}
    for f in sorted(glob.glob(f'{ROOT}/probe/fund_expand_1103/polygon_tickers_*.json.gz')):
        for r in json.load(gzip.open(f))['rows']:
            if r[4]: poly[(r[0], r[4].lstrip('0'))] = r          # 后面的年份覆盖前面的
    out, det = [], []
    for m in raw:
        f, cik = m['symbol'], m['cik']
        D = json.load(gzip.open(os.path.join(mdir, f, 'daily.json.gz')))
        bars = D['data']; last = bars[-1]; d = last['date']
        tick = last['source_ticker']
        pr = poly.get((tick, cik))
        typ = pr[2] if pr else ''
        ex = EXC.get(pr[3], pr[3]) if pr and pr[3] else ';'.join(dict.fromkeys(x.upper() if x.lower() == 'nasdaq' else x for x in (SUB.get(cik, {}).get('x') or []) if x))
        ff = os.path.join(fdir, f, 'fundamentals.json.gz')
        sh, sh_end, sh_src = (None, None, None)
        if os.path.exists(ff): sh, sh_end, sh_src = shares_at(json.load(gzip.open(ff)), d)
        mc, note = None, ''
        if typ == 'ADRC': note = 'ADR:SEC 股数是原股,不折算,市值留空'
        elif sh:
            adj = 1.0
            for b in bars:
                if sh_end < b['date'] <= d: adj *= b['split_coefficient'] if b['split_coefficient'] else 1.0
            # 大额派现也记在 split_coefficient 里,但它不改股数 —— 把那几天的派现系数除回去
            for e in D['corporate_actions']['events']:
                if e['action_type'] == 'special_distribution' and sh_end < e['effective_date'] <= d: adj /= e['split_coefficient']
            mc = last['close'] * sh * adj
        else: note = '没有股数(SEC 封面和资产负债表都没报)'
        sg = 'unknown' if mc is None else ('large' if mc >= 1e10 else 'mid' if mc >= 2e9 else 'small')
        sic = SUB.get(cik, {}).get('sic') or ''
        out.append({'symbol': f, 'name': SUB.get(cik, {}).get('n') or m['name'], 'exchange': ex, 'size_group': sg,
                    'market_cap_usd': round(mc) if mc else '', 'market_cap_date': d, 'sector': sector(sic) if sic else '',
                    'sector_basis': f'SEC SIC {sic} division' if sic else '', 'delisted': m['delisted'].lower(), 'delisting_date': m['delisting_date']})
        det.append({**{k: m[k] for k in ('symbol', 'cik', 'tickers', 'start_date', 'end_date', 'bars', 'missing_bars', 'warnings')},
                    'last_ticker': tick, 'polygon_type': typ, 'sic': sic, 'last_close': last['close'], 'shares': round(sh) if sh else '',
                    'shares_as_of': sh_end or '', 'shares_source': sh_src or '', 'note': note})
    for name, rows in (('manifest.csv', out), ('manifest_detail.csv', det)):
        with open(os.path.join(mdir, name), 'w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    from collections import Counter
    print(Counter(r['size_group'] for r in out), Counter(r['delisted'] for r in out))


if __name__ == '__main__':
    main(*sys.argv[1:])
