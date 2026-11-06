# -*- coding: utf-8 -*-
"""
★★★ 三条融合策略(融-1 震荡 / 融-2 突破 / 融-3 大波段)在**新池**上跑。

★★★ engine/ 一个字节不许改 → 全部用**进程内覆盖层**(和《47》修搜索同一技术):
   ① cache._PANEL      → 新池面板(2,807 只)
   ② RC.pool_index     → 指向新池排名表(并跳过老池的行数断言)
   ③ F.load_pools      → 新池冻结名单(研发 2,224 / 留出 583)
   ④ data.PERF_START   → 2015-01-01(新池排名从 2015 才排得出来)

★★ 每条跑**相邻三点**(规矩②:原著没给的数必须跑三点、报三点是否同向)。
★★★ 只跑研发池。留出池一次都不碰。
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

# ★★★ 必须调这一行:pat6 的进场/出场零件是**运行时挂钩**上去的,
#   `run_friction_1104.py` 在它自己的 main() 里调(第 566 行),
#   ★ 而我们绕过 main() 直接调 run_one → 钩子不会执行 → 那些零件会被判「还没法跑」。
#   ★★ 已核:非 pat6_* 的类型会原样转回原函数(pat6_ops.py:966),
#      所以加这一行**不会改变**本轮三条融合策略的结果(它们没用 pat6 零件)。
pat6_ops.install()

NEWPANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
NEWPOOL = "probe/newpool_1106/pool_NEWPOOL_ALL_1106.csv"
HOLD = os.path.join(HERE, "holdout_newpool_1106.json")
CFGDIR = os.path.join(HERE, "configs")
OUT = os.path.join(HERE, "新策略结果_1106.json")

# ★★ 相邻三点:每条只扫**一个**主参数(规矩②),其余保持配置里的中间值
SWEEP = {
    "融-1_震荡":   ("entry.rules.0.params.threshold", [5.0, 10.0, 15.0]),
    "融-2_突破":   ("entry.rules.0.params.lookback", [20, 40, 55]),
    # ★ 1106 修:融-3 的动量分位挪到 universe 了(原来错写在 entry,engine 拒绝)
    "融-3_大波段": ("entry.rules.0.params.lookback", [60, 90, 120]),
}


def 装覆盖层() -> dict:
    """★★★ 四个覆盖点。★ 返回自证信息,写进结果文件。"""
    wide = pd.read_parquet(NEWPANEL)
    cache._PANEL = {f: wide[f] for f in wide.columns.levels[0]}
    n_sym = cache._PANEL["close"].shape[1]

    idx = pool_scope.PoolIndex(path=NEWPOOL)     # ★ 不走 RC.pool_index 的行数断言
    RC._IDX_CACHE["idx"] = idx                   # ★ 直接塞进它的缓存

    data.PERF_START = "2015-01-01"               # ★ 新池 2014 排不出名次
    return {"面板只数": int(n_sym),
            "面板日期": [str(cache._PANEL['close'].index.min().date()),
                        str(cache._PANEL['close'].index.max().date())],
            "池表行数": idx.rows,
            "★池表 tier 与 rank 不一致行数": len(idx.tier_mismatch),
            "PERF_START": data.PERF_START, "PERF_END": data.PERF_END}


# ══════════════════════════════════════════════════════════════════════
# ★★★ 可续跑 —— 每条臂单独落盘,已跑过的跳过。
#   ★ 为什么要这个:长跑批活不过会话回合边界,被掐了就全白跑。
#   ★★ 有了它,反复调用同一个脚本就能一段一段把活干完。
# ══════════════════════════════════════════════════════════════════════
def 臂路径(臂目录: str, label: str) -> str:
    import hashlib
    h = hashlib.sha256(label.encode("utf-8")).hexdigest()[:16]
    return os.path.join(臂目录, f"arm_{h}.json")


def 读臂(臂目录: str, label: str):
    p = 臂路径(臂目录, label)
    if os.path.exists(p):
        try:
            return json.load(io.open(p, encoding="utf-8"))
        except Exception:
            return None
    return None


def 存臂(臂目录: str, label: str, payload: dict) -> None:
    os.makedirs(臂目录, exist_ok=True)
    io.open(臂路径(臂目录, label), "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, indent=1, default=str))


def 改一处(raw: dict, dotted: str, val) -> dict:
    d = copy.deepcopy(raw)
    cur = d
    parts = dotted.split(".")
    for k in parts[:-1]:
        cur = cur[int(k)] if k.isdigit() else cur[k]
    cur[parts[-1]] = val
    return d


def main() -> int:
    t0 = time.time()
    自证 = 装覆盖层()
    print("★ 覆盖层:", json.dumps(自证, ensure_ascii=False), flush=True)

    hold = json.load(io.open(HOLD, encoding="utf-8"))
    dev = hold["研发池名单"]
    assert not (set(dev) & set(hold["留出池名单"])), "★ 研发/留出有交集,停"
    print(f"★ 研发池 {len(dev)} 只(留出 {len(hold['留出池名单'])} 只一次都不碰)", flush=True)

    import run_friction_1104 as F                                  # noqa: E402
    F.load_pools = lambda: (dev, set(hold["留出池名单"]), hold)
    # ★★★ 1105 踩过的坑:只改 LEDGERS/OUT 不够 —— PER_CHAIN 也指着上一轮的目录,
    #   不改的话这一轮会被当成「已经跑过」整批跳过。三个一起改。
    F.CONFIG_DIR = CFGDIR                       # ★ run_one 用 CONFIG_DIR 拼 yml 路径
    F.PER_CHAIN = os.path.join(HERE, "per_chain_1106")
    F.LEDGERS = os.path.join(HERE, "ledgers_1106")
    F.OUT = OUT
    os.makedirs(F.PER_CHAIN, exist_ok=True); os.makedirs(F.LEDGERS, exist_ok=True)
    HOLDSET = set(hold["留出池名单"])
    ARMS = os.path.join(HERE, "arms_1106")
    os.makedirs(ARMS, exist_ok=True)

    结果, 失败 = [], []
    for name, (dotted, pts) in SWEEP.items():
        p = os.path.join(CFGDIR, f"{name}.yaml")
        base = yaml.safe_load(io.open(p, encoding="utf-8"))
        for v in pts:
            label = f"{name}·{dotted.split('.')[-1]}={v}"
            raw = 改一处(base, dotted, v)
            tmp_name = f"_tmp_{name}_{v}.yaml"
            tmp = os.path.join(CFGDIR, tmp_name)
            io.open(tmp, "w", encoding="utf-8").write(
                yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
            cached = 读臂(ARMS, label)
            if cached is not None:
                结果.append(cached)
                print(f"   ⟳ {label}（已跑过，跳过）", flush=True)
                if os.path.exists(tmp):
                    os.remove(tmp)
                continue
            try:
                # ★ old 传 {}:这三条是新策略,没有「上一轮的值」可对比
                r = F.run_one(label, tmp_name, None, "新策略_1106", dev,
                              HOLDSET, {})
                rec = {"链": label, "结果": r}
                存臂(ARMS, label, rec)           # ★ 立刻落盘,被掐了也不白跑
                结果.append(rec)
                print(f"   ✓ {label}", flush=True)
            except TypeError as e:
                失败.append({"链": label, "原因": f"run_one 签名不符:{e}"})
                print(f"   ✗ {label} —— run_one 签名不符:{e}", flush=True)
                break
            except Exception as e:
                失败.append({"链": label, "原因": f"{type(e).__name__}: {e}"})
                print(f"   ✗ {label} —— {type(e).__name__}: {e}", flush=True)
            finally:
                if os.path.exists(tmp):
                    os.remove(tmp)
        if 失败 and "签名不符" in 失败[-1]["原因"]:
            break

    io.open(OUT, "w", encoding="utf-8").write(json.dumps({
        "★口径": {"池": "新池 2,807 只(考卷已排除)", "只跑研发池": True,
                  "engine改动": "零 —— 进程内覆盖层", **自证,
                  "★相邻三点": {k: v[1] for k, v in SWEEP.items()},
                  "★四个零件缺口": "见各 config 的 meta.known_gap"},
        "条数": len(结果), "失败": 失败, "逐条": 结果,
        "耗时秒": round(time.time() - t0, 1),
    }, ensure_ascii=False, indent=1, default=str))
    print(f"\n★ 写到 {OUT} · 成 {len(结果)} · 败 {len(失败)} · {time.time()-t0:.0f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
