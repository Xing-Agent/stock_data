# -*- coding: utf-8 -*-
"""市场概览页要回填的四样数字（V3 chat 任务单 1125）· 引擎外 · 只读
股票池：研究库的研发池（约 1,300 只，按当天在池里的算），不是标普 500 历史成分 —— 仓库里没有历史成分表。
宽度：probe/减仓_1121/宽度_每日.csv（站上 50 日线占比、创一年新高占比），2004-01 ~ 2026-11-04。
大盘闸（行业惯例版）：标普收盘 > 200 日线，且 200 日线 > 20 个交易日前。
五档：健康多头 = 开 & 宽度 ≥ 上；分化多头 = 开 & 宽度 < 中；分化空头 = 关 & 宽度 ≥ 中；全面空头 = 关 & 宽度 ≤ 下；其余 = 过渡。默认 上/中/下 = 60/50/40；对比版 = 50/50/50。
第 4 样：打法用手册里已有、名字对得上的策略的现成流水（probe/成绩单_1122/out_手册/），按进场那天的状态分格。
        2022-01-01 以后的单子照《422 拍板》单独存（out/封存_*.csv），不进统计。所以第二段是 2015–2021，不是 2015–2025。"""
import os, json, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(os.path.dirname(HERE)); OUT = os.path.join(HERE, "out")
B = pd.read_csv(os.path.join(ROOT, "probe/减仓_1121/宽度_每日.csv"), parse_dates=["date"]).set_index("date"); B = B[B["池里几只"] > 0]
S = pd.read_csv(os.path.join(ROOT, "market_ext_1105/指数长历史_1123/标普500指数_日线.csv"), parse_dates=["date"]).set_index("date")["close"].astype(float)
m200 = S.rolling(200).mean(); 闸 = ((S > m200) & (m200 > m200.shift(20))).reindex(B.index).fillna(False)
W = B["站上50日线pct"].astype(float); NH = B["创一年新高pct"].astype(float); spx = S.reindex(B.index).ffill()
def 五档(上, 中, 下):
    st = pd.Series("过渡", index=B.index)
    st[闸 & (W >= 上)] = "健康多头"; st[闸 & (W < 中)] = "分化多头"; st[(~闸) & (W >= 中)] = "分化空头"; st[(~闸) & (W <= 下)] = "全面空头"; return st
# ---------- 1 宽度的历史分位
def 分位(x):
    r = x.expanding(min_periods=250).apply(lambda a: (a[:-1] < a[-1]).mean() * 100 if len(a) > 1 else np.nan, raw=True)   # 只和当天以前比
    full = x.rank(pct=True) * 100                                                                                            # 和 2004 年以来全部比（含以后）
    return r, full
r1, f1 = 分位(W); r2, f2 = 分位(NH)
T1 = pd.DataFrame({"站上50日线pct": W.round(1), "站上50日线_分位_只和以前比": r1.round(0), "站上50日线_分位_全历史": f1.round(0), "站上50日线_比上周变化": (W - W.shift(5)).round(1),
                   "创一年新高pct": NH.round(1), "创一年新高_分位_只和以前比": r2.round(0), "创一年新高_分位_全历史": f2.round(0), "创一年新高_比上周变化": (NH - NH.shift(5)).round(1),
                   "大盘闸": np.where(闸, "开", "关"), "五档_默认": 五档(60, 50, 40), "五档_一刀切50": 五档(50, 50, 50), "标普收盘": spx.round(2), "池里几只": B["池里几只"]})
T1.to_csv(os.path.join(OUT, "1_宽度的历史分位_每日.csv"))
# ---------- 2 矛盾有多常见
rows = []
for nm, a, b in (("全部 2004-2026", "2004-01-01", "2026-12-31"), ("2005-2014", "2005-01-01", "2014-12-31"), ("2015-2025", "2015-01-01", "2025-12-31"), ("2026", "2026-01-01", "2026-12-31")):
    g = 闸.loc[a:b]; w = W.loc[a:b]
    for th in (50, 40):
        rows.append(dict(时间段=nm, 宽度门槛=th, 交易日=len(g), 闸开天数=int(g.sum()), 闸开但宽度低于门槛_天数=int((g & (w < th)).sum()), 占闸开天数pct=round(float((g & (w < th)).sum() / max(1, g.sum()) * 100), 1),
                         闸关天数=int((~g).sum()), 闸关但宽度不低于门槛_天数=int(((~g) & (w >= th)).sum()), 占闸关天数pct=round(float(((~g) & (w >= th)).sum() / max(1, (~g).sum()) * 100), 1)))
pd.DataFrame(rows).to_csv(os.path.join(OUT, "2_矛盾有多常见.csv"), index=False)
# ---------- 3 每档状态的历史
def 段(st):
    g = (st != st.shift()).cumsum(); out = []
    for _, x in st.groupby(g):
        i1 = B.index.get_loc(x.index[-1]); f = lambda k: (spx.iloc[i1 + k] / spx.iloc[i1] - 1) * 100 if i1 + k < len(spx) else np.nan
        out.append(dict(状态=x.iloc[0], 起=x.index[0].date(), 止=x.index[-1].date(), 天数=len(x), 期间标普涨跌pct=round((spx.loc[x.index[-1]] / spx.loc[x.index[0]] - 1) * 100, 1), 结束后20日=f(20), 结束后60日=f(60)))
    return pd.DataFrame(out)
rows = []
for ver, th in (("默认60/50/40", (60, 50, 40)), ("一刀切50", (50, 50, 50))):
    st = 五档(*th); G = 段(st); G.to_csv(os.path.join(OUT, f"3附_每一段明细_{ver.replace('/', '_')}.csv"), index=False)
    for s, x in G.groupby("状态"):
        L = x.loc[x.天数.idxmax()]; q = lambda c, p: round(float(x[c].dropna().quantile(p)), 1) if x[c].notna().any() else None
        rows.append(dict(版本=ver, 状态=s, 总天数=int(x.天数.sum()), 占全部交易日pct=round(x.天数.sum() / len(st) * 100, 1), 一共几段=len(x), 每段平均几天=round(x.天数.mean(), 1), 每段中位几天=float(x.天数.median()),
                         最长一段=f"{L.起} ~ {L.止}（{L.天数} 天）", 结束后20日_中位=q("结束后20日", .5), 结束后20日_下四分=q("结束后20日", .25), 结束后20日_上四分=q("结束后20日", .75), 结束后20日_涨的比例pct=round(float((x.结束后20日.dropna() > 0).mean() * 100), 0),
                         结束后60日_中位=q("结束后60日", .5), 结束后60日_下四分=q("结束后60日", .25), 结束后60日_上四分=q("结束后60日", .75), 结束后60日_涨的比例pct=round(float((x.结束后60日.dropna() > 0).mean() * 100), 0)))
    r20 = (spx.shift(-20) / spx - 1) * 100; r60 = (spx.shift(-60) / spx - 1) * 100
    rows.append(dict(版本=ver, 状态="对照·任意一天", 总天数=len(st), 结束后20日_中位=round(float(r20.median()), 1), 结束后20日_下四分=round(float(r20.quantile(.25)), 1), 结束后20日_上四分=round(float(r20.quantile(.75)), 1), 结束后20日_涨的比例pct=round(float((r20.dropna() > 0).mean() * 100), 0),
                     结束后60日_中位=round(float(r60.median()), 1), 结束后60日_下四分=round(float(r60.quantile(.25)), 1), 结束后60日_上四分=round(float(r60.quantile(.75)), 1), 结束后60日_涨的比例pct=round(float((r60.dropna() > 0).mean() * 100), 0)))
pd.DataFrame(rows).to_csv(os.path.join(OUT, "3_每档状态的历史.csv"), index=False)
# ---------- 4 每种打法在每档状态下的成绩
打法 = {"趋势跟随（唐奇安通道，手册 trend_following-原著-唐奇安反向通道离场）": "trend_following-原著-唐奇安反向通道离场", "均值回归（RSI2 回踩买，手册 技-14-行业-RSI2）": "技-14-行业-RSI2",
        "突破买入·候选一（达瓦斯箱体，手册 技-6-XING）": "技-6-XING", "突破买入·候选二（VCP 波动收缩，手册 技-5-XING）": "技-5-XING", "突破买入·候选三（杯柄，手册 技-4-行业）": "技-4-行业"}
sret = spx.pct_change().fillna(0)
def 最深(x):
    c = (1 + x).cumprod(); return round(float((c / c.cummax() - 1).min() * 100), 1) if len(x) else None
rows = []
for ver, th in (("默认60/50/40", (60, 50, 40)), ("一刀切50", (50, 50, 50))):
    st = 五档(*th)
    for 名, f in 打法.items():
        for seg, lab, a, b in (("二", "2005-2014", "2005-01-01", "2014-12-31"), ("一", "2015-2021", "2015-01-01", "2021-12-31")):
            p = os.path.join(ROOT, "probe/成绩单_1122/out_手册", f"流水_{seg}_{f}.csv")
            if not os.path.exists(p): rows.append(dict(版本=ver, 打法=名, 时间段=lab, 状态="没有流水")); continue
            L = pd.read_csv(p, parse_dates=["entry_date", "exit_date"])
            if seg == "一" and ver.startswith("默认"): L[L.entry_date >= "2022-01-01"].to_csv(os.path.join(OUT, f"封存_{f}.csv"), index=False)
            L = L[(L.entry_date >= a) & (L.entry_date <= b)].sort_values("exit_date"); L["状态"] = st.reindex(L.entry_date).to_numpy()
            L["ret"] = L.net_pnl / L.notional_in; e = spx.reindex(L.entry_date, method="ffill").to_numpy(); x_ = spx.reindex(L.exit_date, method="ffill").to_numpy(); L["超额"] = L.ret - (x_ / e - 1)
            days = st.loc[a:b]
            for s in ["健康多头", "分化多头", "过渡", "分化空头", "全面空头", "全部"]:
                x = L if s == "全部" else L[L.状态 == s]; n = len(x); d = days.index if s == "全部" else days.index[days == s]
                row = dict(版本=ver, 打法=名, 时间段=lab, 状态=s, 这档有几个交易日=len(d), 交易笔数=n, 样本太少=("是" if n < 30 else ""))
                if n:
                    w = x.r_multiple_net; win = w[w > 0]; los = w[w <= 0]; seq = (w <= 0).astype(int); k = m = 0
                    for v in seq: k = k + 1 if v else 0; m = max(m, k)
                    cum = w.cumsum()
                    row.update(赚钱的概率pct=round(float((w > 0).mean() * 100), 1), 盈亏比=round(float(win.mean() / -los.mean()), 2) if len(win) and len(los) and los.mean() < 0 else None, 最大连亏几笔=int(m),
                               最大回撤_按笔累计R=round(float((cum - cum.cummax()).min()), 1), 每笔净R=round(float(w.mean()), 2), 利润因子=round(float(win.sum() / max(1e-9, -los.sum())), 2),
                               每笔超额pct_对同期标普=round(float(x.超额.mean() * 100), 2), t_每笔超额=round(float(x.超额.mean() / x.超额.std() * np.sqrt(n)), 1) if n > 2 and x.超额.std() > 0 else None,
                               t_每笔净R=round(float(w.mean() / w.std() * np.sqrt(n)), 1) if n > 2 and w.std() > 0 else None)
                row["同期满仓标普最大回撤pct_只算这档的日子"] = 最深(sret.reindex(d)); rows.append(row)
pd.DataFrame(rows).to_csv(os.path.join(OUT, "4_每种打法在每档状态下的成绩.csv"), index=False)
print(T1.tail(2).T.to_string()); print(pd.read_csv(os.path.join(OUT, "2_矛盾有多常见.csv")).to_string()); pd.set_option("display.width", 300)
print(pd.read_csv(os.path.join(OUT, "3_每档状态的历史.csv")).to_string())
