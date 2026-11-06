# -*- coding: utf-8 -*-
"""
★★★ 秒级校验这 4 条新零件（★ 规矩⑨：改配置/加零件先过校验器，不许靠跑一轮才知道对不对）。
★★ 每条都要报**实测覆盖率**和**触发率** —— ★★★ 覆盖率 0 就等于没补上，必须大声报。
★ 规矩⑰：凡是「算不出就跳过」的分支，要报跳了多少。
"""
import io, json, os, sys
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT); sys.path.insert(0, HERE); os.chdir(ROOT)

import 补最后四条_1107 as NEW                                   # noqa: E402
信息 = NEW.install()
from engine import matrices as M, cache                        # noqa: E402

报 = {"★装上了": 信息, "★口径": {
    "engine改动": "零 —— 进程内覆盖层",
    "覆盖率": "有非 NaN 值的「日×票」格子数 ÷ 总格子数",
    "触发率": "判为 True 的格子数 ÷ 有值的格子数",
    "★★★覆盖率为0": "等于没补上 —— 必须大声报，不许打空表",
}, "逐条": []}

# ★ 抽样：★★ 用老池 pilot_300 里**有财报的**票（基本面类要财报，技术面类只要价格）
票 = sorted(cache.symbols())[:40] if hasattr(cache, "symbols") else []
if not 票:
    票 = sorted([d for d in os.listdir("pilot_300") if not d.startswith(".")])[:40]
print(f"★ 抽样 {len(票)} 只：{票[:6]}…", flush=True)
close = cache.field("close", 票)
idx = close.index
print(f"★ 日历 {idx[0].date()} → {idx[-1].date()} · {len(idx)} 个交易日", flush=True)


def 量(名, m, 备注="", 底层: pd.DataFrame | None = None):
    """★★★ 1107 修一处**我自己的量错**（★ 规矩④：数字变好看先当自己错了）：

    ★ 第一版我拿 `m.notna()` 当覆盖率 —— ★★ 而这些规则最后都 `.fillna(False)`，
      ★★★ 所以布尔矩阵**永远 100% 非 NaN** → 量出来「覆盖率 100%」是**假的**，
      它量的是「有没有算出一个布尔值」，不是「底层指标有没有数」。
    → ★★ 现在覆盖率一律看**底层指标**（传 `底层`）；★ 不传的（纯价量规则）
      写明「底层=价量，覆盖率看价格面板」。
    """
    m = m.reindex(index=idx, columns=票)
    总 = m.size
    真 = int((m == True).sum().sum())                     # noqa: E712
    rec = {"条": 名, "总格子": 总, "触发": 真,
           "★触发率_占全格": round(真 / 总 * 100, 3) if 总 else None,
           "备注": 备注}
    if 底层 is not None:
        b = 底层.reindex(index=idx, columns=票)
        有 = int(b.notna().sum().sum())
        rec["★底层有值"] = 有
        rec["★★底层覆盖率"] = round(有 / 总 * 100, 2) if 总 else 0.0
        rec["★触发率_占有值"] = round(真 / 有 * 100, 3) if 有 else None
        if 有 == 0:
            rec["★★★失败"] = "底层覆盖率 0 —— **等于没补上**"
    else:
        rec["★底层"] = "价量（覆盖率看价格面板，不是这条规则的事）"
        if 真 == 0:
            rec["★★★失败"] = "一次都没触发 —— ★ 要查是不是算错了"
    print("  " + json.dumps(rec, ensure_ascii=False), flush=True)
    报["逐条"].append(rec)
    return rec


print("\n★★ ① 基 1.4/4.1 时序估值分位（★ 跟自己历史比）", flush=True)
for mult in ("pe", "pb", "ev_ebit"):
    try:
        raw = NEW._倍数矩阵(M, mult, 票, idx)
        cov = int(raw.notna().sum().sum())
        print(f"   · 倍数 {mult} 原始覆盖率 "
              f"{cov/raw.size*100:.2f}%（{cov} 格）", flush=True)
        for win in (756, 1260):            # ★ 3 年 / 5 年 —— ★★ 相邻两点先看覆盖率
            pct = NEW._时序分位(raw, win)      # ★★★ 这才是底层（★ 分位本身，未 fillna）
            r = NEW.池规则(M, {"type": "valuation_ts_percentile_below",
                              "params": {"multiple": mult, "lookback_days": win,
                                         "percentile": 0.3}}, 票, idx)
            量(f"基1.4/4.1·{mult}·时序分位≤0.3·窗口{win}日", r,
              f"★ 窗口 {win} 个交易日 ≈ {win/252:.0f} 年；★★ 不满窗口算不出",
              底层=pct)
    except Exception as e:
        print(f"   ✗ {mult} —— {type(e).__name__}: {e}", flush=True)
        报["逐条"].append({"条": f"基1.4/4.1·{mult}", "★★★失败": f"{type(e).__name__}: {e}"})

print("\n★★ ② 技 5.1 突破后跟进验证（★ 日频近似，③档）", flush=True)
for n in (3, 4, 5):                        # ★★★ 原著区间 3~5 → 相邻三点全跑（规矩②）
    r = NEW.离场规则(M, {"type": "momentum_not_followed_through",
                       "params": {"days": n, "min_gain_pct": 0.0}}, 票)
    量(f"技5.1·最近{n}天净涨幅≤0就走", r, "★★★ 近似：原定义要「距进场第N天」，矩阵里没有进场日")

print("\n★★ ③ 技 5.2 回踩量价健康度", flush=True)
for 深 in (6.0, 8.0, 10.0):                 # ★★★ 原著没给深度上限 → 相邻三点
    r = NEW.离场规则(M, {"type": "pullback_health_broken",
                       "params": {"lookback": 20, "volume_factor": 0.6,
                                  "max_drawdown_pct": 深}}, 票)
    量(f"技5.2·回踩放量或回撤≥{深}%就走", r, "★ 量门槛 0.6 倍是《78》给的（②档）")

print("\n★★ ④ 基 5.4 排名缓冲（★ 卖那一腿）", flush=True)
NEW._当前CFG = {"ranking": {"primary": {"formula": "ADV20", "order": "desc"}}}
for n in (20, 30, 40):                      # ★★★ 《78》给 30 → 相邻三点
    try:
        r = NEW.离场规则(M, {"type": "rank_drop_out_of_top",
                           "params": {"exit_rank": n}}, 票)
        量(f"基5.4·名次掉出前{n}就走", r,
          f"★ 抽样只有 {len(票)} 只 → ★★ 前{n}名在 {len(票)} 只里的意义和全池不同（只校验能不能算）")
    except Exception as e:
        print(f"   ✗ 前{n} —— {type(e).__name__}: {e}", flush=True)
        报["逐条"].append({"条": f"基5.4·前{n}", "★★★失败": f"{type(e).__name__}: {e}"})

print("\n★★ ⑤ 基 5.4 第二条腿 · 成本门槛（★ 不是矩阵，是要报的数）", flush=True)
报["成本门槛示例"] = {
    "★口径": "★ 来回成本取我们回测用的摩擦（★★ 下面那个数要从配置里读，这里只示范算法）",
    "示例": [NEW.成本门槛(0.2, d) for d in (5, 20, 60, 120)],
}
print(json.dumps(报["成本门槛示例"], ensure_ascii=False, indent=1), flush=True)

print("\n★★ ⑥ 自证：**认不出的类型必须原样转回**（★ 铁律）", flush=True)
try:
    M.exit_signal_matrix({"rules": [{"type": "这个类型根本不存在_1107"}]}, 票[:3])
    报["★★★原样转回自证"] = "★★★ **失败** —— 它把不认识的类型吞掉了！"
    print("   ✗ 失败：吞掉了", flush=True)
except NotImplementedError as e:
    报["★★★原样转回自证"] = f"✓ 原函数照样大声报错：{str(e)[:70]}…"
    print(f"   ✓ 原函数照样报错（没被吞）", flush=True)

报["★★★一处自查出的量错"] = (
    "★ 第一版校验器拿布尔矩阵的 notna() 当覆盖率 → ★★ 因为规则末尾都 fillna(False)，"
    "★★★ 它永远报 100%。★ 已改成看**底层指标**的覆盖率（规矩④救的一处）。")
坏 = [r for r in 报["逐条"] if "★★★失败" in r]
报["★★★失败条数"] = len(坏)
报["★★★失败明细"] = 坏
io.open(os.path.join(HERE, "校验四条_报告_1107.json"), "w", encoding="utf-8").write(
    json.dumps(报, ensure_ascii=False, indent=1, default=str))
print(f"\n{'★★★ 有 '+str(len(坏))+' 条失败 —— 大声报' if 坏 else '★ 四条全部算得出'}")
