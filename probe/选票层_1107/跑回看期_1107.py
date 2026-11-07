# -*- coding: utf-8 -*-
"""
★★★ 选票层 · 回看期相邻三点 —— ★ 红线②：原著没给的数必须跑相邻三点、报是否同向。

★★ 为什么要这一份：留出池上「③ 126 日相对强度」站住了（每笔净R +0.139→+0.190，+37%），
  ★★★ 但 **126 这个回看期是我拍的**（引擎里写死的默认值）——
  ★ 按红线②，必须跑 **60 / 126 / 252** 三点并报三点是否同向。

★★★ 跑前预先登记（写死）：
  · 三点同向（都高于 ADV20 对照）→ ★★ 「回看期不敏感」，可以用，标默认 126
  · 只有 126 高 → ★★★ **「126 是挑出来的」，不许标成原著版，必须写明是我们自己选的**
  · 三点都不高于对照 → ★ 和留出池那一轮矛盾，**两边都报，不许只报好看的那边**
  · 池子：**留出池 583 只**（★ 和站住那一轮同池，才可比）
"""
from __future__ import annotations
import copy, io, json, os, sys, time
import yaml

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(os.path.dirname(HERE))
sys.path.insert(0, ROOT)
sys.path.insert(0, os.path.join(ROOT, "probe", "friction_rerun_1104"))
sys.path.insert(0, os.path.join(ROOT, "probe", "v2_rerun_1030"))
sys.path.insert(0, HERE)
os.chdir(ROOT)
from engine import pat6_ops                                    # noqa: E402
import 回看期覆盖层_1107 as OV                                   # noqa: E402
import 跑选票层_1107 as S                                        # noqa: E402
pat6_ops.install()

OUT = os.path.join(HERE, "回看期结果_1107.json")
ARMS = os.path.join(HERE, "arms_回看期_1107")
回看 = [60, 126, 252]                 # ★ 相邻三点


def main() -> int:
    t0 = time.time()
    自证装 = OV.install()
    print("★ 覆盖层自证:", json.dumps(自证装, ensure_ascii=False), flush=True)
    assert 自证装["★真的换掉了"], "★★★ 覆盖层没装上，停下来查"
    自证 = S.装覆盖层()
    print("★ 面板自证:", json.dumps(自证, ensure_ascii=False), flush=True)
    hold = json.load(io.open(S.HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], hold["留出池名单"]
    print(f"★★★ 本轮跑**留出池 {len(hs)} 只**（和站住那一轮同池）", flush=True)

    import run_friction_1104 as F                                # noqa: E402
    F.load_pools = lambda: (hs, set(dev), hold)
    F.CONFIG_DIR = S.CFGDIR
    F.PER_CHAIN = os.path.join(HERE, "per_chain_回看期_1107")
    F.LEDGERS = os.path.join(HERE, "ledgers_回看期_1107")
    F.OUT = OUT
    for d in (F.PER_CHAIN, F.LEDGERS, ARMS):
        os.makedirs(d, exist_ok=True)

    base = yaml.safe_load(io.open(os.path.join(S.SRC, "技-6-原著.yaml"), encoding="utf-8"))
    结果, 失败 = [], []
    for n in 回看:
        raw = copy.deepcopy(base)
        raw["ranking"] = {"primary": {"formula": f"rs_rank_{n}", "order": "desc",
                                      "rs_lookback": n},
                          "source": "★★★ 回看期是我们自己选的，原著没给 —— 不许标成原著版。"
                                    "★ 红线②：跑相邻三点 60/126/252 并报是否同向"}
        label = f"留出池·突破·技-6-原著·相对强度{n}日"
        tmp = f"_lb_{n}.yaml"
        io.open(os.path.join(S.CFGDIR, tmp), "w", encoding="utf-8").write(
            yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
        cached = S.读臂(ARMS, label)
        if cached is not None:
            print(f"↩ 已有，跳过 {label}", flush=True); 结果.append(cached); continue
        print(f"▶ 跑 {label}", flush=True)
        try:
            r = F.run_one(label, tmp, None, "选票层回看期_1107", hs, set(dev), {})
        except Exception as e:
            失败.append({"臂": label, "错": f"{type(e).__name__}: {e}"})
            print(f"⚠ 失败 {label} —— {type(e).__name__}: {e}", flush=True); continue
        rec = {"链": label, "回看期": n, "结果": r}
        S.存臂(ARMS, label, rec); 结果.append(rec)
        print(f"   ✓ {label} 每笔净R {r['每笔净R']:+.4f}", flush=True)

    报 = {"★预先登记": __doc__.strip()[-700:], "★覆盖层自证": 自证装, "★面板自证": 自证,
         "★★★对照基线": "同池 ①成交额最大先买 每笔净R +0.1385（留出池结果_1107.json）",
         "★★★失败条数": len(失败), "失败明细": 失败, "结果": 结果,
         "★用时秒": round(time.time() - t0, 1)}
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"★ 写完 {OUT};★★★ 失败 {len(失败)} 条")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
