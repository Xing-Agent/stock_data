"""
run_p5_1029 —— 批五修正的跑链脚本(2026-10-29)。

大白话(三秒):外部专家在我们代码里挑出一个真 bug(技-11 把两天合成了一天),
又让我们把 技-14 的 ADX 换成 RSI(2)。这个脚本把【修之前】和【修之后】
并排跑一遍,好让人一眼看出「修这个 bug 改了多少」。

跑什么:
  第一件 · 技-11
    ① 旧实现(一日合并版:下刺+收复同一天,★ 并要求收复当天缩量)—— 原样重跑
    ② 旧 XING 版(跌破 20 日低点再收回,不看量)—— 原样重跑,做底色
    ③ 新两日结构版:Spring 日量门槛 ≥0.8× / ≥1.0× / ≥1.2× SMA50
       × Test 窗口 N = 2 / 3 / 5 —— ★ 九格,看单调性
  第三件 · 技-14
    ④ 旧三道过滤器版(含 ADX≤25)—— 原样重跑
    ⑤ 新组合(Trend_Gate + RSI2≤10 + Reversal)★ 带带宽熔断
    ⑥ 新组合 ★ 不带带宽熔断

★ 硬纪律一条不改,全部沿用 pat6_run.run_one:
  预热 2014 / 绩效 2018-01-02 起 · Bootstrap 10 种子并池 × B=1000
  (★ 强制打印单种子极差)· 三套对照组(★ 不报极性反转)·
  随机对照按实际成交笔数校准 · 两窗口两池子硬关(FNV-1a)·
  集中度自检无条件输出 · 配置用 load_yaml_strict 读。

★ 内存纪律:8GB 机器,今天 OOM 过一次。★ 串行跑,跑前打印 free,
  每条链之后打印 RSS;技-11 和 技-14 分两个进程跑(--only 过滤),
  免得算子缓存一直堆着。

跑法:
  python3 -m engine.run_p5_1029 技-11
  python3 -m engine.run_p5_1029 技-14
"""

from __future__ import annotations

import copy
import json
import os
import subprocess
import time

from . import cache, data, ops_1029, pat6_ops, pat6_run, stats_gate

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_JSON = os.path.join(HERE, "results_1029_批五修正.json")
LEDGER_DIR = os.path.join(HERE, "ledgers_1029_批五修正")


# ---------------------------------------------------------------- 覆盖函数

def _two_day(vmin: float, test_n: int):
    """技-11 两日结构:只改 Spring 日量门槛与 Test 窗口长度。"""
    def f(raw):
        hit = 0
        for r in raw["entry"]["rules"]:
            if r["type"] == "pat6_spring_two_day":
                r["params"]["spring_vol_min_ratio"] = float(vmin)
                r["params"]["test_max_bars"] = int(test_n)
                hit += 1
        assert hit == 1, "两日结构的进场规则没找到 —— 配置被动过了"
        raw["meta"]["name"] = f"技-11_两日结构_量≥{vmin}×_Test窗口{test_n}日"
        return raw
    return f


def _drop_bw_gate(raw):
    """技-14 新组合:把带宽突变熔断那一道显式关掉(enabled: false)。"""
    hit = 0
    for r in raw["entry"]["rules"]:
        if r["type"] == "pat6_bb_bw_jump_gate":
            r["enabled"] = False
            hit += 1
    assert hit == 1, "带宽熔断那一道没找到 —— 配置被动过了"
    raw["meta"]["name"] = "技-14_行业版_RSI2_不带带宽熔断"
    return raw


#: (报表名, 配置文件, 覆盖函数, 这一版是什么, 归属)
VARIANTS = [
    # ===================== 第一件 · 技-11 =====================
    ("技-11 · ★旧实现(一日合并版:收复日要求缩量 ≤0.65×)",
     "技-11-行业.yaml", None,
     "★★ 这就是专家挑出来的 bug 版:把 Spring 日和 Test 日合成了一天,"
     "并要求【下刺收复当天】缩量 ≤0.65×SMA50 —— 物理上自相矛盾。"
     "原样重跑,做「修了多少」的分母。",
     "旧实现(一日合并)"),
    ("技-11 · XING版(跌破 20 日低点再收回 · 完全不看量)",
     "技-11-XING.yaml", None,
     "我们线上那条链的写法:只要下刺再收回就买,量多大都不看。做底色。",
     "XING版"),
] + [
    (f"技-11 · ★两日结构(Spring 日量 ≥{v}× · Test 窗口 {n} 日)",
     "技-11-两日结构.yaml", _two_day(v, n),
     f"★★ 修 bug 后的版本:Spring 日【要求有量】≥{v}×SMA50,"
     f"Test 日(Spring 后 {n} 个交易日内的回踩日)才要求缩量 ≤0.65×SMA50。"
     f"★ 深度不设上限。",
     f"两日结构·量≥{v}×·N={n}")
    for v in (0.8, 1.0, 1.2) for n in (2, 3, 5)
] + [
    # ===================== 第三件 · 技-14 =====================
    ("技-14 · ★旧三道过滤器版(含 ADX(14) ≤25)",
     "技-14-行业.yaml", None,
     "★★ 专家自认是「教科书里流传最广但未经解耦的教条毒药」的那一版:"
     "三步进场 + 三道过滤器(200 日线 / ADX≤25 / 带宽熔断)。"
     "原样重跑,做「换掉 ADX 改了多少」的分母。",
     "旧版·三道过滤器"),
    ("技-14 · ★新组合 RSI(2)≤10(★ 带带宽熔断)",
     "技-14-行业-RSI2.yaml", None,
     "★★ 废除 ADX≤25,换成 RSI(2)≤10。"
     "Entry = (Close>SMA200 且 SMA200 20 日斜率≥0) 且 RSI2≤10 且 "
     "(Low<下轨 且 Close>下轨 且 Close>Open);★ 带宽熔断保留。",
     "新版·RSI2·带熔断"),
    ("技-14 · ★新组合 RSI(2)≤10(★ 不带带宽熔断)",
     "技-14-行业-RSI2.yaml", _drop_bw_gate,
     "同上,★ 把带宽突变熔断那一道显式关掉(enabled: false)—— "
     "专家没说废这一道,所以单独做对照。",
     "新版·RSI2·不带熔断"),
]


def main(argv=None) -> int:
    pat6_ops.install()
    print(subprocess.run(["free", "-m"], capture_output=True, text=True).stdout)
    head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=HERE,
                          capture_output=True, text=True).stdout.strip()
    # ★ 缓存构建时间必须进报告 —— 不许凭记忆写
    cache_file = os.path.join(HERE, "cache", "ohlcv_panel.parquet")
    cache_built = time.strftime("%Y-%m-%d %H:%M:%S",
                                time.localtime(os.stat(cache_file).st_mtime))

    # ★ 让 run_one 把流水写到本次这个目录,★ 不和六条三版的流水混在一起
    pat6_run.LEDGER_DIR = LEDGER_DIR
    syms = cache.symbols()
    print(f"池子 {len(syms)} 只;绩效窗口 {data.PERF_START} .. {data.PERF_END}")
    print(f"缓存 {cache_file}\n  构建时间 {cache_built}")

    only = set(argv or [])
    rows, fails = [], []
    for label, yml, ov, why, ver in VARIANTS:
        if only and not any(k in label for k in only):
            continue
        try:
            rows.append(pat6_run.run_one(label, yml, ov, why, ver, syms))
        except Exception as e:                       # noqa: BLE001
            import traceback
            traceback.print_exc()
            fails.append({"报表名": label, "错误": f"{type(e).__name__}: {e}"})

    # ★ 只跑了一部分时与已有结果**合并**,不覆盖
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
        "缓存文件": cache_file,
        "缓存构建时间": cache_built,
        "池子只数": len(syms),
        "绩效窗口": [data.PERF_START, data.PERF_END],
        "判据口径": {
            "Bootstrap": f"{stats_gate.N_SEEDS_DEFAULT} 个种子并池 × "
                         f"B={stats_gate.B_DEFAULT},在交易流水层面重抽",
            "经验p值": "(1 + #{rand ≥ signal}) / (B + 1)",
            "三套对照组": "条件分层随机 / 块重排 / 波动率选择检验",
            "★不报的": "极性反转 —— 死代码(Z_做空 ≡ −Z_做多)",
            "随机对照校准": "按实际成交笔数校准,校准只看笔数不看成绩",
            "样本下限": stats_gate.SYSTEM_MIN_TRADES,
        },
        "各版结果": rows,
        "跑挂的": fails,
        "pat6备注": pat6_ops.notes(),
    }
    with open(OUT_JSON, "w", encoding="utf-8") as fh:
        json.dump(out, fh, ensure_ascii=False, indent=1, default=str)
    print(f"\n写好 {OUT_JSON}(共 {len(rows)} 版,挂了 {len(fails)} 版)")
    return 0


if __name__ == "__main__":
    import sys
    raise SystemExit(main(sys.argv[1:]))
