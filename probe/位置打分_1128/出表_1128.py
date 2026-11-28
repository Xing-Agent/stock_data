# -*- coding: utf-8 -*-
"""《533》第六批 · 第 6 条出表。读 out/逐笔.parquet、out/测试后破没破.parquet，写 out/表_*.csv 并打印。"""
import os, sys, numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__)); D = os.path.join(HERE, sys.argv[1] if len(sys.argv) > 1 else "out")
pd.set_option("display.width", 250); pd.set_option("display.max_rows", 300)
df = pd.read_parquet(os.path.join(D, "逐笔.parquet")); br = pd.read_parquet(os.path.join(D, "测试后破没破.parquet"))


def st(g):
    r = g.R.to_numpy(); w = r[r > 0].sum(); lo = -r[r < 0].sum()
    return pd.Series(dict(笔数=len(r), 每笔R=round(r.mean(), 3), 中位R=round(np.median(r), 3), 胜率=round((r > 0).mean() * 100, 1), 利润因子=round(w / lo, 2) if lo > 0 else np.nan,
                          t=round(r.mean() / (r.std(ddof=1) / np.sqrt(len(r))), 1) if len(r) > 2 else np.nan, 去掉最好1pct每笔R=round(np.sort(r)[: max(1, int(len(r) * 0.99))].mean(), 3)))


def 存(t, nm): t.to_csv(os.path.join(D, f"表_{nm}.csv"), index=False); print(f"\n=== {nm}"); print(t.to_string(index=False))


br["第几次"] = br.第几次.clip(upper=5).astype(str).replace({"5": "5+"}); br["方向"] = br.方向.map({1: "阻力（往上破）", -1: "支撑（往下破）"})
存(br.groupby(["方向", "段", "第几次"]).破了.agg(次数="count", 十天内破了pct=lambda x: round(x.mean() * 100, 1)).reset_index(), "一_碰第几次后破没破")
存(br.groupby(["方向", "类", "第几次"]).破了.agg(次数="count", 十天内破了pct=lambda x: round(x.mean() * 100, 1)).reset_index(), "一b_按类")

df["次组"] = df.第几次.clip(upper=4).astype(str).replace({"4": "4+"})
F = df[df.事件 == "假突破反手"]
存(F.groupby(["位置", "方向", "段", "次组"]).apply(st, include_groups=False).reset_index(), "二_假突破反手_按第几次")
rows = []
for 名, m in (("只做第1次", F.第几次 == 1), ("第1、2次（拍板）", F.第几次 <= 2), ("做到第3次", F.第几次 <= 3), ("不限", F.第几次 > 0)):
    for k, g in F[m].groupby(["位置", "方向", "段"]): rows.append(dict(规则=名, 位置=k[0], 方向=k[1], 段=k[2], **st(g)))
存(pd.DataFrame(rows), "三_假突破反手_次数上限")
T = df[df.位置 == "真位置"]
存(T.groupby(["事件", "方向", "段", "分数"]).apply(st, include_groups=False).reset_index(), "四_按分数")
存(T.groupby(["事件", "方向", "几样"]).apply(st, include_groups=False).reset_index(), "四b_按哪几样")
S = F[(F.方向 == "空")].assign(逆着强上涨=lambda x: x.ADX强 & ~x.顺势)
存(S.groupby(["位置", "段", "逆着强上涨"]).apply(st, include_groups=False).reset_index(), "五_阻力反手空_ADX过滤")
存(df[df.方向 == "空"].groupby(["位置", "事件", "段", "大盘熊"]).apply(st, include_groups=False).reset_index(), "六_空单_大盘开关")
P = df[df.事件.isin(["突破后第一次回踩", "跌破后第一次反抽"])]
存(P.groupby(["位置", "事件", "段"]).apply(st, include_groups=False).reset_index(), "七_突破后第一次回踩")
存(df.groupby(["位置", "事件", "方向", "段"]).apply(st, include_groups=False).reset_index(), "八_总表")
存(T.groupby(["段"]).apply(lambda g: pd.Series(dict(票数=g.票.nunique(), 每只票每年假突破=round((g.事件 == "假突破反手").sum() / g.票.nunique() / (10 if g.name == "2005-2014" else 7), 1))), include_groups=False).reset_index(), "九_位置有多密")
