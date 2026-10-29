"""
手算核对 vcp_volume_duo(专家 2026-10-29 最终裁决:成交量门禁只剩两条)。

大白话:造一段我们自己知道答案的成交量,把两道门禁分别手算一遍,
和引擎算出来的对一下 —— 对不上就是引擎写错了。

★ 为什么要有这个:1028 那版(三条件全 AND)八年只跑出 15 笔,
  远低于专家预计。任务书要求「差很远就是我们实现得不对,要查」。
  这个脚本是那次核查留下来的,★ 2026-10-29 跟着裁决一起改成两门禁版。

★ 本次裁决删掉的两样,这里一并验证「真的删掉了」:
  ① 条件2(SMA5(t−1) ≤ 0.85 × SMA50(t−1))—— 与门禁1 共线冗余,彻底废除
  ② 1.20 × SMA5(t−1) 连乘项 —— 冗余,删除
  ③ 原 breakout_volume_band 的 1.80 倍上限 —— ★ 物理删除(算子整个没了)

跑法:python -m engine.verify_vcp_volume
"""
import sys

import numpy as np
import pandas as pd

from engine import matrices

RULE = {"type": "vcp_volume_duo", "params": {}}
IDX_LEN = 60


def _run(vol: list[float]) -> bool:
    """把一段造出来的成交量喂给引擎,返回最后一天(突破日 t)的结果。"""
    idx = pd.bdate_range("2020-01-01", periods=len(vol))
    df = pd.DataFrame({"X": vol}, index=idx)

    class FakeCache:
        def field(self, name, symbols=None):
            return df

        def symbols(self):
            return ["X"]

    orig = matrices.cache
    matrices.cache = FakeCache()
    try:
        out = matrices._entry_rule_raw(RULE, ["X"])
    finally:
        matrices.cache = orig
    return bool(out.iloc[len(vol) - 1, 0])


def main(argv=None) -> int:
    fails: list[str] = []

    def check(label: str, vol: list[float], expect: bool, why: str) -> None:
        got = _run(vol)
        ok = got == expect
        print(f"  {'✅' if ok else '★❌'} {label:52s} 手算={expect!s:5s} 引擎={got!s:5s}")
        if not ok:
            fails.append(f"{label}(手算 {expect} / 引擎 {got});{why}")

    # 前 54 天量 = 1000 → SMA50(t−1) 基准 = 1000
    base = [1000.0] * 54
    t = IDX_LEN - 1

    print("=" * 78)
    print("vcp_volume_duo 手算核对(专家 2026-10-29 最终裁决版:只剩两道门禁)")
    print("  门禁1  min(Vol[t−5..t−1]) ≤ 0.60 × SMA50(t−1)")
    print("  门禁2  Vol[t]             ≥ 1.00 × SMA50(t−1)   ★ 无上限")
    print()

    # ---- 正例:有地量日 500,突破日 1100
    v = base + [500, 900, 900, 900, 900] + [1100]
    a = np.array(v)
    sma50_t1 = a[t - 50:t].mean()
    sma5_t1 = a[t - 5:t].mean()
    print(f"  基准:SMA50[t-1]={sma50_t1:.1f}  SMA5[t-1]={sma5_t1:.1f}  "
          f"min(Vol[t-5:t])={a[t - 5:t].min():.0f}")
    print(f"    门禁1  {a[t - 5:t].min():.0f} ≤ {0.60 * sma50_t1:.1f} -> "
          f"{a[t - 5:t].min() <= 0.60 * sma50_t1}")
    print(f"    门禁2  {a[t]:.0f} ≥ {1.00 * sma50_t1:.1f} -> {a[t] >= sma50_t1}")
    print()
    check("正例:地量 500 + 突破日 1100", v, True, "两道门禁都该成立")

    # ---- 反例:没有地量日 → 门禁1 不成立
    check("反例:无地量日(前 5 天最低 900)", base + [900] * 5 + [1100], False,
          "门禁1 该拦下来")

    # ---- 反例:突破日量没上 50 日均量 → 门禁2 不成立
    check("反例:突破日量 950 < SMA50", base + [500, 900, 900, 900, 900] + [950],
          False, "门禁2 该拦下来")

    # ---- 边界:突破日量正好等于 SMA50(写的是 ≥,该成立)
    check("边界:突破日量 = SMA50(≥,该过)",
          base + [500, 900, 900, 900, 900] + [1000.0], True, "门禁2 写的是 ≥")

    # ======================================================================
    # ★★ 以下三条专门验证「裁决删掉的东西真的删掉了」
    # ======================================================================
    print()
    print("  ★★ 验证裁决删掉的三样东西(删没删干净,这三条说话):")

    # ① 原条件2:SMA5(t−1) ≤ 0.85 × SMA50(t−1)
    #    造一段:有地量日(门禁1 过)、突破日放量(门禁2 过),
    #    但前 5 日均量 = (500+1400×4)/5 = 1220 > 0.85×1000 = 850
    #    → 旧的三条件版会被条件2 拦下(False);新版该放过(True)
    v_c2 = base + [500, 1400, 1400, 1400, 1400] + [1100]
    sma5 = np.array(v_c2)[t - 5:t].mean()
    print(f"     ① 条件2 已废除:SMA5[t-1]={sma5:.0f} > 0.85×SMA50=850,"
          f"旧版会拦、新版不该拦")
    check("① 条件2(0.85 收敛)已彻底废除", v_c2, True,
          "★ 如果这里是 False,说明条件2 还在起作用,裁决没落地")

    # ② 原条件3 的 1.20 × SMA5(t−1) 连乘项
    #    造一段:前 5 天 = [500, 1200×4] → SMA5 = 1060,1.20×1060 = 1272
    #    突破日 1100:≥ SMA50(1000) ✅,但 < 1272 → 旧版被连乘项拦下
    v_f = base + [500, 1200, 1200, 1200, 1200] + [1100]
    sma5f = np.array(v_f)[t - 5:t].mean()
    print(f"     ② 1.20×SMA5 连乘项已删:1.20×SMA5[t-1]={1.20 * sma5f:.0f} > "
          f"突破日量 1100,旧版会拦、新版不该拦")
    check("② 1.20 × SMA5 连乘项已删除", v_f, True,
          "★ 如果这里是 False,说明连乘项还在,裁决没落地")

    # ③ 原 breakout_volume_band 的 1.80 倍上限 —— 爆量日必须放过
    #    突破日 5000 = 5.0 × SMA50。专家:原著推崇 2/3/5 倍的爆发日,
    #    焊死 1.80 上限会精准击杀最强的那 5%。
    check("③ 爆量日 5.0×SMA50 必须放过(1.80 上限已物理删除)",
          base + [500, 900, 900, 900, 900] + [5000.0], True,
          "★ 如果这里是 False,说明还有上限在击杀领头羊")

    # ③b 算子本身是不是真的从引擎里删掉了(写了就该报错,不许悄悄跑)
    try:
        _run_band = {"type": "breakout_volume_band", "params": {}}
        idx = pd.bdate_range("2020-01-01", periods=IDX_LEN)
        df = pd.DataFrame({"X": base + [500, 900, 900, 900, 900] + [5000.0]},
                          index=idx)

        class FC:
            def field(self, n, s=None):
                return df

            def symbols(self):
                return ["X"]

        orig = matrices.cache
        matrices.cache = FC()
        try:
            matrices._entry_rule_raw(_run_band, ["X"])
            print("  ★❌ breakout_volume_band 居然还能跑 —— 没有物理删除")
            fails.append("breakout_volume_band 还能跑,1.80 上限没有物理删除")
        finally:
            matrices.cache = orig
    except NotImplementedError as e:
        head = str(e).splitlines()[0]
        print(f"  ✅ breakout_volume_band 已物理删除,写了就报错:{head[:70]}")

    print()
    if fails:
        print("★★ 核对不过:")
        for f in fails:
            print("   - " + f)
        return 1
    print("✅ 全部对得上(含「裁决删掉的三样确实删干净了」三条)。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
