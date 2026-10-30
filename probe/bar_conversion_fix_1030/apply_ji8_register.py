"""
★ 改动 ② · 技-8 —— ★★ **只改声明,不改阈值**(复核不过,不许改值)

三秒版:技-8 的「整理段 3 根」确实错了(原著是 3 至 5 **周**,应为 15),
        ★ 但它只有 31 / 59 笔、单笔占总R 60.9%~1260%、总R 在 13~45 之间乱跳
        —— 这种数据上改一个阈值,改出来的差我们量不出来。所以**不改值**,
        改的是两样东西:① 配置里那句「原著没给」是错的,原著给了;
        ② 补上 time_scale 声明并标 `pending`,让闸门每次跑都把它打出来。

原著原文(XING-大师策略手册v13 · 六附 6.1 ②):
    「那三个数出自欧奈尔《How to Make Money in Stocks》第四版第二章 High,
      Tight Flag:4 至 8 周内上涨 100%–120%,★ **随后横向整理 3 至 5 周**、
      回调不超过 20%–25%(常见仅 10%–15%)。」

★ 所以配置里现写的「★ flag_min_bars / flag_max_bars 是我们的读法边界,原著没给」
  是「说原著没给、其实原著给了」那一类错 —— ★★ 它的后果不是阈值偏差,是
  **这条链会被永久标成「参数不全、不给结论」**,而它其实可以给结论。
  ★ 上界 flag_max_bars = 25 = 5 周 × 5 其实**已经按原著换算对了**,
    写「我们定的」也是不对的。

跑法:python3 probe/bar_conversion_fix_1030/apply_ji8_register.py
"""

from __future__ import annotations

import os

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
CONFIG_DIR = os.path.join(ROOT, "engine", "configs")

FILES = ["技-8.yaml", "技-8-行业-时间止损20日.yaml"]

OLD_NOTE = "        ★ flag_min_bars / flag_max_bars 是我们的读法边界,原著没给。"
NEW_NOTE = (
    "        ★★ 2026-10-30 更正:这里原来写「flag_min_bars / flag_max_bars 是我们的\n"
    "        读法边界,原著没给」—— **原著给了**。手册v13 六附 6.1 ② 引欧奈尔 4th ed.\n"
    "        Ch.2 High, Tight Flag:「随后横向整理 **3 至 5 周**」。\n"
    "        · 上界 flag_max_bars = 25 = 5 周 × 5 ✓ **已经换算对了**(不是我们定的)\n"
    "        · 下界 flag_min_bars = 3 ✗ **应为 15**(3 周 × 5)—— 「3 周」被当成\n"
    "          「3 根日线」。★★ **本轮查出来了但没改**:这条链只有 31 / 59 笔\n"
    "          (< 150 可采信线)、单笔占总R 60.9%~1260%、总R 在 13~45 之间非单调\n"
    "          抖动 → 改了也量不出来。★ 见 time_scale 的 pending 声明与\n"
    "          engine/checks/pending_registry.yaml。")

OLD_INLINE_MIN = "        flag_min_bars: 3         # ★ 我们定的机械读法边界,不是原著\n"
NEW_INLINE_MIN = ("        flag_min_bars: 3         # ★★ 原著是 3 **周** → 应为 15;"
                  "查出来没改,见 time_scale\n")
OLD_INLINE_MAX = "        flag_max_bars: 25        # ★ 我们定的机械读法边界,不是原著\n"
NEW_INLINE_MAX = "        flag_max_bars: 25        # = 5 周 × 5 ✓ 原著给的,换算对了\n"

TIME_SCALE = """
# ---------------------------------------------------------------------------
# ★★ 时间尺度声明(engine/checks/time_scale_unit.py 的 C 式)
#     ★ `pending` = 「查出来了、但本轮没改」—— 闸门会把它单列成第三个桶,
#       不混进「马上处理」,也**不算放过**(每次跑都打印)。
#       ★★ 「没查」/「查了没改」/「没人管」必须是三种状态,不是两种。
# ---------------------------------------------------------------------------
time_scale:
  entry.rules[0].params.flag_min_bars:
    unit: trading_days          # 我们实际作用在**日线**格子上
    book_unit: weeks            # ★ 原著给的是**周**
    book_value: 3               # 原著:横向整理 3 至 5 周,取下界 3
    pending: 技-8 整理段下界 flag_min_bars 3 应为 15(原著 3 周)—— 样本不足,本轮未改
    note: >-
      手册v13 六附 6.1 ② 引 O'Neil 4th ed. Ch.2 High, Tight Flag「随后横向整理
      3 至 5 周」→ 3 周 × 5 = **15 个交易日**。★ 现值 3 = 把「3 周」当成
      「3 根日线」,倍率 1×。★★ 2026-10-30 查实但**未改**:n = 31 / 59(< 150)、
      单笔占总R 60.9%~1259.7%、总R 在 flag_min_bars 13/14/15/16/17 上非单调
      (13.22 / 11.49 / 45.36 / 42.75 / 40.05)→ 改动效果淹在噪声里,量不出来。
  entry.rules[0].params.flag_max_bars:
    unit: trading_days
    book_unit: weeks
    book_value: 5
    note: 原著「横向整理 3 至 5 周」→ 5 周 × 5 = 25 个交易日 ✓ ★ 这个上界换算对了。
"""


def main() -> None:
    for name in FILES:
        p = os.path.join(CONFIG_DIR, name)
        txt = open(p, encoding="utf-8").read()
        if txt.count(OLD_NOTE) != 1:
            raise RuntimeError(f"★★ {name}:那句「原著没给」命中 "
                               f"{txt.count(OLD_NOTE)} 次,不是 1 次 —— 停下。")
        if "time_scale:" in txt:
            raise RuntimeError(f"★★ {name} 已有 time_scale 块,不要重复追加。")
        txt = txt.replace(OLD_NOTE, NEW_NOTE)
        # ★ 行内注释只有 技-8.yaml 有(行业版没写)—— 两种写法都要认,但不许瞎猜
        for old, new in ((OLD_INLINE_MIN, NEW_INLINE_MIN),
                         (OLD_INLINE_MAX, NEW_INLINE_MAX)):
            if old in txt:
                txt = txt.replace(old, new)
        txt = txt.rstrip("\n") + "\n" + TIME_SCALE
        open(p, "w", encoding="utf-8").write(txt)
        print(f"  ✓ {name}:★ 阈值一字未改(flag_min_bars 仍是 3);"
              f"注释改正 + time_scale(pending)已补")

    # ★ 复核:值真的没变、pending 真的生效(进第三个桶,不进「马上处理」)
    import sys
    sys.path.insert(0, ROOT)
    import yaml
    from engine.checks.time_scale_unit import check_config_file, split_problems
    for name in FILES:
        p = os.path.join(CONFIG_DIR, name)
        cfg = yaml.safe_load(open(p, encoding="utf-8"))
        assert cfg["entry"]["rules"][0]["params"]["flag_min_bars"] == 3, name
        assert cfg["entry"]["rules"][0]["params"]["flag_max_bars"] == 25, name
        b = split_problems(check_config_file(p))
        assert b["★★★ 换算算错了(马上处理)"] == [], (name, b)
        assert len(b["★ 查出来但没改(已登记)"]) == 1, (name, b)
        print(f"  ✓ {name} 闸门状态:★★★ 桶 0 条 · ★ 已登记桶 1 条")
        print(f"      {b['★ 查出来但没改(已登记)'][0]}")


if __name__ == "__main__":
    main()
