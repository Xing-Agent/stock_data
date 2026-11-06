# -*- coding: utf-8 -*-
"""
★★★ 尺子 C —— 单独量「进场有没有用」，★ 完全绕开出场规则。

★★ 来历：第 43 轮 Gemini 的修法 C（Lin 1106 16:56 转回来的）——
  「用引擎已有的成交明细，直接算每笔进场后第 5、10、20 天的收益减同期 SPY，
    完全绕开出场规则」。
★★★ 为什么要它：原来那把「赢随机」尺子，随机进场**沿用了策略自己的趋势跟踪出场**
  （止损锁死 −1R、盈利放开跑）→ ★ 它量的主要是**出场**，不是进场。

★ engine 零改动：只读流水 + 日线面板。
★★★ 纪律：
  · 算不出就是 NaN，不猜不补（★ 窗口不够的笔、退市截断的笔都剔掉并单独报数）
  · 显著性按**进场日聚类**（★ 同一天进场的几笔不独立 —— 第 43 轮问题 4 的两个毛病之一）
  · 不写「建议用哪条」，只给数字
"""
import os, sys, json, glob
import numpy as np, pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from engine import data as D                                  # noqa: E402

OUT = os.path.join(ROOT, "probe", "尺子C_1106")
WIN = (5, 10, 20)
# ★★★ 1106 修:`engine.data` **没有** load_ohlcv 这个函数 ——
#   ★ 我又猜了接口名,结果 21 条臂全报算不出(平均超额全是 None)。
#   ★★ 新池的价格在**覆盖层面板**里:probe/newpool_1106/ohlcv_panel_newpool.parquet
#     (3,018 行 × 16,842 列,列是 MultiIndex ('close', 代码))。
#   ★★★ 这是今天第三次猜接口/名字 —— 已登记。
_PANEL = None
面板: dict = {}


def _panel():
    global _PANEL
    if _PANEL is None:
        _PANEL = pd.read_parquet(
            os.path.join(ROOT, "probe/newpool_1106/ohlcv_panel_newpool.parquet"))
    return _PANEL


def 收盘(sym: str):
    if sym not in 面板:
        p = _panel()
        try:
            面板[sym] = p[("close", sym)].dropna()
        except Exception:
            面板[sym] = None
    return 面板[sym]


def 前向收益(sym, 进场日, n, spy):
    """★ 进场后第 n 个**交易日**的收益 − 同期 SPY。★★ 窗口不够 → NaN。"""
    c = 收盘(sym)
    if c is None:
        return np.nan
    i = c.index.searchsorted(pd.Timestamp(进场日))
    if i >= len(c) or i + n >= len(c):
        return np.nan                      # ★ 窗口不够(含退市截断) → 算不出
    r = float(c.iloc[i + n] / c.iloc[i] - 1.0)
    j = spy.index.searchsorted(pd.Timestamp(进场日))
    if j >= len(spy) or j + n >= len(spy):
        return np.nan
    b = float(spy.iloc[j + n] / spy.iloc[j] - 1.0)
    return (r - b) * 100.0                 # ★ 百分点


def 聚类标准误(df, 值列):
    """★★★ 按**进场日**聚类的标准误 —— 同一天进场的几笔当一个观测。
       ★ 做法:先把同一天的几笔取平均,再对「天」求标准误(★★ 最保守也最常见的一种)。"""
    g = df.groupby("entry_date")[值列].mean().dropna()
    n = len(g)
    if n < 3:
        return np.nan, n
    return float(g.std(ddof=1) / np.sqrt(n)), n


def 一条(路径):
    d = pd.read_csv(路径)
    if d.empty or "entry_date" not in d.columns:
        return None
    spy = D.load_benchmark("SPY")["close"]
    d = d[["symbol", "entry_date"]].dropna().copy()
    out = {"①总笔数": int(len(d))}
    for n in WIN:
        col = f"超额{n}日"
        d[col] = [前向收益(s, t, n, spy) for s, t in zip(d["symbol"], d["entry_date"])]
        v = d[col].dropna()
        se, nd = 聚类标准误(d, col)
        out[f"第{n}日"] = {
            "可算笔数": int(len(v)),
            "★算不出笔数": int(len(d) - len(v)),
            "平均超额pct": (round(float(v.mean()), 4) if len(v) else None),
            "中位超额pct": (round(float(v.median()), 4) if len(v) else None),
            "★按进场日聚类的标准误": (round(se, 4) if np.isfinite(se) else None),
            "★★聚类数(不同进场日)": nd,
            "★★★判定": None,
        }
        m = out[f"第{n}日"]
        if m["平均超额pct"] is not None and m["★按进场日聚类的标准误"]:
            t = m["平均超额pct"] / m["★按进场日聚类的标准误"]
            m["t值"] = round(float(t), 2)
            m["★★★判定"] = ("★ 正且过 2 倍标准误" if t > 2 else
                           ("负且过 2 倍标准误" if t < -2 else "★★★ 测不出（在噪声里）"))
    return out


def main() -> int:
    报 = {"★这把尺子量什么": "**只量进场** —— 进场后第 5/10/20 个交易日的收益减同期 SPY，"
                        "★★★ 完全不看策略自己的出场规则",
          "★★为什么要换": "原来的「赢随机」尺子里，随机进场沿用了策略自己的趋势跟踪出场 →"
                      "★ 它量的主要是出场（第 43 轮 Gemini 确认，我们自己也先怀疑到了）",
          "★★★口径": {
              "窗口": "交易日，不是日历日",
              "算不出": "进场后不足 n 个交易日的笔（含退市截断）→ NaN，单独报数，不补",
              "标准误": "★★★ 按**进场日聚类**（同一天进场的几笔先取平均再对天求标准误）"
                      "—— 第 43 轮问题 4 指出同一天的笔不独立",
              "判定尺": "|平均超额| > 2 × 聚类标准误 才算测得出",
              "★不给建议": "只列数字，不写「该不该用」—— 判断留给 Lin",
          }}
    文件 = sorted(glob.glob("probe/挂闸_1106/ledgers_1106/REAL__*.csv")) + \
          sorted(glob.glob("probe/新策略_1106/**/REAL__融-*.csv", recursive=True))
    报["★臂数"] = len(文件)
    for f in 文件:
        名 = os.path.basename(f)[6:-4]
        try:
            r = 一条(f)
        except Exception as e:
            r = {"★跑失败": repr(e)[:200]}
        if r:
            报[名] = r
            print("✓", 名, flush=True)
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "尺子C_报告_1106.json"), "w", encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print("★ 写到", os.path.join(OUT, "尺子C_报告_1106.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
