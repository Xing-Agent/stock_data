"""
剔污染重跑 —— 2026-10-30。

三秒版:上一轮发现朴素基准那个 +450.75% 是**未修反向拆股**造出来的。
        那份污染是**整只票**级别的,而代码里剔的是**单根 bar** 级别的
        (`split_gate.residual_jumps(3.0)`,实测 10 根 / 8 只票)。
        ★★ 这一轮新增一档「整只票剔除」口径,把已知数据断裂清单上的票
           **整只**从池子里排除,然后把每条链的两个数并排报。

★★ 这一轮要回答的**唯一**问题:
   ★ 剔掉断裂清单上那些票之后,**还剩下什么**?
     · 哪些链的结论是**被污染撑着**的(剔除后塌掉)
     · 哪些链的结论**不依赖污染**(剔除后基本不变)—— 这些才是我们真正有的东西
     ★★ 朴素基准(基准五)剔除后是多少?它还能不能当基准?

★★ 硬纪律(照任务书,一条不变通):
  1. ★ **不改现有跑批逻辑** —— `matrices.py` / `chain.py` / `config_adapter.py`
     一个字符都没动。新增的「整只票剔除」口径是通过**给 run_chain 传一个
     更短的 symbols 列表**实现的(池子口径本来就是入参),
     ★ 新算子照上一轮的做法走**运行时挂钩**(pat6_ops / ops_exits_1029)。
     ★ 单根 bar 剔除那一档**原样留着**,这里是**新增一档**,不是改掉它。
  2. 集中度必须报;★ 盈利笔数 < 10 → 不报集中度(它恒等于 100%),改报胜率。
  3. ★ 技-12 / 技-2 一律不用 R 计量 —— 它们 100% 的笔子
     risk_per_share ≈ entry_price,而这**符合原著**(康纳斯书中明确写死不设
     固定止损),不是 bug。这两条一律用「每笔收益率 %」。
  4. ★★ R / % 判定改**双侧**:risk/entry > 0.9(止损≈0,R 退化成收益率)
     **或** < 0.01(止损贴着价格,R 被放大到无意义)→ 都改用每笔收益率 %。
     (上一轮技-10 原著离场版暴露的:止损挂在新低下方 1 tick,
      risk/entry 最小 0.07% → 随机对照里出现 R ≈ 1.2e+11。)
  5. 按收盘价判定,★ 严禁盘中最高价(算子层面保证)。
  6. ★ 串行单进程。2 核 / 7GB,跑前打印 free,每条链之后打印峰值 RSS。
  7. ★ 强制打印单种子极差,并和链效应比大小 —— 极差远大于效应时,
     报告里必须写「本轮 Z 的符号是噪声,两边都不当证据」。本脚本自动给判定。
  8. git add 按文件显式列出(这条由人执行,脚本不碰 git)。

跑法:python3 -m engine.run_declean_1030
"""

from __future__ import annotations

import copy
import importlib.util
import json
import os
import resource
import subprocess
import time

import numpy as np

from . import (analyze, bench_lines, cache, chain, data, matrices, ops_1029,
               ops_exits_1029, pat6_ops, stats_gate)
from .run_batch import _num
from .run_orig_exits_1029 import (_cache_provenance, concentration_or_winrate,
                                  seed_noise_verdict)

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(HERE, "configs")
OUT_JSON = os.path.join(HERE, "results_1030_剔污染.json")
LEDGER_DIR = os.path.join(HERE, "ledgers_1030_剔污染")

MEM_CAP_MB = 1500.0

#: ★ 朴素基准的矩阵缓存,按池子分开(省时间,不改任何口径)
_NAIVE_M_CACHE: dict = {}

#: ★ 两个池子口径的名字 —— 报告里每一处都用这两个词,不许含糊
POOL_DIRTY = "污染版(现状全池)"
POOL_CLEAN = "剔除版(整只票剔除)"

#: ★ 纪律 3:这两条链一律不用 R 计量(符合原著,不是 bug)
FORCE_PCT_CHAINS = ("技-12", "技-2")

#: ★★ 纪律 4:R / % 判定的**双侧**阈值
RATIO_HI, RATIO_LO = 0.9, 0.01


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _load(name: str) -> dict:
    return ops_1029.load_yaml_strict(os.path.join(CONFIG_DIR, name))


def known_break_symbols() -> set[str]:
    """★ 已知数据断裂清单 —— 直接用 checks/anchor_health.py 那一份,不另立清单。"""
    p = os.path.join(HERE, "checks", "anchor_health.py")
    spec = importlib.util.spec_from_file_location("ah_1030", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)                                   # type: ignore
    return m.known_break_symbols()


# ---------------------------------------------------------------- 覆盖函数

def _ts(days: int):
    """技-10:时间止损改成 days 天(原著区间 2~5 的某一端)。"""
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


def _cd13_entry(raw):
    """技-13:进场换成 Countdown 13(离场四条不动)。"""
    raw["entry"]["rules"][0] = {
        "type": "td_buy_countdown",
        "params": {"setup_count": 9, "ref_lag": 4, "countdown": 13, "cd_lag": 2},
        "source": "流传最广版本;★ 和上一轮 run_orig_exits_1029 的同名覆盖函数逐字一致",
    }
    raw["meta"]["name"] = "技-13_TD序列_原著四重离场_Countdown13进场"
    return raw


def _rsi10(raw):
    """技-12:RSI2 阈值 5 → 10(另一个流传值,照 run_a0_12._rsi10)。"""
    raw["entry"]["rules"][0]["params"]["threshold"] = 10.0
    raw["meta"]["name"] = "技-12_康纳斯均值回归_RSI2小于10"
    return raw


def _drop_bw_gate(raw):
    """技-14:把带宽突变熔断那一道显式关掉(照 run_p5_1029._drop_bw_gate)。"""
    hit = 0
    for r in raw["entry"]["rules"]:
        if r["type"] == "pat6_bb_bw_jump_gate":
            r["enabled"] = False
            hit += 1
    assert hit == 1, "带宽熔断那一道没找到 —— 配置被动过了"
    raw["meta"]["name"] = "技-14_行业版_RSI2_不带带宽熔断"
    return raw


# ---------------------------------------------------------------------------
# 要跑的链 —— (报表名, 配置文件, 覆盖函数, 这一版是什么, 分组, 是不是买跌类)
#   ★ 顺序 = 任务书的优先级:买跌四条(技-10/11/12/14)最大暴露,先跑。
# ---------------------------------------------------------------------------
VARIANTS = [
    # ========== ★ 买跌类(最大暴露)==========
    ("技-10 · 原著离场 · 持仓 2 天(严格端)",
     "技-10-原著-持仓2至5天离场.yaml", None,
     "海龟汤买 20 日新低 —— ★ 买跌类,最大暴露", "技-10", True),
    ("技-10 · 原著离场 · 持仓 3 天(中值)",
     "技-10-原著-持仓2至5天离场.yaml", _ts(3), "同上,区间中值", "技-10", True),
    ("技-10 · 原著离场 · 持仓 5 天(宽松端)",
     "技-10-原著-持仓2至5天离场.yaml", _ts(5), "同上,区间宽松端", "技-10", True),
    ("技-10 · 旧实现对照(离场整条拿掉)",
     "技-10.yaml", None,
     "★ 上一轮那 123 笔、前十笔占总盈利 99.79% 的那一档 —— "
     "本轮要回答的就是「那 99.79% 是不是污染」", "技-10", True),

    ("技-11 · 行业版(后人量化版 Spring:下刺 + 收复 + 缩量)",
     "技-11-行业.yaml", None,
     "威科夫 Spring 买破支撑 —— ★ 买跌类", "技-11", True),

    ("技-12 · 康纳斯(RSI2 < 5)",
     "技-12.yaml", None,
     "RSI2 买超卖 —— ★ 买跌类。★ 纪律 3:这条链一律用每笔收益率 %,不用 R",
     "技-12", True),
    ("技-12 · 康纳斯(RSI2 < 10)",
     "技-12.yaml", _rsi10, "同上,另一个流传阈值", "技-12", True),

    ("技-14 · 原著版(Method III 近似:W 底 + MFI 底背离)",
     "技-14-原著.yaml", None, "布林带下轨 —— ★ 买跌类", "技-14", True),
    ("技-14 · 行业版(三步进场 + 三道趋势过滤,含 ADX≤25)",
     "技-14-行业.yaml", None, "同上,旧三道过滤器那一版", "技-14", True),
    ("技-14 · 行业版 RSI2≤10(带带宽熔断)",
     "技-14-行业-RSI2.yaml", None, "同上,批五修正后那一版", "技-14", True),
    ("技-14 · 行业版 RSI2≤10(不带带宽熔断)",
     "技-14-行业-RSI2.yaml", _drop_bw_gate, "同上,熔断显式关掉", "技-14", True),

    # ========== 其余 ==========
    ("技-13 · 原著四重离场 · Setup 9 进场",
     "技-13-原著-四重离场.yaml", None, "TD 序列,四条离场全装", "技-13", False),
    ("技-13 · 原著四重离场 · Countdown 13 进场",
     "技-13-原著-四重离场.yaml", _cd13_entry, "同上,进场换 Countdown 13",
     "技-13", False),

    ("技-8 · 时间止损 20 日【行业做法】· 回调 20%(严格端)",
     "技-8-行业-时间止损20日.yaml", None, "高紧旗形 HTF", "技-8", False),
    ("技-8 · 时间止损 20 日【行业做法】· 回调 25%(宽松端)",
     "技-8-行业-时间止损20日.yaml", _pb(0.25), "同上,宽松端", "技-8", False),

    ("技-1 · 原著离场 · System 1(20 日入 / 10 日反向通道出)",
     "技-1-原著-唐奇安反向通道离场.yaml", None, "系统化趋势跟随", "技-1", False),

    ("技-6 · 原著版 3 日规则(箱底 0 容差)",
     "技-6-原著.yaml", None, "达瓦斯箱体", "技-6", False),

    # ========== 锚点 ==========
    ("buy_and_hold(锚点)",
     "buy_and_hold.yaml", None,
     "★ 锚点链 —— 上一轮 anchor_health 判它 FAIL(67 笔骑在断裂日上,"
     "最严重 FTLF +499.62 倍)。★ 本轮要看剔除版能不能过体检",
     "锚点", False),
]


# ---------------------------------------------------------------------------
# ★★ 纪律 4:R / % 判定改**双侧**
# ---------------------------------------------------------------------------

def r_or_pct_two_sided(led, group: str) -> dict:
    """
    实测 risk_per_share / entry_price,★ **双侧**判定该用 R 还是每笔收益率 %。

    大白话(三秒):R = 「赚了几倍的风险」。它只有在「风险」这个分母是个
      正常数的时候才有意义。
      · 分母 ≈ 整个股价(比值 > 0.9)→ 等于没设止损,R 退化成收益率;
      · 分母 ≈ 0(比值 < 0.01)→ 止损贴着买入价,R 被除出天文数字
        (上一轮真的出现过 R ≈ 1.2e+11)。
      ★ 两头任一头占了多数,R 这把尺子就不能用,改用「每笔收益率 %」。
    """
    base: dict = {"★双侧口径": f"risk/entry > {RATIO_HI} 或 < {RATIO_LO} → 用 %"}
    if group in FORCE_PCT_CHAINS:
        base["★强制用%"] = (
            f"★ 纪律 3:{group} 一律不用 R —— 它 100% 的笔子 "
            f"risk_per_share ≈ entry_price,而这**符合原著**"
            f"(康纳斯书中明确写死不设固定止损),不是 bug。")
    if led is None or led.empty:
        base["口径"] = "没有成交"
        return base
    ratio = (led["risk_per_share"].astype(float)
             / led["entry_price"].astype(float).replace(0.0, np.nan))
    ratio = ratio.replace([np.inf, -np.inf], np.nan).dropna()
    if ratio.empty:
        base["口径"] = "算不出"
        return base
    hi = float((ratio > RATIO_HI).mean())
    lo = float((ratio < RATIO_LO).mean())
    # ★★ 严格双侧:**只要有一笔**落在两头(> 0.9 或 < 0.01),这条链的「平均每笔 R」
    #   就不可信 —— 一笔 risk/entry = 0.07% 的交易就能把均值顶到 R ≈ 1.2e+11
    #   (上一轮技-10 原著离场版的随机对照里真的出现过)。
    #   ★ 不用「占多数才算」那种宽松写法:均值不是中位数,它挡不住单笔极值。
    degenerate = (hi > 0.0) or (lo > 0.0) or group in FORCE_PCT_CHAINS
    base.update({
        "risk/entry_均值": float(ratio.mean()),
        "risk/entry_中位数": float(ratio.median()),
        "risk/entry_最小": float(ratio.min()),
        "risk/entry_最大": float(ratio.max()),
        f"比值>{RATIO_HI} 的笔数占比": hi,
        f"比值<{RATIO_LO} 的笔数占比": lo,
        "★该用哪个计量": ("★ 每笔收益率 %(R 在这条链上无意义)" if degenerate
                          else "每笔 R"),
        "每笔R净_均值": (None if degenerate
                        else float(led["r_multiple_net"].astype(float).mean())),
        "每笔毛收益率_均值": float(led["gross_return"].astype(float).mean()),
    })
    return base


# ---------------------------------------------------------------------------
# ★ 污染归属 —— 这条链有多少笔、多少钱是骑在断裂清单票上的
# ---------------------------------------------------------------------------

def contamination_attribution(led, known: set[str]) -> dict:
    """
    ★ 只读流水,回答一件事:这条链的成绩有多少是断裂清单票给的。
    大白话:污染票占了几成笔数、几成盈利 —— 占得越多,剔除版就会塌得越狠。
    """
    if led is None or led.empty:
        return {"说明": "没有成交"}
    sym = led["symbol"].astype(str)
    bad = sym.isin(known)
    pnl = led["net_pnl"].astype(float)
    gr = led["gross_return"].astype(float)
    pos = pnl[pnl > 0].sum()
    out = {
        "总笔数": int(len(led)),
        "污染票笔数": int(bad.sum()),
        "污染票笔数占比": float(bad.mean()),
        "污染票净盈亏": float(pnl[bad].sum()),
        "全链净盈亏": float(pnl.sum()),
        "污染票占全链净盈亏": (float(pnl[bad].sum() / pnl.sum())
                              if pnl.sum() != 0 else None),
        "污染票占全链总盈利(只数正的)": (float(pnl[bad & (pnl > 0)].sum() / pos)
                                        if pos > 0 else None),
        "污染票平均每笔毛收益率": (float(gr[bad].mean()) if bad.any() else None),
        "干净票平均每笔毛收益率": (float(gr[~bad].mean()) if (~bad).any() else None),
    }
    top = (led.assign(bad_flag=bad)
           .sort_values("gross_return", ascending=False).head(5))
    out["最大五笔"] = [
        {"symbol": str(r.symbol), "毛收益率": float(r.gross_return),
         "净盈亏": float(r.net_pnl), "在断裂清单上": bool(r.bad_flag),
         "entry": str(r.entry_date), "exit": str(r.exit_date)}
        for r in top.itertuples()]
    return out


# ---------------------------------------------------------------------------
# 跑一条链 × 一个池子
# ---------------------------------------------------------------------------

def run_one(label, yaml_name, override, group, syms, pool_name, known,
            with_naive: bool) -> dict:
    t0 = time.time()
    print(f"  --- {pool_name}(池子 {len(syms)} 只)")

    raw = _load(yaml_name)
    if override is not None:
        raw = override(copy.deepcopy(raw))

    cfg = chain.ChainConfig.from_dict(raw)
    rep = cfg.adapt_report
    if not rep.ok:
        raise RuntimeError(f"{label} 还有没实现的规则,不许带着它跑:\n{rep.text()}")

    res = chain.run_chain(cfg, syms)             # ★ 现成入口,池子是入参
    os.makedirs(LEDGER_DIR, exist_ok=True)
    safe = (label.replace("/", "_").replace(" ", "")
            .replace("·", "_").replace("★", ""))
    tag = "污染版" if pool_name == POOL_DIRTY else "剔除版"
    res.save_ledger(os.path.join(LEDGER_DIR, f"{safe}__{tag}.csv"))
    led = res.ledger
    n = len(led)

    out = analyze.evaluate(cfg, res, syms, with_attribution=False,
                           with_sensitivity=False, with_gate=True)

    naive: dict = {}
    if with_naive:
        # ★ 朴素基准的矩阵按池子缓存 —— 同一个池子只建一次(省时间,不改口径)
        mc = _NAIVE_M_CACHE.setdefault(pool_name, {})
        for kind in (bench_lines.NAIVE_MEANREV, bench_lines.NAIVE_RSI2):
            slots = int(((cfg.get("sizing") or {}).get("params") or {})
                        .get("max_positions", 10))
            equal_all = (cfg.get("sizing") or {}).get("type") == "equal_weight_all"
            nb = bench_lines.naive_baseline(
                kind, syms, slots, cfg.get("costs") or {}, res,
                m_cache=mc, equal_all=equal_all, drop_fake_jumps=True)
            nb.pop("_daily", None)
            naive[kind] = _num(nb)

    zs = {k: _num(r.z_effect) for k, r in out["判据"].results.items()
          if not k.startswith("极性反转")}
    perf = out["绝对表现"]
    rec = {
        "池子口径": pool_name,
        "池子只数": len(syms),
        "笔数": n,
        "样本量警示": analyze.sample_size_banner(n),
        "净收益(扣摩擦)": float(perf["净收益(扣摩擦)"]),
        "CAGR(净)": _num(perf["CAGR(净)"]),
        "最大回撤": _num(out["代价"]["最大回撤"]),
        "平均每笔毛收益率": (float(led["gross_return"].astype(float).mean())
                            if n else float("nan")),
        "中位每笔毛收益率": (float(led["gross_return"].astype(float).median())
                            if n else float("nan")),
        "平均持有天数": float(led["holding_days"].mean()) if n else float("nan"),
        "出场原因": led["reason"].value_counts().to_dict() if n else {},
        "★集中度或胜率": _num(concentration_or_winrate(led)),
        "★R还是百分比(双侧)": _num(r_or_pct_two_sided(led, group)),
        "★污染归属": _num(contamination_attribution(led, known)),
        "★三套对照组Z": zs,
        "★种子噪声判定": _num(seed_noise_verdict(out)),
        "基准一_同环境随机进场": _num(out["基准一_同环境随机进场"]),
        "基准二_同等仓位大盘": _num(out["基准二_同等仓位大盘"]),
        "★基准五_朴素基准": naive or "本条未算(朴素基准按池子算一次,见顶层「★朴素基准」)",
        "耗时秒": round(time.time() - t0, 1),
        "峰值RSS_MB": round(_rss_mb(), 1),
    }
    c = rec["★集中度或胜率"]
    if c.get("★报哪个") == "集中度":
        which = f"集中度={(c.get('集中度') or {}).get('前10笔占总盈利比例')}"
    else:
        which = f"胜率={c.get('胜率')}(盈利笔数 {c.get('盈利笔数')} < 10,不报集中度)"
    nb5 = (naive.get(bench_lines.NAIVE_MEANREV) or {}).get("朴素基准总收益")
    print(f"      笔数 {n} | 净收益 {rec['净收益(扣摩擦)']:+.2%} | "
          f"每笔 {rec['平均每笔毛收益率']:+.3%} | {which} | "
          f"基五朴素(均值回归)={nb5} | "
          f"{rec['耗时秒']}s RSS {rec['峰值RSS_MB']}MB")
    if rec["峰值RSS_MB"] > MEM_CAP_MB:
        print(f"      ★★ 内存警告:峰值 {rec['峰值RSS_MB']} MB > {MEM_CAP_MB} MB")
    return rec


def main(argv=None) -> int:
    # ★ 纪律 6:串行,单进程。先确认资源。
    print(subprocess.run(["free", "-m"], capture_output=True, text=True).stdout)
    print(f"CPU 核数 {os.cpu_count()} —— ★ 本脚本**串行单进程**,"
          f"不开任何多进程 / 多线程池。")

    pat6_ops.install()            # 技-6 / 技-11 / 技-14
    ops_exits_1029.install()      # 技-13 四重离场 / 技-10 原著离场

    known = known_break_symbols()
    syms_all = data.full_universe().pool("ALL")
    syms_all = [s for s in syms_all if s in cache.symbols()]
    in_pool = sorted(s for s in syms_all if s in known)
    syms_clean = [s for s in syms_all if s not in known]

    print(f"\n★★ 两个池子口径")
    print(f"  {POOL_DIRTY}:{len(syms_all)} 只")
    print(f"  {POOL_CLEAN}:{len(syms_clean)} 只 "
          f"(剔掉 {len(in_pool)} 只:{', '.join(in_pool)})")
    print(f"  ★ 已知数据断裂清单共 {len(known)} 只,池子里 {len(in_pool)} 只")
    print(f"  绩效窗口 {data.PERF_START} .. {data.PERF_END}\n")

    pools = [(POOL_DIRTY, syms_all), (POOL_CLEAN, syms_clean)]

    only = set(argv or [])
    rows, fails = [], []
    for label, yml, ov, why, group, isdip in VARIANTS:
        if only and not any(k in label for k in only):
            continue
        print("=" * 78)
        print(f"跑链:{label}")
        print(f"  这一版是什么:{why}")
        pair: dict = {"报表名": label, "分组": group, "这一版是什么": why,
                      "配置文件": yml, "★是不是买跌类": isdip, "两版": {}}
        for pool_name, syms in pools:
            try:
                pair["两版"][pool_name] = run_one(
                    label, yml, ov, group, syms, pool_name, known,
                    with_naive=True)
            except Exception as e:                           # noqa: BLE001
                import traceback
                traceback.print_exc()
                fails.append({"报表名": label, "池子": pool_name,
                              "错误": f"{type(e).__name__}: {e}"})
        a = pair["两版"].get(POOL_DIRTY) or {}
        b = pair["两版"].get(POOL_CLEAN) or {}
        if a and b:
            pair["★差值"] = {
                "净收益_剔除−污染": b["净收益(扣摩擦)"] - a["净收益(扣摩擦)"],
                "每笔_剔除−污染": b["平均每笔毛收益率"] - a["平均每笔毛收益率"],
                "笔数_剔除−污染": b["笔数"] - a["笔数"],
                "★净收益剩余比例": (b["净收益(扣摩擦)"] / a["净收益(扣摩擦)"]
                                   if a["净收益(扣摩擦)"] not in (0.0,) else None),
            }
            print(f"  ★★ 并排:净收益 {a['净收益(扣摩擦)']:+.2%} → "
                  f"{b['净收益(扣摩擦)']:+.2%}"
                  f"(差 {pair['★差值']['净收益_剔除−污染']:+.2%});"
                  f"每笔 {a['平均每笔毛收益率']:+.3%} → "
                  f"{b['平均每笔毛收益率']:+.3%}")
        rows.append(pair)
        # ★ 每条链跑完就落盘 —— 中途挂了也不丢前面的数
        _dump(rows, fails, syms_all, syms_clean, known, in_pool)

    _dump(rows, fails, syms_all, syms_clean, known, in_pool)
    print(f"\n写好 {OUT_JSON}(共 {len(rows)} 条链,挂了 {len(fails)} 次)")
    print(f"交易流水:{LEDGER_DIR}/")
    print(f"峰值 RSS {_rss_mb():.0f} MB")
    return 0


def _merge_rows(rows: list[dict]) -> list[dict]:
    """
    ★ 和磁盘上已有的结果合并,按 VARIANTS 的顺序排好。

    为什么要有这个(本轮踩到的):18 条链 × 2 个池子串行跑要一个多小时,
    ★ 跑批进程被外层超时掐掉时,已经跑完的那些不能丢 —— 补跑剩下几条
    (`python3 -m engine.run_declean_1030 技-13 技-8 ...`)时,
    这个函数把补跑的结果并回去,而不是把前面的覆盖掉。
    ★ 同名的链以**本次**结果为准(重跑就是为了覆盖它)。
    """
    old: list[dict] = []
    if os.path.exists(OUT_JSON):
        try:
            with open(OUT_JSON, encoding="utf-8") as fh:
                old = json.load(fh).get("各链两版") or []
        except Exception:                                    # noqa: BLE001
            old = []
    now = {r["报表名"] for r in rows}
    merged = rows + [r for r in old if r.get("报表名") not in now]
    order = {label: i for i, (label, *_rest) in enumerate(VARIANTS)}
    merged.sort(key=lambda r: order.get(r.get("报表名"), 999))
    return merged


def _dump(rows, fails, syms_all, syms_clean, known, in_pool) -> None:
    rows = _merge_rows(rows)
    out = {
        "跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "★溯源": _cache_provenance(),
        "★★本轮要回答的问题": (
            "剔掉已知数据断裂清单上的票之后,还剩下什么?"
            " → 看每条链「两版」的并排数字和「★差值」。"),
        "★★两个池子口径": {
            POOL_DIRTY: len(syms_all),
            POOL_CLEAN: len(syms_clean),
            "剔掉的票": in_pool,
            "已知断裂清单只数": len(known),
            "★剔除口径": (
                "★★ **整只票**剔除 —— 把 checks/anchor_health.known_break_symbols() "
                "返回的票整只从 universe 里排除(传给 run_chain 的 symbols 变短)。"
                "★ 这**不是**单根 bar 剔除:单根 bar 那一档"
                "(split_gate.residual_jumps(3.0),10 根 / 8 只票)原样留着,"
                "本轮是**新增一档**。"),
            "★为什么要分清": (
                "★★ 凡报告里写「已剔除假跳变」的地方,必须说清剔的是**单根 bar** "
                "还是**整只票** —— 票级覆盖率只有 27%,30 只里 22 只在单根 bar "
                "清单里一根都没有(含 SQBG / FTLF 这两只最严重的)。"
                "见 engine/checks/jump_removal_coverage.py。"),
        },
        "绩效窗口": f"{data.PERF_START} .. {data.PERF_END}",
        "判据口径": {
            "Bootstrap": f"{stats_gate.N_SEEDS_DEFAULT} 个种子并池 × "
                         f"B={stats_gate.B_DEFAULT},在交易流水层面重抽",
            "三套对照组": "条件分层随机 / 块重排 / 波动率选择检验",
            "★R/%判定": f"★ 双侧:risk/entry > {RATIO_HI} 或 < {RATIO_LO} → 用 %;"
                        f"★ 技-12 / 技-2 强制用 %(符合原著)",
            "★集中度": "盈利笔数 ≥ 10 → 报集中度;< 10 → 不报(恒等 100%),改报胜率",
            "★并行": "★ 串行单进程。2 核 / 7GB,跑前已打印 free。",
            "★判定口径": "按收盘价判定,全程严禁盘中最高价",
            "★不改跑批逻辑": "matrices.py / chain.py / config_adapter.py 一字未动;"
                             "池子口径走 run_chain(cfg, symbols) 这个现成入参,"
                             "新算子走运行时挂钩(pat6_ops / ops_exits_1029)",
        },
        "各链两版": rows,
        "跑挂的": fails,
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
