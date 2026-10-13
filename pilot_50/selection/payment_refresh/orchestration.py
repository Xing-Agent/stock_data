"""Task-local delivery refresh; production export remains fetch_market_bars.py."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import random
import sys
import time

import httpx

spec=importlib.util.spec_from_file_location('pilot', '/tmp/xing_pilot50.py')
pilot=importlib.util.module_from_spec(spec)
mode=sys.argv[1]
sys.argv[1]='noop'
spec.loader.exec_module(pilot)
ROOT=Path('/app/artifacts/companyfacts-audit/pilot_completion')
BASE=Path('/app/artifacts/companyfacts-audit/pilot_50')
ROOT.mkdir(parents=True,exist_ok=True)

def save(name,data):
    p=ROOT/name; p.parent.mkdir(parents=True,exist_ok=True)
    p.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

if mode=='actions':
    token=asyncio.run(pilot.access_token())
    manifest=json.loads((BASE/'manifest.json').read_text())
    symbols=json.load(open('/tmp/pilot_missing_payments.json'))
    report=[]
    with httpx.Client(base_url='http://127.0.0.1:8000',headers={'Authorization':'Bearer '+token},timeout=180) as client:
        for stock in manifest['stocks']:
            if stock['symbol'] not in symbols: continue
            for interval,start in [('1d','2016-01-01'),('5min','2021-01-01')]:
                params={'start_date':start,'end_date':min('2025-12-31',stock['delisting_date'] or '2025-12-31')}
                for attempt in range(3):
                    r=client.get('/research-data/market-bars/'+stock['symbol']+'/actions',params=params)
                    r.raise_for_status(); data=r.json()
                    if data.get('status')=='ready' and 'fmp_payment_dates_unavailable' not in data.get('warnings',[]): break
                    if attempt<2: time.sleep(61)
                save('actions/'+stock['symbol']+'_'+interval+'.json',data)
                result={'symbol':stock['symbol'],'interval':interval,'status':data.get('status'),'missing_payment_dates':data.get('missing_payment_dates',[]),'warnings':data.get('warnings',[])}
                report.append(result); save('payment_refresh_report.json',report)
                print(json.dumps(result),flush=True)
elif mode=='select':
    original=json.loads((BASE/'manifest.json').read_text())
    inventories=json.loads((BASE/'selection/listing_inventories.json').read_text())
    profiles=json.loads((BASE/'selection/fmp_profiles_snapshot.json').read_text())
    baseline={x['symbol']:x for x in inventories['active_2016-01-01'] if x['assetType']=='Stock' and x['exchange'] in {'NYSE','NASDAQ','AMEX'} and x['ipoDate']<='2016-01-01'}
    survivors={x['symbol'] for x in inventories['active_2025-12-31']}
    exclude={x['symbol'] for x in original['stocks']}
    pool=sorted([x for x in profiles if x['symbol'] in baseline and x['symbol'] in survivors and x['symbol'] not in exclude],key=lambda x:x['symbol'])
    random.Random(20261014).shuffle(pool)
    selected=[]; rejected=[]; groups=set()
    with httpx.Client(timeout=45) as client:
        for candidate in pool:
            symbol=candidate['symbol']
            rows=pilot.fmp(client,'profile',symbol=symbol)
            if not rows or not pilot.common(rows[0]) or rows[0].get('ipoDate','9999')>'2016-01-01':
                rejected.append({'symbol':symbol,'reason':'ineligible_profile'}); continue
            item=rows[0]
            caps=pilot.fmp(client,'historical-market-capitalization',symbol=symbol,**{'from':'2015-12-31','to':'2015-12-31'})
            cap=next((x.get('marketCap') for x in caps if x.get('date')=='2015-12-31' and x.get('marketCap',0)>0),None)
            if cap is None: rejected.append({'symbol':symbol,'reason':'missing_baseline_cap'}); continue
            group='large' if cap>=10e9 else 'mid' if cap>=2e9 else 'small'
            if group in groups: continue
            selected.append({'symbol':symbol,'name':item['companyName'],'exchange':baseline[symbol]['exchange'],'ipo_date':baseline[symbol]['ipoDate'],'size_group':group,'market_cap_usd':cap,'market_cap_date':'2015-12-31','sector':item.get('sector'),'sector_basis':'FMP current profile; not historical GICS','delisted':False,'delisting_date':None,'is_adr':item.get('isAdr')})
            save('selection/profiles/'+symbol+'.json',item)
            groups.add(group); print(json.dumps(selected[-1]),flush=True)
            if len(selected)==3: break
    assert len(selected)==3
    save('supplemental/manifest.json',{'stocks':selected,'seed':20261014,'selection_method':'Supplemental engineering cohort only; fixed-seed one current survivor per historical size group; does not replace original cohort or repair survivorship bias','limitations':original['limitations'],'rejected_candidates':rejected})
elif mode in ('download','audit','retry'):
    pilot.ROOT=ROOT/'supplemental'
    sys.argv=[sys.argv[0],mode,'1'] if mode=='retry' else [sys.argv[0],mode]
    getattr(pilot,mode)()
