# -*- coding: utf-8 -*-
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, os.path.join(HERE, f)); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
L = mod("L", "长历史_1124.py"); V2 = mod("V2", "三层状态机_第二版_1124.py")
VAR = {"新版（431 拍板）": {}, "只把跟进日改回全平": {"跟进日全平": True}, "只把 0.382 改回算到位": {"允许0382": True}, "旧版（昨天的写法）": {"旧反抽": True, "跟进日全平": True}}
if __name__ == "__main__":
    out = {}
    for nm in ("标普500指数", "道琼斯工业指数", "纳斯达克综合指数"):
        D = L.读(nm); out[nm] = {}
        for v, kw in VAR.items():
            R, EV, T = V2.跑(D, **kw); o = {"全部": V2.腿统计(T), "1993以前": V2.腿统计(T[T["开"] < "1993"]) if len(T) else {}, "1993以后": V2.腿统计(T[T["开"] >= "1993"]) if len(T) else {}}
            if v.startswith("新版"):
                T.to_csv(os.path.join(HERE, "out", f"第二版_每一腿_{nm}.csv"), index=False); json.dump(EV, open(os.path.join(HERE, "out", f"第二版_事件_{nm}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
                o["多头_50和20"] = V2.多头(R); o["多头_30和0"] = V2.多头(V2.跑(D, 多A=0.3, 多B=0.0)[0]); o["跌势天数占比pct"] = round(float((R["档"] == "跌势").mean() * 100), 1); o["今天"] = R["档"].iloc[-1]
            out[nm][v] = o
            print("==", nm, v, {k: (x["腿数"], x["每腿平均pct"], x["赚的占比pct"], x["利润因子"], x["t"]) for k, x in o["全部"].items() if isinstance(k, int)}, "合计", o["全部"].get("合计占账户pct"), "回落", o["全部"].get("累计占账户_最深回落pct"))
            if v.startswith("新版"): print("   93前", {k: (x["腿数"], x["每腿平均pct"]) for k, x in o["1993以前"].items() if isinstance(k, int)}, "93后", {k: (x["腿数"], x["每腿平均pct"]) for k, x in o["1993以后"].items() if isinstance(k, int)}); print("   多头", o["多头_50和20"], o["多头_30和0"]["按规则减仓"], o["今天"])
    json.dump(out, open(os.path.join(HERE, "out", "第二版_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
    T = pd.read_csv(os.path.join(HERE, "out", "第二版_每一腿_标普500指数.csv")); print(T[T["第几次"] >= 2].to_string())
