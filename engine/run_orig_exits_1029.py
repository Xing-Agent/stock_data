"""
原著离场规则落地并重跑 —— 2026-10-29。

三秒版:我们一直只实现了「怎么买」,没实现「怎么卖」。这一轮把原著写死的
离场规则装上,然后回答**一个**问题:
  ★ 装上原著离场后,那个「选股 +77~95% → 完整链 −2~−12%」的形状会不会翻正?

所以每条链都给三个并排的数:
  ① 买入持有            —— 全池等权买了就不动
  ② 过完选股后持有      —— ★ 用这条链真正的扳机选出票,买了就不动(不设任何止损/离场)
  ③ 完整链(含新离场)  —— 七步全开
★ 这三个数并排,就是整件事的判据。

★★ 硬纪律(照任务书,一条不变通):
  1. 新配置,不覆盖旧配置 —— 新文件名带「原著」,旧的留着对照。
  2. 三版并跑:原著给区间的(技-10 的 2~5 天)跑严格端/中值/宽松端三组;
     原著没写死的地方**不许我们填**,在报告里写「原著未给出可执行阈值」——
     ★ 这个「跑不了」本身就是产出,由 _unrunnable() 从配置里直接读出来,不手写。
  3. 集中度必须报;★ 但盈利笔数 < 10 时不报集中度(它恒等于 100%),改报胜率。
  4. 技-12 / 技-2 不用 R 计量(它们 risk_per_share ≈ entry_price)——
     ★ 本批没有这两条链,但照样对每条链实测 risk/entry 比并自动判定该用 R 还是 %。
  5. 按收盘价判定,★ 严禁用盘中最高价(算子层面保证,见 ops_exits_1029.py)。
  6. ★ 串行跑,单进程。跑之前打印 free,每条链之后打印峰值 RSS。
  7. 五条基准线都要算(同环境随机 / 同等仓位大盘 / 动态开关 / 槽位机会成本 /
     朴素基准);★ 均值回归类走 benchmark.family: meanrev,不用单边多头指数。
  8. ★ 强制打印单种子极差,并和链效应比大小 —— 极差远大于效应时,
     报告里必须写「本轮 Z 的符号是噪声」。本脚本自动给出这句判定。
  9. YAML 不许有重复 key —— 一律走 ops_1029.load_yaml_strict()。
 10. git add 按文件显式列出(这条由人执行,脚本不碰 git)。

跑法:python3 -m engine.run_orig_exits_1029
"""

from __future__ import annotations

import copy
import json
import os
import resource
import subprocess
import time

import numpy as np

from . import (analyze, bench_lines, cache, chain, data, matrices, ops_1029,
               ops_a0, ops_exits_1029, pat6_ops, stats_gate)
from .bench_lines import _concentration
from .run_batch import _num, signal_funnel, window_pool_gate

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(HERE, "configs")
OUT_JSON = os.path.join(HERE, "results_1029_原著离场.json")
LEDGER_DIR = os.path.join(HERE, "ledgers_1029_原著离场")

MEM_CAP_MB = 1500.0


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _load(name: str) -> dict:
    return ops_1029.load_yaml_strict(os.path.join(CONFIG_DIR, name))


def _cache_provenance() -> dict:
    """commit hash + 读的是哪份缓存 + 缓存构建时间(报告模板必填栏)。"""
    out: dict = {}
    try:
        out["git_commit"] = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=os.path.dirname(HERE),
            capture_output=True, text=True, timeout=20).stdout.strip()
        out["git_工作树是否干净"] = (subprocess.run(
            ["git", "status", "--porcelain"], cwd=os.path.dirname(HERE),
            capture_output=True, text=True, timeout=20).stdout.strip() == "")
    except Exception as e:                                   # noqa: BLE001
        out["git_commit"] = f"拿不到:{e}"
    for name, path in (("价格缓存", cache.PANEL_PARQUET),
                       ("缓存元数据", cache.META_PARQUET)):
        try:
            st = os.stat(path)
            out[name] = path
            out[f"{name}_构建时间"] = time.strftime(
                "%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
            out[f"{name}_字节数"] = st.st_size
        except Exception as e:                               # noqa: BLE001
            out[name] = f"拿不到:{e}"
    out["说明"] = ("★ cache.py 把面板一次性读进模块级变量,进程启动后不再重读 —— "
                   "本批全部版本跑在同一份价格数据上。")
    return out


# ---------------------------------------------------------------- 覆盖函数

def _ts(days: int):
    """技-10:把时间止损改成 days 天(原著区间 2~5 的某一端)。"""
    def f(raw):
        for r in raw["exit"]["rules"]:
            if r["type"] == "time_stop":
                r["params"]["max_holding_days"] = int(days)
        raw["meta"]["name"] = f"技-10_海龟汤_原著离场_持仓{days}天"
        return raw
    return f


def _pb(x: float):
    """技-8:回调上限取原著区间 20–25% 的某一端。"""
    def f(raw):
        raw["entry"]["rules"][0]["params"]["max_pullback"] = float(x)
        raw["meta"]["name"] = f"技-8_高紧旗形HTF_时间止损20日_回调{x}"
        return raw
    return f


def _sys2(raw):
    """技-1:系统 2 = 55 日入场 / 20 日反向通道出场。"""
    raw["entry"]["rules"][0]["params"]["lookback"] = 55
    raw["entry"]["rules"][0]["source"] = (
        "原著(Faith 2003):系统 2 入场 = 55 日通道突破。"
        "★ 系统 2 原著本来就没有「上次突破是赢家就跳过」那个过滤器,"
        "所以这一档比 20 日那一档更接近原著。")
    for r in raw["exit"]["rules"]:
        if r["type"] == "close_below_lowest_low":
            r["params"]["lookback"] = 20
            r["source"] = ("★★ 原著离场:系统 2 退出 = 跌破过去 **20 日最低价** "
                           "全部平仓。★ 写成离场规则而不是移动止损 —— "
                           "原著的通道可以往下跑。")
    raw["meta"]["name"] = "技-1_原著_唐奇安反向通道离场_System2"
    return raw


def _cd13_entry(raw):
    """技-13:进场换成 Countdown 13(离场四条不动)。"""
    raw["entry"]["rules"][0] = {
        "type": "td_buy_countdown",
        "params": {"setup_count": 9, "ref_lag": 4, "countdown": 13, "cd_lag": 2},
        "source": ("流传最广版本:Setup 9 完成后开始数,close ≤ low[t−2] 记一个,"
                   "数到 13。★ 手册只给了「13」这个数,其余是流传版本。"
                   "★ 注意这是**进场**用的 Buy Countdown(close ≤ low[t−2]),"
                   "和离场① 的 Countdown 13(close ≥ high[t−2])方向相反。"),
    }
    raw["meta"]["name"] = "技-13_TD序列_原著四重离场_Countdown13进场"
    return raw


# ---------------------------------------------------------------------------
# 要跑的版本
#   (报表名, 配置文件, 覆盖函数, 这一版是什么, 分组, 是不是「装上原著离场」的那一版)
# ---------------------------------------------------------------------------
VARIANTS = [
    # ================= 技-13 TD 序列 · 四重离场 =================
    ("技-13 · ★原著四重离场 · Setup 9 进场",
     "技-13-原著-四重离场.yaml", None,
     "★ 本轮主角之一:Countdown 13 离场 + TD Price Flip + TD Risk Level 止损 + "
     "反向 Sell Setup 9,四条全装",
     "技-13", True),
    ("技-13 · ★原著四重离场 · Countdown 13 进场",
     "技-13-原著-四重离场.yaml", _cd13_entry,
     "同上四重离场,进场换成 Countdown 13 —— 和上一轮那 207 笔的那一档对齐",
     "技-13", True),
    ("技-13 · 旧实现对照 · Setup 9 进场(只有一条止损)",
     "技-13.yaml", None,
     "★ 对照组:上一轮的旧实现,离场只有「收盘跌破 9 根最低价」一条。"
     "★ 和上面同一份缓存同一天跑,所以差值只来自离场",
     "技-13", False),
    ("技-13 · 旧实现对照 · Countdown 13 进场(只有一条止损)",
     "技-13.yaml", _cd13_entry,
     "★ 对照组:上一轮那 207 笔的那一档", "技-13", False),

    # ================= 技-10 海龟汤 · 持仓 2~5 天 =================
    ("技-10 · ★原著离场 · 持仓 2 天(严格端)",
     "技-10-原著-持仓2至5天离场.yaml", None,
     "★ 原著给的是 2~5 天区间,这是严格端。止损改成新 20 日低点下方 1 tick",
     "技-10", True),
    ("技-10 · ★原著离场 · 持仓 3 天(中值)",
     "技-10-原著-持仓2至5天离场.yaml", _ts(3),
     "★ 同上,区间中值", "技-10", True),
    ("技-10 · ★原著离场 · 持仓 5 天(宽松端)",
     "技-10-原著-持仓2至5天离场.yaml", _ts(5),
     "★ 同上,区间宽松端", "技-10", True),
    ("技-10 · 旧实现对照(离场整条拿掉)",
     "技-10.yaml", None,
     "★ 对照组:上一轮那 123 笔的那一档,exit 里显式写着「原著的离场整条拿掉了」",
     "技-10", False),

    # ================= 技-8 高紧旗形 · 时间止损 20 日 =================
    ("技-8 · ★时间止损 20 日【行业做法】· 回调 20%(严格端)",
     "技-8-行业-时间止损20日.yaml", None,
     "★ 20 日时间止损标【行业普遍做法】,不是原著(赞格无出版专著)",
     "技-8", True),
    ("技-8 · ★时间止损 20 日【行业做法】· 回调 25%(宽松端)",
     "技-8-行业-时间止损20日.yaml", _pb(0.25),
     "★ 同上,回调上限取原著区间宽松端", "技-8", True),
    ("技-8 · 旧实现对照 · 回调 20%(无时间止损)",
     "技-8.yaml", None,
     "★ 对照组:上一轮那 26 笔、平均持仓 603.8 天的那一档", "技-8", False),

    # ================= 技-1 系统化趋势跟随 · 唐奇安反向通道 =================
    ("技-1 · ★原著离场 · System 1(20 日入 / 10 日反向通道出)",
     "技-1-原著-唐奇安反向通道离场.yaml", None,
     "★ 原著离场 = 前 N 日反向极值低点,不是 ATR 回撤。★ 加仓引擎做不到,单单位版",
     "技-1", True),
    ("技-1 · ★原著离场 · System 2(55 日入 / 20 日反向通道出)",
     "技-1-原著-唐奇安反向通道离场.yaml", _sys2,
     "★ 系统 2 原著无「上次突破是赢家就跳过」过滤器 —— 这一档更接近原著",
     "技-1", True),
    ("①趋势跟随 · ★原著离场与原著仓位(20 日反向通道 + 无移动止损 + 单笔 2%)",
     "trend_following-原著-唐奇安反向通道离场.yaml", None,
     "★★ 2026-10-31 新增。trend_following.yaml 署名海龟,但三处自称「原著」的部件"
     "都不是原著:⑥ 离场装 MA50(一条唐奇安反向通道都没有)、⑤ 装了原著没有的"
     "吊灯移动止损、⑦ 单笔风险 0.01 = 原著的一半(把「1 单位 = 1%/N」这个公式的"
     "分子当成了单笔风险)。这一档把**这三处**改回原著,其余(universe / regime / "
     "atr_squeeze / 2.5×ATR / slots)一律原样保留 —— 它们标的是行业惯例,"
     "是专家给的数,动它们属于换参数。★ 所以这一档不是完整的海龟原著",
     "技-1", True),
    ("技-1 · ★★装错的那一版对照:trend_following(吊灯 3ATR + MA50)",
     "trend_following.yaml", None,
     "★★ 这是我们**真正在跑**的那条链 —— 离场装的是吊灯移动止损 3.0×ATR20 + "
     "收盘跌破 MA50,★ 一条唐奇安反向通道都没有。这一档存在的唯一目的是"
     "让「装错」在数字上看得见",
     "技-1", False),

    # ================= 技-6 达瓦斯箱体 =================
    ("技-6 · 原著版 3 日规则(箱底 0 容差)",
     "技-6-原著.yaml", None,
     "★ 复核结论:这一条**本来就已经是原著口径** —— 箱顶/箱底都是「连续 3 天」,"
     "离场 pat6_close_below_darvas_bottom 判的是 close < bot(严格小于)= 0 容差。"
     "★ 本轮对 技-6 零改动,只重跑取数,把它放进三数对照表",
     "技-6", True),
]


# ---------------------------------------------------------------------------
# ★ 三数对照里的第 ② 个数:「过完选股后持有」
# ---------------------------------------------------------------------------

def per_trade_hold_to_end(cfg: chain.ChainConfig, syms: list[str]) -> dict:
    """
    ★★ 三数对照的「乙组」—— **不含资金约束的每笔收益率 %**。

    大白话(三秒):
      ① 全池每只票:进窗口第一天买,拿到这只票的最后一根 bar。
      ② 这条链每一个进场信号:信号次日开盘买,★ **一次都不卖**,
         拿到这只票的最后一根 bar。
      ③ 完整链实际每笔的收益率(流水里现成的)。
    ★ 三个数都是「每笔平均收益率」,所以可以直接并排比。

    ★★ 为什么必须有这一组(本轮踩过的坑,写下来免得下次再踩):
      「买了就不动」在**有槽位、有现金约束**的链上根本跑不出来 ——
      实测:把 技-13 的止损和离场全拆掉、仓位改成等权买入持有,
      ★ 整条链只成交了 **1 笔**(第一个信号日把全部现金买进了唯一那只候选,
        之后现金为 0,再不开仓),净收益 −98.71%。
      ★ 那个 −98.71% 量的是「现金一次性压在一只票上」,**不是选股能力**。
      → 所以「选股那一步有没有毁掉收益」必须用**不含资金约束的每笔收益率**
        来问,这一组就是它。

    ★ 口径(全部用开盘价 / 收盘价的实际价格,★ 不碰盘中最高价):
      · 买入价 = 信号次日开盘价(和链一致:signal_freeze: close / fill: next_open)
      · 卖出价 = 这只票在绩效窗口内**最后一根有价 bar** 的收盘价
        (退市/破产票就是那根 0 价 bar —— 和链的「退市结算」口径一致)
      · ★ 不扣摩擦:三个数都不扣,所以可比。
    """
    m = matrices.build(cfg.raw, syms)
    idx = m.index
    i0 = int(idx.searchsorted(np.datetime64(data.PERF_START)))
    i1 = len(idx) - 1
    close, open_ = m.close, m.open

    def _exit_px(j: int) -> float:
        k = min(i1, int(m.last_bar[j]))
        while k >= 0 and not np.isfinite(close[k, j]):
            k -= 1
        return float(close[k, j]) if k >= 0 else float("nan")

    # ---- ① 全池每只票买入持有
    bh = []
    for j in range(len(m.symbols)):
        i = i0
        while i <= i1 and not (np.isfinite(open_[i, j]) and open_[i, j] > 0):
            i += 1
        if i > i1:
            continue
        px0, px1 = float(open_[i, j]), _exit_px(j)
        if np.isfinite(px0) and px0 > 0 and np.isfinite(px1):
            bh.append(px1 / px0 - 1.0)

    # ---- ② 每个进场信号买了拿到底(★ 一次都不卖,不受槽位/现金约束)
    sig = []
    ent = m.entry & m.universe
    for i in range(i0, i1):
        if not bool(m.regime[i + 1]):
            continue                      # 和链一致:环境关闸时不开新仓
        for j in np.flatnonzero(ent[i]):
            j = int(j)
            if i + 1 > int(m.last_bar[j]):
                continue
            px0 = open_[i + 1, j]
            if not (np.isfinite(px0) and px0 > 0):
                continue
            px1 = _exit_px(j)
            if np.isfinite(px1):
                sig.append(px1 / float(px0) - 1.0)

    def _agg(v, label):
        a = np.asarray(v, dtype=float)
        a = a[np.isfinite(a)]
        return {"笔数": int(a.size),
                "平均收益率": float(a.mean()) if a.size else float("nan"),
                "中位收益率": float(np.median(a)) if a.size else float("nan"),
                "赚钱比例": float((a > 0).mean()) if a.size else float("nan"),
                "口径": label}

    return {
        "①全池每只票买入持有": _agg(bh, "进窗口第一天开盘买,拿到该票最后一根 bar"),
        "②每个进场信号买了拿到底": _agg(
            sig, "信号次日开盘买,★ 一次都不卖,拿到该票最后一根 bar;"
                 "★ 不受槽位与现金约束"),
        "说明": ("★ 这一组是**不含资金约束**的每笔收益率,专门用来隔离"
                 "「选股那一步」和「卖出那一步」。★ 不扣摩擦(三个数都不扣,可比)。"
                 "★ 全程只用开盘价与收盘价,不碰盘中最高价。"),
    }


# ---------------------------------------------------------------------------
# ★ 纪律 3:集中度 or 胜率(盈利笔数 < 10 就不报集中度)
# ---------------------------------------------------------------------------

def concentration_or_winrate(led) -> dict:
    """
    ★ 2026-10-29 新增的那条规则:
      盈利笔数 ≥ 10 → 报「前十笔占总盈利的比例」。
      盈利笔数 < 10  → ★ 不报集中度(它恒等于 100%,测不出东西),改报胜率。
    ★ 为什么加这条:技-13 旧结果那个 100% 集中度,实际含义是
      「225 笔里只有 9 笔赚钱」—— 集中度那个数把真相说反了。
    """
    if led is None or led.empty:
        return {"口径": "没有成交,两个都报不了"}
    n = len(led)
    n_win = int((led["net_pnl"] > 0).sum())
    winrate = float(n_win / n)
    base = {"总笔数": n, "盈利笔数": n_win, "胜率": winrate}
    if n_win < 10:
        base["★报哪个"] = "胜率"
        base["★为什么不报集中度"] = (
            f"盈利笔数只有 {n_win} 笔(< 10)—— 前十笔必然把全部盈利都包进去,"
            f"集中度恒等于 100%,这个数测不出任何东西。"
            f"★ 按 2026-10-29 新加的规则改报胜率:{winrate:.1%}。")
        base["集中度"] = None
    else:
        base["★报哪个"] = "集中度"
        base["集中度"] = _num(_concentration(led))
    return base


# ---------------------------------------------------------------------------
# ★ 纪律 4:这条链该用 R 还是用「每笔收益率 %」
# ---------------------------------------------------------------------------

def r_or_pct(led) -> dict:
    """
    实测 risk_per_share / entry_price。
    ★ 比值 ≈ 1 说明「止损价 ≈ 0」,R 退化成收益率,★ 这时一律改用每笔收益率 %。
    (技-12 / 技-2 就是这种情况 —— 康纳斯书中明确写死不设固定止损,
      ★ 那是**符合原著**的,不是 bug。本批没有这两条链,但照样实测判定。)
    """
    if led is None or led.empty:
        return {"口径": "没有成交"}
    ratio = (led["risk_per_share"].astype(float)
             / led["entry_price"].astype(float).replace(0.0, np.nan))
    ratio = ratio.replace([np.inf, -np.inf], np.nan).dropna()
    if ratio.empty:
        return {"口径": "算不出"}
    frac_near1 = float((ratio > 0.9).mean())
    use_r = frac_near1 < 0.5
    return {
        "risk_per_share/entry_price_均值": float(ratio.mean()),
        "risk_per_share/entry_price_中位数": float(ratio.median()),
        "比值>0.9 的笔数占比": frac_near1,
        "★该用哪个计量": "每笔 R" if use_r else "★ 每笔收益率 %(R 在这条链上无意义)",
        "每笔R净_均值": (float(led["r_multiple_net"].astype(float).mean())
                         if use_r else None),
        "每笔毛收益率_均值": float(led["gross_return"].astype(float).mean()),
    }


# ---------------------------------------------------------------------------
# ★ 纪律 8:单种子极差 vs 链效应 —— 自动给出「符号是不是噪声」的判定
# ---------------------------------------------------------------------------

def seed_noise_verdict(out: dict) -> dict:
    """
    pooled_random_control 已经算好「★单种子每笔R的极差」并无条件打到屏幕上。
    这里把它和链效应(信号均值 − 随机均值)比大小,直接给出那句判定文字。
    """
    pooled = out.get("判据_随机对照_5种子并池") or {}
    spread = pooled.get("★单种子每笔R的极差")
    gv = out.get("判据")
    eff = {}
    if gv is not None:
        for k, r in gv.results.items():
            if k.startswith("极性反转"):
                continue
            try:
                eff[k] = float(r.signal_mean) - float(r.random_mean)
            except Exception:                                # noqa: BLE001
                eff[k] = float("nan")
    effs = [abs(v) for v in eff.values() if np.isfinite(v)]
    max_eff = max(effs) if effs else float("nan")
    verdict = "算不出(极差或效应取不到)"
    if np.isfinite(spread if spread is not None else float("nan")) \
            and np.isfinite(max_eff):
        if spread > max_eff:
            verdict = (f"★★ 本轮 Z 的符号是噪声,两边都不当证据 —— "
                       f"随机对照的单种子极差 {spread:+.4f}R 比链自己最大的效应 "
                       f"{max_eff:.4f}R 还大。")
        else:
            verdict = (f"极差 {spread:+.4f}R ≤ 最大效应 {max_eff:.4f}R —— "
                       f"Z 的符号不是单纯的种子噪声(★ 仍不等于「结论成立」,"
                       f"还要看集中度和笔数)。")
    return {
        "★单种子每笔R的极差": spread,
        "★单种子每笔R的标准差": pooled.get("★单种子每笔R的标准差"),
        "逐种子": pooled.get("逐种子"),
        "各对照组效应(信号均值−随机均值)": eff,
        "最大效应绝对值": max_eff,
        "★判定": verdict,
    }


# ---------------------------------------------------------------- 跑一条链

def run_one(label, yaml_name, override, why, group, is_new, syms) -> dict:
    t0 = time.time()
    print("=" * 78)
    print(f"跑链:{label}")
    print(f"  这一版是什么:{why}")

    raw = _load(yaml_name)
    if override is not None:
        raw = override(copy.deepcopy(raw))

    cfg = chain.ChainConfig.from_dict(raw)
    rep = cfg.adapt_report
    if not rep.ok:
        raise RuntimeError(f"{label} 还有没实现的规则,不许带着它跑:\n{rep.text()}")

    funnel = signal_funnel(raw, [s for s in syms if s in cache.symbols()],
                           data.PERF_START)
    res = chain.run_chain(cfg, syms)
    os.makedirs(LEDGER_DIR, exist_ok=True)
    safe = (label.replace("/", "_").replace(" ", "")
            .replace("·", "_").replace("★", ""))
    res.save_ledger(os.path.join(LEDGER_DIR, f"{safe}.csv"))
    led = res.ledger
    n = len(led)
    print(f"  笔数 {n}")
    banner = analyze.sample_size_banner(n)
    if banner:
        print("  " + banner)

    out = analyze.evaluate(cfg, res, syms, with_attribution=True,
                           with_sensitivity=True, with_gate=True)
    gate4 = window_pool_gate(cfg, syms)
    print("  " + gate4.report().replace("\n", "\n  "))

    # ★ 纪律 7:五条基准线。基准一/二在 evaluate 里,三/四/五在 bench_suite 里
    try:
        bench = bench_lines.bench_suite(cfg, res, syms)
        bench.pop("_curves", None)
    except Exception as e:                                   # noqa: BLE001
        bench = {"★ bench_lines 跑不了": f"{type(e).__name__}: {e}"}

    # ★★ 本轮的判据:三个并排的数。★ 两组口径都给,因为两组问的不是一件事。
    attr = out["分步归因"]
    pt = per_trade_hold_to_end(cfg, syms)
    three = {
        "★甲组_账户净值口径(总收益)": {
            "①买入持有": float(attr.loc["买入持有", "净收益(扣摩擦)"]),
            "②过完选股后持有": float(attr.loc["+选股", "净收益(扣摩擦)"]),
            "③完整链(含新离场)": float(attr.loc["完整链", "净收益(扣摩擦)"]),
            "口径": (
                "① 全池等权买了不动;② 再加上这条链真实的「选股范围 + 环境开关」"
                "(扳机换成天天都买、不设止损、不设离场)—— ★ 这是仓库里"
                "analyze.attribution 一直在用的「+选股」定义;"
                "③ 七步全开。三个数都是绩效窗口内的账户净收益(扣摩擦)。"
                "★ 局限:形态链的 universe/regime 是空的 → ② 必然等于 ①,"
                "这组量不出**扳机**的选股能力。要看扳机,看乙组。"),
        },
        "★乙组_每笔收益率口径(不含资金约束)": {
            "①买入持有": pt["①全池每只票买入持有"]["平均收益率"],
            "②过完选股后持有": pt["②每个进场信号买了拿到底"]["平均收益率"],
            "③完整链(含新离场)": (float(led["gross_return"].astype(float).mean())
                                   if n else float("nan")),
            "明细": pt,
            "③口径": "完整链实际每笔的毛收益率均值(流水 gross_return)",
        },
    }
    jia, yi = three["★甲组_账户净值口径(总收益)"], three["★乙组_每笔收益率口径(不含资金约束)"]
    print(f"  ★三数对照 甲组(账户净值):① {jia['①买入持有']:+.2%}"
          f" / ② {jia['②过完选股后持有']:+.2%} / ③ {jia['③完整链(含新离场)']:+.2%}")
    print(f"  ★三数对照 乙组(每笔收益率):① {yi['①买入持有']:+.2%}"
          f" / ② {yi['②过完选股后持有']:+.2%} / ③ {yi['③完整链(含新离场)']:+.2%}"
          f"  (笔数 {pt['①全池每只票买入持有']['笔数']}"
          f" / {pt['②每个进场信号买了拿到底']['笔数']} / {n})")

    hold = {"平均持有天数": float(led["holding_days"].mean()) if n else float("nan"),
            "中位持有天数": float(led["holding_days"].median()) if n else float("nan"),
            "最长持有天数": int(led["holding_days"].max()) if n else 0,
            "出场原因": led["reason"].value_counts().to_dict() if n else {}}
    print(f"  平均持有 {hold['平均持有天数']:.1f} 天;出场原因 {hold['出场原因']}")

    zs = {k: _num(r.z_effect) for k, r in out["判据"].results.items()
          if not k.startswith("极性反转")}

    rec = {
        "报表名": label,
        "分组": group,
        "★是不是装上原著离场的那一版": is_new,
        "这一版是什么": why,
        "配置文件": yaml_name,
        "链名": cfg.name,
        "笔数": n,
        "样本量警示": banner,
        "★★三数对照": _num(three),
        "持仓时长": _num(hold),
        "★集中度或胜率": _num(concentration_or_winrate(led)),
        "★R还是百分比": _num(r_or_pct(led)),
        "信号漏斗": funnel,
        "绝对表现": _num(out["绝对表现"]),
        "坑一_现金拖累": _num(out["坑一_现金拖累"]),
        "坑二_跳空穿透止损": _num(out["坑二_跳空穿透止损"]),
        "代价": _num(out["代价"]),
        "执行负荷": _num(out["执行负荷"]),
        "摩擦成本": _num(out["摩擦成本"]),
        "基准一_同环境随机进场": _num(out["基准一_同环境随机进场"]),
        "基准二_同等仓位大盘": _num(out["基准二_同等仓位大盘"]),
        "判据_三套对照组": _num(out["判据"]),
        "★三套对照组Z": zs,
        "★种子噪声判定": _num(seed_noise_verdict(out)),
        "判据_随机对照笔数": out.get("判据_随机对照笔数"),
        "★两窗口两池子硬关": _num(gate4),
        "★基准线套件(基准三四五)": _num(bench),
        "分步归因": _num(out["分步归因"]),
        "坑四_摩擦敏感度": _num(out["坑四_摩擦敏感度"]),
        "适配层报告": rep.text(),
        "引擎显式关掉的东西": matrices.disabled_log(),
        "耗时秒": round(time.time() - t0, 1),
        "峰值RSS_MB": round(_rss_mb(), 1),
    }
    print(f"  (用了 {rec['耗时秒']} 秒,峰值 RSS {rec['峰值RSS_MB']} MB)")
    if rec["峰值RSS_MB"] > MEM_CAP_MB:
        print(f"  ★★ 内存警告:峰值 {rec['峰值RSS_MB']} MB 超过 {MEM_CAP_MB} MB")
    return rec


# ---------------------------------------------------------------------------
# ★ 纪律 2:「原著未给出可执行阈值」的项 —— 从配置里直接读出来,不在报告里手写
# ---------------------------------------------------------------------------

def _unrunnable() -> list[dict]:
    out = []
    for f in sorted(os.listdir(CONFIG_DIR)):
        if not (f.startswith("技-") or f in ("trend_following.yaml",)):
            continue
        try:
            d = ops_1029.load_yaml_strict(os.path.join(CONFIG_DIR, f))
        except Exception as e:                               # noqa: BLE001
            out.append({"配置文件": f, "★读不了": f"{type(e).__name__}: {e}"})
            continue
        m = d.get("meta") or {}
        keys = ("原著未给出可执行阈值的项", "原著有引擎做不到的项",
                "cannot_run_reason", "param_gap")
        hit = {k: m[k] for k in keys if m.get(k)}
        if m.get("cannot_run"):
            hit["cannot_run"] = True
        if hit:
            out.append({"配置文件": f, "名": m.get("name"), **hit})
    return out


def main(argv=None) -> int:
    # ★ 纪律 6:串行,单进程。先确认资源。
    print(subprocess.run(["free", "-m"], capture_output=True, text=True).stdout)
    print(f"CPU 核数 {os.cpu_count()} —— ★ 本脚本**串行单进程**,不开任何多进程/多线程池。")

    pat6_ops.install()            # 技-6 达瓦斯箱体用
    ops_exits_1029.install()      # ★ 本轮新装的原著离场算子

    print(data.cohort_report())
    syms = data.full_universe().pool("ALL")
    syms = [s for s in syms if s in cache.symbols()]
    print(f"\n全池 {len(syms)} 只,绩效窗口 {data.PERF_START} .. {data.PERF_END}\n")

    only = set(argv or [])
    rows, fails = [], []
    for label, yml, ov, why, group, is_new in VARIANTS:
        if only and not any(k in label for k in only):
            continue
        try:
            rows.append(run_one(label, yml, ov, why, group, is_new, syms))
        except Exception as e:                               # noqa: BLE001
            import traceback
            traceback.print_exc()
            fails.append({"报表名": label, "错误": f"{type(e).__name__}: {e}"})

    out = {
        "跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "★溯源": _cache_provenance(),
        "全池只数": len(syms),
        "绩效窗口": f"{data.PERF_START} .. {data.PERF_END}",
        "★本轮要回答的问题": (
            "装上原著离场后,那个「选股 +77~95% → 完整链 −2~−12%」的形状会不会翻正?"
            " → 看每条链的「★★三数对照」三个数。"),
        "判据口径": {
            "Bootstrap": f"{stats_gate.N_SEEDS_DEFAULT} 个种子并池 × B="
                         f"{stats_gate.B_DEFAULT},在交易流水层面重抽",
            "经验p值": "(1 + #{rand ≥ signal}) / (B + 1)",
            "Z": f"基础显著 ≥{stats_gate.Z_BASIC};机构级 ≥{stats_gate.Z_INSTITUTIONAL}",
            "三套对照组": "条件分层随机 / 块重排 / 波动率选择检验(比 mean|R|)",
            "★不报的": "极性反转 —— 死代码(Z_做空 ≡ −Z_做多)",
            "样本下限": stats_gate.SYSTEM_MIN_TRADES,
            "★并行": "★ 串行单进程。2 核 / 7GB,跑前已打印 free。",
            "★判定口径": "按收盘价判定,全程严禁盘中最高价",
        },
        "各版结果": rows,
        "跑挂的": fails,
        "★原著未给出可执行阈值 / 原著有引擎做不到的项": _unrunnable(),
        "原著离场算子备注": ops_exits_1029.diagnostics(),
        "A0算子备注": ops_a0.notes(),
        "pat6备注": pat6_ops.notes(),
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n写好 {OUT_JSON}(共 {len(rows)} 版,挂了 {len(fails)} 版)")
    print(f"交易流水:{LEDGER_DIR}/")
    print(f"峰值 RSS {_rss_mb():.0f} MB")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
