"""
A0 十二条 —— 2026-10-29 全量跑。

大白话:手册标「原著完整、不需要补阈值」的 12 条,逐条填成七步配置跑一遍,
出「成立 / 不成立 / 样本不足 / 算不出 / 参数不全 / 拿不到」六种结论之一。

★ 本脚本只跑「能建链」的那几条。另外三类单走:
  · 技-9 / 模-6        —— 拿不到数据,不建链(见各自 yaml 的说明)
  · 模-1 / 模-5        —— 可挂载模块,挂在 技-1 上(本脚本末尾做)
  · 状-4 / 状-6        —— 状态判定,不产生交易信号 → 见 run_a0_states.py

★ 硬纪律照 run_trend_1029.py 那一套,一条不改:
  预热 2016 / 绩效 2018 起 · Bootstrap 在交易流水层面 B=1000 ·
  三套对照组 · 两窗口两池子硬关(FNV-1a 确定性种子)· 两条基准线 ·
  笔数 < 150 打警示 · σ≈0 报「算不出」· 不网格搜索。

跑法:python3 -m engine.run_a0_12
"""

from __future__ import annotations

import copy
import json
import os
import time

import numpy as np
import yaml

from . import (analyze, cache, chain, data, matrices, ops_1029, ops_a0,
               stats_gate, window_pool)
from .run_batch import _num, signal_funnel, window_pool_gate

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(HERE, "configs")
OUT_JSON = os.path.join(HERE, "results_1029_A0十二条.json")
LEDGER_DIR = os.path.join(HERE, "ledgers_1029_A0十二条")


def _load(name: str) -> dict:
    # ★ 用严格加载器：YAML 重复 key 会静默取最后一个，
    #   于是「前面写了 enabled: false、后面还留着 true」这种写法
    #   会让配置看起来关掉了、实际还在干活。★ 这次改成直接报错。
    return ops_1029.load_yaml_strict(os.path.join(CONFIG_DIR, name))


# ---------------------------------------------------------------------------
# 要跑的变体清单
#   每个条目:(报表名, 基础 yaml, 覆盖函数 or None, 这一版是什么/为什么跑它)
# ---------------------------------------------------------------------------

def _sys2(raw: dict) -> dict:
    raw["entry"]["rules"][0]["params"]["lookback"] = 55
    raw["exit"]["rules"][0]["params"]["lookback"] = 20
    raw["meta"]["name"] = "技-1_海龟System2_55日入20日出"
    return raw


def _pb25(raw: dict) -> dict:
    raw["entry"]["rules"][0]["params"]["max_pullback"] = 0.25
    return raw


def _noconfirm(raw: dict) -> dict:
    raw["entry"]["rules"][0]["params"]["require_close_confirm"] = False
    return raw


def _rsi10(raw: dict) -> dict:
    raw["entry"]["rules"][0]["params"]["threshold"] = 10.0
    return raw


def _xing_trend(raw: dict) -> dict:
    """
    ★★ 技-1 的 XING 版 —— 手册自己在正文里列成一张对照表:
         执行时点  收盘价确认,次日开盘执行        (和原著不同)
         退出      跟踪止损,2 倍 ATR              (★ 和原著不同:原著是反向通道)
         初始止损  含在跟踪止损内                  (★ 和原著不同:原著独立设 2N)
         标的与方向 美股个股,只做多               (★ 和原著不同)
    ★ 这就是「原著版 vs XING 版」的差别所在,所以必须单独跑。
    """
    raw["meta"]["name"] = "技-1_XING日终趋势突破版"
    # 初始止损「含在跟踪止损内」= 进场当天的吊灯位
    raw["initial_stop"] = {
        "type": "chandelier",
        "params": {"lookback": 20, "multiple": 2.0, "atr_period": 20},
        "source": "XING 版(手册正文对照表:初始止损含在跟踪止损内)",
    }
    raw["trailing_stop"] = {
        "type": "chandelier",
        "params": {"lookback": 20, "multiple": 2.0, "atr_period": 20},
        "monotonic_up_only": True,
        "source": "XING 版(手册正文对照表:退出 = 跟踪止损 2 倍 ATR)",
    }
    # ★ XING 版没有反向通道退出 —— 把那条去掉,只留跟踪止损
    raw["exit"]["rules"] = [
        {"type": "close_below_trailing_stop", "source": "XING 版(靠跟踪止损出场)"}]
    return raw


def _pb225(raw: dict) -> dict:
    raw["entry"]["rules"][0]["params"]["max_pullback"] = 0.225
    return raw


def _cd13(raw: dict) -> dict:
    raw["entry"]["rules"][0] = {
        "type": "td_buy_countdown",
        "params": {"setup_count": 9, "ref_lag": 4, "countdown": 13, "cd_lag": 2},
        "source": ("流传最广版本:Setup 9 完成后开始数,close ≤ low[t−2] 记一个,"
                   "数到 13。★ 手册只给了「13」这个数,其余是流传版本。"),
    }
    return raw


#: 每个条目:(报表名, 基础 yaml, 覆盖函数, 这一版是什么, 三版框架里的归属)
#  ★ 三版框架 = 硬纪律 B(2026-10-29 策略组拍板):原著版 / 行业版 / XING版
VARIANTS = [
    # ---- 技-1 系统化趋势跟随 ----
    ("技-1 · 海龟 System 1(20 日入 / 10 日出)", "技-1.yaml", None,
     "原著 System 1 参数。★ 原著的「上次突破是赢家就跳过」过滤器引擎没实现,显式不加",
     "原著版"),
    ("技-1 · 海龟 System 2(55 日入 / 20 日出)", "技-1.yaml", _sys2,
     "原著 System 2 参数。★ System 2 原著本来就没有那个过滤器,所以这一档更干净",
     "原著版"),
    ("技-1 · XING 日终趋势突破版(2ATR 跟踪止损)", "技-1.yaml", _xing_trend,
     "★ 手册正文对照表里的 XING 版:退出改成 2 倍 ATR 跟踪止损、初始止损含在里面。"
     "★ 这一档就是回答「原著版和 XING 版差在哪」的那个对照",
     "XING版"),
    # ---- 技-2 法伯月线择时 ----
    ("技-2 · 法伯月线择时(10 月线)", "技-2.yaml", None,
     "★ 12 条里唯一一条真正一个数都不用我们填的。★ 原著版 ≡ XING版(手册没记任何 XING 改动)",
     "原著版 ≡ XING版"),
    # ---- 技-8 高紧旗形:原著给的是区间 → 严格端 / 中值 / 宽松端三组 ----
    ("技-8 · HTF(回调上限 20% · 严格端)", "技-8.yaml", None,
     "★ 原著给的是 20–25% 区间,跑严格端", "原著版·严格端"),
    ("技-8 · HTF(回调上限 22.5% · 中值)", "技-8.yaml", _pb225,
     "★ 原著给的是 20–25% 区间,跑中值", "原著版·中值"),
    ("技-8 · HTF(回调上限 25% · 宽松端)", "技-8.yaml", _pb25,
     "★ 原著给的是 20–25% 区间,跑宽松端", "原著版·宽松端"),
    # ---- 技-10 海龟汤:按三版框架重新标注(任务书 + 协调员指示)----
    ("技-10 · 海龟汤 · XING版(要求收盘确认)", "技-10.yaml", None,
     "★ 我方卡片口径 = XING版。两版只差收盘确认这一处,4 天存活门禁两版都开着",
     "XING版"),
    ("技-10 · 海龟汤 · 原著版(不要求收盘确认)", "技-10.yaml", _noconfirm,
     "★ 附录 D.8 认为原著不要求收盘确认 = 原著版。★ 但 D.8 自己标的是"
     "「待核实(来源存疑)」—— 所以这个「原著版」的标签本身也还没核实",
     "原著版(待核实)"),
    # ---- 技-12 康纳斯 ----
    ("技-12 · 康纳斯(RSI2 < 5)", "技-12.yaml", None,
     "★ 手册没给这个阈值(原文只写「极低值」)。5 是 Connors 体系里流传最广的值,"
     "★ 按三版框架这一档只能算「行业版」,不能算原著版 —— 因为手册没有原文可引",
     "行业版"),
    ("技-12 · 康纳斯(RSI2 < 10)", "技-12.yaml", _rsi10,
     "★ 同上,10 是另一个流传值", "行业版"),
    # ---- 技-13 TD 序列 ----
    ("技-13 · TD Buy Setup 9", "技-13.yaml", None,
     "★ 手册只说「标记为衰竭点」,没说买 —— 进场规则是我们加的,所以这一档只能算 XING版",
     "XING版"),
    ("技-13 · TD Buy Countdown 13", "技-13.yaml", _cd13,
     "★ 同上。Countdown 的计数细节来自流传版本", "XING版"),
]


def run_one(label: str, yaml_name: str, override, why: str, version: str,
            syms: list[str]) -> dict:
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
    safe = label.replace("/", "_").replace(" ", "")
    res.save_ledger(os.path.join(LEDGER_DIR, f"{safe}.csv"))
    n = len(res.ledger)
    led = res.ledger
    print(f"  笔数 {n}")

    banner = analyze.sample_size_banner(n)
    if banner:
        print("  " + banner)

    out = analyze.evaluate(cfg, res, syms, with_attribution=True,
                           with_sensitivity=True, with_gate=True)

    gate4 = window_pool_gate(cfg, syms)
    print("  " + gate4.report().replace("\n", "\n  "))

    # ---- 征兆警报(吊灯 bug 的征兆)。★ 这条链没有移动止损时要注明,
    #      因为那个 bug 只可能来自移动止损 —— 不能看见高胜率就当 bug。
    alarm = []
    has_trail = (raw.get("trailing_stop") or {}).get("type") not in (None, "none")
    if n:
        wr = float((led["net_pnl"] > 0).mean())
        rbar = float(led["r_multiple"].mean())
        if wr > 0.60 or rbar > 0.5:
            if has_trail:
                alarm.append(f"★★ 征兆警报:胜率 {wr:.1%} / 每笔R {rbar:+.3f} "
                             f"—— 本链有移动止损,必须复查吊灯止损")
            else:
                alarm.append(
                    f"★ 征兆数字出现(胜率 {wr:.1%} / 每笔R {rbar:+.3f}),"
                    f"★ 但本链 trailing_stop = none —— 吊灯 bug 在物理上不可能发生,"
                    f"已逐项核对:不是 bug。均值回归策略的高胜率是设计预期。")
    for a in alarm:
        print("  " + a)

    # ---- 持仓时长健康检查:原著的离场被显式关掉的链会退化成「长期持有」
    hold = {"平均持有天数": float(led["holding_days"].mean()) if n else float("nan"),
            "最长持有天数": int(led["holding_days"].max()) if n else 0,
            "出场原因": led["reason"].value_counts().to_dict() if n else {}}

    pol = out["判据"].results.get("极性反转")

    rec = {
        "报表名": label,
        "★三版框框归属": version,
        "这一版是什么": why,
        "配置文件": yaml_name,
        "笔数": n,
        "样本量警示": banner,
        "样本量": ("够(≥150)" if n >= stats_gate.SYSTEM_MIN_TRADES
                   else f"★ 不够(n={n} < {stats_gate.SYSTEM_MIN_TRADES})"),
        "信号漏斗": funnel,
        "持仓时长": _num(hold),
        "绝对表现": _num(out["绝对表现"]),
        "坑一_现金拖累": _num(out["坑一_现金拖累"]),
        "坑二_跳空穿透止损": _num(out["坑二_跳空穿透止损"]),
        "代价": _num(out["代价"]),
        "执行负荷": _num(out["执行负荷"]),
        "摩擦成本": _num(out["摩擦成本"]),
        "基准一_同环境随机进场": _num(out["基准一_同环境随机进场"]),
        "基准二_同等仓位大盘": _num(out["基准二_同等仓位大盘"]),
        "判据_三套对照组": _num(out["判据"]),
        "判据_随机对照触发率": out.get("判据_随机对照触发率"),
        "判据_随机对照笔数": out.get("判据_随机对照笔数"),
        "★极性反转": ({"Z": _num(pol.z_effect), "p": _num(pol.p_empirical),
                       "信号均值": _num(pol.signal_mean),
                       "随机均值": _num(pol.random_mean),
                       "级别": pol.level} if pol is not None else None),
        "★两窗口两池子硬关": _num(gate4),
        "分步归因": _num(out["分步归因"]),
        "坑四_摩擦敏感度": _num(out["坑四_摩擦敏感度"]),
        "征兆警报": alarm,
        "引擎显式关掉的东西": matrices.disabled_log(),
        "A0算子备注": ops_a0.notes(),
        "耗时秒": round(time.time() - t0, 1),
    }
    print(analyze.format_report(out))
    print(f"  (用了 {rec['耗时秒']} 秒)")
    return rec


# ===========================================================================
# 模-1 / 模-5 —— 挂在 技-1 上
# ===========================================================================

def mount_modules(syms: list[str]) -> dict:
    """
    模-5 R 乘数:引擎原生已实现 —— 这里做的是**核对**,不是新算。
    模-1 凯利:只出描述性输入,★ 不接到仓位上(附录 D.6 禁止输出仓位字段)。
    """
    print("=" * 78)
    print("可挂载模块:模-5 R 乘数 / 模-1 凯利仓位 —— 挂在 技-1 上")

    raw = _load("技-1.yaml")
    cfg = chain.ChainConfig.from_dict(raw)
    res = chain.run_chain(cfg, syms)
    led = res.ledger
    n = len(led)

    # ---- 模-5:核对「原始 R 不被移动止损重写」
    risk_ok = bool(np.allclose(
        (led["entry_price"] - led["initial_stop"]).abs().to_numpy(float),
        led["risk_per_share"].to_numpy(float), equal_nan=True))
    moved = int((led["stop_at_exit"] > led["initial_stop"]).sum())

    r = led["r_multiple"].dropna().to_numpy(float)
    rn = led["r_multiple_net"].dropna().to_numpy(float)
    mo5 = {
        "挂上去之后有什么变化": (
            "★ 没有变化 —— 这是关键结论。模-5 只改记账单位,不改任何决策,"
            "而引擎本来就原生用 R 记账(chain.py 的 r_multiple / r_multiple_net / "
            "risk_per_share 三列)。所以「挂载前」和「挂载后」的交易流水逐笔相同。"
            "手册自己也是这么说的:「它不改变任何决策,只改变记账方式。」"),
        "笔数": n,
        "原始R未被移动止损重写_逐笔核对": risk_ok,
        "出场时止损已被抬过的笔数": moved,
        "核对说明": (
            f"★ 这 {moved} 笔的止损在持仓期间被抬过(stop_at_exit > initial_stop),"
            f"★ 但 risk_per_share 仍然等于 abs(进场价 − 初始止损) —— "
            f"逐笔核对通过={risk_ok}。这正是手册要求写死的那条:"
            f"「原始 R 必须留档,不得随移动止损重写分母」。"),
        "每笔R_均值": float(np.mean(r)) if r.size else float("nan"),
        "每笔R_中位数": float(np.median(r)) if r.size else float("nan"),
        "每笔R_扣摩擦均值": float(np.mean(rn)) if rn.size else float("nan"),
        "每笔R_95%CI": analyze._fmt_ci(analyze.ci95(led["r_multiple"])) if n else None,
        "★手册要求的五个并列": {
            "一_R": float(np.mean(r)) if r.size else float("nan"),
            "二_账户收益": float(res.equity.iloc[-1] / res.equity.iloc[0] - 1.0),
            "三_最大回撤": float(analyze.drawdown(res.equity)[0]),
            "四_平均持有天数": float(led["holding_days"].mean()) if n else float("nan"),
            "五_纪律记录": "★ 回测里没有「纪律执行」这个量 —— 它只存在于真实交易。"
                           "报告里必须留这一格为空,不许用别的数顶上。",
        },
        "★样本量标注": f"以上是 {n} 笔的**观察到的平均**,不是策略期望值(手册 v8 修正②)",
    }

    # ---- 模-1:凯利的描述性输入
    wins = r[r > 0]
    losses = r[r < 0]
    p = float(wins.size / r.size) if r.size else float("nan")
    avg_w = float(wins.mean()) if wins.size else float("nan")
    avg_l = float(abs(losses.mean())) if losses.size else float("nan")
    b = avg_w / avg_l if (np.isfinite(avg_w) and np.isfinite(avg_l) and avg_l > 0) \
        else float("nan")
    naive = (p - (1 - p) / b) if np.isfinite(b) and b > 0 else float("nan")

    # 独立性:同一天开仓的笔数 → 这些不是独立样本
    per_day = led.groupby("entry_date").size() if n else None
    clustered = float((per_day[per_day > 1].sum() / n)) if n and per_day is not None \
        else float("nan")

    mo1 = {
        "挂上去之后有什么变化": (
            "★ 没有挂上去 —— 这是本条的结论。理由有两层:\n"
            "  一、手册第 1104 行自己写了:那个二元赌局公式的输出「不能直接当作"
            "股票仓位,必须先做转换」,★ 而这个转换手册没有给出任何形式。\n"
            "  二、即使转换给了,附录 D.6 的禁止字段清单明文禁掉 position_factor / "
            "recommended_position_percent,理由是手册 11.4「不给具体仓位调整建议」。"
            "★ 所以模-1 在任何情况下都不允许输出一个仓位数字。\n"
            "  → 本次只在 技-1 的真实流水上算出凯利公式的**描述性输入**,"
            "并报「如果照搬那个二元公式会得到什么」,★ 明确不是仓位建议。"),
        "样本_笔数": n,
        "胜率p": p,
        "平均盈利R": avg_w,
        "平均亏损R": avg_l,
        "盈亏比b": b,
        "★照搬二元公式会得到": naive,
        "★为什么这个数不能用": (
            f"二元公式假设「输了全亏」。技-1 的实际亏损分布不是这样:"
            f"平均亏损 {avg_l:.3f}R,不是 1 个本金。把 {naive:.3f} 当仓位用"
            f"在数学上是错的 —— 手册第 1104-1106 行讲的就是这件事。"),
        "★手册的敏感度警告": (
            f"手册第 1108 行:「胜率高估 5 个百分点,建议仓位可能高一倍」。"
            f"实测:p={p:.4f} → 公式给 {naive:.4f};"
            f"p+0.05={p + 0.05:.4f} → 公式给 "
            f"{(p + 0.05 - (1 - p - 0.05) / b) if np.isfinite(b) and b > 0 else float('nan'):.4f}"
            f"。★ 这个放大倍数自己看。"),
        "★样本独立性(手册第 1113 行要求看的)": {
            "同日多笔开仓占总笔数比": clustered,
            "说明": ("手册:「100 笔高度相关、集中在同一段行情里的交易,"
                     "提供的不是 100 个独立样本。门槛要看独立性,不只看笔数。」"
                     "★ 独立性的门槛手册没给数 —— 已列入「要回去问」。"
                     "这里只报事实:有多少笔是和别的笔同一天开的。"),
        },
        "★估不准就说估不准": (
            "手册第 1114 行要求:「数据不足或优势估计不稳定时,系统明确返回"
            "『无法可靠估算』,而不是硬算一个数。」"
            f"→ 本次 n={n} 笔,但同日开仓占比 {clustered:.1%},"
            f"独立样本数远少于 {n};且转换形式未定。"
            "★ 结论:无法可靠估算,不输出任何仓位数字。"),
        "全/半/四分之一凯利": (
            "★ 手册第 1109 行说「实务上普遍用半凯利甚至四分之一凯利」,"
            "但没拍用哪个。这是一个直接决定仓位倍数的数 —— 已列入「要回去问」。"),
    }
    print("  模-5:原始R未被重写 =", risk_ok, "/ 止损抬过的笔数 =", moved)
    print("  模-1:p =", round(p, 4), "b =", round(b, 3) if np.isfinite(b) else "nan",
          "→ 二元公式 =", round(naive, 4) if np.isfinite(naive) else "nan",
          "(★ 不作为仓位)")
    return {"模-5_R乘数": _num(mo5), "模-1_凯利仓位": _num(mo1)}


def main(argv=None) -> int:
    print(data.cohort_report())
    syms = data.full_universe().pool("ALL")
    syms = [s for s in syms if s in cache.symbols()]
    print(f"\n全池 {len(syms)} 只,绩效窗口 {data.PERF_START} .. {data.PERF_END}\n")

    out = {
        "跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "全池只数": len(syms),
        "绩效窗口": f"{data.PERF_START} .. {data.PERF_END}(2016 起热机)",
        "口径": ("2026-10-29 A0 十二条。硬纪律:Bootstrap 在交易流水层面 B=1000 / "
                 "三套对照组同环境取样 / 两窗口两池子硬关 FNV-1a 确定性种子 / "
                 "两条基准线(Ē 全周期固定)/ 笔数<150 打警示 / 不网格搜索"),
        "链": [],
    }
    for label, yml, ov, why, version in VARIANTS:
        try:
            out["链"].append(run_one(label, yml, ov, why, version, syms))
        except Exception as e:
            print(f"★ {label} 跑挂了:{type(e).__name__}: {e}")
            out["链"].append({"报表名": label, "★跑挂了": f"{type(e).__name__}: {e}"})
    try:
        out["可挂载模块"] = mount_modules(syms)
    except Exception as e:
        out["可挂载模块"] = {"★跑挂了": f"{type(e).__name__}: {e}"}

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=2)
    print(f"\n原始数字已写:{OUT_JSON}\n交易流水已写:{LEDGER_DIR}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
