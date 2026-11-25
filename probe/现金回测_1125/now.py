import sys
exec(open('cash_bt_v2.py').read().split("g['tb_last']=3.0")[0])
r=mk('分位',0.85)
import bisect
for d in ['2026-11-24','2025-04-15','2020-03-31','2008-10-31','2001-09-28']:
    i=bisect.bisect_right(baad,d); win=sorted(BAA[x] for x in baad[max(0,i-1260):i]); q=win[int(0.85*(len(win)-1))]
    print(d, r(d), 'BAA',BAA[baad[i-1]],'5年85分位',round(q,2),'萨姆',asof(SAHMa,d),'核心CPI3m/前3m',[round(x*100,2) for x in asof(CPIa,d)])
