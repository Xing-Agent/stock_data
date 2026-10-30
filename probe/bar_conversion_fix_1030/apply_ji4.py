"""
★ 改动 ① · 技-4 欧奈尔杯柄 `handle_min_bars` 3 → 5(4 份配置)

三秒版:原著说「柄至少 1–2 周」,手册把日线换算也写出来了(≥5 个交易日),
        同一个算子里 cup_min_bars / cup_max_bars / handle_max_bars 三个都 ×5
        换算对了,★ 只有这个下界没换 —— 它被当成「3 周 = 3 根」了。

原著原文(XING-大师策略手册v13 · 六附 6.1 ①,引 O'Neil《How to Make Money in
Stocks》4th ed. 2009 Ch.2 "The Cup with Handle"):
    要素「柄部持续时间」→ 原著数值「**至少 1–2 周(日线至少 5 个交易日)**」

★ 本脚本只改这 4 份 yaml 的三样东西,别的一字不动:
    ① handle_min_bars: 3 → 5
    ② 那条 source 里「★ 柄长 3~25 个交易日是**我们的读法**(原著只说柄是
       "a few days to a few weeks",没给死数)」—— ★ 这句话本身是错的,
       六附 6.1 ① 明明给了死数。改成原著出处 + 换算依据。
    ③ 顶层补 `time_scale` 块(全库第一份)—— 声明原著单位是**周**,
       我们作用在**交易日**上,换算依据写清。

★ 不许静默跳过:每一处替换都 assert 命中次数,改不到就 raise。
跑法:python3 probe/bar_conversion_fix_1030/apply_ji4.py
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(ROOT, "engine", "configs")

FILES = ["技-4-原著.yaml", "技-4-原著-中值.yaml",
         "技-4-原著-宽松端.yaml", "技-4-行业.yaml"]

OLD_VAL = "        handle_min_bars: 3\n"
NEW_VAL = "        handle_min_bars: 5\n"

OLD_SRC = ('★ 柄长 3~25 个交易日是**我们的读法**(原著只说柄是\n'
           '        "a few days to a few weeks",没给死数)。')
NEW_SRC = (
    '★ 柄长下界 5 个交易日 = **原著**(手册v13 六附 6.1 ①,引 O\'Neil 4th ed.\n'
    '        Ch.2:柄部持续时间「至少 1–2 周(日线至少 5 个交易日)」)——\n'
    '        1 周 × 5 = 5;★ 2026-10-30 之前这里写的是 3,是把「3 周」当成了\n'
    '        「3 根日线」,同一个算子里另外三个 bar 参数都 ×5 换算对了,只有这个\n'
    '        下界没换。柄长**上界** 25 个交易日(= 5 周 × 5)仍是我们的读法。')

TIME_SCALE = """
# ---------------------------------------------------------------------------
# ★★ 时间尺度声明(engine/checks/time_scale_unit.py 的 C 式)——
#     ★ 全库在 2026-10-30 之前**一份都没写过**,本文件是第一批。
#     为什么必须写:`*_bars` 这个后缀只说了「根」,★ 没说**哪种根**,
#     更没说**原著当年是在什么周期上给这个数的**。本轮的错就长在这个缝里。
# ---------------------------------------------------------------------------
time_scale:
  entry.rules[0].params.handle_min_bars:
    unit: trading_days          # 我们实际作用在**日线**格子上
    book_unit: weeks            # ★ 原著给的是**周**
    book_value: 1               # ★ 原著数值:至少 1 周(区间 1–2 周,取下界)
    note: >-
      手册v13 六附 6.1 ① 引 O'Neil 4th ed. Ch.2「柄部持续时间:至少 1–2 周
      (日线至少 5 个交易日)」→ 1 周 × 5 = **5 个交易日**。
      ★ 原值 3 是把「3 周」当成「3 根日线」,2026-10-30 改正。
  entry.rules[0].params.handle_max_bars:
    unit: trading_days
    book_unit: weeks
    book_value: 5
    note: 5 周 × 5 = 25 个交易日;★ 上界本身是我们的读法(原著只给了下界)。
  entry.rules[0].params.cup_min_bars:
    unit: trading_days
    book_unit: weeks
    book_value: 7
    note: 原著「杯体持续 7 周至 65 周」→ 7 × 5 = 35 个交易日。
  entry.rules[0].params.cup_max_bars:
    unit: trading_days
    book_unit: weeks
    book_value: 65
    note: 原著「杯体持续 7 周至 65 周」→ 65 × 5 = 325 个交易日。
"""


def main() -> None:
    for name in FILES:
        p = os.path.join(CONFIG_DIR, name)
        with open(p, encoding="utf-8") as fh:
            txt = fh.read()
        if txt.count(OLD_VAL) != 1:
            raise RuntimeError(
                f"★★ {name}:`handle_min_bars: 3` 命中 {txt.count(OLD_VAL)} 次,"
                f"不是 1 次 —— ★ 不许静默跳过,先看清再改。")
        if txt.count(OLD_SRC) != 1:
            raise RuntimeError(
                f"★★ {name}:那条 source 的原句命中 {txt.count(OLD_SRC)} 次,"
                f"不是 1 次。★ 四份配置的 source 文字有细微差异(杯深下限 0.15/0.12),"
                f"但这一句应逐字相同 —— 对不上就停下。")
        if "time_scale:" in txt:
            raise RuntimeError(f"★★ {name} 已经有 time_scale 块了,不要重复追加。")
        txt = txt.replace(OLD_VAL, NEW_VAL).replace(OLD_SRC, NEW_SRC)
        txt = txt.rstrip("\n") + "\n" + TIME_SCALE
        with open(p, "w", encoding="utf-8") as fh:
            fh.write(txt)
        print(f"  ✓ {name}:handle_min_bars 3 → 5 · source 改正 · time_scale 已补")

    # ★ 改完立刻验:yaml 能读、值真的是 5、time_scale 真的进去了
    import yaml
    for name in FILES:
        cfg = yaml.safe_load(open(os.path.join(CONFIG_DIR, name), encoding="utf-8"))
        v = cfg["entry"]["rules"][0]["params"]["handle_min_bars"]
        assert v == 5, (name, v)
        ts = cfg["time_scale"]["entry.rules[0].params.handle_min_bars"]
        assert ts["book_unit"] == "weeks" and ts["unit"] == "trading_days", (name, ts)
        assert ts["note"]
    print("★ 4 份配置复验通过:值 = 5、book_unit = weeks、note 已写")


if __name__ == "__main__":
    sys.exit(main())
