import sys,os,io,json,copy
ROOT='/home/claude/stock_data'
sys.path.insert(0,ROOT); os.chdir(ROOT)
for d in ('probe/补齐能力_1106','probe/基本面跑批_1106'):
    sys.path.insert(0,os.path.join(ROOT,d))
import numpy as np, pandas as pd, yaml
from engine import cache, matrices as M, data as D
# 只装「本路策略零件」这一层(它才是替换 regime_mask 的那一层)
import 策略零件_1106 as MINE
info=MINE.install()
print('装层:',info.get('环境'))
wide=pd.read_parquet('probe/newpool_1106/ohlcv_panel_newpool.parquet',columns=None)
idx=wide['close'].index; del wide
print('交易日数:',len(idx), idx.min().date(),'→',idx.max().date())
raw=yaml.safe_load(io.open('probe/基本面跑批_1106/configs/基-8_茨威格GARP红绿灯.yaml',encoding='utf-8'))
spec=raw['regime']
print('闸规则:',[r.get('type') for r in spec['rules']],' flatten_when_off=',spec.get('flatten_when_off'))
reg=np.asarray(M.regime_mask(spec,idx),dtype=bool)          # ★ 已装覆盖层
z=np.asarray(MINE.zweig_light(idx,(spec['rules'][0].get('params') or {}),D),dtype=bool)
z1=np.concatenate([[False],z[:-1]])
print()
print('regime 与「未挪 zweig」相同 : %d / %d'%( (reg==z).sum(), len(reg)))
print('regime 与「挪一天 zweig」相同: %d / %d'%( (reg==z1).sum(), len(reg)))
print()
print('开闸比例 regime=%.1f%%  未挪=%.1f%%'%(reg.mean()*100,z.mean()*100))
print()
print('→ 若「挪一天」那行是全等 ⇒ 基-8 的闸已用前一天收盘')
print('   ⇒ 配 chain.py 的 m.regime[i+1] 刚好 = 第 i 天收盘 = **正确**')
print('   ⇒ 而若把 chain.py 改成 [i], 基-8 会变成**滞后两天**(过度滞后)')
