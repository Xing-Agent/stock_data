#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
★★★ 填说明书第 9 格（代价／美元）和第 3 / 6 格（市场环境 / 分层表现）

════════════════════════════════════════════════════════════════════
★★★ 先更正一件事
════════════════════════════════════════════════════════════════════
  ★ 说明书 v1 里第 9 格写的理由是「**本轮流水没入库**，所以这一格算不出来」。
  ★★★ **那句话是错的。** 流水是**没进 git**（757MB，刻意不提交），
     ★ 但它**在磁盘上**：`probe/bench1_rerun_1102/ledgers_1102/`，
     ★★ 45 份真链 + 45 份对照，列齐全（含 `net_pnl` / `entry_date` / `r_multiple_net`）。
  ★ 「没入库」和「不存在」是两件事 —— ★★★ 我把前者当成了后者。

════════════════════════════════════════════════════════════════════
★ 第 9 格算什么（★★ 三个数，规格书要的就是这三个）
════════════════════════════════════════════════════════════════════
  ① **最大一次亏多少美元**        = min(net_pnl)
  ② **最长连亏几次**              = 按离场日排序后最长的连续亏损笔数
  ③ **最长多久不赚钱**            = 累计净盈亏的最长水下时间（自然日 + 交易笔数两种）

  ★★★ **口径必须跟着这个数走**：这些美元数是在**初始资金 100 万美元**、
     按引擎的仓位规则算出来的（`engine/chain.py:412` `initial_equity=1_000_000.0`）。
     ★ 换成 10 万的账户要除以 10 —— ★★ 但**不是线性的**，因为仓位有下限和整股约束。
     ★★★ 所以说明书上要写「**在 100 万账户上**」，不许把它写成一个普适数字。

════════════════════════════════════════════════════════════════════
★ 第 3 / 6 格算什么
════════════════════════════════════════════════════════════════════
  ★ 按**进场那一天的大盘环境**把每一笔分三组，分别算笔数和每笔净 R：
      牛   —— SPY 在 200 日线上，且 200 日线 20 日斜率 > 0
      熊   —— SPY 在 200 日线下
      横盘 —— SPY 在 200 日线上，但斜率 ≤ 0
  ★★★ **这是我们自己定的分法，不是原著的** —— ★ 所以说明书里要标第 ③ 档（我们定的）。
  ★★ 为什么用这一套：它只用 SPY 的收盘价，**没有一个我们自己拍的阈值**
     （200 和 20 是行业里最通行的两个数，而且不是我们为了结果挑的）。

★ 本脚本**只读**：不碰 engine、不碰配置、不碰行情，只读流水和 SPY。
"""
from __future__ import annotations
import json, os, sys, glob, datetime
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", ".."))
LEDGERS = os.path.join(ROOT, "probe", "bench1_rerun_1102", "ledgers_1102")
BENCH = os.path.join(ROOT, "probe", "bench1_rerun_1102", "bench1_rerun_1102.json")
SPY = os.path.join(ROOT, "SPY", "daily.json")
OUT = os.path.join(HERE, "第9和3_6格-1102.json")
EQUITY = 1_000_000.0
PERF_START, PERF_END = "2018-01-01", "2025-12-31"


def say(*a):
    try: print(*a, flush=True)
    except Exception: pass


def 大盘环境() -> pd.Series:
    """★ 返回每个交易日一个标签:牛 / 熊 / 横盘。★★ 只用 SPY 收盘价。"""
    d = pd.DataFrame(json.load(open(SPY, encoding="utf-8"))["data"])
    d["date"] = pd.to_datetime(d["date"])
    d = d.set_index("date").sort_index()
    c = pd.to_numeric(d["close"], errors="coerce")
    ma200 = c.rolling(200, min_periods=200).mean()
    slope = ma200.diff(20)            # ★ 200 日线自己的 20 日变化
    lab = pd.Series(index=c.index, dtype=object)
    lab[(c > ma200) & (slope > 0)] = "牛"
    lab[(c > ma200) & (slope <= 0)] = "横盘"
    lab[c <= ma200] = "熊"
    return lab


def 代价(led: pd.DataFrame) -> dict:
    """★ 第 9 格的三个数。★★ 按**离场日**排序 —— 盈亏是在离场那天实现的。"""
    d = led.dropna(subset=["net_pnl"]).copy()
    if d.empty:
        return {"★算不出来": "流水里一笔有效 net_pnl 都没有"}
    d["exit_date"] = pd.to_datetime(d["exit_date"], errors="coerce")
    d = d.dropna(subset=["exit_date"]).sort_values("exit_date").reset_index(drop=True)
    pnl = d["net_pnl"].to_numpy(float)

    # ① 最大一次亏
    i最差 = int(np.argmin(pnl))
    # ② 最长连亏
    streak = best = 0
    for v in pnl:
        streak = streak + 1 if v < 0 else 0
        best = max(best, streak)
    # ③ 最长水下:累计净盈亏创新高之后,到下一次创新高之间最长的一段
    cum = np.cumsum(pnl)
    peak = np.maximum.accumulate(cum)
    水下 = cum < peak - 1e-9
    最长笔 = s = 0
    起 = None; 最长天 = 0; 最长区间 = None
    日 = d["exit_date"].to_numpy()
    for k, u in enumerate(水下):
        if u:
            s += 1
            if 起 is None: 起 = k
        else:
            if s > 最长笔: 最长笔 = s
            if 起 is not None:
                天 = (日[k] - 日[起]) / np.timedelta64(1, "D")
                if 天 > 最长天: 最长天 = float(天); 最长区间 = (str(pd.Timestamp(日[起]).date()), str(pd.Timestamp(日[k]).date()))
            s = 0; 起 = None
    if s > 最长笔: 最长笔 = s
    if 起 is not None:                      # ★ 收尾:还在水下
        天 = (日[-1] - 日[起]) / np.timedelta64(1, "D")
        if 天 > 最长天:
            最长天 = float(天)
            最长区间 = (str(pd.Timestamp(日[起]).date()), f"{pd.Timestamp(日[-1]).date()}（★ 到样本末尾仍在水下）")

    return {
        "★★★最大一次亏多少美元": round(float(pnl.min()), 2),
        "那一笔": {"票": str(d.loc[i最差, "symbol"]),
                  "进场": str(pd.Timestamp(d.loc[i最差, "entry_date"]).date()),
                  "离场": str(d.loc[i最差, "exit_date"].date()),
                  "离场原因": str(d.loc[i最差, "reason"]),
                  "净R": round(float(d.loc[i最差, "r_multiple_net"]), 4)
                          if pd.notna(d.loc[i最差, "r_multiple_net"]) else None},
        "★★最长连亏几次": int(best),
        "★★★最长多久不赚钱_自然日": round(最长天, 0),
        "最长多久不赚钱_交易笔数": int(最长笔),
        "最长水下区间": 最长区间,
        "★最大一次赚多少美元": round(float(pnl.max()), 2),
        "全期净盈亏美元": round(float(pnl.sum()), 2),
        # ★★★ 这个标必须有,否则「水下 2,842 天」会被当成一个独立的坏消息 ——
        # ★ 而窗口本身只有 2,011 个交易日(8 年)。
        "★★★水下时间怎么读": (
            "★★★ **这条链全期是亏的** → ★ 它在早期创下累计高点之后**再没回去过**，"
            "★★ 所以「最长水下」几乎等于整个窗口 —— "
            "★★★ 这不是一个独立的坏消息，**是「全期亏钱」这件事的另一种说法**。"
            if float(pnl.sum()) < 0 else
            "★ 这条链全期是赚的 → ★★ 水下时间是真正的「连续不赚钱的那一段」，"
            "★★★ 可以直接当代价读。"),
        "★口径": f"初始资金 {EQUITY:,.0f} 美元，引擎自带仓位规则；"
                 f"★★★ 换账户规模不是线性的（仓位有下限和整股约束），"
                 f"所以说明书上必须写「在 {EQUITY/10000:.0f} 万美元账户上」",
    }


def 分环境(led: pd.DataFrame, lab: pd.Series) -> dict:
    """★ 第 3 / 6 格:按**进场那天**的大盘环境分三组。"""
    d = led.copy()
    d["entry_date"] = pd.to_datetime(d["entry_date"], errors="coerce")
    d = d.dropna(subset=["entry_date"])
    d = d[(d["entry_date"] >= PERF_START) & (d["entry_date"] <= PERF_END)]
    d["环境"] = d["entry_date"].map(lab)
    out = {}
    for k in ("牛", "横盘", "熊"):
        g = d[d["环境"] == k]
        if g.empty:
            out[k] = {"笔数": 0, "★这个环境里一笔都没有": True}
            continue
        r = pd.to_numeric(g["r_multiple_net"], errors="coerce").dropna()
        p = pd.to_numeric(g["net_pnl"], errors="coerce").dropna()
        out[k] = {
            "笔数": int(len(g)),
            "占全部笔数": round(len(g) / max(1, len(d)), 4),
            "每笔净R": round(float(r.mean()), 6) if len(r) else None,
            "胜率": round(float((p > 0).mean()), 4) if len(p) else None,
            "净盈亏美元": round(float(p.sum()), 2) if len(p) else None,
            "★笔数<30_不给统计结论": bool(len(g) < 30),
        }
    缺 = int(d["环境"].isna().sum())
    if 缺:
        out["★环境标不出来的笔数"] = {"笔数": 缺,
            "为什么": "进场日早于 SPY 200 日线能算出来的第一天（需要 200 根历史）"}
    return out


def main() -> int:
    if not os.path.isdir(LEDGERS):
        say(f"★★★ 拿不到流水目录 {LEDGERS} —— 停,不猜"); return 2
    files = sorted(glob.glob(os.path.join(LEDGERS, "REAL__*")))
    if not files:
        say("★★★ 一份真链流水都没有 —— 停"); return 3
    say(f"★ 真链流水 {len(files)} 份")

    lab = 大盘环境()
    有标签 = lab.dropna()
    say(f"★★ 大盘环境标签:{有标签.index[0].date()} ~ {有标签.index[-1].date()}"
        f" · 牛 {(有标签=='牛').sum()} 天 · 横盘 {(有标签=='横盘').sum()} 天"
        f" · 熊 {(有标签=='熊').sum()} 天")

    # ★ 链名 ← bench json(流水文件名是压扁的,对不回原名,所以用 json 的顺序对)
    链名 = {}
    if os.path.exists(BENCH):
        b = json.load(open(BENCH, encoding="utf-8"))["逐链"]
        b = list(b.values()) if isinstance(b, dict) else b
        for c in b:
            链名[c["链"].replace(" ", "").replace("/", "_")] = c["链"]

    结果 = {
        "这是什么": "说明书第 9 格(代价/美元)+ 第 3/6 格(市场环境/分层表现)",
        "★★★先更正一件事": "说明书 v1 写第 9 格「流水没入库所以算不出来」——"
                          "那句话错了。流水是**没进 git**(757MB,刻意不提交),"
                          "但它在磁盘上 probe/bench1_rerun_1102/ledgers_1102/。"
                          "「没入库」和「不存在」是两件事。",
        "口径": {
            "流水": LEDGERS,
            "初始资金": EQUITY,
            "★★★美元口径": f"在 {EQUITY/10000:.0f} 万美元账户上；换规模不是线性的",
            "绩效窗口": f"{PERF_START} ~ {PERF_END}（8 年，2011 个交易日）",
            "★大盘环境怎么分的": "牛 = SPY 在 200 日线上且 200 日线 20 日斜率>0；"
                              "熊 = SPY 在 200 日线下；横盘 = 在线上但斜率≤0。"
                              "★★★ 这是**我们自己定的分法，不是原著的** → 第 ③ 档",
            "★为什么用这一套": "只用 SPY 收盘价，没有一个我们自己拍的阈值"
                            "（200 和 20 是行业最通行的两个数，不是为了结果挑的）",
        },
        "生成时间": f"{datetime.datetime.now():%Y-%m-%d %H:%M}",
        "逐链": {},
    }

    for i, f in enumerate(files, 1):
        key = os.path.basename(f).replace("REAL__", "").rsplit(".", 1)[0]
        名 = 链名.get(key, key)
        try:
            led = pd.read_csv(f)
        except Exception as e:
            say(f"[{i}/{len(files)}] ★ 读不到 {key[:40]}:{e}")
            结果["逐链"][名] = {"★读不到": str(e)}
            continue
        结果["逐链"][名] = {"流水文件": os.path.basename(f),
                          "总笔数": int(len(led)),
                          "第9格_代价": 代价(led),
                          "第3_6格_分环境": 分环境(led, lab)}
        c = 结果["逐链"][名]["第9格_代价"]
        if "★★★最大一次亏多少美元" in c:
            say(f"[{i}/{len(files)}] {名[:44]:46} "
                f"最大单笔亏 ${c['★★★最大一次亏多少美元']:>12,.0f} · "
                f"最长连亏 {c['★★最长连亏几次']:>2} 次 · "
                f"最长不赚钱 {c['★★★最长多久不赚钱_自然日']:>5.0f} 天")
        with open(OUT, "w", encoding="utf-8") as fh:
            json.dump(结果, fh, ensure_ascii=False, indent=1)

    say(""); say(f"★ 写出 {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
