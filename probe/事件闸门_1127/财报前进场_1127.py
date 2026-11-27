# -*- coding: utf-8 -*-
"""事件闸门第一测：财报前几天进场的单子，是不是更差、更容易被跳空打穿止损。引擎外，只读现成的流水。
流水 = 成绩单_1122 里技术类策略 2015–2021 的全部单子（2022 年以后封存不读）；财报日 = SEC 8-K 2.02 的首个可交易日（2014 年起）。
「财报前 N 天进场」= 进场日到下一次财报的首个可交易日，隔了 1..N 个交易日（另试 N = 1、3、5），并且这笔单子拿过了那一天。
对照 = 同一批策略里，持仓期间没有碰到财报的单子；以及进场离财报 6~20 个交易日、同样拿过了财报的单子。"""
import pandas as pd, numpy as np, glob, os
R = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))); A = os.path.join(R, 'probe/成绩单_1122/out_手册/')
cal = pd.read_csv(os.path.join(R, 'probe/fund_expand_1103/earnings_calendar_8k202_1103.csv.gz'), usecols=['symbols', 'effective_trade_date', 'is_main_release'])
cal = cal[cal.is_main_release.astype(str).str.lower() == 'true']; cal['d'] = pd.to_datetime(cal.effective_trade_date); E = {s: np.sort(g.d.values) for s, g in cal.groupby('symbols')}
L = []
for f in sorted(glob.glob(A + '流水_一_*.csv')):
    nm = os.path.basename(f)[5:-4]
    if nm.startswith('buy_and_hold'): continue
    t = pd.read_csv(f, parse_dates=['entry_date', 'exit_date']); t = t[t.exit_date <= '2021-12-31']; t['策略'] = nm; L.append(t)
T = pd.concat(L, ignore_index=True); T = T[T.symbol.isin(E.keys())].copy()
def 隔(r):
    e = E[r.symbol]; k = np.searchsorted(e, np.datetime64(r.entry_date), side='right')
    if k >= len(e): return np.nan
    return np.busday_count(np.datetime64(r.entry_date, 'D'), np.datetime64(e[k], 'D')) if e[k] <= np.datetime64(r.exit_date) else 999   # 999 = 这笔单子没拿到下一次财报
T['隔'] = T.apply(隔, axis=1); T = T.dropna(subset=['隔']); T['止损宽'] = T.risk_per_share / T.entry_price
窄线 = T.groupby('策略').止损宽.transform('median'); T['窄'] = T.止损宽 <= 窄线
def 概(x):
    r = x.r_multiple_net
    return dict(笔数=len(x), 每笔平均R=round(r.mean(), 3), 赚钱笔占比=round((r > 0).mean() * 100, 1), 最差一成平均R=round(r[r <= r.quantile(0.1)].mean(), 2), 亏超过1点5R的占比=round((r < -1.5).mean() * 100, 1),
                跳空打穿止损占比=round(x.gap_through.astype(str).str.lower().eq('true').mean() * 100, 1), 持仓天数中位=int(x.holding_days.median()))
rows = []
for 名, m in (("没碰到财报", T.隔 == 999), ("财报前 1 天进场", T.隔.between(1, 1)), ("财报前 1~3 天进场", T.隔.between(1, 3)), ("财报前 1~5 天进场", T.隔.between(1, 5)), ("财报前 6~20 天进场", T.隔.between(6, 20)), ("财报前 21 天以上进场", (T.隔 > 20) & (T.隔 < 999))):
    for 档, mm in (("全部", slice(None)), ("止损窄的一半", T.窄), ("止损宽的一半", ~T.窄)):
        x = T[m][mm[m]] if not isinstance(mm, slice) else T[m]
        rows.append(dict(哪一组=名, 止损=档, **概(x)))
O = pd.DataFrame(rows); O.to_csv(os.path.join(R, 'probe/事件闸门_1127/out/财报前进场_汇总.csv'), index=False)
pd.set_option('display.width', 250); print("单子总数", len(T), "策略数", T.策略.nunique(), "时间", T.entry_date.min().date(), "~", T.entry_date.max().date()); print(O.to_string(index=False))
# 分两段看方向稳不稳
for a, b in (("2015", "2018"), ("2019", "2021")):
    x = T[(T.entry_date >= a) & (T.entry_date <= b + "-12-31")]
    print(a, b, {k: (len(x[m]), round(x[m].r_multiple_net.mean(), 3)) for k, m in (("没碰到", x.隔 == 999), ("前1~3天", x.隔.between(1, 3)), ("前6~20天", x.隔.between(6, 20)))})
# 按策略族看
T['族'] = T.策略.str.extract(r'^(技-\d+|trend_following)')[0]
g = T.groupby('族').apply(lambda x: pd.Series(dict(没碰到=round(x[x.隔 == 999].r_multiple_net.mean(), 3), 前1到3天=round(x[x.隔.between(1, 3)].r_multiple_net.mean(), 3), 前1到3天笔数=int(x.隔.between(1, 3).sum()), 前6到20天=round(x[x.隔.between(6, 20)].r_multiple_net.mean(), 3))))
print(g.to_string()); g.to_csv(os.path.join(R, 'probe/事件闸门_1127/out/按策略族.csv'))
