# -*- coding: utf-8 -*-
"""
★★★ 挂件测试台 · 公共零件（B 路 1106）

大白话:**同一批进场,装与不装挂件,逐笔配对比。** 买点被完全按住,剩下只有「卖」在变。

★ 做法(Gemini 第 45 轮 + 《83》第六步):
  ① 同一个宿主策略,先跑「不装」(原样),再跑「装上某个挂件」
  ② ★★★ 只取两边**都有**的进场(键 = 票|进场日)→ 买点完全控住
  ③ 逐笔配对差;★★ 显著性两种都报:按**进场日聚类**的 t,和**按月块重抽样**的置信区间
  ④ ★★★ 另报:**误杀率**(被挂件提前砍掉的单子里,不装本来会赚的占多少)
     和**在场时间比例**(装了之后持有天数 ÷ 不装的持有天数;以及整条净值曲线的平均仓位)
  ⑤ 判据之二:**大盘替身**(同钱同进同出买 SPY)—— 装/不装两边各算一次,再配对差

★★★ 硬规矩:engine/ 零改动 —— 全部是进程内覆盖层(照抄 probe/新策略_1106/跑新策略_1106.py)。
★★ 只用研发池;留出池断言一笔不许进。考卷 1,042 只在新池烤的时候就已排除。
★★★ 不跑「赢随机」(已作废)—— 所以直接调 chain.run_chain,不经过 run_one。
"""
from __future__ import annotations
import copy, hashlib, io, json, os, sys, time
import numpy as np, pandas as pd, yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "v2_rerun_1030"))
os.chdir(ROOT)

from engine import cache, data, pool_scope, matrices, chain       # noqa: E402
import rerun_core_1030 as RC                                      # noqa: E402
from engine import pat6_ops                                       # noqa: E402

NEWPANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
NEWPOOL = "probe/newpool_1106/pool_NEWPOOL_ALL_1106.csv"
HOLD = "probe/新策略_1106/holdout_newpool_1106.json"
SCOPE = "large_mid"           # ★ 和 run_friction_1104 / 挂闸_1106 同口径

_装过 = {}


def 装覆盖层() -> dict:
    """★★★ 四个覆盖点(和 跑新策略_1106.py 一模一样)。返回自证信息。"""
    if _装过:
        return _装过
    pat6_ops.install()                       # ★ pat6 零件是运行时挂钩;非 pat6 类型原样转回
    if not os.path.exists(NEWPANEL):
        raise RuntimeError(f"★★★ 新池面板不在:{NEWPANEL} —— 先跑 probe/newpool_1106/烤新池_1106.py(约 55 秒)")
    wide = pd.read_parquet(NEWPANEL)
    cache._PANEL = {f: wide[f] for f in wide.columns.levels[0]}
    del wide
    idx = pool_scope.PoolIndex(path=NEWPOOL)
    RC._IDX_CACHE["idx"] = idx
    data.PERF_START = "2015-01-01"
    hold = json.load(io.open(HOLD, encoding="utf-8"))
    dev = hold["研发池名单"]
    hs = set(hold["留出池名单"])
    assert not (set(dev) & hs), "★ 研发/留出有交集,停"
    _装过.update({
        "面板只数": int(cache._PANEL["close"].shape[1]),
        "PERF_START": data.PERF_START, "PERF_END": data.PERF_END,
        "研发池只数": len(dev), "留出池只数": len(hs), "池子口径": SCOPE,
        "_dev": dev, "_hold": hs,
    })
    return _装过


def 读配置(path: str) -> dict:
    return yaml.safe_load(io.open(path, encoding="utf-8"))


def 建矩阵(raw: dict):
    """★ 一个宿主建一次矩阵;挂件只改 trailing_stop / exit.params → 不影响矩阵,可复用。"""
    env = 装覆盖层()
    cfg = chain.ChainConfig.from_dict(copy.deepcopy(raw))
    m = matrices.build(cfg.raw, env["_dev"])
    diag = RC.apply_scope(m, SCOPE)
    return m, diag


def 跑(raw: dict, m) -> tuple[pd.DataFrame, dict]:
    env = 装覆盖层()
    cfg = chain.ChainConfig.from_dict(copy.deepcopy(raw))
    res = chain.run_chain(cfg, env["_dev"], data.PERF_START, data.PERF_END, m=m)
    led = res.ledger.copy()
    if len(led):
        leaked = sorted(set(led["symbol"].astype(str)) & env["_hold"])
        if leaked:
            raise RuntimeError(f"★★★ 留出池漏进来了 {len(leaked)} 只:{leaked[:10]}")
    eq = res.equity
    info = {
        "笔数": int(len(led)),
        "平均仓位(净值曲线敞口均值)": round(float(res.exposure.mean()), 4),
        "期末净值倍数": round(float(eq.iloc[-1] / res.initial_equity), 4),
        "最大回撤": round(float((eq / eq.cummax() - 1).min()), 4),
        "离场原因计数": led["reason"].value_counts().to_dict() if len(led) else {},
    }
    return led, info


# ═════════════════════════ 挂件定义(★ 只改 trailing_stop / exit.params) ═════════════════════════
# ★★ 为什么吊灯和唐奇安都用 staged 单级(when 空 = 每天生效)而不用顶层 type:
#   顶层 chandelier 的原始值是 matrices.build 时按配置预算的 —— 换倍数就得重建矩阵;
#   staged 单级走 chain._chandelier_at 现算(同一公式:近 N 日最高价 − k×ATR),
#   ★ 矩阵可复用,一个宿主只建一次。两条铁律(不高于当根收盘、只许上移)两边一样。
#   ★★ 顶层 lowest_low_trail 执行器里**没有分支**(chain.py 只认 chandelier / staged),
#     所以唐奇安低点止损**只能**用 staged 写 —— 写顶层会被静默忽略(已读代码确认)。

def 装吊灯(raw: dict, k: float, lookback: int = 22) -> dict:
    d = copy.deepcopy(raw)
    ts = d.get("trailing_stop") or {}
    if (ts.get("type") or "none") != "none":
        raise ValueError(f"★ 宿主已有移动止损 {ts.get('type')} —— 装挂件会变成「替换」不是「加装」,停")
    d["trailing_stop"] = {"type": "staged", "stages": [{
        "name": f"挂件·吊灯{k}ATR", "when": {}, "type": "chandelier",
        "params": {"lookback": lookback, "multiple": float(k)},
        "source": "⑤外部模型说的·待核(Gemini 第45轮;吊灯原始定义 Chuck LeBeau,22 日/3ATR 为惯例)"}]}
    return d


def 装唐奇安低点(raw: dict, n: int) -> dict:
    d = copy.deepcopy(raw)
    ts = d.get("trailing_stop") or {}
    if (ts.get("type") or "none") != "none":
        raise ValueError(f"★ 宿主已有移动止损 {ts.get('type')},停")
    d["trailing_stop"] = {"type": "staged", "stages": [{
        "name": f"挂件·唐奇安{n}日低点", "when": {}, "type": "lowest_low_trail",
        "params": {"lookback": int(n)},
        "source": "⑤外部模型说的·待核(Gemini 第45轮;海龟 10/20 日反向通道)"}]}
    return d


def 装时间止损(raw: dict, n: int) -> dict:
    d = copy.deepcopy(raw)
    ex = d.setdefault("exit", {})
    p = ex.setdefault("params", {}) or {}
    if p.get("time_stop_days") is not None:
        raise ValueError(f"★ 宿主已有时间止损 {p.get('time_stop_days')},停")
    p["time_stop_days"] = int(n)
    ex["params"] = p
    return d


# ═════════════════════════ 配对比 ═════════════════════════
def _键(led: pd.DataFrame) -> pd.DataFrame:
    d = led.copy()
    d["entry_date"] = pd.to_datetime(d["entry_date"])
    d["exit_date"] = pd.to_datetime(d["exit_date"])
    d["ret"] = d["net_pnl"].astype(float) / d["notional_in"].astype(float)
    d["键"] = d["symbol"].astype(str) + "|" + d["entry_date"].dt.strftime("%Y-%m-%d")
    n0 = len(d)
    d = d.drop_duplicates("键", keep="first").set_index("键")
    d.attrs["丢重复"] = n0 - len(d)
    return d


_SPY = None


def spy():
    global _SPY
    if _SPY is None:
        _SPY = data.load_benchmark("SPY")["close"].dropna()
    return _SPY


def 替身收益(d: pd.DataFrame) -> pd.Series:
    """★ 大盘替身:同进场日、同离场日买 SPY(口径照抄 probe/大盘替身_1106:收盘对收盘,不扣摩擦)。"""
    s = spy(); idx = s.index
    i = idx.searchsorted(d["entry_date"].values)
    j = idx.searchsorted(d["exit_date"].values)
    ok = (i < len(idx)) & (j < len(idx)) & (j > i)
    out = np.full(len(d), np.nan)
    v = s.to_numpy()
    out[ok] = v[j[ok]] / v[i[ok]] - 1.0
    return pd.Series(out, index=d.index)


def 聚类t(diff: pd.Series, 日: pd.Series) -> dict:
    g = diff.groupby(日.values).mean().dropna()
    nd = len(g)
    m = float(diff.mean())
    se = float(g.std(ddof=1) / np.sqrt(nd)) if nd >= 3 else np.nan
    t = m / se if np.isfinite(se) and se > 0 else np.nan
    return {"均值": m, "聚类标准误": se, "聚类数": nd, "t": t}


def 块重抽样(diff: pd.Series, 日: pd.Series, n_boot: int = 2000, seed: int = 7) -> dict:
    """★★ 按**进场月份**分块重抽样(块 = 一个日历月里进场的全部笔)。
    ★ 理由:同一天/同一周的笔受同一段行情影响,不独立;按月成块把这层相关整块保留。
    ★ 统计量 = 全部笔的配对差均值(按笔加权,与报告的点估计一致)。"""
    月 = pd.to_datetime(日.values).to_period("M")
    df = pd.DataFrame({"d": diff.values, "m": 月})
    sums = df.groupby("m")["d"].agg(["sum", "count"])
    S, C = sums["sum"].to_numpy(), sums["count"].to_numpy()
    nb = len(S)
    if nb < 6:
        return {"块数": nb, "95%区间": None, "说明": "块数 < 6,不做"}
    rng = np.random.default_rng(seed)
    pick = rng.integers(0, nb, size=(n_boot, nb))
    bs = S[pick].sum(1) / C[pick].sum(1)
    lo, hi = np.percentile(bs, [2.5, 97.5])
    return {"块数": nb, "95%区间": [float(lo), float(hi)],
            "区间不含0": bool(lo > 0 or hi < 0)}


def 判(t, 区间不含0) -> str:
    if not np.isfinite(t):
        return "★算不出"
    if abs(t) > 2 and 区间不含0:
        return "★ 正且显著(两种检验都过)" if t > 0 else "负且显著(两种检验都过)"
    if abs(t) > 2 or 区间不含0:
        return "🟡 只过一种检验 —— 不算数"
    return "★★★ 测不出（在噪声里）"


def 配对比(base: pd.DataFrame, arm: pd.DataFrame, 挂件原因: str) -> dict:
    A, B = _键(base), _键(arm)
    共 = A.index.intersection(B.index)
    out = {"不装_笔数": int(len(A)), "装_笔数": int(len(B)),
           "★★共同进场笔数": int(len(共)),
           "共同占不装的比例": round(len(共) / max(1, len(A)), 4),
           "同票同日重复被丢": [A.attrs["丢重复"], B.attrs["丢重复"]]}
    if len(共) < 30:
        out["★算不出"] = f"共同进场只有 {len(共)} 笔"
        return out
    a, b = A.loc[共], B.loc[共]
    日 = a["entry_date"].dt.strftime("%Y-%m-%d")

    # ① 每笔净收益率(已扣摩擦)配对差
    d1 = (b["ret"] - a["ret"]).dropna()
    c1 = 聚类t(d1, 日.loc[d1.index]); b1 = 块重抽样(d1, 日.loc[d1.index])
    # ② 大盘替身差 配对差:(装的那笔 − 同期SPY) − (不装那笔 − 同期SPY)
    sa, sb = 替身收益(a), 替身收益(b)
    xa, xb = a["ret"] - sa, b["ret"] - sb
    d2 = (xb - xa).dropna()
    c2 = 聚类t(d2, 日.loc[d2.index]); b2 = 块重抽样(d2, 日.loc[d2.index])
    # ③ 每笔净R(只在两边都有 R 时)
    d3 = (b["r_multiple_net"].astype(float) - a["r_multiple_net"].astype(float)).dropna()

    # ★★★ 误杀率:装了之后**因挂件**离场、且离场比不装更早的那些笔
    砍 = (b["reason"].astype(str).str.contains(挂件原因)) & (b["exit_date"] < a["exit_date"])
    n砍 = int(砍.sum())
    误杀 = {"被挂件提前砍掉的笔数": n砍,
          "占共同进场": round(n砍 / len(共), 4)}
    if n砍:
        aa, bb = a.loc[砍], b.loc[砍]
        误杀.update({
            "★★误杀率(不装本来会赚的占比)": round(float((aa["ret"] > 0).mean()), 4),
            "砍掉后反而更差的占比(不装>装)": round(float((aa["ret"] > bb["ret"]).mean()), 4),
            "这些笔:不装平均收益pct": round(float(aa["ret"].mean()) * 100, 3),
            "这些笔:装了平均收益pct": round(float(bb["ret"].mean()) * 100, 3),
        })
    hd_a, hd_b = float(a["holding_days"].sum()), float(b["holding_days"].sum())

    def pct(x):
        return None if not np.isfinite(x) else round(x * 100, 4)

    out.update({
        "①每笔净收益率": {
            "不装pct": pct(float(a["ret"].mean())), "装pct": pct(float(b["ret"].mean())),
            "★差pct": pct(c1["均值"]), "聚类标准误pct": pct(c1["聚类标准误"]),
            "聚类数(进场日)": c1["聚类数"], "t": round(c1["t"], 2) if np.isfinite(c1["t"]) else None,
            "按月块重抽样95%区间pct": ([round(x * 100, 4) for x in b1["95%区间"]]
                                if b1.get("95%区间") else None),
            "块数": b1["块数"],
            "★★★判定": 判(c1["t"], b1.get("区间不含0", False)),
        },
        "②大盘替身差(装 减 不装)": {
            "不装_比SPYpct": pct(float(xa.mean())), "装_比SPYpct": pct(float(xb.mean())),
            "★差pct": pct(c2["均值"]), "t": round(c2["t"], 2) if np.isfinite(c2["t"]) else None,
            "按月块重抽样95%区间pct": ([round(x * 100, 4) for x in b2["95%区间"]]
                                if b2.get("95%区间") else None),
            "★★★判定": 判(c2["t"], b2.get("区间不含0", False)),
        },
        "③每笔净R差": round(float(d3.mean()), 4) if len(d3) else None,
        "★★误杀": 误杀,
        "★★在场时间": {
            "持有天数合计_不装": int(hd_a), "持有天数合计_装": int(hd_b),
            "★装÷不装": round(hd_b / hd_a, 4) if hd_a else None,
            "平均持有天_不装": round(float(a["holding_days"].mean()), 2),
            "平均持有天_装": round(float(b["holding_days"].mean()), 2),
        },
        "利润因子(共同进场·净盈亏)": {
            "不装": _pf(a), "装": _pf(b)},
    })
    return out


def _pf(d):
    p = d["net_pnl"].astype(float)
    w, l = p[p > 0].sum(), -p[p < 0].sum()
    return round(float(w / l), 3) if l > 0 else None


def 臂文件(目录: str, label: str) -> str:
    h = hashlib.sha256(label.encode("utf-8")).hexdigest()[:16]
    return os.path.join(目录, f"arm_{h}.csv.gz")


def 流水哈希(led: pd.DataFrame) -> str:
    """★ 规矩⑪:按规则内容去重 —— 流水哈希相同 = 同一个版本。"""
    cols = ["symbol", "entry_date", "exit_date", "exit_price"]
    s = led[cols].astype(str).to_csv(index=False) if len(led) else ""
    return hashlib.sha256(s.encode()).hexdigest()[:12]
