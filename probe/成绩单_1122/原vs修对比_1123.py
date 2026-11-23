# -*- coding: utf-8 -*-
"""只读：对比「原」out_手册/成绩单_二_* 与「套49处坏点修正」out_手册_修/成绩单_二_*。
不重跑任何回测。输出 out_手册_修/原vs修_1123.csv。主路 11-23 第四十四轮（《424》）。"""
import json, io, os, glob, csv
HERE = os.path.dirname(os.path.abspath(__file__))
rows = []
for f in sorted(glob.glob(os.path.join(HERE, 'out_手册_修', '成绩单_二_*.json'))):
    b = os.path.basename(f); o = os.path.join(HERE, 'out_手册', b)
    if not os.path.exists(o): continue
    A = json.load(io.open(o, encoding='utf-8'))['结果']
    B = json.load(io.open(f, encoding='utf-8'))['结果']
    n = b[len('成绩单_二_'):-5]
    da = A['策略']['每年赚pct'] - A['同样仓位的标普']['每年赚pct']
    db = B['策略']['每年赚pct'] - B['同样仓位的标普']['每年赚pct']
    rows.append(dict(名=n, 原年化=A['策略']['每年赚pct'], 修年化=B['策略']['每年赚pct'],
                     年化差=round(B['策略']['每年赚pct'] - A['策略']['每年赚pct'], 2),
                     原笔数=A['策略']['笔数'], 修笔数=B['策略']['笔数'],
                     原对同仓标普=round(da, 2), 修对同仓标普=round(db, 2),
                     翻号='是' if (da > 0) != (db > 0) else '否'))
out = os.path.join(HERE, 'out_手册_修', '原vs修_1123.csv')
with io.open(out, 'w', encoding='utf-8', newline='') as fh:
    w = csv.DictWriter(fh, fieldnames=list(rows[0].keys())); w.writeheader(); w.writerows(rows)
print('已对比', len(rows), '条 →', out)
print('翻号的：', [r['名'] for r in rows if r['翻号'] == '是'])
