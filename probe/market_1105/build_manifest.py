#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 53 · manifest.csv(表头照取数单原样)+ manifest_detail.csv(多给的列:CIK、代码、股本来源…)

大白话:
  · 市值 = 当天收盘价(原始价)× 当时最新的流通股数(SEC 封面 dei:EntityCommonStockSharesOutstanding,多类股相加;
    没有就用 us-gaap:CommonStockSharesOutstanding;再没有(多类股公司)用最近一期加权平均基本股数);股数报告日之后如果拆过股,按 split_coefficient 折算
  · 日子:还在交易的用 2026-11-04;退市的用它最后一个交易日
  · 大小:≥ 100 亿美元 large,20~100 亿 mid,< 20 亿 small(取数单的口径)
  · ADR(Polygon 类型 ADRC)和 SEC 没报股数的:SEC 股数乘不了 → 用 Polygon ticker details 当天的市值(手册 56)
  · 行业:SEC SIC 代码所在大类(sector_basis 写明代码)
  · 交易所:Polygon 年度代码表里这只票最后一次出现时的主交易所,没有就用 SEC 现在的

用法:python3 build_manifest.py market_dir fundamentals_dir [polygon_mcap.json] [polygon_mcap_start.json]
"""
import csv, glob, gzip, json, os, sys
from datetime import date, timedelta
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


def split_adj(bars, events, a, b):
    """a(不含)~ b(含)之间的拆股累计倍数(大额派现折进 split_coefficient 的那几天除回去,它不改股数)"""
    adj = 1.0
    for x in bars:
        if a < x['date'] <= b and x['split_coefficient']: adj *= x['split_coefficient']
    for e in events:
        if e['action_type'] == 'special_distribution' and a < e['effective_date'] <= b: adj /= e['split_coefficient']
    return adj


def tier(mc):
    return 'unknown' if mc is None else ('large' if mc >= 1e10 else 'mid' if mc >= 2e9 else 'small')


def main(mdir, fdir, poly_path=None, poly_start_path=None):
    """poly_path:Polygon ticker details(按 market_cap_date 查)的结果 {文件夹: [代码, 日期, 状态, 市值, …, 类型, cik, 名]}
    poly_start_path:同上,按数据起始日查(给 size_group_at_start 用)"""
    raw = list(csv.DictReader(open(os.path.join(mdir, '_manifest_raw.csv'))))
    SUB = json.load(gzip.open('/home/claude/fx/sub_all.json.gz'))
    PM = json.load(open(poly_path)) if poly_path else {}
    PS = json.load(open(poly_start_path)) if poly_start_path else {}
    poly = {}
    for f in sorted(glob.glob(f'{ROOT}/probe/fund_expand_1103/polygon_tickers_*.json.gz')):
        for r in json.load(gzip.open(f))['rows']:
            if r[4]: poly[(r[0], r[4].lstrip('0'))] = r          # 后面的年份覆盖前面的
    out, det = [], []
    for m in raw:
        f, cik = m['symbol'], m['cik']
        D = json.load(gzip.open(os.path.join(mdir, f, 'daily.json.gz')))
        bars = D['data']; ev = D['corporate_actions']['events']; last = bars[-1]; d = last['date']; first = bars[0]; d0 = first['date']
        tick = last['source_ticker']
        pr = poly.get((tick, cik))
        typ = pr[2] if pr else ''
        ex = EXC.get(pr[3], pr[3]) if pr and pr[3] else ';'.join(dict.fromkeys(x.upper() if x.lower() == 'nasdaq' else x for x in (SUB.get(cik, {}).get('x') or []) if x))
        ff = os.path.join(fdir, f, 'fundamentals.json.gz')
        F = json.load(gzip.open(ff)) if os.path.exists(ff) else None
        sh, sh_end, sh_src = shares_at(F, d) if F else (None, None, None)
        # 1105 手册 56 之后:Polygon ticker details 当天的市值为主(它按股类算全、ADR 也对),SEC 股数 × 收盘做后备。
        # 两者都有的 2,240 只:中位数之比 1.00,同一档 96%;差 2 倍以上的 144 只多是多类股公司 SEC 只报了一类股
        mc, src, note = None, '', ''
        if PM.get(f) and PM[f][2] == 200 and PM[f][3]:
            mc = float(PM[f][3]); src = 'Polygon ticker details' + ('' if PM[f][1] == d else f'({PM[f][1]})')
        elif typ == 'ADRC': note = 'ADR:Polygon 当天没有市值,SEC 股数是原股、不能直接乘'
        elif sh:
            mc = last['close'] * sh * split_adj(bars, ev, sh_end, d); src = 'SEC 股数 × 当天收盘'
            if mc <= 0: mc, src = None, ''
        if mc is None and not note: note = 'Polygon 当天没有市值,SEC 也没报股数'
        # 起始日的市值档(手册 56 可选项):SEC 股数(起始日以前公开的最新一期)× 起始日收盘;没有就用 Polygon 当天的
        mc0, src0 = None, ''
        if typ != 'ADRC' and F:
            s0, e0, _ = shares_at(F, d0)
            if s0: mc0 = first['close'] * s0 * split_adj(bars, ev, e0, d0); src0 = 'SEC 股数 × 起始日收盘'
            else:
                # 起始日以前还没有 XBRL 股数(2009 年以前、或刚上市):用起始日后一年内公开的第一期股数,按中间的拆股折回去(近似,标明)
                d1 = (date.fromisoformat(d0) + timedelta(days=365)).isoformat()
                s1, e1, _ = shares_at(F, d1)
                if s1 and e1 >= d0:
                    mc0 = first['close'] * s1 / split_adj(bars, ev, d0, e1); src0 = 'SEC 股数(起始日后一年内第一期,按拆股折回)× 起始日收盘(近似)'
        if mc0 is None and PS.get(f) and PS[f][2] == 200 and PS[f][3]:
            mc0 = float(PS[f][3]); src0 = 'Polygon ticker details(起始日的市值)'
        sic = SUB.get(cik, {}).get('sic') or ''
        out.append({'symbol': f, 'name': SUB.get(cik, {}).get('n') or m['name'], 'exchange': ex, 'size_group': tier(mc),
                    'market_cap_usd': round(mc) if mc else '', 'market_cap_date': d, 'sector': sector(sic) if sic else '',
                    'sector_basis': f'SEC SIC {sic} division' if sic else '', 'delisted': m['delisted'].lower(), 'delisting_date': m['delisting_date'],
                    'size_group_at_start': tier(mc0) if mc0 else 'unknown', 'market_cap_at_start_usd': round(mc0) if mc0 else '', 'market_cap_at_start_date': d0})
        det.append({**{k: m[k] for k in ('symbol', 'cik', 'tickers', 'start_date', 'end_date', 'bars', 'missing_bars', 'warnings')},
                    'last_ticker': tick, 'polygon_type': typ, 'sic': sic, 'last_close': last['close'], 'shares': round(sh) if sh else '',
                    'shares_as_of': sh_end or '', 'shares_source': sh_src or '', 'market_cap_source': src, 'market_cap_at_start_source': src0, 'note': note})
    for name, rows in (('manifest.csv', out), ('manifest_detail.csv', det)):
        with open(os.path.join(mdir, name), 'w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
    from collections import Counter
    print(Counter(r['size_group'] for r in out), Counter(r['size_group_at_start'] for r in out), Counter(r['delisted'] for r in out))


if __name__ == '__main__':
    main(*sys.argv[1:])
