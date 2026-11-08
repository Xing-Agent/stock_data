# -*- coding: utf-8 -*-
"""★ 1108:挂件 32 臂按规矩㊾ 重判。随机砍单 1000 次的明细原来只存了前 20 次 → 重跑挂件臂 + 随机砍单(同一个种子 777,
结果与昨晚逐位一致才算数 —— 自证写进每个文件),再用分位数判法。"""
import gc, io, json, os, sys, time
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
import 跑22年_1107 as J
T, P = J.T, J.P
for 名, cfgp, 时间点 in J.宿主:
    d = os.path.join(J.RES, 名)
    todo = [x for x in J.挂件表(时间点) if "★②随机砍单对照(1000次·分位数·规矩㊾)" not in json.load(io.open(os.path.join(d, f"B_{x[0]}.json"), encoding="utf-8"))]
    if not todo:
        print("⟳", 名, flush=True); continue
    raw = T.读配置(cfgp); m, _ = T.建矩阵(raw); base, _, _ = T.跑(raw, m)
    for 件, fn, 原因 in todo:
        p = os.path.join(d, f"B_{件}.json"); old = json.load(io.open(p, encoding="utf-8"))
        lk, _, _ = T.跑(fn(raw), m)
        真 = J.摘(P.配对比(base, lk, 原因))
        随 = J.随机砍单_流水级(base, lk, 原因, J.N砍)
        旧20 = [round(x["收益差pct"], 9) for x in old["随机砍单前20次"]]
        新20 = [round(x["收益差pct"], 9) for x in 随[:20]]
        old["★①配对检验(同进场逐笔)"] = 真
        old["★②随机砍单对照(1000次·分位数·规矩㊾)"] = {指: T.噪声判(真[指], [x[指] for x in 随]) for 指 in ("收益差pct", "替身差pct")}
        old["★自证_与昨晚前20次逐位一致"] = (旧20 == 新20)
        old["随机砍单全部_收益差pct"] = [round(x["收益差pct"], 6) for x in 随]
        io.open(p, "w", encoding="utf-8").write(json.dumps(old, ensure_ascii=False, indent=1, default=str))
        print(f"  ✓ {名} {件} 一致={旧20 == 新20} 判={old['★②随机砍单对照(1000次·分位数·规矩㊾)']['收益差pct']['★判'][:12]}", flush=True)
    del m; gc.collect()
print("★ 挂件重判完", flush=True)
