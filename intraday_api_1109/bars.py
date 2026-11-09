#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 145 · 任意周期按需取数接口(只取数,不回测)

一句话:get_bars("NVDA", "15min", "2026-10-26", "2026-11-06") → 这一段 K 线 + 四样口径说明。

大白话:
  · 只向数据源要两种东西:1 分钟线、日线。15 分钟、1 小时、4 小时……都是我们自己用 1 分钟线拼出来的。
    原因:数据源自带的小时线是按整点切的(09:00–10:00 那根把盘前 30 分钟和开盘 30 分钟混在一起),
    我们按开盘 09:30 起切(09:30–10:30、10:30–11:30……15:30–16:00),一根里不会混盘前。
  · 日线直接用数据源的日线:开盘 / 收盘是交易所官方的开盘价、收盘价(收盘竞价),和拿 1 分钟线拼出来的会差几分钱,
    成交量也比盘中加起来大(日线含盘前盘后和收盘竞价)—— 这两点都写在 meta 里。
  · 时间:一律美东时间(America/New_York),带时区写出来;每根 K 线是左闭右开 [开始, 结束)。
  · 价格:默认原始价(raw),拆股前后价位会跳;要拆股折算的传 adjust="split"(数据源的 adjusted=true,只折拆股,不折分红)。

数据源配置(钥匙不进代码、不进仓库):
  环境变量 BARS_BASE_URL(Polygon 兼容的 REST 地址)和 BARS_API_KEY。
  ⚠ 现在手上的那个转售通道只许内部研究用,不能接产品 —— 产品上线要换成正式授权的数据源,接口不用改,换这两个环境变量就行。
"""
import json, os, urllib.parse, urllib.request
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo

ET = ZoneInfo('America/New_York')
INTERVALS = {'1min': 1, '5min': 5, '15min': 15, '30min': 30, '1h': 60, '2h': 120, '4h': 240, '1d': None}
SESSIONS = {'regular': (time(9, 30), time(16, 0)), 'extended': (time(4, 0), time(20, 0))}


def _get(path, params):
    base = os.environ['BARS_BASE_URL'].rstrip('/')
    url = f"{base}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={'X-API-KEY': os.environ['BARS_API_KEY']})
    out = []
    while url:
        with urllib.request.urlopen(req, timeout=60) as r:
            j = json.loads(r.read())
        out += j.get('results') or []
        nxt = j.get('next_url')
        if not nxt: break
        url = base + urllib.parse.urlparse(nxt).path + '?' + urllib.parse.urlparse(nxt).query
        req = urllib.request.Request(url, headers={'X-API-KEY': os.environ['BARS_API_KEY']})
    return out


def _fetch(symbol, mult, span, start, end, adjust):
    return _get(f'/v2/aggs/ticker/{urllib.parse.quote(symbol)}/range/{mult}/{span}/{start}/{end}',
                {'adjusted': 'true' if adjust == 'split' else 'false', 'sort': 'asc', 'limit': 50000})


def aggregate(minute_bars, minutes, session='regular'):
    """把 1 分钟线拼成 N 分钟线。按交易日、从时段开头(常规 09:30 / 延长 04:00)起切,左闭右开;
    时段最后不满 N 分钟的那一根照样给(比如 1h 的 15:30–16:00),标 partial。没成交的分钟数据源本来就没有,拼的时候跳过。"""
    s_open, s_close = SESSIONS[session]
    buckets = {}
    for b in minute_bars:
        t = datetime.fromtimestamp(b['t'] / 1000, ET)
        if not (s_open <= t.time() < s_close): continue
        day_open = datetime.combine(t.date(), s_open, ET)
        k = int((t - day_open).total_seconds() // 60) // minutes
        buckets.setdefault((t.date(), k), []).append(b)
    out = []
    for (d, k), bs in sorted(buckets.items()):
        st = datetime.combine(d, s_open, ET) + timedelta(minutes=k * minutes)
        en = min(st + timedelta(minutes=minutes), datetime.combine(d, s_close, ET))
        out.append({'start': st.isoformat(), 'end': en.isoformat(), 'open': bs[0]['o'], 'high': max(x['h'] for x in bs),
                    'low': min(x['l'] for x in bs), 'close': bs[-1]['c'], 'volume': sum(x['v'] for x in bs),
                    'minutes_with_trades': len(bs), 'partial': (en - st) < timedelta(minutes=minutes)})
    return out


def get_bars(symbol, interval, start, end, session='regular', adjust='raw'):
    """symbol: 单只代码;interval: 1min/5min/15min/30min/1h/2h/4h/1d;start/end: 'YYYY-MM-DD'(美东交易日,含两端);
    session: regular(09:30–16:00)/ extended(04:00–20:00,含盘前盘后);adjust: raw / split"""
    if interval not in INTERVALS:
        return {'error': f'没有这个周期:{interval}。有的:{", ".join(INTERVALS)}(另外数据源还有秒级和周线,接口暂没开)'}
    if interval == '1d':
        rows = _fetch(symbol, 1, 'day', start, end, adjust)
        bars = []
        for b in rows:
            d = datetime.fromtimestamp(b['t'] / 1000, ET).date()
            bars.append({'start': datetime.combine(d, time(9, 30), ET).isoformat(), 'end': datetime.combine(d, time(16, 0), ET).isoformat(),
                         'open': b['o'], 'high': b['h'], 'low': b['l'], 'close': b['c'], 'volume': b['v'], 'partial': False})
        note_close = '日线开盘 / 收盘 = 交易所官方开盘价 / 收盘价(含收盘竞价);最高 / 最低 = 常规时段;成交量 = 全天(含盘前盘后、收盘竞价)。半日交易日的 end 实际是 13:00'
    else:
        rows = _fetch(symbol, 1, 'minute', start, end, adjust)
        bars = aggregate(rows, INTERVALS[interval], session)
        note_close = '由 1 分钟线拼成:每根的收盘 = 区间里最后一笔成交,不含收盘竞价,所以当天最后一根的收盘和日线收盘会差几分钱;成交量只算这个时段'
    return {
        'symbol': symbol, 'interval': interval, 'session': session, 'bars': bars,
        'meta': {
            '1_timezone': 'America/New_York(美东时间,自动处理夏令时);start / end 都带时区偏移,如 -05:00',
            '2_bar_interval': '左闭右开 [start, end):09:30 那根 15 分钟线 = 09:30:00 到 09:44:59',
            '3_adjustment': ('raw:原始成交价,不折拆股、不折分红' if adjust == 'raw' else 'split:数据源已按拆股折算(adjusted=true),不折分红'),
            '4_data_as_of': (bars[-1]['end'] if bars else None),
            'retrieved_at': datetime.now(ET).isoformat(timespec='seconds'),
            'session_rule': f'{session}: {SESSIONS[session][0]}–{SESSIONS[session][1]} 美东;半日交易日(感恩节次日、平安夜等)13:00 收盘,之后没有 K 线',
            'missing_minutes': '没有成交(或停牌)的分钟数据源不给,拼的时候直接跳过,不补;停牌整段就是没有 K 线',
            'close_note': note_close,
            'source': 'Polygon 兼容 REST /v2/aggs(1 分钟线 + 日线)',
        }}


if __name__ == '__main__':
    import sys
    print(json.dumps(get_bars(*sys.argv[1:]), ensure_ascii=False, indent=1)[:4000])
