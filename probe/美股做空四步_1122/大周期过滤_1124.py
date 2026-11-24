# -*- coding: utf-8 -*-
"""《396》第一件 · 第三轮：只在大周期已经转空的时候才空。不重跑，把第一轮（日线，全部三类）和第二轮（1 小时线，ETF）的逐笔按进场那天的大周期档位筛。
大周期档位直接用主 chat 的现成结果（只读）：
  · 三层状态机·默认版（《427》拍板：两条认顶规则放宽）：probe/美股三层状态机_1123/out/SPY_每天的档_两样.csv —— 档 = 涨势 / 跌势 / 试仓
  · 五档第四版（《420》）：probe/大周期五档_1123/out4/SPY_四版_每天的档.csv —— 档 = 涨势 / 涨势·中继 / 见顶 / 跌势 / 筑底期 / 转涨期
★ 我补的：三层的「跌势」切到「试仓」很快（2005–2025 只占 5% 的日子），所以另加一档「跌势或试仓」= 只要三层不在涨势。
★ 我补的：所有票（个股、行业 ETF）一律看 SPY 的档（主 chat 只出了 SPY、QQQ 两份）；进场那天的档用当天收盘判的档（状态机是逐日往前推的，按主 chat 的说法只用到当天为止的数，我没另外核）。
口径：每笔净R（个股借券 1% 一版、5% 一版），利润因子、胜率、到 1 倍比例，按十年分；随机对照只有第一轮有。
"""
import os, io, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); P = os.path.dirname(HERE); OUT = os.path.join(HERE, "out")
三层 = pd.read_csv(os.path.join(P, "美股三层状态机_1123/out/SPY_每天的档_两样.csv"), parse_dates=["date"]).set_index("date")["档"]
五档 = pd.read_csv(os.path.join(P, "大周期五档_1123/out4/SPY_四版_每天的档.csv"), parse_dates=["date"]).set_index("date")["档"]
筛 = {"不筛（原样）": lambda a, b: pd.Series(True, index=a.index),
      "三层=跌势": lambda a, b: a == "跌势",
      "三层=跌势或试仓": lambda a, b: a.isin(["跌势", "试仓"]),
      "五档=跌势": lambda a, b: b == "跌势",
      "五档=见顶或跌势": lambda a, b: b.isin(["见顶", "跌势"]),
      "两套都是跌势": lambda a, b: (a == "跌势") & (b == "跌势")}


def 汇(r, t=None):
    if len(r) == 0: return {"笔数": 0}
    w = r[r > 0].sum(); l = -r[r < 0].sum()
    o = {"笔数": int(len(r)), "每笔净R": round(float(r.mean()), 3), "胜率pct": round(100 * float((r > 0).mean()), 1), "利润因子": round(float(w / l), 2) if l > 0 else None,
         "去掉最赚3笔": round(float(r.sort_values().iloc[:-3].mean()), 3) if len(r) > 5 else None}
    if t is not None:
        o["到1倍pct"] = round(100 * float(t["到1倍"].mean()), 1)
        if "随机毛R" in t:
            o["随机对照净R"] = round(float((t["随机毛R"] - 0.0015 * t["随机费F"] - 0.01 * t["随机借F"]).mean()), 3)
    return o


def 贴档(t, col):
    d = pd.to_datetime(t[col]).dt.normalize()
    return 三层.reindex(d).to_numpy(), 五档.reindex(d).to_numpy()


def main():
    R = {"档位占的日子pct(2005–2025)": {}}
    for nm, s in (("三层", 三层), ("五档", 五档)):
        x = s["2005":"2025"]; R["档位占的日子pct(2005–2025)"][nm] = {k: round(100 * v, 1) for k, v in x.value_counts(normalize=True).items()}
    # 第一轮
    res1 = {}
    for cls in ("指数", "行业", "个股_研究库", "个股_退市股"):
        for vn in ("认法a派发确认", "认法b假突破"):
            ev = pd.read_pickle(os.path.join(OUT, f"{cls}__{vn}__基准.pkl"))["ev"]; ev = ev[ev["层"] == 1].copy()
            ev["类"] = "个股（含退市）" if cls.startswith("个股") else cls; ev["认法"] = vn; res1.setdefault((ev["类"].iat[0] if len(ev) else cls, vn), []).append(ev)
    T1 = []
    for (c, vn), L in res1.items():
        ev = pd.concat(L, ignore_index=True); a, b = 贴档(ev, "日"); ev["三层"], ev["五档"] = a, b
        ev["十年"] = np.where(pd.to_datetime(ev["日"]) < "2015-01-01", "2005–2014", "2015–2025")
        for fn, f in 筛.items():
            m = f(pd.Series(a, index=ev.index), pd.Series(b, index=ev.index)).fillna(False).to_numpy(bool)
            for dk in ("2005–2014", "2015–2025", "合计"):
                g = ev[m & ((ev["十年"] == dk) if dk != "合计" else True)]
                net = g["毛R"] - 0.0015 * g["费F"] - 0.01 * g["借F"]
                row = {"轮": "第一轮·日线进场", "类": c, "认法": vn, "筛": fn, "十年": dk, **汇(net, g)}
                if c.startswith("个股"): row["借券5pct每笔净R"] = round(float((g["毛R"] - 0.0015 * g["费F"] - 0.05 * g["借F"]).mean()), 3) if len(g) else None
                T1.append(row)
    # 第二轮（ETF、1 小时线；取基准：看 7 根、最多试 3 次）
    t2 = pd.read_csv(os.path.join(OUT, "第二轮_小周期_逐笔.csv")); t2 = t2[(t2["K"] == 7) & (t2["试几次"] == 3) & (t2["日"] <= "2025-12-31")].copy()
    t2["类"] = np.where(t2["票"].isin(["SPY", "QQQ", "DIA", "IWM"]), "指数", "行业")
    a, b = 贴档(t2, "日"); t2["三层"], t2["五档"] = a, b
    t2["十年"] = np.where(t2["日"] < "2015-01-01", "2005–2014", "2015–2025")
    for fn, f in 筛.items():
        m = f(pd.Series(a, index=t2.index), pd.Series(b, index=t2.index)).fillna(False).to_numpy(bool)
        for (c, z, sn), g0 in t2[m].groupby(["类", "核心", "止损"]):
            for dk in ("2005–2014", "2015–2025", "合计"):
                g = g0 if dk == "合计" else g0[g0["十年"] == dk]
                T1.append({"轮": "第二轮·1小时进场", "类": c, "认法": f"核心{z}·{sn}止损", "筛": fn, "十年": dk, **汇(g["净R"], g)})
    T = pd.DataFrame(T1); T.to_csv(os.path.join(OUT, "第三轮_大周期过滤_汇总.csv"), index=False)
    # 逐年（第一轮个股认法 a，五档=跌势）
    json.dump(R, io.open(os.path.join(OUT, "第三轮_档位占比.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(json.dumps(R, ensure_ascii=False))
    return T


if __name__ == "__main__":
    T = main(); pd.set_option("display.width", 250); pd.set_option("display.max_rows", 500)
    x = T[(T["十年"] != "合计")]
    print(x[x["轮"] == "第一轮·日线进场"][["类", "认法", "筛", "十年", "笔数", "每笔净R", "利润因子", "到1倍pct", "随机对照净R", "去掉最赚3笔", "借券5pct每笔净R"]].to_string())
