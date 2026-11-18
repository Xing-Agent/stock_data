#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 312 附带一项:同一代码中间断档 → 定性 + 处理建议
依据:Polygon 代码详情(断档前后两个日子各查一次 CIK / 公司名)、Polygon 日线在断档期间有没有 K 线(全部 0 根)、
我们日线的 company_id(company_segments)、接上那天的价格比和拆股系数。"""
import csv
G = list(csv.DictReader(open('全池断档_1118.csv', encoding='utf-8-sig')))
CUT = {  # 要切开的:代码 → (类别, 依据)
 'TLN': ('同一家公司退市后重新上市(中间破产重整)', '同一 CIK 1622536;2016-12 被私有化退市,2023 年破产重整,2024-07 新股重新上市;Polygon company_id 28097→28098'),
 'BTE': ('同一家公司退市后重新上市', '同一 CIK 1279495(Baytex);2020-12 从纽交所摘牌(期间只在多伦多交易),2023-02 重新在纽交所上市;Polygon company_id 4301→4302'),
 'SMCI': ('同一家公司退市后重新上市', '同一 CIK 1375365;2018-08 因财报延迟被纳斯达克摘牌,2020-01 重新上市;Polygon company_id 26153→26154'),
 'GTX': ('同一家公司退市后重新上市(中间破产重整)', '同一 CIK 1735707(Garrett Motion);2020-09 申请破产后摘牌,2021-04 重整完成、2021-05-03 在纳斯达克重新上市;Polygon company_id 12764→12765'),
 'HTZ': ('同一家公司退市后重新上市(中间破产重整)', '同一 CIK 1657853(Hertz);2020-10 从纽交所摘牌,2021-06 重整完成,2021-11-09 重新上市;Polygon company_id 13775→13776'),
 'CHRD': ('破产重组:老股注销换新股', 'OAS(Oasis)2020-11-19 重整完成,老股注销;Polygon company_id 20864→20865(并股表里也已标「破产重组」)'),
 'CRC': ('破产重组:老股注销换新股', 'California Resources 2020-10 重整完成,老股注销;Polygon company_id 6448→6449'),
 'SD': ('破产重组:老股注销换新股', 'SandRidge 2016-10 重整完成,老股注销;Polygon company_id 25413→25414'),
 'DYN__1379895': ('破产重组:老股注销换新股', 'Dynegy 2012-10 重整完成,老股注销;接上后价格是断前的 33 倍'),
 'SAN': ('另一家公司用了旧代码', 'Polygon 代码详情:断前 CIK 1027552「BANCO SANTANDER-CHILE ADS」,接上后 CIK 891478(Banco Santander SA);价格从 83.66 变成 6.22'),
 'NUAN': ('另一家公司用了旧代码', 'Polygon 代码详情:断前 CIK 1102556(旧 Nuance,2005-09 被收购),接上后 CIK 1002517(ScanSoft 改名 Nuance 后接过这个代码)'),
 'ARGO': ('合并后换成另一家公司的股票', 'Polygon 代码详情:断前 CIK 800082 Argonaut Group,接上后 CIK 1091748 Argo Group(2007-08 与 PXRE 合并成新控股公司)'),
}
out = []
for g in G:
    s = g['代码']; r = float(g['接上后收盘']) / float(g['断前收盘'])
    base = {k: g[k] for k in ('代码', '断档前最后一天', '接上的第一天', '断了多少个交易日', '断前收盘', '接上后收盘')}
    base['接上后÷断前'] = round(r, 3)
    if s in CUT:
        cat, why = CUT[s]; act = '切开:断档前后当成两只票,回测不许跨断档持仓'
    elif r > 1.6 or r < 0.65:
        cat = '数据缺一段,而且中间有拆股/并股'; act = '先按并股事件表折算(这类都已放进全池并股核查);数据补不了,回测不许跨断档持仓'
        why = 'Polygon 断档期间 0 根 K 线(Polygon 自己也缺这一段,补不了);同一 CIK;接上后价格跳了 %.1f 倍,和拆股方向一致' % r
    else:
        cat = '数据缺一段'; act = '补不了(Polygon 断档期间也是 0 根 K 线);价格前后接得上,回测不许跨断档持仓即可'
        why = 'Polygon 断档期间 0 根 K 线;同一 CIK;接上后价格变化 %+.0f%%' % ((r - 1) * 100)
        if g['断前代码'] != s and g['断前收盘'] and 9 < float(g['断前收盘']) < 11:
            why += ';SPAC 空壳期,价格在 10 美元左右不动'
    base.update(类别=cat, 处理=act, 依据=why)
    out.append(base)
with open('/home/claude/stock_data/market_ext_1105/代码中间断档_全池_1118.csv', 'w', newline='', encoding='utf-8-sig') as fh:
    w = csv.DictWriter(fh, fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
from collections import Counter
print(len(out), Counter(o['类别'] for o in out))
