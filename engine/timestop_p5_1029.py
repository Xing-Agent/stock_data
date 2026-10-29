"""
timestop_p5_1029 —— 第四件:时间止损的 75 分位,按专家给的口径逐条照办。

大白话(三秒):一笔单子进场之后,几天之内能赚到 1 倍风险(+1R)?
把所有「最后确实赚到了 +1R」的单子按用了几天排个队,取第 75 名那个天数 ——
意思是「四分之三的好单在这么多天内就启动了」。超过这个天数还没启动的,
按时间止损走掉。

★★ 口径(专家给的,逐条照办,★ 一条不许改):
  ① 「首次触达 +1R」★ 必须按【收盘价】,★ 严禁用盘中最高价。
     理由:日线策略没有日内撮合;按 High 会把「盘中摸一下就砸回」误标成
     快速启动,导致 75 分位过严,★ 进而误杀需要 4~5 天蓄势才能收盘站上
     +1R 的真好单。
  ② 最终未触达 +1R 的笔子 ★ 完全排除在分子与分母之外(时间数学上是 ∞)。
  ③ 统计有效性【只看触达 +1R 的绝对笔数 N_win,不看它占总样本的比例】。
     ★ 硬性警报:N_win < 25 → 该分位处于高方差噪音区,【不可采信】,
     ★ 报告里直接标明,不许给一个数。
  ④ 全周期固定一个值,★ 严禁分环境算。理由:① 分环境样本过薄会 P-hacking
     ② 时间止损测的是【形态自身的催化半衰期】,宏观恶化的正确处理是
     用闸门降仓或空仓,★ 不是「在熊市里允许它多熬 10 天」。

★★ 还有一条核心警告(专家的,必须写进报告):
  如果某策略只有 20% 的笔数能摸到 +1R,说明它属于【长尾极低胜率模型】
  (如大级别海龟突破),★ 对这类策略强加时间止损【大概率重蹈
  「砍掉大牛苗子」的覆辙】。★ 时间止损天然只适用于【高胜率、短持有期】的
  动量与反转策略。
  ★ 所以每条链同时报:N_win · N_win/总笔数 · 胜率 · 平均持仓天数,
  ★ 并明确给出「这条链该不该装时间止损」的判断。

★ 实现细节(写明以免被当成猜的):
  · +1R 阈值 = entry_price + risk_per_share(流水里就有这两列,★ 不重算)
  · 天数 d = 从 entry_date(= 实际成交那天)到首次收盘 ≥ 阈值那天,
    中间的交易日数。★ d=0 表示成交当天收盘就站上了 +1R。
  · 扫描范围 = 这笔单子【自己的持仓期】entry_date .. exit_date ——
    ★ 单子已经平掉之后的价格不算「这笔单触达了」。
  · 价格全部取自同一份缓存面板(复权口径与跑链时一致)。

跑法:python3 -m engine.timestop_p5_1029
"""

from __future__ import annotations

import json
import os
import resource
import subprocess
import time

import numpy as np
import pandas as pd

from . import cache, data

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "results_1029_批五时间止损.json")

LEDGER_DIRS = [
    os.path.join(HERE, "ledgers_1029_A0十二条_新拆股口径"),
    os.path.join(HERE, "ledgers_1029_技术派六条三版"),
    os.path.join(HERE, "ledgers_1029_批五修正"),
]

N_WIN_FLOOR = 25            # ★ 专家给的硬性警报线


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _cache_fingerprint() -> dict:
    out = {}
    for label, path in (("ohlcv_panel.parquet", cache.PANEL_PARQUET),
                        ("panel_meta.parquet", cache.META_PARQUET)):
        st = os.stat(path)
        out[label] = {"bytes": st.st_size,
                      "构建时间(mtime, 本地)": time.strftime(
                          "%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))}
    return out


def _verdict(n_win: int, hit_rate: float, winrate: float,
             hold: float, p75, no_stop: float = 0.0,
             giveback: float | None = None) -> str:
    """★ 「该不该装时间止损」的判断 —— 判据写死在这里,不是逐条手写的。"""
    if no_stop > 0.5:
        return ("★★ 先修口径再谈:这条链多数笔子其实没有止损"
                "(risk_per_share ≈ entry_price),「+1R」= 翻倍,"
                "★ 这个 N_win 不能用来判断时间止损。")
    if n_win < N_WIN_FLOOR:
        return (f"★★ 不给数:N_win={n_win} < {N_WIN_FLOOR},"
                f"该分位处于高方差噪音区,【不可采信】。")
    if hit_rate < 0.30:
        return (f"★★ 不建议装:只有 {hit_rate:.1%} 的笔数摸到过 +1R "
                f"→ 属于【长尾极低胜率模型】,强加时间止损大概率重蹈"
                f"「砍掉大牛苗子」的覆辙。")
    gb = "" if giveback is None else f"回吐率 {giveback:.0%}、"
    if hold > 30:
        return (f"★ 谨慎,但这条链的问题不是「启动慢」:平均持仓 {hold:.0f} 天,"
                f"不是短持有期策略;+1R 命中率 {hit_rate:.1%}、{gb}"
                f"胜率只有 {winrate:.1%} —— ★ 四成笔子摸到过 +1R 却只有"
                f"{winrate:.0%} 最终盈利收场,说明该装的是【保本/移动止损】,"
                f"时间止损(填 {p75} 天)只解决「从没启动过」那一部分。")
    return (f"★ 建议装,填 {p75} 天:命中率 {hit_rate:.1%}、{gb}"
            f"胜率 {winrate:.1%}、平均持仓 {hold:.1f} 天 "
            f"—— 属于时间止损天然适用的【高胜率、短持有期】那一类。")


def one_ledger(path: str, close: pd.DataFrame,
               row_of: dict) -> dict:
    led = pd.read_csv(path)
    n = len(led)
    name = os.path.basename(path)[:-4]
    if n == 0:
        return {"链": name, "总笔数": 0,
                "★结论": "★ 拿不到:流水是空的"}
    ca = close.to_numpy(float)
    cols = {s: i for i, s in enumerate(close.columns)}

    days, missing, win_rows = [], 0, []
    for _, r in led.iterrows():
        s = r["symbol"]
        if s not in cols:
            missing += 1
            continue
        i0 = row_of.get(pd.Timestamp(r["entry_date"]))
        i1 = row_of.get(pd.Timestamp(r["exit_date"]))
        if i0 is None or i1 is None:
            missing += 1
            continue
        thr = float(r["entry_price"]) + float(r["risk_per_share"])
        j = cols[s]
        seg = ca[i0:i1 + 1, j]
        ok = np.flatnonzero(np.isfinite(seg) & (seg >= thr))
        if ok.size:
            days.append(int(ok[0]))
            win_rows.append(float(r["net_pnl"]))

    d = np.asarray(days, dtype=float)
    wr = np.asarray(win_rows, dtype=float)
    # ★ 风险距离体检:risk_per_share / entry_price —— 这个数决定「+1R」有多远。
    #   ★ 等于 1.0 = 这条链其实【没有止损】(止损价挂在 0),
    #     那「+1R」就等于「翻倍」,N_win 必然接近 0 —— ★ 这不是策略的结论,
    #     是口径的事实,必须和数字一起报出来,不许当成「它没有快速启动能力」。
    rd = (led["risk_per_share"].astype(float)
          / led["entry_price"].astype(float)).replace([np.inf, -np.inf], np.nan)
    rd_med = float(rd.median())
    no_stop = float((rd >= 0.999).mean())
    n_win = int(d.size)
    hit = n_win / max(1, n)
    winrate = float((led["net_pnl"] > 0).mean())
    hold = float(led["holding_days"].mean())
    q = {}
    if n_win:
        for p in (25, 50, 75, 90, 95):
            q[f"p{p}"] = float(np.percentile(d, p))
    p75 = int(np.ceil(q["p75"])) if n_win else None

    out = {
        "链": name,
        "总笔数": n,
        "★N_win(收盘触达+1R的绝对笔数)": n_win,
        "★N_win/总笔数": round(hit, 4),
        "胜率(net_pnl>0)": round(winrate, 4),
        "平均持仓天数": round(hold, 2),
        "最长持仓天数": int(led["holding_days"].max()),
        "流水里对不上价格的笔数": missing,
        "★风险距离_risk_per_share÷entry_price_中位": round(rd_med, 4),
        "★★「其实没有止损」的笔数占比(risk÷entry ≥0.999)": round(no_stop, 4),
        "首次触达+1R用的交易日数_分位": {k: round(v, 2) for k, v in q.items()},
        "首次触达+1R用的交易日数_均值": round(float(d.mean()), 2) if n_win else None,
        "当天收盘就站上+1R的比例(d=0)":
            round(float((d == 0).mean()), 4) if n_win else None,
        "★摸到过+1R但最终亏钞收场的比例(回吐率)":
            round(float((wr <= 0).mean()), 4) if n_win else None,
    }
    if no_stop > 0.5:
        out["★★口径警报"] = (
            f"★★ 这条链 {no_stop:.0%} 的笔子 risk_per_share ≈ entry_price "
            f"—— 意味着【止损价挂在 0,其实没有止损】。"
            f"★ 于是「+1R」= 股价翻倍,N_win 必然接近 0。"
            f"★ 这是口径事实,不是「这条形态没有启动能力」—— "
            f"要算这条链的时间止损,必须先给它一个真实的止损距离。")
    if n_win < N_WIN_FLOOR:
        out["★★75分位(时间止损该填几天)"] = (
            f"★★ 不给数 —— N_win={n_win} < {N_WIN_FLOOR},"
            f"该分位处于高方差噪音区,【不可采信】")
    else:
        out["★★75分位(时间止损该填几天)"] = p75
    out["★该不该装时间止损"] = _verdict(
        n_win, hit, winrate, hold, p75, no_stop,
        float((wr <= 0).mean()) if n_win else None)
    return out


def main() -> int:
    t0 = time.time()
    print(subprocess.run(["free", "-m"], capture_output=True, text=True).stdout)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                          capture_output=True, text=True).stdout.strip()
    syms = cache.symbols()
    close = cache.field("close", syms)
    row_of = {t: i for i, t in enumerate(close.index)}
    print(f"池子 {len(syms)} 只;价格面板 {close.shape}")

    rows = []
    for d in LEDGER_DIRS:
        if not os.path.isdir(d):
            print(f"★ 目录不存在,跳过:{d}")
            continue
        for f in sorted(os.listdir(d)):
            if not f.endswith(".csv"):
                continue
            rec = one_ledger(os.path.join(d, f), close, row_of)
            rec["流水目录"] = os.path.basename(d)
            rows.append(rec)
            print(f"  {rec['链'][:46]:48s} n={rec['总笔数']:5d} "
                  f"N_win={rec['★N_win(收盘触达+1R的绝对笔数)']:5d} "
                  f"p75={rec['★★75分位(时间止损该填几天)']}")

    focus = [r for r in rows
             if any(k in r["链"] for k in ("技-8", "技-13", "技-10"))]
    out = {
        "git_commit": head,
        "缓存身份": _cache_fingerprint(),
        "统计窗口": [data.PERF_START, data.PERF_END],
        "★口径": {
            "触达+1R": "★ 按【收盘价】:Close ≥ entry_price + risk_per_share;"
                        "★ 严禁用盘中最高价(日线策略无日内撮合)",
            "未触达的笔子": "★ 完全排除在分子与分母之外(时间数学上是 ∞)",
            "统计有效性": f"★ 只看 N_win 绝对笔数;N_win < {N_WIN_FLOOR} → "
                           f"【不可采信】,★ 不给数",
            "分环境": "★ 全周期固定一个值,★ 严禁分环境算",
            "扫描范围": "每笔单子自己的持仓期 entry_date .. exit_date",
            "天数定义": "d = entry_date 到首次收盘触达那天的交易日数;"
                        "d=0 = 成交当天收盘就站上了 +1R",
        },
        "★★ 专家的核心警告": (
            "如果某策略只有 20% 的笔数能摸到 +1R,说明它属于【长尾极低胜率模型】"
            "(如大级别海龟突破),★ 对这类策略强加时间止损【大概率重蹈"
            "「砍掉大牛苗子」的覆辙】。★ 时间止损天然只适用于"
            "【高胜率、短持有期】的动量与反转策略。"),
        "逐链": rows,
        "★重点三条(技-8 / 技-13 / 技-10)": focus,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n写好 {OUT_JSON}(共 {len(rows)} 条链;"
          f"{time.time()-t0:.0f} 秒;峰值 RSS {_rss_mb():.0f} MB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
