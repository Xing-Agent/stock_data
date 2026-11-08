# -*- coding: utf-8 -*-
"""
★★★ 规矩④「数字变好看先当自己错了」:把落在随机带外(或接近)的臂逐笔拆开。
★ 两种「可疑笔」:① 持有期间跨过疑似假跳变日(±15 日)② 出场价 ÷ 进场价 ≥ 10 倍(★ 逐只要回源头核)
★ 报:可疑笔占该臂总盈亏几成;剔掉后的资金年化(纯价格口径 —— ★ 逐笔流水不含分红)。
"""
import glob, io, json, os
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
脏 = json.load(io.open(os.path.join(HERE, "假跳变_并池2004修接缝_1108.json"), encoding="utf-8"))["脏日"]


def 年化(d):
    cd = d["capital_days"].sum()
    return round(float(d["net_pnl"].sum() / cd * 252 * 100), 3) if cd > 0 else None


out, 十倍 = {}, {}
for f in sorted(glob.glob(os.path.join(HERE, "ledgers_2009修接缝", "REAL__*.csv"))):
    d = pd.read_csv(f)
    if d.empty:
        continue
    名 = os.path.basename(f)[6:-4]

    def 跨(r):
        ds = 脏.get(str(r.symbol), [])
        a = pd.Timestamp(str(r.entry_date)[:10]) - pd.Timedelta(days=15)
        b = pd.Timestamp(str(r.exit_date)[:10]) + pd.Timedelta(days=15)
        return any(a <= pd.Timestamp(x) <= b for x in ds)
    d["跨假跳变"] = d.apply(跨, axis=1)
    d["十倍"] = d["exit_price"] / d["entry_price"] >= 10
    bad = d["跨假跳变"] | d["十倍"]
    tot = d["net_pnl"].sum()
    out[名] = {"笔数": len(d), "可疑笔": int(bad.sum()),
              "可疑笔占总盈亏pct": round(float(d.loc[bad, "net_pnl"].sum() / tot * 100), 1) if tot else None,
              "资金年化(纯价格)": 年化(d), "★剔可疑笔后资金年化(纯价格)": 年化(d[~bad])}
    for _, r in d[d["十倍"]].iterrows():
        十倍.setdefault(r.symbol, []).append(f"{str(r.entry_date)[:10]}→{str(r.exit_date)[:10]} "
                                           f"{r.entry_price:.4g}→{r.exit_price:.4g}")
rep = {"★口径": "逐笔流水 = 纯价格(分红只进净值);可疑 = 跨假跳变(±15 日)或 出场÷进场 ≥ 10 倍",
       "逐臂": out, "★涨10倍以上的票(要数据组回源头核)": {k: sorted(set(v)) for k, v in 十倍.items()}}
io.open(os.path.join(HERE, "拆脏数_2009.json"), "w", encoding="utf-8").write(
    json.dumps(rep, ensure_ascii=False, indent=1))
for k, v in out.items():
    print(k, v)
print(len(十倍), "只涨 10 倍以上:", list(十倍)[:40])
