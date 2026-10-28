"""
价格缓存 —— 把 300 个 json 一次性烤成 parquet,★ 并且在最底层就把脏活做完。

大白话:读 json 要 17 秒,跑一条链只要十几秒。读盘不该跑一次付一次。
这个文件把全池烤成一张 parquet,后面所有跑动都从它读,零点几秒。

★★ 三件脏活都在这一层做掉,★ 做一次,★ 后面每条链自动继承:
  一、未记录的 8 根拆股 → 按比例修正(判不准的 2 只直接剔除)
  二、破产类退市 → 在最后一个交易日之后补一根价格为 0 的 bar。
      ★ 这样不管哪条链在持仓,都躲不掉 −100%,不靠任何出场逻辑。
      出处:Shumway (1997, JF) The Delisting Bias in CRSP Data
  三、非破产类退市(并购等)→ 最后一根之后就是 NaN,不再有价格,
      持仓按最后收盘价结算

★ 为什么退市结算要放在价格序列上、不放在出场逻辑里:
  出场逻辑是「每条链自己写的」,写漏一条链就漏一次。价格序列是公用的,
  在这里埋进去,任何引擎(自己写的循环、vectorbt、以后换别的)都躲不掉。

跑法:python -m engine.cache --rebuild
"""

from __future__ import annotations

import os
import time

import numpy as np
import pandas as pd

from . import data, split_gate

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache")
PANEL_PARQUET = os.path.join(CACHE_DIR, "ohlcv_panel.parquet")
META_PARQUET = os.path.join(CACHE_DIR, "panel_meta.parquet")

FIELDS = ("open", "high", "low", "close", "volume", "dollar_volume")

_PANEL: dict[str, pd.DataFrame] | None = None


# ---------------------------------------------------------------- 烤缓存

def build(verbose: bool = True) -> dict[str, pd.DataFrame]:
    """从 json 烤出 parquet。拆股已修、破产 0 价 bar 已埋。"""
    os.makedirs(CACHE_DIR, exist_ok=True)
    t0 = time.time()
    cal = data.trading_calendar()
    meta = data.load_manifest()
    cols: dict[str, dict[str, pd.Series]] = {f: {} for f in FIELDS}
    rows = []

    for sym in sorted(meta):
        df = data.load_daily(sym)          # ★ load_daily 里已经修过拆股
        if df.empty:
            rows.append({"symbol": sym, "status": "空表,跳过", "last_bar": None,
                         "zero_bar": None, "n_bars": 0})
            continue
        r = df.reindex(cal)
        valid = r["close"].notna()
        if int(valid.sum()) < 60:
            rows.append({"symbol": sym, "status": "有效 bar 不足 60 根,跳过",
                         "last_bar": None, "zero_bar": None,
                         "n_bars": int(valid.sum())})
            continue
        last = cal[np.flatnonzero(valid.to_numpy())[-1]]

        # ★★ 破产类:最后一根之后补一根价格为 0 的 bar
        zero_bar = None
        m = meta[sym]
        if m.delisted and m.is_bankruptcy:
            after = cal[cal > last]
            if len(after):
                zero_bar = after[0]
                for f in ("open", "high", "low", "close"):
                    r.loc[zero_bar, f] = 0.0
                r.loc[zero_bar, "volume"] = 0.0
                r.loc[zero_bar, "dollar_volume"] = 0.0

        for f in FIELDS:
            cols[f][sym] = r[f].astype(float)
        rows.append({
            "symbol": sym, "status": "ok", "last_bar": last,
            "zero_bar": zero_bar, "n_bars": int(valid.sum()),
            "delisted": m.delisted, "retirement_category": m.retirement_category,
            "bankruptcy_minus100": bool(m.delisted and m.is_bankruptcy),
            "size_group": m.size_group, "sector": m.sector, "origin": m.origin,
        })

    panel = {f: pd.DataFrame(cols[f], index=cal).sort_index(axis=1) for f in FIELDS}
    wide = pd.concat(panel, axis=1)                   # 两层列:(field, symbol)
    wide.columns = pd.MultiIndex.from_tuples(wide.columns, names=["field", "symbol"])
    wide.to_parquet(PANEL_PARQUET)
    meta_df = pd.DataFrame(rows).set_index("symbol")
    meta_df.to_parquet(META_PARQUET)

    if verbose:
        ok = meta_df[meta_df["status"] == "ok"]
        zb = ok[ok["zero_bar"].notna()]
        print(f"缓存已烤好,用了 {time.time()-t0:.1f} 秒")
        print(f"  {PANEL_PARQUET}")
        print(f"  可用代码 {len(ok)} 只 × {len(cal)} 个交易日")
        print(f"  拆股已修(最底层做一次):"
              f"{[f'{e.symbol} {e.date}' for e in split_gate.FIX_EVENTS]}")
        print(f"  因判不准剔除:{sorted(split_gate.EXCLUDED_SYMBOLS)}")
        print(f"  ★ 补了 0 价 bar(强制 −100%)的破产类 {len(zb)} 只:")
        for s, row in zb.iterrows():
            print(f"      {s:6s} 末根 {pd.Timestamp(row['last_bar']).date()} "
                  f"→ 0 价 bar {pd.Timestamp(row['zero_bar']).date()}")
        skipped = meta_df[meta_df["status"] != "ok"]
        if len(skipped):
            print(f"  跳过 {len(skipped)} 只:{list(skipped.index)}")
    return panel


# ---------------------------------------------------------------- 读缓存

def load(rebuild: bool = False, verbose: bool = False) -> dict[str, pd.DataFrame]:
    """
    读缓存。返回 {field: DataFrame(行=交易日, 列=代码)}。
    缓存不存在就自动烤一次。
    """
    global _PANEL
    if _PANEL is not None and not rebuild:
        return _PANEL
    if rebuild or not os.path.exists(PANEL_PARQUET):
        _PANEL = build(verbose=True)
        return _PANEL
    t0 = time.time()
    wide = pd.read_parquet(PANEL_PARQUET)
    _PANEL = {f: wide[f] for f in wide.columns.levels[0]}
    if verbose:
        print(f"缓存读好,用了 {time.time()-t0:.2f} 秒 "
              f"({_PANEL['close'].shape[1]} 只 × {_PANEL['close'].shape[0]} 天)")
    return _PANEL


def panel_meta() -> pd.DataFrame:
    if not os.path.exists(META_PARQUET):
        build(verbose=False)
    return pd.read_parquet(META_PARQUET)


def field(name: str, symbols: list[str] | None = None) -> pd.DataFrame:
    p = load()[name]
    return p[symbols] if symbols else p


def symbols() -> list[str]:
    return list(load()["close"].columns)


def bars(sym: str) -> pd.DataFrame:
    """取单只票的 OHLCV(含 0 价 bar),去掉没有数据的日子。"""
    p = load()
    df = pd.DataFrame({f: p[f][sym] for f in FIELDS})
    return df[df["close"].notna()]


def last_valid_index() -> pd.Series:
    """每只票最后一根有价格的 bar(含 0 价 bar)。"""
    cl = load()["close"]
    return cl.apply(lambda s: s.last_valid_index())


def main(argv: list[str] | None = None) -> int:
    import argparse
    ap = argparse.ArgumentParser(description="烤/查价格缓存")
    ap.add_argument("--rebuild", action="store_true", help="重新烤一遍")
    a = ap.parse_args(argv)
    load(rebuild=a.rebuild, verbose=True)
    m = panel_meta()
    print()
    print(f"缓存元数据 {META_PARQUET}")
    print(m[m["status"] == "ok"].head(3).to_string())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
