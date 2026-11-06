#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 81 · C1 · 退市股怎么结算(免费版,代替 CRSP delisting returns)

大白话:
  行情库里「最后一根 K 线早于 2026-11-04」的票,逐只到 SEC 申报记录里找「为什么没了」:
    ① data_truncated   —— 不是退市,是我们的数据截断了(取不到清单里「结束日之后同一家还在交易」那 25 只)
    ② bankruptcy       —— 退市前 2 年 ~ 退市后 400 天内交过 8-K 第 1.03 项(破产 / 重整)
    ③ acquisition      —— 退市前后交过 8-K 第 2.01 项(完成收购 / 处置)或第 5.01 项(控制权变更),
                          或者退市前一年内有合并投票材料(DEFM14A / PREM14A)、要约收购(SC TO-T / SC 14D9),而且没有 1.03
    ④ exchange_delisted —— 交易所因为不达标摘牌:退市前 400 天内有 8-K 第 3.01 项(收到退市通知),没有收购证据
       (只认最后收盘 < 5 美元的;价格还高的多半是转板,归到下面)
    ⑤ 证据不硬的再看最后收盘价(外国公司不交 8-K;换股收购的 S-4 是收购方交的,所以常常找不到收购证据):
       · acquisition_likely  —— 有退市 / 注销申报、最后收盘 ≥ 5 美元 → 多半被收购或转板,按最后收盘
       · performance_likely  —— 最后收盘 < 1 美元 → 按 Shumway 近似
       · voluntary_or_other  —— 有退市 / 注销申报,价格在 1~5 美元之间,判不了
       · unknown             —— 什么都没找到

  建议的退市收益(最后一根 K 线收盘之后,还要再乘的那一下):
    · ① 不结算(数据还没完)
    · ③ 0%:按最后收盘结算 —— 收购通常是现金或换股,最后收盘已经贴着成交价
    · ② ④ 用 Shumway(1997, JF)和 Shumway & Warther(1999, JF)的做法:业绩原因退市、又查不到退市后价格的,
        纽交所 / 美交所 -30%,纳斯达克 -55%(这是**行业近似**,不是逐只核过的值,标 ②档)
    · ⑤ 里判不了的两种留空:证据不够,不给数(用的人自己决定按最后收盘还是按 Shumway);推断出来的两种给数但标 low
  考卷那 23 只破产股是逐只读过 8-K 原文的(有的明确为 0),这里**不覆盖考卷**。

用法:python3 delisting_outcomes.py market_ext_dir out.csv
"""
import csv, gzip, json, os, sys
from datetime import date, timedelta

SUB = '/home/claude/fx/sub_all.json.gz'


def dd(x, n): return (date.fromisoformat(x) + timedelta(days=n)).isoformat()


def main(mdir, out):
    S = json.load(gzip.open(SUB))
    man = {r['symbol']: r for r in csv.DictReader(open(os.path.join(mdir, 'manifest.csv')))}
    det = {r['symbol']: r for r in csv.DictReader(open(os.path.join(mdir, 'manifest_detail.csv')))}
    trunc = {r['symbol'] for r in csv.DictReader(open(os.path.join(mdir, 'unavailable.csv'))) if r['stage'] == 'partial' and '后段没给' in r['reason']}
    rows = []
    for s, m in sorted(man.items()):
        if m['delisted'] != 'true': continue
        cik = det[s]['cik']; E = m['delisting_date']; f = S.get(cik, {}).get('f', [])
        def k8(item, lo, hi):
            return [x for x in f if x[1].startswith('8-K') and lo <= x[2] <= hi and item in (x[4] or '').split(',')]
        def forms(prefixes, lo, hi):
            return [x for x in f if x[1].startswith(prefixes) and lo <= x[2] <= hi]
        ev = lambda xs: '; '.join(f'{x[1]} {x[2]} items={x[4]} {x[0]}' if x[4] else f'{x[1]} {x[2]} {x[0]}' for x in xs[:3])
        b = k8('1.03', dd(E, -730), dd(E, 400))
        acq = k8('2.01', dd(E, -45), dd(E, 90)) + k8('5.01', dd(E, -45), dd(E, 90))
        acq2 = forms(('DEFM14A', 'PREM14A', 'SC TO-T', 'SC 14D9', 'DEFM14C', 'S-4'), dd(E, -400), dd(E, 30))
        dn = k8('3.01', dd(E, -400), dd(E, 30))
        vol = forms(('25', '15-12', '15-15', '15F'), dd(E, -30), dd(E, 120))
        exch = (m['exchange'] or '').upper()
        lc = float(det[s]['last_close'] or 0)
        nasdaq = 'NASDAQ' in exch
        if s in trunc: cat, evd, ret, basis, conf = 'data_truncated', '取不到清单:结束日之后同一家还在交易', '', '不结算:数据截断,不是退市', 'high'
        elif b: cat, evd = 'bankruptcy', ev(b); ret = -0.55 if nasdaq else -0.30; basis = 'Shumway 1997 / Shumway & Warther 1999 近似(②档)'; conf = 'medium'
        elif acq or acq2:
            cat, evd, ret, basis = 'acquisition', ev(acq + acq2), 0.0, '按最后收盘结算(收购价已反映在最后收盘)'
            conf = 'high' if acq else 'medium'
        elif dn and lc < 5: cat, evd = 'exchange_delisted', ev(dn); ret = -0.55 if nasdaq else -0.30; basis = 'Shumway 1997 / Shumway & Warther 1999 近似(②档)'; conf = 'medium'
        # 下面三种证据都不硬:外国公司(20-F)不交 8-K,换股收购的 S-4 是收购方交的 —— 所以再看一眼最后收盘价
        elif lc >= 5 and (vol or dn): cat, evd, ret, basis, conf = 'acquisition_likely', ev(vol + dn), 0.0, '推断:有退市 / 注销申报、最后收盘 ≥ 5 美元,多半是被收购或转板;按最后收盘', 'low'
        elif lc < 1: cat, evd = 'performance_likely', ev(vol + dn); ret = -0.55 if nasdaq else -0.30; basis = '推断:最后收盘 < 1 美元;按 Shumway 近似(②档)'; conf = 'low'
        elif vol or dn: cat, evd, ret, basis, conf = 'voluntary_or_other', ev(vol + dn), '', '证据不够,不给数', 'low'
        else: cat, evd, ret, basis, conf = 'unknown', '', '', '证据不够,不给数', 'low'
        rows.append([s, cik, E, det[s]['last_close'], m['exchange'], cat, ret, basis, conf, evd])
    with open(out, 'w', newline='') as fh:
        w = csv.writer(fh)
        w.writerow(['symbol', 'cik', 'last_bar', 'last_close', 'exchange', 'category', 'suggested_delisting_return', 'return_basis', 'confidence', 'sec_evidence'])
        w.writerows(rows)
    from collections import Counter
    print(len(rows), Counter(r[5] for r in rows), Counter((r[5], r[8]) for r in rows))


if __name__ == '__main__':
    main(*sys.argv[1:])
