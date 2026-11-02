# -*- coding: utf-8 -*-
"""分拆事件(人工确认):母公司当时的代码 + 分出来的公司 + 分出公司第一天交易日。
系数 = 母公司除权前一天收盘 ÷ 除权当天开盘(和 Alpha Vantage 记分拆的口径一样),写进 split_coefficient。"""
import polars as pl, json
EV = [  # (母公司当时代码, 分拆出的公司, 分出公司代码)
 ('GRA','GCP Applied Technologies','GCP'),('MTW','Manitowoc Foodservice','MFS'),('WRK','Ingevity','NGVT'),
 ('APD','Versum Materials','VSM'),('RRD','Donnelley Financial + LSC','DFIN'),('HON','AdvanSix','ASIX'),
 ('JCI','Adient','ADNT'),('HCP','Quality Care Properties','QCP'),('XRX','Conduent','CNDT'),('VAR','Varex Imaging','VREX'),
 ('VNO','JBG Smith','JBGS'),('PNR','nVent','NVT'),('DOV','Apergy','APY'),('WYN','Wyndham Hotels','WH'),('SRC','Spirit MTA REIT','SMTA'),
 ('HON','Garrett Motion','GTX'),('HON','Resideo','REZI'),('SERV','frontdoor','FTDR'),('TRN','Arcosa','ACA'),('EQT','Equitrans Midstream','ETRN'),
 ('VFC','Kontoor Brands','KTB'),('KAR','IAA','IAA'),('UTX','Otis + Carrier','CARR'),('AIV','Apartment Income REIT','AIRC'),('MRK','Organon','OGN'),
 ('XPO','GXO Logistics','GXO'),('IP','Sylvamo','SLVM'),('JCOM','Consensus Cloud','CCSI'),('IBM','Kyndryl','KD'),('BLUE','2seventy bio','TSVT'),
 ('ADS','Loyalty Ventures','LYLT'),('CFX','ESAB','ESAB'),('XPO','RXO','RXO'),('FBHS','MasterBrand','MBC'),('GE','GE HealthCare','GEHC'),
 ('MDU','Knife River','KNF'),('LH','Fortrea','FTRE'),('K','WK Kellogg','KLG'),('ARMK','Vestis','VSTS'),('WPC','Net Lease Office Properties','NLOP'),
 ('ALKS','Mural Oncology','MURA'),('MMM','Solventum','SOLV'),('GE','GE Vernova','GEV'),('MDU','Everus Construction','ECG'),('HON','Solstice Advanced Materials','SOLS'),
 ('JEC','Amentum','AMTM'),('HLS','Enhabit','EHAB'),('T','Warner Bros. Discovery(AT&T 股东分到)','WBD'),('PFE','Viatris(Upjohn)','VTRS'),
 ('DWDP','Dow Inc','DOW'),('DWDP','Corteva','CTVA'),('AA','Alcoa Corp(新)','AA'),('ARNC','Arconic Corp(新)','ARNC'),
 ('BAX','Baxalta','BXLT'),('ITT','—',''),('ABT','—',''),('SNI','—',''),('CSC','CSRA','CSRA'),('DISCA','—',''),('FNF','—',''),
]
EV = [e for e in EV if e[2]]
px = pl.read_parquet('/home/claude/splits/px_2015.parquet').sort('ticker', 'd').with_columns(pl.col('close').shift(1).over('ticker').alias('pc'))
cal = sorted(px['d'].unique().to_list()); ci = {d: i for i, d in enumerate(cal)}
first = px.group_by('ticker').agg(pl.col('d').min().alias('f'))
fmap = dict(first.iter_rows())
# 新代码在旧代码之前就有(比如 AA、ARNC、DOW 代码被复用)→ 手工给日期
manual_date = {'AA': '2016-11-01', 'ARNC': '2020-04-01', 'DOW': '2019-04-02', 'CTVA': '2019-06-03', 'WBD': '2022-04-11', 'VTRS': '2020-11-16', 'CARR': '2020-04-03', 'CSRA': '2015-11-30', 'BXLT': '2015-07-01'}
out = []
for par, name, sp in EV:
    d0 = manual_date.get(sp) or fmap.get(sp)
    if not d0 or d0 < '2016-01-01':
        out.append((par, name, sp, d0, None, None, None, '早于 2016 或找不到分出公司')); continue
    i0 = ci.get(d0) or min(range(len(cal)), key=lambda k: abs(ord(cal[k][0]) - ord(d0[0])))
    win = cal[max(0, ci[d0] - 2): ci[d0] + 2] if d0 in ci else []
    g = px.filter((pl.col('ticker') == par) & pl.col('d').is_in(win)).with_columns((pl.col('open') / pl.col('pc')).alias('gap')).sort('gap')
    if g.height == 0:
        out.append((par, name, sp, d0, None, None, None, '母公司那几天没有行情')); continue
    r = g.row(0, named=True)
    out.append((par, name, sp, d0, r['d'], r['pc'] / r['open'], r['gap'], ''))
T = pl.DataFrame(out, schema=['parent_ticker', 'spinco', 'spinco_ticker', 'spinco_first', 'ex_date', 'coefficient', 'gap', 'note'], orient='row')
T.write_csv('spin_events_1101.csv')
pl.Config.set_tbl_rows(80)
print(T.select('parent_ticker', 'spinco_ticker', 'ex_date', pl.col('coefficient').round(3), pl.col('gap').round(3), 'note'))
