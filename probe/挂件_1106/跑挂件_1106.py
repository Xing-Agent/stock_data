# -*- coding: utf-8 -*-
"""
★★★ 第一批出场挂件实测（B 路 1106）—— Gemini 第 45 轮指定的三种

大白话:每个宿主策略先原样跑一遍(不装),再一个一个装上挂件跑;
        只拿两边**都有**的进场逐笔比 —— 买点按死,只看「卖」变了之后好还是坏。

宿主(★ 都是**没有移动止损、没有时间止损**的,这样「装」才是真加装、不是替换):
  · 技-1  唐奇安 20 日突破(突破 / 趋势类)
  · 技-8  高紧旗形 HTF(动量波段类)
  · 技-14-XING 布林触下轨(均值回归类)
  · 技-12 康纳斯 RSI(2)(均值回归类)
挂件:
  · 吊灯移动止损 2 / 3 / 4 倍 ATR(22 日最高价起算)
  · 唐奇安低点止损 10 / 20 日
  · 时间止损:均值回归类 3 / 5 / 10 天;突破/动量类 20 / 40 / 60 天
  ★★★ 不配大盘闸(Gemini 第 45 轮推荐的「SPY 在 200 日线上」与它第 43 轮及我们实测矛盾 → 不采信)

★ 可续跑:每条臂流水落盘(arms_1106/*.csv.gz,不入库),已有就跳过。
★ engine 零改动;只用研发池;不跑赢随机;失败大声报。
"""
from __future__ import annotations
import gc, io, json, os, sys, time, traceback
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import 台_公共_1106 as T                                            # noqa: E402

ARMS = os.path.join(HERE, "arms_1106")
OUT = os.path.join(HERE, "挂件结果_1106.json")

宿主 = [
    ("技-1·唐奇安突破", "engine/configs/技-1.yaml", "突破趋势", [20, 40, 60]),
    ("技-8·高紧旗形", "engine/configs/技-8.yaml", "动量波段", [20, 40, 60]),
    ("技-14-XING·布林触下轨", "engine/configs/技-14-XING.yaml", "均值回归", [3, 5, 10]),
    ("技-12·康纳斯RSI2", "engine/configs/技-12.yaml", "均值回归", [3, 5, 10]),
]


def 挂件表(时间点):
    out = [("不装", None, None)]
    for k in (2.0, 3.0, 4.0):
        out.append((f"吊灯{int(k)}ATR", lambda r, k=k: T.装吊灯(r, k), "止损"))
    for n in (10, 20):
        out.append((f"唐奇安{n}日低点", lambda r, n=n: T.装唐奇安低点(r, n), "止损"))
    for n in 时间点:
        out.append((f"时间止损{n}天", lambda r, n=n: T.装时间止损(r, n), "时间止损"))
    return out


def 单臂(led: pd.DataFrame) -> dict:
    """★ 单臂自己的几个数:笔数、每笔净收益、利润因子、比同期大盘(修正口径 C)。"""
    d = T._键(led)
    s = T.替身收益(d)
    x = (d["ret"] - s).dropna()
    r = T.聚类t(x, d.loc[x.index, "entry_date"].dt.strftime("%Y-%m-%d"))
    return {"笔数": int(len(d)), "每笔净收益pct": round(float(d["ret"].mean()) * 100, 4),
            "利润因子": T._pf(d), "胜率": round(float((d["net_pnl"] > 0).mean()), 4),
            "比同期大盘pct": round(r["均值"] * 100, 4),
            "比同期大盘t": round(r["t"], 2) if np.isfinite(r["t"]) else None,
            "平均持有天": round(float(d["holding_days"].mean()), 2),
            "流水哈希": T.流水哈希(led)}


def 同票两笔(led: pd.DataFrame) -> int:
    """★ 实测:同一只票有没有两笔持仓**时间重叠**(重叠 = 后一笔进场早于前一笔离场)。"""
    d = led.copy()
    d["entry_date"] = pd.to_datetime(d["entry_date"]); d["exit_date"] = pd.to_datetime(d["exit_date"])
    n = 0
    for _, g in d.sort_values("entry_date").groupby("symbol"):
        e, x = g["entry_date"].to_numpy(), g["exit_date"].to_numpy()
        n += int((e[1:] < x[:-1]).sum())
    return n


def main() -> int:
    t0 = time.time()
    env = T.装覆盖层()
    os.makedirs(ARMS, exist_ok=True)
    报 = {"★口径": {k: v for k, v in env.items() if not k.startswith("_")}}
    报["★口径"].update({
        "做法": "同一宿主,装与不装逐笔配对;只取共同进场;聚类 t(进场日)+ 按月块重抽样",
        "判据": "①每笔净收益率差 ②大盘替身差(修正口径 C:不扔当天单、时点对齐)",
        "大盘闸": "不配(Gemini 第45轮建议不采信)", "engine改动": "零"})
    失败 = []
    for 名, cfgp, 类, 时间点 in 宿主:
        raw = T.读配置(cfgp)
        m = None
        legs = {}
        for 件, fn, 原因 in 挂件表(时间点):
            label = f"{名}|{件}"
            p = T.臂文件(ARMS, label)
            if os.path.exists(p):
                legs[件] = (pd.read_csv(p), 原因)
                print("  ⟳", label, flush=True); continue
            try:
                if m is None:
                    tb = time.time(); m, diag = T.建矩阵(raw)
                    print(f"★ 建矩阵 {名} {time.time()-tb:.0f}s", flush=True)
                r = raw if fn is None else fn(raw)
                led, info = T.跑(r, m)
                led.to_csv(p, index=False)
                io.open(p + ".info.json", "w", encoding="utf-8").write(
                    json.dumps(info, ensure_ascii=False, default=str))
                legs[件] = (led, 原因)
                print("  ✓", label, info["笔数"], flush=True)
            except Exception as e:
                失败.append({"臂": label, "原因": f"{type(e).__name__}: {e}"[:300]})
                print("  ✗✗✗", label, e, flush=True)
        del m; gc.collect()
        if "不装" not in legs:
            报[名] = {"★跑失败": "不装那条没跑出来,整个宿主不比"}; continue
        base = legs["不装"][0]
        h = {"类": 类, "配置": cfgp, "不装": 单臂(base),
             "★同票同时两笔(实测重叠次数)": 同票两笔(base)}
        for 件, (led, 原因) in legs.items():
            if 件 == "不装":
                continue
            try:
                h[件] = {"单臂": 单臂(led), "★配对": T.配对比(base, led, 原因)}
                if h[件]["单臂"]["流水哈希"] == h["不装"]["流水哈希"]:
                    h[件]["★注意"] = "流水和不装完全一样 —— 挂件一次都没生效(规矩⑪)"
            except Exception:
                h[件] = {"★跑失败": traceback.format_exc(limit=2)[-300:]}
                失败.append({"臂": f"{名}|{件}", "原因": "配对比失败"})
        报[名] = h
    报["★★★失败"] = 失败
    报["耗时秒"] = round(time.time() - t0, 1)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"★ 写到 {OUT};失败 {len(失败)} 条", flush=True)
    if 失败:
        print("⚠⚠⚠ 失败:", json.dumps(失败, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
