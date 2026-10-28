import importlib.util, json, unittest
from pathlib import Path
spec=importlib.util.spec_from_file_location('exporter', Path(__file__).resolve().parents[1] / 'scripts' / 'export_optimize_fundamentals.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class FakeClient:
 def __init__(self):self.calls=[]
 def get(self,path,params=None):
  self.calls.append((path,params))
  items=[]
  if path.endswith('financial-versions'):
   items=[{'metric':params['metric'],'value':'1','unit':'USD','accepted_at':'2025-02-01T20:00:00+00:00','filed_at':'2025-02-01','pit_eligible':True},
          {'metric':params['metric'],'value':'2','accepted_at':'2027-01-01T00:00:00+00:00'}]
  return m.ApiResponse(200,json.dumps({'items':items,'total_pages':1,'events':[]}).encode())
 def post(self,path,json=None,headers=None):
  self.calls.append((path,json))
  return m.ApiResponse(200,b'{"jobs":[],"results":[]}')
class ExportTests(unittest.TestCase):
 def test_precise_additional_tags_and_independent_time_windows(self):
  c=FakeClient();_,p=m.fetch_company(c,{'symbol':'TEST'},'2016-01-01','2026-10-26',[],'2021-10-26')
  self.assertEqual(len(m.EXTRA_TAGS),18)
  self.assertIn("PaymentsToAcquireProductiveAssets",m.EXTRA_TAGS)
  self.assertIn("ResearchAndDevelopmentExpenseExcludingAcquiredInProcessCost",m.EXTRA_TAGS)
  requested={params['metric'] for path,params in c.calls if path.endswith('financial-versions')}
  for tag in m.EXTRA_TAGS:
   self.assertIn('raw:us-gaap:'+tag,requested)
   self.assertEqual(len(p['financial_versions'][tag]),1)
   self.assertEqual(p['financial_versions'][tag][0]['filing_date'],'2025-02-01T20:00:00+00:00')
  event_params=next(params for path,params in c.calls if path.endswith('earnings-events'))
  self.assertEqual(event_params['start_date'],'2021-10-26')
  self.assertEqual(p['meta']['data_window']['start'],'2016-01-01')
 def test_future_extension_is_parameterized(self):
  c=FakeClient();m.extend_history(c,[{'symbol':'TEST'}],15)
  self.assertEqual(c.calls[0][1]['history_years'],15)
  self.assertEqual(c.calls[0][1]['stage'],'cold')
if __name__ == '__main__':
 unittest.main()
