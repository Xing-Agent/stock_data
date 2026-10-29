"""
pat6_table —— 把 results_1029_技术派六条三版.json 压成报告要的那张总表。

大白话:跑链吐出来的 json 一版有一百多个字段,报告只要 7 列。
这个文件做的就是「挑哪 7 列、怎么读」—— ★ 挑选规则写在代码里,
不是我在报告里手打一遍数字(手打会打错,也没法复现)。

跑法:python3 -m engine.pat6_table
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "results_1029_技术派六条三版.json")


def _z4(rec) -> tuple[str, str]:
    g = rec.get("★两窗口两池子硬关") or {}
    cells = g.get("四格") or []
    zs = [c.get("Z") for c in cells]
    txt = " / ".join("算不出" if z is None else f"{z:+.2f}" for z in zs)
    verdict = "过" if g.get("通过") else "没过"
    return txt, verdict


def _z3(rec) -> str:
    zs = rec.get("★三套对照组Z") or {}
    order = ["条件分层随机", "块重排(Politis&Romano)", "波动率选择(|R|)"]
    out = []
    for k in order:
        v = zs.get(k)
        out.append("算不出" if v is None else f"{v:+.2f}")
    return " / ".join(out)


def _conc(rec) -> str:
    b = rec.get("★基准线套件") or {}
    c = b.get("★链集中度自检") or {}
    v = c.get("前10笔占总盈利比例")
    return f"{v:.1%}" if isinstance(v, (int, float)) else "拿不到"


def _verdict(r: dict) -> str:
    """
    ★ 结论怎么下 —— 规则写在这里,不是我在报告里逐行手写。
    ★ 纪律 6:不许用「样本不足」搪塞一个已经测出没有边际的结论 ——
      所以样本不足也要先看判据的方向,方向明确为负的要说出来。
    """
    n = r["笔数"]
    zs = [v for v in (r.get("★三套对照组Z") or {}).values() if v is not None]
    g = r.get("★两窗口两池子硬关") or {}
    conc = ((r.get("★基准线套件") or {}).get("★链集中度自检") or {}) \
        .get("前10笔占总盈利比例")
    parts = []
    if g.get("通过"):
        parts.append("★ 四格硬关通过")
    else:
        parts.append("四格硬关没过")
    if zs and min(zs) <= -1.65:
        parts.append("★ 测出来是**负边际**(显著差于随机对照)")
    elif zs and max(zs) >= 1.65:
        parts.append("有单关达基础显著,但不足以推翻硬关")
    else:
        parts.append("三套对照组全部不显著 = **测出来没有边际**")
    if n < 150:
        parts.append(f"★ 样本不足(n={n}<150):不代表无效,但方向看左边三列")
    if isinstance(conc, (int, float)):
        if conc > 0.5:
            parts.append(f"★★ 集中度 {conc:.0%} 过半 → 曲线是几笔异常 bar 扛起来的,"
                         f"**这一版的收益数字不可用**")
        elif conc <= 0.25:
            parts.append(f"集中度 {conc:.0%}(一两成以内)→ 是铺得开的效应,"
                         f"收益数字可用")
        else:
            parts.append(f"集中度 {conc:.0%}(两三成)→ 偏集中,收益数字要打折看")
    return ";".join(parts)


def rows() -> list[dict]:
    d = json.load(open(SRC, encoding="utf-8"))
    out = []
    for r in d["各版结果"]:
        z4, v4 = _z4(r)
        abs_ = r.get("绝对表现") or {}
        b1 = r.get("基准一_同环境随机进场") or {}
        diff1 = None
        for k, v in b1.items():
            if "每笔R − 随机进场每笔R" in str(k):
                diff1 = v
        out.append({
            "报表名": r["报表名"],
            "三版归属": r["★三版归属"],
            "笔数": r["笔数"],
            "每笔R净": r.get("每笔R净"),
            "胜率": r.get("胜率"),
            "净收益": abs_.get("净收益(扣摩擦)"),
            "最大回撤": (r.get("★基准线套件") or {}).get("链最大回撤"),
            "卡玛比率": (r.get("★基准线套件") or {}).get("链卡玛比率"),
            "四格Z": z4,
            "硬关": v4,
            "三套对照组Z": _z3(r),
            "集中度_前10笔占总盈利": _conc(r),
            "基准一差值_每笔R": diff1,
            "样本量警示": r.get("样本量警示"),
            "结论": _verdict(r),
        })
    return out


def main() -> int:
    rs = rows()
    hdr = ["报表名", "三版归属", "笔数", "每笔R净", "胜率", "净收益", "最大回撤",
           "卡玛比率", "三套对照组Z", "四格Z", "集中度_前10笔占总盈利",
           "基准一差值_每笔R", "结论"]
    print("| " + " | ".join(hdr) + " |")
    print("|" + "|".join(["---"] * len(hdr)) + "|")
    for r in rs:
        cells = []
        for h in hdr:
            v = r.get(h)
            if isinstance(v, float):
                v = f"{v:+.4f}"
            cells.append("拿不到" if v is None else str(v))
        print("| " + " | ".join(cells) + " |")
    print()
    print(json.dumps({"n": len(rs)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
