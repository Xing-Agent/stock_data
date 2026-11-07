# -*- coding: utf-8 -*-
"""
★★★ 组合日收益尺子 —— ★ 这是前三把尺子都答不了那个问题的那一把。

★★ 为什么要第四把（★★★ 前三把的毛病，逐个写明）：
  · **每笔差**：2 天的笔和 60 天的笔**算一样的权重** → ★ 不公平
  · **每天差**（= 每笔差 ÷ 持有天数）：★★★ **按持有期系统性地压扁一侧** →
      实测融-1：大亏集中在长持有（每笔 −4.359%，÷12 压成 −0.351%），
      大赚集中在短持有（+2.094%，÷1 原样保留）→
      ★ 全部笔每笔差 **+0.011%**（基本是零），而每天差均值 **+0.452%** —— **造假正数**
  · **利润因子**：对持有期敏感、不看回撤（已降为辅助）
★★★ 对的做法（Gemini 第 44 轮原话）：「都按**每天的组合净值**算」。

★ 做法：
  ① 从流水**重建逐日组合净值**（100 万 + 已平仓累计 + 持仓按当日收盘的浮动盈亏）
  ② 算组合的**日收益序列**
  ③ 和 SPY 同期比，★★★ **两个口径都报**（它们回答不同的问题）：
     · **同敞口**：把 SPY 的日收益按我们当天的**实际敞口**缩放
       → 答「同样的钱、同样的日子、同样的仓位重，改成买指数会怎样」
     · **满仓指数**：和 100% 持有 SPY 比
       → 答「我不如一直满仓买指数吗」
  ④ 六个指标（照 Gemini 第 44 轮）：年化收益 · 年化波动 · 夏普 · 最大回撤
     · 回本天数 · 信息比率 · 对 SPY 回归的 alpha 与 **Newey-West t** · 卡玛 · 溃疡指数

★★ 无风险利率用 **DGS3MO**（第 41 轮已定：债券等价口径，不用 DTB3 贴现口径）。
★ engine 零改动。★★★ 算不出一律 NaN 并单独报数，不猜不补。
"""
import glob, json, os, sys
import numpy as np, pandas as pd

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
sys.path.insert(0, ROOT); os.chdir(ROOT)
from engine import data as D                                   # noqa: E402

EQ0 = 1_000_000.0
PANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
OUT = "probe/组合日收益_1106"
_CLOSE = None
_SPY = None
_RF = None


def 收盘():
    global _CLOSE
    if _CLOSE is None:
        _CLOSE = pd.read_parquet(PANEL)["close"]
    return _CLOSE


def spy():
    global _SPY
    if _SPY is None:
        _SPY = D.load_benchmark("SPY")["close"].dropna()
    return _SPY


def 无风险日():
    """★ DGS3MO 年化百分数 → 日收益。★★ 找不到就返回 None（**不拿 0 顶替**）。"""
    global _RF
    if _RF is None:
        for p in ("probe/rates_1102/DGS3MO.csv", "market_macro_1105/DGS3MO.csv"):
            f = os.path.join(ROOT, p)
            if os.path.exists(f):
                d = pd.read_csv(f)
                s = pd.Series(pd.to_numeric(d[d.columns[1]], errors="coerce").values,
                              index=pd.to_datetime(d[d.columns[0]], errors="coerce")
                              ).dropna().sort_index()
                _RF = (s / 100.0) / 252.0
                break
        else:
            _RF = False
    return None if _RF is False else _RF


def 逐日(d: pd.DataFrame):
    """★★★ 重建逐日组合净值 + 当天敞口比例。★ 敞口 = 持仓市值 ÷ 当日净值。"""
    cl = 收盘()
    syms = [s for s in d["symbol"].astype(str).unique() if s in cl.columns]
    if not syms:
        return None, None, len(set(d["symbol"].astype(str)))
    cl = cl[syms]
    idx = cl.index
    实现 = pd.Series(0.0, index=idx)
    g = d.dropna(subset=["exit_date"]).groupby("exit_date")["net_pnl"].sum()
    for t, v in g.items():
        if t in 实现.index:
            实现.loc[t] += float(v)
    实现 = 实现.cumsum().shift(1).fillna(0.0)
    浮 = pd.Series(0.0, index=idx)
    市值 = pd.Series(0.0, index=idx)
    for _, r in d.iterrows():
        s = str(r["symbol"])
        if s not in cl.columns:
            continue
        a = r["entry_date"]
        b = r["exit_date"] if pd.notna(r["exit_date"]) else idx[-1]
        seg = cl[s].loc[(cl.index >= a) & (cl.index < b)].dropna()
        if seg.empty:
            continue
        sh = float(r["shares"])
        浮.loc[seg.index] += (seg - float(r["entry_price"])) * sh
        市值.loc[seg.index] += seg * sh
    eq = (EQ0 + 实现 + 浮).rename("净值")
    敞口 = (市值 / eq.replace(0, np.nan)).clip(lower=0).fillna(0.0)
    return eq, 敞口, len(set(d["symbol"].astype(str))) - len(syms)


def 指标(r: pd.Series, rf: pd.Series | None) -> dict:
    """★ 一条日收益序列的常用指标。★★ 回撤和回本按净值曲线算。"""
    r = r.dropna()
    if len(r) < 60:
        return {"★算不出": f"只有 {len(r)} 个交易日，少于 60 不算"}
    nav = (1.0 + r).cumprod()
    yrs = len(r) / 252.0
    ann = float(nav.iloc[-1] ** (1.0 / yrs) - 1.0)
    vol = float(r.std(ddof=1) * np.sqrt(252))
    ex = r - (rf.reindex(r.index).ffill() if rf is not None else 0.0)
    sharpe = float(ex.mean() / ex.std(ddof=1) * np.sqrt(252)) if ex.std(ddof=1) > 0 else np.nan
    peak = nav.cummax()
    dd = nav / peak - 1.0
    mdd = float(dd.min())
    # ★ 回本天数：最深回撤那天之后，★★ 多少个交易日才回到前高（没回到就算到末尾并标注）
    i = int(dd.values.argmin())
    回本, 回本到了 = np.nan, False
    tgt = float(peak.iloc[i])
    after = nav.iloc[i:]
    hit = after[after >= tgt]
    if len(hit):
        回本 = int(nav.index.get_loc(hit.index[0]) - i); 回本到了 = True
    else:
        回本 = int(len(nav) - 1 - i)
    # ★★ 溃疡指数：回撤深度的均方根（★ 同时惩罚「多深」和「套多久」，Martin & McCann 1989）
    ulcer = float(np.sqrt((dd ** 2).mean()))
    return {
        "年化收益pct": round(ann * 100, 3),
        "年化波动pct": round(vol * 100, 3),
        "夏普": (round(sharpe, 3) if np.isfinite(sharpe) else None),
        "最大回撤pct": round(mdd * 100, 2),
        "回本天数": 回本,
        "★回本了吗": 回本到了,
        "卡玛比率": (round(ann / abs(mdd), 3) if mdd < 0 else None),
        "溃疡指数pct": round(ulcer * 100, 3),
        "交易日数": int(len(r)),
    }


def 回归(y: pd.Series, x: pd.Series, lags: int = 5) -> dict:
    """★★★ 对 SPY 回归：y = alpha + beta·x。★ t 值做 **Newey-West** 自相关调整。"""
    d = pd.concat([y, x], axis=1).dropna()
    if len(d) < 60:
        return {"★算不出": f"重合只有 {len(d)} 天"}
    Y = d.iloc[:, 0].to_numpy(float)
    X = np.column_stack([np.ones(len(d)), d.iloc[:, 1].to_numpy(float)])
    XtXi = np.linalg.pinv(X.T @ X)
    b = XtXi @ (X.T @ Y)
    e = Y - X @ b
    S = (X * e[:, None]).T @ (X * e[:, None])
    for L in range(1, lags + 1):
        w = 1.0 - L / (lags + 1.0)
        A = (X[L:] * e[L:, None]).T @ (X[:-L] * e[:-L, None])
        S += w * (A + A.T)
    V = XtXi @ S @ XtXi
    se = np.sqrt(np.diag(V))
    return {
        "★★★alpha_年化pct": round(float(b[0]) * 252 * 100, 3),
        "★★alpha的t值_NeweyWest": round(float(b[0] / se[0]), 2) if se[0] > 0 else None,
        "beta": round(float(b[1]), 3),
        "★信息比率_年化": (round(float(e.mean() / e.std(ddof=1) * np.sqrt(252)), 3)
                      if e.std(ddof=1) > 0 else None),
        "重合交易日": int(len(d)),
        "★NeweyWest滞后阶数": lags,
    }


def 一条(p: str, rf) -> dict | None:
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
    eq, 敞口, 缺票 = 逐日(d)
    if eq is None:
        return {"★跑失败": "面板里没有这条臂的任何票"}
    r = eq.pct_change()
    s = spy().reindex(eq.index).ffill()
    rs = s.pct_change()
    同敞口 = rs * 敞口.shift(1)        # ★★★ 把 SPY 按我们**前一日收盘**的敞口缩放
    return {
        "①笔数": int(len(d)),
        "★面板里缺的票数": 缺票,
        "★★平均敞口pct": round(float(敞口.mean()) * 100, 1),
        "★★★敞口峰值pct": round(float(敞口.max()) * 100, 1),
        "②策略": 指标(r, rf),
        "③同敞口指数（★ 同样的钱、同样的日子、同样的仓位重）": 指标(同敞口, rf),
        "④满仓指数（★ 一直满仓 SPY）": 指标(rs, rf),
        "⑤对同敞口指数回归": 回归(r, 同敞口),
        "⑥对满仓指数回归": 回归(r, rs),
    }


def main() -> int:
    rf = 无风险日()
    报 = {"★这把尺子": {
        "量什么": "★★★ **组合的日收益** —— ★ 不是每笔，也不是每笔÷天数",
        "为什么要它": ["每笔差：2 天的笔和 60 天的笔算一样权重，不公平",
                   "★★★ 每天差（每笔÷天数）：**按持有期系统性压扁一侧** —— "
                   "实测融-1 全部笔每笔差 +0.011%（基本是零），每天差均值 +0.452%，**造假正数**",
                   "利润因子：对持有期敏感、不看回撤"],
        "出处": "★★ Gemini 第 44 轮原话：「都按**每天的组合净值**算」（⑤档·待核）",
        "两个口径": {"同敞口": "★ 把 SPY 日收益按我们当天**实际敞口**缩放 —— "
                          "答「同样的钱、同样的日子、同样的仓位重，改买指数会怎样」",
                  "满仓指数": "★ 和 100% 持有 SPY 比 —— 答「我不如一直满仓买指数吗」"},
        "无风险利率": ("DGS3MO（★ 第 41 轮已定：债券等价口径）" if rf is not None
                  else "★★★ **找不到文件 → 夏普按 0% 算，已标注**"),
        "engine改动": "零",
    }}
    fs = sorted(glob.glob("probe/挂闸_1106/ledgers_1106/REAL__*.csv")) + \
         sorted(glob.glob("probe/新策略_1106/**/REAL__融-*.csv", recursive=True))
    失败 = 0
    for f in fs:
        名 = os.path.basename(f)[6:-4]
        try:
            r = 一条(f, rf)
        except Exception as e:
            r = {"★跑失败": repr(e)[:200]}
        if r:
            报[名] = r
            if "★跑失败" in r:
                失败 += 1
                print("⚠ 失败", 名, r["★跑失败"][:100], flush=True)
            else:
                print("✓", 名, flush=True)
    报["★★★失败条数"] = 失败
    os.makedirs(OUT, exist_ok=True)
    with open(os.path.join(OUT, "组合日收益_报告_1107.json"), "w",
              encoding="utf-8") as fh:
        json.dump(报, fh, ensure_ascii=False, indent=1)
    print(f"★ 写完;★★★ 失败 {失败} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
