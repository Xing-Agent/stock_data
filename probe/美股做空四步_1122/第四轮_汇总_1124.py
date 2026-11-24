# -*- coding: utf-8 -*-
"""第四轮汇总：读 out/第四轮__*.pkl，出报告用的表（out/第四轮_汇总.json）。"""
import os, glob, json, io
import numpy as np, pandas as pd
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "out")
def 载(cls, cn):
    if cls == "个股":
        return pd.concat([pd.read_pickle(os.path.join(OUT, f"第四轮__个股_{x}__{cn}.pkl")) for x in ("研究库", "退市股")], ignore_index=True)
    return pd.read_pickle(os.path.join(OUT, f"第四轮__{cls}__{cn}.pkl"))
def 汇(t, bor=0.01):
    if len(t) == 0: return {"笔数": 0}
    r = t["毛R"] - 0.0015 * t["费F"] - bor * t["借F"]; w = r[r > 0].sum(); l = -r[r < 0].sum()
    o = {"笔数": int(len(t)), "到1倍pct": round(100 * t["到1倍"].mean(), 1), "到1.618倍pct": round(100 * t["到1618"].mean(), 1), "每笔净R": round(float(r.mean()), 3),
         "胜率pct": round(100 * float((r > 0).mean()), 1), "利润因子": round(float(w / l), 2) if l > 0 else None, "止损距中位pct": round(float((t["R"] / t["E"]).median() * 100), 2)}
    if len(t) > 5: o["去掉最赚3笔"] = round(float(r.sort_values().iloc[:-3].mean()), 3)
    if "随机毛R" in t and t["随机毛R"].notna().all():
        o["随机对照净R"] = round(float((t["随机毛R"] - 0.0015 * t["随机费F"] - bor * t["随机借F"]).mean()), 3)
    return o
R = {"基准": {}, "邻点": {}, "2008年": {}}
for cls in ("指数", "行业", "个股"):
    ev = 载(cls, "基准"); ev["十年"] = np.where(pd.to_datetime(ev["日"]) < "2015-01-01", "2005–2014", "2015–2025")
    g = {}
    for dk in ("2005–2014", "2015–2025"):
        t = ev[ev["十年"] == dk]
        g[dk] = {"全部": 汇(t), "第1次(空三浪)": 汇(t[t["第几次"] == 1]), "第2次及以后": 汇(t[t["第几次"] >= 2]),
                 "按叠加": {nm: 汇(t[m]) for nm, m in (("只有回撤位", t["叠几样"] == 0), ("叠1样", t["叠几样"] == 1), ("叠2样以上", t["叠几样"] >= 2))}}
        if cls == "个股": g[dk]["借券5pct"] = 汇(t, 0.05)
    y = ev.assign(年=pd.to_datetime(ev["日"]).dt.year)
    g["分年"] = {int(k): {"笔数": int(len(q)), "每笔净R": round(float((q["毛R"] - 0.0015 * q["费F"] - 0.01 * q["借F"]).mean()), 2)} for k, q in y.groupby("年")}
    R["基准"][cls] = g
    nb = {}
    for f in sorted(glob.glob(os.path.join(OUT, f"第四轮__{'个股_研究库' if cls == '个股' else cls}__*.pkl"))):
        cn = os.path.basename(f).split("__")[2][:-4]; e = 载(cls, cn); e["十年"] = np.where(pd.to_datetime(e["日"]) < "2015-01-01", "2005–2014", "2015–2025")
        nb[cn] = {dk: {k: 汇(e[e["十年"] == dk]).get(k) for k in ("笔数", "到1倍pct", "每笔净R", "利润因子")} for dk in ("2005–2014", "2015–2025")}
        y8 = e[(pd.to_datetime(e["日"]) >= "2007-10-01") & (pd.to_datetime(e["日"]) <= "2009-03-31")]
        R["2008年"].setdefault(cls, {})[cn] = {k: 汇(y8).get(k) for k in ("笔数", "到1倍pct", "每笔净R", "利润因子")}
    R["邻点"][cls] = nb
json.dump(R, io.open(os.path.join(OUT, "第四轮_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
if __name__ == "__main__":
    for cls in R["基准"]:
        for dk in ("2005–2014", "2015–2025"):
            x = R["基准"][cls][dk]; print(cls, dk, "全部", x["全部"]); print("   第1次", x["第1次(空三浪)"]); print("   第2+", x["第2次及以后"])
            print("   叠", {k: (v.get("笔数"), v.get("每笔净R")) for k, v in x["按叠加"].items()}, x.get("借券5pct", {}).get("每笔净R"))
    for cls in R["邻点"]:
        print(cls); [print("  ", cn, [(v[d]["笔数"], v[d]["每笔净R"], v[d]["利润因子"]) for d in v]) for cn, v in R["邻点"][cls].items()]
    print(json.dumps(R["2008年"], ensure_ascii=False))
    for cls in R["基准"]: print(cls, R["基准"][cls]["分年"])
