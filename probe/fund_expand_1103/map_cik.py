#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""给扩池里每一行「公司 × 年份」定 SEC 公司编号(CIK)。

大白话:候选编号有三个来源 —— 考卷名单(已逐只核过)、SEC 现在的代码表、Polygon 的年度代码表。
代码会被别的公司重复使用(老 Chubb 的 CB 后来给了 ACE),而我们的「公司」是按价格连续切的,
所以同一个公司编号(company_id)在不同年份可能对应两个申报主体。这里按年定:
  候选编号在那一年(前后放宽 150 天)里必须交过年报或季报(10-K / 10-Q / 20-F / 40-F),才算对上。
对不上的列进「待补」。基本面文件按 CIK 存(一家申报主体一个文件夹)。

用法:python3 map_cik.py pool_FULL_ALL.csv sub.json.gz out_dir [polygon_yearly_dir]
"""
import csv, glob, gzip, json, os, sys
from collections import defaultdict
from datetime import date, timedelta

PERIODIC = ('10-K', '10-Q', '20-F', '40-F', '10-KT', '10-QT')
ROOT = '/home/claude/stock_data'


def main(pool_path, sub_path, out_dir, poly_dir=None):
    SUB = json.load(gzip.open(sub_path))
    pool = [r for r in csv.DictReader(open(pool_path)) if int(r['rank']) <= 2000]
    ex = {r['company_id']: r['cik'].lstrip('0') for r in csv.DictReader(open(f'{ROOT}/exam_1042/manifest.csv'))}
    ct = json.load(open(f'{ROOT}/exam_1042/reviews/sec_company_tickers_exchange_1102.json'))
    secnow = {r[2].upper().replace('-', '.'): str(r[0]) for r in ct['data']}
    poly = defaultdict(dict)                      # 代码 → {年: (cik, 名)}
    pinact = set()
    pdate = {}                                    # (代码, 年) → 这条对应关系「当时成立」的那天:还挂牌的用表的日子,已退市的用退市日
    files = sorted(glob.glob(os.path.join(poly_dir or '/nonexistent', 'polygon_tickers_*.json.gz'))) + [f'{ROOT}/probe/exam_1101/polygon_tickers_20151231.json.gz']
    for f in files:
        if not os.path.exists(f): continue
        y = int(os.path.basename(f).split('_')[-1][:4]); j = json.load(gzip.open(f))
        for r in j['rows']:
            if r[4]: poly[r[0]][y] = (r[4].lstrip('0'), r[1]); pdate[(r[0], y)] = (r[6] or '')[:10] if not r[5] else os.path.basename(f).split('_')[-1][:8]
            if r[4] and not r[5]: pinact.add((r[0], y))
    # 每个 CIK 的定期报告日期(排好序)
    per = {c: sorted(r[2] for r in s['f'] if r[1].startswith(PERIODIC)) for c, s in SUB.items()}

    import re, difflib, unicodedata
    STOP = {'INC', 'CORP', 'CORPORATION', 'CO', 'COMPANY', 'LTD', 'PLC', 'THE', 'HOLDINGS', 'HLDGS', 'GROUP', 'CLASS', 'A', 'B', 'C', 'NEW', 'DE',
            'COMMON', 'STOCK', 'LP', 'L', 'P', 'TRUST', 'N', 'V', 'NV', 'SA', 'AG', 'INTERNATIONAL', 'LIMITED', 'LLC', 'REIT', 'HOLDING', 'OF', 'AND', 'SHARES', 'ORDINARY'}
    def toks(x):
        x = unicodedata.normalize('NFKD', x or '').encode('ascii', 'ignore').decode()
        x = re.sub(r'\(.*?\)', ' ', x.upper().replace("'", '')); x = re.sub(r'[^A-Z0-9 ]', ' ', x)
        return [w for w in x.split() if w not in STOP]
    def sim(a, b):
        ta, tb = toks(a), toks(b)
        if not ta or not tb: return 0.0
        r_ = difflib.SequenceMatcher(None, ' '.join(ta), ' '.join(tb)).ratio()
        ov = len(set(ta) & set(tb)) / min(len(set(ta)), len(set(tb)))
        # 1105:字面像但第一个词不同的不算(Alexion Pharmaceuticals vs Vanda Pharmaceuticals 字面相似度 0.8 —— Polygon 把 Alexion 挂在了 Vanda 的 CIK 上)
        return 2 if (ov >= 0.8 or (r_ >= 0.8 and difflib.SequenceMatcher(None, ta[0], tb[0]).ratio() >= 0.75)) else 1 if ov >= 0.66 else 0      # 2 = 名字对得上,1 = 只对上三分之二(弱),0 = 对不上
    def name_lvl(c, nm):
        s_ = SUB.get(c)
        if not s_: return 0
        names = [s_['n']] + [f[0] for f in s_.get('fn', [])]
        return max(sim(nm, n) for n in names)
    def name_ok(c, nm): return name_lvl(c, nm) == 2

    # 1105 第二处改:代码对应关系只在「这串价格当时确实挂着这个代码」时才算数
    #   (例:2021 年 ETF 先用过 META,年底 Polygon 表里的 META 已经是 Meta Platforms —— 不能拿来给那只 ETF;
    #    AABA 2019 年就没了,SEC 现在的代码表里 AABA 是别家 —— 也不能拿来)
    SPAN = defaultdict(list)
    for r_ in csv.DictReader(open('/home/claude/seg/pit_company_segments.csv')):
        SPAN[(r_['company_id'], r_['ticker'])].append((r_['first_seen'], r_['last_seen'], r_['end_type']))
    def covers(cid, s, d, back=45):
        lo_ = (date.fromisoformat(d) - timedelta(days=back)).isoformat(); hi_ = (date.fromisoformat(d) + timedelta(days=45)).isoformat()
        return any(a_ <= hi_ and b_ >= lo_ for a_, b_, _ in SPAN.get((cid, s), []))
    def still_trading(cid, s):
        return any(e_.startswith('样本末尾仍在交易') for _, _, e_ in SPAN.get((cid, s), []))
    def back_of(s, yy):                           # 已退市的那条:退市前一年内这串价格挂过这个代码就算
        return 400 if (s, yy) in pinact else 45
    def snap_date(s, yy):
        d_ = pdate.get((s, yy)) or f'{yy}1231'
        d_ = d_.replace('-', ''); return f'{d_[:4]}-{d_[4:6]}-{d_[6:8]}'

    def filed_in(c, lo, hi):
        return sum(1 for x in per.get(c, []) if lo <= x <= hi)

    # 先按公司收集所有来源的候选(任何年份、任何代码),再逐年用「当年交过定期报告」来核
    co_ciks = defaultdict(set)
    for r in pool:
        cid, s = r['company_id'], r['symbol']
        if cid in ex: co_ciks[cid].add(ex[cid])
        if s.upper() in secnow and still_trading(cid, s): co_ciks[cid].add(secnow[s.upper()])
        for yy, (c, nm) in poly.get(s, {}).items():
            if covers(cid, s, snap_date(s, yy), back_of(s, yy)) and name_ok(c, nm): co_ciks[cid].add(c)
    out, pend = [], []
    for r in pool:
        y, s, cid = int(r['year']), r['symbol'], r['company_id']
        lo, hi = f'{y - 1}-10-01', f'{y}-12-31'          # 当年年初排名 → 看前一年 Q4 到当年底有没有交定期报告
        # 1105 改:按「谁最可信」排先后,不再按「谁交的报告多」—— 后者会让同一串价格里别的年份的主人抢走这一年
        #   ① Polygon 去年年底那份代码表里,这个代码对应的 CIK(最贴近当时)—— 但名字要和 SEC 对得上(防 Polygon 填错)
        #   ② 考卷名单里核过的 CIK  ③ Polygon 其他年份  ④ SEC 现在的代码表  ⑤ 同一串价格别的年份的主人
        order = []
        weak = []                                 # 名字只对上三分之二的(例:Fifth Street Finance vs Fifth Street Senior Floating Rate)放最后
        if (y - 1) in poly.get(s, {}) and covers(cid, s, snap_date(s, y - 1), back_of(s, y - 1)):
            c, nm = poly[s][y - 1]
            if name_ok(c, nm): order.append((c, f'polygon{y - 1}'))
            elif name_lvl(c, nm) == 1: weak.append((c, f'polygon{y - 1}_weakname'))
        if cid in ex: order.append((ex[cid], 'exam'))
        for yy, (c, nm) in sorted(poly.get(s, {}).items(), key=lambda kv: abs(kv[0] - (y - 1))):
            if covers(cid, s, snap_date(s, yy), back_of(s, yy)):
                if name_ok(c, nm): order.append((c, f'polygon{yy}'))
                elif name_lvl(c, nm) == 1: weak.append((c, f'polygon{yy}_weakname'))
        if s.upper() in secnow and still_trading(cid, s): order.append((secnow[s.upper()], 'sec_now'))
        for c in sorted(co_ciks.get(cid, ())): order.append((c, 'same_company_other_year'))
        order += weak
        best = None; tried = []
        for c, src in order:
            n_ = filed_in(c, lo, hi); tried.append((n_, False, c, src))
            if n_ > 0: best = (n_, False, c, src); break
        scored = tried
        base = {'year': y, 'rank': r['rank'], 'symbol': s, 'company_id': cid}
        if best:
            out.append({**base, 'cik': best[2], 'cik_source': best[3], 'periodic_filings': best[0], 'sec_name': SUB[best[2]]['n']})
        else:
            pend.append({**base, 'seg_start': r['seg_start'], 'seg_end': r['seg_end'],
                         'candidates_tried': ';'.join(f'{c}({src})' for _, _, c, src in scored),
                         'reason': 'no_candidate' if not order else 'no_10K_10Q_filed_that_year'})
    # 文件夹:按 CIK,一家申报主体一个;用它最后一次出现在池子里的代码命名,重名加 CIK
    last = {}
    for x in sorted(out, key=lambda x: x['year']): last[x['cik']] = x['symbol']
    names = defaultdict(list)
    for c, s in last.items(): names[s].append(c)
    folder = {c: (s if len(names[s]) == 1 else f'{s}__{c}') for c, s in last.items()}
    for x in out: x['folder'] = folder[x['cik']]
    for name, data in (('pool_cik_by_year_1103.csv', out), ('cik_pending_1103.csv', pend)):
        with open(os.path.join(out_dir, name), 'w', newline='') as fh:
            w = csv.DictWriter(fh, fieldnames=list(data[0]) if data else ['year']); w.writeheader(); w.writerows(data)
    # 一家一行的清单(给建库用)
    agg = defaultdict(lambda: {'symbols': [], 'company_ids': set(), 'years': []})
    for x in out:
        a = agg[x['cik']]; a['years'].append(x['year']); a['company_ids'].add(x['company_id'])
        if x['symbol'] not in a['symbols']: a['symbols'].append(x['symbol'])
    with open(os.path.join(out_dir, 'cik_list_1103.csv'), 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['cik', 'folder', 'company_id', 'symbols', 'y0', 'y1', 'sec_name'])
        for c, a in sorted(agg.items(), key=lambda kv: folder[kv[0]]):
            w.writerow([c, folder[c], ';'.join(sorted(a['company_ids'])), ';'.join(a['symbols']), min(a['years']), max(a['years']), SUB[c]['n']])
    cos_all = {r['company_id'] for r in pool}; cos_ok = {x['company_id'] for x in out}
    print('池子行(公司×年)', len(pool), '· 对上', len(out), '· 待补', len(pend),
          '| 公司', len(cos_all), '· 至少一年对上', len(cos_ok), '· 申报主体(CIK)', len(agg))


if __name__ == '__main__':
    main(*sys.argv[1:])
