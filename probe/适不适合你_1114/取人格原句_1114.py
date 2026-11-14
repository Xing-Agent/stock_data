#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""★★ 只读:把 40 条里判成「人」(和「钱」)的那几格原句摘出来 —— 不改写、不装闸。
   ★ 名单从《93》自己取;★★ 分类沿用 probe/说明书_1102(1104版) + probe/第10格_1114(本轮版),不重判。"""
import io, os, re, json
ROOT = "/home/claude/stock_data"
LIB  = os.path.join(ROOT, "METHOD_LIBRARY")
台账 = os.path.join(ROOT, "手册/93-策略说明书-全40条-按新尺子-1107.md")

def 取行名单():
    t = io.open(台账, encoding="utf-8").read()
    名单, 见过 = [], set()
    for m in re.finditer(r"^\|\s*\*\*([^ |*]+)\s*·", t, re.M):
        k = m.group(1).strip()
        if k not in 见过:
            见过.add(k); 名单.append(k)
    return 名单

def 行名(k):
    t = io.open(台账, encoding="utf-8").read()
    m = re.search(rf"^\|\s*\*\*{re.escape(k)}\s*·\s*([^|*]+)", t, re.M)
    return m.group(1).strip() if m else "?"

def 读卡(名):
    p = os.path.join(LIB, 名 + ".md")
    if not os.path.exists(p): return {}
    t = io.open(p, encoding="utf-8").read()
    g = {}
    for key in ("什么时候用", "谁不该用", "最难受的时候"):
        m = re.search(rf"^{key}\s+(.+)$", t, re.M)
        if m: g[key] = m.group(1).strip()
    return g

人 = ["技-1","技-2","技-3","技-5","技-7","技-8","技-11",
      "基-1","基-2","基-3","基-4","基-5","基-6","基-8","基-9","基-10","基-11","基-12",
      "基-13","基-15","基-16","基-17","基-18","基-19","基-20","基-21","基-23"]
钱 = ["技-9","基-7","基-14"]

名单 = 取行名单()
assert len(名单) == 40, len(名单)
for k in 人 + 钱:
    assert k in 名单, k
out = {"台账条目数": len(名单), "人": len(人), "钱": len(钱), "条目": []}
for k in 人 + 钱:
    c = 读卡(k)
    out["条目"].append({"条目": k, "类": "人" if k in 人 else "钱", "行名": 行名(k),
                        "谁不该用": c.get("谁不该用",""), "什么时候用": c.get("什么时候用",""),
                        "最难受的时候": c.get("最难受的时候","")})
json.dump(out, io.open("/tmp/claude-0/-home-claude-stock-data/63b407f7-0145-5d0b-836e-1fe793ae608a/scratchpad/人格原句_1114.json","w",encoding="utf-8"), ensure_ascii=False, indent=1)
for r in out["条目"]:
    print(f'[{r["类"]}] {r["条目"]} · {r["行名"]}\n    不该用: {r["谁不该用"]}\n    什么时候用: {r["什么时候用"]}')
