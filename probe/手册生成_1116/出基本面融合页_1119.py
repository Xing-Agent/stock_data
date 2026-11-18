#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""大师策略手册 · 基本面 23 条 + 融合 3 条 · 每条一页（2026-11-19，和技术面 14 条同一个样子）

文字（这是什么 / 怎么做 / 什么时候别用）原样取自《182》对外版。
成绩单取自 probe/含分红重出_1116/基本面融合_out_按表折算（按数据组全池并股表折算后的重跑；研发池 large_mid 口径；含分红；2015–2025）。
「数出来的结果」是按固定规则数的事实句，不是评价。
Lin 1114/1118：基-3「它是过滤器，不是发现器」挪进「怎么用」；基-8「会在熊市里让你空仓」挪进「代价」。
"""
import glob, io, json, os, re
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC = os.path.join(ROOT, "手册/182-大师策略手册-对外版-1112.md")
D = os.path.join(ROOT, "probe/含分红重出_1116")
OUT = os.path.join(D, "基本面融合_out_按表折算")
BM = json.load(io.open(os.path.join(D, "基本面主对标_1119.json"), encoding="utf-8"))
BENCH = {"ann": BM["复合年化pct"], "dd": BM["最大回撤pct"]}
SPY = {"ann": 13.44, "dd": -33.7}; RF = 2.0

def 取正文():
    s = io.open(SRC, encoding="utf-8").read()
    a = s.index("## 基本面（23 条）"); b = s.index("## 还没解决的")
    d = {}
    for p in re.split(r"\n(?=### (?:基|融)-\d+ · )", s[a:b])[1:]:
        m = re.match(r"### ((?:基|融)-\d+) · (.+)", p); key, title = m.group(1), m.group(2).strip()
        def blk(h, stops):
            i = p.find(h)
            if i < 0: return ""
            j = min([x for x in (p.find(st, i + len(h)) for st in stops) if x > 0] or [len(p)])
            return p[i + len(h):j].strip()
        别 = [l for l in blk("**什么时候别用**", ["\n---", "\n## "]).split("\n") if l.strip() and "还没写" not in l and not l.strip().endswith("：—")]
        做 = [l for l in blk("**怎么做**", ["**有哪几档", "**这条策略测出来"]).split("\n") if l.strip() and not l.strip().endswith("：—")]
        d[key] = {"title": title, "是": blk("**这是什么**", ["**怎么做**"]), "做": 做, "别": 别}
    return d

def 集中度(n):
    import pandas as pd
    fp = os.path.join(D, "基本面融合_ledgers_按表折算", n + ".csv")
    if not os.path.exists(fp): return None
    x = pd.read_csv(fp); tot = float(x["net_pnl"].sum())
    if tot <= 0 or len(x) < 6: return None
    top = x.nlargest(5, "net_pnl")
    没卖 = int((pd.to_datetime(top["exit_date"]) >= pd.Timestamp("2025-12-30")).sum())
    return {"占比": float(top["net_pnl"].sum() / tot), "票": list(top["symbol"].astype(str))[:3], "没卖": 没卖}

f = lambda x, suf="%": "—" if x is None else f"{x}{suf}"

def main():
    正文 = 取正文()
    recs = {os.path.basename(p)[:-5]: json.load(io.open(p, encoding="utf-8")) for p in glob.glob(OUT + "/*.json")}
    头 = f"""# 大师策略手册 · 基本面 23 条 + 融合 3 条（对外版 · 2026-11-19）

> 每条策略一页：它是干什么的、怎么做、成绩单、什么时候别用。样子和技术面 14 条那份一样。
> **成绩单怎么读**：同一张表里放两把尺子 ——「同范围全买不动」（这条策略能买的那堆股票，全买下拿着不动）和「标普 500」。
> **我们怎么测的（每条都一样）**：2015 年到 2025 年，共 11 年，只有这一段；在成交额排前 2000 名的美股里挑；算上分红；每条策略照自己的规则买卖。换一段时间，结果可能不同。
> **这 11 年的大背景**：科技大股票主导的强势行情。成绩单说的是「这 11 年里的表现」，不是「这条策略永远如此」。
> **这 26 条里，这一轮测出成绩的是 14 条**（基本面 11 条、融合 3 条）。其余 12 条还没有写成可以回测的规则，页面上会写明。
> 过去的成绩不代表以后。这份手册是研究和教学材料，不是投资建议。

**两把尺子（同一段时间）**

| | 每年赚 | 最惨跌掉 |
|---|---:|---:|
| 同范围全买不动 | {BENCH['ann']}% | {BENCH['dd']}% |
| 同上，只算 5 美元以上的票 | 9.5% | −40.3% |
| 标普 500 | {SPY['ann']}% | {SPY['dd']}% |
| 国库券（及格线） | {RF}% | — |

「同范围全买不动」这把尺子有一处要知道：每年 {BENCH['ann']}% 里，大约 4 个百分点来自股价 5 美元以下的那一百多只票。这类票涨跌极端、实际很难按这个价买到，所以把「只算 5 美元以上」的也并排列出来。

---
"""
    页 = [头]; 有成绩 = 0
    keys = [f"基-{i}" for i in range(1, 24)] + [f"融-{i}" for i in range(1, 4)]
    for key in keys:
        t = 正文[key]
        names = sorted(n for n in recs if n.startswith(key + "_") or n.startswith(key + "-"))
        ok = [n for n in names if "跑失败" not in recs[n]]
        bad = [n for n in names if "跑失败" in recs[n] and not any(o.startswith(key + "_") for o in ok)]
        做 = list(t["做"])
        if key == "基-3":
            做.append("- 怎么用：它是过滤器，不是发现器。别拿它当选股主力，把它加在别的低估值策略后面，用来筛掉「便宜但在变差」的公司。")
            t["别"] = [l for l in t["别"] if "过滤器" not in l]
        if key == "基-8":
            t["别"] = [l for l in t["别"] if "熊市里让你空仓" not in l]
        L = [f"## {key} · {t['title']}", "", f"**一句话**　{t['是']}", ""]
        if 做: L += ["**怎么做**", ""] + 做 + [""]
        if ok:
            有成绩 += 1
            L += ["**成绩单**（2015–2025，11 年；成交额排前 2000 名的股票；含分红）", "",
                  "| 版本 | 每年赚 | 最惨跌掉 | 赚钱的笔数 | 盈亏比 | 11 年里赚钱的年数 | 一笔一般拿多久 | 一共多少笔 |", "|---|---:|---:|---:|---:|---:|---:|---:|"]
            有星 = False
            for n in ok:
                r = recs[n]; 星 = " ※" if (r["复合年化pct"] or -99) > SPY["ann"] else ""; 有星 = 有星 or bool(星)
                L.append(f"| {n.split('_', 1)[-1]}{星} | {f(r['复合年化pct'])} | {f(r['最大回撤pct'])} | {f(r.get('胜率pct'))} | {f(r.get('盈亏比_平均赚除以平均亏'), '')} | {r.get('按年_赚钱的年数', '—')} | {f(r.get('持有天数中位'), ' 天')} | {r['笔数']} |")
            L += [f"| *同范围全买不动* | *{BENCH['ann']}%* | *{BENCH['dd']}%* | | | | | |", f"| *标普 500* | *{SPY['ann']}%* | *{SPY['dd']}%* | | | | | |", "",
                  "盈亏比 = 赚钱的那些笔平均赚多少 ÷ 亏钱的那些笔平均亏多少。", ""]
            for n in ok:
                r = recs[n]; c = 集中度(n)
                if c and c["占比"] > 0.5:
                    pct = round(c["占比"] * 100)
                    句 = (f"利润集中：赚得最多的 5 笔赚的比整条策略的总利润还多（{'、'.join(c['票'])} 等），也就是说其余所有交易加起来是亏的。" if pct > 100
                          else f"利润集中：全部利润的 {pct}% 来自赚得最多的 5 笔（{'、'.join(c['票'])} 等）。少了这几笔，成绩会差很多。")
                    if c["没卖"] >= 3: 句 += f"其中 {c['没卖']} 笔买入后一直拿到测试结束都没卖。"
                    L += [句, ""]
                if r["平均仓位pct"] < 30:
                    L += [f"钱大部分时间闲着：这条策略平均只有 {r['平均仓位pct']}% 的钱买成了股票，「每年赚」低主要是这个原因。", ""]
            if key == "基-8":
                L += ["**代价**　这套方法会在熊市里让你空仓。想在熊市里抄底的人用它会很难受。", ""]
            if 有星:
                L += ["※ 这一行每年赚高过标普 500。凡是好看的数我们先当自己算错了：这一行还没逐笔核对完，核完之前请不要单独引用。", ""]
            a = sum((recs[n]["复合年化pct"] or -99) > BENCH["ann"] for n in ok); b = sum((recs[n]["复合年化pct"] or -99) > SPY["ann"] for n in ok)
            e = sum((recs[n]["复合年化pct"] or -99) > RF for n in ok); c2 = sum(recs[n]["最大回撤pct"] > SPY["dd"] for n in ok)
            L += [f"**数出来的结果**　测了 {len(ok)} 个版本：每年赚得比「同范围全买不动」多的 {a} 个；比标普 500 多的 {b} 个；比国库券多的 {e} 个；最惨跌幅比标普 500 浅的 {c2} 个。", ""]
        else:
            L += ["**成绩单**　这一条这轮没有成绩：" + ("规则已经写了，但有一条规则引擎还跑不了。" if bad else "还没有写成可以回测的规则文件。"), ""]
        for n in bad:
            if ok: L += [f"**算不出来的版本**　{n}：不是成绩差，是这个版本跑不起来。", ""]
        L += ["**什么时候别用**", ""] + (t["别"] or ["（还没写）"]) + ["", "---", ""]
        页.append("\n".join(L))
    尾 = """## 要一起知道的（老实写）

- 只测了 2015–2025 这一段。换一段时间没测过。
- 这批成绩是 11-18 按数据组核过的并股表折算后重跑的。折算前有两条成绩虚高（早期巴菲特 17.99%、施洛斯 16.95%），已作废。
- 为了避开查不清的数据，拿掉了 44 只票，其中有破产后换新股的。它们最后归零的亏损也一起拿掉了，对「买便宜货」这类策略是偏好看的方向。
- 仍有 16 笔交易的持仓期里出现过单日涨到 3 倍以上或跌到三分之一以下。数据组核对后判为真实行情，我们没有独立再核。
- 融合 3 条名字叫「融合」，实际只有技术规则，没有基本面筛选。
- 「什么时候别用」有一部分条目还在草稿，没并进来。
"""
    io.open(os.path.join(ROOT, "手册/316-大师策略手册-基本面23条与融合3条-对外版-1119.md"), "w", encoding="utf-8").write("\n".join(页) + 尾)
    print("ok 页数", len(页) - 1, "有成绩", 有成绩)
main()
