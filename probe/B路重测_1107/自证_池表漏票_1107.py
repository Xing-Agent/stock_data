# -*- coding: utf-8 -*-
"""★★★ 自证：并池 3,834 只，可买名单已改成全量 —— 但「大中盘口径」那道筛用的池表里没有新并进来的 1,042 只
→ 它们在 universe 里被整只砍掉。用 engine 自己的 matrices.build + rerun_core.apply_scope 实测，不靠推理。"""
import io, json, os, sys
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "probe", "v2_rerun_1030")); os.chdir(ROOT)
import numpy as np, pandas as pd, yaml
from engine import cache, data, pool_scope, matrices, chain, pat6_ops
import rerun_core_1030 as RC
pat6_ops.install()
wide = pd.read_parquet("probe/并池_1107/ohlcv_panel_newpool.parquet")
cache._PANEL = {f: wide[f] for f in wide.columns.levels[0]}; del wide
RC._IDX_CACHE["idx"] = pool_scope.PoolIndex(path="probe/newpool_1106/pool_NEWPOOL_ALL_1106.csv")
data.PERF_START = "2016-01-04"
syms = sorted(cache._PANEL["close"].columns)
old = set(pd.read_parquet("probe/newpool_1106/panel_meta_newpool.parquet").index)
新 = [s for s in syms if s not in old]
raw = yaml.safe_load(io.open("engine/configs/技-14-原著.yaml", encoding="utf-8"))
cfg = chain.ChainConfig.from_dict(raw)
m = matrices.build(cfg.raw, syms)
pos = {s: j for j, s in enumerate(m.symbols)}
u0 = np.asarray(m.universe)
before = {s: int(u0[:, pos[s]].sum()) for s in 新 if s in pos}
diag = RC.apply_scope(m, "large_mid")
u1 = np.asarray(m.universe)
after = {s: int(u1[:, pos[s]].sum()) for s in 新 if s in pos}
big = ["AAPL", "MSFT", "AMZN", "JPM", "BRK.B", "AVGO", "NFLX"]
out = {"可买名单只数": len(syms), "★并池新进来的只数": len(新),
       "新进来的：筛之前 universe 里有日子的只数": sum(v > 0 for v in before.values()),
       "★★★新进来的：大中盘口径筛完还有日子的只数": sum(v > 0 for v in after.values()),
       "巨头逐只（筛前票日 → 筛后票日）": {s: [before.get(s), after.get(s)] for s in big},
       "整体 universe 砍掉比例": diag.get("universe 票日 砍掉比例")}
print(json.dumps(out, ensure_ascii=False, indent=1))
io.open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "自证_池表漏票_1107.json"), "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
