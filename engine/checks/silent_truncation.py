"""
★ 静默截断自检 —— 引擎实际用的序列,和原始 daily.json 比,被切掉了多少。

三秒版:有些票的历史被整段**切掉**了(不是调整),而且是**悄悄**切的 ——
        这道闸逐只把它们列出来,并且要求每一只在 split_gate 里**有登记**。
        切了但没登记 → ★ FAIL。

────────────────────────────────────────────────────────────────────────
★★ 为什么这是另一种幸存者偏差
────────────────────────────────────────────────────────────────────────
我们一直盯的是「退市的票不在池子里」那一种。★ 这是**另一种**:

    票**还在池子里**,但它**最惨的那段历史被切了**。

实例(已查实):`split_gate` 对 SQBG 的处理是把 **2020-07-27 之前的历史整段切掉**,
不是调整。所以引擎的 SQBG 序列只从 2020-07-27 开始 ——
★ 而被切掉的那一段,正是它从 0.1935 跌到 0.0043(**−97.8%**)的那一段。

★ 切得有理由(按核实的 1 合 40 修完仍残余 30 倍假跳变,口径拿不到 →
  不许编第二个系数),★ 但「有理由」和「静默」是两件事:
  引擎里没有任何地方会告诉你「这只票你只看到了后 20%」。
★ 所以这道闸的用处不是反对切,是让**切掉了什么**变成一个必须读到的数。

★ 这是今天第四次吃「静默」的亏(前三次:delisting_reason / LongTermDebt /
  split_coefficient)—— 所以同样不允许它静默。

────────────────────────────────────────────────────────────────────────
★ 累计涨跌幅那一列的口径声明(必须跟着数一起讲)
────────────────────────────────────────────────────────────────────────
被切段的累计涨跌幅是用**原始价**算的。
★★ 而「原始价本身可能标错」—— 切这一刀的理由恰恰就是「这段价格被额外调整过、
  口径拿不到」。所以这个数要读成「**按原始价看,被切掉的是这样一段**」,
  ★ 不能读成「这只票真实跌了这么多」。
★ ACOR 这种两头都切的(keep=after + keep=before 各一刀),首尾价跨了两个口径,
  累计数更没有意义 —— 所以本文件把**头段和尾段分开报**,不合成一个数。
"""

from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))))

from engine import data as D                                     # noqa: E402
from engine import split_gate as SG                              # noqa: E402


def _raw_rows(symbol: str) -> list[dict]:
    meta = D.load_manifest()[symbol]
    with open(meta.daily_path, encoding="utf-8") as fh:
        raw = json.load(fh)
    return sorted((raw.get("data") or []), key=lambda x: x["date"])


def _cum(rows: list[dict]) -> float | None:
    """一段原始 bar 的累计涨跌幅(按原始收盘价)。不足两根 / 全是 0 价 → None。"""
    cl = []
    for x in rows:
        v = x.get("close")
        try:
            f = float(v)
        except (TypeError, ValueError):
            continue
        if f > 0:
            cl.append(f)
    if len(cl) < 2:
        return None
    return cl[-1] / cl[0] - 1.0


def check(cut_events=None) -> dict:
    """
    逐只比较「原始 daily.json 的日期范围」和「D.load_daily() 返回的日期范围」。

    cut_events:只给自测用 —— 传一份改过的 CUT_EVENTS 来证明「切了但没登记 → FAIL」。
    """
    cuts = SG.CUT_EVENTS if cut_events is None else tuple(cut_events)
    registered = {e.symbol for e in cuts}

    pool = D.full_universe().symbols
    out: dict = {"池子票数": len(pool), "被截断的": [], "没登记的": [],
                 "话": [], "级别": "OK"}

    for s in pool:
        rows = _raw_rows(s)
        if not rows:
            continue
        df = D.load_daily(s)
        if df.empty:
            continue
        k0, k1 = str(df.index[0].date()), str(df.index[-1].date())
        r0, r1 = rows[0]["date"], rows[-1]["date"]
        if r0 == k0 and r1 == k1:
            continue                                   # 没被截断

        head = [x for x in rows if x["date"] < k0]     # 前端被切掉的一段
        tail = [x for x in rows if x["date"] > k1]     # 后端被切掉的一段
        item = {
            "票": s,
            "原始范围": f"{r0}..{r1}",
            "引擎范围": f"{k0}..{k1}",
            "原始根数": len(rows), "引擎根数": int(len(df)),
            "切掉根数": len(rows) - int(len(df)),
            "头段": None, "尾段": None,
            "已登记": s in registered,
            "登记的刀": [f"{e.date}(keep={e.keep})" for e in cuts if e.symbol == s],
        }
        if head:
            item["头段"] = {"起止": f"{head[0]['date']}..{head[-1]['date']}",
                            "根数": len(head), "★按原始价累计涨跌": _cum(head)}
        if tail:
            item["尾段"] = {"起止": f"{tail[0]['date']}..{tail[-1]['date']}",
                            "根数": len(tail), "★按原始价累计涨跌": _cum(tail)}
        out["被截断的"].append(item)
        if not item["已登记"]:
            out["没登记的"].append(s)

    n, p = len(out["被截断的"]), len(pool)
    out["影响票数"] = n
    out["占池子比例"] = n / p if p else 0.0
    out["切掉总根数"] = sum(i["切掉根数"] for i in out["被截断的"])

    out["话"].append(
        f"★ 截断总共影响 {n} 只票,占池子 {out['占池子比例']:.1%}"
        f"(池子 {p} 只);共切掉 {out['切掉总根数']} 根 bar。")
    out["话"].append(
        "★★ 口径声明:下面「按原始价累计涨跌」是用**原始价**算的,而"
        "**原始价本身可能标错** —— 切这一刀的理由就是「这段价格被额外调整过、"
        "口径拿不到」。所以它读作「按原始价看被切掉的是这样一段」,"
        "★ 不是「这只票真实跌了这么多」。")
    for i in out["被截断的"]:
        seg = []
        for which in ("头段", "尾段"):
            d = i[which]
            if not d:
                continue
            c = d["★按原始价累计涨跌"]
            seg.append(f"{which} {d['根数']} 根 {d['起止']} "
                       f"累计 {('%+.1f%%' % (c * 100)) if c is not None else 'n/a'}")
        out["话"].append(
            f"   {i['票']:6s} 原始 {i['原始范围']} → 引擎 {i['引擎范围']}"
            f"(切掉 {i['切掉根数']} 根);{' | '.join(seg)};"
            f"登记:{'✅ ' + ','.join(i['登记的刀']) if i['已登记'] else '★★ 没有登记'}")

    if out["没登记的"]:
        out["级别"] = "FAIL"
        out["话"].append(
            f"★★ FAIL:{len(out['没登记的'])} 只票被截断了,但 split_gate 的 "
            f"CUT_EVENTS 里**没有登记**:{out['没登记的']}。"
            f"★ 截了但没登记 = 这段历史静默消失,没人认领。")
    else:
        out["话"].append(
            f"✅ 被截断的 {n} 只票**全部**在 split_gate.CUT_EVENTS 里有登记 —— "
            f"没有静默截断。")
    return out


# ────────────────────────────────────────────────────────────────────────
# 自测 —— ★ 跑全池真实数据
# ────────────────────────────────────────────────────────────────────────

def _selftest() -> None:
    r = check()
    for line in r["话"]:
        print("  ", line)
    assert r["级别"] == "OK", r["没登记的"]

    # ★ 回归断言:全池 300 只,9 只被截断,全部有登记
    assert r["池子票数"] == 300, r["池子票数"]
    assert r["影响票数"] == 9, [i["票"] for i in r["被截断的"]]
    assert set(i["票"] for i in r["被截断的"]) == {
        "ACOR", "AMRS", "FTLF", "LIXT", "OMEX", "PROP", "SQBG", "UHAL", "XPRO"
    }, [i["票"] for i in r["被截断的"]]

    # ★★ SQBG 那一条 —— 本次要钉住的事实
    sq = next(i for i in r["被截断的"] if i["票"] == "SQBG")
    assert sq["引擎范围"].startswith("2020-07-27"), sq
    assert sq["头段"] is not None and sq["头段"]["★按原始价累计涨跌"] < -0.9, sq
    print(f"\n   ★★ SQBG:引擎序列只从 {sq['引擎范围']} 开始;"
          f"被切掉的头段 {sq['头段']['起止']} 共 {sq['头段']['根数']} 根,"
          f"按原始价累计 {sq['头段']['★按原始价累计涨跌']:+.1%} —— "
          f"★ 被切掉的正是它跌到接近零的那一段。")

    # ★ 多少只被切掉的是「惨段」:9 只里有几只的被切段是大幅下跌
    bad = [(i["票"], i["头段"] or i["尾段"]) for i in r["被截断的"]]
    heavy = [(t, d["★按原始价累计涨跌"]) for t, d in bad
             if d and d["★按原始价累计涨跌"] is not None
             and d["★按原始价累计涨跌"] < -0.5]
    print(f"   ★ 9 只里有 {len(heavy)} 只被切掉的那一段是**跌超 50%** 的:"
          f"{[(t, '%.0f%%' % (c * 100)) for t, c in heavy]}")
    assert len(heavy) >= 5, heavy

    # ── ★★ 反向自测:从登记清单里拿掉 SQBG → 必须 FAIL ────────────────
    without_sqbg = tuple(e for e in SG.CUT_EVENTS if e.symbol != "SQBG")
    r2 = check(cut_events=without_sqbg)
    assert r2["级别"] == "FAIL", r2["话"]
    assert r2["没登记的"] == ["SQBG"], r2["没登记的"]
    print(f"   ★ 反向自测:把 SQBG 从 CUT_EVENTS 里拿掉 → {r2['级别']}"
          f"(没登记的:{r2['没登记的']})→ ★ 闸在工作")

    # 清空整份登记 → 9 只全部没归属
    r3 = check(cut_events=())
    assert r3["级别"] == "FAIL" and len(r3["没登记的"]) == 9, r3["没登记的"]
    print(f"   ★ 反向自测:CUT_EVENTS 清空 → {r3['级别']}"
          f"({len(r3['没登记的'])} 只没登记)→ ★ 闸在工作")

    print("\nchecks/silent_truncation 自测通过 —— "
          "★★ 这是另一种幸存者偏差:票还在池子里,但最惨的那段历史被切了;"
          "★ 现在它不再静默。")


if __name__ == "__main__":
    _selftest()
