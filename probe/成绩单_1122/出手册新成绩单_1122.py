# -*- coding: utf-8 -*-
"""手册技术面全部版本 × 两段时间 的新成绩单汇总（读 out_手册/ 里存下的每天净值，不重跑回测）。「拿得住」用主路《397》的新口径函数。"""
import os, json, glob, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); O = os.path.join(HERE, "out_手册")
def mod(n, p):
    sp = importlib.util.spec_from_file_location(n, p); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
nk = mod("nk", os.path.join(HERE, "新口径拿得住_1122.py")); cj = mod("cj", os.path.join(HERE, "成绩单_1122.py"))
rows = []
for f in sorted(glob.glob(os.path.join(O, "成绩单_*.json"))):
    d = json.load(open(f, encoding="utf-8"))
    if "跑失败" in d: rows.append({"段": d["段"], "名": d["名"], "跑失败": d["跑失败"]}); continue
    段, 名 = d["段"], d["名"]; x = pd.read_parquet(os.path.join(O, f"日线_{段}_{名}.parquet")); eq = x["eq"].dropna(); idx = eq.index
    spy = nk.指数净值("SPY", idx); same = nk.等仓位标普(idx, x["expo"])
    a = nk.生存(eq / eq.iloc[0], spy)[0]; b = nk.生存(same, spy)[0]; c = nk.生存(spy, spy)[0]
    s = d["结果"]["策略"]; t = d["结果"]["同样仓位的标普"]; r = d["结果"].get("随机进场_5次中位", {})
    rows.append({"段": 段, "名": 名, "每年赚": s["每年赚pct"], "最深亏损": s["最深亏损pct"], "赚除以亏": s["每年赚除以最深亏损"], "溃疡绩效": s["溃疡绩效"], "最差一年": s["最差一年pct"],
                 "最长没创新高": s["最长多少个交易日没创新高"], "平均仓位": s.get("平均仓位pct"), "笔数": s.get("笔数"), "利润因子": s.get("利润因子"),
                 "同仓标普_每年赚": t["每年赚pct"], "同仓标普_最深亏损": t["最深亏损pct"], "同仓标普_赚除以亏": t["每年赚除以最深亏损"], "同仓标普_溃疡绩效": t["溃疡绩效"],
                 "拿得住_策略": round(a, 1), "拿得住_同仓标普": round(b, 1), "拿得住_满仓标普": round(c, 1),
                 "随机进场_每年赚": r.get("每年赚pct"), "随机进场_赚除以亏": r.get("每年赚除以最深亏损")})
R = pd.DataFrame(rows); R.to_csv(os.path.join(O, "手册新成绩单_汇总.csv"), index=False)
print(R.groupby("段").size().to_dict())
for 段 in ("一", "二"):
    g = R[R["段"] == 段]; t = g[g["名"] != "buy_and_hold"]
    print(段, "条数", len(t), "| 赚除以亏 > 同仓标普:", int((t["赚除以亏"] > t["同仓标普_赚除以亏"]).sum()), "| 溃疡绩效 > 同仓标普:", int((t["溃疡绩效"] > t["同仓标普_溃疡绩效"]).sum()),
          "| 每年赚 > 随机进场:", int((t["每年赚"] > t["随机进场_每年赚"]).sum()), "| 拿得住 >= 同仓标普:", int((t["拿得住_策略"] >= t["拿得住_同仓标普"]).sum()), "| 拿得住 >= 满仓标普:", int((t["拿得住_策略"] >= t["拿得住_满仓标普"]).sum()),
          "| 满仓标普拿得住", g["拿得住_满仓标普"].iloc[0], "| 拿着不动", g[g["名"] == "buy_and_hold"][["每年赚", "最深亏损", "赚除以亏", "拿得住_策略"]].values.tolist())
