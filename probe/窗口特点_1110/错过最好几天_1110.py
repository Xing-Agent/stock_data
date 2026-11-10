# -*- coding: utf-8 -*-
"""★★★★★ 「这十一年几乎没人真拿到 14.55%」的实测依据 —— ★ Lin 1110 12:24 要的那句硬话。

★★ 三秒版：11 年 2,765 个交易日里，**涨最多的 10 天贡献了全程涨幅的 57%**，
   ★★★ 而那 10 天**全在暴跌里**（★ 七天挤在 2020 年 3 月）。
   ★★★★★ 错过其中 30 天，十一年年化从 +11.53% 变成 **-0.38%**。

★★ 它证的是**机制**（要拿到这个数，你得在最恐慌那几天满仓不动），
   ★★★★★ **不是**「这十年比其他十年特别」—— ★ 那个我们证不了：
   本机 SPY 日线只从 2014-01-02 开始，算不了 2004-2014、2000-2010。
★ 结论写进《156》第 5 条;★★ 本脚本留着是为了 V3 能复现，不用重新想。
"""
from __future__ import annotations
import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, ROOT)
from engine import data as D   # noqa: E402

起, 止 = "2015-01-01", "2025-12-31"


def main() -> int:
    c = D.load_benchmark("SPY")["close"]
    s = c[(c.index >= 起) & (c.index <= 止)]
    r = s.pct_change().dropna()
    yrs = (s.index[-1] - s.index[0]).days / 365.25
    年化 = lambda x: (1 + x).prod() ** (1 / yrs) - 1
    print(f"★ 口径：SPY 日线 {s.index[0].date()} ~ {s.index[-1].date()} · "
          f"**{len(r)} 个交易日 · {yrs:.1f} 年**")
    print(f"★★ 覆盖起点：{c.index.min().date()} —— ★★★★★ 本机只到这里，"
          f"所以**算不了 2004-2014、2000-2010**\n")
    print(f"{'情形':<26}{'总倍数':>9}{'年化':>10}")
    print(f"{'全程不动':<26}{(1 + r).prod():>8.2f}x{年化(r) * 100:>9.2f}%")
    for n in (5, 10, 20, 30, 50):
        去 = r.drop(r.nlargest(n).index)
        print(f"{'错过涨最多的 ' + str(n) + ' 天':<24}{(1 + 去).prod():>8.2f}x{年化(去) * 100:>9.2f}%")
    十 = r.nlargest(10)
    print(f"\n★★★ 涨最多的 10 天合计 **{(十 + 1).prod():.2f}x** = "
          f"全程涨幅的 **{(十 + 1).prod() / (1 + r).prod() * 100:.0f}%**")
    print(f"★★ 它们只占全部交易日的 **{10 / len(r) * 100:.2f}%**")
    print(f"★ 日期：{[str(d.date()) for d in 十.index]}")
    print("\n★★★★★ 自证：如果上面那 10 天**不是**集中在暴跌期，这个解释就不成立 ——")
    print(f"   ★ 这 10 天当天前后各 5 日的 SPY 累计：")
    for d in 十.index:
        w = r[(r.index >= d - __import__('pandas').Timedelta(days=12))
              & (r.index <= d + __import__('pandas').Timedelta(days=12))]
        print(f"     {d.date()}  当天 {十[d] * 100:+.2f}%  · 前后约 12 日累计 {((1 + w).prod() - 1) * 100:+.1f}%")
    print("\n★★ 没查到的：**这不证明「这十年比其他十年特别」** —— 只证明"
          "「要拿到这个数，必须在最恐慌那几天满仓不动」。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
