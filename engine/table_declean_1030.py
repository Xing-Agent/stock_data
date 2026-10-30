"""
剔污染重跑的结果 → markdown 表格 · 2026-10-30。

★ 报告里每个数都从这里出,**不手抄**。
跑法:python3 -m engine.table_declean_1030 > /tmp/t.md
"""

from __future__ import annotations

import json
import os

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(HERE, "results_1030_剔污染.json")

D = "污染版(现状全池)"
C = "剔除版(整只票剔除)"

#: ★ 剔除后「塌掉」的判定线:净收益剩下不到一半,或者由正翻负。
COLLAPSE_FRAC = 0.5


def _pct(x, nd=2):
    if x is None:
        return "—"
    try:
        return f"{float(x):+.{nd}%}"
    except (TypeError, ValueError):
        return "—"


def _short(label: str) -> str:
    return (label.replace(" · ", "·").replace("(", "(").replace(")", ")")
            .replace("★", ""))


def load() -> dict:
    with open(SRC, encoding="utf-8") as fh:
        return json.load(fh)


#: ★ 噪音带:两版的净收益都落在 ±5% 以内时,「塌了 / 没塌」这句话本身没有意义。
#:   出处不是挑出来的阈值 —— 上一轮实测的单种子极差就已经比这个量级大
#:   (见表 6「Z 的符号是噪声」那一列)。
NOISE_BAND = 0.05


def _verdict(a: dict, b: dict) -> str:
    """★ 这条链的结论是被污染撑着的,还是不依赖污染?"""
    ra, rb = a["净收益(扣摩擦)"], b["净收益(扣摩擦)"]
    if a["笔数"] == 0 and b["笔数"] == 0:
        return "没有成交"
    noise = abs(ra) < NOISE_BAND and abs(rb) < NOISE_BAND
    head = "【★ 两版都在 ±5% 噪音量级,下面这句只作方向参考】" if noise else ""
    return head + _verdict_body(ra, rb)


def _verdict_body(ra: float, rb: float) -> str:
    if ra > 0 and rb <= 0:
        return "★★ 被污染撑着(正收益剔除后翻负)"
    if ra > 0 and rb < ra * COLLAPSE_FRAC:
        return "★★ 被污染撑着(剔除后只剩不到一半)"
    if ra <= 0 and rb > 0:
        return "★ 反向:污染是在**压低**它(剔除后由负翻正)"
    if abs(rb - ra) <= abs(ra) * 0.25 or abs(rb - ra) < 0.05:
        return "★ 不依赖污染(剔除后基本不变)"
    if rb > ra:
        return "★ 剔除后变好(污染在压低它)"
    return "剔除后变差,但没塌"


def table_main(d: dict) -> str:
    L = ["### ★★ 表 1 逐链两列对照(净收益,绩效窗口)", "",
         "| 链 | 笔数 污染版 → 剔除版 | **净收益 污染版** | **净收益 剔除版** | 差值 | 剩余比例 | 污染票占本链总盈利 | ★ 判定 |",
         "|---|---|---|---|---|---|---|---|"]
    for row in d["各链两版"]:
        a, b = row["两版"].get(D), row["两版"].get(C)
        if not (a and b):
            L.append(f"| {_short(row['报表名'])} | 跑挂了 | — | — | — | — | — | — |")
            continue
        diff = row["★差值"]
        frac = diff.get("★净收益剩余比例")
        # ★ 污染版净收益 ≤ 0 时「剩下几成」没有意义(负数除负数会变成好看的倍数)
        if not (isinstance(frac, (int, float)) and a["净收益(扣摩擦)"] > 0
                and b["净收益(扣摩擦)"] > 0):
            frac = None
        note = ("★ 污染版本来就 ≤0,不报" if a["净收益(扣摩擦)"] <= 0
                else "★ 剔除后翻负,比不了")
        share = (a.get("★污染归属") or {}).get("污染票占全链总盈利(只数正的)")
        L.append(
            f"| {_short(row['报表名'])} | {a['笔数']} → {b['笔数']} | "
            f"**{_pct(a['净收益(扣摩擦)'])}** | **{_pct(b['净收益(扣摩擦)'])}** | "
            f"{_pct(diff['净收益_剔除−污染'])} | "
            f"{(f'{frac:.2f}×' if isinstance(frac, (int, float)) else note)} | "
            f"{_pct(share, 1)} | {_verdict(a, b)} |")
    return "\n".join(L)


def table_per_trade(d: dict) -> str:
    L = ["### 表 2 每笔收益率口径(不含资金约束的横截面)", "",
         "| 链 | 平均每笔 污染版 | 平均每笔 剔除版 | 差值 | 污染票平均每笔 | 干净票平均每笔 | 污染票笔数占比 |",
         "|---|---|---|---|---|---|---|"]
    for row in d["各链两版"]:
        a, b = row["两版"].get(D), row["两版"].get(C)
        if not (a and b):
            continue
        at = a.get("★污染归属") or {}
        L.append(
            f"| {_short(row['报表名'])} | {_pct(a['平均每笔毛收益率'], 3)} | "
            f"{_pct(b['平均每笔毛收益率'], 3)} | "
            f"{_pct(row['★差值']['每笔_剔除−污染'], 3)} | "
            f"{_pct(at.get('污染票平均每笔毛收益率'), 2)} | "
            f"{_pct(at.get('干净票平均每笔毛收益率'), 3)} | "
            f"{_pct(at.get('污染票笔数占比'), 1)} |")
    return "\n".join(L)


def table_conc(d: dict) -> str:
    L = ["### 表 3 集中度 / 胜率(★ 盈利笔数 < 10 不报集中度,改报胜率)", "",
         "| 链 | 池子 | 总笔数 | 盈利笔数 | 报哪个 | 值 |",
         "|---|---|---|---|---|---|"]
    for row in d["各链两版"]:
        for pool in (D, C):
            v = row["两版"].get(pool)
            if not v:
                continue
            c = v["★集中度或胜率"]
            if c.get("★报哪个") == "集中度":
                val = _pct((c.get("集中度") or {}).get("前10笔占总盈利比例"), 2)
                which = "集中度(前10笔占总盈利)"
            elif c.get("★报哪个") == "胜率":
                val = _pct(c.get("胜率"), 1)
                which = f"★ 胜率(盈利笔数 {c.get('盈利笔数')} < 10)"
            else:
                val, which = "—", c.get("口径", "—")
            L.append(f"| {_short(row['报表名'])} | "
                     f"{'污染版' if pool == D else '剔除版'} | "
                     f"{c.get('总笔数', 0)} | {c.get('盈利笔数', 0)} | "
                     f"{which} | {val} |")
    return "\n".join(L)


def table_r(d: dict) -> str:
    L = ["### 表 4 R 还是「每笔收益率 %」(★ 双侧判定)", "",
         "| 链 | 池子 | risk/entry 中位 | 最小 | 最大 | >0.9 占比 | <0.01 占比 | ★ 该用哪个 |",
         "|---|---|---|---|---|---|---|---|"]
    for row in d["各链两版"]:
        for pool in (D, C):
            v = row["两版"].get(pool)
            if not v:
                continue
            r = v["★R还是百分比(双侧)"]
            forced = "(★ 强制 %)" if r.get("★强制用%") else ""
            # ★★ 判定在这一层按**严格双侧**重算(事实在 JSON、判定在报表层):
            #   只要有一笔 risk/entry > 0.9 或 < 0.01,平均每笔 R 就不可信。
            hi = r.get("比值>0.9 的笔数占比") or 0.0
            lo = r.get("比值<0.01 的笔数占比") or 0.0
            strict_pct = bool(forced) or hi > 0.0 or lo > 0.0
            r = dict(r, **{"★该用哪个计量": (
                "★ 每笔收益率 %(R 在这条链上无意义)" if strict_pct else "每笔 R")})
            L.append(f"| {_short(row['报表名'])} | "
                     f"{'污染版' if pool == D else '剔除版'} | "
                     f"{r.get('risk/entry_中位数', '—')} | "
                     f"{r.get('risk/entry_最小', '—')} | "
                     f"{r.get('risk/entry_最大', '—')} | "
                     f"{_pct(r.get('比值>0.9 的笔数占比'), 1)} | "
                     f"{_pct(r.get('比值<0.01 的笔数占比'), 1)} | "
                     f"{r.get('★该用哪个计量', '—')}{forced} |")
    return "\n".join(L)


def table_naive(d: dict) -> str:
    # ★ 朴素基准只跟「槽位 + 摩擦」有关,和被比的链本身无关 ——
    #   所以同样的槽位/摩擦会给出一模一样的数。这里按数去重,免得一张表抄 36 遍。
    seen: dict = {}
    L = ["### ★★ 表 5 基准五 朴素基准(两版并排)", "",
         "★ 朴素基准的槽位数和摩擦是从被比的链抄过来的,所以槽位一样的链共用同一个数;"
         "下表已按数去重,末列列出用这一档的链。", "",
         "| 版本 | 槽位 | 污染版总收益 | 剔除版总收益 | 差值 | 污染版集中度 | 剔除版集中度 | 哪些链用这一档 |",
         "|---|---|---|---|---|---|---|---|"]
    for row in d["各链两版"]:
        a, b = row["两版"].get(D), row["两版"].get(C)
        if not (a and b):
            continue
        na, nb = a.get("★基准五_朴素基准"), b.get("★基准五_朴素基准")
        if not isinstance(na, dict) or not isinstance(nb, dict):
            continue
        for kind in na:
            x, y = na[kind], nb.get(kind) or {}
            key = (kind, round(x.get("朴素基准总收益") or 0, 6),
                   round(y.get("朴素基准总收益") or 0, 6))
            if key in seen:
                seen[key]["链"].append(_short(row["报表名"]))
                continue
            seen[key] = {
                "链": [_short(row["报表名"])],
                "行": (f"| {kind} | {x.get('槽位约束')} | "
                       f"{_pct(x.get('朴素基准总收益'))} | "
                       f"{_pct(y.get('朴素基准总收益'))} | "
                       f"{_pct((y.get('朴素基准总收益') or 0) - (x.get('朴素基准总收益') or 0))} | "
                       f"{_pct((x.get('★集中度自检') or {}).get('前10笔占总盈利比例'), 1)} | "
                       f"{_pct((y.get('★集中度自检') or {}).get('前10笔占总盈利比例'), 1)} |"),
            }
    for v in seen.values():
        chains = v["链"]
        who = (f"{len(chains)} 条链共用" if len(chains) > 3
               else " / ".join(chains))
        L.append(f"{v['行']} {who} |")
    return "\n".join(L)


def table_seed(d: dict) -> str:
    L = ["### 表 6 单种子极差 vs 链效应(★ 纪律 7:强制打印)", "",
         "| 链 | 池子 | 单种子极差 | 最大效应 | ★ 判定 |",
         "|---|---|---|---|---|"]
    for row in d["各链两版"]:
        for pool in (D, C):
            v = row["两版"].get(pool)
            if not v:
                continue
            s = v["★种子噪声判定"]
            sp, me = s.get("★单种子每笔R的极差"), s.get("最大效应绝对值")
            # ★ 直接比数,不去字符串里找「噪声」两个字 ——
            #   反面那句判定里也有「不是单纯的种子噪声」,匹配字符串会把它也判成噪声。
            if isinstance(sp, (int, float)) and isinstance(me, (int, float)):
                noise = ("★★ Z 的符号是噪声(极差 > 效应)" if sp > me
                         else "极差 ≤ 效应(★ 仍不等于结论成立)")
            else:
                noise = "算不出"
            L.append(f"| {_short(row['报表名'])} | "
                     f"{'污染版' if pool == D else '剔除版'} | "
                     f"{sp if sp is None else f'{sp:+.4g}'}R | "
                     f"{me if me is None else f'{me:.4g}'}R | {noise} |")
    return "\n".join(L)


def main() -> int:
    d = load()
    print(table_main(d), "\n")
    print(table_per_trade(d), "\n")
    print(table_conc(d), "\n")
    print(table_r(d), "\n")
    print(table_naive(d), "\n")
    print(table_seed(d), "\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
