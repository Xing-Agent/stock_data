# -*- coding: utf-8 -*-
"""★★★ 给新池冻一份研发池/留出池名单。★ 冻完就不许改。

★★ 切法:**按代码的 sha256 取模**,不用随机数 ——
   ★★★ 随机可以重抽,重抽就能抽到好看的那一次。哈希只有一种结果。
★ 比例:研发 80% / 留出 20%。
⚠ 考卷那 1,042 只在烤盘时已排除,不在这里。
"""
from __future__ import annotations
import hashlib, io, json, os
import pandas as pd

OUT = "probe/新策略_1106"
META = "probe/newpool_1106/panel_meta_newpool.parquet"


def main() -> int:
    md = pd.read_parquet(META)
    ok = sorted(md[md.status == "ok"].index.astype(str))
    dev, hold = [], []
    for s in ok:
        h = int(hashlib.sha256(s.encode()).hexdigest(), 16)
        (hold if h % 10 < 2 else dev).append(s)      # ★ 模 10 < 2 → 留出(20%)
    assert not (set(dev) & set(hold))
    d = {"★切法": "sha256(代码) % 10 < 2 → 留出池,其余研发池。★ 不用随机数(随机能重抽)",
         "★冻结日": "2026-11-06", "★来源": META,
         "★考卷": "1,042 只在烤盘阶段已排除,不在本名单内",
         "总数": len(ok), "研发池只数": len(dev), "留出池只数": len(hold),
         "留出比例": round(len(hold) / len(ok), 4),
         "研发池名单": dev, "留出池名单": hold}
    p = os.path.join(OUT, "holdout_newpool_1106.json")
    io.open(p, "w", encoding="utf-8").write(json.dumps(d, ensure_ascii=False, indent=1))
    print(f"★ {p}\n   总 {len(ok)} → 研发 {len(dev)} · 留出 {len(hold)} "
          f"({len(hold)/len(ok):.1%})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
