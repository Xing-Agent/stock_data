# -*- coding: utf-8 -*-
"""
★★★ 烤「新池」面板 —— 把 market_ext_1105 的 2,968 只烤成一张 parquet。
★ 目的:池子从 300 只 → 2,968 只(约 ×10 广度)。

★★★ 硬规矩:**engine/ 一个字节不许改。**
   → 做法:在**我们自己的进程里**临时替换 data.load_manifest 和 data.trading_calendar
     (和《47》修搜索那次用的同一种覆盖层技术),engine 文件原样不动。
   → 这样 load_daily 里的**拆股修正**、cache 里的**退市结算**全部原样复用,
     ★★ 新池和老池用的是同一套脏活,结果可对账。

★★ 已知边界(★ 不自己编近似值顶上):
   · **日历仍用 SPY** —— SPY 只有 2014 起,所以新池窗口也只能到 2014。
     ★★★ 要拉到 2008,必须先补 SPY(及其他基准)2008–2014 的日线 —— 另开取数单。
   · 退市结算:新行情的票大多不在 delisting_gate 的核实清单里 →
     ★ 那些只能按「最后收盘价结算」,并**逐只标出来**,不假装有证据。
"""
from __future__ import annotations
import csv, gzip, io, json, os, sys, time
import numpy as np, pandas as pd

sys.path.insert(0, os.path.abspath("."))
from engine import data as edata, delisting_gate                  # noqa: E402

ROOT = os.path.abspath(".")
EXT = os.path.join(ROOT, "market_ext_1105")
OUT = os.path.join(ROOT, "probe", "newpool_1106")
FIELDS = ("open", "high", "low", "close", "volume", "dollar_volume")
EXAM = os.path.join(ROOT, "probe", "exam_1101")        # ⚠ 考卷,不碰


def 考卷名单() -> set[str]:
    """⚠ 考卷那 1,042 只一只都不许进新池。

    ★★★ 这里原来用 os.walk + 「文件名里有 exam」去 glob —— **抓错了**:
       它抓到 `exam_candidates_full_1101.csv`(6,179 只**候选**),
       比真名单多排了 5,137 只。
    ★ 权威名单只有一个文件:`probe/exam_1101/exam_list_1101.csv`(1,042 行)。
    ★★ 所以这里**写死**那一个路径,并断言行数,不再 glob。
    """
    p = os.path.join(EXAM, "exam_list_1101.csv")
    rows = list(csv.DictReader(io.open(p, encoding="utf-8")))
    s = {(r["symbol"] or "").strip().upper() for r in rows if r.get("symbol")}
    assert 1000 <= len(s) <= 1100, f"考卷名单应为 1,042 只,实际 {len(s)} —— 名单文件不对"
    return s


def 目录表() -> dict:
    """★★ market_ext_1105 的目录名可能是 `SYM` 也可能是 `SYM__CIK`
    (例:AAN__706688)。★ 所以不能按 symbol 直接拼路径,要先扫一遍建映射。
    ★★★ 同一个 symbol 有多个目录时(换过主体),**全部记下**,取 bar 最多的那个,
       并在报告里标明有多少只发生过这种情况 —— 不悄悄挑一个。
    """
    m = {}
    for d in sorted(os.listdir(EXT)):
        full = os.path.join(EXT, d)
        if not os.path.isdir(full):
            continue
        sym = d.split("__")[0]
        for fn in ("daily.json.gz", "daily.json"):
            p = os.path.join(full, fn)
            if os.path.exists(p):
                m.setdefault(sym, []).append(p)
                break
    return m


def 读日线(path: str, symbol: str) -> pd.DataFrame:
    """★ 读一只票的日线。★★ 和 engine.load_daily 同口径,★★★ 只多做一件:
    支持 .json.gz(engine 的 load_daily 用的是普通 open,读不了 gz)。
    ★ 拆股修正直接调 engine 的 _apply_split_fix,**不自己另写一套**。
    """
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8") as fh:
        raw = json.load(fh)
    rows = raw.get("data") or []
    cols = ["open", "high", "low", "close", "volume", "dollar_volume"]
    if not rows:
        return pd.DataFrame(columns=cols)
    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df = df.set_index("date").sort_index()
    keep = ["open", "high", "low", "close", "volume"]
    for c in keep:
        if c not in df.columns:
            df[c] = np.nan
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df = df[keep].astype(float)
    df = df[~df.index.duplicated(keep="last")]
    df = edata._apply_split_fix(df, symbol, raw_rows=rows)
    df["dollar_volume"] = df["close"] * df["volume"]
    return df


def 新manifest(exclude: set[str], dirs: dict) -> dict:
    out = {}
    for r in csv.DictReader(io.open(os.path.join(EXT, "manifest.csv"),
                                    encoding="utf-8")):
        sym = (r.get("symbol") or "").strip()
        if not sym or sym.upper() in exclude:
            continue
        cand = dirs.get(sym) or []
        if not cand:
            continue
        p = cand[0] if len(cand) == 1 else None   # ★ 多主体的留到读的时候挑
        out[sym] = edata.SymbolMeta(
            symbol=sym, name=r.get("name", ""), origin="market_ext_1105",
            size_group=(r.get("size_group") or "unknown"),
            sector=(r.get("sector") or ""),
            delisted=str(r.get("delisted", "")).strip().lower() in ("true", "1", "yes"),
            retirement_category=(r.get("retirement_category") or ""),
            daily_path=(p or cand[0]), fundamentals_path=None,
            download_end_date=(r.get("last_bar") or ""))
    return out


def main() -> int:
    t0 = time.time()
    ex = 考卷名单()
    dirs = 目录表()
    多主体 = {k: v for k, v in dirs.items() if len(v) > 1}
    man = 新manifest(ex, dirs)
    print(f"★ 考卷排除 {len(ex)} 只 · 新池候选 {len(man)} 只", flush=True)

    # ★★★ 覆盖层:只在本进程内替换,engine 文件没动
    edata.load_manifest.cache_clear()
    edata.load_manifest = lambda: man                     # type: ignore[assignment]
    cal = edata.trading_calendar()
    print(f"★ 日历 {cal.min().date()} → {cal.max().date()} · {len(cal)} 个交易日",
          flush=True)

    cols = {f: {} for f in FIELDS}
    rows = []
    for i, sym in enumerate(sorted(man), 1):
        if i % 200 == 0:
            print(f"   …{i}/{len(man)}  {time.time()-t0:.0f}s", flush=True)
        try:
            cand = dirs.get(sym) or []
            if len(cand) > 1:   # ★ 多主体:取 bar 最多的那个
                cand = sorted(cand, key=lambda q: -len(读日线(q, sym)))
            df = 读日线(cand[0], sym)      # ★ 拆股修正复用 engine 的函数
        except Exception as e:
            rows.append({"symbol": sym, "status": f"读失败:{type(e).__name__}",
                         "n_bars": 0}); continue
        if df.empty:
            rows.append({"symbol": sym, "status": "空表", "n_bars": 0}); continue
        r = df.reindex(cal)
        valid = r["close"].notna()
        n = int(valid.sum())
        if n < 60:
            rows.append({"symbol": sym, "status": "有效bar<60", "n_bars": n}); continue
        last = cal[np.flatnonzero(valid.to_numpy())[-1]]
        m = man[sym]
        st = delisting_gate.settlement_for(sym)
        px = delisting_gate.forced_price(sym) if m.delisted else None
        zero_bar = None
        if m.delisted and px is not None:
            after = cal[cal > last]
            if len(after):
                zero_bar = after[0]
                for f in ("open", "high", "low", "close"):
                    r.loc[zero_bar, f] = float(px)
                r.loc[zero_bar, "volume"] = 0.0
                r.loc[zero_bar, "dollar_volume"] = 0.0
        for f in FIELDS:
            cols[f][sym] = r[f].astype(float)
        rows.append({
            "symbol": sym, "status": "ok", "n_bars": n,
            "first_bar": cal[np.flatnonzero(valid.to_numpy())[0]], "last_bar": last,
            "delisted": m.delisted, "zero_bar": zero_bar,
            "settlement_basis": (st.basis if st else ""),
            "settlement_price": (float(px) if px is not None else None),
            # ★★★ 没有核实证据、只能按最后收盘价结算的,逐只标出来
            "settlement_fallback_last_close": bool(m.delisted and px is None),
            "size_group": m.size_group, "sector": m.sector,
        })

    os.makedirs(OUT, exist_ok=True)
    panel = {f: pd.DataFrame(cols[f], index=cal).sort_index(axis=1) for f in FIELDS}
    wide = pd.concat(panel, axis=1)
    wide.columns = pd.MultiIndex.from_tuples(wide.columns, names=["field", "symbol"])
    wide.to_parquet(os.path.join(OUT, "ohlcv_panel_newpool.parquet"))
    md = pd.DataFrame(rows).set_index("symbol")
    md.to_parquet(os.path.join(OUT, "panel_meta_newpool.parquet"))

    ok = md[md.status == "ok"]
    rep = {
        "★口径": {
            "来源": "market_ext_1105", "engine改动": "零 —— 用进程内覆盖层",
            "日历": f"SPY,{cal.min().date()} → {cal.max().date()}",
            "★★★ 窗口为什么只到 2014": "SPY 基准文件只有 2014 起;要到 2008 需另补基准日线",
            "考卷": f"已排除 {len(ex)} 只",
        },
        "候选": len(man), "入池": int(len(ok)),
        "按状态": md.status.value_counts().to_dict(),
        "退市": int(ok.delisted.sum()) if "delisted" in ok else None,
        "★只能按最后收盘价结算的": (int(ok.settlement_fallback_last_close.sum())
                                   if "settlement_fallback_last_close" in ok else None),
        "bar数": ({"最少": int(ok.n_bars.min()), "中位": float(ok.n_bars.median()),
                   "最多": int(ok.n_bars.max())} if len(ok) else "★ 入池 0 只,算不出"),
        "size_group": (ok.size_group.value_counts().to_dict() if len(ok) else {}),
        "★同一代码多个主体目录的只数": len(多主体),
        "耗时秒": round(time.time() - t0, 1),
    }
    io.open(os.path.join(OUT, "烤新池_报告_1106.json"), "w", encoding="utf-8").write(
        json.dumps(rep, ensure_ascii=False, indent=1, default=str))
    print(json.dumps(rep, ensure_ascii=False, indent=1, default=str), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
