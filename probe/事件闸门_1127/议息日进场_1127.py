# -*- coding: utf-8 -*-
"""事件闸门第二测：议息日（美联储公布利率决定那天）前后进场的单子，是不是更差、更容易被打穿止损。引擎外，只读现成流水。
日期表 = 同目录 议息日_日期表_2015到2021.csv（美联储官网历年会议页，取每次会议的第二天；2020-03-03 是临时会议，2020-03-15 周日的临时会议记在下一个交易日 03-16）。
单子 = 技术类策略 2015–2021 全部已平单子（按平仓日 ≤ 2021-12-31）。分组：进场日相对议息日的位置（另试 前 1 天 / 前 1~2 天 / 当天），并且单子拿过了议息日。"""
import pandas as pd, numpy as np, glob, os
H = os.path.dirname(os.path.abspath(__file__)); R = os.path.dirname(os.path.dirname(H)); A = os.path.join(R, 'probe/成绩单_1122/out_手册/')
F = np.sort(pd.to_datetime(pd.read_csv(os.path.join(H, '议息日_日期表_2015到2021.csv')).decision_date).values.astype('datetime64[D]'))
L = []
for f in sorted(glob.glob(A + '流水_一_*.csv')):
    nm = os.path.basename(f)[5:-4]
    if nm.startswith('buy_and_hold'): continue
    t = pd.read_csv(f, parse_dates=['entry_date', 'exit_date']); t = t[t.exit_date <= '2021-12-31']; t['策略'] = nm; L.append(t)
T = pd.concat(L, ignore_index=True); e = T.entry_date.values.astype('datetime64[D]'); x = T.exit_date.values.astype('datetime64[D]')
k = np.searchsorted(F, e, side='left'); ok = k < len(F); nxt = np.where(ok, F[np.minimum(k, len(F) - 1)], np.datetime64('2099-01-01'))
T['隔'] = np.where(ok, np.busday_count(e, nxt), 999); T['拿过'] = x >= nxt                       # 隔 = 0：议息日当天进场
def 概(d):
    r = d.r_multiple_net
    return dict(笔数=len(d), 每笔平均R=round(r.mean(), 3), 赚钱笔占比=round((r > 0).mean() * 100, 1), 最差一成平均R=round(r[r <= r.quantile(0.1)].mean(), 2), 亏超过1点5R的占比=round((r < -1.5).mean() * 100, 1),
                跳空打穿止损占比=round(d.gap_through.astype(str).str.lower().eq('true').mean() * 100, 1), 持仓天数中位=int(d.holding_days.median()))
rows = []
for 名, m in (("议息日当天进场", T.隔 == 0), ("议息日前 1 天进场", (T.隔 == 1) & T.拿过), ("议息日前 1~2 天进场", T.隔.between(1, 2) & T.拿过), ("议息日前 3~5 天进场", T.隔.between(3, 5) & T.拿过), ("议息日前 6~15 天进场", T.隔.between(6, 15) & T.拿过), ("其余全部", ~((T.隔 <= 5) & (T.拿过 | (T.隔 == 0))))):
    rows.append(dict(哪一组=名, **概(T[m])))
O = pd.DataFrame(rows); O.to_csv(os.path.join(H, 'out', '议息日进场_汇总.csv'), index=False); pd.set_option('display.width', 250); print("单子总数", len(T)); print(O.to_string(index=False))
for a, b in (("2015", "2018"), ("2019", "2021")):
    d = T[(T.entry_date >= a) & (T.entry_date <= b + "-12-31")]; print(a, b, {n: (int(m.sum()), round(d[m].r_multiple_net.mean(), 3), round(d[m].gap_through.astype(str).str.lower().eq('true').mean() * 100, 1)) for n, m in (("当天", d.隔 == 0), ("前1~2天", d.隔.between(1, 2) & d.拿过), ("前6~15天", d.隔.between(6, 15) & d.拿过))})
# 只看拿得短的（3 天以内就走的），避开「活得久的单子天生好」这个偏差
S = T[T.holding_days <= 3]; print("只看拿 3 天以内的：", {n: (int(m.sum()), round(S[m].r_multiple_net.mean(), 3), round((S[m].r_multiple_net < -1.5).mean() * 100, 1)) for n, m in (("议息日当天或前 1~2 天进场", S.隔 <= 2), ("其余", S.隔 > 2))})
