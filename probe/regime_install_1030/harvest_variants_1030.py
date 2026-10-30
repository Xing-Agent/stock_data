#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 把上一轮没覆盖的 8 个跑批脚本的变体「采」出来 —— 2026-10-30

三秒版:上一轮只覆盖 74/159 个策略(约 47%),★ 原因是其余 8 个跑批脚本
        **没有可导入的 `VARIANTS` 表** —— 它们的配置是在 `main()` 里现搭的。
        ★★ 任务单问:补这 8 个要多少工作量?
        ★★★ 答:**不用改那 8 个脚本**。它们都有一个共同形状 ——
            `chain.run_chain(cfg, ...)` 之后紧接着 `res.save_ledger(.../名字.csv)`。
            ★ 所以只要在**外面**包两层,把 (名字 → cfg.raw) 这一对**录下来**,
              那张「可导入的变体表」就自己出来了。

★★ 为什么这比「改 8 个脚本」好:
   ① **一行 engine/ 都不改,8 个跑批脚本也一行都不改。**
   ② 录下来的是**那个脚本真正跑过的那份 raw**,不是我按它的注释重新搭一份 ——
      ★★★ 重新搭 = 又一次「把已经存在的东西当成缺的去重新发明」(今天第 6 次)。
   ③ ★ 采的时候**不落盘**:`save_ledger` 被换成「只记名字、不写文件」,
      所以**不会覆盖任何别人的流水**(纪律 8:只读 probe/ 下别人的目录,
      这里把同一条纪律用在 engine/ledgers_* 上)。

★ 已知代价(写明,不藏):
  ① 采 = 把那 9 个脚本**各跑一遍**,所以要花它们原本的跑批时间。
     ★★ 2026-10-30 实测:跑满 9 个**超过 30 分钟**,本轮没跑完。
  ② ★★★ **流水不落盘,但 `results_*.json` 会被覆盖。**
     那些脚本除了 `save_ledger` 还会写自己的 `engine/results_*.json`,
     ★ 本采集器**没有**拦这一路 —— 实测 `engine/results_1028_流派一二.json`
       被 `run_batch.py` 重写了(内容等价,但 mtime / 排版会变)。
     ★★ 处置:采完 `git checkout --` 还原,**不要把它提交进去**。
     ★★★ 下一轮要补的一道:把 `json.dump` 也包一层,或者给这些脚本一个
          「只算不写」的开关 —— 这样采集就彻底无副作用。
  ③ ★ 本轮改成**逐脚本落盘**(采完一个写一次),所以中途被打断也留得下成果。
"""
from __future__ import annotations

import io
import json
import os
import sys
import time
import contextlib

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from engine import chain                                        # noqa: E402

OUT = os.path.join(HERE, "harvested_variants_1030.json")

#: ★ 上一轮没覆盖的跑批脚本 → 它写的流水目录(实测映射,不是猜)
#: ★★ 顺序 = 按「脚本行数」从小到大 —— 先采便宜的，★ 这样被打断也先抿到成果
#:   （2026-10-30 实测：9 个一起跑**超过 30 分钟**，所以顺序很要紧）
TARGETS = [
    ("engine.run_trend_1029", "ledgers_1029_趋势跟随", 3),
    ("engine.run_vcp_fixed", "ledgers_1028_vcp修正后", 3),
    ("engine.run_split_bias", "ledgers_1029_拆股偏差", 3),
    ("engine.bench_run_1029", "ledgers_1029_新基准线", 15),
    ("engine.run_batch", "ledgers_1028", 5),
    ("engine.run_vcp_simplified", "ledgers_1029_vcp简化后", 3),
    ("engine.run_fundamental", "ledgers_1029_基本面", 6),
    ("engine.run_gate_redesign", "ledgers_1028_闸门", 15),
    ("engine.run_second_round_1029", "ledgers_1029_第二轮", 12),
]


def harvest(modname: str, timeout_note: str = "") -> dict:
    """跑一遍 `modname.main()`,把 (流水名 → cfg.raw) 录下来,★ 不落盘。"""
    rec: list[dict] = []
    last: dict = {}

    orig_run = chain.run_chain
    orig_save = chain.ChainResult.save_ledger

    def run_chain_spy(cfg, *a, **kw):
        last["raw"] = cfg.raw
        return orig_run(cfg, *a, **kw)

    def save_ledger_spy(self, path: str) -> str:
        # ★★★ 只记名字,**不写文件** —— 不许覆盖任何别人的流水
        rec.append({"流水名": os.path.basename(path)[:-4],
                    "目录": os.path.basename(os.path.dirname(path)),
                    "笔数": int(len(self.ledger)),
                    "raw": last.get("raw")})
        return path

    chain.run_chain = run_chain_spy
    chain.ChainResult.save_ledger = save_ledger_spy
    t0 = time.time()
    err = None
    try:
        mod = __import__(modname, fromlist=["main"])
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            mod.main([])
    except SystemExit:
        pass
    except Exception as exc:                                     # noqa: BLE001
        err = repr(exc)[:400]
    finally:
        chain.run_chain = orig_run
        chain.ChainResult.save_ledger = orig_save
    return {"模块": modname, "采到": len(rec), "耗时秒": round(time.time() - t0, 1),
            "出错": err, "变体": rec}


def _dump(out: list) -> None:
    """★ 逐脚本落盘 —— 中途被打断也留得下成果(见文件头代价 ③)。"""
    tot = sum(r["采到"] for r in out)
    json.dump({"说明": "★ 采 = 跑一遍脚本并录下 (流水名 → cfg.raw);流水不落盘",
               "★已知副作用": "那些脚本自己的 engine/results_*.json 会被重写 —— "
                              "采完 git checkout -- 还原,不要提交",
               "合计采到": tot,
               "已采的脚本数": len(out), "目标脚本数": len(TARGETS),
               "逐脚本": out},
              open(OUT, "w", encoding="utf-8"),
              ensure_ascii=False, indent=1, default=str)


def main() -> int:
    out = []
    for modname, ldir, known in TARGETS:
        print(f"=== {modname}  (已知流水 {known} 份 → {ldir})", flush=True)
        r = harvest(modname)
        r["已知流水份数"] = known
        r["流水目录"] = ldir
        ok = "✓" if r["采到"] == known else "✗ 对不上"
        print(f"    采到 {r['采到']} 个变体 / {r['耗时秒']}s {ok}"
              f"{'  出错: ' + r['出错'] if r['出错'] else ''}", flush=True)
        out.append(r)
        _dump(out)                      # ★ 采完一个就落一次盘
    tot = sum(r["采到"] for r in out)
    known = sum(r["已知流水份数"] for r in out)
    print(f"\n★ 合计采到 {tot} 个变体(已知未覆盖流水 {known} 份)")
    print(f"→ {os.path.relpath(OUT, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
