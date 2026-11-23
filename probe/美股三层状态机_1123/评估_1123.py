# -*- coding: utf-8 -*-
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("m", os.path.join(HERE, "三层状态机_1123.py")); M = importlib.util.module_from_spec(sp); sp.loader.exec_module(M)
顶 = {"SPY": {"2000": ("2000-03-24", "2002-10-09"), "2007": ("2007-10-09", "2009-03-09"), "2020": ("2020-02-19", "2020-03-23"), "2022": ("2022-01-03", "2022-10-12")},
      "QQQ": {"2000": ("2000-03-27", "2002-10-09"), "2007": ("2007-10-31", "2009-03-09"), "2020": ("2020-02-19", "2020-03-23"), "2022": ("2021-11-19", "2022-12-28")}}
def 评(名, D, **kw):
    R, EV = M.跑(D, **kw); c = D.close; o = {}
    转空 = [e for e in EV if e["事"].startswith(("转空", "复跌"))]
    for k, (a, b) in 顶[名].items():
        x = [e for e in 转空 if a <= e["日期"] <= b]
        if x: e = x[0]; pk = c.loc[a]; bt = c.loc[b]; o["顶" + k] = f"{e['日期']}（离顶 {e['收盘'] / pk - 1:.0%}，离底还有 {bt / e['收盘'] - 1:.0%}）"
        else: o["顶" + k] = "没认出"
        y = [e for e in EV if e["事"].startswith(("跟进日·", "大底确认")) and e["日期"] >= b]
        f = [e for e in y if e["事"].startswith("跟进日·")][:1]; g = [e for e in y if e["事"].startswith("大底确认")][:1]
        o["底" + k] = (f"试仓 {f[0]['日期']}（+{f[0]['收盘'] / c.loc[b] - 1:.0%}）" if f and f[0]["日期"] < str(pd.Timestamp(b) + pd.Timedelta(days=400))[:10] else "没有") + (f"；加满 {g[0]['日期']}（+{g[0]['收盘'] / c.loc[b] - 1:.0%}）" if g and g[0]["日期"] < str(pd.Timestamp(b) + pd.Timedelta(days=400))[:10] else "")
    真 = set()
    for k, (a, b) in 顶[名].items(): 真 |= {e["日期"] for e in 转空 if a <= e["日期"] <= b}
    虚 = []
    for e in 转空:
        if e["日期"] in 真: continue
        t = pd.Timestamp(e["日期"]); seg = R.loc[t:]; end = seg[seg["档"] == "涨势"].index[:1]; end = end[0] if len(end) else R.index[-1]
        虚.append((e["日期"], round((c.loc[t:end].min() / e["收盘"] - 1) * 100, 1)))
    o["四个大顶以外的转空"] = len(虚); o["其中之后再跌不到10%"] = sum(1 for _, x in 虚 if x > -10); o["虚惊清单"] = [f"{d}({x}%)" for d, x in 虚]
    ft = [e for e in EV if e["事"].startswith("跟进日·")]; fl = [e for e in EV if e["事"].startswith("跟进日失败")]
    o["跟进日次数"] = len(ft); o["其中失败"] = len(fl); o["小顶预警次数"] = sum(1 for e in EV if e["事"] == "小顶预警"); o["今天"] = R["档"].iloc[-1]
    return o, R, EV
if __name__ == "__main__":
    V = {"主版（照拍板）": {}, "不要求有ST或UTAD": {"要ST或UT": False}, "BC放宽（只要52周新高）": {"BC严": False}, "两样都放宽": {"要ST或UT": False, "BC严": False},
         "横盘12周": {"固定横盘周": 12}, "横盘16周": {"固定横盘周": 16}, "横盘20周": {"固定横盘周": 20}, "跌破2%": {"跌破": 0.02}, "跌破4%": {"跌破": 0.04},
         "两样都放宽+横盘16周": {"要ST或UT": False, "BC严": False, "固定横盘周": 16}}
    out = {}
    for 名 in ("SPY", "QQQ"):
        D = M.M4.美股日线(名); out[名] = {}
        for v, kw in V.items():
            o, R, EV = 评(名, D, **kw); out[名][v] = o
            if v in ("主版（照拍板）", "两样都放宽"):
                R.to_csv(os.path.join(HERE, "out", f"{名}_每天的档_{v[:2]}.csv")); json.dump(EV, open(os.path.join(HERE, "out", f"{名}_事件_{v[:2]}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
                M.画(R, EV, f"{名}_{v[:2]}")
        T = pd.DataFrame(out[名]).T; print("==", 名); print(T.drop(columns=["虚惊清单"]).to_string()); print(out[名]["主版（照拍板）"]["虚惊清单"]); print(out[名]["两样都放宽"]["虚惊清单"])
    json.dump(out, open(os.path.join(HERE, "out", "评估.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=float)
