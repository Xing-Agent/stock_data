#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""取数单第三批 11-19:杠杆 ETF 长历史 + NQ/ES 1 小时 + 股票永续合约清单与 1 小时线。只整理,不算指标。
用法:python3 build_tech_exam_1119.py tech_exam_raw_1119.json.gz yahoo_nq_es_1h_1119.json ../../market_tech_exam_1119"""
import csv, gzip, json, os, sys
from collections import Counter
from datetime import datetime, timezone
from zoneinfo import ZoneInfo
ET = ZoneInfo('America/New_York'); UTC = timezone.utc
R = '/home/claude/stock_data'


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


def num(x):
    f = float(x)
    return int(f) if f == int(f) and abs(f) < 1e15 else f


def main(raw, yahoo, out):
    os.makedirs(out, exist_ok=True)
    J = json.load(gzip.open(raw)); D = J['data']; cut = datetime.fromisoformat(J['retrieved_at'].replace('Z', '+00:00')).timestamp() * 1000
    spy = [x['date'] for x in json.load(gzip.open(f'{R}/market_etf_1106/SPY/daily.json.gz'))['data']]
    man, checks = [], {}

    def write(fn, rows, meta):
        with open(os.path.join(out, fn), 'w', newline='') as fh:
            w = csv.writer(fh); w.writerow(['time', 'open', 'high', 'low', 'close', 'volume']); w.writerows(rows)
        man.append(dict(file=fn, rows=len(rows), start=rows[0][0] if rows else '', end=rows[-1][0] if rows else '', **meta))

    # ── 股票 / ETF(Polygon)
    for t in ['SOXL', 'TQQQ', 'KORU', 'QQQ', 'SOXX']:
        sp = D['splits_' + t]
        spn = ';'.join(f'{a} {f:g}→{to:g}' for a, f, to in sp) or '无'
        for adj, suf in [('true', '拆股折算'), ('false', '原始价')]:
            if adj == 'false' and t != 'KORU': continue
            d = [b for b in D[f'{t}_1d_{adj}'] if b[0] + 86400e3 <= cut]
            src = f'Polygon {t} 日线'
            if t == 'QQQ':  # 2011-03-23 以前代码是 QQQQ:用研究库 market_etf_1106/QQQ(已接好 QQQQ)补 2010-01-04 ~ 2011-03-22
                old = json.load(gzip.open(f'{R}/market_etf_1106/QQQ/daily.json.gz'))['data']
                first = datetime.fromtimestamp(d[0][0] / 1000, ET).date().isoformat()
                pre = [[int(datetime.fromisoformat(x['date']).replace(tzinfo=ET).timestamp() * 1000), x['open'], x['high'], x['low'], x['close'], x['volume']]
                       for x in old if '2010-01-01' <= x['date'] < first]
                d = pre + d; src += f';{first} 以前代码是 QQQQ,取自研究库 market_etf_1106/QQQ(同一只基金,只是换了代码)'
            rows = [[iso(b[0])] + [num(x) for x in b[1:6]] for b in d]
            write(f'{t}_日线_{suf}.csv', rows, dict(source=src, note=f'time = 美东交易日 00:00 换成 UTC;{"拆股并股都已折算(Polygon adjusted=true),不折分红" if adj == "true" else "原始成交价"};期间拆股:{spn}'))
            if adj == 'true':
                days = [datetime.fromtimestamp(b[0] / 1000, ET).date().isoformat() for b in d]
                cal = [x for x in spy if days[0] <= x <= spy[-1]]
                miss = sorted(set(cal) - set(days))
                big = [(days[i], round(d[i][4] / d[i-1][4], 3)) for i in range(1, len(d)) if not 0.5 < d[i][4] / d[i-1][4] < 1.6]
                checks[f'{t}_日线'] = dict(first=days[0], 缺的交易日=len(miss), 缺的例子=miss[:10], 折算后单日涨跌超出_50pct到60pct=big)
            h = [b for b in D[f'{t}_1h_{adj}'] if b[0] + 3600e3 <= cut]
            rows = [[iso(b[0])] + [num(x) for x in b[1:6]] for b in h]
            write(f'{t}_1h_含盘前盘后_{suf}.csv', rows, dict(source=f'Polygon {t} 小时线(原生,整点切)',
                  note=f'含盘前盘后(04:00–20:00 美东);整点切,所以 09:00 那根混了盘前半小时;{"已折拆股" if adj == "true" else "原始价"};没成交的小时没有K线'))
            if adj == 'true':
                per = Counter(datetime.fromtimestamp(b[0] / 1000, ET).date().isoformat() for b in h)
                reg_miss = [dd for dd in spy if dd >= '2020-01-02' and dd <= spy[-1] and dd not in per]
                checks[f'{t}_1h'] = dict(有K线的交易日=len(per), 缺整天=len(reg_miss), 缺整天例子=reg_miss[:10], 每天根数分布=dict(Counter(per.values()).most_common(6)))
    # ── NQ / ES(Yahoo)
    Y = json.load(open(yahoo))
    for k, name in [('NQ', '纳指期货'), ('ES', '标普期货')]:
        y = Y[k]; rows = []
        for i, t in enumerate(y['t']):
            if None in (y['o'][i], y['h'][i], y['l'][i], y['c'][i]): continue
            if t * 1000 + 3600e3 > datetime.fromisoformat(Y['retrieved_at'].replace('Z', '+00:00')).timestamp() * 1000: continue
            rows.append([iso(t * 1000), num(y['o'][i]), num(y['h'][i]), num(y['l'][i]), num(y['c'][i]), num(y['v'][i] or 0)])
        write(f'{k}_1h_连续合约_Yahoo.csv', rows, dict(source=f'Yahoo Finance {k}=F(CME {name}主力连续)',
              note='主力合约连续(到期自动换月,换月处不做价差调整,会有小跳);Yahoo 小时线最多给最近 730 天,2020-01 ~ 2024-11 取不到'))
        checks[f'{k}_1h'] = dict(rows=len(rows))
    # ── 股票永续合约(Binance 全历史 1h;Hyperliquid 只给最近 5000 根)
    for s in ['NVDA', 'QQQ', 'SOXL', 'KORU', 'TQQQ', 'SPY', 'SMH', 'EWY', 'SOXX']:
        a = [r for r in D['perp_binance_' + s] if r[0] + 3600e3 <= cut]
        if not a: continue
        rows = [[iso(r[0])] + [num(x) for x in r[1:6]] for r in a]
        write(f'永续_{s}_1h_Binance.csv', rows, dict(source=f'Binance U 本位永续 {s}USDT /fapi/v1/klines 1h',
              note='7×24 小时交易(美股休市、周末也在交易);价格跟踪对应股票/ETF;volume 单位是合约张数=股数'))
        checks[f'永续_{s}_Binance'] = dict(rows=len(rows), 缺根=int((a[-1][0] - a[0][0]) / 3600e3 + 1 - len(a)))
    for c in ['xyz:XYZ100', 'xyz:SP500', 'xyz:NVDA', 'xyz:SOXL', 'xyz:KORU']:
        a = [r for r in D['perp_hl_' + c] if r[0] + 3600e3 <= cut]
        rows = [[iso(r[0])] + [num(x) for x in r[1:6]] for r in a]
        nm = c.split(':')[1]
        write(f'永续_{nm}_1h_Hyperliquid.csv', rows, dict(source=f'Hyperliquid trade.xyz 市场 {c} candleSnapshot 1h',
              note='7×24 小时;Hyperliquid 接口只给最近约 5000 根,更早的取不到' + (';XYZ100 跟踪纳斯达克 100 指数' if nm == 'XYZ100' else ';SP500 跟踪标普 500 指数' if nm == 'SP500' else '')))
    with open(os.path.join(out, 'manifest.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['file', 'source', 'start', 'end', 'rows', 'note']); w.writeheader()
        for m in man: w.writerow({k: m[k] for k in w.fieldnames})
    json.dump(dict(retrieved_at=J['retrieved_at'], checks=checks), open(os.path.join(out, 'checks.json'), 'w'), ensure_ascii=False, indent=1)
    # 永续合约清单
    PM = D['perp_meta']; T = {'NVDA', 'QQQ', 'TQQQ', 'SOXL', 'KORU', 'SPY', 'SMH', 'SOXX', 'EWY', 'US100', 'US500', 'XYZ100', 'SP500'}
    lst = []
    for r in PM['binance']:
        b = r[0].replace('USDT', '')
        if b in T and r[3] == 'EQUITY': lst.append(['Binance', r[0], b, r[2], '能:从上线起全部 1 小时线(本目录已取)'])
    for r in PM['bybit']:
        b = r[0].replace('USDT', '')
        if b in T: lst.append(['Bybit', r[0], b, r[2], '应该能(接口支持按时间分页;这次没取,Binance 已覆盖)'])
    for r in PM['okx']:
        b = r[0].replace('-USDT-SWAP', '')
        if b in T: lst.append(['OKX', r[0], b, r[1], '应该能(history-candles 接口分页;这次没取,也没逐只验证)'])
    for n in PM['hl_xyz']:
        b = n.split(':')[1]
        if b in T: lst.append(['Hyperliquid(trade.xyz)', n, b, '', '只能拿最近约 5000 根(约 7 个月)' + (',本目录已取' if b in ('XYZ100', 'SP500', 'NVDA', 'SOXL', 'KORU') else ',这次没取')])
    lst.sort(key=lambda x: (x[2], x[3] or '9'))
    with open(os.path.join(out, '股票永续合约清单_1119.csv'), 'w', newline='', encoding='utf-8-sig') as fh:
        w = csv.writer(fh); w.writerow(['交易所', '合约代码', '对应标的', '上线日(交易所给的)', '能不能拿 1 小时历史']); w.writerows(lst)
    for m in man: print(f"{m['file']:<36} {m['start']} ~ {m['end']}  {m['rows']}")
    print(json.dumps(checks, ensure_ascii=False)[:2500])
    for x in lst: print(x)


if __name__ == '__main__':
    main(*sys.argv[1:])
