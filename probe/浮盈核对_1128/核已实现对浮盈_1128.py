# 引擎外 · 只读：段一(2015–2021)每条技术策略，把「对外报的年化」拆成已实现 / 未平仓浮盈两块
# 用途：查「账面正数全靠没平的持仓撑着」这类条目（《501》technique）。不重跑任何回测。
import pandas as pd, glob, os
d = 'probe/成绩单_1122/out_手册/'
rows = []
for f in sorted(glob.glob(d + '流水_一_*.csv')):
    n = os.path.basename(f)[len('流水_一_'):-4]
    p = d + f'日线_一_{n}.parquet'
    if not os.path.exists(p):
        print('跳过(无日线)', n); continue
    t = pd.read_csv(f); e = pd.read_parquet(p)['eq'][:'2021-12-31']
    c = t[t.exit_date <= '2021-12-31']                                          # 按平仓日挑，和 V2.6.13 口径一致
    o = t[(t.entry_date <= '2021-12-31') & (t.exit_date > '2021-12-31')]        # 2021 年底还拿着
    chg = e.iloc[-1] - e.iloc[0]; real = c.net_pnl.sum(); unreal = chg - real
    yrs = (e.index[-1] - e.index[0]).days / 365.25
    rows.append(dict(策略=n, 每年赚=round(((e.iloc[-1] / e.iloc[0]) ** (1 / yrs) - 1) * 100, 1),
                     已平笔数=len(c), 赚钱笔占比=round((c.r_multiple_net > 0).mean() * 100, 1),
                     止损笔数=int((c.reason == '止损').sum()),
                     已实现对期初=round(real / e.iloc[0] * 100, 1), 还拿着=len(o),
                     浮盈对期初=round(unreal / e.iloc[0] * 100, 1)))
O = pd.DataFrame(rows).sort_values('浮盈对期初', ascending=False)
O.to_csv('probe/浮盈核对_1128/已实现对浮盈_段一_1128.csv', index=False)
print(O.to_string(index=False))
bad = O[(O.已实现对期初 < 0) & (O.每年赚 > 0)]
print(f"\n🔴 已平的单子合计亏钱、却报正年化的：{len(bad)} 条 / 共 {len(O)} 条（buy_and_hold 按定义如此，不算）")
print(bad.to_string(index=False))
