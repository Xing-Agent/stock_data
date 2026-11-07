# -*- coding: utf-8 -*-
"""★★★ 把 Lin 那一问拆成两半 —— **信号自己走到巨头上了吗，还是排序旋钮替它走的？**

★ Lin 1107 19:38 问的是：「突破信号到底有没有自己走到巨头上。」
★★ 直接看成交流水**回答不了**这一问，因为成交是两件事共同作用的结果：
   ① **进场扳机**（信号本身）决定「今天哪些票合格」
   ② **排序旋钮** `ranking` 决定「合格的比槽位多时，买哪几只」
      —— ★★★ 45 条链全是 `ADV20 降序` = **先买成交额最大的**，
      它**天生**把持仓往大票推。★ 把这个功劳记在信号头上就是错的。

★★★ 所以这一份量的是**第①步的产物**：`m.entry & m.universe` ——
   「信号判定合格、**还没过排序这一关**」的全体 (交易日 × 票)，按当年 rank 分档。
   ★★ 再和两个分母比：
      · **可买全池**（池子本身的大中小构成）→ 看信号有没有自己偏向大票
      · **成交的**（持仓画像_1107.py 出的那一栏）→ 看排序旋钮又额外推了多少

★ 口径：档位照抄 `engine/pool_scope.py TIER_BANDS`；rank 取**那一天所在年份**的排名。
★★ engine 零改动，只读。
"""
from __future__ import annotations
import io, json, os, sys, time

import numpy as np, pandas as pd, yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
for d in ("probe/friction_rerun_1104", "probe/v2_rerun_1030",
          "probe/选票层_1107", "probe/newpool_1106", "probe/并池_1107"):
    sys.path.insert(0, os.path.join(ROOT, d))
sys.path.insert(0, HERE)
os.chdir(ROOT)
from engine import cache, data, pool_scope, pat6_ops, matrices, chain   # noqa: E402
import rerun_core_1030 as RC                                           # noqa: E402
import 回看期覆盖层_1107 as OV, 接新基准_1107 as BM                      # noqa: E402
import 持仓画像_1107 as PZ                                              # noqa: E402
pat6_ops.install()

PANEL = "probe/并池2004_1107/ohlcv_panel_newpool.parquet"
POOLTAB = "probe/并池2004_1107/pool_MERGED2004_ALL_1107.csv"
代表 = {"大波段": "技-1.yaml", "突破": "技-6-原著.yaml", "震荡": "技-14-原著.yaml"}
窗口起, 窗口止 = "2015-01-01", "2025-12-31"
OUT = os.path.join(HERE, "信号自己走到哪_报告_1107.json")


def main() -> int:
    t0 = time.time()
    OV.install(); BM.install()
    wide = pd.read_parquet(PANEL)
    预热 = pd.Timestamp(窗口起) - pd.Timedelta(days=640)
    wide = wide.loc[(wide.index >= 预热) & (wide.index <= pd.Timestamp(窗口止))]
    cache._PANEL = {f: wide[f] for f in wide.columns.levels[0]}
    del wide
    RC._IDX_CACHE["idx"] = pool_scope.PoolIndex(path=POOLTAB)
    data.PERF_START, data.PERF_END = 窗口起, 窗口止
    dev = sorted(cache._PANEL["close"].columns)

    # ★★★ rank 查表：(年, 票) → 档；★ 一次建好，别在循环里一行行查
    池 = pd.read_csv(POOLTAB, usecols=["year", "symbol", "rank"])
    池["档"] = 池["rank"].map(PZ.档)
    档表 = {(int(y), s): d for y, s, d in zip(池["year"],池["symbol"],池["档"])}

    报 = {"★★★这一份回答什么": __doc__.strip()[:1500],
         "【本次口径】": (f"窗口 {窗口起}~{窗口止} · 池 并池2004 全量 {len(dev)} 只 · "
                    "档位照抄 engine/pool_scope.py TIER_BANDS · 只读，engine 零改动"),
         "★分母_可买全池": PZ.可买全池画像(list(range(2015, 2026))),
         "各族": {}}

    for 族, fn in 代表.items():
        raw = yaml.safe_load(io.open(os.path.join(ROOT, "engine", "configs", fn),
                                     encoding="utf-8"))
        cfg = chain.ChainConfig.from_dict(raw)
        m = matrices.build(cfg.raw, dev)
        RC.apply_scope(m, "large_mid")
        合格 = (m.entry & m.universe)
        idx = pd.DatetimeIndex(m.index)
        用 = (idx >= pd.Timestamp(窗口起)) & (idx <= pd.Timestamp(窗口止))
        合格 =合格[用]; 年 = idx[用].year.to_numpy()
        syms = np.asarray(m.symbols)
        计: dict = {}
        for i in range(合格.shape[0]):
            cols = np.flatnonzero(合格[i])
            if not len(cols):
                continue
            y = int(年[i])
            for c in cols:
                k = 档表.get((y, syms[c]), "当年不在池")
                计[k] = 计.get(k, 0) + 1
        总 = sum(计.values())
        报["各族"][族] = {
            "★配置": fn,
            "★★★合格信号格子数(交易日×票)": int(总),
            "★★★合格信号_按档占比": ({k: round(v / 总, 4) for k, v in
                              sorted(计.items(), key=lambda x: -x[1])} if 总 else {}),
            "★合格信号_按档格子数": dict(sorted(计.items(), key=lambda x: -x[1])),
            "★这一栏是什么": "★★★ 信号判定合格、**还没过 ADV20 排序这一关** —— 这一栏才是「信号自己」",
        }
        print(f"★ {族}: 合格格子 {总:,} · {报['各族'][族]['★★★合格信号_按档占比']}", flush=True)
        del m, 合格

    报["★用时秒"] = round(time.time() - t0, 1)
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"★ 写完 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
