#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 53 · 行情扩面:每个文件夹(= 一个 SEC 申报主体)一份 daily.json.gz,格式照 pilot_300/<票>/daily.json。

大白话:
  · 价格:Polygon 全量日线,**原始价**(adjustment = raw),2004-01-02 起,接 Polygon 2026-08-04 ~ 2026-11-04
  · 按 plan.json 里定好的「哪段时间用哪个代码」把几段接起来;每根 K 线带 source_ticker
  · split_coefficient 逐根给:没事件写 1;拆股那天写比例(1 拆 4 → 4),用的是对齐过的拆股表
    (Polygon 记的日子和价格真正跳的那天不一致时,以价格真正跳的那天为准);2004~2014 年和 2026-08 以后的拆股用同一套办法补齐(align_splits.py)
  · 一次性派现 ≥ 前收 10%:按 11-02 Lin 拍板的规则,也写进 split_coefficient(系数 = 前收 ÷(前收 − 派现)),
    并在 corporate_actions.events 里单独标 special_distribution
  · dividend_amount 逐根给(除息日),没有写 0
  · 分拆没有人工核过(考卷那 44 次是逐只核的),这里不自动加系数;
    换代码那天、以及没有任何事件却隔夜跳到 1.8 倍以上 / 0.55 倍以下的(和 11-01 同一门槛;前收 < 1 美元的不报),都写进 warnings,让用的人自己判断

用法:python3 build_market.py plan.json ohlcv.parquet out_dir [only_n]
"""
import csv, gzip, hashlib, json, os, sys
from collections import defaultdict
import polars as pl

ROOT = '/home/claude/stock_data'
SPECIAL_MIN = 0.10
from datetime import datetime, timezone
RETRIEVED = os.environ.get('RETRIEVED_AT') or datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def main(plan_path, px_path, out_dir, only_n=None):
    P = json.load(open(plan_path))
    plan = P['plan']
    folders = sorted(plan)
    if only_n: folders = folders[:int(only_n)]
    O = pl.read_parquet(px_path)
    Og = {t: g.sort('d') for (t,), g in O.group_by(['ticker'])}
    cal = sorted(O['d'].unique().to_list())
    last_td = cal[-1]
    # 拆股:2004 起全期对齐表(align_splits.py 产出,和 11-01 那张在 2015 年以后逐条一致),只用「确认」的
    AL = pl.read_csv(f'{ROOT}/probe/market_1105/polygon_splits_aligned_1105.csv', infer_schema_length=0).filter(pl.col('check').str.starts_with('确认'))
    # 同一天同一只有两条(Polygon 重复 / 修订版,共 6 处,都是小比例送股)→ 只留和价格跳得最吻合的那条
    AL = AL.with_columns(pl.col('err').cast(pl.Float64)).sort('err').unique(['ticker', 'aligned_date'], keep='first')
    split_on = {(t, d): float(r) for t, d, r in AL.select('ticker', 'aligned_date', 'ratio').iter_rows()}
    # 分红(美元现金)
    D = json.load(gzip.open(f'{ROOT}/probe/splits_1101/polygon_dividends_1101.json.gz'))
    fi = {f: i for i, f in enumerate(D['fields'])}
    # 同一天同金额同类型的完全重复行(Polygon 偶尔重复,~0.07%)只算一次;同一天不同金额(常规 + 特别)相加
    div_on = defaultdict(float); seen = set(); pay_on = {}
    for r in D['rows']:
        t, ex, amt, cur, typ = r[fi['ticker']], r[fi['ex_dividend_date']], r[fi['cash_amount']], r[fi['currency']], r[fi['dividend_type']]
        if (cur or 'USD') == 'USD' and amt and ex < '2026-06-01' and (t, ex, amt, typ) not in seen:
            seen.add((t, ex, amt, typ)); div_on[(t, ex)] += float(amt); pay_on.setdefault((t, ex), r[fi['pay_date']])
    D2 = json.load(gzip.open(f'{ROOT}/probe/market_1105/raw/polygon_dividends_since_20260601.json.gz'))
    for t, ex, amt, cur, typ, freq, pay, *_ in D2['rows']:
        if (cur or 'USD') == 'USD' and amt and '2026-06-01' <= ex <= last_td and (t, ex, amt, typ) not in seen:
            seen.add((t, ex, amt, typ)); div_on[(t, ex)] += float(amt); pay_on.setdefault((t, ex), pay)
    # 考卷 11-02 查出来的 Polygon 漏记大额派现(按公司公告补),这里同样补上(只在这几只出现在本批时生效)
    for k, v in {('MIC', '2021-01-11'): 11.00, ('MIC', '2021-10-08'): 37.386817, ('AABA', '2019-09-24'): 51.50,
                 ('EQC', '2024-12-09'): 19.00, ('NLOK', '2020-02-03'): 12.00}.items():
        if not div_on.get(k): div_on[k] += v
    os.makedirs(out_dir, exist_ok=True)
    man, shas, fails = [], [], [list(x) + ['plan'] for x in P['fail']]
    for f in folders:
        p = plan[f]; rows = []; events = []; warns = list(p.get('warnings', []))
        for t, a, b, cid, et in p['pieces']:
            g = Og.get(t)
            if g is None: warns.append(f'代码 {t}({a}~{b})在 Polygon 日线里找不到'); continue
            g = g.filter((pl.col('d') >= a) & (pl.col('d') <= (b if b < '2026-08-03' else '2099-12-31')))
            for d, op, hi, lo, cl, vo in g.select('d', 'open', 'high', 'low', 'close', 'volume').iter_rows():
                sc = split_on.get((t, d), 1.0)
                dv = round(div_on.get((t, d), 0.0), 6)
                vo = int(round(vo)) if vo is not None and abs(vo - round(vo)) < 1e-6 else vo
                rows.append({'date': d, 'open': op, 'high': hi, 'low': lo, 'close': cl, 'volume': vo, 'dividend_amount': dv,
                             'split_coefficient': sc, 'price': cl, 'adjusted_close': None, 'source_ticker': t})
                if sc != 1.0: events.append({'effective_date': d, 'action_type': 'split', 'split_coefficient': sc, 'cash_amount': None, 'source': 'polygon_splits_aligned', 'source_ticker': t})
                if dv: events.append({'effective_date': d, 'action_type': 'dividend', 'cash_amount': dv, 'payment_date': pay_on.get((t, d)), 'split_coefficient': None, 'source': 'polygon_dividends', 'source_ticker': t})
        rows.sort(key=lambda x: x['date'])
        ded = {}
        for x in rows: ded[x['date']] = x
        rows = [ded[k] for k in sorted(ded)]
        if not rows:
            fails.append([f, p['cik'], '计划里的代码段在 Polygon 日线里都没有数据', 'data']); continue
        # 换代码那天隔夜断层 > 20%(破产重组换新股、分拆、按比例换股合并……)没有核过接续系数 → 不硬接:
        # 只留最后一次断层之后的那段,前面那段列进「取不到的清单」(部分)
        cut_at = None
        for a_, b_ in zip(rows, rows[1:]):
            if a_['source_ticker'] != b_['source_ticker'] and a_['close'] and b_['open'] and abs(b_['open'] / a_['close'] - 1) > 0.20:
                cut_at = (b_['date'], a_['source_ticker'], b_['source_ticker'], b_['open'] / a_['close'] - 1, rows[0]['date'], a_['date'])
        if cut_at:
            d0, t0, t1, jp, s0, e0 = cut_at
            rows = [x for x in rows if x['date'] >= d0]
            events = [e for e in events if e['effective_date'] >= d0]
            warns.append(f'{d0} 代码 {t0} → {t1} 隔夜断层 {jp:+.1%},没核过接续系数,前段 {s0}~{e0} 没给(见取不到的清单)')
            fails.append([f, p['cik'], f'部分:{s0}~{e0}({t0} 等)没给 —— {d0} 换成 {t1} 时隔夜断层 {jp:+.1%},接续系数没核过', 'partial'])
        # 一次性大额派现 → 系数;换代码、无事件大跳 → warnings
        for a_, b_ in zip(rows, rows[1:]):
            pc = a_['close']; amt = b_['dividend_amount']
            if amt and pc and amt / pc >= SPECIAL_MIN and amt < pc:
                c = pc / (pc - amt); b_['split_coefficient'] = round(b_['split_coefficient'] * c, 8)
                events.append({'effective_date': b_['date'], 'action_type': 'special_distribution', 'cash_amount': amt, 'prev_close': pc,
                               'split_coefficient': round(c, 8), 'source': 'rule_1102_special_distribution_ge_10pct', 'source_ticker': b_['source_ticker']})
            if a_['source_ticker'] != b_['source_ticker']:
                warns.append(f"{b_['date']} 代码 {a_['source_ticker']} → {b_['source_ticker']},隔夜 {b_['open'] / pc - 1:+.1%}(没加接续系数)")
            elif pc and pc >= 1 and b_['open'] and b_['split_coefficient'] == 1.0 and not (0.55 <= pc / b_['open'] <= 1.8):   # 和 11-01 扫描同一个门槛
                warns.append(f"{b_['date']} 无事件隔夜跳 {b_['open'] / pc - 1:+.1%}(可能是漏记的分拆 / 拆股,也可能是真行情)")
        i0, i1 = cal.index(rows[0]['date']), cal.index(rows[-1]['date'])
        have = {x['date'] for x in rows}
        missing = [d for d in cal[i0:i1 + 1] if d not in have]
        last = rows[-1]['date']
        delisted = last < last_td
        doc = {'status': 'ready', 'symbol': f, 'cik': p['cik'], 'interval': '1d', 'timezone': 'America/New_York', 'adjustment': 'raw',
               'provider': 'polygon', 'source_url': 'Polygon (Massive) US stocks day aggregates: flat files to 2026-08-03; /v2/aggs/grouped/locale/us/market/stocks/{date}?adjusted=false from 2026-08-04',
               'retrieved_at': RETRIEVED, 'start_date': rows[0]['date'], 'end_date': last, 'warnings': warns,
               'market_coverage': {'status': 'complete' if not missing else 'partial', 'calendar': 'XNYS', 'timezone': 'America/New_York', 'session': 'regular',
                                   'expected_bars': i1 - i0 + 1, 'observed_bars': len(rows), 'missing_bars': len(missing), 'missing_examples': missing[:10]},
               'company_segments': [{'ticker': t, 'from': a, 'to': b, 'company_id': cid} for t, a, b, cid, et in p['pieces']],
               'corporate_actions': {'status': 'ready', 'provider': 'polygon', 'split_provider': 'polygon (aligned to the day the raw price actually jumps)',
                                     'dividend_provider': 'polygon', 'spinoffs': 'not reviewed for this set; see warnings', 'events': sorted(events, key=lambda e: e['effective_date'])},
               'data': rows}
        os.makedirs(os.path.join(out_dir, f), exist_ok=True)
        path = os.path.join(out_dir, f, 'daily.json.gz')
        raw = json.dumps(doc, ensure_ascii=False, separators=(',', ':')).encode()
        with open(path, 'wb') as fh:
            with gzip.GzipFile(fileobj=fh, mode='wb', mtime=0, filename='') as z: z.write(raw)
        shas.append((hashlib.sha256(open(path, 'rb').read()).hexdigest(), f'{f}/daily.json.gz'))
        man.append({'symbol': f, 'cik': p['cik'], 'name': p['name'], 'tickers': ';'.join(dict.fromkeys(x['source_ticker'] for x in rows)),
                    'sic': p.get('sic') or '', 'start_date': rows[0]['date'], 'end_date': last, 'bars': len(rows), 'missing_bars': len(missing),
                    'delisted': delisted, 'delisting_date': last if delisted else '', 'warnings': len(warns)})
    with open(os.path.join(out_dir, '_manifest_raw.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=list(man[0])); w.writeheader(); w.writerows(man)
    with open(os.path.join(out_dir, '_SHA256SUMS'), 'w') as fh:
        for h, n in sorted(shas, key=lambda x: x[1]): fh.write(f'{h}  {n}\n')
    with open(os.path.join(out_dir, '_unavailable.csv'), 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['symbol', 'cik', 'reason', 'stage']); w.writerows(fails)
    print('写了', len(man), '· 取不到', len(fails))


if __name__ == '__main__':
    main(*sys.argv[1:])
