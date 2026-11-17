#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""取数单 11-17 · 技术面考题用:把浏览器拉下来的原始数据(raw_1117.txt.gz)整理成 CSV
只整理数据、不算任何指标或收益。

大白话:
  · 股票(TQQQ SOXL KORU QQQ GLD):Polygon 原生 15 分钟 / 1 小时 / 4 小时 / 日线,adjusted=false(原始价)。
    - 「含盘前盘后」= Polygon 原生 K 线原样(04:00–20:00 美东)。
    - 「常规时段」15 分钟 = 原生 15 分钟里 09:30–16:00 美东那 26 根。
    - 「常规时段_合成」1 小时 / 4 小时 = 用常规时段 15 分钟线从 09:30 起拼:1h 每天 7 根(最后一根 15:30–16:00 只有半小时),
      4h 每天 2 根(09:30–13:30、13:30–16:00)。
    - KORU 2026-07-15 有一次 1 拆 20,所以 KORU 给两套:「拆股折算」(adjusted=true,只折拆股)和「原始价」。
  · 币(BTC ETH):Polygon 这条通道只放行股票和期权(X:BTCUSD 返回 403),改用 Coinbase 公开K线 BTC-USD / ETH-USD。
    Coinbase 没有 4 小时线 → 用 1 小时线按 UTC 00/04/08/12/16/20 点拼,文件名标「合成」。
  · 时间一律 UTC,写成 2026-06-01T13:30:00Z,是每根 K 线的开始时间。
  · 只放完整的 K 线:股票截到美东 2026-11-16 盘后结束;币截到取数时刻之前最后一根已经收完的。
用法:python3 build_tech_exam.py raw_1117.txt.gz ../../market_tech_exam_1117
"""
import csv, gzip, json, os, sys
from collections import defaultdict, Counter
from datetime import datetime, timezone, timedelta, time
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
UTC = timezone.utc
STOCK_LAST_DAY = '2026-11-16'


def load(fp):
    S, k, splits = {}, None, None
    for l in gzip.open(fp, 'rt'):
        l = l.rstrip('\n')
        if l.startswith('#SPLITS '): splits = json.loads(l[8:]); continue
        if l.startswith('#'): k = l[1:]; S[k] = []; continue
        S[k].append(l.split(','))
    return S, splits


def num(x):
    f = float(x)
    return int(f) if f == int(f) and abs(f) < 1e15 else f


def iso(ts):
    return datetime.fromtimestamp(ts, UTC).strftime('%Y-%m-%dT%H:%M:%SZ')


def poly_rows(rows):  # Polygon: t(sec), o, h, l, c, v, n
    out = []
    for r in rows:
        t = float(r[0])
        if datetime.fromtimestamp(t, ET).strftime('%Y-%m-%d') > STOCK_LAST_DAY: continue
        out.append({'t': t, 'o': num(r[1]), 'h': num(r[2]), 'l': num(r[3]), 'c': num(r[4]), 'v': num(r[5])})
    return out


def cb_rows(rows, cutoff, span):  # Coinbase: time, low, high, open, close, volume
    out = []
    for r in rows:
        t = float(r[0])
        if t + span > cutoff: continue
        out.append({'t': t, 'o': num(r[3]), 'h': num(r[2]), 'l': num(r[1]), 'c': num(r[4]), 'v': num(r[5])})
    return sorted(out, key=lambda b: b['t'])


def regular15(bars):
    return [b for b in bars if time(9, 30) <= datetime.fromtimestamp(b['t'], ET).time() < time(16, 0)]


def agg(bars, keyf):
    g = defaultdict(list)
    for b in bars: g[keyf(b)].append(b)
    out = []
    for k in sorted(g):
        bs = sorted(g[k], key=lambda b: b['t'])
        out.append({'t': k, 'o': bs[0]['o'], 'h': max(b['h'] for b in bs), 'l': min(b['l'] for b in bs), 'c': bs[-1]['c'],
                    'v': round(sum(b['v'] for b in bs), 8), 'n15': len(bs)})
    return out


def reg_key(minutes):
    def f(b):
        d = datetime.fromtimestamp(b['t'], ET)
        o = datetime.combine(d.date(), time(9, 30), ET)
        k = int((d - o).total_seconds() // 60) // minutes
        return (o + timedelta(minutes=k * minutes)).timestamp()
    return f


def utc_key(sec):
    return lambda b: b['t'] // sec * sec


def write(path, bars):
    with open(path, 'w', newline='') as fh:
        w = csv.writer(fh); w.writerow(['time', 'open', 'high', 'low', 'close', 'volume'])
        for b in bars: w.writerow([iso(b['t']), b['o'], b['h'], b['l'], b['c'], b['v']])
    return {'file': os.path.basename(path), 'rows': len(bars), 'start': iso(bars[0]['t']), 'end': iso(bars[-1]['t'])}


def main(raw, out):
    os.makedirs(out, exist_ok=True)
    S, splits = load(raw)
    man, checks = [], []
    for sym in ['TQQQ', 'SOXL', 'KORU', 'QQQ', 'GLD']:
        variants = [('', '')] if sym != 'KORU' else [('_adj', '_拆股折算'), ('', '_原始价')]
        for kv, suf in variants:
            m15 = poly_rows(S[f'{sym}_15minute{kv}'])
            h1 = poly_rows(S[f'{sym}_1hour{kv}']); h4 = poly_rows(S[f'{sym}_4hour{kv}']); d1 = poly_rows(S[f'{sym}_1day{kv}'])
            r15 = regular15(m15)
            r1 = agg(r15, reg_key(60)); r4 = agg(r15, reg_key(240))
            files = []
            if sym in ('TQQQ', 'SOXL', 'KORU'):
                files += [(f'{sym}_15min_含盘前盘后{suf}.csv', m15, '原生'), (f'{sym}_15min_常规时段{suf}.csv', r15, '原生(筛 09:30–16:00)')]
            files += [(f'{sym}_1h_含盘前盘后{suf}.csv', h1, '原生'), (f'{sym}_1h_常规时段_合成{suf}.csv', r1, '15 分钟线从 09:30 起拼'),
                      (f'{sym}_4h_含盘前盘后{suf}.csv', h4, '原生(按 UTC 0/4/8/12/16/20 点切)'), (f'{sym}_4h_常规时段_合成{suf}.csv', r4, '15 分钟线从 09:30 起拼'),
                      (f'{sym}_日线{suf}.csv', d1, '原生')]
            for fn, bars, how in files:
                m = write(os.path.join(out, fn), bars); m.update(symbol=sym, source='Polygon', how=how,
                                                                adjust='拆股折算(adjusted=true)' if kv else '原始价(adjusted=false)'); man.append(m)
            # 自检:常规 15 分钟每天 26 根;合成 1h 的最高/最低 = 日线最高/最低(日线最高最低就是常规时段的)
            per_day = Counter(datetime.fromtimestamp(b['t'], ET).date().isoformat() for b in r15)
            short = {d: n for d, n in per_day.items() if n != 26}
            dd = {datetime.fromtimestamp(b['t'], ET).date().isoformat(): b for b in d1}
            hl = defaultdict(lambda: [-1e18, 1e18])
            for b in r1:
                d = datetime.fromtimestamp(b['t'], ET).date().isoformat(); hl[d][0] = max(hl[d][0], b['h']); hl[d][1] = min(hl[d][1], b['l'])
            mism = [d for d in dd if d in hl and (abs(hl[d][0] - dd[d]['h']) > 1e-6 or abs(hl[d][1] - dd[d]['l']) > 1e-6)]
            checks.append({'symbol': sym + suf, 'trading_days_daily': len(d1), 'days_with_regular_15m': len(per_day),
                           'days_not_26_regular_15m': short, 'days_regular_high_low_differs_from_daily': mism})
    # 币
    cut = max(float(r[0]) for r in S['CB_BTC-USD_900'] + S['CB_ETH-USD_900'])  # 最后一根 15 分钟(还没收完)的开始 = 取数时刻附近
    for p, sym in [('BTC-USD', 'BTC'), ('ETH-USD', 'ETH')]:
        m15 = cb_rows(S[f'CB_{p}_900'], cut, 900); h1 = cb_rows(S[f'CB_{p}_3600'], cut, 3600); d1 = cb_rows(S[f'CB_{p}_86400'], cut, 86400)
        h4 = [b for b in agg(h1, utc_key(14400)) if b['t'] + 14400 <= cut]
        for fn, bars, how in [(f'{sym}_15min.csv', m15, '原生'), (f'{sym}_1h.csv', h1, '原生'), (f'{sym}_4h_合成.csv', h4, '1 小时线按 UTC 0/4/8/12/16/20 点拼'),
                              (f'{sym}_日线.csv', d1, '原生(UTC 00:00 切日)')]:
            m = write(os.path.join(out, fn), bars); m.update(symbol=sym, source=f'Coinbase {p}', how=how, adjust='—'); man.append(m)
        gaps = {}
        for fn, bars, sp in [('15min', m15, 900), ('1h', h1, 3600), ('日线', d1, 86400)]:
            exp = int((bars[-1]['t'] - bars[0]['t']) // sp) + 1
            gaps[fn] = {'expected': exp, 'got': len(bars), 'missing': exp - len(bars)}
        gaps['4h_bars_with_<4_hours'] = sum(1 for b in h4 if b['n15'] < 4)
        checks.append({'symbol': sym, 'continuity': gaps})
    with open(os.path.join(out, 'manifest.csv'), 'w', newline='') as fh:
        w = csv.DictWriter(fh, fieldnames=['file', 'symbol', 'source', 'how', 'adjust', 'start', 'end', 'rows']); w.writeheader()
        for m in man: w.writerow({k: m[k] for k in w.fieldnames})
    json.dump({'checks': checks, 'splits_in_window': splits, 'crypto_cutoff_utc': iso(cut)}, open(os.path.join(out, 'checks.json'), 'w'), ensure_ascii=False, indent=1)
    for m in man: print(f"{m['file']:<34} {m['start']} ~ {m['end']}  {m['rows']}")
    print(json.dumps(checks, ensure_ascii=False))


if __name__ == '__main__':
    main(*sys.argv[1:])
