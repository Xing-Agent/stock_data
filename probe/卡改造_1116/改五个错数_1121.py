#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""改那五个错数 · 两段扫 · 默认只演不改（--apply 才真写）
【本次口径】全收益 adj_close · 摩擦档 不适用（只改文本）· 窗口 2015-01-02~2025-12-31
  · 池 不适用 · 标签滞后 不适用
段一：42 份 references/shared/common_boundaries.md（md5 须唯一）
段二：49 份 references/entries/*.md 里那一句（句式唯一，当场断言）
🔴 57% 不在本脚本里 —— 等 Lin 定 甲/乙/丙
"""
import os,io,sys,hashlib,collections
ROOT="/home/claude/stock_data/skills_v2"
APPLY="--apply" in sys.argv
CB_MD5_EXPECT="eb438616e18e9556c333222169e671e6"
CB_N_EXPECT=42; ENTRY_N_EXPECT=49
CB_REP=[("+14.55%/年","+13.47%/年"),("涨 14.55%/年","涨 13.47%/年"),
        ("**-34.1%**","**-33.7%**"),("**2.0 年**","**1.94 年**"),
        ("**-0.38%**","**+1.33%**"),("**0.36%**","**0.362%**")]
ENTRY_OLD="> 个人要坐过 **-34.1%** 回撤、**2.0 年**不创新高，也极少有人做到。"
ENTRY_NEW="> 个人要坐过 **-33.7%** 回撤、**1.94 年**不创新高，也极少有人做到。"
cb,entries=[],[]
for r,d,fs in os.walk(ROOT):
    for fn in fs:
        fp=os.path.join(r,fn)
        if fp.endswith("references/shared/common_boundaries.md"): cb.append(fp)
        elif fn.endswith((".md",".json",".yaml",".yml",".txt")):
            s=io.open(fp,encoding="utf-8",errors="ignore").read()
            if ENTRY_OLD in s: entries.append(fp)
md5s=collections.Counter(hashlib.md5(io.open(f,"rb").read()).hexdigest() for f in cb)
print(f"段一 common_boundaries: {len(cb)} 份 · md5 种类 {len(md5s)} · {md5s.most_common(1)[0][0]}")
assert len(cb)==CB_N_EXPECT, f"🔴 份数不是 {CB_N_EXPECT}：{len(cb)}"
assert len(md5s)==1 and list(md5s)[0]==CB_MD5_EXPECT, "🔴 md5 不唯一或不符 → 停"
print(f"段二 策略条目那一句: {len(entries)} 份")
assert len(entries)==ENTRY_N_EXPECT, f"🔴 份数不是 {ENTRY_N_EXPECT}：{len(entries)}"
src=io.open(cb[0],encoding="utf-8").read(); new=src
for a,b in CB_REP:
    n=new.count(a); assert n>0, f"🔴 段一找不到 {a}"; new=new.replace(a,b)
for p in ["14.55","-34.1%","2.0 年","-0.38%"]:
    assert p not in new, f"🔴 段一改完还残留 {p}"
print(f"段一 diff 行 {sum(1 for a,b in zip(src.splitlines(),new.splitlines()) if a!=b)} · 新 md5 {hashlib.md5(new.encode()).hexdigest()}")
if not APPLY:
    print("\n✅ 只演不改（演完没动任何文件）。真改：加 --apply"); sys.exit(0)
for f in cb: io.open(f,"w",encoding="utf-8").write(new)
for f in entries:
    s=io.open(f,encoding="utf-8").read(); io.open(f,"w",encoding="utf-8").write(s.replace(ENTRY_OLD,ENTRY_NEW))
bad=0
for r,d,fs in os.walk(ROOT):
    for fn in fs:
        if not fn.endswith((".md",".json",".yaml",".yml",".txt")): continue
        s=io.open(os.path.join(r,fn),encoding="utf-8",errors="ignore").read()
        for p in ["14.55","-34.1%","2.0 年","-0.38%"]:
            if p in s: print("🔴 残留",p,os.path.join(r,fn)); bad+=1
print(f"\n{'✅ 复量到 0' if bad==0 else '🔴 残留 '+str(bad)+' 处'} · 段一 {len(cb)} 份 · 段二 {len(entries)} 份 = {len(cb)+len(entries)} 份")
sys.exit(1 if bad else 0)
