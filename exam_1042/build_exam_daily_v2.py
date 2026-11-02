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
O = pl.concat([pl.read_parquet('exam_ohlcv.parquet'), pl.read_parquet('exam_ohlcv_extra_1102.parquet')]).unique(['ticker', 'd'])
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
    'WYN':  [('WYN', START, '2018-05-31'), ('WYND', '2018-06-01', '2021-02-16'), ('TNL', '2021-02-17', None)],
    'CFX':  [('CFX', START, '2022-04-04'), ('ENOV', '2022-04-05', None)],
    'JCOM': [('JCOM', START, '2021-10-07'), ('ZD', '2021-10-08', None)],
    'FBHS': [('FBHS', START, '2022-12-14'), ('FBIN', '2022-12-15', None)],
    # 换股合并、代码被合并后的公司接着用 —— 截断,按退市处理(和老池换股并购的做法一致)
    'AM':   [('AM', START, '2019-03-12')],
    'TCB':  [('TCB', START, None), ('TCF', START, '2019-07-31')],
    'EVHC': [('EVHC', START, '2016-12-01')],
    # ── 11-02 补:公司还在、只是换了代码,原来在换代码那天断了(SEC 同一个 CIK 之后照常交年报)──
    'HCN':  [('HCN', START, '2018-02-27'), ('WELL', '2018-02-28', None)],
    'HCP':  [('HCP', START, '2019-11-04'), ('PEAK', '2019-11-05', '2024-03-01'), ('DOC', '2024-03-04', None)],
    'FLT':  [('FLT', START, '2024-03-22'), ('CPAY', '2024-03-25', None)],
    'GPS':  [('GPS', START, '2024-08-21'), ('GAP', '2024-08-22', None)],
    'BLL':  [('BLL', START, '2022-05-09'), ('BALL', '2022-05-10', None)],
    'NYCB': [('NYCB', START, '2024-10-25'), ('FLG', '2024-10-28', None)],
    'DDR':  [('DDR', START, '2018-10-11'), ('SITC', '2018-10-12', None)],
    'FEYE': [('FEYE', START, '2021-10-04'), ('MNDT', '2021-10-05', None)],
    'HLS':  [('HLS', START, '2017-12-29'), ('EHC', '2018-01-02', None)],
    'FII':  [('FII', START, '2020-01-31'), ('FHI', '2020-02-03', None)],
    'CREE': [('CREE', START, '2021-10-01'), ('WOLF', '2021-10-04', '2025-09-26')],   # 2025-09 破产重整,老股注销
    'POL':  [('POL', START, '2020-07-10'), ('AVNT', '2020-07-13', None)],
    'JW.A': [('JW.A', START, '2022-03-31'), ('WLY', '2022-04-01', None)],
    'CMN':  [('CMN', START, '2016-12-02'), ('CMD', '2016-12-05', '2021-06-01')],
    'HFC':  [('HFC', START, '2022-03-14'), ('DINO', '2022-03-15', None)],
    'XON':  [('XON', START, '2020-01-31'), ('PGEN', '2020-02-03', None)],
    'RBC':  [('RBC', START, '2021-10-04'), ('RRX', '2021-10-05', None)],
    'BXS':  [('BXS', START, '2021-10-28'), ('CADE', '2021-11-01', None)],
    # 合并里本公司是存续方、改了代码:股东手里的股票还在
    'DISCA': [('DISCA', START, '2022-04-08'), ('WBD', '2022-04-11', None)],
    'ESV':  [('ESV', START, '2019-07-30'), ('VAL', '2019-07-31', '2020-08-14')],     # 2020-08 破产,老股只拿认股权证
    'TYC':  [('TYC', START, '2016-09-02'), ('JCI', '2016-09-06', None)],             # 原来错接到 DVMT
    'NCR':  [('NCR', START, '2023-10-16'), ('VYX', '2023-10-17', None)],             # 同日分拆 Atleos
    'ACE':  [('ACE', START, '2016-01-14'), ('CB', '2016-01-15', None)],
    'WGP':  [('WGP', START, '2019-02-27'), ('WES', '2019-02-28', None)],
    'SXL':  [('SXL', START, '2017-04-28'), ('ETP', '2017-05-01', '2018-10-18')],
    'BHI':  [('BHI', START, '2017-07-03'), ('BHGE', '2017-07-05', '2019-10-17'), ('BKR', '2019-10-18', None)],
    'WSH':  [('WSH', START, '2016-01-04'), ('WLTW', '2016-01-05', '2022-01-07'), ('WTW', '2022-01-10', None)],
    'BIN':  [('BIN', START, '2016-05-31'), ('WCN', '2016-06-01', None)],
    'HRG':  [('HRG', START, '2018-07-13'), ('SPB', '2018-07-16', None)],
    'AMSG': [('AMSG', START, '2016-12-01'), ('EVHC', '2016-12-02', '2018-10-10')],
    'HTA':  [('HTA', START, '2022-07-20'), ('HR', '2022-07-21', None)],
    'NSAM': [('NSAM', START, '2017-01-10'), ('CLNS', '2017-01-11', '2018-06-22'), ('CLNY', '2018-06-25', '2021-06-21'), ('DBRG', '2021-06-22', None)],
    'DOW':  [('DOW', START, '2017-08-31'), ('DWDP', '2017-09-01', '2019-05-31'), ('DD', '2019-06-03', None)],
    'DD':   [('DD', START, '2017-08-31'), ('DWDP', '2017-09-01', '2019-05-31'), ('DD', '2019-06-03', None)],
    'LGF':  [('LGF', START, '2016-12-08'), ('LGF.A', '2016-12-09', '2025-05-06'), ('STRZ', '2025-05-07', None)],   # 2025-05 分出新 Lionsgate,原公司改名 Starz(1 并 15)           # 原来错接到 UWT
    'SPN':  [('SPN', START, '2019-09-26'), ('SPN', '2019-12-26', '2020-09-17')],     # 中间 Polygon 缺 62 天;1 并 10
    # 链接错了:DCP 被 Phillips 66 现金收购,不是改名成 CAVA
    'DPM':  [('DPM', START, '2017-01-20'), ('DCP', '2017-01-23', '2023-06-14')],
    # 代码被收购方拿走(换股合并的被并方)—— 截断,按换股并购退市处理
    'CB':   [('CB', START, '2016-01-14')],
    'FOXA': [('FOXA', START, '2019-03-18')],
    'WES':  [('WES', START, '2019-02-27')],
    'ETP':  [('ETP', START, '2017-04-28')],
    'GRUB': [('GRUB', START, '2021-06-14')],
}
# 纯改代码(1 股换 1 股)—— 接续当天不加系数,隔夜涨跌照实算
CONT_ONE = {('WELL', '2018-02-28'), ('PEAK', '2019-11-05'), ('DOC', '2024-03-04'), ('CPAY', '2024-03-25'), ('GAP', '2024-08-22'),
            ('BALL', '2022-05-10'), ('FLG', '2024-10-28'), ('SITC', '2018-10-12'), ('MNDT', '2021-10-05'), ('EHC', '2018-01-02'),
            ('FHI', '2020-02-03'), ('WOLF', '2021-10-04'), ('AVNT', '2020-07-13'), ('WLY', '2022-04-01'), ('CMD', '2016-12-05'),
            ('DINO', '2022-03-15'), ('PGEN', '2020-02-03'), ('RRX', '2021-10-05'), ('CADE', '2021-11-01'), ('WBD', '2022-04-11'),
            ('VAL', '2019-07-31'), ('CB', '2016-01-15'), ('WES', '2019-02-28'), ('ETP', '2017-05-01'), ('BKR', '2019-10-18'),
            ('WTW', '2022-01-10'), ('EVHC', '2016-12-02'), ('CLNS', '2017-01-11'), ('CLNY', '2018-06-25'), ('DBRG', '2021-06-22'),
            ('SPN', '2019-12-26'), ('DCP', '2017-01-23'), ('TNL', '2021-02-17'),
            ('JCI', '2016-09-06')}   # Tyco 1 换 0.955 已经在 JCI 当天的拆股系数里(老 JCI 也用同一个系数),不再叠接续系数
# 按公司区分:DOW→DWDP 是 1 换 1;DD→DWDP 是 1 换 1.282,要系数
CONT_ONE_SYM = {('DOW', 'DWDP', '2017-09-01')}
STOCK_MERGER_CUT = {'AM': 'Antero Midstream Partners 并入 AMGP(改名 AM),换股 + 现金',
                    'TCB': 'TCF Financial 并入 Chemical Financial(改名 TCF),换股',
                    'EVHC': 'Envision Healthcare 并入 AmSurg(改名 EVHC),换股',
                    'CB': '老 Chubb 被 ACE 收购(现金 + 换股),ACE 改名 Chubb 用了 CB 代码',
                    'FOXA': '21 世纪福克斯被迪士尼收购(现金 + 换股),FOXA 代码给了新分出的 Fox Corp',
                    'WES': '老 Western Gas Partners 并入 WGP(换股 1.525),WGP 改名用了 WES 代码',
                    'ETP': '老 Energy Transfer Partners 并入 Sunoco Logistics(换股 1.5),SXL 改名用了 ETP 代码',
                    'GRUB': 'Grubhub 被 Just Eat Takeaway 收购(换股),之后 GRUB 代码挂的是对方的 ADS'}

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
# 11-02:新接上的代码段,从全市场对齐后的拆股表里补上它们自己的拆股
AL = pl.read_csv('/home/claude/stock_data/probe/splits_1101/polygon_splits_aligned_1101.csv', infer_schema_length=0).filter(pl.col('check').str.starts_with('确认'))
added_splits = []
for sym, pcs in SPECIAL.items():
    for t, a, b in pcs:
        for d, ratio in AL.filter((pl.col('ticker') == t) & (pl.col('aligned_date') >= a) & (pl.col('aligned_date') <= (b or END))).select('aligned_date', pl.col('ratio').cast(pl.Float64)).iter_rows():
            if (t, d) not in split_on: split_on[(t, d)] = ratio; added_splits.append((sym, t, d, ratio))
split_on.pop(('TYC', '2016-09-02'), None)          # Tyco 1 换 0.955 实际在 2016-09-06 JCI 第一天生效,不在 TYC 最后一天
split_on[('SPN', '2019-12-26')] = 0.1              # Superior Energy 1 并 10(Polygon 那段行情缺失,价格从 0.15 → 4.69)
added_splits.append(('SPN', 'SPN', '2019-12-26', 0.1))
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
for par, name, sp, d in [('RRD', 'Donnelley Financial + LSC(同日 1 并 3)', 'DFIN', '2016-10-03'), ('J', 'Amentum', 'AMTM', '2024-09-30'), ('EHC', 'Enhabit', 'EHAB', '2022-07-01'),
                         # 11-02 补:隔夜跳空 > 30% 排查出来的漏记分拆
                         ('ALV', 'Veoneer', 'VNE', '2018-07-02'), ('POST', 'BellRing Brands', 'BRBR', '2022-03-11'),
                         ('LBTYK', 'Sunrise Communications', 'SNRE', '2024-11-13'), ('DWDP', 'Dow Inc.', 'DOW', '2019-04-02'),
                         ('IAC', 'Match Group 分离(老 IAC 变成 Match,新 IAC 分出)', 'MTCH', '2020-07-01'), ('IAC', 'Vimeo', 'VMEO', '2021-05-25'),
                         ('CR', 'Crane NXT / Crane Company 分离(CR 代码给了新分出的公司)', 'CXT', '2023-04-04'),
                         ('SITC', 'Curbline Properties', 'CURB', '2024-10-01')]:
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
        if (t1, a1) in CONT_ONE or (sym, t1, a1) in CONT_ONE_SYM: continue
        o = PX.filter((pl.col('ticker') == t1) & (pl.col('d') == a1))
        c = last_close(t0, b0)
        if o.height and c: cont_on[(sym, t1, a1)] = c / float(o['open'][0])

# 分红
D = json.load(gzip.open('/home/claude/stock_data/probe/splits_1101/polygon_dividends_1101.json.gz'))
DV = pl.DataFrame(D['rows'], schema=D['fields'], orient='row', infer_schema_length=None).filter(pl.col('currency').fill_null('USD') == 'USD')
div_on = defaultdict(float)
for t, d, a in DV.select('ticker', 'ex_dividend_date', pl.col('cash_amount').cast(pl.Float64)).iter_rows():
    if a: div_on[(t, d)] += a

# 大额一次性派现(Lin 11-02 同意):≥ 前收 10% 的加系数;下面 5 次 Polygon 没记,按公司公告补(金额、除息日)
SPECIAL_MIN = 0.10
SPECIAL_MISSING = {('MIC', '2021-01-11'): 11.00,        # 出售 IMTT 后的特别分红(businesswire 2020-12-23)
                   ('MIC', '2021-10-08'): 37.386817,    # 出售 Atlantic Aviation 后的分配(businesswire 2021-09-23)
                   ('AABA', '2019-09-24'): 51.50,       # Altaba 解散前清算分配(altaba.com 2019-09-06)
                   ('EQC', '2024-12-09'): 19.00,        # Equity Commonwealth 首次清算分配(businesswire 2024-11-15)
                   ('NLOK', '2020-02-03'): 12.00}       # NortonLifeLock 特别分红(businesswire 2020-01-09)
# HR/HTA 合并那天 4.82 是只发给 HTA 股东的,HTA 那条链的接续系数已经包含;老 HR 股东没拿到 —— 两边都不再加
SPECIAL_SKIP = {('HR', '2022-07-21')}
special_rows = []
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
                v = src.get((sym, t, d)) if src is cont_on else src.get((t, d))
                if v: coef *= v; kinds.append(tag)
            dv = round(div_on.get((t, d), 0.0), 6)
            rows.append({'date': d, 'open': op, 'high': hi, 'low': lo, 'close': cl, 'volume': vo, 'dividend_amount': dv,
                         'split_coefficient': round(coef, 8) if kinds else 1.0, 'price': cl, 'adjusted_close': None, 'source_ticker': t})
            if kinds: events.append({'effective_date': d, 'action_type': '+'.join(kinds), 'split_coefficient': round(coef, 8), 'source_ticker': t})
            if dv: events.append({'effective_date': d, 'action_type': 'dividend', 'cash_amount': dv, 'source_ticker': t})
    rows.sort(key=lambda x: x['date'])
    # 同一天两段重叠(改名当天)只留一根
    ded = {}; [ded.__setitem__(x['date'], x) for x in rows]; rows = [ded[k] for k in sorted(ded)]
    # ── 11-02 Lin 拍板:一次性派现 ≥ 前收 10% 的,按分拆同样处理 —— 系数 = 前收 ÷(前收 − 派现)──
    for a, b in zip(rows, rows[1:]):
        k = (b['source_ticker'], b['date'])
        if k in SPECIAL_SKIP: continue
        amt = SPECIAL_MISSING.get(k)
        if amt is not None:
            b['dividend_amount'] = round(b['dividend_amount'] + amt, 6)
            events.append({'effective_date': b['date'], 'action_type': 'dividend', 'cash_amount': amt, 'source_ticker': b['source_ticker'], 'note': 'Polygon 漏记,按公司公告补'})
        amt = b['dividend_amount']
        pc = a['close']
        if amt and pc and amt / pc >= SPECIAL_MIN and amt < pc:
            c = pc / (pc - amt)
            b['split_coefficient'] = round((b['split_coefficient'] or 1.0) * c, 8)
            events.append({'effective_date': b['date'], 'action_type': 'special_distribution', 'cash_amount': amt, 'prev_close': pc,
                           'coefficient': round(c, 8), 'split_coefficient': b['split_coefficient'], 'source_ticker': b['source_ticker']})
            special_rows.append((sym, b['source_ticker'], b['date'], amt, pc, round(amt / pc, 4), round(c, 6), 'Polygon 漏记' if k in SPECIAL_MISSING else 'Polygon 分红'))
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
pl.DataFrame(special_rows, schema=['symbol', 'ticker', 'ex_date', 'cash_amount', 'prev_close', 'pct_of_prev_close', 'coefficient', 'source'], orient='row').sort('ex_date').write_csv(f'{OUT}/special_distributions_1102.csv')
print('大额派现', len(special_rows))
pl.DataFrame(spin_rows, schema=['parent_ticker', 'spinco', 'spinco_ticker', 'ex_date', 'coefficient'], orient='row').write_csv(f'{OUT}/spinoffs_manual_1102.csv')
print('只数', M.height, '· 退市', M['delisted'].sum(), '· 行数中位', M['bars'].median(), '· 0 行', M.filter(pl.col('bars') == 0).height)
print('拆股事件', sum(1 for k in split_on), '· 分拆', len(spin_on), '· 接续', len(cont_on), cont_on)
