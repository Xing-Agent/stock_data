# -*- coding: utf-8 -*-
"""
★★★ 选票层 —— ★ 「30 只票符合条件、只有 5 个仓位 → 买哪 5 只」换三个挑法。

★★ 来历：Lin 1107 13:05~13:10。他的原话：
  「一个是在什么环境做什么样的策略，然后这个环境中我挑什么样的票，
    这也是很重要的一关。那这两个结合起来，你的止盈止损、进出，
    在这一层再做好了，那基本上就 OK 了。」
  「你的各方面测试，这个策略拿出来就是没有在上面添加任何主观判断，
    直接去调用这个策略，那不一定会比指数收益好。因为这里面假设点就是**平均逻辑** ——
    你做突破，所有符合条件你都做突破。但实际中肯定会挑的。」

★★★ 他说的那一层在引擎里叫 `ranking`。★ 今天查出来：
  **全部 45 条链都设成同一个值 `ADV20 降序`（成交额最大的先买）**，
  配置里我们自己写的理由：「槽位满时必须有个决胜规则，**选了最不含观点的那个**」，
  引擎注释里我们自己写的：「**结论对它敏感** —— 已列为待拍板项」。
  ★★★ **而从没测过别的。**

★ 三个挑法（★★ 都用现成实现，engine 零改动；★★★ 三个都不看未来）：
  ① ADV20 降序                      —— 现状，当**对照**
  ② (Close_t/Close_{t−60}−1)/ATR%20 —— **波动调整后的 60 日动量**
  ③ rs_rank（126 日相对强度排名）     —— 配置填字符串即走这一支

★★★ 预先登记（跑前写死，不许事后改）：
  · 判据 = 对**自己赛道买入持有**（《93》主基准）的超额 + Newey-West t
  · ★★ 三个挑法里只要有一个明显好，必须同时报「三个挑法是否同向」
  · ★★★ 若②③都不如①，结论是「**选票层换法没用**」—— 照报，不许再换第四个挑法去凑
  · ★ 本轮只跑**不挂闸**版（和现有不挂闸流水可比），挂闸版等比法定下来再跑
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
from engine import cache, data, pool_scope, pat6_ops            # noqa: E402
import rerun_core_1030 as RC                                    # noqa: E402
pat6_ops.install()          # ★ 运行时挂钩，engine/ 一个字节没改

NEWPANEL = "probe/newpool_1106/ohlcv_panel_newpool.parquet"
NEWPOOL = "probe/newpool_1106/pool_NEWPOOL_ALL_1106.csv"
HOLD = "probe/新策略_1106/holdout_newpool_1106.json"
SRC = os.path.join(ROOT, "engine", "configs")
CFGDIR = os.path.join(HERE, "configs")
OUT = os.path.join(HERE, "选票层结果_1107.json")

代表 = {"震荡": "技-14-原著.yaml", "突破": "技-6-原著.yaml", "大波段": "技-1.yaml"}
挑法 = {
    "①成交额最大先买_对照": {"primary": {"formula": "ADV20", "order": "desc"},
                      "source": "★ 现状（45 条链全是这个）。配置原文：「选了最不含观点的那个」"},
    "②波动调整动量": {"primary": {"formula": "(Close_t / Close_{t-60} - 1) / ATR_pct_20",
                            "order": "desc"},
                "atr_pct_denominator": "close_t",
                "source": "★★ 引擎已实现的公式（专家第二轮给的，原文照搬）。"
                          "★★★ 原著没给排序规则 —— 不许标成原著版"},
    "③相对强度126日": "rs_rank",
}


def 装覆盖层() -> dict:
    wide = pd.read_parquet(NEWPANEL)
    cache._PANEL = {f: wide[f] for f in wide.columns.levels[0]}
    idx = pool_scope.PoolIndex(path=NEWPOOL)
    RC._IDX_CACHE["idx"] = idx
    data.PERF_START = "2015-01-01"
    return {"面板只数": int(cache._PANEL["close"].shape[1]), "池表行数": idx.rows,
            "PERF_START": data.PERF_START, "PERF_END": data.PERF_END}


def 臂路径(臂目录, label):
    import hashlib
    return os.path.join(臂目录, f"arm_{hashlib.sha256(label.encode()).hexdigest()[:16]}.json")


def 读臂(臂目录, label):
    p = 臂路径(臂目录, label)
    if os.path.exists(p):
        try:
            return json.load(io.open(p, encoding="utf-8"))
        except Exception:
            return None
    return None


def 存臂(臂目录, label, payload):
    os.makedirs(臂目录, exist_ok=True)
    io.open(臂路径(臂目录, label), "w", encoding="utf-8").write(
        json.dumps(payload, ensure_ascii=False, indent=1, default=str))


def main() -> int:
    t0 = time.time()
    自证 = 装覆盖层()
    print("★ 覆盖层:", json.dumps(自证, ensure_ascii=False), flush=True)
    hold = json.load(io.open(HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], set(hold["留出池名单"])
    assert not (set(dev) & hs), "★ 研发池和留出池有交集，停下来查"
    print(f"★ 研发池 {len(dev)} 只（留出 {len(hs)} 只不碰）", flush=True)

    import run_friction_1104 as F                                # noqa: E402
    F.load_pools = lambda: (dev, hs, hold)
    F.CONFIG_DIR = CFGDIR
    F.PER_CHAIN = os.path.join(HERE, "per_chain_1107")
    F.LEDGERS = os.path.join(HERE, "ledgers_1107")
    F.OUT = OUT
    for d in (CFGDIR, F.PER_CHAIN, F.LEDGERS):
        os.makedirs(d, exist_ok=True)
    ARMS = os.path.join(HERE, "arms_1107")
    os.makedirs(ARMS, exist_ok=True)

    结果, 失败 = [], []
    for 族, fn in 代表.items():
        base = yaml.safe_load(io.open(os.path.join(SRC, fn), encoding="utf-8"))
        # ★★★ 自证：原配置的 ranking 必须就是 ADV20（不然这一轮的对照不成立）
        老 = ((base.get("ranking") or {}).get("primary") or {}).get("formula")
        assert str(老).upper().startswith("ADV20"), \
            f"★ {fn} 的 ranking 不是 ADV20（是 {老!r}），停下来查"
        # ★★ 自证：原配置的 regime 必须是空的（本轮只跑不挂闸）
        assert not ((base.get("regime") or {}).get("rules") or []), \
            f"★ {fn} 的 regime 本来就不空，停下来查"
        for 名, spec in 挑法.items():
            raw = copy.deepcopy(base)
            raw["ranking"] = copy.deepcopy(spec)
            label = f"{族}·{fn[:-5]}·{名}"
            tmp = f"_pick_{族}_{名}.yaml"
            io.open(os.path.join(CFGDIR, tmp), "w", encoding="utf-8").write(
                yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
            cached = 读臂(ARMS, label)
            if cached is not None:
                print(f"↩ 已有，跳过 {label}", flush=True)
                结果.append(cached); continue
            print(f"▶ 跑 {label}", flush=True)
            try:
                # ★★★ 签名照抄 probe/挂闸_1106/跑挂闸_1106.py:125 的现成调法 ——
                #   run_one(label, yml, ov, group, dev, hold, old)
                #   ★ 规矩⑬ 补一句（#69）：接口名查过了还不够，**参数也要打 signature**，
                #     不许凭记忆写参数个数和顺序。
                r = F.run_one(label, tmp, None, "选票层_1107", dev, hs, {})
            except Exception as e:
                失败.append({"臂": label, "错": f"{type(e).__name__}: {e}"})
                print(f"⚠ 失败 {label} —— {type(e).__name__}: {e}", flush=True); continue
            rec = {"链": label, "族": 族, "挑法": 名, "结果": r}
            存臂(ARMS, label, rec); 结果.append(rec)
            print(f"   ✓ {label}", flush=True)

    报 = {"★这一轮做什么": __doc__.strip()[:1200], "★覆盖层自证": 自证,
         "★★★失败条数": len(失败), "失败明细": 失败, "结果": 结果,
         "★用时秒": round(time.time() - t0, 1)}
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"★ 写完 {OUT};★★★ 失败 {len(失败)} 条;用时 {报['★用时秒']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
