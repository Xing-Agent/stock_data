# -*- coding: utf-8 -*-
"""
★★★ 分行情比 —— ★ 把「所有行情混成一个平均」拆开。

★★ 来历：Lin 1107 08:54：
  「比如你那个动量的、或者突破单，逻辑上来说都应该是要比大盘跑得好的……
    如果同样是市场可能震荡的话，那可能震荡单会跑得更好一些。
    所以我就觉得你的这些比较肯定有些问题。」
★★★ 他指出的是真缺口：我们把 2015~2025 **十年所有行情混成一个平均** ——
  ★ 一条只在趋势里有效的策略，会被震荡那几年**冲掉**。

★★★ ⚠ 但这个检验的**用法**必须先写清（★ 免得被当成翻盘）：
  「它在对的行情里能赢」**不等于**「它能赚钱」——
  ★★ 要收到那份超额，你得**事先知道现在是什么行情**；
  ★★★ 而我们昨天测过环境闸：三条全部小于噪声。
  → ★ 所以这一份的用处是**诊断**：
    · 趋势段为正、震荡段为负 → ★★ **可修**（环境卡要做好）
    · 两段都为负 → ★★★ **不是行情的问题，是策略本身**

★ 两个轴（★★ 都按**当天**的已实现状态算，★★★ 不看未来）：
  ① **方向**：标普收盘在自己的 200 日均线上方 / 下方（★ 带 1% 缓冲，照 11-04 拍板）
  ② **性质**：效率比 ER(n) = |N 日净变动| ÷ N 日逐日变动绝对值之和
     ★★ 高 = 走直线（趋势）；低 = 来回磨（震荡）
     ★★★ 出处：Kaufman 1995；★ Gemini 第 46 轮把它排在 ADX / 方差比 / 赫斯特之前
     ★★ 门槛原著没给 → **跑相邻三点**（0.5 / 0.6 / 0.7），并报三点是否同向

★ engine 零改动；★★ 算不出单独报数；★★★ 失败大声报。
"""
import glob, json, os, sys
import numpy as np, pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "组合日收益_1106"))
import 组合日收益_1107 as 核                                     # noqa: E402

OUT = "probe/分行情比_1107"


def 行情(idx: pd.DatetimeIndex, er_n: int = 10) -> pd.DataFrame:
    """★ 两个轴，都用标普自己的已实现数据算（★★★ 当天收盘才知道，不看未来）。"""
    s = 核.spy().reindex(idx).ffill()
    ma = s.rolling(200, min_periods=200).mean()
    上 = s > ma * 1.01            # ★ 1% 缓冲带（11-04 拍板，继续适用）
    下 = s < ma * 0.99
    方向 = pd.Series(np.where(上, "线上", np.where(下, "线下", "缓冲带")), index=idx)
    方向[ma.isna()] = "算不出"
    d = s.diff()
    er = (s.diff(er_n).abs() / d.abs().rolling(er_n, min_periods=er_n).sum())
    return pd.DataFrame({"方向": 方向, "ER": er})


def 回归分段(r: pd.Series, bench: pd.Series, mask: pd.Series) -> dict:
    y = r[mask].dropna()
    x = bench.reindex(y.index)
    out = 核.回归(y, x)
    if "★算不出" not in out:
        out["★这一段的交易日数"] = int(len(y))
        nav = (1 + y).cumprod()
        dd = nav / nav.cummax() - 1.0
        out["★这一段年化pct"] = round(float(nav.iloc[-1] ** (252 / len(y)) - 1) * 100, 2)
        out["★这一段最大回撤pct"] = round(float(dd.min()) * 100, 2)
    return out


def 一条(p: str) -> dict | None:
    d = pd.read_csv(p)
    need = {"symbol", "entry_date", "exit_date", "shares", "entry_price", "net_pnl"}
    if d.empty or not need <= set(d.columns):
        return {"★跑失败": f"缺列:{sorted(need - set(d.columns))}"}
    for c in ("entry_date", "exit_date"):
        d[c] = pd.to_datetime(d[c], errors="coerce")
    for c in ("shares", "entry_price", "net_pnl"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["symbol", "entry_date", "shares", "entry_price", "net_pnl"])
    if d.empty:
        return None
    eq, 敞口, 缺 = 核.逐日(d)
    if eq is None:
        return {"★跑失败": "面板里没有这条臂的任何票"}
    r = eq.pct_change()
    s = 核.spy().reindex(eq.index).ffill()
    同敞口 = s.pct_change() * 敞口.shift(1)     # ★ 同敞口指数（主判据口径）
    out = {"①笔数": int(len(d)), "★平均敞口pct": round(float(敞口.mean()) * 100, 1)}

    # ★ 轴一 · 方向（大盘在 200 日线上 / 下）
    g = 行情(eq.index)
    for 名 in ("线上", "线下"):
        m = (g["方向"] == 名)
        if m.sum() >= 60:
            out[f"②方向·{名}"] = 回归分段(r, 同敞口, m)
        else:
            out[f"②方向·{名}"] = {"★算不出": f"只有 {int(m.sum())} 个交易日"}

    # ★★ 轴二 · 性质（效率比高 = 走直线 / 低 = 锯齿）★★★ 相邻三点
    for th in (0.5, 0.6, 0.7):
        for 名, m in (("走直线", g["ER"] >= th), ("锯齿", g["ER"] < th)):
            k = f"③性质·ER≥{th}·{名}"
            m = m & g["ER"].notna()
            out[k] = (回归分段(r, 同敞口, m) if m.sum() >= 60
                      else {"★算不出": f"只有 {int(m.sum())} 个交易日"})
    return out


def main() -> int:
    报 = {"★这一份做什么": {
        "问题": "★★★ 原来把 2015~2025 **十年所有行情混成一个平均** —— "
              "★ 一条只在趋势里有效的策略会被震荡那几年冲掉（Lin 1107 08:54 指出）",
        "★★★用法必须写清": ["「它在对的行情里能赢」**不等于**「它能赚钱」——"
                        "要收到那份超额，你得**事先知道现在是什么行情**；"
                        "而我们昨天测过环境闸：三条全部小于噪声",
                        "★ 所以这一份是**诊断**：趋势段为正、震荡段为负 → **可修**；"
                        "两段都为负 → **不是行情的问题，是策略本身**"],
        "轴一_方向": "标普收盘在自己 200 日均线上方/下方（★ 带 1% 缓冲，11-04 拍板）",
        "轴二_性质": "效率比 ER(10)（★★ Kaufman 1995；Gemini 第 46 轮把它排在 ADX 之前）"
                 "—— ★★★ 门槛原著没给 → **跑相邻三点 0.5 / 0.6 / 0.7**",
        "判据": "★ 对**同敞口指数**回归的 alpha 与 **Newey-West t**（★★ 和主判据同口径）",
        "不看未来": "★★★ 两个轴都只用标普**当天收盘**才知道的数据",
        "engine改动": "零",
    }}
    fs = sorted(glob.glob("probe/挂闸_1106/ledgers_1106/REAL__*.csv")) + \
         sorted(glob.glob("probe/新策略_1106/**/REAL__融-*.csv", recursive=True))
    失败 = 0
    for f in fs:
        名 = os.path.basename(f)[6:-4]
        try:
            r = 一条(f)
        except Exception as e:
            r = {"★跑失败": repr(e)[:200]}
        if r:
            报[名] = r
            if "★跑失败" in r:
                失败 += 1; print("⚠ 失败", 名, flush=True)
            else:
                print("✓", 名, flush=True)
    报["★★★失败条数"] = 失败
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "分行情比_报告_1107.json"), "w", encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print(f"★ 写完;★★★ 失败 {失败} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
