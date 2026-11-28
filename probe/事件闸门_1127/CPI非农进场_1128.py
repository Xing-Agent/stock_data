# -*- coding: utf-8 -*-
"""事件闸门第三测：CPI、非农公布日前后进场的单子。引擎外，只读现成流水。
日期表 = 数据组《515》（BLS 新闻稿存档，168 行逐行和日程页核过）。两样都是美东 08:30 开盘前公布，所以「公布前一天进场」的单子会吃到公布日的开盘跳空。
单子 = 技术类策略 2015–2021 已平单子（平仓日 ≤ 2021-12-31）。分组和议息日那份一样：公布日当天进场 / 前 1 天 / 前 1~2 天 / 前 3~5 天 / 其余。"""
import pandas as pd, numpy as np, glob, os, sys
H = os.path.dirname(os.path.abspath(__file__)); R = os.path.dirname(os.path.dirname(H)); A = os.path.join(R, 'probe/成绩单_1122/out_手册/')
L = []
for f in sorted(glob.glob(A + '流水_一_*.csv')):
    nm = os.path.basename(f)[5:-4]
    if nm.startswith('buy_and_hold'): continue
    t = pd.read_csv(f, parse_dates=['entry_date', 'exit_date']); t = t[t.exit_date <= '2021-12-31']; t['策略'] = nm; L.append(t)
T0 = pd.concat(L, ignore_index=True); e = T0.entry_date.values.astype('datetime64[D]'); x = T0.exit_date.values.astype('datetime64[D]')
def 概(d):
    r = d.r_multiple_net
    return dict(笔数=len(d), 每笔平均R=round(r.mean(), 3), 赚钱笔占比=round((r > 0).mean() * 100, 1), 最差一成平均R=round(r[r <= r.quantile(0.1)].mean(), 2), 亏超过1点5R的占比=round((r < -1.5).mean() * 100, 1),
                跳空打穿止损占比=round(d.gap_through.astype(str).str.lower().eq('true').mean() * 100, 1), 持仓天数中位=int(d.holding_days.median()))
out = []
for 名, 文件 in (("CPI", "CPI_发布日期_2015到2021.csv"), ("非农", "非农_发布日期_2015到2021.csv")):
    F = np.sort(pd.to_datetime(pd.read_csv(os.path.join(H, 文件), encoding='utf-8-sig').release_date).values.astype('datetime64[D]')); assert len(F) == 84
    T = T0.copy(); k = np.searchsorted(F, e, side='left'); ok = k < len(F); nxt = np.where(ok, F[np.minimum(k, len(F) - 1)], np.datetime64('2099-01-01'))
    T['隔'] = np.where(ok, np.busday_count(e, nxt), 999); T['拿过'] = x >= nxt
    for 组, m in (("公布日当天进场", T.隔 == 0), ("公布前 1 天进场", (T.隔 == 1) & T.拿过), ("公布前 1~2 天进场", T.隔.between(1, 2) & T.拿过), ("公布前 3~5 天进场", T.隔.between(3, 5) & T.拿过), ("公布前 6~15 天进场", T.隔.between(6, 15) & T.拿过), ("其余全部", ~((T.隔 <= 5) & (T.拿过 | (T.隔 == 0))))):
        out.append(dict(事件=名, 哪一组=组, **概(T[m])))
    for a, b in (("2015", "2018"), ("2019", "2021")):
        d = T[(T.entry_date >= a) & (T.entry_date <= b + "-12-31")]
        print(名, a, b, {n: (int(m.sum()), round(d[m].r_multiple_net.mean(), 3), round(d[m].gap_through.astype(str).str.lower().eq('true').mean() * 100, 1), round((d[m].r_multiple_net < -1.5).mean() * 100, 1)) for n, m in (("当天", d.隔 == 0), ("前1天", (d.隔 == 1) & d.拿过), ("其余", ~((d.隔 <= 5) & (d.拿过 | (d.隔 == 0)))))})
    S = T[T.holding_days <= 3]; print(名, "只看拿 3 天以内的：", {n: (int(m.sum()), round(S[m].r_multiple_net.mean(), 3), round((S[m].r_multiple_net < -1.5).mean() * 100, 1), round(S[m].gap_through.astype(str).str.lower().eq('true').mean() * 100, 1)) for n, m in (("公布日当天或前 1 天进场", S.隔 <= 1), ("其余", S.隔 > 1))})
O = pd.DataFrame(out); O.to_csv(os.path.join(H, 'out', 'CPI非农进场_汇总.csv'), index=False); pd.set_option('display.width', 250); print("单子总数", len(T0)); print(O.to_string(index=False))
