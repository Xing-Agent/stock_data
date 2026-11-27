# -*- coding: utf-8 -*-
"""《488》第 5 项 · 基本面 11 条 + 融合 3 条的成绩截到 2021-12-31（引擎外，不重跑引擎）。
来源：probe/含分红重出_1116/ 里 11-18「按表折算」那一版的每日净值和流水（就是策略库「新口径成绩」表的出处：和卡里 2015–2025 的数逐条对得上，见脚本最后的核对）。
为什么截断等于重跑：这些策略每天只用当天及以前的数据做决定，所以 2015-01-02 ~ 2021-12-31 这段的每日净值，和「把结束日改成 2021-12-31 重跑」逐日一样；
  差别只在最后一天：重跑会在 2021-12-31 平掉还拿着的仓位，截断是按当天收盘计价——净值一样，只是那几笔没算进「笔数」。
流水：只算 2021-12-31 之前已经平掉的笔（平仓日在 2022 年以后的，用到了封存数据，不算，单独报有几笔）。
利润因子按金额（赚的钱总和 ÷ 亏的钱总和），赚钱笔占比按扣成本后的 R > 0，和 11-18 汇总表同口径。"""
import os, glob, json, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); SRC = os.path.join(ROOT, "probe/含分红重出_1116")
截 = "2021-12-31"
def 指标(e):
    y = (e.index[-1] - e.index[0]).days / 365.25; return round(((e.iloc[-1] / e.iloc[0]) ** (1 / y) - 1) * 100, 2), round(((e / e.cummax()) - 1).min() * 100, 1)
rows = []; 核 = []
for f in sorted(glob.glob(os.path.join(SRC, "基本面融合_日净值_按表折算", "*.csv"))):
    名 = os.path.basename(f)[:-4]; e = pd.read_csv(f, index_col=0, parse_dates=True).iloc[:, 0].dropna()
    t = pd.read_csv(os.path.join(SRC, "基本面融合_ledgers_按表折算", 名 + ".csv"), parse_dates=["entry_date", "exit_date"])
    全 = 指标(e); 核.append((名, 全, len(t)))
    e2 = e.loc[:截]; t2 = t[t.exit_date <= 截]; 挂 = int(((t.entry_date <= 截) & (t.exit_date > 截)).sum())
    w = t2.net_pnl[t2.net_pnl > 0].sum(); lo = -t2.net_pnl[t2.net_pnl < 0].sum(); cg, dd = 指标(e2)
    yr = e2.resample("YE").last(); yr = (yr / yr.shift(1).fillna(e2.iloc[0]) - 1) * 100
    rows.append(dict(条目=名, 每年赚=cg, 最深亏损=dd, 赚钱笔占比=round((t2.r_multiple_net > 0).mean() * 100, 1) if len(t2) else None, 利润因子=round(w / lo, 2) if lo > 0 else None, 笔数=len(t2), 截止时还拿着=挂,
                     赚钱的年数=f"{int((yr > 0).sum())} / {len(yr)}", 按年=" ".join(f"{d.year}:{v:+.1f}" for d, v in yr.items())))
    e2.to_csv(os.path.join(HERE, "净值", 名 + ".csv")); t2.to_csv(os.path.join(HERE, "流水", 名 + ".csv"), index=False)
b = pd.read_csv(os.path.join(SRC, "基本面主对标_日净值_1119.csv"), index_col=0, parse_dates=True).iloc[:, 0].dropna()
bh全, bh = 指标(b), 指标(b.loc[:截]); b.loc[:截].to_csv(os.path.join(HERE, "净值", "全买不动_同范围.csv"))
O = pd.DataFrame(rows); O.to_csv(os.path.join(HERE, "成绩_2015到2021.csv"), index=False)
pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 120); print(O.drop(columns="按年").to_string(index=False)); print(O[["条目", "按年"]].to_string(index=False))
print("全买不动（同范围，含分红，不扣成本）2015–2021:", bh, " 2015–2025:", bh全)
print("核对 2015–2025 全段（应和卡里新口径表一样）:"); [print(" ", x) for x in 核]
json.dump(dict(截止=截, 全买不动_2015到2021=bh, 全买不动_2015到2025=bh全, 条目=rows), open(os.path.join(HERE, "成绩_2015到2021.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
