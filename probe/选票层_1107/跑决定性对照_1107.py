# -*- coding: utf-8 -*-
"""
★★★ 选票层 · 决定性对照 —— ★ Gemini 第 50 轮第四节点出的两档，我原来漏了。

★★ 它的原话（⑤ 档，待核）：
  「**按成交额排序没有任何文献支持它能带来超额收益**，它这十年赚钱纯粹是撞上了大科技股牛市。」
  「测试设计要改：相对强度和动量高度重合，算一档就行。**必须加两档**：
    · 波动率倒数（Frazzini & Pedersen 2014;Blitz & van Vliet 2007）
    · **随机排序跑 100 次取平均** —— 用来看策略的买入触发本身有没有用，
      还是全靠排序在撑。」

★★★ 为什么这一档是**决定性**的：
  ★ 我今天唯一立住的结果是「波动调整动量排序 > 成交额排序」（留出池，三点同向）。
  ★★ 但如果**随便乱排也能打赢成交额排序**，那这句话就不成立 ——
  ★★★ 真相会变成「**成交额排序特别烂**」，这是完全不同的一句话，
    而且意味着我们现在 45 条链的默认设置是在**主动伤害成绩**。

★★★ 跑前预先登记（写死，不许事后改）：
  对照基线 = 同池 ①成交额最大先买 每笔净R **+0.1385**；
  已站住的 = 波动调整动量 **+0.166 ~ +0.186**（30/60/120 三点）。

| 随机排序的均值 | 结论（照这个写） |
|---|---|
| 随机 ≈ 对照（差 < 0.01） | ★★★ **「波动调整动量有效」成立** —— 不是随便排都行 |
| 随机 **> 对照** 且 ≈ 动量 | ★★★ **「动量有效」不成立** —— 真相是「**成交额排序特别烂，随便换都比它好**」 |
| 随机 > 对照 但明显 < 动量 | ★★ **两件都成立**：成交额排序有害 **且** 动量另有超额 —— ★ 要把两段拆开报 |
| 随机 < 对照 | ★ 成交额排序本身有正作用（和 Gemini 说的相反）→ ★★ 原样报，并回去追问它 |

★ 种子数：先跑 **20 个**（★★ 不是 100 —— 每条臂约 4~5 分钟，100 条要 7 小时以上；
  ★★★ 可续跑，机器空着就接着加，报告里会写明实际跑了几个）。
★ 池子：留出池 583 只（和站住那两轮同池，才可比）。
"""
from __future__ import annotations
import copy, io, json, os, statistics, sys, time
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

OUT = os.path.join(HERE, "决定性对照结果_1107.json")
ARMS = os.path.join(HERE, "arms_决定性对照_1107")
对照基线 = 0.1385
种子 = [424242, 20181001, 20220101, 777013, 31337, 90210, 10007, 31415926,
       27182818, 65537, 20260101, 8675309, 112358, 1618033, 2718281,
       999331, 141421, 173205, 223606, 264575]            # ★ 20 个，和引擎的种子表同源风格


def main() -> int:
    t0 = time.time()
    自证装 = OV.install()
    assert 自证装["★真的换掉了"], "★★★ 覆盖层没装上，停"
    自证 = S.装覆盖层()
    hold = json.load(io.open(S.HOLD, encoding="utf-8"))
    dev, hs = hold["研发池名单"], hold["留出池名单"]
    print(f"★★★ 留出池 {len(hs)} 只（和站住那两轮同池）", flush=True)

    import run_friction_1104 as F                                # noqa: E402
    F.load_pools = lambda: (hs, set(dev), hold)
    F.CONFIG_DIR = S.CFGDIR
    F.PER_CHAIN = os.path.join(HERE, "per_chain_决定性对照_1107")
    F.LEDGERS = os.path.join(HERE, "ledgers_决定性对照_1107")
    F.OUT = OUT
    for d in (F.PER_CHAIN, F.LEDGERS, ARMS):
        os.makedirs(d, exist_ok=True)

    base = yaml.safe_load(io.open(os.path.join(S.SRC, "技-6-原著.yaml"), encoding="utf-8"))
    臂 = [("④波动率倒数20日", {"formula": "1/std20", "order": "desc", "inv_vol_window": 20},
          "★★ Gemini 第 50 轮：学术上有依据（Frazzini & Pedersen 2014）")]
    臂 += [(f"⑤随机排序·种子{sd}", {"formula": "random", "order": "desc", "random_seed": sd},
           "★★★ 决定性对照：看买入触发本身有没有用，还是全靠排序在撑")
          for sd in 种子]

    结果, 失败 = [], []
    for 名, prim, src in 臂:
        raw = copy.deepcopy(base)
        raw["ranking"] = {"primary": prim, "source": src}
        label = f"留出池·突破·技-6-原著·{名}"
        tmp = f"_dc_{名}.yaml".replace("·", "_")
        io.open(os.path.join(S.CFGDIR, tmp), "w", encoding="utf-8").write(
            yaml.safe_dump(raw, allow_unicode=True, sort_keys=False))
        cached = S.读臂(ARMS, label)
        if cached is not None:
            结果.append(cached); continue
        print(f"▶ 跑 {名}", flush=True)
        try:
            r = F.run_one(label, tmp, None, "选票层决定性对照_1107", hs, set(dev), {})
        except Exception as e:
            失败.append({"臂": label, "错": f"{type(e).__name__}: {e}"})
            print(f"⚠ 失败 {名} —— {type(e).__name__}: {e}", flush=True); continue
        rec = {"链": label, "挑法": 名, "结果": r}
        S.存臂(ARMS, label, rec); 结果.append(rec)
        print(f"   ✓ {名} 每笔净R {r['每笔净R']:+.4f}", flush=True)
        # ★ 每条跑完就落一次盘（★★ 可续跑；机器被掐也不白跑）
        io.open(OUT, "w", encoding="utf-8").write(json.dumps(
            {"★进行中": True, "结果": 结果, "失败明细": 失败},
            ensure_ascii=False, indent=1, default=str))

    随机 = [r["结果"]["每笔净R"] for r in 结果 if r["挑法"].startswith("⑤")]
    报 = {"★预先登记": __doc__.strip()[-1400:], "★覆盖层自证": 自证装, "★面板自证": 自证,
         "★★★对照基线_成交额排序": 对照基线,
         "★★★已站住的_波动调整动量": "+0.166 ~ +0.186（30/60/120 三点同向）",
         "★★★随机排序": ({"实际跑了几个种子": len(随机),
                      "均值": round(statistics.fmean(随机), 4),
                      "标准差": round(statistics.stdev(随机), 4) if len(随机) > 1 else None,
                      "最小": round(min(随机), 4), "最大": round(max(随机), 4),
                      "★减对照基线": round(statistics.fmean(随机) - 对照基线, 4)}
                     if 随机 else "★★★ 一个都没跑出来"),
         "★★★失败条数": len(失败), "失败明细": 失败, "结果": 结果,
         "★用时秒": round(time.time() - t0, 1)}
    io.open(OUT, "w", encoding="utf-8").write(
        json.dumps(报, ensure_ascii=False, indent=1, default=str))
    print(f"★ 写完;★★★ 失败 {len(失败)} 条;随机跑了 {len(随机)} 个种子")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
