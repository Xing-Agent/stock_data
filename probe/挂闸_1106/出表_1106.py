# -*- coding: utf-8 -*-
"""★ 把 挂闸对照表_1106.json 渲染成 markdown 表格(★★★ 数字一律从 json 来,不手打)。"""
from __future__ import annotations
import io, json, os

HERE = os.path.dirname(os.path.abspath(__file__))
J = os.path.join(HERE, "挂闸对照表_1106.json")
版本序 = ["不挂闸", "挂闸100日", "挂闸200日", "挂闸300日"]
族序 = ["突破", "大波段", "震荡"]
族名 = {"突破": "突破 · 技-6-原著(达瓦斯箱体)",
       "大波段": "大波段 · 技-1(海龟 System 1)",
       "震荡": "震荡 · 技-14-原著(布林带均值回归)"}


def f(x, n=4):
    if x is None:
        return "★算不出"
    try:
        return f"{float(x):+.{n}f}"
    except Exception:
        return str(x)


def money(x):
    if x is None:
        return "★算不出"
    return f"{float(x):+,.0f}"


def main() -> int:
    d = json.load(io.open(J, encoding="utf-8"))
    out = []
    for 族 in 族序:
        c = d["对照"][族]
        out.append(f"\n### {族名[族]}\n")
        out.append("| 版本 | ①笔数 | ②每笔净R | ③每笔毛R | ④摩擦总额(美元) | ④b毛盈亏(美元) | ⑤基准一 | ⑥每笔净R的SE |")
        out.append("|---|---|---|---|---|---|---|---|")
        for 版 in 版本序:
            r = c["四版六数"][版]
            if "★算不出" in r:
                out.append(f"| {版} | ★算不出 | ★算不出 | ★算不出 | ★算不出 | ★算不出 | ★算不出 | ★算不出 |")
                continue
            out.append(f"| {版} | {r['①笔数']:,} | {f(r['②每笔净R'])} | {f(r['③每笔毛R'])} "
                       f"| {money(r['④摩擦总额美元'])} | {money(r['④b毛盈亏美元'])} "
                       f"| {f(r['⑤基准一'])} | {f(r['⑥每笔净R的SE'])} |")
        out.append("")
        out.append("| 对照(挂闸 − 不挂闸) | 改善幅度 | 尺子 2×√(SE²+SE²) | 判定 | 笔数降幅 |")
        out.append("|---|---|---|---|---|")
        b = c["四版六数"]["不挂闸"]
        for 版 in 版本序[1:]:
            j = c["挂闸 vs 不挂闸"].get(版, {})
            a = c["四版六数"][版]
            降 = "★算不出"
            if "★算不出" not in a and "★算不出" not in b and b.get("①笔数"):
                降 = f"−{(1 - a['①笔数'] / b['①笔数']) * 100:.1f}%"
            if "改善幅度" not in j:
                out.append(f"| {版} | ★算不出 | ★算不出 | {j.get('★算不出','★算不出')} | {降} |")
            else:
                out.append(f"| {版} | {f(j['改善幅度'])} | {f(j.get('尺子'))} "
                           f"| {j.get('判定', j.get('★算不出尺子','★算不出'))} | {降} |")
        out.append("")
    out.append("\n### ★★★ 排序型预言的分辨力\n")
    for 版, s in d["排序型预言的分辨力"].items():
        out.append(f"**{版}**")
        if "★算不出" in s:
            out.append(f"- ★算不出:{s['★算不出']}")
            out.append("")
            continue
        out.append(f"- 改善幅度:" + "、".join(f"{k} {f(v)}" for k, v in s["幅度"].items()))
        for k, v in s["两两分辨力"].items():
            out.append(f"- {k}:幅度差 {v['幅度差']:.4f} vs 合成标准误 {v['合成标准误']:.4f} → "
                       + ("★ 分得开" if v["分得开"] else "★★★ 分不开"))
        out.append(f"- **{s['★★★ 结论']}**")
        out.append("")
    txt = "\n".join(out)
    io.open(os.path.join(HERE, "表_1106.md"), "w", encoding="utf-8").write(txt)
    print(txt)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
