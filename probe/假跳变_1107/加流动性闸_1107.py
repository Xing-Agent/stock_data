# -*- coding: utf-8 -*-
"""
★★★★★ 基-7 烟蒂那一族:**剔掉假跳变之后它还是正显著**(t 2.19 / 2.13)——
   ★ 所以要接着问最后一个问题:**这些笔买得到吗？**

★★ 为什么必须问:★ 逐笔拆开看到的:
   · **86% 的笔是「低流动性」档**(196/227)
   · 进场时 ADV20 **中位只有 70~144 万美元**,★★★ **最小 7,003 美元/天**
   · 进场价中位 **3.2~3.3 美元**,★★ 10 分位 **0.69~0.99 美元**,最小 **0.04 美元**
→ ★★★ 一天成交 7 千美元的票,**我们按收盘价成交的假设根本不成立**。

★★★ 做法:在**已剔掉假跳变**的流水上,再按进场时 ADV20 加一道门槛,逐档看成绩。
   ★ 三档(★★ 原著没给 → 相邻三点,规矩②):**100 万 / 500 万 / 2000 万**美元/天。
★★★ 规矩⑰:每一档都要报**剔掉多少笔**和**两批成绩差多少**。
"""
from __future__ import annotations
import glob, importlib.util, io, json, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE); os.chdir(ROOT)
spec = importlib.util.spec_from_file_location("_m91", "probe/买入持有新尺子_1106/新尺子_1106.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
from engine import data                                            # noqa: E402
import 扫假跳变_1107 as 扫                                          # noqa: E402

PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
OUT = os.path.join(HERE, "加流动性闸_报告_1107.json")
容差日 = 15
门槛 = [1_000_000, 5_000_000, 20_000_000]
目标 = ["基-7_早期巴菲特烟蒂·八毛", "基-7_早期巴菲特烟蒂·五毛",
       "基-7_早期巴菲特烟蒂·三分之二", "基-20_价值动量双因子·价值权重0.3"]


def main() -> int:
    w = pd.read_parquet(PANEL); cl, vol = w["close"], w["volume"]; del w
    def 前(x): return x.shift(1).rolling(扫.窗, min_periods=扫.窗).median()
    def 后(x): return x.iloc[::-1].rolling(扫.窗, min_periods=扫.窗).median().iloc[::-1]
    pr, vr = 后(cl) / 前(cl), 后(vol) / 前(vol)
    疑 = (((pr >= 扫.跳变门槛) & (vr <= 1 / 扫.量反向容差))
          | ((pr <= 1 / 扫.跳变门槛) & (vr >= 扫.量反向容差))).fillna(False)
    脏 = {}
    ii, jj = np.where(疑.to_numpy())
    for i, j in zip(ii, jj):
        脏.setdefault(str(cl.columns[j]), []).append(cl.index[i])
    spy = data.load_benchmark("SPY")["close"]

    out = {"★口径": {
        "基线": "★★ 已先剔掉「跨过假跳变日」的笔（±15 日容差）",
        "闸": "★ 进场时 ADV20 ≥ 门槛（★★ 原著没给 → 相邻三点，规矩②）",
        "三档": [f"{x/1e6:.0f}00万" if x < 1e7 else f"{x/1e6:.0f}00万" for x in 门槛],
        "★★★这一步在问什么": "★ 这条策略的成绩是不是**只在买不到的票上**",
    }, "逐条": {}}

    for f in sorted(glob.glob("probe/基本面跑批_1106/ledgers/REAL__*.csv")):
        名 = os.path.basename(f)[6:-4]
        if 名 not in 目标:
            continue
        d = pd.read_csv(f)
        for c in ("entry_date", "exit_date"):
            d[c] = pd.to_datetime(d[c], errors="coerce")
        for c in ("net_pnl", "shares", "entry_price", "notional_in", "adv20_at_entry"):
            d[c] = pd.to_numeric(d[c], errors="coerce")
        d = d.dropna(subset=["entry_date", "net_pnl", "shares", "entry_price"])
        脏标 = np.zeros(len(d), dtype=bool)
        for k, (_, row) in enumerate(d.iterrows()):
            ds = 脏.get(row["symbol"])
            if not ds:
                continue
            a = row["entry_date"] - pd.Timedelta(days=容差日)
            b = (row["exit_date"] if pd.notna(row["exit_date"]) else row["entry_date"]) \
                + pd.Timedelta(days=容差日)
            if any(a <= t <= b for t in ds):
                脏标[k] = True
        base = d.loc[~脏标].copy()
        rec = {"剔假跳变后笔数": int(len(base)), "档": {}}

        def 量(dd):
            if len(dd) < 10:
                return {"★跑失败": f"只剩 {len(dd)} 笔 —— **样本太少，不出数**"}
            eq, 在场, _ = M.逐日净值(dd, cl)
            win = (eq.index >= M.PERF0) & (eq.index <= M.PERF1)
            mm = M.一条指标(eq.loc[win], 在场.loc[win], spy)
            分母 = eq.reindex(dd["entry_date"]).to_numpy()
            ok = np.isfinite(分母) & (分母 > 0)
            pct = pd.Series(np.where(ok, dd["net_pnl"].to_numpy() / 分母 * 100.0, np.nan)).dropna()
            赢, 亏 = pct[pct > 0], pct[pct < 0]
            return {"笔数": int(len(dd)),
                    "alpha年pct": mm.get("★★★⑧alpha年化pct"),
                    "★★★alpha_t": mm.get("★★★⑧alpha_t_NeweyWest"),
                    "卡玛": mm.get("★★★④卡玛比率"),
                    "最大回撤pct": mm.get("★★★③最大回撤pct"),
                    "平均投入pct": mm.get("★★★⑨平均投入比例pct"),
                    "利润因子": (round(float(赢.sum() / abs(亏.sum())), 3)
                             if len(亏) and 亏.sum() != 0 else None)}

        rec["档"]["无闸"] = 量(base)
        for g in 门槛:
            sub = base[base["adv20_at_entry"] >= g]
            r2 = 量(sub)
            r2["★⑰剔掉笔数"] = int(len(base) - len(sub))
            r2["★⑰剔掉那批每笔pct中位"] = (round(float(
                (base[base["adv20_at_entry"] < g]["net_pnl"]
                 / base[base["adv20_at_entry"] < g]["notional_in"] * 100).median()), 2)
                if len(base) > len(sub) else None)
            rec["档"][f"ADV20≥{g/1e6:.0f}00万"] = r2
        out["逐条"][名] = rec
        print(f"\n=== {名} （剔假跳变后 {len(base)} 笔）===", flush=True)
        for g, v in rec["档"].items():
            if "★跑失败" in v:
                print(f"   {g:14s} {v['★跑失败']}", flush=True)
            else:
                print(f"   {g:14s} 笔{v['笔数']:4d} alpha {v['alpha年pct']:>7}%  "
                      f"t={v['★★★alpha_t']:>6}  卡玛 {v['卡玛']:>6}  利因 {v['利润因子']}",
                      flush=True)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(f"\n★ 写到 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
