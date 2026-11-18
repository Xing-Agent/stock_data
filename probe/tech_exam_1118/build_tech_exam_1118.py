#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""取数单第二批 11-18:把浏览器拉下来的原始数据(raw_1118.json.gz)整理成 CSV,只整理、不算指标。
时间一律 UTC(ISO,结尾 Z),是这根 K 线 / 这次结算的时间。
用法:python3 build_tech_exam_1118.py raw_1118.json.gz ../../market_tech_exam_1118"""
import csv, gzip, json, os, sys
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta, time
from zoneinfo import ZoneInfo
ET = ZoneInfo('America/New_York'); UTC = timezone.utc


def iso(ms):
    return datetime.fromtimestamp(ms / 1000, UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


def num(x):
    f = float(x)
    return int(f) if f == int(f) and abs(f) < 1e15 else f


def write(out, fn, header, rows, meta, man):
    with open(os.path.join(out, fn), 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(header); w.writerows(rows)
    man.append(dict(file=fn, rows=len(rows), start=rows[0][0] if rows else '', end=rows[-1][0] if rows else '', **meta))


def agg(bars, keyf):
    g = defaultdict(list)
    for b in bars: g[keyf(b)].append(b)
    out = []
    for k in sorted(g):
        bs = sorted(g[k]); out.append([k, bs[0][1], max(b[2] for b in bs), min(b[3] for b in bs), bs[-1][4], round(sum(b[5] for b in bs), 8), len(bs)])
    return out


def main(raw, out):
    os.makedirs(out, exist_ok=True)
    J = json.load(gzip.open(raw)); D = J['data']
    cut = datetime.fromisoformat(J['retrieved_at'].replace('Z', '+00:00')).timestamp() * 1000
    man, checks = [], {}
    # ① 资金费率
    for s, sym in [('BTCUSDT', 'BTC'), ('ETHUSDT', 'ETH')]:
        rows = sorted({int(t): (iso(int(t)), num(r), num(m) if m not in ('', None) else '') for t, r, m in D[f'binance_funding_{s}']}.items())
        write(out, f'{sym}_资金费率_Binance.csv', ['time', 'funding_rate', 'mark_price'], [v for _, v in rows],
              dict(source=f'Binance USDT 永续 {s} /fapi/v1/fundingRate', note='每 8 小时结算一次;funding_rate 是这次结算的费率(0.0001 = 0.01%)'), man)
        gaps = Counter(round((rows[i][0] - rows[i-1][0]) / 3600e3) for i in range(1, len(rows)))
        checks[f'{sym}_资金费率_Binance 间隔(小时:次数)'] = dict(gaps)
        rows = sorted({int(t): (iso(int(t)), num(r)) for t, r in D[f'bybit_funding_{s}']}.items())
        write(out, f'{sym}_资金费率_Bybit.csv', ['time', 'funding_rate'], [v for _, v in rows],
              dict(source=f'Bybit USDT 永续 {s} /v5/market/funding/history', note='每 8 小时结算一次'), man)
        checks[f'{sym}_资金费率_Bybit 间隔'] = dict(Counter(round((rows[i][0] - rows[i-1][0]) / 3600e3) for i in range(1, len(rows))))
    # ② 持仓量
    for s, sym in [('BTCUSDT', 'BTC'), ('ETHUSDT', 'ETH')]:
        rows = sorted({int(t): (iso(int(t)), num(v)) for t, v in D[f'bybit_oi1h_{s}'] if int(t) >= 1672531200000}.items())
        write(out, f'{sym}_持仓量_1h_Bybit.csv', ['time', 'open_interest'], [v for _, v in rows],
              dict(source=f'Bybit USDT 永续 {s} /v5/market/open-interest intervalTime=1h', note=f'整点快照;单位是 {sym} 个数(不是美元)'), man)
        checks[f'{sym}_持仓量 间隔'] = dict(Counter(round((rows[i][0] - rows[i-1][0]) / 3600e3) for i in range(1, len(rows))))
    # ③ 长历史:Coinbase 日线(原生)、周线(Binance 原生 + 用 Coinbase 日线合成)
    for p, sym in [('BTC-USD', 'BTC'), ('ETH-USD', 'ETH')]:
        d = {int(r[0]) * 1000: [int(r[0]) * 1000, num(r[3]), num(r[2]), num(r[1]), num(r[4]), num(r[5])] for r in D[f'cb_1d_{p}']}
        days = [d[k] for k in sorted(d) if k + 86400e3 <= cut]
        write(out, f'{sym}_日线_Coinbase.csv', ['time', 'open', 'high', 'low', 'close', 'volume'], [[iso(b[0])] + b[1:] for b in days],
              dict(source=f'Coinbase {p}', note='UTC 00:00 切日;volume 单位是币'), man)
        exp = (days[-1][0] - days[0][0]) / 86400e3 + 1; checks[f'{sym}_日线 缺天'] = int(exp - len(days))
        wk = agg([b for b in days], lambda b: int((b[0] - (datetime.fromtimestamp(b[0] / 1000, UTC).weekday()) * 86400e3)))
        wk = [w for w in wk if w[0] + 7 * 86400e3 <= cut and w[6] == 7]
        write(out, f'{sym}_周线_合成_Coinbase.csv', ['time', 'open', 'high', 'low', 'close', 'volume'], [[iso(w[0])] + w[1:6] for w in wk],
              dict(source=f'Coinbase {p} 日线合成', note='周一 UTC 00:00 起算,7 根日线拼一根;2017-01-01 那周不满 7 天,已去掉,从 2017-01-02 那周开始'), man)
        checks[f'{sym}_周线合成 不足7天的周'] = sum(1 for w in wk if w[6] != 7)
        s = 'BTCUSDT' if sym == 'BTC' else 'ETHUSDT'
        bw = [[int(r[0]), num(r[1]), num(r[2]), num(r[3]), num(r[4]), num(r[5])] for r in D[f'bn_1w_{s}']]
        bw = [b for b in bw if b[0] + 7 * 86400e3 <= cut]
        write(out, f'{sym}_周线_Binance.csv', ['time', 'open', 'high', 'low', 'close', 'volume'], [[iso(b[0])] + b[1:] for b in bw],
              dict(source=f'Binance 现货 {s} 原生周线', note='周一 UTC 00:00 起;币安 2017-08-17 才上线,所以从 2017-08-14 那周开始;计价是 USDT'), man)
    # ④ 板块 ETF
    etfs = ['XLK', 'SMH', 'SOXX', 'XLF', 'XLE', 'XLV', 'XLY', 'XLI', 'XLC', 'XLU', 'XLB', 'XLRE', 'XLP', 'IGV']
    split_note = {}
    for t in etfs:
        sp = D[f'etf_splits_{t}']
        split_note[t] = sp
        for adj, suf, note in [('true', '_拆股折算', '只折拆股、不折分红(adjusted=true)'), ('false', '_原始价', '原始成交价')]:
            if adj == 'false' and not sp: continue
            rows = [[datetime.fromtimestamp(b[0] / 1000, ET).strftime('%Y-%m-%d'), num(b[1]), num(b[2]), num(b[3]), num(b[4]), num(b[5])] for b in D[f'etf_{t}_{adj}']]
            fn = f'{t}_日线{suf if sp else ""}.csv'
            write(out, fn, ['date', 'open', 'high', 'low', 'close', 'volume'], rows,
                  dict(source=f'Polygon {t} 日线', note=('无拆股,原始价 = 折算价' if not sp else note + ';期间拆股:' + ', '.join(f'{a} {f:g}→{to:g}' for a, f, to in sp))), man)
    # ⑤ 美股往后补(2026-11-17 起)
    for t in ['TQQQ', 'SOXL', 'KORU', 'QQQ', 'GLD']:
        def ext(rows):
            return [r for r in rows if r[0] + 0 <= cut and time(4, 0) <= datetime.fromtimestamp(r[0] / 1000, ET).time() < time(20, 0)]
        m15 = [[r[0]] + [num(x) for x in r[1:]] for r in D[f'stk_{t}_15minute']]
        h1 = [[r[0]] + [num(x) for x in r[1:]] for r in D[f'stk_{t}_1hour']]
        h4 = [[r[0]] + [num(x) for x in r[1:]] for r in D[f'stk_{t}_4hour']]
        m15 = [r for r in m15 if r[0] + 900e3 <= cut]; h1 = [r for r in h1 if r[0] + 3600e3 <= cut]; h4 = [r for r in h4 if r[0] + 4 * 3600e3 <= cut]
        reg = [r for r in m15 if time(9, 30) <= datetime.fromtimestamp(r[0] / 1000, ET).time() < time(16, 0)]
        def rk(minutes):
            def f(b):
                dt = datetime.fromtimestamp(b[0] / 1000, ET); o = datetime.combine(dt.date(), time(9, 30), ET)
                return int((o + timedelta(minutes=((dt - o).seconds // 60) // minutes * minutes)).timestamp() * 1000)
            return f
        r1 = agg(reg, rk(60)); r4 = agg(reg, rk(240))
        files = []
        if t in ('TQQQ', 'SOXL', 'KORU'):
            files += [(f'{t}_15min_含盘前盘后_补1117起.csv', ext(m15), '原生,04:00–20:00 美东'), (f'{t}_15min_常规时段_补1117起.csv', reg, '原生,筛 09:30–16:00')]
        files += [(f'{t}_1h_含盘前盘后_补1117起.csv', ext(h1), '原生,04:00–20:00 美东'), (f'{t}_1h_常规时段_合成_补1117起.csv', [x[:6] for x in r1], '15 分钟线从 09:30 起拼'),
                  (f'{t}_4h_含盘前盘后_补1117起.csv', h4, '原生;这批按美东 00/04/08/12/16/20 点切(冬令时),和 1117 那批切点不同,见 README'), (f'{t}_4h_常规时段_合成_补1117起.csv', [x[:6] for x in r4], '15 分钟线从 09:30 起拼')]
        for fn, bars, how in files:
            write(out, fn, ['time', 'open', 'high', 'low', 'close', 'volume'], [[iso(b[0])] + list(b[1:6]) for b in bars],
                  dict(source=f'Polygon {t}', note=how + ';原始价'), man)
        checks[f'{t} 11-17 常规时段 15 分钟根数'] = Counter(datetime.fromtimestamp(r[0] / 1000, ET).date().isoformat() for r in reg)
    # ⑥ 币往后补
    for p, sym in [('BTC-USD', 'BTC'), ('ETH-USD', 'ETH')]:
        for g, lab in [(900, '15min'), (3600, '1h')]:
            d = {int(r[0]) * 1000: [int(r[0]) * 1000, num(r[3]), num(r[2]), num(r[1]), num(r[4]), num(r[5])] for r in D[f'cb_{g}_{p}']}
            bars = [d[k] for k in sorted(d) if k + g * 1000 <= cut]
            write(out, f'{sym}_{lab}_补1117起.csv', ['time', 'open', 'high', 'low', 'close', 'volume'], [[iso(b[0])] + b[1:] for b in bars],
                  dict(source=f'Coinbase {p}', note='接在 market_tech_exam_1117 后面(那边截到 11-17 07:30Z,这里从 11-17 00:00Z 起,有重叠方便核对)'), man)
            checks[f'{sym}_{lab}_补 缺根'] = int((bars[-1][0] - bars[0][0]) / (g * 1000) + 1 - len(bars))
    with open(os.path.join(out, 'manifest.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['file', 'source', 'start', 'end', 'rows', 'note']); w.writeheader()
        for m in man: w.writerow({k: m[k] for k in w.fieldnames})
    json.dump({'retrieved_at': J['retrieved_at'], 'checks': checks, 'etf_splits_since_2018': split_note}, open(os.path.join(out, 'checks.json'), 'w'), ensure_ascii=False, indent=1, default=str)
    for m in man: print(f"{m['file']:<34} {m['start']} ~ {m['end']}  {m['rows']}")
    print(json.dumps(checks, ensure_ascii=False, default=str)[:3000])


if __name__ == '__main__':
    main(*sys.argv[1:])
