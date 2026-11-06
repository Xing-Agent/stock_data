# -*- coding: utf-8 -*-
"""
★★★ 用《91》那一套**组合层**指标量仓位臂（★ 大盘替身对仓位几乎是瞎的，见跑批脚本文件头）。
★★ 指标实现**直接 import** `probe/买入持有新尺子_1106/新尺子_1106.py` —— ★★★ 不另造一份
   （★ 第 47 处的教训：不许有两份实现，否则下次还会分叉）。
★ 价格面板用新池 parquet（★★ 老池 `data.price_panel` 覆盖不到新池的票）。
"""
from __future__ import annotations
import glob, importlib.util, json, os, sys
import numpy as np, pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
spec = importlib.util.spec_from_file_location("_m91", "probe/买入持有新尺子_1106/新尺子_1106.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
from engine import data                                            # noqa: E402

PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
OUT = "probe/测仓位_1107/量仓位_报告_1107.json"
_CL = None


def 收盘():
    global _CL
    if _CL is None:
        w = pd.read_parquet(PANEL)
        _CL = w["close"]
        del w
    return _CL


def main() -> int:
    cl = 收盘()
    spy = data.load_benchmark("SPY")["close"]
    报 = {"★口径": {
        "判据": "★★★ 组合层（《91》同一套实现）—— 年化 · 最大回撤 · 卡玛 · 溃疡 · 回本天数 · 信息比率 · alpha(Newey-West)",
        "为什么不用大盘替身": "★ 它量每笔收益率，而换仓位法不改同一笔的进出场价 → 对仓位几乎瞎",
        "净值重建": "★★ 已修第 54 处（已实现在离场日当天落账）",
        "★★★必读旁注": "★ 回撤类指标天然偏向低投入 → 必须和「平均投入比例」并排读",
        "绩效窗口": [str(M.PERF0.date()), str(M.PERF1.date())],
    }}
    失败 = []
    for f in sorted(glob.glob("probe/测仓位_1107/ledgers_1107/REAL__*.csv")):
        名 = os.path.basename(f)[6:-4]
        try:
            d = pd.read_csv(f)
            for c in ("entry_date", "exit_date"):
                d[c] = pd.to_datetime(d[c], errors="coerce")
            for c in ("net_pnl", "shares", "entry_price", "r_multiple_net"):
                d[c] = pd.to_numeric(d[c], errors="coerce")
            n0 = len(d)
            d = d.dropna(subset=["entry_date", "net_pnl", "shares", "entry_price"])
            eq, 在场, 缺票 = M.逐日净值(d, cl)
            win = (eq.index >= M.PERF0) & (eq.index <= M.PERF1)
            m = M.一条指标(eq.loc[win], 在场.loc[win], spy)
            分母 = eq.reindex(d["entry_date"]).to_numpy()
            ok = np.isfinite(分母) & (分母 > 0)
            pct = pd.Series(np.where(ok, d["net_pnl"].to_numpy() / 分母 * 100.0, np.nan)).dropna()
            赢, 亏 = pct[pct > 0], pct[pct < 0]
            m["辅助_笔数"] = int(len(pct))
            m["辅助_跳过笔数"] = int(n0 - len(d))
            m["辅助_利润因子_账户pct口径"] = (round(float(赢.sum() / abs(亏.sum())), 3)
                                     if len(亏) and 亏.sum() != 0 else None)
            m["辅助_胜率"] = round(float((pct > 0).mean()), 4) if len(pct) else None
            if 缺票:
                m["★⑰面板里没有的票"] = [len(缺票), sorted(缺票)[:5]]
            报[名] = m
            print("✓", 名, flush=True)
        except Exception as e:
            报[名] = {"★跑失败": repr(e)[:300]}
            失败.append(名)
            print("✗", 名, repr(e)[:160], flush=True)
    报["★★★跑失败的"] = {"条数": len(失败), "名单": 失败}
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print(f"★ 写到 {OUT} | 跑失败 {len(失败)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
