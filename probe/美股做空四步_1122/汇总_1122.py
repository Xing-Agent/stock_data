# -*- coding: utf-8 -*-
"""《396》第一件 · 把 out/*.pkl 汇成报告用的表（只读结果，不重跑）。
净R = 毛R − 0.15% × 费F − 借券年化 × 借F（费F、借F 在 四步_1122.py 里逐笔记好了）。
"""
import os, io, json, glob
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out"); ROOT = os.path.dirname(os.path.dirname(HERE))
十年 = {"2005–2014": ("2005-01-01", "2014-12-31"), "2015–2025": ("2015-01-01", "2025-12-31")}
类名 = {"指数": "大指数(SPY QQQ DIA IWM)", "行业": "行业ETF(13只)", "个股_研究库": "个股·研究库", "个股_合": "个股·研究库+退市股"}
只数 = {"指数": 4, "行业": 13}


def 载(cls, vn, cn):
    if cls == "个股_合":
        a, b = 载("个股_研究库", vn, cn), 载("个股_退市股", vn, cn)
        return {"ev": pd.concat([a["ev"], b["ev"]], ignore_index=True), "ps": pd.concat([a["ps"], b["ps"]], ignore_index=True)}
    return pd.read_pickle(os.path.join(OUT, f"{cls}__{vn}__{cn}.pkl"))


def 净(t, borrow=0.01):
    return t["毛R"] - 0.0015 * t["费F"] - borrow * t["借F"]


def 汇(t, borrow=0.01, 随机=True):
    if len(t) == 0: return {"笔数": 0}
    r = 净(t, borrow); w = r[r > 0].sum(); ls = -r[r < 0].sum()
    c5 = t["第5天收盘R"]; st5 = t["头5天被止损"] > 0
    o = {"笔数": int(len(t)), "到1倍pct": round(100 * t["到1倍"].mean(), 1), "到1.618倍pct": round(100 * t["到1618"].mean(), 1),
         "每笔毛R": round(float(t["毛R"].mean()), 3), "每笔净R": round(float(r.mean()), 3), "净R中位": round(float(r.median()), 3),
         "胜率pct": round(100 * float((r > 0).mean()), 1), "利润因子": round(float(w / ls), 2) if ls > 0 else None,
         "止损距中位pct": round(float((t["R"] / t["E"]).median() * 100), 2), "平均拿几天": round(float(t["拿几天"].mean()), 1),
         "头5天被止损pct": round(100 * float(st5.mean()), 1), "头5天直接走pct(第5天收盘赚0.5R以上)": round(100 * float(((c5 > 0.5) & ~st5).mean()), 1),
         "头5天来回磨pct(没被打也没走出0.5R)": round(100 * float(((c5.abs() <= 0.5) & ~st5).mean()), 1)}
    if 随机 and "随机毛R" in t:
        rr = t["随机毛R"] - 0.0015 * t["随机费F"] - borrow * t["随机借F"]
        o["随机对照_每笔净R"] = round(float(rr.mean()), 3); o["随机对照_到1倍pct"] = round(100 * float(t["随机到1倍"].mean()), 1)
    return o


def 段(t, a, b): return t[(t["日"] >= a) & (t["日"] <= b)]


def 过核心(ps, cls):
    if len(ps) == 0: return {"次数": 0}
    if cls.startswith("个股"): ps = ps[ps["在池"] > 0]
    return {"次数": int(len(ps)), "之后20天涨跌中位pct": round(100 * float(ps["f20"].median()), 1), "之后60天涨跌中位pct": round(100 * float(ps["f60"].median()), 1),
            "120天内收盘回到顶部之上pct": round(100 * float(ps["120天内收回顶部"].mean()), 1)}


def 大盘背景():
    o = {}
    for s in ("SPY", "QQQ"):
        d = pd.read_csv(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/日线", s + "_日线.csv"), parse_dates=["date"]).set_index("date")["adjusted_close"]
        for k, (a, b) in 十年.items():
            x = d[a:b]; yrs = (x.index[-1] - x.index[0]).days / 365.25
            o[f"{s}_{k}_复合年化pct(含分红)"] = round(100 * ((x.iloc[-1] / x.iloc[0]) ** (1 / yrs) - 1), 1)
            o[f"{s}_{k}_最大回撤pct"] = round(100 * float((x / x.cummax() - 1).min()), 1)
    return o


def main():
    R = {"大盘背景": 大盘背景(), "基准": {}, "邻点": {}}
    for vn in ("认法a派发确认", "认法b假突破"):
        for cls in ("指数", "行业", "个股_研究库", "个股_合"):
            D = 载(cls, vn, "基准"); ev, ps = D["ev"], D["ps"]
            g = {}
            for k, (a, b) in 十年.items():
                t = 段(ev, a, b); p = 段(ps, a, b); yrs = 10 if k.startswith("2005") else 11
                x = {}
                for 层 in (1, 2):
                    tt = t[t["层"] == 层]
                    x[f"第{层}层"] = {"全部": 汇(tt), "按叠加": {nm: 汇(tt[m]) for nm, m in (("只有回撤位", tt["叠几样"] == 0), ("叠1样", tt["叠几样"] == 1), ("叠2样以上", tt["叠几样"] >= 2))}}
                    if cls.startswith("个股"): x[f"第{层}层"]["借券5pct"] = 汇(tt, 0.05, False)
                    x[f"第{层}层"]["过了核心位置"] = 过核心(p[p["层"] == 层], cls)
                t1 = t[t["层"] == 1]
                x["每年每只几次(第1层)"] = round(len(t1) / yrs / (只数.get(cls) or max(1, t1["票"].nunique())), 2) if cls in 只数 else None
                x["每年几笔(第1层)"] = round(len(t1) / yrs, 1)
                x["有过信号的票数"] = int(t1["票"].nunique())
                if cls.startswith("个股") and "退市股" in t1:
                    x["其中退市股的笔"] = 汇(t1[t1["退市股"]], 0.01, False)
                g[k] = x
            y = ev[ev["层"] == 1].copy(); y["年"] = pd.to_datetime(y["日"]).dt.year
            g["分年(第1层)"] = {int(yy): {"笔数": int(len(q)), "到1倍pct": round(100 * q["到1倍"].mean(), 0), "每笔净R": round(float(净(q).mean()), 2)} for yy, q in y.groupby("年")}
            if cls in ("指数", "行业"):
                g["逐笔(第1层+第2层)"] = [{"票": r_["票"], "日": str(r_["日"])[:10], "层": int(r_["层"]), "叠几样": int(r_["叠几样"]), "到1倍": int(r_["到1倍"]), "净R": round(float(净(r_.to_frame().T).iloc[0]), 2), "怎么出": int(r_["怎么出"])} for _, r_ in ev.sort_values("日").iterrows()]
            R["基准"][f"{vn}｜{cls}"] = g
        # 邻点
        for cls in ("指数", "行业", "个股_合"):
            rows = {}
            for f in sorted(glob.glob(os.path.join(OUT, f"{'个股_研究库' if cls == '个股_合' else cls}__{vn}__*.pkl"))):
                cn = os.path.basename(f).split("__")[2][:-4]; ev = 载(cls, vn, cn)["ev"]; ev = ev[ev["层"] == 1]
                rows[cn] = {k: {kk: 汇(段(ev, a, b), 随机=False).get(kk) for kk in ("笔数", "到1倍pct", "每笔净R", "利润因子")} for k, (a, b) in 十年.items()}
            R["邻点"][f"{vn}｜{cls}"] = rows
    json.dump(R, io.open(os.path.join(OUT, "汇总_1122.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("ok")


if __name__ == "__main__":
    main()
