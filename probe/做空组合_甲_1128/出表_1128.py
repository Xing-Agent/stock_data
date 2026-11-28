# -*- coding: utf-8 -*-
"""从汇总 json 直接出报告里的表（不手抄）。"""
import json, os, sys
HERE = os.path.dirname(os.path.abspath(__file__)); OUT = os.path.join(HERE, "out")
def f(x, n=2): return "—" if x is None else (f"{x:+.{n}f}" if isinstance(x, float) else str(x))
def 表(tag, nm="默认"):
    r = json.load(open(os.path.join(OUT, f"{tag}_汇总.json"), encoding="utf-8"))[nm]
    L = ["| 一步一步加 | 笔数 | 每笔(倍风险) | 每笔% | 赚钱笔 | 最深亏损(倍风险) | 最差一笔% | 扣掉大盘后每笔% | 随机进场每笔（中位，5%~95%） | 我们排第几分位 |", "|---|---|---|---|---|---|---|---|---|---|",
         f"| ① 大势向下 | 可进 {r['①大势向下可进的根数']:,} 根 | 这一步就是随机对照本身 | | | | | | | |"]
    for k, v in r.items():
        if not isinstance(v, dict) or "笔" not in v: continue
        rc = v.get("随机对照", {}); 少 = "（样本不够）" if v["笔"] < 30 else ""
        if v["笔"] == 0: L.append(f"| {k} | 0 | — | — | — | — | — | — | — | — |"); continue
        L.append(f"| {k} | {v['笔']}{少} | {f(v['每笔R'])} | {f(v.get('每笔%'))} | {int(round(v['赚钱占比']*100))}% | {f(v['最深亏损R'],1)} | {f(v.get('最差一笔%'),1)} | {f(v.get('扣掉大盘后每笔%'))} | "
                 f"{f(rc.get('随机每笔R中位'))}（{f(rc['5%~95%'][0])} ~ {f(rc['5%~95%'][1])}） | {rc.get('我们排在第几分位','—')} |" if rc else f"| {k} | {v['笔']}{少} | {f(v['每笔R'])} | | | | | | | |")
    return "\n".join(L)
def 档(tag):
    o = json.load(open(os.path.join(OUT, f"{tag}_汇总.json"), encoding="utf-8")); 步 = ["② +顶部形态", "③ +背离", "④ +跌破颈线", "⑤ +无量弱反抽", "⑥ +下面1.5R无支撑"]
    L = ["| 写法 | " + " | ".join(步) + " |", "|---" * 6 + "|"]
    for nm, r in o.items(): L.append(f"| {nm} | " + " | ".join(f"{r[s]['笔']} 笔 / {f(r[s].get('每笔R'))}" for s in 步) + " |")
    return "\n".join(L)
if __name__ == "__main__":
    for tag in sys.argv[1:]:
        print(f"\n### {tag} 默认\n" + 表(tag)); print(f"\n### {tag} 量法乙\n" + 表(tag, "量法乙")); print(f"\n### {tag} 相邻档\n" + 档(tag))
