# -*- coding: utf-8 -*-
"""《570》第二批 · 做空组合 · 汇总：逐步加条件的笔数和成绩、随机对照 1,000 次、扣掉大盘、分段、相邻三档。
用法：python 汇总组合_1128.py 指数日线 | 币日线 | 币4小时 | 个股日线"""
import os, sys, json, importlib.util
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
def mod(n, f):
    sp = importlib.util.spec_from_file_location(n, f); m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m
C = mod("核心", os.path.join(HERE, "组合核心_1128.py"))
档名 = ["默认", "容差0.5", "容差1.5", "κ0.6", "κ1.0", "LB120", "LB500", "止损反抽高", "分形3", "分形8"]
步名 = ["① 大势向下", "② +顶部形态", "③ +背离", "④ +跌破颈线", "⑤ +无量弱反抽", "⑥ +下面1.5R无支撑"]


def 步(d, κ=0.8, 支撑=1.5, 量法="甲"):
    s2 = d.大势_确认.fillna(False).astype(bool); s3 = s2 & d.背离.astype(bool)
    s4 = s3 & d.跌破.fillna(False).astype(bool) & d.get("大势_跌破", pd.Series(False, index=d.index)).fillna(False).astype(bool) & d.get("破_R", pd.Series(np.nan, index=d.index)).notna()
    s5 = s4 & d.get("反抽失败", pd.Series(False, index=d.index)).fillna(False).astype(bool) & (d.get("反抽量比" if 量法 == "甲" else "反抽量比_跌段", pd.Series(np.nan, index=d.index)) < κ) \
        & d.get("大势_反抽", pd.Series(False, index=d.index)).fillna(False).astype(bool) & d.get("抽_R", pd.Series(np.nan, index=d.index)).notna()
    s6 = s5 & (d.get("抽_支撑R", pd.Series(np.nan, index=d.index)) >= 支撑)
    return {2: (s2 & d.左_R.notna(), "左"), 3: (s3 & d.左_R.notna(), "左"), 4: (s4, "破"), 5: (s5, "抽"), 6: (s6, "抽")}


def 单子(d, m, pre, mk):
    x = d[m]; e = x[f"{pre}_进"]; ex = x[f"{pre}_出价"]; pct = (e - ex) / e * 100 - 0.1
    t0 = pd.to_datetime(x[f"{pre}_t"]); t1 = pd.to_datetime(x[f"{pre}_出"])
    m0 = mk.reindex(t0, method="ffill").to_numpy(); m1 = mk.reindex(t1, method="ffill").to_numpy()
    mkt = (m1 / m0 - 1) * 100
    neck = (x.颈线 - e) / x[f"{pre}_atr"] if pre != "左" else pd.Series(np.nan, index=x.index)
    return pd.DataFrame({"sym": x.sym, "t": t0, "出": t1, "R": x[f"{pre}_R"].to_numpy(), "pct": pct.to_numpy(), "大盘pct": mkt, "扣大盘pct": pct.to_numpy() + mkt,
                         "风险ATR": ((x[f"{pre}_止损"] - e) / x[f"{pre}_atr"]).to_numpy(), "颈ATR": neck.to_numpy(), "怎么走": x[f"{pre}_怎么走"].to_numpy()})


def 一档(tag, nm, 池, mk, 随机=True, κ=0.8, 支撑=1.5, 分段=None, 量法="甲"):
    d = pd.read_csv(os.path.join(OUT, f"{tag}_{nm}_形态.csv"), parse_dates=["顶2"]); res = {"形态总数（不管大势）": int(len(d)), "①大势向下可进的根数": int(sum(len(v[5]) for v in 池.values()))}
    for k, (m, pre) in 步(d, κ, 支撑, 量法).items():
        T = 单子(d, m, pre, mk); s = C.统计(T.R, T.pct); s["扣掉大盘后每笔%"] = round(float(T.扣大盘pct.mean()), 2) if len(T) else None
        s["同期大盘每笔%"] = round(float(T.大盘pct.mean()), 2) if len(T) else None
        if len(T):
            s["时间段"] = f"{T.t.min().date()} ~ {T.出.max().date()}"
            s["怎么走"] = T.怎么走.value_counts().to_dict()
        if 随机 and len(T) >= 1:
            rnd = C.随机对照(池, list(zip(T.风险ATR, T.颈ATR)), 1000, 种子=k)
            s["随机对照"] = {"随机每笔R中位": round(float(np.median(rnd)), 3), "5%~95%": [round(float(np.percentile(rnd, 5)), 3), round(float(np.percentile(rnd, 95)), 3)], "我们排在第几分位": C.分位(s["每笔R"], rnd), "过95分位": bool(s["每笔R"] > np.percentile(rnd, 95))}
        if 分段:
            s["分段"] = {}
            for g, f in 分段.items():
                y = T[f(T)]; s["分段"][g] = C.统计(y.R, y.pct)
        res[步名[k - 1]] = s
        if nm == "默认" and 量法 == "甲" and κ == 0.8 and 支撑 == 1.5: T.to_csv(os.path.join(OUT, f"{tag}_默认_第{k}步_逐笔.csv"), index=False)
    # ① 本身：随机（用第 ⑥ 步…没有就用第 ④ 步的风险分布）——报随机进场每笔 R 的分布当底
    return res


if __name__ == "__main__":
    tag = sys.argv[1]; 池 = pd.read_pickle(os.path.join(OUT, f"{tag}_池.pkl"))
    mk = pd.read_pickle(os.path.join(OUT, {"指数日线": "SPY收盘.pkl", "个股日线": "SPY收盘.pkl", "币日线": "BTC日收盘.pkl", "币4小时": "BTC4小时收盘.pkl"}[tag]))
    if tag.startswith("币"):
        九十 = lambda T: (T.sym == "BTC") & (T.t >= "2026-09-01") & (T.t < "2026-11-01")
        分段 = {"2017-2021": lambda T: T.t < "2022-01-01", "2022-2025": lambda T: (T.t >= "2022-01-01") & (T.t < "2026-01-01"), "2026": lambda T: T.t >= "2026-01-01",
                "去掉BTC 2026年9~10月": lambda T: ~九十(T), "BTC": lambda T: T.sym == "BTC", "ETH": lambda T: T.sym == "ETH"}
    elif tag == "指数日线":
        分段 = {"2004年以前": lambda T: T.t < "2005-01-01", "2005-2014": lambda T: (T.t >= "2005-01-01") & (T.t < "2015-01-01"), "2015-2021": lambda T: T.t >= "2015-01-01",
                "SPY": lambda T: T.sym == "SPY", "QQQ": lambda T: T.sym == "QQQ", "IWM": lambda T: T.sym == "IWM", "SOXX": lambda T: T.sym == "SOXX"}
    else:
        分段 = {"2005-2014": lambda T: T.t < "2015-01-01", "2015-2021": lambda T: T.t >= "2015-01-01", "2008年": lambda T: (T.t >= "2008-01-01") & (T.t < "2009-01-01"),
                "去掉2008年": lambda T: (T.t < "2008-01-01") | (T.t >= "2009-01-01")}
    out = {"默认": 一档(tag, "默认", 池, mk, 分段=分段)}
    for nm in 档名[1:]:
        if nm.startswith("κ"): continue
        out[nm] = 一档(tag, nm, 池, mk, 随机=False)
    for κ in (0.6, 1.0): out[f"κ{κ}"] = 一档(tag, "默认", 池, mk, 随机=False, κ=κ)
    out["量法乙"] = 一档(tag, "默认", 池, mk, 分段=分段, 量法="乙")
    for κ in (0.6, 1.0): out[f"量法乙κ{κ}"] = 一档(tag, "默认", 池, mk, 随机=False, κ=κ, 量法="乙")
    for sp in (1.2, 2.0): out[f"支撑{sp}R"] = 一档(tag, "默认", 池, mk, 随机=False, 支撑=sp)
    json.dump(out, open(os.path.join(OUT, f"{tag}_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    for nm, r in out.items():
        print(nm, " | ".join(f"{k[:2]}:{v.get('笔')}笔 {v.get('每笔R')}R" for k, v in r.items() if isinstance(v, dict)))
    print(json.dumps(out["默认"], ensure_ascii=False, default=str)[:3000])
