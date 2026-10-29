"""
用三条新基准线(基准三 动态开关 / 基准四 槽位机会成本 / 基准五 朴素基准)
重算全部已有结论 —— 2026-10-29。

三秒版:旧基准把「策略空仓那几个月大盘在跌」这件事白送给了策略当超额。
        这个脚本把那一笔拆出来叫「择时贡献」,剩下的才叫「选股贡献」,
        并补两条新基准线回答「值不值得占一个槽」和「打不打得过无脑规则」。

跑法:cd /home/claude/xing-agent-stock_data && PYTHONPATH=. python3 -m engine.bench_run_1029

产出:engine/results_1029_新基准线.json          原始数字
      engine/ledgers_1029_新基准线/              交易流水
      /home/claude/新基准线-结果-1029.md         报告(单独写)

★ 本脚本只读共享文件、不改它们。新基准线的实现全在 engine/bench_lines.py。
★ buy_and_hold 的 sanity check 是第一个跑的,而且它不通过就直接把
  「★★ sanity check 没过」写进结果 —— 这就是「能认出自己坏了」的检查点。
"""

from __future__ import annotations

import json
import os
import time
import traceback

import numpy as np
import pandas as pd

from . import analyze, bench_lines, cache, chain, data, matrices, split_gate

HERE = os.path.dirname(os.path.abspath(__file__))
CONFIG_DIR = os.path.join(HERE, "configs")
OUT_JSON = os.path.join(HERE, "results_1029_新基准线.json")
LEDGER_DIR = os.path.join(HERE, "ledgers_1029_新基准线")

#: ★ sanity check 的容差。buy_and_hold 从不空仓 → 闸门从不关 →
#   同敞口口径的择时贡献必须**恒等于 0**(不是「接近 0」,是浮点误差级别)。
SANITY_TOL = 1e-9


def _num(x):
    """把 numpy / pandas / Timestamp 转成 json 能写的东西。"""
    if isinstance(x, dict):
        return {str(k): _num(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_num(v) for v in x]
    if isinstance(x, pd.DataFrame):
        return _num(x.reset_index().to_dict(orient="records"))
    if isinstance(x, pd.Series):
        return _num(x.to_dict())
    if isinstance(x, (pd.Timestamp,)):
        return str(x.date())
    if isinstance(x, (np.integer,)):
        return int(x)
    if isinstance(x, (np.floating,)):
        v = float(x)
        return None if not np.isfinite(v) else v
    if isinstance(x, (np.bool_,)):
        return bool(x)
    if isinstance(x, float):
        return None if not np.isfinite(x) else x
    return x


def _load_raw(name: str) -> dict:
    import yaml
    with open(os.path.join(CONFIG_DIR, name), encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ================================================================ 要跑的清单

def variants() -> list[tuple[str, dict, list[str]]]:
    """
    (链名, 七步配置原始 dict, 口径备注) 的清单。

    ★ 已有结论能重算的全在这儿。跑不了的在 main() 里单独记一条「为什么跑不了」,
      ★ 不许悄悄少跑一条。
    """
    out: list[tuple[str, dict, list[str]]] = []

    # ---- ① sanity check:buy_and_hold(★ 必须第一个跑)
    out.append(("buy_and_hold", _load_raw("buy_and_hold.yaml"),
                ["★ sanity check 专用:它从不空仓 → 闸门从不关 → "
                 "同敞口口径的择时贡献必须恒等于 0"]))

    # ---- ② 流派一 趋势跟随 三档 slots(★ 报告第一节的主角)
    for s in (3, 5, 10):
        raw = _load_raw("trend_following.yaml")
        raw["slots"] = s
        raw["source_slots"] = ("配置主值 10(专家 10-28 结论);3 / 5 档为敏感度展示,"
                               "★ 不是挑最优")
        out.append((f"流派一_趋势跟随_slots{s}", raw,
                    [f"slots={s};口径与 results_1029_趋势跟随最终.json 同源"]))

    # ---- ③ 流派三 现金流纪律(★ 直接复用 run_fundamental 的变体构造,
    #        这样和 results_1029_基本面流派一三.json 是同一条链,数字可比)
    try:
        from .run_fundamental import cashflow_variants, deep_value_variants
        for name, raw, notes, _is_main in cashflow_variants():
            out.append((name, raw, list(notes)))
        for name, raw, notes, _is_main in deep_value_variants((12,)):
            out.append((name, raw, list(notes)))
    except Exception as e:      # pragma: no cover
        print(f"★ 复用 run_fundamental 的变体构造失败:{type(e).__name__}: {e}")

    # ---- ④ 技-* 已跑通的那几条 + 流派三 流动性猎杀
    for fn in ("技-1.yaml", "技-2.yaml", "技-8.yaml",
               "技-10.yaml", "技-12.yaml", "技-13.yaml",
               "liquidity_sweep.yaml"):
        raw = _load_raw(fn)
        nm = (raw.get("meta") or {}).get("name", fn)
        out.append((nm, raw, [f"配置原值(slots={raw.get('slots')})"]))

    return out


# ================================================================ 单条链

def run_one(name: str, raw: dict, notes: list[str], syms: list[str],
            m_cache: dict) -> dict:
    t0 = time.time()
    print("=" * 78)
    print(f"跑链:{name}")
    cfg = chain.ChainConfig.from_dict(raw)
    rep = cfg.adapt_report
    if not rep.ok:
        raise RuntimeError(f"{name} 还有没实现的规则,不许带着它跑:\n{rep.text()}")

    m = matrices.build(cfg.raw, syms)
    res = chain.run_chain(cfg, syms, m=m)
    os.makedirs(LEDGER_DIR, exist_ok=True)
    res.save_ledger(os.path.join(LEDGER_DIR, f"{name}.csv"))
    n = len(res.ledger)
    print(f"  笔数 {n}")

    suite = bench_lines.bench_suite(cfg, res, syms, m=m, m_cache=m_cache)
    rec = _num({k: v for k, v in suite.items() if not k.startswith("_")})
    rec["口径备注"] = notes
    rec["引擎显式关掉的东西"] = matrices.disabled_log()
    rec["耗时秒"] = round(time.time() - t0, 1)

    print(f"  静态基准超额 {suite['★静态基准超额']:+.2%} = "
          f"选股贡献 {suite['★选股贡献']:+.2%} + 择时贡献 {suite['★择时贡献']:+.2%}"
          f"  (残差 {suite['★加法恒等式自检']['残差']:.2e})")
    print(f"  闸门:关闸 {suite['闸门统计']['关闸天数']} 天 "
          f"({suite['闸门统计']['关闸占比']:.1%})")
    print(f"  {suite['★判定_这条策略会不会选股']}")
    ban = suite.get("样本警示")
    if ban:
        print(f"  {ban}")
    print(f"  (用了 {rec['耗时秒']} 秒)")
    return rec


# ================================================================ sanity check

def sanity_check(rec: dict) -> dict:
    """
    ★★ 「能认出自己坏了」的检查点(硬纪律第 11 条)。

    buy_and_hold 从不空仓 → 它的 ② 环境过滤一条规则都没有 → 闸门全程开着 →
    同敞口口径的动态开关基准和静态基准应当**逐日完全相同** →
    ★ 择时贡献恒等于 0,加法恒等式残差恒等于 0。

    之前出过三次「静默失效」(exit.rules 没被执行 / ranking 被忽略 /
    多级移动止损只取第一级),所以新代码必须有一个自己能发现坏掉的点。
    这就是那个点:它不通过,这一轮的所有择时/选股拆分数字全部作废。
    """
    g = rec["闸门统计"]
    timing = rec["★择时贡献"]
    resid = rec["★加法恒等式自检"]["残差"]
    checks = [
        {"检查项": "闸门全程开着(关闸天数 = 0)",
         "实测": g["关闸天数"], "期望": 0, "过": g["关闸天数"] == 0},
        {"检查项": "★ 择时贡献恒等于 0(同敞口口径)",
         "实测": timing, "期望": 0.0,
         "过": timing is not None and abs(timing) <= SANITY_TOL},
        {"检查项": "加法恒等式残差恒等于 0",
         "实测": resid, "期望": 0.0,
         "过": resid is not None and abs(resid) <= SANITY_TOL},
        {"检查项": "静态基准与动态开关基准(同敞口)总收益逐日相同",
         "实测": rec["基准三_动态开关基准_同敞口口径"]["基准总收益"],
         "期望": rec["基准二_静态基准"]["基准总收益"],
         "过": abs(rec["基准三_动态开关基准_同敞口口径"]["基准总收益"]
                   - rec["基准二_静态基准"]["基准总收益"]) <= SANITY_TOL},
    ]
    ok = all(c["过"] for c in checks)
    return {
        "链": "buy_and_hold",
        "为什么拿它当 sanity check":
            "它从不空仓(② 环境过滤一条规则都没有)→ 闸门从不关 → "
            "择时贡献在同敞口口径下必须恒等于 0。不是 0 就是代码坏了。",
        "容差": SANITY_TOL,
        "逐项": checks,
        "★结论": ("✅ 通过 —— 择时/选股的拆分可以用" if ok else
                   "★★ 没过 —— 本轮所有择时/选股拆分数字全部作废,先修代码"),
        "过": ok,
        "★口径说明":
            "★ 原文口径(开闸记满仓指数)下 buy_and_hold 的差额**不是** 0 "
            f"而是约 {rec['★选股贡献_原文口径'] - rec['★选股贡献']:+.2%} —— "
            "那是 Ē(实测 0.981,因为有零头现金和摩擦)和 1.0 的敞口差,"
            "★ 不是 bug。择时贡献一律用同敞口口径算,就是为了把这个敞口差剔掉,"
            "让加法恒等式成立、让 sanity check 有锚。",
    }


# ================================================================ 主程序

def main(argv=None) -> int:
    print(data.cohort_report())
    print()
    print(split_gate.summary())
    print()
    syms = [s for s in data.full_universe().pool("ALL") if s in cache.symbols()]
    print(f"全池 {len(syms)} 只,绩效窗口 {data.PERF_START} .. {data.PERF_END}"
          f"(预热自 {cache.load()['close'].index[0].date()})")
    print(f"★ 读的缓存:{cache.PANEL_PARQUET}")
    print(f"★ 缓存构建时间:"
          f"{time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(os.path.getmtime(cache.PANEL_PARQUET)))}")
    print(f"★ 市场中性规则阈值:{bench_lines.MARKET_NEUTRAL_EBAR_MAX}"
          f"(None = 整条去掉;旧值 {bench_lines.MARKET_NEUTRAL_EBAR_MAX_LEGACY})\n")

    commit = os.popen("git -C %s rev-parse HEAD" % HERE).read().strip() or "(拿不到)"

    # ★ 报告里必须写明「读的是哪份缓存、它是什么时候烤的」——
    #   今天数据层被改了三次、parquet 重烤了三次,不写清这一条,
    #   过两天没人能复现这批数字。
    cache_info = {}
    for label, p in (("价格面板", cache.PANEL_PARQUET),
                     ("面板元数据", cache.META_PARQUET)):
        if os.path.exists(p):
            cache_info[label] = {
                "路径": p,
                "构建时间": time.strftime("%Y-%m-%d %H:%M:%S",
                                          time.localtime(os.path.getmtime(p))),
                "字节": os.path.getsize(p)}
        else:
            cache_info[label] = {"路径": p, "★": "不存在"}

    out: dict = {
        "跑的时间": time.strftime("%Y-%m-%d %H:%M:%S"),
        "git_commit_跑的时候": commit,
        "★读的哪份缓存": cache_info,
        "★市场中性规则": bench_lines.MARKET_NEUTRAL_NOTE,
        "★市场中性规则_当前阈值": bench_lines.MARKET_NEUTRAL_EBAR_MAX,
        "全池只数": len(syms),
        "绩效窗口": f"{data.PERF_START} .. {data.PERF_END}"
                     f"(预热自 {cache.load()['close'].index[0].date()})",
        "★本轮新增的三条基准线": {
            "基准三_动态开关基准": "闸门关 → 无风险利率;闸门开 → 成分匹配指数。"
                                   "量纯选股能力。两个口径都报(原文 / 同敞口)",
            "基准四_槽位机会成本线": "站上 50 日均线 → 全额持 QQQ(★ 仓库没有 QQQ,"
                                     "用替代品);跌破 → 无风险利率。比卡玛和信息比率",
            "基准五_朴素基准": "朴素-均值回归版 + 朴素-RSI版,★ 同槽位约束、同成本扣减",
        },
        "★择时贡献的定义": "动态开关基准(同敞口口径)收益 − 静态基准收益。"
                            "恒等式:静态基准超额 ≡ 选股贡献 + 择时贡献。"
                            "★ 这一笔绝不许混进选股能力。",
        "★基准家族口径": bench_lines.FAMILY_PLAN,
        "★QQQ 缺口": bench_lines.QQQ_MISSING_NOTE,
        "★顺手量到的数据问题": bench_lines.ETF_SPLIT_FINDINGS,
        "链": [],
        "跑不了的": [],
    }

    m_cache: dict = {}
    for name, raw, notes in variants():
        try:
            rec = run_one(name, raw, notes, syms, m_cache)
            out["链"].append(rec)
            if name == "buy_and_hold":
                out["★sanity_check_buy_and_hold"] = sanity_check(rec)
                print("\n" + "=" * 78)
                print("★ sanity check:" + out["★sanity_check_buy_and_hold"]["★结论"])
                for c in out["★sanity_check_buy_and_hold"]["逐项"]:
                    print(f"   {'✅' if c['过'] else '★'} {c['检查项']}:"
                          f"实测 {c['实测']} / 期望 {c['期望']}")
                print("=" * 78 + "\n")
        except Exception as e:
            print(f"★ {name} 跑挂了:{type(e).__name__}: {e}")
            traceback.print_exc()
            out["跑不了的"].append({"链名": name,
                                    "原因": f"{type(e).__name__}: {e}"})

    # ★ 没跑的那几条,明说为什么没跑 —— 不许悄悄少报
    out["跑不了的"] += [
        {"链名": "流派二_动量结构VCP(vcp_momentum.yaml)",
         "原因": "配置里 ⑤「滞涨换血」rotate_out 的触发条件未定义、"
                 "mansfield_rs_positive(against: SECTOR) 不能跑(行业归属非 PIT)"
                 " → 适配层判定不可跑。★ 第二轮用的是「只留门禁1」的手改变体,"
                 "那个变体在 run_second_round_1029.py 里(另一个 agent 正在改该文件),"
                 "★ 本轮没动它,避免冲突。"},
        {"链名": "流派二_盈利质量(quality_compounder.yaml)",
         "原因": "六条规则未实现(gross_profit_to_assets_rank_above / ma_stack_bullish /"
                 " bullish_candle_breakout_prior_high / fundamental_veto / "
                 "close_below_ma_trail 等)→ 适配层判定不可跑"},
    ]

    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(_num(out), fh, ensure_ascii=False, indent=2)
    print(f"\n原始数字已写:{OUT_JSON}")
    print(f"交易流水已写:{LEDGER_DIR}/")
    print(f"git commit(跑的时候):{commit}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
