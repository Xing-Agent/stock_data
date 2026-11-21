# -*- coding: utf-8 -*-
"""《242》⑧ 重考用：补算「商誉+无形 / 总资产」这个新口径（卡 v0.1 改过的那条排雷）。
为什么要单独一个脚本：fa.py 只输出 gw_over_eq（商誉/净资产），
而卡 120~121 行改成「商誉+无形占总资产 > 40% 才算命中」+「先看是不是回购造成的」
→ 新口径那个数**从来没算过**，不补算就没法判 FTDR / KO 到底翻不翻。
只读数据，不跑批。用法：python3 probe/基本面大师考试_1121/补算_商誉总资产口径_1121.py KODK NVDA FTDR KO INTC
"""
import sys, os
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, '..', '..'))
sys.path.insert(0, HERE)
import fa
fa.R = ROOT + '/'          # fa.py 里写死的那个旧数据根目录本容器不存在（闸⑪ 那条），改成按本脚本位置自推仓库根

def one(t):
    f, _ = fa.load(t)
    gw,  _ = fa.g(f, 'Goodwill')
    ia,  _ = fa.g(f, 'IntangibleAssetsNetExcludingGoodwill')
    at, ape = fa.g(f, 'TotalAssets')
    eq, epe = fa.g(f, 'StockholdersEquity')
    ts,  _ = fa.g(f, 'TreasuryStockValue', 'TreasuryStockCommonValue')  # 本数据集没有这个标签 -> 必然 None
    gwia2, _ = fa.g(f, 'IntangiblesAndGoodwill')
    gwia = gwia2 if gwia2 else (gw or 0) + (ia or 0)
    return dict(t=t, bal_period_end=epe, assets_period_end=ape,
                goodwill_bn=gw and gw/1e9, intangible_bn=ia and ia/1e9,
                assets_bn=at and at/1e9, equity_bn=eq and eq/1e9,
                treasury_bn=ts and ts/1e9,
                gw_ia_bn=gwia/1e9, gw_ia_over_assets=gwia/at if at else None,  # 新口径（卡 120 行）
                gw_over_eq=gw/eq if gw and eq else None)       # 旧口径（误杀过 FTDR/KO）

if __name__ == '__main__':
    for t in sys.argv[1:] or ['KODK','NVDA','FTDR','KO','INTC']:
        try:
            o = one(t)
        except Exception as e:
            print('=====', t, ' 取数失败:', type(e).__name__, e); continue
        print('=====', t)
        for k, v in o.items():
            print(f'  {k}: {round(v,4) if isinstance(v,float) else v}')
