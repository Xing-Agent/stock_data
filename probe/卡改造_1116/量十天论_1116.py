# -*- coding: utf-8 -*-
"""只读量尺：核卡里那句硬话的四个数（57% / 0.36% / 错过30天 -0.38% / 14.55%）
规矩(82)：每个数必须带口径（全收益 or 纯价格）+ 窗口。
三道断言：① 文件读到了 ② 两个口径真的不一样（防「纯价格冒充全收益」）③ 窗口边界对得上
不改任何文件，不装闸。"""
import json, math, sys

P = "pilot_300/benchmarks/SPY/daily.json"
d = json.load(open(P))
bars = d["data"]
assert len(bars) > 2000, f"断言①失败：只读到 {len(bars)} 根"

def pick(start, end):
    rows = [b for b in bars if start <= b["date"] <= end]
    assert rows, f"断言③失败：{start}~{end} 没有数据"
    return rows

def series(rows, field):
    v = [float(b[field]) for b in rows]
    assert all(x > 0 for x in v), "断言①失败：有非正价格"
    return v

def stats(v, label):
    n = len(v)
    yrs = (n - 1) / 252.0
    tot = v[-1] / v[0]
    ann = tot ** (1 / yrs) - 1
    # 最大回撤
    peak, mdd = v[0], 0.0
    # 最长不创新高
    peak_i, longest, longest_span = 0, 0, None
    for i, x in enumerate(v):
        if x >= peak:
            peak = x
            if i - peak_i > longest:
                longest, longest_span = i - peak_i, (peak_i, i)
            peak_i = i
        mdd = min(mdd, x / peak - 1)
    if n - 1 - peak_i > longest:
        longest, longest_span = n - 1 - peak_i, (peak_i, n - 1)
    # 日收益
    r = [v[i] / v[i - 1] - 1 for i in range(1, n)]
    lr = [math.log(1 + x) for x in r]
    top10 = sorted(range(len(lr)), key=lambda i: lr[i], reverse=True)[:10]
    share_log = sum(lr[i] for i in top10) / sum(lr)
    # 定义二：剔掉这 10 天后剩下的涨幅，占全程的多少 -> 贡献 = 1 - 剩/全
    rest = math.exp(sum(lr) - sum(lr[i] for i in top10)) - 1
    share_cmp = 1 - rest / (tot - 1)
    top30 = sorted(range(len(lr)), key=lambda i: lr[i], reverse=True)[:30]
    ex30 = math.exp(sum(lr) - sum(lr[i] for i in top30))
    ann_ex30 = ex30 ** (1 / yrs) - 1
    return dict(口径=label, 交易日=n, 收益日=len(r), 年=round(yrs, 2),
                年化=round(ann * 100, 3), 最大回撤=round(mdd * 100, 1),
                最长不创新高交易日=longest, 最长不创新高年=round(longest / 252.0, 2),
                最长不创新高区间=[v and bars and None] and None,
                span=longest_span,
                十天占全程_对数法=round(share_log * 100, 1),
                十天占全程_剔除法=round(share_cmp * 100, 1),
                十天占交易日=round(10 / len(r) * 100, 3),
                错过最好30天_年化=round(ann_ex30 * 100, 2))

out = {"源文件": P, "adjustment": d.get("adjustment"), "adj_close_basis": d.get("adj_close_basis"), "窗口": {}}
for name, (s, e) in {"卡里声明的十一年_2015到2025": ("2015-01-01", "2025-12-31"),
                     "文件全长_2014到2025": ("2014-01-01", "2025-12-31")}.items():
    rows = pick(s, e)
    price = series(rows, "close")
    totret = series(rows, "adj_close")
    assert abs(price[-1] / price[0] - totret[-1] / totret[0]) > 1e-6, \
        "断言②失败：两个口径一模一样 —— 很可能又在用纯价格冒充全收益"
    a = stats(price, "纯价格")
    b = stats(totret, "全收益")
    for x in (a, b):
        i, j = x.pop("span"); x["最长不创新高区间"] = [rows[i]["date"], rows[j]["date"]]
    out["窗口"][name] = {"起": rows[0]["date"], "止": rows[-1]["date"], "两个口径": [a, b]}

json.dump(out, open("手册/量十天论_1116.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps(out, ensure_ascii=False, indent=1))
