# -*- coding: utf-8 -*-
"""第三批 / 第五批共用：把研发池个股的日线（拆股并股已按表折算）切到 2021-12-31 为止，存一份精简的本地缓存（不入库）。
段一 = newpool 面板（2014 起，成绩从 2015 算）+ 流动性池中档掩膜（本容器重建，打了 1118 补丁）；
段二 = 并池2004 面板（2004 起，成绩 2005–2014）+ 流动性池2004 中档掩膜。
2022 年以后的美股行情在这里就切掉，后面的脚本读不到。engine/ 不改。"""
import io, json, os, sys
import pandas as pd, numpy as np
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUT = os.environ.get("XING_CACHE", "/tmp/w")
封存 = pd.Timestamp("2021-12-31")
段 = sys.argv[1]
sys.path.insert(0, ROOT)
if 段 == "一":
    sys.path.insert(0, os.path.join(ROOT, "probe/联合_1122"))
    import 联合回测_1122 as lj
    B, FIX = lj.装()
    from engine import cache
    hold = json.load(io.open(os.path.join(ROOT, B.HOLD), encoding="utf-8")); dev = hold["研发池名单"]
    drop = set(FIX.要拿掉的票())
    mk = pd.read_parquet(os.path.join(OUT, "pool/掩膜中_补丁.parquet"))
else:
    sys.path.insert(0, os.path.join(ROOT, "probe/两段时间_1120"))
    import 环境2004_1120 as ENV
    env = ENV.install(只留测试期=True)
    from engine import cache
    import 按表折算_1118 as FIX
    drop = set(FIX.要拿掉的票()); dev = env["dev"]
    mk = pd.read_parquet(os.path.join(ROOT, "probe/两段时间_1120/流动性池掩膜2004_中.parquet"))
P = cache._PANEL
cols = [s for s in dev if s in P["close"].columns and s not in drop and s in mk.columns]
D = {f: P[f][cols].loc[:封存].astype("float32") for f in ("open", "high", "low", "close", "volume")}
W = pd.concat(D, axis=1); W.to_parquet(os.path.join(OUT, f"股票日线_{段}.parquet"))
mk = mk.loc[:封存, cols].reindex(W.index).fillna(False).astype(bool); mk.to_parquet(os.path.join(OUT, f"股票掩膜_{段}.parquet"))
print(段, "票", len(cols), "天", W.index[0].date(), W.index[-1].date(), "掩膜里平均每天", round(mk.sum(1)[mk.sum(1) > 0].mean()))
