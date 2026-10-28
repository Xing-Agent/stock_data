"""
拆股闸 —— 已知「数据里没记录的拆股/合股」清单与处理方式。

大白话:有 8 根 K 线的价格凭空跳了一下,不是真的涨跌,是拆股或合股
没被数据源记进去。跑任何回测之前必须先把这 8 根处理掉,
不然引擎会把「10 合 1 导致价格 ×10」当成一天涨了 900%。

处理方式只有两种(硬纪律第 5 条:必须修正或剔除):
  ratio_fix      —— 按比例把跳变日之前的全部价格乘上系数,把序列接回去
  exclude_symbol —— 整只票从池子里剔除(不确定到底是拆股还是真暴跌时用这个)

★ 其中 AMRS 2023-08-10 和 PRTY 2019-11-07 这两根,数据和「拆股」这个
  解释是矛盾的(成交量当天放大 7~15 倍,而且都踩在公司重大事件上:
  Amyris 2023-08-09 申请破产保护、Party City 2019-11-07 财报暴跌)。
  真拆股当天成交量通常不会这样放大。
  既然判不准,这里默认 exclude_symbol —— 两个方向的污染都不要:
  当成拆股修会抹掉一次真实的 −67% / −80% 亏损(把成绩做得好看),
  当成暴跌不修又会凭空造出一次巨亏。
  ★ 这条需要 Lin 拍板。改 action 就能切换,不用改代码。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Action = Literal["ratio_fix", "exclude_symbol"]


@dataclass(frozen=True)
class SplitEvent:
    symbol: str
    date: str
    # ratio = 事件当天价格 / 事件前一天价格 的理论值。
    # 10 合 1 → 价格 ×10 → ratio = 10;1 拆 5 → 价格 ÷5 → ratio = 0.2
    ratio: float
    label: str
    action: Action
    note: str = ""


# 清单由 Lin 给出,比例已逐根对着数据核过(见 note 里的实测跳变倍数)
KNOWN_UNRECORDED_SPLITS: tuple[SplitEvent, ...] = (
    SplitEvent("ACOR", "2021-11-30", 10.0, "10合1", "ratio_fix",
               "实测跳变 9.62x,与 10 合 1 一致,成交量未异常放大"),
    SplitEvent("ACOR", "2023-06-05", 20.0, "20合1", "ratio_fix",
               "实测跳变 20.5x,与 20 合 1 一致"),
    SplitEvent("AMRS", "2023-08-10", 0.2, "1拆5", "exclude_symbol",
               "实测跳变 0.192x 虽接近 1/5,但当天成交量 30M→205M,"
               "且 2023-08-09 Amyris 申请破产保护 —— 判不准,默认剔除"),
    SplitEvent("PROP", "2020-05-14", 4.0, "4合1", "ratio_fix",
               "实测跳变 4.00x,成交量极低(几百股),与合股一致"),
    SplitEvent("PRTY", "2019-11-07", 1 / 3, "1拆3", "exclude_symbol",
               "实测跳变 0.328x 虽接近 1/3,但当天成交量 2.7M→42.9M,"
               "且 Party City 当日财报暴跌 —— 判不准,默认剔除"),
    SplitEvent("SQBG", "2020-07-27", 1200.0, "1200合1", "ratio_fix",
               "实测跳变 1209x,与 1200 合 1 一致"),
    SplitEvent("UHAL", "2022-11-10", 0.1, "1拆10", "ratio_fix",
               "实测跳变 0.1013x,与 1 拆 10 一致"),
    SplitEvent("WPG", "2020-12-22", 8.0, "8合1", "ratio_fix",
               "实测跳变 7.82x,与 8 合 1 一致"),
)

EXCLUDED_SYMBOLS: frozenset[str] = frozenset(
    e.symbol for e in KNOWN_UNRECORDED_SPLITS if e.action == "exclude_symbol"
)

FIX_EVENTS: tuple[SplitEvent, ...] = tuple(
    e for e in KNOWN_UNRECORDED_SPLITS if e.action == "ratio_fix"
)


def events_for(symbol: str) -> list[SplitEvent]:
    return [e for e in FIX_EVENTS if e.symbol == symbol]


def summary() -> str:
    lines = ["拆股闸清单(8 根已知未记录的拆股/合股):"]
    for e in KNOWN_UNRECORDED_SPLITS:
        lines.append(f"  {e.symbol:5s} {e.date}  {e.label:10s} -> {e.action:14s} | {e.note}")
    lines.append(f"因判不准而剔除的票:{sorted(EXCLUDED_SYMBOLS) or '无'}")
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
