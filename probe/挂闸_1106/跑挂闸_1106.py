# -*- coding: utf-8 -*-
"""
★★★ 三条代表 × 挂闸/不挂闸,在**同一个池**上对照。
★ 预先登记见 手册/69-挂环境闸-跑前预先登记-1106.md(★★ 跑前已写死)。
★★★ engine/ 零改动 —— 进程内覆盖层。
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
from engine import cache, data, pool_scope                      # noqa: E402
import rerun_core_1030 as RC                                    # noqa: E402

NEWPANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
NEWPOOL = "probe/newpool_1106/pool_NEWPOOL_ALL_1106.csv"
HOLD = "probe/新策略_1106/holdout_newpool_1106.json"
SRC = os.path.join(ROOT, "engine", "configs")
CFGDIR = os.path.join(HERE, "configs")
OUT = os.path.join(HERE, "挂闸结果_1106.json")

代表 = {"震荡": "技-14-原著.yaml", "突破": "技-6-原著.yaml", "大波段": "技-1.yaml"}
闸均线 = [100, 200, 300]            # ★ 相邻三点


def 装覆盖层() -> dict:
    wide = pd.read_parquet(NEWPANEL)
    cache._PANEL = {f: wide[f] for f in wide.columns.levels[0]}
    idx = pool_scope.PoolIndex(path=NEWPOOL)
    RC._IDX_CACHE["idx"] = idx
    data.PERF_START = "2015-01-01"
    return {"面板只数": int(cache._PANEL["close"].shape[1]), "池表行数": idx.rows,
            "★tier与rank不一致": len(idx.tier_mismatch),
            "PERF_START": data.PERF_START, "PERF_END": data.PERF_END}


def main() -> int:
    t0 = time.time()
    自证 = 装覆盖层()
    print("★ 覆盖层:", json.dumps(自证, ensure_ascii=False), flush=True)
    hold = json.load(io.open(HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], set(hold["留出池名单"])
    assert not (set(dev) & hs)
    print(f"★ 研发池 {len(dev)} 只(留出 {len(hs)} 只不碰)", flush=True)

    import run_friction_1104 as F                                # noqa: E402
    F.load_pools = lambda: (dev, hs, hold)
    F.CONFIG_DIR = CFGDIR
    F.PER_CHAIN = os.path.join(HERE, "per_chain_1106")
    F.LEDGERS = os.path.join(HERE, "ledgers_1106")
    F.OUT = OUT
    os.makedirs(CFGDIR, exist_ok=True)
    os.makedirs(F.PER_CHAIN, exist_ok=True); os.makedirs(F.LEDGERS, exist_ok=True)

    结果, 失败 = [], []
    for 族, fn in 代表.items():
        base = yaml.safe_load(io.open(os.path.join(SRC, fn), encoding="utf-8"))
        # ★★★ 自证:原配置的 regime 必须是空的(不然这一轮的对照就不成立)
        orig = (base.get("regime") or {}).get("rules") or []
        assert not orig, f"★ {fn} 的 regime 本来就不空({len(orig)} 条),停下来查"
        版本 = [("不挂闸", None)] + [(f"挂闸{ma}日", ma) for ma in 闸均线]
        for 名, ma in 版本:
            raw = copy.deepcopy(base)
            if ma is not None:
                raw.setdefault("regime", {})["rules"] = [{
                    "type": "index_above_ma",
                    "params": {"symbol": "SPY", "ma": ma},
                    "source": ("★★ ②档 行业改进(Faber 2007;Brock 等 1992)。"
                               "★★★ 原著没写这条闸 —— 不许标成原著版。"),
                }]
                raw["regime"]["flatten_when_off"] = False
            label = f"{族}·{fn[:-5]}·{名}"
            tmp = f"_gate_{族}_{名}.yaml"
            io.open(os.path.join(CFGDIR, tmp), "w", encoding="utf-8").write(
                yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
            try:
                r = F.run_one(label, tmp, None, "挂闸_1106", dev, hs, {})
                结果.append({"链": label, "族": 族, "版本": 名, "结果": r})
                print(f"   ✓ {label}", flush=True)
            except Exception as e:
                失败.append({"链": label, "原因": f"{type(e).__name__}: {e}"})
                print(f"   ✗ {label} —— {type(e).__name__}: {e}", flush=True)
    io.open(OUT, "w", encoding="utf-8").write(json.dumps({
        "★口径": {"预先登记": "手册/69-挂环境闸-跑前预先登记-1106.md",
                  "池": "新池研发 2,224 只(两版同池)", "engine改动": "零", **自证,
                  "闸": "index_above_ma(SPY, ma),flatten_when_off=false",
                  "★相邻三点": 闸均线,
                  "★★★ 这一轮不能回答什么": "不能回答「适合什么环境」—— 只能回答「挂上闸成绩变没变」"},
        "条数": len(结果), "失败": 失败, "逐条": 结果,
        "耗时秒": round(time.time() - t0, 1),
    }, ensure_ascii=False, indent=1, default=str))
    print(f"\n★ 写到 {OUT} · 成 {len(结果)} · 败 {len(失败)} · {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
