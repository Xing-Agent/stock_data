# -*- coding: utf-8 -*-
"""
★★★ 测仓位 —— 三根轴里**唯一没测过的那根**（★ Lin 1106 工单优先级 ④）

★★ 为什么要测它（★ 《83》第六步之后的账）：
   · **买**：直接测过 → **没有优势**（0 条正显著、7 条负显著）
   · **卖**：直接测过 → **测不出**
   · ★★★ **仓位**：**一次都没测过** —— ★ 它是「那 1.543 的利润因子」仅剩的候选解释

★★★★★ 一条方法论上的要紧话（★ 先写在这儿，免得测完才发现用错尺子）：
   ★ **大盘替身对仓位几乎是瞎的。** —— ★★ 它量的是**每一笔的收益率**
     （`net_pnl ÷ notional_in`），而换仓位法**不改变同一笔的进出场价** →
     ★★★ 共同的那些笔，收益率**一模一样**。
   → ★ 仓位只改三件事：**哪些笔能开得出来**（现金/槽位约束）、
     **账户层的净值曲线**、以及**账户百分比口径下的利润因子**。
   → ★★★ 所以测仓位的尺子是 **《91》那一套组合层指标**
     （年化 · 最大回撤 · 卡玛 · 溃疡 · 回本天数 · 信息比率 · alpha），
     ★★ 大盘替身只当旁证。

★ 三种仓位法（★★ 名字是从 `engine/chain.py:455-626` **打出来的**，不是凭记忆写的，规矩⑬）：
   · `risk_fraction`      —— 按单笔风险定量（风险 1% ÷ 进场价减止损价）
   · `fixed_fraction`     —— 每笔固定买 `max_weight` 的权益
   · `equal_weight_all`   —— ★★★ 不限槽位，当天候选**平分现金**
     （★ 工单里写的「equal_all」是代码里的变量名；**配置里的值是 `equal_weight_all`**）

★★★ 三条纪律：engine 零改动（进程内覆盖层）· 只跑研发池 · 每条臂跑完立刻落盘（可续跑）。
"""
from __future__ import annotations
import copy, io, json, os, sys, time
import pandas as pd, yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "friction_rerun_1104"))
sys.path.insert(0, os.path.join(ROOT, "probe", "v2_rerun_1030"))
os.chdir(ROOT)

from engine import cache, data, pool_scope                        # noqa: E402
import rerun_core_1030 as RC                                      # noqa: E402
from engine import pat6_ops                                       # noqa: E402
pat6_ops.install()

NEWPANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
NEWPOOL = "probe/newpool_1106/pool_NEWPOOL_ALL_1106.csv"
HOLD = "probe/新策略_1106/holdout_newpool_1106.json"
SRCCFG = "probe/新策略_1106/configs"
CFGDIR = os.path.join(HERE, "configs")
ARMS = os.path.join(HERE, "arms_1107")
OUT = os.path.join(HERE, "测仓位结果_1107.json")

# ★★★ 宿主：三条融合策略，★ 主参数一律**钉在中间那一点**（规矩：测仓位就只准仓位变）
宿主 = {
    "融-1_震荡":   ("entry.rules.0.params.threshold", 10.0),
    "融-2_突破":   ("entry.rules.0.params.lookback", 40),
    "融-3_大波段": ("entry.rules.0.params.lookback", 90),
}
# ★★ 三种仓位法。★ risk_fraction 那一点就是现有 45 条链的口径 → 当**对照**
仓位 = [
    ("risk_fraction", {"risk_per_trade": 0.01, "max_positions": 10, "max_weight": 0.10}),
    ("fixed_fraction", {"risk_per_trade": 0.01, "max_positions": 10, "max_weight": 0.10}),
    ("equal_weight_all", {"risk_per_trade": 0.01, "max_positions": 10, "max_weight": 0.10}),
]


def 装覆盖层() -> dict:
    wide = pd.read_parquet(NEWPANEL)
    cache._PANEL = {f: wide[f] for f in wide.columns.levels[0]}
    n_sym = cache._PANEL["close"].shape[1]
    del wide
    idx = pool_scope.PoolIndex(path=NEWPOOL)
    RC._IDX_CACHE["idx"] = idx
    data.PERF_START = "2015-01-01"
    return {"面板只数": int(n_sym), "池表行数": idx.rows,
            "PERF_START": data.PERF_START, "PERF_END": data.PERF_END}


def 臂路径(label: str) -> str:
    import hashlib
    return os.path.join(ARMS, f"arm_{hashlib.sha256(label.encode()).hexdigest()[:16]}.json")


def 改一处(raw: dict, dotted: str, val) -> dict:
    d = copy.deepcopy(raw); cur = d; parts = dotted.split(".")
    for k in parts[:-1]:
        cur = cur[int(k)] if k.isdigit() else cur[k]
    cur[parts[-1]] = val
    return d


def main() -> int:
    t0 = time.time()
    os.makedirs(CFGDIR, exist_ok=True); os.makedirs(ARMS, exist_ok=True)
    自证 = 装覆盖层()
    print("★ 覆盖层:", json.dumps(自证, ensure_ascii=False), flush=True)

    hold = json.load(io.open(HOLD, encoding="utf-8"))
    dev, HOLDSET = hold["研发池名单"], set(hold["留出池名单"])
    assert not (set(dev) & HOLDSET), "★ 研发/留出有交集，停"

    import run_friction_1104 as F                                  # noqa: E402
    F.load_pools = lambda: (dev, HOLDSET, hold)
    F.CONFIG_DIR = CFGDIR
    F.PER_CHAIN = os.path.join(HERE, "per_chain_1107")
    F.LEDGERS = os.path.join(HERE, "ledgers_1107")
    F.OUT = OUT
    os.makedirs(F.PER_CHAIN, exist_ok=True); os.makedirs(F.LEDGERS, exist_ok=True)

    结果, 失败 = [], []
    for 名, (dotted, 点) in 宿主.items():
        base = yaml.safe_load(io.open(os.path.join(SRCCFG, f"{名}.yaml"), encoding="utf-8"))
        base = 改一处(base, dotted, 点)
        for 法, 参 in 仓位:
            label = f"{名}·仓位={法}"
            p孤 = 臂路径(label)
            if os.path.exists(p孤):
                try:
                    结果.append(json.load(io.open(p孤, encoding="utf-8")))
                    print(f"   ⟳ {label}（已跑过，跳过）", flush=True)
                    continue
                except Exception:
                    pass
            raw = copy.deepcopy(base)
            raw["sizing"] = {"type": 法, "params": dict(参),
                             "source": "★ ③我们的 —— 这一轮**只**换仓位法，"
                                       "主参数钉在中间点（测仓位就只准仓位变）"}
            tmp_name = f"_sz_{名}_{法}.yaml"
            io.open(os.path.join(CFGDIR, tmp_name), "w", encoding="utf-8").write(
                yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
            try:
                r = F.run_one(label, tmp_name, None, "测仓位_1107", dev, HOLDSET, {})
                rec = {"链": label, "宿主": 名, "仓位法": 法, "结果": r}
                io.open(p孤, "w", encoding="utf-8").write(
                    json.dumps(rec, ensure_ascii=False, indent=1, default=str))
                结果.append(rec)
                print(f"   ✓ {label}", flush=True)
            except Exception as e:
                失败.append({"链": label, "原因": f"{type(e).__name__}: {e}"})
                print(f"   ✗ {label} —— {type(e).__name__}: {e}", flush=True)
            finally:
                q = os.path.join(CFGDIR, tmp_name)
                if os.path.exists(q):
                    os.remove(q)

    io.open(OUT, "w", encoding="utf-8").write(json.dumps({
        "★口径": {**自证, "只跑研发池": True, "engine改动": "零 —— 进程内覆盖层",
                 "★★★主判据": "★ 组合层指标（《91》那一套）—— **不是**大盘替身",
                 "★★★为什么": "大盘替身量每笔收益率，而换仓位不改同一笔的进出场价 → 对仓位几乎瞎",
                 "宿主主参数": {k: v[1] for k, v in 宿主.items()},
                 "三种仓位法": [f for f, _ in 仓位]},
        "条数": len(结果), "★★★失败": 失败, "逐条": 结果,
        "耗时秒": round(time.time() - t0, 1),
    }, ensure_ascii=False, indent=1, default=str))
    print(f"\n★ 写到 {OUT} · 成 {len(结果)} · 败 {len(失败)} · {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
