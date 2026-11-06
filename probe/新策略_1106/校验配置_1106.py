# -*- coding: utf-8 -*-
"""
★★★ 秒级校验器 —— 跑批之前先用极少的票把配置过一遍,看零件认不认。

★ 为什么要它(★★ 这是今天的教训):融-3 的进场格我改了**四次**才对,
  每次都要跑一轮(几十分钟)才知道错 —— ★★★ 而这件事本来 2 秒就能知道。
★ 办法:只拿 8 只票、调 matrices.build 一次,让它该抛的错立刻抛出来。
"""
from __future__ import annotations
import glob, io, json, os, sys
import pandas as pd, yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
from engine import cache, chain, matrices                        # noqa: E402

NEWPANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"


def main(argv: list[str]) -> int:
    wide = pd.read_parquet(NEWPANEL)
    cache._PANEL = {f: wide[f] for f in wide.columns.levels[0]}
    syms = sorted(cache._PANEL["close"].columns)[:8]              # ★ 只要 8 只
    files = argv or sorted(glob.glob(os.path.join(HERE, "configs", "*.yaml")))
    bad = 0
    for f in files:
        name = os.path.basename(f)
        try:
            raw = yaml.safe_load(io.open(f, encoding="utf-8"))
            cfg = chain.ChainConfig.from_dict(raw)
            matrices.build(cfg.raw, syms)
            print(f"  ✓ {name}")
        except Exception as e:
            bad += 1
            print(f"  ✗ {name}\n      {type(e).__name__}: "
                  f"{str(e).splitlines()[0]}")
    print(f"\n★ {len(files)} 份 · 过 {len(files)-bad} · 不过 {bad}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
