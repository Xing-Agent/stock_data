# -*- coding: utf-8 -*-
"""
★★★ 技-7 / 技-8 / 技-9 · **组合层指标**(★ 台账第 7 格:「跑完了,但组合层指标没量」)。

★ 为什么要单独量:★★ `技789结果_1106.json` 里那一套是**逐笔**口径(大盘替身:同进同出比大盘),
   ★★★ 而《91》定的新尺子是**组合层**(每天合成一个组合算净值)——
   ★ 《83》第三步写明:**这一步最关键,跳了会把成绩虚报好几倍**。
→ ★★ 所以这里拿同一批流水,按《91》那一套**组合层**再量一遍,两套并排报。

★★★ 指标全部来自 `probe/买入持有新尺子_1106/新尺子_1106.py`(★ 同一份实现,不另造):
   信息比率 · 对 SPY 回归 alpha 与 Newey-West t · 卡玛 · 溃疡指数 · 最大回撤 · 回本天数
★★ 利润因子**降为辅助**(★ 工单优先级② 定的);❌ 赢随机**不出现**(已作废)。
★ engine 零改动;只读流水,不重跑回测。
"""
from __future__ import annotations
import importlib.util, io, json, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "挂件_1106"))
sys.path.insert(0, os.path.join(ROOT, "probe", "技789_1106"))
os.chdir(ROOT)

spec = importlib.util.spec_from_file_location("_m91", "probe/买入持有新尺子_1106/新尺子_1106.py")
M = importlib.util.module_from_spec(spec); spec.loader.exec_module(M)
from engine import data                                            # noqa: E402
import 台_公共_1106 as T                                            # noqa: E402

ARMS = os.path.join(ROOT, "probe", "技789_1106", "arms_1106")
逐笔 = os.path.join(ROOT, "probe", "技789_1106", "技789结果_1106.json")
PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
OUT = os.path.join(HERE, "组合层_报告_1107.json")


def 一臂(d: pd.DataFrame, cl, spy) -> dict:
    if len(d) < 10:
        return {"★跑失败": f"只剩 {len(d)} 笔 —— **样本太少,不出数**"}
    eq, 在场, _ = M.逐日净值(d, cl)
    win = (eq.index >= M.PERF0) & (eq.index <= M.PERF1)
    mm = M.一条指标(eq.loc[win], 在场.loc[win], spy)
    分母 = eq.reindex(d["entry_date"]).to_numpy()
    ok = np.isfinite(分母) & (分母 > 0)
    pct = pd.Series(np.where(ok, d["net_pnl"].to_numpy() / 分母 * 100.0, np.nan)).dropna()
    赢, 亏 = pct[pct > 0], pct[pct < 0]
    return {"笔数": int(len(d)),
            "★★★信息比率": mm.get("★★★⑦信息比率"),
            "★★★alpha年pct": mm.get("★★★⑧alpha年化pct"),
            "★★★alpha_t_NW": mm.get("★★★⑧alpha_t_NeweyWest"),
            "★★★卡玛比率": mm.get("★★★④卡玛比率"),
            "★★★溃疡指数": mm.get("★★★⑤溃疡指数"),
            "★★★最大回撤pct": mm.get("★★★③最大回撤pct"),
            "★★★回本天数": mm.get("★★★⑥回本交易日"),
            "全期年化pct": mm.get("★★★①全期年化pct"),
            "平均投入pct": mm.get("★★★⑨平均投入比例pct"),
            "利润因子(辅助)": (round(float(赢.sum() / abs(亏.sum())), 3)
                          if len(亏) and 亏.sum() != 0 else None)}


def main() -> int:
    w = pd.read_parquet(PANEL); cl = w["close"]; del w
    spy = data.load_benchmark("SPY")["close"]
    逐 = json.load(io.open(逐笔, encoding="utf-8"))

    out = {"★★★这一份是什么": "技-7/8/9 的**组合层**指标(★ 逐笔那一套在 技789结果_1106.json)",
           "★口径": {"组合层实现": "probe/买入持有新尺子_1106/新尺子_1106.py(★ 同一份,不另造)",
                    "窗口": f"{M.PERF0} → {M.PERF1}",
                    "池": 逐.get("★口径", {}).get("池子口径"),
                    "★★两套怎么读": "逐笔 = 同进同出比大盘(主判据);组合层 = 每天合成组合算净值(《83》第三步)",
                    "❌赢随机": "不出现(已作废)", "利润因子": "降为辅助(工单优先级②)"},
           "逐臂": {}}

    SPY全期 = None
    for 卡 in ("技-7", "技-8", "技-9"):
        for 名 in 逐.get(卡, {}):
            label = f"{卡}|{名}"
            p = T.臂文件(ARMS, label)
            if not os.path.exists(p):
                out["逐臂"][label] = {"★★★跑失败": f"流水不在({os.path.basename(p)}) —— ★ 先跑 跑技789_1106.py"}
                print(f"  ✗✗✗ {label} 流水不在", flush=True)
                continue
            d = pd.read_csv(p)
            for c in ("entry_date", "exit_date"):
                d[c] = pd.to_datetime(d[c], errors="coerce")
            for c in ("net_pnl", "shares", "entry_price", "notional_in"):
                d[c] = pd.to_numeric(d[c], errors="coerce")
            d = d.dropna(subset=["entry_date", "net_pnl", "shares", "entry_price"])
            组 = 一臂(d, cl, spy)
            逐一 = 逐[卡][名]
            out["逐臂"][label] = {
                "★组合层(《91》新尺子)": 组,
                "★逐笔(大盘替身·主判据)": {
                    "笔数": 逐一.get("笔数"), "比同期大盘pct": 逐一.get("★比同期大盘pct"),
                    "t": 逐一.get("t"), "判定": 逐一.get("★★★判定"),
                    "平均持有天": 逐一.get("平均持有天")},
                "★★两套同向吗": None}
            a = 组.get("★★★alpha年pct"); b = 逐一.get("★比同期大盘pct")
            if a is not None and b is not None:
                out["逐臂"][label]["★★两套同向吗"] = (
                    "同向" if (a > 0) == (b > 0) else "★★★ 反向(要查)")
            if "★跑失败" in 组:
                print(f"  ✗ {label} {组['★跑失败']}", flush=True)
            else:
                print(f"  ✓ {label[:46]:46s} alpha {组['★★★alpha年pct']:>7}% "
                      f"t={组['★★★alpha_t_NW']:>6} 卡玛 {组['★★★卡玛比率']:>6} "
                      f"回撤 {组['★★★最大回撤pct']:>7}% | 逐笔 {b}% t={逐一.get('t')}", flush=True)

    # ★★★ 一句总结:组合层里有几条正显著(★ 这是现在最该问的那个数)
    正 = [k for k, v in out["逐臂"].items()
          if isinstance(v.get("★组合层(《91》新尺子)"), dict)
          and (v["★组合层(《91》新尺子)"].get("★★★alpha年pct") or 0) > 0
          and (v["★组合层(《91》新尺子)"].get("★★★alpha_t_NW") or 0) >= 1.96]
    负 = [k for k, v in out["逐臂"].items()
          if isinstance(v.get("★组合层(《91》新尺子)"), dict)
          and (v["★组合层(《91》新尺子)"].get("★★★alpha_t_NW") or 0) <= -1.96]
    out["★★★★★一句话"] = {"臂数": len(out["逐臂"]),
                        "★★★组合层正显著(alpha>0 且 t≥1.96)": len(正), "是哪几条": 正,
                        "组合层负显著(t≤−1.96)": len(负), "负的是哪几条": 负}
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(out, ensure_ascii=False, indent=1, default=str))
    print(f"\n★★★ 组合层正显著 {len(正)} 条 / 负显著 {len(负)} 条 / 共 {len(out['逐臂'])} 条")
    print(f"★ 写到 {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
