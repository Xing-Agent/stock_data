"""
手算核对 vcp_volume_tripod(专家 2026-10-28 修正版的成交量三条件)。

大白话:造一段我们自己知道答案的成交量,把三个条件分别手算一遍,
和引擎算出来的对一下 —— 对不上就是引擎写错了。

★ 为什么要有这个:修正后八年只跑出 15 笔,远低于专家预计的 180–260 笔。
  任务书要求「差很远就是我们实现得不对,要查」。这个脚本就是那次核查,
  ★ 留在仓库里,以后谁都能复跑。

跑法:python -m engine.verify_vcp_volume
"""
import sys, numpy as np, pandas as pd
from engine import matrices, cache

# 造 60 天:前 54 天量=1000(SMA50 基准=1000),
# t-5..t-1 = [500, 900, 900, 900, 900](有 1 天地量 500 ≤ 0.60*1000 ✅
#                                        SMA5=820 ≤ 0.85*1000=850 ✅)
# t 日量 = 1100  (≥1.00*SMA50=1000 ✅ ; ≥1.20*SMA5=984 ✅)  → 应为 True
vol = [1000.0]*54 + [500,900,900,900,900] + [1100]
idx = pd.bdate_range("2020-01-01", periods=len(vol))
df = pd.DataFrame({"X": vol}, index=idx)

class FakeCache:
    def field(self, name, symbols=None): return df
    def symbols(self): return ["X"]
orig = matrices.cache
matrices.cache = FakeCache()
rule = {"type":"vcp_volume_tripod","params":{}}
out = matrices._entry_rule_raw(rule, ["X"])
t = len(vol)-1
print("手算预期 t 日 = True, 引擎算出 =", bool(out.iloc[t,0]))

# 逐条件手算核对
v=np.array(vol); sma50_t1=v[t-50:t].mean(); sma5_t1=v[t-5:t].mean()
print(f"  SMA50[t-1]={sma50_t1:.1f}  SMA5[t-1]={sma5_t1:.1f}  min(Vol[t-5:t])={v[t-5:t].min():.0f}")
print(f"  条件1 {v[t-5:t].min():.0f} <= {0.60*sma50_t1:.1f} -> {v[t-5:t].min()<=0.60*sma50_t1}")
print(f"  条件2 {sma5_t1:.1f} <= {0.85*sma50_t1:.1f} -> {sma5_t1<=0.85*sma50_t1}")
print(f"  条件3 {v[t]:.0f} >= {1.00*sma50_t1:.1f} 且 >= {1.20*sma5_t1:.1f} -> "
      f"{v[t]>=sma50_t1 and v[t]>=1.20*sma5_t1}")

# 反例:去掉地量日(条件1 不成立)应为 False
vol2 = [1000.0]*54 + [900,900,900,900,900] + [1100]
df2 = pd.DataFrame({"X": vol2}, index=idx)
class FC2:
    def field(self,n,s=None): return df2
    def symbols(self): return ["X"]
matrices.cache = FC2()
o2 = matrices._entry_rule_raw(rule, ["X"])
print("反例(无地量日)预期 False, 引擎 =", bool(o2.iloc[t,0]))

# 反例:突破日不放量
vol3 = [1000.0]*54 + [500,900,900,900,900] + [950]
df3 = pd.DataFrame({"X": vol3}, index=idx)
class FC3:
    def field(self,n,s=None): return df3
    def symbols(self): return ["X"]
matrices.cache = FC3()
o3 = matrices._entry_rule_raw(rule, ["X"])
print("反例(突破日量 950 < SMA50)预期 False, 引擎 =", bool(o3.iloc[t,0]))
matrices.cache = orig
