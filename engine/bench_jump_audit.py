"""
★ 残余假跳变审计 —— 每条链的盈亏里,有多少是「跨过一根已知未修拆股 bar」赚来的。

三秒版:仓库这 300 只票里还剩 48 根没修的拆股跳变(engine/split_gate.py 自己的
        residual_jumps() 就在列这份「我们还欠多少」的清单)。这个脚本回答一句话:
        ★ 每条链的成绩里,有多少是踩在这些假 bar 上赚的?

做法:逐笔看持仓区间 [进场日, 出场日] 有没有跨过某根假跳变 bar。
      跨过的笔单独汇总净盈亏,和全链净盈亏比。★ 不改任何价格,只做归因。

跑法:cd /home/claude/xing-agent-stock_data && PYTHONPATH=. python3 -m engine.bench_jump_audit
"""

from __future__ import annotations

import glob
import json
import os

import pandas as pd

from . import split_gate

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER_DIR = os.path.join(HERE, "ledgers_1029_新基准线")
OUT_JSON = os.path.join(HERE, "results_1029_新基准线_假跳变审计.json")


def audit_ledger(path: str, jumps: dict[str, list[pd.Timestamp]]) -> dict:
    led = pd.read_csv(path, parse_dates=["entry_date", "exit_date"])
    if led.empty:
        return {"链名": os.path.basename(path)[:-4], "笔数": 0}
    hit = []
    for i, r in led.iterrows():
        for ts in jumps.get(r["symbol"], ()):
            if r["entry_date"] <= ts <= r["exit_date"]:
                hit.append(i)
                break
    tot = float(led["net_pnl"].sum())
    h = led.loc[hit]
    hp = float(h["net_pnl"].sum()) if len(h) else 0.0
    return {
        "链名": os.path.basename(path)[:-4],
        "笔数": int(len(led)),
        "全链净盈亏": tot,
        "★跨过假跳变的笔数": int(len(h)),
        "★这些笔的净盈亏": hp,
        "★占全链净盈亏比例": (hp / tot if abs(tot) > 1e-9 else None),
        "明细": [{"票": r["symbol"],
                  "进": str(pd.Timestamp(r["entry_date"]).date()),
                  "出": str(pd.Timestamp(r["exit_date"]).date()),
                  "毛收益": float(r["gross_return"]),
                  "净盈亏": float(r["net_pnl"])}
                 for _, r in h.nlargest(5, "net_pnl").iterrows()],
    }


def main(argv=None) -> int:
    raw = split_gate.residual_jumps(3.0)
    jumps: dict[str, list[pd.Timestamp]] = {}
    for sym, d, _r in raw:
        jumps.setdefault(sym, []).append(pd.Timestamp(d))
    print(f"残余假跳变(split_gate.residual_jumps(3.0)):{len(raw)} 根,"
          f"涉及 {len(jumps)} 只票")
    for sym, ds in sorted(jumps.items()):
        print(f"   {sym:6s} {[str(x.date()) for x in ds]}")
    out = {"口径": "逐笔看持仓区间有没有跨过一根已知未修的拆股跳变 bar;"
                   "跨过的笔单独汇总净盈亏。★ 不改价格,只做归因",
           "残余跳变根数": len(raw),
           "涉及票数": len(jumps),
           "逐票跳变日": {k: [str(x.date()) for x in v] for k, v in sorted(jumps.items())},
           "逐链": []}
    for p in sorted(glob.glob(os.path.join(LEDGER_DIR, "*.csv"))):
        rec = audit_ledger(p, jumps)
        out["逐链"].append(rec)
        sh = rec.get("★占全链净盈亏比例")
        print(f"{rec['链名'][:44]:46s} 笔数 {rec['笔数']:5d}  "
              f"跨假跳变 {rec.get('★跨过假跳变的笔数', 0):3d} 笔  "
              f"占净盈亏 {('%.1f%%' % (sh*100)) if sh is not None else 'n/a'}")
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\n已写:{OUT_JSON}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
