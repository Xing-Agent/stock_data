#!/usr/bin/env python3
"""取 Polygon 每年年初的全市场代码表(含已退市),只要「代码 → 公司名 / CIK」这几列。
用途:给基本面扩池(4,263 家)找 SEC 公司编号。只是参考数据,不是行情。

用法(在有 Polygon 代理 key 的那台电脑上):
    export POLYGON_PROXY_KEY=你的key        # key 只放环境变量,不写进任何文件
    cd stock_data && git pull
    python3 probe/fund_expand_1103/fetch_polygon_tickers_yearly.py
    git add probe/fund_expand_1103/polygon_tickers_*.json.gz && git commit -m "polygon tickers yearly" && git push
"""
import gzip, json, os, sys, time, urllib.parse, urllib.request
BASE = os.environ.get('POLYGON_PROXY_BASE', 'http://44.219.45.87:8081')
KEY = os.environ.get('POLYGON_PROXY_KEY') or sys.exit('先 export POLYGON_PROXY_KEY=...')
DATES = ['2016-12-30', '2017-12-29', '2018-12-31', '2019-12-31', '2020-12-31', '2021-12-31',
         '2022-12-30', '2023-12-29', '2024-12-31', '2025-12-31']   # 2015-12-31 已有
FIELDS = ['ticker', 'name', 'type', 'primary_exchange', 'cik', 'active', 'delisted_utc', 'composite_figi']
OUT = os.path.dirname(os.path.abspath(__file__))

def get(url):
    for i in range(5):
        try:
            # 代理的 key:同时放 query 和 header,哪种认就用哪种
            sep = '&' if '?' in url else '?'
            req = urllib.request.Request(url + f'{sep}apiKey={urllib.parse.quote(KEY)}',
                                         headers={'X-API-KEY': KEY, 'Authorization': f'Bearer {KEY}'})
            with urllib.request.urlopen(req, timeout=60) as r:
                return json.loads(r.read())
        except Exception as e:
            print('  重试', i + 1, e); time.sleep(2 + 3 * i)
    raise SystemExit('连不上代理:' + url)

for d in DATES:
    path = os.path.join(OUT, f'polygon_tickers_{d.replace("-", "")}.json.gz')
    if os.path.exists(path): print('已有', path); continue
    rows = []
    for active in ('true', 'false'):
        url = f'{BASE}/v3/reference/tickers?' + urllib.parse.urlencode({'market': 'stocks', 'date': d, 'active': active, 'limit': 1000})
        while url:
            j = get(url)
            for r in j.get('results', []):
                rows.append([r.get(f, '') for f in FIELDS])
            nxt = j.get('next_url')
            url = (nxt.replace('https://api.polygon.io', BASE).replace('https://api.massive.com', BASE)) if nxt else None
            time.sleep(0.15)
    json.dump({'retrieved_at': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'source': f'polygon /v3/reference/tickers market=stocks date={d} (active true+false)',
               'fields': FIELDS, 'rows': rows}, gzip.open(path, 'wt'))
    print(d, len(rows), '行 →', path)
print('完成')
