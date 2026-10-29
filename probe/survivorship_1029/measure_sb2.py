#!/usr/bin/env python3
# -*- coding: utf-8 -*-
import csv, json, os, re, datetime as dt
from collections import Counter
PIT="/home/claude/xing-agent-stock_data/probe/xing-pit-universe-20261029-025954"
REPO="/home/claude/xing-agent-stock_data"
syms={r['symbol']:r for r in csv.DictReader(open(os.path.join(PIT,'pit_universe_symbols.csv')))}
man=list(csv.DictReader(open(os.path.join(REPO,'pilot_300','manifest.csv'))))
d0='2018-01-02'

print("=== A · 我们日线的首根 vs PIT first_seen(差得多 = 我们的历史是按今天的代码回填的)===")
rows=[]
for r in man:
    s=r['symbol']; p=syms.get(s)
    pth=os.path.normpath(os.path.join(REPO,'pilot_300',r['data_path']))
    try:
        bars=json.load(open(pth)).get('data') or []
    except Exception:
        bars=[]
    first=bars[0]['date'] if bars else None
    last=bars[-1]['date'] if bars else None
    if p and first:
        gap=(dt.date.fromisoformat(p['first_seen'])-dt.date.fromisoformat(first)).days
        rows.append((s,r['size_group'],r['delisted'],first,last,p['first_seen'],p['last_seen'],gap))
rows.sort(key=lambda x:-x[7])
print(f"  参与比较 {len(rows)} 只")
bad=[x for x in rows if x[7]>180]
print(f"  ★ PIT first_seen 比我们日线首根晚 >180 天的:{len(bad)} 只 —— 这些票我们手里的那段早期历史,在 PIT 名单里这个代码当时不是它")
for x in bad:
    print(f"     {x[0]:6s} {x[1]:5s} 退市={x[2]:5s} 我们 {x[3]}~{x[4]} | PIT {x[5]}~{x[6]} | 晚 {x[7]} 天")
json.dump(rows,open('/tmp/claude-0/-home-claude/e6b5eede-2545-5921-9bbc-5820cecf2c9c/scratchpad/sb2_rows.json','w'),ensure_ascii=False)

print("\n=== B · 已退市 30 只:PIT last_seen vs manifest download_end_date ===")
for r in man:
    if r['delisted']!='True': continue
    p=syms.get(r['symbol'])
    if not p:
        print(f"     {r['symbol']:6s} ❌ 不在 PIT 名单"); continue
    d=(dt.date.fromisoformat(p['last_seen'])-dt.date.fromisoformat(r['download_end_date'])).days
    print(f"     {r['symbol']:6s} {r['size_group']:5s} PIT末 {p['last_seen']} | 我们末 {r['download_end_date']} | 差 {d:+5d} 天 | {r['retirement_category']}")

print("\n=== C · 相邻日收盘价量级突变(排除有拆股系数的)—— PROP 式拼接的痕迹 ===")
jumps=[]
for r in man:
    pth=os.path.normpath(os.path.join(REPO,'pilot_300',r['data_path']))
    try: bars=json.load(open(pth)).get('data') or []
    except Exception: continue
    for i in range(1,len(bars)):
        a,b=bars[i-1],bars[i]
        sc=b.get('split_coefficient') or 1
        if sc!=1: continue
        ca,cb=a.get('close'),b.get('close')
        if not ca or not cb: continue
        rt=cb/ca
        if rt>=3 or rt<=1/3:
            jumps.append((r['symbol'],r['size_group'],a['date'],b['date'],ca,cb,rt))
jumps.sort(key=lambda x:-max(x[6],1/x[6]))
print(f"  命中 {len(jumps)} 根")
for x in jumps[:25]: print(f"     {x[0]:6s} {x[1]:5s} {x[2]}->{x[3]} {x[4]}->{x[5]} 倍={x[6]:.3f}")

print("\n=== D · ETF 无法识别对核心数字的影响带 ===")
# 复用第一步的分类
def classify(sym):
    base,_,suf=sym.partition('.'); sh=suf.split('.')[0] if suf else ''
    if sh.startswith('W'): return 'warrant'
    if sh=='U': return 'unit'
    if sh=='R': return 'right'
    if sh=='CL': return 'pref'
    if len(base)==5 and base.isalpha() and base[4] in 'WUR': return {'W':'warrant','U':'unit','R':'right'}[base[4]]
    if re.fullmatch(r'[A-Z]{2,5}P[A-Z]',base): return 'pref'
    return 'unclassified'
END='2025-12-31'
alive=[r for r in syms.values() if r['first_seen']<=d0<=r['last_seen']]
co=[r for r in alive if classify(r['symbol'])=='unclassified' and int(r['trading_days'])>=60]
n=len(co); surv=sum(1 for r in co if r['last_seen']>=END)
print(f"  剔非公司后 n={n} 存活={surv} 消失率={(n-surv)/n*100:.2f}%")
for etf_n in (2000,2500,3000):
    for etf_surv_rate in (1.0,0.9,0.75,0.6):
        es=int(etf_n*etf_surv_rate)
        n2=n-etf_n; s2=surv-es
        if n2<=0 or s2<0: continue
        print(f"   假设当日名单里有 {etf_n} 只 ETF、其存活率 {etf_surv_rate:.0%} → 纯公司消失率 = {(n2-s2)/n2*100:5.2f}%  (n={n2})")
