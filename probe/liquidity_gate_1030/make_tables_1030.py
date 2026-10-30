#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""读 gate_results_1030.json,出报告要用的几张表。只读,不重跑。"""
from __future__ import annotations

import json
import os

OUT = os.path.dirname(os.path.abspath(__file__))
D = json.load(open(os.path.join(OUT, "gate_results_1030.json"), encoding="utf-8"))

MIN_TRADES = 30
# 按链那一节用的是引擎自己的账户:100 万美元 / 单笔 10% → 计划仓位 10 万
PLAN = D["引擎仓位口径"]["单笔计划仓位美元"]
XS = ["10", "20", "50", "100", "200", "500", "1000"]

base = D["基线_全库"]
print("=" * 78)
print("一 · 基线(全库 183 文件 / 146,991 笔 / 182 条有成交的链)")
print(f"  每笔净R均值 {base['每笔净R均值']:.4f} · 名义加权总收益率 "
      f"{base['名义加权总收益率']:.4%} · 占用资金年化 "
      f"{base['占用资金年化收益率']:.4%} · 胜率 {base['胜率']:.2%}")
sig = D["信号数"]
print(f"  信号数(纪律5):有漏斗的 {sig['有信号数的链数']} 条链合计 "
      f"{sig['信号数合计']:,} 个合格进场信号 → 成交 {sig['这些链的成交笔数']:,} 笔"
      f"(成交率 {sig['成交率']:.1%})")

# ---------------------------------------------------------------- 门槛折叠
print("\n" + "=" * 78)
print("二 · ★ 网格其实是一维的:挡掉比例只认「门槛美元数 = X × 账户 × 单笔比例」")
seen = {}
for r in D["网格"]:
    seen.setdefault(round(r["门槛_日均成交额美元"]), []).append(
        (r["账户规模"], r["单笔仓位比例"], r["X"], r["定义A_挡掉比例"]))
print(f"  {len(D['网格'])} 行网格里只有 {len(seen)} 个不同的门槛值;同一门槛的行数字完全一样。")
for thr in sorted(seen)[:4]:
    combos = seen[thr]
    if len(combos) > 1:
        s = " = ".join(f"X{c[2]}@{c[0]/1e6:g}M/{c[1]*100:g}%" for c in combos)
        print(f"   门槛 ${thr:,}: {s}  → 都挡掉 {combos[0][3]:.2%}")

# ---------------------------------------------------------------- 分档
print("\n" + "=" * 78)
print("三 · 按大/中/小分档(门槛美元 → 各档挡掉比例;老池 300 只的流水)")
print(f"{'门槛ADV($)':>14} {'全库挡掉':>9} {'大':>7} {'中':>7} {'小':>7} {'未映射':>8}")
done = set()
for r in sorted(D["网格"], key=lambda x: x["门槛_日均成交额美元"]):
    thr = round(r["门槛_日均成交额美元"])
    if thr in done:
        continue
    done.add(thr)
    tb = r["定义A_按分档挡掉"]
    g = lambda k: (f"{tb[k]['挡掉比例']*100:6.1f}%" if k in tb else "     na")
    print(f"{thr:14,} {r['定义A_挡掉比例']*100:8.2f}% "
          f"{g('大')} {g('中')} {g('小')} {g('未映射')}")

# ---------------------------------------------------------------- 收益怎么变
print("\n" + "=" * 78)
print("四 · ★★★ 挡掉之后收益怎么变(全库口径)")
print(f"{'门槛ADV($)':>14} {'挡掉%':>7} {'剩余笔数':>9} {'每笔净R':>9} {'R变化':>8} "
      f"{'占用年化':>9} {'年化变化':>9} {'挡掉那部分占总净盈亏':>12}")
done = set()
for r in sorted(D["网格"], key=lambda x: x["门槛_日均成交额美元"]):
    thr = round(r["门槛_日均成交额美元"])
    if thr in done:
        continue
    done.add(thr)
    rr, an = r["定义A_剩余_每笔净R"], r["定义A_剩余_占用资金年化"]
    cp = r["定义A_挡掉部分占总净盈亏比例"]
    dR = (rr - base["每笔净R均值"]) / abs(base["每笔净R均值"])
    dA = (an - base["占用资金年化收益率"]) / abs(base["占用资金年化收益率"])
    print(f"{thr:14,} {r['定义A_挡掉比例']*100:6.2f}% {r['定义A_剩余笔数']:9,} "
          f"{rr:9.4f} {dR*100:+7.1f}% {an*100:8.2f}% {dA*100:+8.1f}% "
          f"{cp*100:11.1f}%")

# ---------------------------------------------------------------- 定义 A vs B
print("\n" + "=" * 78)
print("五 · 两种口径对照(定义A:仓位=账户×比例,固定;定义B:用引擎每笔实际计划仓位)")
print(f"{'账户/比例':>14} {'X':>5} {'A挡掉%':>8} {'B挡掉%':>8} {'A剩余R':>8} {'B剩余R':>8}")
for r in D["网格"]:
    if r["账户规模"] == 1e6 and r["单笔仓位比例"] == 0.10:
        print(f"{'1M/10%':>14} {r['X']:5} {r['定义A_挡掉比例']*100:7.2f}% "
              f"{r['定义B_挡掉比例']*100:7.2f}% {r['定义A_剩余_每笔净R']:8.4f} "
              f"{r['定义B_剩余_每笔净R']:8.4f}")

# ---------------------------------------------------------------- 按链
print("\n" + "=" * 78)
print(f"六 · ★★ 按策略链(账户 100 万 / 单笔 10% → 计划仓位 ${PLAN:,.0f};X=10 即门槛 $1M)")
ch = D["按链"]
rows = []
for c, e in ch.items():
    rows.append((c, e["基线"]["笔数"], e["基线"]["每笔净R均值"], e["按X"]))

# 6a 几乎不受影响 vs 被挡掉大半(以 X=100 ,即 1% 单日参与率 为准)
X_REF = "100"
scored = [(r[0], r[1], r[3][X_REF]["挡掉比例"], r[3][X_REF]["剩余笔数"], r[2],
           r[3][X_REF]["剩余_每笔净R"]) for r in rows]
scored.sort(key=lambda x: -x[2])
print(f"\n6a · 在 X=100(门槛 $10M)下【被挡掉最多】的 15 条链:")
print(f"{'挡掉%':>7} {'原笔数':>7} {'剩余':>6} {'原每笔R':>9} {'剩余每笔R':>10}  链")
for c, n0, b, nk, r0, r1 in scored[:15]:
    print(f"{b*100:6.1f}% {n0:7,} {nk:6,} {r0:9.4f} "
          f"{(f'{r1:10.4f}' if r1 is not None else '        na')}  {c}")
print(f"\n6b · 在 X=100 下【几乎不受影响】(挡掉 < 1%)的链数:"
      f"{sum(1 for s in scored if s[2] < 0.01)} / {len(scored)}")
print(f"     挡掉 > 50% 的链数:{sum(1 for s in scored if s[2] > 0.5)}")
print(f"     挡掉 > 90% 的链数:{sum(1 for s in scored if s[2] > 0.9)}")

# ---------------------------------------------------------------- 活不下来的链
print("\n" + "=" * 78)
print(f"七 · ★★★ 哪些链在任何合理的 X 下都活不下来(样本门槛 {MIN_TRADES} 笔)")
print("   「最松的合理 X」= 10 —— 等价于「一天之内按当日成交额 10% 的参与率清仓」,")
print("   比这更松就等于承认自己要吃掉当天超过一成的成交量。")
dead_at = {}
for X in XS:
    dead = [(c, e["基线"]["笔数"], e["按X"][X]["剩余笔数"])
            for c, e in ch.items() if e["按X"][X]["剩余笔数"] < MIN_TRADES]
    dead_at[X] = dead
    print(f"   X={X:>4}(门槛 ${int(X)*PLAN:>13,.0f}):"
          f" {len(dead):3d} / {len(ch)} 条链剩余 < {MIN_TRADES} 笔")

print(f"\n7a · 连 X=10 都活不下来的链(原本就 < {MIN_TRADES} 笔的单独标出):")
base_small = {c for c, e in ch.items() if e["基线"]["笔数"] < MIN_TRADES}
for c, n0, nk in sorted(dead_at["10"], key=lambda x: x[2]):
    tag = "(本来就不足 30 笔)" if c in base_small else "★ 本来够、被流动性门槛打没了"
    print(f"   原 {n0:5,} 笔 → 剩 {nk:4,} 笔  {tag}  {c}")

print(f"\n7b · X=100(1% 单日参与率)下活不下来的链:{len(dead_at['100'])} 条;"
      f"其中本来笔数就够的 "
      f"{sum(1 for c,_,_ in dead_at['100'] if c not in base_small)} 条")

# ---------------------------------------------------------------- 全池前瞻
print("\n" + "=" * 78)
print("八 · ★ 前瞻:换到新全量池(每年约 6,000 只)会更狠")
print("   新池各档 60 日日均成交额(美元)分位:")
for t in ("大", "中", "小"):
    q = D["全池前瞻"][t]["分位"]
    print(f"   {t}({D['全池前瞻'][t]['只数年次']:,} 只×年): "
          + ", ".join(f"{k}={v:,.0f}" for k, v in q.items()))
print("\n   各门槛下新池里『买不进去』的只×年比例:")
print(f"{'门槛ADV($)':>14} {'全池':>8} {'大':>8} {'中':>8} {'小':>8}")
pb = D["全池前瞻_不可交易比例"]
seen2 = {}
for k, v in pb.items():
    A = float(k.split("|")[0].split("=")[1])
    p = float(k.split("|")[1].split("=")[1])
    X = float(k.split("|")[2].split("=")[1])
    seen2[round(X * A * p)] = v
for thr in sorted(seen2):
    v = seen2[thr]
    print(f"{thr:14,} {v['全池']*100:7.1f}% {v['大']*100:7.1f}% "
          f"{v['中']*100:7.1f}% {v['小']*100:7.1f}%")
