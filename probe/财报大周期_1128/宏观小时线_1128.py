# -*- coding: utf-8 -*-
"""《571》第五批 · 宏观数据那几条（《527 拍板》第 2 条）：指数和杠杆 ETF 公布前 2 小时到公布后 30 分钟，1 小时线不开新单。
先查数据：ETF 小时线（market_ext_1105/ETF和币_1120/小时线_2015起）有盘前、盘中、盘后三段，2015 起；QQQ、SPY、TQQQ、SOXL 都在。
时间：CPI、非农 8:30（美东）→ 不开新单的窗口 6:30~9:00，全在盘前；卡里规定扳机只看常规时段（9:30–16:00），所以这条对 CPI、非农实际管不到任何一根常规时段的 1 小时线。
      议息 14:00 → 窗口 12:00~14:30：数据里的 1 小时线是 9:30 起每整点半一根，收盘在 12:30、13:30、14:30 的三根在窗口里（14:30 算在内），按收盘进的单子会被拦。
没有现成的 1 小时线做多策略流水，这里只测「如果在那两根收盘进场」风险是不是更大：
  每根收盘假设进一笔多单，止损 = 进场价 − 1.5 × 1 小时 ATR(14)（★ 我定的，另试 1.0、2.0），看之后 3 根常规时段 1 小时线里有没有打到止损，以及到次日收盘的涨跌。
  对照 = 同一时刻（12:30、13:30、14:30 收盘）、不是议息日的日子。2015–2021（美股 2022 起封存）。"""
import os, glob, json
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out")
fs = sorted(f for f in glob.glob(os.path.join(ROOT, "market_ext_1105/ETF和币_1120/小时线_2015起/*.parquet")) if int(os.path.basename(f)[:4]) <= 2021)
syms = ["QQQ", "SPY", "TQQQ", "SOXL"]
X = pd.concat([pd.read_parquet(f, filters=[("symbol", "in", syms)]) for f in fs]); X = X[X.session == "regular"].copy()
X["t"] = pd.to_datetime(X.time_utc).dt.tz_convert("America/New_York"); X = X[X.t.dt.year <= 2021]
fomc = pd.to_datetime(pd.read_csv(os.path.join(ROOT, "probe/事件闸门_1127/议息日_日期表_2015到2021.csv")).decision_date).dt.date
fomc = set(fomc)
res = {}
for s in syms:
    d = X[X.symbol == s].sort_values("t").reset_index(drop=True)
    h, l, c = d.high_adj.to_numpy(), d.low_adj.to_numpy(), d.close_adj.to_numpy()
    pc = np.roll(c, 1); tr = np.maximum(h - l, np.maximum(abs(h - pc), abs(l - pc))); atr = pd.Series(tr).rolling(14).mean().to_numpy()
    end = d.t + pd.to_timedelta(d.minutes, unit="min"); day = d.t.dt.date
    # 次日收盘
    dc = d.groupby(day).close_adj.last(); nxt = dc.shift(-1)
    for 倍 in (1.0, 1.5, 2.0):
        rows = []
        for i in range(14, len(d) - 3):
            hh = end.iloc[i].hour
            if end.iloc[i].minute != 30 or hh not in (12, 13, 14): continue
            S = c[i] - 倍 * atr[i]; hit = (l[i + 1:i + 4] <= S).any()
            nd = nxt.get(day.iloc[i], np.nan)
            rows.append((day.iloc[i] in fomc, hh, hit, nd / c[i] - 1 if nd == nd else np.nan))
        R = pd.DataFrame(rows, columns=["议息日", "收盘时刻", "打到止损", "到次日收盘"])
        g = R.groupby("议息日").agg(笔数=("打到止损", "size"), 三根内打到止损pct=("打到止损", lambda x: round(x.mean() * 100, 1)),
                                     到次日收盘平均pct=("到次日收盘", lambda x: round(x.mean() * 100, 3)), 到次日收盘波动pct=("到次日收盘", lambda x: round(x.std() * 100, 2)))
        res[f"{s}·止损{倍}倍ATR"] = {("议息日" if k else "不是议息日"): v for k, v in g.to_dict("index").items()}
    print(s, res[f"{s}·止损1.5倍ATR"], flush=True)
json.dump(res, open(os.path.join(OUT, "宏观小时线_议息.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
