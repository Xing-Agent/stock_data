# -*- coding: utf-8 -*-
"""★ 把 基本面重测结果_2009.json + 可跑率_2009.json + 覆盖率 → 手册里那一页小结的两张机器表(附录用)。"""
import io, json, os, re
HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
r = json.load(io.open(os.path.join(HERE, "基本面重测结果_2009.json"), encoding="utf-8"))
kp = json.load(io.open(os.path.join(HERE, "可跑率_2009.json"), encoding="utf-8")) \
    if os.path.exists(os.path.join(HERE, "可跑率_2009.json")) else {}
单 = {}
for line in io.open(os.path.join(HERE, "覆盖率_单零件_2009.txt"), encoding="utf-8"):
    m = re.match(r"(\S+) \{'算得出pct': ([\d.]+)", line)
    if m:
        单[m.group(1)] = float(m.group(2))
L = ["### 附 A · 每条策略的可跑率(★ 算不出的票日,不是分数差)", "",
     "| 策略 | ★可跑率(全部零件算得出的票日) | 最拖后腿的零件 |", "|---|---:|---|"]
for k, v in kp.items():
    if "★可跑率pct" in v:
        w = min(v["零件"], key=lambda z: 单.get(z, 999))
        L.append(f"| {k} | {v['★可跑率pct']}% | {w}({单.get(w)}%) |")
    else:
        L.append(f"| {k} | ★★★跑失败:{v.get('★★★跑失败', '')[:80]} | |")
L += ["", "### 附 B · 单个零件算得出的比例(大+中口径在场票日)", "", "| 零件 | 算得出 |", "|---|---:|"]
L += [f"| {k} | {v}% |" for k, v in sorted(单.items(), key=lambda x: x[1])]
L += ["", "### 附 C · 33 条臂的事实表(★ 只是方向,不是成绩)", "",
      "| 策略 | 点 | 笔数 | 第一笔进场 | 净值年化%(全收益) | 随机 2.5%~97.5% | 分位 | 持有日中位 | 年换手 |",
      "|---|---|---:|---:|---:|---|---:|---:|---:|"]
for x in r["表"]:
    band = (f"{x['随机2.5%']} ~ {x['随机97.5%']}" if not isinstance(x["落在随机带内?"], str)
            else "★随机无区分")
    L.append(f"| {x['策略']} | {x['点']} | {x['笔数']} | {x['第一笔进场年']} | {x['★净值年化%(全收益)']} | "
             f"{band} | {x['本臂在随机里的分位']} | {x['持有交易日中位']} | {x['年换手率']} |")
io.open(os.path.join(HERE, "小结附录_2009.md"), "w", encoding="utf-8").write("\n".join(L) + "\n")
print("\n".join(L[:20]))
