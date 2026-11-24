# -*- coding: utf-8 -*-
"""《431 拍板》要干啥第 4 条：同一套规则搬到 SOXX、SMH、BTC、ETH；再加一版「大盘总开关打开才空」（标普在跌势时才开）。
另：成本价止损的几种改法并排（《434》第三节）。
这一版是把周线那套原样搬过去（比特币、半导体也按周线认顶），没有按《423》降一级 —— 降级版下一步做。
锁数据：2022-01-01 ~ 2025-12-31 开的腿单独存、不打印、不进统计（《422 拍板》）。大指数的长历史不受这条限制的部分只报到 2021 年底。"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE))
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
L = mod("L", os.path.join(HERE, "长历史_1124.py")); V2 = mod("V2", os.path.join(HERE, "三层状态机_第二版_1124.py")); SC = mod("SC", os.path.join(ROOT, "probe/历史扫描定级别_1123/扫描_1123.py")); M4 = SC.M
def 锁(T): return (T["开"] >= "2022-01-01") & (T["开"] <= "2025-12-31") if len(T) else pd.Series([], dtype=bool)
def 统(T):
    o = {}
    for k, g in T.groupby("第几次"):
        r = g["这一腿pct"]; o[int(k)] = {"腿数": int(len(g)), "每腿平均pct": round(float(r.mean()), 2), "中位pct": round(float(r.median()), 2), "赚的占比pct": round(float((r > 0).mean() * 100), 1), "最亏pct": float(r.min()), "最赚pct": float(r.max())}
    o["合计占账户pct"] = round(float(T["占账户pct"].sum()), 1) if len(T) else 0.0; return o
if __name__ == "__main__":
    SPX = L.读("标普500指数"); Rspx, _, _ = V2.跑(SPX); 大盘跌势 = (Rspx["档"] == "跌势")
    A = {"SOXX": SC.soxx(), "SMH": SC.etf("SMH"), "BTC": M4.币日线("BTC"), "ETH": M4.币日线("ETH")}
    out = {}
    LV = {"SOXX": "周", "SMH": "周", "BTC": "日", "ETH": "日"}
    for nm0, D in list(A.items()) + [(k + "·低一级", v) for k, v in A.items()]:
        nm = nm0; kw = {"级别": LV[nm0.split("·")[0]]} if "低一级" in nm0 else {}
        R, EV, T = V2.跑(D, **kw); out[nm] = {"数据从": str(D.index[0].date()), "级别": kw.get("级别", "月")}
        if len(T):
            T[锁(T)].to_csv(os.path.join(HERE, "out", f"主战场_{nm}_锁住的腿_不许看.csv"), index=False); U = T[~锁(T)].copy()
            g = 大盘跌势.reindex(pd.to_datetime(U["开"]), method="ffill").to_numpy(); U["大盘在跌势"] = g
            U.to_csv(os.path.join(HERE, "out", f"主战场_{nm}_每一腿.csv"), index=False)
            out[nm]["全部"] = 统(U); out[nm]["大盘在跌势时开的"] = 统(U[U["大盘在跌势"]]); out[nm]["大盘不在跌势时开的"] = 统(U[~U["大盘在跌势"]])
            out[nm]["转空事件"] = [e for e in EV if e["事"].startswith(("转空", "复跌")) and not ("2022" <= e["日期"][:4] <= "2025")]
            out[nm]["今天"] = R["档"].iloc[-1]
        print("==", nm, json.dumps({k: v for k, v in out[nm].items() if k != "转空事件"}, ensure_ascii=False)); print("   ", [(e["事"][:5], e["日期"], e.get("离顶pct")) for e in out[nm].get("转空事件", [])])
        if len(T) and "低一级" in nm: print(U[["第几次", "开", "平", "这一腿pct", "之后最多再跌pct", "怎么平", "大盘在跌势"]].to_string())
    # 成本价止损的几种改法（三个大指数 + SOXX；大指数只到 2021 年底开的腿）
    BE = {}
    for nm, D in (("标普500指数", SPX), ("道琼斯工业指数", L.读("道琼斯工业指数")), ("纳斯达克综合指数", L.读("纳斯达克综合指数")), ("SOXX", A["SOXX"])):
        BE[nm] = {}
        for v in ("成本", "成本加1ATR", "只管第一腿", "无"):
            T = V2.跑(D, 成本保护=v)[2]; T = T[~锁(T)]; x = 统(T)
            BE[nm][v] = {"第1次": x.get(1, {}).get("每腿平均pct"), "第2次": x.get(2, {}).get("每腿平均pct"), "第2次腿数": x.get(2, {}).get("腿数"), "第2次赚的占比": x.get(2, {}).get("赚的占比pct"), "第3次": x.get(3, {}).get("每腿平均pct"), "合计占账户pct": x["合计占账户pct"]}
        print("成本保护", nm, json.dumps(BE[nm], ensure_ascii=False))
    out["成本保护对比"] = BE
    json.dump(out, open(os.path.join(HERE, "out", "主战场_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
