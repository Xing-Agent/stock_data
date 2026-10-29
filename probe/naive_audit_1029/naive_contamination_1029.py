#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
朴素基准(基准五)的污染审计 · 2026-10-29 晚

为什么要有这个文件:
  原著离场那一轮报了一条硬结论 ——
    「15 条链,没有一条打得过朴素基准(朴素基准 +450.75%)」。
  ★ 而朴素基准的规则是「全池每日做多过去 5 天跌幅最深的那 5%,持有 3 天」。
  ★★ 我们池子里有 24 只票在「已知数据断裂清单」上,它们的特征恰好是
     假跌 + 次日假涨(未修的反向拆股)。
  ★★★ 也就是说:这条规则会系统性地专门挑中那些假跌。

做法:按原文定义自己重算一遍朴素基准的选股和持有,把收益拆成
      「在已知断裂清单上的票」和「干净票」两份。

结论(2026-10-29 晚实测,见下方 EXPECTED):
  ★★★ 污染票占 21.4% 的笔数,但占 96.0% 的总收益。
  ★ 剔掉污染票后,平均每笔从 +14.485% 掉到 +0.733%(约 1/20)。
  ★★ 前十笔占总盈利 77.47% —— 按我们自己的口径「过半 → 数字不可用」。
  ★★★ 所以「没有一条链打得过朴素基准」这句话不成立 ——
     那不是一条基准,那是一个未修拆股造出来的数。

★ 连带的推论(比朴素基准本身要紧):
  任何「买跌」类策略在我们这个池子里都最大程度暴露在这个偏差下 ——
  技-12(康纳斯 RSI2 买超卖)· 技-14(布林带下轨)· 技-10(海龟汤买新低)·
  技-11(威科夫 Spring 买破支撑)。★ 它们的历史结论都要按这个角度重看。
"""
import collections
import glob
import importlib.util
import json
import os

_HERE = os.path.dirname(os.path.abspath(__file__))
_REPO = os.path.dirname(os.path.dirname(_HERE))

#: 2026-10-29 晚的实测值,留作回归基线
EXPECTED = {
    "总笔数": 23144, "污染票笔数": 4963, "干净票笔数": 18181,
    "污染票占总收益": 0.960, "干净票平均每笔": 0.00733,
    "前十笔占总盈利": 0.7747,
}

PERF_START, PERF_END = "2018-01-02", "2025-12-31"
LOOKBACK, HOLD, TOP_PCT = 5, 3, 0.05


def known_break_symbols() -> set:
    p = os.path.join(_REPO, "engine", "checks", "anchor_health.py")
    spec = importlib.util.spec_from_file_location("ah", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)                                  # type: ignore
    return m.known_break_symbols()


def load_pool() -> dict:
    px = {}
    for d in sorted(os.listdir(os.path.join(_REPO, "pilot_300"))):
        p = os.path.join(_REPO, "pilot_300", d, "daily.json")
        if not os.path.exists(p):
            continue
        try:
            rows = (json.load(open(p, encoding="utf-8")).get("data") or [])
        except Exception:
            continue
        if len(rows) < 50:
            continue
        px[d] = {r["date"]: r["close"] for r in rows if r.get("close")}
    return px


def audit() -> dict:
    known = known_break_symbols()
    px = load_pool()
    dates = sorted(set().union(*[set(v) for v in px.values()]))
    dates = [d for d in dates if PERF_START <= d <= PERF_END]

    contrib, cnt, per = collections.Counter(), collections.Counter(), []
    for i in range(LOOKBACK, len(dates) - HOLD):
        d0, dL, dH = dates[i], dates[i - LOOKBACK], dates[i + HOLD]
        cand = []
        for s, v in px.items():
            a, b, c = v.get(dL), v.get(d0), v.get(dH)
            if a and b and c and a > 0:
                cand.append((b / a - 1, s, c / b - 1))
        if len(cand) < 20:
            continue
        cand.sort(key=lambda t: t[0])
        for _, s, r in cand[:max(1, int(len(cand) * TOP_PCT))]:
            g = "污染票" if s in known else "干净票"
            contrib[g] += r
            cnt[g] += 1
            per.append((r, s, d0))

    tot, n = sum(contrib.values()), sum(cnt.values())
    wins = sorted([x[0] for x in per if x[0] > 0], reverse=True)
    per.sort(reverse=True)
    return {
        "池子只数": len(px), "其中在断裂清单上": len(set(px) & known),
        "总笔数": n, "平均每笔": tot / n,
        "污染票笔数": cnt["污染票"], "干净票笔数": cnt["干净票"],
        "污染票占总收益": contrib["污染票"] / tot,
        "污染票平均每笔": contrib["污染票"] / max(1, cnt["污染票"]),
        "干净票平均每笔": contrib["干净票"] / max(1, cnt["干净票"]),
        "前十笔占总盈利": sum(wins[:10]) / sum(wins),
        "盈利笔数": len(wins),
        "前十大单笔": [(s, round(r * 100, 1), d, s in known)
                       for r, s, d in per[:10]],
    }


def _selftest() -> None:
    r = audit()
    print(f"  池子 {r['池子只数']} 只,其中 {r['其中在断裂清单上']} 只在已知断裂清单上")
    print(f"  总选中 {r['总笔数']} 笔 | 平均每笔 {r['平均每笔']*100:+.3f}%")
    print(f"  ★★ 污染票 {r['污染票笔数']} 笔({r['污染票笔数']/r['总笔数']*100:.1f}%)"
          f" 占总收益 {r['污染票占总收益']*100:+.1f}%,平均每笔 {r['污染票平均每笔']*100:+.2f}%")
    print(f"  ★  干净票 {r['干净票笔数']} 笔,平均每笔 {r['干净票平均每笔']*100:+.3f}%")
    print(f"  ★★ 前十笔占总盈利 {r['前十笔占总盈利']*100:.2f}% → 过半,按我们自己的口径"
          f"**这个数字不可用**")
    print("  前五大单笔:", r["前十大单笔"][:5])

    # 回归断言:这几个数就是推翻「打不过朴素基准」那句话的依据
    assert r["污染票占总收益"] > 0.90, r
    assert r["前十笔占总盈利"] > 0.50, r
    assert r["干净票平均每笔"] < r["平均每笔"] / 10, r
    print("\n★★★ 结论:朴素基准 +450.75% 是未修拆股造出来的 ——"
          "「15 条链没有一条打得过朴素基准」这句话不成立。")


if __name__ == "__main__":
    _selftest()
