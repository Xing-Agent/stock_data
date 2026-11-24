# -*- coding: utf-8 -*-
"""把「第几次确认开多少仓」折成每一轮跌势里空单实际赚亏（《423 拍板》第 2 条；默认版 = Lin 11-24 放宽后的）
首次跌破（或突发急跌）开 35%；反抽没过第 2 次确认加到 75%；第 3 次及以后加满 100%。「复跌」按它带的次数直接开到对应仓位。
全平：出跟进日（解除跌势）/ 周线证伪 / 2 周内收回。跟进日失败、退回跌势时，按上次的仓位重新开。都按当天收盘价。不算成本、不算融券利息、不算分红（指数点位）。
一轮的赚亏 = 各笔仓位 × (开仓价 − 平仓价) ÷ 开仓价 之和，单位是「占账户的百分比」（账户全拿来做这一件事时）。"""
import os, sys, json, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
sp = importlib.util.spec_from_file_location("L", os.path.join(HERE, "长历史_1124.py")); L = importlib.util.module_from_spec(sp); sp.loader.exec_module(L); M = L.M
档位 = {1: 0.35, 2: 0.75}
def 折(D, **kw):
    R, EV = M.跑(D, **kw); c = D.close; rows = []; cur = None; last = None
    for e in EV:
        k = e["事"]; px = e["收盘"]
        if k.startswith(("转空", "复跌")):
            次 = 1
            if k.startswith("复跌"): 次 = 2
            cur = {"开": e["日期"], "怎么开的": k, "腿": [(档位.get(次, 1.0), px)], "仓": 档位.get(次, 1.0), "次": 次}
        elif cur is None and k.startswith("跟进日失败") and last is not None:      # 跟进日失败退回跌势：按上次平仓时的仓位重新开
            cur = {"开": e["日期"], "怎么开的": "跟进日失败·重开", "腿": [(last["仓"], px)], "仓": last["仓"], "次": last["次"]}
        elif cur is not None and k.startswith("反抽没过"):
            cur["次"] += 1; tgt = 档位.get(cur["次"], 1.0)
            if tgt > cur["仓"]: cur["腿"].append((tgt - cur["仓"], px)); cur["仓"] = tgt
        elif cur is not None and (k.startswith(("跟进日·", "证伪", "2 周内收回"))):
            pnl = sum(w * (p - px) / p for w, p in cur["腿"]); seg = c.loc[cur["开"]:e["日期"]]
            只首 = cur["腿"][0][0] * (cur["腿"][0][1] - px) / cur["腿"][0][1]; 满仓 = (cur["腿"][0][1] - px) / cur["腿"][0][1]
            rows.append({"开": cur["开"], "平": e["日期"], "怎么开的": cur["怎么开的"], "怎么平的": k, "确认到第几次": cur["次"], "最后仓位": cur["仓"], "天数": int((pd.Timestamp(e["日期"]) - pd.Timestamp(cur["开"])).days),
                         "赚亏pct": round(pnl * 100, 2), "只开首仓pct": round(只首 * 100, 2), "一次满仓pct": round(满仓 * 100, 2), "期间指数最多再跌pct": round((seg.min() / cur["腿"][0][1] - 1) * 100, 1), "期间指数最多反弹pct": round((seg.max() / cur["腿"][0][1] - 1) * 100, 1)}); last = {"仓": cur["仓"], "次": cur["次"]} if k.startswith("跟进日·") else None; cur = None
    return pd.DataFrame(rows)
def 概(T):
    if not len(T): return {"轮数": 0}
    r = T["赚亏pct"]
    return {"轮数": int(len(T)), "赚的轮数": int((r > 0).sum()), "合计pct": round(float(r.sum()), 1), "每轮平均pct": round(float(r.mean()), 2), "最赚一轮pct": float(r.max()), "最亏一轮pct": float(r.min()), "去掉最赚2轮后合计pct": round(float(r.sort_values().iloc[:-2].sum()), 1) if len(r) > 2 else None,
            "只开首仓_合计pct": round(float(T["只开首仓pct"].sum()), 1), "一次满仓_合计pct": round(float(T["一次满仓pct"].sum()), 1), "加过仓的轮数": int((T["确认到第几次"] >= 2).sum())}
if __name__ == "__main__":
    out = {}
    for nm in ("标普500指数", "道琼斯工业指数", "纳斯达克综合指数"):
        D = L.读(nm); T = 折(D); T.to_csv(os.path.join(HERE, "out", f"仓位折赚亏_{nm}.csv"), index=False)
        out[nm] = {"全部": 概(T), "1993以前": 概(T[T["开"] < "1993"]), "1993以后": 概(T[T["开"] >= "1993"]), "原样对照_全部": 概(折(D, 要ST或UT=True, BC严=True))}
        print("==", nm, json.dumps(out[nm], ensure_ascii=False))
        T["年代"] = T["开"].str[:3] + "0"; print(T.groupby("年代")["赚亏pct"].agg(["count", "sum"]).round(1).T.to_string())
        print(T.groupby("怎么开的")["赚亏pct"].agg(["count", "sum", "mean"]).round(2).to_string()); print(T.groupby("确认到第几次")["赚亏pct"].agg(["count", "sum", "mean"]).round(2).to_string())
        print(T.nlargest(5, "赚亏pct")[["开", "平", "怎么开的", "最后仓位", "赚亏pct"]].to_string()); print(T.nsmallest(5, "赚亏pct")[["开", "平", "怎么开的", "最后仓位", "赚亏pct"]].to_string())
    json.dump(out, open(os.path.join(HERE, "out", "仓位折赚亏_汇总.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
