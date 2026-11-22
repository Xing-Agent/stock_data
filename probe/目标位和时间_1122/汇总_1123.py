# -*- coding: utf-8 -*-
import os, sys, json, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import importlib.util
sp = importlib.util.spec_from_file_location("m", os.path.join(HERE, "目标位和时间_1123.py")); M = importlib.util.module_from_spec(sp); sp.loader.exec_module(M)
TG = ["形态高度0.7倍", "前高前低", "形态高度1倍", "斐波1.272", "1倍等距", "斐波1.618"]; out = {}
def 到达(x):
    r = {}
    for t in TG:
        g = x["果_" + t].dropna()
        if len(g) < 5: continue
        y = x.loc[g.index]
        r[t] = {"有这个目标的笔数": int(len(g)), "先到目标pct": round((g == "目标").mean() * 100, 1), "先到止损pct": round((g == "止损").mean() * 100, 1), "到时间pct": round((g == "到时间").mean() * 100, 1),
                "目标离进场几R_中位": round(float(y["距_" + t].median()), 2), "到目标用几天_中位": float(y["天_" + t].median()),
                "打平要的到达率pct": round(float(100 / (1 + y["距_" + t].median())), 1)}
    return r
for N in (60, 40, 120):
    ev = pd.read_parquet(os.path.join(HERE, "out", f"事件_N{N}.parquet")); bad = ev[(ev.A_R < -3) | (ev.B_R < -3)]; ev = ev.drop(bad.index); o = {"笔数": int(len(ev)), "剔掉的坏数据单": [f"{a} {str(b)[:10]} {c:.1f}R" for a, b, c in zip(bad["票"], bad["日期"], bad.A_R)]}
    o["到达_全部"] = 到达(ev)
    if N == 60:
        for k in ("段", "方向", "行情", "型", "类"):
            o["到达_按" + k] = {str(a): 到达(g) for a, g in ev.groupby(k)}
        o["到达_段×方向"] = {f"{a}｜{b}": 到达(g) for (a, b), g in ev.groupby(["段", "方向"])}
        z = {}
        for t in TG:
            has = ev["果_" + t].notna(); inz = ev["成区的目标"].str.split("|").apply(lambda L: t in L)
            for nm, g in (("成区", ev[has & inz]), ("单个", ev[has & ~inz])):
                if len(g) >= 5: z[f"{t}｜{nm}"] = {"笔数": int(len(g)), "先到目标pct": round((g["果_" + t] == "目标").mean() * 100, 1), "离进场几R_中位": round(float(g["距_" + t].median()), 2)}
        o["目标区"] = z
    o["AB_全部"] = {"A_照常拿": M.S(ev, "A_R"), "B_5天规则": M.S(ev, "B_R")}
    for k in ("段", "方向", "行情", "型", "类"):
        o["AB_按" + k] = {str(a): {"A": M.S(g, "A_R"), "B": M.S(g, "B_R")} for a, g in ev.groupby(k)}
    o["AB_段×方向"] = {f"{a}｜{b}": {"A": M.S(g, "A_R"), "B": M.S(g, "B_R")} for (a, b), g in ev.groupby(["段", "方向"])}
    cut = ev[ev["B_怎么出"].isin(["收回去撤", "没走开撤"])]
    o["B撤掉的单"] = {w: {"笔数": int(len(g)), "B撤时毛R": round(float(g.B_R.mean()), 3), "如果拿着_毛R": round(float(g.A_R.mean()), 3), "如果拿着_后来到目标pct": round(float((g.A_怎么出 == "目标").mean() * 100), 1), "如果拿着_后来止损pct": round(float((g.A_怎么出 == "止损").mean() * 100), 1)} for w, g in cut.groupby("B_怎么出")}
    keep = ev[~ev.index.isin(cut.index)]; o["B没撤的单_毛R"] = round(float(keep.A_R.mean()), 3); o["B撤掉占比pct"] = round(len(cut) / len(ev) * 100, 1)
    ev["箱高档"] = pd.qcut(ev["箱高除ATR"], 3, labels=["窄", "中", "宽"])
    o["AB_按箱高"] = {str(a): {"A": M.S(g, "A_R"), "B": M.S(g, "B_R"), "箱高除ATR_中位": round(float(g["箱高除ATR"].median()), 1)} for a, g in ev.groupby("箱高档")}
    # 最大回撤（按日期排，逐笔净 R 累加）
    for c in ("A_R", "B_R"):
        s = (ev.sort_values("日期")[c] - ev.sort_values("日期")["成本R"]).cumsum(); o["累计净R最深回落_" + c[0]] = round(float((s - s.cummax()).min()), 1); o["累计净R_" + c[0]] = round(float(s.iloc[-1]), 1)
    out[f"N{N}"] = o
json.dump(out, open(os.path.join(HERE, "out", "汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
for N in ("N60", "N40", "N120"):
    o = out[N]; print(N, o["笔数"], o["AB_全部"], "撤", o["B撤掉占比pct"], o["B撤掉的单"], "没撤", o["B没撤的单_毛R"], o["累计净R_A"], o["累计净R最深回落_A"], o["累计净R_B"], o["累计净R最深回落_B"])
    for t, x in o["到达_全部"].items(): print("  ", t, x)
o = out["N60"]
for k in ("AB_段×方向", "AB_按行情", "AB_按型", "AB_按类", "AB_按箱高"): print(k, json.dumps(o[k], ensure_ascii=False))
print(json.dumps(o["目标区"], ensure_ascii=False)); print(json.dumps({k: {t: (x["先到目标pct"], x["打平要的到达率pct"]) for t, x in v.items()} for k, v in o["到达_段×方向"].items()}, ensure_ascii=False))
print(json.dumps({k: {t: (x["先到目标pct"], x["打平要的到达率pct"]) for t, x in v.items()} for k, v in o["到达_按行情"].items()}, ensure_ascii=False))
