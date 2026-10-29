"""
原著离场结果 → markdown 表格。2026-10-29。

三秒版:把 results_1029_原著离场.json 里那三个并排的数,和逐链明细,
        吐成报告能直接贴的 markdown。★ 报告里的每个数都从这里出,不手抄。

跑法:python3 -m engine.table_orig_exits_1029 > /tmp/tables.md
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
IN_JSON = os.path.join(HERE, "results_1029_原著离场.json")

SHORT = {
    "技-13 · ★原著四重离场 · Setup 9 进场": "技-13 新·四重离场·Setup9",
    "技-13 · ★原著四重离场 · Countdown 13 进场": "技-13 新·四重离场·CD13",
    "技-13 · 旧实现对照 · Setup 9 进场(只有一条止损)": "技-13 旧·Setup9",
    "技-13 · 旧实现对照 · Countdown 13 进场(只有一条止损)": "技-13 旧·CD13",
    "技-10 · ★原著离场 · 持仓 2 天(严格端)": "技-10 新·2天(严格端)",
    "技-10 · ★原著离场 · 持仓 3 天(中值)": "技-10 新·3天(中值)",
    "技-10 · ★原著离场 · 持仓 5 天(宽松端)": "技-10 新·5天(宽松端)",
    "技-10 · 旧实现对照(离场整条拿掉)": "技-10 旧·无离场",
    "技-8 · ★时间止损 20 日【行业做法】· 回调 20%(严格端)": "技-8 新·20日止损·回调20%",
    "技-8 · ★时间止损 20 日【行业做法】· 回调 25%(宽松端)": "技-8 新·20日止损·回调25%",
    "技-8 · 旧实现对照 · 回调 20%(无时间止损)": "技-8 旧·无时间止损",
    "技-1 · ★原著离场 · System 1(20 日入 / 10 日反向通道出)": "技-1 新·原著 Sys1(20/10)",
    "技-1 · ★原著离场 · System 2(55 日入 / 20 日反向通道出)": "技-1 新·原著 Sys2(55/20)",
    "技-1 · ★★装错的那一版对照:trend_following(吊灯 3ATR + MA50)":
        "技-1 ★装错的·trend_following",
    "技-6 · 原著版 3 日规则(箱底 0 容差)": "技-6 原著·3日规则(本来就对)",
}


def nm(r):
    return SHORT.get(r["报表名"], r["报表名"])


def _pct(x, nd=2):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "算不出"
    if v != v:
        return "算不出"
    return f"{v*100:+.{nd}f}%"


def _f(x, nd=2):
    try:
        v = float(x)
    except (TypeError, ValueError):
        return "—"
    if v != v:
        return "—"
    return f"{v:.{nd}f}"


def dig(x, *ks):
    for k in ks:
        if isinstance(x, dict) and k in x:
            x = x[k]
        else:
            return None
    return x


def main() -> int:
    d = json.load(open(IN_JSON, encoding="utf-8"))
    rows = d["各版结果"]

    print("### 表 1 ★ 三数对照 · 甲组(账户净值口径,绩效窗口总收益,扣摩擦)\n")
    print("| 链 | 新/旧 | 笔数 | ① 买入持有 | ② 过完选股后持有 | ③ 完整链 | ③ 是正还是负 |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        j = r["★★三数对照"]["★甲组_账户净值口径(总收益)"]
        c = j["③完整链(含新离场)"]
        print(f"| {nm(r)} | {'★新' if r['★是不是装上原著离场的那一版'] else '旧'} "
              f"| {r['笔数']} | {_pct(j['①买入持有'])} | {_pct(j['②过完选股后持有'])} "
              f"| **{_pct(c)}** | {'正' if c > 0 else '**负**'} |")

    print("\n### 表 2 ★ 三数对照 · 乙组(每笔收益率口径,★ 不含资金约束,不扣摩擦)\n")
    print("| 链 | 新/旧 | ① 全池每票买入持有 | ② 每个信号买了拿到底 | ③ 完整链每笔 | ②笔数 | ③笔数 |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        y = r["★★三数对照"]["★乙组_每笔收益率口径(不含资金约束)"]
        m = y["明细"]
        print(f"| {nm(r)} | {'★新' if r['★是不是装上原著离场的那一版'] else '旧'} "
              f"| {_pct(y['①买入持有'])} | {_pct(y['②过完选股后持有'])} "
              f"| **{_pct(y['③完整链(含新离场)'])}** "
              f"| {m['②每个进场信号买了拿到底']['笔数']} | {r['笔数']} |")

    print("\n### 表 3 持仓时长:原著意图 vs 实测\n")
    print("| 链 | 新/旧 | 笔数 | 平均持有 | 中位 | 最长 | 出场原因 |")
    print("|---|---|---|---|---|---|---|")
    for r in rows:
        h = r["持仓时长"]
        why = "、".join(f"{k} {v}" for k, v in (h.get("出场原因") or {}).items())
        print(f"| {nm(r)} | {'★新' if r['★是不是装上原著离场的那一版'] else '旧'} "
              f"| {r['笔数']} | **{_f(h.get('平均持有天数'),1)}** "
              f"| {_f(h.get('中位持有天数'),1)} | {h.get('最长持有天数')} | {why} |")

    print("\n### 表 4 集中度 or 胜率(纪律 3:盈利笔数 < 10 就不报集中度,改报胜率)\n")
    print("| 链 | 总笔数 | 盈利笔数 | 胜率 | 按规则报哪个 | 前十笔占总盈利 |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        cw = r["★集中度或胜率"]
        conc = cw.get("集中度")
        cstr = (f"**{_pct(conc.get('前10笔占总盈利比例'))}**" if isinstance(conc, dict)
                else "★ 不报(盈利笔数 < 10)")
        print(f"| {nm(r)} | {cw.get('总笔数')} | **{cw.get('盈利笔数')}** "
              f"| **{_pct(cw.get('胜率'),1)}** | {cw.get('★报哪个')} | {cstr} |")

    print("\n### 表 5 五条基准线(全部为绩效窗口总收益)\n")
    print("| 链 | 完整链 | 基一 同环境随机 | 基二 同等仓位大盘 | 基三 动态开关 "
          "| 基四 槽位机会成本※ | 基五 朴素基准 | 打得过基五吗 |")
    print("|---|---|---|---|---|---|---|---|")
    for r in rows:
        b = r["★基准线套件(基准三四五)"]
        b5 = dig(b, "基准五_朴素基准", "朴素-均值回归版", "朴素基准总收益")
        if b5 is None:
            b5 = dig(b, "基准五_朴素基准", "朴素-趋势版", "朴素基准总收益")
        chain_tr = b.get("链总收益")
        ok = "—" if b5 is None or chain_tr is None else ("是" if chain_tr > b5 else "**否**")
        print(f"| {nm(r)} | {_pct(chain_tr)} "
              f"| {_pct(dig(r,'基准一_同环境随机进场','随机进场_平均总收益'))} "
              f"| {_pct(dig(r,'基准二_同等仓位大盘','基准总收益'))} "
              f"| {_pct(dig(b,'基准三_动态开关基准_同敞口口径','基准总收益'))} "
              f"| {_pct(dig(b,'基准四_槽位机会成本线_替代品甲','基准总收益'))} "
              f"| {_pct(b5)} | {ok} |")
    print("\n※ 基准四原文要求 QQQ,★ 仓库里没有 QQQ 日线 → 跑的是**替代品,不是 QQQ**。"
          "凡引用基准四的数字都要带这句话。")

    print("\n### 表 6 两窗口两池子硬关(四格)\n")
    print("| 链 | 四格过不过 | 降级结论 |")
    print("|---|---|---|")
    for r in rows:
        g = r["★两窗口两池子硬关"]
        print(f"| {nm(r)} | {'过' if g.get('通过') else '**不过**'} "
              f"| {g.get('降级结论') or g.get('理由') or ''} |")

    print("\n### 表 7 ★ 单种子极差 vs 链效应(纪律 8)\n")
    print("| 链 | 随机对照单种子每笔R极差 | 链最大效应(信号均值−随机均值) | 判定 |")
    print("|---|---|---|---|")
    for r in rows:
        s = r["★种子噪声判定"]
        print(f"| {nm(r)} | {_f(s.get('★单种子每笔R的极差'),4)} "
              f"| {_f(s.get('最大效应绝对值'),4)} | {s.get('★判定')} |")

    print("\n### 表 8 该用 R 还是用「每笔收益率 %」(纪律 4)\n")
    print("| 链 | risk/entry 均值 | 比值>0.9 占比 | 该用哪个 | 每笔R净 | 每笔毛收益率 |")
    print("|---|---|---|---|---|---|")
    for r in rows:
        q = r["★R还是百分比"]
        print(f"| {nm(r)} | {_f(q.get('risk_per_share/entry_price_均值'),4)} "
              f"| {_pct(q.get('比值>0.9 的笔数占比'),1)} | {q.get('★该用哪个计量')} "
              f"| {_f(q.get('每笔R净_均值'),4)} | {_pct(q.get('每笔毛收益率_均值'))} |")

    print("\n### 表 9 三套对照组 Z\n")
    print("| 链 | 条件分层随机 | 块重排 | 波动率选择(\\|R\\|) |")
    print("|---|---|---|---|")
    for r in rows:
        z = r["★三套对照组Z"]
        print(f"| {nm(r)} | {_f(z.get('条件分层随机'),3)} "
              f"| {_f(z.get('块重排(Politis&Romano)'),3)} "
              f"| {_f(z.get('波动率选择(|R|)'),3)} |")

    print("\n### 附:★ 原著未给出可执行阈值 / 原著有引擎做不到的项(从配置里直接读出来,不手写)\n")
    print("```json")
    print(json.dumps(d["★原著未给出可执行阈值 / 原著有引擎做不到的项"],
                     ensure_ascii=False, indent=1))
    print("```")

    print("\n### 附:溯源\n")
    print("```json")
    print(json.dumps(d["★溯源"], ensure_ascii=False, indent=1))
    print("```")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
