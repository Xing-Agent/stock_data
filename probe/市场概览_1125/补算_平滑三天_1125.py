# -*- coding: utf-8 -*-
"""回 V3 chat《462》的补算：① 换档要新状态连续 3 个交易日成立才算，重算第 3 样；② 第 4 样补成小表（3 种打法 × 5 档 × 2 段，状态用平滑后的）。
口径同 市场概览回填_1125.py（研发池宽度、行业惯例版大盘闸、默认 60/50/40）。打法成绩只到 2021（封存规矩）。"""
import os, importlib.util, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
sp = importlib.util.spec_from_file_location("m", os.path.join(HERE, "市场概览回填_1125.py")); M = importlib.util.module_from_spec(sp); sp.loader.exec_module(M)
def 平滑(st, k=3):
    v = st.to_numpy(); out = v.copy(); cur = v[0]; cand = None; run = 0
    for i in range(len(v)):
        if v[i] == cur: cand = None; run = 0
        else:
            if v[i] == cand: run += 1
            else: cand = v[i]; run = 1
            if run >= k: cur = cand; cand = None; run = 0
        out[i] = cur
    return pd.Series(out, index=st.index)
raw = M.五档(60, 50, 40); rows = []
for k in (1, 2, 3, 5):
    st = raw if k == 1 else 平滑(raw, k); G = M.段(st)
    if k == 3: G.to_csv(os.path.join(OUT, "3附_每一段明细_平滑3天.csv"), index=False); st.rename("五档_平滑3天").to_csv(os.path.join(OUT, "1附_每天的档_平滑3天.csv"))
    for s, x in G.groupby("状态"):
        L = x.loc[x.天数.idxmax()]; q = lambda c, p: round(float(x[c].dropna().quantile(p)), 1)
        rows.append(dict(连续几天才换档=k, 状态=s, 总天数=int(x.天数.sum()), 占全部交易日pct=round(x.天数.sum() / len(st) * 100, 1), 一共几段=len(x), 每段平均几天=round(x.天数.mean(), 1), 每段中位几天=float(x.天数.median()), 最长一段=f"{L.起} ~ {L.止}（{L.天数} 天）",
                         结束后20日_中位=q("结束后20日", .5), 结束后20日_下四分=q("结束后20日", .25), 结束后20日_上四分=q("结束后20日", .75), 结束后20日_涨的比例pct=round(float((x.结束后20日.dropna() > 0).mean() * 100)),
                         结束后60日_中位=q("结束后60日", .5), 结束后60日_下四分=q("结束后60日", .25), 结束后60日_上四分=q("结束后60日", .75), 结束后60日_涨的比例pct=round(float((x.结束后60日.dropna() > 0).mean() * 100)), 这个版本22年一共换档几次=len(G) - 1))
T3 = pd.DataFrame(rows); T3.to_csv(os.path.join(OUT, "3_每档状态的历史_平滑版.csv"), index=False)
st3 = 平滑(raw, 3); 打法 = {"趋势跟随（唐奇安通道）": "trend_following-原著-唐奇安反向通道离场", "均值回归（RSI2 回踩买）": "技-14-行业-RSI2", "突破买入（达瓦斯箱体）": "技-6-XING"}; rows = []
for 名, f in 打法.items():
    for seg, lab, a, b in (("二", "2005-2014", "2005-01-01", "2014-12-31"), ("一", "2015-2021", "2015-01-01", "2021-12-31")):
        L = pd.read_csv(os.path.join(M.ROOT, "probe/成绩单_1122/out_手册", f"流水_{seg}_{f}.csv"), parse_dates=["entry_date", "exit_date"]); L = L[(L.entry_date >= a) & (L.entry_date <= b)].sort_values("exit_date"); L["状态"] = st3.reindex(L.entry_date).to_numpy(); days = st3.loc[a:b]
        for s in ["健康多头", "分化多头", "过渡", "分化空头", "全面空头", "全部"]:
            x = L if s == "全部" else L[L.状态 == s]; n = len(x); w = x.r_multiple_net; row = dict(打法=名, 时间段=lab, 状态=s, 这档有几个交易日=int(len(days) if s == "全部" else (days == s).sum()), 笔数=n, 平均每笔几R=(round(float(w.mean()), 2) if n else None), 样本太少=("是" if n < 30 else ""))
            if n:
                win = w[w > 0]; los = w[w <= 0]; k = m = 0
                for v in (w <= 0): k = k + 1 if v else 0; m = max(m, k)
                cum = w.cumsum(); row.update(赚钱的概率pct=round(float((w > 0).mean() * 100), 1), 盈亏比=(round(float(win.mean() / -los.mean()), 2) if len(win) and len(los) and los.mean() < 0 else None), 最大连亏几笔=int(m), 最大回撤_按笔累计R=round(float((cum - cum.cummax()).min()), 1), 利润因子=round(float(win.sum() / max(1e-9, -los.sum())), 2), t=(round(float(w.mean() / w.std() * np.sqrt(n)), 1) if n > 2 and w.std() > 0 else None))
            rows.append(row)
T4 = pd.DataFrame(rows); T4.to_csv(os.path.join(OUT, "4_打法成绩小表_平滑3天.csv"), index=False)
pd.set_option("display.width", 250)
print(T3[["连续几天才换档", "状态", "占全部交易日pct", "一共几段", "每段中位几天", "每段平均几天", "最长一段", "结束后20日_中位", "结束后60日_中位", "这个版本22年一共换档几次"]].to_string(index=False))
P = T4[T4.状态 != "全部"].pivot_table(index=["打法", "状态"], columns="时间段", values=["平均每笔几R", "笔数"], aggfunc="first"); print(P.to_string())
print("最新一天", st3.index[-1].date(), "原始", raw.iloc[-1], "平滑后", st3.iloc[-1])
