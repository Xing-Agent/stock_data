# -*- coding: utf-8 -*-
"""《517》留出池跑完以后出数（开跑前就写好、登记，跑完不改）。
第 1 条：照 probe/事件闸门_1127/财报前进场_1127.py 原样（源码读进来，只把流水目录换成 out_留出池/、输出换到本目录），
        另按登记的判据算「两段各自的跳空打穿止损占比」（原脚本两段只打了每笔平均 R，判据要的是跳空打穿占比，口径同一列 gap_through）。
第 4 条：照 probe/大师接策略库_1126/算成绩_到2021_修坏点_1127.py 的算法（第一段按平仓日 ≤ 2021-12-31 挑、净值截到 2021-12-31；第二段整段），
        两个池子并排；另报四类先后次序、每条「已平单子合计赚亏」和「每年赚」方向一不一样、笔数。"""
import os, io, re, glob, json, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); H = os.path.join(HERE, "out_留出池") + "/"
OUT = os.path.join(HERE, "结果"); os.makedirs(OUT, exist_ok=True)

# ---------- 第 1 条 ----------
src = io.open(os.path.join(ROOT, "probe/事件闸门_1127/财报前进场_1127.py"), encoding="utf-8").read()
src = src.replace("A = os.path.join(R, 'probe/成绩单_1122/out_手册/')", f"A = {H!r}")
src = src.replace("os.path.join(R, 'probe/事件闸门_1127/out/财报前进场_汇总.csv')", f"{os.path.join(OUT, '第1条_财报前进场_汇总.csv')!r}")
src = src.replace("os.path.join(R, 'probe/事件闸门_1127/out/按策略族.csv')", f"{os.path.join(OUT, '第1条_按策略族.csv')!r}")
assert H in src and "第1条_财报前进场_汇总" in src
g = {"__file__": os.path.join(ROOT, "probe/事件闸门_1127/财报前进场_1127.py"), "__name__": "x"}; exec(compile(src, "财报前", "exec"), g); T = g["T"]
打穿 = lambda x: round(x.gap_through.astype(str).str.lower().eq("true").mean() * 100, 2) if len(x) else None
r1 = {"全段": {"前1~3天": (int(T.隔.between(1, 3).sum()), 打穿(T[T.隔.between(1, 3)])), "前6~20天": (int(T.隔.between(6, 20).sum()), 打穿(T[T.隔.between(6, 20)]))}}
for a, b in (("2015", "2018"), ("2019", "2021")):
    x = T[(T.entry_date >= a) & (T.entry_date <= b + "-12-31")]
    r1[f"{a}–{b}"] = {"前1~3天": (int(x.隔.between(1, 3).sum()), 打穿(x[x.隔.between(1, 3)])), "前6~20天": (int(x.隔.between(6, 20).sum()), 打穿(x[x.隔.between(6, 20)]))}
全 = r1["全段"]; 倍 = 全["前1~3天"][1] / 全["前6~20天"][1] if 全["前6~20天"][1] else None
两段 = all(r1[k]["前1~3天"][1] is not None and r1[k]["前6~20天"][1] is not None and r1[k]["前1~3天"][1] > r1[k]["前6~20天"][1] for k in ("2015–2018", "2019–2021"))
r1["判"] = dict(倍数=round(倍, 2) if 倍 else None, 倍数够1点5=bool(倍 and 倍 >= 1.5), 两段都是前1到3天更高=bool(两段), 成立=bool(倍 and 倍 >= 1.5 and 两段))
print("第1条", json.dumps(r1, ensure_ascii=False))

# ---------- 第 4 条 ----------
def 成绩(A, B=None):
    rows = []
    for f in sorted(glob.glob(A + "流水_*.csv")):
        b = os.path.basename(f)[3:-4]; seg, name = b.split("_", 1); d = A
        if seg == "二" and B and os.path.exists(B + f"流水_二_{name}.csv"): d = B
        t = pd.read_csv(d + f"流水_{seg}_{name}.csv"); e = pd.read_parquet(d + f"日线_{seg}_{name}.parquet")["eq"]
        还 = int(((t.entry_date <= "2021-12-31") & (t.exit_date > "2021-12-31")).sum()) if seg == "一" else 0
        if seg == "一": t = t[t.exit_date <= "2021-12-31"]; e = e[:"2021-12-31"]
        yrs = (e.index[-1] - e.index[0]).days / 365.25; r = t.r_multiple_net; pnl = t.net_pnl
        rows.append(dict(策略=name, 段="2005-2014" if seg == "二" else "2015-2021", 笔数=len(t), 截止时还拿着=还, 每笔平均R=round(r.mean(), 2) if len(t) else np.nan, 赚钱笔占比=round((r > 0).mean() * 100, 1) if len(t) else np.nan,
                         利润因子=round(pnl[pnl > 0].sum() / -pnl[pnl < 0].sum(), 2) if (pnl < 0).any() else np.nan, 已平合计赚=round(pnl.sum()), 每年赚=round(((e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1) * 100, 1), 最深亏损=round((e / e.cummax() - 1).min() * 100, 1)))
    return pd.DataFrame(rows)
类 = {"趋势跟随": ["trend_following", "技-1", "技-2", "技-3"], "突破": ["技-6", "技-4", "技-5", "技-8"], "均值回归": ["技-12", "技-14"], "假突破反手": ["技-10", "技-11", "技-13"]}
def 归(n): return next((k for k, v in 类.items() for p in v if n == p or n.startswith(p + "-")), None)
研 = 成绩(os.path.join(ROOT, "probe/成绩单_1122/out_手册") + "/", os.path.join(ROOT, "probe/成绩单_1122/out_手册_修") + "/"); 留 = 成绩(H)
for X in (研, 留): X["类"] = X.策略.map(归)
M = 研.merge(留, on=["策略", "段", "类"], suffixes=("_研发池", "_留出池"), how="outer"); M.to_csv(os.path.join(OUT, "第4条_逐条并排.csv"), index=False)
def 范围(X): return X[X.类.notna()].groupby(["类", "段"]).agg(版本=("策略", "nunique"), 每年赚最低=("每年赚", "min"), 每年赚最高=("每年赚", "max"), 每年赚中位=("每年赚", "median"), 笔数合计=("笔数", "sum"))
R4 = 范围(研).join(范围(留), lsuffix="_研发池", rsuffix="_留出池"); R4.to_csv(os.path.join(OUT, "第4条_四类范围.csv"))
次序 = {p: {s: list(范围(X).xs(s, level="段")["每年赚中位"].sort_values(ascending=False).index) for s in ("2005-2014", "2015-2021")} for p, X in (("研发池", 研), ("留出池", 留))}
留["方向一致"] = np.sign(留.已平合计赚) == np.sign(留.每年赚); 不一致 = 留[~留.方向一致 & 留.类.notna()][["策略", "段", "笔数", "截止时还拿着", "已平合计赚", "每年赚"]]
json.dump(dict(第1条=r1, 第4条_次序=次序, 第4条_方向不一致=不一致.to_dict("records")), open(os.path.join(OUT, "结果.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
pd.set_option("display.width", 250); print(R4.to_string()); print(次序); print(不一致.to_string(index=False))
