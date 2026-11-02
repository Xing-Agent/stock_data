# -*- coding: utf-8 -*-
"""考卷 1,042 只 → 每只一个 daily.json(和 pilot_300 同格式)+ manifest.csv。
大白话:
  · 价格:Massive/Polygon 全市场日线,原始价(不复权),2016-01-01 ~ 2025-12-31
  · 按「公司」取:沿改名链把几段接起来(FB→META 这种)
  · split_coefficient:拆股(对账后、「价格真正跳的那天」)+ 分拆(人工确认,口径同 Alpha Vantage:前收 ÷ 当天开盘)
    + 改名换代码同时分拆的(AA→ARNC→HWM、IR→TT、UTX→RTX……)接续系数。引擎照旧在 load_daily() 里一次复权
  · dividend_amount:Polygon 分红(除息日)
  · 退市的:取到最后一个交易日为止;结算价见 reviews/ 那份表
"""
import json, os, gzip, hashlib, polars as pl
from collections import defaultdict
OUT = '/home/claude/stock_data/exam_1042'
L = pl.read_csv('/home/claude/exam/exam_list_1101.csv', infer_schema_length=0)
S = pl.read_csv('/home/claude/seg/pit_company_segments.csv', infer_schema_length=0)
O = pl.read_parquet('exam_ohlcv.parquet')
PX = pl.read_parquet('/home/claude/splits/px_2015.parquet')
START, END = '2016-01-01', '2025-12-31'

# ── 特殊公司:代码被复用 / 改名同时分拆 / 换股合并 —— 人工写清楚每一段 ──
# (代码, 起, 止);止为 None 表示到该代码这一段结束
SPECIAL = {
    'AA':   [('AA', START, '2016-10-31'), ('ARNC', '2016-11-01', '2020-03-31'), ('HWM', '2020-04-01', None)],
    'DLPH': [('DLPH', START, '2017-12-04'), ('APTV', '2017-12-05', None)],
    'IR':   [('IR', START, '2020-02-28'), ('TT', '2020-03-02', None)],
    'UTX':  [('UTX', START, '2020-04-02'), ('RTX', '2020-04-03', None)],
    'HTZ':  [('HTZ', START, '2016-06-30'), ('HRI', '2016-07-01', None)],
    'WYN':  [('WYN', START, '2018-05-31'), ('WYND', '2018-06-01', None)],
    'CFX':  [('CFX', START, '2022-04-04'), ('ENOV', '2022-04-05', None)],
    'JCOM': [('JCOM', START, '2021-10-07'), ('ZD', '2021-10-08', None)],
    'FBHS': [('FBHS', START, '2022-12-14'), ('FBIN', '2022-12-15', None)],
    # 换股合并、代码被合并后的公司接着用 —— 截断,按退市处理(和老池换股并购的做法一致)
    'AM':   [('AM', START, '2019-03-12')],
    'TCB':  [('TCB', START, None), ('TCF', START, '2019-07-31')],
    'EVHC': [('EVHC', START, '2016-12-01')],
}
STOCK_MERGER_CUT = {'AM': 'Antero Midstream Partners 并入 AMGP(改名 AM),换股 + 现金',
                    'TCB': 'TCF Financial 并入 Chemical Financial(改名 TCF),换股',
                    'EVHC': 'Envision Healthcare 并入 AmSurg(改名 EVHC),换股'}

segs = S.filter(pl.col('company_id').is_in(L['company_id'].to_list()))
plan = {}
for r in L.iter_rows(named=True):
    sym = r['symbol']
    if sym in SPECIAL:
        pieces = SPECIAL[sym]
    else:
        ch = segs.filter(pl.col('company_id') == r['company_id']).sort('first_seen')
        pieces = [(t, max(a, START), min(b, END)) for t, a, b in ch.select('ticker', 'first_seen', 'last_seen').iter_rows() if b >= START]
    plan[sym] = pieces

# 拆股
SP = pl.read_csv('exam_splits_1101.csv', infer_schema_length=0).filter(pl.col('check').str.starts_with('确认'))
split_on = defaultdict(float)
for t, d, ratio in SP.select('ticker', 'd', pl.col('ratio').cast(pl.Float64)).iter_rows():
    split_on[(t, d)] = ratio
split_on.pop(('AA', '2016-11-01'), None)          # 这条是 Alcoa 拆成两家,已由接续系数处理
# 分拆(人工确认)
SE = pl.read_csv('spin_events_1101.csv', infer_schema_length=0).filter(pl.col('coefficient').is_not_null())
drop = {('UTX', 'CARR'), ('WYN', 'WH'), ('CFX', 'ESAB'), ('JCOM', 'CCSI'), ('FBHS', 'MBC'), ('AA', 'AA'), ('ARNC', 'ARNC'),
        ('DWDP', 'DOW'), ('DWDP', 'CTVA'), ('RRD', 'DFIN')}
spin_on = {}
spin_rows = []
for par, name, sp, d0, ex, coef in SE.select('parent_ticker', 'spinco', 'spinco_ticker', 'spinco_first', 'ex_date', pl.col('coefficient').cast(pl.Float64)).iter_rows():
    if (par, sp) in drop: continue
    spin_on[(par, ex)] = coef; spin_rows.append((par, name, sp, ex, coef))
# 人工补:RRD 1 并 3 + 分出两家同一天;J / EHC 改过名的母公司
def gapcoef(t, d):
    x = PX.filter(pl.col('ticker') == t).sort('d').with_columns(pl.col('close').shift(1).alias('pc')).filter(pl.col('d') == d)
    return float(x['pc'][0] / x['open'][0]) if x.height else None
for par, name, sp, d in [('RRD', 'Donnelley Financial + LSC(同日 1 并 3)', 'DFIN', '2016-10-03'), ('J', 'Amentum', 'AMTM', '2024-09-30'), ('EHC', 'Enhabit', 'EHAB', '2022-07-01')]:
    c = gapcoef(par, d)
    if c: spin_on[(par, d)] = c; spin_rows.append((par, name, sp, d, c))
split_on.pop(('RRD', '2016-10-03'), None)
# Polygon 有时把分拆也记成「拆股」(XPO→GXO、MDU→ECG……):同一天人工分拆已记,就不再叠拆股
for k in list(spin_on):
    split_on.pop(k, None)
# 接续系数:前一段最后一天收盘 ÷ 后一段第一天开盘
def last_close(t, d):
    x = PX.filter((pl.col('ticker') == t) & (pl.col('d') <= d)).sort('d').tail(1); return float(x['close'][0]) if x.height else None
cont_on = {}
for sym, pcs in SPECIAL.items():
    for (t0, a0, b0), (t1, a1, b1) in zip(pcs, pcs[1:]):
        if t0 == 'TCB': continue
        o = PX.filter((pl.col('ticker') == t1) & (pl.col('d') == a1))
        c = last_close(t0, b0)
        if o.height and c: cont_on[(t1, a1)] = c / float(o['open'][0])

# 分红
D = json.load(gzip.open('/home/claude/stock_data/probe/splits_1101/polygon_dividends_1101.json.gz'))
DV = pl.DataFrame(D['rows'], schema=D['fields'], orient='row', infer_schema_length=None).filter(pl.col('currency').fill_null('USD') == 'USD')
div_on = defaultdict(float)
for t, d, a in DV.select('ticker', 'ex_dividend_date', pl.col('cash_amount').cast(pl.Float64)).iter_rows():
    if a: div_on[(t, d)] += a

Og = {t: g.sort('d') for (t,), g in O.group_by(['ticker'])}
os.makedirs(OUT, exist_ok=True)
man = []
last_td = O['d'].max()
for r in L.iter_rows(named=True):
    sym = r['symbol']; rows = []; events = []
    for t, a, b in plan[sym]:
        g = Og.get(t)
        if g is None: continue
        g = g.filter((pl.col('d') >= a) & (pl.col('d') <= (b or END)) & (pl.col('d') <= END))
        for d, op, hi, lo, cl, vo in g.select('d', 'open', 'high', 'low', 'close', 'volume').iter_rows():
            coef = 1.0; kinds = []
            for src, tag in ((split_on, 'split'), (spin_on, 'spinoff'), (cont_on, 'ticker_change_continuation')):
                v = src.get((t, d))
                if v: coef *= v; kinds.append(tag)
            dv = round(div_on.get((t, d), 0.0), 6)
            rows.append({'date': d, 'open': op, 'high': hi, 'low': lo, 'close': cl, 'volume': vo, 'dividend_amount': dv,
                         'split_coefficient': round(coef, 8) if kinds else 1.0, 'price': cl, 'adjusted_close': None, 'source_ticker': t})
            if kinds: events.append({'effective_date': d, 'action_type': '+'.join(kinds), 'split_coefficient': round(coef, 8), 'source_ticker': t})
            if dv: events.append({'effective_date': d, 'action_type': 'dividend', 'cash_amount': dv, 'source_ticker': t})
    rows.sort(key=lambda x: x['date'])
    # 同一天两段重叠(改名当天)只留一根
    ded = {}; [ded.__setitem__(x['date'], x) for x in rows]; rows = [ded[k] for k in sorted(ded)]
    last = rows[-1]['date'] if rows else None
    delisted = bool(last and last < '2025-12-31' and last < last_td)
    doc = {'status': 'ready', 'symbol': sym, 'interval': '1d', 'timezone': 'America/New_York', 'adjustment': 'raw',
           'provider': 'massive_polygon_flatfiles', 'source_url': 'Massive (Polygon) US stocks day aggregates flat files',
           'retrieved_at': '2026-11-02', 'warnings': [], 'start_date': START, 'end_date': END, 'data': rows,
           'company_segments': [{'ticker': t, 'from': a, 'to': b} for t, a, b in plan[sym]],
           'corporate_actions': {'status': 'ready', 'provider': 'polygon_splits_dividends+manual_spinoffs', 'events': events,
                                 'note': 'split_coefficient 已包含拆股、分拆、改名接续三种;引擎按老规矩在 load_daily() 里复权一次'}}
    os.makedirs(f'{OUT}/{sym}', exist_ok=True)
    json.dump(doc, open(f'{OUT}/{sym}/daily.json', 'w'), ensure_ascii=False, separators=(',', ':'))
    mc = float(r['mktcap_20151231']) if r['mktcap_20151231'] else None
    size = 'large' if (mc is None or mc >= 1e10) else 'mid'
    man.append({'symbol': sym, 'name': r['name'], 'origin': 'exam_1042', 'size_group': size, 'sector': r['sic'] or '',
                'market_cap_usd': r['mktcap_20151231'], 'market_cap_date': '2015-12-31', 'delisted': delisted,
                'delisting_date': last if delisted else '', 'retirement_category': ('ACQUISITION_STOCK' if sym in STOCK_MERGER_CUT else ''),
                'data_path': f'{sym}/daily.json', 'download_end_date': last or '', 'bars': len(rows), 'cik': r['cik'],
                'company_id': r['company_id']})
M = pl.DataFrame(man); M.write_csv(f'{OUT}/manifest.csv')
pl.DataFrame(spin_rows, schema=['parent_ticker', 'spinco', 'spinco_ticker', 'ex_date', 'coefficient'], orient='row').write_csv(f'{OUT}/spinoffs_manual_1102.csv')
print('只数', M.height, '· 退市', M['delisted'].sum(), '· 行数中位', M['bars'].median(), '· 0 行', M.filter(pl.col('bars') == 0).height)
print('拆股事件', sum(1 for k in split_on), '· 分拆', len(spin_on), '· 接续', len(cont_on), cont_on)
