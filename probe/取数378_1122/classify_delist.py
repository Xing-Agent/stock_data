#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 378 第 1 样:给每只退市股标「怎么退的」。来源 SEC EDGAR 每家公司的申报记录(data.sec.gov submissions),
只看最后交易日前 400 天到后 200 天之间的申报,按下面的次序判,先命中先算:
  1. 破产:8-K 里有 1.03 项(破产或接管)
  2. 私有化:有 SC 13E3(大股东 / 管理层把公司买回去下市)
  3. 被收购:有并购委托书(DEFM14A / DEFM14C / PREM14A)、要约收购(SC TO-T、SC 14D9)、
     或 8-K 里有 5.01 项(控制权变更),或 2.01 + 3.01 同时出现(交易完成 + 下市通知)
  4. 不达标被摘牌:8-K 里有 3.01 项(收到交易所下市通知 / 不满足上市条件),上面都没有
  5. 主动下市或注销:公司自己交了 Form 25 或 Form 15,上面都没有
  6. 不知道:SEC 里没这家公司,或者窗口里上面这些都没有
被收购里现金和换股没分开(SEC 的申报类型分不出来)。
用法:python3 classify_delist.py SEC.json 总表.csv OUT.csv"""
import csv, json, sys
from collections import Counter

sec, tbl, out = sys.argv[1:4]
S = json.load(open(sec))
# 没有 CIK 的几只(标普补充里 Polygon 参考库没有的),只标公开报道里没有争议的
MANUAL = {
    'BSC': ('被收购', '2008 年摩根大通收购贝尔斯登(换股)'),
    'WM__200809': ('破产', '2008-09 WaMu 银行被 FDIC 接管、控股公司申请破产'),
    'WB__200812': ('被收购', '2008 年富国银行收购 Wachovia(换股)'),
    'GM__200906': ('破产', '2009-06 通用汽车申请破产保护'),
    'CIT__200911': ('破产', '2009-11 CIT 申请预包装破产'),
    'CC__200811': ('破产', '2008-11 Circuit City 申请破产保护'),
    'DAL__200510': ('破产', '2005-09 达美航空申请破产保护'),
    'CPN__200512': ('破产', '2005-12 Calpine 申请破产保护'),
    # 银行本身(不是控股公司)的报告交给 FDIC、不交 SEC,所以 SEC 里查不到
    'FRC': ('破产', '2023-05-01 First Republic Bank 被 FDIC 接管,随后卖给摩根大通;股东基本归零'),
    'SBNY': ('破产', '2023-03-12 Signature Bank 被纽约州监管关闭、FDIC 接管;股东基本归零'),
    'FRE': ('不达标被摘牌', '2008-09 被政府接管(conservatorship),2010-07 因股价长期低于 1 美元被纽交所摘牌,转场外'),
}


def judge(rec):
    f = rec['f']
    forms = Counter(x[0] for x in f)
    items = set()
    for x in f:
        if x[0].startswith('8-K') and x[2]: items.update(i.strip() for i in x[2].split(','))
    ev = []
    if '1.03' in items: return '破产', '8-K 1.03'
    if forms.get('SC 13E3') or forms.get('SC 13E3/A'): return '私有化', 'SC 13E3'
    for k in ('DEFM14A', 'DEFM14C', 'PREM14A', 'SC TO-T', 'SC 14D9'):
        if any(x[0].startswith(k) for x in f): ev.append(k)
    if '5.01' in items: ev.append('8-K 5.01')
    if '2.01' in items and '3.01' in items: ev.append('8-K 2.01+3.01')
    if ev: return '被收购', ';'.join(ev)
    if '3.01' in items: return '不达标被摘牌', '8-K 3.01'
    if any(x[0] in ('25', '25/A') for x in f) or any(x[0].startswith('15') for x in f):
        return '主动下市或注销', ';'.join(sorted({x[0] for x in f if x[0] in ('25', '25/A') or x[0].startswith('15')}))
    return '不知道', '窗口里没有可判断的申报'


rows = list(csv.DictReader(open(tbl, encoding='utf-8-sig')))
res = []
for r in rows:
    if r['交易天数'] in ('', '0'): continue
    c = (r.get('cik') or '').lstrip('0')
    if r['代码'] in MANUAL:
        how, why = MANUAL[r['代码']]; src = '人工(公开报道)'
    elif not c:
        how, why, src = '不知道', '没有 CIK,查不了 SEC', ''
    elif c not in S or not isinstance(S[c], dict):
        how, why, src = '不知道', 'SEC 里查不到这家公司', ''
    else:
        how, why = judge(S[c]); src = 'SEC EDGAR'
    note = ''
    if how == '被收购' and r['最后收盘价'] and float(r['最后收盘价']) < 1:
        note = '最后收盘价不到 1 美元:多半是「反向并购」(没钱的小公司被私人公司借壳),不是溢价收购,做空测试里要当心'
    if how == '不达标被摘牌' and r['最后收盘价'] and float(r['最后收盘价']) >= 5:
        note = '股价不低却收到不达标通知:可能是迟交财报之类,之后可能还有别的结局'
    res.append(dict(备注=note, 代码=r['代码'], 公司名=r['公司名'] or (S.get(c, {}).get('n', '') if isinstance(S.get(c), dict) else ''), cik=c,
                    最后交易日=r['最后交易日'], 最后收盘价=r['最后收盘价'], 怎么退的=how, 依据=why, 来源=src))
with open(out, 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(res[0])); w.writeheader(); w.writerows(res)
c = Counter(x['怎么退的'] for x in res)
print(len(res), c.most_common())
by = Counter((x['最后交易日'][:4], x['怎么退的']) for x in res)
for y in range(2005, 2026):
    print(y, {k: by[(str(y), k)] for k in ['破产', '被收购', '私有化', '不达标被摘牌', '主动下市或注销', '不知道']})
