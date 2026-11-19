exec(open('top4h.py').read().split("for allow in")[0])
for need in ['any2',('sfp','div','dist'),('div','dist'),('sfp','dist')]:
    x=go4(f'4小时·上涨里顶部空·{need}',need=need,allow=('上涨',),box_n=120)
    o=x[x.t<'2026-06']
    print('    按年:',' | '.join(f"{y}:{len(g)}笔{g.R.mean():+.2f}" for y,g in x.groupby('y')))
    print('    分票:',' | '.join(f"{k}:{len(g)}笔{g.R.mean():+.2f}" for k,g in o.groupby('票')))
for b in [60,90,180]:
    go4(f'4小时·上涨里顶部空·any2·箱体{b}',need='any2',allow=('上涨',),box_n=b)
x=go4('全行情·any2',need='any2',allow=('上涨','震荡','下跌'),box_n=120)
