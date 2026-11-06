# -*- coding: utf-8 -*-
"""
★★★ 给 A 路那 33 条基本面臂补算**组合层指标**（★ 工单优先级②的后半截、《92》第三节③）。

★★ 为什么要补:★ 《88》那一版用的是**旧版大盘替身口径**(★★★ 第 47 处错之前的),
   ★★ 而现在的主判据已经换成《91》那一套**组合层**指标。
★ 指标实现**直接 import** `probe/买入持有新尺子_1106/新尺子_1106.py` ——
   ★★★ 不另造一份(第 47 处的教训:不许有两份实现)。

★★★ 两件如实标的:
   ① **技-7/8/9 那 11 条臂量不了** —— ★ 它们的流水在 `probe/新策略_1106/ledgers_1106/`,
     ★★ 那个目录在 .gitignore 里,★★★ **这个容器里是空的** → 要量只能**重跑回测**。
   ② 回撤类指标**天然偏向低投入** → ★★ 必须和「平均投入比例」并排读(★ 照《91》的旁注)。
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
LED = "probe/基本面跑批_1106/ledgers"
OUT = "probe/组合层补算_1107/基本面33条_组合层_1107.json"


def main() -> int:
    w = pd.read_parquet(PANEL); cl = w["close"]; del w
    spy = data.load_benchmark("SPY")["close"]
    报 = {"★口径": {
        "判据": "★★★ 组合层(《91》同一套实现):年化 · 最大回撤 · 卡玛 · 溃疡 ·"
              " 回本天数 · 信息比率 · 对SPY回归alpha与t(Newey-West)",
        "流水来源": LED + "（★ 33 条，已入库）",
        "净值重建": "★★ 已修第 54 处（离场日当天落账）",
        "★★★量不了的": "技-7/8/9 那 11 条臂 —— ★ 流水目录 probe/新策略_1106/ledgers_1106/"
                    " 在 .gitignore 里，★★★ 本容器为空 → 要量只能重跑回测",
        "★★★必读旁注": "★ 回撤类指标天然偏向低投入 → 必须和「平均投入比例」并排读",
        "绩效窗口": [str(M.PERF0.date()), str(M.PERF1.date())],
    }}
    失败 = []
    文件 = sorted(glob.glob(os.path.join(LED, "REAL__*.csv")))
    print(f"★ 找到 {len(文件)} 条流水", flush=True)
    for f in 文件:
        名 = os.path.basename(f)[6:-4]
        try:
            d = pd.read_csv(f)
            for c in ("entry_date", "exit_date"):
                d[c] = pd.to_datetime(d[c], errors="coerce")
            for c in ("net_pnl", "shares", "entry_price", "r_multiple_net"):
                if c in d.columns:
                    d[c] = pd.to_numeric(d[c], errors="coerce")
            n0 = len(d)
            d = d.dropna(subset=["entry_date", "net_pnl", "shares", "entry_price"])
            eq, 在场, 缺票 = M.逐日净值(d, cl)
            win = (eq.index >= M.PERF0) & (eq.index <= M.PERF1)
            m = M.一条指标(eq.loc[win], 在场.loc[win], spy)
            分母 = eq.reindex(d["entry_date"]).to_numpy()
            ok = np.isfinite(分母) & (分母 > 0)
            pct = pd.Series(np.where(ok, d["net_pnl"].to_numpy() / 分母 * 100.0,
                                     np.nan)).dropna()
            赢, 亏 = pct[pct > 0], pct[pct < 0]
            m["辅助_笔数"] = int(len(pct))
            # ★ 规矩⑰:跳过了多少笔必须报
            m["★⑰跳过笔数"] = int(n0 - len(d))
            m["辅助_利润因子_账户pct口径"] = (round(float(赢.sum() / abs(亏.sum())), 3)
                                     if len(亏) and 亏.sum() != 0 else None)
            m["辅助_胜率"] = round(float((pct > 0).mean()), 4) if len(pct) else None
            m["辅助_中位持有天"] = (round(float(pd.to_numeric(
                d.get("holding_days"), errors="coerce").median()), 1)
                if "holding_days" in d.columns else None)
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
    print(f"\n★ 写到 {OUT} | ★★★ 跑失败 {len(失败)} 条"
          + ("（★ 必须大声报，不许打空表）" if 失败 else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
