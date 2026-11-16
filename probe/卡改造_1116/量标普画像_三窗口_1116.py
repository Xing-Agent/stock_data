#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★★★ 量「满仓标普」的三件画像（年化 · 最大回撤 · 最长不创新高）—— ★ 纯价格 和 全收益 两个口径各一份。

★★★★★ 为什么要有这个脚本（《92》1116 第十八轮 四节④ 排的活）：
   39 张卡的共用边界里有一句「不许省」的硬话：
     「和副参考比 —— 满仓标普全收益**同窗口** +14.55%/年，最大回撤 **-34.1%**，最长不创新高 **2.0 年**」
     「个人几乎做不到。**这十一年**里有过 -34.1% 的回撤、2.0 年不创新高」
   ★★ 1116 第十八轮已查实：**+14.55% 是 2009~2025（17 年 · 4,275 个收益日）的数**，
      而同一节声明的窗口是 2015-01-01~2025-12-31（11 年），同窗口全收益真数 13.44%（错号 #120）。
   ★★★ 但 **-34.1% / 2.0 年 是哪个窗口、哪个口径的，一直没查** → 本脚本只查这一件。

★ 只读：只读 `pilot_300/benchmarks/SPY/daily.json`（收盘价 + dividend_amount），
  ★★ **不读面板、不跑回测、不改任何文件**，产物只有一份 json。
★★ 为什么不走 `全收益基准()`：★★★ 它的分红来自 `engine.data.dividends()` → `load_manifest()`，
  而 manifest 里**只有 300 只 pilot 个股、没有 SPY** → 裸调会**静默**返回空分红 = 纯价格冒充全收益。
  ★ 本轮第一版就踩了这一脚（见《208》三节）→ 现在改成直读基准文件，并写死一道「分红不许为空」的断言。
★★★ 不下判决，只出数。
"""
from __future__ import annotations
import json, os
import pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
SRC = os.path.join(ROOT, "pilot_300", "benchmarks", "SPY", "daily.json")
年 = 252.0

窗口 = {
    "B_2015到2025_卡里声明的那个窗口": ("2015-01-01", "2025-12-31"),
    "F_2009到2025_14.55%的出处": ("2009-01-01", "2025-12-31"),
}


def 画像(r: pd.Series) -> dict:
    r = r.dropna()
    eq = (1.0 + r).cumprod()
    峰 = eq.cummax()
    回 = eq / 峰 - 1.0
    新高 = eq >= 峰 * (1 - 1e-12)
    最长, 当前, 末 = 0, 0, None
    for i, v in enumerate(新高.to_numpy()):
        当前 = 0 if v else 当前 + 1
        if 当前 > 最长:
            最长, 末 = 当前, i
    g = {"年化%": round(float((1.0 + r).prod() ** (年 / len(r)) - 1.0) * 100, 3),
         "最大回撤%": round(float(回.min()) * 100, 2),
         "最长不创新高_交易日": int(最长),
         "最长不创新高_年(交易日÷252)": round(最长 / 年, 2),
         "收益日数": int(len(r))}
    if 末 is not None:
        起i = max(末 - 最长, 0)
        g["最长不创新高_区间"] = f"{eq.index[起i].date()}~{eq.index[末].date()}"
        g["最长不创新高_日历年"] = round((eq.index[末] - eq.index[起i]).days / 365.25, 2)
    return g


rows = json.load(open(SRC, encoding="utf-8"))["data"]
df = pd.DataFrame(rows)
df["date"] = pd.to_datetime(df["date"])
df = df.set_index("date").sort_index()
df = df[~df.index.duplicated(keep="last")]
px = pd.to_numeric(df["close"], errors="coerce").dropna()
dv = pd.to_numeric(df.get("dividend_amount"), errors="coerce").reindex(px.index).fillna(0.0)
sp = pd.to_numeric(df.get("split_coefficient"), errors="coerce").reindex(px.index).fillna(1.0)

# ★★★ 跑前写死的三道断言（★ 少一道这份数就不许报）
assert int((dv > 0).sum()) >= 40, f"★★★ SPY 分红格子只有 {int((dv>0).sum())} 个 —— 停跑（空分红会让纯价格冒充全收益）"
assert float(sp[sp != 1.0].count()) == 0, "★★★ 这段里 SPY 有拆股事件 —— 分红和价格要先折算到同口径，停跑"
assert px.index[0].year <= 2015, f"★★★ SPY 数据从 {px.index[0].date()} 才开始 —— 停跑"

纯r = px.pct_change().fillna(0.0)
全r = 纯r + (dv / px.shift(1)).fillna(0.0)

报 = {
    "★这是什么": "满仓标普的三件画像（年化/最大回撤/最长不创新高），纯价格 与 全收益 两个口径并排",
    "★★★本次口径": ("【本次口径】全收益（分红再投）与 纯价格 两份并排 · 摩擦 标普侧不扣 · "
                "窗口 见下逐段 · 池 不适用（只有 SPY） · 标签滞后 不适用"),
    "★只读": f"只读 {os.path.relpath(SRC, ROOT)}；没读面板、没跑回测、没改文件",
    "★数据区间": f"{px.index[0].date()}~{px.index[-1].date()}（{len(px)} 天 · 分红非零 {int((dv>0).sum())} 格 · 拆股事件 0）",
    "★★★这份数据到不了的地方": "数据从 2014-01-02 起 → **2009~2025 那个 17 年窗口本脚本算不了**（14.55% 的复核见《138》三节）",
    "纯价格": {},
    "全收益": {},
}
for 名, (起, 止) in 窗口.items():
    for 口径, r in (("纯价格", 纯r), ("全收益", 全r)):
        g = 画像(r.loc[起:止])
        g["窗口"] = f"{起}~{止}"
        if 名.startswith("F_"):
            g["★★★这一行不算数"] = "数据只到 2014 起 → 这不是真的 2009~2025，只是被截断后的同一段，别引用"
        报[口径][名] = g

报["★★★对账_卡里写的"] = {
    "共用边界原话": "满仓标普全收益同窗口 +14.55%/年，最大回撤 -34.1%，最长不创新高 2.0 年（「这十一年里」）",
    "卡里声明的窗口": "2015-01-01~2025-12-31（11 年）",
    "★★★只报匹配_不下判决": "下面逐个列哪个口径的数和卡里对得上，判决由人下",
    "逐个比": {
        "14.55%/年": "《138》三节：2009~2025（17 年）全收益 —— 本脚本算不了，引《138》",
        "-34.1%": f"11 年窗口 · 纯价格 = {报['纯价格']['B_2015到2025_卡里声明的那个窗口']['最大回撤%']}% ｜ 11 年窗口 · 全收益 = {报['全收益']['B_2015到2025_卡里声明的那个窗口']['最大回撤%']}%",
        "2.0 年不创新高": f"11 年窗口 · 纯价格 = {报['纯价格']['B_2015到2025_卡里声明的那个窗口']['最长不创新高_年(交易日÷252)']} 年 ｜ 11 年窗口 · 全收益 = {报['全收益']['B_2015到2025_卡里声明的那个窗口']['最长不创新高_年(交易日÷252)']} 年",
    },
}

OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "标普三件画像_1116.json")
with open(OUT, "w", encoding="utf-8") as fh:
    json.dump(报, fh, ensure_ascii=False, indent=2)
print(json.dumps(报, ensure_ascii=False, indent=2))
print("→", OUT)
