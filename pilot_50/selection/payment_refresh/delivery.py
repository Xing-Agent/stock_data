"""Apply generated action responses without changing price observations."""
import hashlib
from collections import Counter
import importlib.util
import json
from pathlib import Path
import shutil
import sys

root=Path('/Users/kevin/workspace/xing/stock_data/pilot_50')
stage=Path('/Users/kevin/workspace/xing/agent/artifacts/companyfacts-audit/pilot_completion')
mode=sys.argv[1]
def digest(data):
    return hashlib.sha256(json.dumps(data,sort_keys=True,separators=(',',':')).encode()).hexdigest()
def save(path,data):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n')

if mode=='actions':
    results=[]
    for response in sorted((stage/'actions').glob('*.json')):
        symbol,interval=response.stem.split('_')
        path=root/symbol/('daily.json' if interval=='1d' else '5min.json')
        data=json.loads(path.read_text()); old=data['corporate_actions']; new=json.loads(response.read_text())
        assert new['status']=='ready' and 'fmp_payment_dates_unavailable' not in new.get('warnings',[])
        def identity(e): return (e['effective_date'],e['action_type'],e.get('cash_amount'),e.get('split_coefficient'))
        oldevents={identity(e):e for e in old['events']}; newevents={identity(e):e for e in new['events']}
        assert len(oldevents)==len(old['events']) and set(oldevents)==set(newevents)
        assert all(not e.get('payment_date') or newevents[k].get('payment_date')==e['payment_date'] for k,e in oldevents.items())
        backup=root/'selection/payment_refresh/original_actions'/response.name
        if not backup.exists(): save(backup,old)
        before=digest(data['data'])
        count=sum(not e.get('payment_date') and bool(newevents[k].get('payment_date')) for k,e in oldevents.items())
        data['corporate_actions']=new
        save(path,data)
        assert digest(json.loads(path.read_text())['data'])==before
        results.append({'symbol':symbol,'interval':interval,'filled_payment_dates':count,'remaining':new.get('missing_payment_dates',[]),'price_data_unchanged':True})
    save(root/'selection/payment_refresh/report.json',results)
    print(json.dumps({'updated_files':len(results),'filled_across_files':sum(x['filled_payment_dates'] for x in results),'prices_unchanged':all(x['price_data_unchanged'] for x in results)}))
elif mode=='supplemental':
    destination=root/'supplemental'
    assert not destination.exists(), 'Supplemental delivery already exists'
    shutil.move(str(stage/'supplemental'),str(destination))
    print('Supplemental files delivered')
elif mode=='audit':
    spec=importlib.util.spec_from_file_location('pilot','/private/tmp/xing_pilot50.py')
    pilot=importlib.util.module_from_spec(spec); sys.argv=[sys.argv[0],'noop']; spec.loader.exec_module(pilot)
    pilot.ROOT=root; pilot.audit()
    if (root/'supplemental').exists(): pilot.ROOT=root/'supplemental'; pilot.audit()
elif mode=='final':
    reports=[]
    for folder in (root,root/'supplemental'):
        rows=json.loads((folder/'download_report.json').read_text())
        for row in rows:
            path=folder/row['symbol']/('daily.json' if row['interval']=='1d' else '5min.json')
            assert hashlib.sha256(path.read_bytes()).hexdigest()==row['sha256']
            reports.append(row)
    unresolved={(x['symbol'],day) for x in reports for day in x.get('missing_payment_dates',[])}
    save(root/'combined_acceptance_summary.json',{
        'original_cohort_size':50,'supplemental_cohort_size':3,'files':len(reports),
        'file_hashes_verified':len(reports),'status_counts':dict(Counter(x['status'] for x in reports)),
        'validated_nonempty_files':sum(x['validation_passed'] for x in reports),
        'ready_daily_symbols':[x['symbol'] for x in reports if x['interval']=='1d' and x['status']=='ready'],
        'ready_five_minute_symbols':[x['symbol'] for x in reports if x['interval']=='5min' and x['status']=='ready' and x['validation_passed']],
        'unresolved_payment_events':len(unresolved),
        'unresolved_payment_dates':[{'symbol':symbol,'effective_date':day} for symbol,day in sorted(unresolved)],
        'notes':['Ready does not imply a bar exists at every 5-minute calendar position.',
                 'Original and supplemental cohorts are separate; do not relabel them as a new random 50-stock cohort.',
                 'Six unresolved payment events have cross-provider dividend amount mismatches; three lack a unique FMP date match.']})
    shutil.copyfile('/private/tmp/complete_pilot_data.py',root/'selection/payment_refresh/orchestration.py')
    shutil.copyfile('/private/tmp/deliver_pilot_completion.py',root/'selection/payment_refresh/delivery.py')
    print(json.dumps({'files_verified':len(reports),'unresolved_payment_events':len(unresolved),'statuses':dict(Counter(x['status'] for x in reports))}))
