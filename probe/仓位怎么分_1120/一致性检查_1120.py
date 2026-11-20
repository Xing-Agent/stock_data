#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""一致性检查：新引擎（engine_v2）关掉加仓时，结果必须和旧引擎逐位相同（Lin 11-20《323》第 1 条的前提）

大白话：同一条策略、同一批票、同一段时间，旧引擎跑一遍、新引擎不传 pyramid 跑一遍，
比每天的净值、每天的仓位、每一笔流水的每一列。有任何一处不同就报错、退出码 1。
"""
import copy, io, json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, os.path.join(ROOT, "probe/基本面跑批_1106"))
import yaml, numpy as np, pandas as pd
import 跑基本面_1106 as B
B.装层()
import 补分红_1107 as DIV; DIV.install()
from engine import chain as OLD, matrices, data
from engine_v2 import chain as NEW
hold = json.load(io.open(B.HOLD, encoding="utf-8")); dev = hold["研发池名单"]
mk = pd.read_parquet(os.path.join(ROOT, "probe/流动性池_1114/流动性池掩膜_中.parquet"))
名单 = sys.argv[1:] or ["技-1", "trend_following", "技-3-XING", "技-4-原著-中值", "技-12"]
bad = 0; out = []
for 名 in 名单:
    raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine/configs", 名 + ".yaml"), encoding="utf-8"))
    m = matrices.build(OLD.ChainConfig.from_dict(copy.deepcopy(raw)).raw, dev)
    m.universe = m.universe & mk.reindex(index=m.index, columns=list(m.symbols)).fillna(False).to_numpy(dtype=bool)
    a = OLD.run_chain(OLD.ChainConfig.from_dict(copy.deepcopy(raw)), dev, data.PERF_START, data.PERF_END, m=m, total_return=True)
    b = NEW.run_chain(NEW.ChainConfig.from_dict(copy.deepcopy(raw)), dev, data.PERF_START, data.PERF_END, m=m, total_return=True)
    ok_eq = bool(np.array_equal(a.equity.to_numpy(), b.equity.to_numpy())); ok_ex = bool(np.array_equal(a.exposure.to_numpy(), b.exposure.to_numpy()))
    ok_ld = bool(len(a.ledger) == len(b.ledger) and list(a.ledger.columns) == list(b.ledger.columns) and a.ledger.equals(b.ledger))
    rec = {"策略": 名, "笔数_旧": int(len(a.ledger)), "笔数_新": int(len(b.ledger)), "期末净值_旧": float(a.equity.iloc[-1]), "期末净值_新": float(b.equity.iloc[-1]),
           "每日净值逐位相同": ok_eq, "每日仓位逐位相同": ok_ex, "流水每一列逐位相同": ok_ld}
    out.append(rec); print(rec, flush=True)
    bad += not (ok_eq and ok_ex and ok_ld)
io.open(os.path.join(HERE, "一致性检查_结果_1120.json"), "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1))
print("全部一致 ✅" if not bad else f"🔴 有 {bad} 条不一致"); sys.exit(1 if bad else 0)
