"""
pat6_run —— 技-3 / 技-4 / 技-5 / 技-6 / 技-11 / 技-14 三版并跑。

大白话:把上面六条形态的「原著版 / 行业版 / XING版」各跑一遍,
每一版都过同一套硬纪律,最后吐一份 json 给报告用。

★ 硬纪律照 run_a0_12.py 那一套,一条不改:
  预热 2014 / 绩效 2018-01-02 起 · Bootstrap 在**交易流水层面** ·
  5 个种子并池 × B=1000 · 经验 p 值 · 三套对照组
  (条件分层随机 / 块重排 / ★ 波动率选择检验 —— ★ 极性反转是死代码,不报它) ·
  随机对照按**实际成交笔数**校准 · 两窗口两池子硬关(FNV-1a 确定性种子) ·
  两条基准线 + 动态开关基准与择时贡献 · 笔数 <150 打警示 ·
  σ≈0 报「算不出」· 不网格搜索 · 集中度检查两侧都写。

★ 内存纪律:这台机器 8GB,今天已经 OOM 过一次。本脚本**串行**跑,
  跑之前打印 free,每条链之后打印当前 RSS。不开多进程。

跑法:python3 -m engine.pat6_run
"""

from __future__ import annotations

import copy
import json
import os
import resource
import time

import numpy as np

from . import (analyze, bench_lines, cache, chain, data, matrices, ops_1029,
               pat6_ops, stats_gate)
from .run_batch import _num, signal_funnel, window_pool_gate

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(HERE, "configs")
OUT_JSON = os.path.join(HERE, "results_1029_技术派六条三版.json")
LEDGER_DIR = os.path.join(HERE, "ledgers_1029_技术派六条三版")

MEM_CAP_MB = 1500.0


def _rss_mb() -> float:
    return resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024.0


def _load(name: str) -> dict:
    return ops_1029.load_yaml_strict(os.path.join(CONFIG_DIR, name))


# ---------------------------------------------------------------- 覆盖函数

def _vol(mult: float):
    """技-3 行业版:放量倍数三端。"""
    def f(raw):
        for r in raw["entry"]["rules"]:
            if r["type"] == "pat6_volume_x_sma":
                r["params"]["multiple"] = mult
                r["source"] = (f"行业惯例(1.30~1.80 × SMA50;本档 = {mult})")
        raw["meta"]["name"] = f"技-3_行业版_放量{mult}"
        return raw
    return f


def _vcp_real(ratio: float):
    """
    ★ 技-5:在**真实在跑的那条链**(vcp_momentum.yaml)上只改缩量阈值。

    ★ 另外沿用 run_second_round_1029.py 里**前两批就有**的两处「显式关掉」——
      ★ 不是本次新关的,口径和那条线完全一致,否则笔数不可比:
      ① universe 的「宏观基底_行业 RS」(against: SECTOR)—— 行业标签非 PIT
      ② ⑤「15 日滞涨换血」(action: rotate_out)—— 触发条件没定义,不能猜
    ★ 代价:换血是专家宣称的三大改进之一 → 这一版不是完整的这一派。
    """
    def f(raw):
        for r in raw["universe"]["rules"]:
            for c in (r.get("components") or []):
                if (c.get("type") == "mansfield_rs_positive"
                        and str((c.get("params") or {}).get("against")) == "SECTOR"):
                    c["enabled"] = False
        key = "stop_trail" if "stop_trail" in raw else "trailing_stop"
        before = len(raw[key]["stages"])
        raw[key]["stages"] = [s for s in raw[key]["stages"]
                              if s.get("action") != "rotate_out"]
        assert len(raw[key]["stages"]) == before - 1
        for r in raw["entry"]["rules"]:
            if r["type"] == "vcp_volume_duo":
                r["params"]["dryup_day_ratio"] = ratio
                r["source"] = (f"原著区间端 {ratio}(原文「低于 50 日均量 40%~50%」"
                               f"= 0.50~0.60)")
        raw["meta"]["name"] = f"技-5_真实链_缩量{ratio}"
        return raw
    return f


#: (报表名, 配置文件, 覆盖函数, 这一版是什么, 三版归属)
VARIANTS = [
    # ---------------- 技-3 温斯坦 ----------------
    ("技-3 · 原著版 · ★ 忠实周线(底盘 13 周 / 周量 ≥2× 前 4 周均量)",
     "技-3-原著.yaml", None,
     "放量 2 倍按**周线口径**算 —— 原著本来就是周线方法。"
     "底盘 13 周是我们的读法(原著只说 a few months to several years)",
     "原著版·忠实周线"),
    ("技-3 · 原著版 · 忠实周线(底盘下沿 9 周)",
     "技-3-原著-底盘9周.yaml", None,
     "同上,底盘取区间下沿 2 个月 —— 看「底盘长度」这个我们填的数影响多大",
     "原著版·忠实周线·下沿"),
    ("技-3 · 原著版 · ★ 机械日线(单日量 ≥2×SMA50)",
     "技-3-原著-机械日线.yaml", None,
     "★ 把原著的 2 倍直接套到日线上 —— 口径被换掉了。"
     "这一版存在的唯一目的是量出「直接套用会怎样」",
     "原著版·机械日线对照"),
    ("技-3 · 行业版(放量 1.30× · 严格端)", "技-3-行业.yaml", None,
     "横盘 ≥30 日 + 放量 1.30×SMA50 + SMA150 20 日变化率 ≥0", "行业版·严格端"),
    ("技-3 · 行业版(放量 1.55× · 中值)", "技-3-行业.yaml", _vol(1.55),
     "同上,放量取区间中值", "行业版·中值"),
    ("技-3 · 行业版(放量 1.80× · 宽松端)", "技-3-行业.yaml", _vol(1.80),
     "同上,放量取区间宽松端", "行业版·宽松端"),
    ("技-3 · XING版", "技-3-XING.yaml", None,
     "★ 我们从没为 技-3 建过配置;这一版是用仓库现有写法拼的,"
     "★ 而且**没有放量确认** —— 原著写得最死的那一条被丢了",
     "XING版"),
    # ---------------- 技-4 欧奈尔杯柄 ----------------
    ("技-4 · 原著版(严格端:杯深 ≥15% / 柄深 ≤12% / 放量 1.50×)",
     "技-4-原著.yaml", None, "原著区间的严格端;枢纽点 = 柄高 +$0.10", "原著版·严格端"),
    ("技-4 · 原著版(中值)", "技-4-原著-中值.yaml", None,
     "原著区间中值;枢纽点 = 柄高 +$0.10", "原著版·中值"),
    ("技-4 · 原著版(宽松端:杯深 ≥12% / 柄深 ≤15% / 放量 1.40×)",
     "技-4-原著-宽松端.yaml", None, "原著区间宽松端;枢纽点 = 柄高 +$0.10",
     "原著版·宽松端"),
    ("技-4 · 行业版(枢纽 +0.1% / 放量 1.20× / 柄部极端缩量)",
     "技-4-行业.yaml", None,
     "★ 把 +$0.10 换成 +0.1%,重心从突破日放量转到柄部缩量", "行业版"),
    # ---------------- 技-5 VCP ----------------
    ("技-5 · 原著版(缩量 0.50 · 严格端)", "技-5-原著.yaml", None,
     "衰减 0.50 / 次数 2~4 / 第一段 ≤33% / 缩量 0.50", "原著版·严格端"),
    ("技-5 · 原著版(缩量 0.55 · 中值)", "技-5-原著-中值.yaml", None,
     "同上,缩量取中值", "原著版·中值"),
    ("技-5 · 原著版(缩量 0.60 · 宽松端)", "技-5-原著-宽松端.yaml", None,
     "★ 0.60 正好是原著区间最宽松那一端 —— 我们现在用的就是它", "原著版·宽松端"),
    ("技-5 · 行业版(次数 ≥3 / 衰减 0.65 / 缩量 0.60)", "技-5-行业.yaml", None,
     "行业「标准档」:收缩次数要求提到 3 次", "行业版"),
    ("技-5 · XING版(第一段 ≤30% / 衰减 0.65 / 2~4 次 / 缩量 0.60)",
     "技-5-XING.yaml", None, "我们现在用的值", "XING版"),
    # ★ 技-5 的三端还要在**真实在跑的那条链**上各跑一遍 ——
    #   因为任务书问的「148 笔」是那条链的笔数,不是本次这条剥掉闸门的链。
    ("技-5 · ★真实链 vcp_momentum(缩量 0.50)", "vcp_momentum.yaml",
     _vcp_real(0.50), "★ 带全部环境过滤与选股闸门的真实链,只改缩量阈值",
     "原著版·严格端(真实链)"),
    ("技-5 · ★真实链 vcp_momentum(缩量 0.55)", "vcp_momentum.yaml",
     _vcp_real(0.55), "同上", "原著版·中值(真实链)"),
    ("技-5 · ★真实链 vcp_momentum(缩量 0.60)", "vcp_momentum.yaml",
     _vcp_real(0.60), "★ 这一档就是我们现在在跑的那条链", "XING版/原著宽松端(真实链)"),
    # ---------------- 技-6 达瓦斯 ----------------
    ("技-6 · 原著版(3 日规则,★ 无振幅条件)", "技-6-原著.yaml", None,
     "★ 原著只有「连续 3 天」一个数,振幅百分比原著一个字都没写", "原著版"),
    ("技-6 · 行业版(3 日规则 + 振幅 ≤18% + 存活 ≥10 日)", "技-6-行业.yaml", None,
     "★ 振幅上限是**止损距离风控的安全阀**,不是箱体的定义", "行业版"),
    ("技-6 · XING版(近 25 根区间收窄到 20%)", "技-6-XING.yaml", None,
     "★ 我们现有的百分比收窄写法 —— 它不是达瓦斯", "XING版"),
    # ---------------- 技-11 威科夫 ----------------
    ("技-11 · 行业版(后人量化版:下刺 0.15~0.80 ATR + 收复 + 缩量)",
     "技-11-行业.yaml", None,
     "★ 阈值全部来自 Evans → Pruden → Williams 这一脉,★ 一处都不是原著",
     "行业版(= 后人量化版)"),
    ("技-11 · XING版(跌破 20 日低点再收回)", "技-11-XING.yaml", None,
     "★ 它不区分 Spring 1/2/3 号 —— #1 终极洗盘也会被买进来", "XING版"),
    # ---------------- 技-14 布林带 ----------------
    ("技-14 · 原著版(Method III 近似:W 底 + MFI 底背离)",
     "技-14-原著.yaml", None,
     "★ 原著**反对**裸碰轨;这是作者自己认可的那个用法的近似", "原著版"),
    ("技-14 · 行业版(三步进场 + 三道趋势过滤)", "技-14-行业.yaml", None,
     "不许盘中碰轨限价抄底;ADX≤25 那一条正是「走带」警告的工程化落地", "行业版"),
    ("技-14 · XING版(触下轨就买)", "技-14-XING.yaml", None,
     "★★ 作者点名反对的做法(Bollinger Rule 4)", "XING版"),
]


def run_one(label, yaml_name, override, why, version, syms) -> dict:
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
    safe = label.replace("/", "_").replace(" ", "").replace("·", "_")
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

    # ★ 两条基准线 + 动态开关基准 + 择时贡献 + 集中度自检
    try:
        bench = bench_lines.bench_suite(cfg, res, syms)
        bench.pop("_curves", None)
    except Exception as e:                       # noqa: BLE001
        bench = {"★ bench_lines 跑不了": f"{type(e).__name__}: {e}"}

    hold = {"平均持有天数": float(led["holding_days"].mean()) if n else float("nan"),
            "最长持有天数": int(led["holding_days"].max()) if n else 0,
            "出场原因": led["reason"].value_counts().to_dict() if n else {}}

    # ★ 纪律 6:不许用「样本不足」搪塞 —— 每笔 R / 判据 Z / 基准一差值都摆出来
    rbar = float(led["r_multiple_net"].mean()) if n else float("nan")
    winr = float((led["net_pnl"] > 0).mean()) if n else float("nan")
    gv = out["判据"]
    zs = {k: _num(r.z_effect) for k, r in gv.results.items()
          if not k.startswith("极性反转")}

    rec = {
        "报表名": label,
        "★三版归属": version,
        "这一版是什么": why,
        "配置文件": yaml_name,
        "笔数": n,
        "样本量警示": banner,
        "每笔R净": _num(rbar),
        "胜率": _num(winr),
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
        "★三套对照组Z": zs,
        "判据_随机对照触发率": out.get("判据_随机对照触发率"),
        "判据_随机对照笔数": out.get("判据_随机对照笔数"),
        "★两窗口两池子硬关": _num(gate4),
        "★基准线套件": _num(bench),
        "分步归因": _num(out["分步归因"]),
        "坑四_摩擦敏感度": _num(out["坑四_摩擦敏感度"]),
        "引擎显式关掉的东西": matrices.disabled_log(),
        "pat6备注": pat6_ops.notes(),
        "耗时秒": round(time.time() - t0, 1),
        "峰值RSS_MB": round(_rss_mb(), 1),
    }
    print(analyze.format_report(out))
    print(f"  (用了 {rec['耗时秒']} 秒,峰值 RSS {rec['峰值RSS_MB']} MB)")
    if rec["峰值RSS_MB"] > MEM_CAP_MB:
        print(f"  ★★ 内存警告:峰值 {rec['峰值RSS_MB']} MB 已超过 {MEM_CAP_MB} MB 上限")
    return rec


def main(argv=None) -> int:
    import subprocess
    pat6_ops.install()
    print(subprocess.run(["free", "-m"], capture_output=True,
                         text=True).stdout)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                          capture_output=True, text=True).stdout.strip()
    syms = cache.symbols()
    print(f"池子 {len(syms)} 只;绩效窗口 {data.PERF_START} .. {data.PERF_END}")

    only = set(argv or [])
    rows, fails = [], []
    for label, yml, ov, why, ver in VARIANTS:
        if only and not any(k in label for k in only):
            continue
        try:
            rows.append(run_one(label, yml, ov, why, ver, syms))
        except Exception as e:                   # noqa: BLE001
            import traceback
            traceback.print_exc()
            fails.append({"报表名": label, "错误": f"{type(e).__name__}: {e}"})

    # ★ 原著跑不了的那些:从配置文件里直接读出来,★ 不在报告里手写
    cannot = []
    for f in sorted(os.listdir(CONFIG_DIR)):
        if not f.startswith("技-"):
            continue
        d = ops_1029.load_yaml_strict(os.path.join(CONFIG_DIR, f))
        m = d.get("meta") or {}
        if m.get("cannot_run"):
            cannot.append({"配置文件": f, "名": m.get("name"),
                           "为什么跑不了": m.get("cannot_run_reason"),
                           "原著未给出可执行阈值的项":
                               m.get("原著未给出可执行阈值的项")})
        elif m.get("原著未给出可执行阈值的项"):
            cannot.append({"配置文件": f, "名": m.get("name"),
                           "为什么跑不了": "部分项跑不了(配置里已逐项标出)",
                           "原著未给出可执行阈值的项":
                               m.get("原著未给出可执行阈值的项")})

    # ★ 只跑了一部分时,和已有结果**合并**而不是覆盖 —— 否则补跑三条会把
    #   前面 24 条的结果抹掉。合并按「报表名」为准,同名的用新结果替换。
    if only and os.path.exists(OUT_JSON):
        old = json.load(open(OUT_JSON, encoding="utf-8"))
        names = {r["报表名"] for r in rows}
        rows = [r for r in old.get("各版结果", []) if r["报表名"] not in names] + rows
        fails = [f for f in old.get("跑挂的", []) if f["报表名"] not in names] + fails
        order = [v[0] for v in VARIANTS]
        rows.sort(key=lambda r: order.index(r["报表名"])
                  if r["报表名"] in order else 999)

    out = {
        "git_commit": head,
        "池子只数": len(syms),
        "绩效窗口": [data.PERF_START, data.PERF_END],
        "判据口径": {
            "Bootstrap": f"{stats_gate.N_SEEDS_DEFAULT} 个种子并池 × B="
                         f"{stats_gate.B_DEFAULT},在交易流水层面重抽",
            "经验p值": "(1 + #{rand ≥ signal}) / (B + 1)",
            "Z": f"基础显著 ≥{stats_gate.Z_BASIC};机构级 ≥{stats_gate.Z_INSTITUTIONAL}",
            "三套对照组": "条件分层随机 / 块重排 / 波动率选择检验(比 mean|R|)",
            "★不报的": "极性反转 —— 死代码(Z_做空 ≡ −Z_做多),已被波动率选择检验取代",
            "随机对照校准": "按实际成交笔数校准,校准只看笔数不看成绩",
            "样本下限": stats_gate.SYSTEM_MIN_TRADES,
        },
        "各版结果": rows,
        "跑挂的": fails,
        "★原著跑不了的": cannot,
        "pat6备注": pat6_ops.notes(),
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n写好 {OUT_JSON}(共 {len(rows)} 版,挂了 {len(fails)} 版)")
    print(f"峰值 RSS {_rss_mb():.0f} MB")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
