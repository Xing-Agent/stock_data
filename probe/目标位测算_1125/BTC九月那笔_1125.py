# -*- coding: utf-8 -*-
"""《465》第 5 件：BTC 2026-09-21 那一笔（急拉到 87,397 后做空）。每种方法给的目标位、到没到、哪天到（日线最低价碰到即算），以及到之前有没有先打这条方法自己的止损。
数据：BTC 日线（同主脚本 读()）。只做单笔核对，不进任何统计。"""
import os, sys, importlib.util, pandas as pd, numpy as np
HERE=os.path.dirname(os.path.abspath(__file__))
sp=importlib.util.spec_from_file_location("主",os.path.join(HERE,"目标位测算_1125.py")); 主=importlib.util.module_from_spec(sp); sys.argv=["x","--import"]; sp.loader.exec_module(主)
D=主.读("BTC"); D=D[D.index>="2026-09-01"]
f=lambda n: pd.read_csv(os.path.join(HERE,"out",n))
形=f("形态_逐笔.csv"); 点=f("点数图_逐笔.csv"); 浪=f("波浪_逐笔.csv")
行=[]
def 查(名,起日,E,止损,目标):
    # 日线信号按收盘进场，从下一天算（楔形是 4 小时信号，当天算）
    d=D[D.index>pd.Timestamp(起日)] if 名.startswith(("波","箱","点","前")) else D[D.index>=pd.Timestamp(起日).normalize()]
    碰=d.index[d["low"]<=目标]; 损=d.index[d["high"]>=止损] if 止损 else []
    到=碰[0] if len(碰) else None; 先损=(len(损)>0 and (到 is None or 损[0]<=到))
    行.append(dict(方法=名,信号日=起日,进场=round(E),止损=round(止损) if 止损 else None,目标=round(目标),到了=到 is not None,
                 到的日子=到.date() if 到 is not None else None,用了几天=(到-pd.Timestamp(起日)).days if 到 is not None else None,
                 先打止损=先损,止损日=损[0].date() if len(损) else None))
for _,r in 形[(形.sym=="BTC")&(形["日"]>="2026-09-01")&(形["方向"]==-1)].iterrows():
    查(r["形态"],r["日"],r["E"],r["止损"],r["E"]*(1-r["测算100%距离pct"]/100))
for _,r in 点[(点.sym=="BTC")&(点["日"]>="2026-09-01")&(点["方向"]==-1)].iterrows():
    查(f"点数图 {r['格值倍']}ATR 近端",r["日"],r["E"],None,r["近端"]); 查(f"点数图 {r['格值倍']}ATR 远端",r["日"],r["E"],None,r["远端"])
for _,r in 浪[(浪.sym=="BTC")&(浪["日"]>="2026-09-01")&(浪["方向"]==-1)].iterrows():
    for c,n in (("距离点数1倍pct","点数1倍"),("距离点数1.618倍pct","点数1.618倍"),("距离百分比1倍pct","百分比1倍")):
        查(f"波浪{r['拐点倍']}ATR {n}",r["日"],r["E"],r["止损"],r["E"]*(1-r[c]/100))
    R=r["止损"]-r["E"]; 查(f"波浪{r['拐点倍']}ATR 2R",r["日"],r["E"],r["止损"],r["E"]-2*R)
查("前低(407) 57,718",pd.Timestamp("2026-09-21"),D.loc["2026-09-21","close"],None,57718)
T=pd.DataFrame(行); print(T.to_string(index=False)); T.to_csv(os.path.join(HERE,"out","BTC九月那笔.csv"),index=False)
print("数据最后一天",D.index[-1].date(),"9-21后最低",D["low"].min(),D["low"].idxmin().date())
