# -*- coding: utf-8 -*-
"""
★★★ 大盘替身口径复核（B 路 1106 · 做挂件测试台时顺手查出来的）

大白话:**大盘替身把「当天进、当天被止损」的单子整笔扔掉了。**
  ★ 这些单子几乎全是亏的(当天就打到止损)→ 扔掉它们 = 只留下活过第一天的单子
  → ★★★ 成绩被抬高。止损越紧的策略(技-14 那一族)被抬得越多。

★ 代码出处:probe/大盘替身_1106/大盘替身_1106.py 第 70 行附近
     `if i >= len(idx) or j >= len(idx) or j <= i: 算不出 += 1; continue`
  ★★ j <= i 就是「离场日 = 进场日」→ 整笔从**真策略那一侧**也扔了(不是只扔替身)。

★ 这一份做的事:同一批流水,三种口径并排算(★ 不改原脚本,只读它的流水):
  A · 原口径:收盘→收盘,扔掉当天进当天出
  B · 原口径但**不扔**:当天进当天出的那笔,替身用 SPY 当天「开→收」
  C · ★ 时点对齐:进场用 SPY **开盘**(策略次日开盘买);
      离场 —— 规则/时间离场用 SPY **离场日开盘**(策略也是开盘卖);
              止损/退市用 SPY **离场日收盘**(盘中成交,取收盘是对替身**不利**的一侧 —— 见注)
  ★ 注:止损盘中成交,真实时点在开盘和收盘之间 —— C 用收盘,对替身已是**有利于我们**的近似?
     不一定;所以另报 C' = 止损也用开盘,两个夹出范围。

engine 零改动;只读已入库流水 + 用覆盖层在新池重跑技-14 两版(研发池)。
"""
from __future__ import annotations
import glob, io, json, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import 台_公共_1106 as T                                            # noqa: E402

OUT = os.path.join(HERE, "替身口径复核_1106.json")


def 算(d: pd.DataFrame) -> dict:
    d = d.copy()
    d["entry_date"] = pd.to_datetime(d["entry_date"]); d["exit_date"] = pd.to_datetime(d["exit_date"])
    d["ret"] = d["net_pnl"].astype(float) / d["notional_in"].astype(float)
    d = d[np.isfinite(d["ret"])]
    b = T.data.load_benchmark("SPY")
    o, c = b["open"].to_numpy(float), b["close"].to_numpy(float)
    idx = b.index
    i = idx.searchsorted(d["entry_date"].values); j = idx.searchsorted(d["exit_date"].values)
    ok = (i < len(idx)) & (j < len(idx))
    d = d[ok]; i = i[ok]; j = j[ok]
    同日 = (j == i)
    止损类 = d["reason"].astype(str).isin(["止损", "退市结算", "期末平仓"]).to_numpy()
    日 = d["entry_date"].dt.strftime("%Y-%m-%d")
    out = {"总笔数": int(len(d)), "★当天进当天出笔数": int(同日.sum()),
           "★当天进当天出占比": round(float(同日.mean()), 4),
           "当天进当天出的平均净收益pct": (round(float(d["ret"][同日].mean()) * 100, 3) if 同日.any() else None),
           "当天进当天出里亏钱的占比": (round(float((d["ret"][同日] < 0).mean()), 4) if 同日.any() else None)}

    def one(nm, spy_ret, keep):
        x = (d["ret"].to_numpy() - spy_ret)[keep]
        s = pd.Series(x, index=d.index[keep])
        r = T.聚类t(s, 日[keep])
        bb = T.块重抽样(s, 日[keep])
        out[nm] = {"笔数": int(keep.sum()), "真_每笔pct": round(float(d["ret"].to_numpy()[keep].mean()) * 100, 4),
                  "替身_每笔pct": round(float(np.nanmean(spy_ret[keep])) * 100, 4),
                  "★差pct": round(r["均值"] * 100, 4), "t": round(r["t"], 2),
                  "月块95%区间pct": [round(v * 100, 4) for v in bb["95%区间"]] if bb.get("95%区间") else None,
                  "★判定": T.判(r["t"], bb.get("区间不含0", False))}

    A = c[j] / c[i] - 1
    one("A·原口径(扔当天进当天出)", A, ~同日)
    B = np.where(同日, c[i] / o[i] - 1, A)
    one("B·原口径但不扔(当天那笔用SPY开→收)", B, np.ones(len(d), bool))
    ex_px = np.where(止损类, c[j], o[j])
    C = ex_px / o[i] - 1
    one("C·时点对齐(开盘进;规则出=开盘,止损出=收盘)", C, np.ones(len(d), bool))
    C2 = o[j] / o[i] - 1
    C2 = np.where(同日, c[i] / o[i] - 1, C2)     # ★ 同日止损:开盘进、盘中出 → 替身取当天开→收
    one("C'·时点对齐(止损也按开盘;同日用开→收)", C2, np.ones(len(d), bool))
    return out


def main() -> int:
    报 = {"★这一份查什么": __doc__.strip().split("\n\n")[1]}
    # ① 已入库的老流水(和 大盘替身_报告 里那几条同名)
    for p in sorted(glob.glob("probe/gates_rebuild_1030/ledgers_1030/REAL__*技-14*.csv")):
        nm = os.path.basename(p)[6:-4]
        try:
            报[nm] = 算(pd.read_csv(p))
        except Exception as e:
            报[nm] = {"★跑失败": repr(e)[:300]}
        print("✓", nm, flush=True)
    # ② 新池研发池重跑技-14 两版(★ 挂闸那一轮的「不挂闸」就是原著版)
    for cfgp in ("engine/configs/技-14-原著.yaml", "engine/configs/技-14-XING.yaml"):
        nm = "新池重跑·" + os.path.basename(cfgp)[:-5]
        try:
            raw = T.读配置(cfgp); m, _ = T.建矩阵(raw); led, info = T.跑(raw, m)
            r = 算(led); r["跑批信息"] = info; 报[nm] = r
            del m
        except Exception as e:
            报[nm] = {"★跑失败": repr(e)[:300]}
        print("✓", nm, flush=True)
    失败 = [k for k, v in 报.items() if isinstance(v, dict) and "★跑失败" in v]
    报["★★★失败条数"] = len(失败)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1, default=str))
    if 失败:
        print("⚠⚠⚠ 有跑失败:", 失败)
    print("★ 写到", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
