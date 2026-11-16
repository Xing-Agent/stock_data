#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大师策略手册 · 技术面 14 条 · 每条一页（2026-11-16，按 Lin 认可的海龟样张）

内容一份、出两版：对外版每条一页；对内版同一页后面加「内部附页」。
文字（这是什么 / 怎么做 / 什么时候别用）原样取自《182》对外版，不改写。
成绩单取自 probe/含分红重出_1116/技术面中档_out（流动性池中档、含分红、2015–2025、研发池）。
「一句话结论」是按固定规则数出来的事实句，不是评价。
"""
import csv, glob, io, json, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "手册/182-大师策略手册-对外版-1112.md")
OUT = os.path.join(ROOT, "probe/含分红重出_1116/技术面中档_out")
BENCH = {"ann": 7.28, "dd": -40.3}
SPY = {"ann": 13.44, "dd": -33.7}
RF = 2.0

def 取正文():
    s = io.open(SRC, encoding="utf-8").read()
    a = s.index("## 技术面（14 条）"); b = s.index("## 基本面（23 条）")
    parts = re.split(r"\n(?=### 技-\d+ · )", s[a:b])[1:]
    d = {}
    for p in parts:
        m = re.match(r"### (技-\d+) · (.+)", p)
        key, title = m.group(1), m.group(2).strip()
        def blk(h, stops):
            i = p.find(h)
            if i < 0: return ""
            j = min([x for x in (p.find(st, i + len(h)) for st in stops) if x > 0] or [len(p)])
            return p[i + len(h):j].strip()
        是 = blk("**这是什么**", ["**怎么做**"])
        做 = blk("**怎么做**", ["**有哪几档", "**这条策略测出来"])
        别 = blk("**什么时候别用**", ["\n---"])
        别行 = [l for l in 别.split("\n") if l.strip() and "还没写" not in l]
        d[key] = {"title": title, "是": 是, "做": 做, "别": "\n".join(别行), "别_没写": "还没写" in 别}
    return d

def 版本名(n, key):
    rest = n[len(key):].lstrip("-")
    if n.startswith("trend_following"):
        return "另一份趋势跟随配置（自带大盘闸）" + ("· 原著离场" if "原著" in n else "")
    if not rest: return "默认版"
    rest = rest.replace("原著-", "原著 · ").replace("行业-", "行业 · ")
    return rest + ("版" if rest in ("原著", "行业", "XING") else "")

def 集中度(n):
    import pandas as pd
    fp = os.path.join(ROOT, "probe/含分红重出_1116/技术面中档_ledgers", n + ".csv")
    if not os.path.exists(fp): return None
    d = pd.read_csv(fp)
    tot = float(d["net_pnl"].sum())
    if tot <= 0 or len(d) < 3: return None
    top = d.nlargest(2, "net_pnl")
    days = (pd.to_datetime(top["exit_date"]) - pd.to_datetime(top["entry_date"])).dt.days
    return {"占比": float(top["net_pnl"].sum() / tot), "票": list(top["symbol"].astype(str)), "天": [int(x) for x in days]}

def f(x, suf="%"):
    return "—" if x is None else f"{x}{suf}"

def main():
    正文 = 取正文()
    recs = {os.path.basename(p)[:-5]: json.load(io.open(p, encoding="utf-8")) for p in glob.glob(OUT + "/*.json")}
    池 = {r["name"]: r for r in csv.DictReader(io.open(os.path.join(ROOT, "probe/流动性池_1114/技术面换池_汇总_1114.csv"), encoding="utf-8-sig"))}
    闸 = {}
    for n in ("技-1",):
        g = json.load(io.open(os.path.join(ROOT, "probe/大波段闸四道_1114/out", n + ".json"), encoding="utf-8"))["各版"]
        闸[n] = g
    外, 内 = [], []
    头外 = """# 大师策略手册 · 技术面 14 条（对外版 · 2026-11-16）

> 每条策略一页：它是干什么的、怎么做、我们怎么测的、成绩单、什么时候别用。
> **成绩单怎么读**：同一张表里放了两把尺子 ——「同池子全买不动」（这条策略能买的那堆股票，全买下拿着不动）和「标普 500」。策略要先赢前一把，才说明它的买卖规则有用；再赢后一把，才说明比什么都不做只买标普强。
> **我们怎么测的（每条都一样）**：2015 年到 2025 年，共 11 年，只有这一段；在每天成交 1000 万美元以上的美股里挑票；算上分红；每条策略照自己的规则买卖。换一段时间，结果可能不同。
> 过去的成绩不代表以后。这份手册是研究和教学材料，不是投资建议。

**两把尺子（同一段时间）**

| | 每年赚 | 最惨跌掉 |
|---|---:|---:|
| 同池子全买不动 | 7.3% | −40% |
| 标普 500 | 13.4% | −34% |
| 国库券（及格线） | 2.0% | — |

---
"""
    头内 = 头外.replace("（对外版 · 2026-11-16）", "（对内版 · 2026-11-16）").replace(
        "> 过去的成绩不代表以后。", "> ★ 对内版：每页后面多一张「内部附页」。🔴 附页不发给用户。\n> 过去的成绩不代表以后。") + """
## 内部附页里的词（先看一眼）

| 词 | 大白话 |
|---|---|
| 利润因子 | 所有赚的钱加起来 ÷ 所有亏的钱加起来。大于 1 才是净赚 |
| 平均仓位 | 平均有多少比例的钱买成了股票。10% 就是大部分时间钱闲着 |
| 同等仓位基准 | 按这条策略每天实际买了多少，去买「同池子全买不动」，剩下的钱放国库券。用来分清：成绩差是因为挑得差，还是因为钱大部分时间闲着 |
| 三档门槛 | 池子的成交额门槛分别取 500 万 / 1000 万 / 2000 万美元各测一遍。三档方向一致才算稳 |
| 老池子 | 11-12 之前用的选股范围（成交额排前 2000 名）。只留着对账 |
| 算不出来 | 不是成绩差，是这份配置跑不起来。原因单独写 |

---
"""
    外.append(头外); 内.append(头内)
    for i in range(1, 15):
        key = f"技-{i}"
        t = 正文[key]
        names = sorted([n for n in recs if n == key or n.startswith(key + "-")])
        if key == "技-1":
            names = ["技-1", "trend_following", "trend_following-原著-唐奇安反向通道离场"]
        ok = [n for n in names if "跑失败" not in recs[n]]
        bad = [n for n in names if "跑失败" in recs[n]]
        L = [f"## {key} · {t['title']}", "", f"**一句话**　{t['是']}", "", "**怎么做**", "", t["做"], ""]
        if ok or key in 闸:
            有星 = False
            L += ["**成绩单**（2015–2025，11 年；每天成交 1000 万美元以上的股票；含分红）", "",
                  "| 版本 | 每年赚 | 最惨跌掉 | 赚钱的笔数 | 盈亏比 | 11 年里赚钱的年数 | 一笔一般拿多久 | 一共多少笔 |",
                  "|---|---:|---:|---:|---:|---:|---:|---:|"]
            for n in ok:
                r = recs[n]
                星 = " ※" if (r['复合年化pct'] or -99) > SPY["ann"] else ""
                if 星: 有星 = True
                L.append(f"| {版本名(n, key)}{星} | {f(r['复合年化pct'])} | {f(r['最大回撤pct'])} | {f(r.get('胜率pct'))} | "
                         f"{f(r.get('盈亏比_平均赚除以平均亏'), '')} | {r.get('按年_赚钱的年数', '—')} | {f(r.get('持有天数中位'), ' 天')} | {r['笔数']} |")
            if key in 闸:
                g = 闸[key]["均线200_带斜率_挪0天"]
                L.append(f"| 默认版 + 大盘闸（标普在 200 日线上方才开新仓） | {g['复合年化pct']}% | {g['最大回撤pct']}% | — | — | — | — | {g['笔数']} |")
            L += [f"| *同池子全买不动* | *{BENCH['ann']}%* | *{BENCH['dd']}%* | | | | | |",
                  f"| *标普 500* | *{SPY['ann']}%* | *{SPY['dd']}%* | | | | | |", "",
                  "盈亏比 = 赚钱的那些笔平均赚多少 ÷ 亏钱的那些笔平均亏多少。", ""]
            for n in ok:
                c2 = 集中度(n)
                if c2 and c2["占比"] > 0.5:
                    pct = round(c2["占比"] * 100)
                    两 = f"{c2['票'][0]}、{c2['票'][1]}（分别拿了 {c2['天'][0]} 天和 {c2['天'][1]} 天）"
                    if min(c2["天"]) > 1000:
                        L += [f"⚠️ **{版本名(n, key)}这一行不能当成这条策略的成绩**：利润几乎全部来自 {两} 这两笔，它们买入后好几年一直没卖。这更像是「碰巧买了两只大牛股拿着没动」，不是这条策略的买卖规则在起作用。", ""]
                    elif pct > 100:
                        L += [f"利润集中：{版本名(n, key)}赚得最多的两笔是 {两}，这两笔赚的比整条策略的总利润还多 —— 也就是说，其余所有交易加起来是亏的。", ""]
                    else:
                        L += [f"利润集中：{版本名(n, key)}全部利润的 {pct}% 来自赚得最多的两笔，{两}。少了这两笔，成绩会差很多。", ""]
            if 有星:
                L += ["※ 这一行每年赚高过标普 500。凡是好看的数我们先当自己算错了：这一行还没逐笔核对完，核完之前请不要单独引用。", ""]
            a = sum(1 for n in ok if (recs[n]["复合年化pct"] or -99) > BENCH["ann"])
            b = sum(1 for n in ok if (recs[n]["复合年化pct"] or -99) > SPY["ann"])
            c = sum(1 for n in ok if recs[n]["最大回撤pct"] > SPY["dd"])
            e = sum(1 for n in ok if (recs[n]["复合年化pct"] or -99) > RF)
            L += [f"**数出来的结果**　测了 {len(ok)} 个版本：每年赚得比「同池子全买不动」多的 {a} 个；比标普 500 多的 {b} 个；"
                  f"比国库券多的 {e} 个；最惨跌幅比标普 500 浅的 {c} 个。", ""]
            if key == "技-1":
                L += ["大盘闸那一行要小心用：晚一天看信号，每年赚就从 10.4% 掉到 5.1%，这个改善不稳。", ""]
        else:
            L += ["**成绩单**　这一条这轮没有成绩。", ""]
        if bad:
            for n in bad:
                L.append(f"**算不出来的版本**　{版本名(n, key)}：不是成绩差，是这个版本跑不起来（原因见对内版）。")
            L.append("")
        if not names:
            L += ["**为什么没有成绩**　这条策略还没有写成可以回测的规则文件，这一轮没测。", ""]
        L += ["**什么时候别用**", "", t["别"] or "（还没写）", "", "---", ""]
        外.append("\n".join(L))
        # 内部附页
        N = ["> **内部附页 · " + key + "**（🔴 不发给用户）", ">"]
        if ok:
            N += ["> | 配置文件 | 利润因子 | 平均仓位 | 同等仓位基准 每年赚 | 三档门槛 每年赚（低 / 中 / 高） | 老池子 每年赚 |", "> |---|---:|---:|---:|---|---:|"]
            for n in ok:
                r = recs[n]; p = 池.get(n)
                N.append(f"> | `{n}.yaml` | {f(r.get('利润因子_按金额'), '')} | {r['平均仓位pct']}% | "
                         + (f"{p['mid_same_expo_ann']}% | {p['lo_ann'] or '—'}% / {p['mid_ann'] or '—'}% / {p['hi_ann'] or '—'}% | {p['old_ann'] or '—'}% |" if p else "— | 这份没跑三档 | — |"))
            N.append(">")
        for n in bad:
            N.append(f"> - 算不出来：`{n}.yaml` —— {recs[n]['跑失败'][:160]}")
        旗 = []
        for n in ok:
            r = recs[n]
            if r.get("胜率pct") is not None and r["胜率pct"] < 15:
                旗.append(f"`{n}` 赚钱的笔数只有 {r['胜率pct']}%、盈亏比 {r.get('盈亏比_平均赚除以平均亏')}：成绩靠极少数几笔大赢家，少一两笔结果就会大变，这个数别单独拿出去说。")
            if r["平均仓位pct"] < 15:
                旗.append(f"`{n}` 平均仓位只有 {r['平均仓位pct']}%：钱大部分时间闲着，「每年赚」低主要是这个原因，要对着同等仓位基准看。")
            if (r["复合年化pct"] or -99) > SPY["ann"]:
                旗.append(f"`{n}` 每年赚高过标普 500：按规矩，让我们数字变好看的先当自己错了 —— 还没逐笔核过，核完之前不进对外结论。")
        if key == "技-1":
            旗.append("`技-1.yaml` 和 `技-1-原著-唐奇安反向通道离场.yaml` 除说明文字外完全相同，结果逐位一致，只列一行。")
            旗.append("大盘闸检验（前三道）：技-1 挪 0/1/2 天 3/3 变好、均线五个点 5/5 变好；第四道（留出池）Lin 11-16 定先不跑。")
        if t["别_没写"]:
            旗.append("第 10 格「独立的别用条件」正文还没写；11-14 有 29 条草稿（《189》）等 Lin 过目后并入。")
        if not names:
            旗.append("engine/configs 下没有这条的配置文件。")
        if 旗:
            N += ["> **要知道的**", ">"] + ["> - " + x for x in 旗]
        内.append("\n".join(L[:-2] + N + ["", "---", ""]))
    尾 = """## 还没做完的（老实写）

- 只测了 2015–2025 这一段。换一段时间没测过。
- 基本面 23 条和融合 3 条还没按这个样子出，它们的成绩要按「含分红 + 新对标」重跑。
- 技-7 没有可回测的规则文件；技-9 没有上市日期数据；技-10、技-11、技-13 的原著版各有一处规则引擎还没实现或原著没给数。
- 「什么时候别用」有一部分条目还在草稿，没并进来。
"""
    io.open(os.path.join(ROOT, "手册/301-大师策略手册-技术面14条-对外版-1116.md"), "w", encoding="utf-8").write("\n".join(外) + 尾)
    io.open(os.path.join(ROOT, "手册/302-大师策略手册-技术面14条-对内版-1116.md"), "w", encoding="utf-8").write("\n".join(内) + 尾)
    print("ok", len(外) - 1)

main()
