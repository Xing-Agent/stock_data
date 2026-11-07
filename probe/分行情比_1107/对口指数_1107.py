# -*- coding: utf-8 -*-
"""
★★★ 对口指数 —— ★ 来历：Lin 1107 09:10。

★★ 他指出两件：
 ①「大盘是负的，我是正的；或者大盘亏钱，我没亏钱，这就很好」
   → ★ 要**分大盘涨的天 / 跌的天**分别看
 ②「比的更细 —— 同样做中小股增长，那我比的就不是大盘，我比的是中小股的指数」
   → ★★★ 这是真缺口：我们池子 2,770 只、大量中小盘，
     ★★ 却一直拿 **SPY（大盘股）** 当标尺。
     ★★★ 而 2015~2025 的 SPY 被几只超大市值股撑得极高
       → **我们自己选错了标尺，而且错的方向对我们不利。**

★ 对口标尺不去外面买数据，用我们**自己池子**造：
   **同一个池子、等权、买入持有**（每天对当天有价的票取等权日收益）。
   ★★ 同池同权 —— 这是最不可抱怨的标尺。
   ★★★ 口径⑥ 自查已内置：换标尺会让我们数字**变好看**，
     所以同时报 SPY 和等权池两套，**不许只报好看的那套**。
"""
import glob, json, os, sys
import numpy as np, pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "组合日收益_1106"))
sys.path.insert(0, os.path.join(ROOT, "probe", "分行情比_1107"))
import 组合日收益_1107 as 核                      # noqa: E402

_EW = None


def 等权池():
    """★★★ 对口标尺：同一个池子、等权、买入持有的日收益。
    ★ 每天只用当天和前一天都有价的票（★★ 新上市/退市不会毒掉整天）。
    ★★★ 报出每天参与的票数，免得「某天只剩 3 只票」偷偷进了结论。"""
    global _EW
    if _EW is None:
        close = pd.read_parquet(核.PANEL)["close"]
        if isinstance(close, pd.Series):
            close = close.unstack()
        r = close.pct_change()
        # ★ 去掉单日 |涨跌| > 100% 的格子（★★ 拆股/数据错，不替它猜）
        r = r.where(r.abs() <= 1.0)
        n = r.notna().sum(axis=1)
        _EW = (r.mean(axis=1, skipna=True), n)
    return _EW


def 年化(r: pd.Series) -> float:
    r = r.dropna()
    if len(r) < 20:
        return float("nan")
    return float((1 + r).prod() ** (252 / len(r)) - 1) * 100


def 一条(p: str) -> dict:
    d = pd.read_csv(p)
    for c in ("entry_date", "exit_date"):
        d[c] = pd.to_datetime(d[c], errors="coerce")
    for c in ("shares", "entry_price", "net_pnl"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["symbol", "entry_date", "shares", "entry_price", "net_pnl"])
    eq, 敞口, _ = 核.逐日(d)
    if eq is None:
        return {"★跑失败": "面板里没有这条臂的任何票"}
    r = eq.pct_change()
    spy_r = 核.spy().reindex(eq.index).ffill().pct_change()
    ew_r, ew_n = 等权池()
    ew_r = ew_r.reindex(eq.index)
    out = {"★平均敞口pct": round(float(敞口.mean()) * 100, 1),
           "★等权池每天参与票数_中位": int(ew_n.reindex(eq.index).median())}

    # ★★★ ② 两把标尺并排（同敞口口径，★ 和主判据一致）
    for 标尺名, b in (("标尺A_SPY大盘股", spy_r), ("★★★标尺B_等权同池_对口", ew_r)):
        同敞口 = b * 敞口.shift(1)
        y = r.dropna(); x = 同敞口.reindex(y.index)
        a = 核.回归(y, x)
        out[标尺名] = {
            "★alpha年化pct": (None if "★算不出" in a else round(a["★★★alpha_年化pct"], 2)),
            "★t": (None if "★算不出" in a else round(a["★★alpha的t值_NeweyWest"], 2)),
            "beta": (None if "★算不出" in a else round(a["beta"], 2)),
            "★标尺自己的年化pct": round(年化(b.reindex(y.index)), 2),
        }

    # ★ ① 分大盘涨跌段（Lin：「大盘亏钱我没亏钱也算好」）
    for 名, m in (("大盘涨的天", spy_r > 0), ("★大盘跌的天", spy_r < 0)):
        m = m.reindex(r.index).fillna(False)
        y = r[m].dropna()
        if len(y) < 60:
            out[名] = {"★算不出": f"只有 {len(y)} 天"}; continue
        out[名] = {
            "交易日": int(len(y)),
            "★我们这些天累计pct": round(float((1 + y).prod() - 1) * 100, 2),
            "★大盘这些天累计pct": round(float((1 + spy_r.reindex(y.index)).prod() - 1) * 100, 2),
            "★★等权同池这些天累计pct": round(float((1 + ew_r.reindex(y.index).fillna(0)).prod() - 1) * 100, 2),
        }
    # ★★ 下行捕获率：大盘跌的天我们吃掉多少（<100% = 比大盘少亏）
    dn = out.get("★大盘跌的天", {})
    if "交易日" in dn and dn["★大盘这些天累计pct"] != 0:
        out["★★下行捕获率pct"] = round(dn["★我们这些天累计pct"] / dn["★大盘这些天累计pct"] * 100, 1)
    return out


def main() -> int:
    ew_r, ew_n = 等权池()
    报 = {"★这一份做什么":
          "★★★ 换对口标尺（Lin 1107 09:10）。★ 我们池子 2,770 只、大量中小盘，"
          "却一直拿 SPY（大盘股）当标尺 —— ★★ 而这十年 SPY 被几只巨头撑得极高。"
          "★★★ 对口标尺用我们**自己池子等权买入持有**造（同池同权）。"
          "★ 同时报 SPY 和等权池两套，口径⑥：不许只报好看的那套。",
          "★★等权同池全期年化pct": round(年化(ew_r), 2),
          "★SPY全期年化pct": round(年化(核.spy().pct_change()), 2),
          "★等权池每天参与票数_中位": int(ew_n.median())}
    print(f"★★★ 等权同池全期年化 {报['★★等权同池全期年化pct']}% "
          f"vs SPY {报['★SPY全期年化pct']}% (每天{报['★等权池每天参与票数_中位']}只)", flush=True)
    fs = sorted(glob.glob("probe/挂闸_1106/ledgers_1106/REAL__*.csv")) + \
         sorted(glob.glob("probe/新策略_1106/**/REAL__融-*.csv", recursive=True))
    失败 = 0
    for f in fs:
        名 = os.path.basename(f)[6:-4]
        try:
            报[名] = 一条(f)
        except Exception as e:
            报[名] = {"★跑失败": repr(e)[:200]}; 失败 += 1
            print("⚠ 失败", 名, flush=True); continue
        A, B = 报[名]["标尺A_SPY大盘股"], 报[名]["★★★标尺B_等权同池_对口"]
        print(f"✓ {名:<26} SPY: {A['★alpha年化pct']}/{A['★t']}   "
              f"等权同池: {B['★alpha年化pct']}/{B['★t']}", flush=True)
    报["★★★失败条数"] = 失败
    with open("probe/分行情比_1107/对口指数_报告_1107.json", "w", encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print(f"★ 写完;★★★ 失败 {失败} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
