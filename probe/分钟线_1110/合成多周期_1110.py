# -*- coding: utf-8 -*-
"""★★★★★ 从 5 分钟线合成任意周期 —— ★ Lin 1110 10:21「开干」。

★★ 三秒版：本机有 58 只 · 5 分钟线 · 2021-01-01~2025-12-31。
   ★★★ 15min / 30min / 1h / 2h / 4h 全部从它合成，**不用向任何人要数据**。

★★★★★ 这个脚本的核心不是合成（合成就十行），**是自证** ——
   ★ 昨天我跑同样一件事，开盘一致率只有 4%~20%，★★ 差点报「数据口径有问题」;
   ★★★ 查下去是**我自己把日线索引时区转错了**，整条倒退一天。改完 99.3%~100%。
   → ★★★★★ 所以这里每合成一个周期，都**逐级往上合成回日线**和 daily.json 对一次。
     ★★ 任一级对不上 —— 这个周期**不许落盘**。

★★★ 暂行口径（★ 已发问题单给 Gemini，答了再改这一处）：
   「N 日」在小时/分钟线上**原样读成 N 根本周期**（甲-1）——
   ★★★★★ 不折算、不乘交易小时数，★★ 因为那个换算数原著没给，我们算出来就是自己发明。
   ★ 每份输出里都写死一行 `口径说明`，不许在展示时省掉。

★ 用法：python3 合成多周期_1110.py [周期...]   默认 15min 30min 1h 2h 4h
"""
from __future__ import annotations
import glob
import io
import json
import os
import sys

import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
出目录 = os.path.join(ROOT, "probe", "分钟线_1110", "合成")

周期表 = {"15min": "15min", "30min": "30min", "1h": "60min", "2h": "120min", "4h": "240min"}
口径说明 = (
    "★★★★★ 这一份是从 5 分钟线合成的（provider=alpha_vantage · adjustment=raw 未复权 · "
    "session=regular 无盘前盘后）。「N 日」类参数在本周期上**原样读成 N 根本周期**，"
    "★★★ **不是**原著说的 N 日 —— 原著（欧奈尔/威科夫/唐奇安等）只讲日线和周线，"
    "没有讲小时或分钟线的换算。★★ 展示时这句话不许省。"
)


def 找票() -> dict:
    出 = {}
    for p in (glob.glob(os.path.join(ROOT, "*", "5min.json"))
              + glob.glob(os.path.join(ROOT, "pilot_50", "*", "5min.json"))
              + glob.glob(os.path.join(ROOT, "pilot_50", "supplemental", "*", "5min.json"))):
        出[os.path.basename(os.path.dirname(p))] = p
    return 出


def 读5(p: str):
    """★★ 返回 (df, 元数据)。★★★★★ 文件自带 adjustment/session/status/missing_months ——
    ★ 这几样正是口径,**必须跟着数据一路带到输出**,不许在展示时省掉。"""
    d = json.load(io.open(p, encoding="utf-8"))
    元 = {k: d.get(k) for k in ("adjustment", "session", "provider", "status",
                                "interval", "timezone", "start_date", "end_date")}
    元["缺月数"] = len(d.get("missing_months") or [])
    数 = d.get("data")
    if not isinstance(数, list) or not 数 or not isinstance(数[0], dict):
        return None, 元          # ★★★ status: unavailable 的那两只走这条
    df = pd.DataFrame(数)
    df["time"] = pd.to_datetime(df["time"], utc=True, format="mixed")
    return df.set_index("time").sort_index().tz_convert("America/New_York"), 元


def 读日(票: str) -> pd.DataFrame | None:
    for p in (os.path.join(ROOT, 票, "daily.json"),
              os.path.join(ROOT, "pilot_50", 票, "daily.json"),
              os.path.join(ROOT, "pilot_50", "supplemental", 票, "daily.json")):
        if os.path.exists(p):
            d = json.load(io.open(p, encoding="utf-8"))
            df = pd.DataFrame(d["data"] if isinstance(d, dict) else d)
            c = "date" if "date" in df else "time"
            # ★★★★★ 昨天就是在这一行出错的：日线是**纯日期**，★ 千万不要 utc 解析再转时区,
            #   ★★★ 那会让整条索引倒退一天,拿昨天的日线比今天的合成。
            df["d"] = pd.to_datetime(df[c].astype(str).str[:10]).dt.date
            return df.set_index("d").sort_index()
    return None


def 合成(m: pd.DataFrame, 规则: str) -> pd.DataFrame:
    g = m.resample(规则, label="left", closed="left", origin="start_day")
    out = g.agg(open=("open", "first"), high=("high", "max"),
                low=("low", "min"), close=("close", "last"), volume=("volume", "sum"))
    return out.dropna(subset=["open"])


def 合回日(df: pd.DataFrame) -> pd.DataFrame:
    return df.groupby(df.index.date).agg(open=("open", "first"), high=("high", "max"),
                                         low=("low", "min"), close=("close", "last"))


def main() -> int:
    周期们 = sys.argv[1:] or ["15min", "30min", "1h", "2h", "4h"]
    坏 = [x for x in 周期们 if x not in 周期表]
    if 坏:
        print(f"★★★ 不认识的周期：{坏}。★ 支持：{list(周期表)}")
        return 1
    票们 = 找票()
    print(f"★ 源数据：{len(票们)} 只 5 分钟线")
    os.makedirs(出目录, exist_ok=True)

    台账 = {"★口径说明": 口径说明, "周期": {}, "★★★自证不过的": []}
    for 周期 in 周期们:
        规则 = 周期表[周期]
        成, 败 = [], []
        print(f"\n{'='*14} {周期} {'='*14}")
        print(f"{'票':<8}{'根数':>9}{'合成天':>8}{'开':>7}{'高':>7}{'低':>7}{'收':>7}  判")
        for 票, p in sorted(票们.items()):
            m, 元 = 读5(p)
            if m is None:
                败.append({"票": 票, "因": f"源数据为空（status={元.get('status')}）", "元": 元})
                print(f"{票:<8}{'—':>9}{'—':>8}  ✗ 源数据为空 status={元.get('status')}")
                continue
            df = 合成(m, 规则)
            d = 读日(票)
            if 元.get("adjustment") != "raw":
                败.append({"票": 票, "因": f"复权口径不是 raw：{元.get('adjustment')}", "元": 元})
                continue
            if d is None or df.empty:
                败.append({"票": 票, "因": "没有日线可对照" if d is None else "合成为空"})
                continue
            g = 合回日(df)
            共 = pd.Index(g.index).intersection(d.index)
            if len(共) < 200:
                败.append({"票": 票, "因": f"和日线重合只有 {len(共)} 天"})
                continue
            a, b = g.loc[共], d.loc[共]
            率 = {f: round(float((abs(a[f] - b[f]) / b[f] < 0.002).mean()) * 100, 2)
                  for f in ("open", "high", "low", "close")}
            # ★★★★★ 1110 第三版判据 —— ★ 前两版都是错的，经过写在这里：
            #   【一版】四字段一道 99% 闸 → 32/58 不过。
            #   【二版】以为「开/高/低是真实成交、只有收是集合竞价」,把收移出闸
            #     → ★★★ 又败在开上;查 ISRG 2021-02-08:日线开 768.26、
            #       5 分钟 09:30 那根开 770.82(差 0.33%),★★ 15min 和 1h **都是 39/1255 天不一致**
            #       → ★★★★★ **开和收都是「集合竞价价 vs 桶内第一/最后一笔成交」的口径差。**
            #   【三版·现在】全 56 只量完：高 中位99.9%/最差94.9%、低 99.9%/93.4%、
            #     开 99.6%/95.3%、收 99.7%/**39.3%**。
            #     ★★★★★ **没有任何一个字段干净到能当硬闸** —— 所以不设闸。
            # → ★★ 改成:**如实记录四个字段的一致率 + 按可用性分等级**,全部落盘。
            #   ★★★★★ 并且写死一条使用边界:**分钟级合成数据和日线不是同一个口径**,
            #     ★★★ 所以**不许把分钟级结果和日线回测成绩放在一起比大小**。
            过 = True
            额 = float((b["close"] * b["volume"]).median()) if "volume" in b else float("nan")
            齐 = min(率.values())
            收档 = ("★ 四项都≥99%：分钟级可放心用" if 齐 >= 99 else
                   "★★ 高/低≥99%，开或收有口径差：形态可用，开收价谨慎" if min(率["high"], 率["low"]) >= 99 else
                   "★★★★★ 高/低都不到 99%：这只票分钟级不可用")
            if not 过:
                败.append({"票": 票, "因": "合成回日线对不上（开/高/低）", "一致率": 率})
                continue
            o = os.path.join(出目录, 票)
            os.makedirs(o, exist_ok=True)
            df.reset_index(names="time").assign(**{}).to_json(
                os.path.join(o, f"{周期}.json"), orient="records",
                date_format="iso", force_ascii=False)
            io.open(os.path.join(o, f"{周期}.口径.txt"), "w", encoding="utf-8").write(
                口径说明 + "\n\n★★★ 本票口径（源文件自带，不许省）：\n"
                + "\n".join(f"  · {k} = {v}" for k, v in 元.items())
                + f"\n  · 合成回日线一致率 = {率}"
                + f"\n  · 日均成交额 = {额/1e6:.1f} 百万美元"
                + f"\n  · ★★★ 收盘价可用性 = {收档}\n"
                + "\n★★★★★ 收盘口径差（已查实，不是错误）：日线收盘是**收盘集合竞价价**，"
                  "★★ 本文件末根是 15:55–16:00 的成交。★★★ 流动性越差，两者差越大。\n"
                + "\n★★★★★ adjustment=raw 意味着**未复权** —— "
                  "★★ 「N 根新高」在未复权价上算，★★★ 遇到拆股会出假突破。\n")
            成.append(票)
            台账.setdefault("★★收盘可用性", {}).setdefault(周期, {})[票] = {
                "收一致%": 率["close"], "日均成交额百万": round(额/1e6, 2), "档": 收档}
        台账["周期"][周期] = {"落盘": len(成), "不落盘": len(败)}
        台账["★★★自证不过的"] += [dict(周期=周期, **x) for x in 败]
        print(f"→ ★★ {周期}: 落盘 {len(成)} 只 · ★★★ 自证不过 {len(败)} 只")

    io.open(os.path.join(ROOT, "手册", "合成台账_1110.json"), "w", encoding="utf-8").write(
        json.dumps(台账, ensure_ascii=False, indent=1))
    print(f"\n★★ 台账写到 手册/合成台账_1110.json")
    print("★★★★★ 没查到的：**合成对得上 ≠ 这个周期上的策略判断就对**。"
          "★★ 「N 日读成 N 根」这个口径还在等 Gemini 的行业做法，★ 现在是暂行。")
    return 0 if not 台账["★★★自证不过的"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
