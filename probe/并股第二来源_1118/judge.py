#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""手册 305 / 100 · 给每个「跳变」事件定性:是并股 / 不是并股 / 查不到

大白话:
  · 先看我们自己的日线里那天有没有拆股系数、能不能把跳变解释掉 —— 能的话,引擎本来就会折算,不算问题(「已折算」)。
  · 解释不掉的,拿 SEC 公告全文(8-K / 6-K / 10-Q / 10-K / 委托书)里的句子找「1-for-20 reverse stock split」这类原文,
    比例和当天价格跳的倍数对得上(差 35% 以内)、公告日期在跳变前后合理范围 → 「是并股」,来源写公告链接。
  · Polygon 拆股表(按当时的老代码查)也查一遍,只当参考,不单独作为来源。
  · SEC 两百天窗口里一个字都没提并股,且这一天是放量的真行情 → 「不是并股」;其余 → 「查不到」。比例绝不猜。
用法:python3 judge.py sec_results.json polygon_splits.json
"""
import csv, json, math, os, re, sys
from datetime import date, timedelta

W = {'one': 1, 'two': 2, 'three': 3, 'four': 4, 'five': 5, 'six': 6, 'seven': 7, 'eight': 8, 'nine': 9, 'ten': 10, 'eleven': 11,
     'twelve': 12, 'fifteen': 15, 'twenty': 20, 'twenty-five': 25, 'thirty': 30, 'forty': 40, 'fifty': 50, 'sixty': 60,
     'seventy': 70, 'eighty': 80, 'hundred': 100}
N = r'(\d[\d,]*(?:\.\d+)?|' + '|'.join(sorted(W, key=len, reverse=True)) + r')'
PAT = [re.compile(N + r'\s*(?:\(\s*\d[\d,]*\s*\)\s*)?[-\s]?(?:for|into)[-\s]?\s*' + N + r'(?:\s*\(\s*\d[\d,]*\s*\))?', re.I),
       re.compile(r'\b(1|one)\s*:\s*' + N + r'\b(?!\s*(?:a\.?m|p\.?m|noon|eastern|et\b))', re.I),
       re.compile(r'(?:every|each)\s+' + N + r'\s*(?:\(\s*\d[\d,]*\s*\)\s*)?(?:shares|ordinary shares|common shares|issued)', re.I)]


def val(x):
    x = x.lower().replace(',', '')
    return float(W[x]) if x in W else float(x)


def ratios(s):
    """从一段话里找并股比例,返回「新股数 : 旧股数」里的 旧/新 倍数(1-for-20 → 20)"""
    out = []
    s2 = re.sub(r'&#\d+;|&#x[0-9a-f]+;', ' ', s, flags=re.I)
    for p in PAT[:2]:
        for m in p.finditer(s2):
            try:
                a, b = val(m.group(1)), val(m.group(2))
            except Exception:
                continue
            if a <= 0 or b <= 0: continue
            k = max(a, b) / min(a, b)
            if 1.5 <= k <= 5000 and not (a > 1900 and a < 2100) and not (b > 1900 and b < 2100):
                out.append((k, m.group(0)))
    for m in PAT[2].finditer(s2):
        try:
            k = val(m.group(1))
        except Exception:
            continue
        if 1.5 <= k <= 5000: out.append((k, m.group(0)))
    return out


def main(secf, polyf):
    import os
    R = list(csv.DictReader(open(os.environ.get('EVENTS', '待核事件_1118.csv'), encoding='utf-8-sig')))
    SR = json.load(open(secf)); PS = json.load(open(polyf))
    if os.environ.get('PS2'): PS.update(json.load(open(os.environ['PS2'])))
    if R and '候选序号' in R[0]:
        SR = {str(i): SR[r['候选序号']] for i, r in enumerate(R) if r['候选序号'] in SR}
    import gzip
    cache = {}
    def true_jump(sym, d):
        if sym not in cache: cache[sym] = json.load(gzip.open(f'/home/claude/stock_data/market_ext_1105/{sym}/daily.json.gz'))['data']
        D = cache[sym]; ix = {x['date']: k for k, x in enumerate(D)}; k0 = ix[d]
        best = None
        for k in range(max(1, k0 - 6), min(len(D), k0 + 7)):
            p, c = D[k-1]['close'], D[k]['close']
            if p and c:
                v = abs(math.log(c / p))
                if best is None or v > best[0]: best = (v, k)
        k = best[1]; return D[k]['date'], D[k]['close'] / D[k-1]['close'], (D[k]['open'] or D[k]['close']) / D[k-1]['close'], D[k-1]['date'], D[k].get('split_coefficient')
    out = []
    for i, r in enumerate(R):
        jump = float(r['单日收盘比']); wpr = float(r['窗口价比']) if r['窗口价比'] else jump
        vr = float(r['股数量比']) if r['股数量比'] else None
        if not r['已解释']:
            td, jump, ojump, prevd, coef = true_jump(r['代码'], r['日期'])
            if coef not in (None, 1, 1.0) and ((coef < 1) == (jump > 1)):
                r = dict(r, 已解释='same_day', 残差=jump * coef)
        else:
            td, ojump, prevd = r['日期'], jump, ''
        rev = jump > 1  # 价往上跳 = 并股方向
        k_obs = jump if rev else 1 / jump
        d0 = date.fromisoformat(td)
        res = dict(代码=r['代码'], 日期=td, 标记日=r['日期'], 前一根K线日=prevd, 源头代码=r['源头代码'], cik=r['cik'], 单日收盘比=jump, 窗口价比=r['窗口价比'],
                   股数量比=r['股数量比'], 判据=r['判据'], 来自名单=r['来自名单'])
        if r['已解释']:
            res.update(结论='已折算' if r['已解释'] == 'same_day' else '有系数但日期错位', 比例='', 来源='market_ext_1105 daily.json split_coefficient',
                       备注=('源头系数和跳变同一天,引擎会折算' + (f";折算后当天还剩 {r['残差']:.2f} 倍,是并股当天的真实涨跌" if r.get('残差') and abs(math.log(r['残差'])) > math.log(1.6) else '') if r['已解释'] == 'same_day' else f"源头系数在 {r['已解释'][10:]},价格真正跳在 {r['日期']}"))
            out.append(res); continue
        # Polygon(按老代码 / 新代码都查)
        pol = []
        for t in {r['代码'], r['源头代码']}:
            for ed, f, to in PS.get(t, []):
                edd = date.fromisoformat(ed)
                lo = date.fromisoformat(prevd) if prevd else d0
                if abs((edd - d0).days) <= 10 or (lo - timedelta(days=5) <= edd <= d0):
                    pol.append((t, ed, f, to))
        # SEC
        s = SR.get(str(i))
        cands = []
        if s:
            for doc in s['docs']:
                fd = date.fromisoformat(doc['date'])
                for sn in doc['snips']:
                    if sn.startswith('ERR'): continue
                    low = sn.lower()
                    is_fwd = ('reverse' not in low and 'consolidat' not in low and ('split' in low or 'stock dividend' in low))
                    for k, txt in ratios(sn):
                        cands.append(dict(k=k, txt=txt, form=doc['form'], fd=fd, url=doc['url'], fwd=is_fwd, sn=sn))
        best = None; weak = []
        polk = {round(f / to, 3) if rev else round(to / f, 3) for (_, ed, f, to) in pol}
        for c in cands:
            if (not rev) != c['fwd']:  # 方向:并股找 reverse,拆股找 forward
                continue
            err = abs(math.log(c['k'] / k_obs))
            lag = (d0 - c['fd']).days
            pol_same = any(abs(math.log(c['k'] / pk)) < 0.02 for pk in polk if pk > 0)
            # 价格对得上(差 35% 内);或者 SEC 和 Polygon 两家比例一致、而且实测跳幅落在「比例 ÷4 ~ 比例 ×1.35」之间
            #(仙股并股当天常常再跌一大截,所以只放宽往下的一侧)
            # 收紧(全池这轮加的):没有 Polygon 佐证时,只认跳变前 90 天~后 20 天内的 8-K / 6-K(公告当期事件的文件);
            # 招股书、年报、委托书里常常提到很早以前的拆股,单靠它们会误配
            strong = c['form'] in ('8-K', '6-K', '8-K/A', '6-K/A') and -20 <= lag <= 90
            # 公告里的比例如果正好是 Polygon 记在别的日子的那次拆股(离这次跳变 15 天以上),多半说的是那一次,不认
            elsewhere = any(abs(math.log((f / to if rev else to / f) / c['k'])) < 0.02 and abs((date.fromisoformat(ed) - d0).days) > 15
                            and (t, ed, f, to) not in pol for t in {r['代码'], r['源头代码']} for ed, f, to in PS.get(t, []) if f > 0 and to > 0)
            if elsewhere and not pol_same:
                continue
            if rev:   # 往上跳:并股。比例对得上、文件日期合理即可(大涨正好等于公告比例,巧合的可能很小)
                ok = (err <= math.log(1.35) and (pol_same or -20 <= lag <= 90)) or (pol_same and c["k"] / 4 <= k_obs <= c["k"] * 3 and k_obs >= 1.5)
            else:     # 往下跳:正向拆股。暴跌一半正好碰上「2-for-1」的巧合多,只认当期 8-K/6-K 或 Polygon 佐证
                ok = (err <= math.log(1.35) and (pol_same or strong)) or (pol_same and c["k"] / 4 <= k_obs <= c["k"] * 3 and k_obs >= 1.5)
            if not ok and err <= math.log(1.35) and -20 <= lag <= 200:
                weak.append(c)
            if ok and -20 <= lag <= 200:
                sc = (err, 0 if c['form'] in ('8-K', '6-K', '8-K/A') else 1, abs(lag))
                if best is None or sc < best[0]: best = (sc, c)
        if best and polk and not any(abs(math.log(best[1]['k'] / pk)) < 0.02 for pk in polk if pk > 0):
            c = best[1]
            res.update(结论='查不到', 比例='', 来源=c['url'],
                       备注=f"两家来源比例不一致:SEC {c['form']} {c['fd']} 写「{c['txt']}」,Polygon 写 {pol[0][2]:g}→{pol[0][3]:g};实测跳 {k_obs:.2f} 倍 —— 不猜,请人工看公告")
            out.append(res); continue
        if best:
            c = best[1]; k = c['k']; kk = int(round(k)) if abs(k - round(k)) < 0.05 else round(k, 3)
            res.update(结论='是并股' if rev else '是拆股', 比例=(f'1:{kk}' if rev else f'{kk}:1'),
                       来源=c['url'], 备注=f"SEC {c['form']} {c['fd']} 原文「{c['txt']}」;实测跳 {k_obs:.2f} 倍" +
                       (f";Polygon 也有({pol[0][0]} {pol[0][1]} {pol[0][2]:g}→{pol[0][3]:g})" if pol else ";Polygon 拆股表没有这一条") + (";⚠ 当天另有大幅涨跌,实测跳幅和比例差超过 35%" if abs(math.log(k / k_obs)) > math.log(1.35) else "") + (";⚠ Polygon 的比例和 SEC 不一样" if polk and not any(abs(math.log(k / pk)) < 0.02 for pk in polk if pk > 0) else ""))
        else:
            any_mention = bool(s) and any(doc['snips'] for doc in s['docs'])
            pol_any = bool(pol)
            src0 = 'SEC 全文检索(跳变前 200 天~后 15 天)没有对得上的并股/拆股公告;Polygon 拆股表前后 10 天也没有' if not pol_any else ''
            if r['判据'] == 'P' and abs(math.log(jump)) < math.log(1.5):
                res.update(结论='不用折算', 比例='', 来源='Polygon 拆股表(单一来源)',
                           备注=f"Polygon 记了 {pol[0][1] if pol else ''} {pol[0][2]:g}→{pol[0][3]:g} 的拆股,但我们日线那几天价格没跳(单日 {jump:.2f} 倍)—— 多半是合并、分拆、换股这类,或者价格本来就按新股数记的;照 Polygon 折反而会造出假跳变" if pol else f"价格没跳(单日 {jump:.2f} 倍)")
            elif weak:
                pass
            elif not rev and not pol_any:
                res.update(结论='不是并股', 比例='', 来源=src0,
                           备注=f"价格是往下跳(单日 {jump:.2f} 倍),并股只会让价格往上跳;两处都没有拆股记录 → 真跌" + (f",股数量比 {vr}" if vr else ''))
            elif rev and not pol_any and vr is not None and vr >= 1.5:
                res.update(结论='不是并股', 比例='', 来源=src0,
                           备注=f"价格往上跳 {jump:.2f} 倍同时股数成交量放大 {vr} 倍;并股一定让股数量缩小 → 真涨")
            elif s and s['n'] == 0 and not pol_any:
                res.update(结论='不是并股', 比例='', 来源=src0.replace('没有对得上的', '0 篇提到'),
                           备注=f"美国上市公司并股必须发公告,SEC 全文里一篇都没有、Polygon 也没有;实测单日 {jump:.2f} 倍" + (f",股数量比 {vr}" if vr else ''))
            elif rev and not pol_any and jump < 3 and 'C' not in r['判据']:
                res.update(结论='不是并股', 比例='', 来源=src0,
                           备注=f"前后 6 个交易日里最大的单日涨幅只有 {jump:.2f} 倍,是几天累计的走势或数据断档,不是一次性跳变")
            if weak or res.get('结论') is None:
                why = []
                if not s: why.append('SEC 没查(出错)')
                elif s['n'] == 0: why.append('SEC 200 天窗口里没有任何公告提到并股')
                elif weak: why.append(f"SEC 只有旁证:{weak[0]['form']} {weak[0]['fd']} 写「{weak[0]['txt']}」(不是当期 8-K/6-K,Polygon 也没有,可能说的是更早那次)")
                else: why.append(f"SEC 有 {s['n']} 篇提到并股,但没有比例和日期都对得上的" + ('(提到的比例:' + ','.join(sorted({f'{c["k"]:g}' for c in cands})[:6]) + ')' if cands else ''))
                if pol: why.append(f"Polygon 有 {pol[0][0]} {pol[0][1]} {pol[0][2]}→{pol[0][3]}(单一来源,不填)")
                why.append(f"实测单日 {jump:.2f} 倍,股数量比 {vr}")
                res.update(结论='查不到', 比例='', 来源='', 备注=';'.join(why))
        out.append(res)
    return out


if __name__ == '__main__':
    o = main(*sys.argv[1:3])
    from collections import Counter
    print(Counter(x['结论'] for x in o))
    json.dump(o, open(os.environ.get('OUTJ', 'judged.json'), 'w'), ensure_ascii=False)
