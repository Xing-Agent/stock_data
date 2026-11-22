# -*- coding: utf-8 -*-
"""核查：把截止日放到 2026-11-19，看脚本能不能认出 Lin《394》这次的半导体空单（数据里用 SMH 代替 SOXX）。"""
import sys; sys.path.insert(0,'.')
import importlib; M=importlib.import_module('四步_1122'); import numpy as np, pandas as pd
pd.set_option('display.width',250)
M.DHI=int((np.datetime64("2026-11-19")-M.D0).astype(int))
for nm in ('指数','行业'):
    Z=M.读(nm)
    for lab,p in (('r=0.786',dict(M.BASE,r=0.786)),('r=0.786,w=0.75',dict(M.BASE,r=0.786,w=0.75)),('r=0.5',dict(M.BASE,r=0.5))):
        ev,ps=M.跑一类(Z,0,p,随机对照=False)
        x=ev[(ev['日']>='2026-01-01')&ev['票'].isin(['SMH','QQQ','SPY'])]
        print(nm,lab); print(x[['票','日','层','E','止损','A低','B高','T1','到1倍','毛R','怎么出','出场日']].round(1).to_string() if len(x) else '  无')
