# -*- coding: utf-8 -*-
"""
★★★ 给 22 年并池建排名表 —— ★ 覆盖 2004~2025、全部 3,858 只。

★★ 为什么必须建（★★★ 今天同一类错的第四次）：
  engine 的池子口径（`pool_scope`）按**当年成交额排名**筛 universe。
  ★ 而现有池表 `pool_NEWPOOL_ALL_1106.csv`：
    · **考卷那 1,042 只一只都不在里面（0 / 1042）**
    · 只覆盖 **2015~2025**，2004~2014 **根本没有**
  → ★★★ 所以就算面板里有苹果，`universe` 掩膜也会把它排除 —— **永远买不到**，
    「并池」到那一步其实还是**装饰性的**。

★★★ 一只票要能被买到，必须**同时**出现在三个地方：
   ① **面板**（有价格）② **manifest**（有元信息）③ **池表**（在排名里）
  ★ 我今天在这三处**各被咬了一次**（见《24》#70 / #72 / #74）。

★ 排名定义**照抄** `建排名表_1106.py`，一个字不改（也就是照抄 engine 老池的口径）：
  「★★ 排名都是当年年初回看 **60 个交易日**的日均成交额排名」—— 天生按时点，不看未来。
★★ tier 带宽也照抄：1–500 大 · 501–2000 中 · 2001+ 小。

★★★ 省内存：面板 444MB，机器只有 7GB —— ★ 所以**只读 `dollar_volume` 那一个字段**，
  并在读进来之后立刻降成 float32。
"""
from __future__ import annotations
import io, json, os, sys
import numpy as np, pandas as pd
import pyarrow.parquet as pq

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
os.chdir(ROOT)
OUT = "probe/并池2004_1107"
PANEL = os.path.join(OUT, "ohlcv_panel_newpool.parquet")
LOOKBACK = 60


def tier_of(rank: int) -> str:
    return "大" if rank <= 500 else ("中" if rank <= 2000 else "小")


def 只读成交额() -> pd.DataFrame:
    """★★★ 只读 dollar_volume 一个字段 + 降 float32（★ 否则 OOM）。"""
    sch = pq.read_schema(PANEL)
    names = sch.names
    cols = [n for n in names if n.startswith("('dollar_volume'")]
    assert cols, f"★★★ 面板里没有 dollar_volume 列；列名样例：{names[:3]}"
    # ★★★ 日期是**索引**（在 pandas 元数据里），不是普通列 —— ★ 照规矩⑬ 先打出来再接
    idxcols = [c for c in (sch.pandas_metadata or {}).get("index_columns", [])
               if isinstance(c, str)]
    t = pq.read_table(PANEL, columns=idxcols + cols)
    df = t.to_pandas()          # ★ pandas 元数据会自动把索引恢复
    if not isinstance(df.index, pd.DatetimeIndex):
        if idxcols and idxcols[0] in df.columns:
            df = df.set_index(idxcols[0])
        df.index = pd.to_datetime(df.index)
    # ★★★ 列名两种形态都认（★ 我连着猜错三次格式了，这里不再猜）：
    #   · 元组 ('dollar_volume', 'AAPL')   ← pandas 元数据恢复 MultiIndex 时
    #   · 字符串 "('dollar_volume', 'AAPL')" ← 没恢复时
    def _票(c):
        if isinstance(c, tuple):
            return c[-1]
        t = str(c)
        return t.split("'")[3] if t.startswith("('") else t
    df.columns = [_票(c) for c in df.columns]
    assert all(isinstance(c, str) and c and "(" not in c for c in df.columns), \
        f"★★★ 列名还原失败，样例：{list(df.columns)[:3]}"
    return df.astype("float32")


def main() -> int:
    dv = 只读成交额()
    idx = dv.index
    print(f"★ 只读成交额：{dv.shape[1]} 只 × {len(idx)} 天 · "
          f"{idx.min().date()} → {idx.max().date()} · "
          f"内存 {dv.memory_usage(deep=True).sum()/1e6:.0f} MB", flush=True)
    rows, 年统计 = [], {}
    for year in range(idx.min().year, idx.max().year + 1):
        ys = idx[idx.year == year]
        if len(ys) == 0:
            continue
        base = ys[0]                              # ★ 当年第一个交易日
        hist = idx[idx < base][-LOOKBACK:]        # ★ 回看 60 个交易日（严格在 base 之前）
        if len(hist) < LOOKBACK:
            年统计[str(year)] = f"★ 跳过：base 之前只有 {len(hist)} 个交易日，不足 {LOOKBACK}"
            print(f"   {year}: {年统计[str(year)]}", flush=True)
            continue
        blk = dv.loc[hist]
        adv = blk.mean(axis=0, skipna=True)
        valid = blk.notna().sum(axis=0)
        adv = adv[(valid >= LOOKBACK // 2) & adv.notna() & (adv > 0)]
        adv = adv.sort_values(ascending=False)
        for i, (sym, v) in enumerate(adv.items(), 1):
            rows.append({
                "year": year, "base_date": base.strftime("%Y-%m-%d"),
                "rank": i, "tier": tier_of(i), "symbol": sym,
                "avg_dollar_volume_60d": round(float(v), 1),
                "dollar_vol_price": "close",
                "seg_id": "", "company_id": "", "seg_start": "", "seg_end": "",
                "end_type": "", "renamed_to": "", "old_symbol": "", "old_size": "",
            })
        前10 = list(adv.index[:10])
        年统计[str(year)] = {"排名只数": int(len(adv)), "★前10名": 前10}
        print(f"   {year}: {len(adv)} 只 · 前5 {前10[:5]}", flush=True)

    import csv as _csv
    p = os.path.join(OUT, "pool_MERGED2004_ALL_1107.csv")
    with io.open(p, "w", encoding="utf-8", newline="") as fh:
        w = _csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader(); w.writerows(rows)

    # ★★★ 自证：巨头进没进排名、进在第几名
    chk = {}
    for t in ("AAPL", "MSFT", "AMZN", "NVDA", "GOOG", "BRK.B", "JPM"):
        hit = [r for r in rows if r["symbol"] == t]
        chk[t] = ({"出现年数": len(hit),
                   "2020年排名": next((r["rank"] for r in hit if r["year"] == 2020), None),
                   "2008年排名": next((r["rank"] for r in hit if r["year"] == 2008), None)}
                  if hit else "★★★ 没进排名")
    报 = {"★这一份做什么": __doc__.strip()[:1100],
         "★★★排名定义": "照抄 engine 老池：当年年初回看 60 个交易日的日均成交额排名",
         "★tier带宽": "1–500 大 · 501–2000 中 · 2001+ 小（照抄老池）",
         "★输出": p, "★行数": len(rows), "年统计": 年统计,
         "★★★巨头自证": chk}
    io.open(os.path.join(OUT, "建排名表2004_报告_1107.json"), "w",
            encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1))
    print(f"\n★ 写完 {p}（{len(rows)} 行）")
    print("★★★ 巨头自证:", json.dumps(chk, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
