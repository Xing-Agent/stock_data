# -*- coding: utf-8 -*-
"""
★★★ 选票层 · 留出池复验 —— ★ 判据写死在《95》，这里只产数。
★★ 池子换成**留出池 583 只**（从来没碰过的票），其余口径逐项和研发池那 9 条臂一致。
★★★ engine 零改动。★ 可续跑。
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
import 跑选票层_1107 as S                                        # noqa: E402
pat6_ops.install()

OUT = os.path.join(HERE, "留出池结果_1107.json")
ARMS = os.path.join(HERE, "arms_留出池_1107")
代表 = {"突破": "技-6-原著.yaml"}        # ★ 只跑研发池上唯一三点同向的那一族


def main() -> int:
    t0 = time.time()
    自证 = S.装覆盖层()
    print("★ 覆盖层:", json.dumps(自证, ensure_ascii=False), flush=True)
    hold = json.load(io.open(S.HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], hold["留出池名单"]
    assert not (set(dev) & set(hs)), "★ 研发池和留出池有交集，停下来查"
    # ★★★ 这一轮**跑留出池** —— 把它当「可买名单」传进去，研发池当被排除的那一侧
    print(f"★★★ 本轮跑**留出池 {len(hs)} 只**（研发池 {len(dev)} 只不碰）", flush=True)

    import run_friction_1104 as F                                # noqa: E402
    F.load_pools = lambda: (hs, set(dev), hold)
    F.CONFIG_DIR = S.CFGDIR
    F.PER_CHAIN = os.path.join(HERE, "per_chain_留出池_1107")
    F.LEDGERS = os.path.join(HERE, "ledgers_留出池_1107")
    F.OUT = OUT
    for d in (F.PER_CHAIN, F.LEDGERS, ARMS):
        os.makedirs(d, exist_ok=True)

    结果, 失败 = [], []
    for 族, fn in 代表.items():
        base = yaml.safe_load(io.open(os.path.join(S.SRC, fn), encoding="utf-8"))
        老 = ((base.get("ranking") or {}).get("primary") or {}).get("formula")
        assert str(老).upper().startswith("ADV20"), f"★ {fn} 的 ranking 不是 ADV20，停"
        for 名, spec in S.挑法.items():
            raw = copy.deepcopy(base); raw["ranking"] = copy.deepcopy(spec)
            label = f"留出池·{族}·{fn[:-5]}·{名}"
            tmp = f"_hold_{族}_{名}.yaml"
            io.open(os.path.join(S.CFGDIR, tmp), "w", encoding="utf-8").write(
                yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
            cached = S.读臂(ARMS, label)
            if cached is not None:
                print(f"↩ 已有，跳过 {label}", flush=True); 结果.append(cached); continue
            print(f"▶ 跑 {label}", flush=True)
            try:
                r = F.run_one(label, tmp, None, "选票层留出池_1107", hs, set(dev), {})
            except Exception as e:
                失败.append({"臂": label, "错": f"{type(e).__name__}: {e}"})
                print(f"⚠ 失败 {label} —— {type(e).__name__}: {e}", flush=True); continue
            rec = {"链": label, "族": 族, "挑法": 名, "结果": r}
            S.存臂(ARMS, label, rec); 结果.append(rec)
            print(f"   ✓ {label}", flush=True)

    报 = {"★预先登记": "手册/95-选票层留出池复验-跑前预先登记-1107.md（★ 判据写死在那里）",
         "★★★本轮池子": f"留出池 {len(hs)} 只（研发池 {len(dev)} 只不碰；考卷 1,042 只烤盘阶段已排除）",
         "★覆盖层自证": 自证, "★★★失败条数": len(失败), "失败明细": 失败,
         "结果": 结果, "★用时秒": round(time.time() - t0, 1)}
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"★ 写完 {OUT};★★★ 失败 {len(失败)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
