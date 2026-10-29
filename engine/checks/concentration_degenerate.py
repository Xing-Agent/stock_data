"""
★★ 二 · 集中度退化检测 —— 「前十笔占总盈利 100%」不一定是坏消息,
    也可能是**盈利笔数不足 10 笔**,前十笔按定义就是全部。

三秒版:集中度这个指标只有在盈利笔数够多的时候才读得出东西。
        盈利笔只有 9 笔,「前十笔占 100%」是一句同义反复,不是一个发现。

为什么要有这个文件(2026-10-29 晚实测):
    技-13 TD 序列:223 笔交易,★ 只有 9 笔是赚的 → 前十笔占总盈利 100.0%
    技-10 海龟汤:123 笔交易,★ 只有 12 笔是赚的 → 前十笔占总盈利 99.79%
    技-8  HTF   :26 笔交易,★ 只有 9 笔是赚的  → 前十笔占总盈利 100.0%
  ★ 当时这三个 100% 被读成了「曲线是几笔异常 bar 扛起来的」——
    ★★ 而真相是「盈利笔数不足 10 笔,这个指标在这个样本上退化了」。
    两种读法会导出完全相反的行动:前者是「这一版不可用」,
    后者是「这一版样本太薄,集中度这一列根本不该出现在表里」。

★ 规则(策略组拍的):盈利笔数 < 10 → ★ 不输出集中度,改输出胜率,
  并标注「集中度在此样本上退化,不可读」。
★ 两侧读法都必须打印:过半 → 曲线是几笔扛起来的,数字不可用;
  一两成以内 → 铺得开,可用。

★ 本文件只读流水,不改任何跑批逻辑。
"""

from __future__ import annotations

import csv
import glob
import os
from typing import Sequence

# ────────────────────────────────────────────────────────────────────────
# 阈值 —— 出处写明
# ────────────────────────────────────────────────────────────────────────

#: 前 N 笔。N=10 是现行报表的口径(「前10笔占总盈利比例」)。
TOP_N = 10

#: 盈利笔数低于这个数 → 集中度退化,★ 不输出数。
#  出处:策略组 2026-10-29 原话「如果盈利笔数 < 10,不输出集中度」。
#  为什么正好是 10:前 N 笔里的 N 就是 10 —— 盈利笔 < 10 时
#  「前十笔」在集合意义上**等于全部盈利笔**,比例恒等于 100%,不含任何信息。
MIN_WIN_TRADES = TOP_N

#: 两侧读法的分界。出处:pat6_table._verdict 现行口径(> 0.5 / ≤ 0.25)。
HEAVY_SHARE = 0.50
SPREAD_SHARE = 0.25


class Degenerate(ValueError):
    """集中度在这个样本上退化 —— ★ 不许返回一个数充数。"""


# ────────────────────────────────────────────────────────────────────────
# 一 · 计算
# ────────────────────────────────────────────────────────────────────────

def concentration(pnls: Sequence[float], *, name: str = "<未命名>",
                  top_n: int = TOP_N) -> dict:
    """
    输入一条链的逐笔净盈亏,返回一个 dict。
    ★ 盈利笔数 < MIN_WIN_TRADES 时**不给集中度的数**,而是给胜率 + 退化标注。
    """
    vals = [float(x) for x in pnls]
    n = len(vals)
    wins = sorted((x for x in vals if x > 0), reverse=True)
    n_win = len(wins)
    win_rate = (n_win / n) if n else 0.0

    out: dict = {
        "链": name,
        "总笔数": n,
        "盈利笔数": n_win,
        "胜率": round(win_rate, 4),
    }

    if n_win < MIN_WIN_TRADES:
        out["集中度_前%d笔占总盈利" % top_n] = None
        out["★退化"] = True
        out["★读法"] = (
            f"★★ 集中度在此样本上退化,不可读:盈利笔数 {n_win} 笔 < {top_n} 笔,"
            f"「前 {top_n} 笔」在集合意义上**就是全部盈利笔**,"
            f"比例恒等于 100%,不含任何信息。"
            f"★ 改读胜率:{win_rate:.2%}({n_win}/{n})。"
            f"★ 不许把这个 100% 读成「曲线是几笔异常 bar 扛起来的」—— "
            f"它说明的是样本太薄,不是收益来源集中。")
        return out

    share = sum(wins[:top_n]) / sum(wins)
    out["集中度_前%d笔占总盈利" % top_n] = round(share, 6)
    out["★退化"] = False

    # ★★ 结构下限 —— 这一行是 技-10 逼出来的。
    #   盈利笔 12 笔时,「前 10 笔」最少也占 10/12 = 83.3%(所有盈利笔等大的情况),
    #   ★ 所以 99.79% 要和 83.3% 比,不是和 0 比。
    #   下限本身已经超过「铺得开」的分界 → 这个指标在这个样本上**不可能**报出
    #   「铺得开」,它只能报高 → 半退化,读数要连下限一起给。
    floor = min(1.0, top_n / n_win)
    out["结构下限"] = round(floor, 4)
    if floor > SPREAD_SHARE:
        out["★半退化"] = True
        out["★读法"] = (
            f"★ 半退化,读数必须连下限一起给:集中度 {share:.2%},"
            f"而盈利笔只有 {n_win} 笔 → 「前 {top_n} 笔」的**结构下限就是 "
            f"{floor:.1%}**(所有盈利笔等大时的值)。"
            f"★ 也就是说这个指标在这个样本上**不可能**报出「铺得开」,"
            f"它只能报高 —— 不许把 {share:.1%} 读成「曲线是几笔异常 bar 扛起来的」。"
            f"★ 该一起读的是胜率 {win_rate:.2%}({n_win}/{n})。")
        return out
    out["★半退化"] = False

    if share > HEAVY_SHARE:
        out["★读法"] = (
            f"★★ 集中度 {share:.1%} 过半 → 曲线是几笔扛起来的,"
            f"**这一版的收益数字不可用**(盈利笔 {n_win} 笔,样本够,"
            f"所以这是真的集中,不是退化)。")
    elif share <= SPREAD_SHARE:
        out["★读法"] = (f"集中度 {share:.1%}(一两成以内)→ 铺得开的效应,"
                        f"收益数字可用(盈利笔 {n_win} 笔)。")
    else:
        out["★读法"] = (f"集中度 {share:.1%}(两三成)→ 偏集中,"
                        f"收益数字要打折看(盈利笔 {n_win} 笔)。")
    return out


def check_reported(name: str, reported_share: float | None,
                   n_win: int, n_total: int, *, top_n: int = TOP_N
                   ) -> list[str]:
    """
    ★ 这是会 FAIL 的那一半:别人**已经报出来**一个集中度数字,
      而这个样本的盈利笔数不足 → 这个数字不该被报出来。
    """
    if reported_share is None:
        return []
    if n_win < top_n:
        return [
            f"[{name}] ★★ FAIL 报出了集中度 {reported_share:.1%},"
            f"而盈利笔数只有 {n_win} 笔(总 {n_total} 笔)< {top_n} 笔 —— "
            f"★ 这个数在数学上恒等于 100%,不含信息,★ 不许进表。"
            f"★ 该报的是胜率 {n_win / n_total:.2%} 并标注"
            f"「集中度在此样本上退化,不可读」。"
        ]
    floor = min(1.0, top_n / n_win)
    if floor > SPREAD_SHARE:
        return [
            f"[{name}] ★★ FAIL 集中度 {reported_share:.1%} 单独摆出来是误导:"
            f"盈利笔只有 {n_win} 笔 → 结构下限就是 {floor:.1%},"
            f"★ 这个指标在这个样本上不可能报出「铺得开」。"
            f"★ 要么连下限和胜率({n_win}/{n_total} = {n_win / n_total:.2%})"
            f"一起报,要么不报。"
        ]
    return []


# ────────────────────────────────────────────────────────────────────────
# 二 · 直接跑在流水上
# ────────────────────────────────────────────────────────────────────────

def from_ledger(path: str, *, pnl_col: str = "net_pnl") -> dict:
    with open(path, encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    pnls = [float(r[pnl_col]) for r in rows
            if r.get(pnl_col) not in (None, "")]
    return concentration(pnls, name=os.path.basename(path)[:-4])


def scan_ledger_dir(dirpath: str) -> list[dict]:
    return [from_ledger(p) for p in sorted(glob.glob(os.path.join(dirpath, "*.csv")))]


# ────────────────────────────────────────────────────────────────────────
# 三 · 自测 —— ★ 跑在仓库里现成的真实流水上
# ────────────────────────────────────────────────────────────────────────

_ENGINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _selftest() -> None:
    # ── 真实流水 ①:技-13 TD 序列 —— 223 笔,9 笔赚 ───────────────────
    r13 = from_ledger(os.path.join(_ENGINE, "ledgers_1029_新基准线",
                                   "技-13_TD序列.csv"))
    assert r13["总笔数"] == 223, r13
    assert r13["盈利笔数"] == 9, r13
    assert r13["★退化"] is True, r13
    assert r13["集中度_前10笔占总盈利"] is None, r13
    print(f"  ① 技-13_TD序列:{r13['总笔数']} 笔 / 盈利 {r13['盈利笔数']} 笔 → "
          f"{r13['★读法'][:78]} …")

    # ★ 会 FAIL 的那一半:当年报表里报出来的就是 100.0%
    bad = check_reported("技-13_TD序列", 1.0, r13["盈利笔数"], r13["总笔数"])
    assert bad and "FAIL" in bad[0], bad
    print("  ②", bad[0][:118], "…")

    # ── 真实流水 ②:技-10 海龟汤 —— 123 笔,12 笔赚 → ★ 不退化 ─────────
    r10 = from_ledger(os.path.join(_ENGINE, "ledgers_1029_新基准线",
                                   "技-10_海龟汤.csv"))
    assert r10["总笔数"] == 123 and r10["盈利笔数"] == 12, r10
    assert r10["★退化"] is False, r10
    assert r10["★半退化"] is True, r10
    assert r10["集中度_前10笔占总盈利"] > 0.99, r10
    assert abs(r10["结构下限"] - 10 / 12) < 1e-4, r10
    print(f"  ③ 技-10_海龟汤:{r10['总笔数']} 笔 / 盈利 {r10['盈利笔数']} 笔 → "
          f"集中度 {r10['集中度_前10笔占总盈利']:.2%},★ 结构下限 "
          f"{r10['结构下限']:.1%} → 半退化")
    bad10 = check_reported("技-10_海龟汤", r10["集中度_前10笔占总盈利"],
                           r10["盈利笔数"], r10["总笔数"])
    assert bad10 and "结构下限" in bad10[0], bad10
    print("     →", bad10[0][:118], "…")

    # ── 真实流水 ③:技-8 HTF —— 26 笔,9 笔赚 → 退化 ───────────────────
    r8 = from_ledger(os.path.join(_ENGINE, "ledgers_1029_新基准线",
                                  "技-8_高紧旗形HTF.csv"))
    assert r8["盈利笔数"] == 9 and r8["★退化"] is True, r8
    print(f"  ④ 技-8_高紧旗形HTF:{r8['总笔数']} 笔 / 盈利 {r8['盈利笔数']} 笔 → 同样退化")

    # ── 真实流水 ④:技-12 —— 2631 笔,1590 笔赚 → 两侧读法都要能打印 ────
    r12 = from_ledger(os.path.join(_ENGINE, "ledgers_1029_新基准线",
                                   "技-12_康纳斯均值回归.csv"))
    assert r12["★退化"] is False and "铺得开" in r12["★读法"], r12
    print(f"  ⑤ 技-12_康纳斯:集中度 {r12['集中度_前10笔占总盈利']:.2%} → "
          f"{r12['★读法'][:52]} …")

    # ── 全目录扫一遍:退化的必须全被标出来 ─────────────────────────────
    rs = scan_ledger_dir(os.path.join(_ENGINE, "ledgers_1029_新基准线"))
    deg = [r["链"] for r in rs if r["★退化"]]
    assert "技-13_TD序列" in deg and "技-8_高紧旗形HTF" in deg, deg
    print(f"  ⑥ ledgers_1029_新基准线 共 {len(rs)} 条链,退化 {len(deg)} 条:{deg}")

    print("checks/concentration_degenerate 自测通过 —— "
          "★ 真实流水上 100.0% 被正确判成「退化,不可读」,而不是「几笔扛起来」")


if __name__ == "__main__":
    _selftest()
