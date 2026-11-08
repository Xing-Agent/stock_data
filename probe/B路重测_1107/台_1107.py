# -*- coding: utf-8 -*-
"""
★★★ B 路《100》公共零件 —— 并池 3,834 只 × 2016-01-04~2025-12-31

  ① 装池：并池面板 + ★ 我重建的排名表（老表里没有新并进来的 1,027 只，见 自证_池表漏票_1107.json）
           + 可买名单 = 面板全部 + PERF_START 2016-01-04；跑前自证「可买几只 / 面板几只 / 巨头筛完还有几天」
  ② 环境 2×2 覆盖层：新环境规则 b_spy_2x2（标普 200 日线 × 标普实际波动 vs 过去一年中位数）
     ★★★ engine 零改动：替换 matrices.regime_mask 的函数指针，认不出的规则原样转给原函数；
       ★ 我的那条规则**也做 shift(1)**（和原函数末行 `ok.shift(1)` 同一条路 = 用昨收）
  ③ 随机对照（规矩㊸）三种「把被比较的旋钮随机化」：
     · 环境闸 → 把真实「关闸日」序列整体**随机平移**（段长、段数、关闸天数一模一样，只是挪到别的日子）
     · 挂件   → **随机砍单**：每个持仓日按概率 p 随机给出离场信号，p 调到「被提前砍掉的笔数」和真挂件一样多
     · 环境卡调仓位 → 把「减半」那一档的标签**按月成块打乱**（减半的笔数比例不变）
     · 另：排序随机 10 个种子，量这条宿主自己的单次噪声（和主路 0.0713 同一种量法）
"""
from __future__ import annotations
import copy, hashlib, io, json, os, sys, time
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "v2_rerun_1030"))
os.chdir(ROOT)
from engine import cache, data, pool_scope, matrices, chain, config_adapter, pat6_ops   # noqa: E402
import rerun_core_1030 as RC                                                           # noqa: E402

# ★ 窗口由环境变量 B窗 选:2004(默认,22 年面板,《96》2016 那条已作废)或 2016(第一版,留作对照)
窗 = os.environ.get("B窗", "2004")
if 窗 == "2016":
    PANEL = "probe/并池_1107/ohlcv_panel_newpool.parquet"
    POOL = "probe/B路重测_1107/pool_并池3834_1107.csv"
    START = "2016-01-04"
else:
    PANEL = "probe/并池2004_1107/ohlcv_panel_newpool.parquet"
    POOL = "probe/B路重测_1107/pool_并池2004_1107.csv"
    START = "2004-01-02"
END = "2025-12-31"
SCOPE = "large_mid"
巨头 = ["AAPL", "MSFT", "AMZN", "JPM", "BRK.B", "NVDA"]
_env = {}


# ═════════════════════════ ① 装池 ═════════════════════════
def 装池() -> dict:
    if _env:
        return _env
    pat6_ops.install()
    装环境覆盖层()
    sys.path.insert(0, os.path.join(ROOT, "probe", "并池_1107"))
    import 接新基准_1107 as BM                      # ★ 主路的覆盖层:SPY 等基准读到 2004 起
    _env["★基准覆盖层"] = BM.install()
    wide = pd.read_parquet(PANEL)
    cache._PANEL = {f: wide[f] for f in wide.columns.levels[0]}
    del wide
    RC._IDX_CACHE["idx"] = pool_scope.PoolIndex(path=POOL)
    data.PERF_START = START
    data.PERF_END = END
    syms = sorted(cache._PANEL["close"].columns)
    _env.update({"窗": 窗, "面板只数": len(syms), "★可买名单只数": len(syms), "池表": POOL,
                 "窗口": f"{data.PERF_START} ~ {data.PERF_END}", "口径": SCOPE,
                 "_syms": syms})
    return _env


def 自证巨头(m) -> dict:
    pos = {s: j for j, s in enumerate(m.symbols)}
    u = np.asarray(m.universe)
    i0 = m.index.searchsorted(pd.Timestamp(START))
    return {s: int(u[i0:, pos[s]].sum()) if s in pos else None for s in 巨头}


def 读配置(path):
    import yaml
    return yaml.safe_load(io.open(path, encoding="utf-8"))


def 建矩阵(raw):
    env = 装池()
    cfg = chain.ChainConfig.from_dict(copy.deepcopy(raw))
    m = matrices.build(cfg.raw, env["_syms"])
    前 = 自证巨头(m)
    diag = RC.apply_scope(m, SCOPE)
    后 = 自证巨头(m)
    diag["★巨头大中盘筛前→筛后可买天数"] = {s: [前[s], 后[s]] for s in 巨头}
    diag["★巨头大中盘筛完后可买天数"] = 后
    # ★ 判据:大中盘这道筛不许砍掉巨头(筛后 ≥ 筛前的 99%);策略自己的选股条件砍掉多少不归这里管
    坏 = {s: v for s, v in diag["★巨头大中盘筛前→筛后可买天数"].items() if not v[0] or v[1] < 0.99 * v[0]}
    if 坏:
        raise RuntimeError(f"★★★ 大中盘筛把巨头砍掉了:{坏} —— 停")
    return m, diag


def 跑(raw, m):
    env = 装池()
    cfg = chain.ChainConfig.from_dict(copy.deepcopy(raw))
    res = chain.run_chain(cfg, env["_syms"], data.PERF_START, data.PERF_END, m=m)
    eq = res.equity
    yrs = (eq.index[-1] - eq.index[0]).days / 365.25
    info = {"笔数": int(len(res.ledger)),
            "平均仓位": round(float(res.exposure.mean()), 4),
            "期末净值倍数": round(float(eq.iloc[-1] / res.initial_equity), 4),
            "年化": round(float((eq.iloc[-1] / res.initial_equity) ** (1 / yrs) - 1), 4),
            "最大回撤": round(float((eq / eq.cummax() - 1).min()), 4)}
    return res.ledger.copy(), info, res


def 基准(res) -> dict:
    """★ 三个基准里能算的两个:① 满仓标普买入持有 ③ 同敞口标普(每天按策略当天仓位比例持有标普)。
    ② 自己赛道买入持有 —— 本批没做(成分要按硬条件每季重定,工作量另算),如实写「没做」。"""
    eq = res.equity; idx = eq.index
    spy = data.load_benchmark("SPY")["close"].reindex(idx).ffill()
    r = spy.pct_change().fillna(0)
    yrs = (idx[-1] - idx[0]).days / 365.25
    bh = float(spy.iloc[-1] / spy.iloc[0])
    ex = pd.Series(res.exposure, index=idx).shift(1).fillna(0)
    same = float((1 + ex * r).prod())
    me = float(eq.iloc[-1] / res.initial_equity)
    return {"策略年化": round(me ** (1 / yrs) - 1, 4),
            "①满仓标普年化": round(bh ** (1 / yrs) - 1, 4),
            "③同敞口标普年化": round(same ** (1 / yrs) - 1, 4),
            "②自己赛道": "★没做(本批)"}


# ═════════════════════════ ② 环境 2×2 ═════════════════════════
_orig_regime = None


def 二乘二(index, ma=200, vol_lb=20, med_lb=252) -> pd.DataFrame:
    """★ 未平移(t 行 = 用 t 日收盘算)。返回 DataFrame[线上, 高波动, 档]。"""
    s = data.load_benchmark("SPY")["close"].dropna()
    above = s > s.rolling(ma, min_periods=ma).mean()
    rv = np.log(s).diff().rolling(vol_lb, min_periods=vol_lb).std()
    med = rv.rolling(med_lb, min_periods=med_lb).median()
    hi = rv > med
    ok = s.rolling(ma, min_periods=ma).mean().notna() & med.notna()
    档 = np.where(~ok, "未定", np.where(above & ~hi, "顺风", np.where(above & hi, "震荡放大",
                 np.where(~above & ~hi, "阴跌", "暴跌"))))
    df = pd.DataFrame({"线上": above, "高波动": hi, "档": 档}, index=s.index)
    return df.reindex(index).ffill()


def _regime(spec, index, *a, **k):
    spec = spec or {}
    mine = [r for r in (spec.get("rules") or []) if r.get("type") == "b_spy_2x2"]
    others = {**spec, "rules": [r for r in (spec.get("rules") or []) if r.get("type") != "b_spy_2x2"]}
    ok = _orig_regime(others, index, *a, **k)
    for r in mine:
        p = r.get("params") or {}
        for key in ("ma", "vol_lb", "med_lb", "off_cells"):
            if key not in p:
                raise ValueError(f"b_spy_2x2 缺参数 {key} —— 不给默认值")
        d = 二乘二(index, int(p["ma"]), int(p["vol_lb"]), int(p["med_lb"]))
        mine_ok = ~d["档"].isin(list(p["off_cells"]))
        ok = ok & mine_ok.shift(1, fill_value=False).fillna(False).astype(bool)   # ★ 同一条路:昨收
    return ok


def 装环境覆盖层():
    global _orig_regime
    if _orig_regime is None:
        _orig_regime = matrices.regime_mask
        matrices.regime_mask = _regime
        config_adapter.IMPLEMENTED["regime"] |= {"b_spy_2x2"}


def 覆盖层自证() -> dict:
    return {"matrices.regime_mask 已换成覆盖层": matrices.regime_mask is _regime,
            "原函数保留可转回": _orig_regime is not None and _orig_regime is not _regime,
            "b_spy_2x2 已登记": "b_spy_2x2" in config_adapter.IMPLEMENTED["regime"]}


def 加闸(raw, ma=200, vol_lb=20, med_lb=252, off=("暴跌",)):
    d = copy.deepcopy(raw)
    rg = d.get("regime") or {}
    if rg.get("rules"):
        raise ValueError("★ 宿主本来就有环境闸 —— 加闸会变成叠加,停")
    d["regime"] = {"rules": [{"type": "b_spy_2x2",
                              "params": {"ma": ma, "vol_lb": vol_lb, "med_lb": med_lb, "off_cells": list(off)},
                              "source": "《98》2.1 / 《100》3.1 定的唯一定义;暴跌档切国债(=空仓) Antonacci 2014 双动量 ⑤待核;"
                                        "门槛相邻三点 ③"}],
                   "flatten_when_off": True,
                   "source": "暴跌档=空仓(切短期国债;现金不计利息,对我们不利的一侧)"}
    return d


# ═════════════════════════ ③ 随机对照 ═════════════════════════
def 随机平移(regime: np.ndarray, seed: int, start_i: int) -> np.ndarray:
    """★ 把窗口内的「关闸日」序列整体循环平移一个随机量(段数、段长、天数全不变)。"""
    r = regime.copy()
    seg = r[start_i:]
    rng = np.random.default_rng(seed)
    k = int(rng.integers(60, max(61, len(seg) - 60)))
    r[start_i:] = np.roll(seg, k)
    return r


def 随机砍单矩阵(shape, p, seed) -> np.ndarray:
    rng = np.random.default_rng(seed)
    return rng.random(shape) < p


def 求p(holding_days: np.ndarray, 目标砍掉比例: float) -> float:
    """★ 每个持仓日以概率 p 给离场信号 → 一笔持有 h 天被提前砍掉的概率 ≈ 1-(1-p)^(h-1)。
    解 p 使平均砍掉比例 = 目标。"""
    h = np.maximum(holding_days.astype(float) - 1, 0)
    lo, hi = 0.0, 1.0
    for _ in range(60):
        mid = (lo + hi) / 2
        if np.mean(1 - (1 - mid) ** h) < 目标砍掉比例:
            lo = mid
        else:
            hi = mid
    return (lo + hi) / 2


def 随机排序(m, seed):
    rng = np.random.default_rng(seed)
    m.rank_score = rng.random(np.asarray(m.rank_score).shape)


def 每笔(led) -> dict:
    if len(led) == 0:
        return {"笔数": 0}
    rn = led["r_multiple_net"].astype(float)
    ret = led["net_pnl"].astype(float) / led["notional_in"].astype(float)
    return {"笔数": int(len(led)), "每笔净R": round(float(rn.mean()), 4),
            "每笔净收益pct": round(float(ret.mean()) * 100, 4),
            "净盈亏": round(float(led["net_pnl"].sum()), 0)}


def 噪声判(真, 随机: list) -> dict:
    """★★★ 规矩㊸ v2 + ㊾(1108 换):不再用「均值 ± 标准差」—— 随机分布是偏的。
    ★ 直接调主路的 probe/尺子v2_1107/尺子v2_1107.py 随机对照_分位数()(不另写一套):
      经验分位数 95% 范围 + 经验 p + 偏度;旧的「按标准差」判法也并排留着,打架时以分位数为准。
    ★★ 「★判」字段 = 分位数判法;随机次数 < 100 → 算不出(规矩㊸ v2)。"""
    sys.path.insert(0, os.path.join(ROOT, "probe", "尺子v2_1107"))
    import 尺子v2_1107 as R2
    r = R2.随机对照_分位数(真, 随机)
    r["★判"] = r.get("★★★②新判法_按分位数") or r.get("★★★判") or r.get("★算不出")
    # ★ 旧字段名保留(汇总脚本在用)
    r["真"] = r.get("实测"); r["距随机几个标准差"] = r.get("距随机几个标准差")
    return r


def 臂文件(目录, label):
    return os.path.join(目录, "a_" + hashlib.sha256(label.encode()).hexdigest()[:16] + ".csv.gz")
