# -*- coding: utf-8 -*-
"""
★★★ 选票层 · **波动调整动量**的回看期相邻三点 —— ★ 红线②。

★★ 为什么要这一份：126 日相对强度刚被查出是**单点尖峰**（60 和 252 都等于对照），
  ★★★ 唯一还没被打掉的是「② 波动调整动量」（留出池 +0.1658 vs 对照 +0.1385）。
  ★ 但它的回看期 **60 也是引擎写死的** → 同一个毛病，必须也跑相邻三点。

★★★ 跑前预先登记（写死）：
  · 三点都高于对照（+0.1385）→ ★★ 「波动调整动量这一支站住」，可进《93》第②层
  · 只有 60 高 → ★★★ **又是一个尖峰 → 「选票层」这一层今天整个不成立**，照报
  · 三点都不高 → ★ 同上，整个不成立
  · 池子：留出池 583 只（和前两轮同池）；回看期 **30 / 60 / 120**
"""
from __future__ import annotations
import copy, io, json, os, sys, time
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
for d in ("probe/friction_rerun_1104", "probe/v2_rerun_1030"):
    sys.path.insert(0, os.path.join(ROOT, d))
sys.path.insert(0, HERE)
os.chdir(ROOT)
from engine import pat6_ops                                    # noqa: E402
import 回看期覆盖层_1107 as OV                                   # noqa: E402
import 跑选票层_1107 as S                                        # noqa: E402
pat6_ops.install()

OUT = os.path.join(HERE, "回看期动量结果_1107.json")
ARMS = os.path.join(HERE, "arms_回看期动量_1107")
回看 = [30, 60, 120]


def main() -> int:
    t0 = time.time()
    自证装 = OV.install()
    assert 自证装["★真的换掉了"], "★★★ 覆盖层没装上，停"
    print("★ 覆盖层自证:", json.dumps(自证装, ensure_ascii=False), flush=True)
    自证 = S.装覆盖层()
    hold = json.load(io.open(S.HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], hold["留出池名单"]
    print(f"★★★ 留出池 {len(hs)} 只（和前两轮同池）", flush=True)

    import run_friction_1104 as F                                # noqa: E402
    F.load_pools = lambda: (hs, set(dev), hold)
    F.CONFIG_DIR = S.CFGDIR
    F.PER_CHAIN = os.path.join(HERE, "per_chain_回看期动量_1107")
    F.LEDGERS = os.path.join(HERE, "ledgers_回看期动量_1107")
    F.OUT = OUT
    for d in (F.PER_CHAIN, F.LEDGERS, ARMS):
        os.makedirs(d, exist_ok=True)

    base = yaml.safe_load(io.open(os.path.join(S.SRC, "技-6-原著.yaml"), encoding="utf-8"))
    结果, 失败 = [], []
    for n in 回看:
        raw = copy.deepcopy(base)
        raw["ranking"] = {"primary": {"formula": f"mom{n}_over_ATRpct20", "order": "desc",
                                      "mom_lookback": n},
                          "source": "★★★ 回看期是引擎写死的默认值，原著没给 —— 不许标原著版。"
                                    "★ 红线②：跑相邻三点 30/60/120 并报是否同向"}
        label = f"留出池·突破·技-6-原著·波动调整动量{n}日"
        tmp = f"_mlb_{n}.yaml"
        io.open(os.path.join(S.CFGDIR, tmp), "w", encoding="utf-8").write(
            yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
        cached = S.读臂(ARMS, label)
        if cached is not None:
            print(f"↩ 已有，跳过 {label}", flush=True); 结果.append(cached); continue
        print(f"▶ 跑 {label}", flush=True)
        try:
            r = F.run_one(label, tmp, None, "选票层回看期动量_1107", hs, set(dev), {})
        except Exception as e:
            失败.append({"臂": label, "错": f"{type(e).__name__}: {e}"})
            print(f"⚠ 失败 {label} —— {type(e).__name__}: {e}", flush=True); continue
        rec = {"链": label, "回看期": n, "结果": r}
        S.存臂(ARMS, label, rec); 结果.append(rec)
        print(f"   ✓ {label} 每笔净R {r['每笔净R']:+.4f}", flush=True)

    报 = {"★预先登记": __doc__.strip()[-600:], "★覆盖层自证": 自证装, "★面板自证": 自证,
         "★★★对照基线": "同池 ①成交额最大先买 每笔净R +0.1385",
         "★★★失败条数": len(失败), "失败明细": 失败, "结果": 结果,
         "★用时秒": round(time.time() - t0, 1)}
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"★ 写完 {OUT};★★★ 失败 {len(失败)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
