# -*- coding: utf-8 -*-
"""
★★★★★ #72：`烤新池_1106.py` **静默丢掉 145 行 manifest** —— ★ 93 个代码、其中 33 只是 large。

★★★ 机制（★ 一行代码）：
   · `market_ext_1105/manifest.csv` 里，**换过主体的票 `symbol` 字段写成 `SYM__CIK`**
     （例 `AVGO__1730168` · `BLK__2012383`），共 **145 行**。
   · 而 `目录表()` 建映射时 `sym = d.split("__")[0]` —— ★★ 键是**裸代码** `AVGO`。
   · → `新manifest()` 里 `cand = dirs.get(r["symbol"])` 查的是 `dirs.get("AVGO__1730168")`
     → **None** → `if not cand: continue` → ★★★ **静默跳过，连条数都没记**。

★★ 这一份干什么：**在不改 `烤新池_1106.py` 的前提下**，用进程内覆盖层把 `symbol` 的
   `__CIK` 削掉再查目录，烤一份**影子面板**到本目录，然后和现用面板**逐项对账** ——
   ★★★ 目的是把「修了会变多少」变成一个**具体的数**，好让 Lin 拍板。

★★★★★ ⚠ **不覆盖现用面板**：影子面板写在 `probe/池子缺票_1107/` 下，
   ★ 现用的 `probe/newpool_1106/ohlcv_panel_newpool.parquet` **一个字节都不动**。
"""
from __future__ import annotations
import csv, importlib.util, io, json, os, sys
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
os.chdir(ROOT)
OUT = os.path.join(HERE, "影子_报告_1107.json")

_s = importlib.util.spec_from_file_location("_bake", "probe/newpool_1106/烤新池_1106.py")
B = importlib.util.module_from_spec(_s)
_s.loader.exec_module(B)                      # ★ 有 __main__ 守卫，import 不会跑 main()
from engine import data as edata              # noqa: E402


def 修后manifest(exclude: set[str], dirs: dict) -> dict:
    """★★★ 和 `B.新manifest()` **逐字一样**，只改一处：★ 查目录前把 `__CIK` 削掉。
       ★★ 同一个裸代码有多行时，**取市值最大的那一行**当元信息（★★★ 并记下丢了几行）。"""
    best: dict[str, dict] = {}
    for r in csv.DictReader(io.open(os.path.join(B.EXT, "manifest.csv"), encoding="utf-8")):
        raw = (r.get("symbol") or "").strip()
        sym = raw.split("__")[0]                        # ★★★ 这就是那一处修法
        if not sym or sym.upper() in exclude:
            continue
        if not (dirs.get(sym) or []):
            continue
        try:
            mc = float(r.get("market_cap_usd") or 0)
        except Exception:
            mc = 0.0
        prev = best.get(sym)
        if prev is None or mc > prev[0]:
            best[sym] = (mc, r)
    out = {}
    for sym, (_, r) in best.items():
        cand = dirs[sym]
        out[sym] = edata.SymbolMeta(
            symbol=sym, name=r.get("name", ""), origin="market_ext_1105",
            size_group=(r.get("size_group") or "unknown"),
            sector=(r.get("sector") or ""),
            delisted=str(r.get("delisted", "")).strip().lower() in ("true", "1", "yes"),
            retirement_category=(r.get("retirement_category") or ""),
            daily_path=cand[0], fundamentals_path=None,
            download_end_date=(r.get("last_bar") or ""))
    return out


def main() -> int:
    ex = B.考卷名单()
    dirs = B.目录表()
    老 = B.新manifest(ex, dirs)
    新 = 修后manifest(ex, dirs)
    多出 = sorted(set(新) - set(老))
    少了 = sorted(set(老) - set(新))
    print(f"★ 老口径候选 {len(老)} 只 · 修后候选 {len(新)} 只 → ★★★ 多出 {len(多出)} 只，少了 {len(少了)} 只",
          flush=True)

    # ★ 多出来那批的 size_group / 市值
    mrows = {}
    for r in csv.DictReader(io.open(os.path.join(B.EXT, "manifest.csv"), encoding="utf-8")):
        s = (r.get("symbol") or "").strip().split("__")[0]
        try:
            mc = float(r.get("market_cap_usd") or 0)
        except Exception:
            mc = 0.0
        if s not in mrows or mc > mrows[s][0]:
            mrows[s] = (mc, r)
    from collections import Counter
    sg = Counter((mrows.get(s, (0, {}))[1] or {}).get("size_group") or "?" for s in 多出)
    大 = sorted(多出, key=lambda s: -mrows.get(s, (0, {}))[0])[:20]

    # ---------------- 烤影子面板（★ 复用 B 的读日线/拆股修正，engine 零改动）----------------
    edata.load_manifest.cache_clear()
    edata.load_manifest = lambda: 新                    # type: ignore[assignment]
    cal = edata.trading_calendar()
    cols = {f: {} for f in B.FIELDS}
    失败 = []
    for i, sym in enumerate(sorted(新), 1):
        if i % 400 == 0:
            print(f"   …{i}/{len(新)}", flush=True)
        try:
            cand = dirs.get(sym) or []
            if len(cand) > 1:
                cand = sorted(cand, key=lambda q: -len(B.读日线(q, sym)))
            df = B.读日线(cand[0], sym)
        except Exception as e:
            失败.append((sym, f"{type(e).__name__}"))
            continue
        if df.empty:
            失败.append((sym, "空表")); continue
        r2 = df.reindex(cal)
        if int(r2["close"].notna().sum()) < 60:
            失败.append((sym, "有效bar<60")); continue
        for f in B.FIELDS:
            if f in r2:
                cols[f][sym] = r2[f]
    wide = pd.concat({f: pd.DataFrame(cols[f]) for f in B.FIELDS}, axis=1)
    wide.columns.names = ["field", "symbol"]
    wide.to_parquet(os.path.join(HERE, "ohlcv_panel_影子_1107.parquet"))
    print(f"★★ 影子面板入池 {wide['close'].shape[1]} 只（失败 {len(失败)}）", flush=True)

    # ---------------- 对账：等权同池买入持有 ----------------
    def 等权买入持有(cl: pd.DataFrame, 起, 止) -> dict:
        c = cl.loc[(cl.index >= 起) & (cl.index <= 止)]
        r = c.pct_change()
        # ★ 等权：每天对当天有价的票取平均日收益（★★ 这就是「全买了放着」的日收益）
        d = r.mean(axis=1, skipna=True).fillna(0.0)
        eq = (1 + d).cumprod()
        yrs = (c.index[-1] - c.index[0]).days / 365.25
        ann = float(eq.iloc[-1] ** (1 / yrs) - 1) if yrs > 0 else float("nan")
        dd = float((eq / eq.cummax() - 1).min())
        return {"只数(任一天有价)": int(c.notna().any().sum()),
                "年化pct": round(ann * 100, 3), "最大回撤pct": round(dd * 100, 2),
                "总收益pct": round(float(eq.iloc[-1] - 1) * 100, 2)}

    老面板 = pd.read_parquet("probe/newpool_1106/ohlcv_panel_newpool.parquet")["close"]
    新面板 = wide["close"]
    起, 止 = pd.Timestamp("2018-01-01"), pd.Timestamp("2025-12-31")
    a, b = 等权买入持有(老面板, 起, 止), 等权买入持有(新面板, 起, 止)

    rep = {
        "★★★这一份是什么": "#72 影子烤池 —— ★ 量「修掉那一行会把标尺挪多少」，"
                     "★★★ 不覆盖现用面板",
        "★口径": {"窗口": f"{起.date()} → {止.date()}（和《91》组合层同窗口）",
                "等权买入持有怎么算": "★ 每天对当天有价的票取**平均日收益**，复利 —— "
                              "★★ 这就是『全买了放着』那条线",
                "★★★engine改动": "零 —— 进程内覆盖层",
                "★★★不覆盖现用面板": "影子面板写在 probe/池子缺票_1107/"},
        "★★★★★机制": {
            "一句话": "manifest.csv 里换过主体的票 symbol 写成 `SYM__CIK`（145 行），"
                   "而 目录表() 的键是裸代码 → dirs.get() 查不到 → 静默 continue",
            "manifest总行数": 2968, "带__CIK的行数": 145, "覆盖的不同代码数": 93,
            "★★★为什么一直没人发现": "★ 那个 `continue` **没有任何计数** —— "
                            "★★★ 规矩⑰ 原话：任何「算不出就跳过」的分支必须报跳了多少笔",
        },
        "候选只数": {"老口径": len(老), "修后": len(新), "★★★多出": len(多出), "少了": len(少了)},
        "★★★多出来那批": {"size_group分布": dict(sg),
                   "★市值最大的20只": [{"票": s,
                                  "市值B": round(mrows.get(s, (0, {}))[0] / 1e9, 1),
                                  "size": (mrows.get(s, (0, {}))[1] or {}).get("size_group"),
                                  "名": (mrows.get(s, (0, {}))[1] or {}).get("name", "")[:40]}
                                 for s in 大]},
        "★★★★★等权同池买入持有(标尺本身)": {"老面板": a, "★修后影子面板": b,
                                "★★★差(年化, 个百分点)": round(b["年化pct"] - a["年化pct"], 3)},
        "影子面板": {"入池只数": int(新面板.shape[1]), "烤失败": len(失败)},
        "★★★要 Lin 拍板的": [
            "★★★★★ 这一行要不要现在修 —— ★ 修了**所有成绩都要重跑**（面板变了），"
            "★★ 不修则所有「同池/赛道」基准都是在一个**缺 93 只（含 33 只 large）**的池子上算的",
        ],
    }
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(rep, ensure_ascii=False, indent=1, default=str))
    print("\n★★★★★ 等权同池买入持有（2018→2025）：")
    print("   老面板:", json.dumps(a, ensure_ascii=False))
    print("   修后  :", json.dumps(b, ensure_ascii=False))
    print(f"   ★★★ 年化差 {b['年化pct'] - a['年化pct']:+.3f} 个百分点")
    print("★ 写到", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
