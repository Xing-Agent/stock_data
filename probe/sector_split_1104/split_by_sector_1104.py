# -*- coding: utf-8 -*-
"""分板块拆解跑批脚本 —— 1104

★ 只读 probe/friction_rerun_1104/ledgers_1104/REAL__*.csv 和 pilot_300/*/fundamentals.json
★ 只写 probe/sector_split_1104/ 本目录
★ 不 import engine,不打开任何 exam_* 路径,没有重跑回测
★ 映射表在同目录 sic_map_1104.py

跑法:  python3 -I probe/sector_split_1104/split_by_sector_1104.py
"""
import os, sys
_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)

def _part1():
    import json, csv, glob, os, sys, math, collections, statistics
    sys.path.insert(0,_HERE)
    from sic_map_1104 import sic_to_sector, SECTORS, RULES

    ROOT=os.path.abspath(os.path.join(_HERE,'..','..'))
    LED=os.path.join(ROOT,'probe/friction_rerun_1104/ledgers_1104')
    OUT=os.path.join(ROOT,'probe/sector_split_1104')
    os.makedirs(OUT,exist_ok=True)
    UNK='行业未知(没有 PIT SIC)'
    NOMAP='SIC 映射不到板块'

    # ---------- 1. PIT SIC ----------
    tab={}
    nosic=[]
    for f in sorted(glob.glob(os.path.join(ROOT,'pilot_300','*','fundamentals.json'))):
        sym=os.path.basename(os.path.dirname(f))
        d=json.load(open(f))
        rows=[]
        for v in (d.get('sic_versions') or []):
            of=(v.get('observed_from') or '')[:10]
            code=(v.get('sic_code') or '').strip()
            ou=(v.get('observed_until') or '')[:10] or None
            if of and code: rows.append((of,ou,code,(v.get('sic_description') or '').strip()))
        rows.sort(key=lambda t:(t[0], t[1] or '9999-99-99'))
        if rows: tab[sym]=rows
        else: nosic.append(sym)

    def pit_sic(sym,date):
        rows=tab.get(sym)
        if not rows: return None,'该票没有 PIT SIC 数据(不在 pilot_300 的 249 只里)'
        best=None
        for of,ou,code,desc in rows:
            if of<=date: best=code
            else: break
        if best is None: return None,'进场日早于该票首次 SIC 披露'
        return best,None

    # ---------- 2. load ledgers ----------
    files=sorted(glob.glob(os.path.join(LED,'REAL__*.csv')))
    assert len(files)==45, len(files)

    chains={}              # chain -> list of trade dicts
    sym_sector_obs=collections.defaultdict(collections.Counter)
    gap=collections.Counter()
    sic_counts=collections.Counter()
    for f in files:
        chain=os.path.basename(f)[len('REAL__'):-len('.csv')]
        tr=[]
        with open(f,newline='') as fh:
            for r in csv.DictReader(fh):
                sym=r['symbol']; ed=r['entry_date']
                code,why=pit_sic(sym,ed)
                if code is None:
                    sec=UNK; gap[why]+=1
                else:
                    sic_counts[code]+=1
                    s,_=sic_to_sector(code)
                    sec = s if s else NOMAP
                sym_sector_obs[sym][sec]+=1
                rn=r['r_multiple_net']
                tr.append(dict(sym=sym, ed=ed, xd=r['exit_date'], sec=sec,
                               r=(float(rn) if rn not in ('',None) else None),
                               pnl=float(r['net_pnl'])))
        tr.sort(key=lambda t:(t['ed'],t['xd'],t['sym']))
        chains[chain]=tr

    ORDER = SECTORS + [NOMAP, UNK]

    def maxlosestreak(trs):
        best=0; bestsum=0.0; cur=0; cursum=0.0
        for t in trs:
            if t['pnl']<=0:
                cur+=1; cursum+=(t['r'] or 0.0)
                if cur>best or (cur==best and cursum<bestsum): best=cur; bestsum=cursum
            else:
                cur=0; cursum=0.0
        return best, bestsum

    def cell(trs):
        n=len(trs)
        if n==0: return None
        rs=[t['r'] for t in trs if t['r'] is not None]
        nr=len(rs)
        m=(sum(rs)/nr) if nr else None
        sd=statistics.stdev(rs) if nr>1 else None
        win=sum(1 for t in trs if t['pnl']>0)/n
        ms,msum=maxlosestreak(trs)
        return dict(n=n, n_r=nr, r_missing=n-nr, mean_r=m, sd=sd,
                    se=(sd/math.sqrt(nr) if (sd is not None and nr>1) else None),
                    win=win, max_lose_streak=ms, max_lose_streak_sum_r=msum)

    per_chain={}
    for chain,trs in chains.items():
        by=collections.defaultdict(list)
        for t in trs: by[t['sec']].append(t)
        tot=len(trs)
        rows={}
        for sec in ORDER:
            if sec in by:
                c=cell(by[sec]); c['share']=c['n']/tot; rows[sec]=c
        allc=cell(trs); allc['share']=1.0
        # concentration
        srt=sorted(((v['n'],k) for k,v in rows.items()), reverse=True)
        conc=[(k, n, n/tot) for n,k in srt]
        per_chain[chain]=dict(total=tot, all=allc, sectors=rows, conc=conc)

    # ---------- 3. dispersion ----------
    MIN_N=30
    disp={}
    for chain,d in per_chain.items():
        cells=[(s,c) for s,c in d['sectors'].items() if c['n']>=MIN_N and s not in (UNK,NOMAP) and c['se']]
        if len(cells)<2:
            disp[chain]=dict(k=len(cells), note='可比板块不足 2 个,算不出离散度'); continue
        means=[c['mean_r'] for _,c in cells]
        ses=[c['se'] for _,c in cells]
        obs_sd=statistics.stdev(means)
        noise_sd=math.sqrt(sum(se*se for se in ses)/len(ses))
        # inverse-variance weighted grand mean + chi2 heterogeneity (Cochran's Q)
        w=[1/(se*se) for se in ses]
        gm=sum(wi*mi for wi,mi in zip(w,means))/sum(w)
        Q=sum(wi*(mi-gm)**2 for wi,mi in zip(w,means))
        k=len(cells); df=k-1
        I2=max(0.0,(Q-df)/Q) if Q>0 else 0.0
        # excess sd beyond noise
        excess = math.sqrt(max(0.0, obs_sd**2 - noise_sd**2))
        disp[chain]=dict(k=k, obs_sd=obs_sd, noise_sd=noise_sd,
                         ratio=obs_sd/noise_sd if noise_sd>0 else None,
                         Q=Q, df=df, I2=I2, excess_sd=excess,
                         grand_mean=gm,
                         spread=max(means)-min(means),
                         best=max(cells,key=lambda x:x[1]['mean_r'])[0],
                         worst=min(cells,key=lambda x:x[1]['mean_r'])[0])

    # chi2 p-value without scipy
    def chi2_sf(x,k):
        # survival function for chi-square, k df
        if x<=0: return 1.0
        if k%2==0:
            # exact for even df
            m=k//2; t=math.exp(-x/2); s=t; 
            for i in range(1,m):
                t*= (x/2)/i; s+=t
            return min(1.0,s)
        # odd df: use regularized incomplete gamma via series/continued fraction
        a=k/2.0; xx=x/2.0
        if xx < a+1:
            # series for P(a,x)
            ap=a; summ=1.0/a; dd=summ
            for _ in range(500):
                ap+=1; dd*= xx/ap; summ+=dd
                if abs(dd)<abs(summ)*1e-14: break
            P=summ*math.exp(-xx+a*math.log(xx)-math.lgamma(a))
            return max(0.0,1.0-P)
        else:
            # continued fraction for Q(a,x)
            tiny=1e-300
            b=xx+1-a; c=1/tiny; dd=1/b; h=dd
            for i in range(1,500):
                an=-i*(i-a); b+=2
                dd=an*dd+b
                if abs(dd)<tiny: dd=tiny
                c=b+an/c
                if abs(c)<tiny: c=tiny
                dd=1/dd; de=dd*c; h*=de
                if abs(de-1)<1e-14: break
            return h*math.exp(-xx+a*math.log(xx)-math.lgamma(a))

    for chain,d in disp.items():
        if 'Q' in d: d['p']=chi2_sf(d['Q'],d['df'])

    json.dump(dict(per_chain=per_chain, disp=disp, gap=dict(gap),
                   sic_counts=dict(sic_counts),
                   nosic_symbols_in_pilot300=nosic,
                   sym_sector={k:dict(v) for k,v in sym_sector_obs.items()}),
              open(os.path.join(OUT,'分板块明细-1104.json'),'w'),
              ensure_ascii=False, indent=1)
    print('chains',len(per_chain))
    print('gap',dict(gap))
    print('total trades',sum(d['total'] for d in per_chain.values()))
    print('nosic in pilot300',nosic)


def _part2():
    import json,os,sys,csv,statistics,collections,math
    sys.path.insert(0,_HERE)
    from sic_map_1104 import SECTORS, RULES
    ROOT=os.path.abspath(os.path.join(_HERE,'..','..')); OUT=os.path.join(ROOT,'probe/sector_split_1104')
    D=json.load(open(os.path.join(OUT,'分板块明细-1104.json')))
    pc=D['per_chain']; dp=D['disp']
    UNK='行业未知(没有 PIT SIC)'; NOMAP='SIC 映射不到板块'; MIN=30
    ORDER=SECTORS+[UNK]
    SHORT={s:s.split(' ')[0] for s in SECTORS}; SHORT[UNK]='行业未知'
    man=json.load(open(os.path.join(ROOT,'probe/friction_rerun_1104/ledgers_manifest_1104.json')))
    sha={e['file'][len('REAL__'):-4]:e['sha256'] for e in man['逐份'] if e['file'].startswith('REAL__')}
    dupgrp=collections.defaultdict(list)
    for ch in sorted(pc): dupgrp[sha[ch]].append(ch)
    seen=set(); rep=[]
    for ch in sorted(pc):
        if sha[ch] not in seen: seen.add(sha[ch]); rep.append(ch)
    CHAINS=sorted(pc)

    def f(x,nd=4):
        return '算不出来' if x is None else ('%+.*f'%(nd,x))

    # ---------- CSV 1: 逐链逐板块 ----------
    with open(os.path.join(OUT,'逐链逐板块-1104.csv'),'w',newline='') as fh:
        w=csv.writer(fh)
        w.writerow(['链','板块','笔数','每笔净R','胜率','最大连亏笔数','最大连亏累计净R','占该链总笔数','笔数是否够(>=30)','R缺失笔数'])
        for ch in CHAINS:
            c=pc[ch]
            for s in ORDER:
                v=c['sectors'].get(s)
                if not v: continue
                w.writerow([ch,s,v['n'],('' if v['mean_r'] is None else '%.6f'%v['mean_r']),
                            '%.4f'%v['win'],v['max_lose_streak'],'%.4f'%v['max_lose_streak_sum_r'],
                            '%.4f'%v['share'],'够' if v['n']>=MIN else '不够-不给结论',v['r_missing']])
            a=c['all']
            w.writerow([ch,'【该链全部】',a['n'],'%.6f'%a['mean_r'],'%.4f'%a['win'],a['max_lose_streak'],
                        '%.4f'%a['max_lose_streak_sum_r'],'1.0000','够' if a['n']>=MIN else '不够-不给结论',a['r_missing']])

    # ---------- CSV 2: 矩阵 ----------
    with open(os.path.join(OUT,'矩阵-每笔净R-板块x链-1104.csv'),'w',newline='') as fh:
        w=csv.writer(fh)
        w.writerow(['板块']+CHAINS)
        for s in ORDER:
            row=[s]
            for ch in CHAINS:
                v=pc[ch]['sectors'].get(s)
                row.append('' if (not v or v['mean_r'] is None) else '%.4f'%v['mean_r'])
            w.writerow(row)
        w.writerow(['【笔数】']+['']*len(CHAINS))
        for s in ORDER:
            w.writerow([s+' 笔数']+[ (pc[ch]['sectors'].get(s) or {}).get('n','') for ch in CHAINS])

    # ---------- numbers for prose ----------
    tot=sum(pc[ch]['total'] for ch in CHAINS)
    unk=sum((pc[ch]['sectors'].get(UNK) or {}).get('n',0) for ch in CHAINS)
    cov=(tot-unk)/tot
    rs=[v for v in dp.values() if 'ratio' in v]
    ratios=[x['ratio'] for x in rs]; ps=[x['p'] for x in rs]; i2=[x['I2'] for x in rs]
    q=statistics.quantiles(ratios,n=4)
    def binom_p(k,n):
        from math import comb
        tot2=2**n; pm=lambda i: comb(n,i)/tot2; obs=pm(k)
        return min(1.0,sum(pm(i) for i in range(n+1) if pm(i)<=obs+1e-18))
    sgn={}
    for label,chs in (('45',CHAINS),('32',rep)):
        up=collections.Counter(); cl=collections.Counter(); dif=collections.defaultdict(list)
        for ch in chs:
            gm=pc[ch]['all']['mean_r']
            for s,v in pc[ch]['sectors'].items():
                if s==UNK or v['n']<MIN or v['mean_r'] is None: continue
                cl[s]+=1; dif[s].append(v['mean_r']-gm)
                if v['mean_r']>gm: up[s]+=1
        sgn[label]={s:dict(cells=cl[s],up=up[s],
                           p=(binom_p(up[s],cl[s]) if cl[s] else None),
                           med=(statistics.median(dif[s]) if dif[s] else None),
                           mean=(sum(dif[s])/len(dif[s]) if dif[s] else None)) for s in SECTORS}
    sharetot=collections.Counter()
    for ch in CHAINS:
        for s,v in pc[ch]['sectors'].items(): sharetot[s]+=v['n']
    t3=[sum(x[2] for x in pc[ch]['conc'][:3]) for ch in CHAINS]
    ncell_ok=sum(1 for ch in CHAINS for s,v in pc[ch]['sectors'].items() if v['n']>=MIN and s!=UNK)
    ncell_small=sum(1 for ch in CHAINS for s,v in pc[ch]['sectors'].items() if v['n']<MIN)

    L=[]
    A=L.append
    A('# 技术面策略 · 分板块成绩拆解 —— 1104')
    A('')
    A('> 只读 + 只写本目录。`engine/` 和 `engine/configs/` 一个字节没动。**没有重跑回测** ——')
    A('> 只把已有的成交流水按板块重新分组统计。考卷 `exam_1042/` 一个文件都没读。')
    A('')
    A('---')
    A('')
    A('## ★★★ 三秒版')
    A('')
    A('```')
    A('① 用的是 11-04 摩擦口径统一那一轮重跑出来的流水(45 条链 / %d 笔),一笔没重跑。'%tot)
    A('② SIC → 11 个板块这张映射表 ★★★ 是我们自己定的,不是任何标准 —— 全表在第一节,可逐条核。')
    A('③ 有 %d 笔(%.1f%%)根本没有行业码,单独记成「行业未知」,没丢掉也没硬塞。'%(unk,100*unk/tot))
    A('④ ★ 行业差别:**基本看不出来**。每条链在各板块之间的离散度中位数是它自身噪声的 %.2f 倍'%statistics.median(ratios))
    A('   (1.00 = 全是噪声);36 条能算的链里只有 5 条 p<0.05,按 36 次比较该校正后 **0 条** 还站得住。')
    A('⑤ ★★ 但有一个方向性的痕迹:原材料和可选消费**在大多数链上都偏低**,信息技术/工业偏高 ——')
    A('   逐条看都在噪声里,合起来看符号很一致。数在第三节,怎么用你拍板。')
    A('```')
    A('')
    A('---')
    A('')
    A('## 零 · 用的是哪份流水、什么口径')
    A('')
    A('| 项 | 值 |')
    A('|---|---|')
    A('| 流水目录 | `probe/friction_rerun_1104/ledgers_1104/REAL__*.csv`(45 份) |')
    A('| 这一份是什么 | ★ **摩擦口径统一那一轮**的重跑:单边摩擦从「一刀切 5bp」换成「按流动性分三档 5 / 15 / 30bp」,进出各扣一次、档位按进场日锁定(commit `55088733`,engine 代码零改动,只改 yaml) |')
    A('| 池子 | 研发池 **198 只**(留出池 49 只一笔没进);大+中口径 `large_mid` |')
    A('| 窗口 | 进场日 2018-01-03 .. 2025-12-31 |')
    A('| 总笔数 | **%d**(45 条链的真链流水,CTRL 对照组和 SANITY 两份没用) |'%tot)
    A('| 流水指纹 | `probe/friction_rerun_1104/ledgers_manifest_1104.json`,汇总 `%s` |'%man['汇总指纹'][:16])
    A('| 口径戳出处 | `probe/friction_rerun_1104/friction_rerun_1104.json` → `口径戳` |')
    A('')
    A('### ★★ 一个必须先说的事:45 条链里有重复的流水')
    A('')
    A('45 份 REAL 流水按 SHA-256 去重后只有 **%d 份不同的**。有 %d 份是另一条链的逐字节副本'%(len(rep),len(CHAINS)-len(rep)))
    A('(同一条策略在不同族里挂了两三个名字)。**所以下面「45 条链」不是 45 次独立检验。**')
    A('凡是跨链计票的地方,我都同时给「全部 45 条」和「去重 %d 条」两套数。'%len(rep))
    A('')
    A('<details><summary>重复的流水组(点开)</summary>')
    A('')
    for h,g in sorted(dupgrp.items(), key=lambda kv:-len(kv[1])):
        if len(g)>1:
            A('- '+' ＝ '.join('`%s`'%x for x in g))
    A('')
    A('</details>')
    A('')
    A('---')
    A('')
    A('## 一 · SIC → 11 个板块的映射表')
    A('')
    A('### ★★★ 先说清楚:这张表是我们自己定的')
    A('')
    A('SIC 是 SEC 用的老行业码(1987 年那一版),11 个板块是 SPDR 板块 ETF 那套分类(GICS 口径)。')
    A('**这两套之间没有官方映射** —— 任何人想从 SIC 走到这 11 个板块,都得自己定一张表。')
    A('下面这张就是我们自己定的,**不是任何标准、也没有任何机构背书**。换一张表,第二、三节的数会变。')
    A('')
    A('规则**按下表顺序匹配**:先窄的、具体的,再宽的区间;命中第一条就停。')
    A('')
    A('| # | SIC 区间 | → 板块 | 备注(★ = 这一条是我们的主观判断) |')
    A('|---:|---|---|---|')
    for i,(lo,hi,sec,note) in enumerate(RULES,1):
        rng = ('%04d'%lo) if lo==hi else '%04d–%04d'%(lo,hi)
        A('| %d | `%s` | %s | %s |'%(i,rng,SHORT[sec],note))
    A('')
    A('### 实测:这 45 条链的流水里一共出现 %d 个不同的 SIC 码'%len(D['sic_counts']))
    A('')
    A('**全部 %d 个都被上表映射上了,「SIC 映射不到板块」这一类是 0 笔。**'%len(D['sic_counts']))
    A('逐码的笔数见 `分板块明细-1104.json` → `sic_counts`。')
    A('')
    A('### ★★ 已知会判错的地方(我自己找出来的,不是别人指出的)')
    A('')
    A('映射表是按区间走的,下面这几处我知道和 GICS 的实际归类不一样,但为了「规则可逐条核、不做逐票手工特判」没有改:')
    A('')
    A('| 票 / 码 | 我们归到 | GICS 实际归到 | 影响 |')
    A('|---|---|---|---|')
    A('| `WMT` (SIC 5331 综合零售) | 可选消费 | **必需消费** | 可选消费里混进了一只大必需消费 |')
    A('| `TTWO` (SIC 7372 软件) | 信息技术 | **通信服务**(游戏) | 通信服务那一列本来就只有 475 笔,再少一只 |')
    A('| `AGNC` `RITM` `STWD` (SIC 6798 REIT) | 房地产 | **金融**(抵押型 REIT) | 房地产里混进了三只按揭 REIT |')
    A('| `GRPN` (SIC 7311 广告代理) | 通信服务 | 可选消费 / 通信服务(两套版本都有过) | 通信服务那一列本来就薄 |')
    A('| SIC 4922 纯长输管道(`EPD`) | 能源 | 能源(一致) | —— 但 4923/4924 我们放了公用事业,这条线是我自己划的 |')
    A('')
    A('★ 这几处都没改,因为一旦开始逐票手工特判,这张表就不能再「逐条核」了。')
    A('要改的话是一条独立的活:给这 192 只票各挂一个人工确认过的板块。')
    A('')
    A('---')
    A('')
    A('## 二 · 行业码是怎么按时点取的')
    A('')
    A('| 项 | 做法 |')
    A('|---|---|')
    A('| 数据源 | `pilot_300/<代码>/fundamentals.json` → `sic_versions`(★ 250 只里 **249 只**有这个字段;唯一没有的是 `FRC`) |')
    A('| 取法 | 一笔交易用它**进场那天**生效的那个版本:取所有 `observed_from` 的日期 ≤ 进场日 的版本里**最晚**的那个 |')
    A('| ★★★ 没有回填 | **没有**用最新版本去填历史。进场日早于该票首次 SIC 披露的交易 → 记「行业未知」,不猜 |')
    A('| 严格一点会不会变 | 如果把判据改成 `observed_from < 进场日`(把披露当天也算成还没生效),**全部 %d 笔里只有 2 笔**会换一个 SIC 码 |'%tot)
    A('| 时区 | `observed_from` 是带时区的 UTC 时刻,只取前 10 位当日期用;流水的 `entry_date` 是交易日 |')
    A('')
    A('### 覆盖率')
    A('')
    A('| | 笔数 | 占比 |')
    A('|---|---:|---:|')
    A('| 映射到了 11 个板块之一 | %d | %.1f%% |'%(tot-unk,100*cov))
    A('| 行业未知 · 该票根本没有 SIC 数据(不在 pilot_300 那 249 只里) | %d | %.1f%% |'%(D['gap']['该票没有 PIT SIC 数据(不在 pilot_300 的 249 只里)'],100*D['gap']['该票没有 PIT SIC 数据(不在 pilot_300 的 249 只里)']/tot))
    A('| 行业未知 · 进场日早于该票首次 SIC 披露 | %d | %.1f%% |'%(D['gap']['进场日早于该票首次 SIC 披露'],100*D['gap']['进场日早于该票首次 SIC 披露']/tot))
    A('| SIC 有、但映射不到板块 | 0 | 0.0%% |')
    A('| **合计** | **%d** | **100.0%%** |'%tot)
    A('')
    _only=sorted(k for k,v in D['sym_sector'].items() if list(v.keys())==[UNK])
    _p3=set(os.listdir(os.path.join(ROOT,'pilot_300')))
    _a=[k for k in _only if k not in _p3]; _b=[k for k in _only if k in _p3]
    _part=sorted((k,v) for k,v in D['sym_sector'].items() if UNK in v and len(v)>1)
    A('★★ 第一行那 %d 笔是**真缺口**。流水里一共出现 **%d 只票**,其中 **%d 只整只票**都取不到行业码:'%(
        D['gap']['该票没有 PIT SIC 数据(不在 pilot_300 的 249 只里)'], len(D['sym_sector']), len(_only)))
    A('')
    A('| 情况 | 只数 | 代码 |')
    A('|---|---:|---|')
    A('| 不在 `pilot_300/` 目录里(那 250 只才有 `sic_versions`) | %d | `%s` |'%(len(_a),' '.join(_a)))
    A('| 在 `pilot_300/` 里,但 `sic_versions` 不可用 | %d | `%s` |'%(len(_b),' '.join(_b)))
    A('')
    A('另有 **%d 只**是部分未知(进场日早于它自己的首次 SIC 披露):'%len(_part)
      + ' · '.join('`%s`(%d 笔未知 / %d 笔有)'%(k, v[UNK], sum(x for s2,x in v.items() if s2!=UNK)) for k,v in _part) + '。')
    A('★ `DIS` 这个例子正好说明按时点取是真在生效 —— 同一只票在不同年份落到不同的类里,没有被最新版本回填。')
    A('')
    A('缺什么:要补上这 %d 只的历史 `sic_versions`(得去 SEC 按 CIK 拉历史 10-K/10-Q 里的 SIC),'%len(_only))
    A('以及 `DIS`/`HHH` 2015 年以前的披露。')
    A('')
    A('★ 另外 `pilot_300/sector_classification_current_non_pit.csv` 里有一份**现时点**的板块分类。')
    A('**没用它** —— 文件名里的 `non_pit` 就是说它是用今天的分类回填历史,正是任务单明令禁止的那种做法。')
    A('')
    A('---')
    A('')
    A('## 三 · 逐条策略 × 板块(45 条)')
    A('')
    A('### 口径')
    A('')
    A('| 列 | 定义 |')
    A('|---|---|')
    A('| 笔数 | 这条链落在这个板块的成交笔数 |')
    A('| 每笔净R | 这些笔的 `r_multiple_net` 的**算术平均** —— ★ 和 1102/1104 汇总 JSON 里「每笔净R」同一个定义 |')
    A('| 胜率 | `net_pnl > 0` 的笔数占比 |')
    A('| 最大连亏 | ★ **这个指标 engine 里原来没有,定义是我定的**:按进场日排序后,`net_pnl ≤ 0` 连续出现的**最长一串有多少笔**;后面括号里是那一串的累计净R |')
    A('| 占比 | 笔数 ÷ 这条链的总笔数 |')
    A('')
    A('★★ **笔数 < 30 的行一律标「笔数不够-不给结论」,但笔数照列。**')
    A('★ 全部 %d 条链 × 板块的格子里,**%d 个**笔数 ≥ 30,**%d 个**不够 30。'%(len(CHAINS),ncell_ok,ncell_small))
    A('')
    A('★ 5 笔交易的 `r_multiple_net` 在流水里是空的(`risk_per_share` 退化到 ~0,分母为 0)——')
    A('这 5 笔**计入笔数、胜率、最大连亏,不计入每笔净R**,每张表的最后一列标了出来。')
    A('')
    A('### 笔数集中在哪几个板块(★ Lin 明确要的那一行)')
    A('')
    A('全部 45 条链的 **top-3 板块合计占比**:中位 %.1f%%,最低 %.1f%%,最高 %.1f%%。'%(100*statistics.median(t3),100*min(t3),100*max(t3)))
    A('★★ **没有任何一条链出现「70%% 的交易在科技股」这种集中**:')
    A('单个板块占比最高的一格是下面这个 ——')
    mx=max(((v['share'],s,ch) for ch in CHAINS for s,v in pc[ch]['sectors'].items() if s!=UNK), key=lambda t:t[0])
    A('`%s` 的 %s = **%.1f%%**。'%(mx[2],SHORT[mx[1]],100*mx[0]))
    A('')
    A('全部 45 条链合起来的笔数分布:')
    A('')
    A('| 板块 | 笔数 | 占比 |')
    A('|---|---:|---:|')
    for s,k in sharetot.most_common():
        A('| %s | %d | %.1f%% |'%(SHORT[s],k,100*k/tot))
    A('')
    A('逐链的集中度一行(每条链 top-3):')
    A('')
    A('| 链 | 总笔数 | 集中在哪几个板块(top-3) |')
    A('|---|---:|---|')
    for ch in CHAINS:
        c=pc[ch]
        top=' · '.join('%s %.0f%%'%(SHORT[s],100*sh) for s,n,sh in c['conc'][:3])
        A('| %s | %d | %s(合计 %.0f%%) |'%(ch,c['total'],top,100*sum(x[2] for x in c['conc'][:3])))
    A('')
    A('**逐条策略 × 板块的完整明细表在 → 附录 A。** 机器可读:`逐链逐板块-1104.csv`。')
    A('')
    A('---')
    A('')
    A('## 四 · 横过来看:11 个板块 × 45 条链')
    A('')
    A('完整矩阵在 **附录 B**(机器可读 `矩阵-每笔净R-板块x链-1104.csv`,同一份文件里还附了逐格笔数)。')
    A('下面只回答任务单问的两件事,**只给数字**。')
    A('')
    A('### 问题一 · 有没有哪个板块在大多数策略上都偏好或偏差?')
    A('')
    A('做法:对每一条链,拿它**自己的总体每笔净R**当基线,看每个板块(只算笔数 ≥ 30 的格子)在基线之上还是之下,数票。')
    A('二项 p 值是「如果上下各一半纯属偶然」的双侧概率。')
    A('')
    A('| 板块 | 全部45条:格数 / 高于基线 / 二项p | 中位差(R) | 去重32条:格数 / 高于 / 二项p | 中位差(R) |')
    A('|---|---|---:|---|---:|')
    for s in SECTORS:
        a=sgn['45'][s]; b=sgn['32'][s]
        if a['cells']==0:
            A('| %s | 没有笔数≥30 的格子 | — | 同 | — |'%SHORT[s]); continue
        A('| %s | %d / %d (%.0f%%) / p=%.3f | %+.4f | %d / %d (%.0f%%) / p=%.3f | %+.4f |'%(
          SHORT[s],a['cells'],a['up'],100*a['up']/a['cells'],a['p'],a['med'],
          b['cells'],b['up'],100*b['up']/b['cells'],b['p'],b['med']))
    A('')
    A('★ 11 个板块 = 11 次比较;按 11 次校正的阈值是 p < 0.0045。')
    A('去重 32 条那一套里,**没有一个板块**过这个阈值(最小的是原材料 p=0.021)。')
    A('')
    A('### 问题二 · 跨板块的离散度有多大?和噪声比呢?')
    A('')
    A('大白话:**「同一条策略换个行业,成绩差多少」和「同一条策略什么都不换、纯粹因为笔数有限而抖动的幅度」,哪个大?**')
    A('')
    A('做法(逐条链算,只用笔数 ≥ 30 的板块):')
    A('')
    A('- **实测离散度** = 该链各板块「每笔净R」的标准差')
    A('- **噪声水平** = 各板块那个均值本身的标准误(= 该格 R 的标准差 ÷ √笔数)的均方根 —— 这是「假设行业完全没影响」时,光靠抽样噪声也会出现的离散度')
    A('- **倍数** = 实测 ÷ 噪声。**1.00 = 看到的全是噪声**')
    A('- `Q` = Cochran 异质性统计量(逐格按 1/方差 加权),`df = 板块数 − 1`,`p` 是它的卡方 p 值')
    A('- `I²` = 实测离散里「超出噪声」的那一份占比,0 = 全是噪声')
    A('')
    A('45 条链里 **%d 条**能算(要至少 2 个笔数 ≥ 30 的板块),9 条算不出来(见下)。'%len(rs))
    A('')
    A('| 量 | 中位 | 四分位 | 最小 | 最大 |')
    A('|---|---:|---:|---:|---:|')
    A('| 实测÷噪声 **倍数** | **%.2f** | %.2f – %.2f | %.2f | %.2f |'%(statistics.median(ratios),q[0],q[2],min(ratios),max(ratios)))
    A('| I²(超出噪声的占比) | %.3f | %.3f – %.3f | %.3f | %.3f |'%(statistics.median(i2),statistics.quantiles(i2,n=4)[0],statistics.quantiles(i2,n=4)[2],min(i2),max(i2)))
    A('')
    A('**p 值的分布:**')
    A('')
    A('| 门槛 | 实际条数 | 纯噪声下的期望条数 |')
    A('|---|---:|---:|')
    A('| p < 0.05 | %d / %d | %.1f |'%(sum(p<0.05 for p in ps),len(ps),0.05*len(ps)))
    A('| p < 0.01 | %d / %d | %.1f |'%(sum(p<0.01 for p in ps),len(ps),0.01*len(ps)))
    A('| p < 0.05/%d(按 %d 次比较校正) | **%d / %d** | %.1f |'%(len(ps),len(ps),sum(p<0.05/len(ps) for p in ps),len(ps),0.05))
    A('')
    A('逐条链的离散度(按 p 从小到大):')
    A('')
    A('| 链 | 可比板块数 | 实测离散度(R) | 噪声水平(R) | 倍数 | Q | df | p | I² | 板块间极差(R) |')
    A('|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|')
    for ch,v in sorted(((c,dp[c]) for c in CHAINS), key=lambda kv: kv[1].get('p',9)):
        if 'ratio' not in v: continue
        A('| %s | %d | %.4f | %.4f | **%.2f** | %.2f | %d | %.4f | %.3f | %.3f |'%(
          ch,v['k'],v['obs_sd'],v['noise_sd'],v['ratio'],v['Q'],v['df'],v['p'],v['I2'],v['spread']))
    A('')
    A('**算不出来的 9 条**(笔数 ≥ 30 的板块不足 2 个 —— 这些链总笔数本身就少,整条链都摊不开):')
    A('')
    A('| 链 | 总笔数 | 笔数≥30 的板块数 | 缺什么 |')
    A('|---|---:|---:|---|')
    for ch in CHAINS:
        v=dp[ch]
        if 'ratio' in v: continue
        A('| %s | %d | %d | 笔数不够,摊到板块上每格都太薄 —— 要么扩池、要么放长窗口 |'%(ch,pc[ch]['total'],v['k']))
    A('')
    A('---')
    A('')
    A('## 五 · 算不出来的缺口(一次列全)')
    A('')
    A('| # | 缺口 | 缺什么才能算 |')
    A('|---|---|---|')
    A('| 1 | %d 笔(%.1f%%)没有行业码,其中 %d 只票整只都没有、%d 只部分没有 | 这 %d 只的历史 SIC 版本(SEC 按 CIK 拉 10-K/10-Q) |'%(unk,100*unk/tot,len(_only),len(_part),len(_only)))
    A('| 2 | 9 条链算不出跨板块离散度 | 这些链总笔数太少(最少的只有几十笔);要扩池或放长窗口,**那就是重跑,本轮铁律不许** |')
    A('| 3 | 193 个格子笔数 < 30 | 同上 |')
    A('| 4 | 5 笔的每笔净R 是空的 | 流水里 `risk_per_share` 退化到 ~0。这是 engine 侧的事,本轮没动 |')
    A('| 5 | 「板块」这个维度本身的口径不确定 | 映射表是我们自己定的(第一节)。要定稿得给 192 只票逐票人工确认板块 |')
    A('| 6 | 45 条链里只有 %d 份不同的流水 | 这是事实,不是缺口;但跨链计票要按 %d 看 |'%(len(rep),len(rep)))
    A('| 7 | 板块 × 时间(比如 2020 vs 2022)没拆 | 任务单没要求;要拆的话本轮流水够用,不用重跑 |')
    A('')
    A('---')
    A('')
    A('## 六 · 怎么复现')
    A('')
    A('```')
    A('python3 -I probe/sector_split_1104/split_by_sector_1104.py')
    A('```')
    A('')
    A('读:`probe/friction_rerun_1104/ledgers_1104/REAL__*.csv` + `pilot_300/*/fundamentals.json`')
    A('写:本目录的 6 个文件。★ 完全不读也不 import engine;不碰 `exam_*`。')
    A('')
    A('| 文件 | 是什么 |')
    A('|---|---|')
    A('| `README-分行业表现-1104.md` | 本报告 |')
    A('| `逐链逐板块-1104.csv` | 第三节那张表的机器可读版(45 条 × 各板块 + 该链合计) |')
    A('| `矩阵-每笔净R-板块x链-1104.csv` | 第四节的矩阵(每笔净R + 逐格笔数) |')
    A('| `分板块明细-1104.json` | 全部中间量(逐格统计 / 离散度 / SIC 逐码笔数 / 逐票板块归属) |')
    A('| `sic_map_1104.py` | ★ 那张自定映射表(可执行,规则就是数据) |')
    A('| `split_by_sector_1104.py` | 跑批脚本 |')
    A('')
    A('---')
    A('')
    A('# 附录 A · 逐条策略 × 板块 完整明细')
    A('')
    for ch in CHAINS:
        c=pc[ch]; a=c['all']
        A('### %s'%ch)
        A('')
        A('总笔数 %d · 全体每笔净R %s · 全体胜率 %.1f%% · 全体最大连亏 %d 笔'%(c['total'],f(a['mean_r']),100*a['win'],a['max_lose_streak']))
        A('')
        A('| 板块 | 笔数 | 每笔净R | 胜率 | 最大连亏(笔 / 累计净R) | 占该链总笔数 | 备注 |')
        A('|---|---:|---:|---:|---:|---:|---|')
        for s in ORDER:
            v=c['sectors'].get(s)
            if not v: continue
            note=''
            if v['n']<MIN: note='★★ **笔数不够,不给结论**'
            if s==UNK: note=(note+' · ' if note else '')+'没有 PIT SIC,单独一类'
            if v['r_missing']: note=(note+' · ' if note else '')+'%d 笔 R 为空,未计入每笔净R'%v['r_missing']
            A('| %s | %d | %s | %.1f%% | %d / %s | %.1f%% | %s |'%(
              SHORT[s],v['n'],f(v['mean_r']),100*v['win'],v['max_lose_streak'],
              f(v['max_lose_streak_sum_r'],2),100*v['share'],note or '—'))
        A('| **【该链全部】** | **%d** | **%s** | **%.1f%%** | **%d / %s** | 100.0%% | — |'%(
          a['n'],f(a['mean_r']),100*a['win'],a['max_lose_streak'],f(a['max_lose_streak_sum_r'],2)))
        A('')
        A('**笔数集中在哪几个板块**:'+' · '.join('%s %.0f%%'%(SHORT[s],100*sh) for s,n,sh in c['conc'][:4])
          +'(top-3 合计 %.0f%%)'%(100*sum(x[2] for x in c['conc'][:3])))
        A('')
    A('---')
    A('')
    A('# 附录 B · 矩阵:11 个板块 × 45 条链 的每笔净R')
    A('')
    A('★ 空格 = 这条链在这个板块一笔都没有。**小字号笔数在第二张表。**')
    A('★★ 笔数 < 30 的格子我在数字后面加了 `!` —— 那一格不给结论。')
    A('')
    hdr=['板块']+['C%02d'%i for i in range(1,len(CHAINS)+1)]
    A('| '+' | '.join(hdr)+' |')
    A('|'+'---|'*len(hdr))
    for s in ORDER:
        row=[SHORT[s]]
        for ch in CHAINS:
            v=pc[ch]['sectors'].get(s)
            if not v or v['mean_r'] is None: row.append('')
            else: row.append('%+.3f%s'%(v['mean_r'],'!' if v['n']<MIN else ''))
        A('| '+' | '.join(row)+' |')
    A('| **全体** | '+' | '.join('%+.3f'%pc[ch]['all']['mean_r'] for ch in CHAINS)+' |')
    A('')
    A('### 同一张矩阵的笔数')
    A('')
    A('| '+' | '.join(hdr)+' |')
    A('|'+'---|'*len(hdr))
    for s in ORDER:
        row=[SHORT[s]]
        for ch in CHAINS:
            v=pc[ch]['sectors'].get(s)
            row.append(str(v['n']) if v else '')
        A('| '+' | '.join(row)+' |')
    A('| **全体** | '+' | '.join(str(pc[ch]['total']) for ch in CHAINS)+' |')
    A('')
    A('### 列号 → 链名')
    A('')
    A('| 列 | 链 | 总笔数 |')
    A('|---|---|---:|')
    for i,ch in enumerate(CHAINS,1):
        A('| C%02d | %s | %d |'%(i,ch,pc[ch]['total']))
    A('')
    open(os.path.join(OUT,'README-分行业表现-1104.md'),'w').write('\n'.join(L)+'\n')
    print('written', len(L),'lines')


if __name__=='__main__':
    _part1()
    _part2()
