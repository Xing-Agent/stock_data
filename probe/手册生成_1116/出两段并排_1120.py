# -*- coding: utf-8 -*-
"""技术面每条策略:2015-2025 和 2005-2014 两段成绩并排。只读已有结果,不跑回测。"""
import os, io, json, glob
import pandas as pd
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
A = os.path.join(ROOT, "probe/含分红重出_1116/技术面中档_out")
B = os.path.join(ROOT, "probe/两段时间_1120/第二段_汇总_1120.csv")
BENCH = {"一": (7.28, -40.3, 13.47, -33.7), "二": (9.69, -57.8, 7.61, -55.2)}

def f(x, d=1):
    try:
        x = float(x)
    except Exception:
        return "—"
    if x != x:
        return "—"
    return ("%." + str(d) + "f") % x if d else "%d" % round(x)

def main():
    a = {}
    for p in glob.glob(A + "/*.json"):
        r = json.load(io.open(p, encoding="utf-8"))
        if not r.get("跑失败"):
            a[r["名"]] = r
    b = pd.read_csv(B)
    b = b[b["做法"] == "原样"].set_index("策略")
    names = sorted(set(a) | set(b.index))
    L = []
    L.append("# 339 · 技术面每条策略：两段时间的成绩并排（对内 · 2026-11-20）\n")
    L.append("**一句话：34 个技术面版本，在 2015–2025 这段有 %d 个每年赚得比「同池子全买不动」多；换到 2005–2014（含 2008 年），只剩 %d 个，而且 2008 年没有一个是正的。**\n")
    L.append("> 怎么测的：两段各是一个独立的十年左右。第一段 2015-01 到 2025-12（11 年），第二段 2005-01 到 2014-12（10 年）。规则、股票池门槛（每天成交 1000 万美元以上）、算分红，两段完全一样，没有为第二段调过任何东西。只用研发池。")
    L.append("> 「每年赚」是复合年化。「算不出来」和「成绩差」分开记：表里的「—」是没跑出结果，不是 0 分。")
    L.append("> 第二段的数据里缺一批当年破产的名股（LEH、BSC 等，见《338》），所以第二段对做多策略可能偏乐观。\n")
    L.append("**两把尺子**\n")
    L.append("| | 2015–2025 每年赚 | 最惨跌掉 | 2005–2014 每年赚 | 最惨跌掉 |")
    L.append("|---|---:|---:|---:|---:|")
    L.append("| 同池子全买不动 | %.2f%% | %.1f%% | %.2f%% | %.1f%% |" % (BENCH["一"][0], BENCH["一"][1], BENCH["二"][0], BENCH["二"][1]))
    L.append("| 标普 500 | %.2f%% | %.1f%% | %.2f%% | %.1f%% |\n" % (BENCH["一"][2], BENCH["一"][3], BENCH["二"][2], BENCH["二"][3]))
    L.append("## 总表（按第二段每年赚从高到低）\n")
    L.append("| 策略版本 | ① 每年赚 | ① 最惨跌 | ① 赢同池？ | ② 每年赚 | ② 最惨跌 | ② 2008 年 | ② 赢同池？ | 两段都赢同池？ |")
    L.append("|---|---:|---:|:-:|---:|---:|---:|:-:|:-:|")
    rows = []
    for n in names:
        r1 = a.get(n); r2 = b.loc[n] if n in b.index else None
        y1 = r1["复合年化pct"] if r1 else None
        y2 = float(r2["每年赚pct"]) if r2 is not None else None
        w1 = (y1 is not None and y1 > BENCH["一"][0]); w2 = (y2 is not None and y2 > BENCH["二"][0])
        rows.append((n, r1, r2, y1, y2, w1, w2))
    rows.sort(key=lambda t: -(t[4] if t[4] is not None else -999))
    n1 = sum(t[5] for t in rows); n2 = sum(t[6] for t in rows); nb = sum(t[5] and t[6] for t in rows)
    pos08 = sum(1 for t in rows if t[2] is not None and float(t[2]["2008年pct"]) > 0)
    for n, r1, r2, y1, y2, w1, w2 in rows:
        L.append("| %s | %s%% | %s%% | %s | %s%% | %s%% | %s%% | %s | %s |" % (
            n, f(y1, 2), f(r1["最大回撤pct"] if r1 else None), ("是" if w1 else "否") if r1 else "—",
            f(y2, 2), f(r2["最惨跌pct"] if r2 is not None else None), f(r2["2008年pct"] if r2 is not None else None),
            ("是" if w2 else "否") if r2 is not None else "—", "是" if (w1 and w2) else "否"))
    L.append("\n①= 2015–2025，②= 2005–2014。")
    L.append("\n**数一下**：第一段赢同池的 %d 个；第二段赢同池的 %d 个；两段都赢的 %d 个；2008 年为正的 %d 个。\n" % (n1, n2, nb, pos08))
    d1 = sum(1 for t in rows if t[1] and t[1]["最大回撤pct"] > BENCH["一"][1]); d2 = sum(1 for t in rows if t[2] is not None and float(t[2]["最惨跌pct"]) > BENCH["二"][1])
    db = sum(1 for t in rows if t[1] and t[2] is not None and t[1]["最大回撤pct"] > BENCH["一"][1] and float(t[2]["最惨跌pct"]) > BENCH["二"][1])
    L.append("**另一面也要看**：最惨跌得比同池浅的，第一段 %d 个，第二段 %d 个，两段都浅的 %d 个。也就是说，这些策略多数「赚得没有全买不动多，但跌得没那么深」；它们平均只用了一部分仓位，这两件事是连着的。\n" % (d1, d2, db))
    L.append("⚠ 第二段唯一赢同池的那个（技-10）不可信：它 10 年只做了 135 笔，实际上是「买了基本不卖」，成绩来自拿着不动，不是来自它的买卖规则。\n")
    L.append("## 副指标（每条一行，两段并排）\n")
    L.append("| 策略版本 | ① 笔数 | ① 赚钱的笔 | ① 利润因子 | ① 平均仓位 | ① 赚钱年数 | ② 笔数 | ② 赚钱的笔 | ② 利润因子 | ② 平均仓位 | ② 赚钱年数 | ② 最赚 5 笔占总利润 |")
    L.append("|---|---:|---:|---:|---:|:-:|---:|---:|---:|---:|:-:|---:|")
    for n, r1, r2, y1, y2, w1, w2 in sorted(rows):
        L.append("| %s | %s | %s%% | %s | %s%% | %s | %s | %s%% | %s | %s%% | %s | %s%% |" % (
            n, f(r1["笔数"], 0) if r1 else "—", f(r1["胜率pct"]) if r1 else "—", f(r1["利润因子_按金额"], 2) if r1 else "—",
            f(r1["平均仓位pct"]) if r1 else "—", r1["按年_赚钱的年数"] if r1 else "—",
            f(r2["笔数"], 0) if r2 is not None else "—", f(r2["赚钱的笔pct"]) if r2 is not None else "—",
            f(r2["利润因子"], 2) if r2 is not None else "—", f(r2["平均仓位pct"]) if r2 is not None else "—",
            r2["赚钱的年数"] if r2 is not None else "—", f(r2["最赚5笔占总利润pct"]) if r2 is not None else "—"))
    L.append("\n利润因子 = 赚的钱总额 ÷ 亏的钱总额，大于 1 才是赚的。")
    s = "\n".join(L)
    s = s.replace("有 %d 个每年赚", "有 %d 个每年赚" % n1, 1) if False else s
    s = s.replace("在 2015–2025 这段有 %d 个", "在 2015–2025 这段有 " + str(n1) + " 个").replace("只剩 %d 个", "只剩 " + str(n2) + " 个")
    io.open(os.path.join(ROOT, "手册/339-技术面每条策略-两段时间成绩并排-对内-1120.md"), "w", encoding="utf-8").write(s + "\n")
    print(n1, n2, nb, pos08, len(rows))

main()
